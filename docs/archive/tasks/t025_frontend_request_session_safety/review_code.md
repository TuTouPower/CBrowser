# Task review t025（reviewer_focus: 代码）

- task：`t025_frontend_request_session_safety`
- spec：`docs/tasks/t025_frontend_request_session_safety/task.md`
- diff_anchor：`e171d1a1a3268afa3693626c8e72e80feca3b0b9`
- target：`git -C '<home>/workspace/CBrowser_t025' diff e171d1a1a3268afa3693626c8e72e80feca3b0b9`
- round：1
- reviewed_at：2026-11-04T08:51:16+08:00

reviewed_scope: eb4d40c6a2fd1c36

## Findings

### t025_code_f001 - ProfileDetailPage 本地动作处理器未按 Profile 隔离，A 的迟到响应仍污染 B

- 严重度：important
- 锚点：AC-003——「Profile A 的动作失败或未结束时切换到 B：B 不显示 A 的错误……A 的迟到响应不污染 B」；`scopeMutationToProfile` 只隔离了 mutation 的 `isPending/isError/error` 呈现，详情页另一条动作结果通道（本地 `error`/`success` state）不在隔离内。
- 位置：`src/frontend/src/features/profiles/ProfileDetailPage.tsx:60-66`（切换时重置）、`src/frontend/src/features/profiles/ProfileDetailPage.tsx:99-186`（`handleDuplicate`/`handleReset`/`handleRetrySearchDefaults`/`handleSubmit`/`handleDelete` 的 await 后无条件写本地 state）
- 问题：五个处理器均为 `await mutateAsync(捕获的 profileId)` 后无条件 `setError(...)` / `setSuccess(true)`，await 前后不校验当前 `profileId` 是否仍是发起动作的 Profile。可复现失败场景：在 A 提交保存（`handleSubmit`，请求挂起）→ 路由切到 B（`useEffect` 于 `:60-66` 先清掉 error/success）→ A 的请求随后失败，catch 在 `:172` 执行 `setError(A 的错误文案)`，B 的页面随即渲染该通用错误横幅（`:348` 的 `{error && ...}`）；A 的请求随后成功则在 `:168-169` 清掉共享 `dirtyFields` 并 `setSuccess(true)`，B 显示 A 的成功横幅，且 B 在切换后刚标记的 dirty 字段被清掉、后续 profile 数据 effect 可覆盖 B 的未保存编辑。reset/retry/duplicate/delete 的迟到失败同理写 `setError`（`:107/:120/:130/:184`）。现有 `ProfileDetailPage.isolation.test.tsx` 只覆盖 apply（`.mutate` 通道），未覆盖这条本地 state 通道。
- 建议：处理器在 await 后写本地 state 前捕获并比对发起时的 profileId（与当前 `profileId` 不一致时丢弃本地横幅写入；`dirtyFields.current.clear()` 同样只应在仍为同一 Profile 时执行），或把这些结果也改为按目标 Profile 呈现；补一条「A 的 update/reset 迟到失败/成功不污染 B」的回归用例。

### t025_code_f002 - ApplyStage.preStopInstanceId 只写不读，与「保存 stop 前实例用于识别新实例」的文档口径不符

