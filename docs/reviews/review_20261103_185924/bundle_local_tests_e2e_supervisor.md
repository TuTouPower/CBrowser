# bundle_local_tests_e2e_supervisor

## responsibilities

- End-to-end verification of the Supervisor subsystem against real Docker, a real API process (uvicorn + SQLite) and the production Gateway: dual-profile sandbox lifecycle, container/network ownership and isolation, kernel network policy (namespace + IPv6), startup gate sentinel, SIGKILL/offline recovery with event-spool replay, 3-strikes retry backoff, resource sampling/monitoring policy, cache initialization, orphan-helper reaping, and graceful Supervisor CLI shutdown on SIGTERM.
- Shared gates and helpers: tests/e2e/conftest.py provides the required-mode prerequisite gate (CBROWSER_E2E_REQUIRED) and the real_api_server fixture (real uvicorn subprocess, per-test Bearer token file at 0600, proxy env stripped); tests/fixtures/e2e_env.py is the single source of truth for required image/cache env vars (sha256-pinned) and a free-UDP-span probe; tests/fixtures/wait.py provides bounded polling helpers whose stated contract is that helpers remove races while callers keep the contract assertions.

## interfaces

- Supervisor control HTTP API (/supervisor/v1/profiles/start|stop|status, /supervisor/v1/health, /supervisor/v1/profiles/{id}/resources) exercised over real HTTP with Bearer token files.
- API public/internal HTTP surface (/api/v1/profiles, /runtime/desired-state, /api/v1/internal/supervisor/profiles/{id}/runtime, /runtimes/bind, /runtimes/events) plus read-only SQLite inspection of runtime_events as an observation channel.
- Docker SDK surface: container/network labels com.cbrowser.prefix / managed-by / role / profile-id / instance-id are used as the ownership contract for creation, reconciliation and cleanup assertions.
- In-container Agent UDS (/run/cbrowser/runtime/agent.sock /health and /control) used as the liveness/close oracle inside Browser containers.

## dependencies

- Production code under review-by-proxy: cbrowser.supervisor (core, docker_adapter, recovery_coordinator, resource_policy/monitor, network_policy, startup_gate, control_server), cbrowser.gateway.endpoint, cbrowser.domain.models, cbrowser.runtime_agent.event_storage.
- Out-of-unit test support packages taken as given (not read in this unit): tests/support-style helpers supervisor_recovery_probe (offline_fixture, gateway_service), gateway_probe.topology, api_auth.create_auth_context, scripts.verify_frontend_dist.
- External environment: Docker daemon, sha256-pinned test images and engine/GeoIP caches supplied via CBROWSER\_\* env vars; one namespace-policy assertion additionally requires live public Internet egress.

## flows

- Start flow: create profile in real API -> set desired_state=running -> Supervisor start -> Browser+Stream containers created behind startup gate (ready.json) with per-profile networks and run-local UDP mux ports -> Stream agent registers with Gateway.
- Failure/recovery flows: Browser SIGKILL -> API failure_count increments with durable updated_at -> backoff retry (2s/10s/30s) -> 4th failure sets restart_blocked -> manual reset_blocked recovers; Supervisor SIGKILL -> containers keep running -> restarted Supervisor rescans by prefix labels and re-adopts sessions with identical ports/instance ids.
- Event flow: native exit journal/spool file -> EventForwarder POST /runtimes/events (503 fault injection in startup_recovery) -> spool retained while API offline -> replay on API return; diagnostic events are asserted to be persisted exactly once in runtime_events yet never to mutate desired/observed business state (A1 authoritative-observation semantics).
- Policy flow: one-shot NET_ADMIN helper container installs kernel policy into the target netns and exits; probes then verify allowed TCP still passes while unlisted ports, unauthorized peers, other bridges, CGNAT/benchmark ranges and IPv6 ULA are blocked, and a non-target namespace stays unmodified.

## constraints

- Static review only: no test was executed; all statements about runtime behaviour are read from the test code and its assertions, not from a run.
- The suite is inherently wall-clock heavy (real containers plus real 2s/10s/30s retry backoffs and multi-second burns); the performance view therefore only notes suite-level cost, there is no production code in this unit.
- Token/key files in the tests are consistently written with 0600 permissions and asserted so (container_graph also stat-asserts 0600); no credential values appear anywhere in the unit — tokens are generated per test with secrets.token_urlsafe(32). No finding reproduces any credential.

## decisions

