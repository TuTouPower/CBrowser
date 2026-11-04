"""t031 dialog attendant: state machine + service connection."""

from __future__ import annotations

import asyncio
import json

import pytest
from cbrowser.runtime_agent.dialog_attendant import (
    DialogAttendant,
    DialogAttendantService,
)


def test_attendant_holds_and_releases():
    attendant = DialogAttendant()
    attendant.note_attached("s1", "page-1")
    attendant.note_opening(
        "s1", {"type": "confirm", "message": "Leave?", "url": "https://x/"}
    )
    held = attendant.held_dialogs()
    assert len(held) == 1
    assert held[0].target_id == "page-1"
    assert held[0].dialog_type == "confirm"
    assert held[0].message == "Leave?"
    # Unknown session: opening without attach is ignored.
    attendant.note_opening("s-unknown", {"type": "alert", "message": "?"})
    assert len(attendant.held_dialogs()) == 1
    # Close clears only that session's dialog.
    attendant.note_attached("s2", "page-2")
    attendant.note_opening("s2", {"type": "alert", "message": "Hi"})
    attendant.note_closed("s1")
    assert [d.target_id for d in attendant.held_dialogs()] == ["page-2"]
    # Detach clears the dialog too.
    attendant.note_detached("s2")
    assert attendant.held_dialogs() == []
    # Release clears everything and marks released.
    attendant.note_attached("s3", "page-3")
    attendant.note_opening("s3", {"type": "prompt", "message": "Name?"})
    attendant.release()
    assert attendant.held_dialogs() == []
    assert attendant.released is True
    attendant.rearm()
    assert attendant.released is False


class _FakeWs:
    """Minimal websocket double: scripted inbound, recorded outbound.

    With wait_for_more=False (default) the pump ends when the scripted
    messages run out; with True it waits for messages appended later
    (needed when the test answers through the service connection).
    """

    def __init__(self, inbound: list[dict], *, wait_for_more: bool = False):
        self._queue: asyncio.Queue = asyncio.Queue()
        for msg in inbound:
            self._queue.put_nowait(msg)
        self._wait_for_more = wait_for_more
        self.sent: list[dict] = []
        self.closed = False

    async def send(self, text: str) -> None:
        self.sent.append(json.loads(text))

    async def close(self) -> None:
        self.closed = True

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._queue.empty() and not self._wait_for_more:
            raise StopAsyncIteration
        return json.dumps(await self._queue.get())


@pytest.mark.asyncio
async def test_service_attaches_pages_and_holds_dialog():
    inbound = [
        # getTargets response (id 2: setDiscoverTargets is id 1).
        {
            "id": 2,
            "result": {
                "targetInfos": [{"targetId": "page-1", "type": "page"}]
            },
        },
        # attachToTarget response for page-1 (id 3).
        {"id": 3, "result": {"sessionId": "att-1"}},
        # A dialog opens on the attendant's session.
        {
            "method": "Page.javascriptDialogOpening",
            "sessionId": "att-1",
            "params": {
                "url": "https://x/",
                "message": "Are you sure?",
                "type": "confirm",
            },
        },
    ]
    fake = _FakeWs(inbound, wait_for_more=True)

    async def connect(url: str, **kwargs):
        return fake

    service = DialogAttendantService(connect=connect)
    task = asyncio.create_task(service._run("ws://browser/devtools"))
    # Wait until the dialog is held, then assert while connected.
    for _ in range(100):
        if service.attendant.held_dialogs():
            break
        await asyncio.sleep(0.01)
    held = service.attendant.held_dialogs()
    assert len(held) == 1
    assert held[0].target_id == "page-1"
    assert held[0].dialog_type == "confirm"
    # The service sent discovery + getTargets + attach + Page.enable.
    methods = [msg["method"] for msg in fake.sent]
    assert methods[0] == "Target.setDiscoverTargets"
    assert methods[1] == "Target.getTargets"
    assert methods[2] == "Target.attachToTarget"
    assert methods[3] == "Page.enable"
    assert methods[3] and fake.sent[3].get("sessionId") == "att-1"
    # t031_code_f006: ending the service connection releases the held
    # dialog -- its session is dead and no later session can answer an
    # already-open dialog, so peek must not report it anymore.
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    assert service.attendant.held_dialogs() == []
    assert service.attendant.released is True
    assert fake.closed is True


