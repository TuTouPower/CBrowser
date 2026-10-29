"""Hold an isolated X11 clipboard sentinel while native IME commits are tested."""

import json
import secrets
import sys

from selkies.input_handler import _X11ClipboardMonitor

clipboard = _X11ClipboardMonitor()
sentinel = secrets.token_hex(24)
try:
    assert clipboard.offer([("text/plain", sentinel)])
    print("CBR_CLIP_READY", flush=True)
    for command in sys.stdin:
        if command.strip() == "verify":
            value, mime = clipboard.read(False)
            print(
                "CBR_CLIP_RESULT:"
                + json.dumps({"unchanged": value == sentinel and mime == "text/plain"}),
                flush=True,
            )
        elif command.strip() == "close":
            break
finally:
    clipboard.close()
