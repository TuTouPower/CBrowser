# bundle_local_backend_tests

## responsibilities

- In-package pytest suite for the legacy backend (src/backend): FastAPI routes in main.py (profile CRUD, launch/stop, clipboard, CDP proxy, settings, reset/duplicate, shutdown guard), browser_manager lifecycle and proxy/fingerprint helpers, SQLite database CRUD and legacy-schema rebuild, Pydantic models, per-profile file artifacts, browser download capture over CDP, VNC display/port allocation, host runtime policy, and the RFB protocol message filter/rewrite helpers in main.py.
- Suite is behavior-oriented overall: most tests assert observable outcomes (HTTP status/body, DB rows, filesystem bytes, response headers) rather than internal state, and failure paths (copy failure, request cancellation, quota, oversized bodies) are covered deliberately.

## interfaces

- pytest fixtures from conftest.py: tmp_db (DB_PATH/DATA_DIR redirected to tmp), sample_profile, app_client (Starlette TestClient running main.app lifespan with browser manager neutralised), native_runtime/docker_runtime, autouse HOME isolation.
- Tests drive the app three ways: TestClient HTTP calls, direct awaits of route coroutines (main.duplicate_profile/reset_profile/delete_profile/launch_profile) for interleaving control, and a raw ASGI drive harness (_drive_upload in test_artifacts.py) that counts body reads.
- White-box access to BrowserManager internals (_launching, _held, _cdp_ports, _reserve/_release_stopping) is used intentionally for lifecycle-race tests.

## dependencies

- Production modules: backend.main, backend.browser_manager, backend.database, backend.models, backend.artifacts, backend.downloads, backend.vnc_manager, backend.runtime, backend.settings_store.
- conftest.py stubs the cloakbrowser package (launch, config, download, license submodules) in sys.modules before any backend import; CHROMIUM_VERSION is pinned to a test sentinel that test_api.py's system-status test asserts against.
- unittest.mock AsyncMock/MagicMock/patch at system boundaries (xclip subprocess, httpx.AsyncClient, websockets.connect, cloakbrowser launch); pytest.mark.asyncio on async tests.

## flows

- conftest installs cloakbrowser stubs at import time -> fixtures point the database module at a tmp dir and init schema -> TestClient lifespan runs with VNC/process methods mocked -> tests exercise routes or manager methods -> assertions on responses, DB state and files.
- Concurrency tests seed a profile's browser state on disk, monkeypatch main._copy_browser_state with an event-gated pausable copy, interleave launch/reset/delete/duplicate coroutines, and assert 409 refusals plus post-release success.

## constraints

- Static suite: no real browser, KasmVNC, xclip or network is exercised; every external effect is mocked, so passing here does not evidence real-host behaviour.
- Tests import the package as `backend.*`, i.e. they assume the src/backend parent is on sys.path; several tests mutate the process-global main.browser_mgr singleton (see findings).
- The suite leans on exact production literals (status codes, header values, bookmark folder names, masked-key format), so contract changes in the backend units surface here first.

## decisions

- Mock only at system boundaries for most tests (cloakbrowser module, subprocess, httpx, websockets), keeping route/manager logic real — a sound default that most of the suite follows.
- Event-based synchronisation (_PausableCopy, _until polling, FakeSocket queues) is preferred over sleeps for race tests; remaining fixed sleeps are small and bounded.
- Known wart documented in-file: a real_lifecycle fixture exists solely to undo earlier tests' un-restored swaps of browser_mgr.launch/stop (see f_backend_tests_01).

## evidence

- src/backend/tests/conftest.py:15-46 (sys.modules cloakbrowser stubs), 49-88 (tmp_db/app_client), 91-103 (autouse HOME isolation)
- src/backend/tests/test_api.py:1046-1397 (duplicate lifecycle-safety and CDP download-capture tests with pausable copy and fake upstream)
- src/backend/tests/test_artifacts.py:470-605 (ASGI drive harness proving oversized uploads are refused before the body is read)
- src/backend/tests/test_downloads.py:306-581 (FakeSocket CDP session tests: id-matched replies, malformed frames, reconnect budget)
- src/backend/tests/test_database.py:52-83 (legacy schema rebuild preserving profiles/tags)
- src/backend/tests/test_rfb.py:1-341 (byte-level RFB parse/filter/rewrite coverage)

## uncertainties

- Whether the full-format license-key-shaped literal used as fixture data in the settings tests (f_backend_tests_03) is a real CloakBrowser license key cannot be determined statically; it is reported as a hygiene risk, not a confirmed leak.
- pytest-asyncio mode/configuration lives in packaging files outside this unit; async tests carry explicit marks, but whether the suite is collected with the same ordering/isolation in CI is outside this unit's files.
- The pollution impact in f_backend_tests_01 assumes pytest's default single-process, in-order execution; per-file or parallel (xdist) execution would change which tests observe the leaked mocks, in both directions.

