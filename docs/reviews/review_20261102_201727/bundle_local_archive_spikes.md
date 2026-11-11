# bundle_local_archive_spikes

## responsibilities

- Archive of the ten completed v2 spikes s001-s010 under docs/archive/spikes/: curated spike reports, the independent review records that judged them, and the probe/container code that produced the evidence.
- Preserves the evidence chain behind findings d002-d014 and d016 and the validation work of tasks t001/t003-t009, after those tasks closed.
- Records negative history deliberately: rejected first attempts (s001 all-PASS claim, s005 v1, s008 false-green suite) are retained alongside the corrected verdicts.

## interfaces

- Reports reference outward to docs/findings/dNNN entries and docs/tasks/tNNN follow-ups; reviews pin code snapshots by SHA-256 manifests.
- Probe control surfaces archived as code: s003 token-authenticated supervisor control, s005 unauthenticated UDS capture-policy agent, s006 gateway/agent WebSocket protocol, s008 unauthenticated auxiliary HTTP control (health/peers/restart_ice).
- Container contracts: entrypoint scripts assume the two s001 base images (cbrowser-spike-runtime-browser/stream:test), shared X11/Pulse volumes and per-spike cbrowser-spike-\* resource prefixes.

## dependencies

- s001 base images are a precondition for the s004-s009 container probes; most harnesses also require a macOS/OrbStack host, host Chrome and uv/Playwright.
- External systems exercised: Selkies 2.1.0, coturn, CloakBrowser SDK 0.6.4 (s010), Docker.
- Disposition targets outside the unit: docs/findings/ and docs/archive/tasks/ (existence cross-checked only).

## flows

- Spike lifecycle: probe runs in an independent scratch copy -> independent review replays and hashes sources -> curated report.md with scope banner adopts only technical feasibility -> conclusions land in docs/findings/dNNN -> repo-hygiene moves the spike into docs/archive/spikes/.
- TURN credential flow (s002/s008): a per-run random shared secret is written to a 0600 file and mounted read-only; short-lived (120s TTL) HMAC REST credentials are derived per generation and per role; passwords are never logged, usernames are.
- Cleanup flow: every harness scopes creation and teardown to its own cbrowser-spike-\* container/network/volume names; s010 additionally warns against fuzzy-prefix cleanup of other runs.

## constraints

- Repo rule (AGENTS.md): docs/archive/ mirrors original paths and is append-only; archived files must not be edited in place.
- Reports uniformly instruct: copy code to an independent scratch directory, never run in docs/, never run two same-prefix suites concurrently.
- All results are OrbStack arm64 technical observations; every report separates adopted technical feasibility from production acceptance and leaves public-network, native Linux x86_64 and long-duration gates unproven.
- Secrets discipline stated by the spikes themselves: per-run random secrets, 0600 files, no committed or printed credentials.

## decisions

- Each report’s adoption decision is “yes, feasibility only” with the production gates explicitly retained (t001 scope_adjustment.md is named as the current gate authority).
- s008: the original dual-end same-URL/same-credential fixture was wholly replaced by the split-topology suite; its history report was retained as report_same_url.md.
- s005: report_v1.md is a frozen CONDITIONAL ACCEPT snapshot; report.md supersedes it.
- s003/s005/s006 reviews corrected overstated claims (100% recovery, latency-chapter compliance, DataChannel bypass) and the reports record which conclusions were not adopted.

## evidence

- Existence cross-check (this review): every finding referenced by the spikes exists in docs/findings/ (d001-d025 present, including d002-d014 and d016); t001 exists at docs/archive/tasks/t001_v2_runtime_validation/ and contains scope_adjustment.md; t003, t004, t005, t007, t008 are archived and t009-t012 are the current tasks. No spike verdict is left without a disposition target at existence level.
- Archive marking: 8 of 10 spike report.md files carry the scope-update banner; report_v1.md self-marks as a frozen v1 snapshot in its body.
- Credential hygiene is mostly good in the archive: s002 documents a local-only 0600 TURN secret; s003/s006/s007 secrets are per-run random; s008 logs usernames only and its reviews verify no credential output.
- No third-party copied code was found in the unit: all duplicated code is intra-project fixture copying, and no license or attribution problems were identified (external systems are used via their images/SDKs, not vendored).
- Production cross-check for archived dangerous patterns: Xvfb -ac/-listen tcp and PulseAudio auth-anonymous do not appear in src/ or config/ (runtime uses auth-anonymous=0 and Xauthority); --enable-basic-auth=false appears once in the current stream entrypoint but with Selkies bound to 127.0.0.1.
- Failure history is intact: s001 first_review rejects the original all-PASS report, s005 keeps its first native failure and v1 gaps, s006 keeps its first exit-1 run, s008 keeps the FAIL review of the false-green suite.

