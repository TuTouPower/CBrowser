# bundle_local_backend_supervisor

## responsibilities

- SupervisorCore (core.py) is the sole Docker-socket holder and lifecycle coordinator: idempotent dual-container (Browser+Stream) start/stop, UDP mux port allocation, API instance binding and observed-state reporting, disk runtime-event consumption, and resource sampling orchestration.
- DockerAdapter (docker_adapter.py) builds hardened container specs (pinned sha256 images, read-only rootfs, cap_drop ALL, no-new-privileges), per-profile bridge networks, a startup-gate directory with an atomically written ready.json, and installs the in-namespace iptables policy via a short-lived NET_ADMIN helper container before unblocking the gated entrypoint.
- RecoveryCoordinator + recovery_rules detect abnormal Browser exits from Docker scans and API state, synthesize terminal observations fenced by runtime_instance_id, and execute backoff retries (2s/10s/30s, block after 4 failures per cbrowser.domain.runtime_policy) with bounded cleanup-failure cooldowns.
- EventForwarder persists runtime events to a sha256-named disk spool before attempting delivery to /api/v1/internal/supervisor/runtimes/events, quarantines rejected/unreadable spool files, and replays the spool on reconnect; DownloadArtifactForwarder scans runtime-events download journals and forwards completed downloads to the API Artifact Service with a persisted processed-ID set instead of an mtime cursor.
- Control plane: control_server.py exposes a Bearer-token FastAPI app (health, start, stop, status, reset-blocked, resources, and a CDP WebSocket proxy to the per-profile Agent UDS); runner.py wires everything, holds the flock CoordinatorLock, runs uvicorn plus event-driven/30s-fallback reconciliation, recovery, spool/download forwarding and resource loops.
- Security support modules: PathValidator confines all profile/runtime/secret paths under the data root and rejects reserved profile ids; AgentCredentials derives per-instance HMAC-SHA256 Agent tokens from an external key file; SelkiesTokens writes per-instance credential files with 0600 via atomic replace; secrets are only ever read from files (read_secret_file) and held as SecretStr — no secret values are logged (log lines record error_type names only).

## interfaces

- Control API (protocol.py, extra='forbid' models): POST /supervisor/v1/profiles/start (StartProfileRequest/Response, udp_mux_port constrained to 30000-30991), POST /supervisor/v1/profiles/stop, GET /supervisor/v1/profiles/{id}/status, POST /supervisor/v1/profiles/reset-blocked (operation id via Idempotency-Key header, unlike start/stop which carry operation_id in the body), GET /supervisor/v1/profiles/{id}/resources, WS /supervisor/v1/profiles/{id}/cdp.
- API internal RPC (httpx, Bearer token re-read from token file per call): GET profiles list, GET profiles/{id}/runtime, GET profiles/{id}/versions/{version} (immutable snapshot, identity re-validated), POST runtimes/bind, POST runtimes/observed, POST runtimes/events, POST artifacts/downloads, PATCH profiles/{id}/runtime/desired-state (Idempotency-Key).
- Gateway control RPC (gateway_client.py): POST /gateway/v1/internal/profiles/{id}/disconnect|quota, GET .../visibility with strict bool validation of has_foreground_viewers.
- Agent UDS: GET /health over the per-profile agent.sock (via /proc/self/fd alias for long paths), validated as HealthResponse and identity-checked against profile/instance/config_version before any terminal observation is trusted.
- Container contract: labels com.cbrowser.{managed-by,prefix,profile-id,instance-id,role,config-version,network-policy}; startup gate CLI (startup_gate.py) waits for ready.json matching instance_id+role then os.execv the app; network policy CLI (network_policy.py) takes a NetworkPolicySpec JSON argv and installs iptables/ip6tables fail-closed rules in the target netns.

## dependencies

