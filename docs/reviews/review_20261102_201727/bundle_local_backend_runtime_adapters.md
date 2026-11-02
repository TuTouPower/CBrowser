# bundle_local_backend_runtime_adapters

## responsibilities

- runtime_agent（进程内已核对实现）：在浏览器容器内运行的 UDS FastAPI Agent（agent.py：/health、/config_version、/control、/events/*、/cdp WebSocket 隧道）、BrowserRunner（runner.py：Xvfb/Openbox/PulseAudio 子系统拉起、CloakBrowser SDK 启动、PID/CDP 端口发现、退出观察与终态事件落盘）、CdpProxyManager（cdp_proxy.py：loopback CDP 命令/事件、下载捕获 rearm 与完成事件）、EventStorage（event_storage.py：原子 JSON 落盘、实例级 state journal + discovery cache、终态事件恢复）、profile_defaults（经 Playwright 操作 chrome://settings 把 Google 设为默认搜索引擎）、security.py（launch 参数清洗与 runtime id 校验）。
- adapters/database（已核对实现）：SQLAlchemy 2.0 async SQLite（WAL + busy_timeout=5000、BEGIN IMMEDIATE 写事务）之上的 ProfileRepository（Profile/版本快照/标签/Runtime 绑定与观察状态/幂等 operation_id/运行事件消费）、ArtifactRepository（产物元数据，注释声明 API 是唯一写方）、Alembic 迁移入口。
- adapters/filesystem/artifact_store（已核对实现）：每 Profile 的 uploads/downloads 文件存储——文件名清洗（含 Windows 保留名/非法字符/255 字节上限）、危险 content-type 拒绝、流式原子上传、下载导入与路径逃逸校验、运行 uid/gid 权限修正。
- services（已核对实现）：ProfileService（Profile CRUD 编排、DB 错误分类、duplicate 复制 user_data 并做全量 hash manifest 比对、reset 备份-替换-回滚、per-profile asyncio 锁）、ArtifactService（配额、上传、下载 ingest 去重与校验）。

## interfaces

- UDS HTTP/WS 契约由 runtime_agent/protocol.py 的 Pydantic 模型定义（extra=forbid），与 schemas/runtime/agent_protocol.json 逐字段比对一致（HealthResponse/ConfigVersionResponse/ControlRequest/ControlResponse/RuntimeEventRecord/DownloadEventRecord/RuntimeStateRecord），未发现漂移。
- runner 与 agent 进程间契约：runner_info.json（runner 写入、agent 轮询读取，含 profile_id/runtime_instance_id/config_version/cdp_port/browser_ws_url/browser_pid/runner_pid）+ events_dir 下 state.json、instances/<id>/state.json、events/runtime/<instance>/*.json、events/downloads/*.json。
- 仓储层对上接口：ProfileRepository/ArtifactRepository 的 async 方法与领域模型（cbrowser.domain.models 的 Profile/ProfileConfig/ProfileRuntime/ConfigVersionSnapshot/Artifact，属 backend_api_auth 单元）之间的转换函数 _to_domain_*。
- ProfileService 对 API 层暴露领域异常：ProfileNotFoundError/DatabaseLockError/StaleInstanceError/ConstraintViolationError/ProfileRunningError/ProfileOperationConflictError；ArtifactService 复用 artifact_store 的 Artifact* 异常族。

## dependencies

- 外部进程/工具：Xvfb、xauth、openbox、xdotool、xdpyinfo、pulseaudio、pactl（subsystems/runner 以 subprocess 调用，无 shell）。
- cloakbrowser SDK（launch_persistent_context_async、seed_widevine_hint、PLATFORM_CHROMIUM_VERSIONS）与 Playwright 私有对象（runner._sdk_driver_alive 读取 browser_context._impl_obj._connection._transport._proc）。
- SQLAlchemy async + aiosqlite + Alembic；FastAPI/uvicorn（UDS）；websockets。
- services/profile_service.py:27 顶层依赖旧后端模块 `from diagnostics import emit_runtime_event_log`（src/backend/diagnostics.py，非 cbrowser 包内模块，属 backend_core 单元）。

## flows

- 启动：supervisor 拉起 runner 进程 → BrowserRunner 校验 config snapshot → resolve_engine_binary 校验引擎缓存 ELF/版本 → 写 state=starting → Pulse/Xvfb/Openbox → 生成 chrome_wrapper.sh（捕获真实 PID 与退出码）→ SDK 启动 → 读 DevToolsActivePort 与 /json/version 得到 CDP 端口与 browser_ws_url → 写 runner_info.json + state=running → 后台 _wait_for_chrome_exit 观察退出并落终态事件/state。
- Agent：run_uds_agent 先查终态（terminal 则离线 replay 并 scan_completed_downloads），否则轮询 runner_info.json 后建 CdpProxyManager（连接 CDP、Browser.setDownloadBehavior allowAndName）→ UDS FastAPI（0660 socket）。外部 /cdp 客户端断开且曾发命令时自动 rearm + reconcile 下载。
- 下载完成：CDP downloadProgress(completed) → 校验 filePath 在下载目录内 → 计算 sha256 → DownloadEventRecord 落盘；reconciler 对目录内无匹配 (path,sha256) 事件的非临时文件补发 completed 事件，artifact 侧再由 ArtifactService.ingest_download 校验 sha/size、去重、import_download 搬入规范目录后写元数据，失败 restore_download 回滚。
- Profile 写路径：API → ProfileService（per-profile 锁）→ ProfileRepository 在 write_transaction(BEGIN IMMEDIATE) 内做 operation_id 幂等检查（audit_events.sig_hash）、版本递增与快照写入；运行事件经 consume_runtime_event 仅作诊断记录（注释明确声明生命周期权威在 supervisor 观察，防沙箱内伪造）。

## constraints

- launch 参数安全边界全靠 security.py 的前缀黑名单（RESERVED_PREFIXES + UNSAFE_FLAGS + control 字符正则）与 runner 内置参数拼接顺序（内置在前、用户参数在后）。
- runtime/profile id 文件名安全靠 RUNTIME_ID_PATTERN（[a-zA-Z0-9_\-.:]{1,128} 且排除 . 与 ..）与 EventStorage/artifact_store 的 resolve+is_relative_to 校验。
- SQLite 单写：busy_timeout=5000ms + BEGIN IMMEDIATE；写事务外的读走普通 BEGIN。
- 产物：单文件默认上限 256MiB、每 Profile 200 个/2GiB、磁盘预留 16MiB（ArtifactService/ArtifactStore 常量）；文件名清洗与 dangerous content-type 名单是唯一上传内容防线（无内容扫描）。
- 事件存储：runtime 事件每实例保留最新 100 条（按 mtime 修剪）；download 事件无修剪（见 findings）。

## decisions

- 退出真实性不依赖单一信号：runner 用 wrapper 的 wait 状态 + SDK driver 存活 + Xvfb 存活交叉判定，exit_code=0 且基础设施失效时改判 process_observation_lost（代码注释引用 d016）；agent /health 对 state=stopped 再以 PID 存活与 CDP 探活交叉验证，矛盾时不采信终态。
- Agent 与 Runner 分进程：Runner 崩溃后 Agent 仍能以离线 replay 模式提供终态与已完成下载（run_uds_agent 的 is_terminal 分支）。
- consume_runtime_event 只记诊断不驱动状态机（repository.py:639-641 注释），实例/版本不符的事件仍落库并返回 stale_instance/invalid_config_version 而非丢弃。
- reset/duplicate 的 operation_id 幂等：reset 用 operation_id 的 sha256 派生确定性 fingerprint_seed（同 operation 重放得到同 seed）；duplicate 以 audit source 字符串比对防 operation_id 串用。

## evidence

- src/backend/cbrowser/runtime_agent/security.py:12-67 前缀黑名单与 is_flag_safe 实现
- src/backend/cbrowser/runtime_agent/runner.py:399-441 内置参数与 sanitize_launch_args(cfg.launch_args) 的拼接顺序
- src/backend/cbrowser/runtime_agent/agent.py:218-231 /health 在 async handler 内同步调用 check_display/check_audio/check_browser
- src/backend/cbrowser/runtime_agent/subsystems.py:29-33,69-87 subprocess.run(timeout=1.5) 同步探活
- src/backend/cbrowser/adapters/database/repository.py:816-821 _to_domain_profile 硬编码 runtime_mode/viewer_mode
- src/backend/cbrowser/adapters/database/repository.py:288-367 update_profile 读取 runtime_mode/viewer_mode 进 merged_cfg 但回写字段清单中缺失这两列
- src/backend/cbrowser/runtime_agent/event_storage.py:132-139 save_download_event 无修剪，对照 107-116 行 runtime 事件修剪
- src/backend/cbrowser/services/profile_service.py:96-118 _apply_copy_ownership 非 root 回退 0o777/0o666
- schemas/runtime/agent_protocol.json 与 src/backend/cbrowser/runtime_agent/protocol.py:19-100 逐字段比对一致
- tests view completed by dedicated follow-up review (viewfix_backend_runtime_adapters_tests.json, reviewer e7bbbb5b-e936-4c9b-a778-6bee8d4c55ca): 本单元的测试总体扎实且多为行为级：EventStorage 原子写/损坏/并发/fsync 故障注入、ArtifactService 在真实迁移库+真实文件存储上验证原子上传/配额/MIME/去重/回滚、Profile copy/reset 验证幂等/并发同 key/清单比对/符号链接不跟随、下载对账与 E2E（AC-001~006、t008 重连对账、t013 克隆恢复 Cookie）均走真实路径，mock 只出现在 CDP 协作者与 HTTP 边界。但两个 High 级生产缺陷没有任何测试钉住安全行为：清洗器测试只枚举黑名单自身已列条目，f_01 的全部绕过类（--load-extension、位置型 URL、--fingerprint-* 等）在单元/集成/E2E 任何层级都无用例；/health 的用例只走探活快速失败路径，无任何用例断言事件循环不被阻塞（f_02）。此外 repo

## uncertainties

- 每 Profile 独占一个浏览器容器是架构声明（AGENTS.md/blueprint，未在本单元内核对 supervisor 的容器编排实现）；runner 内多处共享 /tmp 固定路径的实际影响取决于该部署事实是否恒成立。
- 本单元的测试文件不在分配范围内，tests 视角仅能确认 tests/unit 下存在对应测试文件，断言强度与 sanitizer 边界用例覆盖未核对。
- ProfileConfig 中 launch_args 的上游校验（API 层 schema）不在本单元，无法判断危险 flag 是否在进入 runner 前另有拦截；本单元内 runner 是最后一道且仅有黑名单。

## Findings

- [High][72] src/backend/cbrowser/runtime_agent/security.py:12-94 — launch 参数清洗是前缀黑名单，--load-extension、位置型 URL、--fingerprint-* 等危险参数可穿透
  - ID: f_backend_runtime_adapters_01; verification: static
  - Evidence: is_flag_safe 仅拦截 RESERVED_PREFIXES（11 个前缀）与 UNSAFE_FLAGS（8 个精确前缀），其余以 -- 开头的任意 Chromium 参数全部放行; --load-extension/--disable-extensions-except 不在任何名单中：可加载任意磁盘路径的扩展，绕过 ProfileConfig.extension_paths 的治理面，扩展在浏览器内拥有读取 cookie/页面的高权限; 不以 -- 开头的参数（如 file:///… 或任意 URL）只做 control 字符检查后原样放行，将作为 Chromium 启动页/位置参数传入; --fingerprint-* 家族（--fingerprint、--fingerprint-screen-width/height 等）未保留：用户参数在 runner.py:441 拼在内置参数之后，可覆盖 runner 在 414-415 行设置的屏幕指纹，造成指纹自相矛盾; runner.py:399 无条件内置 --no-sandbox，而 UNSAFE_FLAGS 又禁止用户传 --no-sandbox，说明设计意图是基础设施独占此类开关，但黑名单并未覆盖同类开关（如 --load-extension、--js-flags、--enable-features 任意特性）
  - Impact: 在以隐私隔离为核心卖点的产品中，Profile 配置（可能来自导入/API 调用方）可突破预期的参数治理：加载未审扩展、打开本地 file:// 页面、篡改指纹参数使隔离/指纹一致性失效。爆炸半径限于该 Profile 容器内，但正是该产品要防的边界。
  - Fix: 改为白名单或至少扩充黑名单：拦截 --load-extension/--disable-extensions-except、--js-flags、--enable-features/--disable-features 中的敏感项、全部 --fingerprint-* 前缀，并拒绝不以 -- 开头的位置参数（或单列允许的 URL 参数通道）；同步在 API 层（ProfileConfig 校验）前置拦截并补 sanitizer 边界测试。

- [High][95] src/backend/cbrowser/runtime_agent/agent.py:218-231 — /health 在 async handler 内同步执行 subprocess 与 HTTP 探活，阻塞事件循环并拖住 /cdp 隧道
  - ID: f_backend_runtime_adapters_02; verification: static
  - Evidence: get_health 直接调用 check_display/check_audio/check_browser，三者内部均为同步 subprocess.run（xdpyinfo timeout=1.5s、pactl 两次各 1.5s）与 urllib.request.urlopen(timeout=1.5s); 同一事件循环还承载 /cdp WebSocket 隧道转发（agent.py:323-376）与 CdpProxyManager 的事件监听；一次 /health 最坏可阻塞约 4.5s; 对照：同文件 /cdp/version 已用 asyncio.to_thread 包装同步 fetch（agent.py:303-309），说明 health 路径是遗漏而非既定风格
  - Impact: supervisor 周期性轮询 /health 时，CDP 自动化消息与下载事件处理被周期性冻结数秒，表现为自动化命令超时、画面/控制抖动；探活越多阻塞越久，且阻塞期间 health 本身也排队，放大延迟。
  - Fix: 将三个 check_* 改为 async（asyncio.create_subprocess_exec / to_thread 包装）或在 get_health 中以 asyncio.to_thread 并发执行三项探活；同步收紧单项 timeout。

- [Medium][97] src/backend/cbrowser/adapters/database/repository.py:816-821 — _to_domain_profile 硬编码 runtime_mode='docker'、viewer_mode='webrtc'，丢弃数据库中实际存储的值
  - ID: f_backend_runtime_adapters_03; verification: static
  - Evidence: _to_domain_profile 构造 ProfileConfig 时写死 runtime_mode="docker"、viewer_mode="webrtc"（repository.py:820-821），完全不读 m.runtime_mode/m.viewer_mode; create_profile 却按 config 写入这两列（repository.py:126-127），models.py:64-69 两列真实存在且有默认值; get_profile/list_profiles/update_profile 的返回都经此转换，非默认值在读路径上静默丢失
  - Impact: 任何以非默认 runtime_mode/viewer_mode 创建的 Profile，读回即变回 docker/webrtc；上层若据读回值做调度或展示将得到错误事实，且与 config 快照（原始 dict 保存）不一致，形成双口径。
  - Fix: _to_domain_profile 改为读取 m.runtime_mode/m.viewer_mode（与 domain 侧 Literal 对齐校验），并补一条非默认值的往返测试。

- [Medium][90] src/backend/cbrowser/adapters/database/repository.py:288-367 — update_profile 不回写 runtime_mode/viewer_mode 两列，但新版本快照却记录了新值，行与快照分叉
  - ID: f_backend_runtime_adapters_04; verification: static
  - Evidence: update_profile 把 p_model.runtime_mode/viewer_mode 读入 current_dict 并合并 patch 得到 merged_cfg（306-307 行）; 回写段（342-367 行）逐列赋值 name…sort_order、current_config_version、updated_at，唯独没有 p_model.runtime_mode = merged_cfg.runtime_mode 与 viewer_mode; 随后 snapshot_data 以 merged_cfg.model_dump() 落快照（390-398 行），即快照声称已应用新 mode 而 Profile 行仍是旧值
  - Impact: 通过 PATCH 修改 runtime_mode/viewer_mode 会返回成功且版本号递增，但实际未生效；以 Profile 行为准的消费者与以快照为准的消费者（如 runner 的 load_config_snapshot 读快照 config）将拿到不同配置，行为分叉且难以排查。
  - Fix: 回写段补齐两列赋值；或明确将这两列定为不可变并在 patch 合并前拒绝包含它们的请求，同时让快照与行保持同源。结合 f_03 一并修复并加往返/分叉回归测试。

- [Medium][88] src/backend/cbrowser/runtime_agent/cdp_proxy.py:146-175 — CDP 事件监听被单帧异常永久杀死且无重连，下载捕获静默失效
  - ID: f_backend_runtime_adapters_05; verification: static
  - Evidence: _listen_events 对每帧 json.loads(raw_msg)；非法 JSON、或 _handle_download_progress 中 int(params.get('receivedBytes')) 遇到非数值时抛 ValueError，均落入外层 except 后结束监听任务; 监听结束后 pending futures 被统一置 RuntimeError，但 manager 不重连 agent_ws、不重启监听；capture_alive 转 False 后仅 health 显示 degraded，无自愈路径; send_command 依赖同一监听分发响应，监听死亡后所有后续 CDP 命令只能超时
  - Impact: 一条异常 CDP 帧（或 Chrome 侧字段类型变化）即可让该实例的下载捕获、Browser.close、rearm 全部失效直至进程重启，且除一条 error 日志外无恢复动作。
  - Fix: 逐帧 try/except 隔离单帧解析/处理错误（记录后 continue）；监听异常退出时增加带退避的重连与 rearm 逻辑，或至少把 manager 标记为需 supervisor 重建实例的硬故障状态。

- [Medium][92] src/backend/cbrowser/runtime_agent/event_storage.py:132-150 — download 事件文件无任何修剪且每次枚举全量读取，长生命周期 Profile 下无界增长
  - ID: f_backend_runtime_adapters_06; verification: static
  - Evidence: save_download_event 每事件写一个 JSON 文件，无类似 _prune_runtime_events（107-116 行，runtime 事件保留 100 条）的上限; get_download_events 全量 glob+逐个 model_validate；download_reconciler.installed_download_keys 在每次 CdpProxyManager 初始化时全量调用它构建去重集; agent 的 GET /events/downloads 直接返回全部事件（agent.py:296-298）
  - Impact: 下载频繁的 Profile 运行数周后，events/downloads 目录可累积数万文件；每次 Agent 启动、每次事件列表请求都全量读盘+校验，启动与查询延迟随历史线性增长，inode 与磁盘占用无界。
  - Fix: 给 download 事件加保留策略（如每实例保留最近 N 条或按天数），或将去重索引改为增量维护的索引文件；/events/downloads 增加分页/游标。

- [Medium][90] src/backend/cbrowser/services/profile_service.py:96-118 — Profile 复制的权限回退分支把整个浏览器数据目录置为 0o777/文件 0o666（世界可读写）
  - ID: f_backend_runtime_adapters_07; verification: static
  - Evidence: _apply_copy_ownership：当 os.chown 失败且当前 euid 非 0、uid 又不是 1000 时，第二遍 walk 把所有目录 chmod 0o777、文件 chmod 0o666，且不复查 chown 是否其实已部分成功; 复制对象是完整 user_data_dir（含 Cookies、Login Data、Local Storage 等会话凭据材料）
  - Impact: 在非预期 uid 运行 API 进程的环境中，duplicate 出的 Profile 数据对同机所有用户/进程可读写，等于把浏览器会话凭据暴露给同机任意主体，与产品的隔离定位直接冲突。
  - Fix: 删除 0o777/0o666 回退：chown 失败应显式报错并终止复制（或在与运行时相同的 uid 下执行复制），宁可失败也不降级为世界可读写；如确需兼容，至少收紧为 0o700/0o600 并记录告警。

- [Medium][85] src/backend/cbrowser/services/artifact_service.py:44-90 — Artifact 配额检查与写入非原子（TOCTOU），并发上传可突破每 Profile 数量/字节上限
  - ID: f_backend_runtime_adapters_08; verification: static
  - Evidence: upload() 先 _check_quota 读 list_artifacts 计数与字节，再 write_upload + create_artifact，全程无 per-profile 锁（ProfileService 有 _locks，ArtifactService 没有对应机制）; _check_quota 的字节预检用 min(size_hint, max_artifact_bytes)，真实大小在写完后才以 used+size 复查，但计数上限（max_artifacts_per_profile）在写入后不再复查
  - Impact: 同一 Profile 并发发起 N 个上传时，每个都通过配额预检，最终数量与总字节可显著超过 200 个/2GiB 的上限，削弱多 Profile 间的磁盘公平与防滥用边界（磁盘总量仍有 check_space 兜底）。
  - Fix: ArtifactService 引入与 ProfileService 相同的 per-profile asyncio 锁串行化 upload/ingest，或在 create_artifact 的写事务内做配额断言（计数/求和后超限回滚）。

- [Low][80] src/backend/cbrowser/runtime_agent/runner.py:191-267 — PulseAudio/X11/Openbox 配置使用共享固定 /tmp 路径且无条件删除 X 锁，同机多 Runner 会互相破坏
  - ID: f_backend_runtime_adapters_09; verification: suspected
  - Evidence: setup_pulse 写死 /tmp/pulse-config/daemon.conf 与 /tmp/pulse.pa；setup_display 写死 /tmp/.X11-unix/cookie.hex、/tmp/openbox/rc.xml; setup_display 对 /tmp/.X{display_num}-lock 与 X socket 无条件 unlink(missing_ok=True) 后再启动 Xvfb（runner.py:276-278），且所有实例默认 display 同为 :99; 若两个 BrowserRunner 共享同一 /tmp（同容器多 Profile 或宿主机模式），后启动者会覆盖前者配置并删除其 X 锁/socket
  - Impact: 在'每 Profile 独占容器'部署下不触发；一旦容器复用或 runtime_mode 出现非 docker 形态，表现为随机音频/X 会话串扰或显示启动失败。属对部署假设的隐性强耦合。
  - Fix: 把 pulse/openbox/cookie 等路径收进各自 run_dir（或带 runtime_instance_id 的子目录）；删 X 锁前先校验锁内 PID 是否存活。

- [Low][90] src/backend/cbrowser/runtime_agent/runner.py:183-187 — PulseAudio cookie 与 Xauthority 以 0o644 落盘，容器内任意进程可冒用音频/X 会话
  - ID: f_backend_runtime_adapters_10; verification: static
  - Evidence: setup_pulse 生成 256 字节 Pulse 认证 cookie 后 cookie_path.chmod(0o644)（runner.py:186）; setup_display 对 xauth_path 先 touch(mode=0o644) 后又 chmod(0o644)（runner.py:235,258），X11 认证 cookie 明文可读
  - Impact: 同容器内任意 uid 的进程可读取 cookie 后连接 PulseAudio（窃听/注入音频通道）或凭 Xauthority 连接 X 显示（截屏/注入输入）。单租户容器下风险有限，但这与同文件其他位置刻意收紧权限（如 Agent socket 0660、目录 0750）不一致。
  - Fix: cookie 与 Xauthority 改 0o600（属主为运行时用户）；若 Selkies 等组件需跨 uid 读取，应改用组权限 0o640 + 共享组，而非世界可读。

- [Low][85] src/backend/cbrowser/adapters/filesystem/artifact_store.py:205-209 — ArtifactStore 的 artifact_id 未做路径组件校验，与 profile_id 的严格校验不对称
  - ID: f_backend_runtime_adapters_11; verification: static
  - Evidence: profile_dir() 对 profile_id 有 _PROFILE_ID 正则 + '..' 检查（artifact_store.py:176-179）; upload_target/download_target 直接以 artifact_id 拼路径（205-209 行），discard_upload 亦然；artifact_id 含 '/' 或 '..' 时可逃出 uploads/<id> 目录; 当前唯一调用方 ArtifactService 恒传 uuid4（artifact_service.py:72,182），故现行不可达，但适配器作为独立公开面缺少纵深防御
  - Impact: 未来任何以外部输入充当 artifact_id 的调用方（或内部重构）都会引入目录穿越，可覆盖/删除 Profile 产物目录外的文件（受 ensure_inside_profile 保护的仅是另一批方法）。
  - Fix: 在 upload_target/download_target/discard_upload 入口对 artifact_id 施加与 profile_id 同级的单组件校验，或统一走 ensure_inside_profile 断言。

- [Low][88] src/backend/cbrowser/runtime_agent/runner.py:389-395 — Runner 把 DISPLAY/XAUTHORITY/PULSE_*/CLOAKBROWSER_* 写入进程级 os.environ，污染宿主进程环境
  - ID: f_backend_runtime_adapters_12; verification: static
  - Evidence: start() 直接 os.environ[...] 赋值六个变量而非构造子进程 env；BrowserRunner 与 Agent 若同进程或未来多 Runner 同进程，后启动者覆盖前者; 这些变量还会泄漏给 runner 进程后续拉起的所有子进程（包括与浏览器无关的工具调用）
  - Impact: 当前一进程一 Runner 时无实际故障，但这是隐性全局状态耦合：单测/嵌入式调用/多实例演进时会产生难以追踪的环境串扰。
  - Fix: 改为显式 env 字典传给 SDK/子进程（launch_persistent_context_async 的 env 参数或 subprocess env），不再改 os.environ。

