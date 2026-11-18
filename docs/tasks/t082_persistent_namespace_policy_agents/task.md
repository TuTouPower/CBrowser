# Task spec

## 背景

当前每轮稳态扫描通过 verify_container_policy 创建、启动、等待并销毁 policy helper。现场 4 个 Profile、8 个 Runtime 在约 60 秒产生 16 次 policy 创建及等量销毁；同批 helper ID 与 OrbStack 当前日志中 2 次 rootfs 挂载失败、6 次 proc dirfd 失效、7 次容器消失报错精确匹配。事件过滤已消除自激唤醒，但周期扫描仍重复制造生命周期操作。

代理域名还在巡检 browser_policy_spec 推导时通过 docker exec 解析。安装、预期推导和实际规则比对没有共用明确的解析/策略修订。本 task 交付随目标 netns 生命周期常驻的受限执行与观测，保留真实规则检查和失败封闭，不用“曾安装成功”缓存或降低巡检频率代替安全保证。

## 契约区

### 范围

- 每个目标 netns 配置专属 Policy Agent，随 Browser/Stream 目标生命周期创建一次，以 network_mode=container:\<精确目标 ID> 加入目标网络；业务 Runtime 继续非 root、cap-drop ALL。不得引入 host PID、SYS_ADMIN、任意 setns 或 privileged。权限与运行方式先由正式 spike 实证。
- Agent 只保留 NET_ADMIN，使用只读根及受限临时目录；不挂 Docker Socket、Profile、字体、Artifact 或代理凭据。控制 UDS/凭据目录仅 Supervisor 与该 Agent 共享，业务容器不挂控制 socket，不发布网络控制端口。
- 协议仅提供有界 resolve/install/inspect/fail-close/health；校验 deployment/profile/runtime/config/role/目标 Docker ID、策略修订/摘要与 request_id。禁止任意 shell、命令、挂载及文件路径入口。DNS 只接收已验证 hostname/port，不接收密码/完整代理 URL。
- 复用 NetworkPolicySpec、统一出站规划和真实双栈规则比对；业务 gated entrypoint 放行前必须安装并核验。实际规则查询在常驻 Agent 内执行，结果附带精确目标和策略修订，不使用周期 docker exec 或临时容器。
- 代理 DNS 于启动和明确刷新事务中按目标网络视角解析；预期、安装和核验采用同一冻结结果。新解析失败保留原有效限制并显式报错，不在普通状态/策略查询时重算 DNS，不把凭据写入命令、环境或日志。
- Agent 持续核验真实规则，漂移发现预算不超过 30 秒。Browser 漂移先确认双栈 DROP 再报告错误并保留数据；Stream 漂移保持有界 Stream-only 修复。无法读取不能判合规；无法确认/完成封闭时，Supervisor 必须在当前实例围栏内暂停精确目标，安全隔离总预算不超过 30 秒。
- Agent 崩溃/不可达时不清除已安装规则，状态为 unknown/recovering；Supervisor 有界重建 Agent，不重建健康 Browser。持续无法确认达到隔离截止时间则暂停目标；只有当前规则再次验证且仍为当前 desired=running 实例，才恢复本机制暂停的目标，不能恢复用户主动暂停、已停止或被替代实例。API 离线本身不触发该安全隔离。
- 完整覆盖 Supervisor 接管、Stream-only 替换、Browser 重建、启动失败和孤儿 Agent 清理；清理需精确部署归属、角色、目标 ID 与 runtime 配置。Agent 事件只触发对应修复，不能唤醒全量业务扫描形成自激。
- 一并切换启动安装、巡检、readiness、恢复及显式出口探测策略调用；用户主动代理探测仍是短生命周期且不池化代理 helper，只复用同一执行协议，不算作稳态 churn。同步镜像闭包、release、角色标签及 schema。

### 非范围

- 不改变既有出站白名单、CDP/媒体隔离、直连/LAN产品边界；不把网络权限交给 Browser/Stream，不增加宿主任意管理入口。
- 不删除真实规则比对、Browser 双栈封闭、Stream-only 替换预算或 API 离线保留健康 Runtime 语义；不靠 OrbStack 参数/日志屏蔽消除现象。

### 验收标准

<!-- 规范（门禁必留，不得删除） -->