## uncertainties

- Coverage mode for generated artifacts: s001 image_manifest.json was audited at structure plus representative-content level, as permitted for this unit; all prose, scripts and code were read in full except as follows.
- s003 container_cdp_probe.py was covered by a full diff against its near-identical sibling test_cdp_real.py (3 differing spots) plus a head read, rather than an independent line-by-line read.
- s007 run_isolation_probe.py (1054 lines) and the s008 stage2 probes (604/401 lines) were covered by complete structural maps (all functions, assertions, docker invocations, secret handling) plus section reads of every security-relevant region, not a literal line-by-line pass.
- Findings/tasks cross-check was existence-only by design; whether each archived verdict was substantively dispositioned inside those documents belongs to the docs_current unit.
- Whether the pushed public remote still contains the same personal paths was not re-verified online (browser use is out of scope for this review); conclusions rest on the local tree at HEAD 5136766.

## Findings

- [Medium][90] docs/archive/spikes/s005_capture_policy/code/entrypoint_browser.sh:7-7 — Archived container entrypoints disable access control on X11, PulseAudio and Selkies surfaces

    - ID: f_archive_spikes_01; verification: static
    - Evidence: s005 code/entrypoint_browser.sh:7 starts Xvfb with -listen tcp -ac (X11 over TCP with access control disabled).; PulseAudio auth-anonymous=1 in s001 code/entry_browser_full.sh:11, s004 code/entrypoint_browser.sh:11, s008 code/media_fixture/entrypoint_browser.sh:11 and s009 code/entrypoint_browser.sh:11.; Xvfb -ac (no -listen tcp) in s008 code/media_fixture/entrypoint_browser.sh:17 and s009 code/entrypoint_browser.sh:17.; Selkies --enable-basic-auth=false in s001 code/run_spike.sh:231, s004 code/entrypoint_stream.sh:28, s008 code/stage2_stream_entrypoint.sh:28 and s009 code/entrypoint_stream.sh:28, several bound to 0.0.0.0 inside the spike topology.; Cross-check of current tree: the PulseAudio anonymous pattern did not propagate (src/backend/cbrowser/runtime_agent/runner.py uses auth-anonymous=0), but --enable-basic-auth=false does appear in the current stream entrypoint (config/docker/stream_runtime/entrypoint.sh:197), there compensated by a 127.0.0.1 bind.
    - Impact: The spike reports disclose that root/anonymous fixtures are not production acceptance, but the scripts themselves carry no warning header; anyone reusing an archived entrypoint as a runtime starting point inherits unauthenticated screen capture, input injection and audio access on any network that can reach the service.
    - Fix: Add a prominent archive-only warning header to each affected entrypoint stating the disabled controls and the production replacements (Xauthority, auth-anonymous=0, gateway auth), or strip the dangerous flags from the archived copies and note the change in the spike report.

- [Medium][85] docs/archive/spikes/s008_turn_generation_media/code/stage2_stream_runner.py:342-351 — Archived spike code exposes unauthenticated control planes that mutate live media sessions

    - ID: f_archive_spikes_02; verification: static
    - Evidence: s008 stage2_stream_runner.py:342-351 starts an auxiliary HTTP server on 0.0.0.0:18092 with no authentication; POST /restart_ice (handler at :284-339) accepts caller-supplied ICE servers including TURN credentials and forces renegotiation on a live peer.; s005 code/live_policy_agent.py:284-321 serves a control socket at /tmp/capture_policy_agent.sock with no authentication, accepts forged input-activity records and returns state including peer details and the full action history; the s005 v1 independent review already flagged that tests used it to bypass the real DataChannel.; A safer pattern exists in the same archive: s003 supervisor control requires a token (code/recovery_probe/roles.py), so the unauthenticated variants are not the archive norm.
    - Impact: These prototypes mirror the shape of the production supervisor/gateway control surfaces; copied forward, any local process (or any host that can reach a published port) could restart ICE with attacker-chosen TURN servers or forge capture-policy input state.
    - Fix: Mark both files as archive-only prototypes and either remove the control listeners from the archived copies or gate them behind the token pattern used by s003; at minimum add a header stating the endpoints are unauthenticated by design and must not be reused.

