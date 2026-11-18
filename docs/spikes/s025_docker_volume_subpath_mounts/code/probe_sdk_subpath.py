"""s025 experiment: verify docker-py serializes volume subpath mounts.

Captures the container config produced by
``containers.run(..., mounts=[Mount(..., subpath=...)])`` by replacing the
API client's create/start/inspect methods in-process. No daemon is
contacted; this validates client-side serialization only.
"""

from __future__ import annotations

import json
import sys

import docker
from docker.types import Mount


def main() -> int:
    print(f"docker-py version: {docker.__version__}")
    client = docker.DockerClient(base_url="tcp://127.0.0.1:23750", version="1.47")
    captured: dict = {}

    def fake_create(image, command=None, **kwargs):
        captured.update(kwargs)
        return {"Id": "ab" * 32, "Warnings": None}

    def fake_inspect(_cid, **_kw):
        return {
            "Id": "ab" * 32,
            "Name": "/probe",
            "Config": {"Image": "sha256:abc"},
            "State": {"Status": "running"},
            "HostConfig": {},
            "NetworkSettings": {"Networks": {}},
        }

    client.api.create_container = fake_create  # type: ignore[method-assign]
    client.api.start = lambda *_a, **_k: None  # type: ignore[method-assign]
    client.api.inspect_container = fake_inspect  # type: ignore[method-assign]

    mounts = [
        Mount(
            target="/data/profiles/p1/profile",
            source="cbrowser-data",
            type="volume",
            read_only=False,
            subpath="profiles/p1/profile",
        ),
        Mount(
            target="/fonts/windows/abc",
            source="cbrowser-fonts",
            type="volume",
            read_only=True,
            subpath="windows/abc",
        ),
        Mount(
            target="/run/cbrowser/runtime",
            source="cbrowser-runtime",
            type="volume",
            read_only=False,
            subpath="p1",
        ),
    ]
    client.containers.run(
        "sha256:abc", command=["true"], detach=True, mounts=mounts, name="probe"
    )
    host_config = captured["host_config"]
    got = host_config["Mounts"]
    print(json.dumps(got, indent=1))
    for m in got:
        assert m["Type"] == "volume", m
        assert m["VolumeOptions"]["Subpath"], m
    by_target = {m["Target"]: m for m in got}
    assert by_target["/fonts/windows/abc"]["ReadOnly"] is True
    assert by_target["/fonts/windows/abc"]["VolumeOptions"]["Subpath"] == "windows/abc"
    assert by_target["/data/profiles/p1/profile"]["Source"] == "cbrowser-data"
    assert by_target["/run/cbrowser/runtime"]["Source"] == "cbrowser-runtime"
    print("PASS: Mount(subpath=...) serializes to VolumeOptions.Subpath in create config")
    return 0


if __name__ == "__main__":
    sys.exit(main())
