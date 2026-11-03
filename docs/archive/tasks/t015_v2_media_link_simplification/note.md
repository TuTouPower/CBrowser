---
tid: "t015"
slug: "v2_media_link_simplification"
title: "媒体链路收敛：单机直连验证与 TURN/ICE 代次机制去留"
status: "done"
branch: "t015_v2_media_link_simplification"
worktree: ""
review_level: "full"
review_limit: "5"
verify_limit: "5"
diff_anchor: "9ee4a1146be8e42bc552f1150beb8063582ab466"
depends_on: ""
conflicts_with: ""
note: "来源 docs/reviews/review_20261102_201727/adoption_decision.md"
---

# Task 过程总账

front matter 只经 `task.py` 修改；reviewer 只写对应 `review_*.md`。

## 实施笔记

执行期记录关键步骤、决策、验证、阻塞和用户批准的新轮次上限。

创建期不预测实施步骤。只记有追溯价值的内容；无事项时写“无”。

### 2026-11-02 实施

- spike 先行：新建 s011，在真实 Chrome + OrbStack、无 coturn、Gateway 不下发 RTC 配置的拓扑中验证多页面、复制标签、刷新、关闭首 tab、可见性暂停/恢复、Viewer 断线 resume、音视频、键鼠与中文输入；结论 d026，报告 `docs/spikes/s011_direct_media_validation/report.md`。
- 删除 TURN/ICE 机制：移除 `cbrowser/rtc_config/`、`gateway/rotation.py`、`stream_agent/ice_transport.py`、`config/coturn/`；Gateway 不再下发 rtc_config、不再处理 ice_restart/visibility_update；Stream Agent 配置不再要求 SELKIES_TURN_*，注册载荷删除 turn_host/turn_port 与重复 FPS 字段。
- 协议契约：改用按 action 判别的 AgentRegisterEnvelope / AgentHeartbeatEnvelope 与只含 supervisor_quota 的 GatewayControlEnvelope；Gateway/Agent 双向校验，导出 schema 更新并保留漂移守卫；FPS 只由 Stream Agent 配置层决定。
- Gateway 加固：Viewer 的 Origin/会话/Agent/观测态拒绝全部前移到 `ws.prepare()` 与 viewer 注册之前；Agent 注册校验在注册表变更前完成；Viewer 授权失败按来源+Profile 限流（429）；两侧 WebSocket 设置 6MiB+64KiB 上限；密钥统一经 `read_secret_file`；配额 payload 校验失败返回 400；心跳超时日志引用配置值；心跳与捕获仲裁循环逐次隔离异常并由监督任务退避重启。
- Supervisor：移除 coturn 必需项、媒体网络 coturn 连接与 TURN/STUN 环境变量、relay-only 网络模式；Gateway 仍动态加入媒体网络以提供内部 URL。该改动是 AC-002 删除 coturn 的必要机械收敛，不涉及 Supervisor 其他加固（归 t016）。
- 前端：`features/browser-session/adapter.ts` 删除全部测试全局与 DataChannel/WebSocket 报文记录，只保留信令改写、Web Locks 身份、分辨率锁定、activity 丢弃与有文档的 `__getWebRTCStats` 契约；Web Locks 不可用新增专门诊断；运行时检查改走 ApiClient，401 交鉴权层、不可达显示带原因 runtime_not_ready；补 Vitest 覆盖。
- 文档：ADR 013、architecture/gateway/stream_runtime/security/frontend/supervisor、webrtc spec、testing、guides、计划 §8.4/§19.3 标记、隔离分析 guide Superseded、上一轮 adoption D1 已决策。
- 测试：unit 473 passed；integration 79 passed；frontend Vitest 126 passed；legacy src/backend/tests 384 passed；contract 169 passed；tsc -b 与 npm run build（含 verify_frontend_dist）通过；当前源码重建 Stream 镜像后 `tests/e2e/test_stream_runtime_e2e.py` 直连矩阵通过；frontend session/app/media 探针用例在真实拓扑下通过（app 用例 teardown 有一次容器删除瞬时 APIError，随后容器已清理，测试体通过）。testing.md 的旧命令缺 v2 路径，已改为 `PYTHONPATH=src:src/backend`。

