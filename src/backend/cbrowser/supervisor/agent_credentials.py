"""Instance-scoped Agent tokens derived from an externally provided service key."""

import hashlib
import hmac
import json
from pathlib import Path

from pydantic import SecretStr


class AgentCredentials:
    def __init__(self, key_file: Path | str):
        try:
            key = Path(key_file).read_text(encoding="utf-8").strip()
        except (OSError, UnicodeError):
            raise ValueError("Cannot read Agent authentication key file") from None
        if len(key.encode("utf-8")) < 32:
            raise ValueError("Agent authentication key must contain at least 32 bytes")
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
