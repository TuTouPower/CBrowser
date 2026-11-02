# bundle_local_backend_stream_gateway

## responsibilities

- gateway/（源码事实）：aiohttp 信令网关。维护 Stream Agent 动态注册表（HMAC 实例 token 校验 + API 绑定复核 + 心跳驱逐）、为每个 Viewer 建隔离信令隧道（Origin 白名单 + 会话 Cookie 经内部 API 授权后才升级 WebSocket）、提供 Supervisor 控制面（visibility/quota/disconnect，静态 Bearer + compare_digest），并驱动 TURN 凭证代次轮换与逐连接 ICE restart 编排。
- rtc_config/（源码事实）：按 coturn REST API 生成 HMAC-SHA1 短期凭证（username=<expiry>:<role>-<profile_id>），同一代次内为 client（浏览器，经公开 TURN URL）与 stream（Selkies，经 Agent 注册时上报的内网 TURN 主机/端口）分别签发，并给出轮换时序判定（生成间隔/重启提前量/过期）。
- stream_agent/（源码事实）：运行于 stream-runtime 容器内的守护进程。向 Gateway 出站注册并每 10s 心跳上报 Selkies 视频状态；把 Viewer 信令经回环 WebSocket 桥接至本机 Selkies（HELLO 时按需注入 controller_token、按 tab_id+resume_key 关联 SDK peer）；拦截/清洗客户端消息（SETTINGS 键过滤、禁用调参 verb）；执行 8/30 FPS 捕获仲裁与可见性暂停；通过给 Selkies 2.1.0 私有 ABI 打补丁的 GenerationIceTransport 实现同 PeerConnection 的代次化 ICE restart（含旧连接回收与写拒绝验证）；启动时做挂载边界检查（禁止 Docker socket/Profile 数据目录等）与 X11 keymap 刷新适配。
- 文档声明与源码的对应：docs/blueprint/architecture.md 声明 t006 已交付『认证信令 Gateway 与 TURN 凭证轮换』，与本单元源码实现一致；文档同时声明完整 v2 拓扑尚未全部交付（编排/入口切换属后续 task），本单元代码本身不构成整套部署证据。

## interfaces

- Gateway HTTP/WS 路由：GET /stream/agent/register（Agent 注册长连接）、GET /stream/{profile_id}/signal（Viewer 信令）、GET /gateway/v1/internal/profiles/{profile_id}/visibility、POST .../quota、POST .../disconnect（Supervisor 控制面）。
- Gateway -> API 内部 HTTP：GET /api/v1/internal/gateway/profiles/{id}/runtime、POST /api/v1/internal/gateway/viewer-authorize（Bearer token 文件鉴权，5s 超时，失败一律 fail-closed）。
- v2 wire 协议（protocol.py 与 schemas/stream/agent_protocol.json 一致）：GatewayTunnelEnvelope(open/msg/close)、GatewayControlEnvelope(register/rtc_config/ice_restart/ice_restart_answer/supervisor_quota/...)、ProtocolEnvelope(register/heartbeat/ice_restart_offer/ice_restart_committed/error)、GatewayRegisterResponse。
- Agent -> Selkies 回环：ws://127.0.0.1:{SELKIES_PORT}/api/webrtc/signaling，透传 Selkies 原生信令文本（HELLO 等）。
- RtcConfigService.generate_generation 输出 RtcGeneration：client_rtc_config（给浏览器）+ stream 凭证（build_stream_ice_servers/build_stream_rtc_config 给 Agent）。

## dependencies

- cbrowser.supervisor.agent_credentials.AgentCredentials（单元外 callee，Gateway 用其 verify 校验 Agent 的 HMAC-SHA256 实例 token）。
- cbrowser.secret_files.read_secret_file（单元外 callee，GatewayConfig 用其做密钥文件权限/长度校验）。
- aiohttp（Gateway 服务端、Agent 客户端）、httpx（Gateway->API）、pydantic（全链路模型校验）。
- Selkies 2.1.0 私有 ABI（selkies.webrtc/ice/input_handler 的私有属性与方法签名，ice_transport.py 与 x11_keymap.py 以版本守卫 fail-closed 适配）。
- coturn REST HMAC-SHA1 凭证约定（rtc_config/credential.py）；环境变量族 CBROWSER_* / SELKIES_*（两个 config 模块）。

## flows

- Agent 注册：WS 升级 -> 10s 内首包 REGISTER -> ProtocolEnvelope/AgentRegisterPayload 校验 -> AgentCredentials.verify(HMAC) -> API 复核 profile 当前绑定 instance -> 注册表替换旧会话（关闭旧 viewers 与旧 WS）-> 回 ACK -> 下发当前有效代次 RTC_CONFIG -> 进入消息泵（tunnel 转发带 profile/instance/session 三重身份校验 + viewer 归属校验；heartbeat 更新存活与视频状态；restart offer/commit/error 交 RotationCoordinator）。
- Viewer 接入：Origin 规范化白名单 -> cbrowser_session Cookie -> API viewer-authorize（cookie+origin+profile）-> Agent 在线检查 -> API observed_state 复核 -> WS 升级 -> 先下发 rtc_config 帧（含当前代次 client TURN 凭证）-> 向 Agent 发 tunnel open -> 双向透传（cbrowser ice_restart_answer 控制帧在 Gateway 截获，其余原样转发）。
- 凭证轮换：后台循环（<=1s）registry 心跳驱逐 + rotation.tick：到生成间隔生成下一代并向 Agent 推 RTC_CONFIG；到重启提前量对未迁移连接并发执行 restart 握手（Agent 造 offer -> Viewer answer -> Agent setRemoteDescription 并等真实 takeover commit，30s 后备超时）；全部连接迁移后才提交新代次；新连接直接使用 in-progress 代次并计入已迁移。
- ICE restart（Agent 侧）：Gateway ICE_RESTART（携带新代次 ice_servers）-> GenerationIceTransport.prepare_restart 在保留 UDP mux/端口范围/NAT 1-to-1 IP 的新 gatherer 上预收集候选 -> 同 PC 造 offer -> Gateway 转 Viewer -> answer 回来 setRemoteDescription -> start() 以旧远端凭证做竞态围栏 -> 新代次 completed 后关闭旧连接并验证其拒绝写入 -> ICE_RESTART_COMMITTED 回报 Gateway。
- 捕获仲裁：policy 后台 0.2s reconcile + 事件驱动调用，单锁串行：无可见 viewer 暂停捕获；恢复时先 set 8 FPS 再 resume 并请求 IDR；有输入/画面运动（damage 帧增量 >=6fps 估算）升 30 FPS，Supervisor quota 取 min 封顶。

