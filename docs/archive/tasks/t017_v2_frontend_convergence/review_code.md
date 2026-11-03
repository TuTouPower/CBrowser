# Task review t017（reviewer_focus: 代码）

- task：`t017_v2_frontend_convergence`
- spec：`docs/tasks/t017_v2_frontend_convergence/task.md`
- diff_anchor：`5252f75ab2bd726f65f98dfa0a644c9a64d53fb2`
- target：`git -C '/Users/karson/kar/code/CBrowser_t017' diff 5252f75ab2bd726f65f98dfa0a644c9a64d53fb2`
- round：1
- reviewed_at：2026-11-03T05:21:17+08:00

## Findings

### t017_code_f001 - AC-001 未删除仅 v1 使用的 i18n 键

- 严重度：important
- 锚点：AC-001（「仅 v1 使用的 i18n 键」全部移除）
- 位置：`src/frontend/src/i18n.tsx:53`、`:407` 等（`en` 与 `zh` 两套字典）
- 问题：以锚点提交为基线比对，已删除的 v1 文件引用过、且当前 `src/` 内零引用的键仍有 **125 个**，`en`/`zh` 两套字典都完整保留。代表项：`quitManager`/`managerStopped*`（`i18n.tsx:53,56`）、`updateAvailable`/`download`/`dismissUpdate`（`:92-99`）、`tierPro`/`tierFree`/`tierKeyless`（`:97-99`）、`licenseKey`/`releaseChannel`（`:108` 起）、`profileNamePlaceholder`/`fingerprintSeed`/`gpuFamily`/`humanPreset*`（`:162` 起，原 `ProfileForm.tsx`）、`openedInNativeWindow`/`nativeWindowHint`（原 `NativeWindowStatus.tsx`）、`fileSingular`/`filePlural`（原 `ProfileFiles.tsx`）。AC-001 已打勾，但本 diff 的 `i18n.tsx` 只有新增、没有任何键删除，删除范围未完成。
- 建议：用脚本列出「锚点版本中被删除文件引用、当前零引用」的键，从 `en`/`zh` 一并删除；同时保留 `SessionDiagnostics.tsx` 的键映射（`sessionStage*`/`audioStatus*` 等仍在使用，勿误删）。

### t017_code_f002 - 写操作幂等键未按 AC 实现

- 严重度：important
- 锚点：AC-003（「写操作由用户动作生成幂等键并在重试中复用」）
- 位置：`src/frontend/src/shared/api/client.ts:189-231`（`create`/`update`/`setDesiredState`/`stop` 无 `Idempotency-Key`）、`:240-262`（`duplicate`/`reset` 每次调用现生成 key）
- 问题：OpenAPI 对 `POST /profiles`、`PATCH/PUT /profiles/{id}`、`desired-state`、`stop`、`duplicate`、`reset` 都声明了 `Idempotency-Key` 参数，但客户端仅 `duplicate`/`reset` 发送，且 key 在 client 方法内每次调用生成新 UUID（`client.ts:242-245,257-260`）。请求超时或网络失败后，用户再次触发同一动作（重试）会得到新 key，服务端无法去重：重复创建 Profile、重复复制或重复停止。AC 打勾但「由用户动作生成并在重试中复用」未落地，也没有任何 mutation 层保存 key。
- 建议：在 mutation 提交（用户动作）时生成一次 key，随变量传入 client 并让同一动作的自动/手动重试复用；为 `create`/`update`/`setDesiredState`/`stop` 补齐 header。

### t017_code_f003 - `retryable` 未参与重试决策

- 严重度：important
- 锚点：AC-003（「错误对象携带错误码、可重试标志与字段详情，并据此决定重试」）
- 位置：`src/frontend/src/shared/api/client.ts:19,165`（只暴露 `retryable`）；`src/frontend/src/app/providers.tsx:47`（`retry: 1` 硬编码）；`src/frontend/src/features/profiles/useProfilesQuery.ts:56-158`（mutation 无 retry 策略）
- 问题：`rg "retryable" src/frontend/src` 除 `client.ts` 与测试外零命中：查询对任何错误都无条件重试 1 次，mutation 默认 0 次，503/超时（可重试）与 4xx 校验失败（不可重试）没有区别策略。错误对象携带了 `retryable`，但没有任何消费者据此决定重试，AC 的后半句未实现。
- 建议：在 QueryClient `defaultOptions.queries.retry` 与 mutation `retry` 中读取 `ApiError.retryable`（例如仅对 `retryable === true` 重试并限制次数）；若 mutation 暂不自动重试，至少把「用户点击重试」路径接上该标志。

### t017_code_f004 - SSE 401 停流但不触发登出（生产未接线）

- 严重度：important
- 锚点：AC-003（「SSE 遇 401 停止重连并触发登出」）
- 位置：`src/frontend/src/shared/api/sse.ts:99-103,221`；`src/frontend/src/app/providers.tsx:38`
- 问题：`ProfileEventsClient` 新增的 `onUnauthorized` 只有构造参数，`defaultSseClient = new ProfileEventsClient()`（`sse.ts:221`）没有传回调，类也没有 setter；生产代码没有任何地方注入。会话过期时 SSE 分支只 `stop()`，`AuthProvider` 仍保持 `isAuthenticated=true`，用户停留在已失效界面，直到下一次普通 API 请求返回 401。`docs/blueprint/frontend.md` 已宣称「SSE 遇 401 停止重连并触发登出」，与实现不一致。
- 建议：增加 `setOnUnauthorized`（或让 `AppProviders` 构造带回调的实例），把 SSE 401 接到与 `ApiClient` 相同的登出/清理逻辑；再用注入 spy 的用例验证回调只触发一次。

### t017_code_f005 - 同源限制可被 protocol-relative URL 绕过，CSRF 头仍外发

- 严重度：important
- 锚点：AC-003（「只向同源发送凭据与 CSRF 头」）
- 位置：`src/frontend/src/shared/api/client.ts:74-82`
- 问题：origin 校验只覆盖 `endpoint.startsWith("http")`。`request("//attacker.example/x", { method: "POST" })` 或 `"///attacker.example/x"` 不满足该前缀，构造出的 `url` 以 `//` 开头，浏览器会解析为跨源 `https://attacker.example/x`，而后续仍设置 `credentials: "include"` 与 `X-CSRF-Token`（token 值取自本域 `cbrowser_csrf`），即安全令牌被发送到攻击者域。当前所有生产调用点都传固定字面量路径，尚无实际利用链，但新增的安全控制存在可绕过缺口，且新增测试只覆盖了 `https://` 绝对 URL。次要旁路：`new ApiClient({ baseUrl: "https://other.example" })` 的所有相对请求都是跨源且带 CSRF（现有测试也依赖这种用法）。
- 建议：对最终 `url` 用 `new URL(url, window.location.origin)` 校验 origin（覆盖 protocol-relative 与跨源 baseUrl），或显式拒绝 `//`/`///` 前缀并把 baseUrl 限定为同源；补 protocol-relative 用例并断言 `fetch` 未被调用。

### t017_code_f006 - Profile 详情 dirty 状态跨 profileId 复用，切换到克隆页显示并可提交旧编辑

- 严重度：important
- 锚点：行为缺陷（AC-002 的未保存编辑保护实现引入）
- 位置：`src/frontend/src/features/profiles/ProfileDetailPage.tsx:37-59,73`
- 问题：`dirtyFields` 是 `useRef`，只按字段名标记，未按 `profileId` 清空。用户在 profile A 编辑 name/proxy/tags 后点「复制」，`navigate('/profiles/<clone>')` 会复用同一组件实例（`app/router.tsx:38` 同一路由元素，且无 `key`），effect（`:39-55`）因 dirty 跳过回填，克隆详情页显示的是 A 的未保存草稿；用户此时点保存会把 A 的草稿写进克隆。浏览器前进/后退在两个详情 URL 间切换同理。
- 建议：在 `profileId` 变化时清空 dirty 标记（记录 lastProfileId 或在 `useEffect([profileId])` 内 clear），并在 `handleDuplicate` navigate 前 clear。

### t017_code_f007 - 外部取消被误报为超时；外部 signal 监听器不释放

- 严重度：minor
- 锚点：行为缺陷（错误语义/资源）
- 位置：`src/frontend/src/shared/api/client.ts:102-125`
- 问题：`catch` 只判断 `controller.signal.aborted`，外部 `AbortSignal` 触发时也会抛 `errorCode: "timeout"`、`retryable: true`，取消被误报为可重试超时；`externalSignal.addEventListener(..., { once: true })` 在请求正常结束后不移除，长时间复用同一 signal 发多次请求会累积监听器（闭包持有 controller 与请求对象）。
- 建议：用独立 `timedOut` 标志区分超时与外部取消，分别抛对应错误；请求结束后 `removeEventListener`（或改用 `AbortSignal.any` 并清理）。

### t017_code_f008 - SSE `stop()` 后立即 `start()` 存在竞争，可产生重复连接

