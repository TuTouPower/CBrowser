# 真人优先的 Agent 控制权与安全交接（t031）

来源：p029；承接 t030 AC-006 deferral 的常驻 Agent 分支与 setAutoAttach
backstop 确认项。决策见 ADR 019（`docs/blueprint/decisions.md`）。

## 控制模型

- 每 Profile 一条控制记录（`profile_controls`，迁移 0009）：owner
  `user`/`agent`（默认 `user`）、单调 `generation`（每次所有权变更 +1）、
  Agent 实例 id（automation token id）与 Agent 会话 id（均可空）、
  `handoff_reason`、`agent_reclaim_allowed`、`pending_supervisor_close`。
- API 是唯一业务库写入方：Supervisor、Gateway、Agent 永不直写业务库。
- 向 user 的迁移 fail-open（任何授权调用方可把 Profile 移回安全态）；
  向 agent 的迁移 fail-closed（身份一致 + reclaim 标志 + 显式恢复）。
- 默认与重启/崩溃/身份失效一律回到 user；干净 Agent 结束
  （`agent_finish`）与运行时重启/崩溃属于全新开始，reclaim 保持开放；
  人类驱动的交接关闭 reclaim，必须显式恢复。
- 身份失效接线（R1 code f002）：管理面吊销 automation token 时，
  该 token 持有控制的 Profile 各执行一次 `identity_invalid` 交接
  （正常隧道关闭级联 + SSE 广播）；仅吊销后新连接被拒是不够的，
  已建立隧道必须随吊销关闭。token 过期无独立清理点：过期在握手时
  校验（新连接被拒），已建立隧道在过期后不自动关闭属已知残留，
  与 Supervisor 分区窗口同类，待周期性隧道再校验机制闭环（非本
  task 新立项）。
- 同一 Profile 的控制迁移按 profile 级异步锁串行化（R1 code f008）：
  并发认领中胜者唯一、败者为 `control_second_agent` 冲突（409），
  不向调用方泄漏原始 DB 写错误。
- 身份匹配：两维（实例、会话）都携带时必须都一致；缺一维时以另一维
  为准；两维皆无则冲突（`control_no_identity`）；裸隧道握手（仅 token）
  续租会话级认领而不降级。
- 排他只存在于人类侧（一类）与 Agent 侧之间：首版每 Profile 至多一个
  协作 Agent；多人类 Viewer 并发不受限（不复活 ADR 007 租约）。

## 接管触发

- 前台 Viewer 的点击/按键/滚轮/IME 提交（Stream 分类器，保守取向：宁可
  误接管、不漏接管）与 CLI 主动 `control_handoff` 构成可观测的接管边界；
  纯鼠标移动、后台 Viewer 输入、XTEST 注入（结构上不走 WebRTC 数据通道）
  不触发。
- 分类 → Gateway Agent 协议 `HUMAN_INPUT_TAKEOVER` → API 内部端点
  （`require_gateway`）→ 控制服务接管（`human_input`）→ 关闭隧道 + SSE 广播。
- Stream 侧上报为追加式 pending：发送失败保留待下次 flush，接管幂等故
  人类下一次分类输入可重报；Gateway 侧上报失败只记日志、不致命。

## 强制执行

- API 与 Supervisor 各持内存活动隧道注册表（隧道 id、层、身份、代次、
  打开时间、关闭回调）；代理握手在鉴权与控制认领后登记，拆除时注销。
- 接管 = 连接拆除，不是逐消息过滤：API 持久化 owner=user 并代次 +1，
  调 Supervisor 关闭隧道端点（Supervisor 关其代理 websocket、代次围栏
  前进、best-effort 经 UDS /control 向 Agent 发 release_attendant），再关
  API 代理 websocket；API 层隧道先于 SSE 发布关闭。
- 竞态守卫：消息处理校验隧道代次与当前代次，不一致即丢弃/拒绝；API
  转发握手带 `X-CBrowser-Control-Generation`，Supervisor 对不高于围栏
  的转发代次以 4403 拒绝；无该头视为基础设施直连调用（Supervisor token
  即服务间凭证），放行并记日志。
- Supervisor 不可达时接管仍提交（API 为准），记录置
  `pending_supervisor_close`，由 reconcile 每轮重试直至 Supervisor 确认；
  残留窗口：分区内已存在的 Supervisor 直连隧道在分区愈合前不受 API 侧
  关闭约束。
- handoff 响应体返回结算后状态（R1 code f004）：Supervisor 关闭确认
  后的二次提交（pending 清除）反映在返回体中，不返回关闭前快照。
- 恢复时清除 `pending_supervisor_close` 而不补发 Supervisor 关闭
  （R1 范围外复核结论）：恢复后 Agent 的新隧道合法，补发旧代次关闭
  会误杀新隧道；恢复前未确认的旧 Supervisor 直连隧道与分区残留
  窗口同类——仅能为此前已持有控制的同一 Agent 身份恢复通道，不
  构成越权，由后续关闭/重启收敛。