- [Low][92] src/backend/cbrowser/services/artifact_service.py:152-166 — ingest_download 对 sha256/size 不匹配静默返回 None 且无日志，调用方无法区分失败原因
  - ID: f_backend_runtime_adapters_13; verification: static
  - Evidence: ingest_download 中 source 不存在、sha256 不符、size 不符三种情况均 return None，全程无一行日志（artifact_service.py:152-161）; 对照同文件 upload 与 profile_service 的错误处理均有结构化异常/日志，此处把'文件缺失'与'校验失败（潜在篡改/数据损坏）'合并为同一无声结果
  - Impact: 下载产物偶发丢失时运维侧无任何线索区分是浏览器未写完、对账竞态还是校验不一致，排障成本高；校验失败本应是值得告警的完整性信号。
  - Fix: 三种分支分别记录结构化日志（profile、文件名、期望/实际 sha 与 size，sha 只记前后缀），或返回带原因的结果枚举供调用方上报。

- [Low][85] src/backend/cbrowser/services/profile_service.py:182-185 — ProfileService 的 per-profile 锁字典只增不减，长驻 API 进程内存缓慢泄漏
  - ID: f_backend_runtime_adapters_14; verification: static
  - Evidence: _locks: dict[str, asyncio.Lock] 以 setdefault 按 profile_id 创建（profile_service.py:182-185），全文件无任何删除/回收逻辑; Profile 被删除后其锁条目永久保留；Profile 数量大或频繁创建删除时单调增长
  - Impact: 单机长驻进程下为慢速小量泄漏（每条目约百字节级），同时该锁仅进程内有效——多 worker 部署时并不提供跨进程互斥（真正的互斥实际靠 DB 的 BEGIN IMMEDIATE），容易给人错误的安全感。
  - Fix: delete_profile 后清理对应锁条目，或改用带引用计数/弱引用的锁注册表；并在文档中注明跨进程互斥由 DB 事务承担。

