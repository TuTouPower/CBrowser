# 决策记录（ADR）

只记录已经确认、影响后续工作的非显然决策。追加新条目，不重写历史；决策被替代时，新条目通过“替代”字段引用旧编号。

每条结构：`## NNN 标题（YYYY-MM-DD）`，下接 `- 背景` / `- 选项` / `- 结论` / `- 替代` 四项；替代填旧编号，无则写「无」。

## 产品历史勘误入口与 ADR 传播约定（t024）

- 历史审阅/决策文档的事实勘误集中在独立勘误文件中，冻结原文不改：第一轮全仓审阅见 `docs/reviews/review_20261102_201727_errata.md`。跨轮引用一律使用「报告路径 + finding ID」，不使用裸编号。
- ADR 传播清单约定：新增或替代 ADR 时，同一变更须同步核对并更新受影响的现行文档面 —— `docs/blueprint/` 对应主题文件、`docs/specs/` 生效 spec、`docs/plan_v2_architecture_.md` 的对应节标注、相关 findings 的后续标注与 `docs/handoff.md` 现行一节；已归档 task 的原 AC 不改，只在勘误中指向替代关系。

## 001 采用独立 Docker 容器实现多 Profile 强隔离（2026-10-26）

- 背景：单进程或单容器共享 X 显示服务容易出现环境污染、端口竞争、指纹泄露及崩溃连锁反应。
- 选项：
    1. 所有 Profile 跑在单 Manager 容器的不同虚拟显示上。
    2. 每一个 Profile 启动独立 Docker 容器沙箱。
- 结论：采用选项 2。每个 Profile 分配专用容器，挂载独立数据目录，彻底切断进程间共享资源与非法访问。
- 替代：无

## 002 全面切换为 Selkies 2.1.0 WebRTC 架构并移除 VNC/RFB（2026-10-26）

- 背景：原系统采用 noVNC + KasmVNC 链路，后端需维护复杂的 RFB 消息解析、过滤与剪贴板转换逻辑，延迟高且维护负担重。
- 选项：
    1. 优化现存 noVNC/RFB 实现并继续维护兼容层。
    2. 固定官方 Selkies 2.1.0 发布版本，采用纯 WebRTC + ICE/TURN 传输。
- 结论：采用选项 2。移除全部旧 RFB/VNC 兼容层代码，画面低延迟编码与媒体传输由成熟 WebRTC 框架托管。
- 替代：无

## 003 采用 Google Chrome 外部标签页作为唯一官方管理载体（2026-10-26）

- 背景：自建前端标签页管理器在模拟浏览器多标签时容易与内部网页的标签产生层级混乱，且无法利用原生浏览器的进程隔离与快捷键。
- 选项：
    1. 在 React 前端绘制虚拟外层标签栏并内嵌多个 iframe/Canvas。
    2. 外部完全由 Chrome 原生标签页管理，每个操控页只承载对应 Profile 的真实窗口。
- 结论：采用选项 2。严格区分外部 Chrome 标签页与内部 CloakBrowser 原生标签页，消除 UI 嵌套冗余。
- 替代：无

## 004 采用 SQLite WAL + Alembic 作为单机持久化方案（2026-10-26）

- 背景：CBrowser 定位为单机 Docker 部署的隐私浏览器控制平台，写入端唯一受 Control API 调度，无需分布式数据库开销。
- 选项：
    1. 引入外部 PostgreSQL 或 Redis。
    2. 使用嵌入式 SQLite，启用 WAL 模式并配合 Alembic 进行版本化迁移。
- 结论：采用选项 2。极简运维，单文件备份，性能与并发满足单机高可用需求。
- 替代：无

## 005 不在 Python API 中逐帧转发媒体数据（2026-10-26）

- 背景：旧架构通过 FastAPI WebSocket 逐帧处理 RFB 图像与剪贴板二进制，高并发时 CPU 负载极高。
- 选项：
    1. 继续由 Python 后端代理媒体流。
    2. WebRTC 媒体流直接在客户端与运行时容器/TURN 之间直连，API 仅负责信令交换与短期鉴权。
- 结论：采用选项 2。API 脱离媒体流转发路径，保障高并发下的性能与稳定性。
- 替代：无

## 006 操控页面禁止绘制虚拟浏览器边框与外层标签栏（2026-10-26）

- 背景：用户在远程操控隐私浏览器时，若操控页内嵌另一套地址栏与外层标签栏，会导致快捷键与鼠标焦点冲突，视觉混乱。
- 选项：
    1. 前端保留工具条与快捷标签栏。
    2. 操控页面无边框铺满显示真实 CloakBrowser 窗口。
- 结论：采用选项 2。所有配置与管理收纳在 `/manage`，操控页纯净显示远程画面。
- 替代：无

## 007 冻结双容器 WebRTC 目标架构、废弃排他控制租约与定案本地运行基准（2026-10-27T18:50:00+08:00）

- 背景：早期设计中预设单 Profile 单容器运行、排他控制租约（`ControlSession`、心跳超时、抢占接管等待）、60 FPS 恒定帧率、未经验证的 300ms 画面恢复指标，并假设 Selkies 2.1.0 具备原生公共 ICE restart API 及以远端 Linux x86_64 服务器为基准。t001 技术验证（s001–s009, d001–d014）与 2026-10-27 用户执行调整（跳过公网/Linux x86 验证，基准改为当前电脑 Docker + 本机 Chrome 访问）提供了确定性事实与调整依据。
- 选项：
    1. 维持旧设计的单容器与独占控制租约模型，继续假设无 GPU 下恒定 60 FPS 并等待远端 Linux 服务器验证。
    2. 冻结经验证的目标架构：
        - 采用同 Profile 双容器（Browser Runtime 显式 `shareable` IPC 与 Stream Runtime 加入），基于专属卷 X11 Socket 与 MIT-SHM 零拷贝捕获，彻底切断媒体容器对浏览器用户数据的直接挂载；
        - 彻底废弃独占控制租约与接管锁，多外部页面（ViewerConnection）以 `controller` 角色并发解码与输入，依靠官方 `client_tab_id`、Web Locks 与 `resume_key` 维持页面身份与重连；
        - 采用单 Profile 单一共享编码管线，执行 8/30 FPS 自适应仲裁与全后台暂停捕获；
        - API 为唯一 SQLite 写入者，Supervisor 为唯一 Docker Socket 持有者，经受控 UDS 隔离代理 CDP 与事件；
        - 明确 Selkies 2.1.0（commit `6ee68a7a`）同 PC 凭证轮换依赖进程内私有接口适配器（属于内部维护约束，非官方原生 public API）；
        - 将目标部署基准定案为当前 MacBook Pro M1 Max 上的 OrbStack Docker（10 CPU / ~15.66 GiB RAM，CPU 纯软件编码无 GPU 预算）配合本机 Chrome 访问；公网与原生 Linux x86_64 验证明确记为 `NOT_RUN / USER_WAIVED`。
- 结论：采用选项 2。正式冻结目标架构。（t001 时点：当时生产代码尚未实现该目标仍保持旧基线，后续任务（t002+）据此实施；现行架构已落地，状态见现行蓝图。）
- 替代：001（细化并替代单容器沙箱假设为双容器 shareable IPC 隔离）；明确废弃早期计划中关于独占控制租约、恒定 60 FPS 及 300ms 恢复假设。

## 008 区分首次异常与三次自动重试计数（2026-10-30T01:05:04+08:00）

- 背景：架构计划要求异常后完整执行2/10/30秒三次自动重试。原始失败总数在3时阻断会只执行两次重试，与三档等待冲突。
- 选项：
    1. 首次异常算入三次，实际只重试两次。
    2. 首次异常后执行三次重试，持久字段继续记录实际异常总数。
- 结论：采用选项2。failure_count依次为1/2/3时分别等待2/10/30秒，第4次异常阻断；API与Supervisor共用domain/runtime_policy常量。正常启动不清历史，手动重试通过API幂等事务清除阻断。数据库字段结构不变，当前仅隔离测试数据；正式用户数据迁移仍由t010负责。
- 替代：无；明确架构计划中“连续3次失败”指三次自动重试均失败。

## 009 Runtime 网络命名空间策略与启动门禁（2026-10-30T02:31:12+08:00）

- 背景：当前 OrbStack 的普通 bridge 实测跨网可达；internal bridge 对照会改变上网能力，不能直接满足 Browser 外网与 Stream 媒体需求。代理因素尚未证实。
- 选项：依赖普通 bridge；更改全局 OrbStack 配置；或在 Runtime 自有网络命名空间安装明确策略。
- 结论：采用第三项。Supervisor 使用同一镜像运行临时 NET_ADMIN helper，业务进程由实例/角色 gate 阻止提前执行。Browser/Stream 自身权限不变，常驻沙箱仍为两个；无宿主 namespace 或全局规则修改。策略按真实地址和端口最小放行，IPv4/IPv6 同时安装，拒绝覆盖未知 filter 状态。
- 替代：不再以独立 bridge 名称直接推导跨 Profile 隔离；独立网络与严格归属仍用于拓扑和生命周期管理。正式整体验收以当前源镜像和真实连接证据为准。

## 010 Gateway 以 API 绑定判定实例、Stream 侧 TURN 地址由 Agent 注册上报（2026-10-30T21:00:00+08:00）

- 背景：Gateway 是全局服务，需要拒绝过期 Stream 实例的注册，并为每个 Profile 生成 Stream 侧 TURN 配置；但 Gateway 不持久化状态、不访问数据库，也无法得知各 Profile 媒体网络内 coturn 的实际地址。计划 10.3 禁止依赖多网卡 DNS 解析 coturn。
- 选项：
    1. Supervisor 另行向 Gateway 推送期望实例与 coturn 地址。
    2. Gateway 注册时查询 API 持久绑定判定当前实例；Stream Agent 注册时上报 Supervisor 已下发给它的 coturn 实际地址（`turn_host`/`turn_port`），Gateway 只签发凭证并在下发时组装 URL。
    3. Gateway 配置全局 Stream 侧 TURN URL。
