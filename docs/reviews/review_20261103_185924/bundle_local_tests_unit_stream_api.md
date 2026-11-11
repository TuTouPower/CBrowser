# bundle_local_tests_unit_stream_api

## responsibilities

- Unit-tier pytest suite for the v2 service layer: API runtime models and the in-memory SSE broadcaster; artifact store/service (atomic publish, quotas, MIME allowlist, dedupe, reconciliation reasons); auth (trusted-proxy XFF resolution, two-layer login rate limiting, auth DB models/migration 0002, AuthService bootstrap/session/automation-token/viewer authorization); Supervisor automation CDP forwarding over the runtime agent UDS; control-plane error redaction; download scanning/CDP completion events and the Supervisor download-artifact forwarder (path translation, dead-lettering, retry); Gateway config/endpoint/registry (heartbeat liveness, registration throttle); ProfileService duplicate/reset semantics (idempotency keys, manifest verification, permission/ownership exactness, lock release); behavior-equivalence pins for modules extracted from the large coordinators (recovery rules, container/network/volume specs, stream messaging/policy helpers, runtime views); secret-file permission enforcement; Selkies transfer/clipboard/display policy via container spec env and the stream entrypoint script; StreamAgent lifecycle (registration, 10s heartbeat, 1/2/4/8/16/30 reconnect backoff), protocol v2 strictness, binding/generation guards, capture policy arbitration, session resume, controller-token loading/injection, transport hardening; vendored Selkies archive/manifest safety.
- The suite is predominantly behavior-first: most tests assert observable outcomes (stored bytes, DB rows, forwarded HTTP payloads, wire envelopes, file modes) against the real production classes, with mocks confined to system boundaries (httpx MockTransport, Docker-free seams, fake Selkies/Gateway servers on loopback).

## interfaces

- pytest fixtures: tmp_path-backed real SQLite databases via run_database_migrations + create_engine_and_maker; real loopback aiohttp servers (MockGatewayServer, FakeSelkies, mock upstream handlers); Starlette TestClient and httpx ASGITransport for the Supervisor control app; monkeypatch seams for clocks, os.chown/os.geteuid and repository failures.
- Deterministic time seams: ManualClock/\_ClockAsyncio replaces the agent module's asyncio reference in lifecycle tests; freezegun-style manual clocks are NOT used — two files instead patch the stdlib time module itself (see f_tests_unit_stream_api_02).
- Data-file coupling: several tests read repository artifacts as data — schemas/stream/agent_protocol.json (compared against scripts.export_stream_protocol.stream_protocol_schema()) and config/docker/stream_runtime/entrypoint.sh (asserted to contain AC-008/AC-010 directives and locked clipboard/file-transfer flags).

## dependencies

- Production packages under cbrowser.\* (api, auth, adapters.database, adapters.filesystem, domain, services, gateway, supervisor, runtime_agent, stream_agent) — those modules belong to other review units; this unit judges the tests, not the implementations.
- Repo-root scripts package: scripts.vendor_selkies_web (\_safe_relative_path, verify_manifest, extract_from_wheel) and scripts.export_stream_protocol — importing them requires the repo root on sys.path.
- Third-party: pytest/pytest-asyncio markers, pydantic, sqlalchemy, httpx, aiohttp, websockets, jsonschema (Draft202012Validator).

## flows

- Service tests: build real DB + repository/service on tmp_path -> drive public service methods -> assert on returned models, DB state, filesystem bytes/modes and lock idleness.
- Stream agent tests: start a fake Gateway (and fake Selkies upstream) on a loopback port -> run StreamAgent.connect_and_run as a task -> assert on envelopes the fake server received, agent session state and policy outcomes -> stop/cancel and gather.
- Forwarder tests: seed runtime-events JSON files and download payloads on disk -> run DownloadArtifactForwarder.forward_pending against an httpx MockTransport handler -> assert forwarded payload, once-only semantics and dead-letter directory contents.

## constraints