## Review 处置

每个结构化 finding 一行。`已修` 表示本 task 已修复；`遗留` 必须指向 `pNNN` 或 follow-up tid；`撤回` 必须写清理由。critical/important 未解决时不得 PASS。

### Round 1 (2026-11-03T00:01:36+08:00)

|finding_id|severity|status|rationale|fix_ref|
|---|---|---|---|---|
|t015_code_f001|important|已修|Agent 注册身份改由查询参数提供，token 与 API 绑定在 ws.prepare 前校验；升级后核对载荷身份|src/backend/cbrowser/gateway/server.py|
|t015_code_f002|important|已修|配额/断连控制面改用 Pydantic 请求模型，非对象或非法字段返回 400|src/backend/cbrowser/gateway/server.py|
|t015_code_f003|important|已修|Web Locks 不可用时置 ref，后续 WS_CLOSE 不再覆盖专门诊断；补真实消息序列测试|useBrowserSession.ts; BrowserSessionView.test.tsx|
|t015_code_f004|minor|已修|限流键空间超过 1024 时淘汰最旧键，保证有界|gateway/registry.py|
|t015_code_f005|minor|已修|stream_agent 包导出改为新 envelope，删除未使用 dump_agent_envelope|stream_agent/__init__.py; protocol.py|
|t015_code_f006|minor|已修|gateway.md 改用 AgentRegisterEnvelope，architecture.md 交叉引用改 5.4|docs/blueprint/gateway.md; architecture.md|
|t015_code_f007|minor|已修|删除失效 runtimeStatusUrl、any 兜底与无引用 i18n key|useBrowserSession.ts; types.ts; i18n.tsx|
|t015_code_f008|minor|已修|Gateway 控制 token 与 AgentCredentials 统一经 read_secret_file|gateway/server.py; supervisor/agent_credentials.py|
|t015_test_f001|important|已修|adapter 构建守卫改用生产 marker，删除旧测试全局断言|tests/e2e/test_frontend_adapter_build.py|
|t015_test_f002|important|已修|Gateway auth E2E 删除 turn key 读取|tests/e2e/test_gateway_ac001_auth_e2e.py|
|t015_test_f003|important|已修|前端 E2E 统一注入 Playwright 探针（DataChannel/WS/PC），不再依赖生产全局|tests/fixtures/frontend_probe/adapter_probe.py 等|
|t015_test_f004|minor|已修|清理残留 TURN 环境变量与 s008 探针行|test_stream_display_config.py; test_stream_agent_lifecycle.py; testing.md|
|t015_test_f005|minor|已修|补 outer supervised loop 告警与退避重启测试|test_stream_runtime.py; test_stream_agent_lifecycle.py|
|t015_test_f006|minor|已修|401 改真实 ApiClient onUnauthorized 证据；补卸载监听器释放断言|BrowserSessionView.test.tsx|
|t015_test_f007|minor|遗留|Supervisor 网络隔离与 Stream 配额 E2E 覆盖待恢复|p016|

### Round 2 (2026-11-03T01:08:00+08:00)

|finding_id|severity|status|rationale|fix_ref|
|---|---|---|---|---|
|t015_code_f009|minor|已修|gateway.md 的 Agent 实例不符改为升级前 403，quota/disconnect 错误码补 400|docs/blueprint/gateway.md|
|t015_code_f010|minor|已修|Stream Agent secret 与 Supervisor API token 改用 read_secret_file|stream_agent/config.py; supervisor/runner.py|
|t015_test_f008|minor|已修|前端探针改注入到 adapter 之前，只记录实际到达原生 send 的报文|tests/fixtures/frontend_probe/adapter_probe.py|

### Round 3 (2026-11-03T01:35:00+08:00)

