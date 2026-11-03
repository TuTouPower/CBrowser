# bundle_local_backend_stream_gateway

## responsibilities

- Gateway 服务（gateway/server.py）：面向 Stream Agent 的注册握手与消息泵、面向浏览器的 viewer 信令隧道、面向 Supervisor 的内部控制端点（visibility/quota/disconnect），以及基于心跳的 Agent 存活监控。
- Gateway 注册表与限流（gateway/registry.py）：内存中的已注册 Agent 表、心跳超时驱逐、按来源的注册节流与按来源+Profile 的 viewer 授权失败节流。
- Gateway 内部 API 客户端（gateway/api_client.py）：持文件令牌（凭据只记位置与种类：CBROWSER_GATEWAY_API_TOKEN_FILE 指向的令牌文件）调用 API 的 runtime 查询与 viewer 授权判定，失败一律 fail-closed。
- Stream Agent（stream_agent/agent.py）：出站注册到 Gateway（带退避重连），按 viewer 建立到本机 Selkies 的 loopback WebSocket 桥，HELLO 元数据解析与 controller token 注入，断开时 10 秒 resume grace 的 detached upstream 保留，10 秒周期应用层心跳上报 Selkies 视频状态。
- 捕获策略（stream_agent/policy.py + policy_rules.py）：单一串行化 reconcile 控制器仲裁暂停/恢复与 8/30 FPS，拦截客户端调优 verb、清洗 SETTINGS 消息、应用 Supervisor 配额、维护 SDK peer 与 Gateway conn_id 映射。
- 协议与配置（stream_agent/protocol.py、messaging.py、两处 config.py、gateway/endpoint.py）：v2 envelope 的 pydantic 严格模型（extra=forbid、身份字段正则、帧大小上限）、环境变量配置加载与密钥文件校验、Origin/端点规范化。
- 运行时边界自检与 X11 键位补丁（stream_agent/boundary.py、x11_keymap.py）：启动时断言禁止路径未挂载进 Stream 容器；对 Selkies 2.1.0 输入处理做版本与 ABI 绑定的 monkeypatch，使文本覆盖层与 Chromium XKB 缓存一致。

## interfaces

- WS GET /stream/agent/register?profile_id=&runtime_instance_id=（Bearer agent 凭据 + 首包 AgentRegisterEnvelope -> GatewayRegisterResponse ACK）
- WS GET /stream/{profile_id}/signal（Origin 白名单 + cbrowser_session cookie + API authorize_viewer 三重校验后建立隧道）
- GET /gateway/v1/internal/profiles/{profile_id}/visibility?runtime_instance_id=（Supervisor Bearer 控制令牌）
- POST /gateway/v1/internal/profiles/{profile_id}/quota | /disconnect（Supervisor Bearer 控制令牌，instance fence 409）
- 内部 API：GET /api/v1/internal/gateway/profiles/{profile_id}/runtime、POST /api/v1/internal/gateway/viewer-authorize
- v2 envelope 契约：GatewayTunnelEnvelope(open/msg/close)、GatewayControlEnvelope(supervisor_quota)、AgentRegisterEnvelope、AgentHeartbeatEnvelope（discriminator=action 的联合类型）
- 环境变量契约：Gateway 侧 CBROWSER_AGENT_KEY_FILE / CBROWSER_GATEWAY_TOKEN_FILE / CBROWSER_GATEWAY_API_TOKEN_FILE / CBROWSER_GATEWAY_API_URL / CBROWSER_ALLOWED_ORIGINS / CBROWSER_GATEWAY_HOST|PORT / CBROWSER_AGENT_HEARTBEAT_TIMEOUT_SEC；Agent 侧 CBROWSER_PROFILE_ID / CBROWSER_GATEWAY_URL / CBROWSER_RUNTIME_INSTANCE_ID / CBROWSER_CONFIG_VERSION / CBROWSER_AGENT_SECRET_FILE|CBROWSER_AGENT_TOKEN / CBROWSER_UDP_MUX_PORT / CBROWSER_SCREEN_WIDTH|HEIGHT / CBROWSER_SELKIES_CREDENTIALS_FILE / SELKIES_PORT

