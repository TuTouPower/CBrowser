# bundle_local_tests_unit_supervisor_runtime

## responsibilities

- Unit-test coverage for the Supervisor domain: path validation/symlink fences, UDP port allocation, operation journal idempotency, coordinator single-owner lock, network policy (iptables rendering, startup gate), Selkies token provisioning/isolation, resource CPU policy and aggregation, event spool/cursor/delivery, recovery coordinator and startup recovery, normal-exit observation cross-verification, file permissions and atomic storage.
- Unit-test coverage for the Runtime Agent and API-side RuntimeCoordinator: agent protocol schemas and byte-identical schema export, event storage durability/fsync failure handling, launch-arg sanitization, CDP proxy faults over real loopback WebSocket/UDS, coordinator reconcile loops (start/stop/status, retry caps, stable operation ids, error-body parsing), SSE broadcaster epoch/replay semantics.
- Domain/repository tests for the v2 profile store: CRUD and legacy field round-trip, immutable config-version snapshots, idempotency conflicts, CAS instance binding, WAL/busy-timeout pragmas, runtime event policy (disk events are diagnostics only; observations own lifecycle).
- Baseline regression tests pinning packaging contracts (Dockerfile digest pinning and COPY lines), Docker event watcher shutdown behavior, and ownership/cleanup contracts of the tests/fixtures harnesses (RealSupervisorContainer, GatewayTopologyHarness, RealApiProcess).

## interfaces

- Tests exercise public surfaces: FastAPI apps via httpx ASGI transport (supervisor control server, runtime agent), real loopback HTTP/WebSocket/UDS servers (aiohttp, uvicorn, websockets), ProfileRepository async API against real SQLite files, pydantic models, and generated JSON schemas under schemas/runtime and schemas/openapi.
- Several tests bypass public surfaces and drive private members directly: SupervisorCore._sessions/_terminal_observations/_reconcile_instance_observation/_query_agent_health, RuntimeCoordinator._active_tasks/_publish_tasks/_running/_reconcile_profile_loop, RecoveryCoordinator._in_flight_tasks/_cleanup_failures/_reported_dead_instances/_execute_retry, BrowserRunner._wait_for_chrome_exit (see finding f_tests_unit_supervisor_runtime_04).

## dependencies

- pytest with asyncio_mode=auto (root pyproject.toml), pytest-asyncio fixtures, httpx MockTransport/ASGITransport, aiohttp test utils and real servers, docker SDK error types (mocked client in most tests; no live daemon required), sqlalchemy/aiosqlite, jsonschema, runpy-driven export scripts under scripts/.
- Cross-test-module coupling: test_runtime_event_policy.py imports fixtures from test_domain_and_repository (relies on pytest prepending the test dir to sys.path; tests/unit has no __init__.py and no conftest.py); test_baseline_fixture_regressions.py inserts REPO_ROOT and tests/fixtures into sys.path at import time and loads fixture packages plus an e2e test module.
- Import of a bare top-level `diagnostics` module (src/backend/diagnostics.py) in test_exit_reason_allowlist.py depends on src/backend being on sys.path; the root pyproject sets no pythonpath, so resolution depends on the invocation environment.

## flows

- Coordinator tests build a real migrated SQLite DB plus a MockTransport supervisor, then drive reconcile_profile_now or the private reconcile loop and assert on ReconcileOutcome, get_last_error, recorded request paths/bodies, and persisted runtime rows.
- Supervisor core tests construct SupervisorCore with hand-written fake Docker adapters (SimpleNamespace or small classes), seed core._sessions directly, invoke stop/scan/reconcile methods, and assert on returned dicts, port allocator state, session identity, and mock call counts.
- Recovery tests feed RecoveryCoordinator a MagicMock/SimpleNamespace core whose api.get returns a scripted sequence of DummyResponse objects positionally matched to tick()'s internal call order, then assert which observations/starts were (not) triggered.
- Fault tests inject failures at real boundaries: os.fsync raising for directories, chmod-restricted directories, corrupt JSON state files, silent/malformed loopback WebSocket peers, dead PIDs and live dummy CDP HTTP servers for cross-verification.

