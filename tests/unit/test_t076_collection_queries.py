"""t076: collection queries, batched proxy references, runtime summary.

AC-001 collection pages (search/sort/pagination/total, bounded page size);
AC-004 union reference semantics (current/bound/both, dedupe, release);
AC-005 list_proxies SELECT count must not grow with P x R;
AC-006 bounded name candidates find the last item;
AC-007 0/1/100/1000 scale matrix reads without truncation.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy import event, select

from cbrowser.adapters.database.models import (
    ProfileConfigVersionModel,
    ProfileModel,
    ProfileRuntimeModel,
    ProxyEgressObservationModel,
    ProxyModel,
)
from cbrowser.adapters.database.repository import ProfileRepository
from cbrowser.domain.egress_observation import (
    OBSERVATION_TTL_SECONDS,
    EgressObservation,
)
from cbrowser.domain.models import ProfileConfig
from cbrowser.domain.proxy_endpoint import ProxyEndpoint

NOW = datetime.now(timezone.utc)


@pytest_asyncio.fixture
async def repo(db_context):
    _engine, session_maker = db_context
    return ProfileRepository(session_maker)


async def _make_proxy(repo, name, host="proxy.example.com"):
    return await repo.create_proxy(
        {
            "name": name,
            "scheme": "http",
            "host": host,
            "port": 8080,
            "username": "user",
            "password": "s3cret-pw",
        }
    )


async def _make_profile(repo, name, proxy_id=None):
    return await repo.create_profile(
        ProfileConfig(name=name, proxy_id=proxy_id)
    )


def _count_selects(engine):
    statements: list[str] = []

    def _listener(conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip().upper().startswith("SELECT"):
            statements.append(statement)

    event.listen(engine.sync_engine, "before_cursor_execute", _listener)
    return statements, _listener


@pytest.mark.asyncio
async def test_list_proxies_select_count_bounded_by_scale(repo, db_context):
    """AC-005: list_proxies SELECTs must stay bounded as P and R grow.

    Old shape was 2 + P x (2 + R) SELECTs (p121). The batched shape is
    a constant number of SELECTs (proxies + observations + reference
    map) independent of proxy and binding counts.
    """
    engine, _maker = db_context
    proxies = [
        await _make_proxy(repo, f"px-{i:03d}", host=f"proxy{i}.example.com")
        for i in range(20)
    ]
    profiles = [
        await _make_profile(repo, f"prof-{i:03d}", proxy_id=proxies[i % 20].id)
        for i in range(10)
    ]
    for p in profiles:
        await repo.bind_runtime_instance(p.id, f"inst-{p.id}", config_version=1)

    statements, listener = _count_selects(engine)
    try:
        listed = await repo.list_proxies()
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", listener)
    assert len(listed) == 20
    small = len(statements)

    # Grow to 100 proxies / 10 bindings: SELECT count must not grow.
    more = [
        await _make_proxy(repo, f"px-big-{i:03d}", host=f"big{i}.example.com")
        for i in range(80)
    ]
    assert len(more) == 80
    statements2, listener2 = _count_selects(engine)
    try:
        listed2 = await repo.list_proxies()
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", listener2)
    assert len(listed2) == 100
    assert len(statements2) == small, (
        f"SELECTs grew with scale: 20 proxies -> {small}, "
        f"100 proxies -> {len(statements2)}"
    )
    assert small <= 8, statements


@pytest.mark.asyncio
async def test_proxy_used_by_union_semantics(repo):
    """AC-004: current ∪ bound, deduped per profile, with kind labels."""
    proxy_a = await _make_proxy(repo, "px-a", host="a.example.com")
    proxy_b = await _make_proxy(repo, "px-b", host="b.example.com")
    # P1: current A only — created without a proxy, then moved to A, so
    # its runtime row still binds v1 (no proxy) and only current refs A.
    p1 = await _make_profile(repo, "P1", proxy_id=None)
    await repo.update_profile(p1.id, {"proxy_id": proxy_a.id})
    # P2: bound to A (v1) then current moved to B.
    p2 = await _make_profile(repo, "P2", proxy_id=proxy_a.id)
    await repo.bind_runtime_instance(p2.id, "inst-p2", config_version=1)
    await repo.update_profile(p2.id, {"proxy_id": proxy_b.id})
    # P3: current B and bound to B (same env, both kinds -> one entry).
    p3 = await _make_profile(repo, "P3", proxy_id=proxy_b.id)
    await repo.bind_runtime_instance(p3.id, "inst-p3", config_version=1)

    used_a = await repo.get_proxy_used_by(proxy_a.id)
    used_b = await repo.get_proxy_used_by(proxy_b.id)
    assert {e.profile_id: e.kind for e in used_a} == {
        p1.id: "current",
        p2.id: "bound",
    }
    assert {e.profile_id: e.kind for e in used_b} == {
        p2.id: "current",
        p3.id: "both",
    }
    listed = {p.id: p for p in await repo.list_proxies()}
    assert listed[proxy_a.id].used_by_count == 2
    assert listed[proxy_b.id].used_by_count == 2


@pytest.mark.asyncio
async def test_proxy_used_by_released_after_runtime_unbind(repo, db_context):
    """AC-004: once the runtime row is gone the bound reference releases."""
    _engine, session_maker = db_context
    proxy_a = await _make_proxy(repo, "px-a", host="a.example.com")
    p1 = await _make_profile(repo, "P1", proxy_id=proxy_a.id)
    await repo.bind_runtime_instance(p1.id, "inst-p1", config_version=1)
    await repo.update_profile(p1.id, {"proxy_id": None})
    assert len(await repo.get_proxy_used_by(proxy_a.id)) == 1
    # Supervisor unbinds the runtime row when the instance is gone.
    async with session_maker() as session:
        row = await session.get(ProfileRuntimeModel, p1.id)
        await session.delete(row)
        await session.commit()
    assert await repo.get_proxy_used_by(proxy_a.id) == []
    assert (await repo.get_proxy(proxy_a.id)).used_by_count == 0


@pytest.mark.asyncio
async def test_profiles_collection_page_search_sort_no_gap(repo, db_context):
    """AC-001/AC-007: server search finds the last item; pages cover the
    full set exactly once with a stable order; page size is bounded."""
    _engine, session_maker = db_context
    # Bulk-insert 120 profiles (display_number unique) for the matrix.
    async with session_maker() as session:
        session.add_all(
            [
                ProfileModel(
                    id=f"prof-{i:04d}",
                    display_number=1000 + i,
                    name=f"env-{i:04d}",
                    fingerprint_seed=i,
                    user_data_dir=f"/tmp/prof-{i:04d}",
                    sort_order=i,
                    created_at=NOW.isoformat(),
                    updated_at=NOW.isoformat(),
                )
                for i in range(120)
            ]
        )
        await session.commit()

    page = await repo.list_profiles_page(search="env-0119", page=1, page_size=50)
    assert page.total == 1
    assert [p.config.name for p in page.items] == ["env-0119"]

    seen: list[str] = []
    total = None
    for n in (1, 2, 3):
        chunk = await repo.list_profiles_page(page=n, page_size=50)
        total = chunk.total
        assert chunk.page_size == 50
        seen.extend(p.id for p in chunk.items)
    assert total == 120
    assert len(seen) == 120
    assert len(set(seen)) == 120  # no duplicates, no gaps

    clamped = await repo.list_profiles_page(page=1, page_size=5000)
    assert clamped.page_size == 100
    assert clamped.total == 120
    assert len(clamped.items) == 100

    empty = await repo.list_profiles_page(search="no-such-env", page=1, page_size=50)
    assert empty.total == 0
    assert empty.items == []


@pytest.mark.asyncio
async def test_profiles_collection_page_group_filter(repo):
    """AC-001: group filter narrows the total with the same page shape."""
    group = await repo.create_group("g-one", "blue", 0)
    await _make_profile(repo, "in-group", proxy_id=None)
    p = await _make_profile(repo, "grouped-one", proxy_id=None)
    await repo.update_profile(p.id, {"group_id": group.id})
    page = await repo.list_profiles_page(group_id=group.id, page=1, page_size=50)
    assert page.total == 1
    assert page.items[0].config.name == "grouped-one"


@pytest.mark.asyncio
async def test_profiles_collection_page_server_filters(repo, db_context):
    """AC-001: group/ungrouped, direct-proxy, platform and status
    filters narrow the total server-side."""
    _engine, session_maker = db_context
    group = await repo.create_group("g-one", "blue", 0)
    proxy = await _make_proxy(repo, "px-f", host="f.example.com")
    p_grouped = await _make_profile(repo, "grouped", proxy_id=proxy.id)
    await repo.update_profile(p_grouped.id, {"group_id": group.id})
    p_direct = await _make_profile(repo, "direct-one", proxy_id=None)
    p_mac = await _make_profile(repo, "mac-one", proxy_id=None)
    await repo.update_profile(
        p_mac.id, {"fingerprint_platform": "macos"}
    )
    # p_direct is stopped; bind + mark p_grouped running via runtime row.
    async with session_maker() as session:
        rt = await session.get(ProfileRuntimeModel, p_grouped.id)
        rt.observed_state = "running"
        await session.commit()

    assert (
        await repo.list_profiles_page(group_id="ungrouped", page=1, page_size=50)
    ).total == 2
    assert (
        await repo.list_profiles_page(proxy_id="direct", page=1, page_size=50)
    ).total == 2
    assert (
        await repo.list_profiles_page(platform="macos", page=1, page_size=50)
    ).total == 1
    running = await repo.list_profiles_page(
        status="running", page=1, page_size=50
    )
    assert running.total == 1
    assert running.items[0].config.name == "grouped"
    stopped = await repo.list_profiles_page(
        status="stopped", page=1, page_size=50
    )
    assert stopped.total == 2
    by_proxy_name = await repo.list_profiles_page(
        search="px-f", page=1, page_size=50
    )
    assert by_proxy_name.total == 1
    assert by_proxy_name.items[0].config.name == "grouped"


@pytest.mark.asyncio
async def test_profiles_collection_page_status_running_exact(repo, db_context):
    """t076 review f008: status="running_exact" matches only
    observed_state="running" — the "running" bucket (running +
    starting) would let starting rows crowd truly-running rows out
    of the entry page's first page."""
    _engine, session_maker = db_context
    p_run = await _make_profile(repo, "run-one", proxy_id=None)
    p_start = await _make_profile(repo, "start-one", proxy_id=None)
    p_stop = await _make_profile(repo, "stop-one", proxy_id=None)
    async with session_maker() as session:
        rt = await session.get(ProfileRuntimeModel, p_run.id)
        rt.observed_state = "running"
        rt_start = await session.get(ProfileRuntimeModel, p_start.id)
        rt_start.observed_state = "starting"
        await session.commit()

    # The legacy bucket still groups running + starting for the list
    # filter; the exact status does not.
    bucket = await repo.list_profiles_page(
        status="running", page=1, page_size=50
    )
    assert bucket.total == 2
    exact = await repo.list_profiles_page(
        status="running_exact", page=1, page_size=50
    )
    assert exact.total == 1
    assert exact.items[0].config.name == "run-one"
    assert p_stop.id not in [item.id for item in exact.items]


