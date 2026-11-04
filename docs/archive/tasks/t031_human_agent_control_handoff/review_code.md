# Task review t031（reviewer_focus: 代码）

- task：`t031_human_agent_control_handoff`
- spec：`docs/tasks/t031_human_agent_control_handoff/task.md`
- diff_anchor：`09bfb3a0cbf90d55875c4f1abb18647e49b46d35`
- target：相对 diff_anchor 的完整 worktree 改动（`git diff 09bfb3a0cbf90d55875c4f1abb18647e49b46d35`，含已暂存的新增交付文件）
- round：1
- reviewed_at：2026-11-04T21:43:55+08:00

reviewed_scope: 08cddeb20ce183b2

## Findings

### t031_code_f001 - 对话框 peek/应答控制面缺少控制状态门禁，接管围栏存在旁路

- 严重度：important
- 锚点：AC-002（边界后外部 Agent 命令被拒绝、清理均无旁路；已建立隧道被关闭且重连被拒绝）
- 位置：`src/backend/cbrowser/api/v1/control_router.py:213`（`list_control_dialogs`）、`src/backend/cbrowser/api/v1/control_router.py:232`（`answer_control_dialog`）
- 问题：两条控制面端点只校验 automation token（`require_automation_token`），全程不读控制状态、不比对代次与身份。链路自 API 经 `RuntimeCoordinator.answer_attendant_dialog`、`supervisor/control_server.py:344` 的 Supervisor 应答端点直达 Agent `/control` 的 `answer_attendant_dialog`，沿途没有任何一跳校验 owner/generation。由此产生两条可复现的旁路：
  1. 第二 token 旁路：Agent A 持有控制期间，同一 Profile 的另一合法 automation token 可直接 peek 并应答 A 页面上的滞留 dialog，完全绕过 `claim` 的单 Agent 排他与会话身份比对。
  2. 接管后残留旁路：接管级联释放 attendant 只是 best-effort（`supervisor/core.py:1652` 的 `release_dialog_attendant` 失败返回 False），而 `control_server.py:344` 的 close-tunnels 无论 `attendant_released` 真假都返回 200，于是 `control_service.py` 的 handoff 判定 Supervisor 关闭成功、清除 `pending_supervisor_close`，之后永不重试 attendant 释放。只要当次释放失败，旧 token 就可在接管后无限期经此路径应答 dialog（accept/dismiss 含 prompt 文本输入均属浏览器侧动作）。
- 建议：最小修复是在 API 层两条端点接入控制服务：owner 为 user 时拒绝应答（接管后无控制权即无应答权）；owner 为 agent 时要求调用 token 与记录的 agent 身份一致（或至少与当前代次一致），并在接管级联中把 attendant 释放失败纳入 pending 重试（或 close-tunnels 返回非 200 以触发已有 pending 机制）。

### t031_code_f002 - Token 吊销/过期不触动控制状态与隧道，AC-001“身份失效回 user”无生产者

- 严重度：important
- 锚点：AC-001（旧 Agent 崩溃或身份失效后进入 user 安全状态）
- 位置：`src/backend/cbrowser/auth/service.py:285`（`revoke_automation_token`，只改 token 行与审计记录）；`src/backend/cbrowser/domain/models.py:553`（`identity_invalid` 原因字面量）
- 问题：全仓检索确认 `identity_invalid` 原因除字面量定义与 `RECLAIM_ALLOWED_REASONS` 表外没有任何生产者；`revoke_automation_token` 不调用控制服务、不关闭任何隧道。复现场景：Agent 持有控制并保持隧道在线时，管理面吊销其 token——新连接会被 `authorize_automation` 拒绝，但已建立的隧道继续投递命令、控制状态仍为 agent，身份失效并未回到 user 安全状态。过期 token 同理（`resolve_automation_token_id` 只影响新连接的 claim）。与之对照，重启（bind 时 `profile_restart`）与崩溃（observed `error` 时 `crash`）均已接线，唯独身份失效缺口未补。
- 建议：最小修复是在吊销路径（以及可行的过期清理点）接线控制服务：按该 token 持有控制的 Profile 执行一次 `handoff(reason="identity_invalid")`，复用已有隧道关闭级联与 SSE 广播；若吊销入口拿不到控制服务依赖，至少在吊销后使已登记隧道失效并记录该缺口由后续 task 闭环。

