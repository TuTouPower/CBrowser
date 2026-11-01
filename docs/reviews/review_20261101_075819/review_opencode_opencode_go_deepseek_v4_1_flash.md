# CBrowser t001–t007 累计改动独立审阅（opencode 路，最终稿）

- 模型：`opencode-go/deepseek-v4.1-flash`
- Provider：opencode-go
- 思考强度：`effort=high`
- Base：`3c8bdbc55570e85aaeb6365a3d512da9c0ce180c`（t001 diff_anchor）
- Target：`78c95638c8ceb5d84c286994eee82146d7ddddd6`（t007 合入 main）
- 累计差异：`_meta/cumulative.patch`（97,988 行 diff），`changed_files.txt` 507 条（另含 1 条 `docs/specs/chrome_external_tabs.md` → `docs/archive/specs/chrome_external_tabs.md` 重命名）
- 方式：仅静态阅读源码、配置、测试、受控文档；未运行构建/测试/浏览器/Docker/网络；未读取 `.env`、`data/secrets`、认证配置或运行期凭据；未修改源码、task/pending/findings，未 commit/push。文中“已有测试覆盖”只表示仓库内存在该测试或证据，**不代表本路执行通过**。
- 覆盖：`src/backend` 74 个变更文件中 73 个逐文件阅读（`migrations/script.py.mako` 为模板，只核对结构）；`config/docker` 8 个全部阅读；`scripts` 4 个全部阅读；`schemas` 4 个中 OpenAPI 与两个导出 schema 核对关键路径/模型，未逐字段 diff；`src/frontend` 45 个中 30+ 生产文件逐行、9 个测试读断言/头部、生成类型与 lockfile 核验来源；151 个测试全部读取用例名与关键断言，约 15 个文件逐行；219 个文档中 specs/blueprint/findings/guides/pending/t001-t007 task/note/handoff/specs_index/scope review 已读，archive spikes 的 report/review 抽样并逐条登记为历史溯源，归档源码未逐行。剩余缺口在 Appendix 逐路径标注。
- 阶段边界：t008/t013/t014/t009/t010/t011/t012 未实施（Artifact/CDP、复制重置、完整剪贴板、容量/P95/8h/1000 次、真实迁移、旧链路删除、最终 Compose），只按“阶段外”记录，不因未实现判 bug；公网与原生 x86 仍 `NOT_RUN / USER_WAIVED`，未称通过。

______________________________________________________________________

## 1. 安全

### SEC-1 [High] Stream 容器允许任意公网出站，违反生效规范与蓝图

- 位置：`src/backend/cbrowser/supervisor/network_policy.py:143-148`、`:191-196`
- 契约：`docs/blueprint/supervisor.md:49`“Stream 仅额外允许实际 Gateway、coturn 地址/端口及本实例 UDP mux”；`docs/specs/runtime_lifecycle.md:10` 同义。
- 证据：IPv4/IPv6 规则在 DROP 私有/保留段后无条件追加 `-A OUTPUT -j ACCEPT`，对 `role == "stream"` 同样生效；`tests/unit/test_network_policy.py:80-90` 对 stream 只断言 allowed UDP/私有 DROP，未断言最终 ACCEPT 不存在；`test_supervisor_namespace_policy_e2e.py` 只以 browser 角色验证公网正例。
- 触发条件：Stream 容器内任意进程被攻破（Selkies/GStreamer/媒体数据通道缺陷），或流容器配置错误。
- 影响：持有用户屏幕与音频的 Stream 容器可向任意公网地址外传，突破“仅 Gateway/coturn”边界；当前未找到现成远程利用链，但这是容器边界的直接失效。
- 修复建议：stream 角色禁止最终 ACCEPT；只放行 Gateway/coturn/必要 ICE 端点；若确需 Stream 直连公网 Viewer，必须先修订 spec/blueprint 并改为 ICE 候选白名单；补 stream 规则与真实内核负例。
- 置信度：92

### SEC-2 [Medium] Browser 容器可伪造 native 退出事件影响控制面

- 位置：`src/backend/cbrowser/supervisor/docker_adapter.py:676-679`（runtime-events 以 rw 挂入 Browser）；`src/backend/cbrowser/supervisor/core.py:298-369`；`src/backend/cbrowser/adapters/database/repository.py:648-697`
- 证据：`consume_disk_events` 只校验目录名与文件内 `profile_id`、`runtime_instance_id` 一致（`core.py:313-337`），未校验 `event_type` 枚举、`exit_code` 类型或真实性；Browser 容器（含网页进程）对该目录 rw。API 对 `exit_code=0` 直接置 `desired_state=stopped`、清实例；非零累计失败并阻断。
- 触发条件：渲染进程逃逸（`runner.py:381-393` 固定 `--no-sandbox`）或容器内任意代码执行，写入一条合法身份的 `exit` 事件。
- 影响：可强制停止本 Profile 运行意愿、消耗重启预算、制造 `restart_blocked`；畸形 `event_type` 还会毒化 spool（ROB-3）。影响限本 Profile（跨 Profile 目录身份被拒，`tests/unit/test_supervisor_event_delivery.py:...` 有覆盖），但已从内容沙箱越界到主机控制状态。
- 修复建议：事件目录仅由独立进程可写，或 Agent 用实例凭证签名、Supervisor 验签后转发；至少严格校验 schema/枚举/类型/长度并隔离坏事件。
- 置信度：82

### SEC-3 [Medium] 登录限速按代理 IP 统计，可能全局锁定

- 位置：`src/backend/cbrowser/api/v1/auth_router.py:65`；`src/backend/cbrowser/auth/service.py:101-133`；`src/backend/cbrowser/auth/rate_limiter.py:27-38`
- 证据：`client_ip = request.client.host`，未消费可信代理的 `X-Forwarded-For`；Caddy 后所有请求同源 IP；5 次/60 秒即 429。
- 触发条件：任何能访问登录端点者持续错误登录。
- 影响：管理员在窗口内无法登录（可用性），审计来源失真；单机单用户降低实际危害。
- 修复建议：只在受信代理后解析转发头；按会话/令牌与来源组合限速；持久化并观测。
- 置信度：75

### SEC-4 [Low] Agent 注册首包无超时/限速

- 位置：`src/backend/cbrowser/gateway/server.py:279-305`（`ws.prepare` 后 `await ws.receive()`；HMAC 校验在完整 payload 之后）
- 触发条件：能访问 Gateway 端口的客户端大量打开 WS 不发首包。
- 影响：连接/内存长期占用，挤占真实 Agent；单机部署风险有限。
- 修复建议：首包超时、并发与来源限速；先校验 Bearer。
- 置信度：85

### SEC-5 [Info/已登记 p006] Browser 容器可读 Stream Agent 凭证

- 位置：`src/backend/cbrowser/supervisor/core.py:492-497`（`agent_secret.txt` 0644 位于挂入 Browser 的 runtime 目录）
- 说明：p006 已登记；本次确认仍在。Browser 同 uid 亦可在 Stream 启动前覆盖 `agent_secret.txt`/Xauthority，造成注册/显示失败（DoS），但不产生跨容器权限。按 p006 迁移到 `.secrets/<profile>` 0600。
- 置信度：98

### SEC-6 [Info] Chrome 固定 `--no-sandbox` 的取舍未在决策文档显式记录

- 位置：`src/backend/cbrowser/runtime_agent/runner.py:381-393`
- 说明：容器已有 cap-drop ALL/只读根/非 root，边界在容器层；但 `decisions.md` 未记录该安全取舍与补偿。一旦渲染进程逃逸，SEC-2 与 p006 风险同时成立。
- 置信度：90

______________________________________________________________________

## 2. 正确性

### COR-1 [Medium] Gateway 默认 18080 与 Supervisor 硬编码 18097 不一致

- 位置：`src/backend/cbrowser/gateway/config.py:28,86`（18080）；`src/backend/cbrowser/supervisor/docker_adapter.py:494`（`gateway_port=18097`，调用点未覆盖）；`core.py:80`、`runner.py:51,253`（18097）
- 契约：`docs/blueprint/gateway.md` 配置清单默认 `CBROWSER_GATEWAY_PORT=18080`；测试则普遍硬编码 18097（如 `test_supervisor_container_graph_e2e.py:147`、`test_gateway_ac007_visibility_e2e.py:36`），说明测试环境靠额外配置而非默认值对齐。
- 触发条件：按文档默认部署 Gateway 且未覆盖为 18097。
- 影响：`attach_profile_infrastructure` 返回 `ws://<gw_ip>:18097`，Stream Agent 注册失败，Profile 无法 running；t012 按文档编排会踩中。
- 修复建议：端口单源配置（Supervisor 从环境/参数读取），Gateway 与 Supervisor 共用同一变量；补默认值集成测试。
- 置信度：95

### COR-2 [Medium] Gateway 不可用时无法正常停止 Stream 已运行的 Profile

- 位置：`src/backend/cbrowser/supervisor/core.py:666-699`；`src/backend/cbrowser/api/runtime_coordinator.py:380-446`
- 证据：`disconnect_viewers` 对 Gateway 503/TransportError 只在 Stream 容器未运行时放行；Stream 仍 running 则重抛，`stop_profile` 不进入 teardown；API `_reconcile_stopped` 永久退避重试，无 force-stop。
- 触发条件：Gateway 停止/网络故障/Agent 未注册，Stream 仍 running。
- 影响：用户停止无法收敛，容器与端口长期保留，只能手工 Docker；与“Supervisor 唯一协调者”冲突。
- 修复建议：Gateway 不可达时按“无存活信令”降级 teardown，或提供显式 force-stop；保留实例 fence。
- 置信度：85

### COR-3 [Medium] 自动恢复使用 Profile 最新配置版本，绕过“应用并重启”

- 位置：`src/backend/cbrowser/supervisor/recovery_coordinator.py:544-567`
- 证据：优先 `profile_info["current_config_version"]`，仅缺失才回退绑定 `current_rt["config_version"]`；`docs/specs/webrtc_remote_display.md:9`、`docs/specs/profile_management.md:26` 要求明确 apply 后才使用新尺寸。
- 触发条件：运行中修改尺寸保存后 Chrome 异常退出。
- 影响：恢复用未确认的新几何启动，页面仍显示“待应用”，状态与行为矛盾。
- 修复建议：恢复只用故障实例绑定的 config_version；只有 apply/restart 事务绑定新版本。
- 置信度：85