## constraints

- Selkies 固定 2.1.0（webrtc 1.15.0 / ice 0.10.2），私有 ABI 不符即 fail-closed 拒绝启动（ice_transport.py、x11_keymap.py）。
- 固定媒体参数：video_streaming_mode 必须 False、min_fps=8、max_fps=30、depth=24、UDP mux 端口须在 [30000, 30991]（config.py 与 protocol.py 双处声明，口径不完全一致见 f_backend_stream_gateway_13）。
- 所有密钥/令牌必须来自外部文件且 >=32 字节（Gateway 侧经 read_secret_file 强制 0600 权限）；TURN secret 同样 >=32 字节。
- 信封硬上限：tunnel data 与 control payload 均 <=1MB；Agent 侧帧上限 6MB+64KB；注册首包 10s 超时；注册尝试按来源限流 20 次/60s。
- 部署基准（architecture.md 声明）：单机本地 Docker、同机 Chrome；公网 TURN 穿透与 Linux x86_64 验证被用户豁免（NOT_RUN / USER_WAIVED），不得据此宣称公网可达。

## decisions

- 凭证按 Profile 而非按 Viewer 签发：同一代次内所有 Viewer 共用 client TURN 凭证（见 f_backend_stream_gateway_08）。
- Agent 实例 token 为确定性 HMAC（token_for 对 (profile, instance) 恒定），无过期/随机数，依赖 API 绑定复核收敛重放窗口（见 f_backend_stream_gateway_07）。
- ICE restart 的提交以 Agent 报告真实 takeover 为准（ICE_RESTART_COMMITTED），而非 answer 已转发；Gateway 侧另有 30s 后备超时（Agent 侧等待上限 20s）。
- Viewer 关闭后 Agent 侧保留 Selkies 上游会话 10s resume grace（RESUME_GRACE_SECONDS），以 resume_key 恢复；Gateway 断开时走同一 detach 路径。
- Selkies 自身的 RTC 配置监视被禁用（mon_rtc_config 空转、monitoring_utils_used 清空），stream 侧 TURN 配置只许来自 Gateway 经 Agent 下发。
- 失败关闭取向一致：API 不可达时 Agent 注册与 Viewer 授权均拒绝；无有效 TURN 代次时注册/接入均拒绝（但拒绝路径的实现有缺陷，见 f_backend_stream_gateway_01/05）。

## evidence

- src/backend/cbrowser/gateway/server.py:283-486 Agent 注册全链（限流、HMAC 校验、API 绑定复核、替换旧会话、泵内三重身份校验）
- src/backend/cbrowser/gateway/server.py:496-670 Viewer 接入（Origin/Cookie/API 授权、rtc_config 首帧、tunnel open、控制帧截获）
- src/backend/cbrowser/gateway/rotation.py:206-434 轮换 tick、逐连接 restart 握手与代次提交
- src/backend/cbrowser/rtc_config/credential.py:11-25 与 service.py:44-97 TURN REST 凭证生成（client/stream 双角色）
- src/backend/cbrowser/stream_agent/agent.py:378-407 心跳循环；agent.py:1063-1135 restart offer/answer/commit 处理
- src/backend/cbrowser/stream_agent/ice_transport.py:317-520 GenerationIceTransport 的 prepare/start/commit 与旧凭证围栏
- src/backend/cbrowser/stream_agent/policy.py:524-560 客户端 verb 拦截与 SETTINGS 清洗；policy.py:366-520 捕获仲裁单控制器
- src/backend/cbrowser/stream_agent/boundary.py:18-71 启动挂载边界检查的禁止路径清单
- schemas/stream/agent_protocol.json 与 protocol.py 模型逐项对应（导出脚本生成，非手写漂移）
- tests view completed by dedicated follow-up review (viewfix_backend_stream_gateway_tests.json, reviewer 922d4438-5f1f-4ffb-b206-1fcf5a0b78bd): 已全量通读分配的 7 个单元测试文件（test_gateway_registry、test_gateway_rotation_guards、test_stream_agent_lifecycle、test_stream_ice_transport、test_stream_ice_security、test_rtc_config、test_gateway_config），并以兄弟单元 tests_unit_stream_api 与 tests_e2e_stream_frontend 的 findings/summary 为基线去重，再用全仓 grep 与定向阅读核对集成层（tests/integration/test_gateway_signaling.py）与 Docker probe 层（tests/fixtures/stream_probe/ice_restart_failure.py

## uncertainties

- aiohttp 服务端 WebSocketResponse 未显式设置 max_msg_size 时的默认上限取决于所用 aiohttp 版本内部实现，本轮静态审阅未运行验证（关系 f_backend_stream_gateway_17）。
- verify_selkies_abi_guard 中样例 RTCPeerConnection/RTCIceGatherer 实例化是否实际分配 UDP socket 等资源，取决于 Selkies SDK 内部实现（不在本仓），仅能按调用频率推断成本（关系 f_backend_stream_gateway_09）。
- runtime_instance_id 是否每次容器启动全局唯一由 Supervisor 单元决定，未在本单元核对；若 instance id 会复用，f_backend_stream_gateway_07 的重放窗口评估需上调。
- 本单元无测试文件；tests/unit/test_gateway_*、test_stream_*、test_rtc_config 等在 tests_unit_stream_api 单元内，其断言质量与覆盖未在本单元审阅。

## Findings

