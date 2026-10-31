"""RTC configuration service generating client/stream ICE configs."""

from __future__ import annotations

import time
from collections.abc import Sequence
from pathlib import Path

from pydantic import SecretStr

from .credential import generate_turn_credentials
from .models import RtcGeneration, RtcScheduleParams


class RtcConfigService:
    """Produces client/stream RTC configurations with TURN REST credentials."""

    def __init__(
        self,
        turn_secret_file: Path | str,
        turn_public_urls: Sequence[str],
        webrtc_mode: str = "public",
        params: RtcScheduleParams | None = None,
    ) -> None:
        try:
            raw_secret = Path(turn_secret_file).read_text(encoding="utf-8").strip()
        except (OSError, UnicodeError):
            raise ValueError("Cannot read TURN secret file") from None

        if len(raw_secret.encode("utf-8")) < 32:
            raise ValueError(
                "TURN secret requires an external key of at least 32 bytes"
            )

        self._secret = SecretStr(raw_secret)
        self.turn_public_urls = list(turn_public_urls)
        self.webrtc_mode = webrtc_mode
        self.params = params or RtcScheduleParams()

    @property
    def secret_bytes(self) -> bytes:
        return self._secret.get_secret_value().encode("utf-8")

    def generate_generation(
        self,
        profile_id: str,
        generation_num: int,
        now: float | None = None,
    ) -> RtcGeneration:
        """Generates a new generation of RTC configurations for a given Profile."""
        current_time = time.time() if now is None else now
        expiry_time = current_time + self.params.credential_lifetime_sec
        expiry_unix = int(expiry_time)

        # 1. Client credentials & config
        client_user, client_cred = generate_turn_credentials(
            secret=self.secret_bytes,
            profile_id=profile_id,
            role="client",
            expiry_timestamp=expiry_unix,
        )
        client_ice_servers = [
            {
                "urls": list(self.turn_public_urls),
                "username": client_user,
                "credential": client_cred,
            }
        ]
        client_rtc_config = {
            "iceServers": client_ice_servers,
            "iceTransportPolicy": "relay"
            if self.webrtc_mode == "relay-only"
            else "all",
        }

        # 2. Stream credentials
        stream_user, stream_cred = generate_turn_credentials(
            secret=self.secret_bytes,
            profile_id=profile_id,
            role="stream",
            expiry_timestamp=expiry_unix,
        )

        return RtcGeneration(
            generation=generation_num,
            profile_id=profile_id,
            created_at=current_time,
            expires_at=expiry_time,
            client_rtc_config=client_rtc_config,
            stream_username=stream_user,
            stream_credential=stream_cred,
            relay_only=self.webrtc_mode == "relay-only",
        )

    def should_generate_next(self, current_gen: RtcGeneration, now: float) -> bool:
        """Determines if the next generation should be generated based on interval."""
        return now >= current_gen.created_at + self.params.generation_interval_sec

    def should_trigger_restart(self, current_gen: RtcGeneration, now: float) -> bool:
        """Determines if ICE restart should be triggered in advance of expiry."""
        return now >= current_gen.expires_at - self.params.ice_restart_lead_time_sec

    def is_expired(self, gen: RtcGeneration, now: float) -> bool:
        """Checks if a generation has expired."""
        return now >= gen.expires_at