- 结论：采用选项 2。实例真相只有 API 一处，Gateway 重启后仍可判定；Agent 上报的地址只影响其自身配置。删除全局 `CBROWSER_TURN_STREAM_URLS` 及 `turn:coturn` 默认值。
- 替代：无

## 011 Chrome 在容器内以 `--no-sandbox` 运行并依赖容器边界（2026-11-01T10:13:32+08:00）

- 背景：CloakBrowser/Chrome 自带沙箱依赖 user namespace 或 setuid helper；当前 Browser Runtime 以 UID 1000 非 root、只读根文件系统、`cap-drop ALL` 与 `no-new-privileges` 运行，不启用浏览器沙箱，以避免为此放宽容器权限。Runtime Agent 固定注入 `--no-sandbox`，用户 `launch_args` 中的同名标志被安全白名单拒绝。
- 选项：
    1. 放宽容器权限以启用 Chrome 沙箱（privileged、额外 capabilities 或可写/特权 helper）。
    2. 继续使用 `--no-sandbox`，把隔离责任交给容器边界。
- 结论：采用选项 2。容器边界补偿：非 root UID 1000、只读根文件系统、`cap-drop ALL`、`no-new-privileges`、禁止挂载 Docker Socket、每 Profile 独立容器/网络/卷，且仅 Supervisor 可创建容器。残余风险：Chrome renderer 逃逸不再由浏览器沙箱拦截，可影响同容器内的 Xvfb、PulseAudio、Browser Agent 及本 Profile 挂载数据；跨 Profile 仍由容器、网络与卷边界阻断。`--no-sandbox` 只允许由 Runtime Agent 在受管容器内注入，严禁在宿主机或容器外运行 Chrome 时使用。
- 替代：无

## 012 剪贴板开启时采用 Selkies seamless 双向自动同步（2026-11-02T20:09:33+08:00）

- 背景：t014 为保护本机原剪贴板锁定 `clipboard_seamless=false|locked`，结果本机与远程浏览器之间不能直接 Cmd+C/V，只能经 Selkies 侧栏剪贴板框手动搬运。CBrowser 仅供单一用户在本机使用。
- 选项：
    1. 保持 seamless 关闭，只经侧栏剪贴板框显式传输。
    2. Profile `clipboard_sync` 开启时使用 Selkies seamless 双向自动同步，服务端锁定。
- 结论：采用选项 2（用户决定）。`SELKIES_CLIPBOARD_SEAMLESS=true|locked`；`clipboard_sync` 关闭时 `enable_clipboard=false`，双向仍无传输；二进制剪贴板保持 `false|locked`。接受的代价：会话页获得焦点时本机剪贴板内容会发往该 Profile 的远程浏览器，远端复制会覆盖本机剪贴板；需要隔离的 Profile 关闭 `clipboard_sync`。原计划 19.3「用户剪贴板原内容保护」「后台页面不自动覆盖本机剪贴板」作废。
- 替代：t014 的 seamless 关闭策略。

## 013 单机单人部署包络与同机直连媒体链路（2026-11-02T22:00:00+08:00）

- 背景：CBrowser 的唯一目标是同一台 Mac 上的单一用户；原架构仍按多主机流媒体服务维护 coturn、TURN 凭证轮换与同 PeerConnection 的 ICE 代次接管，后者依赖 Selkies 2.1.0 私有 ABI，且是本轮多条缺陷来源。s011/d026 在真实 Chrome + OrbStack 上验证同机 `127.0.0.1` host 候选直连可覆盖多页面、复制标签、刷新、关闭首个页面、可见性暂停/恢复、Viewer 断线 resume、音视频、键鼠与中文输入。
- 选项：
    1. 保留 coturn、短期凭证轮换与 ICE 代次接管，继续为未存在的多主机场景付费。
    2. 删除 coturn、TURN 凭证与轮换、ICE 代次接管与 Selkies 私有 ABI 补丁，媒体只走同机直连；Gateway 收缩为 Agent 注册、信令路由与可见性/配额控制。
- 结论：采用选项 2。Stream 容器 UDP mux 发布到 `127.0.0.1`，客户端与服务端均不下发 TURN 配置；公网、NAT 穿透与原生 Linux x86_64 明确不在需求范围（用户豁免）。该决定替代 010 的 TURN 凭证与地址上报机制；部署拓扑（t012）不再包含 coturn。
- 替代：010

## 014 运行时数据统一归属 uid 1000，删除全局可写回退（2026-11-03T02:00:00+08:00）

- 背景：Profile 复制、Supervisor 引擎缓存与开发路径曾以 0777/0666 回退兼容 macOS 非 1000 uid，导致 Cookie、登录态与运行时文件对宿主其他用户可读写。
- 选项：
    1. 保留全局可写回退以兼容所有宿主 uid。
    2. API、Supervisor 写入的运行时数据与 Browser/Stream 容器统一归属 uid/gid 1000；目录 0700/0750、文件 0600/0640，chown 失败即报错；开发路径改为在匹配 uid 下运行。
- 结论：采用选项 2。Supervisor 以特权完成 chown，X11 目录由 1777 改为 0750（Browser/Stream 同为 uid 1000）；engine cache 只读挂载前收敛为 0750/0640。真实 Browser/Stream 双容器 E2E 已验证媒体与输入正常。
- 替代：无

## 015 默认无中文字体 + per-profile 可选开源 CJK 字体包（2026-11-04T01:04:09+08:00）

- 背景：历史提交 `0b4dc78` 曾 purge 全部 CJK 字体以降低中文字体指纹暴露，Browser 镜像因此对中文网页缺字或 fallback。用户要求改为按 Profile 配置：部分 Profile 保持无中文字体，部分可选不同中文字体包。2026-11-03 已在本地真实引擎验证：字体放在 fontconfig 默认扫描路径之外、按 Profile 生成 `FONTCONFIG_FILE`（include 系统配置并追加字体目录）可精确开关 Chrome 的中文字体可见性。
- 选项：
    1. 镜像全局安装中文字体，所有 Profile 一律可见（回到指纹暴露且不可按 Profile 区分）。
    2. 镜像 staged 文泉驿微米黑/正黑到 `/opt/cbrowser-fonts/`（默认扫描路径之外），`ProfileConfig.font_bundle` 三档（`none` 默认、`wqy-microhei`、`wqy-zenhei`）经 Runner 生成专属 fontconfig 配置控制可见性。
    3. 引入 Windows 专有中文字体（SimSun、Microsoft YaHei）以贴近 Windows 平台伪装。
- 结论：采用选项 2。默认 `none` 保持既有反指纹基线；启用 bundle 的 Profile 明确接受 Linux 中文字体特征与 Windows 伪装不一致的取舍，镜像增大约 22MB。选项 3 因字体不可自由分发、授权风险明确不做。不挂载宿主字体目录、不在宿主数据目录预置字体文件；Stream 容器不涉及（画面渲染只发生在 Browser 容器）。
- 替代：无（`0b4dc78` 的全局 purge 由本决定的 staged + 开关机制取代其效果面，默认行为保持一致）

## 016 默认搜索初始化不作为浏览器就绪成功条件（D1=B，2026-11-04，t022）

默认搜索引擎初始化（set_google_default）是 best-effort 增强，不是浏览器 readiness 的成功条件：初始化异常或超时后浏览器仍视为可用，其结果以独立类型化状态（applied/failed/disabled/pending）呈现到 Profile 页面，并提供受身份围栏保护、可幂等重试的操作；重试不重启浏览器、不干扰已有标签页，只有验证 Google 成为默认后才写成功 marker，正常启动不覆盖用户后续手动选择。原 D1 在 t022 立项时经用户选择 B 方案定案。

## 017 不可变 release 身份、回退约束与凭证分级（2026-11-04，t027）

- 背景：旧发布链路以可变 `*-deploy` 标签与非原子 `compose.env` 覆盖实现"升级"，同名 tag 每次被覆盖、无上一版 release，"可回滚"是假象；脚本还重复构建 API 镜像、无条件重启 Caddy、末尾打印管理员密码、缺失时自动生成全部 secret，且 compose 写死镜像 tag 与 build 块、固定实例命名，无法同 daemon 起隔离的第二实例。
- 选项：
    1. 保留标签覆盖，仅补健康检查与验收探针（回退仍无真实目标）。
    2. 每次发布生成不可变 release（release 标签 + manifest 以镜像 ID 固定六镜像与配置指纹、迁移版本、readiness 能力），current/previous 指针只在 readiness 验收后原子移动；回退显式选上一 release 并受 readiness 能力与迁移版本下限约束；凭证分级：管理员密码用户提供、内部密钥自动随机生成（0600、永不打印）。
- 结论：采用选项 2。发布/回退共用同一验收（有界 `up --wait` + 容器内探针调 t026 `reconcile_all`/`readiness`）；compose 镜像全变量化且无 build 块；实例身份参数化，prefix 异项目占用启动前拒绝；不存在降级迁移，数据从不由发布/回退删除。真实部署演练归 t032。
- 替代：无（DOCKER_DEPLOYMENT.md 旧"标签可回滚"说法自本决定起作废）

## 018 CDP 隧道由透明转发改为拒绝浏览器级破坏性命令（2026-11-04，t030）

- 背景：t029 探针证实隧道透明转发时，外部客户端一句 `Browser.close`
    即按 normal exit 停掉 Profile 且不恢复；Playwright 默认 context 会在
    连接期间覆盖下载行为、绕过 Artifact 捕获。执行器上线前必须先堵住
    这类命令，否则“可用执行器”先于“安全执行器”交付。
