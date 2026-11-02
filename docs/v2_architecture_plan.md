# CBrowser v2.3：最终技术架构修订与实施方案

**目标：** 对现有 CBrowser 仓库进行完整架构重构，保留 CloakBrowser 引擎和核心业务能力，采用当前电脑上的Docker Compose/OrbStack单机部署，通过同一台Mac的Google Chrome Stable访问使用；公网和远程服务器不是本次交付目标。

**架构基准：** Profile、BrowserRuntime、ViewerConnection 三者分离。一个 Profile 对应一个真实浏览器运行实例，一个 Profile 可以同时拥有多个 ViewerConnection。

**开发原则：** 先完成关键技术验证，再冻结架构、迁移数据库和删除旧链路。任何未通过验证的技术能力不得以“后续再解决”的方式进入正式版本。

______________________________________________________________________

## 执行调整：环境验证豁免（2026-10-27T18:35:07+08:00）

用户明确指示“把这两个跳过”：公网环境验证、原生 Linux x86_64 环境验证。本次改造按以下调整执行，优先于下文原环境门禁：

- 第18章公网候选/公网TURN穿透，以及原生Linux x86_64运行验证记为`NOT_RUN / USER_WAIVED`，不冒充通过，不再阻塞本次架构定案和后续实施。
- 同类环境要求适用于后续验收：原生Linux x86_64和公网穿透执行记用户豁免；第19章性能基准已按后续用户指示改为当前Mac/OrbStack实际配额，仍运行性能场景、8小时压力、1000次IME/剪贴板、安全与恢复验收，记录真实硬件、结果及限制，不能将本机数据当成被豁免环境的证明。
- 保留公网/TURN配置、Linux x86_64镜像构建和相关功能实现；仅跳过上述环境上的验证，不删除功能，也不授权外部部署、真实数据迁移或发布到未知目标。
- 第18章其余实验、项目测试、独立review及本地真实黑盒仍须通过。原文“全部通过”按修订后的有效范围解释，被豁免项须始终单列。

## 修订：开源项目调研意见复核（2026-10-30T20:46:00+08:00）

外部调研意见（16 个远程桌面/WebRTC 项目对照）经 Selkies 2.1.0 固定源码与已验证发现（d007、d013、d014、d017）复核后，按以下范围修订本文：

- 采纳：页面可见性只用 Selkies 原生每 Peer `STOP_VIDEO`/`START_VIDEO`，Gateway 不再聚合可见性与活动，Supervisor 前台状态改由 Agent 上报（第9章）；剪贴板与会话内文件传输改为显式配置 Selkies 策略，文件只走 Artifact Service（8.1、8.4）；CBrowser 自有内部协议独立 schema 与版本（7.5）；下载捕获增加目录对账兜底（11.3）；前端处理页面冻结/恢复并显示连接诊断，不显示无解释黑屏（13.4）。
- 已在本文中、无需改动：Selkies 为核心、`client_tab_id` 多页面、每 Profile 共享编码管线、每 Profile 一个 UDP mux 端口、双容器 + 同 Profile IPC/X11/Pulse 卷、原生 IME 与 XTest、CDP 仅内部、不用 noVNC/KasmVNC。调研中“原计划 → 新决定”表的多数“原计划”项并非 v2.3 内容。
- 不采纳：下载捕获改为文件系统监控优先（CDP 事件给出明确完成状态，d002 已验证，文件监控只作兜底）；`/dev/shm` 改为 2 GiB（1 GiB 已在 d004 及 t004/t005 实测通过，由 t009 压测记录峰值后再定）；启用 Selkies WebSocket 双模式备用（本次本机部署不需要，增加一倍测试矩阵）；Selkies 与 KasmVNC 对比基准（引擎已定案并实现，不再回头比选）。

## 修订：t001–t007 累计审阅与 p008/p010 闭环（2026-11-01）

t001–t007 累计三路审阅的采纳项已全部落地并合入 main。以下是相对本文原方案的架构级修订；当前实现细节以 `docs/blueprint/` 与 `docs/specs/` 为准。

- 运行观测权威：Supervisor 以 Docker 容器状态/退出码与 Runtime Agent 进程监督为权威观测；磁盘事件只作诊断补充，不再直接驱动 `observed_state`/`desired_state`；`lifecycle/error` 收敛为 `observed_state=error` 且保留 `desired_state=running`；扫描对同实例会话短路；事件使用游标与 quarantine。
- Stream 出站策略按 `CBROWSER_WEBRTC_MODE` 分档：relay-only 仅放行 Gateway/coturn/本实例 UDP mux；local/lan/public 允许公共目的地址；私有/保留段始终 DROP。修订本文“Stream 只允许实际 Gateway/coturn”的单档表述。
- 停止/清理与信令面解耦：Gateway 不可达时降级 teardown；端口释放在 finally 中执行；停止协调有显式上限并暴露错误。
- Gateway 端点单一配置源，默认 18080；Origin 统一归一；删除 18097 硬编码。
- 凭证与权限：`agent_secret` 迁至 `secrets/<profile>/agent_secret.txt`（0600，仅挂 Stream）；内部 Supervisor/Gateway/Control token 强制 0600；宿主目录 chown 1000 + 0700/0750，x11 保持 1777。
- 认证限速：受信代理 XFF + 每来源滑动窗口 + 全局预算；429 返回 Retry-After。
- TURN 轮换：future 校验 generation；current 过期 fail-closed；disconnect/stop 取消轮换任务与 pending future；upstream 关闭码透传。
- 事件 spool：每实例游标、投递后回收、有界 ACK；`runtime_events` 随 Profile 删除，`audit_events` 保留作为审计总账。
- 数据与输入契约：tags 使用三态（缺席不改 / null 清空 / `[]` 清空）；`failure_count` 第 4 次异常阻断；`name` 等非空字段显式 null 返回 422。
- 前端：诊断数组有界、输入合并、死阶段清理、i18n 补全、测试去固定 sleep。
- 构建：`npm run build` 的 prebuild 自动 vendor、postbuild 自动校验；Selkies 清单迁至 `config/selkies/selkies_web_sha256.txt`；生产 Dockerfile 对 COPY 的 `dist/` 运行同一校验。
- Selkies resume：viewer 隧道关闭/Gateway 断线后 Agent 保留 loopback upstream 10 秒，同 `tab_id`/`resume_key` 重连由 `RESUMED` 接管；窗口到期或 Agent 停止时关闭（d025）。
- 结构：RecoveryCoordinator tick、docker_adapter、stream_agent 拆分为更小模块；p001/p005 闭环。
- 待办：p001、p005–p013 全部闭环，`docs/pending/todo/` 为空。t008、t013、t014、t009、t010、t011、t012 仍按 goal queue 实施。

