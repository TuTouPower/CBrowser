"""Lane-partitioned UDP mux range contract (t032 AC-007)."""

import pytest
from cbrowser.udp_mux import udp_mux_bounds


def test_default_udp_mux_bounds(monkeypatch):
    monkeypatch.delenv("CBROWSER_UDP_MUX_MIN_PORT", raising=False)
    monkeypatch.delenv("CBROWSER_UDP_MUX_MAX_PORT", raising=False)
    assert udp_mux_bounds() == (30000, 30991)


def test_udp_mux_bounds_follow_environment(monkeypatch):
    monkeypatch.setenv("CBROWSER_UDP_MUX_MIN_PORT", "32000")
    monkeypatch.setenv("CBROWSER_UDP_MUX_MAX_PORT", "32991")
    assert udp_mux_bounds() == (32000, 32991)


@pytest.mark.parametrize(
    ("minimum", "maximum"),
    [("32000", "31999"), ("100", "30991"), ("30000", "70000"), ("bad", "30991")],
)
def test_invalid_udp_mux_bounds_are_rejected(monkeypatch, minimum, maximum):
    monkeypatch.setenv("CBROWSER_UDP_MUX_MIN_PORT", minimum)
    monkeypatch.setenv("CBROWSER_UDP_MUX_MAX_PORT", maximum)
    with pytest.raises(ValueError):
        udp_mux_bounds()
