"""Run ownership replaces the retired name-prefix cleanup contract (t060)."""

from types import SimpleNamespace

import pytest

from scripts import gate_container_cleanup as cleanup


def test_no_labels_never_authorize_deletion(tmp_path):
    plan = cleanup.select_cleanup_targets(["t007-a"], ["t006-edge"], runs_dir=tmp_path)
    assert not plan.containers and not plan.networks


def test_unknown_run_never_authorizes_deletion(tmp_path):
    plan = cleanup.select_cleanup_targets(
        ["t007-a"], [], {"t007-a": {cleanup.RUN_LABEL: "a" * 32}}, runs_dir=tmp_path
    )
    assert not plan.containers


def test_label_lookup_error_deletes_nothing(tmp_path):
    def fail(**kwargs):
        raise RuntimeError("Docker label API unavailable")

    client = SimpleNamespace(containers=SimpleNamespace(list=fail))
    with pytest.raises(cleanup.LabelLookupError):
        cleanup.run_cleanup(client, tmp_path)


def test_unknown_registry_performs_no_docker_calls(monkeypatch):
    monkeypatch.delenv("CBROWSER_GATE_RUNS_DIR", raising=False)
    assert cleanup.main() == 0


def test_sparse_docker_container_without_name_is_cleaned_by_id(tmp_path):
    run = "a" * 32
    (tmp_path / (run + ".lock")).touch()
    removed = []
    container = SimpleNamespace(
        id="container-id",
        name=None,
        attrs={"Names": ["/test"], "Labels": {cleanup.RUN_LABEL: run}},
        remove=lambda **kw: removed.append("container-id"),
    )
    network = SimpleNamespace(
        id="network-id",
        name="network",
        attrs={"Labels": {cleanup.RUN_LABEL: run}},
        remove=lambda: removed.append("network-id"),
    )
    client = SimpleNamespace(
        containers=SimpleNamespace(
            list=lambda **kw: [container],
            get=lambda key: container if key == container.id else None,
        ),
        networks=SimpleNamespace(
            list=lambda: [network],
            get=lambda key: network if key == network.id else None,
        ),
    )
    plan = cleanup.run_cleanup(client, tmp_path)
    assert plan.containers == frozenset({"container-id"})
    assert plan.networks == frozenset({"network-id"})
    assert removed == ["container-id", "network-id"]


@pytest.mark.parametrize("vanished", ["container", "network"])
def test_concurrent_cleanup_accepts_already_vanished_resources(monkeypatch, vanished):
    from docker.errors import NotFound

    plan = cleanup.CleanupPlan(frozenset({"box"}), frozenset({"net"}))
    monkeypatch.setattr(cleanup, "collect_targets", lambda client, directory: plan)
    removed = []

    def get_container(name):
        if vanished == "container":
            raise NotFound("another ended-run cleanup already removed container")
        return SimpleNamespace(remove=lambda **kw: removed.append("box"))

    def get_network(name):
        if vanished == "network":
            raise NotFound("another ended-run cleanup already removed network")
        return SimpleNamespace(remove=lambda: removed.append("net"))

    client = SimpleNamespace(
        containers=SimpleNamespace(get=get_container),
        networks=SimpleNamespace(get=get_network),
    )
    assert cleanup.run_cleanup(client) == plan
    assert removed == (["net"] if vanished == "container" else ["box"])
