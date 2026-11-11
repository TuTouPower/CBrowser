# bundle_local_template_tests

## responsibilities

- This unit is the .repo_template toolchain's own test suite: pytest modules (plus one Node-driven JS case file) that exercise the repo_task CLI (task lifecycle: create/start/finish/drop/purge/merge/integrate/cleanup), repo_sync, repo_cleanup, repo_hygiene, repo_state, md_format, the review-status checker, the view server, pending/findings/spikes tooling, and the pre-commit hook.
- A contract subset (9 modules carrying pytestmark = pytest.mark.contract, enumerated in test_contract_suite.CONTRACT_MODULES) doubles as the consumer-repo gate that repo_sync runs after applying the template (CONSUMER_TEST_COMMAND = pytest .repo_template/tests/ -q -m contract, 60s timeout in scripts/repo_sync.py).
- Shared scaffolding: review_support.py (fabricates fingerprint-valid PASS review evidence and neutralizes project verification gates in fixtures), per-module git_repo fixtures that build real temporary git repositories from the template, and CLI subprocess helpers (\_task_cli) that run the real scripts end to end.

## interfaces

- Tests drive production code through three seams: real CLI subprocesses (task.py / repo scripts via \_task_cli), in-process imports of repo_task submodules (store, lifecycle, graph, integration, ledger), and direct function calls into repo_sync / check_review_status / view_server modules.
- Fixtures bind production module constants (ctx.REPO_ROOT, TASKS_DIR, AUDIT_PATH, module-level path constants in pending/findings/spikes tooling) to tmp_path locations via monkeypatch.
- pytest.ini registers only the 'contract' marker; test_contract_suite.py asserts the marker set, the allowlist of contract modules, and that pytest.ini carries no addopts.

## dependencies

- Python 3 stdlib + pytest (monkeypatch, tmp_path, capsys); git CLI for real-repo fixtures; Node for test_chain_plan_cases.js (skipif when node is absent).
- Production code under .repo_template/scripts/ (repo_task package, repo_sync.py, check_review_status.py, view_server.py, md_format tooling) — cross-checked statically during this review.
- The template's own docs/task_template and docs/specs fixtures copied into temporary repos; fixtures/spec_pre_workflow_simplification.md feeds repo_sync migration tests.

## flows

- Real-git end-to-end flows: scaffold repo from template -> create tasks -> start (worktree+branch) -> check AC -> finish -> cleanup-worktree/integrate with handoff.json and review evidence -> assert ledger events, front matter, index and audit side effects.
- Failure/rollback flows: injected OSError via monkeypatched shutil.move/rmtree, failing audit append, failing index rebuild, failing subprocess commands — asserting byte-identical restoration of docs trees and index files.
- Gate flows: check_review_status main() scenarios (missing/stale/FAIL review evidence), workflow contract tests over spec/handoff validation, and repo_sync self-checks (export cleanliness, contract collection equality).

## constraints

- Static review only for this unit report: no test or production code was executed; all findings are from reading the tests and cross-checking the production scripts they exercise.
- The suite assumes serial in-process execution: several tests monkeypatch process-wide stdlib attributes and production module globals (see findings f_template_tests_06, f_template_tests_13).
- Git history for the whole tests directory in this snapshot is a single reorganization commit (524e34e), so per-file attribution/history probing is not possible; all issues found are pre-existing in the snapshot, none attributable to a recent change.

## decisions

- Suite design deliberately favors real git repositories and real CLI subprocesses over mocks for lifecycle behavior; mocks are concentrated on fault injection (filesystem failures) and on gate inputs (review evidence, project verification config).
- Two previously fake-green tests were deleted by the authors with explanatory comments (test_dispatch_integration.py, test_repo_sync.py) — evidence of active test-hygiene maintenance.
- The contract/non-contract split is a deliberate consumer-cost decision: only fast, dependency-light modules run in consumer repos after template sync.

## evidence

