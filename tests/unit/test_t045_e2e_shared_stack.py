from __future__ import annotations

import asyncio
import importlib.util
from pathlib import Path
from typing import Any

import pytest

_MODULE_PATH = (
    Path(__file__).resolve().parents[1] / 'e2e' / 'test_frontend_session_e2e.py'
)


class _FakeHarness:
    def __init__(self) -> None:
        self.start_count = 0
        self.cleanup_count = 0

    async def start(self) -> None:
        self.start_count += 1

    async def cleanup(self) -> None:
        self.cleanup_count += 1


def _load_session_module() -> Any:
    spec = importlib.util.spec_from_file_location(
        'test_frontend_session_e2e_shared_stack', _MODULE_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope='module')
def session_module() -> Any:
    return _load_session_module()


def _stack_class(session_module: Any) -> Any:
    stack_cls = getattr(session_module, 'SharedContainerStack', None)
    assert stack_cls is not None, 'SharedContainerStack 未定义于 session E2E 模块'
    return stack_cls


def test_shared_stack_starts_and_cleans_up_once(session_module: Any) -> None:
    stack_cls = _stack_class(session_module)
    fake = _FakeHarness()
    stack = stack_cls(fake)

    async def scenario() -> None:
        for _ in range(3):
            await stack.start()
        for _ in range(3):
            await stack.cleanup()

    asyncio.run(scenario())

    assert fake.start_count == 1
    assert fake.cleanup_count == 1


def test_reset_profile_state_removes_only_target_profile(
    session_module: Any,
) -> None:
    stack_cls = _stack_class(session_module)
    profiles = {'case_a': 'p-a', 'case_b': 'p-b', 'case_c': 'p-c'}
    stopped: list[str] = []
    deleted: list[str] = []

    async def stop_profile(profile_id: str) -> None:
        stopped.append(profile_id)

    async def delete_profile(profile_id: str) -> None:
        deleted.append(profile_id)

    stack = stack_cls(
        _FakeHarness(),
        profiles=profiles,
        stop_profile=stop_profile,
        delete_profile=delete_profile,
    )

    async def scenario() -> str | None:
        return await stack.reset_profile_state('case_b')

    assert asyncio.run(scenario()) == 'p-b'
    assert stopped == ['p-b']
    assert deleted == ['p-b']
    assert profiles == {'case_a': 'p-a', 'case_c': 'p-c'}

    async def rerun() -> str | None:
        return await stack.reset_profile_state('case_b')

    assert asyncio.run(rerun()) is None
    assert stopped == ['p-b']
    assert deleted == ['p-b']