### COR-4 [Medium] 1 秒扫描重复接管会话并覆盖内存观测态

- 位置：`src/backend/cbrowser/supervisor/core.py:126-280`；`src/backend/cbrowser/supervisor/runner.py:168-184`
- 证据：running 分支未短路已存在 `_sessions`，每 tick 重新 `has_foreground_viewers`、`inspect_container`、`ports.restore`，并整体替换 `ActiveSession(..., observed_state="running")`。
- 触发条件：正常运行 Profile，每约 1 秒。
- 影响：`consume_disk_events` 刚写入的 stopped 可被下一 tick 覆盖；持续的 Docker/Gateway 调用；会话对象引用被替换，部分读取方成陈旧视图。
- 修复建议：已存在同实例会话时仅校正必要字段后 `continue`；补重复扫描测试。
- 置信度：90

### COR-5 [Low] 轮换停滞时新连接可拿到过期 TURN 凭证

- 位置：`src/backend/cbrowser/gateway/rotation.py:75-84`、`:163-168`；`src/backend/cbrowser/rtc_config/service.py:95-105`；`src/backend/cbrowser/gateway/server.py:525-533`
- 证据：`get_effective_generation` 只检查 in-progress 是否过期，否则直接返回 current；不检查 current 是否已过期；`tick` 只记 ERROR。蓝图 `gateway.md`“绝不静默将过期凭证下发给新连接”；`_start_restart_round` 在无未迁移连接时直接提交 in-progress，即使已过期。
- 触发条件：Agent 长期离线/轮换连续失败超过 lifetime。
- 影响：新 Viewer 首帧携带过期凭证，ICE 失败无明确原因。
- 修复建议：current 过期时拒绝新连接或强制新代；提交前校验有效期。
- 置信度：85

### COR-6 [Medium] `PATCH /profiles/{id}` 显式 `name: null` 返回 500

- 位置：`src/backend/cbrowser/domain/models.py:207-240`（`validate_name` 对 None 放行）；`src/backend/cbrowser/api/v1/router.py:298-317`；`src/backend/cbrowser/adapters/database/repository.py:298-300`
- 契约：`docs/specs/runtime_persistence.md:30-32` 要求非空字段（含 name）null/空串/负数返回 422 且不改数据。
- 证据：`model_dump(exclude_unset=True)` 保留 `name=None`，合并进 `ProfileConfig(**current_dict)` 抛 Pydantic ValidationError，未被路由捕获，落入通用 500；`tests/integration/test_v2_api_subprocess.py:233-258` 只测了 `name="   "`，未测 `null`。
- 影响：客户端参数错误被报服务器错误；违反生效 spec。
- 修复建议：`ProfileUpdateRequest.name` 拒绝 None，或捕获合并 ValidationError 映射 422；补真实 HTTP 用例。
- 置信度：92

### COR-7 [Low] `tags: null` 无法清空标签

- 位置：`domain/models.py:233`；`api/v1/router.py:308-310`；`repository.py:338-352`
- 证据：`tags_update = patch_data.pop("tags", None)` 后 `tags_val=None`，repository 将 None 解释为“不修改”；显式 null 与未提供不可区分。`[]` 可清空。
- 影响：API 语义歧义；前端当前总发数组，未实际触发。
- 修复建议：区分“未提供”和“显式 null”，或文档禁止 null。
- 置信度：85

### COR-8 [Low] `restart_blocked` 被 API 协调器无限重试

- 位置：`src/backend/cbrowser/api/runtime_coordinator.py:328-331`、`:448-475`
- 证据：`_reconcile_running` 在 blocked 时 `return False`，默认 `max_retries=None` 的 loop 永久退避重试并重复发布 SSE 错误；`tests/unit/test_api_runtime_coordinator.py` 只测普通收敛与显式上限。
- 影响：永久阻断下常驻任务与 SSE 噪声，持续覆盖 `last_coordinator_error`；不发起真实 start。
- 修复建议：blocked 视为终态，停止该 profile task，用户 reset 后再触发。
- 置信度：90

### COR-9 [High] infrastructure lifecycle 失败未收敛为 error，Profile 可假 running

- 位置：`src/backend/cbrowser/runtime_agent/runner.py:593-635`（SDK driver/显示丢失 → `event_type="lifecycle"`, `exit_code=None`, `state=error`）；`src/backend/cbrowser/supervisor/core.py:321-363`；`src/backend/cbrowser/adapters/database/repository.py:648-663`；`src/backend/cbrowser/supervisor/recovery_coordinator.py:112-235`
- 证据：API `consume_runtime_event` 对 `heartbeat|lifecycle` 只落库并返回 applied，不修改 `observed_state`/`failure_count`/实例；Supervisor 只记录 lifecycle，不更新会话；`scan_and_reconcile_existing` 只看容器 status，Browser 容器因 uds_agent/supervisord 仍 running，于是重新接管为 running。`docs/findings/d016_sdk_owner_lifecycle_boundary.md` 明确要求 t005 将 lifecycle/error 收敛为 error 观测并保留 running 意愿，t003 note 也写明“t005 消费生命周期错误且不得清除 running 意愿”。
- 触发条件：SDK driver 被杀、Xvfb/显示基础设施丢失，Chrome 以 0 退出但日志为 lifecycle/process_observation_lost。
- 影响：API/前端仍显示 running，实际 Chrome 已死；RecoveryCoordinator 不把“容器 running 但浏览器失败”视为缺失实例，不会重试；用户只看到无帧且无法自动恢复，可能永久假 running，直到手动 stop/start。
- 修复建议：API 对 lifecycle/process_observation_lost 设置 observed_state=error（保留 desired running，failure_count 策略按 d016）；Supervisor 在接管时读取/使用 Agent 终态或 runner_info 之外的健康/退出事实；Recovery 将 lifecycle 错误纳入重启判定；补真实子进程用例。
- 置信度：88

### COR-10 [Medium] 删除 Profile 级联删除 runtime_events，违反保留契约

- 位置：`src/backend/cbrowser/adapters/database/models.py:205-225`（`RuntimeEventModel.profile_id` FK `ondelete="CASCADE"`）；`src/backend/cbrowser/adapters/database/repository.py:399-405`
- 契约：`docs/specs/runtime_persistence.md:23`“历史运行事件与审计记录保留在数据库作为去重凭据与历史审计总账”；`docs/blueprint/persistence.md:42` 同义。
- 证据：`runtime_events` FK 明确 CASCADE；`delete_profile` 删除主表后 SQLite 外键级联清空事件；`tests/unit/test_domain_and_repository.py:158-163` 只断言 profile/runtime 消失，未断言事件保留。
- 影响：事件去重总账/审计历史丢失，违背数据保留契约；t010 迁移/审计可能依赖该表。
- 修复建议：`runtime_events.profile_id` 改为 `SET NULL`/`RESTRICT` 或删除时显式保留（同时明确孤儿事件策略）；补真实删除后事件仍存在测试。
- 置信度：95

### COR-11 [Medium] 启动失败若 teardown 抛错会泄漏已分配 UDP 端口

- 位置：`src/backend/cbrowser/supervisor/core.py:559-578`；`src/backend/cbrowser/supervisor/core.py:600-605`
- 证据：失败路径先 `await self.docker.teardown_profile(profile_id)`，后 `await self.ports.release(profile_id)`；若 teardown（Docker 异常/归属不匹配）抛出，release 不执行。`stop_profile` 在 session 为 None 且无匹配容器时直接返回 stopped，也不 release；`scan` 404 路径同理 teardown 抛错则跳过 release。
- 触发条件：容器删除/网络清理失败（Docker daemon 抖动、未知端点、权限）恰好发生在启动失败或删除 Profile 收敛。
- 影响：端口在 `PortAllocator` 中永久占用且无 session/容器对应；多次后 992 个端口耗尽，所有新启动 503。
- 修复建议：`finally` 中释放端口（先确认无同 Profile 容器仍使用该端口），或 stop/scan 对 allocator 做孤儿清理；补 teardown 注入失败测试。
- 置信度：90

### COR-12 [Low] “保留健康 Browser” 注释与重试实际会杀 Browser

- 位置：`src/backend/cbrowser/supervisor/recovery_coordinator.py:126-134` 与 `:489-502`
- 证据：tick 发现 Browser running、Stream 失败时日志“Retaining healthy browser”，但 Condition 2 失败后调度 `_execute_retry`；重试 cleanup 调用 `stop_profile(expected_instance=old_inst)`，teardown 同时删除 Browser 和 Stream，再重启整对。
- 影响：注释/行为不一致；用户可见的“仅媒体失败”会升级为浏览器重启（状态保留但中断），排障预期错误。
- 修复建议：明确策略（只重启 Stream 或整对重启），同步注释/日志；若整对重启是设计，删除误导性“Retaining”说明并记录为重建语义。
- 置信度：85

______________________________________________________________________

## 3. 契约 / 类型 / Breaking

### CT-1 [Medium] `browser_isolation` spec 容器名/标签与实现不一致

- 位置：`docs/specs/browser_isolation.md:12-20` vs `src/backend/cbrowser/supervisor/docker_adapter.py:733-741`、`:916-926`
- 证据：spec 要求 `browser-runtime-{id}`/`stream-runtime-{id}`、`com.cbrowser.managed=true`、`com.cbrowser.runtime-image={digest}`；实现为 `{prefix}-browser-{id}`、`managed-by=supervisor`、`prefix`，无 `runtime-image`。`docs/specs_index.md` 仍列该 spec 生效且最后更新 t003，未随 t005/t007 更新。
- 影响：按 spec 的验收/清理/监控工具无法定位；文档权威性受损。
- 修复建议：更新 spec 到实现契约或加实现标签；同步 specs_index。
- 置信度：95

### CT-2 [Low] 公共 OpenAPI 暴露内部 Supervisor/Gateway 路由

- 位置：`schemas/openapi/cbrowser_v1.json:1472-1901`；`src/backend/cbrowser/api/app.py:297-300`；`scripts/export_openapi.py:11-23`
- 说明：内部路由有 Bearer 保护，不构成越权，但进入公共 schema 与前端生成类型，扩大接口面并误导客户端；建议导出时过滤或标注 internal。
- 置信度：80

### CT-3 [Low/已登记 p005] Gateway Origin 尾斜杠未归一

