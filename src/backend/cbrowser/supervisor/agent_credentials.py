"""Instance-scoped Agent tokens derived from an externally provided service key."""

import hashlib
import hmac
import json
from pathlib import Path

from cbrowser.secret_files import read_secret_file
from pydantic import SecretStr


class AgentCredentials:
    def __init__(self, key_file: Path | str):
        try:
            key = read_secret_file(
                Path(key_file), label="Agent authentication key", minimum_bytes=32
            )
        except RuntimeError as exc:
            raise ValueError(str(exc)) from None
        self._key = SecretStr(key)

    def token_for(self, profile_id: str, runtime_instance_id: str) -> str:
        message = json.dumps(
            ["stream-agent-v1", profile_id, runtime_instance_id], separators=(",", ":")
        ).encode("utf-8")
        return hmac.new(
            self._key.get_secret_value().encode("utf-8"), message, hashlib.sha256
        ).hexdigest()

    def verify(self, token: str, profile_id: str, runtime_instance_id: str) -> bool:
        return hmac.compare_digest(
            token.encode("utf-8"),
            self.token_for(profile_id, runtime_instance_id).encode(),
        )
