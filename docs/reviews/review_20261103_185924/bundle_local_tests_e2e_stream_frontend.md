# bundle_local_tests_e2e_stream_frontend

## responsibilities

- Real-Docker / real-Chrome E2E coverage for the browser runtime (AC-001..006: persistence/isolation, subsystem readiness, UDS+RPC allowlist, download capture/recovery, process lifecycle/exit events, minimal privileges), stream/Selkies session and media paths, gateway AC-001/003/007 (auth, dual-tab media, visibility), the full frontend application (t007 AC-001..010), runtime coordinator desired-state convergence, and profile-defaults application.
- Build-freshness gate tests (tests/unit/test_frontend_build_freshness.py, tests/e2e/test_frontend_build_wiring.py, tests/e2e/test_frontend_adapter_build.py) that pin the npm build chain and the source-stamp mechanism protecting every dist-consuming suite in the unit.

## interfaces

- Suites consume harnesses from sibling fixture units: FrontendAppTopologyHarness (copies production dist), FrontendTopologyHarness (synthetic session host), GatewayTopologyHarness (assets extracted from the stream image), plus e2e_env.require_e2e_env for fail-closed image prerequisites.
- Browser/runtime control is exercised through CDP-over-UDS via docker exec, the runtime agent UDS HTTP API (/health, /control, /events/\*), the public API over Caddy HTTPS, and WireRecorder/adapter_probe JS injected into copied static roots.
- tests/e2e/conftest.py pytest_collection_modifyitems is the enforcement point for dist freshness; tests/unit/test_frontend_build_freshness.py loads that real conftest via runpy to test the hook.

## dependencies

- src/frontend/dist build artifact plus scripts/verify_frontend_dist.py (source hash + stamp) and scripts/write_frontend_build_stamp.py, wired by src/frontend/package.json prebuild/build/postbuild scripts.
- Pinned Docker images supplied via environment (CBROWSER\_\*\_TEST_IMAGE / images_env.txt), host Chrome for Playwright lanes, Docker daemon access from the test process.
- Fixture code owned by other units: tests/fixtures/frontend_probe, frontend_app_probe, gateway_probe, stream_probe (web_lock_shim.js), tests/e2e/e2e_env.py.

## flows

- Freshness flow: npm prebuild vendors Selkies -> vite build -> postbuild writes dist/build-stamp.json (SHA-256 over index.html, package.json, package-lock.json, vite/tailwind/postcss/tsconfig configs and all of src/ + public/) and runs verify --check-freshness; at pytest collection, the conftest hook recomputes the hash and hard-fails the run if any frontend-named test is collected against a stale or stamp-less dist.
- App lane: harness copies dist verbatim into the Caddy static root (adapter probe injected into the copy only) and drives the real app through login, runtime desired-state, media, and fault-injection scenarios.
- Gateway lane: static root is built from Selkies assets extracted out of the stream image, so those suites are independent of the repo dist by construction.
- Session lane: host_builder bundles host_entry.tsx fresh with esbuild into a synthetic host page and copies only assets/selkies from dist (building dist only if files are missing); freshness for the copied parts rests on the same collection hook.

## constraints

- Static review only: no suite was executed; all behavioral claims are read from code.
- Most suites are heavyweight (multi-container topologies, real Chrome) and several negative assertions use bounded fixed time windows rather than polls.
- The freshness guarantee is collection-scoped: it fires only when at least one collected test file has 'frontend' in its filename.

## decisions

- Freshness is enforced once at collection time (fail-closed RuntimeError) instead of per-test or per-harness checks.
- The adapter probe is injected into harness copies of the Selkies index, never into the production dist on disk.
- AC-010 token semantics are tested twice: directly against a real Selkies server in the stream image, and end-to-end through the real gateway topology with real Chrome.
- Prerequisite gating is mixed by design: most suites fail closed via require_e2e_env, while test_runtime_profile_defaults_e2e.py skips unless CBROWSER_E2E_REQUIRED=1 escalates the skip to a failure.