## 修订：单人使用的剪贴板与输入验收（2026-11-02）

用户决定，优先于 8.4 与 19.3 原文：

- 8.4：Profile `clipboard_sync` 开启时 Selkies `clipboard_seamless=true|locked`，纯文本双向自动同步（直接 Cmd+C/V）；关闭时 `enable_clipboard=false`，双向无传输；二进制剪贴板仍关闭。19.3「用户剪贴板原内容保护」「后台页面不自动覆盖本机剪贴板」作废（decisions 012）。
- 19.3：1000 次中文组合输入与 1000 次剪贴板改为 t009 手动清单验收（四类输入框、双页面、复制粘贴同步）；t014 剩余自动化 E2E（p015）不做，t014 以 AC-001/005 已合入状态 drop。

# 1. 最终技术决策

## 1.1 固定技术栈

|模块|最终方案|
|---|---|
|外部客户端|Google Chrome Stable|
|前端|React 19 + TypeScript + Vite|
|路由|React Router 7|
|API 数据管理|TanStack Query 5|
|后端|Python 3.12 + FastAPI + Pydantic 2|
|数据库|SQLite + SQLAlchemy 2 + Alembic|
|浏览器内核|当前 CloakBrowser|
|浏览器运行环境|Linux + Xvfb + Openbox|
|远程显示|Selkies 2.1.0|
|实时媒体|WebRTC|
|信令路由|独立 Stream Gateway|
|媒体中继|coturn|
|HTTPS|Caddy|
|容器管理|Docker Engine API + Runtime Supervisor|
|浏览器自动化|受控 CDP 代理|
|文件管理|独立 Artifact Service|
|测试|Pytest、Vitest、Playwright、Docker Compose 集成测试|

Selkies 固定到官方 2.1.0 发布版本，对应提交 `6ee68a7a815956e6745e916741f13335e0b3ff53`。

参考：

- https://github.com/selkies-project/selkies/releases/tag/2.1.0
- https://github.com/selkies-project/selkies/blob/2.1.0/src/selkies/input_handler.py
- https://github.com/selkies-project/selkies/blob/2.1.0/src/selkies/webrtc_signaling_server.py
- https://docs.selkies.io/latest/secure-mode
- https://docs.selkies.io/latest/reference/settings

## 1.2 明确删除的设计

01. 不实现 CBrowser 自己的外部 Chrome 标签栏。
02. 不实现独占控制租约、租约代次、控制权接管或等待释放。
03. 不引入 Redis。
04. 不使用 noVNC 作为正式远程显示客户端。
05. 不继续维护旧的 KasmVNC/RFB 协议转换层。
06. 不允许 Caddy 自动发现动态容器并直接代理到容器 IP。
07. 不允许 API 和 Supervisor 无规则地同时写入 SQLite。
08. 不将中文输入法实现为剪贴板粘贴模拟。
09. 不允许每个外部页面直接修改同一个 Selkies 显示的全局帧率。
10. 不允许 Browser Runtime 暴露公网 CDP 端口。
11. 不使用 Docker 自动重启策略代替业务状态恢复。
12. 不因外部标签页关闭而停止浏览器进程。
13. 不在 Gateway 重复采集或聚合页面可见性与活动状态；不重新实现 Selkies 已提供的每 Peer 暂停、IME、键鼠输入和剪贴板传输。
14. 不通过 Selkies 会话内文件传输上传或下载文件。

______________________________________________________________________

# 2. 正确的对象模型

## 2.1 三个核心对象

### Profile

保存一个隐私浏览器的长期身份、指纹配置、代理设置、浏览器数据和文件引用。

### BrowserRuntime

代表该 Profile 的真实浏览器进程、浏览器窗口、X11 显示和运行时状态。

### ViewerConnection

代表一个外部 CBrowser 页面与一个 BrowserRuntime 之间的远程显示和输入连接。

对象关系：

```text
Profile A
└── BrowserRuntime A
    ├── ViewerConnection A1
    ├── ViewerConnection A2
    └── ViewerConnection A3

Profile B
└── BrowserRuntime B
    └── ViewerConnection B1
```

ViewerConnection 不代表浏览器所有权，不具有独占控制权。

## 2.2 外部 Chrome 标签页

每个外部 Chrome 标签页打开的都是 CBrowser 页面。页面可以选择任何 Profile，并随时切换操控目标。

例如：

- Chrome 标签 A 当前操作 Profile A。
- Chrome 标签 B 当前操作 Profile B。
- Chrome 标签 C 也操作 Profile A。

A 和 C 看到的是同一个真实浏览器窗口。A 创建内部标签页后，C 也会看到该标签页。

用户切换外部页面中的目标时，只替换该页面的 ViewerConnection。原 Profile 的 BrowserRuntime 继续运行，其他 ViewerConnection 不受影响。

## 2.3 内部浏览器标签页

内部标签页、地址栏、导航按钮和网页内容全部来自真实的 CloakBrowser 窗口。

CBrowser 不仿制内部标签栏，不通过 CDP 绘制浏览器 UI，不将内部标签页建模为 React 路由。

## 2.4 连接身份与权限的区别

Selkies 的 `client_tab_id` 用于区分不同外部页面及其重连身份。

它不是：

- 控制租约；
- Profile 所有者；
- 唯一控制者 ID；
- 禁止其他页面连接的锁。

同一 Profile 可以有多个不同 `client_tab_id` 的 controller Peer，并且它们都可以向同一个浏览器发送输入。

______________________________________________________________________

# 3. 最终服务拓扑

固定常驻服务：

```text
caddy
cbrowser-api
cbrowser-supervisor
cbrowser-stream-gateway
coturn
```

每个 Profile 动态创建两个容器：

```text
browser-runtime-{profileId}
stream-runtime-{profileId}
```

数据目录：

```text
/data/
├── cbrowser.db
├── settings/
├── engine-cache/
├── profiles/
│   └── {profileId}/
│       └── profile/
├── artifacts/
│   └── {profileId}/
│       ├── uploads/
│       └── downloads/
├── runtime-events/
│   └── {profileId}/
└── backups/
```

`profiles/{profileId}/profile` 保存浏览器用户数据。

`artifacts/{profileId}` 是独立的文件存储，不能与浏览器用户数据混为一体。

`runtime-events/{profileId}` 保存需要跨容器、跨服务重启恢复的运行事件。

______________________________________________________________________

# 4. X11、IPC 和容器隔离

## 4.1 保留双容器架构

Browser Runtime 运行 CloakBrowser、Xvfb、Openbox 和 Browser Agent。

Stream Runtime 运行 Selkies、Stream Agent、画面捕获、视频编码和远程输入。