- Docker Engine via docker-py (sync client; all blocking calls wrapped in asyncio.to_thread) — the unit assumes it is the only Docker writer for its resource prefix.
- cbrowser.domain.models / runtime_policy (ProfileConfig, ConfigVersionSnapshot, RuntimeEventRecord, AUTO_RETRY_DELAYS=(2,10,30), BLOCK_AFTER_RUNTIME_FAILURES=4), cbrowser.runtime_agent.protocol (HealthResponse, DownloadEventRecord), cbrowser.gateway.endpoint (GatewayEndpoint), cbrowser.secret_files.read_secret_file — all outside this unit.
- FastAPI/uvicorn for the control server, websockets for the CDP proxy, httpx for API/Gateway/Agent RPC, pydantic v2 models throughout.
- Host environment: Linux flock, /proc/self/fd, /proc/stat (resource host sampling), iptables/ip6tables binaries inside the policy helper image, tini in runtime images.

## flows

- Start: control start -> fetch immutable config snapshot from API and verify identity -> core.start_profile (profile lock) -> check API desired_state/restart_blocked -> write snapshot.json (0600, chowned) -> API bind new inst_<uuid12> -> allocate port -> create profile network + attach Gateway -> report 'starting' -> start Browser container gated -> poll browser_runtime_ready up to ~30s (runner_info.json identity + X11/Pulse/Xauthority/agent.sock) -> write Agent token + Selkies credentials into the secret dir (0600) -> start Stream container gated -> wait for Gateway visibility registration (15s) -> report 'running'. Any failure: report terminal error observation, teardown, release port, emit startup_failure exit event, re-raise.
- Stop: control stop / reconcile / recovery cleanup -> OperationJournal.begin (durable idempotency) -> report 'stopping' -> best-effort Gateway viewer disconnect (2s) -> teardown containers+networks -> release port and forget instance state even on teardown failure -> report 'stopped' -> journal complete.
- Recovery: runner loop (1s tick, scan snapshot reused) -> classify terminated Browsers (skipping native-exit-pending and already-reported instances) -> synthesize exit observation from Docker ExitCode -> schedule retries from persisted API failure_count/updated_at with remaining-delay computation -> pre-wake revalidation of intent, exit-event id and failure_count -> cleanup old pair via journaled stop -> clear Chromium singleton locks -> start with the config_version bound to the failed instance.
- Reconciliation: Docker label scan -> per-profile integrity/fence checks against API runtime -> adopt healthy pairs (policy_ready gate with 60s unprotected grace, Gateway visibility probe, UDP port restore from Stream HostConfig) or tear down on desired=stopped / API 404; non-404 API errors always retain containers.
- Events: Agent writes runtime journals -> consume_disk_events validates (schema, profile/instance match, exit_code present) with per-instance (mtime_ns, name) cursors -> EventForwarder spool-then-send -> archive handled journals (bounded 200/instance); downloads follow the parallel artifact path.

## constraints

- Static review only: no code, tests or builds were executed; every finding is marked static or suspected and nothing here is runtime-verified.
- The unit ships no test files of its own; test coverage lives in other units (tests_*), so the tests view assesses testability and observed seams only.
- Single-process asyncio design: per-profile asyncio locks plus one global stop lock; the flock CoordinatorLock guarantees one Supervisor per data root, and several modules (OperationJournal, SelkiesTokens stale-file cleanup) rely on that single-writer assumption.
- Images must be pinned by sha256 digest (browser, stream, network-policy) or startup refuses; Agent key and Gateway control credentials are mandatory constructor inputs, control token file is mandatory before serving.

## decisions

- Fail-closed sandboxing: containers start behind a startup gate and cannot run their entrypoint until the network policy helper has installed iptables rules and the ready marker is written atomically (file_storage.atomic_write_text with fsync of file and directory).
- API is the authority for intent and failure accounting; the Supervisor never invents desired state — it synthesizes only terminal observations, fenced by (profile_id, runtime_instance_id, config_version) and deduplicated in-memory per generation.
- Events are persisted before delivery (spool-first), with sha256-of-event-id filenames so external identifiers never become path components; corrupt files are quarantined rather than blocking the queue.
- Deliberate split of pure decision logic (recovery_rules.py, network_spec.py, resource_policy.py state machines) from IO (core.py, docker_adapter.py, resource_monitor.py), which keeps the riskiest policies unit-testable without Docker.

