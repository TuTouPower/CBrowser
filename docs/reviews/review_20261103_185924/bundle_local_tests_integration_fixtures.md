# bundle_local_tests_integration_fixtures

## responsibilities

- tests/integration: black-box-ish integration tests for the v2 API (auth, artifacts, SSE, profile patch/copy semantics), Gateway (control RPC, signaling, fixtures), Supervisor (RPC, gateway client, recovery, status truth, capacity), and the API-as-subprocess contract suite (test_v2_api_subprocess).
- tests/fixtures: harnesses and probes — real-process API/Supervisor/Gateway topology (topology.py, offline_fixture.py, gateway_service.py, conftest.py), frontend lanes (frontend_probe, frontend_app_probe), browser/media oracles (browser_oracle, audio_analyzer, clipboard/keymap probes, mitshm C probe), Selkies asset provision (selkies_assets.py), evidence redaction, shared auth helpers (api_auth.py), and the supervisor resource/CPU probe (stream_monitor.py, cpu_burner.py).

## interfaces

- GatewayHarness / ProductionGatewayService both build the production cbrowser.gateway.server.create_gateway_app; the only substitution is the Gateway->API counterparty (HTTP-level FakeApiService, or object-level FakeGatewayApiClient).
- OfflineSupervisorFixture composes RealApiProcess (real uvicorn cbrowser.api.main:app), ProductionGatewayService and RealSupervisorContainer (real supervisor image); offline_fixture.py's header explicitly states it no longer ships a Gateway double.
- conftest.supervisor_api runs the real FastAPI app in a subprocess against a tmp SQLite DB with randomized admin credentials (api_auth.py, 0600 token/password files).
- Tests assert observable behavior: HTTP status codes, visibility semantics from the production Gateway endpoint (test_gateway_control AC-007: visibility returns the Agent's last health report, 503 when unreported — never a guessed False), idempotency, failure counts, log redaction.

## dependencies

- Production packages cbrowser.api / cbrowser.gateway / cbrowser.supervisor / cbrowser.stream_agent driven in-process or as real subprocesses/containers.
- tests/fixtures/e2e_env.py (outside this unit) gates image/env prerequisites via require_e2e_env (skip, or fail when CBROWSER_E2E_REQUIRED=1).
- frontend_probe/host_builder.py and frontend_app_probe/harness.py import tests/fixtures/frontend_probe/adapter_probe.py (outside this unit) and the built frontend dist artifacts.
- stream_monitor.py depends on a gateway double defined in tests/e2e/test_stream_runtime_e2e.py (registered_agents / agent_instances dicts) and on production ResourcePolicyService / ResourceMonitor.
- pytest_plugins = ('test_supervisor_rpc',) couples test_supervisor_observation_authority.py and test_supervisor_status_truth.py to fixtures defined in another test module.

## flows

- E2E topology: harness writes per-run randomized secrets (0600, control dir 0700) -> starts real containers/processes -> drives real browser/CDP through Caddy -> Gateway -> Stream Runtime -> collects redacted evidence; cleanup is label-scoped (com.cbrowser.prefix) with ownership validation and post-clean verification (network_not_empty surfaces as an error).
- Supervisor recovery lane: API process stopped/restarted around a real supervisor container; gateway runs production code in-process; assertions read back supervisor status, audit events and spool state.

## constraints

- Static review only; no test was executed, so pass/fail state of these suites is not asserted here.
- Several lanes require Docker/images and are environment-gated; their absence locally is by design (require_e2e_env), not a finding.

## decisions

- Headline judgment on the t018 question: the previous structural problem — a fixture Gateway re-implementing production visibility/semantics — is gone. Both gateway harnesses and the offline fixture now run production create_gateway_app, the API and Supervisor run as real processes/containers, and visibility is asserted against production behavior. Residual re-implementation is narrower and at the edges: the Gateway->API counterparty fakes, the resource probe's quota-delivery callback, the two Selkies client shims, and the gateway-control stub used by client wire tests.

## evidence

- tests/fixtures/supervisor_recovery_probe/gateway_service.py: ProductionGatewayService constructs the real create_gateway_app; only GatewayApiClient is faked at object level.
- tests/fixtures/supervisor_recovery_probe/offline_fixture.py header: 'this module no longer provides a Gateway double'; RealApiProcess runs real uvicorn cbrowser.api.main:app.
- tests/integration/test_gateway_fixtures.py: GatewayHarness runs real create_gateway_app without api_client, exercising real HTTP to the fake API service.
- tests/fixtures/gateway_probe/topology.py: cleanup strictly by com.cbrowser.prefix labels with ownership checks; secrets randomized per run with 0600 files.
- tests/fixtures/gateway_probe/evidence.py: _redact masks token/secret/password/cookie/resume_key keys in saved evidence.
- tests/fixtures/runtime_probe/audio_analyzer.py: strict two-method frequency verification with 1% tolerance rather than a single heuristic.

## uncertainties

- Whether any CI lane actually runs the Docker-gated suites in this unit could not be verified statically from these files alone.
- The exact divergence between the fixture Selkies shims and the production frontend adapter (src/frontend adapter.ts, another unit) is inferred from the shims' own code plus the adapter's separate existence; a line-level diff against the adapter belongs to the frontend unit.

## Findings

- [Medium][85] tests/fixtures/supervisor_resource_probe/stream_monitor.py:27 — Resource probe re-implements the production supervisor->gateway->agent quota delivery instead of exercising it
  - ID: f_tests_integration_fixtures_01; verification: static
  - Evidence: stream_monitor.py:27-60 reads gateway.agent_instances / gateway.registered_agents (dicts of a test-local fake gateway defined in tests/e2e/test_stream_runtime_e2e.py, not production attributes) and hand-builds the wire envelope {'version': 'v2', 'action': 'supervisor_quota', agent_session_id, runtime_instance_id, ...} sent directly over the agent socket.; Production path is different: supervisor GatewayControlClient.set_quota -> gateway handle_supervisor_quota (src/backend/cbrowser/gateway/server.py:169) which itself constructs the AgentAction.SUPERVISOR_QUOTA envelope (server.py:213) from the gateway's own registry and fencing state.; The fixture hand-rolls its own instance fencing check (agent_instances[pid] == runtime_instance_id) duplicating the gateway's fencing semantics.
  - Impact: The CPU-policy verification validates the fixture's own copy of quota delivery. If the production envelope shape, action name or fencing rules change, this probe can keep passing against its hand-made message while the real Supervisor->Gateway->Agent chain is broken; conversely a legitimate production change can break the probe for non-behavioral reasons.
  - Fix: Deliver quota through the production path in this probe (real GatewayControlClient against a real gateway, or at minimum construct the envelope via the production protocol types in cbrowser.stream_agent.protocol) and drop direct access to the fake gateway's socket registry.

- [Medium][80] tests/fixtures/gateway_probe/selkies_assets.py:22 — Two divergent test-local Selkies client shims re-implement the production adapter's tab-identity semantics, and disagree with each other
  - ID: f_tests_integration_fixtures_02; verification: static
  - Evidence: selkies_assets.py:22 CLIENT_SHIM_SCRIPT embeds a full client re-implementation (WebSocket/RTCPeerConnection wrapping, Web Locks tab arbitration, HELLO rewriting) injected into the official Selkies page; at lines 114-122 it creates a selkies_tab_id in sessionStorage when one is missing.; tests/fixtures/stream_probe/web_lock_shim.js:48-49 implements the same tab-lock idea differently: when no selkies_tab_id exists it closes the socket with 1008 'tab_identity_required' instead of creating an id, and it does not rewrite signaling URLs the way CLIENT_SHIM_SCRIPT does.; A third implementation — the production frontend adapter (src/frontend/src/features/browser-session/adapter.ts, which also manages selkies_tab_id) — is what the frontend lanes exercise, so gateway/stream E2E lanes validate shim behavior rather than the shipped adapter's identity arbitration.
  - Impact: Tab-collision / single-foreground-tab behavior verified in the gateway and stream lanes is the behavior of two mutually inconsistent test shims, not of the production adapter; a regression in the real adapter's arbitration (or a shim/adapter drift) would not be caught by these lanes, and the two lanes can legitimately disagree about the missing-id case.
  - Fix: Drive at least the gateway lane with the real built adapter (as frontend_probe does with dist selkies_adapter.js), or generate both shims from one shared source and document them as protocol probes only, not as adapter behavior coverage.

- [Medium][75] tests/integration/test_gateway_fixtures.py:93 — Two divergent fakes of the same Gateway->API internal surface; the HTTP fake unconditionally allows automation authorization and ignores viewer origin
  - ID: f_tests_integration_fixtures_03; verification: static
  - Evidence: test_gateway_fixtures.py:93-103 FakeApiService.handle_automation_authorize returns allowed=True for any token/profile, and handle_viewer_authorize (line 81) keys authorization without the origin field the production API checks (cf. test_auth_api.py invalid_origin cases).; tests/fixtures/supervisor_recovery_probe/gateway_service.py FakeGatewayApiClient implements the same surface with opposite defaults: deny by default, authorization keyed by (cookie_value, origin, profile_id), explicit allow-list helpers.; Both fakes hand-maintain the response shapes of the production internal API with no shared contract fixture.
  - Impact: Gateway behavior verified in the GatewayHarness lane runs against weaker authorization semantics than the recovery lane and than production: an automation-auth or origin-check regression on the gateway side would be masked by the always-allow HTTP fake, and the two lanes can drift apart as the production API contract evolves.
  - Fix: Unify on one fake implementation (or generate both from a shared contract definition), make automation-authorize deny-by-default with explicit grants mirroring FakeGatewayApiClient, and include origin in the viewer-authorize key.

- [Medium][85] tests/fixtures/frontend_probe/host_builder.py:19 — Frontend build freshness is claimed but not checked: lanes can silently test a stale dist
  - ID: f_tests_integration_fixtures_04; verification: static
  - Evidence: host_builder.py:19-20 ensure_frontend_build docstring says it 'Ensures Vite production build exists and is up to date', but the implementation only checks existence of dist/index.html, the selkies directory and selkies_adapter.js — no mtime or hash comparison against src/.; tests/fixtures/frontend_app_probe/harness.py prepare_frontend_app likewise accepts any pre-existing dist and only errors when artifacts are absent.
  - Impact: After any frontend source change, the frontend E2E lanes keep passing (or failing) against the previous build without any signal, so the suite can certify adapter/UI behavior that is no longer what ships.
  - Fix: Record a build stamp (source tree hash or max mtime) at build time and rebuild or fail loudly when the stamp is stale; or always invoke the build in the harness when a cheap staleness check fails.

- [Low][90] tests/integration/test_normal_exit_replay.py:1 — Module docstring promises an offline-API recovery scenario the file does not implement; tests write into the working tree instead of tmp_path
  - ID: f_tests_integration_fixtures_05; verification: static
  - Evidence: The module docstring's scenario 3 is 'Offline API recovery: API is offline when clean exit occurs, Supervisor restarts, API recovers', but the third test in the file is a dual-Profile isolation test with the API online throughout; no test takes the API offline.; All four tests build data roots under the repo-relative .scratch/normal_exit_fix directory while accepting a tmp_path fixture parameter they never use.; The file also hard-codes behavior in _FakeDocker._inspect by container-name substring ('target_a'/'clean' -> ports 30001/30002).
  - Impact: Readers (and coverage accounting) believe the offline-recovery replay case is covered by this file when it is not; repo-relative scratch roots risk cross-run residue and collisions if the suite is ever run in parallel or from a read-only checkout.
  - Fix: Correct the docstring to describe the implemented scenarios (or implement the offline case), and switch the data roots to the already-accepted tmp_path fixture.

- [Low][85] tests/integration/test_normal_exit_replay.py:811 — Integration tests assert and seed production objects' private internals
  - ID: f_tests_integration_fixtures_06; verification: static
  - Evidence: test_normal_exit_replay.py:811-821 asserts core.ports._allocated and membership in core._sessions.; tests/integration/test_supervisor_status_truth.py seeds core._sessions[profile] directly; tests/integration/test_supervisor_manual_retry.py:68 reads recovery._in_flight_tasks.; tests/integration/test_recovery_snapshot_failure.py:28-31 calls the private coordinator._load_profile_config with SimpleNamespace(api=api, _auth_headers=dict) — the builtin dict type passed as the headers callable, which only works incidentally because dict() returns {}.; tests/integration/test_automation_cdp_flow.py and others assemble subjects from SimpleNamespace objects shaped after private attribute layouts (_token_file, _sessions, _get_profile_lock, _load_profile_config).
  - Impact: Internal refactors of SupervisorCore/RecoveryCoordinator that change no behavior will break these tests, and the dict-as-callable construction can silently produce wrong headers if the production call signature changes; the tests verify implementation layout rather than contract.
  - Fix: Prefer status/RPC-level assertions (the suites already have supervisor status and spool readers) and construct test subjects through production factories or small explicit stub classes with typed surfaces instead of SimpleNamespace mirrors of private attributes.

- [Low][80] tests/integration/test_supervisor_observation_authority.py:57 — The Supervisor Docker boundary is re-faked in at least four divergent hand-rolled forms inside the unit
  - ID: f_tests_integration_fixtures_07; verification: static
  - Evidence: Two unrelated _FakeDocker classes: test_normal_exit_replay.py:67 (with substring-based _inspect) and test_supervisor_observation_authority.py:57 (minimal subset), plus SimpleNamespace docker adapters in test_supervisor_manual_retry.py, test_supervisor_start_capacity.py and test_supervisor_status_truth.py, each implementing a different subset of the production adapter surface.; The same pattern repeats for small helpers: find_free_port/port-probing is re-implemented in at least six files (topology.py, offline_fixture.py, test_gateway_fixtures.py, conftest.py, test_v2_api_subprocess.py, test_supervisor_gateway_control_auth.py), and login/cookie parsing is duplicated between api_auth.py (sync and async copies), topology.py login_api and the two SSE test modules.
  - Impact: When the production DockerAdapter (or auth helper) surface changes, each fake drifts independently; a change can be masked by whichever subset a given fake implements, and fixes must be repeated across copies.
  - Fix: Consolidate one shared fake DockerAdapter and one free-port/login helper under tests/fixtures and have the supervisor suites import them, deleting the per-module copies.

- [Low][80] tests/integration/test_supervisor_gateway_client.py:13 — Gateway-control client wire tests run against a stub that re-implements the gateway's auth/fence semantics
  - ID: f_tests_integration_fixtures_08; verification: static
  - Evidence: test_supervisor_gateway_client.py defines a catch-all aiohttp server that itself decides 401 (bad token) and 409 (stale fence) responses, duplicating semantics owned by the production gateway's control handlers.; The real gateway side of the same contract is covered elsewhere in the unit (test_gateway_control.py, test_supervisor_gateway_control_auth.py), which mitigates but does not remove the duplication.
  - Impact: If the production gateway changes its control-plane status codes or fence rules, the SupervisorGatewayClient tests keep passing against the stub's frozen copy while the client/gateway pair may no longer agree.
  - Fix: Point the client tests at a real create_gateway_app instance for the auth/fence cases (as test_supervisor_gateway_control_auth.py already does for the token matrix) and keep the stub only for transport-level cases (timeouts, malformed bodies).

- [Low][75] tests/integration/test_v2_api_subprocess.py:793 — AC-004 verifies SQLite busy_timeout behavior with wall-clock windows that are load-sensitive
  - ID: f_tests_integration_fixtures_09; verification: static
  - Evidence: test_v2_api_subprocess.py:793 asserts 1.4 <= elapsed < 4.5 for a lock-wait case and line 822 asserts 4.5 <= elapsed_timeout <= 6.5 for the timeout case, against a real subprocess and real lock contention.; The margins assume the contending writer holds the lock for a fixed ~1.5s/5s; under CI load or slow disks the scheduling jitter can push measured elapsed outside these windows without any product regression.
  - Impact: Intermittent failures in the API subprocess contract suite would train developers to ignore or retry the suite, weakening the very gate t018 was meant to restore.
  - Fix: Assert on outcomes rather than elapsed windows where possible (second writer succeeds after release; timeout case raises the expected busy error), keeping only loose sanity bounds (e.g. elapsed >= lock-hold time, elapsed < 3x timeout) if timing must be checked at all.

- [Low][85] tests/fixtures/gateway_probe/topology.py:137 — Topology harness makes profile-bearing data directories world-writable (0o777)
  - ID: f_tests_integration_fixtures_10; verification: static
  - Evidence: topology.py:137-141 chmods the data subdirectories (profiles, runtime, runtime-events, artifacts, spool) and metadata_dir to 0o777 while the control directory holding secrets is 0o700 with 0600 files.; Related fixture hygiene: tests/fixtures/runtime_probe/test_mitshm.c:68 creates its SysV shared-memory segment with IPC_CREAT | 0777 in a probe whose subject is display isolation.
  - Impact: During E2E runs these directories hold real browser profile data; on a shared dev/CI machine any local user can read or tamper with them for the duration of the run. Impact is limited to test environments, hence Low.
  - Fix: Restrict to the minimum the container uid mapping actually needs (e.g. 0o770 with a shared group, or document why 0o777 is required and confine the tree under a 0o700 parent), and create the mitshm segment with 0600.

- [Info][80] tests/fixtures/gateway_probe/evidence.py:14 — Evidence redaction does not cover session identifiers, and the default evidence directory is a predictable shared tmp path
  - ID: f_tests_integration_fixtures_11; verification: static
  - Evidence: evidence.py _redact masks keys matching token/secret/password/cookie/resume_key, but agent_session_id / session_id values are written to evidence JSON unredacted.; DEFAULT_EVIDENCE_DIR is tempfile.gettempdir()/cbrowser_e2e_evidence, shared across runs and users on the machine, with artifacts persisting until manually removed.
  - Impact: Session identifiers are routing capabilities for the stream tunnel; leaving them in long-lived, world-readable-by-default evidence files is a minor information-hygiene gap in an otherwise careful redaction helper.
  - Fix: Add 'session' to the redaction markers and default the evidence dir to a per-run directory under the harness tmp root (keeping the env override).

- [Info][85] tests/integration/test_v2_api_subprocess.py:24 — Module-level scratch directory is created at import time and the OpenAPI spec is re-read on every validation call
  - ID: f_tests_integration_fixtures_12; verification: static
  - Evidence: test_v2_api_subprocess.py:24 SCRATCH_DIR = Path(tempfile.mkdtemp(...)) executes at import/collection time, creating state even when no test in the module runs, and is shared by all tests in the module (contrast conftest.py's per-fixture tmp_path usage).; _validate_schema re-reads and re-parses the full OpenAPI document from the server on each call instead of caching it per module.
  - Impact: Collection-time side effects and cross-test shared scratch make ordering/interference bugs possible and slow the suite marginally; no behavioral incorrectness observed.
  - Fix: Create the scratch dir in a module-scoped fixture and cache the parsed OpenAPI document after the first fetch.

- [Info][70] tests/fixtures/stream_probe/clipboard_oracle.py:1 — Stream probes depend on private internals of the vendored selkies library
  - ID: f_tests_integration_fixtures_13; verification: static
  - Evidence: clipboard_oracle.py drives selkies' private _X11ClipboardMonitor; x11_keymap_probe.py reaches into the keyboard object's private _overlay/_prebind surface.; The library is pinned (selkies 2.1.0 assets are sha256-verified in selkies_assets.py), which bounds the drift risk.
  - Impact: A selkies upgrade can break the probes for non-behavioral reasons; failures would be loud (assertions), so this is a maintenance note rather than a correctness risk.
  - Fix: None required now; when the selkies pin is next bumped, re-check these two probes first and prefer the library's public surface if one appears.

## views

```json
{
  "contracts": {
    "reviewer": "183116b6-7ad0-42ac-8311-aaf82476383c",
    "status": "completed"
  },
  "correctness": {
    "reviewer": "183116b6-7ad0-42ac-8311-aaf82476383c",
    "status": "completed"
  },
  "design": {
    "reviewer": "183116b6-7ad0-42ac-8311-aaf82476383c",
    "status": "completed"
  },
  "documentation": {
    "reviewer": "183116b6-7ad0-42ac-8311-aaf82476383c",
    "status": "completed"
  },
  "performance": {
    "reviewer": "183116b6-7ad0-42ac-8311-aaf82476383c",
    "status": "completed"
  },
  "robustness": {
    "reviewer": "183116b6-7ad0-42ac-8311-aaf82476383c",
    "status": "completed"
  },
  "security": {
    "reviewer": "183116b6-7ad0-42ac-8311-aaf82476383c",
    "status": "completed"
  },
  "tests": {
    "reviewer": "183116b6-7ad0-42ac-8311-aaf82476383c",
    "status": "completed"
  }
}
```

## files_reviewed

```json
[
  "tests/fixtures/api_auth.py",
  "tests/fixtures/frontend_app_probe/harness.py",
  "tests/fixtures/frontend_probe/__init__.py",
  "tests/fixtures/frontend_probe/harness.py",
  "tests/fixtures/frontend_probe/host_builder.py",
  "tests/fixtures/gateway_probe/__init__.py",
  "tests/fixtures/gateway_probe/browser_oracle.py",
  "tests/fixtures/gateway_probe/caddyfile.py",
  "tests/fixtures/gateway_probe/evidence.py",
  "tests/fixtures/gateway_probe/selkies_assets.py",
  "tests/fixtures/gateway_probe/topology.py",
  "tests/fixtures/runtime_probe/audio_analyzer.py",
  "tests/fixtures/runtime_probe/test_mitshm.c",
  "tests/fixtures/stream_probe/clipboard_oracle.py",
  "tests/fixtures/stream_probe/media_page.html",
  "tests/fixtures/stream_probe/web_lock_shim.js",
  "tests/fixtures/stream_probe/x11_keymap_probe.py",
  "tests/fixtures/supervisor_container_probe/api_runtime.Dockerfile",
  "tests/fixtures/supervisor_container_probe/api_runtime.Dockerfile.dockerignore",
  "tests/fixtures/supervisor_recovery_probe/gateway_service.py",
  "tests/fixtures/supervisor_recovery_probe/offline_fixture.py",
  "tests/fixtures/supervisor_resource_probe/cpu_burner.py",
  "tests/fixtures/supervisor_resource_probe/stream_monitor.py",
  "tests/integration/conftest.py",
  "tests/integration/test_api_sse_events.py",
  "tests/integration/test_artifacts_api.py",
  "tests/integration/test_auth_api.py",
  "tests/integration/test_automation_api.py",
  "tests/integration/test_automation_cdp_flow.py",
  "tests/integration/test_gateway_control.py",
  "tests/integration/test_gateway_fixtures.py",
  "tests/integration/test_gateway_signaling.py",
  "tests/integration/test_normal_exit_replay.py",
  "tests/integration/test_profile_copy_reset_api.py",
  "tests/integration/test_profile_patch_semantics.py",
  "tests/integration/test_recovery_snapshot_failure.py",
  "tests/integration/test_runtime_coordinator_integration.py",
  "tests/integration/test_sse_epoch_integration.py",
  "tests/integration/test_supervisor_gateway_client.py",
  "tests/integration/test_supervisor_gateway_control_auth.py",
  "tests/integration/test_supervisor_manual_retry.py",
  "tests/integration/test_supervisor_observation_authority.py",
  "tests/integration/test_supervisor_rpc.py",
  "tests/integration/test_supervisor_start_capacity.py",
  "tests/integration/test_supervisor_status_truth.py",
  "tests/integration/test_v2_api_subprocess.py"
]
```