## dependencies

- aiohttp（Gateway 服务与 Agent 客户端 WS）、httpx（Gateway->API 客户端，timeout=5s、trust_env=False）
- pydantic v2（全部协议模型与配置模型）
- cbrowser.secret_files.read_secret_file（单元外，未审）：密钥文件读取与最小 32 字节校验
- cbrowser.supervisor.agent_credentials.AgentCredentials（单元外，未审）：Agent 注册凭据验证
- Selkies 2.1.0 SDK（单元外）：WebRTCService、selkies.__main__、input_handler._XTestKeyboard、peer_manager/display_pipelines 等内部结构被策略子类与 agent 直接依赖
- CBrowser API 服务（单元外）：runtime 绑定与 viewer 授权的权威来源
- 系统工具 /usr/bin/xkbcomp 与 X11 DISPLAY（x11_keymap）

## flows

- Agent 注册：Bearer 呈现 -> 注册节流 -> query 身份格式校验 -> credentials.verify -> API runtime 绑定校验 -> WS 建立 -> 10s 内首包注册 envelope 与 query 身份比对 -> registry.register（替换旧 session 并关闭其 viewers 与 WS）-> ACK -> 消息泵（tunnel 包按 profile/instance/session 三重身份 + conn_id 归属校验后转发；HEARTBEAT 更新 registry 心跳与视频状态字段）
- Viewer 接入：授权失败节流闸门 -> Origin 规范化与白名单 -> session cookie 存在性 -> API authorize_viewer -> Agent 在线检查 -> API observed_state in (running, ready) -> 登记 ViewerEntry 并向 Agent 发送 tunnel open -> 双向转发（viewer 侧含 cbrowser 控制帧丢弃逻辑）-> 关闭时发送 tunnel close
- Supervisor 控制：Bearer 常量时间比较 -> instance fence 校验 -> visibility 直接读 Agent 最近一次心跳上报的 Selkies peer 状态；quota/disconnect 构造 envelope 经 Agent WS 下发 / 逐个关闭该 profile 的 viewer 并逐条通知 Agent
- Agent 侧隧道：Gateway tunnel open -> 按 conn_id 建 generation 所有的 worker + 有界队列(100) -> 连接 loopback Selkies WS -> HELLO 时解析 client_tab_id/resume_key、按需注入 controller_token、经 peer_manager 以 (tab_id, resume_key) 双因子唯一匹配关联 SDK peer -> 上行 reader 按 generation 转发；tunnel close/Gateway 断开 -> detach 保留 upstream 10 秒待 resume，超时或 stop 时彻底排空
- 心跳存活：Agent 每 10s 上报（首报不等间隔）；Gateway 后台任务以 min(1s, timeout/4) 周期扫描，默认 30s 超时驱逐并关闭其 viewers

## constraints

- UDP mux 端口限定 [30000, 30991]（config 与 protocol 两处一致校验）
- FPS 边界：min_fps >= 8.0、max_fps <= 30.0、配额协议层限定 [8.0, 30.0]
- video_streaming_mode 恒为 False、depth 恒为 24（pydantic 校验拒绝其他值）
- 帧大小三层上限：WS max_msg_size = MAX_STREAM_FRAME_SIZE（约 6.3MB）、tunnel data 字段 <= 1MB、Agent 侧原始 envelope <= 1MB（见 finding f_backend_stream_gateway_02）
- 密钥文件最小 32 字节、0600 等要求由 read_secret_file 执行；agent_token 环境变量回退路径仅要求 >= 8 字符
- 身份字段字符集：profile_id ^[a-zA-Z0-9_-]+$，instance/conn_id ^[a-zA-Z0-9_\-.:]{1,128}$，agent_session_id 另有长度与字符模式
- Selkies 版本硬绑定 2.1.0：x11_keymap 在版本或 ABI 签名不符时抛 RuntimeError，run_standalone_service 据此 sys.exit(1) fail-closed

