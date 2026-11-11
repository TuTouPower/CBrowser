# Task review t017（reviewer_focus: 测试）

- task：`t017_v2_frontend_convergence`
- spec：`docs/tasks/t017_v2_frontend_convergence/task.md`
- diff_anchor：`5252f75ab2bd726f65f98dfa0a644c9a64d53fb2`
- target：`git -C '<repo>_t017' diff 5252f75ab2bd726f65f98dfa0a644c9a64d53fb2`
- round：1
- reviewed_at：2026-11-03T05:19:59+08:00

reviewed_scope: 856ee0423a032102

## Findings

### t017_test_f001 - AC-001 打勾但仅 v1 使用的 i18n 键未删除

- 严重度：important
- 锚点：AC-001（"仅 v1 使用的 i18n 键" 必须移除）
- 位置：`src/frontend/src/i18n.tsx:91-94,97-99,108`（中文同键 `:442-445,447-449,456`）
- 问题：锚点版本中这些键只被已删除的 v1 组件引用：`updateAvailable/download/dismissUpdate` → `components/UpdateBanner.tsx:21`；`dismissLaunchError` → `components/LaunchErrorBanner.tsx:34`；`tierPro/tierFree/tierKeyless` → `components/SystemStatusBadge.tsx:17`；`licenseKey/releaseChannel` → `components/SettingsPanel.tsx:96,127`。当前 `rg` 在 `i18n.tsx` 之外对这些键零命中，但英文与中文两套字典仍完整保留，且本 diff 的 `i18n.tsx` 只有新增、没有任何键删除。AC-001 的删除范围未完成，打勾不成立；也没有任何测试校验 i18n 键清理。
- 建议：从 `en`/`zh` 删除仅 v1 使用的键；补一个最小键引用扫描（或测试）防止残留。

### t017_test_f002 - AC-002 三项 UI/轮询行为无任何测试支撑

- 严重度：important
- 锚点：AC-002（会话启动失败显示错误；Profile 详情页后台刷新不覆盖未保存编辑；应用并重启容忍瞬时轮询失败）
- 位置：`src/frontend/src/features/profiles/BrowserSessionPage.tsx:119-131`、`src/frontend/src/features/profiles/ProfileDetailPage.tsx:37-59,123`、`src/frontend/src/features/profiles/useProfilesQuery.ts:168-195`
- 问题：全仓 vitest 测试没有任何文件引用 `BrowserSessionPage`、`ProfileDetailPage` 或 `useApplyDisplaySettingsMutation`（`src/frontend/src/**/*.test.*` 检索零命中）。现有 E2E 也不覆盖新行为：`tests/e2e/test_frontend_display_apply_e2e.py` 只走 apply 成功路径，`tests/e2e/test_frontend_app_e2e.py:335-345` 只做正常保存，均不制造轮询瞬时失败、不验证后台刷新与脏字段保护、不验证启动失败错误条。三条 AC 打勾只有实现代码，没有可信的自动化证据。
- 建议：分别补测试：1) `setDesiredState` reject 时断言 `session-start-error` 可见且包含错误文本；2) rerender 新的 `profile` 数据，断言已修改字段保持用户值、未修改字段跟随刷新；3) 用 fake timers 让 `getRuntime` 连续 1-2 次 reject 后成功，断言最终收敛；连续 3 次失败断言 `Runtime polling failed`，超时断言 `did not converge before timeout`，以证明两种错误可区分。

### t017_test_f003 - SSE 尾帧与 401 登出无测试，且 401 登出未接线

- 严重度：important
- 锚点：AC-002（SSE 流结束最后一个事件不丢失）、AC-003（SSE 遇 401 停止重连并触发登出）
- 位置：`src/frontend/src/shared/api/sse.ts:99-103,157-175`、`src/frontend/src/shared/api/sse.test.ts`（本 diff 未改动）、`src/frontend/src/shared/api/sse.ts:221`、`src/frontend/src/app/providers.tsx:38`
- 问题：`sse.test.ts` 仍只有"完整 `\n\n` 帧 + 断连重连"用例，未覆盖本 task 新增的流结束 flush 与 401 分支。更严重的是生产侧 `onUnauthorized` 从未注入：`defaultSseClient = new ProfileEventsClient()` 没有回调，`providers.tsx` 也未调用任何 setter，因此 401 只会 `stop()`，不会触发登出。两条 AC 打勾均无有效测试，且"触发登出"实际未实现。
- 建议：在 `sse.test.ts` 用真实 `node:http` 服务器补两例：1) 写入 `id:`/`data:` 后直接 `res.end()`（不写结尾空行），断言最后一个事件被派发；2) 返回 401，注入 `onUnauthorized` spy，断言回调一次且重连计数不再增长。生产侧把 SSE 客户端与 `ApiClient` 共用同一登出回调。

### t017_test_f004 - AC-003 幂等键"生成并在重试中复用"无实现、无测试

- 严重度：important
- 锚点：AC-003（写操作由用户动作生成幂等键并在重试中复用）
- 位置：`src/frontend/src/shared/api/client.ts:232-264`
- 问题：现状只在 `duplicate`/`reset` 每次调用时各生成一个新 UUID（`:242-247`、`:257-261`），没有重试层，也无法在重试中复用同一 key；`rg "Idempotency-Key" src/frontend/src --glob '*.test.*'` 零命中。AC 打勾无测试甚至无"复用"实现依据。
- 建议：在用户动作（mutation 提交）时生成一次幂等键并由重试复用，而不是每次发请求重新生成；补 `node:http` 测试断言首次与重试请求头中的 key 相同。

### t017_test_f005 - AC-003 超时分级、字段详情与"据此决定重试"覆盖不足，且存在恒真式断言

- 严重度：important
- 锚点：AC-003（每类请求超时策略；错误对象携带错误码/可重试标志/字段详情并据此决定重试；只向同源发送凭据与 CSRF）
- 位置：`src/frontend/src/shared/api/client.test.ts:147-192`、`src/frontend/src/shared/api/client.ts:74-82,102-167,229,286`
- 问题：
  1. 超时测试同时构造 `defaultTimeoutMs: 10` 并显式传 `10`（`client.test.ts:160-168`），只能证明默认超时路径；`uploadTimeoutMs`/`longOperationTimeoutMs` 被 `upload`/`stop` 使用（`client.ts:229,286`）完全未测。
  2. `retryable` 断言在 503 上恒真：实现为 `Boolean(payload?.retryable) || response.status === 503`（`client.ts:165`），测试 payload 本身也是 503；即使实现完全忽略 `payload.retryable`，断言仍通过，无法证明"由服务端可重试标志决定"。
  3. 未断言 `ApiError.detail`（AC 的"字段详情"），也未测试任何"据此决定重试"；生产代码中 `retryable`/`errorCode` 无消费者，`providers.tsx:47` 的 `queries.retry: 1` 是无差别重试。
  4. 同源测试只断言 `status: 0`（`client.test.ts:149-151`），未断言 `fetch` 未被调用；并且 `client.ts:74-82` 只检查绝对 endpoint，跨源 `baseUrl` 仍会带 `credentials: include` 与 CSRF 头，此路径未测。
- 建议：用 500 + `retryable: true/false` 两例验证不是状态码兜底；断言 `detail`；给 upload/stop 注入极小超时验证使用 `uploadTimeoutMs`/`longOperationTimeoutMs`；对跨源 baseUrl 明确拒绝或禁止该配置并补测试。

### t017_test_f006 - AC-004 语言切换未测：i18n 测试从未触发 setLocale

- 严重度：important
- 锚点：AC-004（切换语言同步更新文档语言属性）
- 位置：`src/frontend/src/i18n.test.tsx:20-31`
- 问题：用例只预置旧 `cbm.locale` 并渲染 Provider，验证初始检测后 `documentElement.lang` 被设置；`Probe` 的切换按钮虽然定义了 `onClick={() => setLocale("zh")}`，但测试从未点击，`setLocale` 一次都没调用。因此"切换语言同步更新文档语言属性"没有任何覆盖，测试只证明了初次挂载的 effect。
- 建议：点击切换到 `en`/`zh`，断言 `document.documentElement.lang` 随 locale 更新，并断言 `cbrowser.locale` 写入与旧键清理。

### t017_test_f007 - 事件同步 hook 的 stop 无直接断言

- 严重度：minor
- 锚点：AC-003（事件同步 hook 启停对称）
- 位置：`src/frontend/src/features/profiles/useProfilesQuery.ts:262-265`、`src/frontend/src/features/profiles/useProfilesQuery.test.tsx`
- 问题：新增的 `sseClient.stop()` 没有测试。`auth_guard.test.tsx` 对 `sseClient.stop` 的断言由 `providers.tsx:12-16` 既有 cleanup 即可满足，即使删掉 hook 内新增的 stop 也会通过，无法证明本 hook 启停对称。
- 建议：在 `useProfilesQuery.test.tsx` 增加 renderHook 卸载用例，断言 `stop` 调用一次；重渲染断言不重复 `start`。

### t017_test_f008 - 构建 CSS 门禁用子串匹配，可能假绿

- 严重度：minor
- 锚点：AC-002（构建后校验关键类存在于产物 CSS）
- 位置：`scripts/verify_frontend_dist.py:57-63`
- 问题：`if utility not in css_text` 是子串断言，`.bg-primary-foreground` 的出现就能让 `.bg-primary` 通过；转义类名、前缀类名同样无法区分。当前 dist 确实精确包含这两个类（本轮重跑 build 后用 `rg` 核对），但门禁在将来缺少目标类时可能仍然通过。
- 建议：改用选择器边界匹配（如 `\.bg-primary(?![-\w])`）或解析 CSS 选择器列表后做精确集合判断。

### t017_test_f009 - 新增 i18n.test.tsx 未进入 diff，交付状态不完整

- 严重度：minor
- 锚点：行为缺陷（交付状态）+ AC-004
- 位置：`src/frontend/src/i18n.test.tsx`（`git status --short` 显示 `??`）
- 问题：该新测试文件未执行 `git add -N`，`git diff 5252f75...` 中不可见；本次审查通过工作区直接读取且 `reviewed_scope` 指纹已覆盖，但如果实施 commit 使用 `git add -u` 会漏掉 AC-004 目前唯一的测试文件。按派审规范，新交付文件必须出现在 reviewer 的 diff 中。
- 建议：`git add -N src/frontend/src/i18n.test.tsx` 后再派审，或确认实施 commit 已包含该文件。

