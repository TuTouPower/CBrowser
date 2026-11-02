# bundle_local_backend_supervisor

## responsibilities

- Supervisor 进程（runner/__main__）：持 CoordinatorLock 独占 data root，装配 DockerAdapter、PortAllocator、EventForwarder、SupervisorCore、RecoveryCoordinator、ResourceMonitor 与 FastAPI 控制面，是宿主机唯一 Docker Socket 持有人（blueprint 声明，代码结构与之一致）。
- 双容器生命周期（core.start_profile/stop_profile）：按 Profile 创建 Browser/Stream 容器对、专属网络与 UDP mux 端口；启动前绑定 API 实例、报告 observed 状态；停止时先断开观看者、再拆容器、释放端口，并用 OperationJournal 做操作级幂等。
- 启动对账（core.scan_and_reconcile_existing + runner 后台循环）：以 Docker 标签 + API 持久化意愿为准恢复会话、清理孤儿、识别未受网络策略保护的沙箱并在 60 秒宽限后拆除。
- 恢复协调（recovery_coordinator + recovery_rules 纯函数）：异常退出按 2/10/30 秒退避重试、失败 4 次后由 API 侧 restart_blocked 阻断；正常退出与 stopped 意愿永不重启；重试前重读 API 权威状态防陈旧重试。
- 网络策略（network_policy + startup_gate + docker_adapter 的 policy helper）：在容器独立 netns 内用 iptables-restore 原子安装 IPv4/IPv6 fail-closed 规则；运行时入口被 startup_gate 拦截，策略就绪后才写 ready.json 放行 entrypoint。
- 事件与产物转发（event_forwarder、core.consume_disk_events、artifact_forwarder）：运行事件先落盘 spool 再投递 API（event_id 去重、失败隔离到 quarantine）；下载完成事件以持久化 processed 集合做至少一次投递。
- 资源监管（resource_monitor + resource_policy）：线程外采集 Docker stats 与宿主 /proc/stat，按容器配额/宿主压力滞回决策 FPS 上限，经 GatewayControlClient 下发 quota。
- 凭证与文件（agent_credentials、selkies_tokens、gateway_client、file_storage、path_validator）：HMAC 派生实例级 Agent token、随机 Selkies master/controller token、0600 原子写、路径穿越与符号链接逃逸校验、保留 profile_id 黑名单。

## interfaces

- 控制面 HTTP（control_server，Bearer token ≥32 字节、hmac.compare_digest 校验）：GET /supervisor/v1/health、POST /profiles/start|stop|reset-blocked、GET /profiles/{id}/status、GET /profiles/{id}/resources、WS /profiles/{id}/cdp（UDS 代理）。请求/响应模型在 protocol.py，与 schemas/runtime/supervisor_protocol.json 逐字段核对一致（端口范围 30000-30991、状态枚举、必填字段均吻合）。
- 对 API 的内部 RPC（httpx，Bearer token 文件）：GET profiles/{id}/versions/{v}、GET/POST runtimes/bind|observed、PATCH desired-state、POST runtimes/events、POST artifacts/downloads。
- 对 Gateway 的控制 RPC（gateway_client）：disconnect/quota/visibility，profile_id 经 urllib quote 转义，实例围栏以 runtime_instance_id 传递。
- Docker Engine API（docker_adapter）：容器/网络的创建、检查、拆除全部以 com.cbrowser.* 标签做所有权校验后才动手。
- 文件协议：snapshot.json（配置快照，挂入 Browser 容器）、ready.json（策略就绪标记）、runtime-events 磁盘日志、spool/quarantine 目录、control/ 下的 event_cursors.json、download_cursors.json 与 operations/ 日志。

## dependencies

- cbrowser.domain.models（ProfileConfig、ConfigVersionSnapshot、RuntimeEventReportRequest）与 cbrowser.domain.runtime_policy（AUTO_RETRY_DELAYS=(2,10,30)、BLOCK_AFTER_RUNTIME_FAILURES=4）——均在本单元外，仅按调用点核对。
- cbrowser.runtime_agent.protocol（HealthResponse、RuntimeEventRecord、DownloadEventRecord）、cbrowser.secret_files.read_secret_file、cbrowser.gateway.endpoint.GatewayEndpoint。
- 第三方：docker、httpx、fastapi、uvicorn、websockets、pydantic。