- Tests deliberately drive production implementations end-to-end (real SupervisorCore/DockerAdapter/EventForwarder, real API subprocess, production Gateway service) instead of mocks; the only fakes are leaf probes (FakeContainer for the log-wait helper, a MagicMock auth context in the fixture self-test).
- Node-replacement instead of in-place assertion edits is practised and documented in container_graph's header (deprecated 18097-era node replaced by the authoritative-gateway-port node with a coverage note).
- Cleanup is treated as part of the contract: prefix-labelled resources are enumerated in finally blocks, ownership violations are distinguished from cleanup errors (container_graph), and several tests assert zero leaked containers/networks after teardown.

## evidence

- tests/e2e/test_supervisor_container_graph_e2e.py: full containerised API+Gateway+Supervisor topology, duplicate-start idempotency, docker.sock held only by Supervisor, SIGKILL/restart reconciliation with identical container ids and browser PIDs.
- tests/e2e/test_supervisor_offline_recovery_e2e.py: genuine API process stop (connection refused verified), spool persistence across Supervisor SIGKILL, automatic replay, read-only SQLite proof of exactly-once diagnostic ingestion, negative diagnostic probe against live Profile B.
- tests/e2e/test_supervisor_namespace_policy_e2e.py: positive control (control container reaches server before policy), allowed/blocked port matrix, helper persistence after removal, unmodified bystander namespace check.
- tests/e2e/test_supervisor_ipv6_policy_e2e.py: before-policy positive control (echo_ok True, TCP PONG) then after-policy echo denied with TCP preserved; second policy install refused with exit code 3.
- tests/fixtures/wait.py:1-8 states the bounded-polling contract the rest of the unit is measured against.

## uncertainties

- Internals of supervisor_recovery_probe/\*, gateway_probe.topology.cleanup_prefixed_resources, api_auth.create_auth_context and scripts.verify_frontend_dist are outside this unit's file list and were not read; claims that depend on them (e.g. RealSupervisorContainer.sigkill semantics, cleanup completeness) are taken from the call sites' usage and naming.
- Whether CBROWSER_E2E_REQUIRED=1 is ever run on a non-macOS host is not evidenced inside the unit; finding f_tests_e2e_supervisor_03's impact is conditional on that (the gate code itself is unconditional).
- docker-py semantics of calling containers.list on a client after close() (finding f_tests_e2e_supervisor_09) depend on the pinned docker SDK version, which is not part of this unit; hence suspected, not static-confirmed.

## Findings

- [Medium][95] tests/e2e/test_supervisor_startup_recovery_e2e.py:15-21 — Module docstring states the opposite of the asserted A1 semantics for native-exit spool replay

    - ID: f_tests_e2e_supervisor_01; verification: static
    - Evidence: File header, Case 3 (lines 19-21): 'Once the proxy allows normal forwarding, spool replay delivers the normal exit, converging the profile runtime to stopped with no restart.'; The test body asserts the reverse (lines 457-475): after replay_spooled_events() returns 1, the runtime still has runtime_instance_id == native_inst, observed_state == 'starting', failure_count == 0 and last_exit_event_id is None, with the comment 'Disk events are diagnostics and must not converge lifecycle state.'; The sibling suite encodes the same A1 rule explicitly (offline_recovery asserts last_exit_event_id stays None for normal exits because it is 'strictly an abnormal retry fence'), confirming the docstring, not the assertion, is the stale side.
    - Impact: The file header is the stated contract for the suite; a reader (or a future editor 'fixing' the test to match the docstring) would reintroduce exactly the bug A1 removed — a diagnostic disk journal entry converging lifecycle state to stopped. Documentation/implementation contradiction on a safety-relevant semantic.
    - Fix: Rewrite Case 3 in the module docstring to the A1 semantics actually asserted: the replayed native-exit event is persisted as a diagnostic, the bound runtime is left untouched (no convergence to stopped, no last_exit_event_id), and missing-runtime synthesis is suppressed while a native exit is registered.