- [Medium][88] src/backend/cbrowser/gateway/server.py:538-558 — Viewer 接入在 WebSocket 已 prepare 后返回普通 503 Response，且 viewers 条目泄漏
  - ID: f_backend_stream_gateway_01; verification: static
  - Evidence: handle_viewer_signal 在 538-539 行已 web.WebSocketResponse() 并 await ws.prepare(request)，542 行已把 ViewerEntry 写入 viewers 字典; 550-558 行 get_effective_generation 抛 NoActiveGenerationError 时执行 return web.Response(status=503, ...)：对已 prepare 的连接再返回普通 Response，aiohttp 会在写回时抛 RuntimeError，客户端拿不到预期的 503 文本; 该异常分支没有 viewers.pop(conn_id)、没有关闭 ws、也没有通知 Agent 关闭 tunnel，与下方 578-613 行初始化失败路径的完整清理形成对比
  - Impact: TURN 代次恰好全部过期（正是该分支要处理的场景）时，Viewer 看到的是连接异常重置而非可重试的 503；同时 viewers 字典残留一个指向已死 ws 的条目，被 profile_connections() 计为活动连接，影响 RotationCoordinator 的迁移判定与 Supervisor disconnect 的遍历，直到进程重启才消失。
  - Fix: 把 get_effective_generation 调用前移到 ws.prepare 之前（与其它 503 检查同层）；若必须在 prepare 后处理，则改为关闭 ws（code=1013）并弹出 viewers 条目、向 Agent 发送 tunnel close 后 return ws。

- [Medium][90] src/backend/cbrowser/stream_agent/agent.py:378-407 — 心跳循环任一瞬时异常即整体退出，健康 Agent 会被 Gateway 误驱逐并断开全部 Viewer
  - ID: f_backend_stream_gateway_02; verification: static
  - Evidence: _heartbeat_loop 的 try 包住整个 while 循环（385 行），循环体调用 policy.selkies_video_state() 与 ws.send_str(); except Exception 只在 403-407 行记录日志后函数返回，没有按迭代捕获/重试；心跳任务此后永不恢复; Gateway 侧 registry 以 agent_heartbeat_timeout_sec（默认 30s）无心跳即驱逐 Agent 并关闭其全部 Viewer 会话（server.py:695-720）
  - Impact: Selkies 状态查询或单次发送的任何瞬时故障（如 SDK 状态对象短暂异常、WS 发送抖动）都会让心跳永久停止；约 30s 后 Gateway 把仍在正常推流的 Agent 判死，断开该 Profile 的全部观看连接，直到 Gateway WS 本身断开重连才恢复。
  - Fix: 把异常捕获下沉到循环迭代内：单次心跳失败只记录并在下一间隔重试；仅在 ws.closed 或 _running 为假时退出循环。

- [Medium][78] src/backend/cbrowser/stream_agent/ice_transport.py:427-512 — ICE restart 在 start() 失败后 restart_pending 永不复位，后续所有 restart 被永久拒绝
  - ID: f_backend_stream_gateway_03; verification: static
  - Evidence: prepare_restart 在候选收集成功后置 restart_pending=True（420 行），且开头在 restart_pending 为真时直接 raise RuntimeError('Previous ICE restart is still pending')（343-344 行）; start() 在 super().start() 后若 state != 'completed' 抛 ConnectionError（461-466 行）；restart_pending=False 只出现在全部成功的提交路径（512 行），失败路径无复位; Agent _handle_ice_restart_answer 失败后仅向 Gateway 报告 ERROR，Gateway 按退避再次下发 ICE_RESTART，再次经 create_restart_offer -> prepare_restart 被同一 RuntimeError 拒绝，形成无限失败循环
  - Impact: 一次 ICE 代次接管失败（如对端短暂不可达导致 connectivity checks 未 completed）即把该 PeerConnection 的轮换能力永久卡死；凭证到期后 get_effective_generation 无可用代次，流最终中断且只能靠重建 PeerConnection/重启容器恢复。
  - Fix: 在 start() 的失败出口与 wait_restart_commit 超时路径上复位 restart_pending 并回滚到旧连接（或提供显式 abort_restart 清理 provisional gatherer 与凭证围栏状态），保证下一轮 prepare_restart 可重试。

- [Medium][85] src/backend/cbrowser/gateway/config.py:96-118 — RTC 轮换时序参数（lifetime/interval/lead/heartbeat）经 env 解析后无有限性与次序校验
  - ID: f_backend_stream_gateway_04; verification: static
  - Evidence: from_env 对 CBROWSER_RTC_CREDENTIAL_LIFETIME_SEC / GENERATION_INTERVAL_SEC / ICE_RESTART_LEAD_TIME_SEC / AGENT_HEARTBEAT_TIMEOUT_SEC 只做 float() 转换（96-108 行），float('nan') 与负数均可通过; rtc_config/models.py:14-28 的 RtcScheduleParams 对三个字段只有默认值、无任何 validator（未校验 >0、interval<lifetime、lead<lifetime）; 后果可直接由 service.py 判定式推出：lead>=lifetime 时 should_trigger_restart 恒为真；interval>=lifetime 时新代次出生即过期、get_effective_generation 抛 NoActiveGenerationError 拒绝一切接入；lifetime=NaN 时 is_expired/should_generate_next 的比较恒为假，轮换被静默禁用、凭证永不过期
  - Impact: 单个环境变量笔误即可造成两种严重后果之一：网关对所有 Agent/Viewer 全面拒绝服务，或 TURN 凭证轮换被静默关闭（长期使用同一凭证，违背短期凭证设计），且两种情况都只表现为运行期错误/无声失效，配置加载阶段不报错。
  - Fix: 在 RtcScheduleParams 用 model_validator 强制三参数均为有限正数且 generation_interval_sec < credential_lifetime_sec、ice_restart_lead_time_sec < credential_lifetime_sec；heartbeat 超时同理在 GatewayConfig.from_env 校验有限正数，启动即失败并给出明确错误。