## decisions

- 授权 fail-closed：API 不可达/异常时 authorize_viewer 返回 (False, ...)，get_profile_runtime 返回 None 并导致注册 403 / viewer 503
- Gateway 不自行推导可见性：visibility 端点只返回 Agent 心跳上报的 Selkies peer 状态，未上报时 503 而非猜测
- 单一串行控制器：所有捕获状态变更经 asyncio.Lock 串行化的 reconcile_capture_state，外部 resume 调用（_resume_display_capture）被改道进同一控制器
- generation 所有权：viewer worker/reader 以单调 generation 校验归属，过期 generation 不得删除或影响替代者；detach 以 (conn_id, generation) 标记移交 detached upstream
- 包级懒导出：gateway/__init__.py 与 stream_agent/__init__.py 用 __getattr__ 延迟导入，避免包初始化时拉入 Selkies/GStreamer
- 日志脱敏：异常只记 type 名、Gateway URL 经 _sanitize_url 去除 userinfo/query/fragment、配置 repr 中 token 恒为 ***

## evidence

- gateway/server.py:311-470 handle_agent_register 全流程（节流、凭据、API 绑定、替换语义、消息泵身份校验）
- gateway/server.py:472-640 handle_viewer_signal（节流、Origin、cookie、API 授权、Agent/状态检查、转发循环）
- gateway/registry.py:104-152 RegistrationThrottle 与 AuthorizationThrottle 的键与窗口实现
- stream_agent/agent.py:268-390 connect_and_run 注册/重连/退避；agent.py:560-720 detach/resume grace 与 generation 机制
- stream_agent/policy.py:434-570 reconcile_capture_state 三规则；policy.py:570-764 策略化 WebRTCService 子类的输入装甲与回调钩子
- stream_agent/protocol.py:26-246 全部 envelope 模型与校验器；stream_agent/config.py:29-280 配置校验与 from_env fail-closed 密钥加载
- stream_agent/boundary.py:20-71 禁止路径清单与启动断言；stream_agent/x11_keymap.py:37-118 版本/ABI 守卫与补丁安装

## uncertainties

- cbrowser.secret_files.read_secret_file 是否 strip 尾部空白未在本单元核对：gateway/server.py:80-84 将 read_secret_file(gateway_token_file) 的返回值直接 .encode() 作为控制令牌比对，而 gateway/api_client.py:22-24 对同一函数结果显式 .strip()；若该函数不 strip 且令牌文件带尾随换行，Supervisor 控制端点的 Bearer 比对可能恒不匹配。影响：决定 handle_supervisor_* 三端点是否可用，需跨单元（secret_files 与 Supervisor 调用方）核对。
- StreamAgent.close()（agent.py 末尾）是否有生产调用方未在本单元核对：run_standalone_service 的关闭路径走 svc.tasks 取消 + agent.stop()，close() 若仅为嵌入式回退则 f_backend_stream_gateway_06 影响有限。
- Selkies SDK 内部 text_room 与 _find_spare_keycodes 的调用时序在单元外：f_backend_stream_gateway_05 是否可达取决于 SDK 是否会在 _spare_keycodes 赋值前调用 text_room。
- AgentCredentials.verify 的凭据派生/轮换语义在 supervisor 单元，本单元只核对到其被调用且失败返回 401。
- 本单元 16 个文件全部为生产代码、无测试文件；针对本单元的测试位于 tests_*/backend_tests 等其他单元，本轮未交叉核对其覆盖充分性，tests 视角仅就可测性与单元内事实作出判断。

## Findings