## constraints

- Static review only per assignment: no test was executed, so pass/fail status of every assertion is unverified; timing- and environment-sensitive findings are marked suspected where behavior could not be confirmed statically.
- Many tests are integration-grade despite living in tests/unit (real subprocesses, real sockets/UDS, real SQLite, thread-based Docker streams); they assume loopback networking, a writable tmp dir, and (for permission-denial fault injection) a non-root user.
- asyncio_mode=auto means async tests run even without the marker; the explicit @pytest.mark.asyncio markers used throughout are redundant but harmless.

## decisions

- The suite consistently prefers real storage/transport at system boundaries (SQLite files, loopback HTTP/WS/UDS, real subprocess locks) over deep mocking; mocks concentrate on the Docker client and on the SupervisorCore collaborator of RecoveryCoordinator.
- Canary-based leak assertions recur as the standard proof that rejected input/payloads never reach logs or responses (network policy input safety, runtime persistence guards, runtime agent faults, coordinator error responses).
- Schema contracts are pinned by byte-identity between generated exports and checked-in JSON (agent protocol, supervisor protocol, OpenAPI), not by shape sampling — except the weaker duplicate in test_runtime_protocol.py (finding f_tests_unit_supervisor_runtime_11).

## evidence

- All 54 unit files read in full (10,381 lines total per wc -l), including test_baseline_fixture_regressions.py:1-1239 and test_supervisor_normal_exit_observation.py:1-1076.
- Production cross-checks: src/backend/cbrowser/supervisor/core.py:54-71 browser_runtime_ready matches the readiness-fence test's field mutations; src/backend/diagnostics.py:249-264 _SAFE_EXIT_REASONS is derived from ExitReason and _sanitize_reason lowercases/strips before membership check; src/backend/cbrowser/domain/runtime_policy.py:9-24 ExitReason values are all lowercase, so the verbatim-logging test is consistent; src/backend/cbrowser/supervisor/docker_adapter.py uses asyncio.to_thread for blocking Docker work (e.g. lines 218, 409, 641-704), matching the offload tests' premise.
- pyproject.toml:22-32 sets asyncio_mode=auto and testpaths including tests; .gitignore contains `.scratch/`, so the scratch dirs written by three normal-exit tests are ignored by git but still created under the pytest CWD.
- No real secrets found in the unit's test files: tokens are generated with secrets.* or obvious placeholders ('A'*32, 'agent_secret_test', 'super_secret_token' in a repr-redaction assertion, proxy 'user:pass@127.0.0.1:1080').

## uncertainties

- Whether the full unit suite currently passes is unknown (execution was out of scope); in particular the wall-clock tests (f_tests_unit_supervisor_runtime_02/03) and the root-sensitivity suspicion (f_tests_unit_supervisor_runtime_10) can only be settled by running the suite under CI-like load and as root/non-root.
- How `import diagnostics` and `import cbrowser` resolve when tests/unit is run standalone could not be determined from the unit files alone (no conftest.py in tests/unit, no pythonpath in root pyproject); if the harness relies on an installed package or CI env var, test_exit_reason_allowlist.py is environment-fragile, but this was not counted as a finding without the invocation evidence.
- Whether consume_disk_events ever touches SupervisorCore.api on the journal paths used by test_supervisor_event_cursor.py could not be fully traced statically; the closed-client concern (f_tests_unit_supervisor_runtime_07) is therefore marked suspected.

## Findings

