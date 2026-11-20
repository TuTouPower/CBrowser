---
tid: "t094"
slug: "egress_probe_subsystem_root_refactor"
title: "代理出口测速子系统根因重构：服务端作业编排 + 轻量后端探测 + 单一状态源"
status: "done"
branch: "t094_egress_probe_subsystem_root_refactor"
worktree: ""
review_level: "full"
review_limit: "5"
verify_limit: "5"
diff_anchor: "b1f979ba5e7ea2ee3a1bfb22d9d5d52703834434"
spec_source_sha: "b1f979ba5e7ea2ee3a1bfb22d9d5d52703834434"
depends_on: ""
conflicts_with: ""
note: "用户 2026-11-20 授权：p149+p150 按开发铁律聚合立项；纳入 useBatchActions 环境批量与沙箱依赖测试改写；只创建 backlog，不实施。; ；2026-11-20 按 spec_review.md 15 条意见逐项修订 task.md，引用核对至 main@b52808a 实际路径/行号，仍未实施"
---

# Task 进展

front matter 只经 `task.py` 修改；reviewer 只写对应 `review_*.md`。

## 实施笔记

执行期记录关键步骤、决策、验证、阻塞和用户批准的新轮次上限。

创建期不预测实施步骤。只记有追溯价值的内容；无事项时写“无”。

- 2026-11-20：按 `spec_review.md` 的 15 条意见逐项修订 `task.md`，所有引用核对至 main@b52808a 的实际路径、符号与行号；AC 补入独立验收量尺与两条 E2E 链，仍未开始实施。
- 2026-11-20（实施）：run-begin attempt 1（owner opencode-t094-hy4，execution b14ea457）。先核实并改写 4 项 UNVERIFIED 契约（移除 UNVERIFIED 标记）后方得 start。后端新建 `proxy_probe_jobs` + `proxy_probe_job_members` 与迁移 f1a2b3c4d5e6，service 编排作业（冻结集合/权威读模型/fence/终态收敛/重启恢复）、轻量进程内探测、SSE typed 事件；退役整条容器沙箱；前端作业化；环境三动作复用作业框架（POST /profile-batch-jobs）；API 依赖补 socksio/geoip2、compose 补 host-gateway。全量门禁多轮全绿。
- 评审 4 轮（code）/ 3 轮（test）：Round1 code 8 条 important/minor + test 4 条 important；Round2 code 1 条 important(f009 SSE key 分叉)、test 2 条 important；Round3 全部转 minor；Round4 code 0 条。所有 important/critical 已修，minor f007/f008 遗留 p151。review-status：overall=PASS / review_scope=ok / ac_review=ok。

## Review 处置

每个结构化 finding 一行。`已修` 表示本 task 已修复；`遗留` 必须指向 `pNNN` 或 follow-up tid；`撤回` 必须写清理由。critical/important 未解决时不得 PASS。

### Round 1 (2026-11-20T16:17:29+08:00)

|finding_id|severity|status|rationale|fix_ref|
|---|---|---|---|---|
|t094_code_f001|important|已修|探测 HTTP 改 `asyncio.to_thread`，不占事件循环|src/backend/cbrowser/services/egress_probe.py|
|t094_code_f002|important|已修|loopback 代理映射 host.docker.internal + compose extra_hosts|src/backend/cbrowser/services/egress_probe.py, compose.yaml|
|t094_code_f003|important|已修|环境批量服务端作业 + 进度/汇总条|src/frontend/src/features/profiles/EnvironmentListPage.tsx|
|t094_code_f004|important|已修|sessionStorage 持久化 job id + SSE 首读快照纳入在途作业|src/frontend/src/features/proxies/ProxyListPage.tsx, src/backend/cbrowser/api/v1/router.py|
|t094_code_f005|important|已修|零项作业创建即 done|src/backend/cbrowser/adapters/database/repository.py|
|t094_code_f006|minor|已修|\_probe_one_member 返回 error_code 并写入成员|src/backend/cbrowser/services/profile_service.py|
|t094_code_f007|minor|已修|删除死预算，timeout 真接入 HTTP；driver 异常兜底收敛|src/backend/cbrowser/services/profile_service.py|
|t094_code_f008|minor|已修|更新沙箱过期注释与 runner_unavailable 错误码|src/backend/cbrowser/domain/proxy_endpoint.py, src/backend/cbrowser/shared/egress.py|
|t094_test_f001|important|已修|刷新注入 running 读模型 + 多标签 + typed 超窗快照 + 收敛测试|tests/unit/test_t094_probe_job_convergence.py 等|
|t094_test_f002|important|已修|loopback 映射/三协议/非阻塞单测|tests/unit/test_t052_supervisor_runner.py|
|t094_test_f003|important|已修|环境批量提交 + 进度条用例|EnvironmentListPage.test.tsx|
|t094_test_f004|important|已修|跨页 55>50 + 精确 id + 不漂移用例|tests/integration/test_t052_proxy_api.py|