- 严重度：minor
- 锚点：行为缺陷（死状态/文档与实现不一致）——范围区与 `docs/specs/profile_management.md` t025 节均称阶段保存 stop 前 `runtime_instance_id` 并据此「识别 desired=running 的新实例」，但实现从未读该字段做任何判定。
- 位置：`src/frontend/src/features/profiles/useProfilesQuery.ts:231`（字段声明）、`src/frontend/src/features/profiles/useProfilesQuery.ts:241`（初始化）、`src/frontend/src/features/profiles/useProfilesQuery.ts:308`（唯一写入点，全仓无读取点）
- 问题：`startAlreadyEffective`（`useProfilesQuery.ts:319-324`）只凭 `stage.startRequested && desired_state==="running" && observed_state∈{running,starting}` 判定，未比较 `runtime_instance_id` 与 `preStopInstanceId`。已覆盖的幂等重放模型下该启发式可收敛（本轮 applyresume 5 条用例复跑通过），故不构成已证实的 AC-004 失败；但保存的实例 id 是死状态，文档宣称的「新实例识别」实际未发生，未来若出现同 desired/observed 而实例未更换的中间态（如 stop 后旧实例被外部恢复），该判定无从区分。
- 建议：二选一——在 `startAlreadyEffective` 中真正使用实例比较（如要求 `runtime_instance_id !== preStopInstanceId` 或实例为空时的明确回退语义）并补对应用例；或删除该字段并同步 spec/blueprint 口径为「仅以 desired/observed 判定」。

## 结论

- 前轮 finding 复核：Round 1，无前轮。
- 本轮新发现：2 条（important 1、minor 1、critical 0）。
- 未进表的提示：文件过大——`src/frontend/src/shared/api/client.ts` 408 行（基线 400 行、本 task 净增至刚过实现源码 400 行 minor 阈值）、`src/frontend/src/features/profiles/ProfileDetailPage.tsx` 519 行（基线已 502 行、本 task 净增 17 行）；按标准只作提示，拆分与否由实施侧评估，不进 finding 表。圈复杂度：本 task 触及函数手算均 <10（apply mutationFn 约 7），无提示项。安全/契约/性能/健壮性其余视角已扫：同源判定在 fetch 前完成且删除 baseUrl/url 配置项无残留引用（全仓 grep 仅剩测试以 `as never` 传入被忽略的配置验证拒绝行为）；注销调用点仅 AppLayout（try/catch）与 providers SSE 回调（`.catch(() => undefined)`）两处，均有明确处置；未发现范围外改动或新增跨源面。
- AC 复验方式：
  - AC-001：re_verified——读 `same_origin.ts`/`client.ts:request,downloadUrl`/`sse.ts:connect` 实现，复跑 `client.sameorigin.test.ts`（12 条）与 `sse.sameorigin.test.ts`（2 条）全过；跨源在 fetch 前抛 `ApiError(0)`、downloadUrl 只返回同源 path。
  - AC-002：re_verified——读 `providers.tsx:20`、`client.ts:381-390` logout try/finally、`useAuth.tsx:64-71` finally 清状态、AppLayout `:94-100` catch；复跑 `providers.unauthorized.test.tsx`（1 条，真实 SSE 客户端 + 生产 AppProviders，挂载态断言）通过。
  - AC-003：re_verified——scoped mutation 通道复跑三页 isolation 测试共 6 条全过；但按代码独立核查发现详情页本地 state 通道未隔离（见 t025_code_f001），本 AC 实际未完整实现。
  - AC-004：re_verified——读 `useProfilesQuery.ts` apply mutationFn 阶段续跑逻辑，复跑 `useProfilesQuery.applyresume.test.tsx` 5 条全过（start 已生效响应丢失、stop 已生效、stop 未生效、等待期瞬时失败、持续失败有界报错且不发 stop）。
  - AC-005：re_verified——生产 `providers.tsx` 默认 QueryClient 的 queries/mutations 均接 `shouldRetryRequest`（基线已有接线，本 task 补测），复跑 `providers.defaults.test.tsx` 2 条全过。
  - AC-006：trust_prior——红测阶段「修复前失败」的证据只能依赖 note.md 中实施侧记录的失败用例名与命令（已核对记录存在且具体）；绿测阶段由本 reviewer 独立复跑：`npm run test:types` 零错误、Vitest 全量 36 文件 192 条全过。
  - coverage = 5 / 6
- 总体判断：同源边界、注销处置、apply 阶段续跑与默认 retry 均真实落地且复跑通过，但 AC-003 在 ProfileDetailPage 仍有一条未隔离的动作结果通道（important），当前不可 PASS。
- 系统性 follow-up：无