## evidence

- src/backend/cbrowser/supervisor/core.py:850-1080 start_profile full sequence incl. readiness poll and failure path
- src/backend/cbrowser/supervisor/core.py:592-682 consume_disk_events cursor handling
- src/backend/cbrowser/supervisor/event_forwarder.py:128-196 emit/_send_to_api/replay classification
- src/backend/cbrowser/supervisor/docker_adapter.py:113-208 policy gate + network policy installation
- src/backend/cbrowser/supervisor/docker_adapter.py:1009-1060 scan_active_containers label extraction
- src/backend/cbrowser/supervisor/recovery_coordinator.py:146-190 exit classification; 300-390 retry scheduling
- src/backend/cbrowser/supervisor/network_policy.py:122-259 rule rendering and apply_policy
- src/backend/cbrowser/supervisor/runner.py:158-451 serve loop, signal handling and shutdown
- src/backend/cbrowser/domain/runtime_policy.py:5-6 AUTO_RETRY_DELAYS=(2.0,10.0,30.0), BLOCK_AFTER_RUNTIME_FAILURES=4 (cross-checked import)

## uncertainties

- Stream INPUT iptables policy accepts only loopback, established and the UDP mux port; whether the Gateway ever initiates a new TCP connection to Selkies (SELKIES_PORT 18096) cannot be confirmed from this unit — the design appears to assume Stream-initiated signaling to CBROWSER_GATEWAY_URL, but the Stream/Gateway implementations live in other units.
- On startup failure core.start_profile both reports a terminal observation (reason=startup_failure) and emits an exit event with exit_code=1 for the same instance; whether the API counts these as one failure or two depends on API-side semantics outside this unit.
- docker-py Container.name / labels behavior against a real daemon (e.g. name leading slash) affects cleanup_container_by_name and _cleanup_orphan_helpers comparisons; unit tests mock these, and no runtime Docker evidence was available to this static review.
- calculate_cpu_percent (resource_policy.py) may be exercised by test code outside the backend package; the dead-code suspicion is limited to src/backend/cbrowser where grep found no caller.

## Findings

- [Medium][80] src/backend/cbrowser/supervisor/core.py:640-682 — API-rejected disk runtime events are retried every second forever: consume_disk_events never advances the cursor when EventForwarder reports REJECTED
  - ID: f_backend_supervisor_01; verification: static
  - Evidence: core.py consume_disk_events: `delivered = await self.events.emit_event(...)`; `if not delivered: continue` — the per-instance cursor is only advanced (and the file only archived) on the delivered path.; event_forwarder.py emit_event returns False for both UNAVAILABLE and REJECTED; _send_to_api maps any non-200 status < 500 to REJECTED (e.g. 404 for a deleted profile, 400/401/403 for a semantically or credentially rejected exit event).; runner.py background_monitoring_loop calls consume_disk_events every ~1s, so one permanently rejected journal entry is re-read, re-spooled (same sha256 filename), re-POSTed and re-quarantined indefinitely, with warning logs each pass.; Contrast: schema-invalid disk events in the same function are quarantined AND cursor-advanced, so only the API-rejection path lacks a terminal disposition.
  - Impact: A single poison exit event (e.g. for a profile deleted from the API, yielding 404) creates an unbounded 1 Hz retry/log loop for the life of the process and repeatedly re-quarantines spool copies; it also head-of-line blocks nothing but wastes API quota and obscures real failures in logs.
  - Fix: Give emit_event a tri-state result (or expose the outcome) and in consume_disk_events treat REJECTED like the invalid-event path: quarantine the disk journal via _quarantine_event_file with reason 'api_rejected', advance the cursor, and persist cursors. Keep UNAVAILABLE as retry-without-advance.