@pytest.mark.asyncio
async def test_profiles_collection_page_sorts(repo, db_context):
    """AC-001: name/created/recent sorts are stable and server-side."""
    _engine, session_maker = db_context
    a = await _make_profile(repo, "b-name", proxy_id=None)
    b = await _make_profile(repo, "a-name", proxy_id=None)
    by_name = await repo.list_profiles_page(sort="name", page=1, page_size=50)
    assert [p.config.name for p in by_name.items] == ["a-name", "b-name"]
    # t076 review test f001: the old assertion was vacuously true with
    # two rows (either name satisfies `in (...)`). Give the rows
    # distinguishable creation times so `sort="created"` (created_at
    # desc) pins the exact order: the later-created "a-name" first.
    async with session_maker() as session:
        for profile, created in (
            (a, "2026-11-01T00:00:00+00:00"),
            (b, "2026-11-02T00:00:00+00:00"),
        ):
            row = await session.get(ProfileModel, profile.id)
            row.created_at = created
        await session.commit()
    by_created = await repo.list_profiles_page(
        sort="created", page=1, page_size=50
    )
    assert [p.config.name for p in by_created.items] == ["a-name", "b-name"]
    assert by_created.total == 2
    # Recent = latest runtime activity first: b started later than a.
    async with session_maker() as session:
        for pid, started in (
            (a.id, "2026-11-01T00:00:00+00:00"),
            (b.id, "2026-11-02T00:00:00+00:00"),
        ):
            rt = await session.get(ProfileRuntimeModel, pid)
            rt.last_started_at = started
        await session.commit()
    recent = await repo.list_profiles_page(sort="recent", page=1, page_size=50)
    assert [p.config.name for p in recent.items] == ["a-name", "b-name"]


