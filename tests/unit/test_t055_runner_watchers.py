"""t055 A13: runner watchers each close only their own stream.

The container watcher's shutdown race is extracted into
``_watch_container_events``, symmetric with ``_watch_network_events``.
A watcher closes only the stream it was handed: the container watcher's
shutdown must never close the network watcher's stream, and vice versa.
"""

from __future__ import annotations

import threading

from cbrowser.supervisor.runner import (
    _watch_container_events,
    _watch_network_events,
)

PREFIX = "cbrowser-t005"


def _event(action: str, role: str = "browser", prefix: str = PREFIX) -> dict:
    # p057 shape: a Docker container event carries Type/Action and the
    # deployment prefix + business role as Actor attributes.
    return {
        "Type": "container",
        "Action": action,
        "Actor": {
            "Attributes": {
                "com.cbrowser.prefix": prefix,
                "com.cbrowser.role": role,
            }
        },
    }


def _net_event(name: str) -> dict:
    return {"Actor": {"Attributes": {"name": name}}, "id": name}


class _RecordingStream:
    def __init__(self, events: list[dict]) -> None:
        self.events = events
        self.iterated = False
        self.closed = False

    def __iter__(self):
        self.iterated = True
        yield from self.events

    def close(self) -> None:
        self.closed = True


class _FakeDockerClient:
    def __init__(self, stream: _RecordingStream) -> None:
        self.stream = stream
        self.calls: list[dict] = []

    def events(self, **kwargs):
        self.calls.append(kwargs)
        return self.stream


def test_container_watcher_closes_stream_when_stop_races_registration():
    """AC-010: shutdown between subscription and the stop check closes
    the stream and never starts pumping it."""
    stop = threading.Event()
    stream = _RecordingStream([_event("die")])
    client = _FakeDockerClient(stream)
    registered: list[_RecordingStream] = []
    wakes: list[str] = []
    closed: list[_RecordingStream] = []

    def _register(candidate) -> None:
        registered.append(candidate)
        # Simulate shutdown racing the subscription after registration.
        stop.set()

    _watch_container_events(
        client,
        PREFIX,
        stop,
        _register,
        lambda: wakes.append("wake"),
        lambda: closed.append(stream),
    )

    assert client.calls == [
        {
            "decode": True,
            "filters": {
                "type": "container",
                "label": f"com.cbrowser.prefix={PREFIX}",
            },
        }
    ]
    assert registered == [stream]
    assert closed == [stream]
    assert stream.iterated is False
    assert wakes == []


def test_container_watcher_pumps_matching_events_until_stop():
    stop = threading.Event()
    stream = _RecordingStream(
        [_event("die", prefix="other"), _event("die")]
    )
    client = _FakeDockerClient(stream)
    registered: list[_RecordingStream] = []
    wakes: list[str] = []
    closed: list[_RecordingStream] = []

    def _wake() -> None:
        wakes.append("wake")
        stop.set()

    _watch_container_events(
        client,
        PREFIX,
        stop,
        registered.append,
        _wake,
        lambda: closed.append(stream),
    )

    assert registered == [stream]
    assert stream.iterated is True
    assert wakes == ["wake"]
    # Normal pump exit leaves the stream for the caller's close pass;
    # the race branch is the one that closes here.
    assert closed == []


def test_watchers_close_only_their_own_stream():
    """AC-010: each watcher closes only the stream it was handed."""
    container_stream = _RecordingStream([_event("die")])
    network_stream = _RecordingStream([_net_event(f"{PREFIX}-net-p1")])
    container_client = _FakeDockerClient(container_stream)
    network_client = _FakeDockerClient(network_stream)
    container_closed: list[_RecordingStream] = []
    network_closed: list[_RecordingStream] = []

    # The container watcher shuts down mid-registration: it closes only
    # the container stream; the network stream is untouched.
    stop_container = threading.Event()

    def _register_container(candidate) -> None:
        stop_container.set()

    _watch_container_events(
        container_client,
        PREFIX,
        stop_container,
        _register_container,
        lambda: None,
        lambda: container_closed.append(container_stream),
    )
    assert container_closed == [container_stream]
    assert network_closed == []

    # The network watcher shuts down mid-registration: it closes only
    # the network stream; the container stream is untouched.
    stop_network = threading.Event()

    def _register_network(candidate) -> None:
        stop_network.set()

    _watch_network_events(
        network_client,
        PREFIX,
        stop_network,
        _register_network,
        lambda: None,
        lambda: network_closed.append(network_stream),
    )
    assert network_closed == [network_stream]
    assert container_closed == [container_stream]
