# 审阅结果决策（架构优先重评）

## 重评依据

用户指令：以最优架构、最优设计、最少技术债为目标，不按开发时间与改动规模取舍。据此本次重评采用以下原则，替代初版“成本/收益”导向的判断：

1. **单一权威**：运行观测态以 Supervisor + Docker 的真实状态为准；容器内事件只作诊断补充，不驱动生命周期状态。
2. **边界 fail-closed**：网络、凭证、文件权限、过期凭证、未保护沙箱一律显式拒绝并记录，不静默放行。
3. **单一来源**：端口、配置、协议、枚举常量只有一个权威定义，禁止多处硬编码。
4. **生命周期确定性**：停止、清理、端口释放、轮换任务、pending future 都有明确所有权与取消路径。
5. **数据语义可解释**：删除即删除（隐私优先），审计与运行事件分离；规范与实现必须一致。
6. **资源有界**：所有缓存、数组、spool、ACK 集合都有上限或回收机制。
7. **测试确定性**：禁止固定 sleep、禁止依赖静止画面出帧，测试必须触达生产逻辑。

### 与初版决策的差异

- 原 **D1–D12 全部转为采纳**，按上述原则选择方案；仅保留 **D1 数据保留策略** 作为待决定项（涉及隐私与审计的业务取舍）。
- 原 **R1–R10、R13–R15、R18、R19、R21–R23、R26–R28 转为采纳**（已登记 pending 的条目在修复落地后按 pending 流程归档）。
- 原 R11（t008 自动化接入面）仍为阶段外；新增保留不采纳：伪造 exit 事件（同信任域内签名无效，改为严格校验+隔离+文档记录）、内部 RPC 回环（协调设计本意）、Secure Cookie（契约正确）、隧道透传（同信任域）、前端 fail-open（合理降级）、协调器启动顺序（自愈设计）、缓存全量校验（安全措施）。

## 目录

docs/reviews/review_20261101_075819

## 报告来源

- 已读：review_opencode_cpa_gemini_3_8_flash.md, review_opencode_opencode_go_deepseek_v4_1_flash.md, review_opencode_opencode_go_muse_spark_1_3_contributor.md
- 缺失：无（本目录仅 opencode 三路；无 claude / kimi / grok / antigravity，无 intensive bundle）
- 合并说明：三路共约 75 条原始 finding，按“同一架构边界/同一失效模式”归并为 40 项决策。归并映射：
    - A1 = deepseek D8/COR-9 + deepseek COR-4 + deepseek ROB-3 + deepseek SEC-2（缓解部分）+ TEST-2 + TEST-8
    - A2 = deepseek D1/SEC-1 + TEST-1 + deepseek DOC-2
    - A3 = deepseek D5/COR-2 + deepseek COR-11 + TEST-3 + TEST-10
    - A4 = deepseek D4/COR-1 + CT-9 + gemini SEC-003 + deepseek CT-3 + muse C6（p005-f001）
    - A5 = gemini SEC-002 + deepseek SEC-5 + muse S6（p006）+ muse S3 + D12
    - A6 = deepseek D7 + muse S2
    - A7 = deepseek D3/SEC-3 + muse S1
    - A8 = deepseek D6/COR-5 + muse C1 + muse C2 + muse C7（p005-f002）+ muse C8（p005-f003）+ gemini COR-002（p012）+ TEST-7
    - A9 = deepseek D10/PERF-3
    - A10 = deepseek D11/PERF-4 + muse C4 + muse C5（前端部分）
    - A11 = muse K1
    - A12 = deepseek COR-6 + COR-7 + TEST-6 + muse R28
    - A13 = deepseek COR-3 + TEST-4
    - A14 = deepseek COR-8
    - A15 = gemini ROB-001 + gemini ROB-002 + deepseek ROB-1 + deepseek COR-12 + muse C5（快照 id）
    - A16 = deepseek ROB-2 + SEC-4 + muse R1 + muse R2 + muse C5（心跳身份）
    - A17 = deepseek CT-2 + ARCH-5
    - A18 = gemini PERF-001 + deepseek PERF-2
    - A19 = deepseek D9/PERF-1
    - A20 = gemini COR-001
    - A21 = gemini SEC-001
    - A22 = deepseek ROB-5
    - A23 = deepseek ROB-4
    - A24 = deepseek ARCH-1（R27）
    - A25 = deepseek ARCH-3 + gemini ARCH-001（p001）
    - A26 = deepseek CT-1/DOC-1 + deepseek CT-5/DOC-4 + deepseek CT-6/DOC-5 + deepseek CT-7/DOC-6 + deepseek CT-8 + muse K2（spec 部分）
    - A27 = muse D1 + muse K2（端口/部署部分）+ deepseek SEC-6 + deepseek DOC-7
    - A28 = gemini TST-001（p009/p013）+ gemini TST-002（p011）
    - A29 = gemini ARCH-002（p007）
    - A30 = deepseek ARCH-4
    - A31 = muse S7
- 保留不采纳：deepseek SEC-2（原 D2）、deepseek CT-4、deepseek ARCH-2、muse S4、muse S5、muse C3、deepseek ROB-6、deepseek PERF-5。
- 核对方式：已对关键结论做源码/规范实地核对（network_policy、path_validator、docker_adapter、core、recovery_coordinator、repository、models、runtime_coordinator、router、auth_router、rate_limiter、rotation、gateway/server、gateway/config、diagnostics、event_forwarder、pyproject、app、runtime_agent/runner、useBrowserSession、相关 specs/blueprint）。未运行测试、Docker、浏览器；涉及真实内核/Docker 行为的结论仍标注为静态推断。

## 统计

- 采纳：31 项
- 不采纳：8 项
- 待决定：1 项

## 待决定项（请先决策）

### D1. 删除 Profile 时 runtime_events 的保留策略