- [Low][85] src/backend/cbrowser/gateway/server.py:357-395 — 注册因无可用 TURN 代次被拒（1011）发生在旧 Agent 已被驱逐、新 Agent 已入表之后
  - ID: f_backend_stream_gateway_05; verification: static
  - Evidence: 357 行 registry.register(agent) 已替换旧注册，358-373 行随即关闭旧会话的全部 Viewer 并关闭旧 Agent WS; 386-391 行才调用 rotation.get_effective_generation(pid)，NoActiveGenerationError 时 close(1011) 并 return ws; 该返回路径不经过消息泵的 finally（泵根本未启动），registry.remove 从未执行：注册表中留下一个 ws 已关闭、last_heartbeat 为注册时刻的条目，只能等心跳监控超时驱逐
  - Impact: 代次短暂不可用的瞬间，一次注册重试会先杀掉原本健康的旧 Agent 会话与全部 Viewer，再拒绝新 Agent；且注册表残留死条目期间 registry.get 仍返回它（靠各调用点零散的 ws.closed 检查兜底），状态真相不一致。
  - Fix: 把 get_effective_generation 前置到 registry.register 与旧会话驱逐之前；代次不可用时直接以 1011 关闭新连接且不扰动现有注册。或在 1011 分支显式 registry.remove(pid, ws=ws) 回滚。

- [Low][70] src/backend/cbrowser/gateway/server.py:496-520 — Viewer 信令入口无限流，每次尝试都放大为一次内部 API 授权调用
  - ID: f_backend_stream_gateway_06; verification: static
  - Evidence: RegistrationThrottle 只用于 /stream/agent/register（288 行）；handle_viewer_signal 全程无任何按来源/按 Profile 的尝试频次限制; 每次携带任意 cbrowser_session Cookie 的尝试都会触发 api.authorize_viewer（517 行）向 API 发起 POST（httpx 超时 5s），随后还有 get_profile_runtime 查询; Origin 校验仅能挡住无 Origin/异源浏览器请求，挡不住直接构造请求的脚本（Cookie 可任意伪造尝试）
  - Impact: 未授权方可以低成本反复触发 Gateway->API 的授权与运行时查询，造成内部 API 的请求放大与日志噪声；在单机部署下风险有限，但该入口经 Caddy 暴露在与页面相同的 HTTPS 端口上。
  - Fix: 对 viewer-authorize 失败按来源 IP（经 Caddy 时取可信代理头）+ profile 做与注册限流同量级的节流，超限返回 429。

- [Low][90] src/backend/cbrowser/supervisor/agent_credentials.py:21-33 — Agent 实例 token 为确定性 HMAC，无过期与随机数，实例绑定期内可重放
  - ID: f_backend_stream_gateway_07; verification: static
  - Evidence: token_for 以 HMAC-SHA256(key, ['stream-agent-v1', profile_id, runtime_instance_id]) 生成 hex token：同一 (profile, instance) 永远得到同一 token，无时间戳/nonce/过期字段; gateway/server.py 在 handle_agent_register 中以 credentials.verify(raw_token, pid, iid) 校验该 token，随后以 API 的 profile->instance 绑定复核作为唯一时效约束; stream_agent/config.py 的 agent_token 仅要求 >=8 字符，与服务密钥 >=32 字节的强度口径不一致（实际部署由 Supervisor 签发 64 字符 hex，暂不构成可利用弱口令）
  - Impact: token 一旦从某个 stream 容器环境/日志中泄漏，在该 instance 仍是 API 当前绑定的整个窗口内可被用来冒名注册并顶掉合法 Agent（注册替换逻辑会主动关闭旧会话）；窗口长度取决于 instance id 的生命周期与复用策略（由 Supervisor 单元决定，本单元未核对）。
  - Fix: 在 token 消息中加入签发时间戳并在 verify 时校验新鲜度窗口（如 10 分钟，与 Supervisor 签发-容器启动时延匹配），或改为随机 token + Supervisor 侧登记摘要；同时把 Agent 侧 token 最小长度口径与 32 字节对齐。

- [Info][95] src/backend/cbrowser/rtc_config/service.py:44-97 — TURN client 凭证按 Profile 共享且默认有效期 24h，任一 Viewer 可独立用作 coturn 中继凭证
  - ID: f_backend_stream_gateway_08; verification: static
  - Evidence: generate_generation 以 role='client' + profile_id 生成唯一一对 TURN REST 凭证，写入 client_rtc_config 后经 Gateway rtc_config 首帧下发给该 Profile 的每一个 Viewer（server.py:571-577）; username 仅含 <expiry>:client-<profile_id>，不含用户/Viewer 维度；默认 credential_lifetime_sec=24*3600（gateway/config.py:40）; coturn REST 凭证的语义即持证者可在有效期内从任意网络位置使用 TURN 中继（与是否仍在观看该 Profile 无关）
  - Impact: 任一被授权看过某 Profile 的用户都能提取该凭证，在最长 24h 内脱离 CBrowser 独立消耗 coturn 中继带宽；凭证吊销只能等代次轮换/过期，无法按用户收回。多 Viewer 共享同一凭证也使滥用无法归因到具体用户。
  - Fix: 可接受的设计取舍需在 security 文档中显式记录；若要收敛，可缩短默认 lifetime 并依靠现有轮换机制，或在 API 授权时按会话签发独立 role 后缀的凭证（需 coturn 侧用户名规则配合，属跨单元改造）。