- [Medium][85] tests/fixtures/wait.py:1-8 — Shared bounded-polling helpers are unused by this unit; waits are ad-hoc loops and fixed sleeps, including before contract assertions

    - ID: f_tests_e2e_supervisor_02; verification: static
    - Evidence: No file in the unit imports wait_until/poll_until/wait_for_log/wait_until_sync (grep over tests/e2e/test_supervisor\_\*.py and conftest.py returns no match), although wait.py exists precisely to remove trigger/observation races.; Hand-rolled duplicates: test_supervisor_core_e2e.py:201 and :228 (two 'for _ in range(50)' + sleep(0.2) registration waits with no timeout diagnostic), test_supervisor_recovery_e2e.py (three separate 100-iteration health loops), test_supervisor_container_graph_e2e.py defines its own ready() helper, test_supervisor_event_shutdown_e2e.py hand-polls health and log contents.; Fixed delays used as synchronisation before assertions: test_supervisor_offline_recovery_e2e.py:253, :290, :312 ('await asyncio.sleep(2.0)' before asserting spool retention / companion health) and test_supervisor_policy_failure_e2e.py:180 ('await asyncio.sleep(0.5)' after replay_spooled_events() before asserting API failure state).
    - Impact: Fixed sleeps make pass/fail depend on host load: a slower Supervisor makes the offline-recovery retention checks read state before the system has acted (false confidence) or after a transient has passed; the duplicated loops each encode different timeouts and none reports the last observed value on timeout, so failures are hard to diagnose. This is the exact flake class wait.py's docstring says the helpers exist to eliminate.
    - Fix: Route the unit's readiness/state waits through tests/fixtures/wait.py (poll_until/wait_for_log with the last value in the timeout message), and replace the offline_recovery/policy_failure fixed sleeps with polls on the observable condition (spool file presence over a window, API runtime fields reaching the expected values).