- [Low][80] src/backend/cbrowser/adapters/database/repository.py:56-211 — 幂等回放逻辑在 create/update 与 IntegrityError 兜底中四处复制，同形分支易漂移
  - ID: f_backend_runtime_adapters_15; verification: static
  - Evidence: create_profile 的事务内幂等检查（91-103 行）与其 IntegrityError 兜底（192-211 行）几乎同构；update_profile 同样成对出现（247-258 行、402-419 行）; 四处都做 json.loads(audit.details) + sig_hash 比对 + 返回既有实体，任一处的语义修订（如 details 结构变化）都要同步四处
  - Impact: 维护性风险：已有迹象显示兜底路径与主路径细节不完全一致（如 create 兜底只查 ProfileModel 是否存在而主路径还依赖 audit.entity_id），后续修改容易只改一处造成幂等语义不一致。
  - Fix: 抽出单一 _replay_if_committed(operation_id, sig_hash, loader) helper 供四处共用，并为四条路径各保留一条幂等回归测试。

- [Info][75] src/backend/cbrowser/adapters/database/migrations.py:30-41 — 迁移入口在一次性连接上设置 busy_timeout/foreign_keys 不生效，注释声称的配置与实际不符
  - ID: f_backend_runtime_adapters_16; verification: static
  - Evidence: run_database_migrations 打开 sqlite3 连接执行 PRAGMA busy_timeout=5000 与 foreign_keys=ON 后立即 close，再由 Alembic 以自己的连接 upgrade; busy_timeout 与 foreign_keys 均为 per-connection 设置，随连接关闭即失效；只有 journal_mode=WAL 因持久化到数据库文件而生效; 模块 docstring 与函数注释称'Configures database with WAL and busy_timeout=5000'，与实际效果不符
  - Impact: 无直接功能故障（运行时连接由 session.py 的 connect 事件正确设置这两项），但文档/注释给出错误保证，后续维护者可能误以为迁移连接也受 busy_timeout 保护，在并发迁移时遇 locked 报错无从预期。
  - Fix: 删除无效的 busy_timeout/foreign_keys 预配置或改在 Alembic env 的 connect 事件中设置，并修正注释为仅 journal_mode 持久化。

