# 需求规范：Runtime 生命周期协调

本文描述 t005 实现行为，运行意愿协调由 t007 补充。入口鉴权、正式 Gateway、最终 Compose 与用户数据迁移仍由后续 task 交付；生效状态以 specs_index 和最终 task 验收为准。

## 权限与隔离

- API 是唯一 SQLite 写入者。Supervisor 经内部 Bearer RPC 获取不可变配置、绑定实例、上报观测和持久事件，不挂载数据库。只有 Supervisor 持有 Docker Socket。
- 每个 Profile 独立 Browser/Stream 容器、用户数据、Xauthority、Pulse 与网络；Stream 仅共享对应 Browser IPC，不挂用户数据或 Browser Agent Socket。挂载必须规范化并保持所属 Profile，路径穿越、链接逃逸和跨 Profile 别名被拒绝。
- Runtime 保持非 root、只读根、cap-drop ALL、restart policy no。启动前由临时 helper 在自有网络命名空间安装 IPv4/IPv6 策略，gate 确认实例、角色与 ready 标记后才执行业务入口。失败封闭，不修改宿主网络策略。
- Browser 公共目的地址可达，私有/保留地址默认拒绝，代理只按配置地址/端口例外；Stream 只允许实际 Gateway 端点、本实例 UDP mux 与显式白名单，并允许同机直连所需的已建立流量；私有/保留地址仍默认拒绝。独立 bridge 本身不构成隔离证明。

## 运行意愿协调

- 用户只经 `/api/v1` 设置运行意愿；API 持久化后经内部认证 RPC 驱动 Supervisor 真实启动/停止该 Profile 的 Browser/Stream，前端与测试不直调 Supervisor。
- Supervisor 不可达时运行意愿保留，错误经 API 响应与 SSE 显式报告；恢复后按退避重试收敛并清除错误。API 重启时对意愿与观测不一致的 Profile 重新收敛。
- 未配置 Supervisor 时 API 默认显式禁用协调并报告；`CBROWSER_REQUIRE_SUPERVISOR=1` 时缺失配置拒绝启动，生产部署必须启用。

## 生命周期与代际

- API 已记录 running 意愿后，Supervisor 读取指定不可变版本启动实例；配置失败不能猜默认值。Profile 锁串行生命周期请求，相同已运行实例启动返回现有会话。
- UDP mux 端口池为 30000–30991，Profile 独立分配且内外一致。耗尽返回明确错误；已绑定但尚未获得端口的实例通过稳定启动失败事件收敛，不释放其他 Profile 端口。
- Browser 就绪要求 Profile、实例、配置版本、真实 PID 和运行通道均匹配；Stream 必须完成 Gateway 注册后才报告 running。旧就绪文件不能让新实例提前成功。
- 停止携带 operation_id 和 runtime_instance_id。相同请求可重放，相同操作 ID 配不同请求冲突；旧代停止不终止新代。依次标记不可用、等待 Viewer 断开确认、停止 Stream、停止 Browser、删除所属网络，确认释放后回收端口。
- 重建 Browser 前先移除旧自有容器，再清理 Chromium singleton 锁链接。只移除已终止实例的临时入口，不跟随链接修改用户文件。

## 故障与恢复

- Native 事件按所属目录、Profile、实例与配置代际验证，落入持久 spool；API 按 event_id 去重和实例 fence 消费。正常退出清除运行意愿；异常退出保留意愿并累计实际失败数。
- 首次异常后按 2/10/30 秒各重试一次，三次重试均失败后 failure_count=4 并阻断。期限从 API 持久时间计算，Supervisor 重启不重新开始完整等待；失败计数和阻断仅以 API 为权威。
- 手动重试经 API 幂等事务解除阻断；旧手动操作重放不能绕过后来形成的新阻断。手动意愿变化可取消等待中的旧重试，不取消已经进入 Docker 创建的工作。
- API 离线、认证失败或 Docker 扫描失败时保留健康容器。Supervisor SIGKILL 重启后核对意愿、代际、策略 gate、实际端口与注册状态接管，正常停服不终止健康 Runtime。
- 已绑定实例但无对应 Browser 时，使用稳定 missing_runtime 事件收敛并进入正常退避；活跃 Profile 锁期间不合成退出。created/paused/restarting 不视为已退出。
- 已读取的 Native 退出事件即使首次上传失败，也优先于 Docker/missing 合成事件，防止正常退出被误记异常并重启。
- 启动独占锁内回收严格匹配归属的 cache-init/network-policy helper。周期扫描不回收临时 helper；网络清理遇未知端点失败，不强制断开其他对象。