### t031_code_f003 - 前端 SSE 合并不比较代次，过期 SSE 可覆盖新代次状态

- 严重度：minor
- 锚点：AC-005（过期响应和 SSE 不覆盖新代次状态；仅前端合并侧）
- 位置：`src/frontend/src/features/profiles/useProfilesQuery.ts:423`
- 问题：`useProfileEventsSync` 的合并逻辑是 `event.control !== undefined ? event.control : old.control`，不比较 `generation`。SSE 流内有序时无害，但后台标签节流、重连快照与查询 refetch 交错时，旧代次事件可能晚于新代次缓存到达并把管理面控制显示打回旧状态（例如已恢复为 agent 却短暂显示为 user，或反之）。CLI 侧已实现 stale-response 围栏（`control_stale_generation`），前端侧缺失对应围栏。
- 建议：合并时仅当 `event.control.generation >= old.control.generation` 才覆盖；否则丢弃该事件的 control 字段。

### t031_code_f004 - handoff 成功后返回的响应体仍含旧 pending 标志，与 DB 不一致

- 严重度：minor
- 锚点：行为缺陷（响应体与持久化状态不一致）
- 位置：`src/backend/cbrowser/services/control_service.py:262`（`handoff`，`data` 在 `line 296-298` 的 `_set_pending` 二次提交前构造，`line 309` 原样返回）
- 问题：handoff 先提交 `pending_supervisor_close=True` 并构造返回体，Supervisor 关闭成功后再经 `_set_pending(False)` 二次提交；但返回的 `data` 仍是第一次提交的快照，`pending_supervisor_close` 为 True、`updated_at` 为旧值。调用方（CLI/管理面）据此会短暂误以为 Supervisor 关闭仍待重试，直到下一条 SSE 到达才纠正。SSE 本身因发布在二次提交之后是正确的，故仅影响直接响应体。
- 建议：二次提交后重新读取行（或直接在返回体上把 `pending_supervisor_close` 置为实际值并刷新 `updated_at`）再返回。

### t031_code_f005 - claim/handoff 请求体的 agent 身份字段被静默忽略，契约误导

- 严重度：minor
- 锚点：契约·类型（公开接口字段与实现行为不一致）
- 位置：`src/backend/cbrowser/api/v1/control_router.py:149`（`claim_control` 忽略 `body.agent_instance_id`，改用 token id）、`src/backend/cbrowser/api/v1/control_router.py:168`（`handoff_control` 传入的身份参数被 `handoff` 忽略）；`src/backend/cbrowser/domain/models.py` 的 `ControlClaimRequest`/`ControlHandoffRequest`
- 问题：请求模型提供 `agent_instance_id`/`agent_session_id`，但 claim 实际以 token id 作为实例身份、handoff 完全不使用身份参数（fail-open 设计本身合理）。调用方按模型字面传实例身份时会误以为已按该身份声明，而服务端按另一身份登记；排障时请求体与控制记录对不上。
- 建议：二选一——删除请求体中服务端不用的身份字段，或在文档注释中写明“claim 的实例身份恒取自 token，请求体身份字段被忽略”。handoff 的 fail-open 语义也应在字段注释中说明。

### t031_code_f006 - attendant 服务连接掉线不释放滞留状态，与模块文档承诺的生命周期不符

- 严重度：minor
- 锚点：行为缺陷（滞留 dialog 状态在连接掉线后过期残留）+ 文档与实现不一致
- 位置：`src/backend/cbrowser/runtime_agent/dialog_attendant.py:235`（`_run`）、`src/backend/cbrowser/runtime_agent/dialog_attendant.py:333`（`finally` 仅关闭 ws，未调用 `attendant.release()`）
- 问题：模块文档称 attendant 在“服务连接掉线”时释放，但 `_run` 的 `finally` 只关闭 websocket，不清 `_held`/`_session_targets`，`released` 标志也不置位。掉线重连后，旧会话 id 的滞留记录仍在：peek 会返回已无法应答的 dialog（新会话按链实测结论本就无法应答已打开的 dialog），而 `answer_dialog` 用过期 session id 应答失败返回 None 后，CLI 回落到 attach 路径，恰好撞上设计要避开的 Page.enable 挂起。
- 建议：`_run` 的 `finally` 中调用 `attendant.release()`（或至少清空 `_held`），使掉线后的 peek 不再报告过期 dialog；重连后新开 dialog 由新会话正常登记。

