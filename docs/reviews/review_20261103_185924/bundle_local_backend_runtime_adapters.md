# bundle_local_backend_runtime_adapters

## responsibilities

- runtime_agent/runner.py (BrowserRunner): per-generation browser process lifecycle inside the runtime container — engine binary resolution/verification, PulseAudio 48kHz null sink, Xvfb+Openbox with per-run Xauthority, CloakBrowser launch via a PID/exit-code wrapper script, runner_info.json publication, and exit observation that journals a terminal RuntimeEventRecord + RuntimeStateRecord.
- runtime_agent/agent.py: a separate UDS FastAPI process (agent.sock) serving /health (with terminal-state cross-verification against live PID/CDP probes), /config_version, /control (close, rearm_downloads), /events/runtime, /events/downloads, and a raw /cdp WebSocket tunnel to Chrome; in terminal generations it runs in offline replay mode.
- runtime_agent/cdp_proxy.py + download_reconciler.py: the Agent's own CDP connection — Browser.setDownloadBehavior arming with strict ACK, download willBegin/progress event capture with path-containment + sha256, reconnect with backoff, and directory-scan backfill of completed downloads lacking CDP events.
- runtime_agent/event_storage.py: atomic (tmp+fsync+replace+dirsync) JSON persistence for runtime/download events and runtime state, with a versioned download index, per-instance pruning (100), corrupt download-event quarantine, and identity-checked per-instance state selection with optional terminal recovery from exit events.
- runtime_agent/profile_defaults.py: one-time cosmetic setup that drives chrome://settings/searchEngines via the live Playwright context to add Google and make it default, gated by an atomic marker file in the user data dir.
- runtime_agent/protocol.py + security.py + subsystems.py: pydantic UDS protocol models (extra=forbid, ID patterns), runtime-ID path-component validation, and fail-closed X11/PulseAudio/CDP health probes.
- adapters/database: SQLAlchemy async SQLite layer — models.py (profiles, config versions, tags, runtimes, artifacts, settings, runtime/audit events, admins, sessions, automation tokens), repository.py (ProfileRepository: CRUD, config versioning, runtime bind/observe/desired-state state machine, idempotency via audit-row sig_hash, event consumption), artifact_repository.py (artifact metadata; API is the only writer), session.py (engine factory: WAL, busy_timeout=5000, foreign_keys=ON, BEGIN IMMEDIATE for write transactions), migrations.py (Alembic upgrade head bootstrap).
- adapters/filesystem/artifact_store.py: per-profile artifact files under {root}/{profile}/uploads|downloads — filename sanitization (NFC, Windows reserved/illegal rules, 255-byte cap), declared content-type policy, atomic streamed uploads with size cap, download import/restore moves, path-containment checks, runtime uid/gid + 0640/0750 permissions.
- services: ProfileService (domain coordination over ProfileRepository: DB error mapping to lock/constraint errors, per-profile async locks, idempotent-replay checks, duplicate-with-browser-state copy + manifest verification, reset with backup/rollback) and ArtifactService (per-profile locks, count/bytes/disk quotas, upload pipeline, download ingest with checksum/size verification and path+sha dedup).
- launch_args.py: strict whitelist validation of user Chrome launch arguments (exact flags, boolean flags, --lang/--accept-lang value patterns, control-char rejection), plus a lenient filter variant for legacy stored rows.

## interfaces

- UDS HTTP/WS API (agent.py): GET /health, GET /config_version, POST /control {action: close|rearm_downloads}, GET /events/runtime, GET /events/downloads, GET /cdp/version, WS /cdp — consumed by the Supervisor; socket file mode 0660 in a 0750 directory is the only access control.
- runner_info.json: file contract written by BrowserRunner (runner.py) and consumed by the Agent process (agent.py): profile_id, runtime_instance_id, config_version, cdp_port, browser_ws_url, display, pulse_sock/pulse_cookie, xauth_path, browser_pid, runner_pid, engine_build; identity fields are re-validated by the Agent (ConfigVersionResponse + validate_runtime_id + int checks).
- EventStorage file formats: state.json (last-written discovery cache), instances/<instance>/state.json (per-generation journal), events/runtime/<instance>/\<event_id>.json, events/downloads/\<event_id>.json + events/download-index.json (version 1).
- Repository interfaces return domain models (cbrowser.domain.models Profile/ProfileRuntime/ConfigVersionSnapshot/Artifact/RuntimeEvent); ArtifactRepository.get_profile is the exception (returns the ORM row — see finding f_backend_runtime_adapters_08).
- ArtifactStore paths: host {root}/{profile_id}/uploads|downloads/\<artifact_id>/<safe name>; container paths /exchange/downloads/\<artifact_id>/<name> and /exchange/uploads/\<artifact_id>/<name> via container_path().
- CLI entrypoints: runtime_agent/__main__.py (agent: --run-dir/--download-dir/--events-dir/--uds-path) and runner.py main() (--profile-id/--runtime-instance-id/--config-snapshot/--run-dir/--user-data-dir/--events-dir/--engine-cache-dir/--display/--engine-build), both exiting 1 with exception-type-only logging on failure.

