"""E2E verification of AC-001: auth, cookie flags, CSRF, origin & isolation."""

from __future__ import annotations

import json
from pathlib import Path

import aiohttp
import pytest
from gateway_probe.evidence import save_evidence
from gateway_probe.topology import GatewayTopologyHarness
from playwright.async_api import async_playwright


@pytest.mark.asyncio
async def test_ac001_https_login_cookie_flags_csrf_and_viewer_ws_gates(
    tmp_path: Path,
) -> None:
    harness = GatewayTopologyHarness(tmp_path)
    evidence: dict = {}
    try:
        await harness.start()
        # 1. Real Chrome headful navigation to HTTPS entrypoint
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                channel="chrome",
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--ignore-certificate-errors",
                ],
            )
            context = await browser.new_context(
                ignore_https_errors=True,
                viewport={"width": 1280, "height": 720},
            )
            page = await context.new_page()

            # Navigate to the static client root
            await page.goto(harness.origin, wait_until="domcontentloaded")

            # Execute real login via fetch from inside Chrome
            login_resp = await page.evaluate(
                """async (password) => {
                    const res = await fetch('/api/v1/auth/login', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({password})
                    });
                    const data = await res.json();
                    return {status: res.status, data};
                }""",
                harness.admin_password,
            )
            assert login_resp["status"] == 200, f"Login failed: {login_resp}"
            csrf_token = login_resp["data"]["csrf_token"]
            assert csrf_token, "Missing csrf_token in login response"

            # Check context cookies
            cookies = await context.cookies()
            session_cookie = next(
                (c for c in cookies if c["name"] == "cbrowser_session"), None
            )
            assert session_cookie is not None, "cbrowser_session missing"

            evidence["cookie"] = {
                "name": session_cookie["name"],
                "httpOnly": session_cookie["httpOnly"],
                "secure": session_cookie["secure"],
                "sameSite": session_cookie["sameSite"],
            }
            # Assert HttpOnly, Secure, SameSite=Strict
            assert session_cookie["httpOnly"] is True, "Must be HttpOnly"
            assert session_cookie["secure"] is True, "Must be Secure"
            assert str(session_cookie["sameSite"]).lower() == "strict", (
                f"sameSite must be Strict, got {session_cookie['sameSite']}"
            )

            # Master token leak check on login response
            login_json_str = json.dumps(login_resp["data"])
            assert harness.keys["agent"] not in login_json_str
            assert harness.keys["gateway"] not in login_json_str
            assert "turn" not in harness.keys
            assert harness.admin_password not in login_json_str

            # 2. CSRF write protection: write request without CSRF is rejected
            no_csrf_resp = await page.evaluate(
                """async () => {
                    const res = await fetch('/api/v1/profiles', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({name: 'no_csrf_prof'})
                    });
                    return {status: res.status, body: await res.text()};
                }"""
            )
            assert no_csrf_resp["status"] == 403, (
                f"Write without CSRF must return 403, got {no_csrf_resp['status']}"
            )
            evidence["csrf_rejection"] = no_csrf_resp

            # Valid write request with CSRF succeeds
            valid_write_resp = await page.evaluate(
                """async (csrf) => {
                    const res = await fetch('/api/v1/profiles', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                            'X-CSRF-Token': csrf
                        },
                        body: JSON.stringify({name: 'valid_prof'})
                    });
                    return {status: res.status, data: await res.json()};
                }""",
                csrf_token,
            )
            assert valid_write_resp["status"] == 201, (
                f"Valid write request failed: {valid_write_resp}"
            )
            valid_profile_id = valid_write_resp["data"]["id"]
            evidence["valid_write"] = valid_write_resp

            await browser.close()

        # 3. Viewer WS gate negative checks (outside authorized session)
        base_ws = f"wss://127.0.0.1:{harness.caddy_host_port}"
        base_http = f"https://127.0.0.1:{harness.caddy_host_port}"
        ws_url = f"{base_ws}/stream/{valid_profile_id}/signal"
        http_url = f"{base_http}/stream/{valid_profile_id}/signal"

        async with aiohttp.ClientSession(
            connector=aiohttp.TCPConnector(ssl=False)
        ) as session:
            # 3a. Unauthenticated Viewer WS (no cookie) -> rejected 401
            resp_no_auth = await session.get(
                http_url, headers={"Origin": harness.origin}
            )
            assert resp_no_auth.status == 401
            text_no_auth = await resp_no_auth.text()
            assert "cbrowser_session cookie missing" in text_no_auth

            try:
                async with session.ws_connect(
                    ws_url, headers={"Origin": harness.origin}
                ):
                    pytest.fail("Unauthenticated WS unexpectedly connected")
            except aiohttp.WSServerHandshakeError as err:
                assert err.status == 401
                evidence["unauthenticated_ws_rejection"] = {
                    "status": err.status,
                    "body": text_no_auth,
                }

            # 3b. Wrong Origin Viewer WS -> rejected 403
            bad_origin = "https://malicious.example.com"
            auth_cookie_val = session_cookie["value"]
            resp_bad_origin = await session.get(
                http_url,
                headers={
                    "Origin": bad_origin,
                    "Cookie": f"cbrowser_session={auth_cookie_val}",
                },
            )
            assert resp_bad_origin.status == 403
            text_bad_origin = await resp_bad_origin.text()
            assert "Origin not allowed" in text_bad_origin

            try:
                async with session.ws_connect(
                    ws_url,
                    headers={
                        "Origin": bad_origin,
                        "Cookie": f"cbrowser_session={auth_cookie_val}",
                    },
                ):
                    pytest.fail("Viewer WS with bad Origin unexpectedly connected")
            except aiohttp.WSServerHandshakeError as err:
                assert err.status == 403
                evidence["bad_origin_ws_rejection"] = {
                    "status": err.status,
                    "body": text_bad_origin,
                }

            # 3c. Unauthorized Profile Viewer WS -> rejected exactly 403
            # (t024 AC-005/A26): the session is authenticated and the
            # origin valid, so the API's viewer-authorize denial maps to
            # 403; 503 would mean gateway unavailability, not an
            # authorization verdict, and must not satisfy this case.
            unauthorized_pid = "unauthorized_profile_id_xyz"
            unauth_ws_url = f"{base_ws}/stream/{unauthorized_pid}/signal"
            unauth_http_url = f"{base_http}/stream/{unauthorized_pid}/signal"

            resp_unauth = await session.get(
                unauth_http_url,
                headers={
                    "Origin": harness.origin,
                    "Cookie": f"cbrowser_session={auth_cookie_val}",
                },
            )
            assert resp_unauth.status == 403
            text_unauth = await resp_unauth.text()

            try:
                async with session.ws_connect(
                    unauth_ws_url,
                    headers={
                        "Origin": harness.origin,
                        "Cookie": f"cbrowser_session={auth_cookie_val}",
                    },
                ):
                    pytest.fail("Unauthorized profile WS unexpectedly connected")
            except aiohttp.WSServerHandshakeError as err:
                assert err.status == 403
                evidence["unauthorized_profile_ws_rejection"] = {
                    "status": err.status,
                    "body": text_unauth,
                }

        # Verify rejection reasons from both client handshake and Gateway logs
        assert (
            "cbrowser_session cookie missing"
            in evidence["unauthenticated_ws_rejection"]["body"]
        )
        assert "Origin not allowed" in evidence["bad_origin_ws_rejection"]["body"]
        assert (
            "profile_not_found" in evidence["unauthorized_profile_ws_rejection"]["body"]
        )

        gw_logs = harness.gateway_container.logs().decode("utf-8")
        assert "401" in gw_logs, "Gateway access logs must record 401 rejection"
        assert "403" in gw_logs, "Gateway access logs must record 403 rejection"
        evidence["gateway_logs_sample"] = [
            line
            for line in gw_logs.splitlines()
            if any(k in line for k in ("401", "403", "reject", "Origin"))
        ]

        save_evidence("ac001_auth_evidence", evidence, target_dir=tmp_path / "evidence")

    finally:
        await harness.cleanup()