@pytest.mark.asyncio
async def test_proxies_collection_page_scheme_filter(repo):
    """AC-001: scheme filter narrows the proxy total server-side."""
    await _make_proxy(repo, "px-http", host="h.example.com")
    https = await repo.create_proxy(
        {
            "name": "px-https",
            "scheme": "https",
            "host": "s.example.com",
            "port": 8080,
            "username": "user",
            "password": "s3cret-pw",
        }
    )
    page = await repo.list_proxies_page(scheme="https", page=1, page_size=50)
    assert page.total == 1
    assert page.items[0].id == https.id


@pytest.mark.asyncio
async def test_proxy_candidates_find_last_item_bounded(repo):
    """AC-006: bounded name search finds the last candidate, untruncated.

    t076 review test f002: these assertions used to live inside the
    scheme-filter test (with a stray docstring as the only marker), so
    a refactor of that test could silently drop the only backend
    coverage for AC-006 candidate lookup."""
    for i in range(60):
        await _make_proxy(repo, f"cand-{i:03d}", host=f"c{i}.example.com")
    found = await repo.list_proxy_candidates(search="cand-059", limit=50)
    assert [c.name for c in found] == ["cand-059"]
    capped = await repo.list_proxy_candidates(search="cand-", limit=500)
    assert len(capped) == 50  # limit is bounded even when asked for more