两个容器通过专属 X11 Socket 卷连接。

不将两个容器合并，因为浏览器用户数据和媒体处理进程应当保持独立的容器与文件权限边界。

## 4.2 同一 Profile 共享 IPC 命名空间

X11 的 MIT-SHM 可能使用 `XShmGetImage` 等共享内存机制。仅挂载 Unix Domain Socket 不等于共享 System V IPC 命名空间和 `/dev/shm`。

因此，固定采用以下方式：

- 每个 Browser Runtime 使用独立 IPC 命名空间。
- 对应的 Stream Runtime 使用 Docker 的 `IpcMode=container:<browser-runtime-id>`。
- 每个 Profile 独立配置 X11 Socket 卷和 IPC 命名空间。
- 不同 Profile 之间不共享 IPC 命名空间。
- Browser Runtime 的 `/dev/shm` 设置为 1 GiB，Stream Runtime 使用同一 IPC 命名空间。
- Xvfb 显式启用 MIT-SHM、XTEST、XFIXES 等所需扩展。
- 正式运行前验证 X11 捕获实际使用共享内存，并记录是否发生回退。

这项设计的安全边界是：同一 Profile 的浏览器进程与媒体进程被视为相互信任的协作进程，但不同 Profile 仍然完全隔离。

## 4.3 X11 访问权限

每个 Profile 使用自己的 Xauthority 文件和 X11 Socket。

Browser Runtime 负责创建 Xvfb 和 Xauthority；Stream Runtime 只获得访问该显示所需的权限。

Stream Runtime 不挂载浏览器用户数据目录。

Xvfb 不监听 X11 TCP 端口，不使用宿主机 X11 显示。

______________________________________________________________________

# 5. 音频架构

Selkies 的音频配置必须显式定义，不依赖默认值。

CBrowser 保留远程浏览器音频能力，采用每 Profile 独立的虚拟 PulseAudio 服务。

- Browser Runtime 启动虚拟 PulseAudio 服务。
- CloakBrowser 将声音输出到虚拟音频设备。
- PulseAudio Socket 和认证文件放在该 Profile 的专属共享卷。
- Stream Runtime 通过该 Socket 读取音频监视源。
- Selkies 负责将音频编码并传输给各 ViewerConnection。
- 每个外部页面可以独立静音，不影响同一 Profile 的其他页面。
- 不同 Profile 不共享 PulseAudio Socket 或音频源。

音频服务必须在 Browser Runtime 启动时就绪。若音频服务不可用，运行状态显示为音频子系统故障，不允许 Selkies 在后台持续产生无法连接音频服务的错误日志。

验收时测试浏览器音频播放、静音、多个 ViewerConnection 同时接收音频，以及关闭一个外部标签页后其他页面音频不中断。

______________________________________________________________________

# 6. 浏览器数据与文件存储

## 6.1 浏览器用户数据

每个 Profile 使用独立的持久化数据目录：

```text
/data/profiles/{profileId}/profile
```

该目录保存 Cookie、网站存储、浏览器偏好、扩展、浏览历史和内部标签页恢复数据。

Browser Runtime 只挂载自己的目录。

## 6.2 Artifact 存储

保留现有仓库中的独立 Artifact 存储结构：

```text
/data/artifacts/{profileId}/uploads
/data/artifacts/{profileId}/downloads
```

该目录独立于浏览器用户数据。复制浏览器状态时不复制 Artifact 文件。

Browser Runtime 将对应目录挂载到：

```text
/exchange
```

因此，API 返回给浏览器自动化和文件选择器的 `container_path` 必须使用容器内路径，例如：

```text
/exchange/uploads/example.pdf
```

不能返回宿主机路径。

## 6.3 上传流程

1. API 接收上传请求。
2. Artifact Service 检查文件名、MIME 类型、配额和磁盘空间。
3. 文件写入临时文件。
4. 完成校验后原子移动到 `/data/artifacts/{profileId}/uploads/`。
5. Browser Runtime 通过 `/exchange/uploads/` 访问该文件。
6. API 返回 Artifact ID 和容器内路径。

上传失败不留下可被浏览器误用的半成品文件。

## 6.4 下载流程

1. Browser Agent 监听 CDP 下载事件。
2. 浏览器将下载写入 `/exchange/downloads/`。
3. Browser Agent 在下载完成后发送事件。
4. Supervisor 将事件转发给 API。
5. Artifact Service 校验文件状态、大小和配额。
6. API 写入 Artifact 元数据。
7. 下载文件正式出现在管理页面。

外部 CDP 自动化客户端修改下载行为后断开连接时，必须恢复 CBrowser 的下载捕获机制，保留现有仓库的下载重启逻辑。

______________________________________________________________________

# 7. Stream Gateway 与动态信令路由

## 7.1 Caddy 的职责

Caddy 只处理固定入口：

```text
/api/*      -> cbrowser-api
/stream/*   -> cbrowser-stream-gateway
其他路径    -> 前端静态资源
```

Caddy 不查询 Docker，不扫描 Profile 容器，不动态生成反向代理目标。

## 7.2 Agent 主动注册

每个 Stream Agent 启动后，通过专属认证连接注册到 Stream Gateway。

注册信息包含：

- `profile_id`
- `runtime_instance_id`
- `selkies_version`
- `runtime_state`
- `webrtc_udp_port`
- `config_version`

Gateway 在内存中保存活动运行时注册表。

Agent 每 10 秒发送一次健康消息。连接丢失后按 1、2、4、8、16、30 秒的退避间隔重连。

## 7.3 ViewerConnection 的信令流程

外部 Chrome 访问：

```text
wss://cbrowser.example/stream/{profileId}/signal
```

Gateway 执行以下流程：

1. 验证登录会话。
2. 验证 Origin。
3. 校验 Profile 是否存在、运行时是否就绪。
4. 生成 `connectionId`。
5. 找到对应 Stream Agent。
6. 建立独立的信令隧道。
7. 将 SDP、ICE 和 Selkies 信令消息双向转发。
8. 视频和音频媒体建立后直接走 WebRTC，不经过 Gateway。

每个 ViewerConnection 使用自己的信令隧道。关闭其中一条连接不影响其他连接。

信令 WebSocket 心跳只用于判断信令连接存活，不携带页面可见性或活动状态。

## 7.4 运行时停止

Supervisor 停止 Profile 时：

1. 将运行时标记为不可用。
2. Gateway 关闭该 Profile 的全部 ViewerConnection。
3. 停止 Stream Runtime。
4. 停止 Browser Runtime。
5. 回收媒体端口。
6. 更新实际运行状态。

