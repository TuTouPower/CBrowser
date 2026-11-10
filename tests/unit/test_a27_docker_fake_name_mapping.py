from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from docker.errors import NotFound
from docker.models.containers import ContainerCollection

from docker_doubles import FakeContainer, FakeDockerAdapter, FakeDockerClient


def _sdk_containers() -> ContainerCollection:
    def _inspect(_name: str) -> None:
        raise NotFound("No such container")

    api = SimpleNamespace(
        inspect_container=_inspect,
        containers=lambda **_kw: [],
    )
    return ContainerCollection(client=SimpleNamespace(api=api))


def test_missing_name_raises_not_found(tmp_path: Path) -> None:
    fake = FakeDockerAdapter(tmp_path)
    fake.remember_profile_number("p1", 1)
    with pytest.raises(NotFound):
        fake.containers.get(fake.get_browser_container_name("p1"))


def test_misspelled_name_raises_not_found_matching_sdk(tmp_path: Path) -> None:
    fake = FakeDockerAdapter(tmp_path)
    fake.remember_profile_number("p1", 1)
    browser = FakeContainer("inst-browser", "running")
    fake.containers.register(fake.get_browser_container_name("p1"), browser)
    typo = fake.get_browser_container_name("p1") + "-typo"
    with pytest.raises(NotFound):
        fake.containers.get(typo)
    with pytest.raises(NotFound):
        _sdk_containers().get(typo)


def test_unregistered_name_never_falls_back(tmp_path: Path) -> None:
    fake = FakeDockerAdapter(tmp_path)
    fake.remember_profile_number("p1", 1)
    fake.containers.register(
        fake.get_browser_container_name("p1"),
        FakeContainer("inst-browser", "running"),
    )
    with pytest.raises(NotFound):
        fake.containers.get("totally-unregistered-name")


def test_browser_and_stream_same_profile_are_distinct(tmp_path: Path) -> None:
    fake = FakeDockerAdapter(tmp_path)
    fake.remember_profile_number("p1", 1)
    browser = FakeContainer("inst-browser", "running")
    stream = FakeContainer("inst-stream", "running")
    browser_name = fake.get_browser_container_name("p1")
    stream_name = fake.get_stream_container_name("p1")
    fake.containers.register(browser_name, browser)
    fake.containers.register(stream_name, stream)
    assert fake.containers.get(browser_name) is browser
    assert fake.containers.get(stream_name) is stream
    assert fake.containers.get(browser_name) is not stream
    assert fake.containers.get(stream_name) is not browser
    assert set(fake.containers.list()) == {browser, stream}


def test_two_profiles_do_not_cross_resolve(tmp_path: Path) -> None:
    fake = FakeDockerAdapter(tmp_path)
    registered = {}
    for number, profile in enumerate(("p1", "p2"), start=1):
        fake.remember_profile_number(profile, number)
        for role, method in (
            ("browser", fake.get_browser_container_name),
            ("stream", fake.get_stream_container_name),
        ):
            name = method(profile)
            obj = FakeContainer(f"inst-{profile}-{role}", "running")
            registered[(profile, role)] = (name, obj)
            fake.containers.register(name, obj)
    for name, obj in registered.values():
        assert fake.containers.get(name) is obj
    assert (
        fake.containers.get(registered[("p1", "browser")][0])
        is not registered[("p2", "browser")][1]
    )
    assert (
        fake.containers.get(registered[("p1", "stream")][0])
        is not registered[("p2", "stream")][1]
    )
    assert len(fake.containers.list()) == 4


def test_client_containers_share_the_registry(tmp_path: Path) -> None:
    fake = FakeDockerAdapter(tmp_path)
    fake.remember_profile_number("p1", 1)
    browser = FakeContainer("inst-browser", "running")
    name = fake.get_browser_container_name("p1")
    fake.containers.register(name, browser)
    assert fake.client.containers.get(name) is browser


def test_fake_docker_client_supports_name_mapping() -> None:
    client = FakeDockerClient()
    c = FakeContainer("inst-1", "running")
    client.containers.register("c-name", c)
    assert client.containers.get("c-name") is c
    with pytest.raises(NotFound):
        client.containers.get("other-name")
