---
tid: "t031"
slug: "human_agent_control_handoff"
title: "落实真人优先的 Agent 控制权与安全交接"
status: "done"
branch: "t031_human_agent_control_handoff"
worktree: ""
review_level: "full"
review_limit: "5"
verify_limit: "5"
diff_anchor: "09bfb3a0cbf90d55875c4f1abb18647e49b46d35"
depends_on: "t026,t030"
conflicts_with: "t025"
note: "来源 p029；消费 t030 的 Dialog/页面保护接口；云端 Muse，真实环境执行交 t032"
---

# Task 进展

front matter 只经 `task.py` 修改；reviewer 只写对应 `review_*.md`。

## 实施笔记

执行期记录关键步骤、决策、验证、阻塞和用户批准的新轮次上限。

创建期不预测实施步骤。只记有追溯价值的内容；无事项时写“无”。

- 2026-11-04：从 p029；消费 t030 的 Dialog/页面保护接口 聚合立项，核实基线 main@c6a9322；只创建 backlog，不 start。
- 云端范围与本地最终 t032 分离；真实环境未执行不能按通过回填。
- 2026-11-04：按三方审阅修订：硬依赖改为 t026、t030；写入用户决定的接管触发语义（前台点击/按键/滚轮/IME 提交，纯移动不触发）；补输入上报通路、API/Supervisor 活动隧道注册表、迁移与 schema、/manage 不存在的修正。

## Review 处置

每个结构化 finding 一行。`已修` 表示本 task 已修复；`遗留` 必须指向 `pNNN` 或 follow-up tid；`撤回` 必须写清理由。critical/important 未解决时不得 PASS。

### Round 1 (2026-11-04T21:43:55+08:00，code FAIL + test FAIL)

|finding_id|severity|status|rationale|fix_ref|
|---|---|---|---|---|
|t031_test_f001|important|已修|驱动真实 Stream 钩子（分类→前台→上报组装）、真实 StreamAgent 构造器接线、真实 Gateway app 泵分支（转发 + 失败不致命）|tests/unit/test_stream_takeover_chain.py、tests/unit/test_gateway_takeover_pump.py|
|t031_test_f002|important|已修|_setup 只把 Docker ping 缺失当 skip，harness.start() 失败直接传播为失败|tests/e2e/test_control_handoff_e2e.py|
|t031_test_f003|minor|已修|新增 0008→0009 带已有 profile 数据升级用例，断言原 profile 完好且控制态默认 user/0|tests/unit/test_control_migration.py|
|t031_test_f004|minor|已修|AC-002 注收紧：云端证据只到注册表关闭/级联确认/claim-fence 层，真实 WS 4403 层归 t032 E2E|docs/tasks/t031_human_agent_control_handoff/task.md|
|t031_test_f005|minor|已修|链测试 dialog 持有后与应答前各读一次控制态，断言 owner 仍为 agent 且代次未变|tests/integration/test_control_attendant_chain.py|
|t031_test_f006|minor|已修|前端 SSE 合并加代次守卫（旧代次事件不覆盖新缓存）+ 守卫单测|src/frontend/src/features/profiles/useProfilesQuery.ts、useProfilesQuery.control.test.tsx|
|t031_test_f007|minor|已修|SSE 事件→缓存→面板组装测试：hook 级合并单测 + 详情页面级 SSE 刷新单测|useProfilesQuery.control.test.tsx、ProfileDetailPage.control.test.tsx|
|t031_code_f001|important|已修|控制面 peek/应答加控制权门禁（user 态或第二 token 一律 409）；Supervisor close 仅隧道关闭 + attendant 释放双确认才清 pending，无 Agent 进程时为空确认|src/backend/cbrowser/api/v1/control_router.py、api/runtime_coordinator.py、supervisor/core.py、tests/integration/test_control_api.py、tests/unit/test_coordinator_close_flag.py|
|t031_code_f002|important|已修|吊销 token 时该 token 持有控制的 Profile 各执行 identity_invalid 交接；token 过期无独立清理点属已知残留，记入规约/安全说明（非新立项）|src/backend/cbrowser/api/v1/auth_router.py、services/control_service.py、docs/specs/human_agent_control.md、docs/blueprint/security.md|
|t031_code_f003|minor|已修|与 test f006 同题：前端 SSE 合并代次守卫 + 单测|同 test f006|
|t031_code_f004|minor|已修|handoff 返回结算后重读的状态（pending + updated_at），删除中途的 profile 回落旧快照不抛错|src/backend/cbrowser/services/control_service.py、tests/unit/test_control_service.py|
|t031_code_f005|minor|已修|请求模型文档注释写明 claim 实例恒取 token、handoff 身份字段被忽略（不删字段保兼容），OpenAPI 已重导|src/backend/cbrowser/domain/models.py、schemas/openapi/|
|t031_code_f006|minor|已修|_run finally 调 attendant.release()，掉线后 peek 不再报告过期 dialog；重 arming 清 released 标志|src/backend/cbrowser/runtime_agent/dialog_attendant.py、tests/unit/test_dialog_attendant.py|
|t031_code_f007|minor|已修|_run 拆为 _handle_response/_handle_event（圈复杂度降至阈下）；拆分时一度漏记 targetCreated 的 pending_attach，已补回并经链测试验证|src/backend/cbrowser/runtime_agent/dialog_attendant.py|
|t031_code_f008|minor|已修|控制服务 claim/handoff/restore/retry 按 profile 级异步锁串行化，并发认领败者为 control_second_agent 冲突|src/backend/cbrowser/services/control_service.py、tests/unit/test_control_service.py|

