"""t026 AC-009 / test f002: the host-side control CLI contract.

Exit codes are the deployment signal: readiness 0 iff ready, 1 when
not ready or unreachable; reconcile 0 on success, 2 when unreachable.
The JSON payload is printed verbatim for the operator.
"""

from __future__ import annotations

import json

import httpx
import pytest
from cbrowser.supervisor import control_client


def _install_transport(monkeypatch: pytest.MonkeyPatch, handler) -> None:
    def _fake_client() -> httpx.Client:
        return httpx.Client(
            base_url="http://supervisor.invalid",
            transport=httpx.MockTransport(handler),
        )

    monkeypatch.setattr(control_client, "_client", _fake_client)


def test_readiness_exit_zero_when_ready(monkeypatch, capsys):
    _install_transport(
        monkeypatch,
        lambda request: httpx.Response(200, json={"ready": True, "profiles": []}),
    )
    assert control_client.main(["readiness"]) == 0
    assert json.loads(capsys.readouterr().out)["ready"] is True


def test_readiness_exit_one_when_not_ready(monkeypatch, capsys):
    _install_transport(
        monkeypatch,
        lambda request: httpx.Response(
            200, json={"ready": False, "reason": "profile_not_ready"}
        ),
    )
    assert control_client.main(["readiness"]) == 1
    assert json.loads(capsys.readouterr().out)["ready"] is False


def test_readiness_exit_one_and_json_error_when_unreachable(monkeypatch, capsys):
    def _down(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down", request=request)

    _install_transport(monkeypatch, _down)
    assert control_client.main(["readiness"]) == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["ready"] is False
    assert payload["error"].startswith("control_unreachable:")


def test_reconcile_exit_codes(monkeypatch, capsys):
    _install_transport(
        monkeypatch,
        lambda request: httpx.Response(
            200, json={"scanned": 3, "profiles": ["p1"]}
        ),
    )
    assert control_client.main(["reconcile"]) == 0
    assert json.loads(capsys.readouterr().out)["scanned"] == 3

    def _down(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down", request=request)

    _install_transport(monkeypatch, _down)
    assert control_client.main(["reconcile"]) == 2


def test_handlers_hit_the_contract_paths(monkeypatch):
    # test f008: a wrong URL in the CLI must fail the suite — handlers
    # assert the exact control-plane paths.
    seen: list[str] = []

    def _handler(request: httpx.Request) -> httpx.Response:
        seen.append(f"{request.method} {request.url.path}")
        if request.url.path == "/supervisor/v1/readiness":
            return httpx.Response(200, json={"ready": True, "profiles": []})
        if request.url.path == "/supervisor/v1/reconcile":
            return httpx.Response(200, json={"scanned": 0, "profiles": []})
        return httpx.Response(404)

    _install_transport(monkeypatch, _handler)
    assert control_client.main(["readiness"]) == 0
    assert control_client.main(["reconcile"]) == 0
    assert seen == [
        "GET /supervisor/v1/readiness",
        "POST /supervisor/v1/reconcile",
    ]


def test_client_construction_uses_env_url_and_token_file(monkeypatch, tmp_path):
    # test f008: _client itself — env URL + token file → base URL and
    # Bearer header — was previously untested (tests replaced it whole).
    token = "tok_" + "x" * 40
    token_file = tmp_path / "control_token"
    token_file.write_text(token)
    token_file.chmod(0o600)
    monkeypatch.setenv(
        "CBROWSER_SUPERVISOR_URL", "http://supervisor.internal:8091"
    )
    monkeypatch.setenv("CBROWSER_SUPERVISOR_TOKEN_FILE", str(token_file))
    # The sandbox's proxy variables are unrelated to the container this
    # CLI runs in; keep httpx's trust-env pickup out of the assertion.
    for var in (
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "NO_PROXY",
        "http_proxy",
        "https_proxy",
        "all_proxy",
        "no_proxy",
    ):
        monkeypatch.delenv(var, raising=False)

    client = control_client._client()
    try:
        assert str(client.base_url) == "http://supervisor.internal:8091"
        assert client.headers["Authorization"] == f"Bearer {token}"
    finally:
        client.close()
