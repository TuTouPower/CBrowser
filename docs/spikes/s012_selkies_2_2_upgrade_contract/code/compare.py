#!/usr/bin/env python3
"""Reproduce the s012 Selkies 2.1.0 vs 2.2.1 contract comparison.

Fetches the two official py3-none-any wheels from PyPI, verifies their
identities against the values recorded in report.md, and prints the
version-sensitive comparison used by the spike.  Run from any directory;
requires only the stdlib and network access to pypi.org / files.pythonhosted.org.
"""

from __future__ import annotations

import ast
import hashlib
import io
import json
import urllib.request
import zipfile

WHEELS = {
    "2.1.0": (
        "https://files.pythonhosted.org/packages/48/39/"
        "64b75999a7a45a1bf063cc31f2a3fda9da65dafb0fb7a6567ecde9674891/"
        "selkies-2.1.0-py3-none-any.whl",
        "8bde6207ca921cb2f38c3204fafe18d40b5578165894818ae1ca9e46fca7b966",
    ),
    "2.2.1": (
        "https://files.pythonhosted.org/packages/40/33/"
        "ece2923d078b414bed7c1e74e15ba83be34f77ecfc5092d58103bda3f210/"
        "selkies-2.2.1-py3-none-any.whl",
        "18503b5c1491a04194f0a45fa10c547ffe5b4a24f33496ce5d56e97370a6a3cd",
    ),
}

ABI_METHODS = {
    "prebind": ["self", "keysyms"],
    "text_room": ["self"],
    "_find_spare_keycodes": ["self"],
    "_layout_keycode": ["self", "keysym"],
}
ABI_ATTRS = [
    "_spare_keycodes", "_spare_set", "_text_codes",
    "_overlay", "_pressed_kc", "_settle_until",
]
# Static literals only.  "HELLO client ..." is a runtime-concatenated
# message (HELLO ${peer_type} ${json}); the adapter hooks it on the send
# side, so only the template and the identity fields are compared here.
PROTOCOL = ("HELLO ", "client_tab_id", "resume_key")


def fetch(url: str, expected: str) -> bytes:
    with urllib.request.urlopen(url, timeout=120) as resp:
        data = resp.read()
    assert hashlib.sha256(data).hexdigest() == expected, f"wheel hash mismatch {url}"
    return data


def abi_report(zf: zipfile.ZipFile) -> dict:
    tree = ast.parse(zf.read("selkies/input_handler.py").decode("utf-8"))
    cls = next(
        n for n in ast.walk(tree)
        if isinstance(n, ast.ClassDef) and n.name == "_XTestKeyboard"
    )
    methods = {}
    for name in ABI_METHODS:
        fn = next(
            (n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == name),
            None,
        )
        methods[name] = [a.arg for a in fn.args.args] if fn else None
    init = next(
        n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == "__init__"
    )
    assigned = set()
    for node in ast.walk(init):
        targets = (
            node.targets if isinstance(node, ast.Assign)
            else [node.target] if isinstance(node, ast.AnnAssign) else []
        )
        for t in targets:
            if (
                isinstance(t, ast.Attribute)
                and isinstance(t.value, ast.Name)
                and t.value.id == "self"
            ):
                assigned.add(t.attr)
    settle = any(
        isinstance(n, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "_BIND_SETTLE_S" for t in n.targets)
        for n in cls.body
    )
    return {
        "methods": methods,
        "settle": settle,
        "missing_attrs": [a for a in ABI_ATTRS if a not in assigned],
    }


def main() -> None:
    for version, (url, digest) in WHEELS.items():
        zf = zipfile.ZipFile(io.BytesIO(fetch(url, digest)))
        names = set(zf.namelist())
        py_modules = sorted(
            n for n in names
            if n.startswith("selkies/") and n.endswith(".py") and n.count("/") == 1
        )
        core = next(
            (n for n in names if n.endswith("selkies-core.js")), None
        )
        core_text = zf.read(core).decode("utf-8", "replace") if core else ""
        print(f"=== {version}")
        print("top-level py modules:", len(py_modules))
        print("abi:", json.dumps(abi_report(zf), sort_keys=True))
        print("protocol strings in core:", {p: p in core_text for p in PROTOCOL})
        requires = [
            line for line in zf.read(
                f"selkies-{version}.dist-info/METADATA"
            ).decode("utf-8", "replace").splitlines()
            if "pixelflux==" in line or "pcmflux==" in line
        ]
        print("native pins:", requires)


if __name__ == "__main__":
    main()