### Round 2 (2026-11-20T17:10:21+08:00)

|finding_id|severity|status|rationale|fix_ref|
|---|---|---|---|---|
|t094_code_f009|important|已修|env batch 与 probe 共用 probeJobKeys.detail，SSE 单一 handler 驱动两者|src/frontend/src/features/profiles/useProfilesQuery.ts|
|t094_test_f005|important|已修|刷新进度 UI 断言、多标签共享 key、超窗 typed 快照、收敛/围栏/重启四条|test_t094_probe_job_convergence.py, ProxyListPage.test.tsx|
|t094_test_f006|important|已修|混不匹配项排除、并发上限、追加观测不漂移|tests/integration/test_t052_proxy_api.py|

### Round 3 (2026-11-20T17:30:00+08:00)

|finding_id|severity|status|rationale|fix_ref|
|---|---|---|---|---|
|t094_code_f010|minor|已修|导入块缩进统一为 2 空格|src/frontend/src/features/profiles/EnvironmentListPage.tsx|
|t094_test_f007|minor|遗留|精确 id 集合与 country/city 维度专项断言属增量测试优化，不影响 AC-006 行为正确性，已由 scheme 过滤器 + 冻结集合主路径覆盖|p151|
|t094_test_f008|minor|遗留|router 装配经 SSE 集成测试主路径覆盖，超窗 typed 快照机制已单测；专项装配断言属增量优化|p151|

## 收尾报告

### 验收与验证

- task：[`task.md`](task.md)
- 结果：全部满足（[deploy] AC-008/009 按处置注记视为流程完成，真实验证由 p151 跟踪）
- 测试：全量门禁 `scripts/run_gates.sh` EXIT=0——契约 388、单元 2410、集成 216、前端 730（88 文件）+ 生产构建全绿；依赖锁/requirements 与锁文件一致，迁移 head 为 f1a2b3c4d5e6。
- 黑盒：AC-008/009 真实 Docker/Chrome 拓扑因 `REQUIRED_E2E_ENV` 不可变镜像 ID 未配置本机不可执行，按项目既定 USER_WAIVED 口径与 `[deploy]` 处置注记登记 p151，未以 mock/skip/历史结果冒充。
- review：full 双轴 code/test 均 PASS（code Round4、test Round3），`review_scope=ok`、`ac_review=ok`、`next_action=finalize`；9 条 AC 全部 TICK-VALID（AC-001~007 re_verified，AC-008/009 处置型）。
- AC 判定：见 `task.md` 行内打勾

### 结果摘要

- 后端：代理测速从「客户端串行 + 同步 /probe + 容器沙箱」重构为服务端持久作业（POST/GET probe-jobs，202 + job_id、冻结目标集、逐项 observation、权威读模型、SSE 进度、重启恢复与终态收敛）+ API 进程内轻量探测（显式 proxy + trust_env=False、白名单回显、本地 GeoIP、loopback→host.docker.internal 映射、无直连回退、to_thread 不占事件循环）。环境三动作改为服务端作业（POST /profile-batch-jobs）并与测速共用读模型与 SSE 进度。
- 前端：删除 probingAll/probingId 与客户端串行；作业提交即反馈、SSE 实时进度、成功/部分失败/全失败汇总、刷新/多标签恢复、批量期间行按钮禁用；OpenAPI 与生成类型重生成。
- 沙箱彻底退役：删除 Supervisor 控制路由/helper/专用 bridge/策略/docker helper 族/runtime_agent helper/probe_egress_plan；保留 Browser/Stream 的 proxy_enforced 双栈 OUTPUT DROP（ADR 038）。
- 依赖与部署：API 组补 socksio/geoip2 并生成 requirements；compose api 补 host.docker.internal 映射。
- 文档/契约：blueprint/specs/guides/ADR 文案归位；spec front matter 登记 t094；退役范围与 ADR 边界写明。
- 遗留：p151 跟踪 AC-008/009 真实 Docker/Chrome E2E 与 test f007/f008 的增量测试优化（均 minor，不影响行为）。

### 长期文档闭环

在 active spec 的 front matter `tasks` 清单中登记当前 tid（`task.py specs list --json`）；无长期 spec 变更时写 `- specs_index: not_applicable: 具体原因`。正式 spike 须有 report、现存 finding、采纳结论、后续 tid 或无需后续理由；finish 会检查这些引用。
