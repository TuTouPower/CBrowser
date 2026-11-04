"""CLI end-to-end against a fake CDP server (t030, no browser needed)."""

from __future__ import annotations

import asyncio
import io
import json
import sys
from pathlib import Path

import pytest
import websockets

from cbrowser.agent_executor.cli import amain

TOKEN = "cbat_test_token_xyz"


class _FakeCdp:
    """Minimal CDP surface the executor session uses, with a live target set."""

    def __init__(self) -> None:
        self.received: list[dict] = []
        self.targets: dict[str, dict] = {
            "t-user": {"targetId": "t-user", "type": "page", "url": "http://x/"},
        }
        self._counter = 0
        self.hang_release = False
        self.hang_press = False

    def methods(self) -> list[str]:
        return [m.get("method", "") for m in self.received]

    async def handler(self, ws) -> None:
        async for raw in ws:
            try:
                msg = json.loads(raw)
            except ValueError:
                continue
            self.received.append(msg)
            method = msg.get("method")
            params = msg.get("params", {}) or {}
            msg_id = msg.get("id")
            session_id = msg.get("sessionId")
            result: dict = {}
            if method == "Target.getTargets":
                result = {"targetInfos": list(self.targets.values())}
            elif method == "Target.createTarget":
                self._counter += 1
                target_id = f"t-new-{self._counter}"
                self.targets[target_id] = {
                    "targetId": target_id,
                    "type": "page",
                    "url": params.get("url", "about:blank"),
                }
                result = {"targetId": target_id}
            elif method == "Target.attachToTarget":
                result = {"sessionId": f"s-{params.get('targetId')}"}
            elif method == "Page.getFrameTree":
                result = {
                    "frameTree": {
                        "frame": {"id": "f1", "loaderId": "l1"},
                        "childFrames": [],
                    }
                }
            elif method == "DOM.getDocument":
                result = {
                    "root": {
                        "nodeName": "HTML",
                        "backendNodeId": 1,
                        "attributes": [],
                        "children": [
                            {
                                "nodeName": "BODY",
                                "backendNodeId": 2,
                                "attributes": [],
                                "children": [
                                    {
                                        "nodeName": "BUTTON",
                                        "backendNodeId": 10,
                                        "attributes": ["id", "go"],
                                        "children": [],
                                    },
                                    {
                                        "nodeName": "INPUT",
                                        "backendNodeId": 11,
                                        "attributes": ["id", "q"],
                                        "children": [],
                                    },
                                ],
                            }
                        ],
                    }
                }
            elif method == "Accessibility.getFullAXTree":
                result = {
                    "nodes": [
                        {
                            "nodeId": 1,
                            "backendDOMNodeId": 10,
                            "frameId": "f1",
                            "role": {"value": "button"},
                            "name": {"value": "Go"},
                        },
                        {
                            "nodeId": 2,
                            "backendDOMNodeId": 11,
                            "frameId": "f1",
                            "role": {"value": "textbox"},
                            "name": {"value": "Search"},
                        },
                    ]
                }
            elif method == "DOM.resolveNode":
                result = {
                    "object": {
                        "type": "object",
                        "objectId": f"obj-{params.get('backendNodeId')}",
                    }
                }
            elif method == "DOM.describeNode":
                backend = params.get("objectId", "obj-10").split("-")[-1]
                names = {"10": "BUTTON", "11": "INPUT"}
                attrs = {"10": ["id", "go"], "11": ["id", "q"]}
                result = {
                    "node": {
                        "nodeName": names.get(backend, "DIV"),
                        "attributes": attrs.get(backend, []),
                    }
                }
            elif method == "DOM.getContentQuads":
                result = {"quads": [[0, 0, 100, 0, 100, 30, 0, 30]]}
            elif method == "DOM.pushNodesByBackendIdsToFrontend":
                result = {"nodeIds": [100]}
            elif method == "Runtime.evaluate":
                expr = params.get("expression", "")
                value = True if expr == "true" else "Fake"
                result = {"result": {"value": value}}
            elif method == "Target.closeTarget":
                self.targets.pop(params.get("targetId"), None)
            if (
                method == "Input.dispatchMouseEvent"
                and params.get("type") == "mousePressed"
                and self.hang_press
            ):
                # A dialog opened by the mousedown handler: the press
                # never completes and mouseReleased is never sent.  The
                # click must report release_skipped, not a complete click.
                await ws.send(
                    json.dumps(
                        {
                            "method": "Page.javascriptDialogOpening",
                            "sessionId": session_id,
                            "params": {
                                "url": "http://x/",
                                "message": "Sure?",
                                "type": "confirm",
                                "hasBrowserHandler": True,
                            },
                        }
                    )
                )
                continue
            if (
                method == "Input.dispatchMouseEvent"
                and params.get("type") == "mouseReleased"
                and self.hang_release
            ):
                # A modal dialog blocks the renderer: the release response
                # never arrives until the dialog is answered.  The click
                # must return early with the dialog surfaced, not hang.
                await ws.send(
                    json.dumps(
                        {
                            "method": "Page.javascriptDialogOpening",
                            "sessionId": session_id,
                            "params": {
                                "url": "http://x/",
                                "message": "Sure?",
                                "type": "confirm",
                                "hasBrowserHandler": True,
                            },
                        }
                    )
                )
                continue
            if method == "Page.enable" and session_id == "s-t-user":
                # Seed one open confirm on the user page right after attach,
                # so dialog_answer / dialog_wait have something to answer.
                await ws.send(
                    json.dumps(
                        {
                            "method": "Page.javascriptDialogOpening",
                            "sessionId": session_id,
                            "params": {
                                "url": "http://x/",
                                "message": "Sure?",
                                "type": "confirm",
                                "hasBrowserHandler": True,
                            },
                        }
                    )
                )
            response: dict = {"id": msg_id, "result": result}
            if session_id:
                response["sessionId"] = session_id
            await ws.send(json.dumps(response))