## Findings

- [Medium][95] src/backend/tests/test_api.py:143 — Tests replace the global browser_mgr singleton's launch/stop by direct assignment and never restore them, making suite outcomes order-dependent
  - ID: f_backend_tests_01; verification: static
  - Evidence: src/backend/tests/test_api.py:143 test_delete_profile_stops_running does `main.browser_mgr.stop = AsyncMock(...)`; :196 and :206 do the same for `launch` (test_launch_invalid_proxy_400, test_launch_failure_500); :867 repeats the stop swap in test_reset_profile_stops_running. None use monkeypatch, so nothing restores the real methods at test end.; The file itself documents the consequence: the real_lifecycle fixture at src/backend/tests/test_api.py:1082-1088 exists because 'Earlier tests swap browser_mgr.launch/stop for AsyncMocks and never put them back; these tests need the real state machine'.; src/backend/tests/test_api.py:243 test_system_status begins with the comment 'Clear any leaked running profiles from prior tests' and clears browser_mgr.running — leaked-state cleanup is handled ad hoc per test.; Tests that run after the swaps and do not opt into real_lifecycle (e.g. test_reset_profile_returns_updated_profile) silently execute against whichever mock an earlier test installed.
  - Impact: Test results depend on execution order and selection: running a subset (-k filters, single file, xdist sharding, or a future reordering) changes which implementation of launch/stop later tests exercise, so the suite can pass in CI order while the real launch/stop path is broken, or fail spuriously when order changes. The workaround fixture fixes only the tests that remember to use it.
  - Fix: Replace the direct assignments at test_api.py:143/196/206/867 with monkeypatch.setattr(main.browser_mgr, 'launch'/'stop', ...) so teardown restores the real methods, then delete the real_lifecycle workaround fixture and the leaked-state clearing in test_system_status once nothing leaks.

- [Medium][90] src/backend/tests/test_api.py:599 — Cross-origin WebSocket rejection tests accept any exception, so they would still pass if the CSWSH origin guard were deleted
  - ID: f_backend_tests_02; verification: static
  - Evidence: src/backend/tests/test_api.py:599 and :614 (test_vnc_ws_rejects_cross_origin, test_cdp_ws_rejects_cross_origin) wrap websocket_connect in `pytest.raises(Exception)` — any failure satisfies the test.; The mocked running profiles point at ws_port 6100 / cdp_port 5100 where nothing listens (test_api.py _mock_running_profile and inline mocks), so if the origin check in backend/main.py (_check_websocket_origin, closes with 4403) were removed, the accepted connection would fail moments later in the proxy connect and raise an exception all the same.; The companion acceptance tests (test_ws_allows_same_origin, test_ws_allows_no_origin) only assert that '4403' does not appear in the exception string, so the pair of test groups cannot distinguish 'rejected by the guard' from 'failed downstream'.
  - Impact: The only tests covering the cross-site WebSocket hijacking guard on the /vnc and /cdp endpoints cannot fail when the guard regresses or is removed; a security control would lose its regression net while the suite stays green.
  - Fix: Assert the specific rejection: catch the TestClient WebSocketDisconnect and assert its code == 4403 for the cross-origin cases, and for the same-origin/no-origin cases assert the handshake is accepted (or at minimum that any disconnect code is not 4403) with the upstream made connectable or the proxy connect mocked to succeed.

- [Low][60] src/backend/tests/test_api.py:748 — Settings tests use a full-format license-key-shaped literal as fixture data in a public repository
  - ID: f_backend_tests_03; verification: suspected
  - Evidence: A 35-character literal in the production CloakBrowser license-key format (cb_ prefix followed by hex) is used as the test license key at src/backend/tests/test_api.py:748 (test_get_settings_masks_key), again as the `key` value in test_put_settings_persists_and_hot_applies (~:761) and test_put_settings_clears_key (~:774); the masking assertion also embeds that same literal's head and tail fragments as the expected masked string.; Statically the literal is indistinguishable from a real issued key: it is not an obvious placeholder (not all-same-character, not 'test'/'example' shaped), unlike the clearly fake 'cb_test' and 'cb_x' values used elsewhere in the suite.; This is a public/open repository, so anything committed here is published; the value itself is deliberately not reproduced in this finding.
  - Impact: If the literal is a real license key, it is a leaked credential in git history: anyone can use it until revoked, and history rewriting would be needed to remove it. If it is synthetic, it still trains readers to treat real-format keys as acceptable test data.
  - Fix: Replace the literal with an obviously synthetic value of the same shape class (e.g. a repeated-pattern fake that still exercises the masking positions), and if the current value was ever a real key, rotate/revoke it and treat the history copy as exposed.