- 严重度：minor
- 锚点：并发时序
- 位置：`src/frontend/src/shared/api/sse.ts:53-72,176-183`；`src/frontend/src/features/profiles/useProfilesQuery.ts:262-265`
- 问题：cleanup 新增 `stop()` 后，若紧接着 `start()`（React StrictMode 开发态双执行或快速 remount），旧 `connect()` 的 abort rejection 可能在 `start()` 已把 `isClosed` 置回 `false` 后才处理：`catch` 不返回、`finally` 再 `scheduleReconnect()`，而新连接已建立。结果是两条 SSE 流并存、事件重复投递，且 `abortController` 被新连接覆盖后旧流无法被后续 `stop()` 关闭。
- 建议：为每次 `connect()` 使用连接代次（generation token）或独立的 attempt-closed 标志，`catch`/`finally` 只对当前代次生效；`start()` 前确保旧连接已终止。

### t017_code_f009 - SSE 尾帧解析复制主流解析逻辑，`connect()` 复杂度继续升高

- 严重度：minor
- 锚点：DRY / 圈复杂度（`connect()` CC ≥ 30，本 task 新增分支）
- 位置：`src/frontend/src/shared/api/sse.ts:129-175`
- 问题：尾帧处理（`:157-175`）把 `id:`/`data:` 行解析、`currentId` 更新与 JSON dispatch 再写一遍，与主循环（`:129-155`）近似重复；后续处理 `retry:`、BOM、多行 data 边界时需同步两处，容易分叉。`connect()` 本轮新增约 7 个分支后已明显超过 15。
- 建议：抽出单一 `consumeLine(line, state)` 与 `flushPendingEvent(state)`，主循环与尾帧共用；或把 SSE 行解析拆成独立纯函数。

### t017_code_f010 - `ApiClient.request` 圈复杂度超阈值且本轮继续增加

- 严重度：minor
- 锚点：圈复杂度（`request()` CC 约 20+，本 task 新增分支）
- 位置：`src/frontend/src/shared/api/client.ts:69-180`
- 问题：`request()` 同时承担 URL 构造/同源校验、CSRF/credentials、超时与外部取消合并、响应解析与错误映射，本轮又加入 origin、timeout、`errorCode/retryable/detail` 分支；分支集中导致漏处理（如 f005/f007）风险升高。
- 建议：抽出 `resolveUrl`/`assertSameOrigin`、`buildAbortSignal`、`mapErrorResponse` 等小函数，`request()` 只保留流程编排。

## 结论

- 前轮 finding 复核：Round 1，无前轮 finding。
- 本轮新发现：10 条（6 important、4 minor）。
- 未进表的提示：
  - 文件过大：`src/frontend/src/i18n.tsx` 775 行（本 task 净增约 14 行）、`src/frontend/src/features/profiles/ProfileDetailPage.tsx` 432 行（净增约 12 行），均达到 400 行建议阈值；本 task 仍在增大，建议拆分（i18n 可按 en/zh 拆文件，同时清理 f001 的死键）。未直接导致可观测缺陷，故不进 finding 表。
  - 复杂度：除 f009/f010 外，`ProfileDetailPage.tsx` 的 `handleSubmit`/`handleDuplicate` 仍在可接受范围（CC < 15）。
  - 交付卫生：`src/frontend/src/i18n.test.tsx` 在 `git status` 中仍是未跟踪文件（`??`），未执行 `git add -N`，不在本轮 diff 内。本轮已直接读取该文件并纳入复核（vitest 81 passed 包含它），但按派审规则交付前必须进入 diff，否则 commit 用 `git add -u` 会漏交付。
  - 范围外观察：无。diff 未改后端/OpenAPI/browser-session；`docs/blueprint/frontend.md`、`docs/specs_index.md` 的更新与本 task 说明一致，但 blueprint 的「SSE 401 触发登出」目前与实现不符（并入 f004）。
  - 独立复跑证据：`npx tsc -b`（exit 0）、`npm test`（14 files / 81 tests passed）、`npm run build` + `verify_frontend_dist.py`（通过）、`npm ls react-router react-router-dom`（仅 7.18.5 单实例）、`git ls-files '*tsbuildinfo'`（空）。
- 总体判断：AC-001/002/003 存在未实现的打勾项，另有同源校验绕过与详情页状态复用两项可观测缺陷；至少 6 条 blocking 未解决，本轮 FAIL。
- 系统性 follow-up：无（现有 t018 只覆盖测试体系与仓库卫生，不承接本 task 的客户端 AC 缺口）。

### AC 复验方式

- AC-001：`re_verified`。实跑 `npx tsc -b`、vitest（81 passed）、生产构建与 `verify_frontend_dist.py` 均通过；`rg` 确认旧路径与 `@dnd-kit`/`@novnc`/`react-router` 直接依赖零引用；但仅 v1 使用的 125 个 i18n 键仍在（f001），AC 不成立。
- AC-002：`re_verified`。重跑 build + CSS 校验确认 `.bg-primary`/`.text-primary-foreground` 存在于产物；逐处读码核实会话启动错误条、dirty 回填、轮询瞬时失败与超时错误文案、SSE 尾帧 flush；发现 dirty 跨 profileId 泄漏（f006）。其中 UI/轮询分支无自动化用例，属测试层覆盖缺口。
- AC-003：`re_verified`。核对 OpenAPI 的 `Idempotency-Key` 参数与客户端实际发送、`rg "retryable"` 的消费者、`defaultSseClient` 的生产接线、protocol-relative URL 的浏览器解析行为；f002-f005 均成立。
- AC-004：`re_verified`。`npm ls` 确认 `react-router` 单实例、`git ls-files` 确认 tsbuildinfo 未入库、`rg` 确认无 `from "react-router"` 直接导入；i18n 存储迁移与 `documentElement.lang` 由本轮 vitest 用例实际执行通过（`setLocale` 切换分支仅初始化场景覆盖）。
- coverage = 4 / 4

reviewed_scope: 856ee0423a032102

verdict: FAIL

## Round 2 (2026-11-03T05:33:36+08:00)

### 前轮 finding 复核

- f001（important）**修不彻底**：已从 `i18n.tsx` 删除 125 个 v1 键，但仍有 12 个「锚点版本仅被已删除 v1 文件引用、当前 `src/` 零引用」的键保留在两套字典：`retry`（`:20`）、`add`（`:27`）、`test`（`:29`）、`timezone`（`:97`）、`locale`（`:98`）、`width`（`:99`）、`height`（`:100`）、`extensions`（`:102`）、`notes`（`:103`）、`connecting`（`:105`）、`fullscreen`（`:107`）、`send`（`:108`），zh 侧对应 `:221,228,230,290-293,295-296,298,300-301`。`git grep` 显示这些键在锚点仅由 `App.tsx`、`ProfileForm.tsx`、`ProfileViewer.tsx` 引用，当前全仓无引用。AC-001 仍不成立。另 `audioStatus:143` 也是死键，但它在锚点就不是 v1-only，未计入本条。
- f002（important）**核心缺陷已消除，残留见 f011**：`client.ts:103-120` 现在为所有 POST/PUT/PATCH/DELETE 自动补 `Idempotency-Key`，按 `method:url:body` 指纹复用，成功响应后删除；原「每次调用新 UUID、重试无法去重」已不存在。残留的「键按请求内容而非用户动作作用域」问题另立 f011。
- f003（important）**已消除**：`providers.tsx:52-63` 的 query/mutation `retry` 按 `ApiError.retryable` 决策；`client.ts:188` 把后端 `retryable` 与 503 映射进 `ApiError`。
- f004（important）**已消除**：`providers.tsx:9-21` 在 `SseSyncBridge` 注入 `setOnUnauthorized(() => void logout())`，`sse.ts:103-106` 遇 401 调回调并 `stop()`；`sse_hardening.test.ts:19-40` 验证只连一次。生产路径已接线。
- f005（important）**主绕过已消除，残留见 f012**：`client.ts:78-83` 用 `new URL(endpoint, window.location.origin)` 校验绝对与 protocol-relative 端点，`//attacker.example`/`///attacker.example` 均被拦截，不再外发 CSRF/凭据。跨源 `baseUrl` 旁路仍在，见 f012。
- f006（important）**已消除**：`ProfileDetailPage.tsx:39-41` 在 `profileId` 变化时清空 dirty ref，`:43-59` 只回填未修改字段，提交成功后 `:127` 再清空；复制后跳到克隆页不会再显示/提交源 profile 的草稿。
- f007（minor）**仍存在**：`client.ts:124-140` 仍用 `controller.signal.aborted` 统一判定超时，外部 signal 取消会被报成 `errorCode: "timeout"`、`retryable: true`；`addEventListener` 仍未在请求结束后移除。
- f008（minor）**仍存在**：`sse.ts:57-76,180-187` 的 `start()`/`stop()` 没有连接代次，快速 stop→start 时旧 `connect()` 的 catch/finally 仍可能给新连接再安排一条重连。
- f009（minor）**仍存在**：`sse.ts:129-179` 尾帧解析与主循环重复；`connect()` 分支数继续偏高。
- f010（minor）**仍存在**：`client.ts:70-203` 的 `request()` 继续同时承担 URL/同源、CSRF、幂等键、超时、响应解析与错误映射，分支数高。