def _free_port() -> int:
    import socket

    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


async def _run_cli(
    fake: _FakeCdp,
    program: dict,
    monkeypatch: pytest.MonkeyPatch,
    capsys,
    tmp_path,
) -> tuple[int, dict, str]:
    port = _free_port()
    server = await websockets.serve(fake.handler, "127.0.0.1", port)
    monkeypatch.setenv("CBROWSER_AGENT_TOKEN", TOKEN)
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(program)))
    try:
        code = await amain(
            [
                "--endpoint",
                f"ws://127.0.0.1:{port}/cdp",
                "--profile",
                "p1",
                "--runtime-instance",
                "i1",
                "--state-file",
                str(tmp_path / "state.json"),
            ]
        )
    finally:
        server.close()
        await server.wait_closed()
    captured = capsys.readouterr()
    assert TOKEN not in captured.out
    assert TOKEN not in captured.err
    return code, json.loads(captured.out), captured.out


@pytest.mark.asyncio
async def test_cli_happy_path(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture, tmp_path
) -> None:
    fake = _FakeCdp()
    program = {
        "version": 1,
        "steps": [
            {"action": "targets"},
            {"action": "new_page", "url": "http://x/"},
            {"action": "adopt", "targetId": "t-user"},
            {"action": "snapshot", "targetId": "t-user"},
            {"action": "click", "targetId": "t-user", "ref": "f0e0"},
            {"action": "input", "targetId": "t-user", "ref": "f0e1", "text": "hi"},
            {"action": "extract", "targetId": "t-user", "expression": "document.title"},
            {"action": "dialog_answer", "targetId": "t-user", "answer": "dismiss"},
            {"action": "permission", "targetId": "t-user", "kind": "camera"},
            {"action": "cleanup"},
        ],
    }
    code, output, _ = await _run_cli(fake, program, monkeypatch, capsys, tmp_path)
    assert code == 0
    assert output["ok"] is True
    assert len(output["results"]) == 10
    assert output["results"][1]["result"]["target_id"] == "t-new-1"
    snapshot = output["results"][3]["result"]
    assert [n["ref"] for n in snapshot["nodes"]] == ["f0e0", "f0e1"]
    assert output["results"][7]["result"] == {"action": "dismiss"}
    assert output["results"][8]["result"]["decision"] == "needs_human"
    # The explicit cleanup step closed only the agent-created page, never
    # the user page.  A successful exit runs no implicit cleanup: the
    # session persists in the state file for later invocations.
    assert output["results"][9]["result"]["closed"] == ["t-new-1"]
    assert output["results"][9]["result"]["refused"] == []
    assert output["cleanup"] == {}
    assert "Browser.close" not in fake.methods()
    assert "Target.closeTarget" in fake.methods()
    assert "t-user" in fake.targets