- 位置：`src/backend/cbrowser/gateway/config.py:68-71`
- 说明：p005 `t006_code_f001` 已登记且仍成立；API 已 `rstrip("/")`，Gateway 未做。建议在下一触及 Gateway 的 task 闭环。
- 置信度：95

### CT-4 [Info] 自动化凭证只有存储/授权，无自动化接入面

- 位置：`src/backend/cbrowser/api/internal_gateway.py:114-127`；`docs/specs/access_control.md:16-19`
- 说明：t008 尚未实施，当前无自动化客户端路由；按阶段边界不计缺陷，但验收时需补端到端路径。
- 置信度：85

### CT-5 [Medium] `runtime_persistence` spec 仍写 `failure_count>=3` 阻断，与 ADR 008/实现 4 冲突

- 位置：`docs/specs/runtime_persistence.md:59`；`docs/blueprint/decisions.md:76`（ADR 008）；`src/backend/cbrowser/domain/runtime_policy.py:3-4`
- 证据：ADR 008 明确首次异常后三次重试均失败、第 4 次阻断；代码 `BLOCK_AFTER_RUNTIME_FAILURES=4`；spec 仍写“达到 3 次时触发”。
- 影响：验收人员按 spec 预期第 3 次阻断会与实现/测试冲突；文档漂移。
- 修复建议：更新 spec 为 4，并引用 ADR 008。
- 置信度：95

### CT-6 [Medium] `v2_runtime_validation` 仍称刷新保留 `resume_key`，与 t007 修订冲突

- 位置：`docs/specs/v2_runtime_validation.md:34`（“刷新时…保留原有 ID 与 resume_key”）；`docs/archive/tasks/t007_v2_frontend_sessions/task.md` 上下文区（官方客户端刷新生成新 resume_key，仅连接内重连保留）；`docs/blueprint/frontend.md` 已写新语义。
- 影响：生效 spec 与当前前端/测试矛盾，验收和排障可能误判。
- 修复建议：更新 t001 spec 的 2.2，区分刷新与连接内重连。
- 置信度：95

### CT-7 [Low/旧文档债] 活动 blueprint/spec 仍描述控制租约/旧表

- 位置：`docs/blueprint/domain.md`（ControlSession/ControlLease/StreamTicket、15s/30s 租约）；`docs/specs/storage_and_artifacts.md:2.1`（`control_sessions`/`control_leases` 表）
- 说明：ADR 007 与 `persistence.md` 已废弃租约，8 张表无 leases；上述文档未被 t001–t007 修改，属**旧实现既存**文档债，但仍在活动 blueprint/spec，建议在 t011/t012 一并清理。
- 置信度：90

### CT-8 [Low] `runtime_persistence` 验收记录复选框与已完成 t002 不一致

- 位置：`docs/specs/runtime_persistence.md:123-128`（AC-002/003/004/006 仍未勾）
- 说明：t002 task 已 done 且 review PASS，specs_index 登记 t002；验收记录未同步，无法作为当前状态依据。
- 修复建议：同步勾选/备注证据或明确“spec 内验收记录仅历史快照”。
- 置信度：85

### CT-9 [Low] Gateway 端口与 `CBROWSER_GATEWAY_PORT` 默认值无单一来源

- 同 COR-1；另 `attach_profile_infrastructure` 的 `gateway_port` 不从环境读取，部署即使设置 Gateway 端口也无法自动告知 Supervisor。
- 置信度：90

______________________________________________________________________

## 4. 性能 / 资源

### PERF-1 [Medium] 每秒全量扫描 + 每 Profile 多次 RPC/Inspect/Stats

- 位置：`supervisor/runner.py:168-197`；`supervisor/core.py:126-369`；`supervisor/recovery_coordinator.py:63-245`；`supervisor/resource_monitor.py:84-156`
- 证据：后台每秒 `consume_disk_events`（遍历事件目录）+ `replay_spooled_events` + `scan_and_reconcile_existing`（`containers.list` + 每 Profile API GET + `inspect_container` + Gateway 调用）+ `recovery.tick`（全 profiles + 每 Profile runtime）；resource loop 每秒每 Profile 2 个 `stats(one_shot=True)`；COR-4 还重复接管。
- 触发条件：多 Profile 运行（t009 计划 10 Profile）。
- 影响：Docker/API/Gateway 压力与事件循环延迟，压缩 P95/首帧余量；t009 未执行前不能称容量通过。
- 修复建议：事件驱动或降频；缓存 profile 列表；scan 幂等短路；错峰资源采样。
- 置信度：90

### PERF-2 [Medium] 同步 Docker SDK/文件遍历阻塞事件循环

- 位置：`supervisor/docker_adapter.py:714-742`（containers.run）、`:950-973`（remove）、`:199-203`（每次 start 全量 rglob）；`supervisor/core.py:238`（inspect）、`:655`（teardown）
- 触发条件：启动/停止/扫描期间。
- 影响：控制面健康、SSE、Agent 心跳/注册出现秒级停顿；启动慢易触发 30s readiness 上限（`core.py:478-489`）。
- 修复建议：全部 Docker I/O 移入 `asyncio.to_thread`；缓存路径校验只在初始化/变更时执行；readiness 可配置。
- 置信度：85

### PERF-3 [Low] 事件文件/ACK/内存集合只增不减

- 位置：`supervisor/core.py:298-369`；`supervisor/event_forwarder.py:43-46`；`supervisor/recovery_coordinator.py:40-43`；`supervisor/core.py:104`
- 证据：已转发事件文件不删除，每秒重读历史；`_acknowledged` 启动全量读入并增长；`_reported_dead_instances`、`_native_exit_instances` 无界。
- 影响：8h 长跑文件/内存线性增长、扫描变慢（t009 余量）。
- 修复建议：转发后归档/删除；游标/压缩 ack；实例集合按生命周期清理。
- 置信度：90

### PERF-4 [Low] 前端诊断数组无界、输入逐条创建任务

- 位置：`src/frontend/src/features/browser-session/adapter.ts:67-77`；`src/backend/cbrowser/stream_agent/policy.py:215-221`
- 证据：`__sentDataChannelMessages` 永久 push；`record_input` 每输入消息 `create_task(reconcile_capture_state)`，鼠标移动可高频触发。
- 影响：长会话内存增长、输入风暴下任务/锁竞争，影响 1000 次/8h 验收余量。
- 修复建议：环形缓冲；输入合并为标志由周期 reconciler 处理。
- 置信度：80

### PERF-5 [Low] 每次启动全量缓存路径校验

- 位置：`supervisor/docker_adapter.py:199-203`（`rglob("*")` 对 engine-cache/geoip 全部条目）
- 影响：缓存含数千文件时每次 start 增加同步开销（且在事件循环内）。
- 修复建议：初始化/缓存变更时校验一次，启动只校验根和目标文件。
- 置信度：85

______________________________________________________________________

## 5. 架构 / 可维护性

### ARCH-1 [Low] 死代码与重复实现

- 位置：`src/backend/cbrowser/stream_agent/agent.py:90-110`（`_sanitize_packet` 仅自递归，无调用方）；`src/backend/cbrowser/rtc_config/credential.py:28-37`（`verify_turn_credentials` 仅导出）；`src/backend/cbrowser/stream_agent/client_shim.py:3-…`（与 `adapter.ts` 的 Web Locks 逻辑重复，仅供测试）
- 影响：审计面扩大、实现漂移；生产 adapter 与测试 shim 行为可能分叉。
- 修复建议：删除/标注预留；测试至少断言 shim 与生产 adapter 的关键身份语义一致。
- 置信度：90

### ARCH-2 [Low] 内部 RPC 复用公共 handler 产生隐式协调副作用

- 位置：`api/internal_supervisor.py:63-101`；`api/v1/router.py:479-497`；`supervisor/core.py:701-707`
- 证据：Supervisor `reset_blocked` 调 API `PATCH desired-state`，公共 handler 会发布 SSE 并 `trigger_reconcile`，形成 Supervisor→API→Supervisor 回环（靠锁/幂等收敛）。
- 影响：额外启动请求/SSE，异常时序下更难推理。
- 修复建议：内部 RPC 使用不触发协调的专用 handler，或显式 `no_reconcile`。
- 置信度：80

### ARCH-3 [Info] 超大文件/复杂度仍在

- 位置：`docker_adapter.py`（1098 行）、`stream_agent/agent.py`（1153）、`stream_agent/policy.py`（773）、`api/v1/router.py`（696）、`supervisor/core.py`（773）、`stream_agent/ice_transport.py`（667）、`frontend adapter.ts`（555）
- 说明：p001 已登记 tick/docker_adapter 等；本次确认规模未变，不重复计缺陷。
- 置信度：95

### ARCH-4 [Info] 镜像初始化/依赖可复现性不足

- 位置：`config/docker/supervisor_runtime/Dockerfile:19-20`（未复制 `cbrowser/__init__.py`，依赖 namespace package）、`gateway/stream` 复制方式不一致；四个 Dockerfile 基镜像用可漂移 tag（`python:3.12-slim-bookworm`）、Gateway/Supervisor 用 `>=` 依赖范围，无 lock。
- 影响：构建不可完全复现；升级依赖可能改变运行时；属 t012/p010 范围。
- 置信度：85

### ARCH-5 [Info] `schemas/runtime/agent_protocol.json` 无生成脚本

- 位置：`schemas/runtime/agent_protocol.json`；`scripts/` 只有 OpenAPI/stream/supervisor 导出；`tests/unit/test_runtime_protocol.py` 只校验 JSON/样例。
- 影响：Runtime Agent 协议模型与手写 schema 可能漂移；建议增加导出/深比较。
- 置信度：80

______________________________________________________________________

## 6. 健壮性 / 可观测性

### ROB-1 [Low] 退出原因白名单与实际取值不匹配

- 位置：`src/backend/diagnostics.py:247-264`
- 证据：白名单只有 `normal_exit/crash/...`；实际使用 `normal`/`abnormal`/`abnormal_lost`/`process_observation_lost`（`runner.py:559,584,601`）、`startup_failure`（`core.py:575`）、`container_terminated`/`missing_runtime`（`recovery_coordinator.py:229,302`），全部被替换为 `custom_reason`。
- 影响：结构化日志无法区分正常/异常/观测丢失/启动失败，违背可诊断目标。
- 修复建议：白名单与枚举共享常量，补测试。
- 置信度：95