### t031_code_f007 - DialogAttendantService._run 圈复杂度超阈（手算）

- 严重度：minor
- 锚点：圈复杂度标准（新建函数一上来 ≥15 即 minor；无工具可用时手算 McCabe 近似）
- 位置：`src/backend/cbrowser/runtime_agent/dialog_attendant.py:235`
- 问题：`_run` 单函数内含消息分发、waiter 相关性、getTargets 挂接、五类事件分支及嵌套类型校验，手算圈复杂度约 25（含 `and` 短路分支；保守剔除短路计数仍高于 20）。目前未观测到由此导致的行为缺陷，故仅作 minor，不 blocking。
- 建议：后续重构时把 getTargets 响应处理与事件分发拆为独立小函数（例如 `_handle_response`、`_handle_event`），`_run` 只保留收发循环。

### t031_code_f008 - 控制 claim 缺乏 Profile 级串行化，并发冲突时以原始 DB 错误而非 409 呈现

- 严重度：minor
- 锚点：行为缺陷（错误码/状态码不一致；并发时序）
- 位置：`src/backend/cbrowser/services/control_service.py:200`（`claim`，两次独立会话间无锁、无行级串行化）；`src/backend/cbrowser/api/v1/control_router.py:94`（`_handle_control_error` 只映射控制类异常，其余原样抛出）
- 问题：两个 claim 并发交错读-改-写时，后提交方在 SQLite 写冲突下得到原始 DB 错误而非 `control_second_agent`/`control_conflict`：HTTP claim 端点表现为 500、CDP 握手路径表现为 1011 关闭，而非 AC 语义的 409/4403。未观测到静默双控（SQLite 写串行化使败者报错而非悄悄覆盖），故定 minor。
- 建议：给 claim/handoff/restore 加 Profile 级异步锁（与 `ProfileService` 的 per-profile 锁同类机制），或在端点层把 DB 忙/冲突类异常映射为 409 `control_conflict`（可重试语义）。

## 结论

- 前轮 finding 复核（Round 1，无前轮）：不适用。
- 本轮新发现：8 条（important 2 条，minor 6 条）。
- 未进表的提示：
  - 文件过大（结论段提示，不进表）：`src/backend/cbrowser/agent_executor/session.py`（1004 行，本 task 净增约 247 行）；`src/backend/cbrowser/stream_agent/policy.py`（860 行，净增约 91 行）；`src/backend/cbrowser/supervisor/core.py`（2283 行，净增约 97 行）；`src/backend/cbrowser/api/runtime_coordinator.py`（955 行，净增约 128 行）；`src/backend/cbrowser/runtime_agent/agent.py`（732 行，净增约 100 行）；`src/frontend/src/features/profiles/ProfileDetailPage.tsx`（640 行，净增约 97 行）。以上均为既有文件继续增高或跨 800 行阈值，未观测到由此直接导致的行为缺陷。
  - 复杂度 ≥10 提示：除 f007 的 `_run` 外，其余新函数均未达 15 阈值。
  - 范围外观察（不进表）：Supervisor 直连握手无 generation 头时视为基础设施信任调用、分区残留窗口，均已在 ADR 019（`docs/blueprint/decisions.md`）与 `docs/blueprint/security.md` 中如实记录为既定边界，本轮不将其判为缺陷；handoff 已为 user 时的幂等 no-op 不会重试 pending 的 Supervisor 关闭，重试依赖协调器 reconcile 轮次，若运行体长期无 reconcile 触发则 pending 可能滞留较久，建议实施侧确认 reconcile 触发面是否覆盖该场景；restore 会清除 `pending_supervisor_close` 而不补发一次 Supervisor 关闭，属同一 pending 语义的边角，建议与 f001 一并复核。
  - 已核实无问题的关键链路：API 为唯一 `profile_controls` 写方（除模型定义与控制服务外无其他写者）；迁移 `src/backend/migrations/versions/0009_profile_control_state.py` 的 `down_revision` 指向链上最新 0008；新旧两条 CDP 路径复用同一 `automation_cdp` 处理函数，控制 claim 对两者均生效；`make_runtime_response` 的全部调用点均已改为 await；Gateway 内部端点挂在带 `require_gateway` 的路由上；管理面恢复按钮、SSE control 字段校验与 OpenAPI/前端类型均已同步。