Gateway 重启不会停止浏览器。Agent 重新注册后，外部页面可以重建连接。

## 7.5 内部协议边界

CBrowser 只定义自己的内部协议，每种协议有独立 schema、版本字段和运行时校验，不合并为一个通用 WebSocket JSON 处理器：

|协议|两端|职责|
|---|---|---|
|Agent 注册与信令隧道|Stream Agent ↔ Gateway|注册、健康、信令转发、运行时控制（TURN 配置、配额、ICE 轮换）|
|Runtime RPC|Browser Agent ↔ Supervisor（UDS）|浏览器健康、CDP 流、下载与退出事件|
|生命周期 RPC|API ↔ Supervisor|期望状态、实际状态、运行事件、配置快照|
|会话授权|API ↔ Gateway|登录会话与 Profile 访问校验、运行时状态|

媒体、输入、IME、剪贴板沿用 Selkies 2.1.0 官方协议，CBrowser 不另定义。文件内容只经 Artifact Service 的 HTTP 接口传输，不进入信令或 JSON 消息。

______________________________________________________________________

# 8. Selkies 多连接与页面身份

## 8.1 共享 Token

每个 Profile 使用独立的 Selkies master token 和 controller token。

master token 永远不返回前端。

同一 Profile 的多个外部页面可以使用同一个 Profile 级 controller token。所有正式客户端的角色为 `controller`。

Selkies 配置：

```text
SELKIES_MODE=webrtc
SELKIES_ENABLE_DUAL_MODE=false
SELKIES_ENABLE_SHARING=true
SELKIES_ENABLE_COLLAB=false
SELKIES_FILE_TRANSFERS=none
```

上述设置必须显式传入 Stream Runtime。Selkies 2.1.0 中 `enable_dual_mode` 默认 `true`、`file_transfers` 默认 `upload,download`，不显式设置即会开启 WebSocket 模式切换和绕过 Artifact Service 的会话内文件传输。

不设置 `mk_control=true`。

`enable_collab=false` 关闭的是协作权限扩展，不会禁止具有 controller 角色的正常客户端连接。

## 8.2 `client_tab_id`

使用 Selkies 官方客户端的 `pageTabId()` 实现，不自行重写信令身份协议。

官方实现将页面 ID 保存在 `sessionStorage`，刷新页面后保留 ID，不同页面通常拥有独立 ID。

CBrowser 的客户端适配层必须：

- 保留官方 `client_tab_id` 发送逻辑。
- 保留官方 `resume_key` 重连逻辑。
- 新建外部标签页时使用 `target="_blank" rel="noopener"`。
- 在连接前检查活动页面是否存在相同的 Tab ID。
- 发现复制标签页造成的 ID 冲突时，生成新的页面 ID 并重新连接。
- 同一个页面重连时，保持原页面身份。
- 不同页面连接同一 Profile 时，必须具有不同的 `client_tab_id`。

这不是租约系统，而是防止 Selkies 将“另一个外部页面加入”误判为“原页面重新连接”。

## 8.3 多页面输入

同一 Profile 的多个 controller Peer 同时输入时，事件按实际到达 X11 输入系统的顺序处理。

不实现独占控制者、输入锁或接管等待。

## 8.4 剪贴板策略

剪贴板传输使用 Selkies 官方剪贴板消息，CBrowser 不实现自己的同步协议。

- Profile 的 `clipboard_sync` 映射到 Selkies `enable_clipboard`：开启为 `true`，关闭为 `false`；`in`/`out` 单向模式保留为后续可选值，本次不暴露。
- `enable_binary_clipboard=false`，本次只支持纯文本。
- 上述值由服务端固定并锁定（Selkies `|locked` 语义），客户端设置不能覆盖。
- 前端 `ClipboardBridge` 只处理本机剪贴板权限、页面焦点和权限拒绝提示，不改写 Selkies 剪贴板消息。

______________________________________________________________________

# 9. 多连接共享编码器与帧率

这是必须纠正上一版设计的关键部分。

**一个 Profile 对应一个共享的显示捕获和编码管线。不能假设每个 ViewerConnection 都有独立的服务端编码器和独立的 FPS。**

## 9.1 每连接与每 Profile 的设置分离

每个 ViewerConnection 通过 Selkies 官方客户端在页面 `visibilitychange` 时发送 `STOP_VIDEO`/`START_VIDEO`（音频为 `STOP_AUDIO`/`START_AUDIO`）。Selkies 2.1.0 据此只开关该 Peer 的 RTP sender，其他 Peer 不受影响；恢复的 Peer 总是收到关键帧。

每个 ViewerConnection 不能直接修改该 Profile 的全局编码帧率。

Profile 的服务端捕获和编码帧率由 Stream Agent 统一决定。

## 9.2 固定帧率策略

初始配置：

```text
SELKIES_FRAMERATE=8,8-30
```

表示初始 8 FPS，允许在 8–30 FPS 范围内调整。

策略：

- 至少存在一个可见且需要流畅显示的连接：目标 30 FPS。
- 页面可见、画面静止且没有活动时：目标 8 FPS。
- 检测到滚动、输入或显著画面变化：提升到 30 FPS。
- 检测到视频、动画等持续变化内容时，不因用户没有键鼠输入而错误降到 8 FPS。
- 所有连接均隐藏或断开后：暂停服务端画面捕获。
- 任一连接恢复可见后：恢复捕获，先以 8 FPS 建立画面，再根据活动情况提升。

### 9.3 信号来源与单一仲裁

帧率与捕获决策的全部输入都在 Stream Runtime 内取得，不经过 Gateway：

|信号|来源|
|---|---|
|每 Peer 可见性|Selkies `STOP_VIDEO`/`START_VIDEO` 回调|
|Peer 加入与离开|Selkies consumers 变化与 Peer 断开回调|
|用户输入|Selkies 输入数据通道（键鼠、滚动、IME 提交）|
|画面运动|捕获 damage 信号，不用 `encoded_fps`（d005）|
|资源配额|Supervisor 经 Gateway 下发的 Profile 级 FPS 上限|

Stream Agent 以单一串行仲裁器（d013）挂接上述 Selkies 回调，统一执行 pause/resume/set_framerate，避免 Selkies 内置的全部暂停规则与 Agent 帧率策略双头控制。仲裁器的暂停语义与 Selkies 2.1.0 原生规则一致：该显示的全部 consumer 都暂停时才停止捕获。

Gateway 不记录 `visible`、`last_activity`，也不向 Agent 发送可见性更新。只要存在一个未暂停的 Peer，后台页面就不能降低全局编码帧率。