@pytest.mark.asyncio
async def test_cli_step_failure_reports_code_and_still_cleans_up(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture, tmp_path
) -> None:
    fake = _FakeCdp()
    program = {
        "version": 1,
        "steps": [
            {"action": "new_page", "url": "http://x/"},
            {"action": "adopt", "targetId": "t-user"},
            {"action": "snapshot", "targetId": "t-user"},
            {"action": "click", "targetId": "t-user", "ref": "f0e99"},
        ],
    }
    code, output, _ = await _run_cli(fake, program, monkeypatch, capsys, tmp_path)
    assert code == 1
    assert output["ok"] is False
    assert output["error"]["code"] == "ref_stale"
    assert output["error"]["step"] == 3
    # Cleanup still ran after the failure.
    assert output["cleanup"]["closed"] == ["t-new-1"]
    assert "t-user" in fake.targets


@pytest.mark.asyncio
async def test_cli_ref_survives_across_invocations(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture, tmp_path
) -> None:
    """A ref snapshotted in one invocation acts in the next (state file).

    This is the AC-004 cross-call case: without persistence the second
    call would fail with ref_stale because its registry starts empty.
    """
    fake = _FakeCdp()
    port = _free_port()
    server = await websockets.serve(fake.handler, "127.0.0.1", port)
    monkeypatch.setenv("CBROWSER_AGENT_TOKEN", TOKEN)
    state_file = str(tmp_path / "state.json")
    try:
        monkeypatch.setattr(
            sys, "stdin", io.StringIO(json.dumps({
                "version": 1,
                "steps": [
                    {"action": "adopt", "targetId": "t-user"},
                    {"action": "snapshot", "targetId": "t-user"},
                ],
            }))
        )
        code = await amain([
            "--endpoint", f"ws://127.0.0.1:{port}/cdp",
            "--profile", "p1", "--runtime-instance", "i1",
            "--state-file", state_file,
        ])
        assert code == 0
        out1 = json.loads(capsys.readouterr().out)
        ref = out1["results"][1]["result"]["nodes"][0]["ref"]
        assert ref == "f0e0"
        # The fake seeds an open dialog at attach; answer it first so the
        # click below runs against a dialog-free page.
        monkeypatch.setattr(
            sys, "stdin", io.StringIO(json.dumps({
                "version": 1,
                "steps": [
                    {"action": "adopt", "targetId": "t-user"},
                    {"action": "dialog_answer", "targetId": "t-user",
                     "answer": "dismiss"},
                    {"action": "click", "targetId": "t-user", "ref": ref},
                ],
            }))
        )
        code = await amain([
            "--endpoint", f"ws://127.0.0.1:{port}/cdp",
            "--profile", "p1", "--runtime-instance", "i1",
            "--state-file", state_file,
        ])
        assert code == 0
        out2 = json.loads(capsys.readouterr().out)
        assert out2["ok"] is True
        assert out2["results"][2]["result"] == {"x": 50.0, "y": 15.0}
    finally:
        server.close()
        await server.wait_closed()


@pytest.mark.asyncio
async def test_cli_click_returns_early_when_it_opens_a_dialog(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture, tmp_path
) -> None:
    """A click that opens a modal dialog must not hang on the release.

    The release dispatch response never arrives while the dialog is open;
    awaiting it would deadlock the program (the answer step runs after
    click).  The click returns at once with the dialog surfaced.
    """
    fake = _FakeCdp()
    fake.hang_release = True
    program = {
        "version": 1,
        "steps": [
            {"action": "adopt", "targetId": "t-user"},
            {"action": "snapshot", "targetId": "t-user"},
            {"action": "click", "targetId": "t-user", "ref": "f0e0"},
        ],
    }
    code, output, _ = await _run_cli(fake, program, monkeypatch, capsys, tmp_path)
    assert code == 0
    assert output["ok"] is True
    click = output["results"][2]["result"]
    assert click["x"] == 50.0
    assert click["dialog"] == {"type": "confirm", "message": "Sure?"}


