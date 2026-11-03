# Task spec

## 背景

t023 已修外部取消、监听释放、SSE 连接代次及动作幂等键，但 p018 残余行为仍存在。继续清理整个 HTTP/SSE 结构收益低；只修有用户影响的请求边界与会话动作。

## 契约区

### 范围

- 围绕最终解析 URL 做同源校验；覆盖 baseUrl、绝对/相对路径、协议相对及反斜杠输入，再决定凭据与 CSRF。不得为了支持测试服务器开放生产跨源请求。
- 消化 SSE unauthorized 回调中 logout rejection，限定 Profile 启动 mutation 状态归属。
- 把“应用并重启”作为有阶段进度的逻辑动作；start 已生效而响应丢失时观察真实状态或安全重放当前阶段，不重新执行已完成 stop。
- 补真实 AppProviders 默认 QueryClient retry 接线测试；保留已完成取消/SSE 代次/独立动作幂等键回归。

### 非范围

- 不重复实现 t023 已交付行为；不为 HTTP 函数拆分、SSE 解析去重或泛化抽象单独改结构。
- 不修改已有测试预期以迎合实现；真实 Docker/Chrome 会话回归交 t032。

### 验收标准

<!-- 规范（门禁必留，不得删除） -->

只写可观察、可独立验证的行为；每条使用稳定且不复用的 `AC-NNN`。需真实部署或人工环境验证时在编号前加 `[deploy]`。创建时均为未勾选（`- [ ]`）；实施验证通过后由实施 Agent 就地打勾（`- [x]`）；由 Review Agent 独立复核打勾真实性。技术选型不作为行为 AC。

<!-- /规范 -->

- [ ] AC-001：通过生产 ApiClient 发出请求前统一解析最终目标；跨源 baseUrl、绝对 URL、协议相对、反斜杠及混合变体均被拒绝，fetch 未被调用；合法同源目标保留现有凭据/CSRF 语义。
- [ ] AC-002：真实 AppProviders 的 SSE unauthorized 路径遭遇 logout HTTP/网络失败时仍清理认证状态、停止 SSE，且不产生 unhandled rejection；各注销调用点均有明确错误处置。
- [ ] AC-003：Profile A 启动失败或请求未结束时切换 B，B 不显示 A 错误、不被 A pending 状态禁用，迟到响应不污染 B；再次打开 A 按当前 runtime 展示。
- [ ] AC-004：start 已在服务端生效但客户端超时后，同一 apply 动作重试不重跑已完成 stop，不停止或重建新实例；stop 未生效、start 未生效、状态查询短暂失败分别能安全收敛或有界报错。
- [ ] AC-005：不同 apply 调用与并发调用保持独立幂等键，同一动作同阶段重试保持原键；生产 AppProviders 默认 retry 对可重试错误重试、对主动取消不重试。
- [ ] AC-006：新增回归先在旧实现暴露缺陷再通过修复；取消释放、SSE stop/start/EOF 与现有会话测试继续通过；真实拓扑回归入口和期望交付 t032。

### 可测试性声明

<!-- 规范（门禁必留，不得删除） -->

逐条说明不可自动测试的 AC 及替代验证；全部可测则写“全部 AC 可自动测试”。

<!-- /规范 -->

全部 AC 可自动测试；AC 中“目标探针/用例交付”只验入口、断言、报告和收集，不表示已完成目标实跑。真实环境行为执行只在 t032 判定。

## 上下文区

### 执行环境与参考来源

- 执行环境：云端 Muse。完成实现、触达生产逻辑的 unit/integration、可用的普通 Chromium 测试，以及可收集的真实环境用例和逐项运行说明。不要求访问宿主 Mac、OrbStack、用户局域网或真实 CloakBrowser/Stream 镜像；这些执行义务集中到 t032。本 task 的 AC 只验云端交付，不把模拟结果、collect-only、skip 或历史 trust_prior 当作目标环境 PASS。代码交付完成不表示目标环境已验收；t032 通过前不得据此发布或宣称指纹安全。

- ego-lite 参考仓库：https://github.com/citrolabs/ego-lite ；固定研究基线：https://github.com/citrolabs/ego-lite/tree/12407167f84a58af24044f072868051952131491 。云端可直接读取公开源码，无需本机目录。其 AGENTS.md 明确只开源 harness/Skill，浏览器本体与 globalThis.ego 原生绑定闭源；只能借鉴公开实现与故障案例，不依赖原生绑定，不照搬合成事件兜底，不将上游效果当成本项目证据。

- 来源：p018；2026-11-04，main@c6a9322 核实。已复现：生产 ApiClient 的跨源 baseUrl 与 /\\other.test 变体进入 fetch，credentials=include 且携带 CSRF 哨兵；生产 apply mutation 的 start 成功后响应 timeout，重试再次 stop 并在 runtime=running 上等待 stopped 超时。探针位于 .scratch/pending_triage/，只写临时目录。会话页 mutation 无按 profile 重置，SseSyncBridge 使用 void logout() 且 AuthProvider finally 后继续拒绝，属源码机制核对，实施时先补失败测试。已修部分见 client.ts finally、sse.ts generation 和 t023 归档记录。

### 有意不测

- 宿主 Mac/OrbStack、目标 CloakBrowser、真实媒体/X11/指纹站点：当前 task 执行端为云端 Muse，统一由 t032 执行；不得记为 PASS。

### 测试策略

- Vitest 触达生产 ApiClient、BrowserSessionPage、AppProviders 与 useApplyDisplaySettingsMutation；使用可控响应丢失与时钟验证重试阶段，不用测试重写实现。
- 新增 URL 正负矩阵、跨 Profile 迟到响应和 unauthorized logout rejection；运行前端 test:types、Vitest 与生产 build，检查生成产物不混入测试代码。

### 未知契约清单

<!-- 规范（门禁必留，不得删除） -->

未核实的外部契约标为 `UNVERIFIED-BLOCKING` 或 `UNVERIFIED-SPIKE`；核实后改写为结论和验证方式。无则写“无”。

<!-- /规范 -->

- 无；测试服务器 origin 与生产同源策略需分离，不能借兼容测试绕过安全边界。

### 风险与回退

- 风险：重试阶段跟踪错误可能永久等待或重复业务动作；异步 Profile 切换可能残留旧状态。
- 回退：回退本 task 执行 commit；不重放已经成功的浏览器启动或停止命令。

### 依赖与约束

- 无未完成硬依赖。
- 云端/本地边界遵循“执行环境与参考来源”；真实执行义务只在 t032 判定。

### Finalization 时更新的 blueprint

- docs/blueprint/frontend.md：请求安全、注销与会话动作阶段语义。
- docs/blueprint/testing.md：新增残余回归与 t032 真实执行映射。
