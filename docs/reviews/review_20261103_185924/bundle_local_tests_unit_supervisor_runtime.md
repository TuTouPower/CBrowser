# bundle_local_tests_unit_supervisor_runtime

## responsibilities

- Unit-test layer for the v2 supervisor, runtime coordinator/agent, stream runtime, gateway control, domain models and repositories: lifecycle reconcile, startup recovery, stop fences/teardown, event spool delivery and cursors, token/credential isolation, path ownership, network policy, launch-arg allowlisting, evidence redaction, and schema/protocol contract drift.
- Shared fixture base (tests/unit/conftest.py) providing a real migrated database context (run_database_migrations + engine dispose) used across domain/repository and coordinator tests.

## interfaces

- Tests exercise production entry points: SupervisorCore reconcile/report/consume APIs, RuntimeCoordinator publish/stop paths, runtime agent FastAPI app over ASGI transport and real UDS, EventForwarder/EventStorage on-disk spool, generated runtime protocol schema and supervisor OpenAPI schema.
- Fixture/harness code from gateway_probe and supervisor_recovery_probe packages is exercised as test infrastructure (RealSupervisorContainer, RealApiProcess, GatewayTopologyHarness) with mocked Docker clients.

## dependencies

- pytest + pytest-asyncio, httpx (ASGI transport and real loopback/UDS), unittest.mock, docker SDK errors, aiohttp test utils, uvicorn for one real-UDS test.
- Production packages under test: cbrowser.supervisor, cbrowser.runtime_agent, cbrowser.runtime (coordinator), cbrowser.stream_agent, cbrowser.gateway, cbrowser.domain/repositories.

## flows

- Behavioral assertions dominate: terminal-observation reporting requires API ACK before dedup/desired-state change; forged exit files are rejected when process or CDP is alive; owner-loss preserves error semantics; one profile's reconcile failure does not block another profile's restore; spool envelopes carry version=1, legacy unversioned files replay, unknown version 99 is quarantined.
- Deterministic time is the norm: ManualClock/fake_clock fixtures injected into stream runtime, API coordinator, agent faults and recovery coordinator; docker offload test proves event-loop non-blocking via threading.Event rather than wall-clock comparison.

## constraints

- Static review only; no test was executed, so pass/fail status of the suite is not independently confirmed here.
- Several tests depend on environment properties: unprivileged UID for chmod-based fault injection, absence of PID 999999, /tmp space for UDS paths, and CWD=repo root for one schema path.

## decisions

- tests/unit/review_privacy_allowlist.txt (9 lines) exempts historical review snapshots and the t018 review files from privacy scanning, citing decision A44 (history is not rewritten); accepted as a documented, scoped exception rather than a finding.
- test_supervisor_resource_policy.py explicitly preserves legacy test semantics in a labeled section and adds separate gap tests, consistent with the repo rule against rewriting old expectations in place.

## evidence

- test_domain_and_repository.py::test_models_match_migrations asserts compare_metadata == [] after real migrations, plus CAS/idempotency/failure_count behavior tests.
- test_supervisor_startup_recovery.py fake-exit guards assert both emit_event.call_count == 0 and report_terminal_observation.assert_not_awaited() (the channel production actually uses).
- test_supervisor_event_delivery.py asserts queued spool envelope version == 1, legacy replay, and version-99 quarantine; includes real loopback HTTP delivery and listener-restart recovery.
- test_launch_args.py pins the A45 allowlist contract at three layers (ProfileConfig filtering, CreateRequest rejection, runner second gate); test_network_policy_input_safety.py asserts injection-shaped endpoints are rejected and canaries never echo into diagnostics; test_evidence_redaction.py asserts secrets/payloads are redacted on disk.
- test_runtime_protocol.py / test_runtime_agent_protocol_export.py / test_supervisor_schema.py compare generated schemas byte-for-byte / deep-equal and assert internal routes stay out of the public schema.

## uncertainties

- Whether the chmod-0o500 fault-injection test and the relative-path schema test pass in the project's actual CI environment (root vs non-root, CWD) cannot be settled statically.
- Exact 2/10/30 retry backoff values are exercised indirectly (cooldown advance windows in the recovery coordinator tests); no single assertion in this unit pins the full numeric sequence.

## Findings

- [Low][95] tests/unit/test_supervisor_core.py:1 — Module docstring claims AC-004/AC-005 tests that do not exist in this file
  - ID: f_tests_unit_supervisor_runtime_01; verification: static
  - Evidence: Docstring lines 6-7 list '3. Retry policy 2/10/30 backoff and 3-strikes blocking (AC-005)' and '4. Event forwarder offline spooling and recovery deduplication (AC-004)'.; The file contains only two tests: test_path_validator_symlink_and_traversal (line 17) and test_port_allocator_exhaustion_and_reuse (line 47).
  - Impact: Anyone auditing coverage from the docstring overstates this file's scope. The behaviors are covered elsewhere in the unit (event delivery spool tests, recovery coordinator cooldown tests), so this is documentation drift, not a coverage hole.
  - Fix: Trim the docstring to the two tests actually present, or move the AC-004/AC-005 items to the files that implement them.