- 选项：
    1. 保持透明转发，只在执行器文档中警告（调用方自律；一次误发即停
        Profile，不可接受）。
    2. 隧道层拒绝清单命令并返回稳定错误，下载行为与 Emulation 覆盖
        一律拒绝，脚本登记 + 断开清理；关 Tab 不在隧道做归属过滤（实测
        会挂起 Playwright popup 关闭），改由执行器账本 enforcement，隧道
        仅保留最后一页 backstop。
- 结论：采用选项 2（规约见 `docs/specs/agent_executor.md`“隧道过滤”一节）。
    t029 的“外部 Browser.close 停 Profile”与“no_defaults=False 期间客户端
    下载优先”两条断言随策略变更整体替换为拒绝语义测试并注明 t030 为
    裁决来源，不静默改预期。
- 替代：无（透明转发语义自本决定起作废）

## 019 Profile 人机控制权：真人优先、单 Agent 排他与代次围栏（2026-11-04，t031）

- 背景：t030 落下两项输入：其一，CLI 退出后无认领的 JS Dialog 由容器
    内常驻 Agent 分支维护（AC-006 否则分支未实现，打勾 + deferral 注）；
    其二，setAutoAttach 会话的隧道 backstop 漏判。p029 另要求真人输入可
    抢占 Agent 控制。ADR 007 已废弃排他 Viewer 租约：多人类 Viewer 并发
    是既定语义，不能为控制权复活它。
- 选项：
    1. 方法名黑名单式拦截“致变 CDP 命令”（evaluate/callFunctionOn 等
        逐条禁）：p029 已指出 evaluate 可跑任意致变脚本，名单不可靠。
    2. 控制权状态机 + 连接拆除：每 Profile 一条控制记录（owner user/
        agent、单调 generation、Agent 实例 + 会话身份、交接原因、
        agent_reclaim_allowed、pending_supervisor_close），API 为唯一业
        务库写入方；接管时持久化 owner=user 并代次 +1，API 与 Supervisor
        各自关闭已登记的活动隧道并以代次围栏拒旧代次重连；向 user 的迁
        移 fail-open、向 agent 的迁移 fail-closed（身份一致 + reclaim
        标志 + 显式恢复三者缺一不可）。
    3. 恢复 ADR 007 式排他租约并扩展到 Viewer：与多 Viewer 并发语义冲突。
- 结论：采用选项 2。排他只存在于“人类侧作为一类”与“Agent 侧”之间，
    首版每 Profile 至多一个协作 Agent；多人类 Viewer 不受限。默认与重
    启/崩溃/身份失效一律回到 user；干净 Agent 结束（agent_finish）与运
    行时重启/崩溃属于全新开始，reclaim 保持开放；人类驱动的交接关闭
    reclaim，必须显式恢复。Supervisor 分区期间的残留窗口如实记录：分
    区内已存在的 Supervisor 直连隧道在分区愈合前不受 API 侧关闭约束；
    直连 Supervisor 令牌持有者属于基础设施信任边界（Supervisor token
    即服务间凭证），其握手不查 API 状态，但转发代次受围栏约束。
    ADR 006 “配置与管理集中于 /manage”的说法与实现不符（现无 /manage
    路由，管理面为 AppLayout 顶栏 + Profile 详情/自动化页），按 decisions.md
    勘误约定以本条为准修正。存储规约见 `docs/specs/human_agent_control.md`。
- 常驻 Dialog attendant 与链实测结论：attendant 为 Agent 进程内组件，
    持直连 browser_ws 的服务连接、在每页保持 no-op dialog 监听以阻止
    Chrome 自动消解；t031 真浏览器链实测推翻“新会话可经标准 dialog_answer
    应答滞留 dialog”的假设——新会话 Page.enable 会在 modal dialog 后挂起，
    handleJavaScriptDialog 报 "No dialog is showing"，故滞留 dialog 只能
    由 attendant 打开前已 Page.enable 的会话应答；CLI dialog_wait/
    dialog_answer 在未 attach 时先经控制面 peek（/control/dialogs）再经
    attendant 会话应答（/control/dialog-answer），adopt 在目标有滞留 dialog
    时跳过 attach（否则 adopt 先挂在 Page.enable 上）。接管 release 后
    dialog 回归 Chrome 默认处置（链实测：无监听时 firing 的 confirm 自动
    消解为 false）。attendant 状态 v1 不进管理面（Agent 无 API 直连通道），
    人类在视频中直接可见滞留 dialog，CLI 可经 peek 发现；补 API 拉取或
    Agent 上报通道属后续设计，不在本 task 造无消费者 plumbing。
- setAutoAttach 处置：tunnel_filter 补 attachedToTarget/detachedFromTarget
    处理（登记 session→target 映射 + 已知页面），setAutoAttach 本身保持转发
    （执行器自身传输）；最后一页 backstop 由此覆盖自动挂接会话。
- R1 审阅补强（不改结论）：控制面 peek/应答要求调用方持有控制权且
    token 身份与记录的 Agent 实例一致（user 态或第二 token 一律 409）；
    接管级联的 attendant 释放纳入 pending 确认（释放失败则 reconcile
    重试整条级联；无 Agent 进程时为空确认）；吊销 automation token 时
    该 token 持有控制的 Profile 各执行一次 identity_invalid 交接；同一
    Profile 的控制迁移按 profile 级异步锁串行化（并发认领败者为
    control_second_agent 冲突）；服务连接丢失即释放滞留 dialog 状态；
    handoff 响应体返回结算后状态。token 过期无独立清理点（握手时校验，
    已建立隧道过期后不自动关闭）与恢复时清除 pending 而不补发关闭
    （补发会误杀新隧道）均属已知边界，见规约。
- 替代：无（方法名黑名单与排他租约复活均不采用）。

## 020 前端工具链目标版本与 Node LTS 固定（2026-11-05，t033）

- 背景：`docs/plan_20261105_ui_redesign.md` D10 要求技术底层默认升到最新稳定版本（含大版本），t033 在设计系统（t036）之前先升级前端工具链。2026-11-05 实测 npm `latest`：Vite 8.3.5（Rolldown）、@vitejs/plugin-react 6.2.1、Vitest 5.1.0、React/ReactDOM 19.3.1、`react-router` 8.5.1、lucide-react 1.68.0、jsdom 30.1.3、@testing-library/jest-dom 7.0.1、@testing-library/react 16.3.3、@types/node 26.6.6、@types/react(-dom) 19.3.0、@tanstack/react-query 5.106.0、openapi-typescript 7.13.0、TypeScript 7.0.2。
- 选项：全部升到 `latest`；或遇 peer 冲突时选兼容的最高版本。
- 结论：按 D10 升到上述最新稳定版本；路由库由 `react-router-dom` 换为 `react-router` 单包（实测 8.5.1 导出 BrowserRouter/Link/Routes/RouterProvider/createBrowserRouter 等全部 DOM API，25 个源文件仅换包名，无 API 适配）。三项 SPIKE 结论：① Vite 8 Rolldown 仍产出经典 IIFE（`function() {` 开头、行首无 import/export），`verify_frontend_dist.py` 注入顺序校验不变；② jsdom 30 + Vitest 5 + Node 24.21 不再需要 `NODE_OPTIONS=--no-experimental-webstorage`，`run_gates.sh` 两处变通已删除；③ TypeScript 7.0.2 与 openapi-typescript 7.13.0 的 peer `typescript@^5.x` 实测 ERESOLVE 冲突，故 TypeScript 例外固定在当前最高 5.x = 5.9.3（不是 7.x）。宿主构建 Node 固定 26 LTS（`.mise.toml` 固定 26.13.0，`engines.node=">=26.0.0 <27"`），`check_node.mjs` 在 `pretest` 与 `build` 链首校验并输出所需范围。Tailwind 4 迁移与设计系统仍归 t036，不在本决策范围。
- 复查条件：当 `openapi-typescript` 发布兼容 TypeScript 7.x 的版本（peer 放宽到 `^7 || ^5` 或更高）且 `generate:api` 产物与当前 5.9.3 生成结果一致、全套类型检查与 Vitest 通过时，可把 TypeScript 升到 7.x 并删除本例外；复查时同时确认 Vite/Rolldown IIFE 产物形态未变。
- 替代：无（不采用 `--legacy-peer-deps` 强装 TS 7，也不降级 openapi-typescript）。

## 021 运行时底座目标版本、依赖单一来源与 cloakbrowser 锁定（2026-11-05，t034）