## 结论

- 前轮 finding 复核：Round 1，无前轮 finding。
- 改测方向复核：无"迁就实现"的改测。`shared/api/client.test.ts` 仅追加用例，既有断言未改；删除的 4 个 v1 测试文件属于 AC-001 明确要求的 v1 树删除，删除本身合法。但 v1 `ProfileForm.test.tsx` 删除后，v2 `ProfileNewPage`/`ProfileDetailPage` 没有等价表单测试，覆盖存在净损失（提示项，不阻断）。
- 本轮新发现：9 条（6 important、3 minor）。
- 未进表的提示：
  - 本轮实跑 `npx tsc -b`（exit 0）、`NODE_OPTIONS=--no-experimental-webstorage npm test --prefix src/frontend`（14 files / 81 tests passed）、`npm run build --prefix src/frontend`（含 postbuild 的 CSS 校验）均通过；`npm ls react-router react-router-dom` 只有单实例；`git ls-files '*tsbuildinfo'` 为空。
  - 现有 Playwright E2E（`tests/e2e/test_frontend_*_e2e.py`）需要完整 Docker 拓扑，本次未运行，且不覆盖 f002/f003 的新行为，不能作为 AC-002/AC-003 的证据。
  - `i18n.test.tsx` 未跟踪导致 diff 不可见；虽已读取并纳入指纹，建议合并前确认入库。
- 总体判断：AC-001/002/003/004 全部打勾，但 AC-001 有未删除键、AC-002 三项行为零测试、AC-003 幂等/401 登出/重试策略无实现或测试、AC-004 切换语言无测试，且新增 i18n 测试未进入 diff，交付状态 INCOMPLETE，本轮 FAIL。

### AC 复验方式

- AC-001：`re_verified`。实跑 `tsc -b`、vitest（81 passed）、生产构建与 `verify_frontend_dist.py` 均通过，`rg` 确认 v1 路径零引用；但仅 v1 使用的 i18n 键仍在 `i18n.tsx`（f001），AC 不成立。
- AC-002：`trust_prior`。色板类已通过重跑 build + `rg` 独立验证；会话启动错误、详情页脏字段、轮询瞬时失败三项无任何测试或 E2E 证据，只能读代码，无法独立复验。
- AC-003：`trust_prior`。默认超时、同源绝对 URL、错误码有测试；幂等键、SSE 401 登出、按 retryable 决定重试、hook 启停对称无测试或未实现（f003-f007）。
- AC-004：`re_verified`。`npm ls` 确认路由单实例、`git ls-files` 确认 tsbuildinfo 未入库、i18n 存储迁移测试实跑通过；"切换语言"分支未被测试直接验证（f006）。
- coverage = 2 / 4（建议合并前人工抽查 trust_prior 项）。

verdict: FAIL

## Round 2 (2026-11-03T05:33:28+08:00)

- round：2
- reviewed_at：2026-11-03T05:33:28+08:00
- reviewed_scope: 6ba2328dbd02bee6

### 前轮 finding 复核

- **t017_test_f001 - 仍存在（修不彻底）**：Round 1 点名的 `updateAvailable`/`dismissUpdate`/`dismissLaunchError`/`tier*`/`licenseKey`/`releaseChannel` 已删除；但按同一判据全量扫描，仍有 18 个仅被已删除 v1 文件引用、当前无任何 `t("...")` 使用的键留在 `en`/`zh` 两套字典：`retry`、`close`、`add`、`test`、`proxy`、`stopping`、`download`、`timezone`、`locale`、`width`、`height`、`tags`、`extensions`、`notes`、`connected`、`connecting`、`fullscreen`、`send`（`src/frontend/src/i18n.tsx:20,26,27,29,52,56,66,97-105,107,108`；中文 `:221,227,228,230,250,253,262,290-298,300,301`）。锚点版本中这些键 `t()` 调用只出现在 `App.tsx`/`components/*`/`hooks/useProfiles*`；当前树无 `t("<key>")` 命中。AC-001 仍未完成，且没有测试防回归。
- **t017_test_f002 - 仍存在**：本 diff 仍无 `BrowserSessionPage`、`ProfileDetailPage` 或 `useApplyDisplaySettingsMutation` 的测试；`tests/e2e/test_frontend_display_apply_e2e.py` 只覆盖 apply 成功路径。`session-start-error`（`BrowserSessionPage.tsx:121`）、dirty 字段保护（`ProfileDetailPage.tsx:37-64,364-417`）、轮询瞬时失败/超时区分（`useProfilesQuery.ts:174-194`）均无自动化证据。AC-002 三条行为仍不可信。
- **t017_test_f003 - 已消除（以工作区为准）**：新增 `sse_hardening.test.ts` 用真实 `node:http` 覆盖尾帧 flush 与 401（`stop` 后不再重连，`connections===1`）；`providers.tsx:13-21` 已把 `setOnUnauthorized` 接到 `logout`。原 finding 的两个缺口（无测试、未接线）均已补。残留：该测试文件未入 diff（见 f010）；`auth_guard.test.tsx` 的 fake SSE 未实现 `setOnUnauthorized`，SSE 401→实际登出的集成路径仍无测试（列为本轮提示，不另立 finding）。
- **t017_test_f004 - 已消除**：`client.ts:104-119,147` 按 method+URL+body 指纹复用幂等键，成功后删除；`client.test.ts:195-224` 用 fetch stub 验证失败后复用、成功后轮换；若实现不写 key 或每次换 key，测试会失败。测试触达生产逻辑，断言可观察请求头。
- **t017_test_f005 - 修不彻底（仍 important）**：新增用例证明 `errorCode` 与越权绝对 URL 拒绝，但：
  - `client.test.ts:174-192` 在 503 响应上断言 `retryable: true`；实现 `client.ts:188` 对任何 503 都返回 true，无法证明 payload 的 `retryable` 标志被采用，仍属弱断言/近恒真。需用 500 + `retryable: true/false` 两例。
  - 仍未断言 `ApiError.detail`（`client.ts:189`）；该用例的响应 payload 也未带 `detail`。
  - `uploadTimeoutMs`/`longOperationTimeoutMs`（`client.ts:252,297`）无测试；超时用例显式传 10（`client.test.ts:165`），只证明显式超时，不证明默认/分级配置。
  - "据此决定重试"（`providers.tsx:52-62`）无测试；`//host` 分支（`client.ts:78-82`）与跨源 `baseUrl` 仍会携带 `credentials: include`（`client.ts:89`）也未覆盖。
- **t017_test_f006 - 仍存在**：`i18n.test.tsx:20-31` 仍只验证初次挂载 + 旧键迁移；`Probe` 的 `setLocale("zh")` 按钮从未点击，`setLocale`→`document.documentElement.lang` 更新与写入新键无覆盖。AC-004 的"切换语言"仍无测试。
- **t017_test_f007 - 仍存在（minor）**：`useProfilesQuery.test.tsx` 未断言 `useProfileEventsSync` 卸载时调用 `sseClient.stop()`；fake SSE 未统计 stop，`auth_guard.test.tsx` 的 stop 断言由 provider cleanup 即可满足。
- **t017_test_f008 - 仍存在（minor）**：`scripts/verify_frontend_dist.py:57-66` 仍是子串匹配（`if utility not in css_text`），`.bg-primary-foreground` 或前缀类可让 `.bg-primary` 误通过；未改。
- **t017_test_f009 - 仍存在（minor，并入 f010）**：`i18n.test.tsx` 仍为 `??`；本轮新增 `sse_hardening.test.ts` 也是 `??`。见 f010。

### 本轮新发现

#### t017_test_f010 - 新增测试文件未 git add -N，AC-002/003/004 的测试证据不在 diff 中

- 严重度：important
- 锚点：AC-002（SSE 流结束尾帧）、AC-003（SSE 401 登出）、AC-004（切换语言/迁移）；交付状态
- 位置：`src/frontend/src/shared/api/sse_hardening.test.ts`、`src/frontend/src/i18n.test.tsx`（`git status --short` 均为 `??`）
- 问题：`git diff 5252f75...` 不包含这两个文件。`sse_hardening.test.ts` 是 AC-002 尾帧和 AC-003 401 目前唯一测试；`i18n.test.tsx` 是 AC-004 目前唯一测试。任务流程要求在派审前对明确的新交付文件执行 `git add -N`，使新文件进入 reviewer 可见的 diff；当前 Vitest 84 通过包含这两个未跟踪文件，若实施 commit 以 `git add -u` 形成会整段丢失测试证据，交付状态 INCOMPLETE。
- 建议：下次派审前执行 `git add -N -- src/frontend/src/i18n.test.tsx src/frontend/src/shared/api/sse_hardening.test.ts`，并确认实施 commit 包含这两个文件。

### 结论（Round 2）

- 前轮 finding 复核：f001 修不彻底；f002/f005/f006 仍存在；f003/f004 已消除；f007/f008/f009 为 minor 仍存在（f009 并入 f010）。
- 改测方向复核：无"迁就实现"的改测。`client.test.ts` 仅追加用例，既有断言未改；删除的 4 个 v1 测试文件属于 AC-001 明确要求的 v1 树删除，删除合法；但 v1 `ProfileForm.test.tsx` 删除后 v2 表单页无等价表单测试，属覆盖净损失（提示，不阻断）。
- 本轮新发现：1 条（f010 important）。
- 未进表的提示：
  - 实跑 `npx tsc -b` exit 0；`NODE_OPTIONS=--no-experimental-webstorage npm test --prefix src/frontend` 15 files / 84 tests passed；`npm run build`（含 `verify_frontend_dist.py`）通过；`npm ls react-router react-router-dom` 单实例；`git ls-files '*tsbuildinfo'` 为空；`dist/assets/*.css` 精确包含 `.bg-primary` 与 `.text-primary-foreground`。
  - E2E（Docker 拓扑）未运行；t018 已登记测试体系/交付门禁整改，可在该 task 处理 E2E 基础设施。
  - `sse_hardening.test.ts` 使用 50/100ms 固定 sleep；连续 3 次单跑稳定，建议后续改事件/条件等待以降低时序敏感（非本轮阻断）。
  - SSE 401→logout 的集成路径未测（`auth_guard.test.tsx` 的 fake SSE 无 `setOnUnauthorized`），当前只有 client 回调单测 + `providers.tsx` 代码阅读；可选补测，不另立 finding。