- [Medium][95] tests/unit/test_domain_and_repository.py:33-40 — Repository/domain tests build the schema with Base.metadata.create_all instead of the production migrations, so model↔migration drift is undetectable in this suite
  - ID: f_tests_unit_supervisor_runtime_01; verification: static
  - Evidence: db_context fixture (lines 36-42) creates all tables via `await conn.run_sync(Base.metadata.create_all)` on a fresh SQLite file.; Sibling suites in the same unit (test_api_runtime_coordinator.py:22-29, test_runtime_coordinator_error_responses.py:30-36, test_runtime_coordinator_stop_paths.py:23-28) instead call run_database_migrations(db_path), proving the migration path exists and is usable in tests.; test_eight_tables_exist (lines 65-82) only asserts the model-derived table names exist, which is tautological when the schema was just created from the same models.
  - Impact: A migration that diverges from the SQLAlchemy models (missing column, wrong default, missing index) would pass the entire domain/repository suite while breaking or silently altering production behavior; the repository is the persistence core for profiles, runtimes, and idempotency.
  - Fix: Switch db_context to run_database_migrations(temp_db_path) like the coordinator suites, keeping create_all only if a specific test documents why it needs un-migrated schema.

- [Medium][90] tests/unit/test_docker_offload.py:44-67 — Event-loop offload tests assert on wall-clock timing (0.3s injected sleep, elapsed >= 0.25, ticker ticks >= 5), making them flaky under load
  - ID: f_tests_unit_supervisor_runtime_02; verification: static
  - Evidence: test_teardown_offloads_blocking_docker_cleanup replaces adapter._teardown_profile_sync with `lambda _pid: time.sleep(0.3)` and asserts `elapsed >= 0.25` and `ticks >= 5` where the ticker increments every 10ms (lines 26-67).; test_scan_inspect_offloads_blocking_docker_call repeats the same pattern with a 0.3s inspect_container sleep and identical elapsed/tick thresholds (lines 70-127).; Tick counts depend on OS scheduling of both the ticker task and the worker thread; a loaded CI runner can starve either side and flip the result without any production regression.
  - Impact: Intermittent false failures (or false passes if the loop is blocked but the ticker still ran before/after) erode trust in the one suite guarding the 'blocking Docker SDK must not stall the event loop' contract.
  - Fix: Replace wall-clock thresholds with deterministic synchronization: have the blocking stub signal an event from the worker thread and assert the ticker coroutine completes a rendezvous (or count loop iterations via asyncio.sleep(0) yields) while the stub is provably still blocked.

- [Medium][90] tests/unit/test_api_runtime_coordinator.py:266-313 — Coordinator tests synchronize with fixed-sleep polling loops (300 x 10ms) and bare sleeps instead of awaiting observable conditions
  - ID: f_tests_unit_supervisor_runtime_03; verification: static
  - Evidence: test_reconcile_loop_keeps_retrying_until_convergence and test_reconcile_loop_respects_explicit_retry_cap poll `for _ in range(300): await asyncio.sleep(0.01)` waiting for attempts/_active_tasks changes (lines 278-285, 313-320).; Same pattern in tests/unit/test_runtime_coordinator_stop_paths.py:220-224 and tests/unit/test_runtime_coordinator_background_tasks.py:48-51 (100 x 0.01s).; test_coordinator_disabled_when_unconfigured (test_api_runtime_coordinator.py:40-45) fires trigger_reconcile, sleeps a bare 0.05s, then asserts the error was recorded — a pure race.; tests/unit/test_baseline_fixture_regressions.py:1197-1207 asserts a WebSocket survived by sleeping 0.05s twice and checking ws.closed, so a slow crash handler can pass unnoticed.
  - Impact: Tests become duration-dependent: slow CI makes them time out at arbitrary iteration counts, fast machines can finish the loop before the background task even starts (masking regressions), and the disabled-coordinator test can flake either way.
  - Fix: Await the actual condition with asyncio.wait_for on an Event/future set by the mock handler or by a task done-callback, rather than counting sleeps; for the disabled case, expose/await the reconcile task handle returned internally.