- [Medium][75] src/backend/cbrowser/gateway/server.py:313-315; src/backend/cbrowser/gateway/registry.py:104-130 — Agent 注册节流仅按来源地址计数，同机所有 Agent 共享一个额度桶，批量重启时合法注册会被 429 拒绝
  - ID: f_backend_stream_gateway_01; verification: static
  - Evidence: server.py handle_agent_register 以 registration_throttle.allow(request.remote) 为闸门，键只有来源地址，无 profile/instance 维度; registry.py RegistrationThrottle 默认 max_attempts=20、window_seconds=60.0，allow() 对同一 key 的全部尝试（含合法注册）计数; 本系统为单机 Docker 部署（仓库 AGENTS.md 声明），各 Stream 容器经同一桥接地址到达 Gateway，request.remote 对所有 Agent 相同或高度集中; Agent 侧 connect_and_run 以 1..30s 退避重试（agent.py BACKOFF_SCHEDULE），被 429 后不会立即恢复
  - Impact: Gateway 或宿主重启后，若超过 20 个 Profile 的 Agent 在 60 秒窗口内集中重注册，后到者收到 429，必须等窗口滑动/退避后才能注册成功，画面恢复时间被拉长；Profile 数量越多越严重。节流本意是挡未授权尝试，但当前实现把合法注册也计入同一桶。
  - Fix: 将节流键改为按来源+声称身份（profile_id/instance_id）计数，或仅对凭据验证失败的尝试计数（把 allow/record 拆开，成功注册不占额度）；至少提高默认值并在部署文档中声明该耦合。

- [Low][85] src/backend/cbrowser/gateway/server.py:585-605; src/backend/cbrowser/stream_agent/protocol.py:62-67; src/backend/cbrowser/stream_agent/agent.py:41-43,607-617 — 隧道帧大小上限三层不一致：viewer 超 1MB 文本帧使 Gateway 转发循环抛 ValidationError 突然断连，Agent 侧原始 envelope 1MB 上限会静默丢弃转义膨胀后的合法帧
  - ID: f_backend_stream_gateway_02; verification: static
  - Evidence: protocol.py GatewayTunnelEnvelope.validate_data 限制 data 字段 <= 1MB（UTF-8 字节）; server.py viewer 转发循环直接以 GatewayTunnelEnvelope(..., data=text) 构造模型，未捕获 ValidationError；异常穿透 async for 循环，仅靠 finally 做清理，连接以未处理异常方式终止而非受控 close 码; agent.py _handle_gateway_envelope 以 MAX_PAYLOAD_SIZE=1MB 检查原始 envelope 字节数；data 接近 1MB 且含大量需 JSON 转义的字符时，合法 data 的 envelope 序列化后可超过 1MB，被 Agent 静默丢弃（仅 warning 日志）; 两端 WS max_msg_size 又同为 MAX_STREAM_FRAME_SIZE（约 6.3MB），与上述 1MB 上限并存，无注释说明层级关系
  - Impact: 接近边界的大帧（例如大数据量信令/剪贴板类文本）行为不确定：viewer 侧表现为连接异常断开，Agent 侧表现为消息无声丢失，两端日志都不足以定位为同一根因。
  - Fix: 统一口径：或将 data 上限与原始 envelope 上限对齐并在 Gateway 转发前显式检查长度、超限时以 1009 受控关闭并记日志；或在 viewer 循环中捕获 ValidationError 单独处理。并在 protocol.py 注释三层上限的关系。