- AC 复验方式：
  - AC-001：`re_verified`。实跑 tsc/vitest/build，`rg` 确认 v1 路径零引用；但 18 个 v1-only i18n 键仍在 `i18n.tsx`（f001），AC 不成立。
  - AC-002：`trust_prior`。色板门禁 re_verified（build + `rg` CSS 类）；会话启动错误、详情页 dirty 保护、轮询瞬时失败三项无测试，只能读代码（f002）。
  - AC-003：`trust_prior`。幂等、SSE 401、尾帧测试已实跑通过；超时分级、`retryable` 标志、`detail`、按 `retryable` 决定重试、`//host`/跨源 baseUrl 无测试（f005）。
  - AC-004：`re_verified`。路由单实例、tsbuildinfo 未入库、i18n 迁移测试实跑通过；切换语言分支无测试（f006）。
  - coverage = 2 / 4（建议合并前人工抽查 trust_prior 项）。
- 总体判断：AC-001/002/003/004 仍有多条打勾缺少有效测试或实现未完全满足；f001、f002、f005、f006、f010 未解决，本轮 FAIL。
- 系统性 follow-up：已有 t018（测试体系、交付门禁与仓库卫生整改），本轮不新增。

verdict: FAIL

## Round 3 (2026-11-03T05:43:45+08:00)

- round：3
- reviewed_at：2026-11-03T05:43:45+08:00
reviewed_scope: 62cb5b0d1664be92

### 前轮 finding 复核

- **t017_test_f001 - 仍存在（important）**：AC-001 的“仅 v1 使用的 i18n 键”仍未清理完。当前 `src/frontend/src/i18n.tsx` 仍保留 17 个键：en `:20,26,27,29,52,56,66,97-107`（`retry`/`close`/`add`/`test`/`proxy`/`stopping`/`download`/`timezone`/`locale`/`width`/`height`/`tags`/`notes`/`connected`/`connecting`/`fullscreen`/`send`），zh `:220,226,227,229,249,252,261,289-299`。锚点版本 `git grep` 显示这些键的 `t()` 调用只出现在已删除的 `App.tsx`/`components/*`/`hooks/useProfiles*`；当前树（含测试）对这些键零 `t()` 引用。AC-001 打勾不成立，也没有键清理回归测试。
- **t017_test_f002 - 部分修复，仍存在（important）**：本轮新增 `BrowserSessionPage.test.tsx:34-45`（isError 时显示 `session-start-error`）与 `useProfilesQuery.wait.test.ts:22-32`（两次瞬时失败后收敛），会话错误与瞬时失败两项已有自动化证据。但：1）“Profile 详情页后台刷新不覆盖未保存编辑”仍零测试，`rg 'dirty|profile-name-input' src/frontend --glob '*.test.*'` 只命中生产代码，`ProfileDetailPage.tsx:37-64,364-417` 的 dirty 逻辑无测试，`tests/e2e/*` 也无对应场景；2）`useProfilesQuery.wait.test.ts:34-40` 名为 “distinguishes ... from timeout”，实际只断言 `/polling failed/`，超时分支（`useProfilesQuery.ts:194` 的 `did not converge before timeout`）无断言，“错误信息区分轮询失败与超时”只测到一半；3）该测试直接调用导出的内部函数，未覆盖 `useApplyDisplaySettingsMutation` 把错误传到 UI 的链路。
- **t017_test_f003 - 已消除**：`sse_hardening.test.ts:19-40` 用真实 `node:http` 验证 401 只连接一次且回调一次；`:42-63` 验证无尾空行的最后事件被派发；`providers.tsx:13-21` 将 `setOnUnauthorized` 接到 logout。本轮复跑通过。
- **t017_test_f004 - 已消除**：`client.test.ts:195-225` 断言失败后复用、成功后轮换；生产实现 `client.ts:104-119,147`。本轮复跑通过。
- **t017_test_f005 - 仍存在（important）**：`client.test.ts:154-172` 仍同时构造 `defaultTimeoutMs: 10` 并显式传 `10`，只证明显式超时；`uploadTimeoutMs`/`longOperationTimeoutMs`（`client.ts:252,297`）无测试。`:174-193` 在 503 上断言 `retryable: true`，实现 `client.ts:193` 对任何 503 都返回 true，payload 的 `retryable` 被忽略也能通过；且未断言 `ApiError.detail`（该 payload 无 `detail`）。`providers.tsx:52-66` 的“据此决定重试”无测试；`//host` 分支（`client.ts:78-82`）与跨源 `baseUrl` 凭据仍未覆盖。
- **t017_test_f006 - 仍存在（important）**：`i18n.test.tsx:31-32` 点击的是 `setLocale("zh")`，而 `:21` 已把 locale 预置为 zh；点击前后 locale 无变化，`documentElement.lang` 仍为 zh，断言不依赖点击。把 `setLocale` 改成空实现测试仍会通过；AC-004 的“切换语言同步更新文档语言属性”仍未被验证，点击后的 localStorage 写入也未断言。
- **t017_test_f007 - 仍存在（minor）**：`useProfilesQuery.test.tsx` 的 fake SSE 仍无 stop 计数；`useProfilesQuery.ts:262-265` 新增的 cleanup `sseClient.stop()` 无断言。
- **t017_test_f008 - 仍存在（minor）**：`scripts/verify_frontend_dist.py:62-64` 仍是 `utility not in css_text` 子串匹配；`.bg-primary-foreground` 或前缀类可让 `.bg-primary` 误通过。
- **t017_test_f009 - 已消除（并入 f010）**：`i18n.test.tsx` 已出现在 diff。
- **t017_test_f010 - 已消除**：`git status --short` 无 `??`；`BrowserSessionPage.test.tsx`、`useProfilesQuery.wait.test.ts`、`i18n.test.tsx`、`sse_hardening.test.ts` 均以 new file 出现在 diff。

### 本轮新发现

无新增 finding。新测试的残余问题已归入 f002/f005/f006。

### 结论（Round 3）

- 前轮 finding 复核：f001/f002/f005/f006 仍存在（important）；f007/f008 仍存在（minor）；f003/f004/f009/f010 已消除。
- 改测方向复核：无“迁就实现”的改测。`client.test.ts` 只追加用例，既有断言未改；删除的 4 个 v1 测试文件属于 AC-001 明确要求，删除合法。v1 `ProfileForm.test.tsx` 删除后 v2 表单的 dirty/save 行为无等价测试（已计入 f002）。
- 本轮新发现：0 条。
- 未进表的提示：
  - 实跑 `npx tsc -b` exit 0；`NODE_OPTIONS=--no-experimental-webstorage npm test --prefix src/frontend` 17 files / 87 tests passed（新测试单跑 3 次未复现 flake）；`npm run build` 含 `verify_frontend_dist.py` 通过；`npm ls react-router react-router-dom` 单实例；`git ls-files '*tsbuildinfo'` 为空；`dist/assets/*.css` 精确包含 `.bg-primary` 与 `.text-primary-foreground`。
  - `BrowserSessionPage.test.tsx` 整体 mock 了 `useProfilesQuery`，只验证 isError 分支渲染；未覆盖 mutate reject→isError 链路（组件级测试可接受，仅提示）。
  - `useProfilesQuery.wait.test.ts` 直接测试导出的内部函数并 mock 了 `ApiClient`，未覆盖 hook/UI 集成；属测试层级选择，非 blocking。
  - SSE 401→logout 的集成路径仍未测（`auth_guard.test.tsx:46-63` 的 fake SSE 无 `setOnUnauthorized`），当前只有 client 单测 + `providers.tsx:13-21` 代码阅读。
  - `sse_hardening.test.ts:36,61` 使用 100/50ms 固定等待；连续 3 次单跑稳定，仍是时序敏感点。
  - E2E（Docker 拓扑）未运行；现有 E2E 不覆盖 dirty 保护、轮询瞬时失败和会话启动失败。
  - `tsconfig.json` 排除 `*.test.ts(x)`，测试文件不参与 `tsc` 类型检查；属测试基础设施缺口，可并入 t018。
- AC 复验方式：
  - AC-001：`re_verified`。实跑 tsc/vitest/build，`rg` 确认 v1 路径零引用、依赖移除；但 17 个 v1-only i18n 键仍在（f001），AC 不成立。
  - AC-002：`trust_prior`。色板门禁与 SSE 尾帧已独立复验；dirty 保护和轮询超时分支无测试，只能读代码。
  - AC-003：`trust_prior`。幂等、绝对 URL 拒绝、401 单测已复跑通过；超时分级、`retryable` 语义、`detail`、按 retryable 重试无测试（f005）。
  - AC-004：`trust_prior`。i18n 迁移测试通过、路由单实例、tsbuildinfo 未入库已复验；切换语言分支无测试（f006）。
  - coverage = 1 / 4（建议合并前人工抽查 trust_prior 项）。
- 总体判断：f001、f002、f005、f006 四条 important 仍未解决，AC 打勾缺少有效测试，本轮 FAIL。
- 系统性 follow-up：已有 t018（测试体系、交付门禁与仓库卫生整改），本轮不新增。

verdict: FAIL

## Round 4 (2026-11-03T06:01:44+08:00)

- round：4
- reviewed_at：2026-11-03T06:01:44+08:00
reviewed_scope: 992830d2f2e3f44e

### 前轮 finding 复核

