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

## 007 冻结 v2 双容器 WebRTC 目标架构、废弃排他控制租约与定案本地运行基准（2026-10-27T18:50:00+08:00）

- 背景：早期设计中预设单 Profile 单容器运行、排他控制租约（`ControlSession`、心跳超时、抢占接管等待）、60 FPS 恒定帧率、未经验证的 300ms 画面恢复指标，并假设 Selkies 2.1.0 具备原生公共 ICE restart API 及以远端 Linux x86_64 服务器为基准。t001 技术验证（s001–s009, d001–d014）与 2026-10-27 用户执行调整（跳过公网/Linux x86 验证，基准改为当前电脑 Docker + 本机 Chrome 访问）提供了确定性事实与调整依据。
- 选项：
    1. 维持旧设计的单容器与独占控制租约模型，继续假设无 GPU 下恒定 60 FPS 并等待远端 Linux 服务器验证。
    2. 冻结经验证的 v2 目标架构：
        - 采用同 Profile 双容器（Browser Runtime 显式 `shareable` IPC 与 Stream Runtime 加入），基于专属卷 X11 Socket 与 MIT-SHM 零拷贝捕获，彻底切断媒体容器对浏览器用户数据的直接挂载；
        - 彻底废弃独占控制租约与接管锁，多外部页面（ViewerConnection）以 `controller` 角色并发解码与输入，依靠官方 `client_tab_id`、Web Locks 与 `resume_key` 维持页面身份与重连；
        - 采用单 Profile 单一共享编码管线，执行 8/30 FPS 自适应仲裁与全后台暂停捕获；
        - API 为唯一 SQLite 写入者，Supervisor 为唯一 Docker Socket 持有者，经受控 UDS 隔离代理 CDP 与事件；
        - 明确 Selkies 2.1.0（commit `6ee68a7a`）同 PC 凭证轮换依赖进程内私有接口适配器（属于内部维护约束，非官方原生 public API）；
        - 将目标部署基准定案为当前 MacBook Pro M1 Max 上的 OrbStack Docker（10 CPU / ~15.66 GiB RAM，CPU 纯软件编码无 GPU 预算）配合本机 Chrome 访问；公网与原生 Linux x86_64 验证明确记为 `NOT_RUN / USER_WAIVED`。
- 结论：采用选项 2。正式冻结 v2 目标架构。明确当前生产代码尚未实现该目标（当前生产代码仍保持旧基线），后续任务（t002+）据此实施。
- 替代：001（细化并替代单容器沙箱假设为双容器 shareable IPC 隔离）；明确废弃早期计划中关于独占控制租约、恒定 60 FPS 及 300ms 恢复假设。

## 008 区分首次异常与三次自动重试计数（2026-10-30T01:05:04+08:00）

- 背景：架构计划要求异常后完整执行2/10/30秒三次自动重试。原始失败总数在3时阻断会只执行两次重试，与三档等待冲突。
- 选项：
    1. 首次异常算入三次，实际只重试两次。
    2. 首次异常后执行三次重试，持久字段继续记录实际异常总数。
- 结论：采用选项2。failure_count依次为1/2/3时分别等待2/10/30秒，第4次异常阻断；API与Supervisor共用domain/runtime_policy常量。正常启动不清历史，手动重试通过API幂等事务清除阻断。数据库字段结构不变，当前仅隔离v2测试数据；正式用户数据迁移仍由t010负责。
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
    - **Caddy 2.11.8**：`deploy_v2.sh` 默认引用改为 digest 固定；现有 Caddyfile（`tls internal`、`auto_https disable_redirects`、`handle` 转发）经 `caddy validate` 实测通过，行为不变。
    - **cloakbrowser 锁定 0.6.4（D7）**：0.6.4 无 key 模式使用免费 Chromium 146 内核、不校验 license、无并发上限；0.7.0 删除无 key 路径，自动申领的免费 key 只允许 1 个并发会话，会破坏多 Profile 并发。故精确锁定 `cloakbrowser[geoip]==0.6.4`，不升 0.7.x。
- 复查条件：上游恢复无 key 路径且免费 key 不再限制并发会话时，重新评估 cloakbrowser 升级（需真引擎并发验证）；Python/Debian/Caddy 后续大版本升级按同一 digest 固定 + SPIKE + 全量门禁流程。
- 替代：无（不采用 `--legacy-peer-deps` 类绕过，不保留手写并行依赖清单）。