- [Info][70] src/backend/cbrowser/runtime_agent/agent.py:316-321 — /cdp WebSocket 与 /control 在 UDS 上无应用层鉴权，安全完全依赖 socket 文件权限
  - ID: f_backend_runtime_adapters_17; verification: static
  - Evidence: create_agent_app 的全部端点无 token/签名校验；防护仅为 run_uds_agent 中 sock 0660 + 父目录 0750 + umask 077 绑定（agent.py:470-484）; /cdp 可转发任意 CDP 命令（含 Browser.close、下载行为控制），/control 可关闭浏览器
  - Impact: 设计边界记录：任何能打开 agent.sock 的同 uid/gid 进程即拥有完整 CDP 控制权。若容器内浏览器沙箱进程与 Agent 同 uid 运行，沙箱逃逸到同 uid 即直达控制面；当前是否同 uid 取决于 supervisor 的容器用户配置（不在本单元）。
  - Fix: 维持现状亦可，但建议在部署侧确认 runner/agent 与浏览器进程不同 uid；或在 UDS 之上加一层 per-instance token（runner_info 同目录下发、Agent 校验）以获得纵深防御。

- [High][92] tests/unit/test_runtime_agent.py:29-77 — 清洗器测试只枚举黑名单自身条目，f_01 的全部绕过类在任何层级都无测试钉住安全行为
  - ID: f_backend_runtime_adapters_18; verification: static
  - Evidence: test_launch_args_security_sanitization 的三个名单与 security.py 的 RESERVED_PREFIXES/UNSAFE_FLAGS 一一对应（reserved 甚至只测 11 条中的 8 条，缺 --remote-debugging-targets 与 --headless），本质是把实现名单抄进测试：名单删条目测试才红，名单外的新绕过永远绿; 全仓 grep 确认：没有任何测试把 --load-extension/--disable-extensions-except、--js-flags、--fingerprint-* 或不以 -- 开头的位置参数（如 file:///…、https://…）喂给 is_flag_safe/sanitize_launch_args 并断言被拒；test_runtime_persistence_guards.py 的补充用例同样只围绕 IsolateOrigins 与控制字符; 该用例的 safe 名单还把 --enable-features=CDPScreenshotNewSurface 断言为应放行，等于把 f_01 修复方向点名的 --enable-features 通道在测试里钉为预期行为，后续收紧会被此断言挡回; 上游无第二道防线：domain/models.py:69,260,307,364 的 launch_args 只是无校验的 list[str]，api/v1/router.py:188 原样透传，runner.py:380 的 sanitize_launch_args 是唯一关口；集成用例 tests/integration/test_v2_api_subprocess.py:201 只用 [--no-first-run, --disable-sync] 良性参数，E2E 全部快照不设 launch_args
  - Impact: f_01 的绕过在测试套件中完全不可见：当前实现全绿，且未来任何人删改/重构清洗逻辑时，扩展加载、指纹覆盖、位置型 URL 这三类真实攻击面都没有回归网。测试给出的安全感与名单自证成正比，与实际边界强度无关。
  - Fix: 为清洗器补绕过类用例集（扩展加载族、--js-flags、--enable-features 中的敏感特性、全部 --fingerprint-* 前缀、位置参数/URL、大小写与 = 变体），先以期望被拒写红，再随 f_01 的白名单化修复转绿；同时把 safe 名单中的 --enable-features 通用放行断言改为按收紧后的契约逐项声明。

