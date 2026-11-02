# bundle_followup_q_system_properties_01

## Summary

精查证伪：spike harness 的 secret 写出文件在当前树与全部 265 个可达提交中从未入库，初筛三处『像真值』经结构复核均为运行时派生表达式；前瞻风险成立但未兑现，f_08 无升级依据。

## Findings

No findings.

## evidence

```json
[
  "Write-out files never landed: agent_token.secret, turn_secret.txt and turnserver.conf occur 0 times in the current tree and 0 times in any reachable commit. The whole-repo filename history across all 265 commits contains no such file anywhere (only unrelated names: docs p006_browser_runtime_agent_secret_mount.md and src/backend/cbrowser/secret_files.py, which is source code, not a secret).",
  "Current-tree secret-named assignment hits: 23 total, classified as 8 code-generation/derivation expressions, 3 placeholder, 1 fixture-sentinel (s007 entry_browser.sh:9, a shell ${VAR:-default} template whose default is the fixture sentinel already recorded in f_archive_spikes_09), 8 weak/low-entropy short test words or variable references (length 4-11), 1 ambiguous-short expression, and 2 initially flagged 'real-looking' (length 29, medium entropy) that structural re-check refuted: at docs/archive/spikes/s002_selkies_protocol/code/turn_auth_probe.py:38 and docs/archive/spikes/s008_turn_generation_media/code/stage2_media_restart_probe.py:100 the right-hand side is NOT a quoted literal but a base64.b64encode(hmac-derivation) expression truncated by the capture regex - i.e. TURN REST passwords computed at runtime, exactly the per-run generation pattern the spikes document.",
  "The third initial flag, docs/archive/spikes/s006_gateway_media_recovery/code/probe/run_gateway_server.py:34 (agent_token, length 16), is likewise an unquoted call expression (contains parenthesis and attribute access, 16 chars), and line 36 is a longer expression; neither is a committed literal token. The s006 gateway token itself flows through the agent_token.secret file written at runtime (run_verification.py:139 is a generation expression), and that file was never committed (see first evidence item).",
  "History scan gives the same picture: every blob version of spike files present in the 3 path-touching commits (524e34e, d7ee99c, 8ff9fd2) yields the identical hit set as the current tree - the same expressions, placeholders, fixture sentinels and weak test words, and no secret-file blobs at any point. No spike file version in reachable history contains a real-looking literal credential.",
  "Bare-token sweep over all spike text: 92 hex-64 tokens (SHA-256-shaped: review manifests and image digests), 2 hex-32..63, 14 base64-shaped but entropy <4.0 (readable words/paths), 12 base64-shaped high-entropy in non-credential contexts - of which 8 sit in WebRTC ICE/SDP context (consistent with ephemeral per-session material from the recorded October 2026 local-container experiments; session-bound and torn down with their containers, not shared secrets or agent tokens), 1 in session/trace-id context, 3 uncategorised.",
  "gitignore state confirmed as f_archive_spikes_03 described: git check-ignore returns no match for any of the three write-out paths (agent_token.secret, turn_secret.txt, turnserver.conf), neither at their spike locations nor as bare names; no .gitignore file is tracked under the spikes directories. The forward-looking hazard in f_03 therefore stands, but it has not materialised in tree or history."
]
```

## result

```json
"refuted"
```

## limitations

```json
[
  "Shape-based static scan only (no code was run, per the review's static constraint): a human-chosen low-entropy real password pasted without any secret-named context would evade both the assignment scan and the entropy sweep; the sweep mitigates but cannot eliminate this class.",
  "History enumeration relies on the trees of the 3 commits that git rev-list --all reports for the spike paths, plus the whole-repo filename history; git's TREESAME simplification for merges means a blob introduced solely by an evil-merge resolution cannot be fully excluded, though this repository's history is near-linear feature work and every spike file version must pass through a path-touching commit.",
  "Classification of expressions vs literals is structural (quoting, parentheses, generation keywords, entropy class); values were never reproduced, compared against live systems, or tested for validity - 'real-looking' judgements are shape judgements only, per the question's no-copy constraint.",
  "Pre-archive locations were covered by scanning both docs/spikes/ and docs/archive/spikes/ in tree and history; spikes that may have existed only in the author's scratch workspace (.scratch, never committed) are outside git reachability by definition."
]
```