### 本轮新发现

#### t017_code_f011 - 幂等键按请求内容作用域，响应丢失后会把后续同类新动作当作重放

- 严重度：important
- 锚点：AC-003（「写操作由用户动作生成幂等键并在重试中复用」）
- 位置：`src/frontend/src/shared/api/client.ts:103-120`
- 问题：键的指纹是 `method:url:body`，只按请求内容区分，不按用户动作区分；且只有 `response.ok` 才删除键。若一次写请求已在服务端提交、但响应丢失/超时（例如 reset 的 body 恒为 `{"confirm":true}`），键会永久留在 `idempotencyKeys`。之后用户再次执行同一动作（新意图，不是同一次重试）仍命中旧键；服务端按 operation id 走 replay，`repository.py:271-279`（update）与 `profile_service.py:561-566`（reset）直接返回当前 Profile 而不重新应用操作。可复现路径：编辑保存 B 超时但服务端已提交 → 改为 C 保存成功 → 再改回 B 保存；第三次请求复用 B 的旧键，服务端返回当前 C，mutation 报成功而 B 的编辑被静默丢弃。reset/stop/desired-state 这类固定 body 的动作同样会长期无法再次执行，直到页面刷新或映射超过 100 个键。
- 建议：在 mutation/用户动作层生成一次 key（随 variables 传入 client，React Query 重试复用），动作结束或重试链结束后清除；不要用 `method:url:body` 作为 key 的复用边界。

#### t017_code_f012 - 跨源 baseUrl 仍会携带 credentials 与 CSRF 头

- 严重度：minor
- 锚点：AC-003（「只向同源发送凭据与 CSRF 头」）
- 位置：`src/frontend/src/shared/api/client.ts:75-83`、`:89-96`
- 问题：同源校验只检查 `endpoint`，不检查 `baseUrl` 拼出的最终 URL。`new ApiClient({ baseUrl: "https://other.example" })` 后调用 `list()`/`create()` 等相对端点，会向 `https://other.example` 发送 `credentials: "include"` 与从本域 `cbrowser_csrf` 读取的 `X-CSRF-Token`。当前生产只使用默认空 `baseUrl`，无实际利用链；但安全控制没有在最终 URL 上闭合。
- 建议：构造后校验 `baseUrl` 与 `window.location.origin` 同源，或对最终 `url` 统一做 `new URL(url, window.location.origin)` 的 origin 断言。

### AC 复验方式

- AC-001：`re_verified`。重跑 `npx tsc -b`（exit 0）、`npm test`（15 files / 84 tests passed）、`npm run build` 与 `scripts/verify_frontend_dist.py`（通过）；`rg` 确认旧路径、`@dnd-kit`、`@novnc`、`react-router` 直依赖零引用；但 12 个 v1-only i18n 键仍在（f001），AC 未完全满足。
- AC-002：`re_verified`。构建 CSS 中确认 `.bg-primary`/`.text-primary-foreground`；读码确认 `BrowserSessionPage` 启动错误条、`ProfileDetailPage` dirty 回填、`waitForRuntimeState` 连续 3 次失败容忍与超时文案区分；`sse_hardening.test.ts:42-63` 验证尾帧 flush。
- AC-003：`re_verified`。核对 OpenAPI 六个写接口均声明 `Idempotency-Key`，客户端现在全部自动发送并在重试复用；`providers.tsx` 消费 `retryable`；`sse_hardening.test.ts:19-40` 验证 401 停流；用 Node `URL` 实测 protocol-relative 同源校验。f011/f012 为残留缺口。
- AC-004：`re_verified`。`npm ls react-router react-router-dom` 显示仅 `react-router-dom@7.18.5` 及其单实例 `react-router@7.18.5`；`git ls-files '*tsbuildinfo'` 为空；`i18n.test.tsx` 覆盖旧键迁移与 `document.documentElement.lang`。
- coverage = 4 / 4

### 结论

- 本轮新发现：2 条（f011 important、f012 minor）。
- 未进表的提示：
  - 文件过大：`src/frontend/src/i18n.tsx` 477 行（本轮净减约 298 行，虽仍超 400 但方向正确）；`src/frontend/src/features/profiles/ProfileDetailPage.tsx` 436 行（本轮净增约 4 行，建议后续拆分表单/对话框）；`src/frontend/src/shared/api/client.ts` 352 行、`sse.ts` 226 行未超阈值。
  - 复杂度：`client.ts request()` 与 `sse.ts connect()` 的 CC 均 ≥15，对应既有 minor f010/f009；本轮未见因复杂度新增的可观测缺陷。
  - 交付卫生：`src/frontend/src/i18n.test.tsx`、`src/frontend/src/shared/api/sse_hardening.test.ts` 仍是未跟踪文件（`??`），未执行 `git add -N`，不在 `git diff` 中；提交时若用 `git add -u` 会漏交付，必须在实施 commit 前显式加入。
  - 范围外观察：diff 未改后端/OpenAPI/browser-session；`docs/blueprint/frontend.md` 与 `docs/specs_index.md` 已提前按完成态更新（后者在 task 尚未 finish 时登记 t017），若本轮继续修复需同步复核。
- 总体判断：f001 的 i18n 清理仍未完成，f011 的幂等键作用域仍违反 AC-003 且可导致静默丢失用户编辑；两个 blocking 未解决，本轮 FAIL。
- 系统性 follow-up：无。

reviewed_scope: 6ba2328dbd02bee6

verdict: FAIL

## Round 3 (2026-11-03T05:49:59+08:00)

- round：3
- reviewed_at：2026-11-03T05:49:59+08:00
reviewed_scope: 62cb5b0d1664be92

### 前轮 finding 复核

- f001（important）**仍存在（修不彻底）**：Round 2 指出的 12 个键中仅删除了 `extensions`；按同一判据全量重扫，当前仍有 17 个「锚点版本只被已删除的 v1 文件 `t()` 引用、当前 `src/` 零 `t()` 引用」的键留在 en/zh 两套字典：`retry`(`i18n.tsx:20,220`)、`close`(`:26,226`)、`add`(`:27,227`)、`test`(`:29,229`)、`proxy`(`:52,249`)、`stopping`(`:56,252`)、`download`(`:66,261`)、`timezone`(`:97,289`)、`locale`(`:98,290`)、`width`(`:99,291`)、`height`(`:100,292`)、`tags`(`:101,293`)、`notes`(`:102,294`)、`connected`(`:103,295`)、`connecting`(`:104,296`)、`fullscreen`(`:106,298`)、`send`(`:107,299`)。Round 2 未计入的 6 个是 `close`/`connected`/`download`/`proxy`/`stopping`/`tags`；`extensions` 已删除。AC-001 的「仅 v1 使用的 i18n 键全部移除」仍不成立。
- f002（important）**已消除**：`client.ts:103-125` 为所有 POST/PUT/PATCH/DELETE 自动补 `Idempotency-Key`，成功响应后 `:151-153` 删除；原「仅 duplicate/reset 发送、每次新 UUID」已不存在。动作作用域的残留由 f011 跟踪。
- f003（important）**已消除**：`providers.tsx:52-63` 的 query/mutation retry 读取 `ApiError.retryable`；`client.ts:188-195` 映射后端 `retryable` 与 503。
- f004（important）**已消除**：`providers.tsx:13-21` 在 `SseSyncBridge` 注入 `setOnUnauthorized(() => void logout())`；`sse.ts:103-107` 遇 401 回调后 `stop()`；`sse_hardening.test.ts:19-40` 断言只连接一次。生产路径已接线。
- f005（important）**已消除**：`client.ts:78-83` 对 `http`/`//` 前缀用 `new URL(endpoint, window.location.origin)` 校验；本轮到 Node 实测 `//attacker.example` 与 `///attacker.example` 均解析为攻击者 origin 并被拒绝；跨源 `baseUrl` 旁路仍见 f012。
- f006（important）**已消除**：`ProfileDetailPage.tsx:37-41` 在 `profileId` 变化时清空 dirty ref；`:43-59` 只回填未修改字段；提交成功后 `:127` 清空。复制/前进后退切换详情页不会复用旧草稿。
- f007（minor）**仍存在**：`client.ts:127-150` 仍以 `controller.signal.aborted` 统一判定超时，外部 `AbortSignal` 取消会被报成 `errorCode: "timeout"`、`retryable: true`；`addEventListener` 仍未在请求结束移除。
- f008（minor）**仍存在**：`sse.ts:57-76,180-187` 无连接代次，快速 `stop()`→`start()` 时旧 `connect()` 的 catch/finally 仍可能给新连接安排重连。
- f009（minor）**仍存在**：`sse.ts:129-179` 尾帧解析与主循环重复；`connect()` 分支仍多。
- f010（minor）**仍存在**：`client.ts:70-208` 的 `request()` 继续承担 URL/同源、CSRF、幂等键、超时、响应解析与错误映射，分支数高。
- f011（important）**修不彻底**：`client.ts:103-125` 的幂等键仍按 `method:url:body` 指纹而不是用户动作生成，只是把 Round 2 的「永久留键」改成 10s TTL（`:109`）。两个方向仍违反 AC-003：
  1. 长写超时后重试拿不到同一个 key：`stop` 超时 120s、`duplicate`/`reset` 默认 30s，`at` 在请求开始时写入且不刷新（`:107-120`）；超过 10s 的自动/手动重试会生成新 key。若首次 `duplicate` 已在服务端提交但响应丢失，重试会再复制一份；`reset` 会再次重置并重掷指纹。
  2. 不同用户动作在 10s 内可复用同一 key：服务端按 operation id replay（`repository.py:89-101` create、`:272-281` update、`services/profile_service.py:461-470,561-569` duplicate/reset），同一 body 的第二次动作会直接返回首次结果而不重新执行。Round 2 的 B→C→B 保存场景在 10s 内仍可复现。
  10s TTL 不是 AC 要求的「用户动作生成并在重试中复用」。