## flows

- 启动：API 意愿校验（desired=running 且未 blocked）→ 写 snapshot → API bind 实例 → 分配端口 → 建网络并接入 gateway/coturn 基础设施 → 起 Browser 容器（gated entrypoint）→ 等待 runner_info/套接字就绪 → 写 Agent secret 与 Selkies 凭证（0600）→ 起 Stream 容器 → 两个容器分别经 policy helper 安装网络策略并写 ready.json 放行 → 向 Gateway 确认注册 → 报告 observed=running。
- 停止：全局锁+Profile 锁 → OperationJournal.begin 幂等检查 → 报告 stopping → Gateway disconnect_viewers（2 秒超时、尽力而为）→ teardown 容器与网络 → 无论成败释放端口并清会话 → 报告 stopped → journal complete。
- 对账：周期扫描带前缀标签的容器 → 与 API runtime 意愿/实例围栏比对 → 恢复会话（从 Stream 容器 PortBindings 还原 UDP 端口）或拆除（意愿 stopped、API 404、策略未就绪超宽限）。
- 恢复：tick 分类异常退出（Agent 健康确认优先于 Docker 合成退出）→ 按持久化 failure_count/updated_at 计算剩余退避 → 独立 task 睡眠后重验意愿/事件代次/失败计数 → 清理残对 → 以绑定 config_version 重新 start_profile。
- 事件：Browser Agent 写磁盘日志 → consume_disk_events 按 (mtime_ns, name) 游标校验并 emit → EventForwarder 先 spool 落盘再 POST API，DELIVERED 后删 spool，REJECTED/不可读进 quarantine。

## constraints

- 蓝图硬约束（docs/blueprint/architecture.md）：Supervisor 唯一持有 Docker Socket、严禁读写 SQLite、浏览器容器 restart policy 固定 no、CDP 仅回环且必须经鉴权代理、运行容器严禁挂载 docker.sock——代码核对未见违背（本单元无任何 SQLite/数据库引用）。
- 镜像必须不可变摘要（sha256: 或 @sha256:），Browser/Stream/策略 helper 三处均强制（docker_adapter 构造器与 _prepare_policy_gate）。
- 路径围栏：所有挂载源经 PathValidator 解析并校验在 data root 与该 Profile 目录内；secret 目录位于 runtime/.secrets 且不进 Browser 挂载。
- 端口池严格 [30000, 30991]（PortAllocator 与 protocol schema、network_policy 三处一致）。
- 静态审阅：未运行测试/构建/容器；下述结论均为源码与契约证据，运行期行为（如 iptables 规则在 OrbStack 内的实际生效）未实测。

## decisions

- 实例围栏优先于一切自动动作：API 的 runtime_instance_id 与容器标签不一致时只保留现场不拆除（scan/recovery 多处一致实现）。
- 网络策略与业务进程解耦：业务容器以 gated entrypoint 启动，策略由 root+NET_ADMIN 的一次性 helper 在同一 netns 安装，就绪标记按实例+角色校验后才 exec 真正 entrypoint。
- 幂等三层：OperationJournal（命令级）、EventForwarder spool + API event_id（事件级）、PortAllocator.allocate/restore 幂等（资源级）。
- 失败关闭取向：配置快照缺失/几何非法、凭证文件权限非 0600、网络所有权不符、helper 所有权不符均抛错中止而非降级运行。
- stop_profile 持有全局锁串行化所有停止操作（core.py stop_profile 同时取 _global_lock 与 Profile 锁），换取 journal 与端口释放的简单一致性；start 不取全局锁。

## evidence

