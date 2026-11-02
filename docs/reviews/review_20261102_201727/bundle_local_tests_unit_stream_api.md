# bundle_local_tests_unit_stream_api

## responsibilities

- Unit-test coverage for the stream/api/auth/gateway domain: StreamAgent lifecycle, registration, heartbeat, reconnect backoff, RTC config push and ICE restart; gateway config/endpoint/registry/rotation; RTC config and TURN HMAC credential generation; auth client-IP resolution, login rate limiting, admin/session/automation-token services and auth DB models; artifact store/service (quota, MIME, atomic publish, download ingest, reconciliation forwarding); profile copy/reset semantics in ProfileService; secret-file permission enforcement; Selkies entrypoint/container-spec policy pinning (file transfers, clipboard, dual mode).
- Most tests exercise real production objects (real SQLite DBs via migrations, real aiohttp WebSocket servers on loopback, real pydantic models) and assert behavior-observable outcomes (stored rows, forwarded HTTP payloads, wire envelopes, file contents); mocks are mostly confined to boundaries (upstream Selkies WS, gateway WS, HTTP MockTransport, pipeline doubles).

## interfaces

- Production entry points driven directly: StreamAgent.connect_and_run/_handle_control_packet/_handle_tunnel_packet/_viewer_upstream_worker/_upstream_reader/_detach_viewer, LiveCapturePolicyAgent.reconcile_capture_state, RotationCoordinator.handle_agent_restart_offer/cancel_profile, AgentRegistry/RegistrationThrottle, RtcConfigService.generate_generation/should_generate_next/should_trigger_restart/is_expired, generate_turn_credentials, AuthService public methods, ArtifactService.upload/ingest_download, ProfileService.duplicate_profile/reset_profile, GatewayConfig.from_env, StreamAgentConfig.from_env, read_secret_file/read_supervisor_token/read_gateway_token, validate_ice_servers, scan_completed_downloads, DownloadArtifactForwarder.forward_pending, create_control_app (supervisor control surface).
- Wire/schema contracts pinned: schemas/stream/agent_protocol.json compared byte-wise (as parsed JSON) against scripts/export_stream_protocol.py output; pydantic strictness (extra=forbid, strict bool, SecretStr masking) asserted across protocol/config models.

## dependencies

- pytest + pytest-asyncio markers, aiohttp test servers on 127.0.0.1, fastapi TestClient, httpx ASGITransport/MockTransport, SQLAlchemy async sessions on tmp SQLite files, jsonschema Draft202012Validator.
- Production packages under src/backend/cbrowser/{stream_agent,gateway,rtc_config,api,auth,services,adapters,supervisor,runtime_agent} and src/backend/cbrowser/secret_files.py; repo-tree files config/docker/stream_runtime/entrypoint.sh read by three tests.
- Module-global mutable state in cbrowser.stream_agent.ice_transport (_RELAY_ONLY) is shared between production control handling and tests (see finding f_tests_unit_stream_api_01).

## flows

- Agent registration/heartbeat/reconnect flows are tested end-to-end against an in-process mock gateway (test_stream_agent_lifecycle.py), including rejection-driven backoff captured via an injected _sleep_fn instead of real waiting.
- Download flow: CDP completion event -> EventStorage -> supervisor DownloadArtifactForwarder (path translation, once-only forwarding, retry after 401) -> ArtifactService ingest (checksum verify, dedupe by path, partial-file skip, DB-failure rollback).
- Profile copy/reset flows run against a real migrated DB plus a real tmp profile directory, covering singleton-symlink exclusion, manifest verification, operation-id idempotency/conflict, concurrent same-key operations, and rollback on DB failure.

## constraints

- Static review only: no test was executed; pass/fail statements below rest on source reading and cross-checks against production code at HEAD 5136766.
- Cross-checks performed: AgentRegistry.update_heartbeat signature (session id optional, registry.py:55-67) matches both call shapes used; LoginRateLimiter uses time.time() (rate_limiter.py:50,66,80) so the monkeypatched clock in test_auth_client_ip.py genuinely drives it; AuthService default limiter is max_failures=5/window 60s (service.py:38-39), matching the 5-failures-then-limited expectation in test_auth_service.py; ice_transport._RELAY_ONLY is a module global (ice_transport.py:58-68) also mutated by StreamAgent control handling (agent.py:768-770).
- No real secrets found in the unit: credentials are generated with secrets.* or are obvious dummies/canaries; TURN HMAC test recomputes the RFC-style MAC independently rather than copying production code.

