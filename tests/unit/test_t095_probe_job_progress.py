"""t095: 进度=已处理数、受配额并发、统一状态管道与观测表职责。"""

from __future__ import annotations

import asyncio
import datetime
import time
from pathlib import Path

import pytest
import pytest_asyncio

from cbrowser.adapters.database.repository import ProfileRepository
from cbrowser.domain.egress_observation import EgressObservation
from cbrowser.services.profile_service import ProfileService


class _StubProbe:
    """可注入的成员探测桩：记录并发峰值，按配置成功/失败。"""

    def __init__(self, *, delay: float = 0.0, fail: bool = False) -> None:
        self.delay = delay
        self.fail = fail
        self.active = 0
        self.peak = 0

    async def __call__(self, job_id: str, proxy_id: str) -> tuple[str, str | None]:
        self.active += 1
        self.peak = max(self.peak, self.active)
        try:
            if self.delay:
                await asyncio.sleep(self.delay)
            return ("failed", "probe_unreachable") if self.fail else ("ok", None)
        finally:
            self.active -= 1


@pytest_asyncio.fixture
async def repo(db_context):
    return ProfileRepository(db_context[1])


def _service(
    repo: ProfileRepository,
    tmp_path: Path,
    *,
    concurrency: int | None = None,
    on_progress=None,
) -> ProfileService:
    service = ProfileService(
        repo,
        data_root=tmp_path / "data",
        probe_concurrency=concurrency,
    )
    if on_progress is not None:
        service.set_probe_job_progress(on_progress)
    return service


@pytest.mark.asyncio
async def test_all_failed_members_advance_progress_to_total(repo, tmp_path):
    """全部失败时进度从 0 推进到 N，不再长期停在 0/N（AC-001）。"""
    snapshots: list[tuple[int, int, int]] = []

    async def capture(job_id: str) -> None:
        job = await repo.get_probe_job(job_id)
        snapshots.append((job.processed, job.completed, job.failed))

    probe = _StubProbe(fail=True)
    service = _service(repo, tmp_path, on_progress=capture)
    service._probe_one_member = probe  # type: ignore[assignment]

    accepted = await service.request_probe_jobs([f"p{i}" for i in range(4)])
    await service.await_probe_jobs()

    job = await repo.get_probe_job(accepted.job_id)
    assert job.completed == 0 and job.failed == 4
    assert job.processed == 4
    assert snapshots[-1][0] == 4
    assert all(processed >= 1 for processed, _, _ in snapshots), snapshots
    assert all(failed >= completed for _, completed, failed in snapshots)


@pytest.mark.asyncio
async def test_progress_is_read_model_authority_without_observations(repo, tmp_path):
    """进度只取作业读模型；观测表无行也不影响进度（AC-004）。"""
    await repo.create_probe_job(job_id="j-no-obs", proxy_ids=["p1", "p2"])
    await repo.update_probe_job_member(
        job_id="j-no-obs", proxy_id="p1", state="ok", error_code=None,
        observation_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        completed=1, failed=0, done=False,
    )
    await repo.update_probe_job_member(
        job_id="j-no-obs", proxy_id="p2", state="failed", error_code="x",
        observation_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        completed=1, failed=1, done=True,
    )
    job = await repo.get_probe_job("j-no-obs")
    assert job.processed == 2
    assert job.completed == 1 and job.failed == 1
    assert await repo.get_egress_observations("p1") == []
    assert await repo.get_egress_observations("p2") == []


@pytest.mark.asyncio
async def test_observation_history_kept_with_ttl(repo, tmp_path):
    """观测表只存单次结果：多行历史保留、TTL 字段随行写入（AC-004）。"""
    created = await repo.create_proxy({
        "name": "obs-proxy",
        "scheme": "http",
        "host": "proxy.example",
        "port": 8080,
        "credential_revision": 1,
    })
    proxy_id = created.id
    now = datetime.datetime.now(datetime.timezone.utc)
    for i in range(3):
        await repo.record_egress_observation(
            proxy_id,
            EgressObservation(
                proxy_id=proxy_id,
                endpoint_fingerprint="fp",
                credential_revision=1,
                status="ok",
                observed_at=now + datetime.timedelta(seconds=i),
                expires_at=now + datetime.timedelta(seconds=i + 60),
            ),
        )
    history = await repo.get_egress_observations(proxy_id)
    assert len(history) == 3
    assert all(item.expires_at is not None for item in history)