## 停止结果、事件投递与默认搜索（t022）

- 停止命令的结果与观测分离：命令结果为 stopped（实际停止）/already_absent（确认不存在）/superseded_noop（目标已被新实例取代且不触碰新实例），同 operation 重放返回同一结果；消费方只按权威观测记录判定已停止，不把请求成功当作观测停止。生命周期冲突以类型化错误返回 409，端口耗尽 503。
- 诊断事件投递三态：已接受才推进业务状态；永久语义拒绝只入死信一次并持久推进游标；认证/限流/网关类失败为暂不可用，保持待投递重试。
- 默认搜索初始化与浏览器 readiness 分离（D1=B）：有界 best-effort 执行，结果以独立类型化状态呈现（applied/failed/disabled/pending）；失败不写成功 marker、不阻断启动。重试经 API→Supervisor→Agent UDS 的围栏通道（绑定当前实例、request_id 幂等），在 Runner 活 context 上执行，不重启浏览器；只有验证成功才记录成功，正常启动不覆盖用户后续手动选择。

## 基础设施替换后的持续收敛与分层观测（t026）

- 媒体网络固定端点规格：新建网络使用 Supervisor 分配的显式 subnet/ip_range，Gateway 附着在 range 外的固定端点；分配失败（池耗尽/冲突/端点被占/标签不符）显式失败，不退回随机地址。既有不合规网络经 Stream-only 替换重建迁移，Browser 容器、页面、IPC/X11 与 Profile 数据不变。
- 稳态收敛只修复漂移层：附着漂移只重新附着；Stream 策略漂移或可修复的未注册走有界 Stream-only 替换；Browser 策略漂移立即 fail-closed 并报告 error、不自动 teardown；协议级注册拒绝（版本/凭证/身份/载荷/实例未绑定）不替换并报 failed；Gateway 不可达只呈现 recovering。Stream 容器在跑但 Agent 已知未注册时不视为活跃对。
- API 失联期间只按标签/实例一致性恢复网络附着，不执行生命周期动作；readiness 在 API 不可用或任一状态未知时不报 ready。
- Supervisor 提供经内部认证的 reconcile_all 与 readiness（宿主机经容器内命令调用，无新增发布端口）；契约经 schema 导出与一致性测试锁定。
- 分层观测：运行响应与 SSE 暴露 browser/stream/transport 三层状态、版本与 build 标识、最近附着/注册/错误；仅内存保存，API 重启后为 unknown；按实例围栏呈现，异实例观测为 null。信令首次连接异常关闭在 transport recovering 时呈现恢复中，明确失败或超恢复窗口才失败。

## 存量沙箱恢复与升级自愈（t049）

- Supervisor 重启后的存量沙箱恢复是确定性单向流程：容器 label 与 API instance fence 校验 → policy_ready 宽限 → 从 Stream 容器端口绑定恢复 UDP mux 端口 → 实例化 session → 同一轮扫描立即收敛。恢复不读取 Gateway 业务可见性（visibility/注册状态），不因 Gateway 重建后返回 503 而中断。
- 媒体网络附着收敛独立于内存 session 与业务可见性：按 label 解析当前 Gateway 容器并附着到 Profile 合规媒体网络的固定端点，由 API 离线恢复路径与稳态收敛共用同一实现；媒体网络缺失或不合规仍走既有 Stream-only 替换预算，不对不合规网络执行挂载。
- Gateway 容器缺失或控制接口不可达时，存量 session 仍建立，transport 呈现 gateway_missing / gateway_unreachable，不拆除容器；重启后首个未注册读数按既有恢复宽限处理，避免立即替换健康的 Stream。
- 恢复不预置 running（t055）：Agent 健康未知时 session 为 starting，CDP 代理拒绝连接；Agent 健康确认后升级为 running 并上报。注册宽限自恢复时刻起算 90 秒，Gateway 不可见不重置（恢复专属标记，宽限内到达的新注册立即替换）；宽限到期后未注册 Stream 走 Stream-only 替换。
- 观测收口（t055）：Browser 容器查找失败（Docker API 故障）记日志，与“容器不存在”可区分；实例不匹配时观测报告全部异实例 id。媒体附着的 Gateway 解析失败转为 gateway_missing 状态，收敛继续；离线恢复遇非成功状态限频记日志。