- 来源：review_opencode_opencode_go_deepseek_v4_1_flash（COR-10、TEST-5）
- 位置：src/backend/cbrowser/adapters/database/models.py:205-225；src/backend/cbrowser/adapters/database/repository.py:399-405；docs/specs/runtime_persistence.md:23
- 优先级：MEDIUM
- 详细判断理由：已核对：RuntimeEventModel.profile_id 为 `ondelete="CASCADE"`，删除 Profile 会清空运行事件；而 spec 明确要求“历史运行事件与审计记录保留作为去重凭据与历史审计总账”。但 Profile 删除是用户的隐私操作，保留运行事件与删除意图冲突；去重凭据在 Profile 删除后也已无意义，审计职责由独立的 audit_events 承担（无 FK，已保留）。这是隐私与审计保留之间的业务取舍，需用户确认，不能由实现单方面决定。
- 选项：
    - A 随 Profile 级联删除 runtime_events，仅保留 audit_events；同步修订 runtime_persistence spec，删除“运行事件保留”表述（推荐：隐私优先，去重凭据随 Profile 消亡，审计仍有独立总账）
    - B 按现 spec 保留运行事件：FK 改 SET NULL + nullable，新增迁移与孤儿事件查询/清理策略，保留审计价值
    - C 保留但脱敏：删除 profile_id/instance_id 等标识，仅保留匿名统计
- 推荐：A
- 推荐理由：删除语义应与用户意图一致；审计需求已由 audit_events 覆盖；B/C 都会引入孤儿数据与额外清理债。选 A 需同步 A26 的 spec 修订。
- 用户决策：A（审批通过时确认按推荐 A 执行）A

## 采纳项

### A1. 观测态权威化：lifecycle/error 收敛、扫描不覆盖、坏事件隔离

- 来源：review_opencode_opencode_go_deepseek_v4_1_flash（D8、COR-9、COR-4、ROB-3、TEST-2、TEST-8）
- 位置：src/backend/cbrowser/runtime_agent/runner.py:593-635；src/backend/cbrowser/supervisor/core.py:126-369；src/backend/cbrowser/adapters/database/repository.py:648-663；src/backend/cbrowser/supervisor/recovery_coordinator.py:112-235；src/backend/cbrowser/supervisor/event_forwarder.py:163-181
- 优先级：HIGH
- 详细判断理由：已核对：API 对 heartbeat/lifecycle 只落库不改 observed_state；Supervisor 只记录 lifecycle；scan 只要容器 running 就重建会话为 running，并每秒覆盖刚写入的观测态；event_type 未严格校验，且投递失败的坏事件会 `break` 阻塞后续重放。结果是 Chrome 已死但系统长期显示 running，自动恢复不触发；同时容器内写坏事件可毒化 spool。docs/findings/d016 已明确期望 lifecycle/error 收敛为 error 观测并保留 running 意愿。注意：容器内进程属于该 Profile 的信任域，伪造事件的影响限本 Profile；本项不引入签名，而是消除“事件驱动生命周期”的错误设计。
- 修复说明：
    1. Supervisor 定义权威观测：以 Docker 容器状态 + 容器 ExitCode 判定容器生命周期；以 Runtime Agent 进程监督结果（lifecycle/process_observation_lost）判定容器内浏览器生命周期。两者合并为 `observed_state`，通过内部 RPC 上报 API。
    2. API 不再让磁盘事件改变 observed_state/desired_state；lifecycle/error 由 Supervisor 上报的观测收敛为 `observed_state=error`，保留 `desired_state=running` 与 failure_count 策略（按 d016/ADR 008）。
    3. `scan_and_reconcile_existing` 对同实例已存在会话短路，仅在 Docker 状态变化或实例不一致时更新会话；禁止用容器 running 覆盖 error。
    4. `consume_disk_events` 与 `replay_spooled_events` 严格校验 event_type 枚举、exit_code 类型、config_version；非法事件移入 quarantine 并 warning，不阻塞后续；合法但未知事件只作诊断。
    5. 补真实子进程用例：Chrome 被 SIGKILL 但容器仍 running → observed_state=error → Recovery 触发重试；伪造 exit 0 文件不改变 desired_state（TEST-2/TEST-8）。

### A2. 网络策略按角色与 webrtc_mode 生成，Stream 不再无条件公网放行

- 来源：review_opencode_opencode_go_deepseek_v4_1_flash（D1/SEC-1、TEST-1、DOC-2）
- 位置：src/backend/cbrowser/supervisor/network_policy.py:143-148, 191-196；docs/blueprint/supervisor.md:49；docs/specs/runtime_lifecycle.md:10
- 优先级：HIGH
- 详细判断理由：已核对：IPv4/IPv6 规则在私有段 DROP 后对 browser 与 stream 无差别追加 `-A OUTPUT -j ACCEPT`；规范要求 Stream 仅放行 Gateway、coturn 与本实例 UDP mux。Stream 持有屏幕与音频，当前可向任意公网外传，是容器边界的直接失效。但 Stream 与远端 Viewer 的直连 P2P 需要访问 Viewer 的候选地址，不能在所有模式下都收死。
- 修复说明：
    1. `NetworkPolicySpec` 增加 `webrtc_mode`（或由 Supervisor 传入），策略生成按模式分档：
        - relay-only：Stream 仅放行 Gateway、coturn、本实例 UDP mux，禁止最终 `OUTPUT ACCEPT`；
        - local/lan/public：Stream 允许公共目的地址（Viewer 直连），私有/保留段继续 DROP。
    2. Browser 角色维持公共可达、私有/保留拒绝、代理白名单。
    3. 增加 stream 规则单测（relay-only 无最终 ACCEPT、非白名单公网负例、mux 放行）与内核 E2E 负例；同步修订 supervisor.md、runtime_lifecycle.md 的模式矩阵（与 A26 合并处理）。

### A3. 停止与清理不依赖信令面；端口释放有确定路径

- 来源：review_opencode_opencode_go_deepseek_v4_1_flash（D5、COR-2、COR-11、TEST-3、TEST-10）
- 位置：src/backend/cbrowser/supervisor/core.py:559-605, 666-699；src/backend/cbrowser/api/runtime_coordinator.py:380-446
- 优先级：MEDIUM
- 详细判断理由：已核对：Gateway 503/TransportError 且 Stream 仍 running 时 `disconnect_viewers` 重抛，stop 不进入 teardown；API 协调循环 `max_retries=None` 永久重试。另：start 失败路径先 teardown 再 release，teardown 抛出时端口不释放，反复后端口池耗尽。停止与清理不应依赖可失效的信令通道。
- 修复说明：
    1. `disconnect_viewers` 改为 best-effort：设置短超时，失败只 warning，然后继续 teardown；停止语义由“容器已删除、端口已释放”定义，不由信令成功定义。
    2. 端口释放在独立 `try/finally` 中执行；teardown 失败时记录 error 并仍释放端口，残留容器由启动前 orphan cleanup 收敛（避免端口二次分配冲突需在 release 前校验同 Profile 容器归属）。
    3. API 停止协调：保留退避重试但设置上限并显式暴露 `last_coordinator_error`；提供手动重试；禁止无限静默重试。
    4. 补 Gateway 503 + Stream running 的停止用例、teardown 注入失败的端口释放用例（TEST-3/TEST-10）。