- [Medium][90] tests/unit/test_runtime_agent.py:199-220 — /health 非阻塞行为无任何测试：单元用例只走探活快速失败路径，E2E 只断言健康内容不断言并发响应性
  - ID: f_backend_runtime_adapters_19; verification: static
  - Evidence: test_subsystem_checks_negative 只覆盖 socket 不存在、cookie 尺寸错、cdp_port=0/死 PID——三条路径都在执行 subprocess/urlopen 之前或以连接拒绝立即返回，探活的慢路径（xdpyinfo/pactl 各 1.5s 超时、urlopen 1.5s）从未被行使; test_agent_app_routes 对 /health 的调用发生在 display/audio socket 缺失时，get_health 内的同步探活同样立即失败返回；test_runtime_agent_faults.py 的 /health 用例只断言 503 语义; E2E AC-002 杀 PulseAudio/Xvfb 后断言 /health 内容变 degraded，但全程不并发发 /cdp 或第二个 /health 请求，事件循环被同步探活凍结数秒（f_02）在 E2E 中同样不可见; 对照同仓 tests/unit/test_docker_offload.py（兄弟单元）对事件循环卸载有专门的时序断言，说明该仓有测非阻塞的先例，runtime agent 侧缺失是覆盖空白而非风格
  - Impact: f_02 的阻塞在当前套件下全绿：即使有人把 /cdp/version 已有的 asyncio.to_thread 写法也回退成同步调用，也没有任何测试会失败。supervisor 轮询 /health 期间 CDP 隧道被冻结数秒的故障模式只能靠线上体感发现。
  - Fix: 补一条 /health 并发响应性用例：以可控慢探活（monkeypatch subprocess.run 睡眠或假 xdpyinfo/pactl 脚本）让单次探活耗时 ~1s，同时并发请求 /config_version 或 /cdp/version，断言其延迟显著小于探活时长；f_02 修复（to_thread 化）后该用例应转绿并常驻。

