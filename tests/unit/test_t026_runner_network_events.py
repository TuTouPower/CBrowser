"""t026 AC-002 / test f001: the Docker network-event trigger path.

Round 1 drove convergence only by calling ``_converge_session``
directly; the watcher that turns a media-network event into a scan
wakeup had no coverage. The match + pump helpers are exercised here
against scripted event streams, including malformed events.
"""

from __future__ import annotations

import threading

from cbrowser.supervisor.runner import (
    _pump_network_events,
    _watch_network_events,
    media_network_event_matches,
)

PREFIX = "cbrowser-t005"


def _event(name: str) -> dict:
    return {"Actor": {"Attributes": {"name": name}}, "id": name}


def test_media_network_event_matching():
    assert media_network_event_matches(_event(f"{PREFIX}-net-p1"), PREFIX)
    assert not media_network_event_matches(_event(f"{PREFIX}-browser-p1"), PREFIX)
    assert not media_network_event_matches(_event("other-net-p1"), PREFIX)
    # Falls back to the event id when attributes carry no name.
    assert media_network_event_matches(
        {"Actor": {"Attributes": {}}, "id": f"{PREFIX}-net-p2"}, PREFIX
    )


def test_media_network_event_matching_tolerates_malformed_events():
    assert not media_network_event_matches({}, PREFIX)
    assert not media_network_event_matches({"Actor": None}, PREFIX)
    assert not media_network_event_matches("not-a-dict", PREFIX)
    assert not media_network_event_matches(None, PREFIX)


def test_pump_wakes_only_for_media_events_and_stops():
    hits: list[str] = []
    stop = threading.Event()
    events = iter(
        [
            _event("unrelated"),
            _event(f"{PREFIX}-net-p1"),
            _event(f"{PREFIX}-net-p2"),
        ]
    )
    _pump_network_events(events, PREFIX, lambda: hits.append("wake"), stop)
    assert hits == ["wake", "wake"]


def test_pump_stops_when_stop_event_set():
    hits: list[str] = []
    stop = threading.Event()

    def _on_match() -> None:
        hits.append("wake")
        stop.set()

    events = iter(
        [_event(f"{PREFIX}-net-p1"), _event(f"{PREFIX}-net-p2")]
    )
    _pump_network_events(events, PREFIX, _on_match, stop)
    # The stop flag is honored before the next event is processed.
    assert hits == ["wake"]


class _RecordingStream:
    def __init__(self, events: list[dict]) -> None:
        self.events = events
        self.iterated = False

    def __iter__(self):
        self.iterated = True
        yield from self.events


class _FakeDockerClient:
    def __init__(self, stream: _RecordingStream) -> None:
        self.stream = stream
        self.calls: list[dict] = []

    def events(self, **kwargs):
        self.calls.append(kwargs)
        return self.stream


def test_network_watcher_closes_stream_when_stop_races_registration():
    # t026_code_f012 / p035: shutdown that lands between stream
    # subscription and the stop check must close the stream and never
    # start pumping it.
    stop = threading.Event()
    stream = _RecordingStream([_event(f"{PREFIX}-net-p1")])
    client = _FakeDockerClient(stream)
    registered: list[_RecordingStream] = []
    wakes: list[str] = []
    closed: list[_RecordingStream] = []

    def _register(candidate) -> None:
        registered.append(candidate)
        # Simulate shutdown racing the subscription after registration.
        stop.set()

    _watch_network_events(
        client,
        PREFIX,
        stop,
        _register,
        lambda: wakes.append("wake"),
        lambda: closed.append(stream),
    )

    assert client.calls == [{"decode": True, "filters": {"type": "network"}}]
    assert registered == [stream]
    assert closed == [stream]
    assert stream.iterated is False
    assert wakes == []


def test_network_watcher_pumps_matching_events_until_stop():
    stop = threading.Event()
    stream = _RecordingStream(
        [_event("unrelated"), _event(f"{PREFIX}-net-p1")]
    )
    client = _FakeDockerClient(stream)
    registered: list[_RecordingStream] = []
    wakes: list[str] = []
    closed: list[_RecordingStream] = []

    def _wake() -> None:
        wakes.append("wake")
        stop.set()

    _watch_network_events(
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
    # Normal pump exit leaves the stream for the supervisor's final
    # close pass; the race branch is the one that closes here.
    assert closed == []
