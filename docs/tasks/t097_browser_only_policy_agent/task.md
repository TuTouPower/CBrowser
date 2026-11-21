# Task spec

## 背景

本机 Chrome 经宿主回环接收媒体，Stream 经专属网络与 Gateway 交换信令，经共享内存和本地套接字取得画面、音频及传递输入。当前 Browser 与 Stream 共用一个双角色策略模型，各启动一个常驻 Policy Agent。Stream 的启动、恢复、巡检及替换都受其 Agent 约束。现有 Profile 网桥允许外部连接，Stream 的出站约束由策略落地。仅限制宿主端口发布范围不足以替代此约束。

架构按职责划分。Browser 执行不可信站点内容，继续按各 Profile 的代理配置动态管控出口。Stream 的对端和通信面固定，由受管网络拓扑落实隔离。两类容器统一套用动态策略属模型错位。Browser Agent 与其 Profile 的归属也应共用环境身份与可读编号，当前散列命名只表达内部实例身份，缺少 Docker 分组信息。

## 契约区

### 范围

- 用单一受管媒体拓扑承载本机媒体与 Gateway 信令。Stream 保持独立网络隔离和最小权限。显式验证其与公网、局域网、宿主其它服务及其它 Profile 的边界，再移除 Stream 侧策略安装、启动门、巡检、修复和接管。保留 Stream Agent 的信令注册和媒体生命周期。
- Policy Agent 专职 Browser。沿用 Browser 的代理强制、策略失效时的隔离和恢复语义。按同一 Profile 编号生成容器名 `<prefix>-<NNNN>-policy-agent` 与分组服务名 `<NNNN>-policy-agent`，沿用 `<prefix>-profiles` 分组。接管和清理继续以部署、运行实例与目标身份判定。
- 在新版本收敛时一次性替换存量旧形状的受影响运行资源，清理本部署遗留 Stream Agent 与旧命名 Browser Agent，覆盖恢复和回退。停机窗口及影响按真实发布验收记录。

### 非范围

- 局域网访问、公共媒体入口与 TURN 中继。
- Browser 出口策略、代理库和测速机制的功能调整。

### 验收标准

<!-- 规范（门禁必留，不得删除） -->

只写可观察、可独立验证的行为；每条使用稳定且不复用的 `AC-NNN`。需真实部署或人工环境验证时在编号前加 `[deploy]`。创建时均为未勾选（`- [ ]`）；实施验证通过后由实施 Agent 就地打勾（`- [x]`）；由 Review Agent 独立复核打勾真实性。技术选型不作为行为 AC。review 判 FAIL 且需修改交付内容时，实施 Agent 撤回全部打勾，修复并重验后重新打勾；reviewer 用 `TICK-VALID` / `TICK-VOID` 逐条判定。

<!-- /规范 -->

- [ ] AC-001：每个运行中的 Profile 恰有一个绑定本 Browser 实例的 Policy Agent。同组显示 `<NNNN>-browser`、`<NNNN>-stream` 和 `<NNNN>-policy-agent`，容器名与环境稳定编号一一对应。重启 Supervisor 后对符合身份的资源收敛为同一组且无重复；停止后本 Profile 的 Agent 随之清理，其它环境及部署资源不受影响。
- [ ] AC-002：Stream 启动、重建和稳态收敛全程无专属 Policy Agent 及策略就绪等待。信令注册或媒体故障只触发对应恢复，Stream 替换后保留当前 Browser 会话和页面；Gateway 重启后可重新注册。
- [ ] AC-003：配置代理的 Browser 只能经指定代理和必要控制通道通信，策略无法确认或发生漂移时对应 Browser 进入既定失败封闭流程，其它 Profile 和 Stream 资源不因名称或实例相近而被接管、暂停或清理。
- [ ] [deploy] AC-004：目标 OrbStack 上，本机 Chrome 能观看、收听和操作同一个 Profile，媒体只从宿主回环入口接收。Stream 只使用约定的 Gateway 信令与本机媒体通道，隔离验证覆盖公网、局域网、宿主其它服务、Browser 与其它 Profile 的网络边界，以及有 IPv6 时的双栈行为。网络配置失配时不得把越界的 Stream 标记为可用。
- [ ] [deploy] AC-005：隔离部署从仍有两类 Agent 的 release 升级后，运行意愿和 Profile 数据保留，所有受影响环境按新形状收敛且无旧 Agent 残留。回退到受支持的上一 release 后，原有媒体和 Browser 代理功能恢复，且无跨部署清理。