- [Medium][95] tests/unit/test_domain_and_repository.py:99-124 — runtime_mode/viewer_mode 往返测试数据与硬编码常数相同，f_03/f_04 的数据丢失结构性不可见
  - ID: f_backend_runtime_adapters_20; verification: static
  - Evidence: test_profile_crud_and_full_legacy_fields_roundtrip 构造 ProfileConfig 时 runtime_mode='docker'、viewer_mode='webrtc'（109-110 行），正是 _to_domain_profile 在 repository.py:820-821 写死的两个值; 该用例随后断言 fetched.config == config（138 行）与 update 后字段正确，但 update 的 model_copy 只改 name/color_scheme/screen_width（146-152 行），全程没有任何非默认 mode 出现，create/update/get/list 四条路径都测不到 f_03 的读回丢失与 f_04 的行/快照分叉; 全仓 grep 确认 tests/ 下再无第二处给 runtime_mode/viewer_mode 赋非默认值
  - Impact: 这是典型的『测试数据与 bug 常数重合』盲区：字段覆盖看起来完整（全字段往返断言），实际对这两个字段的断言强度为零。f_03/f_04 若回归或长期不修，套件永远全绿，使用者会误以为 mode 字段已被往返测试保护。
  - Fix: 把该往返用例的 mode 改为非默认值（或参数化加一组非默认组合），并补一条 PATCH 只改 viewer_mode 后 get 与最新快照一致的断言；随 f_03/f_04 修复一并落地。

