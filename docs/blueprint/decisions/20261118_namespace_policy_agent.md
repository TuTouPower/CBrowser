# 039 网络策略收归常驻 Policy Agent：命名空间内受限执行与观测（2026-11-18，t082）

- 背景：网络策略的安装、校验与失败封闭长期由一次性 helper 承担——每轮
    verify 都在目标 netns 内创建短生命周期容器执行
    `cbrowser.supervisor.network_policy` CLI，巡检 DNS 解析靠
    `docker exec` 进 Browser 容器。稳态下每 Profile 每轮产生容器创建/销毁
    churn；helper 与目标同生命周期外的执行面使「规则是否仍在」只能靠反复
    重演安装路径观测；临时执行器失败与规则漂移在观测上不可区分。t080 的
    架构范围（`docs/tasks/t080_linux_native_runtime_storage/architecture_scope.md`）
    已把常驻化列为既定方向。
- 选项：
    1. 保留一次性 helper，仅降低 verify 频率：churn 与不可区分性仍在，
        且低频 verify 拉长漂移暴露窗口。
    2. Supervisor 直接在宿主 netns 执行 iptables：Supervisor 须获得
        NET_ADMIN 并跨 netns 操作，权限面与爆炸半径远大于目标本身。
    3. 每目标 netns 一个常驻 Policy Agent（本 ADR 采用）：与目标同
        netns 的受限进程独占策略执行与观测，Supervisor 只经 UDS 协议
        下令与取证。
- 结论：采用选项 3。
    - **Agent 形态**：每 Browser/Stream 目标恰一个 Policy Agent 容器，
        使用同一不可变 policy 镜像，`cap_add` 仅 `NET_ADMIN`、只读根、
        `cap_drop ALL`、no-new-privileges，`network_mode=container:<目标 id>`
        加入目标 netns；不挂 Docker Socket、宿主目录与用户数据，唯一挂载
        是 runtime 卷内自身 slot 的 socket 目录
        （`policy-agents/<slot>`，slot 由 profile/instance/role 派生）。
        身份（deployment、profile、runtime instance、config version、
        role、target container id）在创建时经环境变量与标签双写绑定，
        进程内只从创建环境读取，运行期不可变。
    - **协议**：Supervisor 与 Agent 之间是版本化线协议
        （`schemas/runtime/policy_agent_protocol.json`，由
        `supervisor/policy_agent_protocol.py` 导出并入门禁漂移检查）：
        换行分隔 JSON、一请求一连接、64 KiB 上限，操作集
        `health / resolve / install / inspect / fail_close`。每请求携带
        完整身份，任一字段不符即 `identity_mismatch` 拒绝。`resolve`
        只接受裸 hostname + port（IP 字面量直返，拒绝 URL/凭据/路径/
        注入字符），替代巡检 `docker exec` DNS。
    - **修订围栏与刷新事务**：策略以单调修订号安装；旧修订重放、同
        修订异 spec 均以 `stale_revision` 拒绝，同修订同 spec 幂等
        （先 inspect、漂移则 replace 修复）。上游变化走刷新事务：
        Agent 内 resolve → install 新修订成功后才冻结新 spec，失败抛错
        且旧冻结 spec 与旧规则不变；规则全量替换前先备份双族规则表，
        失败回滚备份，回滚亦失败才失败封闭（`network_policy.replace_policy`）。
        稳态 verify 只做 Agent 内 `inspect`（含修订证明），零容器创建、
        零 exec；派生在上游未变时走冻结 spec，零 DNS。
    - **接管与孤儿**：Supervisor 重启后按标签全等 + health 身份回显
        采纳既有 Agent（health 返回已应用修订与 spec 摘要，接管方据此
        恢复围栏状态）；目标消失或绑定失配的 Agent 由周期孤儿清理
        删除，目标存活时不删（留待 core 接管）。Profile 拆除与探针
        结束同步删除其 Agent。
    - **核心收敛语义**：verify 失败先定点修复该目标 Agent 并重试
        一次；策略状态不可确认起 30 秒预算内为 recovering，超预算后
        Browser 暂停精确目标隔离（`browser_policy_unverifiable`），
        Stream 走既有 Stream-only 有界替换。漂移且失败封闭未获 Agent
        确认时同样暂停隔离，不再停留在无缓解状态。本机制暂停的目标
        只在仍是当前 desired=running 实例且规则复验通过（必要时先经
        Agent 重装一次）后才恢复；用户暂停、他实例暂停记录永不被本
        机制恢复。Agent 容器事件经 runner 定点唤醒对应 Profile 的
        修复，不触发全量扫描（p057 防自激不变）。
    - **删除面**：一次性策略 CLI（`network_policy.main`）删除，
        `network_policy.py` 收敛为纯规则库（渲染、应用、替换、失败
        封闭校验）；临时 helper 的命名、超时与日志抓取路径整体退役。
    - **未验证假设（spike 延期）**：仅 NET_ADMIN + policy 镜像 +
        `network_mode=container` 的完整策略/DNS 能力、以及 pause 冻结
        流量的网络负例与暂停所有权，云端无 Docker 不可证，按用户
        2026-11-18 裁定设计按最小权限假设先行，正式 spike 与 AC-010
        部署验收延期本地执行，分别由 pending p132 / p133 跟踪；spike
        若否定假设，停止扩权并修订本 ADR，不静默绕过。
