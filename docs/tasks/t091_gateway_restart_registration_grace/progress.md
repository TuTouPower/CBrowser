---
tid: "t091"
slug: "gateway_restart_registration_grace"
title: "修复 Gateway 瞬断与重启期间误清活跃会话注册状态"
status: "done"
branch: "t091_gateway_restart_registration_grace"
worktree: ""
review_level: "single"
review_limit: "5"
verify_limit: "5"
diff_anchor: "675c51ca4217adfa6a2cd190e7c05b0c6d69a3be"
spec_source_sha: "675c51ca4217adfa6a2cd190e7c05b0c6d69a3be"
depends_on: ""
conflicts_with: ""
note: "来源 p146；保留 known=True/recovery_armed 会话在 gateway_missing/gateway_unreachable 期间的恢复宽限，仍清理已失活陈旧记录，消除 ac003 Gateway 重启竞态"
---

# Task 进展

front matter 只经 `task.py` 修改；reviewer 只写对应 `review_*.md`。

## 实施笔记

执行期记录关键步骤、决策、验证、阻塞和用户批准的新轮次上限。

创建期不预测实施步骤。只记有追溯价值的内容；无事项时写“无”。

实现已完成（SupervisorCore 两处Gateway边界统一保留 `known`/`recovery_armed` 恢复宽限，仅清理失活陈旧记录），测试与文档同步完成。全量门禁记录见下节。

### 跨会话接管判定（recovery）

原 codex 执行会话（`owner_id=codex_57ad2a90d2a44d4d8e1bea99def04084`）达用量上限无法继续，attempt#1 仍 `running`、未写 terminal/report。主仓 `python3 .repo_template/scripts/task.py recovery t091` 输出原文：

```json
{
  "tid": "t091",
  "phase": "committed_unreported",
  "action": "验证最终提交和 review gate；按原 identity 补缺失的 terminal/report，不重复写已有事件",
  "attempt": 1,
  "execution_id": "82171dc7f4204346b028b41ba497082f",
  "owner_id": "codex_57ad2a90d2a44d4d8e1bea99def04084",
  "branch": "t091_gateway_restart_registration_grace",
  "worktree": "../cbrowser_t091",
  "task_dir": "../cbrowser_t091/docs/tasks/t091_gateway_restart_registration_grace"
}
```

逐项存在性核对（recovery 输出字段，均通过）：

- `tid=t091`：ledger 存在 t091 事件 ✓
- `attempt=1`：ledger `attempt_reserved t091#1` ✓
- `execution_id=82171dc7f4204346b028b41ba497082f`：ledger `attempt_reserved` 与 `handoff.json` 一致 ✓
- `owner_id=codex_57ad2a90d2a44d4d8e1bea99def04084`：ledger `execution_claimed t091#1` 当前 claim ✓
- `branch=t091_gateway_restart_registration_grace`：`refs/heads/...` = `7556cb7` ✓
- `worktree=../cbrowser_t091`：`git worktree list` 登记，HEAD=`7556cb7` ✓（路径按仓库卫生门禁以相对形式记录，避免开发者 home 绝对路径）
- `task_dir`：含 `task.md` / `progress.md` / `review_general.md` / `handoff.json` ✓
- `phase=committed_unreported`：实现 commit 已提交、review gate 已过，仅缺 terminal/report；无 `terminal`/`report` 事件，attempt 仍 `running` ✓

结论：recovery 判定可由原 identity 补关单，无需新 claim。按此用 recovery 给出的 owner-id 跑 `run-close --result done`，再合入并 push。

## 全量门禁记录

### 第 1 轮（2026-11-20T00:14:00+08:00）— 一次全量跑通

- 命令：`CBROWSER_RUN_E2E=1 CBROWSER_E2E_REQUIRED=1 CBROWSER_GATE_WORKERS=1 CBROWSER_GATE_EVIDENCE_DIR=.scratch/t091_gate_r1 scripts/run_gates.sh`（当前 worktree `cbrowser_t091`，证据模式；`CBROWSER_GATE_WORKERS=1` 规避已知 `-n 4` 并行 SQLite WAL 写锁与 E2E 资源抖动；worker 隔离与套件集合不变）。
- 证据：`.scratch/t091_gate_r1/`；`run_id=68c50aceb2604a0d96bb9807b9a8064a`，`manifest.json.all_passed=true`，`cleanup_exit_code=0`，`suites.tsv` 11 条退出码全 0。
- 前置核对：E2E collection preflight 单进程 `108 tests collected`；字体集 windows/macos 各 1 套 `integrity.ok=True`；7 个镜像 sha256 ID 本地均可解析。
- 镜像身份（`manifest.json.image_identity`）：Supervisor `sha256:625886a34b34…` 已核内嵌 `/app/cbrowser/supervisor/core.py` 含 `_should_drop_registration_on_gateway_outage` 及三处 t091 标记（非旧镜像）；Browser `sha256:00969a0d4932…`、Stream `sha256:769e3867859a…`、Gateway `sha256:c20bba600020c…`、API `sha256:84e8092bee3a…`、Caddy `sha256:70b3180738b4…`、invalid-policy `sha256:d9e853e87e55…`、network-policy 同 Supervisor。

