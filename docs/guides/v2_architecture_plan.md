# CBrowser v2.1：架构审查修订稿

**修订原则：先验证关键技术风险，再冻结架构。未经验证，不删除现有 VNC 链路，不执行数据库迁移，不开始大规模重构。**

## 1. 最终架构决策

保留 CloakBrowser 内核和 CBrowser 的 Profile 管理功能。Selkies 2.1.0 作为首选远程显示栈，但必须通过第 10 节的技术验证门槛后，才能成为正式依赖。

固定服务拓扑：

```text
Caddy
  ├── /api/*       → CBrowser API
  ├── /stream/*    → Stream Gateway
  ├── /assets/*    → 静态资源
  └── /*           → React 前端

CBrowser API
  ├── SQLite + Alembic
  ├── Profile / Session / Artifact Services
  ├── mTLS RPC → Runtime Supervisor
  └── mTLS RPC → Stream Gateway

Runtime Supervisor
  └── Docker Engine Socket
       ├── Browser Runtime A
       ├── Browser Runtime B
       └── Browser Runtime N

Stream Gateway
  ├── 固定公网入口
  ├── Session / Lease 验证
  ├── Runtime Agent 连接注册表
  └── WebSocket 信令代理

每个 Browser Runtime
  ├── CloakBrowser
  ├── Xvfb + Openbox
  ├── Selkies 2.1.0
  ├── Runtime Agent
  └── 独立 Profile 数据目录

外部 Chrome
  ├── 管理标签页
  ├── Profile A 操控标签页
  ├── Profile B 操控标签页
  └── Profile N 操控标签页

WebRTC 媒体：外部 Chrome ↔ Browser Runtime / TURN
```

### 服务职责

|服务|唯一职责|明确禁止|
|---|---|---|
|Caddy|HTTPS、固定路由、静态资源|发现动态容器 IP、管理 Profile|
|CBrowser API|业务 API、鉴权、数据库、控制租约|挂载 Docker Socket、直接启动浏览器|
|Runtime Supervisor|容器生命周期、网络、端口和资源分配|执行业务 API、处理浏览器页面输入|
|Stream Gateway|信令代理、会话鉴权、运行时连接路由|代理视频帧、执行任意容器命令|
|Runtime Agent|单个 Profile 的浏览器生命周期、Selkies 控制和状态上报|访问其他 Profile 的数据|
|Selkies|视频捕获、编码、输入、WebRTC 媒体会话|管理 CBrowser 的 Profile 数据库|

不使用 PostgreSQL、Redis、Kubernetes 或多节点调度。SQLite 仍是唯一业务数据库。

## 2. 信令代理：彻底解决动态容器发现问题

### 2.1 固定公开路径

外部 Chrome 使用：

```text
wss://cbrowser.example/stream/{sessionId}/signal
```

Caddy 只把 `/stream/*` 转发给固定的 `cbrowser-stream-gateway` 服务。

**Caddy 永远不直接连接任何动态创建的 Browser Runtime。**

### 2.2 Runtime Agent 反向建立连接

每个 Runtime Agent 在容器启动后，主动连接 Stream Gateway 的内部入口：

```text
wss://gateway:8443/internal/runtime/connect
```

这条连接具有以下属性：

- 使用运行时专属的随机凭证及 TLS 身份验证。
- 注册 `profile_id`、`runtime_instance_id` 和当前运行时代次。
- 每 10 秒发送一次 Agent 心跳。
- 连接断开后按 1、2、4、8、16 秒退避重连，最大间隔 30 秒。
- 不在公网监听 Runtime Agent 控制端口。
- 不在 CBrowser API 或 Stream Gateway 中保存可任意执行的容器命令。

当外部 Chrome 请求信令时：

1. Gateway 验证登录 Cookie、会话 ID 和控制租约。
2. Gateway 查询该会话绑定的 `runtime_instance_id`。
3. Gateway 通过已经建立的 Agent 连接请求创建信令隧道。
4. Agent 在本容器内部连接 Selkies 的 `/api/webrtc/signaling`。
5. Gateway 双向转发信令消息。
6. WebRTC 建立后，视频、音频和实时输入走媒体连接，不经过 Gateway 的信令转发循环。

