# 受控 CDP 自动化

外部自动化只经认证 WebSocket 进入 Supervisor，再由 Agent UDS 转发到浏览器回环 CDP；不发布任何 Browser CDP TCP 端口。

## 入口与鉴权

- 新建入口：`WS /api/v1/automation/profiles/{profileId}/cdp`。
- 旧入口薄适配：`WS /api/profiles/{profileId}/cdp`，同一处理器、同一 Bearer 凭证；不出现在 OpenAPI 中，不提供旧 CDP 端口映射。
- 自动化凭证由登录用户经 `POST /api/v1/automation/tokens` 创建，格式 `cbat_...`，只在创建响应返回明文；凭证限定可访问的 Profile。
- 客户端必须发送 `Authorization: Bearer <token>`；登录 Cookie 不被接受。Bearer 方案名大小写不敏感。
- 未授权、非授权 Profile、凭证撤销关闭码 4401；Supervisor 未配置或上游失败关闭 1011。
- 授权只经上述 v1 入口由 `AuthService.authorize_automation` 执行（t021）：内部 Gateway 面曾有的 `automation-authorize` RPC 无任何生产消费者，已整体删除（含 DTO 与内部 OpenAPI 条目）；t064 后 Gateway 也不再承担 viewer 会话授权，viewer grant 由 API 边缘解析签发、Gateway 本地验签。不得再新增平行的内部自动化授权面。

## 转发链

```text
external client
  -> API automation_router (token verify)
  -> Supervisor control WS /supervisor/v1/profiles/{id}/cdp (supervisor token, constant-time compare)
  -> Agent UDS /run/cbrowser/runtime/{profileId}/agent.sock (ws://localhost/cdp)
  -> Chrome loopback CDP
```

- API 只持有 Supervisor URL 与内部 token；不直接持有 Docker Socket。
- Supervisor 从 `core._sessions` 校验 Profile 处于 running，并经 `PathValidator` 校验 `agent.sock` 位于该 Profile 的 runtime 目录。
- 双向消息按文本/二进制原样透传；任一侧关闭即取消另一侧任务并关闭上游，避免半开隧道。
- 外部客户端断开后，Agent 重置并恢复默认下载捕获策略；随后真实下载仍进入 `/exchange/downloads` 并被 Artifact 链路捕获。

## 前端

`/automation/:profileId` 页面调用 `GET /api/v1/profiles/{profileId}/automation`，展示授权 WS 端点、运行状态、运行实例、Supervisor 配置状态与 Authorization 头格式；直接加载/刷新由认证守卫处理，不依赖前序页面状态。

## 自动化兼容性基线（t029）

外部自动化框架（Playwright 等）经隧道的兼容边界以 `docs/specs/automation_compatibility.md` 的实测为准，要点：

- Playwright `connect_over_cdp` 的 `no_defaults` 决定下载归属：True 时连接期间下载由 Agent 的 browser 级行为捕获、客户端无 download 事件；False 时 Playwright 覆盖默认 context 的下载行为，文件落客户端临时目录、绕过 Artifact 捕获。断开后 Agent rearm 恢复 browser 级捕获。
- 安全断开不发送 `Browser.close`；t029 时隧道对外部 `Browser.close` 完全透明，外部客户端可直接停掉 Profile——该透明语义已被 t030 废止，见下节“Agent 执行器（t030）”。
- 隧道关闭时对端关码透传（t055）：仅当对端主动关闭才向客户端透传关码，且在本地 close 之前读取（本地 close 后 websockets 报自发关码 1000）；客户端先断开时不透传；上游 close 抛错不阻断向客户端发送关码。
- Dialog：opening 事件经隧道转发且 pending 期间可应答；prompt 的 promptText 回传不生效（页面得 null）；客户端退出遗留的 Dialog 不向新连接重放、新连接命令不被阻塞、遗留项被消解。
- 指纹增量与输入比较的逐级结论见 spec；t030 采用某级能力前须确认该级在 spec 中为「无新增变化」，t032 真实镜像复测推翻时以 t032 为准。

t030 必须拦截或避开的 CDP 命令（探针代码 `MUST_MEDIATE_METHODS` 同步维护）：`Browser.close`、`Target.closeTarget`、`Page.close`、`Browser.setDownloadBehavior`、`Page.setDownloadBehavior`、`Emulation.set*` 覆盖族、`Network.emulateNetworkConditions`、`Page.addScriptToEvaluateOnNewDocument`（须登记并在断开时清理）。

## Agent 执行器（t030）

契约见 `docs/specs/agent_executor.md`。要点：