|suite|exit|计数（junit / 日志）|证据存在性核对|
|---|---|---|---|
|protocol_drift_check|0|协议/OpenAPI 导出一致|`logs/protocol_drift_check.log` 存在且非空|
|requirements_check|0|各镜像 group requirements 与锁一致|`logs/requirements_check.log` 存在且非空|
|contract|0|389 tests / 0 fail / 0 err / 1 skip|`logs/contract.log` + `junit/contract.xml` 均存在且非空|
|unit|0|2489 tests / 0 fail / 0 err / 13 skip|`logs/unit.log` + `junit/unit.xml` 均存在且非空|
|integration|0|229 tests / 0 fail / 0 err / 18 skip|`logs/integration.log` + `junit/integration.xml` 均存在且非空|
|design_lint|0|0 error / 0 warning；106 src + 7 public clean|`logs/design_lint.log` 存在且非空|
|design_check|0|design_tokens.css 与品牌资源 up to date|`logs/design_check.log` 存在且非空|
|frontend_test|0|722 cases（最低 499）|`logs/frontend_test.log` 存在且非空|
|frontend_build|0|dist 校验 + selkies 新鲜度通过|`logs/frontend_build.log` 存在且非空|
|image_packages|0|5 镜像包集与 uv.lock 导出一致|`logs/image_packages.log` 存在且非空|
|e2e|0|108 tests / 0 fail / 0 err / 2 skip（106 通过）|`logs/e2e.log` + `junit/e2e.xml` 均存在且非空|

逐项核对：11 个 suite 的 log 全部存在且非空；contract/unit/integration/e2e 4 份 junit 全部存在且非空，`fail=0 / err=0`；`suites.tsv` 11 条与 manifest 名称顺序逐条一致、退出码全 0。E2E 两阶段为并行腿 `44 passed / 2 skipped` 与串行腿 `62 passed / 46 deselected`，合并 junit 即 108 tests —— 上轮 4 个偶发失败本轮在同一完整套件内全部通过，无逐项复跑补票。结论：一次全量运行全绿，门禁通过。

## Review 处置

每个结构化 finding 一行。`已修` 表示本 task 已修复；`遗留` 必须指向 `pNNN` 或 follow-up tid；`撤回` 必须写清理由。critical/important 未解决时不得 PASS。

### Round 1（2026-11-20T00:25:45+08:00）

Round 1 零 finding（clean review）。`review_general.md` verdict PASS，`task.py review-status` 判 `review_level=single / general_verdict=PASS / overall=PASS / review_scope=ok / ac_review=ok / round=1 / next_action=finalize`。

AC 复验（`review_general.md`「AC 复验方式」）：AC-001 `TICK-VALID`（re_verified，两处边界保留 `known=True` 且不触发 `start_stream`，宽限过期后 Stream-only 替换）；AC-002 `TICK-VALID`（re_verified，陈旧 `known=False and not recovery_armed` 在两边界清除，`recovery_armed` 与 immediate-failed 契约保持）；AC-003 `TICK-VALID`（trust_prior，reviewer 独立重跑 t091+t026+t055 共 51 passed，全量门禁/E2E 依实施侧 manifest/junit 与镜像内嵌 t091 代码核验）。无 finding 需处置。

## 收尾报告

### 验收与验证

- task：[`task.md`](task.md)
- 结果：全部满足
- 测试：全量门禁第 1 轮 11/11 suite 通过（证据模式 `run_id=68c50aceb2604a0d96bb9807b9a8064a`，见「全量门禁记录」）。contract 389 tests / 0 fail / 0 err / 1 skip；unit 2489 / 0 / 0 / 13；integration 229 / 0 / 0 / 18；frontend_test 722 cases；e2e 108 / 0 fail / 0 err / 2 skip（106 通过）。
- 黑盒：真实 Docker E2E 全量通过，含 `test_gateway_ac003_media_e2e::test_ac003_dual_chrome_media_inputs_and_gateway_recovery_v2`（41.349s，Gateway SIGKILL→退避→restart→重注册→媒体恢复）；Supervisor 镜像 `sha256:625886a34b34…` 内嵌 t091 修复（三处 `_should_drop_registration_on_gateway_outage`），非旧镜像。
- review：single 级 `review_general.md` Round 1 零 finding，verdict PASS；`task.py review-status` `overall=PASS / next_action=finalize`。
- AC 判定：见 `task.md` 行内打勾（AC-001/002/003 均 `- [x]`）

### 结果摘要

- AC-001/AC-002 由新增 `tests/unit/test_t091_gateway_restart_grace.py` 与替换失效断言后的 `test_t026_supervisor_convergence.py` 覆盖；AC-003 由一次完整全量门禁验证，上轮 4 个偶发失败本轮在同一完整套件内全部通过（非逐项复跑补票）。
- 来源 pending `p146` 已 `closed` / `resolution=transferred` / `fix_ref=t091`，本 task 验证通过后无需改状态。无遗留 finding、无 follow-up tid。

### 长期文档闭环

- specs_index：`docs/specs/runtime_lifecycle.md` 与 `docs/specs/gate_verification.md` 的 front matter `tasks` 均已登记 `t091`；无正式 spike。
- 同步文档：`docs/blueprint/supervisor.md` 已更新 Gateway 不可达/缺失边界对活跃 `known=True` 与 `recovery_armed=True` 会话保留 90s 恢复宽限的收敛语义。