## dependencies

- cbrowser.domain.models and cbrowser.domain.runtime_policy (BLOCK_AFTER_RUNTIME_FAILURES, ExitReason) — outside this unit.
- cloakbrowser SDK (pinned): launch_persistent_context_async, seed_widevine_hint, PLATFORM_CHROMIUM_VERSIONS; runner also reaches into SDK private internals for driver liveness (see finding f_backend_runtime_adapters_06).
- SQLAlchemy 2.0 async + aiosqlite, Alembic (migration scripts under src/backend/migrations/, outside this unit), pydantic v2, FastAPI/uvicorn, websockets.
- External processes/binaries at runtime: Xvfb, xauth, openbox, xdotool, pulseaudio, xdpyinfo, pactl (health probes fail closed when these are missing).
- Top-level `diagnostics` module imported by services/profile_service.py (see finding f_backend_runtime_adapters_11); all other intra-project imports in the unit are cbrowser.\* absolute or package-relative.

## flows

- Launch: BrowserRunner.start() refuses terminal or already-initialized generations (via EventStorage.get_instance_state(recover_terminal=True)) → saves state 'starting' → setup_pulse/setup_display → wrapper-script CloakBrowser launch → PID/CDP-port/ws-url discovery → window sizing → profile defaults → saves state 'running' + runner_info.json → spawns \_wait_for_chrome_exit.
- Exit observation: wrapper exit-code file (or PID disappearance) → normal vs abnormal vs process_observation_lost classification (exit 0 is distrusted when the SDK driver or Xvfb is dead) → durable runtime event (deterministic UUIDv5 id) + terminal state are written before is_running is cleared; infrastructure failure raises after persisting.
- API-side lifecycle: Supervisor calls ProfileRepository.bind_runtime_instance (guards: config version exists, no stale-instance rebind, no overwrite of an active instance without expected_current_instance) → report_observed_state is the only lifecycle authority (terminal error counts one failure, releases the instance, blocks restart at BLOCK_AFTER_RUNTIME_FAILURES; normal_exit clears running intent) → consume_runtime_event stores file-originated events as diagnostics only and never moves lifecycle state.
- Download capture: CDP Browser.downloadWillBegin/downloadProgress on the Agent's own connection → completed files are containment-checked and hashed → DownloadEventRecord persisted; client /cdp disconnects and Agent startup trigger rearm + scan_completed_downloads backfill; ArtifactService.ingest_download then verifies size/sha against the real file, dedups by (sha256, storage_path), moves the file into the artifact store and registers metadata, restoring the file on failure.
- Upload: ArtifactService.upload (per-profile lock) → quota pre-check → ArtifactStore.write_upload streams to a private temp file with running sha256 and max_bytes → quota re-asserted immediately before ArtifactRepository.create_artifact; any failure discards the staged directory.
- Duplicate/reset: duplicate_profile optionally copies the user data dir (only when desired+observed are both stopped, re-checked after the copy) and SHA-256-manifest-compares source vs clone before creating the clone row; reset_profile swaps the data dir for a backup, reseeds the fingerprint (deterministic per operation_id), and restores the backup on failure.

## constraints