### A4. 配置单一来源：Gateway 端口与 Origin 归一

- 来源：review_opencode_opencode_go_deepseek_v4_1_flash（D4、COR-1、CT-9、CT-3）；review_opencode_cpa_gemini_3_8_flash（SEC-003）；review_opencode_opencode_go_muse_spark_1_3_contributor（C6）
- 位置：src/backend/cbrowser/gateway/config.py:28, 68-71, 86；src/backend/cbrowser/supervisor/docker_adapter.py:494, 569, 796；src/backend/cbrowser/supervisor/core.py:80
- 优先级：MEDIUM
- 详细判断理由：已核对：Gateway 默认 18080，Supervisor 硬编码 18097 且调用点未覆盖；按文档默认部署时 Stream Agent 注册必然失败。Gateway 解析 `CBROWSER_ALLOWED_ORIGINS` 未 rstrip，合法 Origin 会被 403（API 侧已归一）。这是多处硬编码与边界归一缺失造成的契约漂移。
- 修复说明：
    1. 定义唯一的 Gateway 端点配置（host/port）对象，由 Supervisor 配置/环境读取并传入 `attach_profile_infrastructure` 与 Stream 启动参数；删除 18097 硬编码；默认值统一为 18080。
    2. Gateway 与 Supervisor 共用同一配置来源；启动时校验端口与 URL 一致，不一致拒绝启动。
    3. `CBROWSER_ALLOWED_ORIGINS` 在 Gateway 与 API 共用归一函数（解析为 scheme+host+port，忽略尾斜杠/默认端口）。
    4. 补默认值集成测试与带尾斜杠 Origin 的握手用例；闭环 p005-f001。

### A5. 凭证与秘密边界：Agent secret 迁出 runtime、内部 token 强制 0600

- 来源：review_opencode_cpa_gemini_3_8_flash（SEC-002）；review_opencode_opencode_go_deepseek_v4_1_flash（SEC-5）；review_opencode_opencode_go_muse_spark_1_3_contributor（S6、S3）
- 位置：src/backend/cbrowser/supervisor/core.py:492-497；src/backend/cbrowser/supervisor/docker_adapter.py:681；src/backend/cbrowser/api/internal_supervisor.py:21-30；src/backend/cbrowser/api/internal_gateway.py:20-29；src/backend/cbrowser/supervisor/control_server.py:46-48；src/backend/cbrowser/gateway/config.py:11-19
- 优先级：MEDIUM
- 详细判断理由：已核对：`agent_secret.txt` 以 0644 写入 `runtime/<profile>/`，而该目录以 rw 挂入 Browser，网页沙箱逃逸后可冒充 Stream Agent；内部服务 token 只校验长度不校验文件模式。两者都是凭证边界不一致，且 Agent secret 与 D2 的伪造事件风险同源。
- 修复说明：
    1. `agent_secret.txt` 迁至 `secrets/<profile>/agent_secret.txt`，0600，仅挂载给 Stream 容器；Browser 容器不再可见。同步更新 `PathValidator`、测试与 E2E 夹具。
    2. 内部 Supervisor/Gateway/Control token 读取时校验 `(mode & 0o077) == 0`，否则拒绝启动；统一为一个 `read_secret_file` 工具，避免四处重复。
    3. 补 Browser 容器不可见 agent secret 的断言测试、0644 token 被拒的单元测试；闭环 p006。

### A6. 宿主目录权限模型：显式属主 + 最小权限

- 来源：review_opencode_opencode_go_deepseek_v4_1_flash（D7）；review_opencode_opencode_go_muse_spark_1_3_contributor（S2）
- 位置：src/backend/cbrowser/supervisor/docker_adapter.py:354-404
- 优先级：MEDIUM
- 详细判断理由：已核对：profile/runtime/events/exchange 统一 chmod 0777，x11 另补 1777；Supervisor 容器以 root 建目录、Browser/Stream 以 uid 1000 运行。多用户宿主下任意 UID 可读写其他 Profile 目录，与严格隔离冲突；但直接收紧会破坏容器写入。
- 修复说明：
    1. 建立显式权限模型：目录创建后 chown 至运行容器的固定 uid/gid（1000:1000），profile/runtime/events/exchange 设 0700/0750；x11 保持 1777（X11 socket 语义）；engine-cache/geoip 只读挂载且宿主不可写。
    2. 宿主直跑 Supervisor（开发/测试）使用可配置 uid/gid 或跳过 chown，避免误改用户文件。
    3. 增加权限断言测试（目录 mode、属主、Browser 可写/其他 uid 不可读）；在 security blueprint 记录威胁模型。

### A7. 认证限速与受信代理边界

- 来源：review_opencode_opencode_go_deepseek_v4_1_flash（D3、SEC-3）；review_opencode_opencode_go_muse_spark_1_3_contributor（S1）
- 位置：src/backend/cbrowser/api/v1/auth_router.py:65；src/backend/cbrowser/auth/service.py:97-134；src/backend/cbrowser/auth/rate_limiter.py:9-39
- 优先级：MEDIUM
- 详细判断理由：已核对：限速键为 `request.client.host`，未消费 X-Forwarded-For；经 Caddy 后所有请求同源，任一来源 5 次失败即全局 429；并发/重启计数丢失。单机降低实际危害，但仍是可用性 DoS 与审计来源失真。
- 修复说明：
    1. 新增受信代理 CIDR 配置；仅当直连来源属于受信代理时，按 X-Forwarded-For 从右向左取第一个非代理地址作为客户端 IP；否则使用直连地址。
    2. 限速分两层：每来源滑动窗口（如 5 次/60s）+ 全局管理员预算（如 20 次/15min），避免无限猜解与单源锁死。
    3. 429 返回 Retry-After；记录来源与命中层级（不记录密码）。
    4. 补 XFF 信任/不信任、全局预算、429 的集成测试。

### A8. TURN 轮换与连接生命周期：代际校验、过期 fail-closed、任务取消、关闭码透传