- [Low][70] src/backend/cbrowser/stream_agent/ice_transport.py:85-140 — ABI 守卫在每个 ICE transport 构造与每次 restart 定位时全量实例化样例 PeerConnection
  - ID: f_backend_stream_gateway_09; verification: suspected
  - Evidence: verify_selkies_abi_guard() 每次调用都新建 RTCIceGatherer()、RTCIceTransport() 与 RTCPeerConnection() 样例对象做 hasattr 检查（121-137 行）; 该函数被 GenerationIceTransport.__init__（242 行，即每个新 PeerConnection 一次）、_main_transport（568 行，每次 create_restart_offer/wait_restart_commit 各一次）、install_ice_transport（558 行）反复调用; 版本与私有属性在进程生命周期内不变，结果未做任何缓存；样例对象是否分配 UDP socket 等资源取决于 SDK 内部实现，未在本仓验证
  - Impact: 每个 Viewer 接入与每次 ICE restart 都付出构造一个完整样例 PeerConnection 的成本，且样例对象未显式关闭，若 SDK 构造即分配资源会形成缓慢泄漏；同时把 fail-closed 检查的耗时放在连接建立的热路径上。
  - Fix: 守卫结果按进程缓存（首次成功后只保留一个廉价的 _VERIFIED 标志检查），样例对象检查只在 install_ice_transport 时执行一次。

- [Low][92] src/backend/cbrowser/gateway/rotation.py:160-176 — handle_agent_error 不处理 _pending_answers，Agent 报错时 Viewer answer 等待必走满 10s 超时
  - ID: f_backend_stream_gateway_10; verification: static
  - Evidence: handle_agent_error 只遍历 (self._pending_offers, self._pending_commits) 并 set_exception（166 行），独漏 self._pending_answers; _restart_connection 第 4 步以 asyncio.wait_for(answer_fut, timeout=10.0) 等待 Viewer answer（rotation.py:385 附近）；Agent 已报错时该等待不会被提前打断; 对比 cancel_profile（180-205 行）对三类 pending 是全量清理的
  - Impact: Agent 在 offer 已转发、等待 Viewer answer 期间报错时，本连接的 restart 仍要空转满 10s 才失败并进入退避，拉长该连接的轮换完成时间与旧凭证占用；无正确性损失（最终仍失败重试），属可避免的时延。
  - Fix: 把 self._pending_answers 一并加入 handle_agent_error 的遍历集合。

- [Low][88] src/backend/cbrowser/gateway/server.py:210-220 — Supervisor quota 路由未校验 max_fps_cap 即转发并回 ok，非法值在 Agent 侧被静默丢弃
  - ID: f_backend_stream_gateway_11; verification: static
  - Evidence: handle_supervisor_quota 取 body.get('max_fps_cap') 后不做任何类型/范围校验，直接放入 GatewayControlEnvelope.payload 并 send，立即返回 {'status': 'ok'}; 真正的校验在 Agent 侧 SupervisorQuotaPayload（[8.0, 30.0] 且有限，protocol.py:246-257），校验失败时 _handle_control_packet 抛错被 agent.py 的泛捕获吞掉并只记日志; 附加问题：Python json 默认接受 NaN/Infinity，body 含 NaN 时 model_dump_json 会产出非严格 JSON 文本，跨实现解析行为未定
  - Impact: Supervisor 误传（如字符串、越界值、NaN）时收到成功回执，但配额实际未生效，形成控制面状态假象；问题只能通过 Agent 日志事后发现，违背该路由同步回执的语义。
  - Fix: 在 Gateway 侧复用 SupervisorQuotaPayload 对 body 做 model_validate，失败返回 400；或把该路由改为校验失败显式报错，不在未校验时返回 ok。

- [Low][85] src/backend/cbrowser/stream_agent/protocol.py:260-277 — ICERestartOffer/AnswerPayload 模型与现行 wire 形态矛盾且全链路无人使用
  - ID: f_backend_stream_gateway_12; verification: static
  - Evidence: ICERestartOfferPayload/ICERestartAnswerPayload 要求 payload 内含 conn_id 字段（260-277 行）; 现行实现中 conn_id 位于信封层：Gateway 从 envelope.payload 只读 generation/sdp/type（rotation.py 的 handle_agent_restart_offer 与 _restart_connection 构造），Agent 侧 _trigger_ice_restart 发送的 payload 只有 {sdp, type}、answer 只有 {generation, type, sdp}，均不含 conn_id; 全仓 grep 显示这两个模型除定义外无引用（Gateway 与 Agent 均未用其校验 restart 载荷）
  - Impact: 死模型给出错误的契约信号：后续维护者若按其校验或构造消息会与现行 wire 不兼容（合法 offer 会被判无效）；restart 载荷实际处于无 schema 校验状态，字段错误只能靠 .get 默认值兜底。
  - Fix: 二选一：删除这两个模型，或把 conn_id 从模型中去掉并在 Gateway/Agent 的 restart 收发路径上真正启用校验，使模型与 schemas/stream/agent_protocol.json 的信封定义一致。

- [Low][80] src/backend/cbrowser/stream_agent/protocol.py:224-243 — 注册载荷把 min_fps/max_fps 硬钉为 8/30，与配置模型允许的 FPS 区间冲突
  - ID: f_backend_stream_gateway_13; verification: static
  - Evidence: AgentRegisterPayload 的 field_validator 要求 min_fps 必须恰为 8、max_fps 必须恰为 30、video_streaming_mode 必须为 False（216-243 行）; StreamAgentConfig 的 model_validator 只要求 8<=min_fps、max_fps<=30 且 min<=max（config.py:151-162），即配置层合法的一组如 min_fps=10 会在 messaging.build_register_payload 构造 AgentRegisterPayload 时抛 ValidationError; 当前 from_env 不读 FPS 环境变量、恒用默认 8/30，所以生产路径暂未触发；但以编程方式构造 StreamAgentConfig 的嵌入方/测试替身会踩中不一致
  - Impact: 同一参数在相邻两层有两套口径，配置校验通过不等于注册能成功；失败点在注册载荷构造处，错误信息指向 fps 常量而非配置来源，排障成本高。
  - Fix: 统一单一权威：要么把 AgentRegisterPayload 的校验放宽为与 config 相同的区间规则，要么把 config 的 validator 收紧为恒定 8/30 并删除可配假象。