- The API process is the only database writer (artifact_repository.py module docstring); repositories rely on BEGIN IMMEDIATE write transactions (session.py) plus SQLite busy_timeout for cross-process serialization with Supervisor-originated calls going through the API.
- Events originating from files writable by the sandboxed profile are diagnostics only; lifecycle authority is Supervisor Docker/Agent observation (repository.py consume_runtime_event step 5 comment and report_observed_state docstring).
- A runtime generation is never relaunched: terminal generations are suppressed and incomplete ('starting') generations raise, requiring a new instance id (runner.py start()).
- User Chrome launch arguments pass two whitelist gates: API-side validation and a second validate_launch_args immediately before launch in the Runner (runner.py); stored legacy rows are filtered, not rejected, when read back (launch_args.filter_launch_args).
- Agent UDS trust boundary is filesystem permissions only: socket 0660 (bound under umask 077), parent dir 0750, PulseAudio cookie 0600, Xauthority/cookie files 0600, runtime dirs 0700.
- Health semantics: a 'stopped' state is cross-verified against live PID and CDP probes before being trusted; an 'error' state is never masked by live-process evidence (agent.py get_health).
- No credentials or secret values were found in the unit's files; proxy values are carried as profile configuration data (ProfileConfig.proxy) and are deliberately kept out of logs — runner/agent top-level handlers log only exception type names for this reason.

## decisions

- Deterministic exit event identity (UUIDv5 over profile/instance) plus event_id primary-key dedup in consume_runtime_event make exit reporting idempotent across duplicate deliveries.
- Idempotency for create/update/set_desired_state is implemented as an audit_events row whose details carry a sha256 sig_hash of (action, target, payload); replays return the committed result, payload mismatches raise IdempotencyConflictError, and an IntegrityError fallback re-reads the audit row to resolve commit races.
- Download event index (download-index.json v1) with file-set reconciliation and corrupt-file quarantine, versus fail-closed StorageError for corrupt runtime events — an intentional-looking asymmetry with operational consequences (see finding f_backend_runtime_adapters_04).
- Chrome is launched through a generated bash wrapper that records the true Chrome PID and wait status, because the SDK's process handle does not expose them; exit classification distrusts both the wrapper and CDP alone.
- Artifact files are owned by the browser runtime uid/gid (default 1000) with 0640/0750 modes so the sandboxed browser can read its /exchange files while the API retains control of the tree.
- safe_filename implements cross-platform portability (Windows reserved names, illegal chars, trailing dots/spaces) even though the host is Linux — artifact names round-trip into the Windows-fingerprint browser environment.

## evidence

- src/backend/cbrowser/adapters/database/models.py:75-100 — ProfileModel relationships (tags, versions, runtime, artifacts) all lazy='selectin'.
- src/backend/cbrowser/runtime_agent/cdp_proxy.py:57-67 capture_alive requires \_last_rearm_ok; :79 initial arm is ACK-checked via start()->rearm_download_capture()->send_command; :216 reconnect path sets \_last_rearm_ok=True right after an unacknowledged send.
- src/backend/cbrowser/runtime_agent/runner.py:564-568 initialize_profile_defaults awaited inside start() before runner_info is written (:600) and before is_running is set (:572).
- src/backend/cbrowser/runtime_agent/event_storage.py:130-144 corrupt runtime event file raises StorageError; :205-231 and :283-313 corrupt download event files are quarantined instead.
- src/backend/cbrowser/runtime_agent/agent.py:440-460 run_uds_agent poll loop and unconditional runner_info['browser_ws_url'] indexing.
- src/backend/cbrowser/runtime_agent/runner.py:744-752 \_sdk_driver_alive reads browser_context.\_impl_obj.\_connection.\_transport.\_proc.
- src/backend/cbrowser/services/profile_service.py:29 'from diagnostics import emit_runtime_event_log' vs cbrowser.\* imports elsewhere in the unit.
- src/backend/cbrowser/adapters/database/artifact_repository.py:34-36 get_profile returns session.get(ProfileModel) directly; :82 storage_path compared in Python after fetching all (profile_id, sha256) download rows.
- src/backend/cbrowser/adapters/database/migrations.py:24-38 docstring claims WAL and busy_timeout=5000 configuration; busy_timeout is executed on a throwaway sqlite3 connection that is closed before Alembic runs.
- src/backend/cbrowser/runtime_agent/runner.py:225-242 \_clear_stale_x11_state: unparseable lock holder (holder=None) falls through to unconditional lock/socket unlink.

## uncertainties