- 总体判断：两条 important 均为 AC 锚定的围栏缺口（控制面旁路与身份失效未回 user），修复前本 task 不可信，故 FAIL。
- 系统性 follow-up：无（f001/f002 均为本 task 内可修复的门禁缺口，不建议另立跨 task 条目）。

## AC 复验方式

- AC-001：re_verified。代码核对：默认态（`get_state` 未持久化时返回 user 默认）、bind 时 `profile_restart`、observed `error` 时 `crash`、claim 的第二 Agent 冲突与身份比对均已实现；但身份失效（吊销/过期）路径缺失，见 f002。
- AC-002：re_verified。代码核对：分类器触发/非触发两类、Gateway 转报、API 与 Supervisor 双层关闭、转发代次围栏、4403 拒绝均已实现；但对话框控制面旁路未被围栏覆盖，见 f001。
- AC-003：re_verified。代码核对：无重放逻辑；CLI 在 `control_handoff` 后跳过剩余步骤；会话 `close` 只 detach、不关闭页面。
- AC-004：trust_prior。代码核对仅覆盖云端可验部分：关闭级联只动两层隧道注册表，不触 Viewer 连接与浏览器生命周期；真实 WebRTC 多 Viewer 连续性依赖 t032 的 E2E 条目，本文未复验。
- AC-005：re_verified。代码核对：CLI stale-response 围栏、会话退出不关闭页面、显式恢复语义均已实现；前端 SSE 合并缺代次比较，见 minor f003。
- AC-006：re_verified。代码核对：attendant 持有 dialog 时不触发控制切换、CLI handOff 原因白名单、恢复须显式操作且无倒计时抢回均已实现；原生权限/验证码/2FA 的真实环境行为仍属 t032。
- AC-007：re_verified。代码核对：管理面展示控制方、代次、交接原因、身份与恢复入口，SSE 含 control 字段并经形状校验；ADR 019 说明了与 ADR 006/007 及存储规约的关系，ADR 006 的 `/manage` 表述已勘误；操控页未新增遮挡。
- AC-008：trust_prior。AC 本身是测试覆盖命题，属测试评审职责；本报告仅确认云端集成/单元测试文件已随改动交付，未独立复验其断言。

coverage = 6 / 8

verdict: FAIL

## Round 2 (2026-11-04T23:30:00+08:00)

- task：`t031_human_agent_control_handoff`
- spec：`docs/tasks/t031_human_agent_control_handoff/task.md`
- diff_anchor：`09bfb3a0cbf90d55875c4f1abb18647e49b46d35`
- target：相对 diff_anchor 的完整 worktree 改动（含已暂存的新增交付文件）
- round：2
- reviewed_at：2026-11-04T23:30:00+08:00
- 复核方式：逐条读 R1 处置表所指的生产代码（不采信处置表自述），并全量扫 R1 之后新增的控制面门禁、吊销接线、coordinator attendant 标志判定、core 空确认、dialog_attendant 拆分与 finally 释放、control_service 锁包装。

reviewed_scope: eacc2c9ec4e353ec

## Findings

### t031_code_f009 - 吊销接线按身份逐个交接时，单个 Profile 交接抛非 NotFound 异常会中断整批

- 严重度：minor
- 锚点：行为缺陷（多 Profile 吊销场景下的部分交接；R1 f002 修复引入的新边角）
- 位置：`src/backend/cbrowser/services/control_service.py:425`（`handoff_for_identity` 的逐个 `handoff` 循环）
- 问题：循环内只捕获 `ControlNotFoundError`（Profile 在扫描与交接之间被删）；若某一 Profile 的 `handoff` 抛其他异常（如 DB 会话/提交错误），异常直接穿出循环，后续同 token 控制的 Profile 不再交接，而 `src/backend/cbrowser/api/v1/auth_router.py:211` 的吊销端点只记一条日志就返回 204。单 Profile 场景（最常见）不受影响；多 Profile 同 token + 中途瞬时故障时才出现残留控制。
- 建议：循环内对单个 Profile 的非 NotFound 异常也记日志并继续处理下一个 Profile，吊销端点返回前汇总失败数（或至少让该残留可被后续 reconcile/重试发现）。

### t031_code_f010 - 对话框应答门禁为检查时序点，门禁通过后、应答到达前发生接管且 attendant 释放失败时存在残留窗口