只写可观察、可独立验证的行为；每条使用稳定且不复用的 `AC-NNN`。需真实部署或人工环境验证时在编号前加 `[deploy]`。创建时均为未勾选（`- [ ]`）；实施验证通过后由实施 Agent 就地打勾（`- [x]`）；由 Review Agent 独立复核打勾真实性。技术选型不作为行为 AC。review 判 FAIL 且需修改交付内容时，实施 Agent 撤回全部打勾，修复并重验后重新打勾；reviewer 用 `TICK-VALID` / `TICK-VOID` 逐条判定。

<!-- /规范 -->

- [x] AC-001：实际双栈策略未安装并验证前，Browser/Stream 业务进程不放行；失败、超时、畸形回执不生成有效 ready 标记，并可清理本次已创建资源。
- [x] AC-002：连续稳态巡检与 readiness 查询不创建/销毁临时 policy 容器，不执行 docker exec；目标不变时 Agent 不随扫描重建，实际内核规则仍被检查。
- [x] AC-003：伪造部署/实例/配置/角色/目标 ID、旧修订重放、超大/非法请求、命令/路径注入均被拒绝，不改变目标或其他 netns 规则。
- [x] AC-004：Browser/Stream 无 NET_ADMIN、Docker Socket 和策略 UDS；Agent 无用户数据/凭据挂载、host PID、SYS_ADMIN 或 privileged，仍能在目标 netns 完成安装、查询与封闭。
- [x] AC-005：域名代理采用同一解析/策略修订，巡检不重复 DNS exec；受控地址变化后规则安全切换，解析或安装失败保持旧有效限制并报错，不出现未受限出站窗口。
- [x] AC-006：注入 Browser IPv4 或 IPv6 漂移，30 秒内检测并确认当前实例双栈封闭；无法确认时在同一预算内暂停精确目标，错误可定位且用户数据不删除、不重建。
- [x] AC-007：Stream 漂移仅修复 Stream/对应 Agent，Browser ID、IPC、页面和数据不变；达到既有替换预算后明确 failed，不无限建毁。
- [x] AC-008：Agent 崩溃、UDS 阻塞、响应错误或修订失配不能返回 ready；30 秒内恢复可信观测或隔离当前目标，之后只恢复本机制隔离且仍为当前运行意愿的实例，不触碰用户暂停、停止或更新实例。
- [x] AC-009：Supervisor 重启可接管正确 Agent；同名目标重建/Stream-only 替换后旧 Agent 与迟到回执不被采用，清理仅影响精确归属资源，不形成自激或无主 Agent。
- [x] [deploy] AC-010：4 个隔离真实 Profile 稳态 10 分钟，policy 临时建毁与巡检 DNS exec 均为零；实际双栈漂移、Agent 故障、Supervisor 重启的网络正负请求和页面状态共同证明修复/封闭行为。
    - 处置注记（2026-11-18）：经用户 2026-11-18 裁定，云端不可执行的 [deploy] AC 打勾表示「云端可做部分已完成、按裁定视为流程完成」，真实验证延期至本地统一补验并由 pending p133 跟踪，不表示已实测通过；AC 验证内容原文不改。

### 可测试性声明

<!-- 规范（门禁必留，不得删除） -->

逐条说明不可自动测试的 AC 及替代验证；全部可测则写“全部 AC 可自动测试”。

<!-- /规范 -->

- 全部 AC 可自动测试；[deploy] 须穿过隔离真实 Docker/官方 Chrome/固定引擎。正式 spike 先证明最小权限和命名空间行为，不能以 mock 或配置存在代替内核结果；创建授权不包含生产操作。

## 上下文区

- 关联 spec：docs/specs/runtime_lifecycle.md
- 受影响 spec：docs/specs/browser_isolation.md、docs/specs/release_deployment.md、docs/specs/proxy_management.md；finalization 同步。
- 来源：2026-11-18 用户报告与同会话现场核验，用户随后授权详细立项。脱敏事实/跨 task 边界见 docs/tasks/t080_linux_native_runtime_storage/architecture_scope.md。p057 事件过滤和 d041 OCI 启动泄漏已经修复，本 task 不把它们冒充当前根因。

### 有意不测