- 来源：review_opencode_opencode_go_deepseek_v4_1_flash（D6、COR-5、TEST-7）；review_opencode_opencode_go_muse_spark_1_3_contributor（C1、C2、C7、C8）；review_opencode_cpa_gemini_3_8_flash（COR-002）
- 位置：src/backend/cbrowser/gateway/rotation.py:75-116, 163-176, 200-260；src/backend/cbrowser/gateway/server.py:254-276, 421-422；src/backend/cbrowser/stream_agent/agent.py:207, 624-628, 896-924, 1043-1046；src/backend/cbrowser/rtc_config/service.py:95-105
- 优先级：MEDIUM
- 详细判断理由：已核对：offer/answer/commit future 只按 conn_id 匹配，不校验 generation；current generation 过期后 get_effective_generation 仍返回它；新连接未登记为已迁移，轮换到期会多做一次 ICE restart；Supervisor 断开不取消 rotation 任务/pending future；Agent 上行关闭码硬编码 1000，丢失 Selkies 4001 驱逐语义。这些问题共同造成轮换状态不可解释、连接关闭原因丢失。
- 修复说明：
    1. 轮换状态机为每个 pending future 记录期望 generation，三个 handler 校验错代丢弃并 warning。
    2. `get_effective_generation` 在 current 已过期且无有效 in-progress 时返回“无可用代”，新 Viewer 连接 fail-closed（503 + 明确错误），不静默下发过期凭证。
    3. 新连接建立时登记为当前/进行中代的已迁移连接；轮换只处理未迁移连接。
    4. Supervisor disconnect / stop 时取消该 Profile 的 `active_restarts` 与三类 pending future，清理幂等。
    5. `_upstream_reader` 读取并透传 upstream close_code/reason；Agent `connect_and_run` finally 取消 restart 任务。
    6. 补错代 offer、过期 current、断连取消、4001 关闭码的测试；闭环 p005-f002/f003 与 p012。

### A9. 事件 spool 生命周期：游标、回收、有界 ACK

- 来源：review_opencode_opencode_go_deepseek_v4_1_flash（D10、PERF-3）
- 位置：src/backend/cbrowser/supervisor/core.py:298-369；src/backend/cbrowser/supervisor/event_forwarder.py:43-46；src/backend/cbrowser/supervisor/recovery_coordinator.py:40-43；src/backend/cbrowser/runtime_agent/event_storage.py
- 优先级：MEDIUM
- 详细判断理由：已核对：Supervisor 每秒全量 glob 并重读所有事件文件；spool 已投递文件不删除，`_acknowledged` 启动全量读入；recovery 的实例集合无界。8h 长跑线性增长，扫描成本随时间上升。去重权威实际在 API 的 event_id 主键，Supervisor 无需永久保留文件与集合。
- 修复说明：
    1. Supervisor 为每个实例维护持久化/可重建的“已处理事件游标”（event_id/mtime），只处理游标之后的事件；不再每秒重读历史。
    2. spool 文件投递成功后删除或移入 `archive/`（按容量/时间轮转）；`_acknowledged` 改为有界最近集合或直接依赖 API 幂等。
    3. 内存集合（`_reported_dead_instances`、`_native_exit_instances`）随实例/session 结束清理。
    4. Runtime Agent 侧保留每实例最新 N 条事件用于状态查询，旧文件轮转；避免 Supervisor 删除 Agent 正在使用的状态文件。
    5. 补长跑/大量历史事件下的游标与回收测试。

### A10. 前端资源有界、状态机清理与输入合并

- 来源：review_opencode_opencode_go_deepseek_v4_1_flash（D11、PERF-4）；review_opencode_opencode_go_muse_spark_1_3_contributor（C4、C5 前端部分）
- 位置：src/frontend/src/features/browser-session/adapter.ts:67-77, 156-158, 358-369；src/frontend/src/features/browser-session/types.ts:10, 17；src/frontend/src/features/profiles/BrowserSessionPage.tsx；src/backend/cbrowser/stream_agent/policy.py:215-221
- 优先级：LOW
- 详细判断理由：已核对：`__sentDataChannelMessages`、`__pcs`、`__restartOffers` 无界 push；`record_input` 每条输入 create_task，鼠标移动可造成任务风暴；`idle`/`connecting_ice` 阶段从未被设置；`stopping/error` 在页面上未特判。长会话内存与锁竞争会缓慢增长，类型与 UI 状态不一致增加维护成本。
- 修复说明：
    1. 诊断数组改环形缓冲（固定容量），`__pcs` 只保留当前活动 PC，`__restartOffers` 封顶。
    2. 输入路径合并为“待 reconcile 标志”，由周期 reconciler 消费，避免每条消息创建任务。
    3. 删除从未使用的阶段类型；为 `stopping/error` 提供明确 UI 状态与可用操作。
    4. 补长会话/高频输入的单元测试。

### A11. 依赖声明完整性

- 来源：review_opencode_opencode_go_muse_spark_1_3_contributor（K1）
- 位置：pyproject.toml:6-17
- 优先级：MEDIUM
- 详细判断理由：已核对：dependencies 无 argon2-cffi、无 aiohttp；auth/service.py 导入 argon2，gateway 依赖 aiohttp；干净环境 `pip install -e .` 后登录 ImportError、Gateway 无法启动。测试门禁靠 `--with` 掩盖了声明缺失。
- 修复说明：增加 `"argon2-cffi>=23.1.0"` 与 `"aiohttp>=3.9.0"`（与 gateway_runtime/Dockerfile 对齐）；在干净虚拟环境执行 `pip install -e .` 并跑认证/Gateway 基础测试；依赖锁定由 A30 统一处理。

### A12. PATCH 输入语义：name null 拒绝、tags 三态明确

- 来源：review_opencode_opencode_go_deepseek_v4_1_flash（COR-6、COR-7、TEST-6）；review_opencode_opencode_go_muse_spark_1_3_contributor（R28）
- 位置：src/backend/cbrowser/domain/models.py:207-240；src/backend/cbrowser/api/v1/router.py:298-317；src/backend/cbrowser/adapters/database/repository.py:298-300；docs/specs/runtime_persistence.md:30-32
- 优先级：MEDIUM
- 详细判断理由：已核对：`name: null` 通过 validator 后在 repository 合并 `ProfileConfig` 时抛 Pydantic 错误，路由未捕获 → 500；spec 要求非空字段 null 返回 422 且数据不变。`tags: null` 与“未提供”不可区分，导致无法清空；tags 的 null 语义 spec 未定义，需显式定契约。
- 修复说明：
    1. `ProfileUpdateRequest.name` 增加 `mode="before"` validator 拒绝显式 None（未提供不触发），返回 422。
    2. tags 采用三态语义：字段缺席 = 不修改；`null` = 清空；`[]` = 清空。router 用 `model_fields_set` 区分缺席与显式 null，repository 接收明确意图。
    3. 在 runtime_persistence spec 写明 tags 三态；补 null/空数组/缺席三种 HTTP 用例，断言数据与快照版本行为一致（TEST-6）。