@pytest.mark.asyncio
async def test_members_run_within_concurrency_and_faster_than_serial(repo, tmp_path):
    """受配额并发：峰值受限于上限，总耗时显著低于串行基线（AC-003）。"""
    delay = 0.06
    total = 9
    limit = 3
    probe = _StubProbe(delay=delay)
    service = _service(repo, tmp_path, concurrency=limit)
    service._probe_one_member = probe  # type: ignore[assignment]

    started = time.monotonic()
    accepted = await service.request_probe_jobs([f"p{i}" for i in range(total)])
    await service.await_probe_jobs()
    elapsed = time.monotonic() - started

    assert probe.peak <= limit, probe.peak
    assert probe.peak >= 2, probe.peak
    assert elapsed < delay * total * 0.6, elapsed
    job = await repo.get_probe_job(accepted.job_id)
    assert job.processed == total and job.state == "done"


@pytest.mark.asyncio
async def test_members_queue_when_over_concurrency_limit(repo, tmp_path):
    """超配额成员排队而非丢弃：上限内峰值受限且全部收敛（AC-003）。"""
    probe = _StubProbe(delay=0.01)
    service = _service(repo, tmp_path, concurrency=2)
    service._probe_one_member = probe  # type: ignore[assignment]

    accepted = await service.request_probe_jobs([f"p{i}" for i in range(6)])
    await service.await_probe_jobs()

    assert probe.peak <= 2
    job = await repo.get_probe_job(accepted.job_id)
    assert job.processed == 6 and job.failed == 0 and job.state == "done"


@pytest.mark.asyncio
async def test_parallel_jobs_keep_member_results_isolated(repo, tmp_path):
    """多作业并发时成员结果不串线；替代 t094「驱动串行」的旧断言（AC-003）。"""

    async def probe(job_id: str, proxy_id: str) -> tuple[str, str | None]:
        await asyncio.sleep(0.01)
        return ("ok", None) if proxy_id.startswith("a") else ("failed", "wrong")

    service = _service(repo, tmp_path, concurrency=4)
    service._probe_one_member = probe  # type: ignore[assignment]
    a = await service.request_probe_jobs(["a1", "a2"])
    b = await service.request_probe_jobs(["b1", "b2"])
    await service.await_probe_jobs()

    ja = await repo.get_probe_job(a.job_id)
    jb = await repo.get_probe_job(b.job_id)
    assert all(m.state == "ok" for m in ja.members)
    assert all(m.state == "failed" for m in jb.members)
    assert ja.processed == 2 and jb.processed == 2


@pytest.mark.asyncio
async def test_slow_member_does_not_block_other_members(repo, tmp_path):
    """单成员超时彼此独立：慢成员不阻塞其他成员完成（AC-003）。"""

    async def probe(job_id: str, proxy_id: str) -> tuple[str, str | None]:
        if proxy_id == "slow":
            await asyncio.sleep(0.3)
            return "failed", "timeout"
        await asyncio.sleep(0.01)
        return "ok", None

    service = _service(repo, tmp_path, concurrency=4)
    service._probe_one_member = probe  # type: ignore[assignment]
    accepted = await service.request_probe_jobs(["slow", "fast1", "fast2", "fast3"])
    await service.await_probe_jobs()

    job = await repo.get_probe_job(accepted.job_id)
    states = {m.proxy_id: m.state for m in job.members}
    assert states["slow"] == "failed"
    assert states["fast1"] == states["fast2"] == states["fast3"] == "ok"
    assert job.processed == 4