## decisions

- Zero Critical/High findings: the suite is predominantly behavior-level with real infrastructure; the defects found are test-validity, isolation and documentation issues, not evidence of broken production behavior.
- Negative assertions that depend on fixed sleeps are rated Medium (not Low) because two of them guard security-relevant invariants (invalid rtc_config must not mutate active config; forged visibility must not register a viewer) and can pass vacuously if the packet is not yet processed.

## evidence

- tests/unit/test_stream_ice_transport.py:155-161 sets process-global relay-only flag without isolation; src/backend/cbrowser/stream_agent/ice_transport.py:58-68 defines the global; src/backend/cbrowser/stream_agent/agent.py:768-770 mutates it from the control path
- tests/unit/test_stream_ice_transport.py:1-16 module docstring promises UDP-mux/port-range and two-peer generation-switch tests that do not exist in the file (file contains only validation, ABI guard, diagnostics and relay-flag tests)
- tests/unit/test_stream_agent_lifecycle.py:540,575,864,890 fixed asyncio.sleep(0.1) before state assertions, including the invalid-rtc_config non-mutation assertion
- tests/unit/test_automation_cdp.py:54-58 CWD-relative .scratch root with shutil.rmtree of a suffix-keyed shared parent
- tests/unit/test_profile_copy_reset.py:270-271 asserts world-writable bits on cloned profile dir and Cookies file
- tests/unit/test_control_error_redaction.py:33,40 redaction checked only at WARNING+ log level and against a two-value status set
- tests/unit/test_stream_protocol_schema.py:14-22 generator-vs-checked-in-schema equality (positive example of drift pinning)
- tests/unit/test_auth_service.py:93-113 and src/backend/cbrowser/auth/service.py:38-39 default limiter alignment verified

## uncertainties

