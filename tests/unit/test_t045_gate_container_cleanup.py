"""t045 AC-002 / p048: gate container + network prefix cleanup.

The cleanup selector is a pure function over container/network name lists;
tests inject those lists with monkeypatch and never touch a real daemon.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = REPO_ROOT / "scripts" / "gate_container_cleanup.py"

_SPEC = importlib.util.spec_from_file_location("gate_container_cleanup", MODULE_PATH)
assert _SPEC is not None and _SPEC.loader is not None
cleanup = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = cleanup
_SPEC.loader.exec_module(cleanup)


@pytest.fixture
def inject_names(monkeypatch: pytest.MonkeyPatch):
    def _inject(containers: list[str], networks: list[str]) -> None:
        monkeypatch.setattr(
            cleanup, "_list_container_names", lambda client: list(containers)
        )
        monkeypatch.setattr(
            cleanup, "_list_network_names", lambda client: list(networks)
        )
        monkeypatch.setattr(
            cleanup,
            "_list_container_labels",
            lambda client: {
                name: {"com.cbrowser.prefix": name} for name in containers
            },
        )

    return _inject


class _FakeContainer:
    def __init__(
        self, name: str, labels: dict[str, str] | None = None
    ) -> None:
        self.name = name
        self.labels = labels or {}
        self.calls: list[str] = []

    def stop(self, **kwargs: Any) -> None:
        self.calls.append("stop")

    def kill(self) -> None:
        self.calls.append("kill")

    def remove(self, **kwargs: Any) -> None:
        self.calls.append("remove")


class _FakeNetwork:
    def __init__(self, name: str) -> None:
        self.name = name
        self.calls: list[str] = []

    def remove(self) -> None:
        self.calls.append("remove")


class _ContainersCollection:
    def __init__(self, objects: list[_FakeContainer]) -> None:
        self._objects = {o.name: o for o in objects}
        self.get_calls: list[str] = []

    def list(self, all: bool = True) -> list[_FakeContainer]:
        return list(self._objects.values())

    def get(self, name: str) -> _FakeContainer:
        self.get_calls.append(name)
        return self._objects[name]


class _NetworksCollection:
    def __init__(self, objects: list[_FakeNetwork]) -> None:
        self._objects = {o.name: o for o in objects}
        self.get_calls: list[str] = []

    def list(self) -> list[_FakeNetwork]:
        return list(self._objects.values())

    def get(self, name: str) -> _FakeNetwork:
        self.get_calls.append(name)
        return self._objects[name]


class _FakeClient:
    def __init__(
        self, containers: list[_FakeContainer], networks: list[_FakeNetwork]
    ) -> None:
        self.containers = _ContainersCollection(containers)
        self.networks = _NetworksCollection(networks)


def test_leftover_prefix_containers_are_selected(inject_names: Any) -> None:
    inject_names(
        [
            "t007-fe-session-abc-browser",
            "t006-relay-deadbeef-supervisor",
            "cbrowser-t003-impl-http-1234",
            "cbrowser-t004-net-5678",
            "t005-inv-42-net-profile",
        ],
        [],
    )

    plan = cleanup.collect_targets(object())

    assert plan.containers == frozenset(
        {
            "t007-fe-session-abc-browser",
            "t006-relay-deadbeef-supervisor",
            "cbrowser-t003-impl-http-1234",
            "cbrowser-t004-net-5678",
            "t005-inv-42-net-profile",
        }
    )
    assert plan.networks == frozenset()


def test_production_and_non_whitelist_containers_are_preserved(
    inject_names: Any,
) -> None:
    inject_names(
        [
            "cbrowser-api",
            "cbrowser-gateway",
            "cbrowser-supervisor",
            "cbrowser-caddy",
            "some-other-session",
            "t007X",
            "cbrowser-t007-extra-session",
        ],
        [],
    )

    plan = cleanup.collect_targets(object())

    assert plan.containers == frozenset()


def test_network_prefix_cleanup(inject_names: Any) -> None:
    inject_names(
        [],
        [
            "t006-relay-deadbeef-edge",
            "cbrowser-t003-impl-http-9999",
            "t005-off-77-net-profile_a",
            "cbrowser-api-net",
            "bridge",
            "host",
            "none",
        ],
    )

    plan = cleanup.collect_targets(object())

    assert plan.networks == frozenset(
        {
            "t006-relay-deadbeef-edge",
            "cbrowser-t003-impl-http-9999",
            "t005-off-77-net-profile_a",
        }
    )
    assert plan.containers == frozenset()


def test_exact_prefix_matching(inject_names: Any) -> None:
    inject_names(
        ["t007-xxx", "t007X", "cbrowser-t007-extra-session", "t007-media-stream"],
        [],
    )

    plan = cleanup.collect_targets(object())

    assert "t007-xxx" in plan.containers
    assert "t007-media-stream" in plan.containers
    assert "t007X" not in plan.containers
    assert "cbrowser-t007-extra-session" not in plan.containers


def test_pure_selector_is_independent_of_docker() -> None:
    plan = cleanup.select_cleanup_targets(
        ["t007-a", "cbrowser-api", "t007X"],
        ["t006-edge", "bridge"],
    )

    assert plan.containers == frozenset({"t007-a"})
    assert plan.networks == frozenset({"t006-edge"})


def test_production_names_never_match_even_with_broad_prefix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(cleanup, "TEST_RESOURCE_PREFIXES", ("cbrowser-",))

    assert cleanup.is_test_resource("cbrowser-api") is False
    assert cleanup.is_test_resource("cbrowser-gateway") is False
    assert cleanup.is_test_resource("cbrowser-supervisor") is False
    assert cleanup.is_test_resource("cbrowser-caddy") is False
    assert cleanup.is_test_resource("cbrowser-t003-impl-http-1") is True


def test_run_cleanup_deletes_only_whitelisted_resources(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    c_target = _FakeContainer(
        "t007-a", {"com.cbrowser.prefix": "t007-previous-run"}
    )
    c_prod = _FakeContainer("cbrowser-api")
    n_target = _FakeNetwork("t006-edge")
    n_default = _FakeNetwork("bridge")
    client = _FakeClient([c_target, c_prod], [n_target, n_default])
    monkeypatch.setattr(
        cleanup, "_list_container_names", lambda c: ["t007-a", "cbrowser-api"]
    )
    monkeypatch.setattr(
        cleanup, "_list_network_names", lambda c: ["t006-edge", "bridge"]
    )

    plan = cleanup.run_cleanup(client)

    assert plan.containers == frozenset({"t007-a"})
    assert plan.networks == frozenset({"t006-edge"})
    assert "stop" in c_target.calls
    assert "remove" in c_target.calls
    assert c_prod.calls == []
    assert "remove" in n_target.calls
    assert n_default.calls == []
    assert client.containers.get_calls == ["t007-a"]
    assert client.networks.get_calls == ["t006-edge"]


def test_foreign_session_container_is_not_a_gate_leftover() -> None:
    """名字碰巧命中测试前缀、但 com.cbrowser.prefix 归属其它会话的容器
    不得被门禁清理删除；只有带测试白名单 label 的残留才纳入计划。"""
    plan = cleanup.select_cleanup_targets(
        ["t007-foreign-session", "t007-stale-leftover", "cbrowser-api"],
        [],
        container_labels={
            "t007-foreign-session": {
                "com.cbrowser.prefix": "external-session-xyz"
            },
            "t007-stale-leftover": {
                "com.cbrowser.prefix": "t007-previous-run"
            },
        },
    )

    assert plan.containers == frozenset({"t007-stale-leftover"})


def test_gate_start_cleanup_never_targets_later_worker_containers() -> None:
    """启动清理在所有 E2E worker 容器创建之前执行，此刻容器列表为空，
    计划必须为空；随后启动的 worker A / worker B 容器不可能被纳入删除。
    worker 隔离由 run_gates.sh 的调用时序保证（启动 / 退出各一次，
    E2E 运行期间不调用清理脚本）。"""
    plan = cleanup.select_cleanup_targets([], [], container_labels={})
    assert plan.containers == frozenset()
    assert plan.networks == frozenset()

    active = cleanup.select_cleanup_targets(
        ["t007-worker-a-browser", "t007-worker-b-browser"],
        ["t006-worker-edge"],
        container_labels={
            "t007-worker-a-browser": {"com.cbrowser.prefix": "t007-run-a"},
            "t007-worker-b-browser": {"com.cbrowser.prefix": "t007-run-b"},
        },
    )
    assert active.containers == frozenset(
        {"t007-worker-a-browser", "t007-worker-b-browser"}
    )
    assert active.networks == frozenset({"t006-worker-edge"})


def test_label_lookup_failure_deletes_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """review f001: an SDK label fault must fail closed, never fall back to a
    name-only match that could delete another worker's containers."""
    monkeypatch.setattr(
        cleanup,
        "_list_container_names",
        lambda client: ["t007-a", "t006-b"],
    )
    monkeypatch.setattr(cleanup, "_list_network_names", lambda client: [])

    def boom(client: Any) -> None:
        raise RuntimeError("docker SDK label lookup failed")

    monkeypatch.setattr(cleanup, "_list_container_labels", boom)
    deleted: list[str] = []
    monkeypatch.setattr(
        cleanup,
        "_delete_container",
        lambda client, name: deleted.append(name),
    )
    monkeypatch.setattr(
        cleanup,
        "_delete_network",
        lambda client, name: deleted.append(name),
    )

    with pytest.raises(cleanup.LabelLookupError):
        cleanup.run_cleanup(object())
    assert deleted == []