- **t017_test_f001 - 仍存在（important）**：Round 3 点名的 17 个 v1-only 键已删 11 个，但 `src/frontend/src/i18n.tsx` 仍保留 6 个（en/zh 双份）：`close`(`:25,211`)、`proxy`(`:47,231`)、`stopping`(`:51,234`)、`download`(`:61,243`)、`tags`(`:92,271`)、`connected`(`:93,272`)。锚点版本中这些键的 `t()` 引用只在已删除的 `ProfileFiles.tsx`、`SettingsPanel.tsx`、`ProfileForm.tsx`、`ProfileList.tsx`、`LaunchButton.tsx`、`UpdateBanner.tsx`、`ProfileViewer.tsx`；当前 `src/frontend/src` 对这些键零 `t()` 引用（`rg` 已复核）。AC-001 的「仅 v1 使用的 i18n 键全部移除」仍不成立，也没有键清理回归测试。
- **t017_test_f002 - 部分消除，仍存在（important）**：新增测试已覆盖会话启动错误（`BrowserSessionPage.test.tsx:33-45`）、dirty 字段保留（`ProfileDetailPage.test.tsx:33-54`）和轮询瞬时失败后收敛（`useProfilesQuery.wait.test.ts:22-31`）。但 AC-002 的「错误信息区分轮询失败与超时」仍只测到一半：`useProfilesQuery.wait.test.ts:34-40` 的用例名声称区分 timeout，实际只断言 `/polling failed/`；`useProfilesQuery.ts:231` 的 `did not converge before timeout` 分支零断言，超时文案被改成与轮询失败相同也不会失败。该测试还只直接调用导出的 `waitForRuntimeState`，没有覆盖 apply mutation → UI 错误链路。
- **t017_test_f003 - 已消除**：`sse_hardening.test.ts:19-40,42-63` 仍用真实 `node:http` 验证 401 单次连接/回调与无尾空行的最后事件；`providers.tsx:13-21` 的 `setOnUnauthorized` 仍接到 logout。本轮复跑通过。
- **t017_test_f004 - 回归/修不彻底（important）**：Round 3 所依据的「失败后复用、成功后轮换」幂等测试已不在当前 worktree。当前唯一幂等测试 `client.test.ts:195-213` 只是连续两次 **成功** 调用 `create` 并显式传入同一个 `"action-key-1"`，断言请求头透传；它没有制造失败或重试，也没有调用 `useCreateProfileMutation`，无法证明「用户动作生成 key」或「重试复用同一 key」。若 mutation hook 每次尝试重新 `newIdempotencyKey()`，该测试仍全绿。见 f011 的具体后果。
- **t017_test_f005 - 仍存在（important）**：`client.test.ts:174-192` 仍在 503 响应上断言 `retryable: true`，而实现 `client.ts:171` 对任何 503 都返回 true，payload 的 `retryable` 被忽略也能通过；该用例名含 "detail" 但 payload 无 `detail`，也未断言 `ApiError.detail`。`client.ts:252,297` 的 `uploadTimeoutMs`/`longOperationTimeoutMs` 仍无测试；`client.test.ts:160-165` 同时配置 `defaultTimeoutMs: 10` 并显式传 `10`，只证明显式超时。`providers.tsx:52-63` 新增的「按 `retryable` 决定 query/mutation 重试」零测试；`//host` 分支与跨源 `baseUrl` 仍无测试。
- **t017_test_f006 - 仍存在（important）**：`i18n.test.tsx:21` 预置 `cbm.locale=zh`，`:31-32` 点击 `setLocale("zh")`。点击前后 locale 都是 zh、`documentElement.lang` 都是 zh，断言不依赖点击；把 `setLocale` 改成空实现测试仍通过。AC-004 的「切换语言同步更新文档语言属性」仍未验证，点击后的 `cbrowser.locale` 写入也未断言。
- **t017_test_f007 - 仍存在（minor）**：`useProfilesQuery.ts:304-307` 新增的 cleanup `sseClient.stop()` 仍无测试；`useProfilesQuery.test.tsx` 的 fake SSE 未统计 stop，`auth_guard.test.tsx` 的 stop 断言可由 provider cleanup 满足。
- **t017_test_f008 - 仍存在（minor）**：`scripts/verify_frontend_dist.py:62-64` 仍是 `utility not in css_text` 子串匹配；`.bg-primary-foreground` 或前缀类可让 `.bg-primary` 误通过。
- **t017_test_f009 - 已消除**：`i18n.test.tsx` 已进入 diff。
- **t017_test_f010 - 已消除**：`git status --short` 无 `??`，本轮新测试均以 new file 出现在 diff。

### 本轮新发现

#### t017_test_f011 - 幂等测试未覆盖 apply 两写路径；同一 key 写不同 payload 会触发后端 idempotency conflict

- 严重度：important
- 锚点：AC-003（写操作由用户动作生成幂等键并在重试中复用）、AC-002（应用并重启）
- 位置：`src/frontend/src/features/profiles/useProfilesQuery.ts:241-250`、`src/frontend/src/shared/api/client.test.ts:195-213`、`src/backend/cbrowser/adapters/database/repository.py:627-645`
- 问题：`useApplyDisplaySettingsMutation` 对整个用户动作只生成一个 `key`，先 `client.profiles.stop(id, key)`（`:242`），再 `client.profiles.setDesiredState(id, "running", key)`（`:249`）。后端两处都落到 `set_desired_state`，`sig_hash` 包含 `desired_state`（`repository.py:627-629`）；stop 先写入 `AuditEventModel`，第二次 running 复用同一 operation id 但 `sig_hash` 不同，`repository.py:638-643` 抛 `IdempotencyConflictError`，API 返回 409 `idempotency_conflict`。现有 `test_frontend_display_apply_e2e.py:239-245` 走真实 stop+start，按当前代码会在第二次写请求失败；该 E2E 本轮未运行，新增单测也没有覆盖 stop→desired-state 的 key 生命周期，因此这条回归没有被任何已执行测试拦住。
- 建议：补一个真实 HTTP 幂等语义测试：stop 与 setDesiredState 依次请求，断言两个写操作都成功，并在失败重试时各自复用同一 key；实现侧不要跨不同 payload 复用同一 operation id（stop 与 running 使用不同 key，或在两次写之间轮换 key），否则「应用并重启」会稳定失败。

#### t017_test_f012 - dirty 测试只验证编辑字段保留，未验证未编辑字段仍跟随后台刷新

- 严重度：minor
- 锚点：AC-002（Profile 详情页后台刷新不覆盖用户未保存的编辑）
- 位置：`src/frontend/src/features/profiles/ProfileDetailPage.test.tsx:33-54`
- 问题：用例只编辑 name 并断言 name 未被刷新覆盖；如果实现改成「一旦用户编辑任意字段就冻结整个表单、不再接受任何后台刷新」，该测试仍通过。当前生产实现按字段 dirty 回填，但测试无法区分这两种行为；proxy/geometry/tags 的 dirty 回填也没有覆盖。
- 建议：同一轮 rerender 同时修改 profile 的 name、proxy 与尺寸，断言 name 保留用户值、未编辑字段取新值；至少再覆盖一个非 name 的 dirty 字段。

### 结论（Round 4）

- 前轮 finding 复核：f001/f002/f004/f005/f006 仍存在（important）；f007/f008 仍存在（minor）；f003/f009/f010 已消除。f004 是 Round 3 结论依据失效后的回归/弱化，不是单纯覆盖扩展。
- 改测方向复核：无「迁就实现」的既有断言改写；v1 测试删除属于 AC-001 合法删除。新的幂等测试用两次成功调用冒充重试（f004/f011），属于新增测试的弱化设计，不是既有断言改写。
- 本轮新发现：2 条（f011 important、f012 minor）。
- 未进表的提示：
  - 本轮实跑 `npx tsc -b` exit 0；`NODE_OPTIONS=--no-experimental-webstorage npx vitest run` 18 files / 88 tests passed；`npm run build`（含 `verify_frontend_dist.py`）通过；`dist/assets/*.css` 精确包含 `.bg-primary` 与 `.text-primary-foreground`；`npm ls react-router react-router-dom` 单实例；`git ls-files '*tsbuildinfo'` 为空。新测试单跑 3 次未复现 flake。
  - E2E（Docker 拓扑）未运行；`test_frontend_display_apply_e2e.py:239-245` 是 f011 的现有高层证据，合并前应实跑，否则 AC-002「应用并重启」仍无通过证据。
  - `tsconfig.json` 仍排除 `*.test.ts(x)`，测试文件不参与 `tsc` 类型检查；属测试基础设施缺口，可并入 t018。
  - SSE 401→logout 的集成路径仍未测（`auth_guard.test.tsx` 的 fake SSE 无 `setOnUnauthorized`），当前只有 client 单测 + `providers.tsx:13-21` 代码阅读。
  - `sse_hardening.test.ts:36,61` 使用 100/50ms 固定 sleep；单跑 3 次稳定，仍是时序敏感点。
  - v1 `ProfileForm.test.tsx` 删除后，v2 详情页的保存/校验行为没有等价表单测试（dirty 测试只覆盖回填），属覆盖净损失提示，不阻断。
- AC 复验方式：
  - AC-001：`re_verified`。实跑 tsc/vitest/build，`rg` 确认 v1 路径零引用；但 6 个 v1-only i18n 键仍在（f001），AC 不成立。
  - AC-002：`trust_prior`。色板门禁与 SSE 尾帧已独立复验；dirty/session/transient 有新测试但超时分支无断言，且 f011 的 apply 两写路径按代码分析会 409，E2E 未运行，不能给出通过证据。
  - AC-003：`trust_prior`。幂等测试只验证 header 透传（f004/f011）；`retryable`、`detail`、超时分级、按 retryable 重试与跨源路径无测试（f005）。
  - AC-004：`trust_prior`。路由单实例、tsbuildinfo 未入库、i18n 迁移测试已复验；但切换语言分支仍是 no-op 测试（f006）。
  - coverage = 1 / 4（建议合并前人工抽查 trust_prior 项）。
- 总体判断：f001、f002、f004、f005、f006、f011 六条 important 未解决；其中新增幂等测试既未覆盖重试，也未覆盖会触发 409 的 apply 两写路径，本轮 FAIL。
- 系统性 follow-up：已有 t018（测试体系、交付门禁与仓库卫生整改）；f011 的幂等语义属本 task 必须修复项，不转 follow-up。

verdict: FAIL

## Round 5 (2026-11-03T06:12:00+08:00)

- round：5
- reviewed_at：2026-11-03T06:12:00+08:00
reviewed_scope: 17cd958032ee86b9

### 前轮 finding 复核