- [Medium][85] src/backend/cbrowser/supervisor/event_forwarder.py:175-196 — EventForwarder classifies every non-200 status below 500 (including 401/403/429) as permanently REJECTED and quarantines the event, unlike the artifact forwarder's retryable-4xx set
  - ID: f_backend_supervisor_02; verification: static
  - Evidence: event_forwarder.py _send_to_api: `return REJECTED if resp.status_code < 500 else UNAVAILABLE`; emit_event on REJECTED calls _quarantine_event_file, and replay_spooled_events only scans spool-root *.json, so quarantined events are never retried.; artifact_forwarder.py in the same unit defines RETRYABLE_4XX = {401, 403, 408, 429} and returns early (retry next pass) for those statuses — the two forwarders disagree on the meaning of the same statuses.; A 200 response whose body lacks status='ok' with a known outcome is also mapped to REJECTED and quarantined.
  - Impact: Transient conditions — supervisor token rotation/reload lag (401/403) or API rate limiting (429) — permanently divert runtime exit events into quarantine, so the API can miss terminal observations that drive failure counting and retry blocking; recovery then depends on the slower Docker-scan synthesis path.
  - Fix: Align event_forwarder with artifact_forwarder: treat 401/403/408/429 (and transport-level 5xx) as UNAVAILABLE/retryable, reserve REJECTED-quarantine for definitive 4xx validation failures, and log the status code (not just its class) when quarantining.

- [Medium][70] src/backend/cbrowser/supervisor/core.py:1090-1102 — stop_profile journals a durable 'stopped' result for a requested instance it never inspected or tore down when the in-memory session tracks a different instance
  - ID: f_backend_supervisor_03; verification: static
  - Evidence: core.py stop_profile: after operations.begin, `if session is not None and session.runtime_instance_id != target: self.operations.complete(command_id, request, result); return result` — result claims status 'stopped' for the requested instance without any Docker scan or teardown of that instance.; The session-is-None branch right below does the opposite: it scans Docker, verifies all owned containers match the target instance, and only then completes — showing the mismatch branch skips a verification the author considered necessary elsewhere.; RecoveryCoordinator._execute_retry relies on stop_profile(expected_instance=old_inst) to remove the residual pair before restart; if a newer session is tracked, cleanup reports success while the old pair can persist, and _reconcile_profile's fence-mismatch path only logs and returns, so the orphan pair is not removed there either.
  - Impact: An orphaned Browser/Stream pair from a superseded generation can survive a 'successful' stop/cleanup, holding its networks and host ports; the journaled completion also makes the false result durable, so replaying the same operation id will never re-attempt the teardown.
  - Fix: In the session-mismatch branch, fall through to the same Docker-scan verification used when session is None: complete the journal only if no containers carry the requested instance id; if matching containers exist, tear them down (or raise the mixed-instance error) instead of reporting stopped.

- [Low][90] src/backend/cbrowser/supervisor/docker_adapter.py:494-510 — X11 permission helper container runs as root with default capabilities, bypassing the hardening every other helper container gets
  - ID: f_backend_supervisor_04; verification: static
  - Evidence: setup_x11_permissions runs the browser image with entrypoint 'chmod', user='0:0', a read-write mount of the profile x11 dir, and remove=True — with no cap_drop, no security_opt no-new-privileges, no read_only rootfs and no name/labels.; By contrast _install_network_policy's helper sets cap_drop=['ALL'], cap_add=['NET_ADMIN'] only, security_opt no-new-privileges, read_only=True and ownership labels; _initialize_cache's helper sets cap_drop=['ALL'] with only DAC_OVERRIDE/FOWNER added and no-new-privileges.
  - Impact: Defense-in-depth inconsistency: a compromised or unexpected entrypoint path in the pinned browser image would execute with Docker's default capability set as root during every profile start; the unlabelled helper also escapes the orphan-helper ownership audit in _cleanup_orphan_helpers.
  - Fix: Align setup_x11_permissions with the other helpers: cap_drop=['ALL'], cap_add=['CHOWN','FOWNER','DAC_OVERRIDE'] as needed for chmod, security_opt=['no-new-privileges:true'], read_only=True, and policy/cache-style labels.