### A13. 恢复使用故障实例绑定的配置版本

- 来源：review_opencode_opencode_go_deepseek_v4_1_flash（COR-3、TEST-4）
- 位置：src/backend/cbrowser/supervisor/recovery_coordinator.py:544-567
- 优先级：MEDIUM
- 详细判断理由：已核对：恢复优先取 `profile_info["current_config_version"]`，仅缺失才回退实例绑定版本。spec 要求显式“应用并重启”后才使用新尺寸；否则运行中改了尺寸未应用、Chrome 崩溃后会用未确认几何启动，页面显示“待应用”但实际已生效，状态与行为矛盾。
- 修复说明：优先使用 `current_rt["config_version"]`（故障实例绑定版本），仅缺失时回退；补“运行中更新未应用 + 崩溃恢复”用例，断言恢复使用旧版本且页面仍显示待应用（TEST-4）。

### A14. restart_blocked 视为终态，停止无限重试

- 来源：review_opencode_opencode_go_deepseek_v4_1_flash（COR-8）
- 位置：src/backend/cbrowser/api/runtime_coordinator.py:328-331, 448-475
- 优先级：LOW
- 详细判断理由：已核对：blocked 时 `_reconcile_running` 返回 False，`_reconcile_profile_loop` 默认 `max_retries=None`，永久退避重试并重复发布 SSE 错误、覆盖 last_coordinator_error；不发起真实 start，属噪声与常驻任务。
- 修复说明：为协调结果引入显式“终止”语义（区别于可重试失败）；restart_blocked 时保留 last_error、停止该轮循环；手动重试（reset_blocked → desired-state）重新触发。补 blocked 不重试的单测。

### A15. 可观测性：SSE 静默异常、日志时间戳、退出原因枚举、恢复日志、快照 id

- 来源：review_opencode_cpa_gemini_3_8_flash（ROB-001、ROB-002）；review_opencode_opencode_go_deepseek_v4_1_flash（ROB-1、COR-12）；review_opencode_opencode_go_muse_spark_1_3_contributor（C5 快照 id）
- 位置：src/backend/cbrowser/api/v1/router.py:118-120；src/backend/cbrowser/stream_agent/agent.py:49-56, 264-281；src/backend/diagnostics.py:247-264；src/backend/cbrowser/supervisor/recovery_coordinator.py:126-134, 489-502；src/backend/cbrowser/api/runtime_coordinator.py:105-111
- 优先级：LOW
- 详细判断理由：已核对：SSE 初始快照 `except Exception: pass`；Service Formatter 已加 ISO8601，日志又手动 `[%s] _iso_now()`，时间戳重复；`_SAFE_EXIT_REASONS` 与实际 reason 不匹配，全部降级为 custom_reason；恢复日志 “Retaining healthy browser” 与实际整对重启不符；SSE 快照事件共用同一 snap id，影响 Last-Event-ID 精度。
- 修复说明：
    1. 快照查询失败记 warning（profile_id + 异常类型，不记载荷）。
    2. 移除日志消息中的手动时间戳，保留结构化 payload 的 `timestamp` 字段。
    3. 退出原因改为共享枚举/常量，白名单覆盖全部实际值，未知值才脱敏；补测试。
    4. 修正恢复日志与注释，明确“本轮保留 Browser，自动重试将整对重建”。
    5. SSE 快照事件使用逐事件唯一 id（沿用 epoch:seq），保证断点续传语义。

### A16. Gateway 连接健壮性与身份校验

- 来源：review_opencode_opencode_go_deepseek_v4_1_flash（ROB-2、SEC-4）；review_opencode_opencode_go_muse_spark_1_3_contributor（R1、R2、C5 心跳身份）
- 位置：src/backend/cbrowser/gateway/server.py:140-154, 279-305, 449, 514-544；src/backend/cbrowser/stream_agent/agent.py:768-770
- 优先级：LOW
- 详细判断理由：已核对：viewer 条目写入后两次 send 在 try 之外，失败会遗留幽灵连接；Agent 注册首包无超时与限速；tick 内单 Profile 发送失败会中断当轮其他 Profile；HELLO 解析静默吞错；心跳未校验 agent_session_id。均为局部健壮性缺口，但会造成资源泄漏与诊断盲区。
- 修复说明：
    1. viewer 初始化放入 try/finally，失败移除条目、关闭 ws、通知 Agent close。
    2. Agent 注册首包 `asyncio.wait_for(timeout=10)`；增加每来源并发/速率限制；超时或非法关闭 1008。
    3. tick 内每个 Profile 的 `_send_agent_control` 单独 try/except，失败只影响该 Profile。
    4. HELLO 解析失败记 warning（不记载荷）。
    5. 心跳校验注册时的 agent_session_id，旧会话心跳不得延长存活。
    6. 补对应单元/集成测试。

### A17. 契约导出与公开面：内部路由不进入公共 OpenAPI、Agent 协议可导出

- 来源：review_opencode_opencode_go_deepseek_v4_1_flash（CT-2、ARCH-5）
- 位置：src/backend/cbrowser/api/app.py:297-300；scripts/export_openapi.py；schemas/runtime/agent_protocol.json；src/frontend/src/shared/api/generated/cbrowser_v1.d.ts
- 优先级：LOW
- 详细判断理由：已核对：internal supervisor/gateway router 直接 include 到同一 app，公开 schema 与前端生成类型包含内部 RPC 路由/DTO；agent_protocol.json 无导出脚本，只靠样例校验，存在漂移风险。契约面应与权限边界一致。
- 修复说明：
    1. 内部 router 增加 `include_in_schema=False`（或按 tag 过滤导出），重新生成 OpenAPI 与前端类型；补断言内部路径不在公开 schema。
    2. 新增 `scripts/export_runtime_agent_protocol.py`，与 stream/supervisor 协议一致的逐字节一致性测试。
    3. 在 blueprint 记录“公共 API 面”边界。

### A18. 所有同步 Docker SDK 调用移出事件循环