- **t017_test_f001 - 仍存在（important）**：6 个 v1-only 键仍在 `src/frontend/src/i18n.tsx:25,47,51,61,92,93`（en）与 `:211,231,234,243,271,272`（zh）：`close`/`proxy`/`stopping`/`download`/`tags`/`connected`。锚点版本 `git grep 't("...")'` 显示这些键仅由已删除的 `ProfileFiles.tsx`/`SettingsPanel.tsx`/`ProfileForm.tsx`/`ProfileList.tsx`/`LaunchButton.tsx`/`UpdateBanner.tsx`/`ProfileViewer.tsx` 引用；当前 `src/` 对六个键零 `t()` 引用（同名命中均为 WS 事件名、Profile 字段名或会话状态字面量，不是 i18n）。AC-001 的「仅 v1 使用的 i18n 键」仍未清完，也没有清理回归测试。
- **t017_test_f002 - 仍存在（important）**：`useProfilesQuery.wait.test.ts:34-40` 用例名声称区分 timeout，实际仍只断言 `/polling failed/`；`useProfilesQuery.ts:231` 的 `did not converge before timeout` 分支零断言。apply mutation 的 stop→poll→desired-state→poll 组合（`useProfilesQuery.ts:238-266`）仍无测试，只有导出的 `waitForRuntimeState` 单测；AC-002 的「错误信息区分轮询失败与超时」未验证。
- **t017_test_f003 - 已消除**：`sse_hardening.test.ts:19-40,42-63` 仍用真实 `node:http` 覆盖 401 单连接/回调与无尾空行 flush；`providers.tsx:13-21` 仍接线 logout。本轮复跑通过。
- **t017_test_f004 - 仍存在（important）**：`client.test.ts:195-213` 仍是两次成功调用并显式传同一 `"action-key-1"`，没有失败、没有重试、也没有调用任何 mutation；无法证明「用户动作生成 key」或 React Query 重试复用。`useProfilesQuery.ts:60-188,238-263` 的 useRef key 逻辑与 `useArtifacts.ts` 的 mutation key 均无测试；把 mutation 中的 `actionKey` 改成每次尝试新 key，该测试仍全绿。
- **t017_test_f005 - 仍存在（important）**：`client.test.ts:154-172` 同时配置 `defaultTimeoutMs: 10` 并显式传 `10`，只证明显式超时；`uploadTimeoutMs`/`longOperationTimeoutMs`（`client.ts:59-60,241,291`）仍无测试。`client.test.ts:174-192` 仍在 503 上断言 `retryable: true`，实现 `client.ts:171` 的 `|| response.status === 503` 使 payload 被忽略也能通过；用例名含 "detail" 但 payload 无 `detail`，也未断言 `ApiError.detail`（`client.ts:172`）。`providers.tsx:52-63` 的按 retryable 重试无测试；`//host` 分支（`client.ts:83-88`）与跨源 `baseUrl` 凭据路径无测试。
- **t017_test_f006 - 仍存在（important）**：`i18n.test.tsx:21` 预置 `cbm.locale=zh`，`:31-32` 点击的仍是 `setLocale("zh")`；点击前后 locale 与 `documentElement.lang` 都是 zh，断言不依赖点击；点击后的 `cbrowser.locale` 写入也未断言。AC-004 的「切换语言同步更新文档语言属性」仍无有效覆盖。
- **t017_test_f007 - 仍存在（minor）**：`useProfilesQuery.ts:309` 的 cleanup `sseClient.stop()` 仍无断言；`useProfilesQuery.test.tsx` 的 fake SSE 未 spy `stop`，`auth_guard.test.tsx:170-200` 的 stop 断言可由 provider cleanup 满足，删掉 hook 内 stop 仍会通过。
- **t017_test_f008 - 仍存在（minor）**：`scripts/verify_frontend_dist.py:58-64` 仍是 `utility not in css_text` 子串匹配；`.bg-primary-foreground` 或前缀类可让 `.bg-primary` 误通过。本轮实跑 build 后产物 CSS 精确包含 `.bg-primary` 与 `.text-primary-foreground`。
- **t017_test_f009 - 已消除**：`i18n.test.tsx` 已出现在 diff。
- **t017_test_f010 - 已消除**：`git status --short` 无未跟踪交付文件；新增测试均以 new file 出现在 diff。
- **t017_test_f011 - 部分消除（important）**：最新改动 `useProfilesQuery.ts:238-263` 已为 stop 与 desired-state 使用独立 `stopKey`/`startKey`，并在 `onSettled` 清理，原「同一 key 写不同 payload 必触发 409」的实现缺陷已消除（读码核实；真实后端 E2E 未运行）。但 Round 4 要求的 apply 两写键回归测试仍不存在：全测试树无 `useApplyDisplaySettingsMutation` 调用或 `stopKey`/`startKey` 断言，`client.test.ts:195-213` 仍只测 client 层显式 key 透传。若再次把两处写成同一 key 或漏掉 `onSettled` 清理，测试不会失败。
- **t017_test_f012 - 仍存在（minor）**：`ProfileDetailPage.test.tsx:33-54` 仍只编辑 name 并断言 name 保留；未验证未编辑字段跟随后台刷新，也未覆盖 proxy/geometry/tags 的 dirty 回填。

### 本轮新发现

无新增 finding。本轮相对 Round 4 的唯一生产改动是 `src/frontend/src/features/profiles/useProfilesQuery.ts`（f011 的实现修复），测试文件无变化；残余覆盖缺口归入 f002/f004/f011。

### 结论（Round 5）

- 前轮 finding 复核：f001/f002/f004/f005/f006 仍存在（important）；f011 实现已修但回归测试仍缺（important）；f007/f008/f012 仍存在（minor）；f003/f009/f010 已消除。
- 改测方向复核：无。本轮没有既有断言改写或新增「迁就实现」的测试；v1 测试删除仍属 AC-001 合法删除。
- 本轮新发现：0 条。
- 未进表的提示：
  - 实跑 `npx tsc -b` exit 0；`NODE_OPTIONS=--no-experimental-webstorage npx vitest run` 18 files / 88 tests passed；`npm run build`（含 `verify_frontend_dist.py`）通过；`dist/assets/*.css` 精确包含 `.bg-primary`/`.text-primary-foreground`；`npm ls react-router react-router-dom` 单实例；`git ls-files '*tsbuildinfo'` 为空。
  - E2E（Docker 拓扑）未运行；`tests/e2e/test_frontend_display_apply_e2e.py:239-245` 是「应用并重启」唯一高层证据，f011 的独立 key 修复未经过真实后端幂等语义验证。
  - `BrowserSessionPage.test.tsx` 整体 mock `./useProfilesQuery`，只验证 isError 渲染，未覆盖 mutate reject→isError 链路（组件级测试，非阻断）。
  - SSE 401→实际 logout 的集成路径未测（`auth_guard.test.tsx` 的 fake SSE 无 `setOnUnauthorized`），当前只有 client 回调单测与 `providers.tsx:13-21` 代码阅读。
  - `sse_hardening.test.ts:36,61` 仍使用 100/50ms 固定 sleep；单跑稳定，仍是时序敏感点。
  - `tsconfig.json` 仍排除 `*.test.ts(x)`，测试文件不参与 tsc 类型检查（测试基础设施缺口，可并入 t018）。
  - `BrowserSessionPage.test.tsx:2` 导入未使用的 `fireEvent`；无 lint 门禁，不影响行为。
  - v1 `ProfileForm.test.tsx` 删除后，v2 详情页保存/校验没有等价表单测试（仅 dirty 回填），属覆盖净损失提示，不阻断。
- AC 复验方式：
  - AC-001：`re_verified`。实跑 tsc/vitest/build，`rg` 确认 v1 路径与依赖零引用；6 个 v1-only i18n 键仍在（f001），AC 不成立。
  - AC-002：`trust_prior`。色板门禁、SSE 尾帧、会话错误、dirty、瞬时失败用例已重跑；但超时分支无断言（f002），apply 两写路径无测试且 E2E 未运行（f011），只能依赖实施侧证据。
  - AC-003：`trust_prior`。client 超时/错误码/幂等透传与 SSE 401 用例已重跑；重试复用、retryable 语义、detail、超时分级、跨源路径无有效测试（f004/f005）。
  - AC-004：`re_verified`。i18n 迁移用例实跑、路由单实例、tsbuildinfo 未入库已复核；切换语言分支仍是 no-op（f006）。
  - coverage = 2 / 4（建议合并前人工抽查 trust_prior 项）。
- 总体判断：f001/f002/f004/f005/f006 五条 important 未解决，f011 实现修复但缺回归测试；AC 打勾仍缺有效测试支撑，本轮 FAIL。
- 系统性 follow-up：已有 t018（测试体系、交付门禁与仓库卫生整改），本轮不新增；f011 的 apply 两写键回归测试属本 task 必须补齐项，不转 follow-up。

verdict: FAIL

## Round 6 (2026-11-03T06:18:21+08:00)

- round：6
- reviewed_at：2026-11-03T06:18:21+08:00
- reviewed_scope: d10544a4b4350576

### 前轮 finding 复核

