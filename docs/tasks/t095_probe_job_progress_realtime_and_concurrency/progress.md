---
tid: "t095"
slug: "probe_job_progress_realtime_and_concurrency"
title: "代理批量测速进度实时性与并发重构"
status: "done"
branch: "t095_probe_job_progress_realtime_and_concurrency"
worktree: ""
review_level: "full"
review_limit: "5"
verify_limit: "5"
diff_anchor: "94ec7cdff9ca62309367ce984d20db4595189852"
spec_source_sha: "94ec7cdff9ca62309367ce984d20db4595189852"
depends_on: ""
conflicts_with: ""
note: "用户 2026-11-20 生产反馈（p152）：进度只算成功数导致失败场景长期 0/N、行状态不实时刷新、88 代理串行耗时数分钟。按开发铁律从领域模型重做：进度与结果正交、受配额并发、状态变更即事件、观测表退回单次结果职责。"
---

# Task 进展

front matter 只经 `task.py` 修改；reviewer 只写对应 `review_*.md`。

## 实施笔记

执行期记录关键步骤、决策、验证、阻塞和用户批准的新轮次上限。

创建期不预测实施步骤。只记有追溯价值的内容；无事项时写“无”。

- 2026-11-20：来源 p152，生产截图反馈与铁律分析已确认；AC 覆盖进度语义、并发、实时刷新、观测表职责与 deploy 验收，尚未实施。
- 2026-11-20（实施）：TDD 先红后绿。先建 `tests/unit/test_t095_probe_job_progress.py` 六例，全红（`processed` 字段与 `probe_concurrency` 构造参数不存在、驱动仍串行）；再实现领域读模型只读 `processed = completed + failed`、`ProfileService._drive_members` 共享 `asyncio.Semaphore` + `asyncio.Lock` 并发驱动、环境批量复用同一驱动，六例转绿。
- 2026-11-20（状态管道）：选择「一次 `probe_job_progress` 推送同时驱动进度读模型与代理列表刷新」，不引入第二事件。`useProfileEventsSync` 的进度处理器在写作业缓存后调用 `invalidateProxyLists`；观测已先于事件落库，失效即取回逐行最新结果，不靠轮询。i18n 进度占位符由 `{completed}` 改为 `{processed}`（代理测速与环境批量同口径）。
- 2026-11-20（旧测试处置）：删除 `tests/unit/test_t094_probe_job_convergence.py::test_concurrent_subset_probes_do_not_interleave`。理由：其断言 `runner.peak <= 1` 编码「驱动串行」旧语义，与 AC-003 受配额并发直接冲突；替换为 `test_t095_probe_job_progress.py::test_parallel_jobs_keep_member_results_isolated`，在新并发语义下验证多作业结果隔离。
- 2026-11-20（门禁）：worktree 软链主仓 `.scratch/gate_venv`、`gate_uv_cache`、`selkies_wheels`、`jpeginfo` 与 `src/frontend/node_modules`（均 gitignore，不改主仓）。`scripts/run_gates.sh` EXIT=0：contract 388 passed / 1 skipped，unit 2417 passed / 13 skipped，integration 216 passed / 18 skipped，前端 731 passed，design lint / check / build 全绿。OpenAPI 与生成类型已重导；`git diff --check` 与 `md_kx` 格式检查通过。
- 2026-11-20（[deploy]）：AC-006 需真实 88 代理 Docker/Chrome 拓扑，本机无镜像 ID 无法执行；按既定口径由主会话立 pending 跟踪，本 task 不写 `docs/pending`。

## Review 处置

每个结构化 finding 一行。`已修` 表示本 task 已修复；`遗留` 必须指向 `pNNN` 或 follow-up tid；`撤回` 必须写清理由。critical/important 未解决时不得 PASS。

### Round 1 (2026-11-20T20:31:00+08:00)

|finding_id|severity|status|rationale|fix_ref|
|---|---|---|---|---|
|t095_code_f001|minor|遗留|注释中「串行」表述与并发语义不符，属纯注释准确性；不影响行为与 AC，不值得重审|p151|
|t095_test_f001|minor|遗留|环境批量「失败计入进度」缺直接断言，共用 `_drive_members` 与 i18n 已由 agent 实现层验证，属增量测试优化|p151|

code/test reviewer 均 PASS；9 条 AC 全 TICK-VALID（AC-001~005 re_verified，AC-006 trust_prior 处置型，p151 跟踪）。

## 收尾报告

### 验收与验证

- task：[`task.md`](task.md)
- 结果：AC-001~006 全部满足（AC-006 按 [deploy] 处置注记视为流程完成，真实验证由 p151 跟踪）。
- 测试：`scripts/run_gates.sh` EXIT=0（contract 388 passed / 1 skipped；unit 2417 passed / 13 skipped；integration 216 passed / 18 skipped；前端 731 passed；design lint / check / build 全绿）。TDD：`test_t095_probe_job_progress.py` 七例先红后绿，覆盖全失败进度推进、读模型权威、观测历史 TTL、并发上限与耗时、超限排队、慢成员隔离、多作业隔离；前端新增失败进度 + 事件驱动列表刷新用例。
- 黑盒：`blackbox_verify` 需真实 Docker/Chrome 镜像 ID，本机缺失；AC-006 不以 mock/skip 冒充，按既定口径由主会话立 pending 跟踪。
- review：full 双轴 code/test 均 PASS（各 1 minor 遗留 p151），`review_scope=ok`、`ac_review=ok`、`next_action=finalize`；6 条 AC 全 TICK-VALID（AC-001~005 re_verified，AC-006 trust_prior 处置型）。
- AC 判定：见 `task.md` 行内打勾

### 结果摘要

- 进度与结果正交：读模型派生 `processed = completed + failed`，运行中进度按已处理数推进，终态分别汇总成功/失败；代理测速、单条测速与环境批量共用，失败计入进度。
- 受配额并发：共享 `asyncio.Semaphore`（`CBROWSER_PROBE_JOB_CONCURRENCY`，默认 8）+ 计数锁 + `write_transaction` 串行写；超限排队、单成员超时独立、多作业不串线。
- 统一状态管道：一次 `probe_job_progress` 写进度缓存并失效代理列表；观测只存单次结果、历史与 TTL 不变，进度不从观测反推。
- 遗留：AC-006 [deploy] 生产规模验收由 p151 第 4 项跟踪；p153（测速全失败真因 GeoIP 路径缺失）为独立缺陷，不在本 task 范围。

### 长期文档闭环

在 active spec 的 front matter `tasks` 清单中登记当前 tid（`task.py specs list --json`）；无长期 spec 变更时写 `- specs_index: not_applicable: 具体原因`。正式 spike 须有 report、现存 finding、采纳结论、后续 tid 或无需后续理由；finish 会检查这些引用。

- specs_index：`docs/specs/proxy_management.md` 与 `docs/specs/profile_management.md` 的 `tasks` 已登记 `t095`。