- [Low][85] src/backend/cbrowser/gateway/server.py:221-222,266-288 — Supervisor 控制端点对下游发送/关闭失败无防护，quota 与 disconnect 在 Agent/viewer 套接字异常时以未处理 500 中断且后续 viewer 不再处理
  - ID: f_backend_stream_gateway_03; verification: static
  - Evidence: handle_supervisor_quota 结尾 await agent.ws.send_str(env.model_dump_json()) 无 try/except，Agent 恰在 fence 校验后断开时异常直接穿透为 500; handle_supervisor_disconnect 循环内 await v_entry.ws.close(...) 与 await agent.ws.send_str(...) 均无防护，任一 viewer 关闭抛错即中断循环，剩余 viewers 既不关闭也不通知 Agent，接口返回 500; 对照同文件 close_viewers_for_session（server.py:98-115）对每个 viewer 的 close 都做了 best-effort try/except，说明本文件既定风格就是防护单点失败
  - Impact: Supervisor 在竞态时刻调用 disconnect/quota 时得到含义模糊的 500，且 disconnect 可能只执行一半：部分 viewer 已断、部分仍连在 Agent 上，与 Supervisor 的预期状态不一致，需要额外对账。
  - Fix: 将 quota 的 send 与 disconnect 循环内的 close/send 改为逐项 best-effort（记录失败 conn_id），处理完所有目标后再统一返回结果；Agent WS 发送失败时返回 503 与 visibility/quota 既有口径一致。

- [Low][80] src/backend/cbrowser/stream_agent/policy.py:263-291; src/backend/cbrowser/stream_agent/protocol.py:83-92 — LiveCapturePolicyAgent.set_supervisor_quota 只校验正数与 <=max_fps，接受低于 8 FPS 下限的配额，与协议层 [8.0, 30.0] 约束不一致
  - ID: f_backend_stream_gateway_04; verification: static
  - Evidence: protocol.py SupervisorQuotaPayload.validate_quota_cap 明确要求 max_fps_cap 有限且在 [8.0, 30.0]; policy.py set_supervisor_quota 仅拒绝 NaN/inf/<=0，随后 bounded_cap = min(cap_val, self.max_fps)，如 cap=2.0 会被原样接受; reconcile_capture_state Rule 3 以 desired_fps = min(desired, cap) 应用配额，可把帧率压到 min_fps=8.0 的产品下限以下; 当前生产路径只有 Gateway 经协议校验后下发一条，但 set_supervisor_quota 是策略类公开方法，其他调用方（含测试与未来控制面）可绕过协议层约束
  - Impact: 纵深防御缺口：任一未经协议模型校验的调用即可让捕获帧率跌破 8 FPS 下限，与 StreamAgentConfig/协议宣称的不变量冲突，且不会有任何日志提示越界。
  - Fix: 在 set_supervisor_quota 中按同一口径拒绝或钳制到 [self.min_fps, self.max_fps]，越界时记录 warning 并说明被拒绝/钳制后的值。

- [Low][45] src/backend/cbrowser/stream_agent/x11_keymap.py:71-77 — x11_keymap 的 text_room 回退路径在 _spare_keycodes 尚未赋值时可能对 None 求和抛 TypeError
  - ID: f_backend_stream_gateway_05; verification: suspected
  - Evidence: text_room 补丁：original_room 返回 0（注释称 native evdev 无界）时执行 sum(key not in held for key in keyboard._spare_keycodes); _spare_keycodes 仅在 find_named_spares（_find_spare_keycodes 补丁）或 prebind_with_refresh 的 missing 分支中被赋值；若 SDK 在首次查找备用键位前调用 text_room，该属性为初始值（SDK 侧预计为 None）; 同文件 prebind_with_refresh 对 _spare_keycodes is None 做了显式判空，说明作者意识到该属性可为 None，但 text_room 路径未做同样防护
  - Impact: 若 SDK 调用时序命中该路径，文本输入房间计算会在 Selkies 输入处理内抛 TypeError，可能中断当次文本键入甚至污染输入处理状态；是否可达取决于 Selkies 2.1.0 内部调用顺序（单元外，未核实），故标 suspected。
  - Fix: text_room 中先取 spares = keyboard._spare_keycodes，若为 None 直接返回 original_room 的结果（或 0 的无界语义），与 prebind 路径的判空口径一致。

