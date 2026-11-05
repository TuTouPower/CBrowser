# Task spec

## 背景

t023 已交付外部取消、监听释放、SSE 连接代次、动作幂等键及其回归（`action_key_mutation.ts`），p018 仍残留四类有用户影响的缺陷：

- 出站目标：`ApiClient.request` 只检查原始 endpoint 前缀（`client.ts:87-95`），拼接 baseUrl 后的最终地址与 `/\\other.test` 反斜杠变体可绕过并携带 `credentials: "include"` 与 CSRF；`ProfileEventsClient.connect`（`sse.ts:176`）与 `artifacts.downloadUrl`（`client.ts:354`）没有同源判定。生产实例的 baseUrl/url 为空（`client.ts:400`、`sse.ts:319`），当前生产路径不可达，属防御缺口；baseUrl 只服务测试夹具指向随机端口测试服务器。
- 会话动作：“应用并重启”重试时客户端以同一键再次发送 stop，服务端按幂等键重放为 no-op（`repository.py:688-694`，不会再次停实例），但客户端随后等待 `observed_state === "stopped"`（`useProfilesQuery.ts:220-242`），在 desired=running 的新实例上空等到 120 秒超时。缺陷在客户端阶段跟踪，不在服务端重放。
- mutation 归属：`BrowserSessionPage`、`AppLayout` 顶栏（启动/停止/应用及 `display-apply-error` 条）与 `ProfileDetailPage` 共享 mutation 状态；切换 Profile 不重置 error/pending，B 显示 A 的错误或被 A 的 pending 禁用。
- 注销：`SseSyncBridge` 以 `void logout()` 调用（`providers.tsx:16`），logout 失败的 rejection 未处置；现有 fake SSE 不实现 `setOnUnauthorized`，相关测试可经 unmount 清理假通过。

## 契约区

### 范围

- 对 ApiClient 请求、SSE 连接与下载链接生成三个入口统一按最终解析 URL 做同源判定，再决定凭据与 CSRF；生产不需要的 baseUrl/url 可配置项优先删除，测试改为同源夹具（jsdom origin 指向测试服务器或注入 fetch），不得为测试开放生产跨源。
- SSE unauthorized 回调与其他注销调用点明确处置 logout 失败。
- “应用并重启”作为带阶段进度的逻辑动作：阶段状态与 stop 前 runtime_instance_id 跨重试保存，重试从实际阶段续跑。
- BrowserSessionPage、AppLayout、ProfileDetailPage 的动作状态按 Profile 隔离。
- 补生产 AppProviders 默认 QueryClient retry 接线测试。

### 非范围

- 不重复实现 t023 已交付行为；不为 HTTP 函数拆分、SSE 解析去重或泛化抽象单独改结构。
- 不修改已有测试预期以迎合实现；删除 baseUrl 等配置项导致旧测试夹具失效时，只改夹具准备方式，断言保持。真实 Docker/Chrome 会话回归交 t032。

### 验收标准

<!-- 规范（门禁必留，不得删除） -->

只写可观察、可独立验证的行为；每条使用稳定且不复用的 `AC-NNN`。需真实部署或人工环境验证时在编号前加 `[deploy]`。创建时均为未勾选（`- [ ]`）；实施验证通过后由实施 Agent 就地打勾（`- [x]`）；由 Review Agent 独立复核打勾真实性。技术选型不作为行为 AC。review 判 FAIL 且需修改交付内容时，实施 Agent 撤回全部打勾，修复并重验后重新打勾；reviewer 用 `TICK-VALID` / `TICK-VOID` 逐条判定。

<!-- /规范 -->

- [x] AC-001：跨源目标（任何可配置的 base/url、绝对 URL、协议相对、反斜杠及混合变体）在 ApiClient 请求、SSE 连接与下载链接生成三个入口均被拒绝：fetch 未被调用、不产生跨源下载链接；合法同源目标保留现有凭据/CSRF 语义。
- [x] AC-002：经生产 AppProviders 与实现 `setOnUnauthorized` 的 SSE 客户端触发 unauthorized，logout HTTP/网络失败时仍清理认证状态、停止 SSE，且不产生 unhandled rejection；断言来自 unauthorized 回调路径本身，不能依赖 unmount 清理通过；各注销调用点均有明确错误处置。
- [x] AC-003：在 BrowserSessionPage、AppLayout 顶栏与 ProfileDetailPage 中，Profile A 的动作失败或未结束时切换到 B：B 不显示 A 的错误（含 `display-apply-error` 条），按钮不被 A 的 pending 禁用，A 的迟到响应不污染 B；再次打开 A 按当前 runtime 展示。
- [x] AC-004：apply 动作阶段跨重试保存：stop 已生效后重试不再等待已完成阶段；start 已在服务端生效而响应丢失时，重试识别 desired=running 的新实例并收敛到 running，不等待 stopped、不停止或重建新实例；stop 未生效、start 未生效、状态查询短暂失败分别安全续跑或有界报错。
- [x] AC-005：不注入 QueryClient 的生产 AppProviders 默认配置下，queries 与 mutations 对可重试错误重试、对主动取消与不可重试错误不重试；t023 的独立动作幂等键既有回归原样通过。
- [x] AC-006：AC-001–AC-004 的新增回归先在修复前实现上失败再通过，失败用例名与命令记入 note.md 实施笔记（不只留在 gitignored 目录）；取消释放、SSE stop/start/EOF 与现有会话测试继续通过；真实拓扑回归入口和期望交付 t032。