- [Medium][90] docs/archive/spikes/s006_gateway_media_recovery/code/probe/run_verification.py:35-35 — Archived harnesses write live secrets into their own source directory, and those paths are not gitignored

    - ID: f_archive_spikes_03; verification: static
    - Evidence: s006 run_verification.py:35 sets TOKEN_FILE to agent_token.secret inside the probe directory and :139-141 writes a fresh agent token there on every run.; s008 code/probe_work/start_coturn.sh:14-30 generates a random TURN shared secret and writes turn_secret.txt plus a turnserver.conf containing the static-auth-secret into probe_work/ inside the code tree (both chmod 600).; git check-ignore returns no match for agent_token.secret, turn_secret.txt or turnserver.conf, so an in-tree run leaves real secrets as untracked-but-committable files.; Mitigation on record: spike reports instruct copying code to an independent scratch directory before running, and s002 documents its TURN secret file as local-only 0600, never committed or printed.
    - Impact: A single in-tree verification run followed by a bulk git add would commit a live TURN shared secret or gateway agent token to a public repository; the archive instructions reduce but do not eliminate the risk because the scripts default to writing beside themselves.
    - Fix: Add the three generated filenames to .gitignore (or relocate the write paths to a TMPDIR/scratch env var with a hard failure when run inside the repo tree) and note the generated files in the spike reports.

- [Low][95] docs/archive/spikes/s001_selkies_runtime/blackbox_review.md:4-4 — Archived reviews in a public repository contain the developer’s personal host paths and username

    - ID: f_archive_spikes_04; verification: static
    - Evidence: Absolute macOS home-directory paths containing the account username appear at s001 blackbox_review.md:4, s004 blackbox_review.md:6, s005 independent_review.md:5, s005 independent_review_r4.md:33 and :56, s006 independent_review.md:4, s008 independent_review_split.md:33, :34 and :37, s009 independent_review.md:18.; The paths also disclose the local directory layout (project checkout and nested .scratch review workspaces).; Internal test-network addressing (dedicated Docker subnet host 172.29.0.10:3478) is printed in s002 report.md:189 and throughout the s008 evidence sections.
    - Impact: Low-grade privacy exposure: the username and workstation layout of the developer are permanently published in git history, useful for targeted phishing or social engineering; the internal addresses are experiment-scoped and low sensitivity.
    - Fix: Scrub the username-bearing path prefixes to a placeholder (e.g. $HOME or <workspace>) in the archived review files; accept that history rewrite is out of scope and treat this as a going-forward redaction plus a note in the archive.

- [Low][90] docs/archive/spikes/s001_selkies_runtime/report.md:44-44 — Reproduction instructions in archived reports still reference pre-archive docs/spikes/ paths that no longer exist

    - ID: f_archive_spikes_05; verification: static
    - Evidence: Re-run commands citing docs/spikes/... appear at s001 report.md:44, s002 report.md:30 and :199, s003 report.md:34 and :57, s003 container_download_report.md:26, s004 report.md:41, s005 report_v1.md:39 and s006 report.md:38.; The material now lives under docs/archive/spikes/; the referenced docs/spikes/ paths do not exist in the tree.; Newer reports (s007-s010) were written with archive-aware instructions, so the stale paths are confined to the earlier spikes.
    - Impact: A reader or agent following an archived report verbatim hits missing paths and may conclude the spike is unreproducible or improvise an in-tree run, which interacts with the secret-writing hazard in f_archive_spikes_03.
    - Fix: Append an archive errata note to each affected report giving the current docs/archive/spikes/ location (archive rules allow additions) rather than editing the historical command text.