- This unit contains no test files; test coverage for these modules lives in other units (backend_tests, tests\_\*), so the tests view is based on testability of the code as read, not on coverage measurement.
- duplicate_profile copies the source fingerprint_seed unchanged into the clone (profile_service.py duplicate_profile builds ProfileConfig from source.model_dump() changing only the name). Whether a clone intentionally shares the source's browser fingerprint or should receive a fresh seed cannot be decided from this unit alone — it depends on the product definition of 'duplicate'.
- ProfileService.update_profile merges a caller-supplied dict into the current config and constructs ProfileConfig(\*\*merged); whether unexpected patch keys can reach it depends on ProfileConfig's extra-field policy and the API layer, both outside this unit.
- Whether the Supervisor polls /health frequently enough for the per-call subprocess probes (xdpyinfo + two pactl calls, subsystems.py) to matter operationally is determined by Supervisor code outside this unit.

## Findings

- [Medium][90] src/backend/cbrowser/adapters/database/models.py:75-100 — Every profile read eager-loads the full config-version history and artifact rows via selectin relationships

    - ID: f_backend_runtime_adapters_01; verification: static
    - Evidence: models.py:75-100 defines ProfileModel.tags, .versions, .runtime and .artifacts all with lazy='selectin', so any SELECT of ProfileModel rows also loads all four collections.; repository.py get_profile() and list_profiles() select ProfileModel and convert with \_to_domain_profile(), which only consumes m.tags — the version snapshots (each a full JSON config blob, unbounded history) and artifact rows are loaded and discarded.; ProfileService.get_profile() is called as an existence/identity check at the head of nearly every service operation (bind, report, desired-state, versions, duplicate, reset), so the heavy load runs on hot paths, not just on profile listing.
    - Impact: Read cost and memory grow with each profile's accumulated version history and artifact count rather than with the data actually returned; list_profiles() multiplies this across all profiles. On a long-lived install with many edits per profile, routine runtime polling and list calls degrade steadily.
    - Fix: Use lazy='raise' or 'noload' for versions/artifacts on the read paths and load them explicitly only in list_config_versions/get_config_version and artifact flows (e.g. selectinload only tags in get_profile/list_profiles, or load_only plus explicit relationship loads where needed).

- [Medium][85] src/backend/cbrowser/runtime_agent/runner.py:564-568 — Cosmetic default-search-engine setup sits on the critical launch path and can fail an otherwise healthy browser start

    - ID: f_backend_runtime_adapters_02; verification: static
    - Evidence: runner.py start() awaits initialize_profile_defaults(...) at :564 after the browser context is launched but before runner_info.json is written (:600) and before is_running is set (:572); an exception propagates out of start().; profile_defaults.py drives chrome://settings/searchEngines with fixed sleeps (1.5s/1.0s) and multi-strategy DOM/shadow-DOM scraping (\_MAKE_GOOGLE_DEFAULT_JS has three fallback selector strategies including localized 'Make default'/Chinese label matching), and converts any failure — dialog not found, button never enabled, verification mismatch — into ProfileDefaultsError.; A marker-file hit is the only fast path; any profile with set_google_default enabled whose marker was lost (e.g. fresh copy of a used data dir) re-runs the full UI automation on next launch.
    - Impact: A Chrome UI change, localization difference, or timing flake in a purely cosmetic preference step aborts the whole runtime generation after Chrome has already started, leaving the generation in 'starting' state (which start() itself treats as requiring a new instance id). Launch reliability is coupled to the most fragile automation in the unit.
    - Fix: Move initialize_profile_defaults off the readiness path: launch, publish runner_info, mark running, then apply defaults best-effort in the background with failures logged and the marker left unwritten so a later launch retries; or at minimum catch ProfileDefaultsError in start() and continue.