- [Low][85] src/backend/cbrowser/supervisor/docker_adapter.py:210-214 — Every Browser launch recursively revalidates the entire engine cache tree, making start latency grow with cache size
  - ID: f_backend_supervisor_05; verification: static
  - Evidence: _validate_cache_paths iterates `root.rglob('*')` over both engine_cache and geoip_cache and calls PathValidator.validate_safe_path per entry (each doing resolve() plus an ancestor symlink walk).; It is called in __init__, after every ensure_runtime_cache initialization, and again inside start_browser_container (`self._validate_cache_paths()` just before building volumes) — i.e. once per profile start, over a Chromium binary/cache tree that can contain thousands of files.
  - Impact: Profile start (and every recovery restart) pays an O(files x path-depth) syscall tax that grows with the shared cache; under recovery storms this adds avoidable latency inside the startup path, though it is not a correctness risk.
  - Fix: Validate cache paths once at construction and after cache initialization only; on the per-start path, validate the two roots without recursion, or cache a validated fingerprint (e.g. root identity + mtime) and skip re-walking unchanged trees.

- [Low][75] src/backend/cbrowser/supervisor/docker_adapter.py:1040-1052 — scan_active_containers emits config_version=None for label-less containers, and downstream int(None) conversions abort recovery classification for all profiles in the tick
  - ID: f_backend_supervisor_06; verification: static
  - Evidence: scan_active_containers builds dicts with `'config_version': labels.get('com.cbrowser.config-version')`, which is None when the label is absent (containers pre-dating the label, or partially labelled).; recovery_coordinator._classify_abnormal_exits calls `int(b_c.get('config_version', 1))` — dict.get's default does not apply because the key exists with value None, so int(None) raises TypeError, which is not caught in tick/_classify_abnormal_exits and aborts the whole classification pass (only the runner's generic loop handler catches it).; core.stop_profile has the same pattern: `config_version = int(matching[0]['config_version'])`.; Related brittleness: start_stream_container indexes b_inspect['Config']['Labels']['com.cbrowser.config-version'] directly, raising KeyError instead of DockerSandboxError for a label-less Browser container.
  - Impact: One legacy or partially labelled container pair can suppress abnormal-exit classification (and hence synthetic exit reporting) for every profile on every tick until it disappears; the failure surfaces only as a generic 'Reconciliation failed' warning with an error_type, hiding the cause.
  - Fix: Normalize at the source: in scan_active_containers coerce the label to int with a safe default (skip or flag containers whose config-version label is missing/non-numeric), and replace downstream int(...) conversions with a shared tolerant parser that treats None as 'unknown' and skips fencing-sensitive actions for that container.

- [Low][85] src/backend/cbrowser/supervisor/control_server.py:118-160 — Control start endpoint maps lifecycle conflicts to HTTP 500 while the stop endpoint maps its conflict to 409
  - ID: f_backend_supervisor_07; verification: static
  - Evidence: start_profile catches generic Exception from core.start_profile and raises HTTP 500 'Runtime start failed'; core.start_profile raises RuntimeError for client-visible conflicts: 'API running intent is required before starting a runtime', 'Automatic retries exhausted; manual retry required', 'Existing runtime must finish cleanup before a new start'.; stop_profile in the same file maps ValueError to 409 'Conflicting lifecycle operation', showing the API distinguishes conflicts elsewhere.; Only PortPoolExhaustedError gets a precise mapping (503) in the start endpoint.
  - Impact: API callers cannot distinguish 'retry later / user action needed' (blocked, wrong intent, cleanup in progress) from a genuine supervisor fault; monitoring alerting on 500s will page on routine lifecycle conflicts.
  - Fix: Introduce typed lifecycle-conflict errors in core (or match on the existing RuntimeError categories) and map them to 409 in the start endpoint, reserving 500 for unexpected failures; keep the error detail free of internals as today.