- core.py:641-1261 start/stop/terminal observation 全链与 control_server.py:86-210 的 RPC 映射逐行核对
- docker_adapter.py:146-207 策略 helper 的 cap_drop=ALL + NET_ADMIN + no-new-privileges 与 _runtime_policy_ready 的 ready.json 精确比对
- network_policy.py:136-254 IPv4/IPv6 规则渲染顺序（allowlist → 私有段 DROP → 非 relay-only 才最终 ACCEPT）与文件头契约注释逐项对照
- protocol.py 与 schemas/runtime/supervisor_protocol.json 逐字段比对：StartProfileRequest/Response、StopProfileRequest/Response、ResetBlocked、ProfileRuntimeStatus 一致
- domain/runtime_policy.py（单元外核对）：AUTO_RETRY_DELAYS=(2.0,10.0,30.0)、BLOCK_AFTER_RUNTIME_FAILURES=4，与 recovery_rules.retry_delay_for_failure 的索引围栏（先 budget 检查后取延迟）核对安全
- path_validator.py:21-152 validate_profile_id 保留字黑名单与符号链接逐段检查；selkies_tokens.py:31-57 凭证文件 0600 与逐实例新文件名策略
- unit_plan.json 显示 supervisor 测试被分派至 tests_unit_supervisor_runtime（约 50 个 test_supervisor_*/test_recovery_*/test_network_policy_* 文件）、tests_e2e_supervisor、tests_integration_fixtures 三个兄弟单元
- tests view completed by dedicated follow-up review (viewfix_backend_supervisor_tests.json, reviewer e3d67f25-ec09-4cbb-83b7-7964b713979a): Read in full: tests/unit/test_supervisor_core.py, test_supervisor_recovery_coordinator.py, test_supervisor_startup_recovery.py, test_runtime_coordinator_stop_paths.py, test_supervisor_event_delivery.py, tests/e2e/test_supervisor_core_e2e.py, test_supervisor_offline_recovery_e2e.py. The long tail (network policy, port recovery, stop fence/teardown, operation journal, reconcile fences, resource faul

## uncertainties

- artifact_forwarder 翻译出的宿主路径最终是否被 API 侧再次做包含性校验，取决于 backend_runtime_adapters/backend_api_auth 单元的 artifact_service，本单元内无法确认，故 f_backend_supervisor_02 标 suspected。
- gateway_client.py 中 token 读取代码经工具回显时被脱敏打码，仅能确认其调用 read_secret_file（label=Gateway control token、minimum_bytes=32）并以 SecretStr 保存，未逐字核对其异常分支。
- supervisor 专用 blueprint（docs/blueprint/supervisor.md）不在本单元 context_files 内，文档视角仅以 architecture.md、AGENTS.md 与模块 docstring 为据；模块 docstring 中的 AC 编号与行为描述未见与实现冲突。
- tests 视角为 partial：未读取兄弟测试单元，无法判断断言是否存在恒真/弱化模式。

## Findings

- [Medium][85] src/backend/cbrowser/supervisor/core.py:345-381 — 对账循环中单个 Profile 的异常会中断全部 Profile 的恢复，且在启动阶段直接使 Supervisor 退出
  - ID: f_backend_supervisor_01; verification: static
  - Evidence: scan_and_reconcile_existing 的 per-profile 循环体内无 try/except 隔离：gateway_control 为 None 时 raise RuntimeError（349 行）、Stream 容器缺 UDP 映射时 raise DockerSandboxError（377-381 行）、ports.restore 冲突时抛 ValueError（377 行调用 PortAllocator.restore）; runner.serve_supervisor 在创建控制面之前先 await core.scan_and_reconcile_existing()（runner.py serve_supervisor 开头），异常经 run_supervisor 的 finally 关闭全部客户端后向上传播，进程退出; 后台循环中该异常被 runner 的泛 catch 记录为 Reconciliation failed 后每轮重试，排在故障 Profile 之后的 Profile 永远得不到会话恢复
  - Impact: 一个由旧版本创建、HostConfig 无 UDP PortBindings 的残留 Stream 容器（或一次端口恢复冲突）即可让 Supervisor 每次启动都在对账阶段崩溃，或在运行时长期阻断其余健康 Profile 的会话还原与孤儿清理。
  - Fix: 在 scan_and_reconcile_existing 的 per-profile 循环体外包一层异常隔离：记录该 Profile 的对账失败并 continue；仅把 raise 保留给全局性错误（如 Docker 不可达）。同时考虑启动阶段对账失败时仍先拉起控制面再后台重试。

- [Medium][65] src/backend/cbrowser/supervisor/artifact_forwarder.py:20-27 — 下载产物路径翻译不做包含性校验，事件文件可构造逃出 Profile 下载目录的宿主路径
  - ID: f_backend_supervisor_02; verification: suspected
  - Evidence: translate_download_path 仅做前缀剥离后 Path(data_root)/artifacts/{profile_id}/downloads/{relative} 拼接，relative 中的 ../ 不被规范化或拒绝，profile_id 直接取事件内容字段; 上游模型 DownloadEventRecord（runtime_agent/protocol.py:72-87，单元外核对）对 download_path 无 pattern 约束，profile_id 的 pattern 允许纯点号（如 ".."); forward_pending 只校验事件文件位于 events_root 下（artifact_forwarder.py:118-121），payload 的 path 与 profile_id 均取自事件文件内容（139-143 行）；而 events 目录以 rw 挂载进 Browser 容器（volume_spec.browser_volumes），与被沙箱化的浏览器进程共享
  - Impact: 被攻陷或异常的 Browser 容器内进程可伪造下载完成事件，使 Supervisor 向 API 登记指向其他 Profile 目录乃至 data root 之外的宿主路径的产物记录；是否最终落库取决于 API 侧是否复检（不在本单元内，待跨单元确认）。
  - Fix: 在 translate_download_path 中对拼接结果做 resolve + relative_to(artifacts/{profile_id}/downloads) 校验，越界即拒绝并隔离该事件；同时以事件文件所在目录名（而非事件内容）为准校验 event.profile_id 一致性。

