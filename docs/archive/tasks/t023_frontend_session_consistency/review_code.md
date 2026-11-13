# Task review t023（reviewer_focus: 代码）

- task：`t023_frontend_session_consistency`
- spec：`docs/tasks/t023_frontend_session_consistency/task.md`
- diff_anchor：`aca792e864548c0c234baf34ca49ef08b821c418`
- target：`git -C '<home>/workspace/CBrowser_t023' diff aca792e864548c0c234baf34ca49ef08b821c418`
- round：1
- reviewed_at：2026-11-04T04:47:31+08:00

reviewed_scope: 946f623455961d84

## Findings

### t023_code_f001 - search-defaults 重试 mutation 未分配幂等键，自动重试与并发调用可在后端重复执行

- 严重度：important
- 锚点：AC-003（A19）：profiles mutations 应在每次 mutate/mutateAsync 调用边界建立动作 key、单动作网络重试沿用同一键；本动作完全无键
- 位置：`src/frontend/src/features/profiles/useProfilesQuery.ts:152-161`、`src/frontend/src/shared/api/client.ts:243-250`
- 问题：其余 profiles/artifacts mutation 均已迁入 `useActionKeyMutation`，唯独 `useRetrySearchDefaultsMutation` 仍用裸 `useMutation`，其 mutationFn 调 `client.profiles.retrySearchDefaults(id)`；而 client 的 `retrySearchDefaults` 签名根本不接受 idempotencyKey、请求也不带 `Idempotency-Key` 头。后端该端点的契约恰恰依赖此键去重：`src/backend/cbrowser/api/v1/router.py:627-648` 注释明确「调用方的幂等键成为端到端 request_id，同键重复提交由 supervisor/agent 去重而非执行两次」，`src/backend/cbrowser/api/runtime_coordinator.py:306-322` 亦载明无调用方键时每次调用新生成一个。失败场景：生产 `AppProviders` 给 mutations 配置了 `retry: shouldRetryRequest`（`src/frontend/src/app/providers.tsx:57`），该 POST 返回可重试错误时 TanStack 自动重试 mutationFn，每次都是无键的新 HTTP 请求，后端每次新生成 request_id，搜索默认设置初始化被重复执行；用户双击/并发两次 mutateAsync 同理无任何去重。这正是 spec 风险区所指「已完成操作重复执行」。实施笔记所称「profiles/artifacts 全部带 key hooks 迁入」与代码不符。
- 建议：`client.profiles.retrySearchDefaults` 增加可选 idempotencyKey 参数并透传 `Idempotency-Key` 头；`useRetrySearchDefaultsMutation` 改走 `useActionKeyMutation`，mutationFn 用 `{ input, actionKey }`；补一条与 create 相同的「重试复用同键、并发异键」行为测试（现有 `ProfileDetailPage.searchDefaults.test.tsx:98` 只断言以 `"p1"` 调用，未断言键）。

### t023_code_f002 - SSE 事件校验放行缺失生成类型必填字段的事件，仍强转为合法运行状态

- 严重度：important
- 锚点：AC-005（A21）：SSE 消费采用生成事件类型并验证真实事件语义，畸形事件不会被强转为合法运行状态
- 位置：`src/frontend/src/shared/api/sse.ts:55-62`、`src/frontend/src/shared/api/sse.ts:76`
- 问题：生成类型 `ProfileRuntimeStatusEvent` 中 `failure_count: number`、`restart_blocked: boolean`、`updated_at: string` 均为必填（`src/frontend/src/shared/api/generated/cbrowser_v1.d.ts` 该 schema 定义，字段无 `?`），但 `parseProfileRuntimeEvent` 对三者只做「存在时类型正确」检查（`e.failure_count !== undefined && ...` 等），缺失时直接放行，最后以 `return raw as ProfileRuntimeEvent` 强转。失败场景：投递一条仅含 `profile_id/desired_state/observed_state` 的残缺事件，校验返回非 null，被 `dispatchEvent` 当作完整合法事件投递（`sse.ts:214-215`），消费者 `useProfileEventsSync` 再以 `?? old` 把缺失字段从旧状态拼回，合成一个线上从未出现过的运行状态——正是 A21 要消除的「用 Partial 掩盖不一致」。现有测试未覆盖此形：`sse_generation.test.ts` 的畸形用例 bad-2 只缺 `profile_id`，VALID_EVENT 则三字段俱全。
- 建议：按生成类型把 `failure_count`、`restart_blocked`、`updated_at` 改为必填校验（缺失或类型不符返回 null 走 error 通道）；`search_defaults` 子字段维持现状（其 `error_kind/request_id` 在生成类型中确为可选）。补一条「缺任一必填字段即拒绝」的参数化测试。

