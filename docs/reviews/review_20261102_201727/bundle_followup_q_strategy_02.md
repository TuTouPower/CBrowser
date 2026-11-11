# bundle_followup_q_strategy_02

## Summary

精查证实：repo_template 是跨仓平台投资，CBrowser 是消费方而非作者（整树由一次重组提交导入、本仓零工具链提交、上游同步通道存活）；本仓未入库 sync_manifest.json 为新 Low。

## Findings

- [Low][90] .repo_template/ (absence of sync_manifest.json and sync_policy.json); git commit 524e34e — CBrowser's template adoption left no committed sync_manifest baseline, so the documented fresh-clone re-attachment path cannot work from committed files alone
    - ID: f_followup_q_strategy_02_01; verification: static
    - Evidence: Tree-wide find returns no sync_manifest.json / sync_policy.json anywhere in the committed tree; .gitignore:43 ignores only sync_state.json, so the manifest's absence is not an ignore artifact.; .repo_template/docs/usage.md:134 defines sync_manifest.json as the portable baseline committed with sync commits ('随同步 commit 入库'), from which a fresh clone without local state re-attaches to the source while preserving the version baseline.; git log shows the template arrived via the manual reorganization commit 524e34e (2026-10-26) and no repo_sync apply/sync commit exists in history, so no manifest was ever produced for this consumer.
    - Impact: A fresh clone (e.g. this review clone, a new machine, a collaborator) cannot determine from committed files which template source or resolved template commit this copy corresponds to; the version baseline exists only in the owner's main-clone gitignored sync_state.json, contradicting the toolchain's own portability story and making template-version questions (like this one) harder to answer than designed.
    - Fix: Run one formal repo_sync status/init + sync cycle from the real source and commit the resulting .repo_template/sync_manifest.json (resolved commit plus shareable source URL, per usage.md:134), so the consumer's template baseline is recorded in-repo.

## evidence

```json
[
  "CBrowser self-identifies as a consumer, not the author: AGENTS.md:12 states '本项目使用模板仓 repo_template。此声明必须保留，消费仓不得删除。'; AGENTS.md:35 restricts .repo_template/ edits to template-evolution occasions, and AGENTS.md:46 requires reporting toolchain defects for a decision rather than fixing them locally — consumer discipline, verbatim from the template's own protocol.",
  "The shipped documentation is written for an arbitrary consumer fleet, not for this product: .repo_template/docs/usage.md is titled '消费仓如何使用 repo_template' and specifies a producer/consumer protocol — source may be a Git URL, a factory root, or a local product root (usage.md:136; repo-template-sync/SKILL.md steps 1-3), consumers keep a portable committed baseline (.repo_template/sync_manifest.json, usage.md:134) and a shared-decision file (sync_policy.json).",
  "A cross-repo feedback loop exists by design: .repo_template/skills/template-issue-report/SKILL.md has consumer repos file sanitized GitHub issues against the template repo (explicitly NOT the consumer's own origin), i.e. the toolchain is maintained in its own repo with downstream consumers reporting upstream.",
  "Git history shows zero toolchain authorship inside CBrowser: the entire .repo_template tree (90 files) entered in one bulk reorganization commit 524e34e (2026-10-26, 'reorganize repository structure to align with repo_template standards') and no later commit in the 265-commit history touches .repo_template/ at all — inconsistent with the toolchain being developed as this product's own overhead, consistent with import from an external source.",
  "In-repo operational records show the sync channel is live, with the source maintained outside and ahead of CBrowser: docs/archive/handoff.md:208/220 records the owner's main clone holds an (ignored) sync_state and 'repo_sync status 读取固定本地来源' (reads a fixed local source); docs/archive/tasks/t004_v2_stream_runtime/note.md:155 records main-clone repo_sync status showing '模板存在待同步差异' (pending template differences from the source) that the task deliberately did not pull."
]
```

## result

```json
"confirmed"
```

## limitations

```json
[
  "Other repositories are out of scope for this review: whether any other specific repo consumes repo_template today, how many consumers exist, and whether the template repo is still actively maintained at HEAD time cannot be verified from inside CBrowser. The amortization breadth across a portfolio therefore remains unproven; what is confirmed is the load-bearing premise — the toolchain is a deliberate platform artifact authored and maintained outside this product, and CBrowser consumes it through a live sync channel.",
  "sync_state.json is gitignored by design and absent from this fresh clone; the main clone's sync state is known only through archived in-repo notes (docs/archive/handoff.md, t004 note), not by direct inspection.",
  "Result 'confirmed' applies to the question's core dichotomy (deliberate platform investment consumed by this repo vs. this product's own overhead). It does not by itself dispose of f_global_strategy_03's separate component concerning hollow tests for the toolchain's destructive commands, which is independent of where the toolchain is maintained."
]
```