- f012（minor）**仍存在**：`client.ts:75-77` 仍只校验 `endpoint`，不校验 `baseUrl` 拼出的最终 URL；`new ApiClient({ baseUrl: "https://other.example" })` 的相对请求仍带 `credentials: "include"` 与 `X-CSRF-Token`。生产只用默认空 `baseUrl`，无实际利用链。

### 本轮新发现

#### t017_code_f013 - 会话页启动错误条跨 profile 残留

- 严重度：minor
- 锚点：AC-002（会话页启动失败显示错误）实现引入的状态泄漏
- 位置：`src/frontend/src/features/profiles/BrowserSessionPage.tsx:119-131`；`src/frontend/src/features/profiles/useProfilesQuery.ts:129-145`
- 问题：`setDesiredStateMutation.isError` 属于 `useMutation` 实例状态；从 `/` 切到 `/?profileId=<other>` 时 `BrowserSessionPage` 不卸载（`app/router.tsx:19-22` 同一 element，无 `key`），也没有在 `profileId` 变化时 `reset()`。profile A 启动失败后切到 profile B，B 的「runtime not ready」页仍显示 A 的错误条，误导用户以为 B 启动失败。
- 建议：在 `profileId` 变化时 `setDesiredStateMutation.reset()`（或给页面加 `key={profileId}`）。

#### t017_code_f014 - SSE 401 触发的 logout 未捕获 rejection

- 严重度：minor
- 锚点：AC-003（SSE 401 触发登出）错误路径
- 位置：`src/frontend/src/app/providers.tsx:14-15`；`src/frontend/src/features/auth/useAuth.tsx:64-71`；`src/frontend/src/shared/api/client.ts:155-159,335-340`
- 问题：SSE 401 回调执行 `void logout()`，而 `logout()` 的 `client.auth.logout()` 在会话已过期时会再次返回 401，`request()` 抛 `ApiError`，`logout` 的 try/finally 不吞异常，`void` 使 rejection 无人处理。浏览器会记录 unhandled rejection；本地登出状态仍由 `finally` 清除，不影响 AC 主行为。
- 建议：把回调改为 `void logout().catch(() => {})`，或在 `logout()` 内捕获登出请求失败（`AppLayout.tsx:57-62` 已采用显式 catch 的同一模式）。

#### t017_code_f015 - blueprint 前端门禁仍引用已删除的 tsbuildinfo

- 严重度：minor
- 锚点：AC-004（TypeScript 增量构建产物不入库）文档一致性
- 位置：`docs/blueprint/testing.md:160,166`
- 问题：本 diff 删除了 `src/frontend/tsconfig.tsbuildinfo` 并把 `tsBuildInfoFile` 指向 `node_modules/.tmp`（`src/frontend/tsconfig.json:12`、`.gitignore`），但 `testing.md:160` 仍写「构建会改写已入库的 `src/frontend/tsconfig.tsbuildinfo`，提交前还原」，门禁代码块 `:166` 仍执行 `git show HEAD:src/frontend/tsconfig.tsbuildinfo > ...`。提交后该路径在 HEAD 不存在，按 `-e -o pipefail` 执行会失败。
- 建议：删除该还原步骤并更新说明，或改为校验 `tsBuildInfoFile` 不在 `git ls-files` 中。

### AC 复验方式

- AC-001：`re_verified`。实跑 `npx tsc -b`（exit 0）、`NODE_OPTIONS=--no-experimental-webstorage npm test --prefix src/frontend`（17 files / 87 tests passed）、`npm run build --prefix src/frontend` + `verify_frontend_dist.py`（通过）；`rg` 确认 v1 路径与 `@dnd-kit`/`@novnc`/直接 `react-router` 零引用；但 17 个 v1-only i18n 键仍在（f001），AC 不成立。
- AC-002：`re_verified`。重跑 build 并 grep `dist/assets/*.css` 确认 `.bg-primary`/`.text-primary-foreground`/`.border-primary`/`.text-primary` 等全部存在；读码核实 `BrowserSessionPage.tsx:119-131` 错误条、`ProfileDetailPage.tsx:37-59` dirty 回填、`useProfilesQuery.ts:177-194` 连续 3 次失败容忍与超时文案；`sse_hardening.test.ts:42-63` 验证尾帧 flush。dirty/轮询两项无独立自动化用例，按代码路径核实；新错误条跨 profile 残留见 f013。
- AC-003：`re_verified`。核对 OpenAPI 六个写接口的 `Idempotency-Key` 声明与客户端实际发送；读码核实 10s 指纹复用（f011）、`providers.tsx` 的 retryable 消费者、`client.ts:78-83` 同源校验、`sse.ts:103-107` + `providers.tsx:13-21` 的 401 登出接线；Node `URL` 实测 protocol-relative 拦截。f011/f012 为残留缺口。
- AC-004：`re_verified`。`npm ls react-router react-router-dom` 仅 `react-router-dom@7.18.5` 与单实例 `react-router@7.18.5`；`git ls-files '*tsbuildinfo'` 为空；`i18n.tsx:448-450` 同步 `documentElement.lang`、`:421-434` 迁移旧键；`i18n.test.tsx` 实跑通过。`testing.md:160,166` 已过期（f015）。
- coverage = 4 / 4

### 结论（Round 3）

- 前轮 finding 复核：f001 修不彻底；f011 修不彻底；f002/f003/f004/f005/f006 已消除；f007/f008/f009/f010/f012 仍存在（minor）。
- 本轮新发现：3 条 minor（f013-f015）。
- 未进表的提示：
  - 文件过大：`src/frontend/src/i18n.tsx` 475 行（本 task 净减约 284 行，方向正确）；`src/frontend/src/features/profiles/ProfileDetailPage.tsx` 436 行（本 task 净增约 14 行，建议后续拆分表单/对话框）；`client.ts` 357 行、`sse.ts` 226 行未超阈值。
  - 复杂度：`client.ts request()` 与 `sse.ts connect()` 的 CC 均 ≥15，对应既有 minor f010/f009；本轮未见因复杂度新增的可观测缺陷。
  - 交付卫生：`git status --short` 无未跟踪交付文件；新测试均以 new file 出现在 diff 中。
  - 范围外观察：diff 未改后端/OpenAPI/browser-session；`docs/blueprint/frontend.md` 已按实际行为更新；`docs/specs_index.md` 在 task 尚未 finish 时提前登记 t017（流程时序问题，非内容错误，不改判）。
  - 未运行：Playwright E2E（需要完整 Docker 拓扑），故 AC-002/003 的端到端路径未复验。
- 总体判断：AC-001 仍有 17 个 v1-only i18n 键，AC-003 的幂等键仍不是按用户动作作用域生成并在重试中复用；f001/f011 两个 important 未解决，本轮 FAIL。
- 系统性 follow-up：无（t018 承接测试体系与仓库卫生，不承接 f011 的客户端幂等语义）。

verdict: FAIL

## Round 4 (2026-11-03T06:02:29+08:00)

- round：4
- reviewed_at：2026-11-03T06:02:29+08:00
reviewed_scope: 992830d2f2e3f44e

### 前轮 finding 复核