verdict: FAIL


## Round 2 (2026-11-04T09:00:28+08:00)

- round：2
- reviewed_at：2026-11-04T09:00:28+08:00

reviewed_scope: c787107b1310a725

## Findings（Round 2）

无新 finding。本轮未发现新引入的 critical / important / minor 问题；下述两条为前轮 finding 的复核结论，不新占编号。

## 结论（Round 2）

- 前轮 finding 复核：
  - t025_code_f001（important）：**已消除**。以 diff/代码为准：`ProfileDetailPage.tsx:62-64` 新增 `activeProfileIdRef`（渲染期同步为当前路由 `profileId`）与 `isStillOnProfile`；五个本地处理器均先捕获 `targetId`，await 后的全部本地写入均受守卫——`handleDuplicate` 导航（`:112`）与 `setError`（`:115`）、`handleReset` 的 `setResetOpen/setSuccess`（`:126`）、success 定时器回调内层守卫（`:129-131`）与 `setError`（`:133`）、`handleRetrySearchDefaults` 的 `setError`（`:145`）、`handleSubmit` 的 `dirtyFields.current.clear()`（`:185`，在守卫 `:185` 检查之后）、`setSuccess` 与定时器内层守卫（`:188-190`）、`setError`（`:192`）、`handleDelete` 的导航（`:204`）与 `setError`（`:207`）。A→B→A 回切时守卫按「当前即目标」放行，迟到结果只落在目标 Profile 本人页面，符合 AC-003 语义。新增回归 `ProfileDetailPage.isolation.test.tsx` 的 late update failure / late update success 两条本 reviewer 独立复跑通过（见下），f001 的失败场景（B 显示 A 错误横幅、迟到成功清 B 的 dirtyFields 并显示成功横幅）不再成立。
  - t025_code_f002（minor）：**已消除**。`ApplyStage.preStopInstanceId` 不再只写不读：`useProfilesQuery.ts:320-325` 的 `instanceEvidence` 真实读取该字段——新旧 `runtime_instance_id` 均已知时须不同才计入 `startAlreadyEffective`（`:326-331`），任一未知时回退 desired/observed 判定，与任务口径一致；`docs/specs/profile_management.md` t025 节已同步为同一表述（「新实例」的认定在新旧实例 id 均已知时要求二者不同，任一未知回退 desired/observed）。新增回归 `useProfilesQuery.applyresume.test.tsx` 的「does not skip stop/start when the pre-stop instance was externally restored」本 reviewer 独立复跑通过：旧实例被外部恢复时重试走完整 stop/start（stop/start 各 2 次）并收敛到新实例 `i2`，未误跳。