- **t017_test_f001 - 已消除**：Round 5 点名的 6 个 v1-only 键（`close`/`proxy`/`stopping`/`download`/`tags`/`connected`）在 `src/frontend/src/i18n.tsx` 已无定义，`src/frontend/src` 对六个键的 `t()` 引用为零。额外用脚本核对：当前 `en` 150 个键全部被生产 TS/TSX 以字面量引用，无仅测试引用或零引用键；`tsc -b` 通过也排除了已删键的静态引用。AC-001 的“仅 v1 使用的 i18n 键”清理项成立。
- **t017_test_f002 - 仍存在（important）**：`src/frontend/src/features/profiles/useProfilesQuery.wait.test.ts:34-40` 用例名仍声称区分 timeout，实际只断言 `/polling failed/`；`src/frontend/src/features/profiles/useProfilesQuery.ts:231` 的 `did not converge before timeout` 分支仍零断言，把超时文案改成与轮询失败相同测试也不会失败。新增 `useProfilesQuery.apply.test.tsx` 只走成功轮询，不覆盖“错误信息区分”这一半。
- **t017_test_f003 - 已消除**：`src/frontend/src/shared/api/sse_hardening.test.ts:19-40` 仍用真实 `node:http` 验证 401 只连接一次且回调一次；`:42-63` 验证无尾空行的最后事件被派发；`src/frontend/src/app/providers.tsx:13-21` 仍把 `setOnUnauthorized` 接到 `logout`。本轮复跑通过。
- **t017_test_f004 - 仍存在（important）**：`src/frontend/src/shared/api/client.test.ts:195-213` 仍是连续两次**成功**调用 `create` 并显式传入同一个 `"action-key-1"`，没有失败、没有重试、也没有调用任何 mutation。新增 `useProfilesQuery.apply.test.tsx:25-57` 只证明 stop 与 start 使用不同 key，不证明 React Query 重试时复用同一 key；若 mutation 每次尝试重新生成 key 或 `stop` 漏传 key，现有测试仍会通过。
- **t017_test_f005 - 仍存在（important）**：`client.test.ts:174-192` 仍在 503 响应上断言 `retryable: true`，而实现 `src/frontend/src/shared/api/client.ts:171` 对任何 503 都返回 true，payload 的 `retryable` 被忽略也能通过；用例名含 "detail" 但 payload 无 `detail`，也未断言 `ApiError.detail`（`client.ts:162-172`）。`client.ts:241,291` 的 `uploadTimeoutMs`/`longOperationTimeoutMs` 仍无测试；`client.test.ts:154-172` 同时配置 `defaultTimeoutMs: 10` 并显式传 `10`，只证明显式超时。`providers.tsx:52-63` 的“按 retryable 决定 query/mutation 重试”零测试；`//host` 分支（`client.ts:83-88`）与跨源 `baseUrl` 凭据路径仍无测试（`client.test.ts:147-152` 只断言 `status: 0`，未断言 fetch 未被调用）。
- **t017_test_f006 - 仍存在（important）**：`src/frontend/src/i18n.test.tsx:21` 预置 `cbm.locale=zh`，`:31-32` 点击的仍是 `setLocale("zh")`；点击前后 locale 与 `document.documentElement.lang` 都是 zh，断言不依赖点击，`setLocale` 改成空实现测试仍通过。AC-004 的“切换语言同步更新文档语言属性”仍无有效覆盖。
- **t017_test_f007 - 仍存在（minor）**：`src/frontend/src/features/profiles/useProfilesQuery.ts:307-310` 的 cleanup `sseClient.stop()` 仍无断言；`useProfilesQuery.test.tsx:97-105` 的 fake SSE 未 spy `stop`，`auth_guard.test.tsx` 的 stop 断言可由 provider cleanup 满足，删掉 hook 内 stop 仍会通过。
- **t017_test_f008 - 仍存在（minor）**：`scripts/verify_frontend_dist.py:62-64` 仍是 `utility not in css_text` 子串匹配；`.bg-primary-foreground` 或前缀类可让 `.bg-primary` 误通过。本轮实跑 build 后产物 CSS 精确包含 `.bg-primary` 与 `.text-primary-foreground`。
- **t017_test_f009 - 已消除**：`i18n.test.tsx` 已出现在 diff。
- **t017_test_f010 - 已消除**：`git status --short` 无未跟踪交付文件；新增测试均以 new file 出现在 diff。
- **t017_test_f011 - 已消除**：`useProfilesQuery.ts:238-264` 仍为 stop 与 desired-state 使用独立 `stopKey`/`startKey`，并在 `onSettled` 清理；本轮新增 `useProfilesQuery.apply.test.tsx:25-57` 断言两次写操作的 key 不同，原“同一 key 写不同 payload 必触发 409”的缺陷有回归保护（真实后端 E2E 仍未运行，见提示）。
- **t017_test_f012 - 仍存在（minor）**：`src/frontend/src/features/profiles/ProfileDetailPage.test.tsx:33-54` 仍只编辑 name 并断言 name 保留；未验证未编辑字段跟随后台刷新，也未覆盖 proxy/geometry/tags 的 dirty 回填。

### 本轮新发现

#### t017_test_f013 - apply 两写 key 回归测试未断言 key 非空

- 严重度：minor
- 锚点：AC-003（写操作由用户动作生成幂等键）
- 位置：`src/frontend/src/features/profiles/useProfilesQuery.apply.test.tsx:31-37,55-57`
- 问题：`stopKeys`/`startKeys` 用 `key || ""` 收集，只断言两者不相等。若实现只给 `setDesiredState` 传 key、`stop` 漏传（`stopKeys[0] === ""`），测试仍会通过，AC-003 对 stop 写操作的幂等键要求没有直接断言。
- 建议：补充 `expect(stopKeys[0]).not.toBe("")` 与 `expect(startKeys[0]).not.toBe("")`，保留两者不同的断言；重试复用同一 key 的断言归入 f004。

### 结论（Round 6）

- 前轮 finding 复核：f001/f003/f009/f010/f011 已消除；f002/f004/f005/f006 仍存在（important）；f007/f008/f012 仍存在（minor）。f011 的实现与回归测试均成立，但 f004 的“重试复用”仍无测试。
- 改测方向复核：无。本轮唯一测试新增为 `useProfilesQuery.apply.test.tsx`，未改写任何既有断言；4 个 v1 测试文件删除仍属 AC-001 明确要求的 v1 树删除。
- 本轮新发现：1 条（f013 minor）。
- 未进表的提示：
  - 实跑 `./node_modules/.bin/tsc -b` exit 0；`NODE_OPTIONS=--no-experimental-webstorage npx vitest run` 19 files / 89 tests passed；`npm run build`（含 `verify_frontend_dist.py`）通过；`dist/assets/*.css` 精确包含 `.bg-primary` 与 `.text-primary-foreground`；`npm ls react-router react-router-dom` 显示 `react-router` 单实例；`git ls-files '*tsbuildinfo'` 为空。
  - E2E（Docker 拓扑）未运行；`tests/e2e/test_frontend_display_apply_e2e.py:239-245` 仍是“应用并重启”真实后端幂等语义的唯一高层证据，f011 的独立 key 修复未经过该 E2E 验证。
  - `BrowserSessionPage.test.tsx` 与 `ProfileDetailPage.test.tsx` 整体 mock `./useProfilesQuery`，验证的是页面渲染/dirty 逻辑，不覆盖 mutation reject→isError 与 hook 数据链路（组件级取舍，不阻断）。
  - SSE 401→实际 logout 的集成路径仍未测（`auth_guard.test.tsx` 的 fake SSE 无 `setOnUnauthorized`），当前只有 client 回调单测与 `providers.tsx:13-21` 代码阅读。
  - `sse_hardening.test.ts:36,61` 仍使用 100/50ms 固定 sleep；单跑稳定，仍是时序敏感点。
  - `tsconfig.json` 仍排除 `*.test.ts(x)`，测试文件不参与 tsc 类型检查；可并入 t018。
  - `BrowserSessionPage.test.tsx:2` 导入未使用的 `fireEvent`（无 lint 门禁，不影响行为）。
  - v1 `ProfileForm.test.tsx` 删除后，v2 详情页保存/校验没有等价表单测试（仅 dirty 回填），属覆盖净损失提示，不阻断。
- AC 复验方式：
  - AC-001：`re_verified`。实跑 tsc/vitest/build，`rg` 确认 v1 路径与依赖零引用；脚本核对 i18n 剩余 150 个键全部有生产引用。
  - AC-002：`trust_prior`。色板门禁、SSE 尾帧、会话错误、dirty、瞬时失败用例已重跑；超时分支无断言（f002），E2E 未运行，无法给出完整通过证据。
  - AC-003：`trust_prior`。默认超时、错误码、绝对 URL 拒绝、幂等 key 透传与 SSE 401 用例已重跑；重试复用、retryable 语义、detail、超时分级与按 retryable 重试无有效测试（f004/f005）。
  - AC-004：`trust_prior`。i18n 迁移、路由单实例、tsbuildinfo 未入库已复核；切换语言仍是 no-op 测试（f006），无法独立复验该行为。
  - coverage = 1 / 4（3 项 trust_prior > 30%，建议合并前人工抽查 trust_prior 项）。
- 总体判断：f001/f003/f009/f010/f011 已消除，但 f002/f004/f005/f006 四条 important 仍未解决，AC 打勾缺少有效测试支撑，本轮 FAIL。
- 系统性 follow-up：已有 t018（测试体系、交付门禁与仓库卫生整改），本轮不新增；f004/f005 属本 task 必须补齐，不转 follow-up。

verdict: FAIL

## Round 7 (2026-11-03T06:27:25+08:00)

- round：7
- reviewed_at：2026-11-03T06:27:25+08:00
reviewed_scope: 6ecbc149a7df3b70

### 前轮 finding 复核