- All 32 unit files read completely (test_task_start_flow.py is 2128 lines, read in chunks including lines 1611-2128).
- Cross-check: scripts/repo_task/lifecycle.py cmd_purge (lines 747-769) refuses purge when require_primary_worktree fails, task_schedule_references is non-empty, tracked_anywhere(task dir) is true, has_unmerged_commits(branch) is true, or remove_worktree fails — grep shows purge is exercised only in test_task_archive_dir.py (with all of those guards stubbed permissive) plus message-string checks in test_evidence_repair.py.
- Cross-check: scripts/repo_sync.py lines 73-74 and 1534-1542 confirm CONSUMER_TEST_COMMAND/CONSUMER_TEST_TIMEOUT are real globals used by \_run_tests; the contract test asserts on them via __code__.co_names rather than behavior.
- Cross-check: lifecycle.py line 17 binds git_common_lock by direct import (from .locks import ...), so the purge tests' string-path patch of repo_task.locks.git_common_lock cannot affect lifecycle's binding.
- No real secrets in the unit: credential-looking strings are obvious placeholders ('secret', 'dirty secret', 'super_secret_value' in the MCP env-sanitization test that verifies placeholder replacement); fixture .env files contain only the placeholder 'secret' inside tmp dirs.
- Skip/skipif markers in the unit are environment-gated and honest (node absence, Windows flock semantics, symlink support, customized consumer testing.md), with one weakened case reported as f_template_tests_04.

## uncertainties

- Whether cmd_purge is wrapped by any lock at the CLI layer outside lifecycle.py was checked in cli.py (no wrapper found; purge.set_defaults(func=cmd_purge)) — the no-op lock stub finding rests on this static reading.
- Runtime behavior (whether every described test currently passes) was not verified, per the static-review constraint; findings concern what the tests do and do not establish, not current pass/fail state.
- Duplicated \_valid_spec replacement tables across modules were compared by reading; byte-level identity of every copy was not diffed mechanically.

## Findings

- [Medium][90] .repo_template/tests/test_task_archive_dir.py:246-318 — Purge's safety-refusal guards are stubbed off in the only purge tests, so every refusal branch of the most destructive command is untested

    - ID: f_template_tests_01; verification: static
    - Evidence: Both purge tests (test_purge_tombstone_cleanup_failure_warns_and_completes_purge, test_purge_audit_failure_restores_directory_and_derived_index) monkeypatch lifecycle.require_primary_worktree -> None, task_schedule_references -> [], tracked_anywhere -> False, has_unmerged_commits -> False, remove_worktree -> (True, '').; Production cmd_purge (scripts/repo_task/lifecycle.py:747-769) refuses with sys.exit when the task is still referenced by the schedule graph, when the task dir is tracked on any branch, when the branch has unmerged commits, or when remove_worktree fails; a grep for 'purge' across tests/ finds no other test exercising these refusals (test_evidence_repair.py only checks message strings).; The tests stub repo_task.locks.git_common_lock via string-path monkeypatch.setattr, but lifecycle.py:17 binds git_common_lock by direct import, so that stub cannot affect lifecycle's binding (and cmd_purge does not consult it) — part of the isolation the tests appear to set up is a no-op.
    - Impact: A regression that weakens or drops any purge refusal (e.g. purging a task that is tracked, referenced, or has unmerged commits) would pass the entire suite while silently enabling irreversible deletion of real work.
    - Fix: Add purge tests against the real-git git_repo fixture that trigger each refusal with guards active: referenced task (depends_on/conflicts_with pointing at it), task dir committed on a branch, branch with an unmerged commit, and remove_worktree failure — asserting SystemExit, the refusal message, and that the task directory and index are untouched.

