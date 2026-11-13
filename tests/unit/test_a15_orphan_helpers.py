"""A15: orphan helper scan rejects suspicious identities per resource."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from cbrowser.supervisor.docker_adapter import DockerAdapter
from cbrowser.supervisor.path_validator import PathValidator

BROWSER = "sha256:f2a8d42810c13c8480b83e4308669c754e86b0fe4a24c6215159e43a8d1f5346"
STREAM = "sha256:072e86762d2f1810e86a2d20169d4be451b5a19e0ebabc880e882de63ac0d531"


class _Container:
    def __init__(self, name, labels):
        self.name = name
        self.labels = labels
        self.removed = False

    def remove(self, force=False):
        self.removed = True


def _labels(role, prefix, deployment_id=None):
    labels = {
        "com.cbrowser.prefix": prefix,
        "com.cbrowser.managed-by": "supervisor",
        "com.cbrowser.role": role,
    }
    if deployment_id is not None:
        labels["com.cbrowser.instance-id"] = deployment_id
    return labels


def _adapter(tmp_path, candidates):
    root = tmp_path / "data"
    engine = root / "engine_cache"
    engine.mkdir(parents=True)
    (engine / "geoip").mkdir(parents=True)
    client = SimpleNamespace(
        containers=SimpleNamespace(list=lambda **kwargs: list(candidates))
    )
    return DockerAdapter(
        path_validator=PathValidator(root),
        engine_cache_dir=engine,
        docker_client=client,
        browser_image=BROWSER,
        stream_image=STREAM,
        policy_image=BROWSER,
        # t069: cleanup only claims resources whose instance-id label
        # matches the configured deployment identity.
        deployment_instance_id="dep-a15",
    )


def test_mixed_candidates_only_strict_owner_is_deleted(tmp_path):
    adapter = _adapter(tmp_path, [])
    prefix = adapter.resource_prefix
    legal = _Container(
        f"{prefix}-policy-abcdef012345",
        _labels("network-policy", prefix, "dep-a15"),
    )
    wrong_name = _Container(
        f"{prefix}-policy-NOTHEXVALUE",
        _labels("network-policy", prefix, "dep-a15"),
    )
    unrelated = _Container(
        "external-container", _labels("database", prefix, "dep-a15")
    )
    adapter.client.containers.list = lambda **kwargs: [
        legal,
        wrong_name,
        unrelated,
    ]

    adapter._cleanup_orphan_helpers()

    assert legal.removed is True
    assert wrong_name.removed is False
    assert unrelated.removed is False


def test_single_bad_candidate_does_not_abort_remaining_scan(tmp_path):
    adapter = _adapter(tmp_path, [])
    prefix = adapter.resource_prefix
    bad = _Container(
        f"{prefix}-cache-NOTHEXVALUE", _labels("cache-init", prefix)
    )
    later_legal = _Container(
        f"{prefix}-x11-0123456789ab",
        _labels("x11-permissions", prefix, "dep-a15"),
    )
    adapter.client.containers.list = lambda **kwargs: [bad, later_legal]

    adapter._cleanup_orphan_helpers()

    assert bad.removed is False
    assert later_legal.removed is True


def test_mismatched_prefix_is_retained_and_recorded(tmp_path, caplog):
    adapter = _adapter(tmp_path, [])
    prefix = adapter.resource_prefix
    foreign = _Container(
        f"{prefix}-policy-abcdef012345",
        _labels("network-policy", "some-other-prefix"),
    )
    adapter.client.containers.list = lambda **kwargs: [foreign]

    adapter._cleanup_orphan_helpers()

    assert foreign.removed is False
    assert "Orphan helper identity mismatch retained" in caplog.text
    assert foreign.name not in caplog.text


def test_strict_name_match_is_not_relaxed(tmp_path):
    adapter = _adapter(tmp_path, [])
    prefix = adapter.resource_prefix
    near_miss = _Container(
        f"{prefix}-policy-abcdef01234",
        _labels("network-policy", prefix, "dep-a15"),
    )
    long_tail = _Container(
        f"{prefix}-policy-abcdef0123456",
        _labels("network-policy", prefix, "dep-a15"),
    )
    uppercase = _Container(
        f"{prefix}-policy-ABCDEF012345",
        _labels("network-policy", prefix, "dep-a15"),
    )
    legal = _Container(
        f"{prefix}-policy-abcdef012345",
        _labels("network-policy", prefix, "dep-a15"),
    )
    adapter.client.containers.list = lambda **kwargs: [
        near_miss,
        long_tail,
        uppercase,
        legal,
    ]

    adapter._cleanup_orphan_helpers()

    assert near_miss.removed is False
    assert long_tail.removed is False
    assert uppercase.removed is False
    assert legal.removed is True
