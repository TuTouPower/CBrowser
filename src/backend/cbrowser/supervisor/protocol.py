"""Data models and protocols for CBrowser Supervisor Internal Control Server."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ObservedState = Literal["stopped", "starting", "running", "stopping", "error"]
DesiredState = Literal["stopped", "running"]


class StartProfileRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    profile_id: str = Field(min_length=1, max_length=128)
    config_version: int = Field(default=1, ge=1)
    force: bool = False
    operation_id: str | None = Field(default=None, min_length=1, max_length=128)


class StartProfileResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    profile_id: str
    status: Literal["starting", "running"]
    runtime_instance_id: str
    udp_mux_port: int = Field(ge=30000, le=30991)
    browser_container: str
    stream_container: str


class StopProfileRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    profile_id: str = Field(min_length=1, max_length=128)
    runtime_instance_id: str = Field(min_length=1, max_length=128)
    operation_id: str = Field(min_length=1, max_length=128)


class StopProfileResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    profile_id: str
    runtime_instance_id: str | None = None
    status: Literal["stopped", "stopping"]


class ResetBlockedRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    profile_id: str = Field(min_length=1, max_length=128)


class ResetBlockedResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    profile_id: str
    status: str = "ok"
    message: str = "Restart block cleared"


class ProfileRuntimeStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")
    profile_id: str
    runtime_instance_id: str | None = None
    observed_state: ObservedState = "stopped"
    desired_state: DesiredState = "stopped"
    udp_mux_port: int | None = None
    browser_container_id: str | None = None
    stream_container_id: str | None = None
    restart_blocked: bool = False
    failure_count: int = 0