## Profile 显示编号与沙箱身份（t050）

- 每个 Profile 有部署内唯一、永不复用的显示编号（0001、0002…），创建时分配；删除不复用、其余不重排。API 的 Profile/内部 runtime 响应暴露 `display_number`，Runtime Coordinator 启动请求携带 `profile_number`。
- 沙箱容器命名为 `<prefix>-<NNNN>-browser|stream`，带 `com.cbrowser.profile-number`；同一 Profile 停止/重启沿用同一编号与名称。容器发现、停止与清理以标签为准，不再依赖 UUID 命名。
- 全部沙箱显式归入聚合 compose 项目 `<prefix>-profiles`（t051 起 service 为 `<NNNN>-browser` / `<NNNN>-stream`，见下），Docker Desktop 单组呈现；部署 prefix 冲突检查以 instance-id 标签为唯一归属依据：派生项目容器只有 instance-id 标签等于本实例 id（或标签缺失且项目为本实例项目时）才识别为本实例自有资源，标签存在且不符时拒绝。

## 部署身份、沙箱归属与媒体网络超时（t051）

- **部署身份标签**：部署时为实例生成确定性 `instance_id`（`sha256("cbrowser-instance-v1\0<prefix>\0<data_root>")[:32]`），写入 release 状态；compose 服务与 Supervisor 创建的全部沙箱、helper、网络都带 `com.cbrowser.instance-id=<instance_id>`（部署身份键）。运行时实例 id 不走标签，写入容器运行时配置（Stream 环境变量 `CBROWSER_RUNTIME_INSTANCE_ID`、gated entrypoint `--instance-id`、Browser 命令 `--runtime-instance-id`），扫描/查找/回收经 `container_runtime_instance_id` 从配置读取。
- **归属唯一依据**：deploy.sh 的冲突判定与 Supervisor 的扫描都以「instance-id 标签值 == 本实例 instance_id」作为唯一归属依据，删除基于 project 名的豁免。伪造 project 标签但 instance-id 不符时拒绝；本实例沙箱缺少 instance-id 标签时不被认领（不采用、不删除）。
- **沙箱 service 编号**：两个不同编号的 Profile 同时运行时，各自 Browser / Stream 容器的 `com.docker.compose.service` 分别为 `<NNNN>-browser` / `<NNNN>-stream` 且互不相同，`com.docker.compose.project` 仍为 `<prefix>-profiles`。
- **前缀规则**：资源 prefix 须匹配 `^[a-z0-9][a-z0-9_]*$`（小写、数字、下划线，不含连字符），默认 `cbrowser`（deploy.sh 与 compose 的默认值；Supervisor/runner/docker_adapter 的默认前缀为 `cbrowser-t005`）；deploy.sh 与 Supervisor 启动都在执行任何 Docker 操作前校验，含大写、空格、斜杠或连字符时失败并提示。
- **媒体网络超时**：Docker 网络调用以超时为限（默认 30 秒，`CBROWSER_DOCKER_NETWORK_TIMEOUT` 可配）；挂起的调用使该次启动以明确错误失败，不阻塞其它 Profile 的网络创建。分配锁只覆盖 get+分配+预留阶段，不跨 Docker 创建持有；并发分配经预留子网集保证不同子网。创建冲突为错误，不重试。
- **启动独占锁内回收**：回收严格匹配 prefix、managed-by、角色、随机名称与 instance-id 的遗留 cache-init/network-policy helper；异部署或无 instance-id 标签的 helper 不回收。

## 运行错误收敛与控制发布（t056）

- **读错误不清错误（A26）**：读取运行错误（`get_last_error` / runtime 响应 / SSE 的 `last_coordinator_error`）是纯读，不清除已存错误；错误只在写路径清除。
- **清除绑定目标版本（A26）**：错误清除只发生在同一 `config_version` 的实例成功到达 running 时；清除判定为 `runtime.config_version >= 错误目标版本`（新版本成功可 supersede 旧版本错误，旧版本运行中不结算新版本错误；无目标版本的错误在任意 running 到达时清除）。失败时记录的错误带目标版本（启动失败的目标版本为当时最新版本）；后续同版本重试失败不丢弃已记录的目标版本。
- **控制续期先提交后发布（A2）**：控制租约续期升级（renew-upgrade）在事务提交成功后才发布控制变更事件；提交失败时不发布、不持久化升级。
- **下游错误严格解析（A15，t069 收紧）**：Coordinator 记录的下游错误只在响应体为合法 `ErrorResponse` 时保留其 `error` 与 `message`（格式 `"<error>: <message>"`），经 `last_coordinator_error` 呈现；旧形状 `detail`、纯文本体与缺字段响应判为协议错误并记稳定标记，不再解析为业务错误。observed-state 上报 422 单次定论，不再去字段降级重发。