## evidence

- src/frontend/package.json:8-12 - vendor:selkies, verify:selkies --check-freshness, prebuild/build/postbuild chain confirmed as the wiring tests assert.
- tests/e2e/conftest.py:31-39 - collection hook calls verify_frontend_build_freshness(REPO_ROOT/src/frontend/dist, REPO_ROOT/src/frontend) whenever a frontend-named item is collected.
- scripts/verify_frontend_dist.py:30-60 - frontend_source_hash coverage and fail-closed stamp verification (missing/unreadable/mismatched stamp all raise).
- tests/e2e/test_stream_selkies_tokens_e2e.py - credentials file asserted 0600, outside Browser mounts, unreadable from the Browser container, master token scanned out of page content, console logs, and every topology container's logs.
- tests/e2e/test_browser_runtime_e2e.py - containers run UID 1000, read-only rootfs, cap-drop ALL, no-new-privileges; AC-006 verifies X11/PulseAudio authorization positively and negatively; AC-001 asserts cross-profile cookie isolation with a synthetic secret cookie.
- tests/e2e/test_frontend_app_e2e.py - WireRecorder scans DOM/storage/network/WS frames for token leakage; HELLO metadata asserted against an exact whitelist key set.

## uncertainties

- require_e2e_env semantics live in tests/e2e/e2e_env.py (tests_e2e_supervisor unit); fail-closed judgments here are based on call sites inside this unit only.
- Whether CI actually sets CBROWSER_E2E_REQUIRED=1 is decided outside this unit; that setting determines whether the profile-defaults skip path is a live coverage hole.
- web_lock_shim.js and GatewayTopologyHarness internals belong to the tests_integration_fixtures unit; the mock/shim divergence finding is judged from usage sites in test_stream_runtime_e2e.py, not from a full read of those fixtures.
- No test was run (static review constraint), so flake-related findings are marked suspected where they depend on machine load or timing.

## Findings

- [Medium][85] tests/e2e/conftest.py:32 — Dist freshness gate is keyed on test filename containing 'frontend', not on actual dist consumption

    - ID: f_tests_e2e_stream_frontend_01; verification: static
    - Evidence: tests/e2e/conftest.py:31-39 - pytest_collection_modifyitems computes frontend_items = [item for item in items if "frontend" in Path(str(item.fspath)).name] and only then calls verify_frontend_build_freshness; the check is skipped entirely when no collected file matches the substring.; tests/fixtures/frontend_app_probe/harness.py (prepare_frontend_app) copies src/frontend/dist verbatim into the static root with no freshness check of its own, so the collection hook is the only barrier between a stale dist and the app/auth/display/media suites.; tests/fixtures/frontend_probe/host_builder.py (ensure_frontend_build) builds the frontend only when dist files are missing, never when they are stale; the session lane therefore also depends solely on the filename-triggered hook.; tests/unit/test_frontend_build_freshness.py:62-67 - the hook's own unit test exercises exactly one synthetic item (test_frontend_app_e2e.py), so the filename-filter behavior itself (which files trigger, which escape) is untested.
    - Impact: Today every dist-consuming suite happens to have 'frontend' in its filename, so the gate works; but the guarantee is a naming coincidence. Renaming a suite, or adding a new dist-consuming suite without 'frontend' in its name, silently re-opens the stale-dist hole this mechanism was built to close, with no failing test to reveal it.
    - Fix: Trigger the freshness check on actual dist consumption instead of filename: e.g. run it unconditionally for the tests/e2e tree, or have the harnesses that copy dist call verify_frontend_build_freshness in prepare_static/prepare_frontend_app, and extend the hook unit test with a non-frontend-named dist consumer case.

