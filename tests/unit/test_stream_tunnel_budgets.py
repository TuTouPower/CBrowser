"""Shared tunnel size budgets (t022 A15 / AC-008)."""

from __future__ import annotations

import pytest
from cbrowser.stream_agent.protocol import (
    MAX_STREAM_FRAME_SIZE,
    MAX_TUNNEL_DATA_SIZE,
    MAX_TUNNEL_ENVELOPE_SIZE,
    GatewayTunnelEnvelope,
    serialize_tunnel_envelope,
)
from pydantic import ValidationError


def _envelope(data: str) -> GatewayTunnelEnvelope:
    return GatewayTunnelEnvelope(
        version="v2",
        type="msg",
        profile_id="profile_a",
        runtime_instance_id="instance_a",
        agent_session_id="session_a",
        conn_id="conn_a",
        data=data,
    )


def test_budget_layers_are_consistent() -> None:
    assert MAX_TUNNEL_DATA_SIZE < MAX_TUNNEL_ENVELOPE_SIZE <= MAX_STREAM_FRAME_SIZE


def test_data_at_budget_boundary_passes() -> None:
    envelope = _envelope("x" * MAX_TUNNEL_DATA_SIZE)
    assert envelope.data is not None
    assert len(envelope.data.encode("utf-8")) == MAX_TUNNEL_DATA_SIZE


def test_data_over_budget_is_rejected() -> None:
    with pytest.raises(ValidationError):
        _envelope("x" * (MAX_TUNNEL_DATA_SIZE + 1))


def test_json_escaping_expansion_is_charged_to_the_envelope_layer() -> None:
    """Data inside the raw budget whose JSON escaping inflates the envelope
    past the envelope budget must be refused at serialization time."""
    # Each control char is 1 raw byte but 6 bytes once escaped (XXXX).
    data = "\x01" * (MAX_TUNNEL_DATA_SIZE // 2)
    envelope = _envelope(data)
    with pytest.raises(ValueError):
        serialize_tunnel_envelope(envelope)


def test_in_budget_envelope_serializes() -> None:
    envelope = _envelope('{"key": "value with \\"quotes\\""}')
    text = serialize_tunnel_envelope(envelope)
    assert len(text.encode("utf-8")) <= MAX_TUNNEL_ENVELOPE_SIZE