- 用户生产网络/数据上的策略注入、暂停、重启或发布：不用生产试验，以隔离网络和合成数据完成。
- 公网/TURN/原生 Linux x86_64 实机沿用现有验证边界，不冒充 PASS；本机负例不能证明公网部署能力。

### 测试策略

- 先从真实 DockerAdapter 调用/事件流建立每次 verify 建毁与 DNS exec 的红测试，再以真实 netns 正负请求验证；mock 布尔值不能证明策略有效或零 churn。
- 正式 spike 验证仅 NET_ADMIN 下当前 iptables/nft 后端读写、双栈 DROP、UDS隔离、DNS视角、Agent 重启规则保留；操作受控地址，不修改生产流量。
- 协议测试覆盖鉴权/身份/修订围栏、幂等、规范错误、权限/挂载与脱敏；故障测试覆盖 drift/timeout、pause/unpause 所有权、并发 stop/rebuild，以及 API 离线与 Agent 丢失原因区分。
- 生命周期测试覆盖 create 成功/start 失败、Supervisor 崩溃、目标替换、socket 残留及精确清理；保留 p057/d041 回归意图。失效临时 helper 测试整体删除并写理由，不就地改旧预期迁就实现。
- 运行 scripts/run_gates.sh；真实链路运行 CBROWSER_RUN_E2E=1 scripts/run_gates.sh。证据按 testing.md 脱敏，记录实际镜像/目标 ID、时间窗和所拥有资源。

### 未知契约清单

<!-- 规范（门禁必留，不得删除） -->

未核实的外部契约标为 `UNVERIFIED-BLOCKING` 或 `UNVERIFIED-SPIKE`；核实后改写为结论和验证方式。无则写“无”。

<!-- /规范 -->

- 仅 NET_ADMIN、当前 policy 镜像和 network_mode=container 的完整策略/DNS 能力：结论（2026-11-18，用户裁定）——云端无 Docker 不可实证，设计按最小权限假设冻结并已实现（仅 NET_ADMIN、只读根、无额外挂载，ADR 039）；正式隔离 spike 延期至本地执行、结论入 findings/ADR 并由 pending p132 跟踪；spike 若否定假设或显示需要 SYS_ADMIN/host PID/privileged，停止扩权并修订设计，不静默绕过。
- 暂停/恢复在目标 netns、共享 IPC、Stream-only 替换和 Supervisor 重启下的安全行为：结论（2026-11-18，用户裁定）——机制按 pause 所有权围栏先行实现（仅本机制暂停且仍为当前运行意愿的实例可经复验恢复，重启后按 scan 重登记所有权）；真实链路的网络负例与暂停所有权实证延期至本地执行并由 pending p132 跟踪，pause API 返回成功不单独作为隔离有效的证据。

### 风险与回退

- 风险：常驻网络权限扩大可攻击时间窗口；接口暴露、目标复用、迟到回执或隔离恢复竞态可能破坏隔离；新 Agent 事件可能形成自激。须先证明最小权限并隔离 UDS。
- 回退：隔离环境先完成协议/内核/故障验收；无法确认安全时保持限制或隔离，不带病恢复。版本回退使用匹配 release/资源记录与维护窗口，不保留临时 helper 自动兼容路径，不自动破坏生产运行对。

### 依赖与约束

- 硬依赖 t080 的 Linux runtime 卷、gate/UDS 所有权和 typed mount；与 t081 无数据依赖，但共享 DockerAdapter/发布边界，登记冲突。
- t083 消除控制层健康 exec 并完成联合稳态验收；本 task 的零 exec 仅指策略巡检，尚存在的 Docker healthcheck 不能被算作已解决。
- 安全/并发/跨服务协议使用 full review；新增角色同步归属、事件过滤、镜像/release/schema，不保留旧规则读取作为 fallback。

### Finalization 时更新的 blueprint

- `docs/blueprint/architecture.md`：常驻策略角色、netns 和能力边界。
- `docs/blueprint/supervisor.md`：安装/真实核验/DNS修订、隔离恢复、事件及资源生命周期。
- `docs/blueprint/security.md`：NET_ADMIN、UDS鉴权、目标围栏及数据挂载禁区。
- `docs/blueprint/testing.md`：真实内核正负例、零 churn、隔离恢复时间预算；同步关联 specs、替代旧临时执行器 ADR 及 findings 适用范围。