- Whether pytest is run with xdist parallelism in CI is not visible from this unit; the shared-state and fixed-port findings assume parallel or repeated runs are possible (CI config is another unit's scope).
- The world-writable profile-copy permission (f_tests_unit_stream_api_07) may be a deliberate spec decision for cross-uid runtime access; the blueprint/spec text governing it was outside this unit, so it is recorded as a test-side lock-in concern, not a production defect claim.
- Timing tolerances in capture-policy tests (real sleeps of 0.1-0.15s against monotonic damage/cooldown math in policy.py) were assessed statically; actual flake rates require execution data this review did not produce.

## Findings

- [Medium][90] tests/unit/test_stream_ice_transport.py:155-161 — Test mutates the process-global ICE relay-only flag without isolation, polluting other tests
  - ID: f_tests_unit_stream_api_01; verification: static
  - Evidence: test_relay_only_policy_flag calls set_relay_only(True) then set_relay_only(False) with plain asserts in between and no fixture/finally restore; an assertion failure or interruption leaves the flag True for the rest of the process.; src/backend/cbrowser/stream_agent/ice_transport.py:58-68: _RELAY_ONLY is a module-level global; set_relay_only mutates it for all subsequent PeerConnection creation in the process.; src/backend/cbrowser/stream_agent/agent.py:768-770: the production control path also calls set_relay_only, and tests/unit/test_stream_agent_lifecycle.py (test_agent_rtc_config_relay_only_intent) asserts on the same global is_relay_only() after driving a real agent, so the flag's value depends on cross-file test execution order.
  - Impact: Order-dependent, hard-to-diagnose failures or silent behavior changes in unrelated stream tests (e.g. transports created with relay-only gatherer wrapping) when tests are reordered, selected individually after a failure, or parallelised; a leaked True also changes what later tests actually exercise.
  - Fix: Wrap the flag in an autouse fixture that snapshots and restores _RELAY_ONLY around each test in both files (or expose a context manager in ice_transport and use it); in test_relay_only_policy_flag, restore in a finally block.

- [Medium][95] tests/unit/test_stream_ice_transport.py:1-16 — Module docstring claims UDP-mux/generation-continuity coverage that the file does not contain
  - ID: f_tests_unit_stream_api_02; verification: static
  - Evidence: Docstring items 3 and 4 promise 'Profile UDP mux and port range preservation across generations' and a 'Two-peer in-process WebRTC restart generation switch (same PC/DTLS/SCTP, continuity of DataChannel, rejection of retired connection writes)'.; The file's actual tests cover only: ice server validation types/schemes, ABI guard (version/missing SDK/missing private attributes), restart-offer transport type check, diagnostics sanitization, and the relay-only flag; no test touches UDP mux ports, port ranges, generation switching, or DataChannel continuity.
  - Impact: Coverage traceability is false: readers and acceptance reviews can believe ICE generation continuity and mux-port preservation are unit-verified when they are only exercised (if at all) by Docker e2e probes in other units; a regression in generation switching would not be caught here despite the claim.
  - Fix: Either add the promised tests (or explicit pytest.mark.skip placeholders with a pointer to the e2e files that own the coverage) or rewrite the docstring to describe only what the file verifies and reference where generation/mux behavior is covered.

- [Medium][85] tests/unit/test_stream_agent_lifecycle.py:532-578 — Security-relevant negative assertions rely on fixed 0.1s sleeps and can pass without the packet being processed
  - ID: f_tests_unit_stream_api_03; verification: static
  - Evidence: test_agent_rtc_config_push_and_ice_restart sends an invalid rtc_config envelope, sleeps a fixed asyncio.sleep(0.1) (lines 540, 575 pattern), then asserts agent.active_rtc_config.generation is unchanged; if the agent's message pump has not processed the envelope within 100ms under load, the assertion passes vacuously.; test_agent_rtc_config_relay_only_intent repeats the pattern at lines 864 and 890 before asserting relay_only state flips.; The same idiom appears in tests/unit/test_stream_transport_hardening.py (asyncio.sleep(0.05) after sending a forged visibility_update, then asserting the ghost viewer is absent from agent.policy.peers): absence after a fixed delay does not prove the packet was handled and rejected.
  - Impact: The tests that guard 'invalid control input must not mutate agent state' can go green while never exercising the rejection path, so a production regression that accepts invalid rtc_config or forged visibility could ship undetected; conversely the positive assertions after the same sleeps are flake-prone under CI load.
  - Fix: Replace fixed sleeps with condition waits (poll for a processed-message counter/ack, or send a subsequent valid sentinel envelope and assert ordering), so the negative assertion is made only after the invalid packet is known to have been handled.

- [Medium][75] tests/unit/test_automation_cdp.py:54-58 — UDS test root is CWD-relative, suffix-keyed and rmtree'd, risking cross-test deletion and repo-tree state
  - ID: f_tests_unit_stream_api_04; verification: static
  - Evidence: _short_root builds Path('.scratch/t008_uds') / tmp_path.name[-8:] / 'data' relative to the process CWD and calls shutil.rmtree(root.parent, ignore_errors=True) before use.; The key is only the last 8 characters of the pytest tmp dir name, so two different tests (or parallel xdist workers) whose tmp names share a suffix map to the same directory, and each setup recursively deletes the other's live socket tree.; The path depends on pytest being launched from the repo root; from another CWD the sockets land in a different .scratch tree, and state is left inside the working tree rather than tmp_path.
  - Impact: Flaky WebSocket CDP tests under parallel execution (socket deleted mid-test), irreproducible failures when the suite is invoked from a different directory, and hidden inter-test coupling through the filesystem.
  - Fix: Derive the short root from a collision-proof unique component (e.g. tempfile.mkdtemp under /tmp with the test's full node id hashed) and remove only the test's own leaf directory; do not rmtree a shared parent.

- [Low][90] tests/unit/test_stream_agent_lifecycle.py:623-637 — Selkies-version test's assertions are environment-conditional, so its core claim is untested in one of the two environments
  - ID: f_tests_unit_stream_api_05; verification: static
  - Evidence: test_selkies_version_comes_only_from_installed_distribution branches on whether the selkies distribution is installed: if absent it only asserts resolve_selkies_version() raises RuntimeError; if present it asserts equality with the installed version.; In an environment without selkies (typical unit-test CI), the raise happens regardless of the CBROWSER_SELKIES_VERSION=9.9.9 env var, so the stated claim 'an environment string must not misreport the running Selkies' is never actually exercised against an installed distribution.
  - Impact: A regression letting the env var override the installed version would pass the suite in the no-Selkies environment, which is exactly where this unit suite runs; the test gives false confidence in version-pinning.
  - Fix: Stub importlib.metadata.version (monkeypatch) to a fixed installed version and assert the env var is ignored deterministically in both branches, keeping a separate small test for the not-installed raise.

- [Low][90] tests/unit/test_stream_binding_guards.py:110-122 — Pervasive assertions on private internals couple tests to implementation shape rather than observable behavior
  - ID: f_tests_unit_stream_api_06; verification: static
  - Evidence: test_stream_binding_guards.py asserts policy._supervisor_fps_cap before/after control packets (lines 117-122) and agent.conn_id_to_sdk_peer_id contents, instead of the externally visible capture behavior.; test_stream_capture_policy.py asserts agent._is_paused (lines 116, 132), agent._supervisor_fps_cap (lines 222-224) and agent._loop_task/_motion_task identity (lines 333-337), duplicating pipeline state it already observes via the mock pipeline.; tests/unit/test_profile_copy_reset.py repeatedly reaches into repo._session_maker (e.g. lines 88-91 and passim) to build ArtifactRepository, and test_gateway_rotation_guards.py seeds coordinator._pending_offers/_pending_answers directly.
  - Impact: Internal refactors that preserve behavior (renaming a private field, changing task bookkeeping) break many tests, discouraging cleanup; conversely a private field can hold the expected value while the observable behavior is wrong, weakening the suite as a behavior contract.
  - Fix: Where an observable surface exists (pipeline framerate/capturing state, forwarded envelopes, registry lookups, service return values), assert on it and drop the private-state assert; where no surface exists, treat the missing observability as a production API gap rather than normalising private access.

- [Low][80] tests/unit/test_profile_copy_reset.py:264-271 — Test locks in world-writable permissions on cloned browser profile state including Cookies
  - ID: f_tests_unit_stream_api_07; verification: static
  - Evidence: test_copy_permissions_are_readable_and_writable_for_runtime asserts clone_dir mode & 0o002 and (clone_dir / 'Cookies') mode & 0o002, i.e. the suite mandates other-writable permission bits on a directory tree containing session cookies.; The companion artifact check (tests/unit/test_artifact_service.py, test_uploaded_file_is_readable_by_runtime_user) asserts only bitmask presence (file & 0o040, dir & 0o050), which would also pass for an over-broad 0o777 mode.
  - Impact: If the runtime uid/gid separation assumption changes, the tests still demand world-writable cookie state, blocking a permission tightening and normalising an over-broad mode; bitmask-presence asserts cannot detect accidental widening to 0o777.
  - Fix: Assert the exact intended mode (or an upper bound, e.g. mode & ~0o002 == 0 for state files) and tie the exception, if any, to the specific runtime group rather than 'other'; record the governing spec reference in the test name/docstring.

- [Low][85] tests/unit/test_secret_file_permissions.py:36 — Positive token-read assertion checks only non-None, not the token value
  - ID: f_tests_unit_stream_api_08; verification: static
  - Evidence: test_internal_tokens_reject_group_readable_files ends with assert read_supervisor_token(_secret(tmp_path / 'sup_ok', 0o600)) is not None, although _secret wrote the known value 'a'*32.; A regression returning an empty string or a constant placeholder from read_supervisor_token would satisfy 'is not None' and pass.
  - Impact: The happy path of a credential-loading function is verified only for existence, so value-corruption regressions (trimming, wrong file, placeholder) escape this test.
  - Fix: Assert equality with the written secret value ('a' * 32), mirroring the exact-value assertion already used for read_secret_file in the same file (line 27).

- [Low][85] tests/unit/test_api_models_and_sse.py:63-82 — SSE broadcaster test asserts substrings instead of parsing the emitted frame
  - ID: f_tests_unit_stream_api_09; verification: static
  - Evidence: test_sse_broadcaster_initial_snapshot checks only 'event: runtime_state' in first_chunk and 'p_snap' in first_chunk.; It never parses the data: line as JSON nor checks the event payload fields, so a frame with malformed JSON, missing fields, or the profile id appearing in the wrong place would still pass.
  - Impact: Wire-format regressions in the SSE snapshot (the exact contract the frontend consumes) can pass while the event name and an id substring remain present.
  - Fix: Split the chunk into event/data lines, json-parse the data payload, and assert the snapshot event's profile_id, desired_state and observed_state fields exactly.

- [Low][90] tests/unit/test_selkies_file_transfers.py:31-34 — Entrypoint-content tests use CWD-relative paths while a sibling test anchors to __file__
  - ID: f_tests_unit_stream_api_10; verification: static
  - Evidence: test_selkies_file_transfers.py:31 and tests/unit/test_stream_selkies_tokens.py:257 read Path('config/docker/stream_runtime/entrypoint.sh') relative to the process CWD.; tests/unit/test_stream_clipboard_policy.py:38-41 reads the same file via Path(__file__).resolve().parents[2] / 'config/...', proving the anchored pattern exists in the same suite.
  - Impact: Running pytest from src/backend, an IDE root, or any non-repo-root CWD makes the two relative-path tests fail with FileNotFoundError despite no code change, and can mask real entrypoint regressions in local runs.
  - Fix: Anchor both reads to Path(__file__).resolve().parents[2] like test_stream_clipboard_policy.py.

- [Low][80] tests/unit/test_control_error_redaction.py:33-40 — Redaction test inspects only WARNING-and-above logs and accepts two different status codes
  - ID: f_tests_unit_stream_api_11; verification: static
  - Evidence: caplog.at_level(logging.WARNING) means records below WARNING are not captured for the canary check; a production change logging the upstream exception at DEBUG or INFO would leak the canary without failing this test.; assert response.status_code in (500, 502) leaves the externally visible error contract ambiguous; the test does not pin which failure mode yields which code.
  - Impact: The log-redaction guarantee is verified only for the log levels the current implementation happens to use, and the response contract can drift between 500 and 502 unnoticed.
  - Fix: Capture at DEBUG level (caplog.at_level(logging.DEBUG)) for the canary assertion, and assert the specific expected status per action once the production mapping is fixed, or document why both codes are contractual.

- [Low][85] tests/unit/test_stream_transport_hardening.py:321-335 — Real-WebSocket test binds a hardcoded port 18491 instead of an ephemeral one
  - ID: f_tests_unit_stream_api_12; verification: static
  - Evidence: test_real_ws_gateway_and_worker_generation binds web.TCPSite to 127.0.0.1:18491 and hardcodes the same port in gateway_url and upstream_url.; The sibling suite (test_stream_agent_lifecycle.py) already has a unique_port fixture that binds port 0, showing the ephemeral pattern is available.
  - Impact: Parallel test workers, a leftover process, or any local service on 18491 makes the test fail at bind time or, worse, connect to a foreign server; failures are environmental and erode trust in the suite.
  - Fix: Bind port 0 and read back the assigned port from the site/server sockets (as FakeSelkies in test_stream_resume.py does), interpolating it into the config URLs.

- [Low][70] tests/unit/test_refactor_behavior_equivalence.py:99-108 — Retry-timing assertions use tight wall-clock tolerances that can flake under load
  - ID: f_tests_unit_stream_api_13; verification: static
  - Evidence: test_recovery_schedule_predicates computes remaining_retry_seconds from datetime.now(UTC) timestamps and asserts 4.9 < remaining <= 5.0 and 14.9 < remaining <= 15.0, leaving only 100ms of slack for scheduling delay between timestamp creation and the call.; remaining_retry_seconds itself reads the wall clock internally (production recovery_rules), so a >100ms stall on a loaded CI runner flips the lower bound.
  - Impact: Intermittent failures in a pure-function equivalence test, training developers to ignore red runs in exactly the file meant to pin refactor safety.
  - Fix: Widen tolerances (e.g. 4.5 < remaining <= 5.0) or freeze time by injecting/mocking the clock used by remaining_retry_seconds.

- [Info][95] tests/unit/test_rtc_config.py:55-64 — Duplicated assertion: steps 3 and 4 assert the same credential inequality
  - ID: f_tests_unit_stream_api_14; verification: static
  - Evidence: Step 3 asserts client_user != stream_user and client_cred != stream_cred; step 4 ('Cross-role mismatch is detectable from the HMAC itself') repeats exactly client_cred != stream_cred without testing an actual cross-role verification (e.g. validating the client credential against the stream username).; The HMAC recomputation in steps 1-2 already pins the credential construction independently, so step 4 adds no coverage.
  - Impact: Minor: inflates the apparent coverage of cross-role confusion resistance; a reader may believe role-confusion rejection is tested when only inequality of two MACs is shown.
  - Fix: Replace step 4 with an assertion that the client credential does not equal base64(HMAC(secret, stream_user)) computed for the wrong role binding, or delete the duplicate and keep the comment accurate.

- [Info][90] tests/unit/test_auth_models.py:1-27 — Test names/docstring claim migration-0002 scope but the helper runs the full migration chain
  - ID: f_tests_unit_stream_api_15; verification: static
  - Evidence: Module docstring: 'Unit tests for auth database models and migration 0002_auth'; test_migration_0002_creates_auth_tables calls run_database_migrations(db_file), which applies the whole migration chain, not 0002 in isolation.; The test therefore also passes if auth tables are created by a later migration, and would not isolate a broken 0002 upgrade path.
  - Impact: Minor traceability drift: migration-specific regressions (e.g. 0002 broken but compensated later) are not isolated despite the naming.
  - Fix: Rename to reflect full-chain migration coverage, or add a targeted test that upgrades to 0002 explicitly if per-migration isolation is a project requirement.

- [Info][95] tests/unit/test_stream_resume.py:201-202 — Duplicated assignment line in test_detached_session_expires_after_grace
  - ID: f_tests_unit_stream_api_16; verification: static
  - Evidence: Lines 201-202 contain agent.agent_session_id = 'sess_test' twice in immediate succession, a copy-paste residue also diverging from the single assignment used in the sibling tests (lines 138, 171).
  - Impact: No behavioral effect; signals unreviewed duplication and slightly obscures the fixture setup.
  - Fix: Delete the duplicate line.

## views

```json
{
  "contracts": {
    "reviewer": "35487a81-8acc-438d-ac19-ac3570700664",
    "status": "completed"
  },
  "correctness": {
    "reviewer": "35487a81-8acc-438d-ac19-ac3570700664",
    "status": "completed"
  },
  "design": {
    "reviewer": "35487a81-8acc-438d-ac19-ac3570700664",
    "status": "completed"
  },
  "documentation": {
    "reviewer": "35487a81-8acc-438d-ac19-ac3570700664",
    "status": "completed"
  },
  "performance": {
    "reviewer": "35487a81-8acc-438d-ac19-ac3570700664",
    "status": "completed"
  },
  "robustness": {
    "reviewer": "35487a81-8acc-438d-ac19-ac3570700664",
    "status": "completed"
  },
  "security": {
    "reviewer": "35487a81-8acc-438d-ac19-ac3570700664",
    "status": "completed"
  },
  "tests": {
    "reviewer": "35487a81-8acc-438d-ac19-ac3570700664",
    "status": "completed"
  }
}
```

## files_reviewed

```json
[
  "tests/unit/test_api_models_and_sse.py",
  "tests/unit/test_artifact_service.py",
  "tests/unit/test_auth_client_ip.py",
  "tests/unit/test_auth_models.py",
  "tests/unit/test_auth_service.py",
  "tests/unit/test_automation_cdp.py",
  "tests/unit/test_control_error_redaction.py",
  "tests/unit/test_download_reconciler.py",
  "tests/unit/test_gateway_config.py",
  "tests/unit/test_gateway_endpoint.py",
  "tests/unit/test_gateway_registry.py",
  "tests/unit/test_gateway_rotation_guards.py",
  "tests/unit/test_profile_copy_reset.py",
  "tests/unit/test_refactor_behavior_equivalence.py",
  "tests/unit/test_rtc_config.py",
  "tests/unit/test_secret_file_permissions.py",
  "tests/unit/test_selkies_file_transfers.py",
  "tests/unit/test_stream_agent_lifecycle.py",
  "tests/unit/test_stream_agent_protocol_v2.py",
  "tests/unit/test_stream_binding_guards.py",
  "tests/unit/test_stream_capture_policy.py",
  "tests/unit/test_stream_clipboard_policy.py",
  "tests/unit/test_stream_display_config.py",
  "tests/unit/test_stream_ice_security.py",
  "tests/unit/test_stream_ice_transport.py",
  "tests/unit/test_stream_protocol_schema.py",
  "tests/unit/test_stream_resume.py",
  "tests/unit/test_stream_selkies_tokens.py",
  "tests/unit/test_stream_transport_hardening.py"
]
```
