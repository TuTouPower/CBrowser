# Task review t025（reviewer_focus: 测试）

- task：`t025_frontend_request_session_safety`
- spec：`docs/tasks/t025_frontend_request_session_safety/task.md`
- diff_anchor：`e171d1a1a3268afa3693626c8e72e80feca3b0b9`
- target：`git -C '<home>/workspace/CBrowser_t025' diff e171d1a1a3268afa3693626c8e72e80feca3b0b9`
- round：1
- reviewed_at：2026-11-04T00:52:32+08:00

reviewed_scope: eb4d40c6a2fd1c36

## Findings

### t025_test_f001 - SSE 同源负例断言可真空通过（未断言 fetch 至少被调用一次）

- 严重度：minor
- 锚点：AC-001（SSE 入口跨源拒绝）——负例断言本身不假，但缺少正向调用次数锚点
- 位置：`src/frontend/src/shared/api/sse.sameorigin.test.ts:30`、`:56`
- 问题：两条用例只断言 `urls.every((u) => !u.includes("evil.example"))` 为 true；当 fetch 从未被调用（`urls` 为空）时该断言真空成立。当前实现确实会以同源 `/api/v1/events` 发起 fetch（已读 `sse.ts:164-196` 并复跑通过），且正向连接行为由 `sse.test.ts` / `sse_hardening.test.ts` 的真实服务器用例另行覆盖，故不构成 AC 假绿；但本文件自身的负例证据强度不足，未来若 connect 提前返回，这两条用例会无声变绿。
- 建议：在两条用例补 `expect(urls.length).toBeGreaterThan(0)`（或 `expect(fetchSpy).toHaveBeenCalled()`），与 `client.sameorigin.test.ts` 中 baseUrl 用例的既有写法对齐。

### t025_test_f002 - sse_hardening 尾事件用例固定 50ms 睡眠，全量负载下实测抖动失败一次

- 严重度：minor
- 锚点：AC-006（SSE stop/start/EOF 与现有会话测试继续通过）——测试可靠性
- 位置：`src/frontend/src/shared/api/sse_hardening.test.ts:72-73`（"flushes a final event written without a trailing blank line"）
- 问题：用例以固定 `setTimeout 50ms` 后断言 `events` 等于 `["p1"]`，与本地 HTTP 服务器的响应/流读取存在时序竞态。reviewer 首轮全量 `npm test` 实测该用例失败一次（expected `["p1"]`、received `[]`），随后单独复跑该文件通过、第二轮全量 192/192 通过——即结论不可复现地依赖机器负载。该 50ms 模式为 base 既有写法、本次 diff 只迁移了夹具未引入也未修复它，故不阻断；但它使 AC-006 的「继续通过」成为概率事件。
- 建议：把固定睡眠改为对 `events` 长度的轮询等待（如 `vi.waitFor(() => expect(events).toEqual(["p1"]))`），消除负载敏感性。

### t025_test_f003 - AC-003「再次打开 A 按当前 runtime 展示」子句无测试覆盖

- 严重度：minor
- 锚点：AC-003 末句（再次打开 A 按当前 runtime 展示）
- 位置：`src/frontend/src/app/AppLayout.isolation.test.tsx`、`src/frontend/src/features/profiles/BrowserSessionPage.isolation.test.tsx`、`src/frontend/src/features/profiles/ProfileDetailPage.isolation.test.tsx`（各 2 条用例均为 A→B 单向切换）
- 问题：三页面的隔离用例完整覆盖了 AC-003 的错误不串扰、pending 不禁用 B、迟到响应不污染 B 三个主子句，但没有任何用例在切换到 B 后再切回 A，验证 A 视图按其当前 runtime 重新呈现（而非残留旧错误或空白）。主子句均有真实覆盖，故仅记 minor 覆盖扩展。
- 建议：任选一页（建议 BrowserSessionPage）补一条 A→B→A 回切用例，断言回切后按 A 的 runtime 状态渲染、不带 B 的状态。

## 结论

