"""Unit tests for RTC configuration, TURN REST HMAC credentials, and rotation timing."""

import base64
import hashlib
import hmac
import secrets
import time
from pathlib import Path

import pytest
from cbrowser.rtc_config.credential import generate_turn_credentials
from cbrowser.rtc_config.models import RtcScheduleParams
from cbrowser.rtc_config.service import RtcConfigService


def test_turn_credential_hmac_format_and_roles(tmp_path: Path) -> None:
    secret = secrets.token_urlsafe(32).encode("utf-8")
    secret_file = tmp_path / "turn_secret.txt"
    secret_file.write_bytes(secret)

    expiry = int(time.time()) + 86400
    profile_id = f"prof_{secrets.token_hex(4)}"

    # Generate client credentials
    client_user, client_cred = generate_turn_credentials(
        secret=secret,
        profile_id=profile_id,
        role="client",
        expiry_timestamp=expiry,
    )

    # Generate stream credentials
    stream_user, stream_cred = generate_turn_credentials(
        secret=secret,
        profile_id=profile_id,
        role="stream",
        expiry_timestamp=expiry,
    )

    # 1. Username format: <expiry_unix>:<role>-<profile_id>
    assert client_user == f"{expiry}:client-{profile_id}"
    assert stream_user == f"{expiry}:stream-{profile_id}"

    # 2. Credential format: base64(HMAC-SHA1(secret, username))
    expected_client_mac = hmac.new(
        secret, client_user.encode("utf-8"), hashlib.sha1
    ).digest()
    assert client_cred == base64.b64encode(expected_client_mac).decode("utf-8")

    expected_stream_mac = hmac.new(
        secret, stream_user.encode("utf-8"), hashlib.sha1
    ).digest()
    assert stream_cred == base64.b64encode(expected_stream_mac).decode("utf-8")

    # 3. Client and stream credentials must differ
    assert client_user != stream_user
    assert client_cred != stream_cred

    # 4. Cross-role mismatch is detectable from the HMAC itself
    assert client_cred != stream_cred


def test_rtc_config_secret_validation(tmp_path: Path) -> None:
    short_secret_file = tmp_path / "short_secret.txt"
    short_secret_file.write_text("too_short", encoding="utf-8")

    with pytest.raises(ValueError, match="at least 32 bytes"):
        RtcConfigService(
            turn_secret_file=short_secret_file,
            turn_public_urls=["turn:turn.example.com:3478?transport=udp"],
            webrtc_mode="public",
        )

    missing_secret_file = tmp_path / "non_existent.txt"
    with pytest.raises(ValueError, match="Cannot read TURN secret file"):
        RtcConfigService(
            turn_secret_file=missing_secret_file,
            turn_public_urls=["turn:turn.example.com:3478?transport=udp"],
            webrtc_mode="public",
        )


def test_rtc_config_relay_only_mode_policy(tmp_path: Path) -> None:
    secret_file = tmp_path / "turn_secret.txt"
    secret_file.write_text(secrets.token_urlsafe(32), encoding="utf-8")

    service_relay = RtcConfigService(
        turn_secret_file=secret_file,
        turn_public_urls=["turn:turn.example.com:3478?transport=udp"],
        webrtc_mode="relay-only",
    )
    gen_relay = service_relay.generate_generation(profile_id="p1", generation_num=1)
    assert gen_relay.client_rtc_config["iceTransportPolicy"] == "relay"
    assert gen_relay.relay_only is True
    stream_cfg_relay = gen_relay.build_stream_rtc_config("10.0.0.1", 3478)
    assert stream_cfg_relay["relay_only"] is True

    service_public = RtcConfigService(
        turn_secret_file=secret_file,
        turn_public_urls=["turn:turn.example.com:3478?transport=udp"],
        webrtc_mode="public",
    )
    gen_public = service_public.generate_generation(profile_id="p1", generation_num=1)
    assert gen_public.client_rtc_config["iceTransportPolicy"] == "all"
    assert gen_public.relay_only is False
    stream_cfg_public = gen_public.build_stream_rtc_config("10.0.0.1", 3478)
    assert stream_cfg_public["relay_only"] is False


def test_turn_rotation_time_calculation_and_windows(tmp_path: Path) -> None:
    secret_file = tmp_path / "turn_secret.txt"
    secret_file.write_text(secrets.token_urlsafe(32), encoding="utf-8")

    params = RtcScheduleParams(
        credential_lifetime_sec=86400,
        generation_interval_sec=43200,
        ice_restart_lead_time_sec=21600,
    )
    service = RtcConfigService(
        turn_secret_file=secret_file,
        turn_public_urls=["turn:turn.example.com:3478?transport=udp"],
        webrtc_mode="public",
        params=params,
    )

    t0 = 1_000_000.0
    gen1 = service.generate_generation(profile_id="p1", generation_num=1, now=t0)
    assert gen1.generation == 1
    assert gen1.created_at == t0
    assert gen1.expires_at == t0 + 86400

    # Before generation interval: do not generate next
    assert service.should_generate_next(gen1, now=t0 + 43199.0) is False
    # At generation interval: generate next
    assert service.should_generate_next(gen1, now=t0 + 43200.0) is True

    # Restart trigger for gen1: expires_at (t0 + 86400) - lead_time (21600) = t0 + 64800
    assert service.should_trigger_restart(gen1, now=t0 + 64799.0) is False
    assert service.should_trigger_restart(gen1, now=t0 + 64800.0) is True

    # Expiry detection
    assert service.is_expired(gen1, now=t0 + 86399.0) is False
    assert service.is_expired(gen1, now=t0 + 86400.0) is True


def test_rtc_generation_stream_credentials_and_url_formatting(tmp_path: Path) -> None:
    secret_file = tmp_path / "turn_secret.txt"
    secret_file.write_text(secrets.token_urlsafe(32), encoding="utf-8")

    service = RtcConfigService(
        turn_secret_file=secret_file,
        turn_public_urls=["turn:turn.example.com:3478?transport=udp"],
        webrtc_mode="public",
    )
    gen = service.generate_generation(profile_id="p1", generation_num=1)
    assert hasattr(gen, "stream_username")
    assert hasattr(gen, "stream_credential")
    assert not hasattr(gen, "stream_rtc_config")

    # IPv4 URL assembly
    stream_servers_v4 = gen.build_stream_ice_servers("10.0.0.1", 3478)
    assert len(stream_servers_v4) == 1
    assert stream_servers_v4[0]["urls"] == [
        "turn:10.0.0.1:3478?transport=udp",
        "turn:10.0.0.1:3478?transport=tcp",
    ]
    assert stream_servers_v4[0]["username"] == gen.stream_username
    assert stream_servers_v4[0]["credential"] == gen.stream_credential

    # IPv6 URL assembly (brackets required)
    stream_servers_v6 = gen.build_stream_ice_servers("2001:db8::1", 3478)
    assert len(stream_servers_v6) == 1
    assert stream_servers_v6[0]["urls"] == [
        "turn:[2001:db8::1]:3478?transport=udp",
        "turn:[2001:db8::1]:3478?transport=tcp",
    ]
    assert stream_servers_v6[0]["username"] == gen.stream_username
    assert stream_servers_v6[0]["credential"] == gen.stream_credential
