#!/usr/bin/env python3
"""Probe 5: Verify recreating an edge container with different port bindings
using the Docker SDK as Supervisor would do.
"""

import docker
import json
import os

def main():
    client = docker.from_env()
    container_name = "s017-probe-recreate"

    # Clean up previous
    try:
        c = client.containers.get(container_name)
        c.remove(force=True)
    except docker.errors.NotFound:
        pass

    print("[1] Creating initial container bound to 127.0.0.1:54326...")
    c1 = client.containers.run(
        "python:3.12-alpine",
        command=["python3", "-m", "http.server", "8080"],
        name=container_name,
        detach=True,
        ports={"8080/tcp": ("127.0.0.1", 54326)},
        labels={"com.cbrowser.role": "edge-proxy", "com.cbrowser.managed-by": "supervisor"}
    )

    inspect1 = client.api.inspect_container(c1.id)
    bindings1 = inspect1["HostConfig"]["PortBindings"]
    print("Initial PortBindings:", bindings1)

    print("[2] Supervisor-style recreate: Recreating container bound to 0.0.0.0:54326...")
    # Extract config to preserve mounts, networks, env, image
    image = inspect1["Config"]["Image"]
    cmd = inspect1["Config"]["Cmd"]
    labels = inspect1["Config"]["Labels"]

    # Stop & remove old
    c1.remove(force=True)

    # Recreate with new binding
    c2 = client.containers.run(
        image,
        command=cmd,
        name=container_name,
        detach=True,
        ports={"8080/tcp": ("0.0.0.0", 54326)},
        labels=labels
    )
    inspect2 = client.api.inspect_container(c2.id)
    bindings2 = inspect2["HostConfig"]["PortBindings"]
    print("Recreated PortBindings:", bindings2)

    success = (bindings1.get("8080/tcp")[0]["HostIp"] == "127.0.0.1" and
               bindings2.get("8080/tcp")[0]["HostIp"] == "0.0.0.0")
    print("Recreate test success:", success)

    c2.remove(force=True)

    result = {
        "initial_binding": bindings1,
        "recreated_binding": bindings2,
        "success": success
    }
    out_path = os.environ.get("PROBE_OUTPUT", "/probe/result_edge_rebuild.json")
    try:
        with open(out_path, "w") as f:
            json.dump(result, f, indent=2)
        print("Saved to", out_path)
    except Exception as e:
        print("Failed to save:", e)

if __name__ == "__main__":
    main()