### ROB-2 [Low] Viewer 首帧/隧道 open 发送失败时遗留 viewers 条目

- 位置：`gateway/server.py:514-544`（`viewers[conn_id]` 写入与两次 `send_str` 在 try 外）
- 影响：连接抖动时 `viewers` 泄漏，disconnect/轮换看到幽灵连接。
- 修复建议：发送包入 try/finally，失败移除并通知 Agent close。
- 置信度：85

### ROB-3 [Low] 单个畸形 spool 事件阻塞后续重放

- 位置：`supervisor/event_forwarder.py:168-178`；`supervisor/core.py:321-349`
- 证据：重放遇首个失败 `break`；`event_type` 未校验，API 422 持续失败，坏文件排前永久阻塞。
- 修复建议：坏事件 quarantine/跳过并告警；严格校验枚举/类型。
- 置信度：82

### ROB-4 [Info] 心跳超时使用 wall clock

- 位置：`gateway/registry.py:60-70`
- 说明：时钟回拨延迟驱逐、前跳提前驱逐；liveness 建议 monotonic（TURN 到期仍需 wall clock）。
- 置信度：85

### ROB-5 [Low] `scan` 每秒重复告警“Unprotected sandbox not adopted” 且不隔离

- 位置：`supervisor/core.py:222-226`
- 证据：policy_ready 为 false 时只 `continue`，容器保持运行但不纳入 session/资源/端口管理，每秒重复 warning；若 gate 未开放，容器可能处于半启动状态。
- 影响：暴露未受策略保护的沙箱、日志噪声；无自动清理。
- 修复建议：对该状态设置一次性告警并对安全失败容器执行受控 teardown（或留待显式人工处理），不要静默无限重试。
- 置信度：80

### ROB-6 [Low] `RuntimeCoordinator` 启动收敛在 API 尚未监听时先发 RPC

- 位置：`api/runtime_coordinator.py:194-227`；`api/app.py:105-119`
- 证据：lifespan 在 `coordinator.start()` 内调度 task，早于 `init_admin_password`/yield；Supervisor 启动时会回查 API，而 API 尚未 accept，首轮可能失败并退避。
- 影响：启动日志错误/延迟收敛；最终可恢复，但排障噪声。
- 修复建议：在 yield 后或 API 监听就绪后再启动收敛扫描。
- 置信度：75

______________________________________________________________________

## 7. 测试 / 规格

### TEST-1 [Medium] Stream egress 契约无测试

- 位置：`tests/unit/test_network_policy.py:61-90`；`tests/e2e/test_supervisor_namespace_policy_e2e.py`（browser-only 公网正例）
- 影响：SEC-1 漏检；“网络正负对照”不能证明 Stream 只允许 Gateway/coturn。
- 建议：stream 规则断言 + 非白名单公网负例。
- 置信度：95

### TEST-2 [Medium] 无事件伪造/畸形事件测试

- 位置：`tests/unit/test_supervisor_event_delivery.py`（身份测试但不覆盖伪造/非法 event_type）；`tests/unit/test_runtime_event_policy.py`（非退出事件不改变状态）
- 影响：SEC-2/ROB-3/COR-9 无回归保护。
- 建议：伪造 exit0、非法 event_type、坏 config_version、lifecycle 收敛。
- 置信度：90

### TEST-3 [Low] 停止路径未覆盖 Gateway 503 + Stream running

- 位置：`tests/unit/test_supervisor_stop_fence.py`、`tests/e2e/test_supervisor_recovery_e2e.py`
- 影响：COR-2 无回归。
- 置信度：85

### TEST-4 [Low] 恢复版本选择无测试

- 位置：`tests/unit/test_supervisor_recovery.py` 全部使用 config_version=1，无“运行中更新未应用 + 崩溃”场景
- 影响：COR-3 无回归。
- 置信度：85

### TEST-5 [Low] 删除后事件保留无测试

- 位置：`tests/unit/test_domain_and_repository.py:158-163`；`tests/integration/test_v2_api_subprocess.py:297-298`
- 影响：COR-10 无回归。
- 置信度：90

### TEST-6 [Low] 非空字段 null 更新无测试

- 位置：`tests/integration/test_v2_api_subprocess.py:233-258`（仅测空串/负数）
- 影响：COR-6 无回归。
- 置信度：90

### TEST-7 [Low] 过期 current generation 无测试

- 位置：`tests/unit/test_rtc_config.py:147-148`（仅 is_expired）；`tests/integration/test_gateway_rotation.py`（未构造 current 过期）
- 影响：COR-5 无回归。
- 置信度：85

### TEST-8 [Low] lifecycle/error 到 API 的收敛无测试

- 位置：`tests/e2e/test_browser_runtime_e2e.py:1616-1770`（只验证 Agent/本地 state）；`tests/integration/test_v2_api_subprocess.py` 无 lifecycle 用例
- 影响：COR-9 无回归。
- 置信度：88

### TEST-9 [Info] 本路未执行任何测试/构建

- 说明：仓库内 E2E 证据与既有 review PASS 只作追溯；本路不能据此称当前 HEAD 通过。

### TEST-10 [Low] 端口泄漏失败注入无测试

- 位置：`tests/integration/test_supervisor_start_capacity.py` 只测绑定后耗尽；`tests/unit/test_supervisor_port_recovery.py` 只测 allocator
- 影响：COR-11 无回归。
- 置信度：85

______________________________________________________________________

## 8. 文档规范

### DOC-1 [Medium] `browser_isolation` spec 标签/名称漂移

- 同 CT-1；active spec 与实现/测试不一致，`specs_index` 仍标 t003 最后更新。
- 置信度：95

### DOC-2 [Medium] Stream egress 规范与实现矛盾

- 同 SEC-1；`supervisor.md:49`、`runtime_lifecycle.md:10` 与 `network_policy.py` 冲突。需决定“Stream 是否允许公网直连”，并同步 spec/蓝图/测试。
- 置信度：95

### DOC-3 [Low/已登记 p005] t006 minor 未闭环

- `docs/pending/todo/p005_t006_review_minors.md`：f001 尾斜杠、f003 `_restart_tasks` 未取消失败仍成立；t007 已收尾但未处理。建议下一触及 Gateway/Agent 的 task 闭环。
- 置信度：95

### DOC-4 [Medium] `runtime_persistence` failure_count 阈值过期

- 同 CT-5；ADR 008 已替代，spec 未更新。
- 置信度：95

### DOC-5 [Medium] `v2_runtime_validation` resume_key 语义过期

- 同 CT-6；t007 修订后刷新会生成新 resume_key，旧 spec 仍称保留。
- 置信度：95

### DOC-6 [Low] `domain.md` / `storage_and_artifacts.md` 仍写 ControlSession/ControlLease/旧表

- 同 CT-7；属旧文档债，非累计改动引入，但活动文档应清理。
- 置信度：90

### DOC-7 [Low] `testing.md` 前端/后端测试数量陈旧

- 位置：`docs/blueprint/testing.md:...` 仍写前端 49 tests、legacy 384；t007 门禁实际 Vitest 105、unit 307、integration 55；文档混合基线与当前值未注明版本。
- 影响：读者误判门禁范围。
- 修复建议：按阶段/版本标注或更新为当前值。
- 置信度：85

### DOC-8 [Info] 历史档案与任务记录

- `docs/archive/spikes/**`、`docs/archive/tasks/**` 的 report/review/old code 保留历史语义；本路按 findings d001–d024、task/note/handoff 交叉核对，不把其历史 PASS 当当前正确性保证；归档字节/行尾空格不视为当前文档冲突。
- 置信度：—

______________________________________________________________________

## Spec 合规结论（按 `specs_index`）

|Spec|结论|证据/缺口|
|---|---|---|
|`access_control`|基本符合|Argon2id、Secure/HttpOnly/SameSite、CSRF/Origin、429、Viewer 三级校验、自动化 token 存储/撤销/审计；SEC-3 可用性偏差；自动化接入面属 t008。|
|`runtime_lifecycle`|部分符合|Docker 单持有者、端口池、gate fence、事件 fence、2/10/30/4、恢复、手动重试；COR-2/9/11、SEC-1/2、PERF-1/2 与规范冲突。|
|`webrtc_remote_display`|部分符合|独立隧道、token 注入、RTC 轮换、ICE 提交、适配层、音频状态；COR-5（过期凭证）违反“不向新连接下发过期凭证”；COR-3 与 apply 语义冲突。|
|`browser_isolation`|文档漂移/部分符合|双容器、IPC、非 root、只读根、cap-drop、CDP loopback、Stream 不挂用户数据；CT-1 标签/名称过时，SEC-1 egress 超范围。|
|`profile_management`|基本符合|URL 页面独立目标、登录回跳同源、SSE、API 启停、显示待应用；COR-6/7 输入边界偏差。|
|`runtime_persistence`|部分符合|WAL/busy_timeout、BEGIN IMMEDIATE、幂等/实例 fence/版本快照、迁移与模型一致（0001/0002 已核）；COR-6/10、CT-5/8 文档/数据保留偏差。|
|`storage_and_artifacts`|阶段外/旧文档|t008 未实施；spec 仍列租约旧表（CT-7），不计当前实现缺陷。|
|`v2_runtime_validation`|历史/部分过期|t001 证据有效；resume_key 描述与 t007 冲突（CT-6）。|

______________________________________________________________________

## Strengths

1. **凭证/秘密边界扎实**：外部文件、最小长度、fail-closed；Agent HMAC 派生、Gateway/Agent 双向身份匹配、Selkies token 独立 `.secrets` 0600 且 Browser 不挂载、TURN REST 短期凭证、日志脱敏白名单。
2. **实例 fence/幂等**：API 绑定/观测/事件 fencing、操作日志、审计幂等、stop expected_instance、native exit 优先，能防止旧代覆盖新代；`test_supervisor_event_delivery` 等负例存在。
3. **网络隔离方向正确**：netns helper + gate + IPv4/IPv6 私有段阻断 + DNS 在 gated runtime；Browser 侧验证较完整（问题集中在 Stream 最终放行与测试盲区）。
4. **前端会话分层**：固定 Selkies 资产/单一 adapter 构建、HELLO/tab_id/resume_key 保留、每页静音走官方 pipelineControl、阶段诊断、冻结恢复、防止开放重定向。
5. **持久化/恢复基础**：原子写+fsync、spool+ack、404 才清理、API 离线保留容器、Supervisor SIGKILL 恢复均有真实 E2E 证据（历史）。
6. **规格/证据链**：t001–t007 task/note/findings 对失败、撤回、遗留记录较完整，pending 能追踪已知 minor（p001/p005–p013）。