- 背景：D7/D10 要求运行时、基础镜像、依赖锁定与 Caddy 升到当前最新稳定版本；Selkies 升级拆到 t043 单独回退。2026-11-05 核实现状：全部 Python 镜像 `python:3.12-slim-bookworm`、辅助阶段 `debian:bookworm-slim`、无 `uv.lock`、依赖分散在 `requirements.in`/`requirements.txt` 与 `src/backend/requirements.txt`、SQLAlchemy 2.0.43 / Alembic 1.16.5 / aiosqlite 0.21.0、Caddy 2.8-alpine。
- 选项：全升最新；或遇兼容问题时保留例外。
- 结论：
    - **Python 3.15.2 / Debian trixie**：六个运行时镜像全部改为 digest 固定的 `python:3.15-slim-trixie@sha256:8c13a3f...`、Browser 辅助阶段 `debian:trixie-slim@sha256:f6b08b0...`；trixie apt 包名 SPIKE 实测全部可用（X11/GStreamer/Pulse/XTEST/文泉驿字体等）。`pyproject.toml` 的 `requires-python` 与 `uv.lock` 均为 `>=3.15`，`run_gates.sh` 的 `GATE_PYTHON_MINOR=3.15`，`.mise.toml` 固定 3.15.2。
    - **依赖单一来源**：修正 `pyproject.toml` 原缺陷（`dependencies` 误落在 `[project.scripts]` 表下，项目依赖为空），改用 PEP 735 `[dependency-groups]` 定义 6 组；`uv.lock` 为唯一锁定来源，`scripts/generate_requirements.sh` 按组 `uv export --only-group` 生成各镜像 requirements 与门禁 requirements；`tests/unit/test_t034_dependency_lock.py` 在门禁中校验一致，手改即失败。删除 `src/backend/requirements.txt` 与四处 `requirements.in`。
    - **升级版本**：`uv.lock` 解析 77 包，SQLAlchemy 2.1.8、Alembic 1.20.1、aiosqlite 0.22.1；全量 unit（1002+）、integration（142）、contract（222）在 Python 3.15 下通过，无弃用用法导致的回归。
    - **Caddy 2.11.8**：`deploy.sh` 默认引用改为 digest 固定；现有 Caddyfile（`tls internal`、`auto_https disable_redirects`、`handle` 转发）经 `caddy validate` 实测通过，行为不变。
    - **cloakbrowser 锁定 0.6.4（D7）**：0.6.4 无 key 模式使用免费 Chromium 146 内核、不校验 license、无并发上限；0.7.0 删除无 key 路径，自动申领的免费 key 只允许 1 个并发会话，会破坏多 Profile 并发。故精确锁定 `cloakbrowser[geoip]==0.6.4`，不升 0.7.x。
- 复查条件：上游恢复无 key 路径且免费 key 不再限制并发会话时，重新评估 cloakbrowser 升级（需真引擎并发验证）；Python/Debian/Caddy 后续大版本升级按同一 digest 固定 + SPIKE + 全量门禁流程。
- 替代：无（不采用 `--legacy-peer-deps` 类绕过，不保留手写并行依赖清单）。

## 022 Selkies 升级至 2.2.1 与契约适配（2026-11-05，t043）

- 背景：D10 要求 Selkies 升到当前最新 2.x；t034 已把运行时底座升到 Python 3.15 / trixie，但刻意把 Selkies 拆到 t043 以保留独立回退边界。正式 spike `docs/spikes/s012_selkies_2_2_upgrade_contract/report.md` 与 finding `docs/findings/d030_selkies_2_2_1_upgrade_contract.md` 以官方 wheel 源码逐项比对 2.1.0 → 2.2.1。
- 选项：升到 2.2.1；或发现不可适配破坏变化时停止报告用户并保留 2.1.0。
- 结论：采用 2.2.1（PyPI 最新 2.x，METADATA 声明支持 Python 3.15）。比对结论：Python 模块清单相同；`webrtc_signaling_server.py` 的 HELLO / client_tab_id / resume_key / resume 语义不变；`_XTestKeyboard` 私有 ABI（4 方法签名、`_BIND_SETTLE_S`、6 个实例属性）AST 校验全部一致；Web 客户端 `selkies-core.js` 从 `src/` 移到根但协议字符串上下文逐字相同，`adapter.ts` 的 WebSocket hook 有效——**无不可适配的破坏性变化**。适配点：Web 客户端文件清单与 SHA 清单重生（2018 行）、index.html 新增 `__SELKIES_DEFER_INITIALIZATION` / modulepreload / 末尾 `selkies-core.js` module（vendor 注入 marker 改通用「首个 module tag」而非写死 2.1.0 bundle 名，IIFE adapter 仍在 head 首位）、pixelflux 2.2.3 / pcmflux 2.2.1 随 `uv.lock` 联动、`x11_keymap` 的 `SUPPORTED_SELKIES_VERSION=2.2.1` 版本门禁（ABI 校验本身不变）。ADR 002 / 013 的历史「2.1.0 固定」表述按 ADR 传播约定由本条更新现行文档面，历史条目原文不改。
- 复查条件：后续 2.x 升级沿用同一 spike（协议字符串、私有 ABI AST、Web 客户端文件清单/注入顺序、原生依赖）与 Stream/会话 E2E 差异探针；任一不可适配变化按 t043 契约停止报告用户，不自行保留旧版。
- 替代：无。

## 023 Profile 领域模型重建：单 baseline、Group/Proxy 引用与配置版本三分（2026-11-05，t035）

- 背景：`docs/plan_20261105_ui_redesign.md` WP06/WP07 要求 Profile 由「业务 Tag + 内嵌 proxy 字符串」改为「分组库 + 代理库引用」，代理密码需单一来源且不进快照/日志/SSE；同时迁移链 0001-0009 已累积 9 个修订，旧代 schema 与新模型不可增量兼容。AC-002 要求旧代 DB 失败封闭并输出重建指引。认证 SOCKS5 的引擎能力经正式 spike `s013_authenticated_socks5_engine_probe` 验证（finding `d031`）。
- 选项：① 保留 0001-0009 链并新增增量迁移 + 兼容读取；② 折叠为单 baseline、旧代 DB 失败封闭；③ 代理密码随版本快照复制；④ 认证 SOCKS5 一律 422 拒绝。
- 结论：
    - **破坏性升级不留兼容层**：迁移目录只保留 `0001_baseline.py`（revision `b7e1c9d4a2f3`，`down_revision=None`），删除 0001-0009。API 启动（`migrations.py` 的 `LegacySchemaError` + `REBUILD_GUIDANCE`）与 `scripts/deploy.sh`（只读探测 `alembic_version`）均对旧代 DB 失败封闭，不修改该 DB、不构建镜像、不移动 release 指针。**生产数据必须经用户批准的备份与迁移流程重建**，不自动升级、不静默删数据。
    - **release controller 按修订链判回退下限**：`current_revision_chain()` 读取当前源码树的修订 id，旧代 release（退役 0001-0009 head）拒绝作为回退目标；同代 release 之间的发布与回退通过。删除原 `applied_migration_version` 字符串比较机制。
    - **Proxy 凭据单一来源**：密码只存 `proxies` 表；配置版本快照只存 `proxy_id` 与 `proxy_credential_revision`（无代理时为 `None`），不含密码。`update_proxy` 改连接字段时在同一事务为引用 Profile 生成新版本并广播 SSE；改 name/region/notes 不生成。Supervisor 经只读 internal 端点取凭据，Runner 挂载 0600 `proxy_credentials.json`，revision 不一致或文件缺失即失败封闭 `proxy_credentials_changed`。
    - **配置版本三分**：只改元数据（name/notes/sort_order/group_id）、只改即时策略 `capture_preview`、或提交与当前值相同的运行配置，都不生成新版本、运行中不出现待应用；只有运行配置字段值变化才生成。
    - **认证 SOCKS5 走端到端分支**：Chromium 146 实测支持 `socks5://user:pass@host:port`（正确凭据 `loaded=True`、错误凭据 `net::ERR_SOCKS_CONNECTION_FAILED`），故 Runner 直接构造 `--proxy-server`，不采用 422 拒绝创建的降级路径。
- 复查条件：Chromium 主版本或指纹平台升级后重跑 `s013` 的三组实测（无认证 / 正确凭据 / 错误凭据），若引擎不再接受带认证 SOCKS5 则按 AC-008 回退到 API 422 分支；后续 schema 破坏性升级沿用「单 baseline + 旧代失败封闭 + 修订链回退下限」流程。
- 替代：①/③/④ 均不采用（兼容层与自动升级违背破坏性升级不留包袱原则；快照复制密码违背凭据单一来源；422 拒绝与实测引擎能力不符）。

## 024 平台字体运行时只读挂载与 Profile 绑定不可变字体集（2026-11-06T07:27:29+08:00，t041）

- 背景：ADR 015（t020）按 Profile 三档 `font_bundle`（文泉驿）开关 CJK 字体，并写明不挂载宿主字体目录、不在宿主数据目录预置字体；Runner 的 fontconfig 配置 include `/etc/fonts/fonts.conf`，会把 `/usr/share/fonts` 下 apt 安装的全部字体暴露给所有 Profile。t041 正式 spike `s014`（结论 `d032` / `d033`）在 cloakbrowser 0.6.4 / Chromium 146 实测：`--fingerprint-platform=windows` / `=macos` 下 `navigator.platform`、UA、UA-CH `platform` / `platformVersion` 两平台一致；只白名单声明字体目录的 `FONTCONFIG_FILE` 使 Liberation / Nimbus / 文泉驿等 Linux 专属字体命中 0；两种平台都有原生 CJK 字体（微软雅黑、宋体；苹方、冬青黑体），文泉驿本身成为 Linux 特征。用户 2026-11-05 决定 Profile 可选 windows / macos 指纹平台并绑定不可变字体集（D15），字体只在运行时挂载、不进镜像不入库。
- 选项：
    1. 保留 ADR 015 的 `font_bundle` 三档与 include 系统 fontconfig 的开关机制。
    2. 删除 `font_bundle`，平台专有字体只在运行时由 Supervisor 只读挂载，Profile 绑定按内容寻址的不可变字体集，Runner 生成只白名单声明绑定集目录（不含基础字体）的 `FONTCONFIG_FILE`。
    3. 把平台专有字体打进 Browser 镜像或提交到 git 仓库随发布分发。
