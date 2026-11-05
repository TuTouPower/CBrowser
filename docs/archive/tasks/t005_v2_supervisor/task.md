# Task spec

## 背景

完整落实 docs/v2_architecture_plan.md 对应正式实施阶段。实现唯一 Docker 协调者与运行事件恢复；t001全项技术验证通过前不实施。

## 契约区

### 范围

- src/backend/cbrowser/supervisor、schemas/runtime、config/docker/supervisor_runtime、scripts/export_supervisor_protocol.py 和对应 Docker 集成测试；为内部认证RPC对接扩展API路由/应用注册并同步OpenAPI，以共享domain/runtime_policy统一API repository与Supervisor的重试阈值，不改变用户鉴权阶段范围或数据库结构。对接正式 Browser/Stream Runtime，分配网络、挂载、端口及实例，认证 RPC 协调期望/实际状态，持久事件重放与异常重试；统一数据根包含engine-cache，明确缓存/用户数据/Artifact/事件各目录的初始化及挂载权限；采集真实主机/容器CPU负载，向Stream下发Profile级过载限制。

### 非范围

- 不越过前置验证门禁，不静默缩减计划或改写验收标准；不处理与本阶段无关重构，不覆盖未获具体授权的用户数据或外部环境。

### 验收标准

<!-- 规范（门禁必留，不得删除） -->

只写可观察、可独立验证的行为；每条使用稳定且不复用的 `AC-NNN`。需真实部署或人工环境验证时在编号前加 `[deploy]`。创建时均为未勾选（`- [ ]`）；实施验证通过后由实施 Agent 就地打勾（`- [x]`）；由 Review Agent 独立复核打勾真实性。技术选型不作为行为 AC。review 判 FAIL 且需修改交付内容时，实施 Agent 撤回全部打勾，修复并重验后重新打勾；reviewer 用 `TICK-VALID` / `TICK-VOID` 逐条判定。

<!-- /规范 -->

- [x] AC-001：真实启动两个 Profile，各有独立 Browser/Stream 容器、Xauthority/Pulse/IPC 和受限挂载；Stream 复用对应 Browser IPC，跨 Profile 访问失败，所有挂载规范化后位于允许数据根目录，路径穿越及符号链接逃逸被拒绝。

- [x] AC-002：并发生命周期请求幂等执行，Profile 使用独立且内外一致的 UDP mux 端口；端口耗尽明确报错、不重复分配；停止先标不可用并断 Viewer，再停 Stream/Browser，确认释放后回收端口。

- [x] AC-003：Supervisor 是唯一持有 Docker Socket 的服务，不挂载 SQLite；通过认证 RPC 获取配置和上报事件，未授权控制请求失败；事务内不等待容器启动。

- [x] AC-004：API 离线期间事件落盘，恢复后按 event_id 去重并校验 runtime_instance_id；Supervisor SIGKILL 重启扫描现存容器，等待 API 期望状态后协调，正常浏览器关闭在双方重启后仍不误启动。

- [x] AC-005：首次异常退出保留运行意愿，随后按2/10/30秒各重试一次，三次重试均失败后阻断（failure_count记录实际异常总数，此时为4），手动重试清除阻断；正常退出与主动停止不重试，Browser restart policy 为 no。

- [x] AC-006：Stream 仅接入对应媒体网络，Gateway/coturn 动态接入且实际网络地址明确下发；重复创建/失败回滚不残留孤立容器、端口和网络，不影响其他 Profile。

- [x] AC-007：真实CPU过载触发Profile级资源限制，Stream实际降帧且恢复负载后回归活动目标；低负载和全后台对照不误触发，调度决策可查询并关联测量窗口，不将Viewer心跳当控制租约。

### 可测试性声明

<!-- 规范（门禁必留，不得删除） -->

逐条说明不可自动测试的 AC 及替代验证；全部可测则写“全部 AC 可自动测试”。

<!-- /规范 -->

全部AC具备可自动验证路径；需真实部署/用户数据/原生平台的行为必须具备对应环境和授权，缺失时保持未通过，不用模拟替代。

## 上下文区

- 来源：docs/v2_architecture_plan.md；t001/t002已集成，t003/t004完成真实整镜像、Chrome及独立full review，于84f84311815b合入main。公网和原生Linux x86执行仅两项USER_WAIVED，保留支持；本task真实Docker、恢复和资源验收不豁免。

### 有意不测

- 无已豁免计划行为；范围外阶段由其独立task执行，不据此取消完整目标验收

### 测试策略

- 真实 Docker Engine 和独立 API/Supervisor 进程，SIGKILL/离线事件重放/并发分配/异常重试实测；单测补路径规范化和状态机，不 mock Docker 来证明权限与网络。

### 未知契约清单

<!-- 规范（门禁必留，不得删除） -->

未核实的外部契约标为 `UNVERIFIED-BLOCKING` 或 `UNVERIFIED-SPIKE`；核实后改写为结论和验证方式。无则写“无”。

<!-- /规范 -->

- 前置契约已核实：t002 API/事件模型、t003 Runtime UDS/SDK持久上下文及生命周期事件、t004 Stream主动注册/认证会话/配额控制已真实验证。接口以schemas/runtime/agent_protocol.json、schemas/stream/agent_protocol.json及实际Pydantic为准。Browser03/Stream07不可变镜像与只读Linux引擎缓存已保留，main合并后13Runtime和12Stream E2E通过。
- Browser使用shareable IPC/1GiB shm及restart policy no；Stream仅共享对应Browser IPC/hostname，挂XSocket文件/Xauthority/Pulse子目录，不挂runtime全目录、用户数据、agent.sock或Docker Socket。音频为cbrowser_sink.monitor/48000Hz/S16LE/双声道，UDP mux端口池30000–30991。
- 自有Supervisor RPC与CPU采样调度由本task实现并先红后绿验证，不将待实现自有协议当已有外部能力。RPC不得在SQLite事务内等待容器启动；测试使用新数据根和随机短凭证，正式凭证由外部文件提供，不设默认。实际用户数据迁移和公网发布留原定后续task。

### 风险与回退

- 风险：跨服务权限、并发恢复、凭证或数据一致性可能失败；任何未验证行为不得凭配置字段或模拟通过。
- 回退：隔离worktree、测试数据根和容器资源；保留失败日志，回退本阶段产物。生产数据和外部变更按具体验证备份/回滚方案执行。

### 依赖与约束

- 必须先取得t002,t004完成产物；所有正式实施继承t001全项通过硬门禁。保持计划20实施顺序；公共文档/索引由主控串行收尾。

### Finalization 时更新的 blueprint

- docs/blueprint/supervisor.md：单 Socket 持有者、事件与生命周期；docs/specs/runtime_lifecycle.md：幂等、重试、网络与端口。