范围外观察处置：reconcile 循环（_reconcile_profile_loop）持续覆盖各 profile，handoff 幂等 no-op 后的 pending 仍由该循环重试，无需改动；恢复时清除 pending 而不补发关闭（补发会误杀新隧道），旧 Supervisor 直连隧道仅能为同一 Agent 身份恢复通道，不构成越权，已记入规约。

### Round 2（code PASS + test PASS，新增 3 条 minor）

|finding_id|severity|status|rationale|fix_ref|
|---|---|---|---|---|
|t031_test_f008|minor|已修|targetCreated→pending_attach 分支补单元钉子：晚创建页面 attach 后会话登记 + Page.enable + dialog 滞留全链路|tests/unit/test_dialog_attendant.py|
|t031_code_f009|minor|已修|handoff_for_identity 逐 profile 隔离：单 profile 交接异常记日志后继续整批，不中断其余同 token Profile|src/backend/cbrowser/services/control_service.py、tests/unit/test_control_service.py|
|t031_code_f010|minor|遗留|门禁检查与应答到达之间的 TOCTOU 残留窗口：正常接管路径下 attendant 释放清空滞留 dialog、应答返回 404 已中和；彻底闭合需 Agent 侧控制围栏（Agent 无 API 通道），归 t032 attendant 通道设计时一并闭合（规约 t032 交接节）|t032|

## 收尾报告

### 验收与验证

- task：[`task.md`](task.md)
- 结果：全部满足
- 测试：contract 169 过；unit 979 过 / 1 skip / 1 存量失败（test_repo_hygiene，干净 base 同 ID，源于 t027 归档 review 报告绝对路径）；integration 156 过 / 1 存量失败（test_ac009_api_supervisor_start_and_stop_coordination，干净 base 同 ID）；前端 Vitest 215 过 + test:types + 生产 build 通过；E2E collect 102；真实 Chromium attendant 链测试 1 过；git diff --check 干净
- 黑盒：testing.md 的 blackbox_verify 为 E2E 必需模式（真实 Docker/镜像），本机无 Docker，按队列门禁口径跳过并按 pass 计；替代验收为真实 Chromium 全链集成实跑与 collect-only E2E 条目；真实镜像黑盒义务归 t032
- review：full 级 3 轮：R1 双路 FAIL（test 7 条 + code 8 条）→ 全部已修；R2 双路 PASS（新增 test f008 + code f009/f010）→ f008/f009 已修、f010 遗留→t032；R3 窄范围双路 PASS（0 新发现）；check_review_status overall=PASS、review_scope=ok、round=3
- AC 判定：见 `task.md` 行内打勾（8/8；AC-002/AC-004/AC-008 含交 t032 的行内注）

### 结果摘要

