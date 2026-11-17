#!/usr/bin/env python3
"""Import mihomo one-to-one node listeners into the cbrowser proxy library."""

from __future__ import annotations

import argparse
import http.cookiejar
import json
import logging
import ssl
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MAPPING = REPO_ROOT.parent / "temp123/mihomo_proxy/config/node_port_mapping.json"
DEFAULT_PASSWORD_FILE = REPO_ROOT / "config/deploy/secrets/admin_password"
DEFAULT_API_BASE = "https://127.0.0.1:56661"

logger = logging.getLogger("import_mihomo_proxies")


class ApiClient:
    def __init__(self, api_base: str, origin: str, password_file: Path) -> None:
        self.api_base = api_base.rstrip("/")
        self.origin = origin
        self.csrf_token = ""
        jar = http.cookiejar.CookieJar()
        context = ssl._create_unverified_context()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(jar),
            urllib.request.HTTPSHandler(context=context),
        )
        password = password_file.read_text(encoding="utf-8").strip()
        status, body = self.request(
            "POST", "/api/v1/auth/login", {"password": password}, csrf=False
        )
        if status != 200 or not isinstance(body, dict) or not body.get("csrf_token"):
            raise RuntimeError(f"login failed with HTTP {status}")
        self.csrf_token = body["csrf_token"]

    def request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        *,
        csrf: bool = True,
    ) -> tuple[int, Any]:
        headers = {"Origin": self.origin}
        if csrf and self.csrf_token:
            headers["X-CSRF-Token"] = self.csrf_token
        data = None
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(
            self.api_base + path, data=data, headers=headers, method=method
        )
        try:
            with self.opener.open(request, timeout=60) as response:
                raw = response.read()
                return response.status, json.loads(raw) if raw else {}
        except urllib.error.HTTPError as error:
            raw = error.read()
            try:
                return error.code, json.loads(raw) if raw else {}
            except json.JSONDecodeError:
                return error.code, {}


def list_proxies(client: ApiClient) -> list[dict[str, Any]]:
    status, body = client.request("GET", "/api/v1/proxies")
    if status != 200:
        raise RuntimeError(f"list proxies failed with HTTP {status}")
    return body if isinstance(body, list) else body.get("items", [])


def load_entries(
    mapping_file: Path, start_port: int, end_port: int
) -> list[tuple[int, str, str]]:
    mapping = json.loads(mapping_file.read_text(encoding="utf-8"))
    entries: list[tuple[int, str, str]] = []
    for key, value in mapping.items():
        port = int(value.get("port", key))
        if value.get("type") != "single_node" or not (start_port <= port <= end_port):
            continue
        name = str(value.get("node_name") or f"node-{port}")
        entries.append((port, name, f"http://127.0.0.1:{port}"))
    return sorted(entries)


def wait_for_batch(
    client: ApiClient, proxy_ids: list[str], timeout: float, interval: float
) -> list[str]:
    pending = set(proxy_ids)
    deadline = time.monotonic() + timeout
    while pending and time.monotonic() < deadline:
        current = {item["id"]: item for item in list_proxies(client)}
        pending = {
            pid
            for pid in pending
            if current.get(pid, {}).get("observation_status") == "pending"
        }
        if not pending:
            break
        time.sleep(interval)
    return sorted(pending)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mapping", type=Path, default=DEFAULT_MAPPING)
    parser.add_argument("--password-file", type=Path, default=DEFAULT_PASSWORD_FILE)
    parser.add_argument("--api-base", default=DEFAULT_API_BASE)
    parser.add_argument("--origin", default="")
    parser.add_argument("--start-port", type=int, default=21000)
    parser.add_argument("--end-port", type=int, default=21087)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--batch-timeout", type=float, default=180.0)
    parser.add_argument("--poll-interval", type=float, default=5.0)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO, format="%(levelname)s %(message)s", stream=sys.stderr
    )
    entries = load_entries(args.mapping, args.start_port, args.end_port)
    logger.info(
        "candidates=%d range=%d-%d", len(entries), args.start_port, args.end_port
    )
    if args.dry_run:
        for port, name, url in entries[:5]:
            logger.info("sample port=%d name=%s url=%s", port, name, url)
        return 0

    origin = args.origin or args.api_base.rstrip("/")
    client = ApiClient(args.api_base, origin, args.password_file)
    existing = {item.get("proxy_url"): item for item in list_proxies(client)}
    created: list[dict[str, Any]] = []
    updated: list[dict[str, Any]] = []
    skipped: list[int] = []
    failed: list[dict[str, Any]] = []
    unsettled: list[str] = []
    batches = (len(entries) + args.batch_size - 1) // args.batch_size

    for index in range(batches):
        batch = entries[index * args.batch_size : (index + 1) * args.batch_size]
        batch_ids: list[str] = []
        for port, name, url in batch:
            prior = existing.get(url)
            if prior is not None:
                if prior.get("name") != name:
                    status, body = client.request(
                        "PATCH",
                        f"/api/v1/proxies/{prior['id']}",
                        {"name": name, "notes": f"mihomo node-{port}"},
                    )
                    if status == 200:
                        updated.append({"port": port, "id": prior["id"], "name": name})
                    else:
                        failed.append(
                            {
                                "port": port,
                                "stage": "rename",
                                "status": status,
                                "error": body.get("error"),
                            }
                        )
                else:
                    skipped.append(port)
                continue
            status, body = client.request(
                "POST",
                "/api/v1/proxies",
                {"proxy_url": url, "name": name, "notes": f"mihomo node-{port}"},
            )
            if status in (200, 201) and isinstance(body, dict) and body.get("id"):
                created.append(
                    {
                        "port": port,
                        "id": body["id"],
                        "name": body.get("name"),
                        "observation_status": body.get("observation_status"),
                    }
                )
                existing[url] = body
                batch_ids.append(body["id"])
            else:
                failed.append(
                    {
                        "port": port,
                        "stage": "create",
                        "status": status,
                        "error": body.get("error") or body.get("error_code"),
                    }
                )
        if batch_ids:
            pending = wait_for_batch(
                client, batch_ids, args.batch_timeout, args.poll_interval
            )
            unsettled.extend(pending)
            logger.info(
                "batch %d/%d created=%d settled=%d pending=%d",
                index + 1,
                batches,
                len(batch_ids),
                len(batch_ids) - len(pending),
                len(pending),
            )

    result = {
        "api_base": args.api_base,
        "range": [args.start_port, args.end_port],
        "candidates": len(entries),
        "created": created,
        "updated": updated,
        "skipped": skipped,
        "failed": failed,
        "unsettled": unsettled,
    }
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    print(
        json.dumps(
            {
                "candidates": len(entries),
                "created": len(created),
                "updated": len(updated),
                "skipped": len(skipped),
                "failed": len(failed),
                "unsettled": len(unsettled),
            },
            ensure_ascii=False,
        )
    )
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