- 严重度：minor
- 锚点：AC-002（边界后外部 Agent 命令被拒绝；残留窗口极窄，见问题段）
- 位置：`src/backend/cbrowser/api/v1/control_router.py:213`（`_require_dialog_agent` 检查点）经 `src/backend/cbrowser/api/runtime_coordinator.py:384`（`answer_attendant_dialog`）到 Agent 应答
- 问题：门禁只在 API 入口读一次控制状态，随后 coordinator → Supervisor → Agent 的多跳转发不再复核 owner/generation。正常接管路径下该窗口无害：接管级联会释放 attendant 并清空滞留 dialog，应答随后返回 404。窗口仅在 attendant 释放失败（pending 保持、reconcile 待重试）且释放失败原因不是 Agent 完全不可达时才成立——此时在途应答仍可能命中未清空的滞留 dialog。概率极低且需接管与应答精确交错，故定 minor，不 blocking。
- 建议：后续可在 coordinator/Supervisor 应答转发时携带门禁时的 generation 并在 Agent 侧或 Supervisor 侧复核一次；或在接管重试释放成功前由 API 层拒绝该 Profile 的对话框应答。

## 结论

- 前轮 finding 复核（逐条以代码为准，均已消除）：
  - t031_code_f001（important，已消除）：`src/backend/cbrowser/api/v1/control_router.py:213` 的 `_require_dialog_agent` 在 peek/应答两端点前置门禁——owner 非 agent 时 409 `control_not_agent`，第二 token 时 409 `control_second_agent`；`src/backend/cbrowser/api/runtime_coordinator.py:311` 的 `close_supervisor_tunnels` 仅当 Supervisor 回包 `attendant_released is True` 才确认关闭，释放失败则 pending 保持、由 `reconcile_profile_now` 重试整条级联；`src/backend/cbrowser/supervisor/core.py:1652` 的 `release_dialog_attendant` 在无 Agent 进程时返回 True（空确认），已 armed 且可达时按 Agent 200 确认。
  - t031_code_f002（important，已消除）：`src/backend/cbrowser/api/v1/auth_router.py:211` 的吊销端点在吊销提交后经 `src/backend/cbrowser/services/control_service.py:425` 的 `handoff_for_identity` 对该 token 持有控制的各 Profile 执行 `identity_invalid` 交接（正常隧道关闭级联 + SSE 广播）；`src/backend/cbrowser/api/app.py:186` 已把控制服务接线到可选依赖，吊销路径不会静默跳过；token 过期无独立清理点的残留已写入 `docs/specs/human_agent_control.md` 与 `docs/blueprint/security.md`（非本 task 新立项，与处置表一致）。
  - t031_code_f003（minor，已消除）：`src/frontend/src/features/profiles/useProfilesQuery.ts:423` 的 SSE 合并现为 `event.control.generation >= old.control.generation` 才覆盖，旧代次事件不再打回管理面显示；与 test f006 同题。
  - t031_code_f004（minor，已消除）：`src/backend/cbrowser/services/control_service.py:288` 的 `handoff` 在二次提交（pending 结算）与 API 隧道关闭、SSE 发布之后经 `get_state` 重读再返回，响应体不再含旧 pending 标志与旧 `updated_at`；Profile 中途被删时保留旧快照而不抛错。
  - t031_code_f005（minor，已消除）：`src/backend/cbrowser/domain/models.py:557`（`ControlClaimRequest`）与 `:570`（`ControlHandoffRequest`）的类注释已写明实例字段被忽略、claim 身份恒取 token、handoff 为 fail-open；OpenAPI 导出 `schemas/openapi/cbrowser_v1.json` 已同步含上述注释文本。
  - t031_code_f006（minor，已消除）：`src/backend/cbrowser/runtime_agent/dialog_attendant.py:339` 的 `_run` finally 现调用 `attendant.release()` 再关 ws，掉线后 peek 不再报告过期 dialog；`arm` 重连时经 `rearm` 清除 released 标志。
  - t031_code_f007（minor，已消除）：`_run` 已拆为 `src/backend/cbrowser/runtime_agent/dialog_attendant.py:235` 的 `_handle_response`（含 getTargets/attach 相关性）与 `:266` 的 `_handle_event`（含 targetCreated 的 pending_attach 登记，未漏），`_run` 只剩收发循环，圈复杂度已降至阈下。
  - t031_code_f008（minor，已消除）：`src/backend/cbrowser/services/control_service.py:214`（claim）、`:288`（handoff）、`:380`（restore）、`:467`（retry）均经 `_lock_for` 的 Profile 级异步锁串行化；并发认领败者为 `control_second_agent` 冲突（对应单测断言已见于 `tests/unit/test_control_service.py:257`），不再泄漏原始 DB 错误。