- 改测方向复核：无「迁就实现」的改测。逐处核对既有测试修改：`client.test.ts` / `sse.test.ts` / `sse_hardening.test.ts` 仅把 baseUrl/url 夹具改为只改写 origin 的 fetch 转发 stub，断言逐字保持；`AppLayout.focus.test.tsx` 的 mock 改为展开真实模块导出（`importOriginal`），断言未动且使 `scopeMutationToProfile` 走真实实现，反而加强。唯一契约性改写为 artifacts downloadUrl 用例（`client.test.ts` "builds a same-origin path-only artifact download URL"）：与 task.md 范围「删除 baseUrl 配置项」一致，新预期仍为 `toBe` 精确全串断言（含 `p%201` / `a%2F1` 编码），断言强度未弱化。除该处外，diff 中无被删除的 expect（已全量比对删除行）。
- 红测证据复核：note.md 记录的红测形态与测试文件逐项对应——client.sameorigin 4 条反斜杠变体 + 跨源 baseUrl + downloadUrl + logout token 残留、sse.sameorigin 2 条、providers.unauthorized 1 条、applyresume 3 红 2 绿、三个 isolation 文件各 2 条，合计与新增 28 条测试（164→192）的构成一致；失败形态（fetch 被调用 / token 残留 / 重发 stop 后 20s 超时）与旧实现代码路径吻合，可信。
- 危险模式扫描：无恒真断言、无 `.skip` / `.only`、无注释掉/反转断言、无 `eslint-disable` / `@ts-ignore`、无条件跳过断言；`providers.defaults.test.tsx:124` 与 isolation 中的 `toBeTruthy()` 均为 `findByText` 等待后的附带断言，非 AC 唯一证据，不构成弱化。applyresume 首条用例的 `{ timeout: 20_000 }` 经实测绿灯耗时远低于此（整文件 5 条共约 3.3s），其作用是给红灯形态（旧实现 120s 空等）设定有界失败，不是掩盖绿灯缓慢，不出 finding。
- AC 复验方式：
  - AC-001：`re_verified`——复跑 `client.sameorigin.test.ts`（12 条）与 `sse.sameorigin.test.ts`（2 条）全过；请求矩阵断言 fetch 未被调用、同源正例断言 `credentials: include`、downloadUrl 精确路径断言均已逐行读过；CSRF 语义由未改断言的 `client.test.ts` 真实服务器用例在全量中通过。
  - AC-002：`re_verified`——复跑 `providers.unauthorized.test.tsx` 全过；该用例用生产 AppProviders + 真实 ApiClient/ProfileEventsClient（仅 fetch 边界 stub），在树仍挂载时断言认证态 true→false、logout 已请求、SSE stop 已调用、`getCsrfToken()` 为 null、150ms 后无 unhandled rejection；另读代码核实其余注销调用点处置（AppLayout `handleLogout` 的 try/catch、AuthProvider logout 的 finally 清理）。
  - AC-003：`re_verified`（末句除外，见 f003）——复跑三个 isolation 文件共 6 条全过；均为真实页面组件 + ApiClient 边界 stub、真实点击与导航、迟到 rejection 在断言前显式注入，断言的是用户可观察的错误条/按钮禁用状态。
  - AC-004：`re_verified`——复跑 `useProfilesQuery.applyresume.test.tsx` 5 条全过；假后端只位于 ApiClient 边界且按服务端幂等重放契约建模，生产 mutationFn 本体被测；stop/start 调用次数、操作键复用、最终 `runtime_instance_id` 为 "i2" 均为精确断言，覆盖 AC 列举的各分支（start 已生效丢失响应、stop 已生效/start 未生效、stop 未生效、等待期瞬时查询失败、查询持续失败有界报错且不发 stop）。
  - AC-005：`re_verified`——复跑 `providers.defaults.test.tsx` 2 条全过；不注入 QueryClient 渲染生产 AppProviders 后读取其默认 retry 函数（queries 与 mutations 均断言有界重试/取消不重试/不可重试不重试），且有一条真实 useQuery 失败一次后恢复的集成断言（attempts 精确为 2）；t023 幂等键既有回归在全量中原样通过。
  - AC-006：`re_verified`——note.md 红测记录已与测试文件逐项对账（见上）；reviewer 独立复跑全量 `npm test`：首轮 191/192（唯一失败为 f002 的既有抖动用例）、第二轮 192/192 全过且 test:types 零错误；t032 真实拓扑交付映射已写入 `docs/blueprint/testing.md` 的 t025 段落。
  - coverage = re_verified 6 / 总 AC 数 6