______________________________________________________________________

## Appendix A：逐路径覆盖清单（`[R]` 正文/分段读过；`[S]` 读头部/用例名/关键断言或结构；`[H]` 历史档案，按 report/findings 溯源，未逐行；`[M]` 机械生成/lockfile，核对来源与差异；`[N]` 未读）

> 为满足逐路径披露，下面按 `changed_files.txt` 分组列出全部 507 条。同一目录块的状态适用于块内每一项；例外在块首注明。删除/重命名项注明行为迁移。

### Root / 配置 / schema / scripts（除注明均为 `[R]`）

```
.gitignore  [M]
pyproject.toml  [R]
config/docker/browser_runtime/Dockerfile
config/docker/browser_runtime/entrypoint.sh
config/docker/gateway_runtime/Dockerfile
config/docker/gateway_runtime/Dockerfile.dockerignore  [S]
config/docker/stream_runtime/Dockerfile
config/docker/stream_runtime/entrypoint.sh
config/docker/supervisor_runtime/Dockerfile
config/docker/supervisor_runtime/Dockerfile.dockerignore  [S]
schemas/openapi/cbrowser_v1.json  [S]（生成物；核对路径/模型，未逐字段 diff）
schemas/runtime/agent_protocol.json  [S]
schemas/runtime/supervisor_protocol.json  [S]
schemas/stream/agent_protocol.json  [S]
scripts/export_openapi.py  [R]
scripts/export_stream_protocol.py  [R]
scripts/export_supervisor_protocol.py  [R]
scripts/vendor_selkies_web.py  [R]
```

### `src/backend`（74）

块内 `[R]`，例外：`migrations/script.py.mako` = `[S]`（模板）。

```
src/backend/cbrowser/adapters/database/migrations.py
src/backend/cbrowser/adapters/database/models.py
src/backend/cbrowser/adapters/database/repository.py
src/backend/cbrowser/adapters/database/session.py
src/backend/cbrowser/api/app.py
src/backend/cbrowser/api/internal_gateway.py
src/backend/cbrowser/api/internal_supervisor.py
src/backend/cbrowser/api/main.py
src/backend/cbrowser/api/runtime_coordinator.py
src/backend/cbrowser/api/v1/auth_router.py
src/backend/cbrowser/api/v1/router.py
src/backend/cbrowser/auth/__init__.py
src/backend/cbrowser/auth/dependencies.py
src/backend/cbrowser/auth/rate_limiter.py
src/backend/cbrowser/auth/service.py
src/backend/cbrowser/domain/models.py
src/backend/cbrowser/domain/runtime_policy.py
src/backend/cbrowser/gateway/__init__.py
src/backend/cbrowser/gateway/__main__.py
src/backend/cbrowser/gateway/api_client.py
src/backend/cbrowser/gateway/config.py
src/backend/cbrowser/gateway/registry.py
src/backend/cbrowser/gateway/rotation.py
src/backend/cbrowser/gateway/server.py
src/backend/cbrowser/rtc_config/__init__.py
src/backend/cbrowser/rtc_config/credential.py
src/backend/cbrowser/rtc_config/models.py
src/backend/cbrowser/rtc_config/service.py
src/backend/cbrowser/runtime_agent/__main__.py
src/backend/cbrowser/runtime_agent/agent.py
src/backend/cbrowser/runtime_agent/cdp_proxy.py
src/backend/cbrowser/runtime_agent/event_storage.py
src/backend/cbrowser/runtime_agent/profile_defaults.py
src/backend/cbrowser/runtime_agent/protocol.py
src/backend/cbrowser/runtime_agent/runner.py
src/backend/cbrowser/runtime_agent/security.py
src/backend/cbrowser/runtime_agent/subsystems.py
src/backend/cbrowser/services/profile_service.py
src/backend/cbrowser/stream_agent/__init__.py
src/backend/cbrowser/stream_agent/agent.py
src/backend/cbrowser/stream_agent/boundary.py
src/backend/cbrowser/stream_agent/client_shim.py
src/backend/cbrowser/stream_agent/config.py
src/backend/cbrowser/stream_agent/ice_transport.py
src/backend/cbrowser/stream_agent/policy.py
src/backend/cbrowser/stream_agent/protocol.py
src/backend/cbrowser/stream_agent/x11_keymap.py
src/backend/cbrowser/supervisor/__init__.py
src/backend/cbrowser/supervisor/__main__.py
src/backend/cbrowser/supervisor/agent_credentials.py
src/backend/cbrowser/supervisor/control_server.py
src/backend/cbrowser/supervisor/coordinator_lock.py
src/backend/cbrowser/supervisor/core.py
src/backend/cbrowser/supervisor/docker_adapter.py
src/backend/cbrowser/supervisor/event_forwarder.py
src/backend/cbrowser/supervisor/file_storage.py
src/backend/cbrowser/supervisor/gateway_client.py
src/backend/cbrowser/supervisor/network_policy.py
src/backend/cbrowser/supervisor/operation_journal.py
src/backend/cbrowser/supervisor/path_validator.py
src/backend/cbrowser/supervisor/port_allocator.py
src/backend/cbrowser/supervisor/protocol.py
src/backend/cbrowser/supervisor/recovery_coordinator.py
src/backend/cbrowser/supervisor/resource_monitor.py
src/backend/cbrowser/supervisor/resource_policy.py
src/backend/cbrowser/supervisor/runner.py
src/backend/cbrowser/supervisor/selkies_tokens.py
src/backend/cbrowser/supervisor/startup_gate.py
src/backend/diagnostics.py
src/backend/migrations/alembic.ini
src/backend/migrations/env.py
src/backend/migrations/script.py.mako  [S]
src/backend/migrations/versions/0001_initial_schema.py
src/backend/migrations/versions/0002_auth.py
```

### `src/frontend`（45）

`[R]` 生产文件；测试 `[S]`（读用例名/断言/头部）；生成/锁 `[M]`。

```
src/frontend/package-lock.json  [M]（仅核对依赖变化来源）
src/frontend/package.json  [R]
src/frontend/src/app/AppLayout.tsx
src/frontend/src/app/RequireAuth.tsx
src/frontend/src/app/auth_guard.test.tsx  [S]
src/frontend/src/app/providers.tsx
src/frontend/src/app/router.test.tsx  [S]
src/frontend/src/app/router.tsx
src/frontend/src/features/artifacts/ProfileFilesPlaceholder.tsx  [S]
src/frontend/src/features/auth/LoginPage.tsx
src/frontend/src/features/auth/redirect.ts
src/frontend/src/features/auth/useAuth.tsx
src/frontend/src/features/automation/ProfileAutomationPlaceholder.tsx  [S]
src/frontend/src/features/browser-session/BrowserSessionView.test.tsx  [S]
src/frontend/src/features/browser-session/BrowserSessionView.tsx
src/frontend/src/features/browser-session/SessionDiagnostics.tsx
src/frontend/src/features/browser-session/adapter.ts
src/frontend/src/features/browser-session/adapter_restart.test.ts  [R]
src/frontend/src/features/browser-session/audio_control.ts
src/frontend/src/features/browser-session/audio_status.test.ts  [R]
src/frontend/src/features/browser-session/audio_status.ts
src/frontend/src/features/browser-session/host_entry.tsx
src/frontend/src/features/browser-session/index.ts
src/frontend/src/features/browser-session/media_controls.test.tsx  [S]
src/frontend/src/features/browser-session/selkies_adapter_entry.ts
src/frontend/src/features/browser-session/types.ts
src/frontend/src/features/browser-session/useBrowserSession.ts
src/frontend/src/features/profiles/BrowserSessionPage.tsx
src/frontend/src/features/profiles/ProfileDetailPage.tsx
src/frontend/src/features/profiles/ProfileNewPage.tsx
src/frontend/src/features/profiles/useProfilesQuery.test.tsx  [S]
src/frontend/src/features/profiles/useProfilesQuery.ts
src/frontend/src/features/settings/SettingsPage.tsx  [S]（前 80 行；其余硬编码属 p007）
src/frontend/src/i18n.tsx  [S]（新增键/中英对照）
src/frontend/src/main.tsx
src/frontend/src/shared/api/client.test.ts  [S]
src/frontend/src/shared/api/client.ts
src/frontend/src/shared/api/generated/cbrowser_v1.d.ts  [M]（生成物，抽样关键模型）
src/frontend/src/shared/api/sse.test.ts  [S]
src/frontend/src/shared/api/sse.ts
src/frontend/src/shared/api/types.ts
src/frontend/src/shared/components/BrowserSessionMount.tsx
src/frontend/src/vite-env.d.ts  [S]
src/frontend/tsconfig.json
src/frontend/vite.selkies.config.ts
```

### `tests`（151）

`[S]` 统一表示：已读取文件名、全部用例名、关键断言/头部；约 15 个文件逐行（标 `[R]`）。其余正文未逐行，未运行。

```
tests/e2e/*  [S]（全部 38 个 E2E；重点 test_frontend_app_e2e.py:753-880、test_frontend_session_e2e.py:365-463、test_supervisor_namespace_policy_e2e.py:124-540 读断言）
tests/fixtures/*  [S]（api_auth.py、frontend_probe/harness.py、gateway_probe/topology.py 读关键段；其余按引用）
tests/integration/*  [S]（test_auth_api.py、test_v2_api_subprocess.py:220-300、test_gateway_rotation.py 关键段读）
tests/unit/test_domain_and_repository.py  [R]（重点段）
tests/unit/test_network_policy.py  [R]
tests/unit/test_runtime_event_policy.py  [R]
tests/unit/test_supervisor_event_delivery.py  [R]
tests/unit/test_supervisor_reconcile_fences.py  [R]
tests/unit/test_runtime_coordinator_background_tasks.py  [R]
tests/unit/test_api_models_and_sse.py  [S]
其余 unit/integration/e2e 文件  [S]
```

完整 151 个测试路径在下方 A.1 逐条列出；状态以每行尾部为准。