- [Low][80] src/backend/cbrowser/supervisor/control_server.py:88-92 — 内部 API URL 直接拼接未转义的 profile_id，与 gateway_client 的 quote 做法不一致
  - ID: f_backend_supervisor_03; verification: static
  - Evidence: start_profile 用 f-string 把 req.profile_id 拼入 /api/v1/internal/supervisor/profiles/{profile_id}/versions/{version} 路径，未做 URL 转义；profile_id 在 protocol 层仅约束长度 1-128; core.py 的 bind 与 observed 上报同样以 ?profile_id={profile_id} 拼 query（core.py start_profile 与 _report_observed），含 & 或 # 的 id 可注入额外 query 参数; 同包 gateway_client._path 对 profile_id 使用 quote(profile_id, safe='')，说明项目内既定做法是转义；PathValidator.validate_profile_id 的文件系统校验发生在这次 HTTP 拉取之后
  - Impact: 调用方为内部可信的 Runtime Coordinator，实际风险有限；但异常 profile_id 可改变请求路径/查询语义，拉取到错误配置或使围栏校验基于错误资源，且与同包既定转义规范漂移。
  - Fix: 对所有拼入 URL 的 profile_id/instance_id 统一 quote(..., safe='')，或在 control_server 入口先以 validate_profile_id 拒绝非法标识再拉取配置。

- [Low][60] src/backend/cbrowser/supervisor/resource_monitor.py:64-80 — 资源采集的异常过滤漏掉 ValueError/TypeError，一个容器的异常 HostConfig 可拖垮全部 Profile 的配额下发
  - ID: f_backend_supervisor_04; verification: suspected
  - Evidence: _collect 中 containers.get、container_cpu_limit、container.stats 在同一 try 内，但 except 仅捕获 (DockerException, OSError); resource_policy.container_cpu_limit（resource_policy.py:11-30）对 CpusetCpus 做 int(value) 解析、对 HostConfig 数值直接比较，畸形 attrs 会抛 ValueError/TypeError; sample() 经 asyncio.to_thread 调用 _collect，异常穿透到 runner.resource_loop 的泛 catch，仅记录 Resource monitoring failed，该窗口所有 Profile 的 quota 决策与下发全部跳过且每 5 秒重复
  - Impact: 单个容器返回非预期 HostConfig（如 CpusetCpus 含空段）时，资源监管整体失效而非单 Profile 隔离失败，与该文件头注明的 fault isolation 目标相悖。
  - Fix: 在 _collect 的 per-target try 中补捕 (ValueError, TypeError, KeyError)，或在 container_cpu_limit 内对 CpusetCpus 解析做防御并返回已识别的部分限制。

