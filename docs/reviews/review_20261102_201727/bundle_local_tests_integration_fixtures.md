# bundle_local_tests_integration_fixtures

## responsibilities

- Integration tests (tests/integration/, 23 files) exercise the real FastAPI app (TestClient, in-process uvicorn, and true subprocess uvicorn), the real Gateway app over real WebSocket/HTTP, the real SupervisorCore/RecoveryCoordinator against a real subprocess API, and the real Runtime Agent UDS app; Docker-topology E2E lanes live behind the fixture harnesses.
- Fixtures (tests/fixtures/, 35 files) provide: real Docker container topologies (API/Supervisor/Gateway/coturn/Caddy) in gateway_probe/topology.py and frontend_probe/harness.py; the official Selkies web client extracted from the stream image and hash-verified (selkies_assets.py); a from-scratch Gateway re-implementation for supervisor suites (supervisor_recovery_probe/gateway_fixture.py) plus offline process fixtures (offline_fixture.py); SDK-level ICE/clipboard/keymap/audio/MIT-SHM probes (stream_probe/, runtime_probe/); container fixture images (supervisor_container_probe/) and resource-policy probes (supervisor_resource_probe/).
- Oracles are mostly behavioral and strong where it matters: decoded-frame/audio-energy progression via getStats (chrome_relay.py), raw PCM frequency analysis with 1% tolerance (audio_analyzer.py), socket-leak accounting via /proc/self/fd (ice_* probes), SHA-256 manifest verification of extracted Selkies assets, and physical server-log secret-redaction checks (test_v2_api_subprocess.py).

## interfaces