- [Low][90] src/backend/tests/test_browser_manager.py:216 — Launch-args tests perform the production append inside the test body instead of exercising BrowserManager.launch
  - ID: f_backend_tests_04; verification: static
  - Evidence: src/backend/tests/test_browser_manager.py:216-244: test_launch_args_appended_to_fingerprint_args and its empty/None variants build args via _mgr._build_fingerprint_args(profile) and then execute `args += profile.get('launch_args') or []` in the test itself before asserting membership — the behaviour under test is the test's own line.; The production behaviour lives in BrowserManager.launch (src/backend/browser_manager.py:505-528): it rejects manager-owned debugging flags from user launch_args, builds fingerprint args, and only then appends user args. The dedicated tests bypass both the rejection filter and the ordering.; Real-path coverage exists only incidentally: test_launch_passes_license_config checks one flag's ordering through launch(), and test_launch_rejects_user_debugging_flags checks rejection — neither is the test that claims to cover launch_args appending.
  - Impact: If launch() stopped appending user launch_args, appended them before the fingerprint args (breaking override semantics), or dropped the debugging-flag filter, the three tests named for this behaviour would still pass; the coverage signal for a fingerprint/stealth-relevant code path is illusory.
  - Fix: Drive these cases through manager.launch() with launch_persistent_context_async mocked (as the neighbouring launch tests already do) and assert on the final args list passed to the launcher, including ordering after fingerprint args and rejection of --remote-debugging-* flags.

- [Low][95] src/backend/tests/test_auth.py:133 — test_logout_clears_cookie never verifies the cookie is actually cleared
  - ID: f_backend_tests_05; verification: static
  - Evidence: src/backend/tests/test_auth.py:133-139 logs in, posts /api/auth/logout, and asserts only status 200 and {"ok": True}; it never inspects the Set-Cookie header, the client's cookie jar, or a follow-up authenticated request.; The neighbouring test_login_correct_sets_cookie (test_auth.py:124-128) does assert the cookie exists in resp.cookies, so the asymmetric gap is specific to logout.
  - Impact: A logout regression that returns ok without expiring the auth_token cookie — leaving the session fully valid — would pass this test despite its name claiming the opposite.
  - Fix: After logout, assert the auth_token cookie is gone/expired in the response (or that a subsequent GET /api/profiles with the previously set cookie returns 401 while AUTH_TOKEN is set).

- [Info][90] src/backend/tests/test_auth.py:17 — Auth fixtures duplicate conftest app_client's lifespan-neutralising patches instead of reusing it
  - ID: f_backend_tests_06; verification: static
  - Evidence: src/backend/tests/test_auth.py:17-42: client_no_auth and client_auth each repeat the same four monkeypatch lines used by conftest.py's app_client (vnc.validate_available, browser_mgr.cleanup_stale, cleanup_all, vnc.cleanup_stale), differing only in the AUTH_TOKEN value.; conftest.py:66-88 already centralises those patches; the auth fixtures cannot reuse app_client as-is only because they also need to set main.AUTH_TOKEN, which a small wrapper fixture could add.
  - Impact: If the app lifespan gains another host requirement that must be neutralised in tests, three fixtures need the same edit; miss one and the auth tests fail (or worse, diverge) for reasons unrelated to auth.
  - Fix: Base client_no_auth/client_auth on the app_client fixture (or a shared helper in conftest) and only add the AUTH_TOKEN monkeypatch on top.

## views

```json
{
  "contracts": {
    "reviewer": "98c14ab7-ced5-4b99-ba80-0688fcb00471",
    "status": "completed"
  },
  "correctness": {
    "reviewer": "98c14ab7-ced5-4b99-ba80-0688fcb00471",
    "status": "completed"
  },
  "design": {
    "reviewer": "98c14ab7-ced5-4b99-ba80-0688fcb00471",
    "status": "completed"
  },
  "documentation": {
    "reviewer": "98c14ab7-ced5-4b99-ba80-0688fcb00471",
    "status": "completed"
  },
  "performance": {
    "reviewer": "98c14ab7-ced5-4b99-ba80-0688fcb00471",
    "status": "completed"
  },
  "robustness": {
    "reviewer": "98c14ab7-ced5-4b99-ba80-0688fcb00471",
    "status": "completed"
  },
  "security": {
    "reviewer": "98c14ab7-ced5-4b99-ba80-0688fcb00471",
    "status": "completed"
  },
  "tests": {
    "reviewer": "98c14ab7-ced5-4b99-ba80-0688fcb00471",
    "status": "completed"
  }
}
```

## files_reviewed

```json
[
  "src/backend/tests/conftest.py",
  "src/backend/tests/test_api.py",
  "src/backend/tests/test_artifacts.py",
  "src/backend/tests/test_auth.py",
  "src/backend/tests/test_browser_manager.py",
  "src/backend/tests/test_database.py",
  "src/backend/tests/test_downloads.py",
  "src/backend/tests/test_models.py",
  "src/backend/tests/test_rfb.py",
  "src/backend/tests/test_runtime.py",
  "src/backend/tests/test_vnc_manager.py"
]
```