- [Low][90] docs/archive/spikes/s005_capture_policy/independent_review_r4.md:20-20 — Archived reviews cite review artifacts that were never archived, breaking the hash-manifest audit trail

    - ID: f_archive_spikes_06; verification: static
    - Evidence: s005 independent_review_r4.md:20 includes a file named previous_review_r3.md in its SHA-256 manifest, but the s005 directory contains only independent_review.md and independent_review_r4.md.; s006 independent_review.md:19-20 states that review_launcher_only.md and review_cmdline_failure.md are retained, but neither exists in the s006 directory.; Directory listings of both spike folders confirm the absences; the missing files are the prior-round reviews the manifests rely on for continuity.
    - Impact: The multi-round review chain cannot be fully audited from the archive: a verifier cannot confirm what the missing rounds said or that the frozen hashes cover the complete record.
    - Fix: Add an archive note to both spikes recording that the cited files exist only in the original scratch workspace (or were not preserved), so the gap is explicit rather than discoverable only by failed lookup.

- [Low][85] docs/archive/spikes/s008_turn_generation_media/report_same_url.md:1-1 — Two archived reports lack the archive scope banner, including a superseded near-duplicate report

    - ID: f_archive_spikes_07; verification: static
    - Evidence: Eight of the ten spike report.md files open with the “范围更新” banner declaring the snapshot status and pointing to t001/scope_adjustment.md and the architecture plan for current gates.; s008 report_same_url.md has no banner and no superseded marking anywhere, yet is a near-duplicate of report.md describing the replaced same-URL/same-credential topology; s008 report.md:35-37 records that this fixture was wholly replaced and its history report retained.; s010 report.md also has no banner (mitigated by strong in-body scoping: the 5 checks are explicitly not the formal six-AC acceptance).; There is no index or README at docs/archive/spikes/ level explaining the banner convention.
    - Impact: A reader or agent landing on report_same_url.md first can mistake a superseded topology’s conclusions for current results, since nothing in the file itself signals that it is history.
    - Fix: Prepend the standard scope banner (or a one-line superseded-by pointer to report.md) to report_same_url.md and s010 report.md as archive additions.

- [Low][95] docs/archive/spikes/s003_selkies_control/code/container_uds/container_cdp_probe.py:1-1 — Whole spike files are duplicated across and within spikes, so fixes never propagate between copies

    - ID: f_archive_spikes_08; verification: static
    - Evidence: s003 container_uds/container_cdp_probe.py differs from s003 code/test_cdp_real.py in only 3 places (extra glob import, glob-based Chrome path, --no-sandbox); the rest is identical.; s006 code/media_fixture/{entry_browser_full.sh, test_cloak_loop.py, gen_wav.py} are byte-identical to the s001 files of the same names (disclosed as fixture copying in s006 report.md:22).; s007 code/fixture/test_mitshm.c is byte-identical to s001 code/test_mitshm.c (verified by diff).; s008 code/media_fixture/entrypoint_browser.sh and s009 code/entrypoint_browser.sh carry the same SHA-256 in both spikes’ independent reviews (dcbc7d70...), i.e. another verbatim cross-spike copy.; s009 ime_native_probe.py and extra_harness.py duplicate the remote_value() CDP helper verbatim.
    - Impact: Corrections applied to one copy (e.g. the Xvfb/PulseAudio hardening relevant to f_archive_spikes_01, or assertion fixes) silently leave the other copies stale, and hash manifests in reviews pin different copies inconsistently.
    - Fix: Record the duplication explicitly in the affected spike reports (source of truth copy per file) so future readers patch all copies; no code change needed inside the archive itself.

- [Low][90] docs/archive/spikes/s007_profile_isolation/code/entry_browser.sh:9-9 — Hard-coded test secrets and token-via-argv patterns persist in archived scripts

    - ID: f_archive_spikes_09; verification: static
    - Evidence: s007 code/entry_browser.sh:9 embeds a hard-coded default profile secret literal passed to the browser runner (kind: plaintext fixture sentinel, value not reproduced here).; s007 code/run_isolation_probe.py:250 and :297 embed plaintext per-profile sentinel secret literals and pass them as container command arguments, making them visible via docker inspect and process listings.; s003 code/recovery_probe/roles.py:26 compares the supervisor token with a non-constant-time != and the token is passed via --token command-line arguments in test_orchestration.py:85 and :112.; All are experiment fixtures rather than production credentials, and the s007 sentinels exist to prove cross-profile non-leakage.
    - Impact: Low direct risk, but the archive normalizes embedding secrets in scripts and argv; copied into production-adjacent tooling the same shapes leak through process lists and inspect output.
    - Fix: Note in the s007/s003 reports that the literals are deliberate fixtures and that the production pattern is the 0600 file / env channel already used by the TURN spikes.