- [Medium][92] tests/unit/test_runtime_coordinator_stop_paths.py:260-360 — Large parts of the suite assert on and mutate private implementation state and replace the system-under-test's own methods, coupling tests to internals rather than behavior
  - ID: f_tests_unit_supervisor_runtime_04; verification: static
  - Evidence: Stop-path tests set `coordinator._running = True` (lines 260, 304, 346) and call the private `coordinator._reconcile_profile_loop` directly instead of start()/trigger_reconcile.; test_api_runtime_coordinator.py:313-320 asserts membership in private `coord._active_tasks`; test_runtime_coordinator_background_tasks.py:44-66 asserts on private `_publish_tasks` and replaces the coordinator's own `publish_profile_change` method on the instance.; test_runtime_coordinator_stop_paths.py:205-218 replaces `coordinator.reconcile_profile_now` (a method of the SUT class) with a flaky stub to test the loop's exception handling.; Recovery tests seed and assert private state throughout: coordinator._in_flight_tasks, _cleanup_failures, _cleanup_cooldown_until, _reported_dead_instances (test_supervisor_recovery_coordinator.py, test_recovery_authority.py:84-90 seeds _cleanup_failures["p1"] = 3).; Supervisor tests pervasively seed `core._sessions[...]` and replace `core._query_agent_health` on the instance (test_supervisor_normal_exit_observation.py, test_supervisor_stop_fence.py:30, test_resource_fault_isolation.py:29-30 assigns core.resource_monitor).; RecoveryCoordinator tests drive api.get through positionally-ordered side_effect lists whose comments enumerate tick()'s internal call sequence ('1st get in tick()', '2nd get after the observation report', test_supervisor_startup_recovery.py:80-109), so any internal reordering of fetches breaks tests without a behavior change.
  - Impact: Refactors that preserve behavior (renaming internals, changing task bookkeeping, reordering fetches) break dozens of tests, while behavior regressions that keep the same internal shape can pass; the suite's signal about observable contracts is diluted.
  - Fix: Where a public seam exists, drive it (start/trigger_reconcile/stop, HTTP transports, repository state) and assert on outcomes (get_last_error, persisted runtime rows, emitted requests); where no seam exists, treat that as a design note for the production class rather than reaching into privates from tests.

- [Low][97] tests/unit/test_supervisor_core.py:1-9 — Module docstring claims retry-policy (AC-005) and event-forwarder spooling (AC-004) tests that do not exist in the file
  - ID: f_tests_unit_supervisor_runtime_05; verification: static
  - Evidence: Header lists four test areas, including '3. Retry policy 2/10/30 backoff and 3-strikes blocking (AC-005)' and '4. Event forwarder offline spooling and recovery deduplication (AC-004)'.; The entire 73-line file contains only test_path_validator_symlink_and_traversal and test_port_allocator_exhaustion_and_reuse; no retry, backoff, or forwarder test exists in it.; The claimed behaviors are covered elsewhere in the unit (recovery coordinator tests, test_supervisor_event_delivery.py), so the gap is false attribution in this file rather than a total coverage hole.
  - Impact: Coverage audits or reviewers trusting the header will believe AC-004/AC-005 are pinned by this file; if the sibling files are moved or renamed, the claimed coverage silently disappears.
  - Fix: Trim the docstring to the two areas actually tested here, or move the retry/forwarder tests into this file.

- [Low][95] tests/unit/test_supervisor_normal_exit_observation.py:600-601 — Three tests create scratch state under the pytest CWD inside the repository (.scratch/normal_exit_fix) instead of using tmp_path
  - ID: f_tests_unit_supervisor_runtime_06; verification: static
  - Evidence: Lines 600, 917, and 999 build `data_root = (Path(".scratch/normal_exit_fix") / f"u_{secrets.token_hex(3)}").resolve()` and mkdir it; cleanup is shutil.rmtree in finally.; All other tests in the same file use tmp_path; the UDS test additionally derives a relative socket path from os.getcwd() (lines 625-627), tying correctness to the invocation directory.; .gitignore does list `.scratch/`, so artifacts are not committed, but a killed test run leaves state in the working tree and parallel/xdist runs share the same parent directory.
  - Impact: Working-tree pollution, CWD-dependent behavior, and potential interference with repo tooling/scans that walk the tree; failures are confusing because state lives outside the usual tmp fixtures.
  - Fix: Use tmp_path (or tmp_path_factory) for these three tests like the rest of the file; if a short UDS path is the real constraint, create the socket under tmp_path with a short name.

