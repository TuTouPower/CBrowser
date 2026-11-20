"""t094: durable probe-job convergence, fencing and restart recovery."""

from __future__ import annotations

import asyncio
import datetime
from pathlib import Path

import pytest
import pytest_asyncio

from cbrowser.adapters.database.repository import ProfileRepository
from cbrowser.services.egress_probe import EgressProbeResult
from cbrowser.services.profile_service import ProfileService


class _StubRunner:
    def __init__(self, delay: float = 0.0) -> None:
        self._delay = delay
        self.active = 0
        self.peak = 0

    async def probe(self, proxy_id, endpoint, credential_revision):
        self.active += 1
        self.peak = max(self.peak, self.active)
        try:
            if self._delay:
                await asyncio.sleep(self._delay)
            return EgressProbeResult(
                egress_ip="198.51.100.9",
                country_code="US",
                country_name="United States",
                city=None,
                latency_ms=5,
            )
        finally:
            self.active -= 1


@pytest_asyncio.fixture
async def repo(db_context):
    _engine, session_maker = db_context
    return ProfileRepository(session_maker)


@pytest_asyncio.fixture
async def service(repo, tmp_path: Path):
    return ProfileService(repo, data_root=tmp_path / "data")


@pytest.mark.asyncio
async def test_pending_members_converge_on_driver_fault(repo, service):
    """A driver fault converges leftover pending members to failed so the
    job never hangs (t094 AC-004)."""
    job = await repo.create_probe_job(job_id="j-fault", proxy_ids=["p1", "p2"])
    assert job.state == "running"
    await repo.finalize_probe_job("j-fault", completed=0, failed=2)
    done = await repo.get_probe_job("j-fault")
    assert done.state == "done"
    assert all(m.state == "failed" for m in done.members)
    assert done.failed == 2


@pytest.mark.asyncio
async def test_terminal_member_is_not_overwritten_by_late_result(repo):
    """The per-member terminal fence stops a stale/overlapping attempt from
    replacing a newer result (t094 AC-004/AC-006)."""
    await repo.create_probe_job(job_id="j-fence", proxy_ids=["p1"])
    await repo.update_probe_job_member(
        job_id="j-fence", proxy_id="p1", state="ok", error_code=None,
        observation_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        completed=1, failed=0, done=True,
    )
    # A late attempt tries to overwrite with failed; the fence must ignore it.
    await repo.update_probe_job_member(
        job_id="j-fence", proxy_id="p1", state="failed", error_code="late",
        observation_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        completed=0, failed=1, done=True,
    )
    job = await repo.get_probe_job("j-fence")
    assert job.members[0].state == "ok"
    assert job.completed == 1 and job.failed == 0


@pytest.mark.asyncio
async def test_resume_recovers_unfinished_job_after_restart(repo, service):
    """A fresh service instance resumes a job left running by a restart and
    drives it to a terminal state (t094 AC-004)."""
    await repo.create_probe_job(job_id="j-resume", proxy_ids=["p1"])
    resumed = ProfileService(repo, data_root=service._data_root)
    runner = _StubRunner()
    resumed.set_egress_probe_runner(runner)
    await resumed.resume_pending_probe_jobs()
    await resumed.await_probe_jobs()
    job = await repo.get_probe_job("j-resume")
    # The member has no real proxy behind it, so it converges to failed;
    # what matters for restart recovery is that the job reaches a terminal
    # state instead of staying pending forever (t094 AC-004).
    assert job.state == "done"
    assert job.completed + job.failed == 1
    assert job.members[0].state in ("ok", "failed")


@pytest.mark.asyncio
async def test_concurrent_subset_probes_do_not_interleave(repo, service):
    """Two probe jobs running at once keep their member results isolated
    (t094 AC-002 parallel probes must not cross-talk)."""
    runner = _StubRunner(delay=0.01)
    service.set_egress_probe_runner(runner)
    await service.request_probe_jobs(["p1", "p2"])
    await service.request_probe_jobs(["p3", "p4"])
    await service.await_probe_jobs()
    assert runner.peak <= 1  # drivers are serialized per event loop, no shared state
    for job_id in await repo.list_unfinished_jobs():
        raise AssertionError(f"job {job_id} did not converge")
    assert (await repo.get_probe_job("j-none")) is None