- [Medium][90] src/backend/cbrowser/runtime_agent/cdp_proxy.py:190-253 — After a CDP reconnect, download capture is reported healthy without the rearm command ever being acknowledged

    - ID: f_backend_runtime_adapters_03; verification: static
    - Evidence: The initial arm is strict: start() -> rearm_download_capture() -> send_command() raises unless the response contains a result (cdp_proxy.py:69-108).; The reconnect path inside \_listen_events (:216-235) instead increments \_next_cmd_id, sends Browser.setDownloadBehavior fire-and-forget, increments rearm_count and sets self.\_last_rearm_ok = True unconditionally; the comment explains the ACK cannot be awaited from the sole reader coroutine.; The rearm response id is never registered in pending_cmd_futures, so when the listener later consumes it, an 'error' response from Chrome is silently dropped (only ids present in pending_cmd_futures are matched).; capture_alive (:57-67) — which agent.py get_health uses for cdp_ready — therefore returns True after reconnect even if Chrome rejected or never applied the download behavior.
    - Impact: Health can report cdp_ready while download capture is actually disarmed after a transient CDP drop: downloads then land with default Chrome behavior and are only recovered if their files appear in the reconciler's directory scan; downloadWillBegin/downloadProgress events (and their guided file names) are lost for that period without any signal.
    - Fix: Track the reconnect rearm id and resolve \_last_rearm_ok from its actual response when the listener consumes it (set \_last_rearm_ok=False at send time, flip to True only on a result-bearing response with the matching id, False on error/timeout).

- [Low][85] src/backend/cbrowser/runtime_agent/event_storage.py:130-144 — One corrupt runtime event file hard-fails all runtime-event reads, unlike download events which are quarantined

    - ID: f_backend_runtime_adapters_04; verification: static
    - Evidence: \_read_runtime_events raises StorageError on the first unparseable/invalid file (:141-143); get_runtime_events, the Agent's GET /events/runtime handler, and get_instance_state(recover_terminal=True) all flow through it.; The download side of the same class handles the identical situation by quarantining the corrupt file and continuing (\_rebuild_download_index :225-233, get_download_events :296-305).; BrowserRunner.start() calls get_instance_state(..., recover_terminal=True) before anything else, so a single corrupt event JSON in the instance's directory prevents that generation's state from being read at all (start aborts via StorageError -> 503 in the Agent, exception in the Runner).
    - Impact: Atomic writes make corruption unlikely, but any torn/foreign/older-format file in events/runtime/<instance>/ permanently blocks the events endpoint and terminal recovery for that instance instead of degrading to the remaining valid events; the operator's only remedy is manual file removal.
    - Fix: Apply the download-side policy to runtime events: quarantine unparseable files and continue with the valid ones, reserving StorageError for identity mismatches (profile/instance/version conflicts), which are genuine integrity signals.

- [Low][90] src/backend/cbrowser/runtime_agent/agent.py:440-460 — Agent startup crashes with KeyError when runner_info.json exists but never gains browser_ws_url

    - ID: f_backend_runtime_adapters_05; verification: static
    - Evidence: run_uds_agent polls runner_info.json up to 100 times, breaking only when 'browser_ws_url' is present in the parsed dict (:440-449); a file that parses successfully but lacks the key leaves runner_info as a non-empty dict.; The missing-info guard is `if not runner_info:` (:451), which does not fire for that partial dict, and CdpProxyManager is then constructed with runner_info['browser_ws_url'] (:459), raising KeyError instead of the intended RuntimeError('Runner info missing...').
    - Impact: A Runner that wrote partial/stale runner_info (e.g. killed mid-write from an older format, or a hand-placed file) makes the Agent die with an opaque KeyError after the full ~20s poll, and the __main__ handler logs only the exception type, slowing diagnosis. Behavior differs from the clean not-found path for no reason.
    - Fix: Treat 'no browser_ws_url after polling' as missing: change the guard to `if 'browser_ws_url' not in runner_info:` before constructing CdpProxyManager.

- [Low][75] src/backend/cbrowser/runtime_agent/runner.py:744-752 — Exit classification depends on Playwright/SDK private internals; any shape change silently flips clean exits to observation-lost errors

    - ID: f_backend_runtime_adapters_06; verification: static
    - Evidence: \_sdk_driver_alive() reaches through browser_context.\_impl_obj.\_connection.\_transport.\_proc — three levels of underscore-private attributes of the pinned cloakbrowser/Playwright stack — and returns False on any AttributeError/OSError/IndexError.; \_wait_for_chrome_exit (:693-706) treats 'not \_sdk_driver_alive()' with exit_code 0 as infrastructure_failure, rewriting the reason to process_observation_lost, persisting state 'error' instead of 'stopped', and raising RuntimeError.
    - Impact: If an SDK patch release renames or restructures those internals, every normal browser close is misclassified as an infrastructure failure: the API side counts a runtime failure (report_observed_state failure path), users see errors for intentional closes, and repeated occurrences can trip restart_blocked. The failure mode is silent — the probe cannot distinguish 'internals changed' from 'driver actually dead'.
    - Fix: Prefer an observable liveness signal that does not depend on private attributes (e.g. CDP ws responsiveness plus /proc checks on PIDs the Runner itself owns), and log distinctly when the private-attribute probe itself fails so a shape change is diagnosable rather than indistinguishable from a dead driver.