|finding_id|severity|status|rationale|fix_ref|
|---|---|---|---|---|
|t015_code_f011|critical|已修|Stream 镜像补 COPY secret_files.py，重建镜像后直连 E2E 通过|config/docker/stream_runtime/Dockerfile|
|t015_code_f012|minor|已修|规整 stream_agent 包导出元组缩进并去重|stream_agent/__init__.py|
|t015_code_f013|minor|已修|Agent secret 文件最低长度统一为 32 字节，测试夹具改用 token_urlsafe(32)|stream_agent/config.py; tests/unit/test_stream_selkies_tokens.py|
|t015_code_f014|minor|已修|frontend.md 改为描述实际 script 注入顺序|docs/blueprint/frontend.md|

### Round 4 (2026-11-03T01:45:00+08:00)

|finding_id|severity|status|rationale|fix_ref|
|---|---|---|---|---|
|t015_code_f015|minor|已修|Stream 验证指南构建清单补 secret_files.py|docs/guides/stream_runtime_validation.md|
|t015_code_f016|minor|已修|task spec 测试策略改为实际 script 注入|docs/archive/tasks/t015_v2_media_link_simplification/task.md|
|t015_test_f009|minor|已修|testing.md 删除两个已删除测试文件路径|docs/blueprint/testing.md|
|t015_test_f010|minor|已修|前端探针 __pcs 改为追加，保持与其他探针语义一致|tests/fixtures/frontend_probe/adapter_probe.py|
|t015_test_f011|minor|已修|新增 Stream Runtime 打包守卫测试|tests/unit/test_baseline_runtime_regressions.py|

### Round 5/6 (2026-11-03T01:55:00+08:00)

|finding_id|severity|status|rationale|fix_ref|
|---|---|---|---|---|
|t015_code_f017|minor|撤回|生产挂载前 Supervisor 已强制 credentials 文件 0600，controller token 由 Supervisor 生成 ≥42 字符；直接构造 StreamAgentConfig 不是受支持入口，按 JSON 原文走通用 secret 读取器会改变错误语义，收益低于风险。|src/backend/cbrowser/supervisor/docker_adapter.py:753|
|t015_test_f012|minor|遗留|Agent 替换测试的 close 1001、conn_id 差异、下行回复与 Viewer 存活断言待恢复|p016|
|t015_test_f013|minor|遗留|Supervisor 中途失败原子回滚 E2E 待改为仅 Gateway 失败并恢复|p016|

## 收尾报告

### 验收与验证

- task：[`task.md`](task.md)
- 结果：全部满足
- 测试：unit 473 passed；integration 79 passed；frontend Vitest 126 passed；legacy 384 passed；contract 169 passed；tsc -b、npm run build/verify 通过；当前源码重建 Stream 镜像（含 secret_files.py）后直连 E2E 通过；frontend session/app/media 探针用例在真实拓扑通过（app teardown 一次瞬时 APIError，容器已清理）。
- 黑盒：真实 Chrome + OrbStack 无 coturn 直连矩阵（s011 与 tests/e2e/test_stream_runtime_e2e.py）；真实 Gateway 拓扑 integration 通过；Browser Runtime E2E 使用 p014 镜像通过。
- review：full code/test 两路 Round 2 均 PASS；Round 1 的 3+3 blocking 全部修复；剩余 minor 已修或转 p016。
- AC 判定：见 `task.md` 行内打勾

### 结果摘要

- 删除 coturn/TURN/ICE 代次与 Selkies 私有 ABI 补丁，媒体改为同机 127.0.0.1 直连；Gateway/Agent/前端协议与加固按 AC 收口；ADR 013 与相关 blueprint/spec 同步。遗留：p016（Supervisor 网络隔离与 Stream 配额 E2E 覆盖恢复）；d026 为 s011 验证结论。

### 长期文档闭环

本 task 须出现在 specs_index 的关联 task 列；无长期 spec 变更时写 `- specs_index: not_applicable: 具体原因`。正式 spike 须有 report、现存 finding、采纳结论、后续 tid 或无需后续理由；finish 会检查这些引用。