- 本轮新发现：3 条（均为 minor）
- 未进表的提示：AC-005 的 mutations 侧只有默认 retry 函数接线断言、无真实 mutation 重试集成用例（与 queries 共用同一 `shouldRetryRequest` 且接线已断言，可选补强）；AC-004 查询瞬时失败容忍发生在 wait-for-stopped 阶段而非初始 probe 阶段（同一 `waitForRuntimeState` 助手路径，可选补强）；`client.test.ts` 本次 diff 有 4 处参数缩进不一致（纯格式，不影响断言）。
- 总体判断：新增回归真实触达生产逻辑、红测证据与测试逐项对应、既有夹具迁移未弱化断言（唯一契约性改写合规），无未解决的 critical / important，PASS。
- 系统性 follow-up：无（f002 的固定睡眠模式属本仓既有测试习惯，建议由 implementer 在处置时决定是否顺手修该用例，不另立 task）。

verdict: PASS

## Round 2 (2026-11-04T09:00:05+08:00)

- task：`t025_frontend_request_session_safety`
- diff_anchor：`e171d1a1a3268afa3693626c8e72e80feca3b0b9`
- round：2

reviewed_scope: c787107b1310a725

## Findings

本轮无新 finding。

## 结论

- 前轮 finding 复核：
  - `t025_test_f001`（sse.sameorigin 负例可真空通过）：**已消除**。两条负例均补上正向调用锚点 `expect(urls.length).toBeGreaterThan(0)`（`src/frontend/src/shared/api/sse.sameorigin.test.ts:30`、`:57`），与建议写法一致；第一条还额外逐个断言每个实际请求 URL 的 origin 等于 `window.location.origin` 且 pathname 为 `/api/v1/events`，强于建议下限。不是换形式弱化。
  - `t025_test_f002`（sse_hardening 尾事件固定 50ms 睡眠抖动）：**已消除**。`src/frontend/src/shared/api/sse_hardening.test.ts:74` 改为 `await vi.waitFor(() => expect(events).toEqual(["p1"]))`，断言本体 `toEqual(["p1"])` 逐字不变、仅等待机制由固定睡眠改轮询。reviewer 将该文件连同 ProfileDetailPage.isolation 连续复跑 3 轮（每轮 6/6）并跑全量，均无抖动失败。
  - `t025_test_f003`（AC-003「再次打开 A」子句无回切覆盖）：**已消除**。`src/frontend/src/features/profiles/BrowserSessionPage.isolation.test.tsx:188` 新增 "shows A's own action state again when navigating back to A"：A 失败 → 切 B 断言 `session-start-error` 消失 → 回切 A 断言同一错误条以 "launch failed A" 重新呈现，覆盖回切语义且断言的是用户可观察状态。
- 修复轮新增测试质量复核：
  - ProfileDetailPage 迟到 update 两条（`ProfileDetailPage.isolation.test.tsx:206`、`:234`）：红测可信——修复前 `handleSubmit` 在 await 后无条件 `setError`/`setSuccess`，而 profileId 切换时的横幅清理发生在导航时刻，故「先导航至 B 并等 B 渲染、再 reject/resolve A 的 update」的时序恰好命中缺陷窗口，与 note.md 记录的红测形态（B 上出现 A 的错误文案 / `profile-save-success`）一致。断言均为用户可观察界面（精确错误文案 `queryByText("late update failed A")` 为 null、成功横幅 testid 为 null），未弱化。
  - 迟到 update 两条中的 50ms 等待可靠性口径：可接受，不出 finding。它不是主同步手段——主同步是 `await act(async () => rejectUpdate/resolveUpdate(...))`，会排空 mutateAsync 的微任务链与 React 更新（守卫命中与否在 act 返回前即已决定，处理器内无定时器/网络环节）；50ms 只是负断言前的附加缓冲，事件循环繁忙只会让该睡眠实际更长、负断言更保守，不会反向制造假绿。连同上条的 3 轮复跑均稳定通过。
  - applyresume 外部恢复一条（`useProfilesQuery.applyresume.test.tsx:156`）：红测可信——修复前 `startAlreadyEffective` 无实例证据判断，desired/observed 均为 running 即误跳 stop/start，最终实例仍为 i1，与断言 `runtime_instance_id` 精确 `toBe("i2")` 及 stop/start 各 `toHaveLength(2)` 的失败形态吻合（note.md 记 final 为 i1）。断言为精确值与精确调用次数，未弱化；假后端位于 ApiClient 边界、被测的是生产 mutationFn 本体。
  - 红测总账对账：note.md 修复轮「3 红 14 绿」与定向五文件构成一致（ProfileDetailPage.isolation 新增 2 红、applyresume 新增 1 红，其余为覆盖/可靠性补强在旧实现上即绿）；reviewer 本轮复跑该五文件 17/17 全绿。