### t023_code_f003 - ApiClient 在响应体读取前即移除外部取消监听并清除超时，体阶段既不能取消也不能超时

- 严重度：important
- 锚点：AC-002（A18）：外部取消与内部超时可区分，且「所有请求结束后」才移除取消监听
- 位置：`src/frontend/src/shared/api/client.ts:134-154`、`src/frontend/src/shared/api/client.ts:166`、`src/frontend/src/shared/api/client.ts:200-205`
- 问题：`try/finally` 只包住 `await fetch(...)`，finally 里 `clearTimeout(timer)` 并 `externalSignal.removeEventListener("abort", onExternalAbort)`；但请求并未结束——错误体 `await response.json()`（166 行）与成功体 `await response.json()/text()`（200-205 行）都在 finally 执行之后才运行。失败场景：服务器已发响应头、响应体慢速滴流或停滞时，调用方 abort 外部 signal，监听已被移除，内部 controller 永不 abort；同时超时 timer 也已清除，于是 `client.request` 既不报 `cancelled` 也不报 `timeout`，只能悬挂到服务器自行关闭响应体为止（React Query 侧无兜底超时）。本 diff 新增的 removeEventListener 落在这个位置，使原先「监听至少存续到 abort 发生」的取消路径在体阶段失效，与 AC-002 的字面要求不符；现有测试 `client.test.ts` 的「removes the external abort listener once the request settles」用一次性完整 Response 断言，无法区分移除发生在体读取前还是之后。
- 建议：把响应状态处理与响应体读取整体纳入同一 try/finally（或把 timer 清除与监听移除移到 `request` 真正 return/throw 之前的最外层 finally）；补一条「响应头已到、体未完时外部 abort 立即以 cancelled 拒绝」的受控流测试。

### t023_code_f004 - 新增 parseProfileRuntimeEvent 圈复杂度约 29，校验分支全部堆在单函数

- 严重度：minor
- 锚点：行为缺陷无；圈复杂度标准（CC ≥ 15 且本 task 新建该函数）
- 位置：`src/frontend/src/shared/api/sse.ts:37-77`
- 问题：按 prompt 的手算口径（基数 1，每个 if +1、短路 `&&`/`||` 各 +1）该函数 CC 约 29：含 3 处多条件合取/析取守卫与 `search_defaults` 子对象的 6 项嵌套校验。当前均为扁平 early-return，尚无可观测缺陷，但后续生成类型再增字段时继续在此堆分支，漏检风险上升（f002 的必填漏检已在此结构下发生）。
- 建议：将 `search_defaults` 子对象校验抽为独立 `parseSearchDefaults` 辅助函数，顶层只保留主字段守卫；不要求本轮以外的重构。

## 结论