- [Low][65] scripts/verify_frontend_dist.py:42 — Source hash silently skips missing allowlisted inputs and ignores non-allowlisted build inputs at the frontend root

    - ID: f_tests_e2e_stream_frontend_02; verification: suspected
    - Evidence: scripts/verify_frontend_dist.py:30-46 - frontend_source_hash hashes a fixed allowlist (index.html, package.json, package-lock.json, five named config files) plus everything under src/ and public/; the loop body is guarded by 'if not path.is_file(): continue', so an allowlisted input that disappears between stamp and check contributes nothing instead of failing.; Build inputs living at the frontend root outside the allowlist (for example a newly introduced .env file or an additional vite config variant) are never hashed, so changing them leaves the stamp valid while the built output can differ.
    - Impact: A dist can pass the freshness check while no longer reflecting all inputs that influenced (or should influence) the build - a narrow but real bypass of the fail-closed intent, reachable by ordinary config evolution rather than by an attacker.
    - Fix: Fail the hash computation when an allowlisted path that existed at stamp time is missing (or record the file list in the stamp and compare sets), and hash any additional build-relevant root files (e.g. .env\*, *.config.*) or document the allowlist as exhaustive.

- [Medium][90] tests/e2e/test_stream_selkies_tokens_e2e.py:341 — AC-010 'agent token injection' test re-implements the StreamAgent in the test instead of exercising production agent code

    - ID: f_tests_e2e_stream_frontend_03; verification: static
    - Evidence: tests/e2e/test_stream_selkies_tokens_e2e.py:341-346 - agent_forward_hello is a local Python function whose docstring says it 'Emulates StreamAgent upstream worker HELLO token injection'; it inserts the controller token into the HELLO dict and the test sends the result directly to the Selkies server.; The test named test_e2e_ac010_agent_controller_token_injection_and_coexistence therefore proves the Selkies server's token/coexistence/resume semantics given an already-injected token, but never runs the production Stream Agent forwarding path it is named after.; Partial mitigation in the same file: the final gateway-topology test drives the real chain (Chrome -> Gateway -> Agent -> Selkies) and verifies decode and input, but it does not cover the multi-tab coexistence, resume-supersede (close 4001 'Superseded by a new connection.'), or cloned-tab cases that the emulated test asserts.
    - Impact: A regression in the real agent's HELLO forwarding (wrong token injected, metadata dropped, injection skipped for reconnects) would leave this suite green while the feature is broken; the test's name and docstring overstate the coverage a reader or CI dashboard would attribute to it.
    - Fix: Route at least the coexistence/resume scenarios through the real Stream Agent (as the gateway-topology test in the same file does), or rename/re-document the emulated test to state it covers server-side token semantics only.

- [Medium][80] tests/e2e/test_stream_runtime_e2e.py:94 — Stream runtime suite validates tab/media semantics against an in-test GatewayMockServer and a Web Locks shim, not the production gateway/adapter

    - ID: f_tests_e2e_stream_frontend_04; verification: static
    - Evidence: tests/e2e/test_stream_runtime_e2e.py:94 - class GatewayMockServer is a test-local re-implementation of the gateway side of the signaling protocol; the suite's dual-tab identity, cloned-tab remapping, reconnect/re-register, and media-matrix assertions are all evaluated against this mock.; tests/e2e/test_stream_runtime_e2e.py:33 - WEB_LOCK_SHIM_JS loads tests/fixtures/stream_probe/web_lock_shim.js and injects it into pages, replacing the browser's Web Locks behavior that production tab-identity logic relies on; lock-contention outcomes are therefore shim-defined.; Browser-side scripts in the same file rewrite the WebSocket path to bypass the production gateway route, so the production adapter-to-gateway wiring is outside this suite's evidence.
    - Impact: If the mock or shim diverges from production gateway/adapter behavior (message shapes, lock semantics, close codes), the suite passes against the divergence and can also fail spuriously when production changes legitimately. Real-topology suites (gateway AC-003/007, frontend session/app) cover parts of the production path, but the specific tab-identity and IME/clipboard invariants asserted here rest on the mock.
    - Fix: Port the highest-value invariants (tab identity, cloned-tab remap, resume) to the real gateway topology harness, or add a contract test pinning GatewayMockServer's protocol surface against the production gateway implementation so divergence fails loudly.