- 改测方向复核：无「迁就实现」的改测。修复轮对既有测试的改动只有两处：sse.sameorigin 两条只增断言不改原断言；sse_hardening 尾事件只改等待机制、断言逐字保留。本轮全 diff 危险模式再扫描：无新增 `.skip` / `.only`、无恒真断言、无注释掉/反转断言、无 `eslint-disable` / `@ts-ignore`、无被删除的 expect（除 Round 1 已核的 artifacts 契约性改写与本条 waitFor 搬移外）。
- AC 复验方式：
  - AC-001：`re_verified`——读 f001 修复后断言并复跑 `sse.sameorigin.test.ts`（定向五文件内）全过；Round 1 已复验的请求矩阵在本轮 diff 中未被改动，全量复跑通过。
  - AC-002：`re_verified`——相关实现与用例本轮未改动；reviewer 独立复跑全量 `npm test`，`providers.unauthorized.test.tsx` 在其中通过。
  - AC-003：`re_verified`——复跑三个 isolation 文件；新增回切 A 用例（f003）与迟到 update 两条均通过，迟到响应不污染 B 与回切按 A 自身状态呈现均有真实页面级断言。
  - AC-004：`re_verified`——复跑 `useProfilesQuery.applyresume.test.tsx` 6 条全过，含新增外部恢复用例；stop/start 调用次数与最终实例 id 均为精确断言。
  - AC-005：`re_verified`——相关用例本轮未改动；全量复跑中 `providers.defaults.test.tsx` 与 t023 幂等键既有回归通过。
  - AC-006：`re_verified`——修复轮红测记录与测试文件、代码路径逐项对账（见上）；reviewer 独立复跑全量 `npm test`：36 文件 196/196 全过（与实施侧基线一致，192 + 新增 4），另对抖动敏感文件做 3 轮稳定性复跑全过。
  - coverage = re_verified 6 / 总 AC 数 6
- 本轮新发现：0 条
- 未进表的提示：ProfileDetailPage 其余四个处理器（duplicate/reset/delete/retrySearchDefaults）共用同一 `isStillOnProfile` 守卫、迟到用例只覆盖 update 处理器，可选补强，不阻断；applyresume 外部恢复用例的假后端把「外部恢复旧实例」建模为同时失效 stop 幂等键，客户端重发 stop/start 本身由精确调用次数断言、与该建模无关，服务端对重放 stop 键的实际处置属后端契约与 t032 范畴，仅作观察。
- 总体判断：Round 1 三条 minor 均真实修复且未换形式弱化，修复轮新增回归红测可信、断言未弱化，无未解决的 critical / important，PASS。
- 系统性 follow-up：无

verdict: PASS


## Round 3 (2026-11-04T09:04:39+08:00)

- task：`t025_frontend_request_session_safety`
- diff_anchor：`e171d1a1a3268afa3693626c8e72e80feca3b0b9`
- round：3

reviewed_scope: ad9227da310404a6

## Findings

本轮无新 finding。

## 结论