@pytest.mark.asyncio
async def test_cli_rejects_bad_program_version(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture, tmp_path
) -> None:
    fake = _FakeCdp()
    code, output, _ = await _run_cli(
        fake, {"version": 99, "steps": []}, monkeypatch, capsys, tmp_path
    )
    assert code == 2
    assert output["error"]["code"] == "invalid_program"


@pytest.mark.asyncio
async def test_cli_missing_step_fields_are_invalid_program_not_internal(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture, tmp_path
) -> None:
    # A malformed program is the caller's fault: it must surface as
    # invalid_program, never as internal_error (which would look like an
    # executor bug and send debugging down the wrong path).
    for steps in (
        [{"action": "click"}],
        [{"action": "click", "targetId": "t-user"}],
        [{"action": "input", "targetId": "t-user", "ref": "f0e0"}],
        [{"action": "wait_for_target_count"}],
        [{"action": "wait_for_target_count", "count": "two"}],
    ):
        fake = _FakeCdp()
        code, output, _ = await _run_cli(
            fake, {"version": 1, "steps": steps}, monkeypatch, capsys, tmp_path
        )
        assert code == 1
        assert output["error"]["code"] == "invalid_program"


@pytest.mark.asyncio
async def test_cli_state_file_from_another_runtime_is_discarded(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture, tmp_path
) -> None:
    """A state file re-pointed at another runtime must not validate.

    Run 1 snapshots and creates an agent page under runtime i1.  Run 2
    passes the same state file but runtime i2: the persisted ref must
    fail with ref_stale, and the persisted ledger must not authorize
    closing run 1's agent page (it is baseline-unknown in run 2).
    """
    fake = _FakeCdp()
    port = _free_port()
    server = await websockets.serve(fake.handler, "127.0.0.1", port)
    monkeypatch.setenv("CBROWSER_AGENT_TOKEN", TOKEN)
    state_file = str(tmp_path / "state.json")
    try:
        monkeypatch.setattr(
            sys,
            "stdin",
            io.StringIO(
                json.dumps(
                    {
                        "version": 1,
                        "steps": [
                            {"action": "new_page", "url": "http://x/"},
                            {"action": "adopt", "targetId": "t-user"},
                            {"action": "snapshot", "targetId": "t-user"},
                        ],
                    }
                )
            ),
        )
        code = await amain(
            [
                "--endpoint",
                f"ws://127.0.0.1:{port}/cdp",
                "--profile",
                "p1",
                "--runtime-instance",
                "i1",
                "--state-file",
                state_file,
            ]
        )
        assert code == 0
        capsys.readouterr()
        monkeypatch.setattr(
            sys,
            "stdin",
            io.StringIO(
                json.dumps(
                    {
                        "version": 1,
                        "steps": [
                            {
                                "action": "click",
                                "targetId": "t-user",
                                "ref": "f0e0",
                            },
                            {"action": "cleanup"},
                        ],
                    }
                )
            ),
        )
        code = await amain(
            [
                "--endpoint",
                f"ws://127.0.0.1:{port}/cdp",
                "--profile",
                "p1",
                "--runtime-instance",
                "i2",
                "--state-file",
                state_file,
            ]
        )
        assert code == 1
        out = json.loads(capsys.readouterr().out)
        assert out["error"]["code"] == "ref_stale"
        # The failure path still ran cleanup, but with the run-1 ledger
        # discarded it closed nothing: t-new-1 survives.
        assert out["cleanup"]["closed"] == []
        assert "t-new-1" in fake.targets
    finally:
        server.close()
        await server.wait_closed()