## 资源策略

Supervisor 聚合实际主机与容器 CPU 窗口，按最紧 cgroup/cpuset 预算计算压力，结合真实前台可见性下发 Profile 级 FPS cap。缺失或失败样本不能当低负载，单个 Profile 采样或 RPC 失败不阻断其他 Profile；解除限制后由 Stream 活动策略决定恢复 8/30 FPS。全后台不误触发前台 cap，Viewer 心跳不建立控制租约。

## 跨服务中立模块与镜像边界（t062）

Gateway 与 Supervisor 的双向依赖已删除：端点/Origin、Agent 凭证、原子写、per-profile 锁、投递分类与实例 fence 收敛到中立包 `cbrowser/shared/` 各一份实现，全部消费方（含 REST 视图与协调器的 fence、两个投递转发器、三个锁持有方）改走同一实现；Supervisor 控制端口以 `DEFAULT_SUPERVISOR_PORT` 为唯一权威（8091 分裂消除）。认证返回领域会话对象、egress 探针 I/O 移出 domain。运行镜像按包粒度打包，闭包以 Dockerfile 组装文件树实际导入验证（单元层）；真实镜像构建与 readiness 属部署验证，顺延本地执行（见 task t062 的 AC-005 登记）。

## 控制面严格契约（t069）

- 错误响应只有 `ErrorResponse` 一种合法形状，解析唯一落点 `cbrowser/shared/error_response.py`：coordinator 下游透传、Supervisor 的 Gateway 可见性判定、agent_executor 控制调用全部经它；旧 `detail` 形状、裸文本与缺字段响应是协议错误，不作业务结果（可见性判未知、控制调用抛 `control_protocol_error`）。
- observed-state 上报单次定论：422 不再触发去掉 `browser_product`/`browser_user_agent` 的降级重发，失败不伪报收敛。
- 资源归属只认 `com.cbrowser.instance-id` 标签与配置的部署实例 ID 相等；未配置部署身份时不认领任何容器/网络，名称与前缀不再参与归属判定。

## 验证边界

验证分为单元/真实 HTTP、独立 Supervisor 与 API 进程、完整 Docker 容器图、网络内核正负对照、CPU 采样和官方 Chrome 实际帧数。各层证据不互相替代。完整部署和容量/P95/8小时/1000次输入验收仍按架构计划后续阶段执行；公网与原生 Linux x86_64 仅两项记为 USER_WAIVED。

## 代理认证转发器生命周期（t065）

- 启动顺序：网络 → 转发器 → Browser → Stream。转发器在 Browser 之前创建并等就绪（监听端口可连通）后才启动 Browser：Browser 的出站策略需在容器内以 Docker DNS 解析转发器名，Runner 在启动时读端点文件；任一环节失败即启动失败封闭，Browser 不启动，失败清理经 teardown 一并清除转发器。
- 凭据与端点文件：启动时凭据写 secret 目录（0600），端点文件写 runtime 目录（无秘密，冻结 credential_revision）；无代理时两者均删除，不留 stale 文件给下一代读到。
- 收敛：转发器缺失/退出而 Browser/Stream 仍在、且 API 意愿为 running 时，reconcile 只重建转发器（`_replace_proxy_forwarder_only`，与 Stream 替换同型预算：300 秒窗口内最多 3 次）；Browser 容器、Stream、Profile 数据、runtime 实例与端口均不动。
- 就绪：`_profile_readiness` 增加 `proxy-forwarder` 检查（有端点文件的 Profile 要求转发器 running，无端点文件时空过）与转发器策略复核（`proxy_forwarder_policy_spec`＋`verify_container_policy`）；`_confirm_sandbox_gone` 计入转发器角色。
- 停止：`stop_profile` 经 `teardown_profile` 清除转发器容器（与 Browser/Stream 同名清理的归属校验）。