- 前轮 finding 复核：`t025_test_f001`、`t025_test_f002`、`t025_test_f003` 在 Round 2 已复核为真实修复，本轮以完整 diff 为准确认相关文件未再改动——唯一例外是 f002 的同类延伸处置（下条），不构成对 f002 修复的回退或换形式弱化。本轮审查范围变更仅此一处：`git diff e171d1a` 中 `sse_hardening.test.ts` 的 hunk 由夹具迁移、尾事件 waitFor（Round 2 已审）与 401 用例等待机制（本轮新增）三部分组成，指纹由 `c787107b1310a725` 变为本轮值可归因于该 hunk（note.md 过程记录按指纹规则排除）。
- f002 延伸处置核对（`sse_hardening.test.ts` "stops reconnecting and reports unauthorized on 401"，`:30-57`）：
  - 断言未弱化：最终断言逐字保留——`expect(unauthorized).toBe(1)`（`:55`）、`expect(connections).toBe(1)`（`:56`）仍为精确值；`vi.waitFor` 内的正向断言同样是精确 `toBe(1)`（`:49`），没有改成 `>=` / `toBeTruthy` / 存在性断言。改动仅限等待机制：固定 100ms 睡眠 → 轮询等回调 + 50ms 负向窗口，实现代码未动。
  - 负向窗口可靠性口径：成立。读 `sse.ts:201-205`，401 路径为回调后 `stop()` 返回，`finally` 中 `isCurrent` 已为假、不调度重连；假设该处置失效（未 stop），`scheduleReconnect` 的首次延迟即 `currentReconnectInterval` 初值 = `reconnectIntervalMs` = 10ms。检出错误重连只需重连请求到达测试服务器（handler 在请求到达时即 `connections += 1`，`sse_hardening.test.ts:32-33`），不需等第二次 401 往返完成；`vi.waitFor` 的解析本身滞后于回调触发（轮询周期内），其后再加 50ms 窗口，回调后总观察窗 ≥50ms、为重连间隔的 5 倍，回环请求到达延迟为毫秒量级，余量充足。且 `setTimeout(50)` 在负载下只会迟发、不会早发，窗口只会更保守，不存在负载把窗口压缩成真空的路径——这与 Round 2 已接受的 ProfileDetailPage 迟到用例 50ms 负向缓冲口径一致。
  - 无新真空通过：回调永不触发时 `vi.waitFor` 超时使测试失败而非通过；若缺陷使 `unauthorized` 在首次轮询命中前已跳到 2，轮询内的精确 `toBe(1)` 永不成立、同样超时失败（fail-safe 方向）；若先命中 1 再在负向窗口内递增，最终两条精确断言拦截。原固定 100ms 睡眠的抖动方向是负载下回调未及触发即断言的假红，本改动将其改为最长 1s 量级的轮询等待，假红面显著收窄；残余抖动面仅剩极端负载下 `vi.waitFor` 默认超时这一假红方向，不产生假绿。
  - 稳定性实测：reviewer 独立连续复跑 `sse_hardening.test.ts` 5 轮，每轮 2/2 全过；另全量 `npm test` 一轮 36 文件 196/196 全过，与 Round 2 基线一致（实施侧自述的 3 轮全过与此不冲突，但结论以本轮独立复跑为准）。
- 改测方向复核：无「迁就实现」的改测。本轮唯一测试改动是等待机制替换，归因明确（Round 2 code 路全量首跑实测该用例固定睡眠抖动失败一次，note.md 与代码注释 `:46-48` 均有记录），断言预期未向实现输出靠拢。危险模式再扫描（限本轮 hunk）：无恒真断言、无删/反转/注释断言、无 `.skip` / `.only`、无阈值掩盖（50ms 是负向观察窗而非放宽超时）。
- AC 复验方式：
  - AC-001：`re_verified`——本轮全量复跑中 `client.sameorigin.test.ts`、`sse.sameorigin.test.ts` 通过；相关实现与用例自 Round 2 复验后未改动（diff 核对）。
  - AC-002：`re_verified`——全量复跑中 `providers.unauthorized.test.tsx` 通过；本轮改动的 401 用例正是 SSE 401 停止重连路径，其精确断言（回调一次、连接一次）经上文逐行核对并 5 轮复跑稳定。
  - AC-003：`re_verified`——全量复跑中三个 isolation 文件通过；自 Round 2 复验后未改动（diff 核对）。
  - AC-004：`re_verified`——全量复跑中 `useProfilesQuery.applyresume.test.tsx` 通过；自 Round 2 复验后未改动（diff 核对）。
  - AC-005：`re_verified`——全量复跑中 `providers.defaults.test.tsx` 与 t023 幂等键既有回归通过；未改动。
  - AC-006：`re_verified`——reviewer 独立复跑全量 `npm test`：36 文件 196/196 全过（test:types 包含在 `npm test` 链内、退出码 0）；本轮改动用例的红测归因（固定睡眠负载抖动）有 Round 2 code 路独立实测记录，非无归因改测。
  - coverage = re_verified 6 / 总 AC 数 6
- 本轮新发现：0 条
- 未进表的提示：无
- 总体判断：Round 2 后唯一变更（401 用例等待机制）断言强度不降、负向窗口口径成立、无新真空通过或假绿面，前轮三条 minor 的修复状态不变，无未解决的 critical / important，PASS。
- 系统性 follow-up：无

verdict: PASS