- 结论：采用选项 2。运行配置新增 `fingerprint_platform`（默认 `windows`）与 `font_set_id`，经增量迁移 `0002_fingerprint_platform.py` 加入，两者修改任一生成新 `ProfileConfigVersion`；Runner 按绑定快照选择平台，删除写死的参数。基础开源字体六项（`fonts-noto-color-emoji` / `fonts-freefont-ttf` / `fonts-unifont` / `fonts-ipafont-gothic` / `fonts-wqy-zenhei` / `fonts-tlwg-loma-otf`）放镜像 `/opt/cbrowser-base-fonts`（默认扫描路径之外，仅满足 CloakBrowser 安装要求，**不进入**指纹 Profile 白名单，用户 2026-11-06 裁决）；平台字体集存宿主 `CBROWSER_FONTS_DIR/{platform}/{set_id}/`（内容寻址 set_id + 来源与 sha256 manifest，经 `.worktreeinclude` 供 worktree 共享），只读挂到 `/run/cbrowser/fonts/{platform}/{set_id}`。绑定集缺失或 manifest / 文件不一致时启动失败封闭 `font_set_unavailable`，`font_set_id` 为 null 时回退基础开源字体可见、保证页面可用（空字体集会让真实栈页面交互失败），runtime 状态报告「平台字体未配置」并在 `missing_fonts` 标明当前暴露 Linux 基础字体；runtime 响应与 SSE 下发实际 `font_set_id` 与 `missing_fonts`，`GET /api/v1/font-sets` 列出平台、来源、版本、静态完整性与 `used_by_count`。字体不进任何镜像层与 git 仓库，部署 / 发布脚本不复制字体目录（AC-008）；`font_bundle` 字段、镜像字体包、代码、文档与测试引用一并删除（AC-009）。UA-CH `architecture=arm` 与 windows UA `x64` 的差异：引擎层无 flag、CDP 页面级覆盖漏 ServiceWorker，按用户裁决不做半套覆盖（`d032` + `p045`），AC-004 文本不改。选项 3 把平台字体打进镜像 / 仓库等同分发，授权与来源风险明确不做；平台字体只从官方渠道取得、只在运行时只读挂载，不进入任何镜像层与仓库。
- 替代：015（本条为现行决定，替代 ADR 015；历史 ADR 015 原文不改，其「不挂载宿主字体目录」「不预置字体文件」结论由运行时只读挂载取代）。

## 025 DESIGN.md 为设计权威与亮暗双模式约定（2026-11-06T14:26:49+08:00，t036）

- 背景：前端颜色硬编码（Tailwind 3 `surface-0..4` / `gray-*` / `emerald-*`），只有暗色；设计参考原型与实现分离，无法约束后续 UI task。plan 4 节（D1，用户 2026-11-05 确认）要求以 google-labs-code/design.md alpha 格式的设计文件作为唯一设计权威并支持亮暗双模式。正式 spike `s015` + finding `d034` 在 `@google/design.md@0.4.0` 实测：前缀 token 正常解析、成对组件分别做 WCAG AA 对比度检查、程序化 `lint()` 返回已解析 hex / RGB；`@tailwindcss/vite@4.3.4` 与 t033 选定的 Vite 8.3.5 构建兼容。
- 选项：
    1. 继续用 Tailwind 3 自定义 `theme.extend.colors` 并手写两套 CSS 变量。
    2. 采用根目录 `DESIGN.md` 作为唯一权威，精确固定 `@google/design.md@0.4.0`，由生成器输出 Tailwind 4 `@theme` 变量，业务代码只用语义 token；双模式以 `light-*` / `dark-*` 成对角色 + 成对组件表达。
    3. 等上游规范正式支持多模式后再做主题。
- 结论：采用选项 2。`DESIGN.md` 章节按规范顺序，`primary` 为模式无关品牌色，其余颜色角色成对且集合相同（由生成器校验，官方 lint 不校验此规则）；字体 / 间距 / 圆角与模式无关只定义一次。`design:tokens` 生成 `design_tokens.css`（亮色默认 + `.dark` 覆盖全部颜色变量），产物入库，`design:lint` / `design:check` 与 `design:tokens` 接入完整门禁。Tailwind 4 以 `--color-*: initial` 重置默认调色板，删除 PostCSS / autoprefixer / `tailwind.config.ts`；字体经 `@fontsource` 自托管。主题偏好 `system` / `light` / `dark`（默认 `dark`）存 `cbrowser.theme`，`public/theme_boot.js` 外链经典脚本保证首帧无闪烁，UI 主题与 Profile `color_scheme` 互不影响。选项 1 保留硬编码分歧、无单一权威；选项 3 把已确认的需求无限期推迟。
- 复查条件：`@google/design.md` 升级或上游正式支持多模式时重跑 `s015` 的 lint 与 Vite build 两条命令；若双模式写法失效，只改 token 写法与生成器，业务代码不变。
- 替代：不影响既有 ADR；ADR 020（t033 前端工具链）为本次 Tailwind 4 / Vite 8 前提，ADR 015 字体三档由 ADR 024 取代。

## 026 局域网访问、边缘容器重建与媒体直连扩展（2026-11-08T04:30:00+08:00，t042）

- 背景：p037 要求局域网访问可配置并在 UI 中保存与应用生效；用户 2026-11-05 决定只保留 HTTPS（D14），删除原 HTTP 降级与开关。正式 spike `s017`（结论 `d036`）在当前 Docker (OrbStack) / Chromium 146 / Selkies 2.2.1 实测：
    1. 端口物理隔离：端口绑定 `127.0.0.1` 阻断宿主局域网 IP 访问（连接被拒/超时）；绑定 `0.0.0.0` 连通。
    2. 安全上下文：Chrome 访问未信任的局域网 HTTPS 时，跳过证书警告后页面中 `window.isSecureContext` 恒为 `true`，`navigator.locks`、`RTCPeerConnection`、`crypto.subtle` 全部正常生效。安装根证书为消除浏览器警告与防止中间人攻击的最佳实践，非 Web Locks / WebRTC 功能阻断硬前置。
    3. Selkies 2.2.1：原生支持 `--webrtc-public-ip` 与 `--webrtc-ice-lite`，局域网模式下注入通告 IP 并将 UDP mux 绑定到 `0.0.0.0` 即可输出局域网 host candidate。
    4. 边缘容器重建归属：运行期端口绑定变更必须重建容器；宿主机严禁常驻进程（ADR 017），Supervisor 作为单机唯一持有 Docker socket 的协调者，统一接管 Caddy 与 Stream 的重建与对账。
- 选项：
    1. 引入外部宿主守护进程或脚本监听端口变更并重建 Caddy。
    2. Supervisor 作为单机唯一 Docker 协调者，接管边缘代理（Caddy）与媒体容器（Stream）的端口重建与版本对账。
    3. 仅修改反向代理规则，不修改 Docker Host Port 绑定。
- 结论：采用选项 2。
    - **端口绑定物理隔离**：本机模式下，HTTPS 端口（Caddy）与媒体 UDP mux（Stream）强制绑定 `127.0.0.1`，非回环访问在网络层物理不可达；局域网模式（p053 暂搁，未接线）下，绑定 `0.0.0.0`，Selkies 注入局域网通告 IP 输出局域网 host candidate。
    - **Supervisor 统一接管边缘容器重建**：应用操作由 API 发起，Supervisor 执行原子重建。对 Caddy，Supervisor 保留原有 volume、network、image 与 compose 标签，仅重写 `PortBindings` 并原子替换容器；对 Stream，`_converge_session` 与启动对账比对当前运行容器标签中的绑定地址与通告 IP，漂移即重建。
    - **修订 ADR 013**：媒体链路依然无 STUN/TURN、无 ICE 重启机制，但由原「仅同机回环 127.0.0.1 直连」扩展为「本机回环 / 局域网 host 候选直连可配置」。
- 复查条件：Docker 网络或网络后端架构变更、或需支持公网/NAT 穿透时重新评审。
- 替代：修订 ADR 013（媒体直连由仅回环扩展为支持局域网直连）。选项 1 违背单机免外部守护原则；选项 3 无法满足本机模式物理阻断要求。

## 027 omni 视觉系统迁移采用 AA-safe 色板与 DESIGN.md 派生字体字重（2026-11-09T22:00:00+08:00，t047）

- 背景：用户要求前端界面参考 omni_panel 的 `DESIGN.md` 改造视觉风格（冷灰主题、Inter 字体、高字重标题、大圆角与柔和阴影），且不动主要界面与交互。直接复制 omni 色值在现有 `design:lint` 门禁下有 4 处因 WCAG AA 对比度不足（< 4.5:1）而失败（亮色 accent、亮色 danger、暗色 on-accent、亮色 muted 在背景上）。同时 `@google/design.md` linter 将 front matter 中未知的 `shadows`/`motion` 视作 warning（阻断门禁），且原生成器硬编码 Space Grotesk 字体、未输出字重与行高变量。
- 选项：
    1. 放宽门禁（忽略 contrast warning 或允许部分非 AA 颜色对），手写 Tailwind 阴影配置。
    2. 采用 AA-safe 变体调色板（亮色 accent `#2F66E0`、亮色 danger `#DC2626`、暗色 on-accent `#0B1220`、亮色 muted `#5C6478`），生成器直接从 `DESIGN.md` 的 `typography` 派生字体栈，输出字重、行高与字距变量，并从 `## Elevation & Depth` 正文表格解析 `--shadow-*` 阴影变量；保持 `.dark` 首帧机制不变。
    3. 彻底重构前端主题架构为 `data-theme` 与五档强调色切换。