- Static review only: no test in this unit was executed for this review; pass/fail claims are limited to what the source proves.
- Several tests bind real loopback TCP ports and Unix sockets and create real files/DBs; they are unit-tier by location but integration-weight in cost and in environment assumptions (POSIX permission bits, AF_UNIX path length).
- Tests lean on exact production literals (close codes 4401/1013, env values like 'false|locked', retry delay sequence), so contract changes in the implementation units surface here first.

## decisions

- Prefer real collaborators over mocks for stateful behavior (real SQLite, real artifact store, real aiohttp servers); mocks are reserved for failure injection (DB failure restoring a download, chown denial, flaky Selkies state) and for the API side of the forwarder.
- Protocol contract is pinned at three independent levels — pydantic models (test_stream_agent_protocol_v2), exported JSON schema equivalence (test_stream_protocol_schema), and live wire traffic (test_stream_transport_hardening) — deliberate defense in depth rather than accidental duplication.
- Security-negative testing is explicit: redaction canary (test_control_error_redaction), audit logs asserted to never contain tokens or hashes (test_auth_service), traversal parametrizations for artifact ids, download sources and archive members, forged/stale tunnel envelopes asserted to leave no trace in policy state.
- All credential-looking values in the unit are synthetic: generated via secrets.token\_\* or obvious placeholders (e.g. 'valid_secret_123', a 'dummyhash' argon2-shaped string); no real-format live credential was found, and none is reproduced in this report.

## evidence

- tests/unit/test_artifact_service.py:52-588 (atomic publish, oversize cleanup, quota races via asyncio.gather, traversal parametrization, ownership/mode exactness)
- tests/unit/test_download_reconciler.py:147-434 (dead-letter taxonomy: unreadable/profile_mismatch/unsupported_version/path_escape; older-event ordering; retryable 401 then success)
- tests/unit/test_stream_agent_lifecycle.py:41-101 (ManualClock sleep seam), 288-713 (registration fields, heartbeat rhythm and state, backoff sequence and reset, supervised heartbeat restart)
- tests/unit/test_stream_transport_hardening.py:247-433 (real WS gateway proving generation-safe close gating and forged-envelope rejection)
- tests/unit/test_profile_copy_reset.py:44-565 (duplicate/reset idempotency, operation-key cross-action conflicts, manifest mismatch cleanup, symlink-safe ownership)
- tests/unit/test_auth_service.py:130-190 (audit details asserted free of token and hash after create and revoke)

## uncertainties

- pytest configuration (asyncio mode, rootdir/invocation directory, xdist usage) lives in packaging files outside this unit; whether the cwd-relative file reads in f_tests_unit_stream_api_01 actually bite depends on that configuration, which was not part of this unit.
- The SSE broadcaster's post-snapshot delivery may be covered by integration/e2e units outside this file set; f_tests_unit_stream_api_08 records the gap within this unit only.
- Whether GatewayConfig validates the agent key before the token files (the ordering assumption in f_tests_unit_stream_api_06) is a property of the gateway unit's implementation, not verifiable from this unit's files alone.

## Findings

- [Low][90] tests/unit/test_stream_selkies_tokens.py:253 — Entrypoint-content tests read config/docker/stream_runtime/entrypoint.sh via a cwd-relative path, unlike the __file__-anchored pattern used in the same unit

    - ID: f_tests_unit_stream_api_01; verification: static
    - Evidence: tests/unit/test_stream_selkies_tokens.py:253-254: entrypoint_path = Path("config/docker/stream_runtime/entrypoint.sh") — resolved against the pytest process working directory.; tests/unit/test_selkies_file_transfers.py:30 does the same relative read for the same file.; The sibling test in the same unit anchors correctly: tests/unit/test_stream_clipboard_policy.py:20-24 builds the path from Path(__file__).resolve().parents[2], and test_stream_protocol_schema.py:11 anchors its schema path the same way — so the unit is internally inconsistent.
    - Impact: These tests assert security-relevant entrypoint directives (file transfers disabled, dual mode off, master token file at 0600). Run from any working directory other than the repo root (IDE runner, subdirectory invocation, changed rootdir), they error with FileNotFoundError unrelated to the code under test; run from a different checkout's root they would silently validate the wrong tree's entrypoint.
    - Fix: Anchor both reads the way test_stream_clipboard_policy.py already does: Path(__file__).resolve().parents[2] / "config/docker/stream_runtime/entrypoint.sh".