- [Low][85] src/backend/cbrowser/stream_agent/policy.py:356-364 — 捕获仲裁周期循环不捕获异常，任一 pipeline 调用失败即永久停止周期仲裁
  - ID: f_backend_stream_gateway_14; verification: static
  - Evidence: _reconciliation_loop 的 try 只捕获 asyncio.CancelledError（356-364 行），reconcile_capture_state 内的 await p.pause_screen_capture()/set_framerate()/resume_screen_capture() 等 SDK 调用一旦抛错即穿透; 循环任务异常退出后无人重启（start() 只创建一次任务，stop() 才回收），且未检索的 task 异常只会产生 asyncio 告警; 周期循环承担输入冷却到期后的 30->8 FPS 回落与状态收敛；事件驱动的 reconcile 调用（viewer 开关、消费者变化）仍在，故故障表现为部分仲裁失效而非全停，更难察觉
  - Impact: Selkies pipeline 方法的一次瞬时异常会让帧率停留在 30 FPS 不再回落（CPU 持续高耗）或暂停/恢复状态不再收敛，直到 Agent 进程重启；与 d013 捕获仲裁的可靠性预期相悖。
  - Fix: 在循环体内按迭代捕获 Exception 并记录（含 caller 与异常类型），下一周期继续；或给循环任务加 done 回调，异常退出时告警并按退避重启。

- [Low][95] src/backend/cbrowser/gateway/registry.py:30 — 文档/日志把心跳超时写死为 30s，与可配置项脱节；credential 模块 docstring 声称存在验证函数
  - ID: f_backend_stream_gateway_15; verification: static
  - Evidence: registry.py:30 类 docstring 写 'detects lost heartbeats (>30s)'，server.py:704 日志写 'timed out (>30s)'，但实际超时取 config.agent_heartbeat_timeout_sec（CBROWSER_AGENT_HEARTBEAT_TIMEOUT_SEC 可改，gateway/config.py:105-107 与 server.py:699-702）; rtc_config/credential.py:1 docstring 为 'TURN REST HMAC credential generation and verification'，但模块只定义 generate_turn_credentials，验证在 coturn 侧完成，本模块无 verify 函数; 两处均为陈述与实现不一致，会误导按日志排障与按 docstring 找 API 的维护者
  - Impact: 运维改大心跳超时后，日志仍宣称 30s，排障时易误判驱逐时机；credential docstring 使读者误以为本模块提供验证能力。
  - Fix: docstring 与日志改为引用配置值（如 f'timed out (>{timeout_sec}s)' 并把 timeout 传入日志参数）；credential.py docstring 改为仅 'generation' 并注明验证由 coturn 完成。

- [Info][90] src/backend/cbrowser/gateway/api_client.py:19-27 — 密钥文件读取口径不一致：API token 与 RtcConfigService 直读文件，绕过统一的权限校验读取器
  - ID: f_backend_stream_gateway_16; verification: static
  - Evidence: GatewayApiClient.__init__ 用 Path.read_text 直读 API token 文件，只校验 >=32 字节（20-22 行），不做 0600 权限检查; RtcConfigService.__init__ 同样以 Path.read_text 直读 TURN secret（rtc_config/service.py:28-40）; 对照组：GatewayConfig 对同批文件统一走 cbrowser.secret_files.read_secret_file，强制 group/other 不可读且 >=32 字节；生产路径经 from_env 预检后风险被前置拦截，但这两个类被独立构造（如测试、嵌入）时无此保护
  - Impact: 纵深防御不一致：密钥文件若被误设为宽松权限，独立构造路径不会告警；当前生产入口（__main__ -> from_env）已预检，同批文件实际风险低，属一致性问题而非现行漏洞。
  - Fix: GatewayApiClient 与 RtcConfigService 改用 read_secret_file 读取（保留各自的错误语义映射），使全部密钥文件只有一个读取权威。

- [Low][55] src/backend/cbrowser/gateway/server.py:291 — Gateway 服务端 WebSocket 未显式设置 max_msg_size，1MB 上限只在整帧接收后由模型层执行
  - ID: f_backend_stream_gateway_17; verification: suspected
  - Evidence: 两处 web.WebSocketResponse() 均未传 max_msg_size（291 行 Agent 注册、538 行 Viewer 信令），依赖 aiohttp 默认值（版本相关，本轮未实测）; Agent->Gateway 的 1MB 约束由 GatewayTunnelEnvelope.validate_data 在整帧已接收并 json 解析后才执行；Viewer->Gateway 方向在 Gateway 层完全没有大小检查，靠 Agent worker 在出队后以 MAX_PAYLOAD_SIZE 拦截（agent.py:856-860）; 对照 Agent 作为客户端连接 Gateway/上游时显式设置了 max_msg_size=MAX_FRAME_SIZE（agent.py ws_connect）
  - Impact: 已注册 Agent 或已授权 Viewer 可发送远超 1MB 的单帧，Gateway 需先把整帧缓冲进内存才有机会拒绝，形成可被滥用的内存压力面；实际默认上限取决于 aiohttp 版本，未确认前按防御缺口记录。
  - Fix: 为两处 WebSocketResponse 显式设置 max_msg_size（如 1MB + 信封余量，与 Agent 侧 MAX_FRAME_SIZE 口径对齐），使超限帧在传输层即被关闭而非应用层事后拒绝。