- 本轮新发现：2 条（minor 2 条：f009、f010；无 critical/important）。
- 未进表的提示：
  - 文件过大（结论段提示，不进表）：`src/backend/cbrowser/services/control_service.py`（491 行，本 task 新建即超 400 行 minor 阈值，未观测到由此导致的行为缺陷）；R1 已提示的其他大文件无新增超阈行为缺陷。
  - 复杂度 ≥10 提示：无（拆分后的 `_run` 及其两个 handler 均未达 15 阈值）。
  - 范围外观察（不进表）：`_require_dialog_agent` 在记录无实例 id 时 defer（与 claim 规则一致）；生产路径上隧道握手与显式 claim 均以 token id 作实例 id，故 defer 分支实际不可达，仅作防御。Supervisor 层对话框端点本身只验 Supervisor token（基础设施信任），控制边界在 API 层门禁，不另判缺陷。`restore` 清除 pending 而不补发关闭、handoff 幂等 no-op 后 pending 依赖 reconcile 重试，均为处置表已记录的既定语义，本轮不重复出 finding。
  - 已核实无问题的关键链路：吊销接线在 app 层真实接线（非仅路由默认值）；对话框门禁覆盖 peek 与应答两条端点且第二 token 测试断言已见于 `tests/integration/test_control_api.py:311`；吊销交接测试断言 `identity_invalid` 与 reclaim 关闭已见于同文件 `:343`；coordinator 空确认与非确认两分支测试已见于 `tests/unit/test_coordinator_close_flag.py:35` 与 `:51`；新改动六个关键生产文件经 `py_compile` 通过。
- 总体判断：R1 的两条 important 均已在代码层面消除，本轮仅有两条 minor 新边角，故 PASS。
- 系统性 follow-up：无（f009/f010 均为本 task 内可修的小边角，不建议另立跨 task 条目）。

## AC 复验方式

- AC-001：re_verified。代码核对：默认 user、重启/崩溃回 user、第二 Agent 冲突均在；本轮新增核对吊销路径 `identity_invalid` 接线真实存在且 app 层已接线，过期残留已如实写入规约与安全说明。
- AC-002：re_verified。代码核对：分类器、Gateway 转报、双层关闭、代次围栏均在；本轮新增核对对话框控制面门禁与 attendant 释放纳入 pending 确认；残留仅 f010 的极窄检查时序窗口。
- AC-003：trust_prior。沿用 R1 代码核对（无重放逻辑、CLI handoff 后停步）；本轮未重验该条的全部调用点。
- AC-004：trust_prior。云端可验部分（关闭级联只动隧道注册表）与 R1 一致；真实 WebRTC 多 Viewer 连续性仍属 t032。
- AC-005：re_verified。代码核对：handoff 返回结算后重读（f004 修复）与前端 SSE 代次守卫（f003 修复）均已落地；CLI stale-response 围栏与 R1 一致。
- AC-006：re_verified。代码核对：attendant 掉线释放（f006 修复）与拆分（f007 修复）均已落地；原生权限/验证码/2FA 真实环境行为仍属 t032。
- AC-007：re_verified。代码核对：管理面展示与 SSE control 字段与 R1 一致；本轮新增核对规约与安全说明已记录 f001/f002 的修复语义。
- AC-008：trust_prior。AC 本身是测试覆盖命题，属测试评审职责；本报告仅确认修复相关的集成/单元测试文件已随改动交付并含对应断言，未独立复验其全部断言。

coverage = 5 / 8

verdict: PASS

## Round 3 (2026-11-04T23:36:00+08:00)

- task：`t031_human_agent_control_handoff`
- spec：`docs/tasks/t031_human_agent_control_handoff/task.md`
- diff_anchor：`09bfb3a0cbf90d55875c4f1abb18647e49b46d35`
- target：本轮窄范围复核，仅 f009 修复、f010 遗留处置与本轮指纹三项，不重审全部改动
- round：3
- reviewed_at：2026-11-04T23:36:00+08:00
- 复核方式：逐行读本轮所指的生产代码与处置行（不采信处置表自述）；指纹按仓库内 review 指纹 checker 方法重算（该方法排除 task 目录的过程文件，含本报告文件自身，故本节写入不改变指纹）