### `docs`（219）

`[R]` 已读正文/关键段；`[H]` 历史档案按 report/findings/task 交叉核对，未逐行；`[S]` 读摘要/结构。

```
docs/archive/handoff.md  [H]
docs/archive/pending/*  [R]
docs/archive/specs/chrome_external_tabs.md  [R]（重命名保留旧租约语义，已被 profile_management 取代）
docs/archive/spikes/**  [H]（s001–s010 的 report/review 抽样；code 未逐行；不据此判当前正确性）
docs/archive/tasks/t001..t007/{task.md,note.md}  [R]；{review_code,review_test,handoff.json,scope_adjustment,validation_matrix}  [H/S]
docs/archive/tasks_index.json  [S]
docs/blueprint/{architecture,browser_runtime,decisions,frontend,gateway,persistence,security,stream_runtime,supervisor,testing}.md  [R]
docs/findings/d001..d024  [R]
docs/guides/*  [R]
docs/handoff.md  [R]
docs/pending/todo/p001,p005..p013  [R]
docs/reviews/review_local_benchmark_20261027/review_benchmark.md  [S]
docs/reviews/review_v2_scope_20261027/{review_disposition,review_scope_revised,review_traceability}.md  [R]；{review_scope_initial}  [S]
docs/specs/{access_control,browser_isolation,profile_management,runtime_lifecycle,runtime_persistence,storage_and_artifacts,v2_runtime_validation,webrtc_remote_display}.md  [R]
docs/specs_index.md  [R]
docs/tasks/t008..t014/{task.md,note.md}  [R/S]（task.md 全读，note 为 backlog 模板）
docs/tasks_index.json  [R]
docs/v2_architecture_plan.md  [R]（豁免/修订/相关章节）
```

以下变更文档路径同样已计入：`docs/archive/specs/chrome_external_tabs.md`（R100 改名）、`docs/tasks/t001_v2_runtime_validation/task.md`（D，已归档）、`docs/tasks/t001_v2_runtime_validation/note.md` → `docs/tasks/t010_v2_data_migration/note.md`（R093；当前内容为 backlog 模板，不是 t001 正文迁移）、`docs/tasks_index.json`/`docs/archive/tasks_index.json`（[R]）。历史档案中的旧路径/旧租约/旧状态只保留历史语义，不当作当前实现冲突。

### Appendix A.1 `tests` 全量 151 路径（默认 `[S]`，行的尾部 `[R]` 为逐行重点段）

```
tests/e2e/test_browser_runtime_e2e.py [S]
tests/e2e/test_frontend_adapter_build.py [S]
tests/e2e/test_frontend_app_auth_e2e.py [S]
tests/e2e/test_frontend_app_e2e.py [S]
tests/e2e/test_frontend_display_apply_e2e.py [S]
tests/e2e/test_frontend_ice_failure_e2e.py [S]
tests/e2e/test_frontend_media_e2e.py [S]
tests/e2e/test_frontend_session_e2e.py [S]
tests/e2e/test_frontend_session_vendor.py [R]
tests/e2e/test_gateway_ac001_auth_e2e.py [S]
tests/e2e/test_gateway_ac003_media_e2e.py [S]
tests/e2e/test_gateway_ac005_relay_e2e.py [S]
tests/e2e/test_gateway_ac007_visibility_e2e.py [S]
tests/e2e/test_runtime_coordinator_e2e.py [S]
tests/e2e/test_runtime_profile_defaults_e2e.py [S]
tests/e2e/test_stream_client_identity_e2e.py [S]
tests/e2e/test_stream_ice_commit_e2e.py [S]
tests/e2e/test_stream_ice_failure_e2e.py [S]
tests/e2e/test_stream_ice_relay_e2e.py [S]
tests/e2e/test_stream_rtc_config_e2e.py [S]
tests/e2e/test_stream_runtime_e2e.py [S]
tests/e2e/test_stream_selkies_tokens_e2e.py [S]
tests/e2e/test_stream_x11_keymap_e2e.py [S]
tests/e2e/test_supervisor_browser_network_e2e.py [S]
tests/e2e/test_supervisor_cache_initialization_e2e.py [S]
tests/e2e/test_supervisor_container_graph_e2e.py [S]
tests/e2e/test_supervisor_core_e2e.py [S]
tests/e2e/test_supervisor_infrastructure_network_e2e.py [S]
tests/e2e/test_supervisor_ipv6_policy_e2e.py [S]
tests/e2e/test_supervisor_namespace_policy_e2e.py [S]
tests/e2e/test_supervisor_network_ownership_e2e.py [S]
tests/e2e/test_supervisor_offline_recovery_e2e.py [S]
tests/e2e/test_supervisor_orphan_helpers_e2e.py [S]
tests/e2e/test_supervisor_policy_failure_e2e.py [S]
tests/e2e/test_supervisor_recovery_e2e.py [S]
tests/e2e/test_supervisor_resource_capacity_e2e.py [S]
tests/e2e/test_supervisor_resource_monitor_e2e.py [S]
tests/e2e/test_supervisor_resource_policy_e2e.py [S]
tests/e2e/test_supervisor_retry_e2e.py [S]
tests/e2e/test_supervisor_startup_recovery_e2e.py [S]
tests/fixtures/api_auth.py [S]
tests/fixtures/frontend_app_probe/__init__.py [S]
tests/fixtures/frontend_app_probe/harness.py [S]
tests/fixtures/frontend_probe/__init__.py [S]
tests/fixtures/frontend_probe/harness.py [S]
tests/fixtures/frontend_probe/host_builder.py [S]
tests/fixtures/gateway_probe/__init__.py [S]
tests/fixtures/gateway_probe/browser_oracle.py [S]
tests/fixtures/gateway_probe/caddyfile.py [S]
tests/fixtures/gateway_probe/evidence.py [S]
tests/fixtures/gateway_probe/selkies_assets.py [S]
tests/fixtures/gateway_probe/selkies_web_sha256.txt [S]
tests/fixtures/gateway_probe/topology.py [S]
tests/fixtures/runtime_probe/audio_analyzer.py [S]
tests/fixtures/runtime_probe/test_mitshm.c [S]
tests/fixtures/stream_probe/chrome_relay.py [S]
tests/fixtures/stream_probe/clipboard_oracle.py [S]
tests/fixtures/stream_probe/ice_commit_outcome.py [S]
tests/fixtures/stream_probe/ice_pending_close.py [S]
tests/fixtures/stream_probe/ice_relay_generations.py [S]
tests/fixtures/stream_probe/ice_restart_failure.py [S]
tests/fixtures/stream_probe/ice_turn_timeout.py [S]
tests/fixtures/stream_probe/media_page.html [S]
tests/fixtures/stream_probe/rtc_config_apply.py [S]
tests/fixtures/stream_probe/rtc_config_relay_only.py [S]
tests/fixtures/stream_probe/x11_keymap_probe.py [S]
tests/fixtures/supervisor_container_probe/api_runtime.Dockerfile [S]
tests/fixtures/supervisor_container_probe/api_runtime.Dockerfile.dockerignore [S]
tests/fixtures/supervisor_container_probe/gateway_container.py [S]
tests/fixtures/supervisor_container_probe/gateway_runtime.Dockerfile [S]
tests/fixtures/supervisor_container_probe/gateway_runtime.Dockerfile.dockerignore [S]
tests/fixtures/supervisor_recovery_probe/gateway_contract.md [S]
tests/fixtures/supervisor_recovery_probe/gateway_fixture.py [S]
tests/fixtures/supervisor_recovery_probe/offline_fixture.py [S]
tests/fixtures/supervisor_resource_probe/cpu_burner.py [S]
tests/fixtures/supervisor_resource_probe/stream_monitor.py [S]
tests/integration/test_api_sse_events.py [S]
tests/integration/test_auth_api.py [S]
tests/integration/test_gateway_control.py [S]
tests/integration/test_gateway_fixtures.py [S]
tests/integration/test_gateway_rotation.py [S]
tests/integration/test_gateway_signaling.py [S]
tests/integration/test_recovery_snapshot_failure.py [S]
tests/integration/test_runtime_coordinator_integration.py [S]
tests/integration/test_sse_epoch_integration.py [S]
tests/integration/test_supervisor_gateway_client.py [S]
tests/integration/test_supervisor_gateway_fixture_auth.py [S]
tests/integration/test_supervisor_manual_retry.py [S]
tests/integration/test_supervisor_rpc.py [S]
tests/integration/test_supervisor_start_capacity.py [S]
tests/integration/test_supervisor_status_truth.py [S]
tests/integration/test_v2_api_subprocess.py [S]
tests/unit/test_api_models_and_sse.py [S]
tests/unit/test_api_runtime_coordinator.py [S]
tests/unit/test_auth_models.py [S]
tests/unit/test_auth_service.py [S]
tests/unit/test_browser_readiness_fence.py [S]
tests/unit/test_control_error_redaction.py [S]
tests/unit/test_domain_and_repository.py [S]
tests/unit/test_gateway_config.py [S]
tests/unit/test_gateway_registry.py [S]
tests/unit/test_network_policy.py [R]
tests/unit/test_network_policy_input_safety.py [S]
tests/unit/test_recovery_authority.py [S]
tests/unit/test_recovery_shutdown_safety.py [S]
tests/unit/test_resource_fault_isolation.py [S]
tests/unit/test_rtc_config.py [S]
tests/unit/test_runtime_agent.py [S]
tests/unit/test_runtime_agent_faults.py [S]
tests/unit/test_runtime_coordinator_background_tasks.py [R]
tests/unit/test_runtime_coordinator_stop_paths.py [S]
tests/unit/test_runtime_event_broadcaster_epoch.py [R]
tests/unit/test_runtime_event_policy.py [R]
tests/unit/test_runtime_instance_storage.py [S]
tests/unit/test_runtime_persistence_guards.py [S]
tests/unit/test_runtime_profile_defaults.py [S]
tests/unit/test_runtime_protocol.py [S]
tests/unit/test_stream_agent_lifecycle.py [S]
tests/unit/test_stream_agent_protocol_v2.py [S]
tests/unit/test_stream_binding_guards.py [S]
tests/unit/test_stream_capture_policy.py [S]
tests/unit/test_stream_display_config.py [S]
tests/unit/test_stream_ice_security.py [S]
tests/unit/test_stream_ice_transport.py [S]
tests/unit/test_stream_protocol_schema.py [S]
tests/unit/test_stream_runtime.py [S]
tests/unit/test_stream_selkies_tokens.py [S]
tests/unit/test_stream_transport_hardening.py [S]
tests/unit/test_supervisor_adapter_paths.py [S]
tests/unit/test_supervisor_agent_credentials.py [S]
tests/unit/test_supervisor_control_auth.py [S]
tests/unit/test_supervisor_coordinator_lock.py [S]
tests/unit/test_supervisor_core.py [S]
tests/unit/test_supervisor_display_config.py [S]
tests/unit/test_supervisor_event_delivery.py [R]
tests/unit/test_supervisor_file_storage.py [S]
tests/unit/test_supervisor_infrastructure_config.py [S]
tests/unit/test_supervisor_operation_journal.py [S]
tests/unit/test_supervisor_port_recovery.py [S]
tests/unit/test_supervisor_profile_path_ownership.py [S]
tests/unit/test_supervisor_reconcile_fences.py [R]
tests/unit/test_supervisor_recovery.py [S]
tests/unit/test_supervisor_recovery_coordinator.py [S]
tests/unit/test_supervisor_resource_aggregation.py [S]
tests/unit/test_supervisor_resource_policy.py [S]
tests/unit/test_supervisor_schema.py [S]
tests/unit/test_supervisor_selkies_token_instances.py [S]
tests/unit/test_supervisor_selkies_token_isolation.py [S]
tests/unit/test_supervisor_selkies_tokens.py [S]
tests/unit/test_supervisor_startup_recovery.py [S]
tests/unit/test_supervisor_stop_fence.py [S]
```