- 来源：review_opencode_cpa_gemini_3_8_flash（PERF-001）；review_opencode_opencode_go_deepseek_v4_1_flash（PERF-2）
- 位置：src/backend/cbrowser/supervisor/docker_adapter.py:714-742, 950-1038；src/backend/cbrowser/supervisor/core.py:238；src/backend/cbrowser/supervisor/resource_monitor.py
- 优先级：MEDIUM
- 详细判断理由：已核对：`teardown_profile` 声明 async 但内部 cleanup 直接执行同步 Docker SDK；`inspect_container`、`containers.run`、资源 stats 等也在事件循环内。Docker daemon 抖动时 Supervisor 健康探针、SSE、Agent 消息全部停顿，启动慢还会撞 30s readiness 上限。
- 修复说明：把 teardown 同步清理整体包为 `asyncio.to_thread`；scan 的 inspect、启动/停止的 Docker 调用、资源采样统一 `to_thread`；禁止在事件循环内调用 Docker SDK。补“Docker 调用延迟不阻塞心跳/扫描”的测试。

### A19. 扫描改为事件驱动 + 低频兜底 + 指标

- 来源：review_opencode_opencode_go_deepseek_v4_1_flash（D9、PERF-1）
- 位置：src/backend/cbrowser/supervisor/runner.py:168-197；src/backend/cbrowser/supervisor/core.py:126-369；src/backend/cbrowser/supervisor/recovery_coordinator.py:63-245
- 优先级：MEDIUM
- 详细判断理由：已核对：后台循环固定 1s 执行事件消费、spool 重放、全量容器扫描、恢复 tick；scan 每个 Profile 还有 API GET、inspect、Gateway 调用。多 Profile 下线性放大，且扫描语义与事件驱动重复。当前无容量数据，但设计上应避免轮询一切。
- 修复说明：
    1. 订阅 Docker events 作为容器状态变化的主触发；扫描仅在事件到达、启动/停止操作、以及 30s 低频兜底时执行。
    2. 事件文件消费改游标（A9）；resource 采样独立低频循环并错峰。
    3. 增加每阶段耗时/次数指标（结构化日志或 Prometheus 兼容计数），为 t009 容量验收提供数据。
    4. 保持行为等价：任何容器状态变化最终都能被收敛。

### A20. 协调重试使用稳定 operation_id

- 来源：review_opencode_cpa_gemini_3_8_flash（COR-001）
- 位置：src/backend/cbrowser/api/runtime_coordinator.py:352, 420
- 优先级：LOW
- 详细判断理由：已核对：每次请求体用 `uuid.uuid4().hex[:8]` 生成 operation_id；退避重试被 Supervisor 视为新请求，OperationJournal 的幂等重放失效，只能靠 profile 锁兜底，破坏长周期幂等设计。
- 修复说明：在协调轮次入口生成一次稳定 operation_id（新轮次再生成），重试复用；补重试复用同一 id 的单元测试。

### A21. PathValidator 对 profile_id 增加保留名与点号校验

- 来源：review_opencode_cpa_gemini_3_8_flash（SEC-001）
- 位置：src/backend/cbrowser/supervisor/path_validator.py:100-137
- 优先级：LOW
- 详细判断理由：已核对：只排除空串、斜杠、`..`；secret 目录位于 `runtime/.secrets/<id>`，若 profile_id 为 `.secrets`，runtime 目录会与 secret 根重叠并以 rw 挂入 Browser。当前 profile_id 由服务端 uuid4 生成，无法经 API 构造，属纵深防御缺口。
- 修复说明：抽取统一 `_validate_profile_id`：拒绝空串、分隔符、`..`、点号开头与保留名（`.secrets` 等），所有目录 getter 复用；补 `.secrets` 被拒测试。保持现有字符集以免破坏 UUID。

### A22. 未受策略保护的沙箱 fail-closed 收敛

- 来源：review_opencode_opencode_go_deepseek_v4_1_flash（ROB-5）
- 位置：src/backend/cbrowser/supervisor/core.py:222-226
- 优先级：LOW
- 详细判断理由：已核对：policy_ready 为 false 时只 `continue` 并每秒 warning，容器保持运行但不纳入 session/资源/端口管理；若 gate 未开放，容器可能处于半启动状态，暴露未受策略保护的沙箱。安全边界应 fail-closed，而不是无限重试告警。
- 修复说明：对连续 N 次（或超过 60s）仍无有效 gate/ready 标记的受管容器执行受控 teardown，并一次性 error 告警；新启动中的容器设宽限期避免误杀；补策略失败收敛测试（与既有 test_supervisor_policy_failure 对齐）。

### A23. 心跳存活判定改用 monotonic 时钟

- 来源：review_opencode_opencode_go_deepseek_v4_1_flash（ROB-4）
- 位置：src/backend/cbrowser/gateway/registry.py:60-70
- 优先级：INFO
- 详细判断理由：已核对：注册表存活判定使用 wall clock，系统时钟回拨会延迟驱逐、前跳会提前驱逐。进程内 liveness 语义应使用单调时钟；TURN 过期仍用 wall clock。
- 修复说明：heartbeat 时间戳与超时计算改 `time.monotonic()`；保持对外 JSON 时间字段不变；补时钟跳变的单元测试（可注入时钟）。

### A24. 清理死代码与测试重复实现

- 来源：review_opencode_opencode_go_deepseek_v4_1_flash（ARCH-1）
- 位置：src/backend/cbrowser/stream_agent/agent.py:90-110；src/backend/cbrowser/rtc_config/credential.py:28-37；src/backend/cbrowser/stream_agent/client_shim.py
- 优先级：LOW
- 详细判断理由：已核对：`_sanitize_packet` 仅自递归、无调用方；`verify_turn_credentials` 仅测试使用；`client_shim.py` 与生产 `adapter.ts` 的 Web Locks 逻辑重复，存在行为漂移风险。死代码与双实现会增加审计面。
- 修复说明：删除无调用方的 `_sanitize_packet`；`verify_turn_credentials` 若确认仅测试使用则移入测试工具或删除；`client_shim` 若未被生产引用则删除，改由 Playwright 对真实 adapter 产物做身份语义测试，或从同一源生成 shim 并加一致性断言。

### A25. 结构性拆分：恢复 tick、Docker 适配、Stream Agent

