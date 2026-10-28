"""Pydantic models for Browser Runtime Agent UDS protocol."""

from __future__ import annotations

import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


def utc_now_iso() -> str:
    return datetime.datetime.now(datetime.UTC).isoformat()


RuntimeEventType = Literal["exit", "heartbeat", "lifecycle"]
DownloadState = Literal["in_progress", "completed", "canceled"]
AgentStatus = Literal["ok", "degraded", "error"]


class HealthResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: AgentStatus
    ready: bool
    display_ready: bool
    browser_ready: bool
    audio_ready: bool
    cdp_ready: bool
    profile_id: str
    runtime_instance_id: str
    config_version: int = Field(default=1, ge=1)
    details: dict[str, Any] = Field(default_factory=dict)


class ConfigVersionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    profile_id: str
    runtime_instance_id: str
    config_version: int = Field(default=1, ge=1)


class ControlRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: Literal["close", "rearm_downloads"]
    params: dict[str, Any] = Field(default_factory=dict)


class ControlResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["ok", "error"]
    action: str
    message: str | None = None


class RuntimeEventRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: str = Field(pattern=r"^[a-zA-Z0-9_\-\.:]{1,128}$")
    profile_id: str = Field(pattern=r"^[a-zA-Z0-9_\-\.:]{1,128}$")
    runtime_instance_id: str = Field(pattern=r"^[a-zA-Z0-9_\-\.:]{1,128}$")
    event_type: RuntimeEventType = "exit"
    exit_code: int | None = None
    exit_reason: str | None = Field(default=None, max_length=128)
    config_version: int = Field(default=1, ge=1)
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: str = Field(default_factory=utc_now_iso)


class DownloadEventRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: str = Field(pattern=r"^[a-zA-Z0-9_\-\.:]{1,128}$")
    profile_id: str = Field(pattern=r"^[a-zA-Z0-9_\-\.:]{1,128}$")
    runtime_instance_id: str = Field(pattern=r"^[a-zA-Z0-9_\-\.:]{1,128}$")
    guid: str
    url: str | None = None
    suggested_filename: str | None = None
    download_path: str | None = None
    state: DownloadState = "in_progress"
    received_bytes: int = Field(default=0, ge=0)
    total_bytes: int = Field(default=0, ge=0)
    created_at: str = Field(default_factory=utc_now_iso)


class RuntimeStateRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    profile_id: str
    runtime_instance_id: str
    config_version: int = Field(default=1, ge=1)
    state: Literal["starting", "running", "stopped", "error"]
    exit_code: int | None = None
    exit_reason: str | None = None
    browser_pid: int | None = None
    updated_at: str = Field(default_factory=utc_now_iso)