- [Low][80] src/backend/cbrowser/supervisor/artifact_forwarder.py:262-281 — Processed download-event IDs are only pruned for instances seen in the latest scan, so the persisted cursor set grows without bound across instance churn
  - ID: f_backend_supervisor_08; verification: static
  - Evidence: forward_pending builds `present` only from event files currently on disk and calls _prune(present) solely when something changed; _prune intersects processed IDs per (profile, instance) present in `present`.; Instances whose event files have all been archived/deleted by other paths never appear in `present`, so their processed ID sets are never intersected away; _save_processed rewrites the whole structure to download_cursors.json on every change.; Each runtime instance contributes a fresh instance_id key (inst_<uuid12> per start in core.start_profile), so normal restart churn accumulates entries monotonically.
  - Impact: Long-lived supervisors accumulate stale per-instance processed sets in memory and in the 0600 cursor file, making every save O(total history) and slowly bloating a file on the forwarding hot path; functionally delivery stays correct.
  - Fix: Prune against the instances that exist on disk (events_root profile dirs / instance subdirs) rather than only those with files in this pass, or drop processed entries for instances absent from the events tree for a full pass, and skip _save_processed when the serialized payload is unchanged.

- [Low][80] src/backend/cbrowser/supervisor/network_policy.py:230-259 — apply_policy discards iptables-restore diagnostics and can leave a half-installed policy (IPv4 applied, IPv6 failed) with no rollback or family identification
  - ID: f_backend_supervisor_09; verification: static
  - Evidence: apply_policy runs iptables-restore then ip6tables-restore with capture_output=True and, on non-zero exit, raises RuntimeError('Network filter installation failed') without including stderr or which family failed.; The IPv4 ruleset remains installed in the namespace when the IPv6 restore fails; nothing removes it (fail-closed for traffic, but the namespace state no longer matches either the old or the intended policy).; main() maps the failure to exit code 3 with only error_type logged, so operators cannot tell a bad rule from a missing binary.
  - Impact: Debuggability and atomicity gap in a security-critical installer: partial installs are safe-by-default here (chains default DROP) but a failed helper leaves an undocumented mixed policy, and the discarded stderr forces reproduction under a debugger to diagnose rule errors.
  - Fix: Include the failing tool name and a truncated stderr in the raised error/log, and on second-family failure attempt a best-effort flush/restore of the first family (or document explicitly why leaving the DROP-default IPv4 ruleset is the intended terminal state).

- [Low][90] src/backend/cbrowser/supervisor/recovery_coordinator.py:520-540 — Chromium singleton-lock filename list is maintained in three places; recovery hardcodes its own copy instead of importing SINGLETON_LOCK_NAMES
  - ID: f_backend_supervisor_10; verification: static
  - Evidence: volume_spec.py defines SINGLETON_LOCK_NAMES = ('SingletonLock', 'SingletonCookie', 'SingletonSocket') and docker_adapter.start_browser_container imports and uses it before launching a new Browser.; recovery_coordinator._execute_retry repeats the literal tuple ('SingletonLock', 'SingletonCookie', 'SingletonSocket') inline when clearing stale locks before a recovery start.; core.py does not clear the locks itself but relies on these two paths, so the invariant 'locks cleared before every Browser start' depends on both copies staying in sync.
  - Impact: If Chromium introduces or renames a singleton artifact, updating the shared constant fixes the normal start path while the recovery path silently keeps clearing the old set — precisely the path exercised after crashes, where a stale lock blocks restart.
  - Fix: Import SINGLETON_LOCK_NAMES from cbrowser.supervisor.volume_spec in recovery_coordinator and delete the inline tuple.

- [Info][60] src/backend/cbrowser/supervisor/resource_policy.py:36-73 — calculate_cpu_percent appears to be dead code: no caller exists in the backend package; the live path uses calculate_quota_normalized_percent
  - ID: f_backend_supervisor_11; verification: suspected
  - Evidence: grep over src/backend/cbrowser finds calculate_cpu_percent only at its definition in resource_policy.py; record_stats and sample paths call calculate_quota_normalized_percent instead.; The two functions implement overlapping contracts (the docstring of calculate_cpu_percent describes a 'preserved mathematical contract'), which invites future fixes being applied to the unused variant.
  - Impact: Maintenance hazard only: duplicated CPU math can drift, and reviewers cannot tell which function is authoritative without a caller search.
  - Fix: Remove calculate_cpu_percent if no external/test caller exists, or add a comment naming its intended consumers; keep calculate_quota_normalized_percent as the single implementation.