- [Low][88] tests/unit/test_artifact_service.py:104-118 — Artifact 配额只有串行用例，f_08 的并发 TOCTOU 无测试覆盖
  - ID: f_backend_runtime_adapters_21; verification: static
  - Evidence: test_quota_and_mime_are_enforced 与 test_profile_byte_quota_is_enforced_after_streaming 均为严格串行 await 调用，并发交错下 _check_quota 与写后复查之间的窗口从未被行使; 全文件 grep 无 asyncio.gather/并发上传用例；copy/reset 侧已有同 key 并发用例（test_profile_copy_reset.py），说明并发覆盖在 services 层并非一贯缺失，唯独 ArtifactService 空白
  - Impact: f_08 的配额突破（并发 N 个上传同时过预检、计数上限写后不再复查）在套件中不可见；后续给 ArtifactService 加锁或把配额断言下沉事务时也没有回归网验证语义不变。
  - Fix: 补并发用例：以 max_artifacts_per_profile=2 并发发起 4 个 upload，断言成功数不超过上限且 list 结果与磁盘文件一致；随 f_08 修复转绿。

- [Low][90] tests/unit/test_artifact_service.py:354-367 — artifact_id 路径组件校验（f_11）无测试：穿越型 artifact_id 从未被喂给 store 的三个拼接入口
  - ID: f_backend_runtime_adapters_22; verification: static
  - Evidence: 本文件的穿越类用例只有两条：test_store_rejects_profile_id_path_traversal（profile_id）与 test_download_source_rejects_paths_outside_the_downloads_directory（下载源路径）; grep 确认 tests/ 全仓没有任何用例引用 upload_target/download_target/discard_upload，更没有以含 '/' 或 '..' 的 artifact_id 调用它们；f_11 指出的与 profile_id 不对称的校验缺口在测试侧同样不对称
  - Impact: 当前唯一调用方恒传 uuid4 使 f_11 不可达，但适配器作为独立公开面，未来调用方以外部输入充当 artifact_id 时无任何测试能拦住目录穿越回归；且修复 f_11 时也缺现成的红用例锚点。
  - Fix: 对三个入口各补一条以 '../escape'、'a/b' 为 artifact_id 的拒绝用例，与 profile_id 用例并列；随 f_11 修复落地。

