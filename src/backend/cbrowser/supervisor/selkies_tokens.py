"""Per-profile runtime Selkies token generation and management."""

from __future__ import annotations

import json
import re
import secrets
from dataclasses import dataclass
from pathlib import Path

from cbrowser.shared.atomic_write import atomic_write_text

_INSTANCE_ID = re.compile(r"^[A-Za-z0-9_-]+$")
_CREDENTIALS_PREFIX = "selkies_tokens_"


@dataclass(frozen=True)
class SelkiesTokens:
    master_token: str
    controller_token: str

    @classmethod
    def generate(cls) -> SelkiesTokens:
        return cls(
            master_token=secrets.token_urlsafe(32),
            controller_token=secrets.token_urlsafe(32),
        )

    def write_credentials_file(self, path: Path) -> None:
        """Write credentials file with 0600 mode for Stream container."""
        content = json.dumps(
            {
                "master_token": self.master_token,
                "controller_token": self.controller_token,
            },
            indent=2,
        )
        atomic_write_text(path, content, mode=0o600)

    def provision_credentials_file(
        self, secret_dir: Path, runtime_instance_id: str
    ) -> Path:
        """Write this instance's credentials to a fresh path and drop stale ones.

        Each start uses a new file name instead of replacing the previous one in
        place: a restarted Stream container must never bind-mount a path that a
        prior container mounted, because some Docker file-sharing layers keep
        serving the stale entry for a moment after an atomic replace.
        """
        if not _INSTANCE_ID.match(runtime_instance_id):
            raise ValueError("Invalid runtime_instance_id for credentials file")
        target = secret_dir / f"{_CREDENTIALS_PREFIX}{runtime_instance_id}.json"
        for stale in secret_dir.glob(f"{_CREDENTIALS_PREFIX}*.json"):
            if stale != target:
                stale.unlink()
        self.write_credentials_file(target)
        return target