- 本轮新发现：4 条（important 3、minor 1）
- 未进表的提示：文件过大——`src/frontend/src/i18n.tsx` 464 行（实现源码 minor 阈值 400），本 task 净增约 9 行，既存字典文件、按标准仅提示不进表；复杂度——`ProfileEventsClient.connect`（`sse.ts`）本就分支较多，本轮代次检查再增数处守卫，扁平可读，仅提示。其余已扫视角：安全（redirect 开放重定向防护保留并扩展、ProfileFilesPage 失败文案只含文件名不含内容、无凭证进日志）、契约/Breaking（`ProfileRuntimeStatusEvent` 导出与 generated 一致、旧 i18n 键删除与消费者同步）、性能（上传顺序执行系 spec 指定语义）、架构（BrowserSessionMount 入 feature 且 props 复用 feature 类型、shared 无反向导入 feature，经 grep 核实）均已扫过，除上表外未命中。
- AC 复验方式：
  - AC-001：re_verified——读 `redirect.ts` 规范化逻辑与 `redirect.test.ts` 22 例变体表，读 `BrowserSessionPage.tsx` 五态分支（非 404 错误带重试、404 才 profileNotFound、runtime 错误单独重试）与 `useBrowserSession.ts` 的 tRef 改造；相关测试在全量 Vitest 运行中通过。
  - AC-002：re_verified——读 `sse.ts` 代次实现并逐场景推演立即 stop/start、重复 start、401、登出后旧流报错；读 `client.ts` cancelled/timeout 区分逻辑；运行 `sse_generation.test.ts`、`client.test.ts` 通过；但体阶段监听移除时机不符（见 f003）。
  - AC-003：re_verified——读 `action_key_mutation.ts` 调用边界铸键实现与 profiles/artifacts 全部 hooks 的迁移、apply 派生键（`:stop`/`:start`）；运行 actionkeys/retry 测试通过；同时独立发现 retrySearchDefaults 一处未迁移（见 f001），故本 AC 实际未完整达成。
  - AC-004：re_verified——读 `SettingsPage.tsx`（仅 controlApiStatusTitle/Hint 加 health.check 结果）、`ProfileFilesPage.tsx` 上传循环的 succeeded=index、remaining=length-index-1 计数与首败即停；i18n 新文案双语齐备；页面部分失败测试在全量运行中通过。
  - AC-005：re_verified——读 i18n en 派生 `TranslationKey` 与 zh `satisfies Record<TranslationKey, string>`、键集相等测试，独立运行 `npx tsc -p tsconfig.test.json` 退出码 0；读 SSE 校验比对 generated 类型，发现必填字段漏检（见 f002），故本 AC 实际未完整达成。
  - AC-006：re_verified——独立运行全量前端 Vitest（27 文件 156 tests 全通过）与 `test:types`（tsc -p tsconfig.test.json，零错误）；逐项查证 credentials=include 的 fetch-spy 断言、shouldRetryRequest 真实 retry 复用键断言、media_controls 的具体 `window.location.origin` 断言、各页面经 ApiClientContext 注入独立 stub（grep 确认生产页面无单例直引、无 vi.mock hooks 模块残留）。
  - AC-007：trust_prior——代码层已独立复核：grep 确认 `__cbrowserHostLoaded/__statusBtnClicked` 只存在于 `tests/fixtures/frontend_probe/host_entry.tsx`、生产 src 无测试 globals；BrowserSessionMount 已入 feature 且从 `types.ts` 导入 props、shared 版已删；`readClipboardPermission` 与 `onSessionError` 已删且无残留引用；tailwind accent 已删、primary 为唯一品牌色字面量。但「生产 bundle 不含 globals」的 dist grep 证据依赖实施笔记自述（reviewer 只读，未重跑 build 以免改动 worktree）。
  - coverage = 6 / 7
- 总体判断：存在 3 条未解决 important（f001 幂等键遗漏、f002 SSE 必填漏检、f003 取消监听移除时机），AC-003 与 AC-005 被打勾但实际未完整达成，FAIL。
- 系统性 follow-up：无（三条 important 均为本 task 范围内可直接修复项，不另立 follow-up）。

verdict: FAIL

## Round 2 (2026-11-04T04:58:10+08:00)

- round：2
- reviewed_at：2026-11-04T04:58:10+08:00
- target：`git -C '<home>/workspace/CBrowser_t023' diff aca792e864548c0c234baf34ca49ef08b821c418`（全量回归扫描）＋ Round 1 四条 finding 的修复代码与新增测试逐项复核

reviewed_scope: 1b7466a84b7e073f

## Findings

本轮无新发现（0 条新 finding，不续编新编号）。前轮 f004 的残余复杂度问题系前轮延续，见下方复核，不另编号。

## 结论