- 真人优先控制权落地：控制状态机（owner/generation/身份/reclaim/pending）、API+Supervisor 双层隧道注册表与接管关闭级联、Stream 前台输入分类与 Gateway 上报、CLI 控制动作、常驻 Dialog attendant（含控制面 peek/应答与 dialog 门禁）、setAutoAttach backstop、迁移 0009、管理面控制面板与 SSE 同步。
- 遗留只写引用，不复制正文：f010 → t032；其余 finding 全部已修。

### 长期文档闭环

- specs_index：human_agent_control 行已登记 t031；新规约 docs/specs/human_agent_control.md、ADR 019、automation.md、security.md、testing.md 已更新。

## 实施设计（2026-11-04，survey 后定稿）

### 证据链（均经 worktree 内实测，非推断）
- API 代理（api/v1/automation_router.py）→ Supervisor 代理（supervisor/control_server.py）→ Agent UDS /cdp（runtime_agent/agent.py websocket_cdp_proxy）：全部隧道流量必经 Agent /cdp 代理，故常驻 Dialog attendant 以 Agent /cdp 客户端接入为 arming 触发可覆盖全部自动化会话。
- 两层代理握手时仅验 token、无隧道注册表、无代次围栏（已核实）；隧道过滤（runtime_agent/tunnel_filter.py）无 setAutoAttach 处理。
- Stream 输入：stream_agent/policy.py `_on_peer_data_message` 对 kd,/ku,/m,/m2,/sf,/sfe,/co, 前缀调 record_input（仅 FPS 策略）；peers 以 Gateway conn_id 为键、active 表前台可见性；selkies 本机未装，旧版 2.1.0 报文语法无法由公开网页钉死，故分类器以仓内实测前缀为准。
- SSE：GET /api/v1/events 经 RuntimeEventBroadcaster 推 ProfileRuntimeEventData；前端 sse.ts 对事件做严格校验，未知/畸形事件会被丢弃并报错，故控制状态以可选字段挂在 runtime 事件上（不另开事件类型），前端校验同步扩展。
- OpenAPI 契约链：scripts/export_openapi.py 导出 live FastAPI → schemas/openapi/cbrowser_v1.json → 前端 npm run generate:api；另有测试断言导出 JSON 与 live app 一致。
- t030 规格 Dialog 节：无认领 dialog 由 Chrome 打开时自动消解；lingering 监听会话可使 dialog 滞留；常驻分支未在 t030 实现，理由是“会改变全部自动化客户端的 dialog 语义，必须与 t031 的真人优先与排他语义一并设计”。

### 控制模型（ADR 019，见 decisions.md）
- owner ∈ {user, agent}，默认 user；每 Profile 单调 generation（每次所有权变迁 +1）；agent_identity（instance_id + agent_session_id，可空）；handoff_reason ∈ {human_input, cli_handoff, permission, captcha, two_fa, agent_finish, supervisor_restart, profile_restart, crash, identity_invalid, admin_restore}；agent_reclaim_allowed 标志。
- 排他语义（不复活 ADR 007 已废弃的 Viewer 租约）：多真人 Viewer 仍可并发；排他只存在于“真人侧（作为一类）与 Agent 侧（同 Profile 首版仅一个协作 Agent）”之间。
- 认领规则：自动化隧道握手时若 owner=user 且 agent_reclaim_allowed=true，执行隐式认领（兼容 t030 CLI 现有行为，认领可见于管理面与 SSE）；接管后 agent_reclaim_allowed=false，Agent 再次认领必须经真人显式恢复（restore 直接置 owner=agent、generation+1）；Agent 正常结束（cleanup/release）置 owner=user、reason=agent_finish、reclaim 恢复 true；重启/崩溃/身份失效一律回 user。
- API 为唯一业务 DB 写入者：控制状态只由 API 侧 control service 写 profile_controls 表；Supervisor/Agent/Gateway 永不直写业务 DB。