Supervisor 资源策略需要的“是否有前台 Viewer”由 Stream Agent 在健康消息中上报（未暂停视频 consumer 数、捕获是否运行，均取自 Selkies 状态）。Gateway 只保存 Agent 最近一次上报值，供 Supervisor 现有查询端点读取，不从页面采集。

页面在可见状态下失去响应（主线程卡死、调试暂停）时不会发送 `STOP_VIDEO`，该 Peer 继续计为消费者，直到 PeerConnection 断开后由 Selkies 移除。这只多占用捕获资源，不影响其他页面，接受该代价。

## 9.4 固定屏幕尺寸

远程显示尺寸由 Profile 配置决定，不由某个外部标签页的窗口尺寸决定。

默认：

```text
1920×1080
DPR=1
```

Selkies 的页面身份和连接恢复不能让第一个或最后一个连接的页面大小改变远程显示尺寸。

如果需要改变屏幕分辨率，用户必须通过 Profile 配置修改并明确应用新设置。

______________________________________________________________________

# 10. WebRTC 端口与 coturn

## 10.1 单 Profile 一个 UDP mux 端口

每个 Stream Runtime 使用一个独立 UDP mux 端口。该 Profile 的所有 ViewerConnection 共享这个端口。

端口池：

```text
30000–30991/UDP
```

Supervisor 通过 Docker Engine API 分配端口并以相同的容器内端口发布到宿主机。

例如：

```text
Profile A: 30000/UDP
Profile B: 30001/UDP
Profile C: 30002/UDP
```

Selkies 配置：

```text
SELKIES_WEBRTC_UDP_MUX_PORT=<allocated_port>
```

不同时设置 `webrtc_port_range`，因为 UDP mux 已经提供固定单端口模式。

## 10.2 网络模式

部署环境通过配置明确指定：

```text
CBROWSER_WEBRTC_MODE=local|lan|public|relay-only
CBROWSER_WEBRTC_ADVERTISE_IP=<实际可达地址>
```

`CBROWSER_WEBRTC_ADVERTISE_IP` 传递给 Selkies 的 `SELKIES_WEBRTC_PUBLIC_IP`。

`public` 模式必须保证：

- 公网地址可达。
- 宿主机 UDP 端口正确发布。
- 防火墙允许对应的媒体端口。
- ICE host candidate 中的地址和端口与实际发布的地址和端口一致。

## 10.3 网络拓扑

Browser Runtime 只接入自己的 `browser-egress-{profileId}` 网络。

Stream Runtime 只接入自己的 `profile-stream-{profileId}` 网络，不额外连接 `stream-egress-{profileId}`，避免多网卡造成默认路由和回包路径不对称。

Supervisor 在创建 Profile 时动态将 Stream Gateway 和 coturn 接入对应的 Profile 网络。Gateway 与 coturn 是受信任的共享基础设施，Stream Runtime 不能访问其他 Profile 的运行容器。

Supervisor 将 Gateway 和 coturn 在该 Profile 网络中的实际地址传递给 Stream Runtime，禁止依赖多网卡容器的 DNS 返回顺序。

## 10.4 coturn

coturn 固定使用：

- UDP/TCP 3478。
- TLS/TCP 5349。
- UDP 中继端口 50000–50999。

coturn 的公开监听地址、容器内 relay 地址、`external-ip` 映射和 Docker 端口发布必须保持一致。

coturn 加入 `cbrowser-edge` 网络，并由 Supervisor 动态加入各 Profile 的媒体网络。coturn 使用固定的公网映射 relay 地址，不能将任意 Profile 的私有网络 IP 广播给外部 Chrome。

Stream Runtime 通过自己所在的 Profile 网络访问 coturn。外部 Chrome 使用 coturn 的公开地址。

## 10.5 独立 RTC 配置

Selkies 默认的 RTC 配置不能直接满足所有部署拓扑。

CBrowser 增加 `RtcConfigService`，分别为：

- 外部 Chrome 客户端。
- 对应的 Stream Runtime。

生成 RTC 配置。

客户端配置使用公网可达的 TURN URL；Stream Runtime 使用对应 Profile 网络内可达的 TURN URL。双方可以使用不同的 TURN 凭证。

不依赖 Selkies 默认 `/api/turn` 自动提供不同的客户端与服务端配置。

## 10.6 TURN 凭证刷新

采用 TURN REST HMAC 短期凭证。

- 单份凭证有效期：24 小时。
- 每 12 小时生成新凭证。
- 在现有凭证到期前 6 小时执行 ICE 重启，切换到新凭证。
- 新建 ViewerConnection 总是获取当前有效的 RTC 配置。
- TURN 配置更新失败时记录错误并重试，不能静默使用过期凭证。

`relay-only` 模式同时要求客户端和服务端使用 relay candidate。客户端设置 `iceTransportPolicy=relay`，服务端禁止使用只提供 host candidate 的 ICE-lite 配置。

该模式必须通过实际 relay-to-relay 测试后才允许发布。

______________________________________________________________________

# 11. Browser Agent、CDP 和下载捕获

## 11.1 独立的本地控制通道

Browser Runtime 不连接 API 管理网络，也不暴露 CDP TCP 端口。

每个 Profile 在宿主机创建独立运行时通信目录：

```text
/run/cbrowser/runtime/{profileId}/
```

该目录只挂载到对应 Browser Runtime 和 Supervisor。

Browser Agent 在该目录中提供：

```text
agent.sock
```

通过 Unix Domain Socket 暴露固定的运行时 RPC，包括：

- 健康状态。
- 浏览器进程状态。
- CDP 双向流。
- 下载事件。
- 浏览器配置版本。
- 正常退出事件。

Browser Agent 不接受任意 shell 命令，不提供通用文件系统访问接口。

## 11.2 CDP 数据流

```text
自动化客户端
    ↓
CBrowser API 鉴权与授权
    ↓
Supervisor 内部 CDP 流代理
    ↓
/run/cbrowser/runtime/{profileId}/agent.sock
    ↓
Browser Agent
    ↓
Chrome CDP loopback
```

API 不直接访问 Browser Runtime 网络。

Supervisor 只代理被授权的 CDP 流，不解析自动化命令，也不写 SQLite。

Browser Agent 将 CDP 请求转发到本容器的回环地址。CDP 端口不映射到宿主机公网，也不暴露给其他 Profile。

## 11.3 文件和下载事件

Browser Agent 监听 CDP 下载事件，记录下载完成、路径、文件大小和状态。

Agent 通过 Unix Socket 将事件发送给 Supervisor，Supervisor 再通过经过认证的 RPC 转发给 API。

外部 CDP 自动化客户端断开后，Browser Agent 恢复 CBrowser 的下载捕获设置，避免外部自动化改变下载策略后使 Artifact 管理失效。