- 前轮 finding 复核：
  - t023_code_f001（important，AC-003）：**已消除**。以最终代码为准：`src/frontend/src/shared/api/client.ts:251-266` 的 `retrySearchDefaults` 已增加可选 `idempotencyKey` 参数并透传 `Idempotency-Key` 头；`src/frontend/src/features/profiles/useProfilesQuery.ts:152-161` 的 `useRetrySearchDefaultsMutation` 已改走 `useActionKeyMutation`（调用边界铸键、重试复用同键、无共享 ref 清除，`src/frontend/src/shared/api/action_key_mutation.ts:37-66`）。新增测试非自述：`useProfilesQuery.actionkeys.test.tsx:123-161` 断言单动作重试两试同键、第二动作新键且非空；`ProfileDetailPage.searchDefaults.test.tsx:98-101` 页面级断言以 `("p1", expect.any(String))` 调用。本 reviewer 独立运行上述两文件通过。
  - t023_code_f002（important，AC-005）：**已消除**。`src/frontend/src/shared/api/sse.ts:71-73` 对 `failure_count` / `restart_blocked` / `updated_at` 已改为无条件必填类型校验（`typeof !== "number" / "boolean" / "string"` 即返回 null），与生成类型 `cbrowser_v1.d.ts` 中 `ProfileRuntimeStatusEvent` 的必填定义一致；残缺事件不再被 `return raw as ProfileRuntimeEvent` 强转为合法状态。新增参数化用例 `sse_generation.test.ts:269-284` 逐一删除六个必填字段（含本条三字段）断言拒绝，本 reviewer 独立运行通过。
  - t023_code_f003（important，AC-002）：**已消除**。`src/frontend/src/shared/api/client.ts:134-215` 已将状态处理与响应体读取（错误体 166 行、成功体 200-205 行）整体纳入同一 try，`clearTimeout` 与 `externalSignal.removeEventListener` 移至最外层 finally（213-215 行），监听与超时存续到体读完；错误体读取被 abort 时于 180-182 行按 `controller.signal.aborted` 上抛交外层映射（timedOut → timeout、externalSignal.aborted → cancelled），不再吞为「非 JSON」。新增受控流用例 `client.test.ts:391-435`（响应头已到、体永不完时外部 abort 以 cancelled / retryable=false 拒绝并断言监听移除），本 reviewer 独立运行通过；超时在体阶段同理由 timer 仍武装而成立（代码复核）。
  - t023_code_f004（minor，复杂度）：**修不彻底（残余 minor，不阻断）**。建议的抽取已落实：`search_defaults` 子校验已抽为独立 `isValidSearchDefaults`（`sse.ts:30-42`，手算 CC ≈ 11），顶层只保留主字段守卫。但按 Round 1 与 prompt 的同一手算口径（基数 1 ＋ 每个 if ＋ 每个短路 `&&`/`||`），`parseProfileRuntimeEvent`（`sse.ts:52-77`）现为 10 个 if ＋ 5 个短路运算 ≈ CC 16，较 Round 1 的 ≈29 大幅下降，但仍略高于 minor 阈值 15。当前均为扁平 early-return、无可观测缺陷，不升格、不阻断 PASS；实施侧可在处置表中将其记为遗留 minor 或再拆一层守卫后于下一轮复核。
- 本轮新发现：0 条。对全部 diff 做回归扫描：修复仅触及 `client.ts` / `sse.ts` / `useProfilesQuery.ts` 三处生产文件与对应测试，未见行为分叉或新缺陷——client 重构后 401 处理、错误体 detail/message 提取、204/空体与 text/json 分流语义与 Round 1 基线一致，ApiError 在外层 catch 优先原样上抛（`client.ts:190-192`）；diff 新增行中无 `.skip` / `.only` / `@ts-ignore` / 恒真断言（grep 核查，`as unknown as` 均为既有测试 stub 模式与 Round 1 已审的 action_key 包装）；Round 1 其余结论（安全、契约/Breaking、性能、架构）维持不变，复核 grep 确认生产 src 无测试宿主 globals、无 `readClipboardPermission` / `onSessionError` 残留、shared 无反向导入 feature、tailwind 无 accent。
- 未进表的提示：文件过大——`src/frontend/src/i18n.tsx` 464 行（同 Round 1，既存字典文件）；`src/frontend/src/shared/api/client.ts` 恰达 400 行（实现源码 minor 阈值，本轮因 f003 重构净增，按标准仅提示不进表）。复杂度——`ApiClient.request` 与 `ProfileEventsClient.connect` 分支较多但均为扁平顺序处理、本轮未新增嵌套，仅提示（同 Round 1 口径）；f004 残余见上。
- AC 复验方式：
  - AC-001：re_verified——本轮独立全量运行含 `redirect.test.ts` 22 例与 BrowserSessionPage 页面测试全过；本 AC 生产代码未被本轮修复触及，与 Round 1 已读代码一致。
  - AC-002：re_verified——读最终 `client.ts` / `sse.ts` 代次与取消实现，独立运行 `client.test.ts`、`sse_generation.test.ts`、`sse.test.ts`、`sse_hardening.test.ts`（含新增体流式取消用例）全过。
  - AC-003：re_verified——读 `action_key_mutation.ts`、全部 profiles/artifacts hooks 与 `client.ts` 键透传，独立运行 actionkeys 与 searchDefaults 页面测试（断言见 f001 复核）。
  - AC-004：re_verified——本 AC 生产代码未被本轮修复触及；独立全量运行含 SettingsPage 与 ProfileFilesPage 部分失败测试全过，与 Round 1 代码复核结论一致。
  - AC-005：re_verified——读最终 `parseProfileRuntimeEvent` 并比对生成类型必填字段，独立运行缺字段参数化用例与 `npx tsc -p tsconfig.test.json`（退出码 0）。
  - AC-006：re_verified——独立运行全量前端 Vitest：27 文件 162 tests 全通过（Round 1 为 156，本轮 +6 与新增用例数吻合）；`test:types` 零错误。
  - AC-007：trust_prior——代码层已复核（grep 确认生产 src 无测试 globals、已删符号无残留、shared 无反向导入、accent 已删）；「生产 bundle 不含 globals」的 dist grep 证据仍依赖实施侧构建自述，本 reviewer 只读未重跑 build 以免改动 worktree。
  - coverage = 6 / 7
  - 建议合并前人工抽查 trust_prior 项