- [Info][95] src/backend/cbrowser/supervisor/port_allocator.py:1-6 — PortAllocator docstring claims thread-safety but the implementation is guarded only by an asyncio.Lock
  - ID: f_backend_supervisor_12; verification: static
  - Evidence: Module docstring: 'Thread-safe / asyncio-safe, idempotent...'; the implementation protects _allocated/_used_ports solely with asyncio.Lock and performs unsynchronized reads in get_port/is_port_used.; All in-unit callers use it from the event loop (core.start_profile/stop_profile/reconcile), so current behavior is safe; the claim is broader than the guarantee.
  - Impact: Documentation inaccuracy: a future caller from a worker thread (the codebase uses asyncio.to_thread extensively for Docker calls) could rely on the docstring and introduce a data race on port ownership.
  - Fix: Correct the docstring to 'asyncio-safe (single event loop)' or back the claim with a threading lock; also document that get_port/is_port_used are unsynchronized snapshots.

## views

```json
{
  "contracts": {
    "reviewer": "aa12e052-d197-4b86-a3fe-a58ab4e52fa5",
    "status": "completed"
  },
  "correctness": {
    "reviewer": "aa12e052-d197-4b86-a3fe-a58ab4e52fa5",
    "status": "completed"
  },
  "design": {
    "reviewer": "aa12e052-d197-4b86-a3fe-a58ab4e52fa5",
    "status": "completed"
  },
  "documentation": {
    "reviewer": "aa12e052-d197-4b86-a3fe-a58ab4e52fa5",
    "status": "completed"
  },
  "performance": {
    "reviewer": "aa12e052-d197-4b86-a3fe-a58ab4e52fa5",
    "status": "completed"
  },
  "robustness": {
    "reviewer": "aa12e052-d197-4b86-a3fe-a58ab4e52fa5",
    "status": "completed"
  },
  "security": {
    "reviewer": "aa12e052-d197-4b86-a3fe-a58ab4e52fa5",
    "status": "completed"
  },
  "tests": {
    "reviewer": "aa12e052-d197-4b86-a3fe-a58ab4e52fa5",
    "status": "completed"
  }
}
```

## files_reviewed

```json
[
  "src/backend/cbrowser/supervisor/__init__.py",
  "src/backend/cbrowser/supervisor/__main__.py",
  "src/backend/cbrowser/supervisor/agent_credentials.py",
  "src/backend/cbrowser/supervisor/artifact_forwarder.py",
  "src/backend/cbrowser/supervisor/container_spec.py",
  "src/backend/cbrowser/supervisor/control_server.py",
  "src/backend/cbrowser/supervisor/coordinator_lock.py",
  "src/backend/cbrowser/supervisor/core.py",
  "src/backend/cbrowser/supervisor/docker_adapter.py",
  "src/backend/cbrowser/supervisor/event_forwarder.py",
  "src/backend/cbrowser/supervisor/file_storage.py",
  "src/backend/cbrowser/supervisor/gateway_client.py",
  "src/backend/cbrowser/supervisor/metrics.py",
  "src/backend/cbrowser/supervisor/network_policy.py",
  "src/backend/cbrowser/supervisor/network_spec.py",
  "src/backend/cbrowser/supervisor/operation_journal.py",
  "src/backend/cbrowser/supervisor/path_validator.py",
  "src/backend/cbrowser/supervisor/port_allocator.py",
  "src/backend/cbrowser/supervisor/protocol.py",
  "src/backend/cbrowser/supervisor/recovery_coordinator.py",
  "src/backend/cbrowser/supervisor/recovery_rules.py",
  "src/backend/cbrowser/supervisor/resource_monitor.py",
  "src/backend/cbrowser/supervisor/resource_policy.py",
  "src/backend/cbrowser/supervisor/runner.py",
  "src/backend/cbrowser/supervisor/selkies_tokens.py",
  "src/backend/cbrowser/supervisor/startup_gate.py",
  "src/backend/cbrowser/supervisor/volume_spec.py"
]
```