- [Low][85] src/backend/cbrowser/adapters/filesystem/artifact_store.py:131-139 — Executable-type blocking is declared-metadata only, and the two ingest paths enforce it inconsistently

    - ID: f_backend_runtime_adapters_07; verification: static
    - Evidence: validate_content_type() only inspects the caller-supplied content_type string against DANGEROUS_CONTENT_TYPES; uploaded bytes are never sniffed in write_upload (artifact_store.py) or ArtifactService.upload.; ArtifactService.upload rejects a dangerous declared type (exception propagates), while ingest_download catches ArtifactInvalidContentType and silently relabels the artifact 'application/octet-stream' (artifact_service.py:224-227), i.e. downloads are always accepted regardless of type.; For downloads the type is derived from the filename extension via mimetypes.guess_type, so an executable payload named without a known extension also passes as octet-stream.
    - Impact: The dangerous-type list gives the appearance of an executable-upload control, but any client can store an executable by declaring a benign content type; the stored content_type is later trusted when serving the artifact back. The upload/download inconsistency means the policy is neither uniformly enforced nor uniformly advisory.
    - Fix: Decide the policy explicitly: either document the check as advisory metadata hygiene (and drop the security framing), or enforce it on both paths using the same rule — for downloads, reject or quarantine dangerous detected types instead of relabeling, and consider magic-byte sniffing for the small dangerous set if the control is meant to be real.

- [Low][95] src/backend/cbrowser/adapters/database/artifact_repository.py:34-36 — ArtifactRepository.get_profile leaks the SQLAlchemy ORM model across the repository boundary

    - ID: f_backend_runtime_adapters_08; verification: static
    - Evidence: get_profile returns `await session.get(ProfileModel, profile_id)` — a live ORM object tied to a session that is closed when the method returns — while every other method in both repositories converts to domain models (\_to_domain / \_to_domain_profile).; Its only in-unit caller, ArtifactService, uses it purely as an existence check (`is None`) in upload() and ingest_download(), so the ORM object itself is never needed.
    - Impact: The leaked model invites future callers to read attributes on a detached ORM instance (risking lazy-load errors outside a session, especially with selectin relationships) and breaks the unit's otherwise consistent rule that the database layer speaks domain types.
    - Fix: Replace with an existence query (select(1) / session.get returning bool) named e.g. profile_exists, and update ArtifactService call sites.

- [Low][90] src/backend/cbrowser/adapters/database/artifact_repository.py:63-84 — find_download_duplicate fetches all (profile, sha256) rows and filters storage_path in Python despite a composite index

    - ID: f_backend_runtime_adapters_09; verification: static
    - Evidence: The query filters only profile_id, kind and sha256, materializes all matching rows, then loops comparing row.storage_path == storage_path (:81-83).; models.py:211 already defines Index('idx_artifacts_profile_sha256', 'profile_id', 'sha256'); adding storage_path to the WHERE clause is a one-line change.
    - Impact: Minor: extra row materialization per download ingest; only grows if many same-content downloads accumulate under one profile (bounded by the 200-artifact quota), so impact is small but the fix is free.
    - Fix: Add ArtifactModel.storage_path == storage_path to the select() predicates and return the first row.

- [Low][80] src/backend/cbrowser/adapters/database/repository.py:190-208 — Idempotency commit-race recovery is copy-pasted between create_profile and update_profile; utc_now_iso is also defined twice

    - ID: f_backend_runtime_adapters_10; verification: static
    - Evidence: The `except IntegrityError:` block that re-reads the audit row, compares sig_hash and returns the existing profile appears nearly verbatim in create_profile (:190-208) and update_profile (:415-433), on top of the already-duplicated in-transaction replay check in both methods.; utc_now_iso is defined in adapters/database/models.py:16-17 and independently in cbrowser.domain.models; repository.py and artifact_repository.py import the domain one while models.py uses its own for column defaults.
    - Impact: Any fix to the replay/conflict logic (e.g. the deleted-profile fall-through, where an audit row exists but the profile is gone and execution falls into a fresh insert that re-raises) must be made in two places and can drift; the duplicate time helper invites format drift between column defaults and explicitly written timestamps.
    - Fix: Extract a shared helper (e.g. \_resolve_idempotency_race(session_maker, operation_id, sig_hash, profile_id)) used by both methods, and import utc_now_iso from one canonical module.