- [Low][90] tests/unit/test_runtime_agent.py:306 — Residual wall-clock timing assertions can flake under load
  - ID: f_tests_unit_supervisor_runtime_02; verification: static
  - Evidence: test_runtime_agent.py lines 306-316: three health probes each time.sleep(0.25), then assert elapsed < 0.6 to prove concurrency.; test_domain_and_repository.py line 465: WAL reader parallelism test asserts elapsed < 1.0 while a write lock is held.
  - Impact: On a heavily loaded CI runner the agent concurrency assertion (0.6s budget vs 0.75s serialized floor) can fail spuriously; most of the unit has moved to injected clocks and condition waits, leaving these as the residual flake surface.
  - Fix: Prove concurrency structurally (e.g. overlapping-interval recording in the probe handler) instead of an elapsed-time budget; keep the WAL bound but derive it from lock-hold duration rather than an absolute 1.0s.

- [Low][90] tests/unit/test_runtime_coordinator_background_tasks.py:48 — Fixed-interval polling loops remain in a few async tests
  - ID: f_tests_unit_supervisor_runtime_03; verification: static
  - Evidence: test_runtime_coordinator_background_tasks.py lines 48-51: for _ in range(100): await asyncio.sleep(0.01) waiting for _publish_tasks to drain.; test_runtime_coordinator_stop_paths.py lines 220-223: 300 x sleep(0.01) waiting for loop liveness change.; test_supervisor_recovery.py lines 500-507: 50 x sleep(0.05) waiting for heartbeat observability (with pytest.fail fallback).
  - Impact: The loops are condition-bounded (not bare sleep-then-assert), so the risk is limited: on slow machines the fixed budget can expire before the condition holds, producing intermittent failures that are hard to attribute.
  - Fix: Adopt the _wait_until/ManualClock predicate-wait pattern already used in test_stream_runtime.py and test_api_runtime_coordinator.py for these remaining sites.

- [Low][85] tests/unit/test_supervisor_event_cursor.py:34 — Test helper returns a SupervisorCore whose API client is already closed; cursor assertion accepts two values
  - ID: f_tests_unit_supervisor_runtime_04; verification: static
  - Evidence: _core() (lines 34-44) constructs SupervisorCore inside 'async with httpx.AsyncClient(...)' (line 37) and returns it after the block exits, so core's api client is closed; current tests pass only because consume_disk_events never uses that client.; Line 63: assert cursors['p1']['inst_1'][1] in {'e1.json', 'e2.json'} accepts either filename as the cursor position.
  - Impact: Latent fragility: any future test in this file that exercises a core path using the api client fails with a confusing closed-client error; the two-value cursor assertion weakens the precision guarantee the cursor mechanism exists to provide.
  - Fix: Build the client outside the helper's async-with (or construct the core with a caller-managed client), and assert the exact expected cursor filename for the seeded event order.

- [Low][90] tests/unit/test_runtime_protocol.py:23 — Schema validity test depends on CWD via a relative path
  - ID: f_tests_unit_supervisor_runtime_05; verification: static
  - Evidence: Line 23: schema_path = Path('schemas/runtime/agent_protocol.json') in test_schema_json_file_validity.; Sibling tests in this unit anchor paths with Path(__file__).parents[2] instead of relying on the working directory.
  - Impact: Running pytest from any directory other than the repo root makes this test fail for environmental reasons, which either hides in CI configuration assumptions or produces misleading failures for developers.
  - Fix: Anchor the path to the repo root via Path(__file__).resolve().parents[2], as the sibling tests do.

- [Low][80] tests/unit/test_runtime_persistence_guards.py:144 — Storage-failure injection via chmod 0o500 is environment-dependent (root bypasses it)
  - ID: f_tests_unit_supervisor_runtime_06; verification: suspected
  - Evidence: Line 144: event_directory.chmod(0o500) is used to force a write failure for the terminal-storage-failure propagation test (restored to 0o700 at line 150).; POSIX permission bits do not block writes for UID 0, so under a root test runner the injected failure never occurs.
  - Impact: In a containerized root CI the test either fails spuriously or, worse, is silently skipped around; the failure-propagation behavior it guards is security-relevant (terminal state must not be swallowed).
  - Fix: Inject the failure at the storage seam (monkeypatch the write method to raise) instead of relying on filesystem permissions, keeping a permission-based variant only when os.geteuid() != 0.

- [Low][85] tests/unit/test_supervisor_normal_exit_observation.py:316 — Suite-wide coupling to private internals as test seams
  - ID: f_tests_unit_supervisor_runtime_07; verification: static
  - Evidence: Tests routinely replace or read private members: core._query_agent_health assignment and core._sessions seeding (test_supervisor_normal_exit_observation.py), coordinator._publish_tasks/_active_tasks polling (coordinator tests), recovery._cleanup_failures, adapter._teardown_profile_sync, gw_control._client swap.; test_runtime_coordinator_error_responses.py and test_runtime_coordinator_stop_paths.py fabricate runtime state with raw sqlite3 UPDATE statements (acknowledged in in-file comments).
  - Impact: Assertions overwhelmingly check behavioral outcomes, so correctness signal is good; the cost is maintainability — internal refactors that preserve behavior will still break many tests, and raw-SQL state fabrication can drift from the real write path's invariants.
  - Fix: Where a seam is load-bearing (agent health query, session seeding), promote it to a named test-facing constructor/fixture parameter; prefer repository APIs over raw SQL for state fabrication.

