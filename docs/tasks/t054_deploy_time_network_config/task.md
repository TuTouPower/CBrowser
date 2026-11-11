# Task spec

## 背景

2026-11-10 intensive review（`docs/reviews/review_20261110_200842`）在网络域列出 33 个问题（第 24–40、43–54、59–62、102、113、114 项）。它们全部出在「运行时修改网络配置」这条跨进程链路上：API / Gateway / Supervisor / 磁盘四方各持一份状态（Gateway publication 回执只在内存、ACK 不幂等、revoke 无身份校验、fencing 只在 Supervisor 内存且依赖 header 自觉携带、运行时读者不校验已应用状态、双文件写非联合原子、哈希不覆盖端口、部署指纹哈希的是生成器源码、rollback 不重读、恢复循环与 apply 并发），并且 LAN 媒体面整条未接线（`_get_applied_network_config` 零调用、`allow_lan_media` 恒为 False、新 Stream 与稳态替换都回落 loopback）。

ADR 026（t042）以 LAN 访问需求为前提，由 Supervisor 接管边缘重建。之后用户在 p053 明确放弃原生 LAN，设置页却仍暴露 LAN 开关与运行时改端口。用户 2026-11-10 在 adoption_decision D1 选择 C：网络配置回到部署期，删除运行时网络应用整条链路与全部 LAN 代码（采纳项 A61）。

同时第 41、42 项（A14）：`CBROWSER_TRUSTED_PROXY_CIDRS` 在 compose / deploy / `.env.example` 中均未接线，生产环境中所有请求的来源都是 Caddy 地址，登录、令牌与 viewer 限流按单一来源聚合；client_ip 解析器在 `auth/client_ip.py` 与 `gateway/client_ip.py` 有两份逐字节相同的副本。

## 契约区

### 范围

- 删除 LAN：设置页 LAN 开关与 IP 输入、`lan_access_enabled` / `lan_advertised_ip` 模型字段与两份校验、`allow_lan_media` 与 LAN 媒体策略分支、Stream `bind_host` / `advertised_ip` 参数与标签、root-ca 下载端点与前端链接；Caddy HTTPS 端口与 Stream UDP mux 固定绑定 `127.0.0.1`。
- 删除运行时网络应用：API 网络设置写接口、apply 与 disconnect 预检、`NetworkService` 事务、Gateway publication 协议（authorize / ACK / revoke）、Supervisor `rebuild-edge` / `converge-streams` 端点、restore fencing、operation journal 中的网络回执、已应用状态双文件；以增量迁移删除网络事务与 pending / applied 网络配置表。
- HTTPS 端口只由 `.env` 的 `CBROWSER_HTTPS_PORT` 决定，部署时生效；默认端口收敛为单一常量，删除后端、脚本与前端中的重复字面量。
- Origin 白名单由部署配置确定性派生（`127.0.0.1` / `localhost` + 端口），API 与 Gateway 读取同一部署输入；删除 Gateway 磁盘状态重读的死代码。
- 部署指纹改为哈希最终 Caddyfile 产物；rollback 使用目标 release 记录的端口与 Caddyfile。
- 设置页保留只读网络信息（当前访问地址与端口），删除网络设置表单。
- 可信代理来源：compose 的 edge 网络固定 IPAM 子网，deploy.sh 推导并注入 `CBROWSER_TRUSTED_PROXY_CIDRS` 到 API 与 Gateway；client_ip 解析器合并为一个共享模块，Gateway 镜像按文件白名单纳入。
- 删除失效的网络事务、publication、fencing、LAN 相关测试并写明理由；新增覆盖新语义的结构测试与行为测试。

### 非范围

- 不实现任何 LAN / 多设备访问（p053 保持 parked）。
- 不保留运行时改端口能力，不做旧网络配置数据迁移或兼容。
- 不改 HTTPS-only 决定（D14）与 Origin 归一化算法本体。
- 不改 Gateway viewer 授权与限流模型本体（只改来源识别接线）。

### 验收标准

<!-- 规范（门禁必留，不得删除） -->

只写可观察、可独立验证的行为；每条使用稳定且不复用的 `AC-NNN`。需真实部署或人工环境验证时在编号前加 `[deploy]`。创建时均为未勾选（`- [ ]`）；实施验证通过后由实施 Agent 就地打勾（`- [x]`）；由 Review Agent 独立复核打勾真实性。技术选型不作为行为 AC。review 判 FAIL 且需修改交付内容时，实施 Agent 撤回全部打勾，修复并重验后重新打勾；reviewer 用 `TICK-VALID` / `TICK-VOID` 逐条判定。

<!-- /规范 -->