- [Low][90] tests/unit/test_auth_client_ip.py:47 — Two files monkeypatch the stdlib time module itself (time.time / time.monotonic), so every in-process clock reader sees the fake clock during those tests

    - ID: f_tests_unit_stream_api_02; verification: static
    - Evidence: tests/unit/test_auth_client_ip.py:47: monkeypatch.setattr(time, "time", lambda: now[0]) patches the stdlib time module object imported at file top.; tests/unit/test_stream_capture_policy.py:156 and :181: monkeypatch.setattr(policy_module.time, "monotonic", ...) — policy_module.time is the same stdlib time module, so this freezes time.monotonic process-wide for the test's duration.; The lifecycle tests in the same unit demonstrate the contained alternative: \_ClockAsyncio replaces only the agent module's asyncio reference (test_stream_agent_lifecycle.py:83-101).
    - Impact: During these tests, any other code that consults time.time/time.monotonic — asyncio bookkeeping that looks the function up dynamically, logging, httpx/sqlalchemy internals, or future production code paths added to the objects under test — observes frozen/manual time. That makes outcomes sensitive to what else runs inside the test window and can mask real timing behavior; monkeypatch does restore the attribute afterwards, so the risk is intra-test coupling, not cross-test leakage.
    - Fix: Give LoginRateLimiter and the capture policy an injectable clock (or patch the consuming module's own namespace binding, e.g. cbrowser.auth.rate_limiter.time) instead of mutating the shared stdlib module object.

- [Low][95] tests/unit/test_stream_transport_hardening.py:303 — Real-WebSocket hardening test binds a hard-coded port 18491 instead of an ephemeral port

    - ID: f_tests_unit_stream_api_03; verification: static
    - Evidence: tests/unit/test_stream_transport_hardening.py:303 binds web.TCPSite(runner, "127.0.0.1", 18491); the same literal is baked into the config and upstream URLs at :310 and :315.; Sibling files avoid this: test_stream_agent_lifecycle.py's unique_port fixture binds port 0 to obtain a free port, and test_stream_resume.py's FakeSelkies binds port 0 and reads back the assigned port.
    - Impact: A leftover process from a previous run, a parallel xdist worker, or any other suite using 18491 makes this test fail with address-in-use — a spurious failure in the file that carries the protocol-hardening evidence. The failure mode is loud, so this is a flakiness/maintenance issue, not a silent-green one.
    - Fix: Bind port 0 and read the assigned port from the site (as FakeSelkies.start does), then format the gateway/upstream URLs from it.

- [Low][90] tests/unit/test_auth_service.py:192 — test_viewer_and_automation_authorize packs nine distinct authorization behaviors into one sequentially stateful test

    - ID: f_tests_unit_stream_api_04; verification: static
    - Evidence: tests/unit/test_auth_service.py:192-311 single test covers, in order: viewer authorization (valid/invalid origin, invalid session, missing profile), automation authorization, session-token-as-automation rejection, no-audit-on-unknown-token accounting, expired token, session expiry pruning, forged-token throttling (10 attempts then rate_limited), profile_unauthorized, token_revoked, and finally the authorize_denied audit-secret scan.; Later assertions depend on state created or destroyed by earlier ones in the same function (the automation token is revoked near the end; audit counts are taken mid-test), and the function also performs mid-body imports (from sqlalchemy import select at :252) duplicating the file's top-level imports.
    - Impact: A regression in any early behavior aborts the test and masks all later checks, so one failure hides the state of eight other security behaviors; when it fails, the failing behavior is hard to localize from the test name. The shared-state sequencing also means the checks cannot be run or reordered independently.
    - Fix: Split into focused tests (viewer authorize, automation authorize happy/denied paths, expiry, throttling, revocation, audit hygiene) sharing the auth_db fixture and small token/profile factory helpers.

- [Low][90] tests/unit/test_artifact_service.py:396 — Ownership-failure test asserts with pytest.raises(Exception), the broadest possible exception class

    - ID: f_tests_unit_stream_api_05; verification: static
    - Evidence: tests/unit/test_artifact_service.py:396: with pytest.raises(Exception, match="ownership") — any Exception whose message contains 'ownership' satisfies the test, including an unrelated failure raised from a different layer that happens to mention ownership.; Sibling tests in the same file assert the specific domain exceptions (ArtifactTooLarge, ArtifactQuotaExceeded, ArtifactInsufficientStorage, ArtifactInvalidName), so the broad form is an outlier.
    - Impact: If the chown-denial path regresses to raise a different error (or an incidental error containing the word appears earlier in upload), the test can pass while the intended ownership-failure contract — raise, and register nothing — is only half checked (the list==[] assertion still holds, but the error identity is unverified).
    - Fix: Assert the concrete exception type the store raises for ownership failures (or PermissionError if that is the contract), keeping the message match as a secondary check.

- [Low][80] tests/unit/test_gateway_config.py:73 — Short-secret gateway config test points two token-file env vars at files that are never created, coupling the test to validation order

    - ID: f_tests_unit_stream_api_06; verification: static
    - Evidence: tests/unit/test_gateway_config.py:73 and :75 set CBROWSER_GATEWAY_TOKEN_FILE and CBROWSER_GATEWAY_API_TOKEN_FILE to tmp_path / "dummy.txt"; no line in the test creates dummy.txt.; The test expects ValueError matching 'at least 32 bytes' (the agent-key length branch) at :80-81, which only surfaces if GatewayConfig.from_env reads and validates the agent key file before opening the two token files.
    - Impact: The test silently encodes an implementation-order assumption in the gateway unit: reorder validation (e.g. read all files first) and this test fails with a missing-file error despite the short-secret behavior being unchanged — a false failure that points at the wrong cause. It cannot silently pass for the wrong reason (the message match prevents that), so the risk is brittleness, not false confidence.
    - Fix: Create dummy.txt with a valid-length secret (as \_set_required_env does for the other gateway tests) so the only invalid input is the short agent key.

- [Low][90] tests/unit/test_automation_cdp.py:51 — \_short_root ignores the tmp_path fixture, hand-rolls a /tmp directory, and never cleans it up

    - ID: f_tests_unit_stream_api_07; verification: static
    - Evidence: tests/unit/test_automation_cdp.py:51-56: \_short_root(tmp_path) never uses its argument; it mkdtemps under /tmp, immediately rmtree's the fresh parent with ignore_errors=True, and returns parent/'data' which does not exist until callers mkdir it.; Neither caller (test_supervisor_cdp_websocket_forwards_to_agent_uds, test_supervisor_cdp_rejects_missing_or_foreign_token) removes the created /tmp/cbrowser-t008-uds-\* tree afterwards, bypassing pytest's tmp_path retention/cleanup conventions.
    - Impact: Every run leaks a token file (mode 0600) and runtime directories under /tmp on the test machine, and the setup-time rmtree of a just-created unique directory is dead work that obscures intent. The AF_UNIX length motivation is legitimate, but the lifecycle handling is not.
    - Fix: Use pytest's tmp_path with a short base (e.g. the basetemp configuration) or keep mkdtemp but register cleanup via a fixture/finalizer that removes the tree; drop the unused parameter and the setup rmtree.

- [Info][85] tests/unit/test_api_models_and_sse.py:64 — SSE broadcaster coverage stops at the initial snapshot chunk

    - ID: f_tests_unit_stream_api_08; verification: static
    - Evidence: tests/unit/test_api_models_and_sse.py:64-82: the only broadcaster test subscribes with a snapshot provider and asserts on the first chunk only ('event: runtime_state', profile id present).; No test in this file publishes an event after subscription, exercises a second concurrent subscriber, or probes the maxlen=10 buffer's eviction behavior, although RuntimeEventBroadcaster is the push path for runtime status changes.
    - Impact: Within this unit, the broadcaster's live-delivery behavior — the part most likely to regress (dropped events, cross-subscriber interference, unbounded buffering) — is unverified; the test would stay green if post-snapshot events were never delivered. Coverage may exist in integration/e2e units outside this file set (recorded as an uncertainty).
    - Fix: Add tests that publish after subscribing and assert the second chunk, fan out to two subscribers, and overflow maxlen to pin eviction semantics.

- [Info][95] tests/unit/test_download_reconciler.py:33 — Dead duplicate code in tests: repeated function-local 'import asyncio' and a duplicated consecutive assignment

    - ID: f_tests_unit_stream_api_09; verification: static
    - Evidence: tests/unit/test_download_reconciler.py imports asyncio at top level (line 5) and again inside test bodies at lines 33, 118, 358 and 431 — four no-op re-imports.; tests/unit/test_stream_resume.py:199-200 assigns agent.agent_session_id = "sess_test" twice in consecutive lines in test_detached_session_expires_after_grace.
    - Impact: No behavioral effect; the duplicates are copy-paste residue that adds noise when reading the forwarder/resume tests and suggests the surrounding blocks were duplicated without a cleanup pass.
    - Fix: Delete the four local re-imports and the duplicated assignment line.

- [Info][90] tests/unit/test_profile_copy_reset.py:88 — Profile copy/reset tests reach into ProfileRepository's private \_session_maker to build the artifact repository

    - ID: f_tests_unit_stream_api_10; verification: static
    - Evidence: tests/unit/test_profile_copy_reset.py:88, :117 and :370 construct ArtifactRepository(repo.\_session_maker) — a private attribute of ProfileRepository — because the test context does not retain the session maker it originally created in \_context (lines 25-31).; The same file's other white-box accesses are deliberate production seams (monkeypatching profile_service.\_copy_user_data), whereas \_session_maker is incidental plumbing.
    - Impact: Renaming or restructuring the repository's session-maker attribute breaks three tests despite unchanged behavior; the fix is trivial since \_context already has the maker in scope before constructing the repository.
    - Fix: Return the session maker from \_context and pass it to ArtifactRepository directly.

## views

```json
{
  "contracts": {
    "reviewer": "143ae932-2870-4a89-b44d-470847520005",
    "status": "completed"
  },
  "correctness": {
    "reviewer": "143ae932-2870-4a89-b44d-470847520005",
    "status": "completed"
  },
  "design": {
    "reviewer": "143ae932-2870-4a89-b44d-470847520005",
    "status": "completed"
  },
  "documentation": {
    "reviewer": "143ae932-2870-4a89-b44d-470847520005",
    "status": "completed"
  },
  "performance": {
    "reviewer": "143ae932-2870-4a89-b44d-470847520005",
    "status": "completed"
  },
  "robustness": {
    "reviewer": "143ae932-2870-4a89-b44d-470847520005",
    "status": "completed"
  },
  "security": {
    "reviewer": "143ae932-2870-4a89-b44d-470847520005",
    "status": "completed"
  },
  "tests": {
    "reviewer": "143ae932-2870-4a89-b44d-470847520005",
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
  "tests/unit/test_profile_copy_reset.py",
  "tests/unit/test_refactor_behavior_equivalence.py",
  "tests/unit/test_secret_file_permissions.py",
  "tests/unit/test_selkies_file_transfers.py",
  "tests/unit/test_stream_agent_lifecycle.py",
  "tests/unit/test_stream_agent_protocol_v2.py",
  "tests/unit/test_stream_binding_guards.py",
  "tests/unit/test_stream_capture_policy.py",
  "tests/unit/test_stream_clipboard_policy.py",
  "tests/unit/test_stream_display_config.py",
  "tests/unit/test_stream_protocol_schema.py",
  "tests/unit/test_stream_resume.py",
  "tests/unit/test_stream_selkies_tokens.py",
  "tests/unit/test_stream_transport_hardening.py",
  "tests/unit/test_vendor_selkies_security.py"
]
```