- [Low][70] src/backend/cbrowser/supervisor/core.py:842 — 含完整 ProfileConfig 的 snapshot.json 以 0644 写入，与本单元对凭证文件一律 0600 的口径不一致
  - ID: f_backend_supervisor_05; verification: static
  - Evidence: core.start_profile 将 ConfigVersionSnapshot（内嵌 config.model_dump() 全量）以 atomic_write_text(mode=0o644) 写到 runtime/snapshot.json；docker_adapter.start_browser_container 复制时同样 0o644（docker_adapter.py:646）; ProfileConfig.proxy 是自由字符串字段（domain/models.py:57，单元外核对），代理 URL 常内嵌 user:password 凭证; 同单元对 Agent secret 与 Selkies 凭证强制 0600 并在 start_stream_container 中显式校验权限位，event_cursors/download_cursors/OperationJournal 也都是 0600；缓解因素是 runtime 目录在 manage_ownership 时为 0750
  - Impact: 开启所有权管理时风险被目录权限大幅缓解；未开启（宿主直跑开发模式，目录回退 0777）时，同机其他用户可读到含代理凭证的完整配置快照。
  - Fix: snapshot.json 改为 0600 写入（容器内 Agent 以属主 uid 1000 读取，与 secret 文件同一模型），或在文档中明确其按公开配置对待并禁止 proxy 内嵌凭证。

- [Low][70] src/backend/cbrowser/supervisor/docker_adapter.py:263-286 — 引擎缓存与未托管所有权回退路径把目录置为 0777 全局可写
  - ID: f_backend_supervisor_06; verification: static
  - Evidence: _initialize_cache 对 engine_cache、geoip_cache 直接 chmod(0o777)，内嵌初始化脚本进一步把缓存树下所有目录 chmod(0o777)；该缓存存放随后被 Browser 容器执行的 CloakBrowser 引擎二进制; _secure_directory 在 manage_ownership=False 时把 Profile 数据目录 chmod 为 0o777/0o1777（docker_adapter.py:378-390），docstring 自述为 legacy world mode 回退; 蓝图（architecture.md 7.1）定案部署为单机个人 Mac，宿主多用户威胁有限，故定级 Low
  - Impact: 同机任意本地进程可篡改引擎缓存二进制或 Profile 数据，下一次容器启动即以被篡改内容运行；单用户部署下主要风险来自同机其他低权限进程/应用。
  - Fix: 缓存目录改为 0755+属主写入（初始化 helper 以 root 运行时显式 chown 回 runtime uid），并把 0777 回退至少收紧为 0750/0700 后在文档中声明开发模式的权限代价。

- [Low][65] src/backend/cbrowser/supervisor/control_server.py:238-247 — CDP WebSocket 在校验 Bearer token 之前先 accept 连接
  - ID: f_backend_supervisor_07; verification: static
  - Evidence: cdp_proxy 第一行即 await websocket.accept()，之后才读取 Authorization 头并用 hmac.compare_digest 校验，失败关 4401; 同文件 HTTP 端点均以 Depends(verify_token) 在处理前拒绝 401，未认证请求不进入业务逻辑; accept 之前未发生任何数据代理，故无数据泄漏；问题仅在于未认证客户端也能完成 WebSocket 升级握手
  - Impact: 未认证连接可完成升级并短暂占用连接资源，与 HTTP 面的前置拒绝口径不一致；在仅回环/内网暴露的部署下影响较小。
  - Fix: 在 accept 前先读 websocket.headers 做同样的 token 校验，失败时以 close(code=4401) 直接拒绝（Starlette 允许 accept 前关闭），通过后再 accept 并继续会话检查。

- [Low][70] src/backend/cbrowser/supervisor/container_spec.py:44-82 — stream_labels 未像 browser_labels 那样把 config_version 强转 str，存在向 Docker 传入非字符串标签值的潜在路径
  - ID: f_backend_supervisor_08; verification: static
  - Evidence: browser_labels 用 str(config_version) 且返回 dict[str, str]；stream_labels 直接放入原值且标注 dict[str, Any]; 当前唯一调用点传的是从 Browser 容器标签读回的字符串（docker_adapter.start_stream_container），故现行路径不触发；但函数签名接受 Any，一旦有调用方像 Browser 路径那样传 snapshot 的 int version，docker-py 会收到非字符串标签值
  - Impact: 潜在契约漂移：同类函数行为不一致，后续调用方按 browser_labels 的先例传 int 时会在容器创建期才失败。
  - Fix: stream_labels 内同样 str(config_version) 并把返回类型收紧为 dict[str, str]。