Selkies 官方的实际 WebRTC 信令端点是 `/api/webrtc/signaling`，其连接协议和鉴权流程必须由固定版本的适配器处理，不得自行假定它存在一个原生 `/signal` 端点。

### 2.3 隧道故障行为

- Gateway 重启：Runtime Agent 自动重新注册；浏览器容器不停止。
- Agent 连接断开：不立即销毁 Profile，不重启浏览器。
- 信令连接断开：现有 WebRTC 媒体可以继续工作；需要重连时重新申请信令连接。
- Runtime 容器重建：Supervisor 生成新的 `runtime_instance_id`，旧实例的所有信令映射立即失效。
- 旧实例恢复注册：Gateway 拒绝旧实例代次，不能覆盖新实例。

不允许通过扫描 Docker 容器列表来决定每一条信令的目标。Docker 容器发现只属于 Supervisor 的生命周期恢复职责。

## 3. WebRTC 端口、NAT 和 ICE 候选地址

### 3.1 固定端口分配规则

不使用多个容器共享同一个宿主机 UDP 端口的方案，也不依赖随机端口映射后自动修改 SDP。

固定使用以下规则：

- 媒体 UDP 宿主机端口池：`30000–30991`。
- 每个运行时分配一个连续的 16 端口区间。
- 最多同时分配 62 个运行时端口区间。
- 宿主机端口号与容器内端口号完全相同。
- Supervisor 通过 Docker Engine API 为每个容器逐端口创建 UDP 绑定。
- Selkies 的 `webrtc_port_range` 设置为当前 Profile 分配的 16 端口区间。

示例：

|Profile|容器内端口|宿主机端口|
|---|---|---|
|A|30000–30015/UDP|30000–30015/UDP|
|B|30016–30031/UDP|30016–30031/UDP|
|C|30032–30047/UDP|30032–30047/UDP|

这样，端口映射不会改变 WebRTC 所宣告的候选端口。

### 3.2 明确的部署网络模式

环境变量固定为：

```text
CBROWSER_ACCESS_MODE=local|lan|public|relay-only
CBROWSER_WEBRTC_ADVERTISE_IP=<实际可达的 IP>
```

每次部署只能选择一种模式。

|模式|候选地址|宿主机媒体端口|使用条件|
|---|---|---|---|
|`local`|`127.0.0.1`|仅绑定回环地址|仅同一台主机的 Chrome|
|`lan`|宿主机局域网 IP|绑定局域网接口|仅局域网访问|
|`public`|稳定公网 IP|开放并转发 UDP 30000–30991|公网直连，需配置防火墙/NAT|
|`relay-only`|使用 TURN 中继候选|不发布 Browser Runtime 的媒体端口|无法保证直接 ICE 连通，或要求媒体全部中继|

`CBROWSER_WEBRTC_ADVERTISE_IP` 必须传递给 Selkies 的 `webrtc_public_ip` 配置。该设置负责替换主机候选地址中的私有 IP，但不会自动修改端口映射。`webrtc_port_range` 和 `webrtc_public_ip` 都是 Selkies 官方支持的配置项。

### 3.3 TURN 规则

TURN 使用独立的服务器端口池：

- UDP/TCP 3478。
- TLS/TCP 5349。
- 中继端口 UDP/TCP 50000–59999。
- 使用短期 TURN 凭证。
- 凭证最长有效期 10 分钟。
- TURN 凭证按控制会话签发，不使用公开的长期共享密码。

`relay-only` 模式下，客户端强制使用中继候选，服务端也必须提供可达的 TURN 中继候选。该模式不要求向公网发布每个 Browser Runtime 的直接媒体端口，但会增加网络带宽和延迟。