- Agent UDS 层为本地信任边界（0660 socket + Supervisor 管理的 runtime
  目录）；UDS 直连客户端不在强制范围内（与直接访问 runtime 目录等价）。
- 清理与 XTEST 式旁路在 user 态下被拒绝；已执行的动作不声称可撤销；
  取消/超时不自动重放；恢复须显式授权、无倒计时自动抢回。

## CLI 控制动作

- `control_claim`（显式认领）、`control_handoff`（reason + 可选 detail；
  其后程序停步、余步记 `skipped: control_handed_off`）、`control_release`
  （best-effort，reason `agent_finish`，永不抛错）。
- API 源由 `--endpoint` 同源推导（ws/wss → http/https）；同一 `cbat_`
  token 作 Bearer 鉴权，token 永不写日志。
- CLI 侧交接原因仅 `cli_handoff`/`permission`/`captcha`/`two_fa`/
  `agent_finish`；服务端原因（`human_input` 等）不是 CLI 原因。
- `session.permission` 只返回 needs-human 载荷、不自动交接；harness 模式
  为 permission → `control_handoff`，会话本身永不因权限探针自动交接。
- `cleanup()` 不自动释放控制（进程退出不等于会话结束，会话经状态文件
  延续；人类接管恒可抢占）。
- 代次围栏：claim/handoff 响应代次低于已知代次时 claim 报
  `control_stale_generation`；handoff 仍按动作名停步（已决定交接的 CLI
  不得继续发 Agent 命令）。
- 隧道连接关闭码 4403 映射为 `control_revoked`（需显式人类恢复）。

## 常驻 Dialog attendant 与控制面应答路径

- 形态：Agent 进程内组件（非新进程），持直连 browser_ws 的服务连接，
  在每页保持 no-op dialog 监听以阻止 Chrome 自动消解；自身永不自动应答。
- arming：Agent /cdp 代理客户端接入时幂等 arming（API 与 Supervisor 两路
  隧道必经该代理，故全覆盖）；release：接管级联（UDS /control
  `release_attendant`）、Agent 停机、服务连接丢失。
- 链实测结论（真浏览器，tests/integration/test_control_attendant_chain.py）：
  dialog 打开后才 attach 的新会话无法观测或应答它——Page.enable 在 modal
  dialog 后挂起，handleJavaScriptDialog 报 "No dialog is showing"；只有
  打开前已 Page.enable 的会话（attendant）能应答。故：
  - CLI dialog_wait/dialog_answer 在会话未 attach 时先经控制面 peek
    （`GET /control/dialogs`）再经 attendant 会话应答
    （`POST /control/dialog-answer`）；adopt 在目标有滞留 dialog 时跳过
    attach（否则 adopt 先挂在 Page.enable 上）。
  - 接管 release 后 dialog 回归 Chrome 默认处置（链实测：无监听时 firing
    的 confirm 自动消解为 false）。
  - 控制面门禁（R1 code f001）：peek/应答是 Agent 动作，要求调用方
    持有控制权且 token 身份与记录的 Agent 实例一致；user 态或第二
    token 一律 409。接管级联的 attendant 释放纳入 pending 确认：
    Supervisor close 仅当隧道关闭与 attendant 释放双确认才算成功，
    否则 pending 由协调器 reconcile 轮次重试；无 Agent 进程时释放为
    空确认（死进程无 attendant 状态可留）。
  - 服务连接丢失即释放滞留状态（R1 code f006）：掉线会话的 dialog
    已无人能应答，peek 不再报告过期 dialog；下次 /cdp 接入重新
    arming。
- attendant 状态 v1 不进管理面（Agent 无 API 直连通道）；人类在视频中
  直接可见滞留 dialog，CLI 可经 peek 发现；补上报通道属后续设计。

## setAutoAttach backstop

- `tunnel_filter.observe_incoming` 处理 `Target.attachedToTarget`（登记
  session→target 映射 + 已知页面）与 `Target.detachedFromTarget`（弹出
  映射）；`setAutoAttach` 本身保持转发（执行器自身传输）；最后一页
  backstop 由此覆盖自动挂接会话发现的页面。

## 管理面

- 现有管理面（AppLayout 顶栏 + Profile 详情/自动化页，不新增路由与布局
  重建；ADR 006 的 /manage 说法按勘误修正）在 runtime/event 的可选
  `control` 字段上展示控制方、代次、交接原因、Agent 身份、Supervisor
  关闭待重试警告与显式恢复入口；操控页保持纯画面，不新增遮挡。
- SSE 事件经 runtime 事件的可选 `control` 字段承载（不新增事件类型；
  非法 control 使整条事件按畸形丢弃）。

## t032 交接（本 task 不判定）

- 目标 WebRTC/X11 来源的接管、原生权限交接用例、真实拓扑下的接管/
  恢复、AC-005 缩放子项复核（t029）与 attendant 管理面暴露通道设计。