- [Low][70] src/backend/cbrowser/supervisor/control_server.py:172-210 — status 端点在 try 保护范围外直接下标访问 API 响应字段，畸形 200 响应变成未处理的 500
  - ID: f_backend_supervisor_09; verification: static
  - Evidence: get_status 的 try 仅包住 api.get 与 raise_for_status/json 解析的调用段，其后 runtime["runtime_instance_id"]、runtime["desired_state"] 等下标访问位于保护之外; 同端点对传输失败映射 503 的意图明确，但字段缺失时 KeyError 会穿透为 FastAPI 默认 500，与该映射口径不一致
  - Impact: API 返回结构漂移或旧版本响应时，状态查询以未分类 500 失败，调用方（Runtime Coordinator）难以区分“状态不可用”与“服务端 bug”。
  - Fix: 把字段读取纳入同一 try 并映射 503，或先以 ProfileRuntimeStatus 兼容的 pydantic 模型校验 API 响应再取值。

- [Low][60] src/backend/cbrowser/supervisor/runner.py:82-87 — 启动装配以裸 read_text 读取 Supervisor→API token，绕过本单元统一的 secret 文件校验
  - ID: f_backend_supervisor_10; verification: static
  - Evidence: run_supervisor 用 token_file.read_text().strip() 直接拼 Authorization 头种子共享 api_client，无最小长度/格式校验; 对照：control_server 对控制 token 强制 read_secret_file(minimum_bytes=32)（control_server.py:45-56），gateway_client 对 Gateway token 同样要求 ≥32 字节，EventForwarder/Core 的 _get_bearer_token 也走 read_secret_file; 若 token 文件被误配为弱值或错文件，启动不报错，表现为后续所有 API 调用 401 的远端症状
  - Impact: 凭证强度与装配错误在启动期不可见，排障成本高；与本单元其他三处 token 读取口径漂移。
  - Fix: runner 改用 read_secret_file(token_file, label=..., minimum_bytes=32) 读取并在失败时启动即报错；共享 client 的头与逐请求 _auth_headers 保持单一来源。

- [Info][65] src/backend/cbrowser/supervisor/operation_journal.py:23-31 — OperationJournal.lookup 对损坏的日志文件不做防护，异常会穿透停止路径
  - ID: f_backend_supervisor_11; verification: static
  - Evidence: lookup 直接 json.loads(path.read_text()) 并下标 record["request"]，无 OSError/ValueError/KeyError 防护; 同单元的 spool 与磁盘事件读取均对损坏文件做 quarantine 隔离（event_forwarder、core._quarantine_event_file），唯独操作日志没有对应处理; 写入走 atomic_write_text，正常运行下损坏概率低，故定级 Info
  - Impact: 日志文件被外部改动或磁盘损坏时，stop_profile 每次都会在 journal 阶段抛错（控制面映射 500），该 Profile 的停止操作被永久阻断而非降级执行。
  - Fix: lookup 捕获解析异常时把坏文件改名隔离并按无记录处理（或显式抛带 operation_id 上下文的错误），与 spool 的 quarantine 口径统一。

- [Info][80] src/backend/cbrowser/supervisor/metrics.py:30-44 — StageMetrics.snapshot 只重置上报时钟不重置计数，周期日志输出的是自启动以来累计值而非区间值
  - ID: f_backend_supervisor_12; verification: static
  - Evidence: record 只累加 count/total/max；snapshot 更新 _last_report 并返回全部累计统计，无任何清零; runner 后台循环以 should_report（60 秒）节流打印 Supervisor stage metrics，读感上像区间遥测，实际 max_ms 是历史最大值、count 是累计次数
  - Impact: 运维者会把累计值误读为最近一分钟的阶段耗时，掩盖新近出现的慢阶段或误报已恢复的问题。
  - Fix: snapshot 后清零各 StageStats（或同时输出累计与区间两组），并在日志字段名上区分 cumulative/interval。

