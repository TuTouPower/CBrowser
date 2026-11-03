"""Real Docker topology harness serving the complete Vite frontend build."""

from __future__ import annotations

import asyncio
import json
import logging
import shutil
from pathlib import Path
from typing import Any

import httpx
from frontend_probe.adapter_probe import inject_adapter_probe
from frontend_probe.harness import REPO_ROOT, FrontendTopologyHarness

logger = logging.getLogger("cbrowser.frontend_app_probe.harness")

DIST_DIR = REPO_ROOT / "src" / "frontend" / "dist"


def prepare_frontend_app(dest_dir: Path) -> Path:
    """Copies the production frontend build (app + vendored Selkies) as static root."""
    index = DIST_DIR / "index.html"
    selkies_index = DIST_DIR / "selkies" / "index.html"
    adapter = DIST_DIR / "selkies" / "selkies_adapter.js"
    if not index.is_file():
        raise RuntimeError(
            "Frontend production build missing; run "
            "`npm run build --prefix src/frontend`"
        )
    if not selkies_index.is_file():
        raise RuntimeError(
            "Vendored Selkies assets missing; run scripts/vendor_selkies_web.py first"
        )
    if not adapter.is_file():
        raise RuntimeError(
            "Built Selkies adapter missing; run `npm run build --prefix src/frontend`"
        )
    # Refuse to serve a stale or unstamped build (t024 AC-003/A24): the
    # freshness gate lives at the copy point, independent of suite naming.
    import sys

    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    from scripts.verify_frontend_dist import verify_frontend_build_freshness

    verify_frontend_build_freshness(DIST_DIR, REPO_ROOT / "src" / "frontend")
    if dest_dir.exists():
        shutil.rmtree(dest_dir)
    shutil.copytree(DIST_DIR, dest_dir)
    inject_adapter_probe(dest_dir / "selkies" / "index.html")
    return dest_dir


class FrontendAppTopologyHarness(FrontendTopologyHarness):
    """Full application topology with API Runtime Coordinator enabled."""

    prefix_base = "t007-fe-e2e"
    test_label = "t007-fe-e2e"

    def prepare_static(self) -> None:
        prepare_frontend_app(self.static_dir)

    def api_environment_extra(self) -> dict[str, str]:
        return {
            "CBROWSER_SUPERVISOR_URL": f"http://{self.prefix}-supervisor:8005",
            "CBROWSER_REQUIRE_SUPERVISOR": "1",
        }

    async def api_client(self) -> httpx.AsyncClient:
        """Authenticated API client over the HTTPS Caddy entrypoint."""
        auth_headers = await self.login_api()
        return httpx.AsyncClient(
            base_url=self.origin,
            headers=auth_headers,
            verify=False,
            trust_env=False,
            timeout=30.0,
        )

    async def get_runtime(self, profile_id: str) -> dict[str, Any]:
        async with await self.api_client() as client:
            resp = await client.get(f"/api/v1/profiles/{profile_id}/runtime")
            resp.raise_for_status()
            return resp.json()

    async def set_desired_state(self, profile_id: str, state: str) -> dict[str, Any]:
        async with await self.api_client() as client:
            resp = await client.patch(
                f"/api/v1/profiles/{profile_id}/runtime/desired-state",
                json={"desired_state": state},
            )
            resp.raise_for_status()
            return resp.json()

    async def wait_runtime(
        self,
        profile_id: str,
        *,
        desired: str | None = None,
        observed: str | None = None,
        timeout: float = 90.0,
    ) -> dict[str, Any]:
        deadline = asyncio.get_running_loop().time() + timeout
        last: dict[str, Any] = {}
        while asyncio.get_running_loop().time() < deadline:
            try:
                last = await self.get_runtime(profile_id)
            except (httpx.HTTPError, httpx.TransportError):
                await asyncio.sleep(0.3)
                continue
            desired_ok = desired is None or last.get("desired_state") == desired
            observed_ok = observed is None or last.get("observed_state") == observed
            if desired_ok and observed_ok:
                return last
            await asyncio.sleep(0.3)
        raise TimeoutError(
            f"Runtime did not reach desired={desired} "
            f"observed={observed}: {json.dumps(last)}"
        )

    def selkies_tokens(self, profile_id: str) -> dict[str, str]:
        # Supervisor keeps one per-instance credentials file outside the
        # Browser-mounted runtime dir.
        secret_dir = self.data_dir / "runtime" / ".secrets" / profile_id
        files = sorted(secret_dir.glob("selkies_tokens_*.json"))
        if len(files) != 1:
            raise RuntimeError(f"Expected one Selkies credentials file: {files}")
        return json.loads(files[0].read_text(encoding="utf-8"))

    def containers_for(self, profile_id: str) -> list[Any]:
        return self.docker_client.containers.list(
            all=True,
            filters={"label": f"com.cbrowser.profile-id={profile_id}"},
        )

    def container_names(self, profile_id: str) -> tuple[str, str] | None:
        """Returns (browser, stream) container names for a profile, if bound."""
        found: dict[str, str] = {}
        for container in self.containers_for(profile_id):
            role = container.labels.get("com.cbrowser.role")
            if role in ("browser", "stream"):
                found[role] = container.name
        if "browser" in found and "stream" in found:
            return found["browser"], found["stream"]
        return None