- 结论：采用选项 2。在不破坏任何业务代码与首帧机制的前提下，纯靠 token 管线升级完成整体视觉换肤；全部颜色对 100% 满足 WCAG AA 4.5:1 门禁；字体平滑迁移至 Inter Variable 与 JetBrains Mono Variable；圆角与阴影全局自动更新。选项 1 违背严格门禁质量铁律；选项 3 超出用户“只改主题背景字体字号、不动主界面”的明确需求范围。
- 替代：本条修订 ADR 025 中的字体栈声明（Space Grotesk / IBM Plex 替换为 Inter / JetBrains Mono）与单字重假设（生成器扩展输出字重、行高、字距与阴影）。
- 修订（2026-11-13，t059）：本条「全部颜色对 100% 满足 WCAG AA 4.5:1 门禁」的声称范围在此收紧并落实为门禁事实。此前官方 linter 的 contrast-ratio 仅覆盖 components 成对 textColor/backgroundColor；t059 实测发现门禁外真实不达标：亮色 warning 作文字对亮色背景仅 2.04:1、亮色 danger 作文字对亮色页面背景 4.01:1、亮 / 暗 on-surface-subtle 对 raised/subtle 底色 3.91–4.50:1、亮色分组 teal/green/amber/orange 作图形对亮色背景低于 3.0:1。t059 将对比度门禁补齐为三类全覆盖（成对 component、仅 textColor 的 component 对同模式四种底色、DESIGN.md `## Contrast` 表声明的代码直用文字对 4.5:1 与图形对 3.0:1），并修正 8 个 token 至门禁通过（light-warning `#F5A524`→`#8D5F15`、light-danger `#DC2626`→`#CA2323`、light-on-surface-subtle `#626A7D`→`#61687B`、dark-on-surface-subtle `#858D9C`→`#929AA7`、light-group-teal `#0EA5A3`→`#0C8F8E`、light-group-green `#16A34A`→`#149443`、light-group-amber `#CA8A04`→`#AC7603`、light-group-orange `#EA580C`→`#DE530B`）。自此 AA 声称以生成器门禁（design_lint / design_check）的实际覆盖面为准，不再作门禁外推断。

## 028 运行时与部署可靠性：控制面 DB 进 named volume、部署身份与发布原子性（2026-11-11，t051）

- 背景：p068（2026-11-10 18:37–18:51 登录与 `/auth/session` 持续 500，日志 `disk I/O error`，自愈后 `integrity_check` 正常）根因高度疑似 WAL `-shm` wal-index 跨宿主/VM bind mount（macOS → OrbStack VM）的 mmap 与锁语义失稳；日志未记 SQLite 扩展错误码，无法区分 `SQLITE_IOERR_SHMMAP` 与 `SQLITE_IOERR_READ/WRITE`。同时应用层放大故障：`api/app.py` 的 `DBAPIError` 处理器把非 `IntegrityError` 一律映射为 500 `database_error` / `retryable=false`，`AuthService` 无重试，前端直接透传后端英文错误。review_20261110_200842 另指出：部署归属判定只凭可伪造标签（A59）、prefix 无校验且与派生命名空间重叠（A22）、发布指针两步写无 fsync（A43）、不可读库 fail-open（A44）、数据根仍带代际标识（A55）、证据与 Docker 错误脱敏规则分散（A58）。
- 选项：
    1. 数据库留在宿主 bind mount，只加错误码日志与重试。
    2. 数据库迁入 compose named volume `db`，并补齐错误分级、备份/恢复、部署身份、指针原子化与去代际化（本 task 采用）。
    3. 把 `com.cbrowser.instance-id` 复用为部署身份（A59 字面）。
- 结论：采用选项 2。
    - **数据库位置**：`cbrowser.db`（含 `-wal` / `-shm`）进 named volume `db`（`name: ${CBROWSER_PREFIX:-cbrowser}-db`），API 挂载 `db:/data/db`、`CBROWSER_DB_PATH=/data/db/cbrowser.db`；字体改为独立部署输入 `${CBROWSER_FONTS_DIR}:/fonts:ro`。WAL 的 `-shm` 与数据库始终同文件系统、同机。
    - **部署身份**：`instance_id = sha256("cbrowser-instance-v1\0<prefix>\0<data_root>")[:32]`（跨 release 稳定、跨实例区分），媒体子网池按 `pool_index = sha256(identity) mod 64` 得 `10.{192+index}.0.0/16`；写入 release env 与 manifest。归属判定以 `com.cbrowser.instance-id` 标签值 == 本实例 instance_id 为唯一依据（AC-021 规定的键名），删除 project 名豁免。运行时 id 随之归位：每轮唯一的运行时实例 id 不再占用该标签，改由容器运行时配置承载（Stream 环境变量 `CBROWSER_RUNTIME_INSTANCE_ID`、gated entrypoint `--instance-id`、Browser 命令 `--runtime-instance-id`），扫描/查找/回收经 `container_runtime_instance_id` 从配置读取，两身份各行其道、互不冒充。（2026-11-11 用户裁定：初版实现以语义冲突为由自造 `com.cbrowser.deployment-id` 键、并把默认前缀改为 `cbrowser`，均被驳回；本 ADR 按规定键名与默认部署前缀 `cbrowser-t005` 落定。）
    - **发布原子性**：`current_release` / `previous_release` 两文件改为单一 JSON `release_pointer.json`（`{"current": …, "previous": …|null}`），原子写含文件与父目录 fsync；损坏指针 fail-soft 替换。部署前容器内在线备份数据库并记入 manifest，`deploy.sh restore` 可恢复；旧宿主库只提示、不删除/移动。schema 检查先建 API 镜像再以只读挂载读 stamp，不可读库 fail-closed。
    - **错误分级**：`SQLITE_BUSY` / `SQLITE_LOCKED` / `SQLITE_IOERR`（含扩展码，按扩展码 & 0xFF 取主码）为瞬时错误 → 503（`database_busy` / `database_unavailable`）、`retryable=true`、`Retry-After: 1`；确定性错误仍 500 / 409。`AuthService` 对瞬时错误有界重试（最多 3 次）；登录页对两类 503 显示本地化文案。日志只记 SQLite 错误码名 + 方法/路径，永不记 SQL 文本与绑定参数（`str(exc.orig)` 与 `logger.exception` 的 traceback 行都会带 SQL）。
    - **前缀规则**：部署输入的资源 prefix 须匹配 `^[a-z0-9][a-z0-9_]*$`（不含连字符，避免与 `<prefix>-profiles` / `<prefix>-<NNNN>` 命名空间重叠），deploy.sh 与 Supervisor 启动都在任何 Docker 操作前校验；默认部署前缀 `cbrowser-t005` 是编译内既定标识、先于该规则存在，不在校验之列（deploy.sh 自身的默认 `cbrowser` 满足规则，校验其输入不变）。
    - **媒体网络超时**：Docker 网络调用以 30 秒为限（`CBROWSER_DOCKER_NETWORK_TIMEOUT` 可配）；分配锁只覆盖 get+分配+预留，创建在锁外执行，挂起时仅该次启动失败；创建冲突为错误，不重试。
    - **去代际化**：产品无代际标识；迁移文件改名 `0001_baseline.py`（原名含代际后缀，revision `b7e1c9d4a2f3` 不变），现行文档/源码/脚本中的代际自指清除，由 hygiene 测试守护；例外仅 deploy.sh 的旧库探测（须写出真实旧路径）与对应断言。
- 复查条件：真实部署（AC-013）、双实例真实 Docker（AC-014）、真实 Docker 挂起（AC-015）均未在本机验证（无 Docker 环境），须在用户机按 t032 演练补验；升级后 t051 之前创建的沙箱/网络无 instance-id 部署标签，新 Supervisor 不认领，属 A59 字面语义，由既有 orphan 路径处置。
- 替代：选项 1 留下 bind mount 失稳根因，只治标；选项 3 破坏运行时实例查找。指针两文件 + 无 fsync、不可读库 fail-open、project 名豁免均不保留。

## 029 代理链接为唯一录入，国家为 Browser 同视角观测（2026-11-11，t052）

- 背景：代理弹窗暴露 9 个平铺字段 + 独立「从 URL 粘贴」框，链接与字段是两套可漂移的表示；`country_code` 被建模为可写静态配置，实际是出口 IP 的观测结果（有来源、时间、视角、端点指纹、凭据版本与失效条件）；从 API 进程经代理探测得到的是 API 网络路径，可能与 Browser 真实出口不同；`127.0.0.1` 是视角相关地址，宿主、API 容器、Browser 容器指向三个不同网络栈；探测接口若按请求 host 复用已存密码会形成 SSRF + 凭据外送。来源 p060（已归档）与 parked p040 的出口 IP 部分；用户 2026-11-10 裁决：loopback 端点由 Supervisor 按 Browser 网络视角映射到宿主并单端口放行（不引入 egress broker，p038 保持 parked）；出口国家在保存后自动探测，不提供保存前草稿探测接口。
- 选项：
    1. 保留平铺字段录入 + 前端粘贴辅助，国家仍手填或由 API 进程探测。
    2. 链接为唯一录入（`ProxyEndpoint` 值对象 + 四格式解析器），国家改为 Supervisor 在 Browser 同视角的 helper 内探测、本机 GeoLite2 判定，loopback 端点由 Supervisor 映射并单端口放行（本 task 采用）。
    3. 引入 egress broker 统一代理出口。
- 结论：采用选项 2。
    - **链接唯一录入**：`ProxyCreateRequest` / `ProxyUpdateRequest` 只接受 `proxy_url`（`extra="forbid"`）；四种格式（标准 URL、无协议 `host:port` 默认 http、`host:port:user:pass`、`user:pass@host:port`），IPv6 必须括号，密码 percent-decode；`ProxyResponse` 只返回脱敏链接与派生只读字段，密码永不进响应。名称省略时由 `host:port` 派生。PATCH 的 `proxy_url` 省略 = 端点不变，提供 = 整端点（含密码）整体替换。
    - **国家是观测**：迁移 `0006` 删除 `proxies.country_code` 列（无真实用户，不做数据迁移）；新增 `proxy_egress_observations` 表（指纹、凭据版本、视角 `browser`、出口 IP、国家、来源、状态、错误码、观测/过期时间，TTL 24 小时）。端点指纹或凭据版本变化、观测过期时旧观测立即失效；探测失败记 failed 行、不猜国家。
    - **Browser 同视角探测**：Supervisor 用 Browser 镜像建短生命周期 helper（专用 bridge 网络、browser-role 网络策略、0600 凭证文件、GeoIP 缓存只读挂载），经 `runtime_agent.egress_probe` 访问 IP 回显端点（复用 cloakbrowser SDK 的三个回显服务，只发一次 HTTPS GET 取自身出口 IP），国家由本机 GeoLite2 判定，出口 IP 不发往第三方地理库。探测接口 `POST /api/v1/proxies/{id}/probe` 只接受代理 ID（非空 body 422），服务端加载已存端点与凭据执行。
    - **loopback 映射**：`127.0.0.0/8` / `localhost` / `::1` 端点在库与指纹中保持原样，交给容器前映射为 `host.docker.internal` 并加 `extra_hosts={"host.docker.internal": "host-gateway"}`；网络策略只放行映射地址与该代理端口。映射失败时启动与探测在执行前以 `LoopbackMappingError` 明确报错并给出处置提示，绝不出现启动成功但无法联网。
    - **前端**：弹窗默认只显示代理链接、备注与只读国家状态，高级设置默认折叠；链接与高级字段双向同步；失焦显示脱敏链接；编辑端点而密码框留空时拦截提交（防静默清除已存密码）。