CDP 下载事件是主来源。Browser Agent 启动或 CDP 会话重建后扫描 `/exchange/downloads/` 一次，对没有完成事件的已完成文件（排除 `.crdownload` 等临时文件）补发下载事件，API 按路径与校验和去重。目录扫描只做对账兜底，不替代 CDP 事件。

______________________________________________________________________

# 12. SQLite 单写者与运行状态恢复

## 12.1 数据库写入归属

**CBrowser API 是唯一 SQLite 写入者。**

Supervisor 不挂载 SQLite 数据库文件，不直接更新 `desired_state`、`observed_state` 或其他业务表。

Supervisor 通过内部认证 RPC：

- 接收期望状态变更。
- 上报实际运行状态。
- 上报运行事件。
- 请求配置快照。
- 请求 Profile 生命周期操作。

SQLite 开启 WAL，并设置 `busy_timeout=5000`。所有事务保持短小，禁止在事务中执行 Docker API 调用或等待浏览器启动。

## 12.2 运行状态模型

每个 Profile 保存：

```text
desired_state
observed_state
runtime_instance_id
config_version
failure_count
restart_blocked
last_exit_event_id
```

`desired_state` 表示用户期望状态；`observed_state` 表示真实运行状态。

## 12.3 主动停止

1. API 在事务中将 `desired_state=stopped`。
2. API 向 Supervisor 发送带幂等操作 ID 的停止命令。
3. Supervisor 关闭对应 ViewerConnection。
4. Supervisor 停止 Stream Runtime 和 Browser Runtime。
5. Supervisor 回收端口和容器。
6. Supervisor 上报实际停止事件。
7. API 更新 `observed_state=stopped`。

## 12.4 用户直接关闭浏览器

Browser Agent 在浏览器进程退出时写入持久化退出事件。

事件包括：

```text
profile_id
runtime_instance_id
event_id
exit_code
exit_reason
config_version
```

Supervisor 读取事件并发送给 API。API 消费事件时按 `event_id` 去重。

正常退出必须将 `desired_state=stopped`，不能只更新 `observed_state`。否则服务重启后，旧的 `desired_state=running` 会导致浏览器被重新启动。

## 12.5 Supervisor 或 API 离线

- Supervisor 不写 SQLite。
- API 不可用时，Supervisor 将事件保存在持久化事件队列中。
- Browser Agent 的正常退出事件写入独立的运行事件目录。
- API 恢复后消费事件，校验 `runtime_instance_id` 和事件 ID。
- 重复事件不得重复触发状态转换。
- Supervisor 重启后扫描现存容器，等待 API 恢复期望状态，再执行 reconciliation。

Browser Runtime 的 Docker restart policy 固定为 `no`。所有浏览器重启均由 Supervisor 根据业务状态决定。

## 12.6 异常退出

- 正常退出：设置 `desired_state=stopped`。
- 异常退出：保留 `desired_state=running`。
- 异常退出后自动重试 3 次，间隔 2、10、30 秒。
- 三次自动重试均失败后设置 `restart_blocked=true`；`failure_count` 记录实际异常总数，含首次异常，此时为 4。
- 用户手动重试后清除失败计数和阻断标记。

______________________________________________________________________

# 13. 前端架构与交互

## 13.1 路由

```text
/
 /settings
 /profiles/new
 /profiles/:profileId
 /profiles/:profileId/files
 /automation/:profileId
```

主界面使用查询参数保存当前操控目标：

```text
/?profileId=PROFILE_ID
```

页面加载时恢复该目标。用户切换 Profile 时只改变当前页面的 `selectedProfileId` 和 ViewerConnection。

禁止使用跨标签页共享的 `localStorage.currentProfileId`。

## 13.2 前端目录

```text
src/frontend/src/
├── app/
│   ├── router.tsx
│   └── providers.tsx
├── features/
│   ├── profiles/
│   ├── browser-session/
│   │   ├── BrowserSessionView.tsx
│   │   ├── SelkiesClientAdapter.ts
│   │   ├── ViewerConnection.ts
│   │   └── ClipboardBridge.ts
│   ├── artifacts/
│   ├── automation/
│   └── settings/
└── shared/
    ├── api/
    ├── components/
    └── i18n/
```

## 13.3 前端状态

每个页面独立维护：

```text
selectedProfileId
viewerConnection
streamState
```

TanStack Query 负责 Profile 和配置数据；SSE 推送运行状态；ViewerConnection 自己负责 WebRTC 连接状态。

同一个 Profile 可以存在多个 ViewerConnection。前端不维护任何控制租约或全局唯一控制者状态。

## 13.4 页面关闭和恢复

页面关闭或切换目标时，关闭当前 PeerConnection 和信令 WebSocket。

页面恢复时，根据 `selectedProfileId` 重新查询运行状态，若浏览器仍在运行，就重新建立 ViewerConnection。

任何 ViewerConnection 的关闭都不能调用 Profile stop API。

页面被浏览器冻结后恢复（Page Lifecycle `freeze`/`resume`、bfcache 的 `pageshow`）时，检查信令与 PeerConnection 状态，已失效则按原 `client_tab_id` 与 `resume_key` 重建连接。

连接失败不显示无解释黑屏。页面显示当前阶段（运行时未就绪、信令失败、ICE 失败、媒体无帧）及可执行操作（重连、查看运行状态）；诊断信息取自 `RTCPeerConnection` 状态与 `getStats()`（选中候选类型、RTT、丢包），不新增媒体回退通道。

______________________________________________________________________

# 14. 鉴权与 API 兼容

## 14.1 用户鉴权

正式 Docker 部署强制启用登录。

首次启动时设置管理员密码。密码使用 Argon2id 哈希存储。

浏览器页面使用：

- HTTPS。
- `HttpOnly`、`Secure`、`SameSite=Strict` Cookie。
- CSRF Token。
- WebSocket Origin 验证。

Viewer 信令必须校验用户身份和 Profile 访问权限。

## 14.2 CDP 自动化鉴权

CDP 自动化使用独立的 Bearer Token 或 mTLS。

浏览器 Viewer WebSocket 必须验证 Origin；CDP 自动化允许合法的非浏览器客户端不提供 Origin，但必须通过独立凭证和 Profile 授权。

不将用户登录 Cookie 当成通用 CDP 自动化凭证。

## 14.3 API 版本

内部 UI API 统一迁移到 `/api/v1`。

旧的内部 Profile CRUD 路由在 v2 发布时作为破坏性变更移除。旧的 CDP 连接入口保留为薄兼容适配器，转发到新的 CDP 代理，不保留旧的 CDP 端口暴露方式。

旧的 `AUTH_TOKEN` 可选鉴权模式不再作为正式部署方式。