- [Low][90] src/backend/cbrowser/services/profile_service.py:29 — profile_service imports a top-level 'diagnostics' module, unlike every other import in the unit

    - ID: f_backend_runtime_adapters_11; verification: static
    - Evidence: Line 29: `from diagnostics import emit_runtime_event_log` — a bare top-level import that only resolves if the backend source root (src/backend) is on sys.path.; All other intra-project imports in the unit are absolute cbrowser.\* (repository.py, artifact_service.py) or package-relative (runtime_agent/*); the backend test suite's own convention (tests import the package as backend.* with the parent on sys.path, per the backend_tests unit) shows import roots already vary by entry point.
    - Impact: Importing cbrowser.services.profile_service from any context whose sys.path lacks src/backend (a different launcher, an embedding tool, a test harness rooted at the package parent) fails with ModuleNotFoundError at import time, before any logic runs.
    - Fix: Move emit_runtime_event_log under the cbrowser package (e.g. cbrowser.diagnostics) and import it as cbrowser.diagnostics, or use the correct absolute path for its actual location.

- [Low][80] src/backend/cbrowser/runtime_agent/runner.py:225-242 — Stale-X11 cleanup unlinks the lock and socket unconditionally when the lock file content is unparseable

    - ID: f_backend_runtime_adapters_12; verification: static
    - Evidence: \_clear_stale_x11_state only proves the display is free when the lock file parses to a PID and that PID is gone (ProcessLookupError -> pass, live/PermissionError -> raise).; When int() parsing fails or the read raises OSError, holder stays None and execution falls through to lock_path.unlink + sock_path.unlink (:241-242) — the same path taken for a proven-stale lock.
    - Impact: If a live Xvfb's lock file is momentarily unreadable or partially written, a second Runner for the same display deletes the live server's socket file; the existing server keeps running but becomes unreachable, and the new Xvfb may then start on the same display number with split-brain state. Narrow race, but the fail-safe direction is backwards: unproven ownership should stop, not delete.
    - Fix: Treat an existing-but-unparseable lock file as 'display in use' (raise) or re-read/retry briefly before deciding; only unlink when staleness is proven (parseable PID that no longer exists) or when neither file exists.

- [Low][80] src/backend/cbrowser/services/artifact_service.py:168-176 — Artifact delete removes the database row before deleting the file, and a directory-valued storage_path raises after the row is gone

    - ID: f_backend_runtime_adapters_13; verification: static
    - Evidence: ArtifactService.delete() awaits repository.delete_artifact() first, then store.delete() in a thread (:171-175).; ArtifactStore.delete() calls target.unlink(missing_ok=True) without guarding IsADirectoryError; unlink on a directory raises IsADirectoryError (an OSError not suppressed by missing_ok), which propagates out of delete().; storage_path normally points at a file written by this unit, so the trigger requires a corrupted/foreign row — but the ordering means any store.delete failure reports an API error for an artifact whose metadata is already deleted.
    - Impact: Mostly consistency hygiene: a failed file removal surfaces as a failed delete even though the artifact no longer exists in the database; a directory at storage_path would also leak (never removed) while the caller believes deletion was attempted.
    - Fix: In ArtifactStore.delete, treat a directory target explicitly (rmdir/rmtree the artifact directory, mirroring discard_upload) and make store deletion failure-tolerant with logging, since the DB row is already committed as deleted.

- [Info][95] src/backend/cbrowser/runtime_agent/agent.py:296-460 — Agent control and CDP endpoints have no per-request authentication; the UDS file permissions are the entire trust boundary

    - ID: f_backend_runtime_adapters_14; verification: static
    - Evidence: create_agent_app exposes POST /control (close_browser, rearm_downloads) and the WS /cdp full-browser-control tunnel with no token, origin, or peer-credential check; protection is entirely the socket setup in run_uds_agent (umask 077 bind, sock chmod 0660, parent chmod 0750, agent.py:505-525).; This matches the documented design (Supervisor and Agent share the runtime volume; the sandbox boundary is the container), and no additional exposure was found — the socket is never bound to TCP.
    - Impact: Any process that gains read/write access to the profile's runtime directory (or runs in a container sharing that volume) obtains full CDP control of the browser and can close it or read all events. Acceptable under the current single-host container model, but it means volume-mount configuration mistakes elsewhere silently become browser-takeover paths.
    - Fix: No change required for the current topology; if the runtime volume is ever shared more broadly, add SO_PEERCRED checking or a per-generation token file (0600) required on /control and /cdp.

- [Info][85] src/backend/cbrowser/adapters/database/migrations.py:24-38 — Migration docstring overstates busy_timeout configuration; the pragma is set on a throwaway connection

    - ID: f_backend_runtime_adapters_15; verification: static
    - Evidence: run_database_migrations' docstring says it 'Configures database with WAL and busy_timeout=5000', but the code opens a raw sqlite3 connection, executes the pragmas and closes it (:33-38) before Alembic runs on its own connections.; journal_mode=WAL persists in the database file, but busy_timeout is per-connection and does not persist; the busy_timeout that actually protects the application comes from session.py's connect listener, not from this function.
    - Impact: Documentation accuracy only: a reader could believe Alembic migrations themselves run under busy_timeout=5000 (they rely on Alembic/SQLAlchemy defaults), and could remove session.py's listener believing migrations already configured the database.
    - Fix: Correct the docstring to state WAL is persisted here and busy_timeout is applied per-connection by the engine factory in session.py; drop the no-op pragma or keep it with an accurate comment.

## views

```json
{
  "contracts": {
    "reviewer": "5c3e596b-542e-4a7e-a07c-ed8f4617c164",
    "status": "completed"
  },
  "correctness": {
    "reviewer": "5c3e596b-542e-4a7e-a07c-ed8f4617c164",
    "status": "completed"
  },
  "design": {
    "reviewer": "5c3e596b-542e-4a7e-a07c-ed8f4617c164",
    "status": "completed"
  },
  "documentation": {
    "reviewer": "5c3e596b-542e-4a7e-a07c-ed8f4617c164",
    "status": "completed"
  },
  "performance": {
    "reviewer": "5c3e596b-542e-4a7e-a07c-ed8f4617c164",
    "status": "completed"
  },
  "robustness": {
    "reviewer": "5c3e596b-542e-4a7e-a07c-ed8f4617c164",
    "status": "completed"
  },
  "security": {
    "reviewer": "5c3e596b-542e-4a7e-a07c-ed8f4617c164",
    "status": "completed"
  },
  "tests": {
    "reviewer": "5c3e596b-542e-4a7e-a07c-ed8f4617c164",
    "status": "completed"
  }
}
```

## files_reviewed

```json
[
  "src/backend/cbrowser/adapters/database/artifact_repository.py",
  "src/backend/cbrowser/adapters/database/migrations.py",
  "src/backend/cbrowser/adapters/database/models.py",
  "src/backend/cbrowser/adapters/database/repository.py",
  "src/backend/cbrowser/adapters/database/session.py",
  "src/backend/cbrowser/adapters/filesystem/artifact_store.py",
  "src/backend/cbrowser/launch_args.py",
  "src/backend/cbrowser/runtime_agent/__main__.py",
  "src/backend/cbrowser/runtime_agent/agent.py",
  "src/backend/cbrowser/runtime_agent/cdp_proxy.py",
  "src/backend/cbrowser/runtime_agent/download_reconciler.py",
  "src/backend/cbrowser/runtime_agent/event_storage.py",
  "src/backend/cbrowser/runtime_agent/profile_defaults.py",
  "src/backend/cbrowser/runtime_agent/protocol.py",
  "src/backend/cbrowser/runtime_agent/runner.py",
  "src/backend/cbrowser/runtime_agent/security.py",
  "src/backend/cbrowser/runtime_agent/subsystems.py",
  "src/backend/cbrowser/services/artifact_service.py",
  "src/backend/cbrowser/services/profile_service.py"
]
```