## views

```json
{
  "contracts": {
    "reviewer": "e2f8cc1f-7c6f-4f68-bbf5-3fca891adbc7",
    "status": "completed"
  },
  "correctness": {
    "reviewer": "e2f8cc1f-7c6f-4f68-bbf5-3fca891adbc7",
    "status": "completed"
  },
  "design": {
    "reviewer": "e2f8cc1f-7c6f-4f68-bbf5-3fca891adbc7",
    "status": "completed"
  },
  "documentation": {
    "reviewer": "e2f8cc1f-7c6f-4f68-bbf5-3fca891adbc7",
    "status": "completed"
  },
  "performance": {
    "reviewer": "e2f8cc1f-7c6f-4f68-bbf5-3fca891adbc7",
    "status": "completed"
  },
  "robustness": {
    "reviewer": "e2f8cc1f-7c6f-4f68-bbf5-3fca891adbc7",
    "status": "completed"
  },
  "security": {
    "reviewer": "e2f8cc1f-7c6f-4f68-bbf5-3fca891adbc7",
    "status": "completed"
  },
  "tests": {
    "status": "completed",
    "reviewer": "e7bbbb5b-e936-4c9b-a778-6bee8d4c55ca"
  }
}
```

## files_reviewed

```json
[
  "src/backend/cbrowser/adapters/database/artifact_repository.py",
  "src/backend/cbrowser/adapters/database/migrations.py",
  "src/backend/cbrowser/adapters/database/models.py",
  "src/backend/cbrowser/adapters/database/repository.py",
  "src/backend/cbrowser/adapters/database/session.py",
  "src/backend/cbrowser/adapters/filesystem/artifact_store.py",
  "src/backend/cbrowser/runtime_agent/__main__.py",
  "src/backend/cbrowser/runtime_agent/agent.py",
  "src/backend/cbrowser/runtime_agent/cdp_proxy.py",
  "src/backend/cbrowser/runtime_agent/download_reconciler.py",
  "src/backend/cbrowser/runtime_agent/event_storage.py",
  "src/backend/cbrowser/runtime_agent/profile_defaults.py",
  "src/backend/cbrowser/runtime_agent/protocol.py",
  "src/backend/cbrowser/runtime_agent/runner.py",
  "src/backend/cbrowser/runtime_agent/security.py",
  "src/backend/cbrowser/runtime_agent/subsystems.py",
  "src/backend/cbrowser/services/artifact_service.py",
  "src/backend/cbrowser/services/profile_service.py"
]
```