### Appendix A.2 `docs` 全量 219 路径（`[R]` 读正文/关键段；`[S]` 读摘要/结构；`[H]` 历史档案按 report/findings 溯源，未逐行）

```
docs/archive/handoff.md [H]
docs/archive/pending/p002_policy_failure_test_conditional_asserts.md [R]
docs/archive/pending/p003_api_supervisor_start_wiring.md [R]
docs/archive/pending/p004_selkies_profile_tokens.md [R]
docs/archive/specs/chrome_external_tabs.md [R]（由 docs/specs 改名；旧租约语义归档）
docs/archive/spikes/s001_selkies_runtime/blackbox_review.md [H]
docs/archive/spikes/s001_selkies_runtime/code/Dockerfile.spike-browser [H]
docs/archive/spikes/s001_selkies_runtime/code/Dockerfile.spike-stream [H]
docs/archive/spikes/s001_selkies_runtime/code/entry_browser_full.sh [H]
docs/archive/spikes/s001_selkies_runtime/code/gen_wav.py [H]
docs/archive/spikes/s001_selkies_runtime/code/run_spike.sh [H]
docs/archive/spikes/s001_selkies_runtime/code/test_cloak_loop.py [H]
docs/archive/spikes/s001_selkies_runtime/code/test_mitshm.c [H]
docs/archive/spikes/s001_selkies_runtime/first_review.md [H]
docs/archive/spikes/s001_selkies_runtime/image_manifest.json [H]
docs/archive/spikes/s001_selkies_runtime/report.md [H]
docs/archive/spikes/s002_selkies_protocol/code/datachannel_restart_probe.py [H]
docs/archive/spikes/s002_selkies_protocol/code/ice_restart_probe.py [H]
docs/archive/spikes/s002_selkies_protocol/code/turn_auth_probe.py [H]
docs/archive/spikes/s002_selkies_protocol/report.md [H]
docs/archive/spikes/s003_selkies_control/blackbox_review.md [H]
docs/archive/spikes/s003_selkies_control/code/container_uds/browser_agent.py [H]
docs/archive/spikes/s003_selkies_control/code/container_uds/container_cdp_probe.py [H]
docs/archive/spikes/s003_selkies_control/code/container_uds/run_cross_container.py [H]
docs/archive/spikes/s003_selkies_control/code/container_uds/supervisor_client.py [H]
docs/archive/spikes/s003_selkies_control/code/container_uds/supervisor_override_control.py [H]
docs/archive/spikes/s003_selkies_control/code/recovery_probe/container_agent.py [H]
docs/archive/spikes/s003_selkies_control/code/recovery_probe/roles.py [H]
docs/archive/spikes/s003_selkies_control/code/recovery_probe/test_orchestration.py [H]
docs/archive/spikes/s003_selkies_control/code/test_cdp_real.py [H]
docs/archive/spikes/s003_selkies_control/code_review.md [H]
docs/archive/spikes/s003_selkies_control/container_download_report.md [H]
docs/archive/spikes/s003_selkies_control/container_download_review.md [H]
docs/archive/spikes/s003_selkies_control/recovery_review.md [H]
docs/archive/spikes/s003_selkies_control/report.md [H]
docs/archive/spikes/s004_media_connections/blackbox_review.md [H]
docs/archive/spikes/s004_media_connections/code/entrypoint_browser.sh [H]
docs/archive/spikes/s004_media_connections/code/entrypoint_stream.sh [H]
docs/archive/spikes/s004_media_connections/code/media_e2e_probe.py [H]
docs/archive/spikes/s004_media_connections/code/start_containers.sh [H]
docs/archive/spikes/s004_media_connections/code/stop_containers.sh [H]
docs/archive/spikes/s004_media_connections/report.md [H]
docs/archive/spikes/s005_capture_policy/code/entrypoint_browser.sh [H]
docs/archive/spikes/s005_capture_policy/code/entrypoint_stream.py [H]
docs/archive/spikes/s005_capture_policy/code/live_policy_agent.py [H]
docs/archive/spikes/s005_capture_policy/code/native_visibility_e2e.py [H]
docs/archive/spikes/s005_capture_policy/code/revision_03/test_e2e_real_pipeline.py [H]
docs/archive/spikes/s005_capture_policy/code/test_e2e_real_pipeline.py [H]
docs/archive/spikes/s005_capture_policy/code/test_page.html [H]
docs/archive/spikes/s005_capture_policy/independent_review.md [H]
docs/archive/spikes/s005_capture_policy/independent_review_r4.md [H]
docs/archive/spikes/s005_capture_policy/report.md [H]
docs/archive/spikes/s005_capture_policy/report_v1.md [H]
docs/archive/spikes/s006_gateway_media_recovery/code/media_fixture/entry_browser_full.sh [H]
docs/archive/spikes/s006_gateway_media_recovery/code/media_fixture/gen_wav.py [H]
docs/archive/spikes/s006_gateway_media_recovery/code/media_fixture/test_cloak_loop.py [H]
docs/archive/spikes/s006_gateway_media_recovery/code/probe/gateway_core.py [H]
docs/archive/spikes/s006_gateway_media_recovery/code/probe/run_agent_client.py [H]
docs/archive/spikes/s006_gateway_media_recovery/code/probe/run_gateway_server.py [H]
docs/archive/spikes/s006_gateway_media_recovery/code/probe/run_verification.py [H]
docs/archive/spikes/s006_gateway_media_recovery/independent_review.md [H]
docs/archive/spikes/s006_gateway_media_recovery/report.md [H]
docs/archive/spikes/s007_profile_isolation/code/Dockerfile.isolation-browser [H]
docs/archive/spikes/s007_profile_isolation/code/Dockerfile.isolation-stream [H]
docs/archive/spikes/s007_profile_isolation/code/audio_analyzer.py [H]
docs/archive/spikes/s007_profile_isolation/code/browser_runner.py [H]
docs/archive/spikes/s007_profile_isolation/code/entry_browser.sh [H]
docs/archive/spikes/s007_profile_isolation/code/entry_stream.sh [H]
docs/archive/spikes/s007_profile_isolation/code/fixture/test_mitshm.c [H]
docs/archive/spikes/s007_profile_isolation/code/run_isolation_probe.py [H]
docs/archive/spikes/s007_profile_isolation/code/test_cross_ipc.py [H]
docs/archive/spikes/s007_profile_isolation/independent_review_final.md [H]
docs/archive/spikes/s007_profile_isolation/independent_review_r3.md [H]
docs/archive/spikes/s007_profile_isolation/independent_review_r4.md [H]
docs/archive/spikes/s007_profile_isolation/report.md [H]
docs/archive/spikes/s008_turn_generation_media/code/media_fixture/entrypoint_browser.sh [H]
docs/archive/spikes/s008_turn_generation_media/code/probe_work/cleanup.sh [H]
docs/archive/spikes/s008_turn_generation_media/code/probe_work/start_coturn.sh [H]
docs/archive/spikes/s008_turn_generation_media/code/stage2_adapter.py [H]
docs/archive/spikes/s008_turn_generation_media/code/stage2_adversarial_probe.py [H]
docs/archive/spikes/s008_turn_generation_media/code/stage2_containers.sh [H]
docs/archive/spikes/s008_turn_generation_media/code/stage2_media_restart_probe.py [H]
docs/archive/spikes/s008_turn_generation_media/code/stage2_stream_entrypoint.sh [H]
docs/archive/spikes/s008_turn_generation_media/code/stage2_stream_runner.py [H]
docs/archive/spikes/s008_turn_generation_media/independent_review_failed.md [H]
docs/archive/spikes/s008_turn_generation_media/independent_review_final.md [H]
docs/archive/spikes/s008_turn_generation_media/independent_review_generation.md [H]
docs/archive/spikes/s008_turn_generation_media/independent_review_split.md [H]
docs/archive/spikes/s008_turn_generation_media/report.md [H]
docs/archive/spikes/s008_turn_generation_media/report_same_url.md [H]
docs/archive/spikes/s009_native_ime_input/code/entrypoint_browser.sh [H]
docs/archive/spikes/s009_native_ime_input/code/entrypoint_stream.sh [H]
docs/archive/spikes/s009_native_ime_input/code/extra_harness.py [H]
docs/archive/spikes/s009_native_ime_input/code/ime_native_probe.py [H]
docs/archive/spikes/s009_native_ime_input/code/investigate_compositionend.py [H]
docs/archive/spikes/s009_native_ime_input/code/start_containers.sh [H]
docs/archive/spikes/s009_native_ime_input/code/stop_containers.sh [H]
docs/archive/spikes/s009_native_ime_input/code/test_blank_cdp.py [H]
docs/archive/spikes/s009_native_ime_input/code/verify_extra_harness.py [H]
docs/archive/spikes/s009_native_ime_input/independent_review.md [H]
docs/archive/spikes/s009_native_ime_input/report.md [H]
docs/archive/spikes/s010_cloakbrowser_exit_observation/code/probe.py [H]
docs/archive/spikes/s010_cloakbrowser_exit_observation/report.md [H]
docs/archive/tasks/t001_v2_runtime_validation/handoff.json [H]
docs/archive/tasks/t001_v2_runtime_validation/note.md [R]
docs/archive/tasks/t001_v2_runtime_validation/review_code.md [H]
docs/archive/tasks/t001_v2_runtime_validation/review_test.md [H]
docs/archive/tasks/t001_v2_runtime_validation/scope_adjustment.md [R]
docs/archive/tasks/t001_v2_runtime_validation/task.md [R]
docs/archive/tasks/t001_v2_runtime_validation/validation_matrix.md [R]
docs/archive/tasks/t002_v2_backend_foundation/handoff.json [H]
docs/archive/tasks/t002_v2_backend_foundation/note.md [R]
docs/archive/tasks/t002_v2_backend_foundation/review_code.md [H]
docs/archive/tasks/t002_v2_backend_foundation/review_test.md [H]
docs/archive/tasks/t002_v2_backend_foundation/task.md [R]
docs/archive/tasks/t003_v2_browser_runtime/handoff.json [H]
docs/archive/tasks/t003_v2_browser_runtime/note.md [R]
docs/archive/tasks/t003_v2_browser_runtime/review_code.md [H]
docs/archive/tasks/t003_v2_browser_runtime/review_test.md [H]
docs/archive/tasks/t003_v2_browser_runtime/task.md [R]
docs/archive/tasks/t004_v2_stream_runtime/handoff.json [H]
docs/archive/tasks/t004_v2_stream_runtime/note.md [R]
docs/archive/tasks/t004_v2_stream_runtime/review_code.md [H]
docs/archive/tasks/t004_v2_stream_runtime/review_test.md [H]
docs/archive/tasks/t004_v2_stream_runtime/task.md [R]
docs/archive/tasks/t005_v2_supervisor/handoff.json [H]
docs/archive/tasks/t005_v2_supervisor/note.md [R]
docs/archive/tasks/t005_v2_supervisor/review_code.md [H]
docs/archive/tasks/t005_v2_supervisor/review_test.md [H]
docs/archive/tasks/t005_v2_supervisor/task.md [R]
docs/archive/tasks/t006_v2_gateway_auth_rtc/handoff.json [H]
docs/archive/tasks/t006_v2_gateway_auth_rtc/note.md [R]
docs/archive/tasks/t006_v2_gateway_auth_rtc/review_code.md [H]
docs/archive/tasks/t006_v2_gateway_auth_rtc/review_test.md [H]
docs/archive/tasks/t006_v2_gateway_auth_rtc/task.md [R]
docs/archive/tasks/t007_v2_frontend_sessions/handoff.json [H]
docs/archive/tasks/t007_v2_frontend_sessions/note.md [R]
docs/archive/tasks/t007_v2_frontend_sessions/review_code.md [H]
docs/archive/tasks/t007_v2_frontend_sessions/review_test.md [H]
docs/archive/tasks/t007_v2_frontend_sessions/task.md [R]
docs/archive/tasks_index.json [S]
docs/blueprint/architecture.md [R]
docs/blueprint/browser_runtime.md [R]
docs/blueprint/decisions.md [R]
docs/blueprint/frontend.md [R]
docs/blueprint/gateway.md [R]
docs/blueprint/persistence.md [R]
docs/blueprint/security.md [R]
docs/blueprint/stream_runtime.md [R]
docs/blueprint/supervisor.md [R]
docs/blueprint/testing.md [R]
docs/findings/d001_v2_validation_baseline.md [R]
docs/findings/d002_cdp_uds_download_recovery.md [R]
docs/findings/d003_selkies_ice_restart_gap.md [R]
docs/findings/d004_docker_shareable_ipc_contract.md [R]
docs/findings/d005_encoded_fps_is_not_motion.md [R]
docs/findings/d006_runtime_event_recovery_checkpoint.md [R]
docs/findings/d007_multi_viewer_media_identity.md [R]
docs/findings/d008_gateway_process_media_recovery.md [R]
docs/findings/d009_turn_hmac_relay_transport.md [R]
docs/findings/d010_ice_generation_continuity.md [R]
docs/findings/d011_profile_ipc_audio_boundary.md [R]
docs/findings/d012_turn_generation_media_commit.md [R]
docs/findings/d013_capture_visibility_arbiter.md [R]
docs/findings/d014_native_ime_commit_path.md [R]
docs/findings/d015_sql_error_log_boundary.md [R]
docs/findings/d016_sdk_owner_lifecycle_boundary.md [R]
docs/findings/d017_native_xkb_named_spares.md [R]
docs/findings/d018_selkies_native_peer_entry.md [R]
docs/findings/d019_turn_loopback_mapping.md [R]
docs/findings/d020_orbstack_bridge_reachability.md [R]
docs/findings/d021_selkies_ice_restart_commit_is_async.md [R]
docs/findings/d022_selkies_rtc_config_url_contract.md [R]
docs/findings/d023_headless_chrome_visibility_static.md [R]
docs/findings/d024_selkies_token_secure_mode.md [R]
docs/guides/browser_runtime_validation.md [R]
docs/guides/stream_runtime_validation.md [R]
docs/guides/supervisor_validation.md [R]
docs/handoff.md [R]
docs/pending/todo/p001_supervisor_recovery_tick_complexity.md [R]
docs/pending/todo/p005_t006_review_minors.md [R]
docs/pending/todo/p006_browser_runtime_agent_secret_mount.md [R]
docs/pending/todo/p007_frontend_i18n_residue.md [R]
docs/pending/todo/p008_stream_agent_selkies_resume.md [R]
docs/pending/todo/p009_e2e_multi_viewer_fixed_sleep.md [R]
docs/pending/todo/p010_frontend_build_selkies_vendor_wiring.md [R]
docs/pending/todo/p011_t007_test_minor_followups.md [R]
docs/pending/todo/p012_stream_tokens_eviction_close_race.md [R]
docs/pending/todo/p013_ac001_static_frames_flake.md [R]
docs/reviews/review_local_benchmark_20261027/review_benchmark.md [S]
docs/reviews/review_v2_scope_20261027/review_disposition.md [R]
docs/reviews/review_v2_scope_20261027/review_scope_initial.md [S]
docs/reviews/review_v2_scope_20261027/review_scope_revised.md [R]
docs/reviews/review_v2_scope_20261027/review_traceability.md [R]
docs/specs/access_control.md [R]
docs/specs/browser_isolation.md [R]
docs/specs/chrome_external_tabs.md [R100→docs/archive/specs/chrome_external_tabs.md]
docs/specs/profile_management.md [R]
docs/specs/runtime_lifecycle.md [R]
docs/specs/runtime_persistence.md [R]
docs/specs/storage_and_artifacts.md [R]
docs/specs/v2_runtime_validation.md [R]
docs/specs/webrtc_remote_display.md [R]
docs/specs_index.md [R]
docs/tasks/t001_v2_runtime_validation/task.md [D]（删除；已归档到 docs/archive/tasks/t001_v2_runtime_validation/task.md）
docs/tasks/t008_v2_artifacts_automation/note.md [S]
docs/tasks/t008_v2_artifacts_automation/task.md [R]
docs/tasks/t009_v2_full_acceptance/note.md [S]
docs/tasks/t009_v2_full_acceptance/task.md [R]
docs/tasks/t010_v2_data_migration/note.md [S]（R093 检测自 t001 note，实际为 backlog 模板）
docs/tasks/t010_v2_data_migration/task.md [R]
docs/tasks/t011_v2_remove_legacy/note.md [S]
docs/tasks/t011_v2_remove_legacy/task.md [R]
docs/tasks/t012_v2_docker_release/note.md [S]
docs/tasks/t012_v2_docker_release/task.md [R]
docs/tasks/t013_v2_profile_copy_reset/note.md [S]
docs/tasks/t013_v2_profile_copy_reset/task.md [R]
docs/tasks/t014_v2_clipboard_input/note.md [S]
docs/tasks/t014_v2_clipboard_input/task.md [R]
docs/tasks_index.json [R]
docs/v2_architecture_plan.md [S]（豁免/修订/第3/12/13/15章相关段）
```

