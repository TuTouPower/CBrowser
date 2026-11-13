"""Viewer grants: API-minted, Gateway-verified, profile-bound, expiring.

The grant is the only authorization material the Gateway ever sees for a
viewer handshake (t064): it must not carry session material, must not be
forgeable without the shared key, and must die quickly.
"""

import base64
import json
import secrets

import pytest
from cbrowser.shared.viewer_grants import (
    GRANT_TTL_SECONDS,
    ViewerGrantAuthority,
)


def _authority(tmp_path, name="viewer_grant_key", key=None):
    path = tmp_path / name
    path.write_text(key or secrets.token_urlsafe(32))
    path.chmod(0o600)
    return ViewerGrantAuthority(path), path


def test_mint_verify_roundtrip_binds_profile_and_expiry(tmp_path):
    authority, _ = _authority(tmp_path)
    grant = authority.mint("profile_a", now=1_000.0)
    claims = authority.verify(grant, "profile_a", now=1_000.0)
    assert claims is not None
    assert claims.profile_id == "profile_a"
    assert claims.expires_at == 1_000 + GRANT_TTL_SECONDS
    assert claims.grant_id


def test_grant_payload_carries_no_session_material(tmp_path):
    authority, _ = _authority(tmp_path)
    grant = authority.mint("profile_a", now=1_000.0)
    payload_b64 = grant.split(".", 1)[0]
    payload = json.loads(base64.urlsafe_b64decode(payload_b64 + "=="))
    assert set(payload) == {"v", "profile_id", "grant_id", "exp"}
    assert payload["v"] == 1


def test_expired_grant_is_rejected(tmp_path):
    authority, _ = _authority(tmp_path)
    grant = authority.mint("profile_a", now=1_000.0)
    assert authority.verify(grant, "profile_a", now=1_000.0 + GRANT_TTL_SECONDS) is None
    assert (
        authority.verify(grant, "profile_a", now=1_000.0 + GRANT_TTL_SECONDS + 1)
        is None
    )


def test_grant_for_another_profile_is_rejected(tmp_path):
    authority, _ = _authority(tmp_path)
    grant = authority.mint("profile_a", now=1_000.0)
    assert authority.verify(grant, "profile_b", now=1_000.0) is None


def test_tampered_payload_or_signature_is_rejected(tmp_path):
    authority, _ = _authority(tmp_path)
    grant = authority.mint("profile_a", now=1_000.0)
    payload_b64, signature = grant.split(".", 1)
    payload = json.loads(base64.urlsafe_b64decode(payload_b64 + "=="))
    payload["profile_id"] = "profile_b"
    forged_payload = base64.urlsafe_b64encode(
        json.dumps(payload).encode("utf-8")
    ).decode("ascii").rstrip("=")
    assert authority.verify(f"{forged_payload}.{signature}", "profile_b", now=1_000.0) is None
    flipped = ("0" if signature[0] != "0" else "1") + signature[1:]
    assert authority.verify(f"{payload_b64}.{flipped}", "profile_a", now=1_000.0) is None


def test_grant_signed_by_another_key_is_rejected(tmp_path):
    authority, _ = _authority(tmp_path)
    other, _ = _authority(tmp_path, name="other_key")
    grant = other.mint("profile_a", now=1_000.0)
    assert authority.verify(grant, "profile_a", now=1_000.0) is None


@pytest.mark.parametrize(
    "garbage",
    ["", ".", "abc", "a.b.c", "!!!.???", "e30.invalidsig", "e30." + "0" * 64],
)
def test_malformed_grants_are_rejected_without_raising(tmp_path, garbage):
    authority, _ = _authority(tmp_path)
    assert authority.verify(garbage, "profile_a", now=1_000.0) is None


def test_missing_or_short_key_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="key"):
        ViewerGrantAuthority(tmp_path / "missing")
    key = tmp_path / "short_key"
    key.write_text("short")
    key.chmod(0o600)
    with pytest.raises(ValueError, match="key"):
        ViewerGrantAuthority(key)


def test_grants_for_same_profile_are_unique(tmp_path):
    authority, _ = _authority(tmp_path)
    first = authority.mint("profile_a", now=1_000.0)
    second = authority.mint("profile_a", now=1_000.0)
    assert first != second