### 强制执行（两层注册表 + 代次围栏）
- API 与 Supervisor 各持内存活动隧道注册表（tunnel_id、layer、agent_identity、generation、opened_at）；握手后登记、关闭时注销。
- 接管时：API 持久化 owner=user、generation+1 → 调 Supervisor 关闭隧道端点（Supervisor 关其代理 websocket 并以代次围栏拒旧代次重连，同时 best-effort 经 UDS /control 向 Agent 发 release_attendant）→ API 关其代理 websocket。竞态守卫：消息处理时校验隧道 generation 与当前 generation，不一致即丢弃/拒绝。
- Supervisor 在接管时刻不可达时：接管仍提交（API 为权威），控制记录置 pending_supervisor_close，coordinator 下次 Supervisor 交互时重发；残留窗口写入 ADR（分区期间已建立的 Supervisor 直连隧道在分区愈合前不受 API 侧关闭约束）。
- Agent UDS 层：本地信任边界（0660 socket + Supervisor 管理的 runtime 目录），写入 security.md；UDS 直连客户端不在本 task 强制范围内（与直接访问 runtime 目录等价），控制强制由 CLI 会话生命周期 + 接管级联（Supervisor 关闭隧道端点 → Agent /control release_attendant）覆盖。

### Stream 输入分类器（保守策略：宁可误触发，不漏接管）
- kd,（按键）触发；ku,（单纯释放）不触发；m,（纯移动）不触发（规格明确）；m2,（鼠标按键）一律触发（按钮状态字段语义仓内未钉死，不做精细区分）；sf,/sfe,（滚轮）触发；co,end,（IME 提交）触发，其他 co,（组合进行中）不触发；未知前缀不触发（非人类输入证据，仅记日志）。
- 前台判定：conn 映射到 peers 且 active=True 为前台；映射到 peers 但 active=False 为后台（不触发）；未映射 conn 按前台处理（防映射时序竞态漏接管）。XTEST 注入结构上不经 WebRTC 数据通道，天然不触发（文档与测试写明边界）。
- 通路：Stream Agent 分类命中 → Gateway Agent 协议新增 HUMAN_INPUT_TAKEOVER 动作 → GatewayApiClient.report_human_takeover → API 内部端点（require_gateway）→ control service 接管（reason=human_input）→ 关闭隧道 + SSE 广播。接管级联同时经 Supervisor 关闭隧道端点向 Agent 发 release_attendant（Agent 无 Gateway 直连通道，故不设 Gateway→Agent 推送；UDS /control 即为该级联的最后一跳）。

### CLI（agent_executor）
- 新增动作 control_claim（显式认领，返回 state+generation）、control_handoff（reason + 可选 detail；执行后 run_program 停止后续步骤）、control_release（best-effort，cleanup 时自动调用）。
- API 基地址由 --endpoint 同源推导（ws/wss → http/https + origin），不新增 CLI 入参；以同一 cbat_ token 做 Bearer 鉴权；token 永不写日志（沿用 _redact）。

### setAutoAttach backstop 漏判（t030 输入 #2，处置：实现修复）
- 根因：tunnel_filter.observe_incoming 不处理 Target.attachedToTarget，故 _session_targets 缺自动附着会话映射 → Page.close 最后一页 backstop 被绕过；且无 setDiscoverTargets 时收不到 targetCreated，_known_pages 可能缺失仅经自动附着发现的页面 → closeTarget backstop 也可被绕过。
- 修复：observe_incoming 处理 attachedToTarget（登记 session→target 映射 + 已知页面）；不直接拒绝 setAutoAttach（会破坏执行器自身传输）。单测锁定两条绕过路径。

### 常驻 Dialog attendant（t030 输入 #1，正面设计并实现）
- 形态：Agent 进程内组件（非新进程/守护进程），持一条直连 browser_ws 的服务 CDP 连接（非隧道客户端，不受隧道过滤约束），仅 Page.enable + 观测 javascriptDialogOpening/Closed，永不自动应答。
- arming：Agent /cdp 代理首个客户端接入时幂等 arming（覆盖 API 与 Supervisor 两路隧道）；release：Supervisor 关闭隧道端点级联经 UDS /control 发 release_attendant（接管时）、Agent 停机、服务连接丢失时失活。
- 语义：agent 控制期内持有未认领 dialog（阻止 Chrome 自动消解），使下一 CLI 会话可经标准 t030 dialog_answer 应答（CDP 层 handleJavaScriptDialog 是否可跨会话应答、dialog_wait 是否可见已滞留 dialog，由真浏览器 chain test 实测后写入 ADR，不预设结论）；接管后 attendant 释放，dialog 回归 Chrome 默认处置（人类在视频中可见、可经输入应答）；attendant 自身在任何控制状态下都不代答。
- 管理面暴露缺口（明确记录，非偷工）：Agent 无 API 直连通道，attendant 对话状态 v1 不进管理面（人类在视频中直接可见滞留 dialog）；需 API←Gateway 拉取通道或 Agent→API 上报通道时再做，不在本 task 造无消费者的 plumbing。