## Appendix B：未审/未执行缺口（必须在结论中保留）

1. **未运行**任何单元/集成/E2E/构建/Docker/Chrome/网络；不能把仓库内 PASS 记录当本路结果。
2. **未逐行**阅读约 136 个测试正文（用例名/关键断言已审），未逐行阅读 archive spikes 的 ~120 个历史源文件、t001–t007 review_code/review_test 全文、`package-lock` 每个包内容、OpenAPI 每个字段。
3. **未验证** Docker 内核规则实际生效、真实 Stream 公网 egress 负例、真实 Gateway 503 stop、伪造事件写入、lifecycle 收敛、删除后事件保留；这些是静态推断/调用链证据。
4. 公开网络、原生 Linux x86_64 继续 `NOT_RUN / USER_WAIVED`，未计 PASS；容量/P95/8h/1000 次输入、真实 Compose/迁移/旧链路删除均在阶段外。

## Appendix C：问题计数

Critical 0；High 2（SEC-1、COR-9）；Medium 14（SEC-2/3、COR-1/2/3/4/6/10/11、CT-1/5/6、PERF-1/2）；Low 30（SEC-4、COR-5/7/8/12、CT-2/3/7/8/9、PERF-3/4/5、ARCH-1/2、ROB-1/2/3/5/6、TEST-3/4/5/6/7/8/10、DOC-3/6/7）；Info 9（SEC-5/6、CT-4、ARCH-3/4/5、ROB-4、TEST-9、DOC-8）。相同根因已合并：SEC-1/DOC-2/TEST-1；SEC-2/ROB-3/TEST-2；CT-1/DOC-1；CT-5/DOC-4；CT-6/DOC-5；COR-6/TEST-6；COR-10/TEST-5；COR-3/TEST-4；COR-2/TEST-3；COR-5/TEST-7；COR-9/TEST-8；COR-11/TEST-10。