@pytest.mark.asyncio
async def test_cli_timeout_codes_are_distinguishable(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture, tmp_path
) -> None:
    # wait_for_target_count that never converges -> step_timeout.
    fake = _FakeCdp()
    code, output, _ = await _run_cli(
        fake,
        {
            "version": 1,
            "steps": [
                {
                    "action": "wait_for_target_count",
                    "count": 99,
                    "timeoutMs": 100,
                }
            ],
        },
        monkeypatch,
        capsys,
        tmp_path,
    )
    assert code == 1
    assert output["error"]["code"] == "step_timeout"
    # dialog_wait on a target with no dialog (a fresh agent page is never
    # seeded by the fake) -> dialog_timeout, after attach.
    fake = _FakeCdp()
    code, output, _ = await _run_cli(
        fake,
        {
            "version": 1,
            "steps": [
                {"action": "new_page", "url": "http://x/"},
                {
                    "action": "dialog_wait",
                    "targetId": "t-new-1",
                    "timeoutMs": 100,
                },
            ],
        },
        monkeypatch,
        capsys,
        tmp_path,
    )
    assert code == 1
    assert output["error"]["code"] == "dialog_timeout"
    # dialog_answer with no dialog open -> dialog_not_open.
    fake = _FakeCdp()
    code, output, _ = await _run_cli(
        fake,
        {
            "version": 1,
            "steps": [
                {"action": "new_page", "url": "http://x/"},
                {
                    "action": "dialog_answer",
                    "targetId": "t-new-1",
                    "answer": "dismiss",
                },
            ],
        },
        monkeypatch,
        capsys,
        tmp_path,
    )
    assert code == 1
    assert output["error"]["code"] == "dialog_not_open"
    # dialog_answer with a typo'd answer on an open dialog ->
    # invalid_program, not a silent fold into the opposite default.
    fake = _FakeCdp()
    code, output, _ = await _run_cli(
        fake,
        {
            "version": 1,
            "steps": [
                {"action": "adopt", "targetId": "t-user"},
                {
                    "action": "dialog_answer",
                    "targetId": "t-user",
                    "answer": "accep",
                },
            ],
        },
        monkeypatch,
        capsys,
        tmp_path,
    )
    assert code == 1
    assert output["error"]["code"] == "invalid_program"


@pytest.mark.asyncio
async def test_cli_program_timeout_and_cancel_are_distinguishable() -> None:
    """run_program maps program timeout and task cancel to distinct codes,
    and runs fail-safe cleanup in both cases."""
    from cbrowser.agent_executor.cli import run_program

    class _HangingSession:
        def __init__(self) -> None:
            self.cleaned = 0

        async def wait_for(self, *args):
            await asyncio.Event().wait()

        async def cleanup(self):
            self.cleaned += 1
            return {"closed": []}

        async def close(self):
            return None

    hanging = _HangingSession()
    output, _ = await run_program(
        hanging,
        {
            "version": 1,
            "steps": [
                {
                    "action": "wait_for",
                    "targetId": "t",
                    "expression": "true",
                }
            ],
        },
        program_timeout=0.05,
        token="",
    )
    assert output["error"]["code"] == "step_timeout"
    assert hanging.cleaned == 1

    hanging = _HangingSession()
    task = asyncio.create_task(
        run_program(
            hanging,
            {
                "version": 1,
                "steps": [
                    {
                        "action": "wait_for",
                        "targetId": "t",
                        "expression": "true",
                    }
                ],
            },
            program_timeout=30.0,
            token="",
        )
    )
    await asyncio.sleep(0.05)
    task.cancel()
    output, _ = await task
    assert output["error"]["code"] == "cancelled"
    assert hanging.cleaned == 1


@pytest.mark.asyncio
async def test_cli_set_input_files_step(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture, tmp_path
) -> None:
    fake = _FakeCdp()
    program = {
        "version": 1,
        "steps": [
            {"action": "adopt", "targetId": "t-user"},
            {"action": "snapshot", "targetId": "t-user"},
            {
                "action": "set_input_files",
                "targetId": "t-user",
                "ref": "f0e1",
                "files": ["/tmp/probe-upload.txt"],
            },
        ],
    }
    code, output, _ = await _run_cli(fake, program, monkeypatch, capsys, tmp_path)
    assert code == 0, output
    assert output["ok"] is True
    sent = [
        m
        for m in fake.received
        if m.get("method") == "DOM.setFileInputFiles"
    ]
    assert len(sent) == 1
    assert sent[0]["params"]["files"] == ["/tmp/probe-upload.txt"]
    assert "DOM.pushNodesByBackendIdsToFrontend" in fake.methods()