- [Low][70] tests/unit/test_supervisor_event_cursor.py:33-45 — Test helper returns a SupervisorCore whose httpx API client has already been closed by the exiting `async with` block
  - ID: f_tests_unit_supervisor_runtime_07; verification: suspected
  - Evidence: _core() constructs SupervisorCore inside `async with httpx.AsyncClient(...) as api:` and returns it after the block exits (lines 37-44), so core.api is a closed client for every subsequent consume_disk_events() call.; The tests pass only insofar as the exercised journal path uses the AsyncMock EventForwarder and never the real client; test_old_normal_exit_cannot_remove_new_local_runtime in the sibling file shows consume paths can involve API delivery.; The 'restarted supervisor' leg of test_cursor_processes_each_journal_once_and_archives builds a second core the same way, doubling the latent trap.
  - Impact: Any future change that makes consume_disk_events use core.api on these paths fails with httpx's misleading 'client has been closed' error, and the helper teaches a broken construction pattern to future tests.
  - Fix: Keep the client alive for the test's lifetime (create it without the context manager and aclose it in the test's finally, or construct the core inside the test body).

- [Low][93] tests/unit/test_baseline_fixture_regressions.py:20-27 — Import-time sys.path mutation and cross-test-module coupling pollute the whole pytest session
  - ID: f_tests_unit_supervisor_runtime_08; verification: static
  - Evidence: Module import executes `sys.path.insert(0, p)` for REPO_ROOT and tests/fixtures (lines 24-27), permanently changing import resolution for every other test module collected in the session.; The same file loads tests/e2e/test_supervisor_recovery_e2e.py via importlib and manually drives its `real_api_and_sup` fixture generator through `__wrapped__` (lines 1063-1120), coupling a unit test to an e2e test module's internals.; test_runtime_event_policy.py:11-12 similarly imports fixtures from the sibling test module test_domain_and_repository, which works only because pytest prepends the test directory to sys.path (no __init__.py/conftest in tests/unit).
  - Impact: Import order across the suite becomes load-bearing: renaming a fixture module, adding a same-named module, or running a subset can change what other tests import, producing failures unrelated to the change under review.
  - Fix: Move shared fixtures into tests/unit/conftest.py or a non-test helper package imported normally, and drop the sys.path inserts and the e2e-module fixture driving.

- [Low][90] tests/unit/test_supervisor_startup_recovery.py:63-64 — Test docstring claims a '2s backoff' that no assertion in the file verifies
  - ID: f_tests_unit_supervisor_runtime_09; verification: static
  - Evidence: test_missing_runtime_reports_error_observation_once docstring: 'Missing runtime reports one authoritative error observation with 2s backoff.'; The test asserts report_terminal_observation was awaited once with reason='missing_runtime', emit_event was not called, and the instance is in _reported_dead_instances; nothing measures or asserts any delay/backoff value.; No other test in the file asserts timing either, so the claimed backoff contract is untested while appearing covered.
  - Impact: A regression removing or changing the retry backoff would pass this suite while the docstring continues to claim the behavior is locked down.
  - Fix: Either assert the scheduled delay/cooldown state the coordinator records for the retry, or remove the backoff claim from the docstring.

- [Low][65] tests/unit/test_runtime_persistence_guards.py:131-147 — Write-denial fault injection via chmod 0o500 silently stops injecting when the suite runs as root
  - ID: f_tests_unit_supervisor_runtime_10; verification: suspected
  - Evidence: test_terminal_storage_failure_propagates_instead_of_reporting_saved chmods the runtime events directory to 0o500 and expects runner._wait_for_chrome_exit to raise StorageError (lines 141-146).; Root ignores directory write-permission bits, so under a root-run container the save succeeds, no StorageError is raised, and the test fails (or, worse, would be 'fixed' by weakening it).; Other permission tests in the unit assert resulting file modes (0o600/0o750), which hold regardless of uid; only this denial-based injection is uid-sensitive. No skipif guard for euid==0 exists in the file.
  - Impact: The durability-failure contract (terminal event save failure must propagate) loses its only test in root-run environments, which are common for this Docker-centric project's CI.
  - Fix: Inject the failure by monkeypatching the storage write (as the same file already does for os.fsync) or skip when os.geteuid() == 0 with an explicit reason.

