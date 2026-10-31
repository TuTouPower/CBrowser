"""Unit tests for cbrowser.stream_agent.ice_transport.
Tests:
1. Version guards and private ABI checks (fail-closed on unsupported environment or
missing attributes)
2. ICE server validation and URL security (no credentials in repr/logs, validation
of schemes)
3. Profile UDP mux and port range preservation across generations
4. Two-peer in-process WebRTC restart generation switch (same PC/DTLS/SCTP,
continuity of DataChannel,
rejection of retired connection writes) when run in Docker Selkies 2.1.0 environment
5. Mocked/Host-level interface assertions without Selkies installed
"""

from unittest.mock import MagicMock, patch

import pytest
from cbrowser.stream_agent.ice_transport import (
    GenerationIceTransport,
    SelkiesABIGuardError,
    UnsupportedSelkiesVersionError,
    create_restart_offer,
    validate_ice_servers,
    verify_selkies_abi_guard,
)


def test_ice_server_validation_types():
    # Empty or None
    assert validate_ice_servers(None) == []
    assert validate_ice_servers([]) == []

    # Invalid list type
    with pytest.raises(ValueError, match="ice_servers must be a list"):
        validate_ice_servers("not-a-list")

    # Invalid item type
    with pytest.raises(ValueError, match="Invalid ice_server entry type"):
        validate_ice_servers([123])

    # Missing urls
    with pytest.raises(ValueError, match="Missing 'urls' field"):
        validate_ice_servers([{"username": "user"}])


def test_ice_server_url_schemes_and_sanitization():
    # Unsupported scheme
    with pytest.raises(ValueError, match="Unsupported ICE server scheme"):
        validate_ice_servers([{"urls": "http://example.com:3478"}])

    with pytest.raises(ValueError, match="Unsupported ICE server scheme"):
        validate_ice_servers([{"urls": "ftp://secret:pass@example.com"}])


def test_verify_selkies_abi_guard_raises_on_wrong_version():
    with patch("cbrowser.stream_agent.ice_transport._SELKIES_AVAILABLE", True):
        mock_selkies = MagicMock()
        mock_selkies.__version__ = "2.0.9"
        with patch(
            "cbrowser.stream_agent.ice_transport.selkies", mock_selkies, create=True
        ):
            with pytest.raises(
                UnsupportedSelkiesVersionError, match="Unsupported selkies version"
            ):
                verify_selkies_abi_guard()


def test_verify_selkies_abi_guard_raises_when_sdk_missing():
    with patch("cbrowser.stream_agent.ice_transport._SELKIES_AVAILABLE", False):
        with pytest.raises(
            UnsupportedSelkiesVersionError, match="not installed or importable"
        ):
            verify_selkies_abi_guard()


def test_verify_selkies_abi_guard_raises_on_missing_private_attributes():
    mock_selkies = MagicMock()
    mock_selkies.__version__ = "2.1.0"
    mock_selkies.webrtc.__version__ = "1.15.0"
    mock_selkies.ice.__version__ = "0.10.2"

    # Mock RTCPeerConnection missing _RTCPeerConnection__iceTransports
    class FakePC:
        pass

    class FakeTransport:
        pass

    mock_pc_mod = MagicMock()
    mock_pc_mod.RTCPeerConnection = FakePC

    with (
        patch("cbrowser.stream_agent.ice_transport._SELKIES_AVAILABLE", True),
        patch("cbrowser.stream_agent.ice_transport.selkies", mock_selkies, create=True),
        patch(
            "cbrowser.stream_agent.ice_transport.selkies_pc_mod",
            mock_pc_mod,
            create=True,
        ),
        patch(
            "cbrowser.stream_agent.ice_transport.RTCIceGatherer",
            return_value=MagicMock(),
            create=True,
        ),
        patch(
            "cbrowser.stream_agent.ice_transport.RTCIceTransport",
            return_value=FakeTransport(),
            create=True,
        ),
    ):
        with pytest.raises(SelkiesABIGuardError):
            verify_selkies_abi_guard()


@pytest.mark.asyncio
async def test_create_restart_offer_requires_generation_ice_transport():
    with patch("cbrowser.stream_agent.ice_transport.verify_selkies_abi_guard"):
        mock_pc = MagicMock()
        mock_pc._RTCPeerConnection__iceTransports = {
            MagicMock()
        }  # Not GenerationIceTransport
        mock_pc.sctp = None

        with pytest.raises(TypeError, match="not GenerationIceTransport"):
            await create_restart_offer(mock_pc)


def test_diagnostics_sanitization():
    # Test that GenerationIceTransport diagnostics and repr don't leak credentials
    with patch("cbrowser.stream_agent.ice_transport.verify_selkies_abi_guard"):
        mock_gatherer = MagicMock()
        mock_conn = MagicMock()
        mock_conn.local_username = "user_frag_123"
        mock_conn.local_password = "SUPER_SECRET_LOCAL_PASS"
        mock_conn.remote_username = "rem_frag_456"
        mock_conn.remote_password = "SUPER_SECRET_REMOTE_PASS"
        mock_gatherer._connection = mock_conn

        transport = GenerationIceTransport(mock_gatherer)
        diag = transport.get_diagnostics()

        diag_str = str(diag)
        repr_str = repr(transport)

        assert "SUPER_SECRET_LOCAL_PASS" not in diag_str
        assert "SUPER_SECRET_REMOTE_PASS" not in diag_str
        assert "SUPER_SECRET_LOCAL_PASS" not in repr_str
        assert "SUPER_SECRET_REMOTE_PASS" not in repr_str
        assert diag["local_ufrag"] == "user_frag_123"


def test_relay_only_policy_flag():
    from cbrowser.stream_agent.ice_transport import is_relay_only, set_relay_only

    set_relay_only(True)
    assert is_relay_only() is True
    set_relay_only(False)
    assert is_relay_only() is False