- 总体判断：Round 1 三条 important（f001 / f002 / f003）均已真实修复并有新增行为测试经本 reviewer 独立运行验证，本轮全量回归无新 critical / important；仅余 f004 残余 minor（复杂度 ≈16），按判定式仅有 minor 时可 PASS。
- 系统性 follow-up：无。

verdict: PASS

## Round 3 (2026-11-04T05:01:52+08:00)

- round：3（定向复审）
- reviewed_at：2026-11-04T05:01:52+08:00
- target：`git -C '<home>/workspace/CBrowser_t023' diff aca792e864548c0c234baf34ca49ef08b821c418`，范围严格限定于 Round 2 唯一残余 t023_code_f004 的修复复核（`hasValidCoreFields` 抽取）、校验语义比对与自 Round 2 指纹以来的 diff 漂移检查

reviewed_scope: 03ee67642d1ffbd4

## Findings

本轮无新发现（0 条新 finding，不续编新编号）。

## 结论

- 前轮 finding 复核：
  - t023_code_f001 / f002 / f003（important）：Round 2 已确认消除，本轮定向范围外；其生产代码（`client.ts`、`useProfilesQuery.ts` 及 sse.ts 代次/必填校验部分）自 Round 2 后无变化（证据见下方 diff 漂移检查），Round 2 结论维持。
  - t023_code_f004（minor，复杂度）：**残余已消除**。
    - 复杂度复算（与 Round 1 / Round 2 同一手算口径：基数 1 ＋ 每个 `if` ＋ 每个短路 `&&` / `||`）：当前顶层 `parseProfileRuntimeEvent`（`src/frontend/src/shared/api/sse.ts:73-83`）仅含 5 个 `if`——第 76 行空值守卫为 1 个 `if` ＋ 2 个 `||`，第 78 / 79 / 80 / 81 行各 1 个单条件守卫（`hasValidCoreFields` / `runtime_instance_id` / `last_coordinator_error` / `search_defaults` 子校验）——分支合计 7，**CC ≈ 8**，较 Round 2 的 ≈16 减半，不仅低于 minor 阈值 15，也低于结论提示阈值 10，残余消除。
    - 抽取未把复杂度转嫁成新的超标函数：`hasValidCoreFields`（`sse.ts:45-62`）为 6 个 `if` ＋ 3 个 `||`，CC ≈ 10，仅达结论提示线、远低于 minor 阈值 15；`isValidSearchDefaults`（`sse.ts:31-43`）与 Round 2 一致 CC ≈ 11，未被本轮触及。三函数均为扁平 early-return，无可观测缺陷。
    - 校验语义未变（逐字段与 Round 2 已确认口径及生成类型比对）：必填六字段全部原样移入 `hasValidCoreFields`——`profile_id` 为非空 string（`sse.ts:46`）、`desired_state` ∈ {stopped, running}（49 行）、`observed_state` ∈ {stopped, starting, running, stopping, error}（52-56 行）、`failure_count` 为 number（58 行）、`restart_blocked` 为 boolean（59 行）、`updated_at` 为 string（60 行），与生成类型 `ProfileRuntimeStatusEvent`（`src/frontend/src/shared/api/generated/cbrowser_v1.d.ts:774-804`）的必填定义逐项一致；可选三字段仍留在顶层——`runtime_instance_id` / `last_coordinator_error` 经 `isNullableString`（undefined / null / string 才放行，79-80 行）、`search_defaults` 经未改动的 `isValidSearchDefaults`（81 行，其子字段 state 枚举必填、runtime_instance_id / updated_at 必填、error_kind / request_id 可空，与生成类型 `SearchDefaultsStatusData`（`cbrowser_v1.d.ts:876-890`）一致）。各守卫均为无副作用纯谓词、合取关系，抽取与求值顺序不影响拒绝/放行结果；全部通过后才 `return raw as ProfileRuntimeEvent`（82 行），与 Round 2 语义相同。
    - 实跑验证：本 reviewer 独立运行 `NODE_OPTIONS=--no-experimental-webstorage npx vitest run src/shared/api/sse_generation.test.ts src/shared/api/sse.test.ts src/shared/api/sse_hardening.test.ts`，3 文件 12 tests 全通过；其中 `sse_generation.test.ts:269-284` 的「逐一删除六个必填字段即拒绝」参数化用例在抽取后仍绿，直接覆盖 `hasValidCoreFields` 的必填语义。
  - diff 漂移检查（自 Round 2 指纹 `1b7466a84b7e073f` 以来）：确认其余部分无变化。证据：当前指纹经官方脚本同源函数重算为 `03ee67642d1ffbd4`，与本轮派审 prompt 注入值一致；指纹算法排除 note.md 等流程文件，故指纹变化只能来自 scoped 交付内容——而全部 diff 文件中仅 `src/frontend/src/shared/api/sse.ts`（mtime 2026-11-04T04:58:48+08:00）与 `docs/tasks/t023_frontend_session_consistency/note.md`（mtime 04:59:22+08:00）在 Round 2 reviewed_at（04:58:10+08:00）之后被修改，其余 diff 文件 mtime 均 ≤ 04:53+08:00、早于 Round 2 复审。note.md 的变化即「Review 处置」f004 条更新文字，与派审说明一致。sse.ts 内部除 `hasValidCoreFields` 抽取外，其余段落（代次隔离、flushEvent、重连）与 Round 2 已审内容逐段比对一致。