- [Low][92] tests/unit/test_runtime_protocol.py:19-33 — Schema validity test uses a CWD-relative path and existence-only assertions, duplicating the stronger byte-identity export test
  - ID: f_tests_unit_supervisor_runtime_11; verification: static
  - Evidence: test_schema_json_file_validity opens Path("schemas/runtime/agent_protocol.json") relative to the process CWD (line 23), unlike sibling tests that anchor at Path(__file__).resolve().parents[2] (test_runtime_agent_protocol_export.py:10, test_supervisor_schema.py:12).; Its assertions stop at file existence, title, and presence of six $defs keys — all strictly weaker than test_runtime_agent_protocol_export.py's byte-identical comparison of the generated schema against the checked-in file.
  - Impact: Running pytest from any directory other than the repo root fails this test spuriously; and the weak assertions add maintenance surface without adding contract protection beyond the export test.
  - Fix: Anchor the path at the repo root like the sibling tests, or delete this test in favor of the byte-identity export test.

- [Low][95] tests/unit/test_baseline_fixture_regressions.py:44-620 — Fixture regression tests repeat the same ~15-line token-file and image-env setup in nearly every test instead of sharing a fixture
  - ID: f_tests_unit_supervisor_runtime_12; verification: static
  - Evidence: The identical block (write sup_token/gw_token/agent_key with secrets.token_hex(32), chmod 0o600, _set_test_images_env) is copy-pasted into at least eight tests (e.g. lines 52-64, 115-127, 178-190, 240-252, 316-328, 380-392, 442-454, 505-517).; The same pattern repeats across the unit: the BROWSER/STREAM digest constants and _adapter() factory are re-declared in test_supervisor_adapter_paths.py, test_supervisor_display_config.py, test_supervisor_file_permissions.py, test_supervisor_selkies_tokens.py, and test_supervisor_selkies_token_isolation.py with slight variations.; RealApiProcess token setup is likewise repeated four times within the same file (lines ~1004-1013, 1050-1059, 1097-1106, 1150-1159).
  - Impact: A change to the fixture contract (e.g. an additional required key file) must be edited in a dozen places; divergent copies are already visible (some tests write token_urlsafe, others token_hex), increasing the chance a test exercises a subtly different setup than intended.
  - Fix: Extract a shared fixture/helper (per-file fixture or tests/unit/conftest.py) that provisions the three key files and image env, and a single adapter factory for the supervisor tests.

## views

```json
{
  "contracts": {
    "reviewer": "1e87906a-b5d1-47a7-9394-f08cf272260c",
    "status": "completed"
  },
  "correctness": {
    "reviewer": "1e87906a-b5d1-47a7-9394-f08cf272260c",
    "status": "completed"
  },
  "design": {
    "reviewer": "1e87906a-b5d1-47a7-9394-f08cf272260c",
    "status": "completed"
  },
  "documentation": {
    "reviewer": "1e87906a-b5d1-47a7-9394-f08cf272260c",
    "status": "completed"
  },
  "performance": {
    "reviewer": "1e87906a-b5d1-47a7-9394-f08cf272260c",
    "status": "completed"
  },
  "robustness": {
    "reviewer": "1e87906a-b5d1-47a7-9394-f08cf272260c",
    "status": "completed"
  },
  "security": {
    "reviewer": "1e87906a-b5d1-47a7-9394-f08cf272260c",
    "status": "completed"
  },
  "tests": {
    "reviewer": "1e87906a-b5d1-47a7-9394-f08cf272260c",
    "status": "completed"
  }
}
```

## files_reviewed

```json
[
  "tests/unit/test_api_runtime_coordinator.py",
  "tests/unit/test_baseline_fixture_regressions.py",
  "tests/unit/test_baseline_runtime_regressions.py",
  "tests/unit/test_browser_readiness_fence.py",
  "tests/unit/test_docker_offload.py",
  "tests/unit/test_domain_and_repository.py",
  "tests/unit/test_exit_reason_allowlist.py",
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