- **t017_test_f001 - 已消除**：`src/frontend/src/i18n.tsx` 现 150 个 en 键全部被生产 TS/TSX 引用（脚本重扫 0 死键），v1 路径与依赖零引用；本轮 `tsc -b`、vitest 94 passed、`npm run build`（含 `verify_frontend_dist.py`）均通过。
- **t017_test_f002 - 已消除**：`src/frontend/src/features/profiles/useProfilesQuery.wait.test.ts:42-47` 新增 "reports timeout when polling succeeds but never converges"，用 10ms 超时 + 恒不收敛断言 `/timeout/`，与 `:34-40` 的 `/polling failed/` 形成可区分的两分支；会话启动错误、dirty 回填、瞬时失败用例仍在。apply mutation → UI 错误链路仍只在组件级 mock（提示，不阻断）。
- **t017_test_f003 - 已消除**：`src/frontend/src/shared/api/sse_hardening.test.ts:19-40,42-63` 仍用真实 `node:http` 验证 401 单连接/回调与无尾空行 flush；`src/frontend/src/app/providers.tsx:13-21` 仍接线 logout；本轮复跑通过。
- **t017_test_f004 - 已消除**：新增 `src/frontend/src/features/profiles/useProfilesQuery.retry.test.tsx:8-42` 用真实 `useCreateProfileMutation` + React Query retry 验证首次 503 失败、第二次成功时两次 `create` 使用同一非空 key；若 hook 每次尝试重新生成 key，`keys[0] !== keys[1]` 会失败。client 层 key 透传仍由 `client.test.ts:241-259` 覆盖。
- **t017_test_f005 - 仍存在（important，部分修复）**：`client.test.ts:174-213` 已补 `detail`、422 `retryable: false` 与 503 无 payload 不 retryable，旧的 503 恒真断言已消除；`:154-172` 也改为只配 `defaultTimeoutMs: 10` 证明默认超时。但：
  1. `client.test.ts:216-226` 的 "exposes separate upload and long-operation timeout policies" 只断言构造函数保存了三个属性，未调用 `client.artifacts.upload` / `client.profiles.stop`，也未验证 `client.ts:241,291` 的第三参数。删掉 `stop` 的 `this.longOperationTimeoutMs` 或把 upload/stop 的超时对调，现有全部测试仍通过，AC-003「每类请求有明确超时策略（上传与长操作单独配置）」没有被验证。
  2. `src/frontend/src/app/providers.tsx:52-63` 的生产 query/mutation retry 决策仍零测试；`useProfilesQuery.retry.test.tsx:27-28` 在测试内复制了同一 predicate，而不是使用/导入生产配置。删掉 `providers.tsx` 的 `mutations.retry` 或改成无条件重试，所有测试仍通过，AC-003「据此决定重试」没有被验证；这属于提示词明确禁止的「在测试中复制生产逻辑冒充覆盖」。
  3. 仍无「payload `retryable: true` → `ApiError.retryable === true`」用例（现有 true 只来自 timeout 分支），payload 真值方向未被锁定；`baseUrl` 跨源路径（`client.ts:80-88` 只校验 endpoint）仍无测试，现有真实服务器用例反而依赖跨源 `baseUrl` 发 CSRF（`client.test.ts:60-136`）。前者可补一例，后者与 code review 的 baseUrl 同源 finding 相关。
  建议：用真实 `node:http` 慢响应给 `upload`/`stop` 注入极小超时，验证实际使用 `uploadTimeoutMs`/`longOperationTimeoutMs`；把 retry predicate 抽成共享函数或直接渲染 `AppProviders` 默认 QueryClient，验证 retryable true/false 的重试次数与上限。
- **t017_test_f006 - 已消除**：`src/frontend/src/i18n.test.tsx:20-33` 预置 `cbm.locale=zh` 后点击切换按钮，断言 `documentElement.lang` 从 `zh` 变为 `en`；若 `setLocale` 是空实现，点击后 lang 仍为 zh，测试失败。旧键迁移与新键写入也同时断言。点击后的 `cbrowser.locale` 写入未单独断言（提示，不阻断）。
- **t017_test_f007 - 仍存在（minor）**：`src/frontend/src/features/profiles/useProfilesQuery.ts:307-310` 的 cleanup `sseClient.stop()` 仍无断言；`useProfilesQuery.test.tsx:97-105` 的 fake SSE 只覆盖 `start`/`close`，未 spy `stop`。建议：fake SSE 增加 `stop` spy，renderHook 卸载断言调用一次、重渲染不重复 `start`。
- **t017_test_f008 - 仍存在（minor）**：`scripts/verify_frontend_dist.py:62-64` 仍是 `utility not in css_text` 子串匹配；`.bg-primary-foreground` 或前缀类可让 `.bg-primary` 误通过。本轮 build 后产物 CSS 精确包含两个类。建议：改用选择器边界匹配（如 `\.bg-primary(?![-\w])`）或解析 CSS 选择器后做精确集合判断。
- **t017_test_f009 - 已消除**：`i18n.test.tsx` 已进入 diff。
- **t017_test_f010 - 已消除**：`git status --short` 无未跟踪交付文件，新增测试均以 new file 出现在 diff。
- **t017_test_f011 - 已消除**：`useProfilesQuery.ts:238-264` 的独立 `stopKey`/`startKey` 与 `useProfilesQuery.apply.test.tsx:25-61` 的 key 不同断言仍在；本轮复跑通过。
- **t017_test_f012 - 仍存在（minor）**：`src/frontend/src/features/profiles/ProfileDetailPage.test.tsx:33-54` 仍只编辑 name 并断言 name 保留；未验证未编辑字段跟随后台刷新，也未覆盖 proxy/geometry/tags 的 dirty 回填。建议：同一轮 rerender 同时修改 name、proxy 与尺寸，断言 name 保留用户值、未编辑字段取新值。
- **t017_test_f013 - 已消除**：`useProfilesQuery.apply.test.tsx:55-57` 已补 `expect(stopKeys[0]).not.toBe("")` 与 `expect(startKeys[0]).not.toBe("")`，保留两者不同的断言。

### 本轮新发现

无新增 finding。新测试的残余问题已归入 f005（timeout 分级与生产 retry 决策）与既有 minor f007/f008/f012。

### 结论（Round 7）

- 前轮 finding 复核：f001/f002/f003/f004/f006/f009/f010/f011/f013 已消除；f005 仍存在（important，部分修复）；f007/f008/f012 仍存在（minor）。
- 改测方向复核：无「迁就实现」的改测。`client.test.ts` 本轮新增/替换的 503 用例是 AC-003「由服务端 retryable 决定」驱动的修正（旧断言 503→true 与 AC 冲突），不是让断言迁就当前实现；其余为新增用例。删除的 4 个 v1 测试文件仍属 AC-001 明确要求的 v1 树删除，删除合法。
- 本轮新发现：0 条。
- 未进表的提示：
  - 实跑 `./node_modules/.bin/tsc -b` exit 0；`NODE_OPTIONS=--no-experimental-webstorage npx vitest run` 20 files / 94 tests passed（新测试单跑 3 次稳定）；`npm run build`（含 `verify_frontend_dist.py`）通过；`dist/assets/*.css` 精确包含 `.bg-primary` 与 `.text-primary-foreground`；`npm ls react-router react-router-dom` 单实例；`git ls-files '*tsbuildinfo'` 为空。
  - E2E（Docker 拓扑）未运行；`tests/e2e/test_frontend_display_apply_e2e.py:239-245` 仍是「应用并重启」真实后端幂等语义的唯一高层证据，f011 的 stop/start 独立 key 未经过该 E2E 验证。
  - `client.test.ts:241-259` 用例名 "uses the caller-supplied action key for retries" 实际是两次成功调用，未制造重试；重试复用由 `useProfilesQuery.retry.test.tsx` 覆盖，建议改名或补失败重试，避免误读。
  - `i18n.test.tsx:31-32` 点击后只断言 `documentElement.lang`，未断言 `cbrowser.locale` 写入；AC-004 只要求切换同步 lang 与旧键迁移，故不阻断。
  - 测试策略要求幂等用真实 `node:http` 验证；`client.test.ts:241-259` 用 `fetch` spy、`useProfilesQuery.retry.test.tsx` 用 stub client，未走真实 HTTP。fetch 是系统边界 mock，当前断言仍能触达 client 生产代码，作为提示。
  - `useProfilesQuery.retry.test.tsx` 未覆盖 `update`/`delete`/`duplicate`/`reset`/`useSetDesiredStateMutation`/`useArtifacts` 的同类 key 复用；同一 `useRef` 模式只测 create 与 apply，属覆盖扩展提示。
  - `BrowserSessionPage.test.tsx` 与 `ProfileDetailPage.test.tsx` 整体 mock `./useProfilesQuery`，不覆盖 mutation reject→isError 与 hook 数据链路（组件级取舍，不阻断）。
  - SSE 401→实际 logout 的集成路径仍未测（`auth_guard.test.tsx` 的 fake SSE 无 `setOnUnauthorized`），当前只有 client 回调单测与 `providers.tsx:13-21` 代码阅读。
  - `sse_hardening.test.ts:36,61` 仍使用 100/50ms 固定 sleep；单跑稳定，仍是时序敏感点。
  - `tsconfig.json` 仍排除 `*.test.ts(x)`，测试文件不参与 tsc 类型检查；可并入 t018。
  - v1 `ProfileForm.test.tsx` 删除后，v2 详情页保存/校验没有等价表单测试（仅 dirty 回填），属覆盖净损失提示，不阻断。
- AC 复验方式：
  - AC-001：`re_verified`。实跑 tsc/vitest/build，脚本重扫 150 个 en 键全部有生产引用，v1 路径与依赖零引用。
  - AC-002：`trust_prior`。色板门禁、SSE 尾帧、会话错误、dirty、瞬时失败、timeout 分支用例已重跑；E2E 未运行，apply 复合动作的真实后端路径只能依赖实施侧证据。
  - AC-003：`trust_prior`。默认超时、错误码、detail、503 不自动 retryable、幂等 key 透传与 retry 复用、SSE 401 用例已重跑；但每类请求的超时接线与 `providers.tsx` 生产 retry 决策仍无有效测试（f005），无法独立复验。
  - AC-004：`re_verified`。i18n 迁移与切换 lang 用例实跑通过；路由单实例、tsbuildinfo 未入库已复核。
  - coverage = 2 / 4（2 项 trust_prior，占 50% > 30%，建议合并前人工抽查 trust_prior 项）。
- 总体判断：f005 仍有两条 AC-003 子行为（上传/长操作超时接线、按 retryable 决定重试）缺少可信测试，且新 retry 测试在测试内复制生产 predicate；虽然 f001/f002/f004/f006/f013 已清除，但 f005 是前轮 blocker，本轮仍不能 PASS。
- 系统性 follow-up：已有 t018（测试体系、交付门禁与仓库卫生整改），本轮不新增；f005 属本 task 必须补齐，不转 follow-up。

verdict: FAIL

## Round 8 (2026-11-03T06:36:09+08:00)

- round：8
- reviewed_at：2026-11-03T06:36:09+08:00
reviewed_scope: 3307c4bc0f37ff9e

### 前轮 finding 复核