- 本轮新发现：0 条。
- 未进表的提示：复杂度——`hasValidCoreFields` CC ≈ 10 达结论提示线（见上），仅提示不进表；文件过大提示同 Round 2（`i18n.tsx` 464 行、`client.ts` 400 行），本轮未触及。安全 / 契约 / 性能 / 架构等视角在本轮定向范围内随语义比对一并扫过，除 f004 残余外未命中。
- AC 复验方式（本轮为定向复审，仅 AC-005 与本残余直接相关）：
  - AC-005：re_verified——逐字段比对最终 `parseProfileRuntimeEvent` / `hasValidCoreFields` / `isValidSearchDefaults` 与生成类型必填/可选定义，独立运行上述 SSE 三件套测试（含缺字段参数化用例）全过。
  - AC-001 / AC-002 / AC-003 / AC-004 / AC-006 / AC-007：trust_prior——依赖 Round 2 的独立复验结论；本轮以 mtime 与指纹证据确认其代码自 Round 2 后未变化，故 Round 2 的 re_verified 证据继续有效，但本轮未重跑其测试。
  - coverage = 1 / 7
  - 建议合并前人工抽查 trust_prior 项
- 总体判断：f004 残余（顶层 CC ≈16 略超 15）已经本次抽取真实消除（顶层 CC ≈ 8），抽取未改变校验语义、无新超标函数、自 Round 2 以来 diff 其余部分无变化；当前无未解决 critical / important / minor。
- 系统性 follow-up：无。

verdict: PASS