@pytest.mark.asyncio
async def test_service_target_created_attach_records_session():
    """t031_test_f008: a page created after startup (Target.targetCreated)
    must attach AND record its session, so a dialog opening on it is
    held -- the branch the code f007 split once dropped."""
    fake = _FakeWs([], wait_for_more=True)

    async def connect(url: str, **kwargs):
        return fake

    service = DialogAttendantService(connect=connect)
    task = asyncio.create_task(service._run("ws://browser/devtools"))
    try:
        # Wait for discovery sends, then inject a late page creation.
        for _ in range(100):
            if len(fake.sent) >= 2:
                break
            await asyncio.sleep(0.01)
        await fake._queue.put(
            {
                "method": "Target.targetCreated",
                "params": {
                    "targetInfo": {"targetId": "page-9", "type": "page"}
                },
            }
        )
        # Wait for the attach send, then answer it with a session id.
        attach_id = None
        for _ in range(100):
            for msg in fake.sent:
                if msg.get("method") == "Target.attachToTarget" and (
                    msg.get("params") or {}
                ).get("targetId") == "page-9":
                    attach_id = msg["id"]
                    break
            if attach_id is not None:
                break
            await asyncio.sleep(0.01)
        assert attach_id is not None
        await fake._queue.put(
            {"id": attach_id, "result": {"sessionId": "att-9"}}
        )
        # Page.enable on the new session proves the mapping stuck.
        for _ in range(100):
            if any(
                m.get("method") == "Page.enable"
                and m.get("sessionId") == "att-9"
                for m in fake.sent
            ):
                break
            await asyncio.sleep(0.01)
        # A dialog opening on that session is now held for page-9.
        await fake._queue.put(
            {
                "method": "Page.javascriptDialogOpening",
                "sessionId": "att-9",
                "params": {
                    "url": "https://x/",
                    "message": "Hi?",
                    "type": "alert",
                },
            }
        )
        for _ in range(100):
            if service.attendant.held_dialogs():
                break
            await asyncio.sleep(0.01)
        held = service.attendant.held_dialogs()
        assert len(held) == 1
        assert held[0].target_id == "page-9"
        assert held[0].dialog_type == "alert"
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
    fake = _FakeWs([])

    async def connect(url: str, **kwargs):
        return fake

    service = DialogAttendantService(connect=connect)
    service.attendant.note_attached("s1", "page-1")
    service.attendant.note_opening("s1", {"type": "alert", "message": "x"})
    task = asyncio.create_task(service._run("ws://browser/devtools"))
    await asyncio.sleep(0)
    await service.release()
    assert service.attendant.held_dialogs() == []
    assert service.attendant.released is True
    assert task.done()


class _AnswerFakeWs(_FakeWs):
    """Answers handleJavaScriptDialog requests with a success response."""

    def __init__(self, inbound: list[dict]):
        super().__init__(inbound, wait_for_more=True)

    async def send(self, text: str) -> None:
        msg = json.loads(text)
        await super().send(text)
        if msg.get("method") == "Page.handleJavaScriptDialog":
            await self._queue.put({"id": msg["id"], "result": {}})


@pytest.mark.asyncio
async def test_service_answer_dialog_on_attendant_session():
    inbound = [
        {
            "id": 2,
            "result": {
                "targetInfos": [{"targetId": "page-1", "type": "page"}]
            },
        },
        {"id": 3, "result": {"sessionId": "att-1"}},
        {
            "method": "Page.javascriptDialogOpening",
            "sessionId": "att-1",
            "params": {
                "url": "https://x/",
                "message": "Are you sure?",
                "type": "confirm",
            },
        },
    ]
    fake = _AnswerFakeWs(inbound)

    async def connect(url: str, **kwargs):
        return fake

    service = DialogAttendantService(connect=connect)
    service.arm("ws://browser/devtools")
    task = service._task
    assert task is not None
    # Wait until the dialog is held, then answer through the service.
    for _ in range(100):
        if service.attendant.held_dialogs():
            break
        await asyncio.sleep(0.01)
    assert service.attendant.held_dialogs()
    answered = await service.answer_dialog("page-1", accept=False)
    assert answered is not None
    assert answered["type"] == "confirm"
    assert answered["target_id"] == "page-1"
    assert service.attendant.held_dialogs() == []
    # The answer went out on the attendant's own session.
    handle = [m for m in fake.sent if m["method"] == "Page.handleJavaScriptDialog"]
    assert len(handle) == 1
    assert handle[0]["sessionId"] == "att-1"
    assert handle[0]["params"]["accept"] is False
    # No held dialog: answer returns None without sending.
    assert await service.answer_dialog("page-1", accept=True) is None
    await service.release()
    assert task.done()


@pytest.mark.asyncio
async def test_service_answer_dialog_returns_none_when_not_running():
    service = DialogAttendantService()
    service.attendant.note_attached("s1", "page-1")
    service.attendant.note_opening("s1", {"type": "alert", "message": "x"})
    assert await service.answer_dialog("page-1", accept=True) is None