@pytest.mark.asyncio
async def test_proxy_country_ranges_from_observations(repo):
    """AC-006: country -> city ranges come from the backend, keyed by
    stable country code.

    t076 review f004 replaces the old aggregation: ranges used to
    collect every historical observation row, so one proxy observed in
    three places offered three cities. Ranges now aggregate the latest
    still-valid observation per proxy — the same rows the collection
    filter matches — so each proxy contributes exactly one current
    country/city. The old single-proxy-three-observations setup is
    deleted wholesale; the new setup records one observation per proxy.
    """
    now = NOW
    for name, host, country_code, city in (
        ("px-geo-jp1", "geo1.example.com", "JP", "Tokyo"),
        ("px-geo-jp2", "geo2.example.com", "JP", "Osaka"),
        ("px-geo-us", "geo3.example.com", "US", "Ashburn"),
    ):
        proxy = await _make_proxy(repo, name, host=host)
        await repo.record_egress_observation(
            proxy.id,
            EgressObservation(
                proxy_id=proxy.id,
                endpoint_fingerprint=ProxyEndpoint(
                    scheme="http", host=proxy.host, port=proxy.port, username="user"
                ).fingerprint,
                credential_revision=proxy.credential_revision,
                status="ok",
                egress_ip="203.0.113.9",
                country_code=country_code,
                city=city,
                observed_at=now,
                expires_at=now + timedelta(seconds=OBSERVATION_TTL_SECONDS),
            ),
        )
    ranges = await repo.proxy_country_ranges()
    by_code = {r.country_code: r for r in ranges}
    assert by_code["JP"].cities == ["Osaka", "Tokyo"]
    assert by_code["US"].cities == ["Ashburn"]


@pytest.mark.asyncio
async def test_list_runtimes_single_query_contents(repo):
    """AC-002: one batched read returns every profile's runtime state
    (the summary the list UI consumes instead of per-profile HTTP)."""
    proxy = await _make_proxy(repo, "px-r", host="r.example.com")
    p1 = await _make_profile(repo, "R1", proxy_id=proxy.id)
    p2 = await _make_profile(repo, "R2", proxy_id=None)
    await repo.bind_runtime_instance(p1.id, "inst-r1", config_version=1)
    runtimes = await repo.list_runtimes()
    by_id = {r.profile_id: r for r in runtimes}
    assert by_id[p1.id].runtime_instance_id == "inst-r1"
    assert by_id[p1.id].config_version == 1
    assert by_id[p2.id].runtime_instance_id is None


@pytest.mark.asyncio
async def test_proxies_collection_page_country_filter(repo):
    """AC-001/AC-006: proxy pages filter by stable country code."""
    jp = await _make_proxy(repo, "px-jp", host="jp.example.com")
    us = await _make_proxy(repo, "px-us", host="us.example.com")
    for proxy, code in ((jp, "JP"), (us, "US")):
        await repo.record_egress_observation(
            proxy.id,
            EgressObservation(
                proxy_id=proxy.id,
                endpoint_fingerprint=ProxyEndpoint(
                    scheme="http", host=proxy.host, port=proxy.port, username="user"
                ).fingerprint,
                credential_revision=proxy.credential_revision,
                status="ok",
                egress_ip="203.0.113.9",
                country_code=code,
                observed_at=NOW,
                expires_at=NOW + timedelta(seconds=OBSERVATION_TTL_SECONDS),
            ),
        )
    page = await repo.list_proxies_page(country_code="JP", page=1, page_size=50)
    assert page.total == 1
    assert page.items[0].id == jp.id