- f001（important）**仍存在（修不彻底）**：本轮又删除了 11 个键（`retry`/`add`/`test`/`timezone`/`locale`/`width`/`height`/`notes`/`connecting`/`fullscreen`/`send`），但按同一判据重扫（锚点版本仅被已删除 v1 文件以 `t("键")` 引用、当前 `src/` 零 `t()` 引用），仍有 6 个键留在 en/zh 两套字典：`close`（`i18n.tsx:25,211`，锚点仅 `ProfileFiles.tsx`/`SettingsPanel.tsx`）、`proxy`（`:47,231`，仅 `ProfileForm.tsx`/`ProfileList.tsx`）、`stopping`（`:51,234`，仅 `LaunchButton.tsx`）、`download`（`:61,243`，仅 `UpdateBanner.tsx`）、`tags`（`:92,271`，仅 `ProfileForm.tsx`）、`connected`（`:93,272`，仅 `ProfileViewer.tsx`）。这 6 个字符串当前只出现在 WebSocket 事件名、Profile 字段名或会话状态字面量里，不是 i18n 使用；AC-001 的「仅 v1 使用的 i18n 键」仍未清完。
- f002（important）**已消除**：`client.ts:195-264` 的写方法不再自动生成 UUID，改为接收调用方 key；原「仅 duplicate/reset 发送、每次新 UUID」的问题不存在。动作级 key 由 mutation 层传入（见 f016 的新问题）。
- f003（important）**已消除**：`providers.tsx:52-63` 的 query/mutation retry 读取 `ApiError.retryable`；`client.ts:169-181` 映射后端 `retryable` 与 503。
- f004（important）**已消除**：`providers.tsx:13-21` 注入 `setOnUnauthorized(() => void logout())`；`sse.ts:103-107` 遇 401 回调后 `stop()`；`sse_hardening.test.ts:19-40` 断言只连接一次。
- f005（important）**已消除**：`client.ts:83-88` 对 `http`/`//` 前缀用 `new URL(endpoint, origin)` 校验 origin；Node 实测 `//attacker.example/x` 与 `///attacker.example/x` 均解析到攻击者 origin 并被拒绝。跨源 `baseUrl` 旁路仍见 f012。
- f006（important）**已消除**：`ProfileDetailPage.tsx:37-41` 在 `profileId` 变化时清空 dirty ref；`:43-59` 只回填未修改字段；提交成功后 `:127` 清空。
- f007（minor）**仍存在**：`client.ts:109-125` 仍以 `controller.signal.aborted` 统一判定超时，外部 `AbortSignal` 取消会被报成 `errorCode: "timeout"`、`retryable: true`；`addEventListener` 仍未在请求结束移除。
- f008（minor）**仍存在**：`sse.ts:57-76,181-187` 无连接代次，快速 `stop()`→`start()` 时旧 `connect()` 的 catch/finally 仍可能给新连接安排重连。
- f009（minor）**仍存在**：`sse.ts:129-179` 尾帧解析与主循环重复；`connect()` 分支仍多。
- f010（minor）**仍存在**：`client.ts:75-160` 的 `request()` 继续承担 URL/同源、CSRF、超时、响应解析与错误映射，分支数高。
- f011（important）**已消除（原缺陷）**：`client.ts` 的 `method:url:body` 指纹与 10s TTL 已删除；`useProfilesQuery.ts`/`useArtifacts.ts` 改为 mutation 级 `useRef` 保存 key，React Query 自动重试复用同一 key，不同用户动作得到新 UUID。但复合动作复用了同一 key，另立 f016。
- f012（minor）**仍存在**：`client.ts:80-88` 仍只校验 `endpoint`，不校验 `baseUrl` 拼出的最终 URL；`new ApiClient({ baseUrl: "https://other.example" })` 的相对请求仍带 `credentials: "include"` 与 `X-CSRF-Token`。
- f013（minor）**仍存在**：`BrowserSessionPage.tsx:13-19,119-131` 未在 `profileId` 变化时 `reset()` mutation 错误；从 A 切到 B 时 A 的启动错误条仍显示。
- f014（minor）**仍存在**：`providers.tsx:14-16` 仍是 `void logout()`，会话过期时 `client.auth.logout()` 再次 401 会使 promise rejection 无人处理。
- f015（minor）**仍存在**：`docs/blueprint/testing.md:160,166` 仍要求还原已移出版本库的 `src/frontend/tsconfig.tsbuildinfo`。

### 本轮新发现

#### t017_code_f016 - 复合动作复用同一幂等键，「应用并重启」必然 409

- 严重度：critical
- 锚点：AC-002（「应用并重启」在轮询遇到瞬时失败时继续收敛）与 AC-003（写操作由用户动作生成幂等键并在重试中复用）
- 位置：`src/frontend/src/features/profiles/useProfilesQuery.ts:241-249`；后端 `src/backend/cbrowser/adapters/database/repository.py:627-644`、`src/backend/cbrowser/api/app.py:229-240`
- 问题：`useApplyDisplaySettingsMutation` 为一次「应用并重启」生成一个 key（`:241`），先用它调用 `stop`（`:242`），再用同一个 key 调用 `setDesiredState("running")`（`:249`）。后端把 `Idempotency-Key` 作为审计记录主键，且 `sig_hash` 包含 `desired_state`（`repository.py:627-629`）：第一次 stop 写入 `sig(stopped)`，第二次 running 命中同一 operation id 但 sig 不同，抛 `IdempotencyConflictError`，全局 handler 返回 409 `idempotency_conflict`（`app.py:229-240`），且 `retryable: false`。结果是点击「应用并重启」时 profile 已被停止，但重启请求必定失败，profile 停在 stopped；每次重试都会重复同一冲突，功能完全不可用。同一 hook 级的 `actionKey` 还会在 pending 期间被下一次 `mutate` 复用：例如 `AppLayout.tsx:40-55` 的 stop 尚未返回时用户切到另一个 profile 再执行启停，第二次请求会带上前一个 profile 的 key，`sig_hash` 因 `profile_id` 不同而不匹配，同样 409。
- 建议：按「每个 HTTP 写请求」持有幂等键，而不是按 mutation：复合动作保存两个独立 key（stop key、desired-state key），各自在整条 mutation 重试链中复用；或把 key 作为 mutation variables 的一部分并与具体请求绑定，变量变化时重置。补一条用例断言「应用并重启」发出的 stop 与 desired-state 使用不同 key 且不会命中服务端 conflict。

### AC 复验方式

- AC-001：`re_verified`。实跑 `npx tsc -b`（exit 0）、`NODE_OPTIONS=--no-experimental-webstorage npx vitest run`（18 files / 88 tests passed）、`npm run build --prefix src/frontend`（含 `verify_frontend_dist.py`）；`rg` 确认 v1 路径、`@dnd-kit`、`@novnc`、直接 `react-router` 零引用；但按锚点引用集重扫仍有 6 个 v1-only i18n 键（f001），AC 不成立。
- AC-002：`re_verified`。产物 CSS 中确认 `.bg-primary`/`.text-primary-foreground`；读码核实会话启动错误条、dirty 回填、`waitForRuntimeState` 连续 3 次失败容忍与超时文案；但「应用并重启」因 f016 必定 409，该分项不成立。未运行 Playwright E2E。
- AC-003：`re_verified`。核对六个 profile 写接口的 `Idempotency-Key` 发送与 mutation 级复用；`providers.tsx` 消费 `retryable`；`sse.ts`+`providers.tsx` 完成 401 登出接线；Node 实测 protocol-relative 同源拦截。f016 为新的幂等键作用域缺陷，f012 为残留同源缺口。
- AC-004：`re_verified`。`npm ls react-router react-router-dom` 仅 `react-router-dom@7.18.5` 与单实例 `react-router@7.18.5`；`git ls-files '*tsbuildinfo'` 为空；`i18n.tsx:393-434` 完成存储键迁移与 `documentElement.lang` 同步，`i18n.test.tsx` 实跑通过。`testing.md:160,166` 已过期（f015）。
- coverage = 4 / 4

### 结论（Round 4）

- 前轮 finding 复核：f001 修不彻底（剩 6 个键）；f002/f003/f004/f005/f006/f011 已消除；f007/f008/f009/f010/f012/f013/f014/f015 仍存在（minor）；本轮新增 f016（critical）。
- 本轮新发现：1 条（critical）。
- 未进表的提示：
  - 文件过大：`src/frontend/src/i18n.tsx` 448 行（本 task 净减约 311 行，方向正确）、`src/frontend/src/features/profiles/ProfileDetailPage.tsx` 436 行（本 task 净增约 14 行）、`src/frontend/src/shared/api/client.ts` 353 行、`src/frontend/src/shared/api/sse.ts` 226 行；`i18n.tsx` 与 `ProfileDetailPage.tsx` 仍超 400 行建议阈值，未直接导致可观测缺陷，不进 finding 表。
  - 复杂度：`client.ts request()` 与 `sse.ts connect()` 的 CC 仍 ≥15，对应既有 minor f010/f009；本轮未见因复杂度新增的可观测缺陷。
  - 交付卫生：`git status --short` 无未跟踪交付文件；新测试均以 new file 出现在 diff 中。
  - 范围外观察：diff 未改后端/OpenAPI/browser-session；`docs/blueprint/frontend.md` 已按实际行为更新；`docs/specs_index.md` 在 task 尚未 finish 时提前登记 t017（流程时序问题，非内容错误，不改判）。
  - 未运行：Playwright E2E（需要完整 Docker 拓扑），故 AC-002/003 的端到端路径未复验。
- 总体判断：AC-001 仍有 6 个 v1-only i18n 键；幂等键修复让「应用并重启」固定 409 并可能把 profile 停在 stopped，f001/f016 两个 blocking 未解决，本轮 FAIL。
- 系统性 follow-up：无（f016 与 f001 均为本 task 内可直接修复的缺陷）。

verdict: FAIL

## Round 5 (2026-11-03T06:10:10+08:00)

- round：5
- reviewed_at：2026-11-03T06:10:10+08:00
reviewed_scope: 17cd958032ee86b9

### 前轮 finding 复核