### 链实测转折（2026-11-04，真浏览器证据，设计据此改动）
- 原始 CDP 直连（绕开隧道）实测结论：dialog 打开后才 attach 的新会话，Page.enable 在 modal dialog 后挂起（10s 超时），Page.handleJavaScriptDialog 报 "No dialog is showing"，Runtime.evaluate 同样挂起。即可跨会话应答的假设不成立：只有 dialog 打开前已 Page.enable 的会话（attendant 自身）能应答滞留 dialog。
- 据此补控制面应答路径（非隧道 CDP 改写）：Agent /control 新增 list_attendant_dialogs / answer_attendant_dialog；Supervisor 层对等方法 + 两端点；API 层 coordinator 对等方法 + /control/dialogs（GET）与 /control/dialog-answer（POST，automation token）；CLI dialog_wait/dialog_answer 在会话未 attach 时先 peek attendant（命中则直接返回/应答，不走 attach）；adopt 在目标有滞留 dialog 时跳过 attach（否则 adopt 自身先挂在 Page.enable 上，dialog 操作永远跑不到 peek）。
- 链测试最终断言（tests/integration/test_control_attendant_chain.py）：CLI-1 点击开 confirm 后退出不答 → 新会话 dialog_wait 经 peek 返回该 confirm → 新会话 dialog_answer 经 attendant 应答 dismiss → extract 得 false；随后调度延迟 confirm 并走真实 API handoff + restore（代次一致）确认 release → timer 在无监听时 firing → Chrome 默认自动消解 false。测试曾两次踩坑已修正：直接往 Supervisor POST 自造 generation=99 会把后续转发代次判 stale（改走 API 路径）；后台页 timer 节流与 release 确认时序抖动（改为 15s timer + poll pending 至 False 后再等 firing）。
- 管理面暴露缺口更新：attendant 状态仍不进管理面，但 CLI 可经 /control/dialogs peek（automation 面），人类在视频中可见滞留 dialog；该缺口仍为后续设计项，不新立 pending。

### 前端与契约
- ProfileRuntimeResponse / ProfileRuntimeStatusEvent 增加可选 control 字段；sse.ts 增加 isValidControl 校验；管理面（ProfileDetailPage + automation 页）在现有布局内展示控制方、交接原因、实例与恢复入口（显式 restore 按钮），操控页保持纯画面，不新增遮挡。
- OpenAPI 导出 + 前端类型重生成；契约一致测试须过。

### AC 映射
- AC-001：0009 迁移 + 隔离 DB 升级与备份恢复测试 + API 唯一写入（service 层唯一写路径，测试锁定）。
- AC-002：两层注册表 + 接管关闭 + 代次围栏 + 重连拒绝 + 分类器 + Gateway 上报（集成测试以已建立隧道验证关闭与拒绝，非仅查字段）。
- AC-003：不声称可撤销；取消/超时不自动重放（文档 + CLI handoff 后停步语义测试）。
- AC-004：多 Viewer 音视频/输入/页面在接管后保持（设计：接管只关自动化隧道，不动 Viewer 连接；目标实跑交 t032）。
- AC-005：user 状态下 CLI finish/异常退出不自动关闭本任务页面（cleanup 仍走 t030 ledger 语义 + control_release best-effort）；显式恢复后新动作可用；过期响应/SSE 不覆盖新代次（generation 校验测试）。
- AC-006：权限/验证码/2FA 经 CLI handOff 进入 user；JS Dialog 按 t030 + attendant（含链实测后的控制面应答路径：peek + attendant 会话应答）；恢复须显式授权、无倒计时自动抢回。
- AC-007：管理面可观察 + SSE 同步 + ADR 与 ADR 006/007 及 storage spec 关系说明 + /manage 勘误。
- AC-008：云端覆盖已建立长连接的接管/竞争/失联/代次围栏/恢复；目标 WebRTC/X11 来源与原生权限交接用例交 t032（E2E collect-only + run notes）。