### 可测试性声明

<!-- 规范（门禁必留，不得删除） -->

逐条说明不可自动测试的 AC 及替代验证；全部可测则写“全部 AC 可自动测试”。

<!-- /规范 -->

全部 AC 可自动测试；AC 中“目标探针/用例交付”只验入口、断言、报告和收集，不表示已完成目标实跑。真实环境行为执行只在 t032 判定。

## 上下文区

### 执行环境与参考来源

- 执行环境：云端 Muse。完成实现、触达生产逻辑的 unit/integration、可用的普通 Chromium 测试，以及可收集的真实环境用例和逐项运行说明。不要求访问宿主 Mac、OrbStack、用户局域网或真实 CloakBrowser/Stream 镜像；这些执行义务集中到 t032。本 task 的 AC 只验云端交付，不把模拟结果、collect-only、skip 或历史 trust_prior 当作目标环境 PASS。代码交付完成不表示目标环境已验收；t032 通过前不得据此发布或宣称指纹安全。

- 来源：p018；2026-11-04，main@c6a9322 核实，同日按三方审阅修订。已复现：生产 ApiClient 的跨源 baseUrl 与 `/\\other.test` 变体进入 fetch，`credentials=include` 且携带 CSRF 哨兵；apply 在 start 成功后响应 timeout，重试以同一 stop 键重放 no-op 后等待 stopped 超时。审阅补充：SSE 与 downloadUrl 同类缺口、AppLayout/ProfileDetailPage 同构 mutation、AC-005 幂等键部分已由 t023 交付。探针位于 `.scratch/pending_triage/`，只写临时目录。

### 有意不测

- 宿主 Mac/OrbStack、目标 CloakBrowser、真实媒体/X11/指纹站点：当前 task 执行端为云端 Muse，统一由 t032 执行；不得记为 PASS。

### 测试策略

- Vitest 触达生产 ApiClient、ProfileEventsClient、AppProviders、BrowserSessionPage、AppLayout、ProfileDetailPage 与 useApplyDisplaySettingsMutation；以可控响应丢失与时钟验证重试阶段，不用测试重写实现。
- URL 正负矩阵覆盖三个出站入口；unauthorized 测试使用实现 `setOnUnauthorized` 的客户端并断言回调路径；跨 Profile 迟到响应覆盖三个页面。
- 运行前端 test:types、Vitest 与生产 build，检查生成产物不混入测试代码。

### 未知契约清单

<!-- 规范（门禁必留，不得删除） -->

未核实的外部契约标为 `UNVERIFIED-BLOCKING` 或 `UNVERIFIED-SPIKE`；核实后改写为结论和验证方式。无则写“无”。

<!-- /规范 -->

- 无；测试服务器 origin 与生产同源策略需分离，不能借兼容测试绕过安全边界。

### 风险与回退

- 风险：重试阶段跟踪错误可能永久等待或重复业务动作；异步 Profile 切换可能残留旧状态；删除配置项遗漏测试夹具迁移。
- 回退：回退本 task 执行 commit；不重放已经成功的浏览器启动或停止命令。

### 依赖与约束

- 无未完成硬依赖；与 t026（`useProfilesQuery.ts`、`sse.ts`、`useBrowserSession.ts`）及 t031 前端改动互斥，不同时 active。
- 云端/本地边界遵循“执行环境与参考来源”；真实执行义务只在 t032 判定。

### Finalization 时更新的 blueprint

- docs/blueprint/frontend.md：出站同源边界、注销失败处置、会话动作阶段语义与按 Profile 隔离的动作状态。
- docs/blueprint/testing.md：新增残余回归与 t032 真实执行映射。