______________________________________________________________________

# 15. 数据库和完整迁移

## 15.1 数据库结构

使用 SQLAlchemy 2 + Alembic。

表：

- `profiles`
- `profile_config_versions`
- `profile_tags`
- `profile_runtimes`
- `artifacts`
- `settings`
- `runtime_events`
- `audit_events`

不创建 `leases` 表，也不持久化 ViewerConnection。

## 15.2 旧字段迁移

迁移必须完整覆盖旧 Profile 数据，包括：

- `fingerprint_seed`
- `proxy`
- `timezone`
- `locale`
- `screen_width`、`screen_height`
- `gpu_family`
- `humanize`、`human_preset`
- `geoip`
- `clipboard_sync`
- `auto_launch`
- `color_scheme`
- `launch_args`
- `extension_paths`
- `allow_3p_cookies`
- `set_google_default`
- `capture_preview`
- `restore_session`
- `transparent_proxy`
- `portable_cookies`
- `notes`
- `tags`
- `sort_order`
- `runtime_mode`
- `viewer_mode`

新架构删除 native-window 和多平台原生运行模式，但不因此丢弃仍然有效的 Profile 配置字段。无意义的旧运行模式字段在迁移后映射为 Docker 运行模式。

## 15.3 运行状态迁移

- 旧 `running` 必须与真实容器状态核对。
- 旧 `initializing` 在迁移时映射为待检查状态。
- 旧 `stopped` 映射为 `desired_state=stopped`。
- 不根据数据库旧状态直接假定容器仍然存在。
- 迁移前停止旧版本和浏览器进程。

## 15.4 Profile 复制与重置

复制分为两个明确操作：

1. 只复制配置：新建 Profile 和配置版本，不复制浏览器用户数据或 Artifact。
2. 同时复制浏览器状态：在源浏览器停止后复制浏览器用户数据目录，再校验文件和配置。

Artifact 不参与浏览器状态复制。

重置操作按当前仓库语义保留其指纹种子重新生成行为，并明确显示将清除哪些数据。不得把重置简单实现成删除全部文件后保留旧配置。

## 15.5 数据目录与备份

保留统一的 bind mount 数据根目录，不将核心数据分散到不可见的 Docker named volume 中。

备份必须覆盖：

```text
/data/cbrowser.db
/data/settings/
/data/profiles/
/data/artifacts/
/data/runtime-events/
```

迁移工具支持 `--dry-run`，校验 Profile、Tag、Artifact 数量和文件校验和。失败时恢复旧数据库和目录。

______________________________________________________________________

# 16. 安全与网络矩阵

|来源|目标|允许操作|
|---|---|---|
|Chrome|Caddy|HTTPS 页面、API 和信令|
|API|SQLite|唯一业务数据库读写|
|API|Supervisor|经过认证的生命周期和运行时 RPC|
|API|Stream Gateway|会话授权、运行时状态和连接查询|
|Supervisor|Docker Socket|容器创建、停止、检查和网络管理|
|Supervisor|Browser Agent UDS|浏览器健康、CDP 流和运行事件|
|Stream Agent|Stream Gateway|运行时注册和信令隧道|
|Stream Runtime|coturn|TURN 配置和媒体中继|
|Browser Runtime A|Browser Runtime B|禁止|
|Stream Runtime A|Stream Runtime B|禁止|
|Browser Runtime|Docker Socket|禁止|
|API|Docker Socket|禁止|
|外部 Chrome|CDP 端口|禁止直接访问|

Supervisor 创建容器前必须规范化并校验挂载路径，确保所有 Profile 挂载位于允许的宿主机目录内。

容器使用非 root 用户、`no-new-privileges`、最小 capabilities、默认 seccomp 和只读根文件系统。Browser Runtime 不使用 `privileged: true`，不使用宿主机网络。

______________________________________________________________________

# 17. 仓库文件改造

|现有文件|最终处理|
|---|---|
|`src/backend/main.py`|拆分 API、鉴权和服务层，删除 RFB 代理|
|`src/backend/browser_manager.py`|拆分 Profile、Browser Agent、运行时协调、下载捕获|
|`src/backend/database.py`|SQLAlchemy 2、Repository、Alembic|
|`src/backend/vnc_manager.py`|删除|
|`src/backend/artifacts.py`|重构为 Artifact Service|
|`src/backend/downloads.py`|下载监听迁移到 Browser Agent|
|`src/backend/runtime.py`|删除 native-window 运行路径|
|`src/backend/models.py`|拆分 Domain Model、API Schema 和运行时协议|
|`src/backend/diagnostics.py`|保留，增加结构化运行时日志|
|`src/frontend/src/App.tsx`|Router + Provider|
|`src/frontend/src/components/ProfileViewer.tsx`|改为 Selkies WebRTC 适配组件|
|`src/frontend/src/hooks/useProfiles.ts`|TanStack Query hooks|
|`src/frontend/src/lib/api.ts`|OpenAPI 生成类型与统一 API client|
|`src/frontend/src/components/ProfileFiles.tsx`|保留，迁移到 Artifact 模块|
|`src/frontend/src/components/CdpEndpointButton.tsx`|保留，迁移到 Automation 模块|
|`src/frontend/src/components/NativeWindowStatus.tsx`|删除|
|`config/docker/Dockerfile`|拆分 API、Supervisor、Browser Runtime、Stream Runtime|
|`compose.yaml`|改为 `compose.yaml`|
|`config/docker/entrypoint.sh`|删除旧 VNC 和进程清理逻辑|
|`app_entry.py`|删除原生应用入口|
|`run-macos.sh`、`run-windows.bat`|删除|
|`packaging/`|删除原生安装包构建流程|
|`.github/workflows/ci.yml`|前后端、Chrome E2E、Docker 集成测试|
|`.github/workflows/release.yml`|多架构容器镜像构建和发布|
|`README.md`|重写为 Docker + Chrome 部署文档|
|`DOCKER_DEPLOYMENT.md`|重写网络、数据迁移、备份和恢复|

旧 VNC/RFB 链路只有在新架构通过完整验收后才删除。

______________________________________________________________________

# 18. 第一阶段：技术验证 Spike

正式重构前，建立 `spike/selkies-runtime` 分支。

该阶段不迁移数据库、不删除旧实现、不修改用户数据。

必须完成：