- [Medium][90] tests/integration/test_gateway_signaling.py:211-325 — Viewer 信令『无可用 TURN 代次』分支（生产缺陷 f_backend_stream_gateway_01 所在）无任何回归测试
  - ID: f_backend_stream_gateway_18; verification: static
  - Evidence: 生产路径：handle_viewer_signal 在 server.py:538-558 先 ws.prepare 并写入 viewers 字典，之后 get_effective_generation 抛 NoActiveGenerationError 时 return 普通 web.Response(503)——这正是 f_backend_stream_gateway_01 的缺陷点（响应写回抛错 + viewers 条目泄漏）; 分配的 7 个单元测试文件无一 import 或驱动 cbrowser.gateway.server（全仓 grep 确认 handle_viewer_signal 只出现在 e2e 的 GatewayMockServer 重实现与 fixtures 的 gateway_fixture 中，均非生产代码）; 集成层 test_viewer_handshake_rejections 覆盖的五种拒绝（错 Origin、缺 Cookie、API 授权拒绝、无 Agent、observed_state 非 running）全部发生在 WS prepare 之前；测试内 harness 的 RtcConfigService 始终持有有效代次，『已过期代次』状态从未被构造; 单元层 test_gateway_rotation_guards.py:54-58 只在 RotationCoordinator 对象上断言 NoActiveGenerationError 被抛出，未经 Gateway 信令路径观察客户端实际收到的关闭方式与 viewers 字典状态
  - Impact: f_backend_stream_gateway_01 修复与否无测试信号：把 503 前移、或改走 close(1013)+清理 viewers，现有套件都无法区分改前改后；该分支恰在『全部代次过期』这一轮换故障时刻触发，是 Viewer 可重试语义与 RotationCoordinator 迁移判定的共同依赖点。
  - Fix: 在 tests/integration/test_gateway_signaling.py 增加用例：注册 Agent 且 observed=running，但让代次过期（短 lifetime 的 GatewayHarness 或直接推进 coordinator 状态），断言客户端收到可识别的重试性关闭（如 1013 或 prepare 前的 503）、且 Gateway viewers/profile_connections 中无残留条目；修复生产缺陷时先以此用例复现当前异常重置行为。

- [Medium][88] tests/unit/test_stream_agent_lifecycle.py:299-367 — Agent 心跳循环无故障注入测试，单次瞬时异常永久停跳（生产缺陷 f_backend_stream_gateway_02）可无声通过
  - ID: f_backend_stream_gateway_19; verification: static
  - Evidence: 生产路径：agent.py:378-407 的 _heartbeat_loop 以单个 try 包住整个 while 循环，policy.selkies_video_state() 或 ws.send_str() 任一瞬时异常即令循环整体退出（f_backend_stream_gateway_02）; 全仓 grep 确认没有任何测试引用 _heartbeat_loop；test_stream_agent_lifecycle.py 的心跳用例（:299-367 节奏、:699-776 状态跟随）使用的 _SelkiesVideoState 替身只返回固定状态、从不抛错，MockGatewayServer 的消息泵对发送失败仅记录 debug 日志后容忍断开; Gateway 侧『Agent 沉默 -> 驱逐』有覆盖（test_agent_heartbeat_timeout_eviction），但那测的是 Agent 整体不再发包；『单次异常后应继续发包』这一 Agent 侧存活契约没有任何用例表达; 现有心跳测试断言的是节奏与载荷字段，对循环的异常后存续性无断言，缺陷结构（try 包住循环）与全部现有测试兼容
  - Impact: f_backend_stream_gateway_02 的生产影响是健康 Agent 被误驱逐、全部 Viewer 被断开；由于零覆盖，该缺陷即使被『修回』原样也不会变红，心跳可靠性只能依赖集成/e2e 的长时间运行偶然暴露。
  - Fix: 在 test_stream_agent_lifecycle.py 增加故障注入用例：让 selkies_video_state 替身首呼抛错（或让网关侧首个心跳 send 失败）后恢复正常，断言后续心跳仍按节奏到达 MockGateway 且数量持续增长；修复生产循环后该用例应先红后绿。

- [Low][80] tests/unit/test_stream_ice_transport.py:118-131 — ICE restart 在 start() 阶段失败后的 restart_pending 楔死（生产缺陷 f_backend_stream_gateway_03）无测试；现有失败 probe 只覆盖候选收集阶段
  - ID: f_backend_stream_gateway_20; verification: static
  - Evidence: 生产代码分段核对（ice_transport.py:340-437 与 440-512）：restart_pending=True 只在 prepare_restart 候选收集成功后置位；start() 中 super().start() 后 state != 'completed' 抛 ConnectionError、以及旧连接写拒绝校验失败抛 RuntimeError 两条路径均不复位 restart_pending，后续 prepare_restart 在 :343-344 恒被 'still pending' 拒绝; 单元层对 GenerationIceTransport 的唯一 restart 相关用例（test_create_restart_offer_requires_generation_ice_transport）以全 mock PeerConnection 只断言类型不符抛 TypeError，从不驱动真实 prepare_restart/start 周期; Docker probe ice_restart_failure.py 的三次失败 restart 以 force_relay+无 TURN 触发，失败点是 prepare_restart 内的 'Relay candidates unavailable'（候选收集阶段、置位之前），其后健康 restart 成功只能证明收集阶段回滚完好，不能证明 start() 阶段失败后可恢复; ice_pending_close.py 只调用一次 prepare_restart 验证 pending 期关闭语义，未涉及 start() 失败后的再次 prepare
  - Impact: f_backend_stream_gateway_03 的触发条件（对端短暂不可达导致新代次 connectivity 未 completed）与 probe 的触发条件（无 relay 候选）不同，现有绿色证据会让读者误以为『失败 restart 可恢复』已被完整证明；楔死一旦发生只能靠重建 PeerConnection/重启容器恢复，且无测试会在回归时报警。
  - Fix: 新增 probe 或单元用例：在真实双 peer 拓扑中先成功 prepare_restart，再让 start() 以不可达的远端参数失败（或令旧连接写拒绝校验失败），断言 transport.restart_pending 被复位且随后一次健康 restart 能完成提交；若 Selkies 环境外无法驱动 start()，至少在 ice_restart_failure.py 旁新增 start 阶段失败变体并在 docstring 中区分两个失败阶段。