- 复查条件：真实 Docker（OrbStack）上的 helper 启动、host-gateway 映射与策略放行须在用户机实测（本机无 Docker，fake-docker 单元测试不能代替；t052 AC-010/AC-011 真实部分与 AC-012）；`GeoLite2-City.mmdb` 在真实部署 engine-cache 中的存在性同样待用户机验证；IP 回显服务不可用时探测记 failed，不降级猜测。
- 替代：选项 1 保留模型错误与视角错误；选项 3（egress broker / 内置 mihomo）属 p038，保持 parked。不做连通性与延迟检测（p040 剩余部分保持 parked）、不做保存前草稿探测、不允许人工声明国家。

## 030 英文 Profile 裁剪中文字体（2026-11-11，t053）

- 背景：p069 要求英文 Profile 不加载任何中文字体、中文 Profile 必须加载平台中文字体。ADR 024（t041）按操作系统整体挂载字体集，fontconfig 白名单只声明目录，英文 Profile 也会暴露微软雅黑 / 宋体 / 苹方 / 冬青黑体。d033 已实测：真实 Windows / macOS 不论系统语言均预装原生中文字体，裁剪后英文 Profile 可能呈现“缺少系统原生字体”特征；用户 2026-11-10 已知悉该事实，仍确认按原需求裁剪。
- 选项：
    1. 保留 ADR 024 的字体集整体可见，只在 UI 层面提示语言与字体不一致。
    2. 按 Profile 语言生成 fontconfig：英文 Profile 在白名单之外追加 `<selectfont><rejectfont>`，按 fontconfig `lang` 覆盖排除中文标签字体；中文 Profile 不裁剪（本 task 采用）。
    3. 按字体文件名单 / 来源系统裁剪（黑名单式维护中文字体清单）。
- 结论：采用选项 2。
    - **裁剪机制**：`locale == "en-US"` 时，对中文语言标签 `zh` / `zh-cn` / `zh-tw` / `zh-hk` / `zh-mo` / `zh-sg` 各追加一条 `<selectfont><rejectfont>`，排除 `lang` 覆盖含任一中文标签的字体；`locale == "zh-CN"` 时不追加。裁剪只看字体的 fontconfig `lang` 覆盖声明，不看文件名或来源；日文、韩文等非中文 CJK 字体除非其 `lang` 覆盖声明含中文，否则不被裁剪。未绑定字体集时回退 `/opt/cbrowser-base-fonts` 的场景同样遵守该规则。
    - **语言是显式配置**：`locale` 收敛为封闭枚举 `zh-CN` / `en-US`（新建默认 `en-US`），非法值与非法时区在写入边界 422 拒绝；时区 → 语言规则为中文地区时区集合（`Asia/Shanghai` / `Asia/Chongqing` / `Asia/Urumqi` / `Asia/Harbin` / `Asia/Hong_Kong` / `Asia/Macau` / `Asia/Taipei`）→ `zh-CN`、其余 → `en-US`，时区为空时语言保持当前值。`locale` 属运行配置，变更生成新配置版本、重启生效。
    - **已知取舍**：英文 Profile 访问中文页面时中文字符回退为方框，属用户确认取舍；按 `lang` 覆盖判定可能把部分同时声明中文覆盖的日文字体一并排除，以字体集清单逐项测试固定结果。指纹检测网站对“英文平台缺原生中文字体”的判定属外部风控行为，非本系统契约。
    - **字体集链路收紧（同 task 审阅缺陷）**：默认集只由后端按完整性决定（`GET /api/v1/font-sets` 返回各平台 `default_font_set_id`，只取完整性通过的集），前端不再自行推导，「无」为显式 null；绑定集时 fontconfig 生成失败即启动失败 `font_set_unavailable`，不回落系统配置；损坏集重新导入原子替换，Coordinator 删除运行时缓存、按 Supervisor 同一校验函数实时读取；`used_by_count` 按 `(fingerprint_platform, font_set_id)` 统计，列表校验 manifest 平台与目录一致；会话详情区分「字体集完整性」与「探测字体未覆盖」两种文案。
- 复查条件：Browser 镜像内 fontconfig 版本对 `.ttc` 集合的 `lang` 排除是否生效，须在用户机以 `fc-list` 实测（宿主 fontconfig 2.15.0 已验证机制成立）；真实引擎下 `navigator.language` 是否等于 Profile 语言且不被出口 IP 推断覆盖，须在用户机实测（本机无真实引擎，见 t053 环境跳过项）。
- 替代：选项 1 留下指纹矛盾；选项 3 的文件名黑名单随字体集来源漂移、不可维护。**本条部分替代 ADR 024**：仅替代其中“字体集整体可见”的部分——英文 Profile 的 fontconfig 白名单排除覆盖中文的字体；ADR 024 其余结论（运行时只读挂载、不可变字体集、失败封闭、null 回退基础字体）全部保留。

## 031 网络配置收归部署期：删除局域网与运行时网络应用（2026-11-11，t054）

- 背景：review_20261110_200842 的 A61（用户 2026-11-10 选方案 C）与 A14 要求：网络配置回到部署期，删除运行时的网络应用链；同时 p053 的前提已变——局域网访问不再是“暂搁待接线”，而是彻底不做：t042 建起的整条链（Settings 局域网开关与通告 IP、`NetworkService` 事务、Gateway 发布协议、Supervisor `rebuild-edge` / `converge-streams`、恢复围栏、操作日志网络收据、双文件已应用状态、LAN 媒体策略、root-ca 下载）全部删除，无保留、无兼容。默认端口此前在后端、脚本、前端三处各写一份字面量（`56661`），已收敛为唯一常量 `DEFAULT_HTTPS_PORT`。
- 选项：
    1. 保留运行时应用链，只把局域网开关藏起来（前端隐藏、后端保留）。
    2. 网络配置收归部署期：部署时渲染 Caddyfile、端口只从部署输入来，运行期无任何网络变更入口（本 task 采用）。
    3. 保留局域网但改由部署期开关（部署时决定绑定地址）。
- 结论：采用选项 2。
    - **删除局域网**：`lan_access_enabled` / `lan_advertised_ip` 字段与两处校验、`allow_lan_media` 与 LAN 媒体策略分支、Stream 的 `bind_host` / `advertised_ip` 参数与标签、root-ca 下载端点与前端链接全部删除；Caddy HTTPS 端口与 Stream UDP mux 固定绑定 `127.0.0.1`，媒体放行只剩链路本地 `169.254.0.0/16` / `fe80::/10`。
    - **删除运行时网络应用**：网络设置写端点、应用/断开预检、`NetworkService`、Gateway 发布协议（authorize/ACK/revoke）、Supervisor `rebuild-edge` / `converge-streams`、恢复围栏、日志网络收据、双文件已应用状态全部删除；增量迁移 `0008`（`3751fed02a4a`）删除全部 `settings` 表 `network.%` 行（降级为有文档说明的 no-op：已删行无恢复路径）。
    - **端口只从部署输入来**：唯一常量 `DEFAULT_HTTPS_PORT = 56661`（`network_config.py`）；`CBROWSER_HTTPS_PORT` 只在部署期从 `.env` 读入，deploy.sh 默认值直接运行该常量得出；后端入口默认值、deploy.sh、前端均不再写字面量。`network_config` CLI 只剩 `render`（`--network-dir`、`--https-port`）：确定性写出部署端口的 Caddyfile 并打印 `BIND_HOST=127.0.0.1` / `HTTPS_PORT` / `PUBLIC_ORIGIN` / `CADDYFILE_SHA256`；渲染失败即以 CLI 退出码拒绝部署。
    - **Origin 白名单由部署配置确定性派生**：`derive_origin_whitelist(https_port)`（`127.0.0.1` / `localhost` + 端口，纯 https）；API 启动时从 `CBROWSER_HTTPS_PORT` 派生、Gateway 从同一环境变量派生，两服务读同一部署输入；Gateway 读盘重载的死代码删除。
    - **指纹改为最终产物**：release manifest 与 env 的 `caddyfile_sha256` 改为渲染后 `$DATA_ROOT/network/Caddyfile` 的 SHA-256（生成器源码改动不再改变指纹，端口改动改变指纹）；回退时按目标 release 记录的端口重渲染并校验 sha 与目标 manifest 一致，不一致拒绝。
    - **受信代理来源**：compose `edge` 网络固定 IPAM 子网，deploy.sh 按实例身份摘要派生（`172.{18 + digest mod 14}.0.0/16`，避开 Docker 默认 `172.17.0.0/16`，双实例可共存），写入 `CBROWSER_EDGE_SUBNET`，并以同一值注入 API 与 Gateway 的 `CBROWSER_TRUSTED_PROXY_CIDRS`；部署前预检该子网与已存 Docker 网络子网、宿主接口地址的重叠，重叠即拒绝并提示改 prefix / 数据根或显式指定子网。`client_ip` 两份字节相同拷贝合并为唯一共享模块 `cbrowser.shared.client_ip`，Gateway 镜像经 Dockerfile 白名单引入。
    - **设置页只读**：网络区块只显示当前访问地址与端口（取 `window.location`），表单、保存/应用按钮、应用确认弹窗、root-ca 区块全部删除。