- [Medium][90] tests/e2e/conftest.py:22-28 — Required-mode gate demands the macOS Chrome app path for the whole E2E session, blocking the Docker-only supervisor suite on any non-macOS host

    - ID: f_tests_e2e_supervisor_03; verification: static
    - Evidence: \_missing_requirements() unconditionally appends 'Google Chrome at /Applications' when /Applications/Google Chrome.app/Contents/MacOS/Google Chrome is absent (lines 22-28).; pytest_collection_modifyitems calls pytest.exit(returncode=2) with that list whenever CBROWSER_E2E_REQUIRED=1 and anything is missing (lines 41-47); the check is not scoped to items that launch a local browser.; No test in this unit uses a host Chrome binary — all browsers run inside the pinned runtime image; the same hook already demonstrates item-scoped gating by special-casing 'frontend' items for the dist-freshness check (lines 33-39).
    - Impact: On a Linux CI runner (the natural host for a Docker-based suite, and the Supervisor's own production environment) required mode can never start: the session exits before any supervisor test runs, so the fail-closed gate silently disables the entire E2E safety net outside one developer's Mac.
    - Fix: Scope the Chrome prerequisite to the items that need it (e.g. only frontend items, mirroring the existing dist-freshness branch), or drop the host-Chrome check from the supervisor collection path and let the frontend unit own it.

- [Low][90] tests/e2e/test_supervisor_startup_recovery_e2e.py:246 — Assertions and driving hooks coupled to private internals of SupervisorCore/RecoveryCoordinator

    - ID: f_tests_e2e_supervisor_04; verification: static
    - Evidence: test_supervisor_startup_recovery_e2e.py:246 drives core.\_get_profile_lock(profile_id) to manufacture the lock-held case; :280 asserts 'profile_id in coordinator.\_in_flight_tasks'; :455 asserts 'native_inst not in coordinator.\_reported_dead_instances'; the flow at :431 depends on core.has_native_exit backed by \_native_exit_instances.; test_supervisor_resource_monitor_e2e.py asserts observed[-1]['container_samples'][0][3] == 500_000_000, a positional tuple index into the monitor's internal sample record.
    - Impact: The behavioural outcomes are also asserted through the API, but the private-state assertions make the suite fail on internal refactors that preserve behaviour (renaming the in-flight registry, changing the sample tuple shape), and the lock case can only be produced by reaching into Core — the test's maintenance cost tracks implementation details rather than the contract.
    - Fix: Where an equivalent observable signal exists, assert on it (API runtime fields, supervisor status endpoint); keep private access only where no external oracle exists and mark those spots with a comment naming the missing public seam.

- [Low][95] tests/e2e/test_supervisor_retry_e2e.py:7-14 — Retry suite docstring describes a subprocess harness and a -9 returncode check that the test does not contain

    - ID: f_tests_e2e_supervisor_05; verification: static
    - Evidence: Docstring lines 7 and 13-14: 'Real independent Supervisor subprocess (RealSupervisorProcess running cbrowser.supervisor.runner)' and 'SIGKILL Supervisor subprocess (verifying returncode == -9)'.; Implementation imports RealSupervisorContainer (line 55) and constructs it at line 170; the mid-backoff kill is sup_proc.sigkill() on the container and the only identity assertion is that the restarted container id differs — no returncode is ever read.
    - Impact: A reader trusting the header believes exit-code -9 propagation is covered when it is not; if runner-level SIGKILL exit semantics regress, this suite would not notice despite claiming to verify them.
    - Fix: Update the docstring to the container harness actually used and drop the returncode claim, or add the returncode assertion where a real subprocess is used (the event_shutdown suite covers CLI SIGTERM exit 0 separately).

- [Low][80] tests/e2e/test_supervisor_container_graph_e2e.py:83 — Topology test chmods data and metadata directories to 0777 while elsewhere asserting strict 0600/0700 hygiene

    - ID: f_tests_e2e_supervisor_06; verification: static
    - Evidence: Lines 80-83: control dir is chmod 0700, then profiles/runtime/runtime-events/artifacts/spool are created and chmod'ed 0o777; line 99 chmods the API metadata dir (holding control.db) 0o777.; The same file carefully asserts key files are exactly 0600 (lines 92-96) and that secret mounts are read-only and absent from the Browser container, i.e. least-privilege is part of the contract being modelled.
    - Impact: On a shared Docker host, world-writable spool/runtime/metadata directories let another local user inject spool events or tamper with the control DB the test treats as authoritative; it also normalises 0777 as the way to make multi-container sharing work, which can leak into deployment examples copied from the test.
    - Fix: Use the owning uid/gid or ACLs/group permissions actually required by the container users instead of 0777, or add a comment stating 0777 is a test-only concession and which production mechanism replaces it.

- [Low][85] tests/e2e/test_supervisor_namespace_policy_e2e.py:530 — Hard assertion on live public Internet egress (1.1.1.1:80) makes the policy suite fail in offline environments

    - ID: f_tests_e2e_supervisor_07; verification: static
    - Evidence: Step 6 (lines 528-533) probes 1.1.1.1:80 from inside the target container and asserts success ('Public IPv4 egress was blocked'), with a 3.0s timeout.; Unlike the image/cache prerequisites, this environmental dependency has no gate: require_e2e_env can fail/skip for missing images, but nothing checks or skips for egress availability before the assertion.
    - Impact: In sandboxed CI or any offline development environment the kernel-policy suite fails for reasons unrelated to the policy under test, training developers to ignore or skip the whole file — including its isolation assertions.
    - Fix: Gate the public-egress step on an explicit env flag or a reachability pre-check that skips only that step, keeping the isolation assertions mandatory.

- [Low][90] tests/e2e/test_supervisor_container_graph_e2e.py:371-380 — Stream secret-mount read-only guarantee is conditional; disappearance of the mount would pass silently

    - ID: f_tests_e2e_supervisor_08; verification: static
    - Evidence: Lines 371-380: for '/tmp/secret.txt' and '/tmp/selkies_credentials.json', the read-only assertion runs only 'if sec_target in stream_destinations'; the unconditional part asserts only that the targets are absent from the Browser container's mounts.; The credential file is a live secret channel (Selkies credentials), so its mount mode in the Stream container is one of the isolation invariants this test exists to prove.
    - Impact: A regression that drops the credentials mount from the Stream container (breaking authenticated streaming) — or remounts it under a different destination — evades this assertion entirely; the test would still pass while the invariant it names is gone.
    - Fix: Assert the expected presence set explicitly: require the credentials destination to exist in the Stream mounts with RW False, and keep the browser-absence assertion as is.

- [Low][60] tests/e2e/test_supervisor_ipv6_policy_e2e.py:150-154 — Zero-leak assertion runs on the Docker client after the finally block has closed it

    - ID: f_tests_e2e_supervisor_09; verification: suspected
    - Evidence: The finally block ends with client.close() (line 150); the statement after the try/finally, 'assert not client.containers.list(all=True, filters=...)' (lines 152-154), reuses that closed client for the leak check.; Whether a closed docker-py client still serves requests depends on the SDK version's session handling, which is not pinned anywhere in this unit.
    - Impact: The test's final leak guarantee may raise a client error instead of verifying cleanup, or behave differently across docker SDK upgrades — the assertion most meant to catch leaked containers is itself the fragile one.
    - Fix: Move the leak assertion inside the try (before close) or perform it with a fresh client, so the check runs against a live connection.

- [Info][85] tests/e2e/test_supervisor_policy_failure_e2e.py:127 — Dummy gateway endpoints and image-digest strictness drift across files, obscuring which values are contractual

    - ID: f_tests_e2e_supervisor_10; verification: static
    - Evidence: policy_failure constructs SupervisorCore with gateway_url='ws://127.0.0.1:18097' (line 127) — the legacy port that container_graph's header says was deprecated and replaced for asserting stale assumptions; startup_recovery uses 'ws://127.0.0.1:9999' for the same never-connected purpose.; Digest validation alternates between requiring startswith('sha256:') (most files) and accepting 'sha256:' anywhere via '@sha256:' in test_supervisor_orphan_helpers_e2e.py and policy_failure's \_get_required_env_image.
    - Impact: No behavioural impact in these tests (the gateway URL is never dialled in the failure path), but the drift makes it unclear whether 18097 still has meaning anywhere, and weakens the otherwise uniform 'immutable digest' gate the suite advertises.
    - Fix: Use one obviously-dummy gateway URL constant for never-connected cores and one shared digest assertion helper in e2e_env.py.

- [Info][95] tests/e2e/test_supervisor_policy_failure_e2e.py:59 — Stale fixture type annotation: real_api_server annotated as a 3-tuple while conftest yields 4 values

    - ID: f_tests_e2e_supervisor_11; verification: static
    - Evidence: policy_failure annotates the parameter 'real_api_server: tuple[str, str, Path]' (line 59) and immediately unpacks four values (api_url, auth_token, token_file, auth_headers).; conftest.py's real_api_server yields exactly that 4-tuple (api_url, token, token_file, auth_headers).
    - Impact: Cosmetic but misleading for anyone editing the fixture contract; type checkers over the test tree would flag or, worse, silently accept the wrong shape elsewhere.
    - Fix: Update the annotation to tuple[str, str, Path, dict] (or drop it, as the other consumers do).

- [Info][65] tests/fixtures/e2e_env.py:41-57 — free_udp_port_span probes then releases the ports, so the returned span is not reserved (TOCTOU)

    - ID: f_tests_e2e_supervisor_12; verification: suspected
    - Evidence: free_udp_port_span binds the candidate UDP sockets, then closes them all in the finally block before returning the base port (lines 45-56); callers (core, recovery, retry, offline suites) treat the span as theirs for PortAllocator ranges minutes later.; Only UDP is probed; nothing rechecks the span at allocation time inside the helper.
    - Impact: On a busy host another process can claim a probed port between the probe and the Supervisor's bind, producing rare, hard-to-reproduce E2E flakes that look like allocator bugs. In the isolated environments the suite targets this is unlikely, hence Info.
    - Fix: Document the race in the docstring as an accepted test-only limitation, or have callers retry start-up on bind failure with a fresh span.

## views

```json
{
  "contracts": {
    "reviewer": "52de8dfc-5ded-4a0a-b56d-1bfec0356011",
    "status": "completed"
  },
  "correctness": {
    "reviewer": "52de8dfc-5ded-4a0a-b56d-1bfec0356011",
    "status": "completed"
  },
  "design": {
    "reviewer": "52de8dfc-5ded-4a0a-b56d-1bfec0356011",
    "status": "completed"
  },
  "documentation": {
    "reviewer": "52de8dfc-5ded-4a0a-b56d-1bfec0356011",
    "status": "completed"
  },
  "performance": {
    "reviewer": "52de8dfc-5ded-4a0a-b56d-1bfec0356011",
    "status": "completed"
  },
  "robustness": {
    "reviewer": "52de8dfc-5ded-4a0a-b56d-1bfec0356011",
    "status": "completed"
  },
  "security": {
    "reviewer": "52de8dfc-5ded-4a0a-b56d-1bfec0356011",
    "status": "completed"
  },
  "tests": {
    "reviewer": "52de8dfc-5ded-4a0a-b56d-1bfec0356011",
    "status": "completed"
  }
}
```

## files_reviewed

```json
[
  "tests/e2e/conftest.py",
  "tests/e2e/test_supervisor_browser_network_e2e.py",
  "tests/e2e/test_supervisor_cache_initialization_e2e.py",
  "tests/e2e/test_supervisor_container_graph_e2e.py",
  "tests/e2e/test_supervisor_core_e2e.py",
  "tests/e2e/test_supervisor_event_shutdown_e2e.py",
  "tests/e2e/test_supervisor_ipv6_policy_e2e.py",
  "tests/e2e/test_supervisor_namespace_policy_e2e.py",
  "tests/e2e/test_supervisor_network_ownership_e2e.py",
  "tests/e2e/test_supervisor_offline_recovery_e2e.py",
  "tests/e2e/test_supervisor_orphan_helpers_e2e.py",
  "tests/e2e/test_supervisor_policy_failure_e2e.py",
  "tests/e2e/test_supervisor_recovery_e2e.py",
  "tests/e2e/test_supervisor_resource_capacity_e2e.py",
  "tests/e2e/test_supervisor_resource_monitor_e2e.py",
  "tests/e2e/test_supervisor_resource_policy_e2e.py",
  "tests/e2e/test_supervisor_retry_e2e.py",
  "tests/e2e/test_supervisor_startup_recovery_e2e.py",
  "tests/fixtures/e2e_env.py",
  "tests/fixtures/wait.py"
]
```