- f001（important）**仍存在（本轮未修）**：`i18n.tsx` 相对 Round 4 无任何变化，仍有 6 个「锚点版本仅被已删除 v1 文件以 `t("键")` 引用、当前 `src/` 零 `t()` 引用」的键留在 en/zh 两套字典：`close`（`i18n.tsx:25,211`，锚点仅 `ProfileFiles.tsx`/`SettingsPanel.tsx`）、`proxy`（`:47,231`，仅 `ProfileForm.tsx`/`ProfileList.tsx`）、`stopping`（`:51,234`，仅 `LaunchButton.tsx`）、`download`（`:61,243`，仅 `UpdateBanner.tsx`）、`tags`（`:92,271`，仅 `ProfileForm.tsx`）、`connected`（`:93,272`，仅 `ProfileViewer.tsx`）。全量重扫当前 `src/frontend/src` 的 `t("字面量")` 与 `SessionDiagnostics` 的键映射，除上述 6 个外无其他死键；这 6 个字符串当前只出现在 WebSocket 事件名、Profile 字段名或会话状态字面量里，不是 i18n 使用。AC-001 的「仅 v1 使用的 i18n 键」仍未清完，打勾不成立。
- f002（important）**已消除**：`client.ts:195-264` 的写方法不再在客户端内生成 UUID，改为接收调用方 key；`useProfilesQuery.ts:60-70` 等 mutation 在动作层生成并复用。原缺陷不存在。
- f003（important）**已消除**：`providers.tsx:52-63` 的 query/mutation retry 读取 `ApiError.retryable`；`client.ts:166-173` 映射后端 `retryable` 与 503。
- f004（important）**已消除**：`providers.tsx:13-21` 注入 `setOnUnauthorized(() => void logout())`；`sse.ts:103-107` 遇 401 回调后 `stop()`；`sse_hardening.test.ts:19-40` 断言只连接一次。
- f005（important）**已消除（原绕过）**：`client.ts:83-88` 对 `http`/`//` 前缀用 `new URL(endpoint, origin)` 校验 origin；Node 实测 `//attacker.example/x` 与 `///attacker.example/x` 均解析到攻击者 origin 并被拒绝。反斜杠变体见 f017。
- f006（important）**已消除**：`ProfileDetailPage.tsx:39-41` 在 `profileId` 变化时清空 dirty ref；`:43-59` 只回填未修改字段；提交成功后 `:127` 清空。
- f007（minor）**仍存在**：`client.ts:108-131` 仍以 `controller.signal.aborted` 统一判定超时，外部 `AbortSignal` 取消会被报成 `errorCode: "timeout"`、`retryable: true`；`:113` 的 `addEventListener` 仍未在请求结束移除。
- f008（minor）**仍存在**：`sse.ts:57-76,181-187` 无连接代次，快速 `stop()`→`start()` 时旧 `connect()` 的 catch/finally 仍可能给新连接安排重连。
- f009（minor）**仍存在**：`sse.ts:129-179` 尾帧解析与主循环重复；`connect()` 分支仍多。
- f010（minor）**仍存在**：`client.ts:75-186` 的 `request()` 继续承担 URL/同源、CSRF、超时、响应解析与错误映射，分支数高。
- f011（important）**已消除**：`client.ts` 已无 `method:url:body` 指纹或 10s TTL；mutation 层 `useRef` 保存 key、`onSettled` 清理，不同用户动作得到新 UUID（本轮的复合动作拆分见 f016 复核）。
- f012（minor）**仍存在**：`client.ts:80-88` 仍只校验 `endpoint`，不校验 `baseUrl` 拼出的最终 URL；`new ApiClient({ baseUrl: "https://other.example" })` 的相对请求仍带 `credentials: "include"` 与 `X-CSRF-Token`。
- f013（minor）**仍存在**：`BrowserSessionPage.tsx:13-19,119-131` 未在 `profileId` 变化时 `reset()` mutation 错误；从 A 切到 B 时 A 的启动错误条仍显示。
- f014（minor）**仍存在**：`providers.tsx:14-16` 仍是 `void logout()`，会话过期时 `client.auth.logout()` 再次 401 会使 promise rejection 无人处理。
- f015（minor）**仍存在**：`docs/blueprint/testing.md:160,166` 仍要求还原已移出版本库的 `src/frontend/tsconfig.tsbuildinfo`，提交后该命令会失败。
- f016（critical）**已消除（本轮修复的主体）**：`useProfilesQuery.ts:238-239` 拆成 `stopKey`/`startKey` 两个 ref，`:242-243` 分别生成两个独立 key，`:244` 的 `stop` 用 stop key，`:251` 的 `setDesiredState("running")` 用 start key，`:261-264` 在 `onSettled`（React Query 5 在整条重试链结束后才调用，已核对 `@tanstack/query-core@5.105.0` 的 `mutation.js`）清理。后端以 operation id 为 `AuditEventModel` 主键并按 `sig_hash` 校验（`repository.py:627-629,640-644`），两个不同 key 不再触发 `idempotency_conflict`，「应用并重启」不再固定 409。修复引入的边界见 f018。

### 本轮新发现

#### t017_code_f017 - 同源校验可被反斜杠前缀绕过