- [Low][90] tests/unit/test_gateway_config.py:10-52 — 轮换时序参数既无校验测试、env 解析也从未以非默认值被行使（关联生产缺陷 f_backend_stream_gateway_04）
  - ID: f_backend_stream_gateway_21; verification: static
  - Evidence: 全仓单元测试 grep 无一设置 CBROWSER_RTC_CREDENTIAL_LIFETIME_SEC、CBROWSER_RTC_GENERATION_INTERVAL_SEC、CBROWSER_RTC_ICE_RESTART_LEAD_TIME_SEC 或 CBROWSER_AGENT_HEARTBEAT_TIMEOUT_SEC；test_gateway_config_from_env_success 只断言三者等于默认值 86400/43200/21600，from_env 对这四个值的 float() 解析路径从未以自定义值行使; test_rtc_config.py:110-143 与 test_gateway_rotation_guards.py 的 _service() 只以合法组合（86400/43200/21600、10/5/2）构造 RtcScheduleParams；NaN、负数、interval>=lifetime、lead>=lifetime 从未被任何测试构造或断言应被拒绝; 生产侧 RtcScheduleParams 无 validator、GatewayConfig.from_env 只做 float() 转换（f_backend_stream_gateway_04），因此『非法时序配置应启动即失败』这一预期行为在测试层也没有任何钉子
  - Impact: 时序参数笔误的两类后果（全面拒绝接入 / 轮换被静默禁用）在测试层均不可见：即使将来补上生产校验，也没有现成用例防止校验被再次删掉；env 改名或解析回归（如读错变量名）同样不会被默认值断言发现。
  - Fix: 在 test_gateway_config.py 增加：设置四个 CBROWSER_RTC_*/HEARTBEAT env 为非默认合法值并断言解析结果；在 test_rtc_config.py（或 rotation guards）增加参数化负例：NaN、负数、interval>=lifetime、lead>=lifetime 构造 RtcScheduleParams / from_env 应抛错——与 f_backend_stream_gateway_04 的生产校验同批落地，先红后绿。

- [Low][85] tests/unit/test_gateway_rotation_guards.py:54-124 — RotationCoordinator 的代次接管完成路径（tick 调度、restart 握手至提交、handle_agent_error）在单元层无测试
  - ID: f_backend_stream_gateway_22; verification: static
  - Evidence: 现有四个 coordinator 用例只覆盖元素级守卫：get_effective_generation 过期 fail-closed、陈旧 offer 丢弃、register_connection 标记 migrated、cancel_profile 取消任务与 pending future; 全仓 grep 确认没有任何测试调用 RotationCoordinator.tick 或 handle_agent_error，也没有用例驱动 _restart_connection 的完整握手（Agent offer -> Viewer answer -> ICE_RESTART_COMMITTED -> current generation 推进、in_progress 清空）; 生产缺陷 f_backend_stream_gateway_10（handle_agent_error 漏处理 _pending_answers、answer 等待必走满 10s）正位于这片无覆盖区，其行为从未被任何断言观察; 接管完成语义目前只由 Docker e2e（test_gateway_ac005_relay_e2e 的双代次观察）与 probe（ice_commit_outcome 的 wait_restart_commit）兜底，单元层回归定位粒度粗、且 e2e 在缺镜像 env 时整体 skip（兄弟单元 f_tests_e2e_stream_frontend_01）
  - Impact: 轮换编排的状态机回归（提交条件、代次推进、错误路径的等待清理）只能在重型 e2e 中暴露，且 e2e 静默跳过时该路径实际零执行；f_backend_stream_gateway_10 这类时延缺陷无测试可钉。
  - Fix: 在 test_gateway_rotation_guards.py 以可控 send_agent/send_viewer 替身补三类用例：tick 到点生成 in-progress 代次并下发 RTC_CONFIG；完整握手后 current 代次推进且 migrated 清算；handle_agent_error 同时失败 offers/commits/answers 三类 pending（含 answers 用例钉住 f_backend_stream_gateway_10 的修复）。

## views

```json
{
  "contracts": {
    "reviewer": "e6cc69dd-f345-4ffc-aea8-84b3199bdceb",
    "status": "completed"
  },
  "correctness": {
    "reviewer": "e6cc69dd-f345-4ffc-aea8-84b3199bdceb",
    "status": "completed"
  },
  "design": {
    "reviewer": "e6cc69dd-f345-4ffc-aea8-84b3199bdceb",
    "status": "completed"
  },
  "documentation": {
    "reviewer": "e6cc69dd-f345-4ffc-aea8-84b3199bdceb",
    "status": "completed"
  },
  "performance": {
    "reviewer": "e6cc69dd-f345-4ffc-aea8-84b3199bdceb",
    "status": "completed"
  },
  "robustness": {
    "reviewer": "e6cc69dd-f345-4ffc-aea8-84b3199bdceb",
    "status": "completed"
  },
  "security": {
    "reviewer": "e6cc69dd-f345-4ffc-aea8-84b3199bdceb",
    "status": "completed"
  },
  "tests": {
    "status": "completed",
    "reviewer": "922d4438-5f1f-4ffb-b206-1fcf5a0b78bd"
  }
}
```

## files_reviewed

```json
[
  "src/backend/cbrowser/gateway/__init__.py",
  "src/backend/cbrowser/gateway/__main__.py",
  "src/backend/cbrowser/gateway/api_client.py",
  "src/backend/cbrowser/gateway/config.py",
  "src/backend/cbrowser/gateway/endpoint.py",
  "src/backend/cbrowser/gateway/registry.py",
  "src/backend/cbrowser/gateway/rotation.py",
  "src/backend/cbrowser/gateway/server.py",
  "src/backend/cbrowser/rtc_config/__init__.py",
  "src/backend/cbrowser/rtc_config/credential.py",
  "src/backend/cbrowser/rtc_config/models.py",
  "src/backend/cbrowser/rtc_config/service.py",
  "src/backend/cbrowser/stream_agent/__init__.py",
  "src/backend/cbrowser/stream_agent/agent.py",
  "src/backend/cbrowser/stream_agent/boundary.py",
  "src/backend/cbrowser/stream_agent/config.py",
  "src/backend/cbrowser/stream_agent/ice_transport.py",
  "src/backend/cbrowser/stream_agent/messaging.py",
  "src/backend/cbrowser/stream_agent/policy.py",
  "src/backend/cbrowser/stream_agent/policy_rules.py",
  "src/backend/cbrowser/stream_agent/protocol.py",
  "src/backend/cbrowser/stream_agent/x11_keymap.py"
]
```