不能把 `webrtc_public_ip` 配成任意公网 IP 就认为 NAT 已经打通。公网模式必须同时满足公网地址可达、端口转发正确、容器端口与宣告端口一致。

## 4. 中文输入法：禁止用剪贴板模拟输入法

### 4.1 最终实现

不实现自有的剪贴板文本注入输入代理，不使用 `navigator.clipboard` 作为中文输入通道，也不通过 CDP 模拟粘贴来处理所有文本输入。

复用 Selkies 2.1.0 已有的输入协议和服务端输入实现：

- 浏览器端捕获真实键盘输入和 IME 组合事件。
- IME 提交内容通过 Selkies 的原生文本提交消息传输。
- 服务端在 Linux X11 环境中使用 Selkies 自带的 XTEST 键盘实现、动态键映射和虚拟键盘文本注入机制。
- 输入事件直接进入真实 CloakBrowser 窗口。
- 地址栏、网页文本框和 `contenteditable` 编辑器都通过真实窗口输入路径处理，而不是使用同一个剪贴板粘贴补丁。

参考实现：

- [Selkies 2.1.0 输入处理器](https://github.com/selkies-project/selkies/blob/2.1.0/src/selkies/input_handler.py)
- [Selkies 2.1.0 安全模式](https://docs.selkies.io/latest/secure-mode)

特别注意：`Xutf8LookupString` 是用于读取 X 输入法查找结果的接口，不是向 Chrome 注入字符的通用 API。不得把它当成文本注入的实现方案。

### 4.2 剪贴板与输入法彻底分离

Selkies 的剪贴板配置固定为：

```text
SELKIES_ENABLE_CLIPBOARD=true
SELKIES_CLIPBOARD_SEAMLESS=false
```

剪贴板只允许用户明确触发的操作，不再自动双向同步。

远程浏览器页面没有常驻工具栏，但提供以下远程快捷操作：

|快捷键|功能|
|---|---|
|`Ctrl+Alt+Shift+C`|将远程剪贴板复制到本机剪贴板|
|`Ctrl+Alt+Shift+V`|将本机剪贴板发送到远程浏览器并执行粘贴|

macOS 和 Linux Chrome 均必须通过端到端测试验证这两个组合键。

中文 IME 提交不能触发剪贴板同步，也不能覆盖用户本机原有剪贴板。

如果浏览器拒绝本机剪贴板 API，系统只在用户明确执行复制或粘贴时显示一次性提示，提供手动点击操作。这是正常操控页面唯一允许的临时 UI 例外，不增加常驻按钮或工具栏。

### 4.3 输入验收

必须在真正的 CloakBrowser 窗口中验证：

1. 地址栏输入中文。
2. 普通网页输入框输入中文。
3. React/Vue 控制的表单输入框输入中文。
4. `contenteditable` 富文本编辑器输入中文。
5. 输入过程中触发的 `input`、组合事件和网页校验行为。
6. 中英文切换、退格、选区替换和连续组合输入。
7. 输入法提交期间切换外部 Chrome 标签页。
8. 输入失败后重新聚焦和继续输入。

禁止以“最终页面出现中文字符”作为唯一成功标准。

## 5. 控制租约：在 Selkies 服务端强制撤权

Selkies 2.1.0 默认允许多个页面加入同一显示并同时操控，因此不能只在 CBrowser API 层拒绝第二个会话。

### 5.1 使用官方安全模式

每个 Browser Runtime 启用 Selkies Secure Mode：

- 设置独立的 `SELKIES_MASTER_TOKEN`。
- 使用 `SELKIES_TOKENS_FILE` 或内部 API 管理会话 Token。
- 关闭分享功能：`enable_sharing=false`。
- 关闭协作：`enable_collab=false`。
- 关闭共享观看及其他玩家入口。
- 不将 master token 交给外部 Chrome。
- 每个控制会话只获得自己的短期 Session Token。

CBrowser 为当前唯一控制者签发一个 `role=controller`、`mk_control=true` 的 Token。

### 5.2 接管流程

每个 Profile 在 SQLite 中保存一个单调递增的 `lease_epoch`。

接管必须按以下顺序执行：

1. API 事务锁定该 Profile 的控制租约。
2. 增加 `lease_epoch`。
3. 将旧租约标记为 `revoked`。
4. Gateway 拒绝旧租约发起的新信令连接。
5. Runtime Agent 更新 Selkies 的 Token 表，删除旧 Token。
6. 等待 Selkies 完成旧 Peer 的撤销。
7. 确认旧控制权已失效后，签发新 Token。
8. 新会话建立媒体和输入连接。
9. API 记录接管结果。

Selkies 官方安全模式明确支持通过 `POST /api/tokens` 替换会话 Token 表。被移除的 Token 会使已连接的 Peer 断开，角色变化也会被实时协调。此能力可以直接用于控制权撤销，而不是自行重新实现一套输入权限协议。

**撤权成功的标准不是旧页面收到断线通知，而是旧 Peer 在服务端不再具有任何输入权限。**

测试时必须在旧连接仍然存活的情况下持续发送键盘和鼠标事件，验证这些事件不能进入浏览器。

## 6. 后台冻结、休眠与租约状态机

Chrome 隐藏页面可能被冻结或丢弃；冻结后定时器和网络任务可能停止，丢弃页面时也不保证收到卸载事件。不能依赖 `setInterval` 心跳或 `beforeunload` 释放租约。

### 6.1 会话状态

```text
ACTIVE
  ├── 页面隐藏 → BACKGROUND
  ├── 信令断开 → SUSPECT
  └── 主动接管 → REVOKED

BACKGROUND
  ├── 页面恢复 → ACTIVE
  └── 租约过期 → EXPIRED

SUSPECT
  ├── 原会话重连 → ACTIVE
  └── 租约过期 → EXPIRED

EXPIRED
  └── 重新申请 → 新 lease_epoch
```

### 6.2 固定租约参数

- 活跃页面每 5 秒发送一次心跳。
- 隐藏页面尽可能发送一次 `BACKGROUND` 状态事件。
- 隐藏状态不立即释放控制租约。
- 连接失联 30 秒后进入 `SUSPECT`。
- 原会话在 120 秒租约宽限期内可恢复。
- 宽限期结束后，旧租约自动过期。
- 过期后恢复的标签页必须重新申请控制权。
- 如果另一标签页已经获得新租约，旧标签页不能恢复控制权。
- 主动接管不等待 120 秒宽限期，立即执行服务端撤权。

隐藏页面关闭视频捕获和解码，浏览器进程继续运行。恢复时先重新验证租约，再重建媒体连接。

Chrome 页面冻结或丢弃时不依赖浏览器端发送最后一次心跳。服务端租约到期逻辑是最终权威。

## 7. 浏览器关闭、崩溃和期望状态恢复

### 7.1 数据库状态

每个 Profile 必须持久化：

```text
desired_state
observed_state
runtime_instance_id
config_version
failure_count
restart_blocked
last_exit_event_id
```

`desired_state` 表示用户期望的状态，`observed_state` 表示实际运行状态。二者不能混为一个字段。

### 7.2 主动停止

用户点击停止时：

1. API 在事务中先将 `desired_state=stopped`。
2. Supervisor 接收带有幂等操作 ID 的停止命令。
3. Runtime Agent 正常关闭浏览器和 Selkies。
4. Supervisor 回收端口、网络和容器。
5. API 最终确认 `observed_state=stopped`。

### 7.3 用户直接关闭浏览器

用户在真实浏览器窗口关闭最后一个窗口时，Runtime Agent 记录浏览器进程退出事件。

事件包含：

- `profile_id`
- `runtime_instance_id`
- 单调递增事件序号
- 退出原因和退出码
- 事件时间
- 当前配置版本

正常的用户关闭事件必须将 `desired_state` 更新为 `stopped`，而不是只更新 `observed_state`。

Agent 先将事件原子写入持久化的 Profile 运行时状态目录，再向控制服务报告。控制服务不可用时，事件仍然保留。

### 7.4 崩溃与自动恢复

- 正常退出：设置 `desired_state=stopped`，不自动重启。
- 异常退出：保留 `desired_state=running`，记录失败原因。
- 异常退出自动重试最多 3 次，退避间隔为 2、10、30 秒。
- 3 次失败后设置 `restart_blocked=true`，等待用户手动重试。
- 用户手动重试会清除 `restart_blocked` 和失败计数。
- Browser Runtime 容器的 Docker restart policy 固定为 `no`，所有重启由 Supervisor 决定。

### 7.5 启动恢复顺序

Supervisor 启动后必须按以下顺序执行：

1. 读取持久化运行时退出事件。
2. 校验 `runtime_instance_id` 和事件序号。
3. 将未消费的正常退出事件应用到 SQLite。
4. 枚举由 CBrowser 管理的现存容器。
5. 对照 `desired_state`、`restart_blocked` 和实际容器状态。
6. 停止不应存在的运行时。
7. 恢复应运行且未被阻断的运行时。
8. 等待 Runtime Agent 注册后才报告就绪。

这样可以防止“用户关闭浏览器后，服务重启又将浏览器自动打开”的问题。

## 8. 性能策略与资源调度

### 8.1 固定帧率策略

Selkies 支持设置帧率范围，并且可以动态调整采集帧率。其官方设置允许限制帧率范围，软件编码还可以控制多线程行为。

CBrowser 默认配置：

```text
SELKIES_MODE=webrtc
SELKIES_ENABLE_DUAL_MODE=false
SELKIES_FRAMERATE=8,8-30
```

这里的 `8,8-30` 表示初始 8 FPS，允许的范围为 8–30 FPS。

固定行为：

- 新连接和静止页面：8 FPS。
- 用户输入、鼠标操作、滚动或明显画面变化：30 FPS。
- 连续 3 秒没有输入且画面变化低于阈值：降回 8 FPS。
- 页面进入后台：停止该会话的视频捕获。
- 页面恢复前台：先恢复 8 FPS，再按活动情况提高到 30 FPS。
- 60 FPS 只作为显式高性能配置，不作为默认值。

画面变化检测必须在技术验证阶段证明开销足够低。如果当前 Selkies 暴露的帧活动信息不足，就在其捕获适配层增加低分辨率变化率统计，不允许在 React 页面中持续截图分析。

### 8.2 全局资源调度

新增 `StreamBudgetManager`，负责根据实际 CPU 利用率、编码器类型和活动流数量调整帧率。

固定策略：

- CPU 利用率连续 15 秒超过 80%：将活跃流逐级从 30 FPS 降至 20、15、8 FPS。
- CPU 利用率连续 60 秒低于 65%：每 30 秒恢复一个档位。
- 隐藏标签页优先暂停视频捕获。
- 不因媒体暂停而停止浏览器进程。
- 不允许一个 Profile 的编码负载阻塞 API、会话撤权或其他 Profile 的控制操作。

硬件编码能力通过运行时检测决定，不能因为使用 Selkies 就假定存在 NVIDIA 或 VA-API 编码器。

无硬件编码时使用已验证的 H.264 软件编码器和自适应帧率。`cpu_encode_threading` 根据实际负载测试选择，不能同时默认开启所有编码线程并宣称支持 10 路 1080p60。

### 8.3 明确的容量承诺

正式版本的基准环境固定为 Linux x86_64、8 vCPU、32 GiB RAM、无 GPU，并额外测试用户的 macOS OrbStack arm64 环境。

必须测试：

- 10 个 Profile 容器同时运行。
- 10 个外部 Chrome 标签页全部连接。
- 9 个后台标签页暂停视频，1 个前台标签页以 1080p30 工作。
- 3 个前台浏览器窗口同时以 1080p30 工作。
- 10 个前台媒体流同时运行的 CPU、内存、帧率和延迟。

产品保证 10 个 Profile 可以同时运行和建立会话。10 路同时保持 1080p30 不作为无 GPU 环境的默认性能承诺；实测容量由自动帧率调度器控制。

参考验收目标：

|指标|验收目标|
|---|---|
|10 个运行时的启动与持久化|全部通过|
|单活跃流 1080p30 输入延迟|P95 不超过 100 ms，局域网 RTT 不超过 10 ms|
|单活跃流首次画面|运行时就绪后 P95 不超过 1 秒|
|3 路活跃流|15 分钟测试内 CPU 不持续超过 80%|
|10 路活跃流|完成容量测试，记录可维持的帧率与延迟|
|后台标签页|无持续视频编码负载|
|8 小时压力测试|无会话串线、数据损坏或无法恢复的运行时退出|

如果单活跃流或三活跃流的硬门槛不通过，不进入正式迁移阶段。

## 9. 内部网络与服务认证闭环

### 9.1 网络连接矩阵

|来源|目标|允许行为|
|---|---|---|
|外部 Chrome|Caddy HTTPS|管理页面、API 和信令入口|
|外部 Chrome|Browser Runtime 媒体端口|仅允许当前部署模式对应的 ICE 媒体连接|
|外部 Chrome|coturn|使用短期凭证建立 TURN 中继|
|CBrowser API|SQLite|业务数据读写|
|CBrowser API|Supervisor|mTLS 生命周期 RPC|
|CBrowser API|Stream Gateway|mTLS 会话授权、租约更新和撤权|
|Runtime Agent|Stream Gateway|专属认证的出站控制连接|
|Runtime Agent|本地 Selkies|仅限当前容器内的信令、Token 和运行状态接口|
|Runtime A|Runtime B|**禁止**|
|Browser Runtime|Docker Socket|**禁止**|
|CBrowser API|Docker Socket|**禁止**|

### 9.2 Docker 网络隔离

每个 Profile 创建独立的内部控制网络：

```text
profile-control-net-{profileId}
```

该网络只包含对应的 Browser Runtime 和 Stream Gateway 的网络接口。

Browser Runtime 另有自己的外网出口网络。该出口网络不连接其他 Profile，也不连接 CBrowser API。

Stream Gateway 是唯一连接到多个 Profile 控制网络的服务。它只接受经授权的 Agent 注册和信令隧道，不提供通用的容器端口代理。

Browser Runtime 的外网出口还必须通过宿主机防火墙规则限制私有网段、链路本地地址和云元数据地址。代理配置启用时，除配置的代理端点、DNS 和必要的媒体服务外，不允许绕过代理直接访问互联网。

### 9.3 服务身份认证

- API → Supervisor：mTLS，RPC 方法采用固定白名单。
- API → Gateway：mTLS，控制消息携带操作 ID 和租约代次。
- Runtime Agent → Gateway：运行时专属凭证和 TLS 身份验证。
- Gateway → Runtime Agent：只允许该 Profile 已注册的 Agent 隧道。
- Agent → Selkies：使用本运行时的 master token。
- 外部 Chrome → Gateway：登录 Cookie、Origin 校验和会话租约验证。
- Runtime Supervisor：唯一拥有 Docker Socket 的服务。

Supervisor 在创建容器前必须验证 Profile UUID、配置版本、镜像摘要和所有挂载路径。所有宿主机挂载路径必须规范化并确认位于允许的 Profile 数据根目录中，不能通过 `..` 或符号链接逃逸到其他目录。

## 10. 第一阶段：技术验证门槛

**这次架构冻结必须发生在技术验证之后。**

验证在独立分支 `spike/selkies-runtime` 完成，不迁移数据库，不删除现有 VNC 实现。

### 验证任务

01. 使用当前 CloakBrowser 引擎在 Linux 容器内启动一个真实浏览器窗口。
02. 证明 1920×1080、DPR 1 的真实浏览器 UI 能完整显示。
03. 证明 Selkies 2.1.0 的官方客户端可以作为无常驻工具栏的全窗口视图。
04. 证明 `POST /api/tokens` 可以实时撤销旧控制 Peer。
05. 证明旧 Peer 在被撤权后不能继续发送有效输入。
06. 证明 `/stream/{sessionId}/signal` 通过 Gateway 的 Agent 隧道建立连接。
07. 证明 WebRTC 直连模式的 ICE 候选地址和端口映射一致。
08. 证明 TURN 中继模式可以建立连接。
09. 证明中文 IME 可以在真实地址栏和网页编辑器中输入，而不依赖剪贴板。
10. 证明剪贴板在关闭无缝同步后，不会因中文输入被覆盖。
11. 证明隐藏、冻结、丢弃、刷新和电脑休眠后的租约恢复符合第 6 节状态机。
12. 证明用户直接关闭浏览器后，正常退出事件能持久化并更新 `desired_state`。
13. 在 macOS Chrome Stable 和 Linux Chrome Stable 上测试远程快捷键映射。
14. 完成 1、3、10 个活跃流的性能测试。
15. 在 arm64 OrbStack 和 x86_64 Linux Docker 环境验证构建及运行时依赖。

Chrome 的冻结和丢弃测试使用 `chrome://discards`，并结合官方 Page Lifecycle 事件进行验证。

### 验证通过标准

只有当以下条件全部满足时，才冻结 Selkies 2.1.0 为正式远程显示栈：

- 真正的浏览器窗口和内部标签页完整可用。
- 中文输入路径不依赖剪贴板。
- 旧控制 Peer 被撤权后确实不能输入。
- 信令可以通过固定 Gateway 连接任意动态 Profile。
- ICE 和 TURN 路径通过实测。
- 生命周期恢复和退出事件没有状态矛盾。
- 单活跃流和三活跃流的性能门槛通过。

任一条件不通过，必须先修复 Spike 并重新测试。不得以“后续重构时再解决”为理由继续迁移。

## 11. 正式重构顺序

技术验证通过后，按以下顺序实施：

01. 创建新的 Domain Model、SQLAlchemy 2、Alembic 和数据迁移工具。
02. 实现 API、Supervisor RPC、Runtime Registry 和 Session Lease Service。
03. 实现每 Profile 独立网络、端口分配和运行时镜像。
04. 接入已经通过验证的 Selkies 客户端和 Runtime Agent。
05. 实现 Stream Gateway 的签名会话票据、信令隧道和撤权处理。
06. 实现浏览器关闭事件日志、状态恢复和重启策略。
07. 重构 React 路由，分离 `/manage` 和 `/browser/{profileId}`。
08. 迁移文件管理、代理、指纹配置和自动化 CDP 功能。
09. 完成安全测试和压力测试。
10. 备份并迁移旧数据。
11. 验证 Profile、Cookie、文件、配置和内部标签页恢复状态。
12. 正式删除旧 noVNC/RFB 链路及不再需要的原生桌面启动代码。

旧数据库和旧容器在新版本验收前保持可恢复状态。

## 12. 最终结论

CBrowser v2 的正式架构应当是：

- 一个 CBrowser API 服务。
- 一个拥有 Docker Socket 的 Runtime Supervisor。
- 一个固定入口的 Stream Gateway。
- 一个 coturn 服务。
- 每个 Profile 一个隔离的 CloakBrowser 运行时容器。
- Selkies 2.1.0 负责远程显示、IME 输入和服务端输入权限。
- WebRTC 媒体直接传输，或在无法直连时使用 TURN。
- Chrome 原生管理外部标签页，CloakBrowser 原生管理内部标签页。

这次修订的核心不是增加更多服务，而是消除四类架构错误：动态容器发现依赖、剪贴板与输入法耦合、API 租约与实际输入权限脱节，以及期望状态和真实运行状态不一致。

**正式开发的第一项工作不是重写 `main.py`，而是完成单 Profile 的端到端技术验证。** 只有验证通过后，才允许开始数据库迁移、代码大规模拆分和旧链路删除。