- [Low][90] tests/e2e/test_stream_selkies_tokens_e2e.py:204 — AC-008 'positive' WebRTC signaling check accepts any message type, including connection close

    - ID: f_tests_e2e_stream_frontend_05; verification: static
    - Evidence: tests/e2e/test_stream_selkies_tokens_e2e.py:196-204 - after connecting to /api/webrtc/signaling and sending 'INVALID PROTOCOL TEST', the assertion is msg.type in (WSMsgType.CLOSE, WSMsgType.CLOSED, WSMsgType.TEXT), commented 'WebSocket connected and handled message'.; A server that immediately closes every signaling connection satisfies this assertion, so the positive half of AC-008 does not demonstrate that WebRTC signaling remains functional with dual mode disabled (the negative half - /api/switch returns 403 with the exact message - is asserted precisely).
    - Impact: The AC-008 regression net has a hole exactly on its positive claim: dual mode could be disabled in a way that also breaks normal WebRTC signaling and this test would stay green.
    - Fix: Assert a protocol-meaningful response (e.g. a TEXT protocol error frame, or complete a minimal valid HELLO exchange) instead of accepting CLOSE/CLOSED.

- [Low][80] tests/e2e/test_gateway_ac001_auth_e2e.py:197 — Unauthorized-profile viewer WebSocket assertion accepts 503, conflating correct rejection with gateway unavailability

    - ID: f_tests_e2e_stream_frontend_06; verification: static
    - Evidence: tests/e2e/test_gateway_ac001_auth_e2e.py:185-210 - case 3c asserts resp_unauth.status in (403, 404, 503) and repeats the same set for the error variant; neighboring cases in the same test are precise (401 for unauthenticated, 403 for wrong Origin, exact cookie flags, exact log lines).; 503 is the gateway's own 'not ready/unavailable' outcome, so a broken or mis-wired gateway satisfies the authorization assertion.
    - Impact: The authorization boundary for per-profile viewer access can silently degrade to an availability failure while the AC-001 suite reports success; the wide status set also hides which behavior production actually implements, weakening the test as a contract.
    - Fix: Determine the single intended status for an authenticated-but-unauthorized profile (403 or 404) and assert it exactly; treat 503 as a harness readiness failure to be waited out before the assertion.

- [Low][80] tests/e2e/test_browser_runtime_e2e.py:1032 — Immediacy and rearm assertions in the browser runtime suite rest on fixed sleeps instead of polling

    - ID: f_tests_e2e_stream_frontend_07; verification: static
    - Evidence: tests/e2e/test_browser_runtime_e2e.py:1029-1045 - AC-002 kills PulseAudio (pkill -9) and Xvfb, then awaits asyncio.sleep(1.0) and asserts /health already reports ready False with the specific subsystem flag False; the docstring claim is that health must 'immediately' reflect the failure, but the 1.0s window is neither polled nor justified.; tests/e2e/test_browser_runtime_e2e.py:1334 - AC-004 waits a fixed sleep(1.5) for download-behavior rearm after the external client disconnects, then immediately triggers the recovery download whose landing directory is the assertion.; Elsewhere the same unit predominantly uses poll_until/wait_until helpers (e.g. wait_for_uds_ready, poll loops with deadlines), so these fixed windows are local inconsistencies rather than a suite-wide convention.
    - Impact: On a loaded CI host, health propagation or rearm slower than the fixed window produces false failures; conversely the windows silently tolerate regressions up to 1.0-1.5s in failure-detection latency that the AC wording claims is immediate.
    - Fix: Poll /health until the degraded state appears with a bounded deadline (keeping a separate, explicit upper bound if immediacy is itself a requirement), and poll for the rearmed state or first post-rearm download with a deadline instead of sleeping 1.5s.