- [Info][95] docs/archive/spikes/s002_selkies_protocol/report.md:98-98 — Encoding corruption (mojibake) is baked into several archived documents

    - ID: f_archive_spikes_10; verification: static
    - Evidence: Replacement/garbled characters appear at s002 report.md:98 and :189, s003 container_download_review.md:96, s004 blackbox_review.md:101, s005 independent_review.md:99 and s007 independent_review_r4.md:299.; The corruption sits inside otherwise load-bearing evidence text (addresses, verdict sentences), indicating the agent reports were copied into the archive through a lossy encoding step.
    - Impact: Cosmetic to mildly confusing; a small number of evidence strings are not fully legible, weakening the archive’s value as a verbatim record.
    - Fix: Leave the historical text as-is (archive is append-only) and, if the original scratch reports survive, append corrected copies; otherwise note the known-corrupt lines in the affected reports.

- [Info][90] docs/archive/spikes/s005_capture_policy/code/test_e2e_real_pipeline.py:2-2 — Overstated wording inside archived code contradicts the caution of the spike reports

    - ID: f_archive_spikes_11; verification: static
    - Evidence: s005 test_e2e_real_pipeline.py:2 and native_visibility_e2e.py:2 describe themselves as “Production-grade” in docstrings.; s003 code/test_cdp_real.py:388 prints “Recovery is 100% genuine!” while s003 report.md:51 explicitly declines “100%/彻底根除” wording.; s005 code/revision_03/test_e2e_real_pipeline.py tail (:946) summarizes “ALL 9 ... PASSED” although the retired file contains 10 scenarios including the removed Scenario 10.; s007 code/run_isolation_probe.py:13 docstring still describes Revision-2 paplay audio generation although the frozen R5 code uses browser WebAudio; s010 code/probe.py:3 names itself probe_v2.py inside a file archived as probe.py.
    - Impact: Anyone reading code before reports (the common agent workflow) receives stronger claims than the project actually adopted; the reports’ corrections only help if they are read first.
    - Fix: Rely on the existing report banners; optionally append a one-line archive note to the s005 and s003 reports listing the disclaimed in-code phrases.

- [Info][75] docs/archive/spikes/s007_profile_isolation/independent_review_r3.md:93-93 — Archived s007 reviews assert a “no exclusive lease” architecture invariant that current project documents no longer state

    - ID: f_archive_spikes_12; verification: suspected
    - Evidence: s007 independent_review_r3.md:93, independent_review_r4.md:315 and independent_review_final.md (§五) present “无独占租约机制 / 杜绝独占租约设计” as a standing CBrowser architecture property.; The current repo AGENTS.md describes the system as built on strict Profile isolation with control-lease management (控制租约管理), i.e. leases are part of the current architecture vocabulary.; The archived claim is not marked as time-scoped to the v2 spike phase.
    - Impact: A reader mining the archive for architecture constraints could adopt a superseded invariant and misjudge current lease-related design or review decisions.
    - Fix: Treat the claim as historical to the spike phase; if the blueprint still needs the distinction (exclusive vs managed leases), record it in docs/blueprint/decisions.md rather than in archived reviews.

## views

```json
{
  "security": {
    "status": "completed",
    "reviewer": "b4e77a10-2357-4856-931c-60213a0c6ddc"
  },
  "correctness": {
    "status": "completed",
    "reviewer": "b4e77a10-2357-4856-931c-60213a0c6ddc"
  },
  "contracts": {
    "status": "completed",
    "reviewer": "b4e77a10-2357-4856-931c-60213a0c6ddc"
  },
  "performance": {
    "status": "not_applicable",
    "reviewer": "b4e77a10-2357-4856-931c-60213a0c6ddc",
    "reason": "Archived one-off experiment probes with no production performance contract; latency/throughput figures in the reports are historical observations and resource bounds were spike success criteria, not service SLOs."
  },
  "design": {
    "status": "completed",
    "reviewer": "b4e77a10-2357-4856-931c-60213a0c6ddc"
  },
  "robustness": {
    "status": "completed",
    "reviewer": "b4e77a10-2357-4856-931c-60213a0c6ddc"
  },
  "tests": {
    "status": "completed",
    "reviewer": "b4e77a10-2357-4856-931c-60213a0c6ddc"
  },
  "documentation": {
    "status": "completed",
    "reviewer": "b4e77a10-2357-4856-931c-60213a0c6ddc"
  }
}
```

