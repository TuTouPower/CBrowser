"""Host CLI for the t030 agent executor: ``cbrowser-agent``.

Reads a JSON action program from stdin, runs it in one session over the
existing cbat_ authenticated automation tunnel, and prints a machine-
readable JSON result to stdout.  Steps, errors and cleanup are stable
and distinguishable; the CLI never sends Browser.close, never closes a
context, and never closes a page it cannot prove this session created.

Token input is ``--token-file`` (0600) or ``CBROWSER_AGENT_TOKEN``; there
is deliberately no ``--token`` flag (it would leak into process listings).
0600 is a caller-custody convention: a broader mode draws a stderr
warning, not a refusal (refusing would not un-expose the file).
The token is never written to stdout, stderr or logs; step results are
caller-owned data and are passed through (see the executor spec).

One invocation is one process, but one agent session spans many
invocations: snapshot refs and page ownership persist in a state file
(``--state-file``, default under ~/.cache) keyed by profile +
runtime-instance, so an agent can snapshot in one call and act on a ref
in the next.  Live validation still rejects every stale ref.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

from .session import ExecutorSession, SessionError
from .state import (
    bound_state,
    decode_ledger,
    decode_snapshots,
    default_state_path,
    load_state,
    save_state,
)
from .transport import CdpError, CdpTimeoutError, TunnelRejectedError

PROGRAM_VERSION = 1


def _redact(text: str, token: str) -> str:
    if token:
        return text.replace(token, "[redacted-token]")
    return text


def _step_error_code(exc: Exception) -> str:
    if isinstance(exc, SessionError):
        return exc.error_code
    if isinstance(exc, TunnelRejectedError):
        return "tunnel_rejected"
    if isinstance(exc, CdpTimeoutError):
        return "step_timeout"
    if isinstance(exc, CdpError):
        return "cdp_error"
    if isinstance(exc, asyncio.TimeoutError):
        return "step_timeout"
    return "internal_error"


def _req_str(step: dict, field: str, *, allow_empty: bool = False) -> str:
    """Required program string field; missing/wrong type is the caller's
    error (invalid_program), never an internal error."""
    value = step.get(field)
    if not isinstance(value, str) or (not allow_empty and not value):
        raise SessionError(
            "invalid_program", f"step needs a string {field!r}"
        )
    return value


def _req_int(step: dict, field: str, default: int | None = None) -> int:
    value = step.get(field, default)
    if isinstance(value, bool) or not isinstance(value, int):
        raise SessionError(
            "invalid_program", f"step needs an integer {field!r}"
        )
    return value


async def _run_step(session: ExecutorSession, step: dict) -> dict:
    action = step.get("action")
    if action == "targets":
        return {"targets": await session.list_targets()}
    if action == "new_page":
        return await session.new_page(step.get("url"))
    if action == "adopt":
        return await session.adopt(_req_str(step, "targetId"))
    if action == "snapshot":
        return await session.snapshot(_req_str(step, "targetId"))
    if action == "click":
        return await session.click(
            _req_str(step, "targetId"), _req_str(step, "ref")
        )
    if action == "input":
        return await session.input_text(
            _req_str(step, "targetId"),
            _req_str(step, "ref"),
            _req_str(step, "text", allow_empty=True),
        )
    if action == "navigate":
        return await session.navigate(
            _req_str(step, "targetId"), _req_str(step, "url")
        )
    if action == "wait_for":
        return await session.wait_for(
            _req_str(step, "targetId"),
            _req_str(step, "expression"),
            _req_int(step, "timeoutMs", 10000),
        )
    if action == "extract":
        return await session.extract(
            _req_str(step, "targetId"), _req_str(step, "expression")
        )
    if action == "dialog_answer":
        answer = step.get("answer")
        if answer is not None and not isinstance(answer, str):
            raise SessionError("invalid_program", "answer must be a string")
        prompt_text = step.get("promptText")
        if prompt_text is not None and not isinstance(prompt_text, str):
            raise SessionError(
                "invalid_program", "promptText must be a string"
            )
        return await session.dialog_answer(
            _req_str(step, "targetId"),
            answer,
            prompt_text,
        )
    if action == "dialog_wait":
        return await session.dialog_wait(
            _req_str(step, "targetId"), _req_int(step, "timeoutMs", 10000)
        )
    if action == "set_input_files":
        files = step.get("files")
        if not isinstance(files, list) or not files:
            raise SessionError("invalid_program", "set_input_files needs files")
        return await session.set_input_files(
            _req_str(step, "targetId"),
            _req_str(step, "ref"),
            [str(f) for f in files],
        )
    if action == "permission":
        return await session.permission(
            _req_str(step, "targetId"), _req_str(step, "kind")
        )
    if action == "wait_for_target_count":
        return await session.wait_for_target_count(
            _req_int(step, "count"), _req_int(step, "timeoutMs", 10000)
        )
    if action == "cleanup":
        return await session.cleanup()
    raise SessionError("invalid_program", f"unknown action: {action!r}")


async def run_program(
    session: ExecutorSession,
    program: dict,
    program_timeout: float,
    token: str,
) -> tuple[dict, int]:
    """Run all steps. Returns (output, exit).

    Cleanup semantics: on failure or cancel, cleanup runs immediately
    (fail-safe: agent pages do not linger after a broken run).  On
    success there is no implicit cleanup -- the session persists in the
    state file and the agent's pages stay alive for later invocations;
    closing them is the explicit ``cleanup`` step's job.  An earlier
    version cleaned up on every exit, which made multi-invocation agent
    work impossible (a page created in one call was gone by the next).
    """
    steps = program.get("steps")
    if not isinstance(steps, list):
        raise SessionError("invalid_program", "program.steps must be a list")
    results: list[dict] = []
    error: dict | None = None

    async def _steps() -> None:
        for index, step in enumerate(steps):
            if not isinstance(step, dict):
                raise SessionError(
                    "invalid_program", f"step {index} is not an object"
                )
            try:
                result = await _run_step(session, step)
            except Exception as exc:  # noqa: BLE001 - per-step error taxonomy
                nonlocal_error = {
                    "code": _step_error_code(exc),
                    "message": _redact(str(exc), token),
                    "step": index,
                    "action": step.get("action"),
                }
                results.append({"action": step.get("action"), "error": nonlocal_error})
                raise _StepFailed(nonlocal_error) from None
            results.append({"action": step.get("action"), "result": result})

    try:
        await asyncio.wait_for(_steps(), timeout=program_timeout)
    except _StepFailed as failed:
        error = failed.error
    except asyncio.TimeoutError:
        error = {
            "code": "step_timeout",
            "message": f"program exceeded {program_timeout}s",
            "step": len(results),
        }
    except asyncio.CancelledError:
        error = {"code": "cancelled", "message": "program cancelled"}
    except SessionError as exc:
        error = {"code": exc.error_code, "message": _redact(str(exc), token)}

    cleanup_result: dict = {}
    if error is not None:
        try:
            cleanup_result = await session.cleanup()
        except Exception as exc:  # noqa: BLE001 - cleanup failure is reported
            cleanup_result = {
                "error": {
                    "code": _step_error_code(exc),
                    "message": _redact(str(exc), token),
                }
            }
    await session.close()

    output: dict[str, Any] = {
        "ok": error is None,
        "results": results,
        "cleanup": cleanup_result,
    }
    if error is not None:
        output["error"] = error
    return output, 0 if error is None else 1


class _StepFailed(Exception):
    def __init__(self, error: dict) -> None:
        super().__init__(error["code"])
        self.error = error


def load_token(args: argparse.Namespace) -> str:
    if args.token_file:
        # The token file is the caller's custody: 0600 is the documented
        # convention.  Refusing to run on a broader mode would not
        # un-expose an already world-readable file, it would only deny
        # service -- so warn loudly and continue, and let the caller fix
        # the file's permissions.
        import stat

        mode = stat.S_IMODE(Path(args.token_file).stat().st_mode)
        if mode != 0o600:
            print(
                "cbrowser-agent: warning: token file "
                f"{args.token_file} has mode {mode:03o}, expected 0600",
                file=sys.stderr,
            )
        return Path(args.token_file).read_text(encoding="utf-8").strip()
    token = os.environ.get("CBROWSER_AGENT_TOKEN", "").strip()
    if not token:
        raise SystemExit(
            "cbrowser-agent: no token: pass --token-file or set "
            "CBROWSER_AGENT_TOKEN"
        )
    return token


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="CBrowser agent executor: run a JSON action program "
        "over the authenticated automation tunnel."
    )
    parser.add_argument("--endpoint", required=True, help="Automation WS URL")
    parser.add_argument("--profile", required=True, help="Profile id")
    parser.add_argument(
        "--runtime-instance", required=True, help="Runtime instance id"
    )
    parser.add_argument("--token-file", help="File holding the cbat_ token")
    parser.add_argument(
        "--state-file",
        help="Session state file (refs + page ledger). Defaults to "
        "~/.cache/cbrowser/agent-executor/<profile>_<runtime>.json",
    )
    parser.add_argument(
        "--timeout", type=float, default=120.0, help="Program timeout seconds"
    )
    parser.add_argument(
        "--step-timeout", type=float, default=30.0, help="Per-step timeout seconds"
    )
    return parser


async def amain(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    token = load_token(args)
    raw = sys.stdin.read()
    try:
        program = json.loads(raw)
    except ValueError:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": {"code": "invalid_program", "message": "stdin is not JSON"},
                    "results": [],
                    "cleanup": {},
                }
            )
        )
        return 2
    if not isinstance(program, dict) or program.get("version") != PROGRAM_VERSION:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": {
                        "code": "invalid_program",
                        "message": f"program.version must be {PROGRAM_VERSION}",
                    },
                    "results": [],
                    "cleanup": {},
                }
            )
        )
        return 2
    state_path = (
        Path(args.state_file)
        if args.state_file
        else default_state_path(args.profile, args.runtime_instance)
    )
    state = load_state(state_path)
    # Only trust state written for this exact (profile, runtime):
    # a state file copied or re-pointed across runtimes is discarded,
    # never overlaid, so its refs and cleanable grants cannot leak in.
    snapshots_raw, ledger_raw = bound_state(
        state,
        profile_id=args.profile,
        runtime_instance_id=args.runtime_instance,
    )
    session = ExecutorSession(
        endpoint=args.endpoint,
        token=token,
        profile_id=args.profile,
        runtime_instance_id=args.runtime_instance,
        step_timeout=args.step_timeout,
        initial_snapshots=decode_snapshots(snapshots_raw),
        initial_ledger=decode_ledger(ledger_raw),
    )
    try:
        await session.start()
    except SessionError as exc:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": {
                        "code": exc.error_code,
                        "message": _redact(str(exc), token),
                    },
                    "results": [],
                    "cleanup": {},
                }
            )
        )
        await session.close()
        return 1
    output, code = await run_program(session, program, args.timeout, token)
    try:
        snapshots, ledger = session.export_state()
        save_state(
            state_path,
            snapshots,
            ledger,
            profile_id=args.profile,
            runtime_instance_id=args.runtime_instance,
        )
    except Exception as exc:  # noqa: BLE001 - state loss warns, never fails the run
        print(f"cbrowser-agent: warning: cannot save state: {exc}", file=sys.stderr)
    print(json.dumps(output))
    return code


def main(argv: list[str] | None = None) -> int:
    try:
        return asyncio.run(amain(argv))
    except KeyboardInterrupt:
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