- 复查条件：真实部署（AC-010）、真实引擎下的 Origin 与端口行为（AC-006/007/008/009 真实部分）、各平台真实字体名均未在本机验证（无 Docker、无真实引擎），须在用户机按 t032 演练补验。
- 替代：选项 1 留下整条死链与漂移面；选项 3 保留局域网攻击面，与“彻底不做”的前提相背。**本条替代 ADR 026 的运行时边缘重建部分**：Supervisor 不再接管 Caddy / Stream 的端口重建与版本对账，运行期端口绑定不可变更；ADR 026 其余结论（端口物理隔离的实测结论、单机免外部守护原则）保留；ADR 013 的媒体直连回到仅回环（局域网 host 候选扩展随本条删除）。p053 的“暂搁”前提随本条作废。

## 032 跨服务共享规则收归中立包，镜像按包粒度打包（2026-11-13，t062）

- 背景：p073 登记的跨服务共享代码无中立归属问题全面暴露：Gateway 与 Supervisor 双向 import（端点模块在 Gateway、Agent 凭证在 Supervisor）；原子写有 1 份规范实现加 4 份手写变体（其中一份无 fsync、一份固定暂存名）；per-profile 锁有 3 份独立实现且路由直接访问 service 私有锁注册表；Origin 格式化在部署期另有一份手工实现靠注释维持与请求侧一致；实例 fence 在 REST 视图与协调器各写一份；投递分类在事件转发器定义、工件转发器只借常量手写判断；Supervisor 控制端口出现 8091/8005 两份默认值，控制客户端的 8091 实际无人监听；认证依赖与路由直接以 ORM `SessionModel` 为契约；egress 的 httpx/GeoIP/文件 I/O 住在 domain。各运行镜像为此逐文件 COPY 跨包补丁（三行 Supervisor 文件进 Gateway 镜像、整包 Gateway 进 Supervisor 镜像、API 镜像全量复制后端目录）。
- 选项：
    1. 保留现状，只修 8091 错值与最痛的重复（锁）。
    2. 建中立包收敛全部共享规则与实现，镜像按包粒度打包，依赖方向以测试守护（本 task 采用）。
    3. 把共享代码下沉到 domain 包统一承载。
- 结论：采用选项 2。
    - **中立归属**：`cbrowser/shared/` 为唯一中立包，承载 endpoints（端点/Origin/控制端口权威值）、agent_credentials、atomic_write、profile_locks、delivery、fencing、egress（探针 I/O 与其词汇 ECHO_URLS/错误类型）、client_ip。Gateway 与 Supervisor 互不 import；shared 除 `secret_files` 叶子外零 cbrowser import——这是镜像闭包的硬约束：shared 若依赖 domain，Gateway 镜像（不带 domain）内的 shared 模块将不可导入（闭包测试实测驱动此收敛，探针签名因此由收 ProxyEndpoint 改为收其 proxy_url 字符串）。
    - **单一实现**：原子写全仓一份（独占临时文件 + fsync + replace + 目录 fsync；按 preview 旧实现的所有权语义修正规范实现会在 O_EXCL 碰撞时误删他人暂存的缺陷）；手写点（preview、runtime_agent event_storage/fontconfig、agent_executor state）全部改走 shared，流式 artifact 写为例外但补目录 fsync 对齐耐久契约。per-profile 锁全仓一份注册表，API 侧 ProfileService 以公开方法 `profile_lock()` 供路由协调，Supervisor 核心与恢复协调器共用同一注册表与 `is_profile_locked` 探查。Origin 白名单改由同一 `normalize_origin` 构造；fence 与投递分类各一份函数、全部消费方委托。
    - **端口权威**：`DEFAULT_SUPERVISOR_PORT = 8005` 与派生的 `DEFAULT_SUPERVISOR_URL` 为唯一权威，runner/控制客户端/compose/就绪探针全部对齐，8091 字面量全仓清除并由测试锁定。
    - **领域会话**：`AuthService` 返回领域对象 `AuthenticatedSession`（不含 token_hash 等存储细节），依赖与路由只消费领域对象，ORM 只留在 service 层内。
    - **镜像边界**：Dockerfile 按包粒度 COPY（API 改为 cbrowser 整包 + migrations），删除全部跨服务逐文件补丁；Gateway 镜像不再带 Supervisor 文件与 domain，Supervisor 镜像不再带 Gateway 包，Browser 镜像补 shared 整包与 secret_files 叶子一行。闭包验证分两层：单元层按各 Dockerfile 组装文件树逐模块实际导入（test_t062_image_closure）加 import 图边界守护（test_t062_boundaries），a26 的 Browser 闭包模型同步把 shared 作为 terminal 包（只展开其顶层叶子引用）；真实 Docker 构建与 readiness 属 [deploy] 验证，顺延本地（AC-005 登记）。
- 替代：选项 1 留下双向依赖与多份权威实现，漂移面不收敛；选项 3 让 domain 承载 I/O 与基础设施，破坏领域层纯度且 Supervisor/Gateway 镜像仍需整包带 domain。**本条不改变** ADR 031 的部署期网络结论与 ADR 029 的同视角观测结论，只迁移其实现归属（`network_config` 仍为部署期模块、探针仍由 Browser 视角执行）。

## 033 引擎制品解压清单固定与指纹升级默认阻断（2026-11-13，t068）

- 背景：p081 调研建议 `CLOAKBROWSER_VERSION` 钉死 + `CLOAKBROWSER_AUTO_UPDATE=false` + Ed25519 校验下载，但实测暴露信任缝隙：`cloakbrowser==0.6.4` 只对**下载压缩包**的 `SHA256SUMS` + 分离 `SHA256SUMS.sig` 做 Ed25519 验签（包内硬编码公钥 `MKFKwIhUcKWq5xTuNA0Ovg99njcDEcEJvmWYYhApvaU=`），解压后目录无签名；`ensure_binary()` 命中已有可执行 `chrome` 即不校验 ELF/SHA-256/版本（实测损坏非 ELF 伪文件被直接返回）；`CLOAKBROWSER_DOWNLOAD_URL` 关闭验签、`CLOAKBROWSER_SKIP_CHECKSUM=true` 跳过校验、free-tier license key 丢弃版本 pin、`latest_version_<tag>` marker 在 `AUTO_UPDATE=false` 下仍能劫持无 pin 解析；`chrome --version` 只报四段无法区分补丁号。engine-cache 只读挂载不足以代替 cache_init/自动更新路径核验。
- 选项：
    1. 只加 `CLOAKBROWSER_VERSION` + `AUTO_UPDATE=false` 环境变量，信任 SDK 缓存（拒绝：缓存命中不校验，损坏/替换不可见）。
    2. 在 deploy / cache_init / BrowserRunner 三处用仓库权威 per-file SHA-256 清单校验解压制品，强制禁用自动更新与所有绕过变量；指纹基线探针 + 差异门禁默认阻断（本 task 采用）。
    3. 为实验下载第二套未批准 arm64 引擎做真实跨版本升级比对（拒绝：违反 ADR 021，且本机无该制品）。
- 结论：采用选项 2。
    - **单一权威清单**：`cbrowser/engine_artifacts.py` 登记 `linux-arm64/146.0.7680.177.3` 的 15 个文件 SHA-256（`chrome` = `3cf52315…`）、ELF machine 183、压缩包 `8b71ce53…`、信任来源；`linux-x64/146.0.7680.177.5` 只固定压缩包摘要并显式标注解压件未验证。
    - **三处校验**：`deploy.sh` 发布前 `verify-cache --allow-empty`（空缓存延后到 cache_init）；Supervisor `cache_init` helper 容器内 `verify_wrapper_package` + `enforce_pinned_engine_env` + `ensure_binary(browser_version=pinned)` + `verify_extracted_engine_cache`；`BrowserRunner.resolve_engine_binary` 启动前全量复验。release manifest 写入 `engine` 块，`compose.yaml` 注入 `CLOAKBROWSER_AUTO_UPDATE=false` 与 `CBROWSER_ENGINE_BUILD`。
    - **fail-closed**：损坏/缺文件/ELF 不符/版本不符/未批准 build/自动更新 marker/绕过环境变量/缓存树变更后未复验，一律拒绝启动或部署。
    - **指纹升级门禁**：`cbrowser/fingerprint_verification/` 真实引擎四上下文（main/iframe/Worker/ServiceWorker）离线探针 + 本地 TLS `ClientHello` JA3/JA4；`comparator.compare_reports` 遇漂移/缺测/上下文翻转/未获批非确定方差/`inconclusive` 默认 `blocked`，仅显式批准规则可放行同制品重复。
    - **TLS 结论**：BoringSSL 逐连接随机化扩展顺序，`ja3` 不可作跨连接一致判据；`ja4`（稳定两值：首次握手 / TLS1.3 PSK 复用）与 `ja3_sorted` 才是可复现身份；windows 与 macos 共用同一 Linux TLS 栈。不引用厂商通过率。
    - **未能验证**：真实跨版本引擎升级放行（本机只有一套已获准 arm64 制品）、linux-x64 解压件完整性、公网第三方检测站。
- 复查条件：出现第二套已获准 `linux-arm64` 制品时，用本探针产出两套基线并跑 `compare` 验证真实跨版本放行/阻断；cloakbrowser 升级或 `BINARY_SIGNING_PUBKEYS` 轮换时重跑验签与清单核对。
- 替代：无（细化并收紧 ADR 021 的 cloakbrowser 锁定，不升级版本）。