- [Medium][95] .repo_template/tests/test_task_start_flow.py:1234-1264 — test_drop_keeps_archived_state_when_index_rebuild_fails never invokes cmd_drop — it hand-simulates the scenario and asserts a disjunction

    - ID: f_template_tests_02; verification: static
    - Evidence: The test defines fake_rebuild_index/calls bookkeeping that is never installed or used (dead code, lines 1237-1243).; Instead of calling lifecycle.cmd_drop, the test itself moves the task directory with shutil.move, then calls the monkeypatched lifecycle.rebuild_index directly and asserts the stub raises 'disk full'.; The key postcondition is assert got['status'] in ('dropped', 'backlog') — satisfied by either the success or the rollback outcome, so the test passes under both semantics its docstring claims to pin down.
    - Impact: The named behavior — drop's handling of an index-rebuild failure after the archive move (keep archived state, report index needs repair) — has no actual coverage; a regression in cmd_drop's real error path (e.g. wrongly moving the directory back, corrupting front matter, or swallowing the error) would go undetected.
    - Fix: Drive the scenario through lifecycle.cmd_drop in-process with only store/lifecycle.rebuild_index patched to fail at the post-archive call, and assert the exact contract: directory stays under docs/archive/tasks, front matter status is exactly 'dropped', and the raised/reported error names the index as needing repair.

- [Low][85] .repo_template/tests/review_support.py:13-35 — End-to-end fixtures fabricate the PASS review evidence and disable project verification gates, so the full flow never runs a genuine review or real gate commands

    - ID: f_template_tests_03; verification: static
    - Evidence: ensure_review_evidence (line 22) writes review_code.md/review_test.md containing 'verdict: PASS' with the real current scope fingerprint; it is used by 7 call sites across the integration fixtures.; configure_project_verification (lines 25-35) writes docs/specs/testing.md with doctor/test/blackbox gates set to the disabled value in every real-git fixture, and appends a specs-index exemption line to every fixture note.md.; Real gate-command execution is only covered with synthetic commands (false / exit 7) in isolated run_checks tests; no test pairs the complete start->finish->integrate flow with gates that actually execute project commands.
    - Impact: The workflow state machine is well covered, but the evidence pipeline is only tested for plumbing (fingerprint match, verdict parsing). Regressions in what the gates accept as evidence content, or in run_checks' real command execution within the full flow, would not be caught by the end-to-end suite.
    - Fix: Add one end-to-end scenario whose fixture testing.md configures a real trivially-passing command (and a failing variant) and whose review reports are produced through the same writer path a reviewer uses, asserting the flow succeeds/fails on the genuine gate outcomes.

- [Low][90] .repo_template/tests/test_precommit_hook.py:176-194 — Python 3.9 compatibility test silently falls back to whatever /usr/bin/python3 is, so it can pass without ever running 3.9

    - ID: f_template_tests_04; verification: static
    - Evidence: Line 179: system_python = shutil.which('python3.9') or '/usr/bin/python3'; if that path exists the test runs the hook under it and asserts success (no TypeError).; On a modern system /usr/bin/python3 is 3.11+/3.12, so the test's 3.9-compat claim is exercised against a newer interpreter; only when neither binary exists does it skip (lines 180-184).
    - Impact: The hook's declared Python 3.9 compatibility (the reason this test exists) can regress — e.g. use of 3.10+ syntax or stdlib — while this test stays green on developer machines and CI images that lack a real python3.9.
    - Fix: Resolve strictly: if shutil.which('python3.9') is None, skip with the reason; do not substitute another interpreter. Optionally assert the resolved interpreter's version_info[:2] == (3, 9) before running.

- [Low][95] .repo_template/tests/test_contract_suite.py:100-118 — test_sync_apply_runs_contract_suite asserts on \_run_tests' bytecode co_names instead of observable behavior

    - ID: f_template_tests_05; verification: static
    - Evidence: Line 104: source = rs.\_run_tests.__code__.co_names, followed by assertions that CONSUMER_TEST_COMMAND / CONSUMER_TEST_TIMEOUT appear in the function's global-name table.; Production \_run_tests (scripts/repo_sync.py:1534-1542) currently references those globals, so the test passes — but any behavior-preserving refactor (e.g. resolving the constants through a helper or a module-level alias) changes co_names and fails the test, while the assertion itself never proves the command or timeout is actually used at runtime.
    - Impact: A brittle internal-structure assertion in the consumer-facing contract suite: it can false-fail after legitimate refactors of repo_sync, training maintainers to distrust or delete the gate, and it duplicates weaker coverage than the behavioral timeout test already present in test_repo_sync.py.
    - Fix: Replace with a behavioral assertion: stub subprocess.run in repo_sync, call \_run_tests on a fixture consumer repo, and assert the invoked argv equals CONSUMER_TEST_COMMAND and the timeout kwarg equals CONSUMER_TEST_TIMEOUT.

