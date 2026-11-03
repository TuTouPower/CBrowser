"""Real Docker container topology harness for frontend session E2E tests."""

from __future__ import annotations

import logging
import os
import uuid
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
FIXTURES_DIR = REPO_ROOT / "tests" / "fixtures"

import docker
from gateway_probe.topology import GatewayTopologyHarness

from .host_builder import prepare_frontend_host

logger = logging.getLogger("cbrowser.frontend_probe.harness")


def load_images_env() -> None:
    """Loads immutable image IDs from .scratch/images_env.txt into os.environ."""
    env_file = REPO_ROOT / ".scratch" / "images_env.txt"
    if env_file.is_file():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k = k.strip()
            v = v.strip()
            if k not in os.environ and v:
                os.environ[k] = v


class FrontendTopologyHarness(GatewayTopologyHarness):
    """Topology harness customized for t007 frontend session E2E tests."""

    prefix_base = "t007-fe-session"
    test_label = "t007-fe-session"

    def __init__(
        self,
        work_dir: Path,
        agent_heartbeat_timeout_sec: float = 30.0,
    ) -> None:
        load_images_env()
        super().__init__(
            work_dir=work_dir,
            agent_heartbeat_timeout_sec=agent_heartbeat_timeout_sec,
        )
        # Dedicated prefix for this lane
        self.prefix = f"{self.prefix_base}-{uuid.uuid4().hex[:8]}"

    def _run_container(
        self, role: str, image_id: str, **kwargs: Any
    ) -> docker.models.containers.Container:
        labels = kwargs.pop("labels", {})
        labels.update(
            {
                "com.cbrowser.prefix": self.prefix,
                "com.cbrowser.test": self.test_label,
                "com.cbrowser.role": role,
            }
        )
        if role == "gateway":
            labels["com.cbrowser.managed-by"] = "supervisor"

        container = self.docker_client.containers.run(
            image_id,
            name=f"{self.prefix}-{role}",
            detach=True,
            network=self.edge_network.name,
            labels=labels,
            **kwargs,
        )
        self.containers.append(container)
        return container

    def prepare_static(self) -> None:
        """Prepares the Caddy static root for this harness variant."""
        prepare_frontend_host(self.static_dir)

    def api_environment_extra(self) -> dict[str, str]:
        """Extra environment variables for the API container."""
        return {}