- 严重度：minor
- 锚点：AC-003（「只向同源发送凭据与 CSRF 头」）
- 位置：`src/frontend/src/shared/api/client.ts:80-88`
- 问题：同源校验只覆盖 `endpoint.startsWith("http") || endpoint.startsWith("//")`。`endpoint = "/\\evil.example/x"`（源码字面量 `"/\\\\evil.example/x"`）既不匹配 `http` 也不匹配 `//`，跳过校验；构造出的相对 URL 在浏览器 URL 解析中把 `\` 等价为 `/`，最终请求 `https://evil.example/x`，而 `:94-102` 仍发送 `credentials: "include"` 与从本域读取的 `X-CSRF-Token`。Node WHATWG URL 实测 `new URL("/\\evil.example/x", "https://app.example")` → `https://evil.example/x`。当前生产调用点全是固定字面量路径，无实际利用链，故与 f012 同级定 minor；但同源控制没有在最终 URL 上闭合。
- 建议：对最终 `url` 统一做 `new URL(url, window.location.origin)` 的 origin 断言（同时闭合 f012 的跨源 `baseUrl`），或显式拒绝含 `\` 的端点；补反斜杠用例并断言 `fetch` 未被调用。

#### t017_code_f018 - 「应用并重启」在 start 请求超时重试时会先重放 stop，可能 120s 假失败

- 严重度：minor
- 锚点：AC-002（「应用并重启」收敛语义）与 AC-003（重试复用幂等键）的实现边界
- 位置：`src/frontend/src/features/profiles/useProfilesQuery.ts:241-259`
- 问题：两个 key 在整条 mutation 重试链中复用。若 `setDesiredState("running")` 已在服务端生效但响应超时（`ApiError.errorCode === "timeout"`, `retryable: true`），React Query 会重跑整个 `mutationFn`：`:244` 的 `stop` 用 stop key 命中后端 replay（`repository.py:640-646`「return current state」），不会把已经 running 的 profile 再次停掉；随后 `:245-250` 的 `waitForRuntimeState(observed === "stopped", 120s)` 等不到 stopped，抛普通 Error（不满足 mutation 的 `ApiError` 重试条件），用户看到「did not converge before timeout」的假失败并额外等待 120s，尽管重启实际已成功。
- 建议：按阶段记录完成标志并跳过已完成阶段的 replay 等待（例如 start 请求超时重试时直接进入最终 running 等待），或对复合动作关闭 React Query 自动重试、由轮询循环自行收敛；补一条「start 超时后重试」的用例锁定行为。

### AC 复验方式

- AC-001：`re_verified`。实跑 `npx tsc -b`（exit 0）、`NODE_OPTIONS=--no-experimental-webstorage npx vitest run`（18 files / 88 tests passed）、`npm run build --prefix src/frontend` + `verify_frontend_dist.py`（通过）；`rg` 确认 v1 路径、`@dnd-kit`、`@novnc`、直接 `react-router` 零引用；`npm ls` 仅 `react-router-dom@7.18.5` 与单实例 `react-router@7.18.5`；但按锚点引用集重扫仍有 6 个 v1-only i18n 键（f001），AC 不成立。
- AC-002：`re_verified`。产物 CSS 中确认 `.bg-primary`/`.text-primary-foreground`；读码核实 `BrowserSessionPage.tsx:119-131` 启动错误条、`ProfileDetailPage.tsx:39-59` dirty 回填、`waitForRuntimeState`（`useProfilesQuery.ts:205-232`）连续 3 次失败容忍与 `polling failed`/`did not converge before timeout` 文案区分、SSE 尾帧 flush；f016 拆分后「应用并重启」的 stop/start 不再共用 operation id。未运行 Playwright E2E（需完整 Docker 拓扑），复合动作的真实编排未端到端复验。
- AC-003：`re_verified`。核对六个 profile 写接口的 `Idempotency-Key` 发送与 mutation 层复用（`useProfilesQuery.ts:60-195`、`useArtifacts.ts:34-72`）；`providers.tsx` 消费 `retryable`；`sse.ts`+`providers.tsx` 完成 401 登出接线；Node 实测 protocol-relative 同源拦截；后端 replay 语义读码确认 stop/start 拆分有效。f012/f017/f018 为残留缺口。
- AC-004：`re_verified`。`npm ls react-router react-router-dom` 仅 `react-router-dom@7.18.5` 与单实例 `react-router@7.18.5`；`git ls-files '*tsbuildinfo'` 为空；读码确认 `i18n.tsx:421-429` 同步 `documentElement.lang`、`:394-407` 迁移旧键；`i18n.test.tsx` 随套件通过。`testing.md:160,166` 已过期（f015）。
- coverage = 4 / 4

### 结论（Round 5）

- 前轮 finding 复核：f001 仍存在（6 个键，本轮未修）；f016 已消除（stop/start key 拆分生效）；f002/f003/f004/f005/f006/f011 已消除；f007/f008/f009/f010/f012/f013/f014/f015 仍存在（minor）。
- 本轮新发现：2 条 minor（f017 同源反斜杠绕过、f018 复合动作重试假失败）。
- 未进表的提示：
  - 文件过大：`src/frontend/src/i18n.tsx` 448 行（本 task 净减约 311 行，方向正确）、`src/frontend/src/features/profiles/ProfileDetailPage.tsx` 436 行（本 task 净增约 14 行）、`src/frontend/src/shared/api/client.ts` 353 行、`sse.ts` 226 行、`useProfilesQuery.ts` 312 行；`i18n.tsx` 与 `ProfileDetailPage.tsx` 仍超 400 行建议阈值，未直接导致可观测缺陷，不进 finding 表。
  - 复杂度：`client.ts request()` 与 `sse.ts connect()` 的 CC 仍 ≥15，对应既有 minor f010/f009；`useApplyDisplaySettingsMutation` 的 mutationFn 拆分后分支较少，本轮未见因复杂度新增的可观测缺陷。
  - 交付卫生：`git status --short --untracked-files=all` 无未跟踪交付文件；新测试均以 new file 出现在 diff 中。
  - 范围外观察：diff 未改后端/OpenAPI/browser-session；`docs/blueprint/frontend.md` 已按实际行为更新；`docs/specs_index.md` 在 task 尚未 finish 时提前登记 t017（流程时序问题，非内容错误，不改判）。
  - 未运行：Playwright E2E（需要完整 Docker 拓扑），故 AC-002/003 的端到端路径未复验。
- 总体判断：本轮唯一代码改动是把「应用并重启」的 stop/start 幂等键拆开，f016 已消除且静态验证通过；但 AC-001 的 i18n 清理本轮未动，仍有 6 个 v1-only 死键，f001 这个 important 未解决，本轮 FAIL。
- 系统性 follow-up：无（f001/f017/f018 均为本 task 内可直接修复的缺陷）。

verdict: FAIL

## Round 6 (2026-11-03T06:18:20+08:00)

- round：6
- reviewed_at：2026-11-03T06:18:20+08:00
reviewed_scope: d10544a4b4350576

### 前轮 finding 复核

- f001（important）**已消除**：`i18n.tsx:17-196` 与 `:198-365` 两套字典现各 150 键（锚点 293 键，共删 144 键），Round 5 点名的 `close`/`proxy`/`stopping`/`download`/`tags`/`connected` 已全部不存在。按锚点重扫：锚点里仅被已删除 v1 文件以 `t("键")` 引用的键，当前生产代码全部零 `t()` 引用；反向扫描当前字典，150 个键在非测试生产代码中均有引用（134 个直接 `t("键")`，16 个经 `SessionDiagnostics.tsx:15-37` 的 `AUDIO_STATUS_KEYS`/`STAGE_TITLE_KEYS` 映射），无死键、无未定义键，en/zh 键集合完全一致。AC-001 的 i18n 清理成立。
- f016（critical）**已消除且保持**：`useProfilesQuery.ts:238-243` 仍为 `stopKey`/`startKey` 两个 ref，`:244` 的 stop 与 `:251` 的 setDesiredState 分别携带独立 key，`:261-264` 在整条重试链结束后的 `onSettled` 清理；新增 `useProfilesQuery.apply.test.tsx:26-58` 用真实 hook 断言两个请求各一次且 key 不同。复核 `AppLayout.tsx:150-172`、`ProfileDetailPage.tsx:331-335` 的按钮均由对应 `isPending` 禁用，未发现同一 hook 并发复用 key 的可达路径。
- f002 / f003 / f004 / f005 / f006 / f011（important）**已消除**：本轮未改动对应文件，复核 `client.ts:195-264`（调用方传 key）、`providers.tsx:52-63`（retryable）、`providers.tsx:13-21`+`sse.ts:103-107`（401 登出）、`client.ts:83-88`（绝对 URL 同源）、`ProfileDetailPage.tsx:39-59`（dirty 回填）均未见回归。
- f007（minor）**仍存在**：`client.ts:108-126` 仍以 `controller.signal.aborted` 统一判定超时，外部取消会被报成 `timeout`/`retryable: true`；`:113` 的监听器未在请求结束移除。
- f008（minor）**仍存在**：`sse.ts:57-76,181-190` 无连接代次，快速 `stop()`→`start()` 时旧 `connect()` 的 catch/finally 仍可能给新连接安排重连。
- f009（minor）**仍存在**：`sse.ts:121-179` 尾帧解析与主循环仍重复；`connect()` 分支多。
- f010（minor）**仍存在**：`client.ts:75-186` 的 `request()` 继续承担 URL/同源、CSRF、超时、响应解析与错误映射。
- f012（minor）**仍存在**：`client.ts:80-88` 仍只校验 `endpoint`，不校验 `baseUrl` 拼出的最终 URL。
- f013（minor）**仍存在**：`BrowserSessionPage.tsx:115-130` 未在 `profileId` 变化时 `reset()` mutation 错误，从 A 切到 B 时 A 的启动错误条仍显示。
- f014（minor）**仍存在**：`providers.tsx:15` 仍是 `void logout()`，登出请求再 401 时 promise rejection 无人处理。
- f015（minor）**仍存在**：`docs/blueprint/testing.md:160,166` 仍要求还原已移出版本库的 `src/frontend/tsconfig.tsbuildinfo`。
- f017（minor）**仍存在**：`client.ts:80-88` 的同源校验仍可被 `/\evil.example/x` 反斜杠前缀绕过（最终 URL 才解析）。
- f018（minor）**仍存在**：`useProfilesQuery.ts:241-259` 在 start 请求超时重试时会先重放 stop 并重新等待 stopped，可能额外等待 120s 后报假失败。

### 本轮新发现

无。0 条。

### AC 复验方式

- AC-001：`re_verified`。实跑 `npx tsc -b`（exit 0）、`NODE_OPTIONS=--no-experimental-webstorage npx vitest run`（19 files / 89 tests passed）、`npm run build` + `verify_frontend_dist.py`（通过）；`rg` 确认 `@dnd-kit`、`@novnc`、直接 `react-router` 与 v1 路径零引用；脚本重扫确认当前 i18n 字典无 v1-only 死键；`npm ls` 仅 `react-router-dom@7.18.5` 与单实例 `react-router@7.18.5`；`git ls-files '*tsbuildinfo'` 为空。
- AC-002：`re_verified`。产物 CSS 中确认 `.bg-primary`/`.text-primary-foreground`；`BrowserSessionPage.tsx:119-131` 启动错误条、`ProfileDetailPage.tsx:39-59` dirty 回填、`useProfilesQuery.ts:210-231` 连续 3 次失败容忍与 `polling failed`/`did not converge before timeout` 文案、`sse.ts:157-179` 尾帧 flush 均在位。未运行 Playwright E2E（需完整 Docker 拓扑），复合动作端到端未复验。
- AC-003：`re_verified`。核对六个 profile 写接口的 `Idempotency-Key` 发送与 mutation 层复用（`useProfilesQuery.ts:57-195`、`useArtifacts.ts:34-72`）；`useApplyDisplaySettingsMutation` 的 stop/start key 拆分与新增用例通过；`providers.tsx` 消费 `retryable`；`sse.ts`+`providers.tsx` 完成 401 登出接线。f012/f017/f018 为残留 minor。
- AC-004：`re_verified`。`i18n.tsx:371-417` 存储键迁移到 `cbrowser.locale` 并读取/清除旧 `cbm.locale`，`:409-411` 同步 `documentElement.lang`；`i18n.test.tsx` 随套件通过；`git ls-files '*tsbuildinfo'` 为空；`npm ls` 确认路由单包单实例。
- coverage = 4 / 4

### 结论（Round 6）

- 前轮 finding 复核：f001 已消除（144 个 v1-only 键删净，当前 150 键全部有生产引用）；f016 已消除且保持（stop/start key 独立、onSettled 清空，新增用例锁定）；f002/f003/f004/f005/f006/f011 仍为已消除；f007/f008/f009/f010/f012/f013/f014/f015/f017/f018 仍为 minor。
- 本轮新发现：0 条。
- 未进表的提示：
  - 文件过大：`src/frontend/src/i18n.tsx` 436 行（锚点 759 行，本 task 净减 323 行，不满足「仍净增」条件）；`src/frontend/src/features/profiles/ProfileDetailPage.tsx` 436 行（本 task 净增约 14 行，超 400 建议阈值，未直接导致可观测缺陷）；`client.ts` 353、`useProfilesQuery.ts` 312、`sse.ts` 226 行。
  - 复杂度：`client.ts request()` 与 `sse.ts connect()` 的 CC 仍 ≥15，对应既有 minor f010/f009；本轮未见因复杂度新增的可观测缺陷。
  - 构建观察：首次 `npm run build` 在 vite copyDir 阶段对刚被 `prebuild` 重写的 vendored 文件偶发一次 ENOENT，立即重跑通过；判断为同 worktree 并发构建/文件系统瞬时竞争，非本 diff 缺陷。
  - 交付卫生：`git status --short --untracked-files=all` 无 reviewer 不可见的未跟踪交付文件；`reviewed_scope` 实时重算为 `d10544a4b4350576`，与报告一致。
  - 未运行：Playwright E2E（需要完整 Docker 拓扑）。
- 总体判断：f001 与 f016 两个前轮 blocking 均已消除，本轮无新的 critical/important，仅余既有 minor，本轮 PASS。
- 系统性 follow-up：无。

verdict: PASS

## Round 8 (2026-11-03T06:39:22+08:00)

- round：8
- reviewed_at：2026-11-03T06:39:22+08:00
reviewed_scope: 3307c4bc0f37ff9e

### 前轮 finding 复核

- f001（important）**已消除**：`i18n.tsx:17-196`/`:198-365` 两套字典各 150 键且键集合一致；重扫生产代码（含 `SessionDiagnostics.tsx:16-35` 的键映射）无 v1-only 死键，`t()` 字面量均有定义。实跑 `tsc -b` 与 vitest 通过。
- f016（critical）**已消除且保持**：`useProfilesQuery.ts:238-243` 仍为独立 `stopKey`/`startKey`，`:244` 的 stop 与 `:251` 的 setDesiredState 分别携带不同 key，`:261-264` 在整条重试链结束后清理；`useProfilesQuery.apply.test.tsx` 断言两 key 非空且不同，本轮套件通过。`AppLayout.tsx:150-172`、`ProfileDetailPage.tsx:331-335` 的按钮 pending 时禁用，未发现同一 hook 并发复用 key 的可达路径。
- f002（important）**已消除**：`client.ts:202-312` 的写方法接收调用方 key；`useProfilesQuery.ts:60-195`、`useArtifacts.ts:38-72` 在 mutation 层生成并复用。
- f003（important）**已消除**：`providers.tsx:52-57` 的 query/mutation retry 使用 `client.ts:33-38` 的 `shouldRetryRequest`，按 `ApiError.retryable` 决策。
- f004（important）**已消除**：`providers.tsx:13-21` 注入 SSE 401 回调；`sse.ts:103-107` 停止重连；`sse_hardening.test.ts:19-40` 断言只建立一次连接。
- f005（important）**已消除**：`client.ts:90-95` 对 `http` 与 protocol-relative 端点做同源校验；本轮复核未回归。
- f006（important）**已消除**：`ProfileDetailPage.tsx:39-41` 按 `profileId` 清空 dirty 标记，`:43-59` 只回填未修改字段，`:127` 保存成功后清空。
- f011（important）**已消除**：`client.ts` 已无 `method:url:body` 指纹或 TTL；动作级 key 由 mutation 层持有并在 `onSettled` 清理；复合动作拆分见 f016 复核。
- f007（minor）**仍存在**：`client.ts:115-137` 仍以 `controller.signal.aborted` 统一判定超时，外部 `AbortSignal` 取消会被报成 `timeout`/`retryable: true`；`:120` 的监听器未在请求结束后移除。
- f008（minor）**仍存在**：`sse.ts:57-76,180-190` 无连接代次，快速 `stop()`→`start()` 时旧 `connect()` 的 catch/finally 仍可能给新连接安排重连。
- f009（minor）**仍存在**：`sse.ts:121-179` 尾帧解析仍复制主循环逻辑，`connect()` 分支多。
- f010（minor）**仍存在**：`client.ts:82-193` 的 `request()` 仍同时承担 URL/同源、CSRF、超时、响应解析与错误映射。
- f012（minor）**仍存在**：`client.ts:87-95` 只校验 `endpoint`，不校验 `baseUrl` 拼出的最终 URL。
- f013（minor）**仍存在**：`BrowserSessionPage.tsx:119-131` 未在 `profileId` 变化时 `reset()` mutation 错误，从 A 切到 B 时 A 的启动错误条仍显示。
- f014（minor）**仍存在**：`providers.tsx:13-16` 仍是 `void logout()`，登出请求再次 401 时 promise rejection 无人处理。
- f015（minor）**仍存在**：`docs/blueprint/testing.md:160,166` 仍要求还原已移出版本库的 `src/frontend/tsconfig.tsbuildinfo`。
- f017（minor）**仍存在**：`client.ts:90-95` 的同源校验仍可被 `/\evil.example/x` 反斜杠前缀绕过（最终 URL 才解析）。
- f018（minor）**仍存在**：`useProfilesQuery.ts:241-259` 在 start 或轮询失败触发整条 mutation 重试时会先重放 stop 并重新等待 stopped，可能额外等待 120s 后报假失败。

### 本轮新发现

无。0 条。本轮生产代码变更仅为将 retry 谓词提取为 `client.ts:33-38` 供 `providers.tsx` 与测试复用；复核语义未变。

### AC 复验方式

- AC-001：`re_verified`。实跑 `./node_modules/.bin/tsc -b`（exit 0）、`NODE_OPTIONS=--no-experimental-webstorage npx vitest run`（20 files / 95 tests passed）、`npm run build`（含 `verify_frontend_dist.py`，通过）；`rg` 确认 v1 路径、`@dnd-kit`、`@novnc`、直接 `react-router` 零引用；`git ls-files '*tsbuildinfo'` 为空；i18n 150/150 键无死键。
- AC-002：`re_verified`。产物 `dist/assets/index-B3JXeF3D.css` 精确包含 `.bg-primary` 与 `.text-primary-foreground`；读码核实 `BrowserSessionPage.tsx:119-131` 启动错误条、`ProfileDetailPage.tsx:39-59` dirty 回填、`useProfilesQuery.ts:205-231` 连续 3 次失败容忍及 `polling failed`/`timeout` 文案、`sse.ts:161-179` 尾帧 flush。未运行 Playwright E2E（需要完整 Docker 拓扑），端到端路径未复验。
- AC-003：`re_verified`。`client.ts:202-312` 的 profile 与 artifact 写操作均透传调用方 key；`useProfilesQuery.ts`/`useArtifacts.ts` 在 mutation 层生成并复用（`useProfilesQuery.retry.test.tsx` 通过）；`providers.tsx:52-57` 消费 `ApiError.retryable`；`sse.ts:103-107` + `providers.tsx:13-21` 完成 401 停流与登出；`useProfilesQuery.ts:305-310` 启停对称。f007/f012/f017/f018 为残留 minor。
- AC-004：`re_verified`。`i18n.tsx:409-411` 同步 `documentElement.lang`，`i18n.tsx:382-395,413-417` 迁移/写入 `cbrowser.locale` 并读取旧 `cbm.locale`；`i18n.test.tsx` 通过；`git ls-files '*tsbuildinfo'` 为空；`npm ls` 仅 `react-router-dom@7.18.5` 与单实例 `react-router@7.18.5`；`tsconfig.json:12` 指向 `node_modules/.tmp`。
- coverage = 4 / 4

### 结论（Round 8）

- 前轮 finding 复核：f001/f016 已消除且保持；f002/f003/f004/f005/f006/f011 仍为已消除；f007/f008/f009/f010/f012/f013/f014/f015/f017/f018 仍为 minor。
- 本轮新发现：0 条。
- 未进表的提示：
  - 文件过大：`ProfileDetailPage.tsx` 436 行（本 task 净增约 14 行，超 400 建议阈值）、`i18n.tsx` 436 行（本 task 净减约 323 行，不满足「仍净增」条件）；`client.ts` 360、`useProfilesQuery.ts` 312、`sse.ts` 226 行未超阈值。
  - 复杂度：`client.ts request()` 与 `sse.ts connect()` 的 CC 仍 ≥15，对应既有 minor f010/f009；本轮未因复杂度新增可观测缺陷。
  - 交付卫生：`git status --short --untracked-files=all` 无未跟踪交付文件；本轮 scope 指纹与实时重算一致。
  - 范围外观察：未改后端/OpenAPI/browser-session；`docs/specs_index.md` 在 task finish 前登记 t017（流程时序问题，非内容错误）；`docs/blueprint/testing.md:160,166` 仍引用已移出版本库的 tsbuildinfo（f015）。
  - 未运行：Playwright E2E（需要完整 Docker 拓扑）。
- 总体判断：两个前轮 blocking（f001/f016）均已消除并保持，本轮无新的 critical/important，剩余均为已有 minor，本轮 PASS。
- 系统性 follow-up：无。

verdict: PASS