@pytest.mark.asyncio
async def test_scale_matrix_1000(repo, db_context):
    """AC-005/AC-007: 1000-scale matrix — list_proxies SELECTs stay at
    the small-scale bound with 1000 proxies / 100 bound runtimes, and
    1000 profiles page, search and resolve candidates without
    truncation. (0/1 scale: empty-collection and single-item cases are
    covered by the empty search and union tests above.)"""
    import json
    import uuid

    engine, session_maker = db_context
    async with session_maker() as session:
        session.add_all(
            [
                ProxyModel(
                    id=f"scale-px-{i:04d}",
                    name=f"scale-px-{i:04d}",
                    scheme="http",
                    host=f"s{i}.example.com",
                    port=8080,
                    created_at=NOW.isoformat(),
                    updated_at=NOW.isoformat(),
                )
                for i in range(1000)
            ]
        )
        await session.commit()
    # 100 profiles: current ref to one proxy, bound ref to another,
    # runtime row bound to config version 1.
    async with session_maker() as session:
        session.add_all(
            [
                ProfileModel(
                    id=f"scale-prof-{i:03d}",
                    display_number=5000 + i,
                    name=f"scale-prof-{i:03d}",
                    fingerprint_seed=i,
                    user_data_dir=f"/tmp/scale-prof-{i:03d}",
                    sort_order=i,
                    proxy_id=f"scale-px-{i:04d}",
                    created_at=NOW.isoformat(),
                    updated_at=NOW.isoformat(),
                )
                for i in range(100)
            ]
        )
        session.add_all(
            [
                ProfileConfigVersionModel(
                    id=str(uuid.uuid4()),
                    profile_id=f"scale-prof-{i:03d}",
                    version=1,
                    snapshot=json.dumps(
                        {
                            "config": {
                                "name": f"scale-prof-{i:03d}",
                                "proxy_id": f"scale-px-{(i + 500):04d}",
                            },
                        }
                    ),
                    created_at=NOW.isoformat(),
                )
                for i in range(100)
            ]
        )
        session.add_all(
            [
                ProfileRuntimeModel(
                    profile_id=f"scale-prof-{i:03d}",
                    desired_state="stopped",
                    observed_state="stopped",
                    runtime_instance_id=f"scale-inst-{i:03d}",
                    config_version=1,
                )
                for i in range(100)
            ]
        )
        await session.commit()
    # 1000 paging profiles under a distinct name prefix.
    async with session_maker() as session:
        session.add_all(
            [
                ProfileModel(
                    id=f"scale-env-{i:04d}",
                    display_number=9000 + i,
                    name=f"scale-env-{i:04d}",
                    fingerprint_seed=i,
                    user_data_dir=f"/tmp/scale-env-{i:04d}",
                    sort_order=i,
                    created_at=NOW.isoformat(),
                    updated_at=NOW.isoformat(),
                )
                for i in range(1000)
            ]
        )
        await session.commit()

    statements, listener = _count_selects(engine)
    try:
        listed = await repo.list_proxies()
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", listener)
    assert len(listed) == 1000
    assert len(statements) <= 8, statements

    seen: list[str] = []
    for page_no in range(1, 11):
        chunk = await repo.list_profiles_page(
            search="scale-env-", page=page_no, page_size=100
        )
        assert chunk.total == 1000
        seen.extend(p.id for p in chunk.items)
    assert len(seen) == 1000
    assert len(set(seen)) == 1000  # no duplicates, no gaps

    last = await repo.list_profiles_page(
        search="scale-env-0999", page=1, page_size=50
    )
    assert last.total == 1
    assert last.items[0].id == "scale-env-0999"

    proxy_hits = await repo.list_proxy_candidates(search="scale-px-0999")
    assert [c.id for c in proxy_hits] == ["scale-px-0999"]
    profile_hits = await repo.list_profile_candidates(search="scale-env-0999")
    assert [c.id for c in profile_hits] == ["scale-env-0999"]


