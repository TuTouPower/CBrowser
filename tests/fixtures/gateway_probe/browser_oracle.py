"""Browser CDP oracle for navigating motion/audio page and checking state."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

MEDIA_PAGE_HTML = (
    Path(__file__).resolve().parents[1] / "stream_probe" / "media_page.html"
).read_text(encoding="utf-8")


def browser_eval(
    container: str,
    expression: str,
    target_id: str | None = None,
    html: str = MEDIA_PAGE_HTML,
) -> dict:
    """Executes expression in Browser container Chrome instance via CDP socket."""
    script = """import asyncio, json, urllib.parse, websockets

async def main():
    from cbrowser.runtime_agent.socket_root import container_agent_socket_path
    async with websockets.unix_connect(
        container_agent_socket_path(), "ws://localhost/cdp"
    ) as ws:
        counter = 0

        async def command(method, params=None, session=None):
            nonlocal counter
            counter += 1
            request = {"id": counter, "method": method, "params": params or {}}
            if session:
                request["sessionId"] = session
            await ws.send(json.dumps(request))
            while True:
                result = json.loads(await asyncio.wait_for(ws.recv(), 10))
                if result.get("id") == counter:
                    if "error" in result:
                        err = result["error"]
                        raise RuntimeError(f"Browser CDP request failed: {err}")
                    return result.get("result", {})

        target_id = parameters["target_id"]
        if target_id is None:
            pages = [
                target
                for target in (await command("Target.getTargets"))["targetInfos"]
                if target["type"] == "page"
            ]
            if len(pages) != 1:
                raise RuntimeError(f"Expected 1 page target, found {len(pages)}")
            target_id = pages[0]["targetId"]

        session = (
            await command(
                "Target.attachToTarget", {"targetId": target_id, "flatten": True}
            )
        )["sessionId"]

        if parameters["target_id"] is None:
            await command("Page.enable", session=session)
            await command("Runtime.enable", session=session)
            await command(
                "Page.navigate",
                {
                    "url": "data:text/html;charset=utf-8,"
                    + urllib.parse.quote(parameters["html"])
                },
                session,
            )
            for _ in range(100):
                value = await command(
                    "Runtime.evaluate",
                    {
                        "expression": '!!document.getElementById("probe_input")',
                        "returnByValue": True,
                    },
                    session,
                )
                if value.get("result", {}).get("value"):
                    break
                await asyncio.sleep(0.02)
            await command("Page.bringToFront", session=session)

        value = await command(
            "Runtime.evaluate",
            {
                "expression": parameters["expression"],
                "returnByValue": True,
                "awaitPromise": True,
                "userGesture": True,
            },
            session,
        )
        if "exceptionDetails" in value:
            err = value["exceptionDetails"]
            raise RuntimeError(f"Browser fixture expression failed: {err}")

        info = json.load(open("/run/cbrowser/runtime/runner_info.json"))
        pid = info["browser_pid"]
        start_ticks = open(f"/proc/{pid}/stat").read().rsplit(")", 1)[1].split()[19]
        print(
            json.dumps(
                {
                    "target_id": target_id,
                    "identity": {"pid": pid, "start_ticks": start_ticks},
                    "value": value.get("result", {}).get("value"),
                }
            )
        )

asyncio.run(main())
"""
    full_script = (
        "parameters = "
        + repr({"target_id": target_id, "expression": expression, "html": html})
        + "\n"
        + script
    )
    result = subprocess.run(
        ["docker", "exec", container, "python3", "-c", full_script],
        text=True,
        capture_output=True,
        timeout=25,
        check=False,
    )
    assert result.returncode == 0, f"browser_eval failed: {result.stderr}"
    return json.loads(result.stdout.strip().splitlines()[-1])