- 来源：review_opencode_opencode_go_deepseek_v4_1_flash（ARCH-3）；review_opencode_cpa_gemini_3_8_flash（ARCH-001）
- 位置：src/backend/cbrowser/supervisor/recovery_coordinator.py:63-370；src/backend/cbrowser/supervisor/docker_adapter.py（1098 行）；src/backend/cbrowser/stream_agent/agent.py（1153 行）；src/backend/cbrowser/stream_agent/policy.py（773 行）；src/backend/cbrowser/api/v1/router.py（696 行）
- 优先级：LOW
- 详细判断理由：`RecoveryCoordinator.tick` 约 310 行、圈复杂度约 68，串联可用性探测、容器扫描、异常识别、实例判定与 2/10/30s 调度；`docker_adapter` 混合容器、网络、卷、标签、权限；`stream_agent/agent.py` 混合 WS 协议、上游转发、token、ICE。功能正确，但职责混杂使修改与审计成本持续上升。
- 修复说明：
    1. `RecoveryCoordinator.tick` 拆为 observe/classify/schedule 三个阶段函数，状态转移表驱动，保持行为等价。
    2. `docker_adapter` 拆为 container_runtime / network_runtime / volume_spec / labels 等模块，保留原公共入口。
    3. `stream_agent/agent.py` 拆为 connection / upstream_relay / token / lifecycle 子模块。
    4. 纯重构，不混入功能改动；依赖现有 unit/E2E 作为行为基线，必要时补特征测试。按独立 task 实施并 review。
    5. 闭环 p001；p005 的复杂度部分一并归档。

### A26. spec 契约同步

- 来源：review_opencode_opencode_go_deepseek_v4_1_flash（CT-1、CT-5、CT-6、CT-7、CT-8、DOC-1、DOC-4、DOC-5、DOC-6）；review_opencode_opencode_go_muse_spark_1_3_contributor（K2 spec 部分）
- 位置：docs/specs/browser_isolation.md:12-20；docs/specs/runtime_persistence.md:59, 123-128；docs/specs/v2_runtime_validation.md:34；docs/blueprint/domain.md；docs/specs/storage_and_artifacts.md:2.1；docs/specs_index.md
- 优先级：MEDIUM
- 详细判断理由：已核对：spec 容器名/标签仍为 `browser-runtime-{id}`、`com.cbrowser.managed=true`、`runtime-image`，实现为 `{prefix}-browser-{id}`、`managed-by=supervisor`、`prefix/role/instance-id/network-policy`；failure_count 写 3 而 ADR 008/实现为 4；resume_key 仍写刷新保留；domain/storage spec 仍有 ControlSession/ControlLease 旧表；runtime_persistence 验收复选框未勾；specs_index 更新时间滞后。规范是验收与实现的唯一契约，漂移即债。
- 修复说明：
    1. browser_isolation：按实现更新容器名、标签、prefix 语义，注明 Stream UDP mux 当前仅绑定宿主回环。
    2. runtime_persistence：failure_count 阈值改 4 并引用 ADR 008；补 tags 三态与 A12 语义；按 D1 决策更新运行事件保留表述；移除/标注历史验收复选框，指向 task/review 证据。
    3. v2_runtime_validation：区分刷新生成新 resume_key 与连接内重连保留。
    4. domain.md 与 storage_and_artifacts：删除 ControlSession/ControlLease/StreamTicket 与租约时长，指向 ADR 007 与无租约模型。
    5. specs_index 同步最后更新记录。

### A27. blueprint 说明同步：时间锚点、端口绑定、no-sandbox 取舍、测试计数

- 来源：review_opencode_opencode_go_muse_spark_1_3_contributor（D1、K2 部署部分）；review_opencode_opencode_go_deepseek_v4_1_flash（SEC-6、DOC-7）
- 位置：docs/blueprint/architecture.md:9 及端口矩阵；docs/blueprint/decisions.md；docs/blueprint/testing.md
- 优先级：LOW
- 详细判断理由：已核对：architecture.md “旧单容器实现保持完全不变”无时间锚点；Stream UDP mux 实际仅绑定 `127.0.0.1`（docker_adapter.py:896），矩阵未注明；decisions.md 未记录 Chrome `--no-sandbox` 与容器边界补偿；testing.md 的测试计数已与门禁实际输出不符。蓝图是长期真相，模糊表述会误导后续架构决策。
- 修复说明：
    1. architecture.md 该句补“（t001 时点陈述，后续 t005–t007 已新增 v2 链路）”；端口矩阵注明 Stream UDP 当前仅宿主回环，t012 公网部署需调整。
    2. decisions.md 增加 ADR：`--no-sandbox` 由容器边界（非 root、只读根、cap-drop ALL、no-new-privileges）承担隔离，记录残余风险与禁止在容器外使用。
    3. testing.md 去掉易漂移的硬编码计数，改为门禁命令与“以实际输出为准”，或标注测量时点。

### A28. 测试确定性与覆盖：去固定 sleep、驱动画面变化、补 SSE 失效回归

- 来源：review_opencode_cpa_gemini_3_8_flash（TST-001、TST-002）
- 位置：tests/e2e/test_stream_runtime_e2e.py:120-130；tests/e2e/test_frontend_app_e2e.py:180-210；src/frontend/src/features/profiles/useProfilesQuery.ts:183-221；src/frontend/src/features/browser-session/audio_status.test.ts:35-45
- 优先级：LOW
- 详细判断理由：已核对：multi-viewer 用例硬等待 `sleep(2.0)`；帧率断言依赖静止页面出帧；`useProfileEventsSync` 的 `profileKeys.runtime(id)` 失效重取无回归测试；`audio_status` 测试辅助函数未透传 totalAudioEnergy（判定逻辑不读该字段，结论不受影响）。测试不确定性会掩盖真实回归。
- 修复说明：
    1. 固定 sleep 改带超时的条件轮询（viewer 注册、状态达成的显式条件）。
    2. 帧率断言前通过输入或在测试页制造画面变化，不依赖 damage 编码的静止帧。
    3. 补 `useProfileEventsSync` 触发 runtime 查询失效的 Vitest 用例。
    4. 修复 audio_status 辅助函数字段透传。
    5. 闭环 p009、p011、p013。

### A29. 前端 i18n 补全

- 来源：review_opencode_cpa_gemini_3_8_flash（ARCH-002）
- 位置：src/frontend/src/features/settings/SettingsPage.tsx:25, 77-78, 84, 89, 94；ProfileNewPage.tsx:54, 84, 98, 110, 124；ProfileDetailPage.tsx:80, 92；useBrowserSession.ts:343
- 优先级：LOW
- 详细判断理由：已核对：多处 placeholder/按钮/诊断文案硬编码英文，未通过 `useI18n` 的 `t()` 渲染；中英切换不一致，属 UI 完整性债。
- 修复说明：补齐中英字典键值，替换全部硬编码文案；补断言语言切换后关键文案变化的测试；闭环 p007。