- [Low][90] .repo_template/tests/test_task_archive_dir.py:246-318 — Suite-wide pattern of monkeypatching process-global stdlib attributes (subprocess.run, os.\*, shutil via module alias) makes correctness depend on serial execution

    - ID: f_template_tests_06; verification: static
    - Evidence: monkeypatch.setattr(lifecycle.shutil, 'move'/'rmtree', ...) in test_task_archive_dir.py and test_task_start_flow.py patches the shared stdlib shutil module object itself (lifecycle.shutil is the stdlib module), so every in-process caller sees the fake for the test's duration.; Same pattern elsewhere: subprocess.run replaced globally in test_repo_hygiene.py, test_repo_cleanup.py, test_repo_sync.py and test_md_format.py; os.replace/os.fsync/os.umask replaced in test_task_save.py.; monkeypatch restores values at teardown, but within the window the SUT's other modules, fixture code and pytest internals all observe the patched attribute; nothing in pytest.ini or the suite guards against parallel (pytest-xdist) or reordered execution.
    - Impact: Tests can interfere with each other or mask real behavior when run in parallel, in a different order, or when production code starts calling the same stdlib function from a second module — failures would be intermittent and hard to attribute.
    - Fix: Prefer patching the name in the consuming module's namespace (e.g. lifecycle.move if imported directly, or a small seam function in production code) over patching the stdlib module object; where global patching is unavoidable, document the serial-execution assumption in pytest.ini.

- [Low][85] .repo_template/tests/test_check_review_status.py:351-613 — check_review_status main() scenarios stub the checker's own current_scope_fingerprint, leaving main's wiring to the real fingerprint untested end to end

    - ID: f_template_tests_07; verification: static
    - Evidence: At least 9 main()-level scenarios (lines 351, 419, 489, 506, 521, 538, 558, 574, 589, 613) monkeypatch crs.current_scope_fingerprint to a constant lambda (or a defect-driven variant returning '0'\*16).; The real function is exercised directly in test_review_scope_fingerprint.py and test_dispatch_integration.py (real-git untracked-file case), but always called by the tests themselves — never through crs.main with a real task dir and anchor.; One scenario (test_main_reports_missing_disposition) does run unstubbed, but its note.md carries no diff_anchor, so it does not exercise the anchored fingerprint path through main either.
    - Impact: A wiring regression inside main — wrong argument order/shape when calling current_scope_fingerprint(task_dir, anchor), or mishandling of its None/raising cases — would pass all main() tests while breaking the real stale-evidence detection the checker exists for.
    - Fix: Add one main() scenario on a real-git fixture (mirroring the dispatch-integration setup) that writes a genuine review report with the real fingerprint, asserts PASS, then modifies a tracked file and asserts main reports stale — with no stubbing of current_scope_fingerprint.

