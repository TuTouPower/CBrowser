---
tid: "t093"
slug: "runtime_download_e2e_completion"
title: "按完成事件验证真实浏览器下载"
status: "done"
branch: "t093_runtime_download_e2e_completion"
worktree: ""
review_level: "single"
review_limit: "5"
verify_limit: "5"
diff_anchor: "633dc75983774e319f0338b4bf7a3d94859bd9ce"
spec_source_sha: "633dc75983774e319f0338b4bf7a3d94859bd9ce"
depends_on: ""
conflicts_with: ""
note: "来源 p148；修正下载 E2E 对临时文件的误判及转发清理检查"
---

# Task 进展

front matter 只经 `task.py` 修改；reviewer 只写对应 `review_*.md`。

## 实施笔记

执行期记录关键步骤、决策、验证、阻塞和用户批准的新轮次上限。

创建期不预测实施步骤。只记有追溯价值的内容；无事项时写“无”。

- 新增 `wait_for_captured_download`（`tests/e2e/test_browser_runtime_e2e.py:1408`）：以 `completed` 事件 + `suggested_filename` 匹配、断言 `download_path == /exchange/downloads/{guid}`、要求最终文件 `path.is_file()` 且 `read_bytes() == content`，替代原 `glob("*")` 与“先取目录首文件、后等完成事件”的顺序；消除 Chrome 空 `.crdownload` 临时文件导致的提前成功/失败与重命名竞态。
- 三个下载位点（`test_ac004`：首个、中间、重连后）与 `test_t008` 的转发位点统一经该 helper 观察；转发清理断言改为对 helper 返回的单个 `Path` 做 `assert not downloaded.exists()`。
- 移除因该改动失效的 `events_dir` 局部变量；未触及 `src/` 生产下载逻辑、镜像或协议。
- 承接原 codex 会话同一 `owner_id`（`codex_57ad2a90d2a44d4d8e1bea99def04084`），主仓 `task.py recovery t093` 判 `phase=executing`，按同 owner 直接续行；`preflight --require-verified` 为 PASS。

### 真实 E2E 验证（AC-001 / AC-002）

前置：required 模式（`CBROWSER_E2E_REQUIRED=1`）单进程 collect-only `15 tests collected`；不可变 Browser 镜像 `sha256:00969a0d4932957cc6804901fd49a45c5b47616876d73bb6db197d5d1914ddb0`（本地可解析）；引擎缓存 `data/instance/engine-cache`（chromium-146.0.7680.177.3 + geoip/GeoLite2-City.mmdb），`:ro` 挂载；gate venv Python 3.15.2。两条用例在同一候选镜像上分别运行，JUnit 保存在 `.scratch/t093_e2e/`。

|AC|用例|结果|JUnit 与逐项存在性核对|
|---|---|---|---|
|AC-001|`test_ac004_download_capture_and_recovery`|PASSED 18.096s|`junit_ac001.xml`：tests=1 / failures=0 / errors=0 / skipped=0；首个/中间/重连后下载均经 `wait_for_captured_download` 校验完成事件与字节内容（`:1495/:1560/:1618`）|
|AC-002|`test_t008_download_reconcile_after_agent_restart`|PASSED 25.099s|`junit_ac002.xml`：tests=1 / failures=0 / errors=0 / skipped=0；完成事件最终文件经转发移除 `assert not downloaded.exists()`（`:1826`），重启后 manual.csv 对账断言全过（`:1840-1849`）|

逐项核对：两份 JUnit 均存在且非空，`testcase` 名分别为 `test_ac004_download_capture_and_recovery` 与 `test_t008_download_reconcile_after_agent_restart`，`failures/errors/skipped` 全为 0。reviewer 独立重跑两条 E2E 亦通过（16.56s / 24.65s）。无临时文件误判残留，无生产改动。

## Review 处置

每个结构化 finding 一行。`已修` 表示本 task 已修复；`遗留` 必须指向 `pNNN` 或 follow-up tid；`撤回` 必须写清理由。critical/important 未解决时不得 PASS。

### Round 1（2026-11-20T01:54:10+08:00）

Round 1 零 finding（clean review）。`review_general.md` verdict PASS，`reviewed_scope: fba0779bffc3182f` 与当前交付一致；`task.py review-status` 判 `review_level=single / general_verdict=PASS / overall=PASS / review_scope=ok / ac_review=ok / round=1 / next_action=finalize`。

AC 复验（`review_general.md`「AC 复验方式」）：AC-001 `TICK-VALID`（re_verified，三个下载位点均关联 completed 事件与最终文件并逐字节校验，独立重跑 `test_ac004` 通过）；AC-002 `TICK-VALID`（re_verified，完成事件最终文件被转发移除、重启后 manual.csv 对账全过，独立重跑 `test_t008` 通过）。无 finding 需处置。

## 收尾报告

### 验收与验证

- task：[`task.md`](task.md)
- 结果：全部满足
- 测试：required 模式 collect-only `15 tests collected`；两条真实 Docker E2E 均通过，JUnit `junit_ac001.xml`（18.096s）与 `junit_ac002.xml`（25.099s）`failures/errors/skipped` 全 0，逐项存在性核对通过。
- 黑盒：真实 Docker/Chrome 下载捕获、转发清理与重启对账两条 E2E 通过（同一候选镜像 `sha256:00969a0d4932…`、引擎缓存 + geoip）；reviewer 独立重跑亦通过。
- review：single 级 `review_general.md` Round 1 零 finding，verdict PASS；`task.py review-status` `overall=PASS / next_action=finalize`。
- AC 判定：见 `task.md` 行内打勾（AC-001/002 均 `- [x]`）

### 结果摘要

- 以完成事件关联最终文件与字节内容替代目录枚举/首文件观察，修复空 `.crdownload` 临时文件误判与转发清理重命名竞态；仅改测试观察逻辑，不改生产下载逻辑、镜像或协议。
- 来源 pending `p148` 已 `closed` / `resolution=transferred` / `fix_ref=t093`，本 task 验证通过后无需改状态。无遗留 finding、无 follow-up tid。

### 长期文档闭环

- specs_index: not_applicable: 本 task 仅修正测试对已定义完成行为的观察，无关联 spec，task.md 上下文区与 blueprint 均无长期文档变更。
- 无正式 spike。