### 可测试性声明

<!-- 规范（门禁必留，不得删除） -->

逐条说明不可自动测试的 AC 及替代验证；全部可测则写“全部 AC 可自动测试”。

<!-- /规范 -->

- AC-001 至 AC-003 可自动测试。AC-004、AC-005 受 Docker 后端和真实媒体行为约束，在隔离 OrbStack 部署中记录网络端点、运行资源身份与 Chrome 媒体结果。

## 上下文区

- 关联 spec：docs/specs/runtime_lifecycle.md
- 受影响 spec：`docs/specs/webrtc_remote_display.md`、`docs/specs/browser_isolation.md`、`docs/specs/release_deployment.md`。
- 来源：p154、p156（2026-11-21 核实）。`start_stream_container` 仍创建 Stream gate 和 Agent，Supervisor 在启动恢复及稳态分支检查 Stream 规则。`_ensure_media_network` 当前创建普通网桥。`policy_agent_labels` 缺 Profile 编号和 Compose 分组，`_policy_agent_name` 使用散列 slot；现有标签已携带真实目标身份。t082、t083 与 ADR 039 描述上述现行路径，未发现等价进行中 task。
- 参考：[Docker 网桥](https://docs.docker.com/engine/network/drivers/bridge/)、[Docker 端口发布](https://docs.docker.com/engine/network/port-publishing/)。

### 有意不测

- 公网或局域网浏览器接入成功：产品目标为同机 Chrome，本任务验证外部接入被拒绝。

### 测试策略

- 先用现行测试入口固化旧行为差异，验证运行时资源拓扑、Profile 展示身份、认领和孤儿清理，以及 Browser 安装、漂移和失败封闭。验证多 Profile、相似名称、旧实例事件与第二部署。
- 真实 OrbStack 验证同时覆盖成功的信令、音视频、输入，受控端点的隔离检查及旧 release 升级/回退。以当前 Stream 规则在两条允许路径之外的行为作对照。

### 未知契约清单

<!-- 规范（门禁必留，不得删除） -->

未核实的外部契约标为 `UNVERIFIED-BLOCKING` 或 `UNVERIFIED-SPIKE`；核实后改写为结论和验证方式。无则写“无”。

<!-- /规范 -->

- UNVERIFIED-SPIKE：固定媒体拓扑在目标 OrbStack 上能否同时满足宿主回环 UDP 发布、Gateway 信令与 Stream 出站隔离。实施前用隔离最小拓扑实测成功与拒绝矩阵，按结果选定声明式拓扑，记录回退条件。现有规则允许链路本地媒体回包，不能从回环发布直接推导等价拓扑。

### 风险与回退

- 风险：套用普通网桥会放开 Stream 出站，机械切成内部网桥也可能打断 OrbStack 媒体映射。存量 Agent 改名与运行实例替换涉及资源身份和启动窗口。
- 回退：按已验证的 release 回退路径重新收敛受影响的运行资源，保留数据卷和运行意愿。新 release 在网络和媒体契约未通过时不进入成功状态。避免在新运行时同时保留两套策略路径。

### 依赖与约束

- 无前置 task。以仓库支持的本机 Chrome 与 OrbStack 为验收环境。保留只读根、最小权限、既有环境隔离及严格部署归属。

### Finalization 时更新的 blueprint

- `docs/blueprint/architecture.md`、`docs/blueprint/supervisor.md`：媒体拓扑、Browser 专属策略和 Profile 资源分组。
- `docs/blueprint/testing.md`：固定媒体拓扑、资源身份及发布切换验收。
- 新增 ADR 记录拓扑实证与对应取代范围，引用 ADR 031、038、039 及 t083 的历史决策。