- [Low][90] .repo_template/tests/test_task_modularization.py:46-116 — Structural source-text assertions (line counts, substring scans, __wrapped__/spy wiring checks) test implementation shape instead of behavior

    - ID: f_template_tests_08; verification: static
    - Evidence: test_task_modularization.py asserts scripts/task.py is under 30 lines, scans module sources for substrings such as 'import task' not in text (which misses dynamic imports and can false-positive on comments/docstrings), and checks for literal 'main()' text.; test_dispatch_integration.py asserts cmd_integrate exposes __wrapped__ and spies on integration.file_lock to prove chain locking — both are internal wiring details of the current implementation.; These sit alongside genuinely behavioral CLI tests in the same files, so the structural assertions add failure modes without adding contract coverage.
    - Impact: Behavior-preserving refactors (inlining a helper, renaming a decorator, moving code between the facade and submodules) break the suite without any user-visible contract changing, which erodes trust in the modularization guardrails these tests were written to enforce.
    - Fix: Replace source-shape assertions with import/AST-level checks (parse the facade's AST for import statements; assert the CLI surface via --help and dispatch behavior) and replace the __wrapped__/file_lock spy checks with an observable concurrency test (two overlapping integrates, one waits/fails on the held lock).

- [Low][95] .repo_template/tests/test_evidence_repair.py:161-161 — Tautological filler assertion at the end of a rewind-messages test

    - ID: f_template_tests_09; verification: static
    - Evidence: Line 161: assert \_identity_args(identity) — asserts only that a test helper returns a non-empty list, at the end of a test whose stated purpose is verifying rewind/recovery message contents.; Every other call site uses \_identity_args(identity) as argument expansion for real CLI invocations (lines 62-148); the bare assert adds no coverage of the behavior under test.
    - Impact: Minor: inflates the apparent assertion count and can mislead a reader into thinking the identity arguments themselves were validated against the reserved attempt.
    - Fix: Delete the line, or replace it with a meaningful check (e.g. the args equal the attempt/execution ids returned by the reserve call earlier in the test).

- [Low][85] .repo_template/tests/test_task_start_flow.py:117-117 — CLI subprocess helpers run without timeouts, so a deadlocked production CLI hangs the whole suite instead of failing

    - ID: f_template_tests_10; verification: static
    - Evidence: \_task_cli in test_task_start_flow.py (line 117), test_dispatch_integration.py (line 100) and test_goal.py invoke subprocess.run without a timeout argument; the same holds for most \_git helpers.; Only the pre-commit hook tests (timeout=30) and the flock probe tests in test_review_report_regressions.py (timeout=5-10) bound their subprocesses; one design-regression test bounds its contract-suite subprocess at 120s.; The toolchain explicitly models lock contention (git_common_lock, chain locks, dispatch ledger locks), i.e. a deadlock in the CLI is a realistic failure mode these tests are meant to catch.
    - Impact: A locking regression that deadlocks the CLI would hang CI/the consumer contract run indefinitely (or until an outer job timeout kills it) with no per-test diagnosis, instead of failing the specific scenario.
    - Fix: Give \_task_cli and the shared subprocess helpers a generous default timeout (e.g. 60s) that raises a clear failure naming the command, keeping the existing shorter timeouts for lock probes.

- [Low][85] .repo_template/tests/test_goal.py:28-55 — The \_valid_spec placeholder-replacement scaffolding is copy-pasted across at least three modules with an already-divergent fourth variant

    - ID: f_template_tests_11; verification: static
    - Evidence: \_valid_spec is defined independently in test_goal.py (line 28), test_task_start_flow.py (line 29, with an extra unknown_contract_item parameter) and test_dispatch_integration.py; test_task_document_validation.py carries a fourth variant, \_fill_spec_text (line 19), with a different replacement set.; test_workflow_contracts.py imports the helper from test_dispatch_integration instead of redefining it, showing a shared-home pattern already exists but was not applied consistently.
    - Impact: When the task template's placeholders change, three to four copies must be updated in lockstep; a missed copy produces confusing failures in unrelated modules, and the existing divergence (extra parameter, different replacements) makes it unclear which copy is canonical.
    - Fix: Move the canonical spec-filling helper into review_support.py (the existing shared test-support module) and have all modules import it, keeping per-module overrides as thin wrappers where a variant is genuinely needed.

- [Info][90] .repo_template/tests/test_render_review_prompts.py:19-28 — Module-wide autouse fixture disables diff-anchor validation by default (disclosed, but new tests silently inherit the stub)

    - ID: f_template_tests_12; verification: static
    - Evidence: An autouse fixture (line 25) replaces rrp.validate_diff_anchor with the identity function for every test in the module; the two tests that exercise the real validator (lines 301, 314) must explicitly opt back in via REAL_VALIDATE_DIFF_ANCHOR (line 19).; The stub is disclosed in the fixture's docstring, and anchor drift itself is covered elsewhere (test_workflow_contracts.py, test_review_scope_fingerprint.py).
    - Impact: Low risk today, but any future render test added to this module will silently skip anchor validation; a prompt-rendering regression that only manifests with invalid anchors would be missed by exactly the tests closest to it.
    - Fix: Invert the default: stub validate_diff_anchor only in the tests that need deterministic prompts (named fixture, not autouse), leaving the real validator active elsewhere.

- [Info][80] .repo_template/tests/test_view_server.py:387-440 — View-server tests mutate module-global cache state without restoring it and authenticate with the private \_SESSION_TOKEN

    - ID: f_template_tests_13; verification: static
    - Evidence: The cache-debounce test assigns view_server.\_CACHED_HTML directly (line 387) and manipulates the module's last-render timestamp, with no teardown restoring the originals.; Handler tests build requests using the module-private \_SESSION_TOKEN as the valid credential rather than obtaining a token through the server's public surface.; No other test in the suite currently calls the rendered-HTML path afterwards in the same process, so the leakage is presently harmless — but it is order-dependent by construction.
    - Impact: Fragility only: a future test that renders HTML after the debounce test in the same process could observe the earlier test's fake cached page, producing confusing order-dependent failures.
    - Fix: Snapshot and restore \_CACHED_HTML/\_LAST_RENDER_TIME around the debounce test (or expose a cache-reset helper in view_server for tests), and fetch the session token through the same accessor the server itself uses.

## views

```json
{
  "contracts": {
    "reviewer": "3aa25552-0b3c-4e6b-9d80-4c85934056c7",
    "status": "completed"
  },
  "correctness": {
    "reviewer": "3aa25552-0b3c-4e6b-9d80-4c85934056c7",
    "status": "completed"
  },
  "design": {
    "reviewer": "3aa25552-0b3c-4e6b-9d80-4c85934056c7",
    "status": "completed"
  },
  "documentation": {
    "reviewer": "3aa25552-0b3c-4e6b-9d80-4c85934056c7",
    "status": "completed"
  },
  "performance": {
    "reviewer": "3aa25552-0b3c-4e6b-9d80-4c85934056c7",
    "status": "completed"
  },
  "robustness": {
    "reviewer": "3aa25552-0b3c-4e6b-9d80-4c85934056c7",
    "status": "completed"
  },
  "security": {
    "reviewer": "3aa25552-0b3c-4e6b-9d80-4c85934056c7",
    "status": "completed"
  },
  "tests": {
    "reviewer": "3aa25552-0b3c-4e6b-9d80-4c85934056c7",
    "status": "completed"
  }
}
```

## files_reviewed

```json
[
  ".repo_template/tests/fixtures/spec_pre_workflow_simplification.md",
  ".repo_template/tests/package.json",
  ".repo_template/tests/pytest.ini",
  ".repo_template/tests/review_support.py",
  ".repo_template/tests/test_chain_plan.py",
  ".repo_template/tests/test_chain_plan_cases.js",
  ".repo_template/tests/test_check_review_status.py",
  ".repo_template/tests/test_contract_suite.py",
  ".repo_template/tests/test_design_regressions.py",
  ".repo_template/tests/test_dispatch_integration.py",
  ".repo_template/tests/test_evidence_repair.py",
  ".repo_template/tests/test_goal.py",
  ".repo_template/tests/test_md_format.py",
  ".repo_template/tests/test_pending.py",
  ".repo_template/tests/test_plan.py",
  ".repo_template/tests/test_precommit_hook.py",
  ".repo_template/tests/test_render_review_prompts.py",
  ".repo_template/tests/test_repo_cleanup.py",
  ".repo_template/tests/test_repo_hygiene.py",
  ".repo_template/tests/test_repo_state.py",
  ".repo_template/tests/test_repo_sync.py",
  ".repo_template/tests/test_review_report_regressions.py",
  ".repo_template/tests/test_review_scope_fingerprint.py",
  ".repo_template/tests/test_task_archive_dir.py",
  ".repo_template/tests/test_task_document_validation.py",
  ".repo_template/tests/test_task_modularization.py",
  ".repo_template/tests/test_task_save.py",
  ".repo_template/tests/test_task_scheduling.py",
  ".repo_template/tests/test_task_start_flow.py",
  ".repo_template/tests/test_task_unverified.py",
  ".repo_template/tests/test_view_server.py",
  ".repo_template/tests/test_workflow_contracts.py"
]
```