- [Low][50] src/backend/cbrowser/stream_agent/agent.py:1055-1062（close 方法，文件末尾 run_standalone_service 之前） — StreamAgent.close() 只置 _running 并关 Gateway WS，不停心跳与策略后台循环，作为终止手段使用时会泄漏后台任务
  - ID: f_backend_stream_gateway_06; verification: suspected
  - Evidence: close() 实现仅 self._running=False 与 asyncio.create_task(self._gw_ws.close())，未取消 _heartbeat_task、未调 policy.stop()、未排空 viewer workers 与 detached upstreams; 对照 stop()（同文件）完整执行心跳取消、WS 关闭、_cleanup_all_viewers(detach=False)、_close_all_detached_upstreams、policy.stop(); 心跳循环靠 while self._running 退出但会先睡满当前 heartbeat_interval；policy 的 reconciliation/motion 监督循环无 _running 检查，只靠 stop() 取消
  - Impact: 若任何嵌入方以 close() 作为最终关闭（其命名与同步签名容易给人此印象），策略循环与 detached upstream 计时器会继续存活并操作已关闭的服务对象；当前仓库内生产路径走 stop()，实际影响取决于单元外调用方，故标 suspected。
  - Fix: 明确 close() 语义：或删除该方法只保留 stop()，或让其至少同步取消心跳任务并调度 policy.stop()，并在 docstring 写明它不是完整关闭。

- [Info][90] src/backend/cbrowser/gateway/registry.py:12-24; src/backend/cbrowser/gateway/server.py:455-463 — Gateway 注册表中的 runtime_state 在注册后永不更新，心跳携带的 runtime_state 被处理代码丢弃
  - ID: f_backend_stream_gateway_07; verification: static
  - Evidence: RegisteredAgent 含 runtime_state 字段，注册时由 AgentRegisterPayload.runtime_state 填充; server.py 消息泵处理 HEARTBEAT 时只取 payload 的 unpaused_video_consumers 与 capture_running 写入 agent，未同步 beat.runtime_state 到 agent.runtime_state; AgentHeartbeatPayload 明确含 runtime_state 字段（protocol.py:203-211），即协议设计意图包含该状态的上报通道
  - Impact: registry 中 runtime_state 恒为注册瞬间值（当前注册负载恒为 ready，影响小），但任何未来读取该字段做决策的代码都会拿到陈旧状态，形成隐性误导。
  - Fix: 在 HEARTBEAT 处理中同步 agent.runtime_state = beat.runtime_state；或删除 RegisteredAgent.runtime_state 字段以免误用。

- [Info][90] src/backend/cbrowser/stream_agent/messaging.py:17-18; src/backend/cbrowser/stream_agent/policy_rules.py:33-34,64-68; src/backend/cbrowser/stream_agent/policy.py:608-616; src/backend/cbrowser/stream_agent/protocol.py:43-67,109-127,156-169 — 同义逻辑多处重复实现：iso_now 双定义、身份校验器在四个协议模型中复制、客户端 verb 拦截存在两套实现
  - ID: f_backend_stream_gateway_08; verification: static
  - Evidence: iso_now 在 messaging.py 与 policy_rules.py 各定义一份（实现相同），policy.py 又分别从 policy_rules 导入两个别名; should_block_client_verb（policy_rules.py）用 startswith(FORBIDDEN_PEER_PREFIXES) 实现拦截，但 policy.py 的服务子类 _on_peer_data_message 直接内联 msg.startswith(self.FORBIDDEN_PEER_PREFIXES)，未调用该函数；函数仅经包 __init__ 再导出; profile_id / runtime_instance_id / conn_id 三个校验器在 GatewayTunnelEnvelope、GatewayControlEnvelope、_AgentEnvelope 等模型中逐字复制四份
  - Impact: 规则变更（如新增禁止 verb 前缀、放宽身份字符集）需多处同步修改，漏改一处即出现 Gateway 与 Agent、或不同 envelope 之间口径漂移；当前各副本内容一致，属维护性风险而非现行缺陷。
  - Fix: 抽取共享的校验函数/mixin 供各 envelope 复用；_on_peer_data_message 改为调用 should_block_client_verb；iso_now 只保留一处定义、另一处导入复用。