@pytest.mark.asyncio
async def test_proxy_country_ranges_exclude_expired_ok_observations(repo):
    """AC-006 (t076 review f004): country ranges use the same "latest
    and still valid" rows as the collection filter — a country whose
    latest ok observation expired must not offer a dead option that
    filters to zero rows."""
    stale = await _make_proxy(repo, "px-stale", host="stale.example.com")
    fresh = await _make_proxy(repo, "px-fresh", host="fresh.example.com")

    def _obs(proxy, country_code, city, observed_at, expires_at):
        return EgressObservation(
            proxy_id=proxy.id,
            endpoint_fingerprint=ProxyEndpoint(
                scheme="http", host=proxy.host, port=proxy.port, username="user"
            ).fingerprint,
            credential_revision=proxy.credential_revision,
            status="ok",
            egress_ip="203.0.113.9",
            country_code=country_code,
            city=city,
            observed_at=observed_at,
            expires_at=expires_at,
        )

    await repo.record_egress_observation(
        stale.id,
        _obs(stale, "JP", "Tokyo", NOW - timedelta(hours=2), NOW - timedelta(hours=1)),
    )
    await repo.record_egress_observation(
        fresh.id,
        _obs(fresh, "JP", "Osaka", NOW, NOW + timedelta(seconds=OBSERVATION_TTL_SECONDS)),
    )
    ranges = await repo.proxy_country_ranges()
    by_code = {r.country_code: r for r in ranges}
    assert by_code["JP"].cities == ["Osaka"]
    # The filter side agrees: only the fresh proxy matches JP.
    page = await repo.list_proxies_page(country_code="JP", page=1, page_size=50)
    assert page.total == 1
    assert page.items[0].id == fresh.id


@pytest.mark.asyncio
async def test_proxy_impact_reuses_single_reference_map(repo, db_context):
    """AC-005 (t076 review f005): one proxy_impact call computes the
    reference map once (3 SELECTs), not once per helper."""
    engine, _maker = db_context
    proxy_a = await _make_proxy(repo, "px-a", host="a.example.com")
    proxy_b = await _make_proxy(repo, "px-b", host="b.example.com")
    p1 = await _make_profile(repo, "P1", proxy_id=proxy_a.id)
    await repo.bind_runtime_instance(p1.id, "inst-p1", config_version=1)
    p2 = await _make_profile(repo, "P2", proxy_id=proxy_a.id)
    await repo.bind_runtime_instance(p2.id, "inst-p2", config_version=1)
    await repo.update_profile(p2.id, {"proxy_id": proxy_b.id})

    statements, listener = _count_selects(engine)
    try:
        current, bound_only = await repo.proxy_impact(proxy_a.id)
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", listener)
    assert sorted(current) == sorted([p1.id])
    assert bound_only == [p2.id]
    assert len(statements) == 3, statements


@pytest.mark.asyncio
async def test_profiles_collection_page_carries_row_names(repo):
    """AC-001 (t076 review f006): the collection page returns the row's
    group/proxy display names, so list pages never fetch the whole
    group/proxy tables just to name a row."""
    group = await repo.create_group("Work", "blue", 0)
    proxy = await _make_proxy(repo, "px-named", host="n.example.com")
    named = await _make_profile(repo, "Named", proxy_id=proxy.id)
    await repo.update_profile(named.id, {"group_id": group.id})
    plain = await _make_profile(repo, "Plain", proxy_id=None)

    page = await repo.list_profiles_page(sort="name", page=1, page_size=50)
    by_id = {item.id: item for item in page.items}
    assert by_id[named.id].group_name == "Work"
    assert by_id[named.id].group_color == "blue"
    assert by_id[named.id].proxy_name == "px-named"
    assert by_id[plain.id].group_name is None
    assert by_id[plain.id].group_color is None
    assert by_id[plain.id].proxy_name is None


@pytest.mark.asyncio
async def test_like_search_escapes_wildcards(repo):
    """AC-001 (t076 review f007): `%`/`_` in a search term match
    literally instead of acting as LIKE wildcards."""
    for name in ("100%", "1000", "100A"):
        await _make_proxy(repo, name, host=f"{name}.example.com")
    page = await repo.list_proxies_page(search="100%", page=1, page_size=50)
    assert page.total == 1
    assert page.items[0].name == "100%"
    found = await repo.list_proxy_candidates(search="100%")
    assert [c.name for c in found] == ["100%"]

    await _make_profile(repo, "a_b", proxy_id=None)
    await _make_profile(repo, "axb", proxy_id=None)
    page = await repo.list_profiles_page(search="a_b", page=1, page_size=50)
    assert page.total == 1
    assert page.items[0].config.name == "a_b"