## views

```json
{
  "contracts": {
    "reviewer": "bb257d5c-e0ff-41e9-acd8-fddb07961af9",
    "status": "completed"
  },
  "correctness": {
    "reviewer": "bb257d5c-e0ff-41e9-acd8-fddb07961af9",
    "status": "completed"
  },
  "design": {
    "reviewer": "bb257d5c-e0ff-41e9-acd8-fddb07961af9",
    "status": "completed"
  },
  "documentation": {
    "reviewer": "bb257d5c-e0ff-41e9-acd8-fddb07961af9",
    "status": "completed"
  },
  "performance": {
    "reviewer": "bb257d5c-e0ff-41e9-acd8-fddb07961af9",
    "status": "completed"
  },
  "robustness": {
    "reviewer": "bb257d5c-e0ff-41e9-acd8-fddb07961af9",
    "status": "completed"
  },
  "security": {
    "reviewer": "bb257d5c-e0ff-41e9-acd8-fddb07961af9",
    "status": "completed"
  },
  "tests": {
    "reviewer": "bb257d5c-e0ff-41e9-acd8-fddb07961af9",
    "status": "completed"
  }
}
```

## files_reviewed

```json
[
  "tests/unit/conftest.py",
  "tests/unit/review_privacy_allowlist.txt",
  "tests/unit/test_api_runtime_coordinator.py",
  "tests/unit/test_baseline_fixture_regressions.py",
  "tests/unit/test_baseline_runtime_regressions.py",
  "tests/unit/test_browser_readiness_fence.py",
  "tests/unit/test_docker_offload.py",
  "tests/unit/test_domain_and_repository.py",
  "tests/unit/test_evidence_redaction.py",
  "tests/unit/test_exit_reason_allowlist.py",
  "tests/unit/test_launch_args.py",
  "tests/unit/test_network_policy.py",
  "tests/unit/test_network_policy_input_safety.py",
  "tests/unit/test_recovery_authority.py",
  "tests/unit/test_recovery_shutdown_safety.py",
  "tests/unit/test_resource_fault_isolation.py",
  "tests/unit/test_runtime_agent.py",
  "tests/unit/test_runtime_agent_faults.py",
  "tests/unit/test_runtime_agent_protocol_export.py",
  "tests/unit/test_runtime_coordinator_background_tasks.py",
  "tests/unit/test_runtime_coordinator_error_responses.py",
  "tests/unit/test_runtime_coordinator_stop_paths.py",
  "tests/unit/test_runtime_event_broadcaster_epoch.py",
  "tests/unit/test_runtime_event_policy.py",
  "tests/unit/test_runtime_instance_storage.py",
  "tests/unit/test_runtime_persistence_guards.py",
  "tests/unit/test_runtime_profile_defaults.py",
  "tests/unit/test_runtime_protocol.py",
  "tests/unit/test_stream_runtime.py",
  "tests/unit/test_supervisor_adapter_paths.py",
  "tests/unit/test_supervisor_agent_credentials.py",
  "tests/unit/test_supervisor_control_auth.py",
  "tests/unit/test_supervisor_coordinator_lock.py",
  "tests/unit/test_supervisor_core.py",
  "tests/unit/test_supervisor_display_config.py",
  "tests/unit/test_supervisor_event_cursor.py",
  "tests/unit/test_supervisor_event_delivery.py",
  "tests/unit/test_supervisor_file_permissions.py",
  "tests/unit/test_supervisor_file_storage.py",
  "tests/unit/test_supervisor_infrastructure_config.py",
  "tests/unit/test_supervisor_metrics.py",
  "tests/unit/test_supervisor_normal_exit_observation.py",
  "tests/unit/test_supervisor_operation_journal.py",
  "tests/unit/test_supervisor_port_recovery.py",
  "tests/unit/test_supervisor_profile_path_ownership.py",
  "tests/unit/test_supervisor_reconcile_fences.py",
  "tests/unit/test_supervisor_recovery.py",
  "tests/unit/test_supervisor_recovery_coordinator.py",
  "tests/unit/test_supervisor_resource_aggregation.py",
  "tests/unit/test_supervisor_resource_policy.py",
  "tests/unit/test_supervisor_schema.py",
  "tests/unit/test_supervisor_selkies_token_instances.py",
  "tests/unit/test_supervisor_selkies_token_isolation.py",
  "tests/unit/test_supervisor_selkies_tokens.py",
  "tests/unit/test_supervisor_startup_recovery.py",
  "tests/unit/test_supervisor_stop_fence.py",
  "tests/unit/test_supervisor_stop_teardown.py",
  "tests/unit/test_supervisor_unprotected_sandbox.py"
]
```