01. 单 Profile CloakBrowser 在 Browser Runtime 中运行。
02. Stream Runtime 使用同 Profile IPC 命名空间和 X11 Socket 捕获画面。
03. 验证 MIT-SHM 正常工作。
04. 验证虚拟音频输出和 Selkies 音频捕获。
05. 验证固定分辨率和真实内部浏览器 UI。
06. 验证同一 Profile 两个不同 `client_tab_id` 同时连接。
07. 验证刷新、复制标签页和关闭首个页面。
08. 验证两个页面同时输入。
09. 验证一个页面后台暂停不会降低另一个页面的全局编码帧率。
10. 验证观看视频时不会因为没有键鼠输入而错误降到 8 FPS。
11. 验证信令通过 Gateway 动态 Agent 隧道。
12. 验证 WebRTC UDP mux 端口映射。
13. 验证公网候选地址。
14. 验证 TURN 凭证、刷新和 relay-only。
15. 验证 CDP UDS 通道和下载捕获。
16. 验证 Supervisor 重启、API 重启和浏览器正常退出。
17. 验证 macOS OrbStack arm64 和 Linux x86_64 Docker。

全部通过后才冻结正式架构。

______________________________________________________________________

# 19. 性能与完整验收

## 19.1 性能基准

基准使用当前电脑与当前Docker配额，不再要求独立Linux x86_64服务器。实测快照（2026-10-27T18:42:07+08:00）：

|层级|基准条件|
|---|---|
|宿主机|MacBook Pro（MacBookPro18,2），Apple M1 Max，10核CPU，64GiB统一内存，arm64|
|宿主系统|macOS 26.5.2；版本随实际验收记录，不把旧版本号当功能要求|
|Docker后端|OrbStack Linux/aarch64；当前Docker Engine 29.4.0|
|容器可用资源|docker info实测10 CPU、16,819,609,600 bytes内存（约15.66GiB），按实际配额测试，不把宿主64GiB全部计入容器预算|
|媒体编码|Docker容器按CPU编码/无GPU加速基准；宿主Apple GPU不计入容器编码算力预算|
|访问端|同一台Mac上的Google Chrome Stable，通过本机入口访问Docker服务|
|网络路径|本机HTTPS/信令及Docker实际媒体路径；公网NAT/跨互联网链路不在本次基准范围|

测试1、3、10个活跃流，并测试10个Profile同时运行、9个后台流暂停、1个前台流工作。按1→3→10逐级增加负载，记录成功运行容量、拒绝原因、实际帧率和资源使用；10流场景用于找容量边界，不预设10路复杂网页都能1080p30。资源不足时必须明确报告，不能静默丢连接、OOM或损坏数据。

测试接通电源，记录能耗/散热状态、Chrome版本、Docker配额和后台负载；CPU和内存在宿主Chrome与Docker间共享。不得为跑分擅自停止现有服务或扩大Docker配额。后续电脑/配额改变时重新记录环境，不能沿用旧结果。

目标：

|指标|验收目标|
|---|---|
|单活跃流|1080p30|
|输入到画面反馈延迟|通过同机Chrome实际测量输入至画面反馈，P95不超过100ms；同时记录媒体路径RTT和负载|
|运行时就绪后的首次画面|P95 不超过 1 秒|
|后台标签页|该 Peer 停止接收 RTP，全部后台时暂停服务端捕获|
|多流资源调度|CPU超过阈值或容器资源受限时按规则降低Profile级FPS，并明确显示资源限制|
|8 小时压力测试|无数据损坏、会话串线或不可恢复的运行时退出|

10个Profile的驻留与10个同时活跃流分别报告；实际容量以当前Mac/OrbStack实测为准。单活跃流目标、8小时压力、输入/剪贴板和安全验收继续保留，不以改基准免除。

## 19.2 标签页验收

- 当前标签页切换 Profile 不影响其他标签页。
- 两个标签页可以连接同一 Profile。
- 同一 Profile 的内部标签页变化同步反映在所有连接页面。
- 关闭一个 ViewerConnection 不影响其他连接。
- 关闭外部标签页不停止浏览器。
- 停止 Profile 才会关闭真实浏览器进程。

## 19.3 输入与剪贴板验收

- 1000 次中文组合输入。
- 1000 次纯文本剪贴板测试。
- 地址栏、普通输入框、受控输入框和富文本编辑器测试。
- 双页面同时输入。
- 用户剪贴板原内容保护。
- 剪贴板权限拒绝时显示明确操作提示。
- 后台页面不自动覆盖本机剪贴板。

## 19.4 安全与恢复验收

- Profile 数据卷互相隔离。
- CDP 端口不对公网开放。
- Browser Runtime 无 Docker Socket。
- API 不直接操作 Docker。
- Supervisor 是唯一 Docker Socket 持有者。
- 运行时事件重复消费不会重复修改业务状态。
- 用户正常关闭浏览器后，服务重启不会重新打开浏览器。
- Gateway 重启不会停止浏览器。
- coturn、ICE 和 UDP 端口映射通过真实网络测试。
- Selkies 会话内文件上传下载已关闭，WebSocket 模式切换不可用。
- 剪贴板方向与二进制剪贴板设置不能被客户端覆盖。

______________________________________________________________________

# 20. 正式实施顺序

01. **技术验证：** 单 Profile、IPC、X11、Selkies、多页面连接、IME、TURN、CDP。
02. **新后端骨架：** Domain、Service、Repository、API、Alembic。
03. **Browser Runtime：** CloakBrowser、Xvfb、Openbox、Browser Agent。
04. **Stream Runtime：** Selkies、音频、媒体捕获、WebRTC。
05. **Supervisor：** 生命周期、端口、网络、事件恢复。
06. **Stream Gateway：** Agent 注册、信令代理、ViewerConnection。
07. **前端：** Profile 选择、当前页面切换、在新标签页打开、多页面连接。
08. **文件与自动化：** Artifact、CDP UDS、下载捕获和剪贴板。
09. **安全和压力测试。**
10. **数据迁移。**
11. **删除旧 VNC/RFB 链路和原生桌面代码。**
12. **发布 Docker + Chrome 正式版本。**

______________________________________________________________________

# 最终结论

CBrowser v2.3 继续采用 Profile、BrowserRuntime、ViewerConnection 三者独立的模型，不恢复独占租约，也不引入 Redis。

正式架构保留两个运行容器，并通过同 Profile 的 IPC 命名空间和 X11 Socket 连接显示；Stream Gateway 通过 Agent 隧道路由信令；CDP 和下载捕获通过受控 Unix Domain Socket 与 Supervisor 连接；API 是唯一 SQLite 写入者；共享编码器的捕获与帧率由 Stream Agent 依据 Selkies 原生每 Peer 暂停、本地输入和画面运动统一仲裁。Selkies 已实现的多页面、每 Peer 暂停、IME、输入和剪贴板传输直接复用，不重复开发。

**先完成 Spike，后冻结架构，再重构、迁移和删除旧链路。** 这条顺序是正式实施的硬性要求，而不是可跳过的建议。