- GatewayHarness (tests/integration/test_gateway_fixtures.py): real production Gateway app (create_gateway_app) + FakeApiService implementing /api/v1/internal/gateway/* for gateway control/signaling/rotation suites.
- SupervisorGatewayFixture (gateway_fixture.py) with a written contract (gateway_contract.md): agent register WS, visibility/quota/disconnect control RPC with Bearer + instance fencing, test viewer WS; consumed by offline_fixture as OfflineGatewayMock and by gateway_container.py in a Docker image.
- GatewayTopologyHarness / FrontendTopologyHarness / FrontendAppTopologyHarness: start()/cleanup() over a labeled Docker graph, login_api()/create_and_start_profile() helpers, prefix-scoped label cleanup (cleanup_prefixed_resources).
- api_auth.create_auth_context: randomized 0o600 admin password file + env for subprocess/container API launches, shared by several suites.
- Probe scripts communicate results as JSON on stdout (ice_*, rtc_config_*, chrome_relay relay_generations.json, stream_monitor proof JSON) for their invoking suites to assert on.

## dependencies

- Production code under src/backend (cbrowser.api.app.create_app, cbrowser.gateway.server.create_gateway_app, cbrowser.supervisor.*, cbrowser.runtime_agent.*, cbrowser.stream_agent.*) — tests import it directly.
- Pinned Selkies 2.1.0 library, including private internals (_X11ClipboardMonitor, _XTestKeyboard, ice transport internals) used by probes.
- Docker (docker-py and docker CLI via subprocess) with immutable sha256 image IDs supplied through CBROWSER_*_TEST_IMAGE env vars and engine/GeoIP caches; suites skip or assert-fail when these are absent (offline_fixture.get_e2e_prerequisites).
- coturn and Caddy pinned by digest in topology.py; config/selkies/selkies_web_sha256.txt as the asset manifest authority.

## flows

- API suites: build app with tmp_path SQLite + random-secret files -> login over HTTP -> drive profiles/runtime/artifacts/automation endpoints -> assert status codes, payloads, on-disk state and (for subprocess suites) physical logs.
- Gateway suites: GatewayHarness starts FakeApiService + real Gateway on ephemeral ports -> test acts as Agent and/or Viewer over real WebSockets -> assertions on frames, close codes, fencing status codes and rotation generations.
- Supervisor suites: supervisor_api fixture launches a real uvicorn subprocess -> tests drive internal RPC, then run SupervisorCore/RecoveryCoordinator in-process against fake or real Docker surfaces and assert the API-visible runtime record.
- Topology E2E: harness creates labeled network/containers with generated secrets -> Caddy HTTPS origin -> browser/Selkies client oracles observe media, ICE and clipboard behavior -> label-scoped cleanup tears the graph down.

## constraints

- Static review only: no test or probe was executed; pass/fail status of Docker-dependent lanes is not established here.
- Suites require a Docker host with prebuilt immutable images and engine/GeoIP caches; several lanes are therefore environment-gated (skip via get_e2e_prerequisites, hard assert on sha256 env in topology).
- Probes assume Linux /proc, X11 (:99), UDS paths and host.docker.internal conventions of the project's own containers.

## decisions

- Gateway behavior is tested against the real Gateway app with only the API faked (FakeApiService), while Supervisor behavior is tested against a re-implemented Gateway fixture — an asymmetry that concentrates drift risk on the supervisor side (finding 01).
- The Selkies web client used in gateway E2E is the official client extracted from the stream image and verified against a pinned SHA-256 manifest before a test-local shim is injected (selkies_assets.py).
- Cleanup safety is taken seriously in the topology harness: cleanup only removes resources whose com.cbrowser.prefix label matches, and start() failures trigger cleanup with chained exceptions.
- Negative-path proof is a recurring pattern: forged journals, stale instances, wrong ICE passwords, replayed idempotency keys and foreign credentials are first-class test cases across the unit.

## evidence

- tests/fixtures/gateway_probe/topology.py:596-675 label-verified cleanup; :369-388 verify_manifest use in selkies_assets.py:369-386 (SHA-256 of every extracted asset).
- tests/fixtures/stream_probe/chrome_relay.py:218-245 asserts framesDecoded and totalAudioEnergy strictly increase across an ICE generation change and that the selected pair stays relay with the new ufrag.
- tests/fixtures/runtime_probe/audio_analyzer.py:224-293 dual-method (autocorrelation + ZCR) frequency verification with 1% tolerance and crosstalk rejection.
- tests/integration/test_v2_api_subprocess.py:700-712 asserts sentinel secrets never appear in the physical server log after runtime-event processing.
- tests/integration/test_gateway_control.py and test_gateway_signaling.py run the production create_gateway_app over real WebSockets (fencing, isolation, close codes asserted on the wire).
- tests/fixtures/supervisor_recovery_probe/offline_fixture.py:48-98 prerequisites gate: missing env -> skip, present-but-invalid digest/path -> hard failure.

## uncertainties

- Which client shim production actually ships (web_lock_shim.js is referenced by tests/e2e outside this unit; the frontend build's selkies_adapter.js is a third variant) — the impact size of finding 02 depends on this, though the in-unit divergence is factual.
- Whether the supervisor suites' reliance on the fixture Gateway's viewer-based visibility is an accepted simplification recorded in some spec outside this unit; gateway_contract.md presents the fixture behavior as its contract without flagging the difference from production.
- Whether the build pipeline that consumes api_runtime.Dockerfile applies api_runtime.Dockerfile.dockerignore exactly as written (finding 08 is marked suspected for this reason).
- No execution evidence: Docker-dependent lanes, timing-sensitive rotation/resource tests and the C probe were reviewed statically only.

## Findings

- [High][80] tests/fixtures/supervisor_recovery_probe/gateway_fixture.py:130-163 — SupervisorGatewayFixture re-implements the Gateway with different visibility semantics than the production Gateway, so supervisor recovery suites validate against a divergent counterparty
  - ID: f_tests_integration_fixtures_01; verification: static
  - Evidence: Fixture _handle_visibility computes has_foreground_viewers from its own viewer WebSocket sets (self._foreground_viewers, gateway_fixture.py:161-163), i.e. from test-viewer connections it tracks itself.; The production Gateway contract exercised in tests/integration/test_gateway_control.py:117-121 (AC-007) is the opposite source of truth: 'visibility endpoint returns only the Agent's last health report', driven by agent heartbeat payloads (viewer_count/unpaused_video_consumers/capture_running), never by viewer sockets.; The fixture is the counterparty for the supervisor offline/recovery E2E lane (offline_fixture.py:691 OfflineGatewayMock = SupervisorGatewayFixture) and for container blackbox runs (gateway_container.py), so those suites can pass while the supervisor's behavior against the real Gateway's report-based visibility is broken, and vice versa.; Fixture also invents lifecycle semantics not verified against production: on agent disconnect it closes that profile's viewers with code 1001 (gateway_fixture.py agent-register finally block), a behavior the contract doc (gateway_contract.md) does not state for this fixture.
  - Impact: Supervisor foreground/idle and quota decisions that depend on has_foreground_viewers are tested against semantics the production Gateway does not implement; contract drift between fixture and production Gateway is invisible to the suites that use the fixture.
  - Fix: Make the fixture's visibility derive from agent health reports like production (accept heartbeat/report frames and answer from the last report, 503 before the first report), or clearly scope the fixture contract as a different, reduced contract and add at least one supervisor-level test against the real Gateway app (as test_gateway_control.py does with create_gateway_app).

- [Medium][85] tests/fixtures/gateway_probe/selkies_assets.py:22-322 — Two divergent tab-identity/WebSocket shims exist (CLIENT_SHIM_SCRIPT vs web_lock_shim.js); different suites exercise different client identity behavior
  - ID: f_tests_integration_fixtures_02; verification: static
  - Evidence: selkies_assets.py CLIENT_SHIM_SCRIPT wraps window.WebSocket with a plain function, rewrites signaling URLs to /stream/{profileId}/signal, generates a selkies_tab_id UUID when missing, suppresses 'activity' frames, filters cbrowser control frames, and handles rtc_config/ice_restart itself.; tests/fixtures/stream_probe/web_lock_shim.js:1-66 implements the same tab-lock idea via a Proxy, but closes the socket with 1008 'tab_identity_required' when no tab id exists instead of generating one, only intercepts signaling paths, and has no rtc_config/ice_restart/activity handling.; The gateway E2E lane runs the official Selkies client patched with CLIENT_SHIM_SCRIPT (prepare_selkies_web_assets), while stream identity E2E uses web_lock_shim.js; HELLO gating, collision remap and reconnect behavior therefore differ between suites.
  - Impact: A tab-identity or signaling regression can be hidden in one lane and exposed in the other; fixes must be made twice and the two implementations have already drifted in observable behavior (missing-id handling).
  - Fix: Converge on one shim implementation shared by both lanes (single source file injected by both harnesses), or document precisely which client each lane is meant to emulate and add a parity test for the HELLO/tab-lock behavior.

- [Medium][90] tests/fixtures/frontend_probe/harness.py:144-389 — FrontendTopologyHarness duplicates the entire gateway topology startup instead of reusing it; turnserver.conf is generated in three places with different parameters
  - ID: f_tests_integration_fixtures_03; verification: static
  - Evidence: frontend_probe/harness.py _start_containers (lines 144-389) re-implements gateway_probe/topology.py _do_start (lines 213-589) almost verbatim: API/coturn/gateway/supervisor/Caddy startup, the same turnserver.conf string, the same supervisor command line, the same port-readiness logic; the class comment admits the parent start() is bypassed.; turnserver.conf content is constructed independently in topology.py:254-272, frontend_probe/harness.py:178-196, and stream_probe/chrome_relay.py:39-45, with different relay port ranges (50000-50040 vs 42100-42140) and different external-ip/relay-ip wording.; Any change to production wiring (env names, supervisor flags, TURN settings) must be edited in two or three places; a miss silently changes what an E2E lane proves.
  - Impact: Harness drift: frontend and gateway E2E lanes can unknowingly test different topologies, and maintenance fixes land in one copy only.
  - Fix: Parameterize GatewayTopologyHarness._do_start (static-asset preparation and api_environment_extra hooks already exist) and delete the duplicated _start_containers; generate turnserver.conf from one shared helper.

- [Medium][85] tests/integration/test_gateway_rotation.py:466-493 — ICE generation commit is asserted through the system's own log line ('Generation N officially committed') rather than an observable protocol/media outcome
  - ID: f_tests_integration_fixtures_04; verification: static
  - Evidence: test_gateway_rotation.py _committed() (lines 466-469) scans caplog records for the literal string 'Generation {n} officially committed'; both commit tests (lines 497-611) use it as the primary oracle for commit and non-commit.; tests/fixtures/stream_probe/chrome_relay.py:199-216 polls `docker logs` of the stream container for the same sentence as the generation-retirement fence before checking media stats.; The log wording is thus an implicit cross-component contract: rewording the log breaks tests without any behavior change, and emitting the line early would make the rotation commit tests pass without a real takeover.
  - Impact: Commit semantics — a core correctness property of credential rotation — rest partly on self-reported state; log refactors cause false failures and premature log emission would cause false passes.
  - Fix: Expose an observable commit signal (e.g. the generation reported in a subsequent rtc_config/visibility response or agent-confirmed state via the API) and assert on it; keep log checks, if any, as secondary diagnostics. In chrome_relay.py the getStats/ufrag checks already provide the real oracle and could stand alone.

- [Medium][90] tests/fixtures/stream_probe/ice_restart_failure.py:68-117 — Many tests and probes assert on or manipulate private internals instead of observable behavior, coupling the suite to implementation details
  - ID: f_tests_integration_fixtures_05; verification: static
  - Evidence: ice_restart_failure.py:68,90-117 reads the name-mangled selkies attribute transport._RTCIceTransport__monitor_task; ice_pending_close.py:63-71 asserts on transport._connection and connection._closed; ice probes generally reach a.sctp.transport.transport.; tests/integration/test_normal_exit_replay.py:811-813 asserts core.ports._allocated and core._sessions membership; test_supervisor_manual_retry.py:69 reads recovery._in_flight_tasks; test_supervisor_status_truth.py:119 injects core._sessions[profile] directly.; Shortcuts bypass the surface under test: test_artifacts_api.py:105 mutates env['client'].app.state.artifact_service.max_artifact_bytes = 8 to force a 413; test_sse_epoch_integration.py:122-132 injects an event by publishing through app.state.coordinator.broadcaster instead of provoking it via the API; test_recovery_snapshot_failure.py:31 calls coordinator._load_profile_config; test_supervisor_gateway_fixture_auth.py:32 and test_supervisor_gateway_client.py read site._server.sockets.; Several supervisor tests construct SimpleNamespace fake cores (test_supervisor_manual_retry.py, test_supervisor_start_capacity.py, test_supervisor_status_truth.py), so the coordinator runs against hand-shaped partial doubles of SupervisorCore.
  - Impact: Refactors that preserve behavior break tests (false failures), and internal-state assertions can stay green while the externally visible behavior is wrong; the fake-core tests silently stop matching SupervisorCore's real attribute surface as it evolves.
  - Fix: Where a public observable exists (API runtime state, WS frames, socket counts via /proc), assert on it; where internals are unavoidable, confine them to one helper with a comment naming the invariant, and prefer constructing the real SupervisorCore over SimpleNamespace cores.

- [Medium][80] tests/fixtures/gateway_probe/topology.py:27-42 — Free-port selection is TOCTOU and several probes bind fixed host ports, so parallel or repeated runs collide
  - ID: f_tests_integration_fixtures_06; verification: static
  - Evidence: topology.py find_free_port binds a socket, closes it and returns the number; GatewayTopologyHarness picks caddy/coturn host ports in __init__ (lines 139-140) long before containers start, leaving a wide race window; the same pattern is copy-pasted in offline_fixture.py:103-106, test_gateway_fixtures.py find_free_port, test_runtime_coordinator_integration.py, test_v2_api_subprocess.py and test_automation_cdp_flow.py.; Every topology instance publishes the full TURN relay range on the host (topology.py:281-299: ports 50000-50040/udp bound to 127.0.0.1), so two harnesses on one host cannot coexist.; stream_probe/chrome_relay.py:64-71 binds fixed host ports 34861 and 42100-42140; ice_pending_close.py:41, ice_restart_failure.py:42 and ice_turn_timeout.py:41 all open UdpMux(30028).
  - Impact: Running suites in parallel (or a stale container/process still holding a port) fails with bind errors unrelated to the code under test; flaky infrastructure failures erode trust in the E2E lanes.
  - Fix: Prefer Docker-assigned host ports (publish without a host port and read back the mapping, as the harnesses already do for API/gateway/supervisor), parameterize the mux and TURN ports per run, and drop fixed host port bindings where the check does not specifically need them.

- [Medium][90] tests/integration/test_v2_api_subprocess.py:29-35 — Several integration tests keep state in the repo .scratch directory instead of tmp_path, coupling runs and polluting the workspace
  - ID: f_tests_integration_fixtures_07; verification: static
  - Evidence: test_v2_api_subprocess.py creates SCRATCH_DIR at import time (lines 29-35, module-level mkdir) and a new test_run_<millis> directory per fixture invocation (line 143) that is never removed; UV cache and TMPDIR of the server subprocess also point into .scratch.; test_automation_cdp_flow.py:88,244 works under Path('.scratch/t008_uds_flow') / '.scratch/t008_agent_flow' relative to the process cwd.; test_normal_exit_replay.py accepts the tmp_path fixture in all four tests (lines 142, 294, 438, 634) but never uses it, building data roots under .scratch/normal_exit_fix instead, and its finally blocks call shutil.rmtree(data_root) without ignore_errors, so a cleanup failure can mask the real test outcome.
  - Impact: Leftover state from previous (possibly failed) runs sits in the repo, test behavior depends on cwd and on what earlier runs left behind, and .scratch grows unboundedly with per-run databases and logs.
  - Fix: Use tmp_path/tmp_path_factory for all per-test state (the fixtures already receive it), remove the import-time mkdir, and make cleanup best-effort (ignore_errors or a fixture finalizer) so it cannot mask assertion failures.

- [Medium][65] tests/fixtures/supervisor_container_probe/api_runtime.Dockerfile:4-14 — Fixture runtime Dockerfiles duplicate production packaging with hand-maintained subsets; the api_runtime .dockerignore does not whitelist the auth package its Dockerfile copies
  - ID: f_tests_integration_fixtures_08; verification: suspected
  - Evidence: api_runtime.Dockerfile pins its own dependency versions and COPYs a hand-picked subset of src/backend/cbrowser (gateway, api, auth, domain, services, adapters), duplicating the production images under config/docker/; gateway_runtime.Dockerfile does the same for the gateway probe.; api_runtime.Dockerfile.dockerignore excludes everything ('**') and re-includes listed paths, but contains no entry for src/backend/cbrowser/auth even though api_runtime.Dockerfile:11 COPYs that package (auth contains service.py, dependencies.py, rate_limiter.py, client_ip.py).; The same .dockerignore admits domain/ and services/ only as top-level '*.py' while sibling packages use '/**', so adding a subpackage to domain or services would silently drop it from the test image.
  - Impact: The 'real Docker topology' lanes can build an image whose code subset differs from production (or fail to build after a routine package change), and version pins drift from the production dependency set without any test noticing.
  - Fix: Build fixture images FROM the production Dockerfiles (or a shared base) and only add probe entrypoints; if a subset image is intentional, generate the copy list and .dockerignore from the package layout and add a CI check that the whitelist covers every COPY source.

- [Medium][80] tests/fixtures/supervisor_container_probe/gateway_container.py:14-31 — Container entrypoint for the gateway fixture bypasses the fixture's own lifecycle and contradicts its contract doc; fixture start() also swallows startup failure
  - ID: f_tests_integration_fixtures_09; verification: static
  - Evidence: gateway_contract.md:18 states the fixture 'Always binds 127.0.0.1:{port}' and section 5 defines lifecycle through start()/stop(); gateway_container.py instead pokes privates (gateway._app, gateway._runner, gateway._site) and binds TCPSite on 0.0.0.0.; In that container path SupervisorGatewayFixture.stop() is a no-op: stop() (gateway_fixture.py:418-471) only cleans up when self._loop is running, but the container entrypoint never sets _loop/_thread, so the runner/site it created are never cleaned by stop().; gateway_fixture.py:415 awaits ready_event.wait with a 10s timeout but ignores the boolean result; if the server thread fails to bind, start() returns as if ready and callers fail later with unrelated connection errors.
  - Impact: The documented fixture contract does not describe the container deployment that blackbox tests actually run, and startup failures are reported far from their cause.
  - Fix: Give the fixture an explicit host parameter and a start_in_loop/run-standalone entry used by the container script; check the ready_event result in start() and raise with the bind error; update gateway_contract.md to describe the container binding.

- [Low][90] tests/integration/test_normal_exit_replay.py:38 — Inter-test coupling: fixtures are imported from sibling test modules instead of living in conftest/shared fixtures
  - ID: f_tests_integration_fixtures_10; verification: static
  - Evidence: pytest_plugins = ('test_supervisor_rpc',) in test_normal_exit_replay.py:38, test_supervisor_observation_authority.py:25 and test_supervisor_status_truth.py:13 makes the supervisor_api fixture available only if that test module imports cleanly.; test_supervisor_manual_retry.py:10 and test_supervisor_start_capacity.py:14 do 'from test_supervisor_rpc import supervisor_api as supervisor_api', which depends on pytest's rootdir sys.path insertion and executes the module (including its importlib loader boilerplate) at collection time.; test_gateway_control.py, test_gateway_rotation.py and test_gateway_signaling.py each do sys.path.insert(0, <test dir>) then 'from test_gateway_fixtures import GatewayHarness'.; The importlib spec-loader snippet for fixtures/api_auth.py is copy-pasted into four files (offline_fixture.py, test_runtime_coordinator_integration.py, test_supervisor_rpc.py, test_v2_api_subprocess.py) instead of a package import or conftest helper.
  - Impact: Renaming, moving or breaking one test module breaks unrelated modules at collection; fixture provenance is hard to trace, and duplicated loader code drifts.
  - Fix: Move supervisor_api and the api_auth loader into tests/conftest.py or a tests/fixtures package import, and import GatewayHarness via the fixtures package path consistently.

- [Low][75] tests/integration/test_gateway_signaling.py:545-581 — A few assertions are tolerant or wall-clock-threshold based, weakening or destabilizing the oracle
  - ID: f_tests_integration_fixtures_11; verification: static
  - Evidence: test_gateway_signaling.py:551-556 accepts an optional 'visibility_update' control packet before the expected tunnel message, so two different gateway behaviors both pass a test whose stated purpose is that viewer frames never reach the agent as control.; tests/fixtures/supervisor_resource_probe/stream_monitor.py:86,100-102 asserts absolute decoded-frame thresholds (capped <= 24 frames/2s, restored > 30) against a real Chrome decoder on shared hardware.; test_v2_api_subprocess.py AC-004 asserts wall-clock windows (elapsed 1.4-4.5s and 4.5-6.5s) around SQLite lock contention; under load these can flake even though the busy-timeout behavior is correct.
  - Impact: The tolerant branch can mask a regression in frame filtering; threshold-based checks produce intermittent failures that train developers to ignore the E2E lanes.
  - Fix: Remove the optional-packet branch (assert the first agent packet is the tunnel message, as the sibling test in test_gateway_control.py does), and replace absolute frame/time thresholds with relative or repeated-sample criteria where the property allows it.

- [Low][85] tests/fixtures/gateway_probe/topology.py:141-151 — Fixture secret handling: world-writable secret-bearing directories, world-readable TURN secret config, a 0777 shared-memory probe segment, and unredacted evidence dumps
  - ID: f_tests_integration_fixtures_12; verification: static
  - Evidence: topology.py _init_dirs_and_secrets chmods control_dir, data subdirs and metadata_dir to 0o777 (lines 143-151) while the key files inside control_dir are 0o600; directory write permission lets any local user replace the key files the containers will trust.; turnserver.conf containing static-auth-secret is chmod 0o644 in topology.py:270, frontend_probe/harness.py:194 and written the same way in chrome_relay.py (config written then chmod 0o644).; tests/fixtures/runtime_probe/test_mitshm.c:68 creates the probe's SysV segment with IPC_CREAT | 0777 — world-accessible shared memory inside a probe whose purpose is verifying isolation.; gateway_probe/evidence.py save_evidence dumps arbitrary payloads as JSON into .scratch/t006_relay/evidence by default with no redaction hook.
  - Impact: Test-only and localhost-scoped, but the fixtures run on developer/CI machines with real Docker access; permissive modes normalize weak secret handling and could leak TURN credentials or session-bearing evidence payloads to other local users.
  - Fix: Use 0o700 for control/metadata dirs (containers run as root or with explicit uid mapping in these harnesses), 0o600 for turnserver.conf, 0600 for the shm segment (the X server access pattern does not require world permissions), and document/redact what save_evidence may contain.

- [Low][85] tests/fixtures/stream_probe/clipboard_oracle.py:7-9 — Probes depend on private APIs of the pinned Selkies library (underscore classes and internals), so a Selkies bump can break the test rig without any production change
  - ID: f_tests_integration_fixtures_13; verification: static
  - Evidence: clipboard_oracle.py:7 imports selkies.input_handler._X11ClipboardMonitor and drives it as the clipboard sentinel oracle.; x11_keymap_probe.py:6-14 imports selkies.input_handler._XTestKeyboard, asserts on the identity of its prebind attribute and reads keyboard._overlay.; ice_* probes and rtc_config_relay_only.py read selkies internals such as pc._RTCPeerConnection__iceTransports and gatherer._connection._local_candidates (the latter is monkeypatched to inject candidates).
  - Impact: These probes are the acceptance evidence for clipboard, keymap and ICE behavior; if a Selkies 2.1.x update renames internals, the rig fails (or is quietly dropped) even though production behavior is unchanged.
  - Fix: Pin and note the coupling in each probe header (some already do), wrap Selkies-internal access in one small adapter module per probe family, and treat probe breakage on Selkies bumps as a rig-update task rather than a product failure.

- [Low][90] tests/fixtures/frontend_probe/host_builder.py:17-31 — ensure_frontend_build claims to ensure an up-to-date build but only checks that dist files exist, so frontend E2E can silently run against a stale production build
  - ID: f_tests_integration_fixtures_14; verification: static
  - Evidence: host_builder.py:18 docstring: 'Ensures Vite production build exists and is up to date'; the implementation (lines 20-31) only tests for the presence of dist/index.html, dist/selkies and selkies_adapter.js and never compares source mtimes or hashes.; prepare_frontend_host then serves whatever dist contains, and picks the stylesheet as css_files[0] from an unsorted glob (line 68).
  - Impact: A developer who changed frontend sources without rebuilding gets green E2E results for code that is not what they edited — a false-confidence oracle for the frontend lane (the app-probe variant raises on missing build but has the same staleness blind spot).
  - Fix: Either always rebuild in the harness, or record and compare a source hash/mtime manifest and rebuild when stale; adjust the docstring to match the actual guarantee.

## views

```json
{
  "security": {
    "status": "completed",
    "reviewer": "fc0c55d8-42b8-467a-ab01-3d2fd61033dc"
  },
  "correctness": {
    "status": "completed",
    "reviewer": "fc0c55d8-42b8-467a-ab01-3d2fd61033dc"
  },
  "contracts": {
    "status": "completed",
    "reviewer": "fc0c55d8-42b8-467a-ab01-3d2fd61033dc"
  },
  "performance": {
    "status": "completed",
    "reviewer": "fc0c55d8-42b8-467a-ab01-3d2fd61033dc"
  },
  "design": {
    "status": "completed",
    "reviewer": "fc0c55d8-42b8-467a-ab01-3d2fd61033dc"
  },
  "robustness": {
    "status": "completed",
    "reviewer": "fc0c55d8-42b8-467a-ab01-3d2fd61033dc"
  },
  "tests": {
    "status": "completed",
    "reviewer": "fc0c55d8-42b8-467a-ab01-3d2fd61033dc"
  },
  "documentation": {
    "status": "completed",
    "reviewer": "fc0c55d8-42b8-467a-ab01-3d2fd61033dc"
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
  "tests/fixtures/stream_probe/chrome_relay.py",
  "tests/fixtures/stream_probe/clipboard_oracle.py",
  "tests/fixtures/stream_probe/ice_commit_outcome.py",
  "tests/fixtures/stream_probe/ice_pending_close.py",
  "tests/fixtures/stream_probe/ice_relay_generations.py",
  "tests/fixtures/stream_probe/ice_restart_failure.py",
  "tests/fixtures/stream_probe/ice_turn_timeout.py",
  "tests/fixtures/stream_probe/media_page.html",
  "tests/fixtures/stream_probe/rtc_config_apply.py",
  "tests/fixtures/stream_probe/rtc_config_relay_only.py",
  "tests/fixtures/stream_probe/web_lock_shim.js",
  "tests/fixtures/stream_probe/x11_keymap_probe.py",
  "tests/fixtures/supervisor_container_probe/api_runtime.Dockerfile",
  "tests/fixtures/supervisor_container_probe/api_runtime.Dockerfile.dockerignore",
  "tests/fixtures/supervisor_container_probe/gateway_container.py",
  "tests/fixtures/supervisor_container_probe/gateway_runtime.Dockerfile",
  "tests/fixtures/supervisor_container_probe/gateway_runtime.Dockerfile.dockerignore",
  "tests/fixtures/supervisor_recovery_probe/gateway_contract.md",
  "tests/fixtures/supervisor_recovery_probe/gateway_fixture.py",
  "tests/fixtures/supervisor_recovery_probe/offline_fixture.py",
  "tests/fixtures/supervisor_resource_probe/cpu_burner.py",
  "tests/fixtures/supervisor_resource_probe/stream_monitor.py",
  "tests/integration/test_api_sse_events.py",
  "tests/integration/test_artifacts_api.py",
  "tests/integration/test_auth_api.py",
  "tests/integration/test_automation_api.py",
  "tests/integration/test_automation_cdp_flow.py",
  "tests/integration/test_gateway_control.py",
  "tests/integration/test_gateway_fixtures.py",
  "tests/integration/test_gateway_rotation.py",
  "tests/integration/test_gateway_signaling.py",
  "tests/integration/test_normal_exit_replay.py",
  "tests/integration/test_profile_copy_reset_api.py",
  "tests/integration/test_profile_patch_semantics.py",
  "tests/integration/test_recovery_snapshot_failure.py",
  "tests/integration/test_runtime_coordinator_integration.py",
  "tests/integration/test_sse_epoch_integration.py",
  "tests/integration/test_supervisor_gateway_client.py",
  "tests/integration/test_supervisor_gateway_fixture_auth.py",
  "tests/integration/test_supervisor_manual_retry.py",
  "tests/integration/test_supervisor_observation_authority.py",
  "tests/integration/test_supervisor_rpc.py",
  "tests/integration/test_supervisor_start_capacity.py",
  "tests/integration/test_supervisor_status_truth.py",
  "tests/integration/test_v2_api_subprocess.py"
]
```
