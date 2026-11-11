"""Attach local gate ownership to SDK-created test infrastructure."""

from __future__ import annotations

import inspect
import os
from functools import wraps

import pytest


@pytest.fixture(scope="session", autouse=True)
def gate_docker_ownership():
    run_id = os.environ.get("CBROWSER_GATE_RUN_ID")
    from docker import APIClient

    originals = {}
    for name in ("create_container", "create_network"):
        original = getattr(APIClient, name)
        originals[name] = original

        def decorate(method):
            signature = inspect.signature(method)

            @wraps(method)
            def create(*args, **kwargs):
                bound = signature.bind(*args, **kwargs)
                if run_id:
                    bound.arguments["labels"] = {
                        **(bound.arguments.get("labels") or {}),
                        "com.cbrowser.gate-run": run_id,
                    }
                if "environment" in signature.parameters:
                    environment = bound.arguments.get("environment") or {}
                    if run_id:
                        if isinstance(environment, list):
                            environment = [
                                *environment,
                                f"CBROWSER_GATE_RUN_ID={run_id}",
                            ]
                        else:
                            environment = {
                                **environment,
                                "CBROWSER_GATE_RUN_ID": run_id,
                            }
                    bound.arguments["environment"] = environment
                    # APIClient.create_container injects config proxies after
                    # formatting environment; disable that explicit SDK option.
                    bound.arguments["use_config_proxy"] = False
                return method(*bound.args, **bound.kwargs)

            return create

        setattr(APIClient, name, decorate(original))
    try:
        yield
    finally:
        for name, original in originals.items():
            setattr(APIClient, name, original)