@pytest.mark.asyncio
async def test_cli_click_reports_release_skipped_when_dialog_opens_on_press(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture, tmp_path
) -> None:
    """A mousedown-triggered dialog leaves the press uncompleted.

    mouseReleased was never sent, so the click did not happen; the
    result must say so instead of looking like a complete click.
    """
    fake = _FakeCdp()
    fake.hang_press = True
    program = {
        "version": 1,
        "steps": [
            {"action": "adopt", "targetId": "t-user"},
            {"action": "snapshot", "targetId": "t-user"},
            {"action": "click", "targetId": "t-user", "ref": "f0e0"},
        ],
    }
    code, output, _ = await _run_cli(fake, program, monkeypatch, capsys, tmp_path)
    assert code == 0
    click = output["results"][2]["result"]
    assert click["dialog"] == {"type": "confirm", "message": "Sure?"}
    assert click["release_skipped"] is True
    assert not any(
        m.get("method") == "Input.dispatchMouseEvent"
        and (m.get("params") or {}).get("type") == "mouseReleased"
        for m in fake.received
    )


@pytest.mark.asyncio
async def test_cli_token_file_broad_mode_warns_but_still_runs(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture, tmp_path
) -> None:
    """0600 is a custody convention: broader modes warn, not refuse.

    Refusing would not un-expose an already world-readable file; it
    would only deny service.  The warning is the signal to fix perms.
    """
    import os

    fake = _FakeCdp()
    port = _free_port()
    server = await websockets.serve(fake.handler, "127.0.0.1", port)
    monkeypatch.delenv("CBROWSER_AGENT_TOKEN", raising=False)
    token_file = tmp_path / "token.txt"
    token_file.write_text(TOKEN, encoding="utf-8")
    os.chmod(token_file, 0o644)
    try:
        monkeypatch.setattr(
            sys, "stdin", io.StringIO(json.dumps({"version": 1, "steps": [{"action": "targets"}]}))
        )
        code = await amain(
            [
                "--endpoint",
                f"ws://127.0.0.1:{port}/cdp",
                "--profile",
                "p1",
                "--runtime-instance",
                "i1",
                "--token-file",
                str(token_file),
                "--state-file",
                str(tmp_path / "state.json"),
            ]
        )
        captured = capsys.readouterr()
        assert code == 0
        assert "0600" in captured.err
        assert TOKEN not in captured.err
        os.chmod(token_file, 0o600)
        monkeypatch.setattr(
            sys, "stdin", io.StringIO(json.dumps({"version": 1, "steps": [{"action": "targets"}]}))
        )
        code = await amain(
            [
                "--endpoint",
                f"ws://127.0.0.1:{port}/cdp",
                "--profile",
                "p1",
                "--runtime-instance",
                "i1",
                "--token-file",
                str(token_file),
                "--state-file",
                str(tmp_path / "state.json"),
            ]
        )
        captured = capsys.readouterr()
        assert code == 0
        assert "0600" not in captured.err
    finally:
        server.close()
        await server.wait_closed()


def test_cli_help_smoke_and_entrypoint_declaration(tmp_path) -> None:
    """The installed entrypoint and --help must work (Skill points at them).

    Runs the module as the console script would (``python -m ...``) and
    checks the declared entrypoint in pyproject.toml matches the module.
    """
    import os
    import subprocess

    repo_root = Path(__file__).resolve().parents[2]
    env = dict(os.environ)
    env["PYTHONPATH"] = str(repo_root / "src" / "backend")
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "cbrowser.agent_executor.cli",
            "--help",
        ],
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
    )
    assert proc.returncode == 0
    for flag in ("--token-file", "--state-file", "--timeout", "--endpoint"):
        assert flag in proc.stdout
    pyproject = (repo_root / "pyproject.toml").read_text(encoding="utf-8")
    assert 'cbrowser-agent = "cbrowser.agent_executor.cli:main"' in pyproject
