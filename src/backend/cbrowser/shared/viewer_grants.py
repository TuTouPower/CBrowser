"""Short-lived viewer authorization grants shared by the API and Gateway.

Neutral home (t062/t064): the API mints a grant at the edge after it has
validated the management session (Caddy ``forward_auth``), and the Gateway
verifies the grant locally during the viewer handshake. The session
cookie itself never reaches the Gateway.

A grant is a profile-bound, HMAC-signed capability with a fixed short
lifetime. Its payload carries exactly a version, the profile id, a random
grant id and the expiry — never any session material — so a leaked grant
is worth strictly less than the cookie it replaces: one profile, at most
``GRANT_TTL_SECONDS``. Revocation and expiry of the underlying session
are re-decided by the API on every handshake (each connection re-runs
``forward_auth``); the grant only bridges the edge decision to the
Gateway.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from dataclasses import dataclass
from pathlib import Path

from cbrowser.secret_files import read_secret_file
from pydantic import SecretStr

GRANT_TTL_SECONDS = 60
_GRANT_VERSION = 1

#: Header carrying the deployment edge-proof secret on Caddy's
#: forward_auth subrequest to the API resolver (Caddy -> API hop).
EDGE_PROOF_HEADER = "X-CBrowser-Edge-Proof"
#: Header naming the profile the API authorized; Caddy copies it from
#: the resolver response onto the proxied handshake (API -> Gateway hop).
AUTHORIZED_PROFILE_HEADER = "X-CBrowser-Authorized-Profile"
#: Header carrying the viewer grant itself (API -> Gateway hop).
VIEWER_GRANT_HEADER = "X-CBrowser-Viewer-Grant"


@dataclass(frozen=True)
class ViewerGrantClaims:
    profile_id: str
    grant_id: str
    expires_at: int


def _b64encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64decode(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


class ViewerGrantAuthority:
    """Mints and verifies viewer grants from one shared key file."""

    def __init__(self, key_file: Path | str):
        try:
            key = read_secret_file(
                Path(key_file), label="Viewer grant key", minimum_bytes=32
            )
        except RuntimeError as exc:
            raise ValueError(str(exc)) from None
        self._key = SecretStr(key)

    def _sign(self, payload_b64: str) -> str:
        return hmac.new(
            self._key.get_secret_value().encode("utf-8"),
            payload_b64.encode("ascii"),
            hashlib.sha256,
        ).hexdigest()

    def mint(self, profile_id: str, *, now: float | None = None) -> str:
        issued = int(time.time() if now is None else now)
        payload = {
            "v": _GRANT_VERSION,
            "profile_id": profile_id,
            "grant_id": secrets.token_hex(16),
            "exp": issued + GRANT_TTL_SECONDS,
        }
        payload_b64 = _b64encode(
            json.dumps(payload, separators=(",", ":")).encode("utf-8")
        )
        return f"{payload_b64}.{self._sign(payload_b64)}"

    def verify(
        self, grant: str, profile_id: str, *, now: float | None = None
    ) -> ViewerGrantClaims | None:
        """Return the claims for a well-formed, unexpired, correctly
        signed grant bound to ``profile_id``; ``None`` for anything else.
        Never raises on malformed input."""
        try:
            payload_b64, signature = grant.split(".", 1)
            if not hmac.compare_digest(
                signature.encode("utf-8"), self._sign(payload_b64).encode("utf-8")
            ):
                return None
            payload = json.loads(_b64decode(payload_b64))
        except Exception:  # noqa: BLE001 - malformed grant material is a denial
            return None
        if not isinstance(payload, dict) or payload.get("v") != _GRANT_VERSION:
            return None
        expires_at = payload.get("exp")
        grant_profile = payload.get("profile_id")
        grant_id = payload.get("grant_id")
        if (
            not isinstance(expires_at, int)
            or not isinstance(grant_profile, str)
            or not isinstance(grant_id, str)
        ):
            return None
        current = int(time.time() if now is None else now)
        if expires_at <= current:
            return None
        if grant_profile != profile_id:
            return None
        return ViewerGrantClaims(
            profile_id=grant_profile, grant_id=grant_id, expires_at=expires_at
        )