### A30. 构建可复现：基镜像 digest 与依赖锁定

- 来源：review_opencode_opencode_go_deepseek_v4_1_flash（ARCH-4）
- 位置：config/docker/supervisor_runtime/Dockerfile:19-20；全部 runtime Dockerfile；pyproject.toml
- 优先级：INFO
- 详细判断理由：已核对：基镜像使用可漂移 tag（`python:3.12-slim-bookworm`），Gateway/Supervisor 使用 `>=` 依赖且无 lock；supervisor 镜像未复制 `cbrowser/__init__.py`，依赖 namespace package。同一源码在不同时间构建可能得到不同运行时，属供应链债。
- 修复说明：
    1. 基镜像按 digest 固定；依赖使用 lock（uv lock / pip-compile）并在 CI 校验。
    2. 明确复制 `cbrowser/__init__.py` 或改为显式包安装，消除 namespace 隐式依赖。
    3. 增加可复现构建检查（两次构建依赖清单一致）。
    4. 与 t012 的最终 Compose/镜像发布对齐，但不等待 t012 才修。

### A31. 独立启动模式移除 token 环境变量回退

- 来源：review_opencode_opencode_go_muse_spark_1_3_contributor（S7）
- 位置：config/docker/stream_runtime/entrypoint.sh:95-99
- 优先级：INFO
- 详细判断理由：已核对：无挂载凭证的独立/测试启动路径把 controller token 导出到环境变量；环境变量可经 `docker inspect` 读取，违背“凭证只走文件”的边界。受管路径不走此分支，但保留回退会诱导不安全用法。
- 修复说明：删除环境变量回退，独立启动也必须提供凭证文件（0600）；测试夹具生成临时文件；在 stream_runtime 文档写明唯一凭证来源。

## 不采纳项

### R1. Browser 容器可伪造 native exit 事件

- 来源：review_opencode_opencode_go_deepseek_v4_1_flash（SEC-2）
- 位置：src/backend/cbrowser/supervisor/docker_adapter.py:676-679；src/backend/cbrowser/supervisor/core.py:298-369；src/backend/cbrowser/adapters/database/repository.py:648-697
- 优先级：MEDIUM
- 详细判断理由：事实成立，但容器内进程本就属于该 Profile 的信任域；跨 Profile 伪造已被目录名 + profile_id + runtime_instance_id 校验阻断，影响限本 Profile（攻击者已控制该 Profile 的浏览器）。在没有独立信任域（独立 VM/独立写入进程）的前提下，事件签名密钥同样暴露在容器内，签名不能提供额外保证。本决策改为：A1 让事件不再驱动生命周期状态（Docker/Agent 观测权威化）+ 严格 schema + quarantine + 在 security blueprint 记录信任边界；单独的签名方案不采纳，避免引入无实际收益的复杂度。

### R2. 自动化凭证只有存储/授权，无自动化接入面

- 来源：review_opencode_opencode_go_deepseek_v4_1_flash（CT-4）
- 位置：src/backend/cbrowser/api/internal_gateway.py:114-127；docs/specs/access_control.md:16-19
- 优先级：INFO
- 详细判断理由：自动化客户端 API 属 t008 交付范围，当前未实施不计缺陷；提前实现会与 t008 的 Artifact/CDP 自动化契约耦合。保留阶段边界。

### R3. 内部 RPC 复用公共 handler 产生协调回环

- 来源：review_opencode_opencode_go_deepseek_v4_1_flash（ARCH-2）
- 位置：src/backend/cbrowser/api/internal_supervisor.py:63-101；src/backend/cbrowser/api/v1/router.py:479-497
- 优先级：LOW
- 详细判断理由：Supervisor reset_blocked 通过 API desired-state 触发协调，是“意愿变更 → 协调启动”的设计本意，不是隐式副作用；回环由期望态与幂等收敛，正是事件驱动架构的入口。拆成不触发协调的内部 handler 反而会制造第二条启动路径，增加债。

### R4. Cookie `secure=True` 硬编码

- 来源：review_opencode_opencode_go_muse_spark_1_3_contributor（S4）
- 位置：src/backend/cbrowser/api/v1/auth_router.py:80-95
- 优先级：LOW
- 详细判断理由：认证契约与部署拓扑（Caddy TLS）本就要求 Secure；允许本地 http 会削弱会话安全。直连 http 不可用是预期行为，不做开关。

### R5. Agent→Viewer 隧道原样转发控制帧

- 来源：review_opencode_opencode_go_muse_spark_1_3_contributor（S5）
- 位置：src/backend/cbrowser/gateway/server.py:421-422；adapter.ts:345-423
- 优先级：LOW
- 详细判断理由：Stream 容器本就持有该 Profile 的媒体面与信令，属同一信任域；服务端已校验 conn_id 归属。在页面侧重写官方客户端的控制帧解析会增加与官方协议的耦合债，收益不足。保留信任假设并在 security blueprint 记录。

### R6. 前端 runtime 查询失败 fail-open

- 来源：review_opencode_opencode_go_muse_spark_1_3_contributor（C3）
- 位置：src/frontend/src/features/browser-session/useBrowserSession.ts:149-153
- 优先级：LOW
- 详细判断理由：fail-open 让信令仍可尝试建立，能容忍 runtime 查询的瞬时失败；若信令也失败，后续阶段会给出真实错误。改为 fail-closed 会降低可用性；引入第三个“未知”阶段属过度设计。

### R7. coordinator 在 API 尚未监听时先启动收敛

- 来源：review_opencode_opencode_go_deepseek_v4_1_flash（ROB-6）
- 位置：src/backend/cbrowser/api/runtime_coordinator.py:194-227；src/backend/cbrowser/api/app.py:105-119
- 优先级：LOW
- 详细判断理由：首轮失败会退避重试并最终收敛，是自愈设计的正常路径；FastAPI lifespan 内没有可靠的“监听后”钩子，强行改顺序会引入时序特例。仅启动期日志噪声，不构成架构债。

### R8. 每次启动全量缓存路径校验

- 来源：review_opencode_opencode_go_deepseek_v4_1_flash（PERF-5）
- 位置：src/backend/cbrowser/supervisor/docker_adapter.py:199-203
- 优先级：LOW
- 详细判断理由：该校验是只读缓存的防篡改措施，成本有界（缓存文件规模可控）；缓存或跳过校验会削弱安全保证。保留现状并在 A19 的指标中观察实际耗时。
