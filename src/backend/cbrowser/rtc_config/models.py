"""Data models for RTC configuration and rotation parameters."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class RtcScheduleParams(BaseModel):
    """Parameters governing credential validity and rotation cycles."""

    model_config = ConfigDict(extra="forbid")

    credential_lifetime_sec: float = Field(
        default=24 * 3600.0, description="Total validity duration of a TURN credential"
    )
    generation_interval_sec: float = Field(
        default=12 * 3600.0,
        description="Interval at which a new generation is produced",
    )
    ice_restart_lead_time_sec: float = Field(
        default=6 * 3600.0,
        description="Advance window before expiry to trigger ICE restart",
    )


class RtcGeneration(BaseModel):
    """An immutable generation of client and stream RTC configurations."""

    model_config = ConfigDict(extra="forbid")

    generation: int = Field(ge=1)
    profile_id: str
    created_at: float
    expires_at: float
    client_rtc_config: dict[str, Any]
    stream_username: str
    stream_credential: str
    relay_only: bool = False

    def build_stream_ice_servers(
        self, turn_host: str, turn_port: int
    ) -> list[dict[str, Any]]:
        host_part = f"[{turn_host}]" if ":" in turn_host else turn_host
        return [
            {
                "urls": [
                    f"turn:{host_part}:{turn_port}?transport=udp",
                    f"turn:{host_part}:{turn_port}?transport=tcp",
                ],
                "username": self.stream_username,
                "credential": self.stream_credential,
            }
        ]

    def build_stream_rtc_config(self, turn_host: str, turn_port: int) -> dict[str, Any]:
        return {
            "generation": self.generation,
            "ice_servers": self.build_stream_ice_servers(turn_host, turn_port),
            "relay_only": self.relay_only,
        }