- 本轮新发现：0 条。
- 未进表的提示：文件过大——`src/frontend/src/features/profiles/ProfileDetailPage.tsx` 543 行（本轮继续净增、已过实现源码 400 行 minor 阈值）、`src/frontend/src/shared/api/client.ts` 408 行、`src/frontend/src/features/profiles/useProfilesQuery.ts` 411 行（三者均刚过阈值，按标准只作提示、不进 finding 表，拆分与否由实施侧评估）。圈复杂度：本轮触及函数手算均 <10，无提示项。范围外观察（测试层，归 test 路）：本 reviewer 第一次全量 `npm test` 时 `sse_hardening.test.ts` 的「stops reconnecting and reports unauthorized on 401」一条失败（`sse_hardening.test.ts:44-46` 仍用固定 100ms 睡眠等回调，全量负载下抖动）；该文件单独复跑 3/3 通过、第二次全量复跑 36 文件 196 条全过，判为负载抖动而非实现回归——t025_test_f002 当时只把尾事件用例改成轮询，此 401 用例的固定睡眠建议 test 路后续一并改轮询，不构成 code 路 finding。
- AC 复验方式：
  - AC-001：re_verified——同源实现（`same_origin.ts`/`client.ts`/`sse.ts`）与 Round 1 复核一致且本轮未被修复轮改动；第二次全量复跑中 `client.sameorigin.test.ts`、`sse.sameorigin.test.ts` 全过。
  - AC-002：re_verified——`providers.tsx` 的 `.catch(() => undefined)` 处置与 logout finally 清 token 与 Round 1 一致；全量复跑中 `providers.unauthorized.test.tsx` 通过。
  - AC-003：re_verified——本轮重点复验：读 `ProfileDetailPage.tsx` 五个处理器的 targetId 守卫（见 f001 复核），定向复跑 `ProfileDetailPage.isolation.test.tsx` 4 条全过（含新增 late update 两条）；三页 scoped mutation 通道与 Round 1 一致，全量复跑中 BrowserSessionPage/AppLayout/ProfileDetailPage 三组 isolation 测试全过。Round 1 指出的本地 state 通道缺口已补齐，本 AC 现完整实现。
  - AC-004：re_verified——读 `useProfilesQuery.ts:296-360` 阶段续跑与 `instanceEvidence` 逻辑，定向复跑 `useProfilesQuery.applyresume.test.tsx` 6 条全过（含新增 externally restored 一条；start 已生效收敛、stop 已生效跳过、stop 未生效重跑、瞬时查询失败容忍、持续失败有界报错且不发 stop 均保持）。
  - AC-005：re_verified——生产 AppProviders 默认 retry 接线与 Round 1 一致；全量复跑中 `providers.defaults.test.tsx` 2 条通过。
  - AC-006：trust_prior——修复轮「修复前失败」的红测证据只能依赖 note.md 实施笔记记录（已核对：late update 两条全红、externally restored 一条红、合计 3 红 14 绿，记录具体）；绿测阶段由本 reviewer 独立复跑：定向两文件 10/10 通过，`npm test`（= test:types 零错误 + Vitest）第二次全量 36 文件 196 条全过（基线口径 192 + 新增 4）。
  - coverage = 5 / 6
- 总体判断：Round 1 的两条 finding（important 1、minor 1）均已按 diff/代码核实真实修复且有先红后绿回归锁定，本轮无新 blocker；同源边界、注销处置、apply 阶段续跑（含新实例证据判定）与按 Profile 隔离（含详情页本地横幅通道）均成立。
- 系统性 follow-up：无（sse_hardening 401 用例固定睡眠改轮询属 test 路既有 f002 同类小事，已在上文提示，不另立项）。

verdict: PASS


## Round 3 (2026-11-04T09:02:32+08:00)

- round：3
- reviewed_at：2026-11-04T09:02:32+08:00

reviewed_scope: ad9227da310404a6

## Findings（Round 3）

无新 finding。本轮未发现新引入的 critical / important / minor 问题。

## 结论（Round 3）