- 宿主 CLI `cbrowser-agent`（stdin JSON 动作程序，`version: 1`），经 cbat\_
    认证隧道连接；生产路径走原始 CDP（Playwright 不暴露 targetId），不用
    Playwright 直连。凭证只经 `--token-file`（0600）或环境变量；CLI 输出
    不含凭证、Cookie 或认证头。
- 会话横跨多次调用：ref 与页面账本持久化到状态文件（默认
    `~/.cache/cbrowser/agent-executor/<profile>_<runtime>.json`，0600、原子
    写入）；成功退出不隐式清理，失败/取消自动清理，显式 `cleanup` 是正常
    结束的清理入口。启动时先 baseline 再开 discovery，持久化账本按存活
    目标覆盖 baseline。
- 账本来源、管理权、清理权三分离；adopt 不改来源、不授清理权；popup
    归属需 openerId + 动作时序 + 账本三方证据；清理保留最后一个页面。
- 快照 frame 归属以 DOM 映射为准（AX 节点除根外无 frameId）；子 frame
    DOM 元素无 AX 对应时也进快照（role/name 为空）；ref 校验含
    runtime、target、frame、loader、签名与 `isConnected` 存活；失配返回
    `ref_stale`。
- Dialog：动作前监听、保守应答语义；click 分发是 dialog 感知的（modal
    阻塞渲染线程时提前返回 dialog 信息，不等满步骤超时）；遗留 dialog 在
    无认领会话时由 Chrome 在打开时即自动消解为 false，下一调用畅通；
    lingering 处理会话滞留的 dialog 属 Chrome 层限制（见 spec）。
- 权限/设备提示不可检测（CDP 无原生事件），一律返回需真人并附 t031
    handOff 载荷；文件选择独立步骤（`set_input_files` 先在同会话请求
    document 再推送节点，否则 Chrome 报“Document needs to be requested
    first”——跨调用的新会话不能复用旧会话的 document 请求）。
- 跨调用遗留 Dialog 的机制选择（task 设计要求记录的选择与依据）：
    新连接能得知并应答的 dialog 由 CLI 处理；CLI 退出后无认领的 dialog
    由 Chrome 在打开时自动消解，下一调用畅通（实测：Opening 后紧跟
    Closed，结果 false）。常驻 Agent 维护 dialog 状态的分支不在 t030
    实现：它会改变全部自动化客户端的 dialog 语义，必须与 t031 的真人优先
    与排他设计一并定夺；仍由 live 外部处理会话持有的 dialog 不属于
    “CLI 退出后遗留”，其仲裁归 t031。
- t031 续（真人优先控制权，ADR 019）：常驻分支落地为 Agent 进程内
    attendant（直连 browser_ws 服务连接、每页 no-op 监听、接管时 release）；
    链实测推翻“新会话可经标准 dialog_answer 应答滞留 dialog”——新会话
    Page.enable 在 modal dialog 后挂起、handleJavaScriptDialog 报无 dialog，
    故滞留 dialog 只能由 attendant 会话经控制面应答（CLI 未 attach 时先
    peek `/control/dialogs` 再经 `/control/dialog-answer` 应答；adopt 在
    目标有滞留 dialog 时跳过 attach）。接管 release 后 dialog 回归 Chrome
    默认处置（无监听时 firing 的 confirm 自动消解为 false）。
- t031 续（setAutoAttach）：tunnel_filter 补 attachedToTarget/
    detachedFromTarget 处理，setAutoAttach 本身保持转发；最后一页 backstop
    由此覆盖自动挂接会话发现的页面。
- 隧道 v2：拒绝 `Browser.close`、下载行为覆盖、Emulation 覆盖族与
    `Network.emulateNetworkConditions`（稳定 CDP 错误 -32000）；
    `addScriptToEvaluateOnNewDocument` 按会话登记、断开时清理；关 Tab
    不在隧道做归属过滤（会挂起 Playwright popup 关闭），由账本 enforcement，
    隧道仅保留最后一页 backstop。
- 薄入口 Skill 在 `assets/skills/cbrowser-agent/SKILL.md`。

## 验证

- 单元：Supervisor WS 到 UDS 的双向转发、缺失/错误 token 的 4401、大小写 Bearer。
- 集成：真实 API + Supervisor control uvicorn + UDS echo 的完整认证转发；API 状态接口；旧入口与新入口同样拒绝无效凭证。
- 真实 E2E：真实 Chrome 经 Agent UDS 执行 CDP 命令并触发下载，证明 loopback CDP 未被公网端口暴露。
- 兼容性探针（t029）：全链矩阵/下载/Dialog/外部 close 集成测试与 L0–L6 采样驱动，入口与证据分级见 `docs/blueprint/testing.md` 的探针矩阵一节。