- [Low][60] tests/e2e/test_frontend_app_e2e.py:685 — Hard wall-clock latency budgets (input \<= 3000ms, first frame \<= 8000ms) asserted on shared CI hardware

    - ID: f_tests_e2e_stream_frontend_08; verification: suspected
    - Evidence: tests/e2e/test_frontend_app_e2e.py:629 - assert first_frame_ms \<= 8000; tests/e2e/test_frontend_app_e2e.py:685 - assert input_latency_ms \<= 3000. Both are single-sample hard asserts measured through a multi-container real topology on the CI host.; No retry, percentile, or load-normalization accompanies the thresholds in the surrounding test code.
    - Impact: These are the suite's only quantitative performance gates and the most load-sensitive asserts in the unit; under host contention they are the likeliest source of intermittent red runs, which historically trains teams to ignore or widen them until they stop detecting real regressions.
    - Fix: Keep the budgets but measure over a few samples and assert on the median (or mark the test with a documented flake-retry policy reserved for these two asserts), and record measured values in CI output so threshold drift is visible.

- [Low][85] tests/e2e/test_frontend_session_vendor.py:13 — Selkies vendor test asserts only that two imported constants equal literal strings

    - ID: f_tests_e2e_stream_frontend_09; verification: static
    - Evidence: tests/e2e/test_frontend_session_vendor.py:13-15 - the entire 17-line file asserts PINNED_SELKIES_VERSION == "2.1.0" and PINNED_WHEEL_SHA256 == a literal hash string, both imported from the production vendoring module.; Nothing in the test verifies that the pinned wheel is the artifact actually vendored into dist, that the manifest verification consumes these constants, or that a deliberate pin bump is the only way the test can fail.
    - Impact: The test is a change-detector for the pin values, not a verification of vendoring: the wheel actually served to browsers could diverge from the pin (stale vendor output, manifest drift) while this test stays green; that behavior is covered, if at all, by test_frontend_build_wiring.py's manifest checks in another file.
    - Fix: Extend the test to run the manifest verification against the vendored tree (or assert the vendored wheel file's real SHA-256 equals PINNED_WHEEL_SHA256), keeping the literal pin assertions as the change alarm.

- [Low][75] tests/e2e/test_runtime_profile_defaults_e2e.py:444 — Profile-defaults suite still skips on missing prerequisites by default, unlike fail-closed siblings in the same unit

    - ID: f_tests_e2e_stream_frontend_10; verification: static
    - Evidence: tests/e2e/test_runtime_profile_defaults_e2e.py:444-446 - when prerequisites are missing, the helper raises only if os.environ.get("CBROWSER_E2E_REQUIRED") == "1" and otherwise calls pytest.skip(message); in a default run the whole file (search-engine defaults, marker atomicity/corruption, cross-restart preservation) silently does not execute.; Contrast within the same unit: tests/e2e/test_stream_selkies_tokens_e2e.py uses an autouse fixture calling require_e2e_env(...) unconditionally, and the browser/gateway suites resolve image IDs via require_e2e_env-style assertions rather than skipping.
    - Impact: Unless CI sets CBROWSER_E2E_REQUIRED=1 (decided outside this unit), an environment regression that removes the runtime image turns this suite green-by-skip and the profile-defaults behavior loses its only real-Docker coverage without any signal.
    - Fix: Align with the unit's fail-closed pattern: resolve prerequisites through require_e2e_env, or invert the default so absence of the image fails unless an explicit opt-out variable is set.

- [Info][80] tests/e2e/test_stream_selkies_tokens_e2e.py:96 — Selkies test runner container omits the capability hardening sibling suites in this unit apply

    - ID: f_tests_e2e_stream_frontend_11; verification: static
    - Evidence: tests/e2e/test_stream_selkies_tokens_e2e.py:96-113 - SelkiesE2ERunner starts the stream image with --read-only and a tmpfs, but without --cap-drop ALL or --security-opt no-new-privileges.; Sibling suites in the same unit consistently add both: test_browser_runtime_e2e.py container launches and peer probes use --cap-drop ALL + no-new-privileges:true, and test_stream_x11_keymap_e2e.py uses --network none --read-only --cap-drop ALL.
    - Impact: Test-only exposure (loopback-bound port, ephemeral container), so impact is minimal; the inconsistency matters because these runners are routinely copied as templates for new suites, propagating the weaker baseline.
    - Fix: Add --cap-drop ALL and --security-opt no-new-privileges:true to the runner's docker arguments if the Selkies server tolerates them, or note in the class docstring why it cannot run with them.

- [Info][55] tests/fixtures/frontend_probe/adapter_probe.py:45 — Adapter probe retains only the last 500 DataChannel messages, silently evicting early messages tests may assert on

    - ID: f_tests_e2e_stream_frontend_12; verification: suspected
    - Evidence: tests/fixtures/frontend_probe/adapter_probe.py:45 - the injected probe caps window.\_\_sentDataChannelMessages at 500 entries with rolling eviction (shift) once the cap is exceeded.; Multiple suites in this unit read this buffer back to assert which control messages the page sent (e.g. visibility/activity frames in the media and session suites); a long or chatty session can evict the very messages an assertion looks for, producing a false failure indistinguishable from a product bug.
    - Impact: Latent flake/false-negative source in the probe's consumers; harmless for the short sessions in the current suites, but the failure mode would be misleading if session lengths grow.
    - Fix: Record per-type counters or a separate never-evicted log for the control message types under assertion, or document the 500-message bound at the probe's consumers.

## views

```json
{
  "contracts": {
    "reviewer": "811f4a7b-2cf3-4c4c-90ee-947bd35bab0a",
    "status": "completed"
  },
  "correctness": {
    "reviewer": "811f4a7b-2cf3-4c4c-90ee-947bd35bab0a",
    "status": "completed"
  },
  "design": {
    "reviewer": "811f4a7b-2cf3-4c4c-90ee-947bd35bab0a",
    "status": "completed"
  },
  "documentation": {
    "reviewer": "811f4a7b-2cf3-4c4c-90ee-947bd35bab0a",
    "status": "completed"
  },
  "performance": {
    "reviewer": "811f4a7b-2cf3-4c4c-90ee-947bd35bab0a",
    "status": "completed"
  },
  "robustness": {
    "reviewer": "811f4a7b-2cf3-4c4c-90ee-947bd35bab0a",
    "status": "completed"
  },
  "security": {
    "reviewer": "811f4a7b-2cf3-4c4c-90ee-947bd35bab0a",
    "status": "completed"
  },
  "tests": {
    "reviewer": "811f4a7b-2cf3-4c4c-90ee-947bd35bab0a",
    "status": "completed"
  }
}
```

## files_reviewed

```json
[
  "tests/e2e/test_browser_runtime_e2e.py",
  "tests/e2e/test_frontend_adapter_build.py",
  "tests/e2e/test_frontend_app_auth_e2e.py",
  "tests/e2e/test_frontend_app_e2e.py",
  "tests/e2e/test_frontend_build_wiring.py",
  "tests/e2e/test_frontend_display_apply_e2e.py",
  "tests/e2e/test_frontend_media_e2e.py",
  "tests/e2e/test_frontend_session_e2e.py",
  "tests/e2e/test_frontend_session_vendor.py",
  "tests/e2e/test_gateway_ac001_auth_e2e.py",
  "tests/e2e/test_gateway_ac003_media_e2e.py",
  "tests/e2e/test_gateway_ac007_visibility_e2e.py",
  "tests/e2e/test_runtime_coordinator_e2e.py",
  "tests/e2e/test_runtime_profile_defaults_e2e.py",
  "tests/e2e/test_stream_runtime_e2e.py",
  "tests/e2e/test_stream_selkies_tokens_e2e.py",
  "tests/e2e/test_stream_x11_keymap_e2e.py",
  "tests/fixtures/frontend_probe/adapter_probe.py",
  "tests/unit/test_frontend_build_freshness.py"
]
```