- 变更范围核对（本轮核心）：**与任务交代一致，Round 2 后仅一处同类延伸改动**。核对依据三方吻合——(1) Round 2 报告对 `src/frontend/src/shared/api/sse_hardening.test.ts` 的范围外观察记录：当时尾事件用例已改 `vi.waitFor` 轮询、401 用例仍为固定 100ms 睡眠且全量首跑抖动一次；(2) note.md 实施笔记末行与「Review 处置」t025_test_f002 行记录的处置缘由（按 f002 同类延伸、正向等待改轮询、保留 50ms 负向窗口、断言不变）；(3) 当前文件实况：401 用例位于 `sse_hardening.test.ts:44-55`，正向等待为 `await vi.waitFor(() => expect(unauthorized).toBe(1))`（`:49`）、其后保留 50ms 负向窗口（`:50`），尾事件用例（`:81`）与同源夹具迁移部分均与 Round 2 已审状态一致。完整 diff（27 文件）其余部分与 Round 2 报告描述的已审状态逐项一致（f001 的 `activeProfileIdRef`/`targetId` 守卫、f002 的 `instanceEvidence`、同源三入口、注销处置、apply 阶段续跑均在且未再改动），未发现 Round 2 之外的实现或测试变更混入。
- 该改动无实现影响、401 语义断言未变：改动只落在测试文件，不触任何生产代码；断言与 Round 2 前完全相同——`expect(unauthorized).toBe(1)` 与 `expect(connections).toBe(1)`（`:54-55`）。正向等待由固定 100ms 睡眠改为轮询至回调实际发生，严格强于原等待（不再依赖负载下的固定时长）；50ms 负向窗口在 `reconnectIntervalMs: 10` 下覆盖约 5 个重连间隔，401 后若错误重连仍会被 `connections` 计数捕获，原「停止重连」语义的负向检查未被弱化；`client.stop()` 位置与原一致。不属于阈值增大掩盖问题或弱化断言（等待机制变更、断言与期望值原样）。
- 前轮 finding 复核：t025_code_f001（important）与 t025_code_f002（minor）在本轮 diff 中仍为 Round 2 已核实修复状态，未被本轮改动触及，保持已消除。
- 本轮新发现：0 条。
- 未进表的提示：文件过大——`src/frontend/src/features/profiles/ProfileDetailPage.tsx` 543 行、`src/frontend/src/features/profiles/useProfilesQuery.ts` 411 行、`src/frontend/src/shared/api/client.ts` 408 行，均刚过实现源码 400 行 minor 阈值，与 Round 2 口径一致，按标准只作提示、不进 finding 表。圈复杂度：本轮触及函数手算均 <10，无提示项。安全/正确性/契约·Breaking/性能·资源/架构·可维护性/健壮性·可观测/规格一致性其余视角已扫：本轮延伸改动不新增任何出站入口、凭据面或公开签名，无新命中。
- AC 复验方式：
  - AC-001：re_verified——同源实现与前两轮一致且未被本轮改动；本轮全量复跑中 `client.sameorigin.test.ts`、`sse.sameorigin.test.ts` 全过。
  - AC-002：re_verified——`providers.tsx` 的 `.catch(() => undefined)` 处置与 logout finally 清 token 与前轮一致，全量复跑中 `providers.unauthorized.test.tsx` 通过；与本轮改动直接相关的 `sse_hardening.test.ts` 401 用例本 reviewer 独立连跑 3 轮均 2/2 通过（unauthorized 恰一次、不重连），Round 2 记录的全量负载抖动在本轮全量复跑中未再现。
  - AC-003：re_verified——三页 scoped mutation 与 ProfileDetailPage 本地通道守卫与 Round 2 核实状态一致；全量复跑中 BrowserSessionPage/AppLayout/ProfileDetailPage 三组 isolation 测试全过。
  - AC-004：re_verified——`useProfilesQuery.ts` 阶段续跑与 `instanceEvidence` 逻辑未变；全量复跑中 `useProfilesQuery.applyresume.test.tsx` 全过。
  - AC-005：re_verified——生产 AppProviders 默认 retry 接线未变；全量复跑中 `providers.defaults.test.tsx` 2 条通过。
  - AC-006：trust_prior——「修复前失败」的红测证据只能依赖 note.md 实施笔记记录（前两轮已核对具体）；绿测阶段由本 reviewer 独立复跑：`sse_hardening.test.ts` 定向连跑 3 轮全过、`npm test` 全量 36 文件 196 条全过（与 Round 2 后基线口径一致，含 test:types）。
  - coverage = 5 / 6
- 总体判断：Round 2 后唯一 scope 变更为 sse_hardening 401 用例的同类轮询改造，无实现影响、断言未变、原抖动在本轮定向连跑与全量复跑中均未再现；前轮两条 finding 保持已消除，本轮无新 blocker。
- 系统性 follow-up：无

verdict: PASS