def test_incomplete_label_lookup_deletes_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A partial label map cannot authorize any name-only deletion."""
    monkeypatch.setattr(
        cleanup, "_list_container_names", lambda client: ["t007-a"]
    )
    monkeypatch.setattr(cleanup, "_list_network_names", lambda client: [])
    monkeypatch.setattr(cleanup, "_list_container_labels", lambda client: {})
    deleted: list[str] = []
    monkeypatch.setattr(
        cleanup,
        "_delete_container",
        lambda client, name: deleted.append(name),
    )

    with pytest.raises(cleanup.LabelLookupError):
        cleanup.run_cleanup(object())
    assert deleted == []


def test_main_returns_failure_on_label_lookup_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """main() propagates fail-closed as a non-zero gate cleanup step."""
    import types

    fake_docker = types.ModuleType("docker")
    fake_docker.from_env = lambda **kwargs: object()
    monkeypatch.setitem(sys.modules, "docker", fake_docker)
    monkeypatch.setattr(
        cleanup, "_list_container_names", lambda client: ["t007-a"]
    )
    monkeypatch.setattr(cleanup, "_list_network_names", lambda client: [])

    def boom(client: Any) -> None:
        raise RuntimeError("label API down")

    monkeypatch.setattr(cleanup, "_list_container_labels", boom)
    assert cleanup.main() == 1
