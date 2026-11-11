"""t052: repository-level egress observation currency (test f005).

The TTL-expiry rule was only tested at the pure-function layer
(``observation_is_current``); the wiring in
``ProfileRepository._current_observation`` — stale ok rows are hidden,
pending/failed rows are still surfaced — had no repository-level test.
This file also pins the list path: ``list_proxies`` must fetch the
current observation for every proxy in one batched query (code f005),
not one SELECT per row.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy import event

from cbrowser.adapters.database.models import ProxyEgressObservationModel
from cbrowser.adapters.database.repository import ProfileRepository
from cbrowser.domain.egress_observation import (
    OBSERVATION_TTL_SECONDS,
    EgressObservation,
)
from cbrowser.domain.proxy_endpoint import ProxyEndpoint

NOW = datetime.now(timezone.utc)


def _endpoint(host="proxy.example.com", port=8080):
    return ProxyEndpoint(scheme="http", host=host, port=port, username="user")


@pytest_asyncio.fixture
async def repo(db_context):
    _engine, session_maker = db_context
    return ProfileRepository(session_maker)


async def _make_proxy(repo, name, host="proxy.example.com", port=8080):
    return await repo.create_proxy(
        {
            "name": name,
            "scheme": "http",
            "host": host,
            "port": port,
            "username": "user",
            "password": "s3cret-pw",
        }
    )


def _observation(proxy, *, status="ok", observed_at=None, expires_at=None,
                 country_code="JP", egress_ip="203.0.113.7"):
    return EgressObservation(
        proxy_id=proxy.id,
        endpoint_fingerprint=_endpoint(
            proxy.host, proxy.port
        ).fingerprint,
        credential_revision=proxy.credential_revision,
        status=status,
        egress_ip=egress_ip,
        country_code=country_code,
        observed_at=observed_at if observed_at is not None else NOW,
        expires_at=expires_at,
    )


@pytest.mark.asyncio
async def test_expired_ok_observation_is_hidden_by_get_proxy(repo):
    """AC-007 (test f005): an ok row past its TTL must not surface —
    ``get_proxy`` reports unknown with no country, as if unobserved."""
    proxy = await _make_proxy(repo, "px-expired")
    expired = _observation(
        proxy,
        observed_at=NOW - timedelta(seconds=OBSERVATION_TTL_SECONDS + 3600),
        expires_at=NOW - timedelta(seconds=3600),
    )
    await repo.record_egress_observation(proxy.id, expired)

    got = await repo.get_proxy(proxy.id)
    assert got is not None
    assert got.observation_status == "unknown"
    assert got.country_code is None
    assert got.egress_ip is None


@pytest.mark.asyncio
async def test_pending_row_after_expired_ok_is_still_surfaced(repo):
    """A newer pending row is not hidden by the stale-ok rule: the UI
    must show 'detecting' while a re-probe is in flight (AC-006)."""
    proxy = await _make_proxy(repo, "px-reprobe")
    await repo.record_egress_observation(
        proxy.id,
        _observation(
            proxy,
            observed_at=NOW - timedelta(seconds=OBSERVATION_TTL_SECONDS + 3600),
            expires_at=NOW - timedelta(seconds=3600),
        ),
    )
    await repo.record_egress_observation(
        proxy.id,
        _observation(
            proxy,
            status="pending",
            observed_at=NOW,
            expires_at=None,
            country_code=None,
            egress_ip=None,
        ),
    )

    got = await repo.get_proxy(proxy.id)
    assert got is not None
    assert got.observation_status == "pending"
    assert got.country_code is None


@pytest.mark.asyncio
async def test_failed_row_is_surfaced_not_hidden(repo):
    proxy = await _make_proxy(repo, "px-failed")
    await repo.record_egress_observation(
        proxy.id,
        _observation(
            proxy,
            status="failed",
            observed_at=NOW,
            expires_at=None,
            country_code=None,
            egress_ip=None,
        ),
    )

    got = await repo.get_proxy(proxy.id)
    assert got is not None
    assert got.observation_status == "failed"
    assert got.country_code is None


@pytest.mark.asyncio
async def test_list_proxies_batches_observation_lookup(repo, db_context):
    """code f005 (red before the batch fix): listing N proxies must
    issue exactly one SELECT against proxy_egress_observations, not
    one per proxy row."""
    engine, _maker = db_context
    proxies = [
        await _make_proxy(repo, f"px-{i}", host=f"proxy{i}.example.com")
        for i in range(3)
    ]
    for i, proxy in enumerate(proxies):
        await repo.record_egress_observation(
            proxy.id,
            _observation(
                proxy,
                observed_at=NOW,
                expires_at=NOW + timedelta(seconds=OBSERVATION_TTL_SECONDS),
                country_code=["JP", "US", "DE"][i],
                egress_ip=f"203.0.113.{i + 1}",
            ),
        )

    statements: list[str] = []

    def _count(conn, cursor, statement, parameters, context, executemany):
        if "proxy_egress_observations" in statement:
            statements.append(statement)

    event.listen(engine.sync_engine, "before_cursor_execute", _count)
    try:
        listed = await repo.list_proxies()
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", _count)

    by_id = {p.id: p for p in listed}
    assert {by_id[p.id].country_code for p in proxies} == {"JP", "US", "DE"}
    assert all(by_id[p.id].observation_status == "ok" for p in proxies)
    selects = [s for s in statements if s.lstrip().upper().startswith("SELECT")]
    assert len(selects) == 1, selects


@pytest.mark.asyncio
async def test_list_proxies_fetches_only_latest_observation_row_per_proxy(
    repo, db_context
):
    """code f007 (red before the bounded-query fix): with several
    history rows per proxy, ``list_proxies`` must still return each
    proxy's latest row only, issue exactly one observation SELECT, and
    materialise exactly one observation row per proxy — not the whole
    history.  The old implementation returned the right values but
    fetched every history row and discarded all but the latest."""
    engine, _maker = db_context
    proxies = [
        await _make_proxy(repo, f"px-hist-{i}", host=f"proxy{i}.example.com")
        for i in range(3)
    ]
    for i, proxy in enumerate(proxies):
        # Old ok row, then a newer ok row, then a newest pending row.
        await repo.record_egress_observation(
            proxy.id,
            _observation(
                proxy,
                observed_at=NOW - timedelta(seconds=7200),
                expires_at=NOW + timedelta(seconds=OBSERVATION_TTL_SECONDS),
                country_code=["JP", "US", "DE"][i],
                egress_ip=f"203.0.113.{i + 1}",
            ),
        )
        await repo.record_egress_observation(
            proxy.id,
            _observation(
                proxy,
                observed_at=NOW - timedelta(seconds=3600),
                expires_at=NOW + timedelta(seconds=OBSERVATION_TTL_SECONDS),
                country_code=["FR", "GB", "NL"][i],
                egress_ip=f"198.51.100.{i + 1}",
            ),
        )
        await repo.record_egress_observation(
            proxy.id,
            _observation(
                proxy,
                status="pending",
                observed_at=NOW,
                expires_at=None,
                country_code=None,
                egress_ip=None,
            ),
        )

    statements: list[str] = []
    loaded_rows: list[object] = []

    def _count(conn, cursor, statement, parameters, context, executemany):
        if "proxy_egress_observations" in statement:
            statements.append(statement)

    def _on_load(target, context):
        loaded_rows.append(target)

    event.listen(engine.sync_engine, "before_cursor_execute", _count)
    event.listen(ProxyEgressObservationModel, "load", _on_load)
    try:
        listed = await repo.list_proxies()
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", _count)
        event.remove(ProxyEgressObservationModel, "load", _on_load)

    # Latest row per proxy wins: the newest pending row, not either ok row.
    by_id = {p.id: p for p in listed}
    assert len(listed) == 3
    for proxy in proxies:
        assert by_id[proxy.id].observation_status == "pending"
        assert by_id[proxy.id].country_code is None
        assert by_id[proxy.id].egress_ip is None
    selects = [s for s in statements if s.lstrip().upper().startswith("SELECT")]
    assert len(selects) == 1, selects
    # Bounded fetch: one materialised observation row per proxy, not
    # the 9 history rows.
    assert len(loaded_rows) == 3, len(loaded_rows)
