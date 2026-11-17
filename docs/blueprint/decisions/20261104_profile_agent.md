# 019 Profile 人机控制权：真人优先、单 Agent 排他与代次围栏（2026-11-04，t031）

- 背景：t030 落下两项输入：其一，CLI 退出后无认领的 JS Dialog 由容器
    内常驻 Agent 分支维护（AC-006 否则分支未实现，打勾 + deferral 注）；
    其二，setAutoAttach 会话的隧道 backstop 漏判。p029 另要求真人输入可
    抢占 Agent 控制。ADR 007 已废弃排他 Viewer 租约：多人类 Viewer 并发
    是既定语义，不能为控制权复活它。
- 选项：
    1. 方法名黑名单式拦截“致变 CDP 命令”（evaluate/callFunctionOn 等
        逐条禁）：p029 已指出 evaluate 可跑任意致变脚本，名单不可靠。
    2. 控制权状态机 + 连接拆除：每 Profile 一条控制记录（owner user/
        agent、单调 generation、Agent 实例 + 会话身份、交接原因、
        agent_reclaim_allowed、pending_supervisor_close），API 为唯一业
        务库写入方；接管时持久化 owner=user 并代次 +1，API 与 Supervisor
        各自关闭已登记的活动隧道并以代次围栏拒旧代次重连；向 user 的迁
        移 fail-open、向 agent 的迁移 fail-closed（身份一致 + reclaim
        标志 + 显式恢复三者缺一不可）。
    3. 恢复 ADR 007 式排他租约并扩展到 Viewer：与多 Viewer 并发语义冲突。
- 结论：采用选项 2。排他只存在于“人类侧作为一类”与“Agent 侧”之间，
    首版每 Profile 至多一个协作 Agent；多人类 Viewer 不受限。默认与重
    启/崩溃/身份失效一律回到 user；干净 Agent 结束（agent_finish）与运
    行时重启/崩溃属于全新开始，reclaim 保持开放；人类驱动的交接关闭
    reclaim，必须显式恢复。Supervisor 分区期间的残留窗口如实记录：分
    区内已存在的 Supervisor 直连隧道在分区愈合前不受 API 侧关闭约束；
    直连 Supervisor 令牌持有者属于基础设施信任边界（Supervisor token
    即服务间凭证），其握手不查 API 状态，但转发代次受围栏约束。
    ADR 006 “配置与管理集中于 /manage”的说法与实现不符（现无 /manage
    路由，管理面为 AppLayout 顶栏 + Profile 详情/自动化页），事实复核按
    `docs/blueprint/conventions.md` 的评审维护约定，以本条为准修正。存储规约见 `docs/specs/human_agent_control.md`。
- 常驻 Dialog attendant 与链实测结论：attendant 为 Agent 进程内组件，
    持直连 browser_ws 的服务连接、在每页保持 no-op dialog 监听以阻止
    Chrome 自动消解；t031 真浏览器链实测推翻“新会话可经标准 dialog_answer
    应答滞留 dialog”的假设——新会话 Page.enable 会在 modal dialog 后挂起，
    handleJavaScriptDialog 报 "No dialog is showing"，故滞留 dialog 只能
    由 attendant 打开前已 Page.enable 的会话应答；CLI dialog_wait/
    dialog_answer 在未 attach 时先经控制面 peek（/control/dialogs）再经
    attendant 会话应答（/control/dialog-answer），adopt 在目标有滞留 dialog
    时跳过 attach（否则 adopt 先挂在 Page.enable 上）。接管 release 后
    dialog 回归 Chrome 默认处置（链实测：无监听时 firing 的 confirm 自动
    消解为 false）。attendant 状态 v1 不进管理面（Agent 无 API 直连通道），
    人类在视频中直接可见滞留 dialog，CLI 可经 peek 发现；补 API 拉取或
    Agent 上报通道属后续设计，不在本 task 造无消费者 plumbing。
- setAutoAttach 处置：tunnel_filter 补 attachedToTarget/detachedFromTarget
    处理（登记 session→target 映射 + 已知页面），setAutoAttach 本身保持转发
    （执行器自身传输）；最后一页 backstop 由此覆盖自动挂接会话。
- R1 审阅补强（不改结论）：控制面 peek/应答要求调用方持有控制权且
    token 身份与记录的 Agent 实例一致（user 态或第二 token 一律 409）；
    接管级联的 attendant 释放纳入 pending 确认（释放失败则 reconcile
    重试整条级联；无 Agent 进程时为空确认）；吊销 automation token 时
    该 token 持有控制的 Profile 各执行一次 identity_invalid 交接；同一
    Profile 的控制迁移按 profile 级异步锁串行化（并发认领败者为
    control_second_agent 冲突）；服务连接丢失即释放滞留 dialog 状态；
    handoff 响应体返回结算后状态。token 过期无独立清理点（握手时校验，
    已建立隧道过期后不自动关闭）与恢复时清除 pending 而不补发关闭
    （补发会误杀新隧道）均属已知边界，见规约。
- 替代：无（方法名黑名单与排他租约复活均不采用）。