reviewed_scope: de621b4faa4495d9

## Findings

本轮新发现：0 条。

## 逐项核查

### 1. f009 修复：通过

- 位置：`src/backend/cbrowser/services/control_service.py:425`（`handoff_for_identity`），循环体在 `:451-462`。
- 核实：扫描谓词未变（owner 为 agent 且实例 id 等于被吊销 token）；循环内先捕获 `ControlNotFoundError` 后继续，再以通用异常分支记 `logger.warning`（含 profile id）后继续，`handed` 仅在交接成功时追加。单 profile 异常不再穿出循环中断整批，其余同 token Profile 仍被交接。
- 无行为回归：失败 Profile 仍保持 agent（未被误标为已交接）；`handoff` 自身的逐 profile 锁与隧道关闭级联未动；通用异常分支只捕获 `Exception`，不吞掉取消信号；扫描与返回语义除“失败项不再中断整批”外无其他变化。
- 对应测试：`tests/unit/test_control_service.py` 的 `test_handoff_for_identity_isolates_per_profile_failures` 断言失败 Profile 被排除在返回外、另一 Profile 交接为 user、失败 Profile 仍为 agent，与代码一致。本轮环境无 pytest 可用，故该测试未在本轮重跑，仅以代码与断言原文核对；`control_service.py` 经 `py_compile` 通过。

### 2. f010 遗留处置：合理，指向明确

- 位置：`docs/tasks/t031_human_agent_control_handoff/note.md` Round 2 处置行（f010 记为遗留，指向 t032）。
- 正常路径中和成立：接管级联经 `src/backend/cbrowser/supervisor/core.py:1652` 的 `release_dialog_attendant` 调 Agent `/control` 的 `release_attendant`（`src/backend/cbrowser/runtime_agent/agent.py:335`），最终调 `src/backend/cbrowser/runtime_agent/dialog_attendant.py:112` 的 `release()` 清空滞留记录与会话目标；此后在途应答因无滞留记录返回空，经 Agent 404、Supervisor 与协调器逐层回落为空，最终由 `src/backend/cbrowser/api/v1/control_router.py:297` 以 404 拒绝。且接管后新到的应答请求在门禁处即因 owner 非 agent 被 409 拒绝，故残留窗口确如处置所述仅限“门禁已通过、在途应答尚未到达”且 attendant 释放失败（pending 保持、待 reconcile 重试）的交错情形。
- 彻底闭合需 Agent 侧围栏的理由成立：规约 `docs/specs/human_agent_control.md` 已写明 attendant 状态 v1 不进管理面、Agent 无 API 直连通道；在途应答转发链（协调器→Supervisor→Agent）现无携带门禁代次并复核的通道，本地小修无法闭合，须随通道设计一并做。
- 指向明确：处置行指向 t032，规约同文件的 t032 交接节列有 attendant 通道设计条目，可定位到后续工作；措辞上规约条目名为 attendant 管理面暴露通道设计，与处置行“attendant 通道设计”非逐字相同，但所指为同一通道设计工作，不影响定位。

### 3. Scope 指纹：一致

- 本轮写入前以 checker 方法重算当前 worktree 指纹为本节所载值；该 checker 排除 task 目录过程文件（`note.md`、本报告文件、`review_test.md`）及 pending/findings/archive 等流程路径，故本节追加本身不改变指纹。

## 结论

- 前轮 finding 复核（仅本轮范围）：f009 已按 R2 建议在代码层面消除（逐 profile 隔离、记日志、继续整批）；f010 未修但遗留理由成立、指向明确，按 minor 遗留处理，不阻断。
- 本轮新发现：0 条（无 critical/important）。
- 未进表的提示：
  - f009 失败 Profile 的残留目前仅见于日志行：吊销端点沿用 R2 已有行为丢弃返回的已交接清单（非本轮改动引入），日志行亦未附异常堆栈；残留的发现面仍为日志与人工重试，不影响本轮“隔离、记日志、继续整批”的判定口径。
  - f010 处置行与规约条目的措辞非逐字相同（见上），定位无歧义，不另立 finding。
- 总体判断：三项全过且无新发现，故 PASS。

verdict: PASS