- [x] AC-001：API 不再提供任何修改网络配置的端点，也不提供 root-ca 下载端点；OpenAPI 中不存在 LAN 与网络 apply 相关字段与路径。
- [x] AC-002：设置页只显示当前访问地址与端口，无 LAN 开关、IP 输入、端口输入或「应用」操作。
- [x] AC-003：部署后 Caddy HTTPS 端口与全部 Stream UDP mux 端口只绑定 `127.0.0.1`；compose 结构测试与 Supervisor 容器规格测试对此断言。
- [x] AC-004：修改 `.env` 中 `CBROWSER_HTTPS_PORT` 后重新部署，新端口生效，API 与 Gateway 的 Origin 白名单同时更新为新端口，旧端口不可访问。
- [x] AC-005：仓库中默认 HTTPS 端口只在一处定义，其余位置引用它；测试对重复字面量做负向断言。
- [x] AC-006：只修改网络配置（端口）而不改源码时，部署指纹随之变化并触发 Caddy 重建；rollback 后 Caddy 绑定的端口与目标 release 记录一致。
- [x] AC-007：Supervisor 不再提供 `rebuild-edge` / `converge-streams` 端点；Gateway 不再接受 publication 协议请求；网络事务相关表经增量迁移删除。
- [x] AC-008：经 Caddy 进入的登录与 viewer 请求，限流按真实客户端来源计数：两个不同来源各自独立计数，一个来源被锁定不影响另一个。
- [x] AC-009：API 与 Gateway 使用同一 client_ip 解析实现；不在可信 CIDR 内的对端发送的 XFF 不被采信。
- [x] AC-010：[deploy] 真实部署后：本机浏览器可登录、启动 Profile 出图；从本机以外的接口访问 HTTPS 与 UDP 端口被拒绝；修改端口重新部署后可用新端口登录。

### 可测试性声明

<!-- 规范（门禁必留，不得删除） -->

逐条说明不可自动测试的 AC 及替代验证；全部可测则写“全部 AC 可自动测试”。

<!-- /规范 -->

- AC-001..009：可自动测试（OpenAPI 结构断言、前端组件测试、compose / container_spec 结构测试、fake Docker CLI 驱动 deploy.sh、迁移测试、经 Caddy 拓扑的集成测试或模拟 XFF 链路的单测）。
- AC-010：真实部署验证；替代验证为 `scripts/deploy.sh deploy` 后人工执行登录、出图、外部接口探测与改端口重新部署，并记录结果。

## 上下文区

- 来源：`docs/reviews/review_20261110_200842/adoption_decision.md` A61（原 D1，用户 2026-11-10 选 C）、A14；审阅原文第 24–42、43–54、59–62、102、113、114 项。核实：2026-11-10 抽验 `_get_applied_network_config` 零调用、compose / deploy / `.env.example` 无 `CBROWSER_TRUSTED_PROXY_CIDRS`、设置页仍有 LAN 开关（`SettingsPage.tsx:69-139`）。
- 前提变化：ADR 026 的 LAN 前提已被 p053（用户放弃原生 LAN）推翻；本 task 新增 ADR 替代 ADR 026 的运行时边缘重建部分。

### 有意不测

- 删除后的代码路径：随代码删除，不保留测试。
- 宿主多网卡环境下的外部可达性：以 AC-003 的绑定结构断言替代，真实部署人工抽查（AC-010）。

### 测试策略

- 结构：compose 端口绑定 loopback；OpenAPI 不含网络写端点与 LAN 字段；默认端口单一定义。
- deploy.sh：fake Docker CLI 覆盖端口变更后的指纹变化、rollback 端口一致、`CBROWSER_TRUSTED_PROXY_CIDRS` 注入与 edge 子网一致。
- 单元 / 集成：client_ip 共享模块的可信与不可信 XFF；限流按真实来源计数；Origin 白名单随部署端口派生。
- 迁移：增量迁移删除网络事务表后 API 正常启动。

### 未知契约清单

<!-- 规范（门禁必留，不得删除） -->

未核实的外部契约标为 `UNVERIFIED-BLOCKING` 或 `UNVERIFIED-SPIKE`；核实后改写为结论和验证方式。无则写“无”。

<!-- /规范 -->

- 无。edge 网络固定 IPAM 子网与 compose 端口绑定为 Docker 标准语义；Caddy 作为反向代理设置 XFF 为其默认行为，实施时以集成测试确认。

### 风险与回退

- 风险：删除面大，遗漏引用会导致构建或门禁失败；实施时全量 grep `lan_`、`network_service`、`publication`、`rebuild-edge`、`converge-streams`、`root-ca`、`applied_network`。
- 风险：edge 固定子网与宿主已有网络冲突；deploy.sh 预检子网冲突并给出可执行提示。
- 回退：revert 实现 commit；增量迁移删除的表无真实数据。

### 依赖与约束

- 与 t051 冲突（`compose.yaml`、`scripts/deploy.sh`、Supervisor），须在 t051 合并后开始。
- 与 t055（Supervisor `core.py`）、t056（错误契约、迁移）存在文件重叠，按 `conflicts_with` 串行。

### Finalization 时更新的 blueprint

- `docs/blueprint/decisions.md`：新增 ADR「网络配置为部署期配置」，替代 ADR 026 运行时边缘重建部分，记录 p053 前提变化。
- `docs/blueprint/gateway.md`、`docs/blueprint/supervisor.md`、`docs/blueprint/security.md`、`docs/blueprint/architecture.md`：删除运行时网络应用与 LAN 描述，写明端口与 Origin 来源、可信代理来源。
- `docs/specs/access_control.md`：删除 LAN 段，改写 Origin 派生与来源识别。
- `docs/specs/release_deployment.md`：端口、指纹与 rollback 语义。