## files_reviewed

```json
[
  "docs/archive/spikes/s001_selkies_runtime/blackbox_review.md",
  "docs/archive/spikes/s001_selkies_runtime/code/Dockerfile.spike-browser",
  "docs/archive/spikes/s001_selkies_runtime/code/Dockerfile.spike-stream",
  "docs/archive/spikes/s001_selkies_runtime/code/entry_browser_full.sh",
  "docs/archive/spikes/s001_selkies_runtime/code/gen_wav.py",
  "docs/archive/spikes/s001_selkies_runtime/code/run_spike.sh",
  "docs/archive/spikes/s001_selkies_runtime/code/test_cloak_loop.py",
  "docs/archive/spikes/s001_selkies_runtime/code/test_mitshm.c",
  "docs/archive/spikes/s001_selkies_runtime/first_review.md",
  "docs/archive/spikes/s001_selkies_runtime/image_manifest.json",
  "docs/archive/spikes/s001_selkies_runtime/report.md",
  "docs/archive/spikes/s002_selkies_protocol/code/datachannel_restart_probe.py",
  "docs/archive/spikes/s002_selkies_protocol/code/ice_restart_probe.py",
  "docs/archive/spikes/s002_selkies_protocol/code/turn_auth_probe.py",
  "docs/archive/spikes/s002_selkies_protocol/report.md",
  "docs/archive/spikes/s003_selkies_control/blackbox_review.md",
  "docs/archive/spikes/s003_selkies_control/code/container_uds/browser_agent.py",
  "docs/archive/spikes/s003_selkies_control/code/container_uds/container_cdp_probe.py",
  "docs/archive/spikes/s003_selkies_control/code/container_uds/run_cross_container.py",
  "docs/archive/spikes/s003_selkies_control/code/container_uds/supervisor_client.py",
  "docs/archive/spikes/s003_selkies_control/code/container_uds/supervisor_override_control.py",
  "docs/archive/spikes/s003_selkies_control/code/recovery_probe/container_agent.py",
  "docs/archive/spikes/s003_selkies_control/code/recovery_probe/roles.py",
  "docs/archive/spikes/s003_selkies_control/code/recovery_probe/test_orchestration.py",
  "docs/archive/spikes/s003_selkies_control/code/test_cdp_real.py",
  "docs/archive/spikes/s003_selkies_control/code_review.md",
  "docs/archive/spikes/s003_selkies_control/container_download_report.md",
  "docs/archive/spikes/s003_selkies_control/container_download_review.md",
  "docs/archive/spikes/s003_selkies_control/recovery_review.md",
  "docs/archive/spikes/s003_selkies_control/report.md",
  "docs/archive/spikes/s004_media_connections/blackbox_review.md",
  "docs/archive/spikes/s004_media_connections/code/entrypoint_browser.sh",
  "docs/archive/spikes/s004_media_connections/code/entrypoint_stream.sh",
  "docs/archive/spikes/s004_media_connections/code/media_e2e_probe.py",
  "docs/archive/spikes/s004_media_connections/code/start_containers.sh",
  "docs/archive/spikes/s004_media_connections/code/stop_containers.sh",
  "docs/archive/spikes/s004_media_connections/report.md",
  "docs/archive/spikes/s005_capture_policy/code/entrypoint_browser.sh",
  "docs/archive/spikes/s005_capture_policy/code/entrypoint_stream.py",
  "docs/archive/spikes/s005_capture_policy/code/live_policy_agent.py",
  "docs/archive/spikes/s005_capture_policy/code/native_visibility_e2e.py",
  "docs/archive/spikes/s005_capture_policy/code/revision_03/test_e2e_real_pipeline.py",
  "docs/archive/spikes/s005_capture_policy/code/test_e2e_real_pipeline.py",
  "docs/archive/spikes/s005_capture_policy/code/test_page.html",
  "docs/archive/spikes/s005_capture_policy/independent_review.md",
  "docs/archive/spikes/s005_capture_policy/independent_review_r4.md",
  "docs/archive/spikes/s005_capture_policy/report.md",
  "docs/archive/spikes/s005_capture_policy/report_v1.md",
  "docs/archive/spikes/s006_gateway_media_recovery/code/media_fixture/entry_browser_full.sh",
  "docs/archive/spikes/s006_gateway_media_recovery/code/media_fixture/gen_wav.py",
  "docs/archive/spikes/s006_gateway_media_recovery/code/media_fixture/test_cloak_loop.py",
  "docs/archive/spikes/s006_gateway_media_recovery/code/probe/gateway_core.py",
  "docs/archive/spikes/s006_gateway_media_recovery/code/probe/run_agent_client.py",
  "docs/archive/spikes/s006_gateway_media_recovery/code/probe/run_gateway_server.py",
  "docs/archive/spikes/s006_gateway_media_recovery/code/probe/run_verification.py",
  "docs/archive/spikes/s006_gateway_media_recovery/independent_review.md",
  "docs/archive/spikes/s006_gateway_media_recovery/report.md",
  "docs/archive/spikes/s007_profile_isolation/code/Dockerfile.isolation-browser",
  "docs/archive/spikes/s007_profile_isolation/code/Dockerfile.isolation-stream",
  "docs/archive/spikes/s007_profile_isolation/code/audio_analyzer.py",
  "docs/archive/spikes/s007_profile_isolation/code/browser_runner.py",
  "docs/archive/spikes/s007_profile_isolation/code/entry_browser.sh",
  "docs/archive/spikes/s007_profile_isolation/code/entry_stream.sh",
  "docs/archive/spikes/s007_profile_isolation/code/fixture/test_mitshm.c",
  "docs/archive/spikes/s007_profile_isolation/code/run_isolation_probe.py",
  "docs/archive/spikes/s007_profile_isolation/code/test_cross_ipc.py",
  "docs/archive/spikes/s007_profile_isolation/independent_review_final.md",
  "docs/archive/spikes/s007_profile_isolation/independent_review_r3.md",
  "docs/archive/spikes/s007_profile_isolation/independent_review_r4.md",
  "docs/archive/spikes/s007_profile_isolation/report.md",
  "docs/archive/spikes/s008_turn_generation_media/code/media_fixture/entrypoint_browser.sh",
  "docs/archive/spikes/s008_turn_generation_media/code/probe_work/cleanup.sh",
  "docs/archive/spikes/s008_turn_generation_media/code/probe_work/start_coturn.sh",
  "docs/archive/spikes/s008_turn_generation_media/code/stage2_adapter.py",
  "docs/archive/spikes/s008_turn_generation_media/code/stage2_adversarial_probe.py",
  "docs/archive/spikes/s008_turn_generation_media/code/stage2_containers.sh",
  "docs/archive/spikes/s008_turn_generation_media/code/stage2_media_restart_probe.py",
  "docs/archive/spikes/s008_turn_generation_media/code/stage2_stream_entrypoint.sh",
  "docs/archive/spikes/s008_turn_generation_media/code/stage2_stream_runner.py",
  "docs/archive/spikes/s008_turn_generation_media/independent_review_failed.md",
  "docs/archive/spikes/s008_turn_generation_media/independent_review_final.md",
  "docs/archive/spikes/s008_turn_generation_media/independent_review_generation.md",
  "docs/archive/spikes/s008_turn_generation_media/independent_review_split.md",
  "docs/archive/spikes/s008_turn_generation_media/report.md",
  "docs/archive/spikes/s008_turn_generation_media/report_same_url.md",
  "docs/archive/spikes/s009_native_ime_input/code/entrypoint_browser.sh",
  "docs/archive/spikes/s009_native_ime_input/code/entrypoint_stream.sh",
  "docs/archive/spikes/s009_native_ime_input/code/extra_harness.py",
  "docs/archive/spikes/s009_native_ime_input/code/ime_native_probe.py",
  "docs/archive/spikes/s009_native_ime_input/code/investigate_compositionend.py",
  "docs/archive/spikes/s009_native_ime_input/code/start_containers.sh",
  "docs/archive/spikes/s009_native_ime_input/code/stop_containers.sh",
  "docs/archive/spikes/s009_native_ime_input/code/test_blank_cdp.py",
  "docs/archive/spikes/s009_native_ime_input/code/verify_extra_harness.py",
  "docs/archive/spikes/s009_native_ime_input/independent_review.md",
  "docs/archive/spikes/s009_native_ime_input/report.md",
  "docs/archive/spikes/s010_cloakbrowser_exit_observation/code/probe.py",
  "docs/archive/spikes/s010_cloakbrowser_exit_observation/report.md"
]
```