- [Info][95] src/backend/cbrowser/gateway/server.py:343-349 — Agent 注册包解码处 except (ValidationError, Exception) 冗余捕获，掩盖预期的窄异常分类
  - ID: f_backend_stream_gateway_09; verification: static
  - Evidence: handle_agent_register 中 reg_raw = json.loads(msg.data) 与 AgentRegisterEnvelope.model_validate 的异常捕获写作 except (ValidationError, Exception)，ValidationError 本就是 Exception 子类，该元组等价于裸 except Exception; 同文件其他解码边界（如 _handle_gateway_envelope 在 agent.py 对应侧）均有明确注释说明宽捕获的隔离意图，此处无注释，读者无法判断是有意全捕获还是笔误
  - Impact: 无功能影响（行为与全捕获一致且结果为关闭连接+1008），但会让后续维护者误以为 ValidationError 有特殊处理路径，也使静态检查工具对此文件的同类问题脱敏。
  - Fix: 改为 except Exception 并补注与同文件其他边界一致的隔离意图注释，或只捕获 (ValidationError, ValueError) 并为其余异常留日志。

- [Info][85] src/backend/cbrowser/gateway/server.py:68-683 — Gateway 全部路由处理器为 create_gateway_app 内的闭包，无法独立导入或单测，本单元亦无任何测试文件
  - ID: f_backend_stream_gateway_10; verification: static
  - Evidence: handle_agent_register / handle_viewer_signal / handle_supervisor_* 均为 create_gateway_app 内部闭包，捕获 registry、viewers、credentials、api 等每应用状态，模块级不可见; 构造应用必须先成功读取三份密钥文件并实例化 GatewayApiClient（server.py:80-91），轻量 handler 级测试也绕不开完整装配; 本单元 16 个文件经盘点全部为生产代码；其测试分布在其他审阅单元，本单元范围内无法自证覆盖
  - Impact: handler 级回归只能靠启完整应用的集成测试覆盖，编写与运行成本高，容易使身份 fence、节流、替换语义这类纯逻辑分支缺少快速回归网；属可测性结构观察，非现行功能缺陷。
  - Fix: 可将纯逻辑（身份比对、fence 判定、节流键构造）抽为可导入的模块级函数供 handler 调用与单测，handler 闭包只保留 I/O 编排。

## views

```json
{
  "contracts": {
    "reviewer": "e35fa667-d828-4d41-860f-1950ec937487",
    "status": "completed"
  },
  "correctness": {
    "reviewer": "e35fa667-d828-4d41-860f-1950ec937487",
    "status": "completed"
  },
  "design": {
    "reviewer": "e35fa667-d828-4d41-860f-1950ec937487",
    "status": "completed"
  },
  "documentation": {
    "reviewer": "e35fa667-d828-4d41-860f-1950ec937487",
    "status": "completed"
  },
  "performance": {
    "reviewer": "e35fa667-d828-4d41-860f-1950ec937487",
    "status": "completed"
  },
  "robustness": {
    "reviewer": "e35fa667-d828-4d41-860f-1950ec937487",
    "status": "completed"
  },
  "security": {
    "reviewer": "e35fa667-d828-4d41-860f-1950ec937487",
    "status": "completed"
  },
  "tests": {
    "reviewer": "e35fa667-d828-4d41-860f-1950ec937487",
    "status": "completed"
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
  "src/backend/cbrowser/gateway/server.py",
  "src/backend/cbrowser/stream_agent/__init__.py",
  "src/backend/cbrowser/stream_agent/agent.py",
  "src/backend/cbrowser/stream_agent/boundary.py",
  "src/backend/cbrowser/stream_agent/config.py",
  "src/backend/cbrowser/stream_agent/messaging.py",
  "src/backend/cbrowser/stream_agent/policy.py",
  "src/backend/cbrowser/stream_agent/policy_rules.py",
  "src/backend/cbrowser/stream_agent/protocol.py",
  "src/backend/cbrowser/stream_agent/x11_keymap.py"
]
```