- [Medium][90] tests/unit/test_supervisor_startup_recovery.py:122-271 — 四个防误报退出守卫测试只断言 emit_event 未被调用，而生产协调器根本不使用该通道，守卫失效时测试仍全绿
  - ID: f_backend_supervisor_13; verification: static
  - Evidence: 生产代码核对：src/backend/cbrowser/supervisor/recovery_coordinator.py 全文 grep emit_event 零命中，合成退出只经 report_terminal_observation 上报（220、398 行）; test_core_profile_lock_held_skips_exit_synthesis、test_native_exit_priority_prevents_synthetic_docker_exit、test_native_exit_priority_prevents_synthetic_missing_exit、test_docker_created_status_does_not_synthesize_exit 四个测试唯一的否定断言均为 mock_core.events.emit_event.call_count == 0，无一断言 report_terminal_observation 未被调用; mock_core fixture 中 report_terminal_observation 是无约束 AsyncMock（test_supervisor_recovery_coordinator.py 同型 fixture、startup_recovery fixture 第 51 行），守卫回归时 tick 会顺利调用它并继续，测试无感; 同文件正例 test_missing_runtime_reports_error_observation_once（63 行起）明确断言 report_terminal_observation 以 reason='missing_runtime' 被调用，反证合成退出的真实通道就是它而非 emit_event
  - Impact: 锁占用、原生退出优先、created 状态这三类防误报守卫若回归，协调器会为正在启动或健康的 Profile 合成 error 观察，触发不必要的拆除/重试，而这四个以守卫命名的测试仍全部通过——守卫实际处于无测试状态，且比没有测试更危险，因为它制造已覆盖的假象。
  - Fix: 在四个守卫测试中补上 mock_core.report_terminal_observation.assert_not_awaited()（与 emit_event 断言并列，双通道封锁）；后续新增合成退出路径时，守卫测试统一断言两条上报通道均未触发。

- [Medium][85] tests/unit/test_supervisor_reconcile_fences.py:14-62 — scan_and_reconcile_existing 的单 Profile 异常隔离无任何测试，单元最高优先级生产缺陷 f_backend_supervisor_01 没有回归网
  - ID: f_backend_supervisor_14; verification: static
  - Evidence: core.py:345-381 的 per-profile 对账在 gateway_control 为 None、Stream 容器缺 UDP PortBindings、PortAllocator.restore 冲突时分别抛 RuntimeError/DockerSandboxError/ValueError 并中断整轮扫描（生产 finding f_backend_supervisor_01 的静态证据）; 对账测试全量清点：reconcile_fences 只测锁占用与策略未就绪不接纳；test_supervisor_recovery 测 API 错误时保留容器；unprotected_sandbox 测宽限拆除；normal_exit_observation 与 integration test_normal_exit_replay 测正常退出观察——每个 Profile 的容器记录均为良构，无一注入单 Profile 异常后断言其余 Profile 仍被恢复; e2e 恢复类用例（recovery/offline/startup_recovery）均以健康容器集重启 Supervisor；runner.serve_supervisor 在拉起控制面前先 await scan_and_reconcile_existing、异常即进程退出的启动期路径同样无覆盖
  - Impact: f_backend_supervisor_01 的故障模式（一个遗留容器使全部 Profile 的会话恢复长期停摆、启动期崩溃循环）没有任何自动化回归网：该缺陷被修复时无 pinning 用例可依，日后重构对账循环再次引入同类中断也不会被发现。
  - Fix: 新增双 Profile 对账用例：其一为缺 UDP PortBindings 的遗留 Stream 容器（或预置 restore 端口冲突），断言 scan_and_reconcile_existing 不向外抛错且另一 Profile 的会话被恢复、端口被正确还原；与 f_backend_supervisor_01 的隔离修复一并落地并作为其回归 pin。