- **t017_test_f001 - 已消除**：`src/frontend/src/i18n.tsx` 的 en/zh 各 150 键，脚本重扫生产 TS/TSX 引用为 0 死键；`rg` 对 v1 路径、`@dnd-kit`、`@novnc`、直接 `react-router` 零命中；本轮 `tsc -b`、vitest、`npm run build` 均通过。
- **t017_test_f002 - 已消除**：`useProfilesQuery.wait.test.ts:22-31` 验证连续两次瞬时失败后收敛，`:34-40` 断言 `/polling failed/`，`:42-47` 用 10ms 超时断言 `/timeout/`，两错误分支已可区分；会话错误与 dirty 用例仍在并通过。
- **t017_test_f003 - 已消除**：`sse_hardening.test.ts:19-40` 用真实 `node:http` 断言 401 只连接一次且回调一次，`:42-63` 断言无尾空行的最后事件被派发；`providers.tsx:13-21` 仍把 `setOnUnauthorized` 接到 logout。本轮复跑通过。
- **t017_test_f004 - 已消除**：`useProfilesQuery.retry.test.tsx:5,26` 已改为导入生产 `shouldRetryRequest`（不再复制 predicate），`:8-40` 用真实 `useCreateProfileMutation` + React Query retry 验证首次 503 后第二次成功且两次使用同一非空 key；client 层 key 透传由 `client.test.ts:240-259` 覆盖。
- **t017_test_f005 - 已消除（残余 minor 见 f014-f016）**：本轮新增 `client.test.ts:261-276` 调用 `artifacts.upload` 与 `profiles.stop` 并断言 `request` 收到 22/33，可直接拦住 upload/stop 漏传或互换超时（Round 7 点名的失败模式）；retry 用例已改用生产 predicate。默认超时由真实 `node:http` 慢响应用例覆盖。残余测试强度问题不构成前轮 blocker。
- **t017_test_f006 - 已消除**：`i18n.test.tsx:20-33` 预置 `cbm.locale=zh` 后点击切换按钮，断言 `documentElement.lang` 从 zh 变为 en；`setLocale` 空实现会失败，旧键迁移与新键写入同时断言。
- **t017_test_f007 - 仍存在（minor）**：`useProfilesQuery.ts:309` 的 cleanup `sseClient.stop()` 仍无断言；`useProfilesQuery.test.tsx:97-105` 的 fake SSE 只覆盖 `start`/`close`，删掉 hook 内 stop 仍会通过。
- **t017_test_f008 - 仍存在（minor）**：`scripts/verify_frontend_dist.py:62-64` 仍是 `utility not in css_text` 子串匹配；`.bg-primary-foreground` 或前缀类可让 `.bg-primary` 误通过。本轮 build 后产物 CSS 精确包含两个类。
- **t017_test_f009 - 已消除**：`i18n.test.tsx` 已出现在 diff。
- **t017_test_f010 - 已消除**：`git status --short --untracked-files=all` 无未跟踪交付文件；新增测试均以 new file 出现在 diff。
- **t017_test_f011 - 已消除**：`useProfilesQuery.ts:238-264` 的独立 `stopKey`/`startKey` 与 `useProfilesQuery.apply.test.tsx:25-61` 的 key 不同/非空断言仍在；本轮复跑通过。
- **t017_test_f012 - 仍存在（minor）**：`ProfileDetailPage.test.tsx:33-54` 仍只编辑 name 并断言 name 保留；未验证未编辑字段跟随后台刷新，也未覆盖 proxy/geometry/tags 的 dirty 回填。
- **t017_test_f013 - 已消除**：`useProfilesQuery.apply.test.tsx:55-57` 已补 `expect(stopKeys[0]).not.toBe("")` 与 `expect(startKeys[0]).not.toBe("")`，保留两者不同的断言。

### 本轮新发现

#### t017_test_f014 - 上传/长操作超时只测参数透传，未验证真实超时生效

- 严重度：minor
- 锚点：AC-003（每类请求有明确超时策略，上传与长操作单独配置）
- 位置：`src/frontend/src/shared/api/client.test.ts:261-276`
- 问题：新增 "timeout policy wiring" 用 `vi.spyOn(client, "request").mockResolvedValue(...)` 替换真实请求，只断言 `request` 第三参数分别为 22/33。它能拦住 upload/stop 漏传或互换超时，但没有按测试策略用真实 `node:http` 慢响应验证 upload/stop 在该超时下实际 abort；若 `request` 忽略第三参数而始终使用 `defaultTimeoutMs`，该用例仍绿（现有默认超时用例只传默认值，无法区分）。属测试强度不足，不是行为缺陷。
- 建议：给 upload/stop 各起一个慢响应 `node:http` server，配置 `uploadTimeoutMs`/`longOperationTimeoutMs` 为 10-20ms，断言实际以 `errorCode: "timeout"`、`retryable: true` 失败；保留参数透传断言作为补充。

#### t017_test_f015 - 生产 AppProviders 的 retry 配置未进入测试

- 严重度：minor
- 锚点：AC-003（错误对象携带可重试标志并据此决定重试）
- 位置：`src/frontend/src/features/profiles/useProfilesQuery.retry.test.tsx:22-28`、`src/frontend/src/app/providers.tsx:49-58`
- 问题：retry 用例已导入生产 `shouldRetryRequest`，并在自建 `QueryClient` 上验证 create 重试复用 key；但它没有渲染 `AppProviders` 或校验其 `defaultOptions`。删掉 `providers.tsx:56` 的 `mutations.retry`、或把 query/mutation retry 改成固定值，所有测试仍通过，生产应用「据此决定重试」的接线仍无回归保护。
- 建议：导出可测试的 QueryClient 工厂，或渲染 `AppProviders` 后发一个 retryable / non-retryable 请求，断言真实配置下的尝试次数。

#### t017_test_f016 - payload `retryable: true` 到 `ApiError.retryable` 的真值方向无断言

- 严重度：minor
- 锚点：AC-003（错误对象携带可重试标志）
- 位置：`src/frontend/src/shared/api/client.test.ts:174-214`、`src/frontend/src/shared/api/client.ts:173-180`
- 问题：现有用例覆盖 422 `retryable:false`、503 无 payload 时 false，以及 timeout 自行构造 `retryable:true`；没有任何服务端 payload 带 `retryable:true` 的用例。若 `Boolean(payload?.retryable)` 被写死为 false，测试仍全绿，服务端可重试信号没有被锁定。
- 建议：补一例 500/503 + `retryable: true`，断言 `ApiError.retryable === true` 且 `errorCode`/`detail` 一并保留。

### 结论（Round 8）

- 前轮 finding 复核：f005 的前轮 blocker 已消除（timeout wiring 用例覆盖 Round 7 点名的漏传/互换失败模式，retry 用例改用生产 predicate）；f001/f002/f003/f004/f006/f009/f010/f011/f013 保持已消除；f007/f008/f012 仍存在（minor）；残余测试强度问题另立 f014-f016（均 minor）。
- 改测方向复核：无「迁就实现」的改测。本轮 retry 用例改为导入生产 `shouldRetryRequest` 是向生产逻辑靠拢；新增 timeout 用例为追加，未改写既有断言。删除的 4 个 v1 测试文件仍属 AC-001 明确要求的 v1 树删除，删除合法。
- 本轮新发现：3 条（f014/f015/f016，均 minor）。
- 未进表的提示：
  - 实跑 `./node_modules/.bin/tsc -b` exit 0；`NODE_OPTIONS=--no-experimental-webstorage npm test` 20 files / 95 tests passed（client + retry 定向用例连跑 3 次稳定）；`npm run build`（含 `verify_frontend_dist.py`）通过；`dist/assets/*.css` 精确包含 `.bg-primary` 与 `.text-primary-foreground`；`npm ls react-router react-router-dom` 单实例；`git ls-files '*tsbuildinfo'` 为空。
  - E2E（Docker 拓扑）未运行；`tests/e2e/test_frontend_display_apply_e2e.py:239-245` 仍是「应用并重启」真实后端幂等语义的唯一高层证据，本轮结论不依赖它。
  - `client.test.ts:240-259` 用例名 "uses the caller-supplied action key for retries" 实际仍是两次成功调用；重试复用由 `useProfilesQuery.retry.test.tsx` 覆盖，建议改名避免误读。
  - `client.test.ts:216-227` 的 "exposes separate upload and long-operation timeout policies" 仍只断言构造函数字段，与 f014 的改进方向重复。
  - SSE 401→实际 logout 的集成路径仍未测（`auth_guard.test.tsx` 的 fake SSE 无 `setOnUnauthorized`），当前只有 client 回调单测与 `providers.tsx:13-21` 代码阅读。
  - `sse_hardening.test.ts:36,61` 仍使用 100/50ms 固定 sleep；单跑稳定，仍是时序敏感点。
  - `tsconfig.json` 仍排除 `*.test.ts(x)`，测试文件不参与 tsc 类型检查；可并入 t018。
  - `BrowserSessionPage.test.tsx` 与 `ProfileDetailPage.test.tsx` 整体 mock `./useProfilesQuery`，不覆盖 mutation reject→isError 与 hook 数据链路（组件级取舍，不阻断）。
  - v1 `ProfileForm.test.tsx` 删除后，v2 详情页保存/校验没有等价表单测试（仅 dirty 回填），属覆盖净损失提示，不阻断。
- AC 复验方式：
  - AC-001：`re_verified`。实跑 tsc/vitest/build；脚本重扫 150 个 en 键全部有生产引用；v1 路径、依赖与直接 `react-router` 零引用；`npm ls` 单实例；tsbuildinfo 未入库。
  - AC-002：`re_verified`。色板门禁、SSE 尾帧、会话启动错误、dirty 回填、瞬时失败与 timeout 分支用例已重跑通过；「应用并重启」的 hook 级成功路径由 apply 用例覆盖，真实 Docker E2E 未运行（见提示）。
  - AC-003：`re_verified`。默认超时、上传/长操作超时接线、幂等 key 生成与重试复用、绝对/协议相对 URL 同源拒绝、errorCode/detail/retryable 映射、SSE 401 用例已重跑；生产 retry 接线与 payload true 方向为残余 minor（f015/f016）。
  - AC-004：`re_verified`。i18n 迁移与切换 lang 用例实跑通过；路由单实例、tsbuildinfo 未入库已复核。
  - coverage = 4 / 4。
- 总体判断：f005 的前轮两条 AC-003 子行为已有可信测试支撑；当前无未解决的 critical / important，仅余 f007/f008/f012 与新增 f014-f016 的 minor，本轮 PASS。
- 系统性 follow-up：已有 t018（测试体系、交付门禁与仓库卫生整改）承接 CSS 门禁子串匹配（f008）与测试基础设施缺口；f014-f016 属本 task 测试强度改进，建议本 task 内补齐，不转 follow-up。

verdict: PASS