- [Low][85] tests/unit/test_download_reconciler.py:84-137 — translate_download_path 的路径包含性没有任何负例测试，逃逸输入从未被驱动过
  - ID: f_backend_supervisor_15; verification: static
  - Evidence: artifact_forwarder.translate_download_path 仅做前缀剥离后 Path 拼接，无 resolve/relative_to 包含性校验，事件内容里的 ../ 相对路径与 '..' 型 profile_id 可逃出该 Profile 的 downloads 目录（生产 finding f_backend_supervisor_02，suspected）; tests/unit/test_download_reconciler.py 五个用例覆盖扫描补登、校验和事件、正向翻译加单次转发、旧事件不跳过、4xx 重试；唯一的翻译用例（84 行）只给良构的 /exchange/downloads/<guid> 路径; 对整个 tests/ 树 grep，未见以含 ../ 的 download_path 或 '..' 的 profile_id 驱动 translate_download_path/forward_pending 并断言拒绝或隔离的用例
  - Impact: 下载路径翻译这条安全边界只有正向覆盖：日后对 translate_download_path 的重构即使彻底打穿包含性也没有测试报警；f_backend_supervisor_02 修复时也没有现成的 pinning 负例可依，只能新写。
  - Fix: 在 test_download_reconciler.py 增加负例：事件的相对路径含 ../ 段、profile_id 为 '..' 或含分隔符时，forward_pending 拒绝或隔离该事件且不向 API 投稿任何指向 Profile 下载目录之外的宿主路径；与 f_backend_supervisor_02 的包含性修复一并落地。

## views

```json
{
  "contracts": {
    "reviewer": "f47a219f-40ea-44df-8c2f-c9d723656061",
    "status": "completed"
  },
  "correctness": {
    "reviewer": "f47a219f-40ea-44df-8c2f-c9d723656061",
    "status": "completed"
  },
  "design": {
    "reviewer": "f47a219f-40ea-44df-8c2f-c9d723656061",
    "status": "completed"
  },
  "documentation": {
    "reviewer": "f47a219f-40ea-44df-8c2f-c9d723656061",
    "status": "completed"
  },
  "performance": {
    "reviewer": "f47a219f-40ea-44df-8c2f-c9d723656061",
    "status": "completed"
  },
  "robustness": {
    "reviewer": "f47a219f-40ea-44df-8c2f-c9d723656061",
    "status": "completed"
  },
  "security": {
    "reviewer": "f47a219f-40ea-44df-8c2f-c9d723656061",
    "status": "completed"
  },
  "tests": {
    "status": "completed",
    "reviewer": "e3d67f25-ec09-4cbb-83b7-7964b713979a"
  }
}
```

## files_reviewed

```json
[
  "src/backend/cbrowser/supervisor/__init__.py",
  "src/backend/cbrowser/supervisor/__main__.py",
  "src/backend/cbrowser/supervisor/agent_credentials.py",
  "src/backend/cbrowser/supervisor/artifact_forwarder.py",
  "src/backend/cbrowser/supervisor/container_spec.py",
  "src/backend/cbrowser/supervisor/control_server.py",
  "src/backend/cbrowser/supervisor/coordinator_lock.py",
  "src/backend/cbrowser/supervisor/core.py",
  "src/backend/cbrowser/supervisor/docker_adapter.py",
  "src/backend/cbrowser/supervisor/event_forwarder.py",
  "src/backend/cbrowser/supervisor/file_storage.py",
  "src/backend/cbrowser/supervisor/gateway_client.py",
  "src/backend/cbrowser/supervisor/metrics.py",
  "src/backend/cbrowser/supervisor/network_policy.py",
  "src/backend/cbrowser/supervisor/network_spec.py",
  "src/backend/cbrowser/supervisor/operation_journal.py",
  "src/backend/cbrowser/supervisor/path_validator.py",
  "src/backend/cbrowser/supervisor/port_allocator.py",
  "src/backend/cbrowser/supervisor/protocol.py",
  "src/backend/cbrowser/supervisor/recovery_coordinator.py",
  "src/backend/cbrowser/supervisor/recovery_rules.py",
  "src/backend/cbrowser/supervisor/resource_monitor.py",
  "src/backend/cbrowser/supervisor/resource_policy.py",
  "src/backend/cbrowser/supervisor/runner.py",
  "src/backend/cbrowser/supervisor/selkies_tokens.py",
  "src/backend/cbrowser/supervisor/startup_gate.py",
  "src/backend/cbrowser/supervisor/volume_spec.py"
]
```
