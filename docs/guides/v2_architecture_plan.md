# CBrowser v2.2：完整技术架构与仓库改造实施方案

**方案状态：最终架构决策**

**部署模式：Docker Compose 单机部署**

**外部浏览器：Google Chrome Stable**

**浏览器内核：保留 CloakBrowser**

**远程显示：Selkies 2.1.0，固定版本并通过技术验证后投入生产**

**核心原则：Profile、BrowserRuntime 和 ViewerConnection 三者独立；允许多个 ViewerConnection 同时连接同一个 BrowserRuntime。**

______________________________________________________________________

# 第一部分：产品模型与核心架构

## 1. 产品目标与不可变规则

CBrowser 是一个通过 Web 界面管理、启动和操控多个隐私浏览器的系统。浏览器实际运行在 Docker 中，用户通过外部 Chrome 访问 CBrowser。

产品必须实现以下行为：

01. 用户打开 CBrowser 主界面，可以选择任意一个隐私浏览器进行操作。
02. 用户可以在当前 CBrowser 页面中切换操控目标，不必新建 Chrome 标签页。
03. 用户可以点击“在新标签页打开”，由 Chrome 创建新的外部标签页。
04. 每个外部标签页可以独立选择操控目标。
05. 多个外部标签页可以同时连接不同的隐私浏览器。
06. 多个外部标签页也可以同时连接同一个隐私浏览器。
07. 外部标签页切换操控目标时，不停止原来的浏览器。
08. 关闭外部标签页只结束该页面的连接，不关闭远程浏览器。
09. 只有用户明确停止浏览器、删除配置，或浏览器发生需要恢复的故障时，才改变浏览器运行状态。
10. 每个隐私浏览器内部的标签栏、地址栏和网页全部由真实运行的 CloakBrowser 管理。

### 明确禁止的设计

- 不实现 CBrowser 自己的外部 Chrome 标签栏。
- 不将外部标签页绑定为某个 Profile 的永久所有者。
- 不实现独占控制租约。
- 不实现租约代次、接管等待或租约续期。
- 不使用 Redis 保存连接或租约。
- 不因为一个外部标签页关闭而停止浏览器。
- 不将远程浏览器内部标签页转换为 React 页面路由。
- 不通过 CDP 创建一套仿制的浏览器 UI。
- 不允许媒体连接断开自动触发浏览器重启。

## 2. 正确的标签页模型

<box border radius="xl" padding={3} gap={3}>
  <box background="surface-secondary" radius="lg" padding={3} gap={2}>
    <title size="md">外部 Chrome：由 Chrome 管理标签页</title>
    <grid columns={3} gap={2}>
      <grid-item>
        <box background="surface" border radius="md" padding={2} gap={1}>
          **外部标签 A**
          <text size="sm" color="secondary">当前目标：隐私浏览器 A</text>
        </box>
      </grid-item>
      <grid-item>
        <box background="surface" border radius="md" padding={2} gap={1}>
          **外部标签 B**
          <text size="sm" color="secondary">当前目标：隐私浏览器 B</text>
        </box>
      </grid-item>
      <grid-item>
        <box background="surface" border radius="md" padding={2} gap={1}>
          **外部标签 C**
          <text size="sm" color="secondary">当前目标：隐私浏览器 A</text>
        </box>
      </grid-item>
    </grid>
  </box>
  <box align="center" gap={1}>
    <icon name="arrow-down" size="xl" color="secondary"/>
    <text size="xs" color="secondary">三个独立页面连接两个浏览器运行实例</text>
  </box>
  <grid columns={2} gap={2}>
    <grid-item>
      <box border radius="lg" padding={3} gap={2}>
        <title size="md">隐私浏览器 A</title>
        <badge color="success">2 个连接</badge>
        <divider color="subtle"/>
        <text size="sm">真实浏览器窗口</text>
        <text size="sm">内部标签 1</text>
        <text size="sm">内部标签 2</text>
        <text size="sm" color="secondary">A、C 看到同一个窗口</text>
      </box>
    </grid-item>
    <grid-item>
      <box border radius="lg" padding={3} gap={2}>
        <title size="md">隐私浏览器 B</title>
        <badge>1 个连接</badge>
        <divider color="subtle"/>
        <text size="sm">真实浏览器窗口</text>
        <text size="sm">内部标签 1</text>
        <text size="sm">内部标签 2</text>
        <text size="sm" color="secondary">只有 B 当前连接</text>
      </box>
    </grid-item>
  </grid>
</box>

### 2.1 三个独立对象

|对象|定义|生命周期|
|---|---|---|
|`Profile`|浏览器配置、指纹参数、代理和持久化数据的逻辑身份|长期存在|
|`BrowserRuntime`|该 Profile 对应的实际浏览器进程、窗口和运行容器|从启动到停止|
|`ViewerConnection`|某个外部 CBrowser 页面与某个 BrowserRuntime 之间的一条画面和输入连接|从连接建立到连接结束|

关系为：

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

这里没有“浏览器所有者”字段，也没有“当前唯一控制者”字段。

### 2.2 在当前标签页切换目标

外部标签 A 正在查看隐私浏览器 A 时，用户点击侧边栏中的隐私浏览器 B：

1. 前端关闭 A 对应的 `ViewerConnection`。
2. 前端保留当前页面和外部 Chrome 标签页。
3. 前端请求 B 的流媒体连接配置。
4. 前端创建新的 `ViewerConnection`，连接 B。
5. A 的浏览器进程继续运行，内部标签页、Cookie 和网站状态均保持不变。
6. 其他正在连接 A 的外部标签页不受影响。

切换过程中不停止 A，不重启 B，也不创建额外的浏览器实例。

### 2.3 在新标签页打开

主界面提供“在新标签页打开”操作。该操作使用普通链接和 Chrome 原生标签页机制：

```html
<a href="/?profileId=PROFILE_ID"
   target="_blank"
   rel="noopener">
  在新标签页打开
</a>
```

`PROFILE_ID` 替换为实际 Profile ID。

新标签页打开后，显示完整的 CBrowser 主界面，并将对应 Profile 作为初始操控目标。用户仍然可以在新页面中切换到其他 Profile。

新标签页的选择状态独立于原页面。两个页面选择相同 Profile 时，建立两条连接到同一个运行实例的 ViewerConnection。

### 2.4 同时操作同一个浏览器

两个外部页面同时连接隐私浏览器 A 时：

- 两边显示的是同一个真实浏览器窗口。
- 任一页面切换内部标签页，另一页面看到的内容也随之变化。
- 任一页面输入文字、点击链接或滚动，都会作用于同一个浏览器。
- 两边的鼠标、键盘和焦点共享同一个远程桌面。
- 两边同时输入时，事件按实际到达 X11 输入系统的顺序处理，可能产生输入交错。

最后一点是共享同一个真实浏览器的自然行为。CBrowser 不实现输入锁、排队接管或控制权争抢。

主界面可以显示“当前有 2 个页面正在连接此浏览器”，但这个数字只用于信息展示，不用于阻止连接。

______________________________________________________________________

## 3. 页面路由与前端状态

CBrowser 只实现自己的应用页面，不实现外部 Chrome 的标签管理。

固定路由：

|路由|用途|
|---|---|
|`/`|CBrowser 主界面|
|`/settings`|全局设置|
|`/profiles/new`|创建 Profile|
|`/profiles/:profileId`|Profile 配置管理|
|`/profiles/:profileId/files`|Profile 文件管理|
|`/automation/:profileId`|自动化与 CDP 管理|

主界面使用查询参数记录当前操控目标：

```text
/?profileId=PROFILE_A
```

页面初始化时读取 `profileId`。用户在侧边栏切换目标时，更新当前页面的 URL 查询参数，并更新该页面自己的 React 状态。

禁止使用 `localStorage.currentProfileId` 作为全局当前目标，因为同源外部标签页会共享 `localStorage`，导致一个页面切换目标时覆盖另一个页面的状态。

页面状态使用独立的 React 状态；Profile 配置和运行状态通过 API 查询；连接状态由当前页面自己的 ViewerConnection 管理。

刷新页面时，可以通过 URL 恢复原操控目标。原连接关闭后重新创建，不重新启动浏览器。

______________________________________________________________________

# 第二部分：最终技术栈

## 4. 技术选型

|模块|最终技术|
|---|---|
|前端框架|React 19 + TypeScript + Vite|
|前端路由|React Router 7|
|前端数据请求与缓存|TanStack Query 5|
|API 类型生成|FastAPI OpenAPI + openapi-typescript|
|后端 API|Python 3.12 + FastAPI + Pydantic 2|
|数据库|SQLite + SQLAlchemy 2 + Alembic|
|远程显示|Selkies 2.1.0，固定发布提交|
|浏览器引擎|当前 CloakBrowser 引擎|
|图形显示|Xvfb + Openbox|
|实时媒体|WebRTC|
|媒体中继|coturn|
|入口反向代理|Caddy|
|容器生命周期|Docker Engine API + Runtime Supervisor|
|信令路由|独立 Stream Gateway|
|状态推送|Server-Sent Events（SSE）|
|自动化接口|受控 CDP 代理|
|测试|Pytest、Vitest、Playwright、Docker Compose 集成测试|

依赖必须锁定到具体版本。Selkies 固定到 [官方 2.1.0 发布版本](https://github.com/selkies-project/selkies/releases/tag/2.1.0)，对应提交 `6ee68a7a815956e6745e916741f13335e0b3ff53`。

### 4.1 为什么不引入 Redis 和 PostgreSQL

CBrowser 是单机 Docker 应用，只有一个权威 API 服务负责业务数据库写入。Profile、配置、运行期望状态、Artifact 元数据都保存在 SQLite。

活动的 WebRTC 连接、信令隧道和运行时在线注册表属于短期内存状态，不需要持久化到 Redis。

Supervisor 负责容器生命周期，SQLite 负责长期业务状态。服务重启后，Supervisor 通过 Docker 容器状态和持久化运行事件恢复运行状态，Gateway 通过 Agent 重新注册恢复路由。

不引入 Redis、PostgreSQL 或额外的分布式一致性协议。

### 4.2 为什么使用独立的 Stream Gateway

API 负责业务，Gateway 负责信令连接。这样：

- API 不需要转发 WebSocket 信令消息。
- API 不需要处理 WebRTC SDP 和 ICE 消息。
- Gateway 不需要查询 SQLite 来处理每条信令。
- 视频帧直接通过 WebRTC 传输，不经过 Python API。
- 运行时容器动态创建和销毁，不需要动态修改 Caddy 配置。
- Gateway 重启不会停止浏览器。

______________________________________________________________________

# 第三部分：运行时和容器架构

## 5. 常驻服务与动态容器

Docker Compose 中固定运行以下服务：

```text
caddy
cbrowser-api
cbrowser-supervisor
cbrowser-stream-gateway
coturn
```

每个 Profile 运行时由 Supervisor 动态创建两个容器：

```text
browser-runtime-{profileId}
stream-runtime-{profileId}
```

两个容器分别承担浏览器运行和远程显示职责。

## 6. Browser Runtime

Browser Runtime 负责真实浏览器窗口和浏览器数据。

容器包含：

- CloakBrowser 运行程序。
- Xvfb 虚拟 X11 显示服务器。
- Openbox 轻量窗口管理器。
- Browser Agent。
- 必要的字体、浏览器依赖和文件交换工具。

固定显示环境：

```text
DISPLAY=:99
Xvfb geometry: 1920x1080x24
X11 TCP listener: disabled
```

Openbox 只负责窗口管理，不显示桌面面板。CloakBrowser 使用普通窗口模式，默认最大化显示，保留真实浏览器的内部标签栏、地址栏、导航按钮和网页区域。

Browser Runtime 不运行 Selkies，不暴露 CDP 端口，也不挂载 Docker Socket。

### 6.1 浏览器数据

每个 Profile 使用独立的数据目录：

```text
/data/profiles/{profileId}/profile
/data/profiles/{profileId}/exchange
```

`profile/` 保存 Cookie、网站存储、浏览器偏好、内部标签页恢复状态、扩展和浏览历史。

`exchange/` 用于上传文件、待处理下载和文件交换。

Browser Runtime 只挂载自己的 Profile 目录。不同 Profile 不共享浏览器用户数据目录。

### 6.2 GPU 与指纹隔离

Browser Runtime 默认不挂载宿主机物理 GPU 设备。浏览器的渲染环境和指纹参数由 CloakBrowser 的配置机制管理。

这不是对指纹不可检测的保证。正式版本必须验证 GPU 模拟参数、WebGL、字体、屏幕尺寸、时区、语言和代理行为的一致性。

## 7. Stream Runtime

Stream Runtime 负责远程画面、视频编码、键鼠输入、IME 和剪贴板。

容器包含：

- Selkies 2.1.0。
- Stream Agent。
- 必要的媒体编码器。
- 远程显示与输入适配组件。

Stream Runtime 与 Browser Runtime 通过专属的 X11 Socket 卷连接。

```text
browser-runtime
  ├── Xvfb :99
  ├── Openbox
  ├── CloakBrowser
  └── X11 Socket Volume
          │
          ▼
stream-runtime
  ├── Selkies
  ├── X11 画面捕获
  ├── XTEST / 虚拟键盘输入
  ├── WebRTC 编码
  └── Stream Agent
```

X11 Socket 卷只挂载到对应的 Browser Runtime 和 Stream Runtime。Stream Runtime 不挂载浏览器 Profile 数据目录。

Stream Runtime 可以通过 X11 注入输入事件，这是它的工作职责；但它不能直接读取浏览器 Cookie、网站本地存储或下载文件。

物理 GPU 设备只在经过验证后挂载到 Stream Runtime，用于视频编码。Browser Runtime 不因视频编码需要而直接获得宿主机 GPU 设备。

### 7.1 X11 Socket 与权限

Xvfb 使用 Unix Domain Socket，不监听 X11 TCP 端口。

Browser Runtime 创建独立的 Xauthority 文件，Stream Runtime 以只读方式读取认证信息。X11 Socket 卷只允许对应 Profile 的两个容器访问。

启动顺序固定：

1. 创建 X11 Socket 卷。
2. 启动 Browser Runtime。
3. 等待 Xvfb 和 Openbox 就绪。
4. 启动 CloakBrowser。
5. 等待浏览器窗口和 CDP 健康检查通过。
6. 启动 Stream Runtime。
7. 等待 Selkies、X11 捕获和 WebRTC 信令服务就绪。
8. 注册运行时路由。
9. 更新 Profile 运行状态为 `running`。

如果 X11 Socket 跨容器连接在技术验证中未通过，禁止继续进行数据库迁移和大规模重构，先修复该集成问题。

______________________________________________________________________

# 第四部分：信令路由与动态运行时注册

## 8. Caddy 只负责固定入口

外部 Chrome 的信令地址：

```text
wss://cbrowser.example/stream/{profileId}/signal
```

Caddy 配置固定为：

```text
/api/*      -> cbrowser-api:8080
/stream/*   -> cbrowser-stream-gateway:8090
其他路径    -> CBrowser 前端静态资源
```

Caddy 不查询 Docker，不扫描容器，不动态发现 Profile IP，也不直接连接 Browser Runtime 或 Stream Runtime。

这样就消除了“Caddy 如何发现动态容器 IP”的问题。

## 9. Stream Gateway 与 Stream Agent 的连接

采用 **Stream Agent 主动连接 Gateway** 的架构，不让 Gateway 依赖动态容器 IP。

每个 Stream Agent 启动后，主动建立一个经过认证的控制 WebSocket：

```text
wss://cbrowser-stream-gateway:8091/internal/agent/control
```

连接注册信息包含：

- `profile_id`
- `runtime_instance_id`
- `runtime_image_digest`
- `config_version`
- `webrtc_udp_port`
- `selkies_version`
- `agent_version`

Gateway 在内存中维护：

```text
runtime_registry[profile_id] = {
    runtime_instance_id,
    agent_control_connection,
    runtime_state,
    capabilities
}
```

这个注册表只保存活动运行时信息，不是 Profile 数据库，也不是控制租约系统。

### 9.1 建立一条 ViewerConnection

外部 Chrome 连接 Gateway 时：

1. Gateway 验证登录 Cookie。
2. Gateway 验证 WebSocket Origin。
3. Gateway 从 URL 中读取 `profileId`。
4. Gateway 查找该 Profile 对应的活动 Stream Agent。
5. Gateway 为本次连接生成随机 `connectionId`。
6. Gateway 通过 Agent 控制连接发送 `OPEN_SIGNAL_TUNNEL`。
7. Stream Agent 建立到 Gateway 的专用信令隧道。
8. Stream Agent 在本地连接 Selkies 的 `/api/webrtc/signaling`。
9. Gateway 将外部 Chrome、Agent 隧道和 Selkies 信令连接组成双向消息通道。

信令消息包括 SDP、ICE candidate 和连接协商消息。视频帧不经过该通道。

### 9.2 为什么每条连接使用独立隧道

一个 Agent 控制连接负责管理命令；每条 ViewerConnection 使用单独的信令隧道。

不在一个自定义二进制复用协议中混合多个信令流，也不需要为视频帧设计自有转发协议。

单条 ViewerConnection 关闭时，Gateway 只关闭该连接对应的隧道，不影响其他连接。

### 9.3 运行时停止与注册

Supervisor 启动 Stream Runtime 后，等待 Agent 注册成功，再向 Gateway 确认该 Profile 可连接。

停止 Profile 时：

1. Supervisor 通知 Gateway 将该运行时标记为不可用。
2. Gateway 关闭该 Profile 的全部 ViewerConnection 和信令隧道。
3. Supervisor 停止 Stream Runtime。
4. Supervisor 停止 Browser Runtime。
5. Supervisor 回收 WebRTC UDP 端口。
6. Supervisor 更新实际运行状态。

如果 Gateway 重启，Stream Agent 自动重新连接，Supervisor 重新发送当前运行时快照。所有浏览器进程继续运行，外部页面重新建立 ViewerConnection。

### 9.4 Gateway 的服务安全

Stream Gateway 不挂载 Docker Socket。

Agent 控制连接使用独立的运行时身份验证。每个运行时使用自己的客户端证书，由内部 CA 签发；证书身份包含 Profile ID 和 Runtime Instance ID。

Gateway 只允许已注册 Agent 建立信令隧道。客户端 URL 只能指定 Profile ID，不能指定任意上游 URL、端口或 IP，避免将 Gateway 变成任意 TCP/HTTP 代理。

______________________________________________________________________

# 第五部分：多连接、鉴权与连接生命周期

## 10. ViewerConnection 不等于控制所有权

每条 ViewerConnection 只代表一条画面和输入连接。

它具有以下字段：

```text
connection_id
profile_id
runtime_instance_id
created_at
connected_at
transport_state
client_origin
```

不包含：

```text
owner_profile_id
lease_epoch
exclusive_controller
lease_expires_at
takeover_state
```

ViewerConnection 保存在 Stream Gateway 的内存连接注册表中。它不写入 SQLite，也不需要 Redis。

### 10.1 多连接规则

同一个 Profile 可以同时拥有任意数量的 ViewerConnection，具体数量受系统资源限制。

每个连接都可以向同一个真实浏览器发送输入。Selkies 使用多个控制客户端共享同一个显示的能力。

Selkies 配置固定为：

- WebRTC 模式。
- `enable_sharing=true`。
- `enable_collab=false`。
- 禁止向外部提供 master token。
- 所有正式客户端均使用 `role=controller`。
- 不设置 `mk_control=true`，避免启用单一 Token 的输入权限限制。

参考：

- [Selkies 2.1.0 安全模式](https://docs.selkies.io/latest/secure-mode)
- [Selkies 2.1.0 输入处理器](https://github.com/selkies-project/selkies/blob/2.1.0/src/selkies/input_handler.py)
- [Selkies 2.1.0 WebRTC 信令服务](https://github.com/selkies-project/selkies/blob/2.1.0/src/selkies/webrtc_signaling_server.py)

### 10.2 Profile 级流媒体 Token

每个 Profile 的 Stream Runtime 拥有一个专属的 `controller_token`。该 Token 只授权访问对应运行时，不具有 Selkies master 权限。

运行时启动时生成该 Token，并在 Selkies 的安全模式 Token 表中注册：

```json
{
  "PROFILE_CONTROLLER_TOKEN": {
    "role": "controller"
  }
}
```

`PROFILE_CONTROLLER_TOKEN` 是占位符，实际部署时使用随机生成的高熵 Token。Token 表中不设置 `mk_control`。

同一 Profile 的多个外部标签页使用相同的 Profile 级 controller token。Selkies 通过各自的 Peer ID 区分连接，不需要为每个标签页维护独立的控制权。

API 只在 HTTPS 下向已认证页面返回对应 Profile 的 controller token。它存放在页面内存中，不放进 URL、`localStorage` 或日志。

Gateway 仍然必须验证 CBrowser 登录 Cookie、Origin 和 Profile 运行时状态。单独持有 controller token 不足以绕过 Gateway 访问内部运行时。

Selkies 的 master token 永远不返回前端。

### 10.3 切换目标时的连接关闭

当前页面从 A 切换到 B 时：

1. 关闭 A 的 WebRTC PeerConnection。
2. 关闭 A 的信令 WebSocket。
3. Gateway 清理 A 对应的 ViewerConnection。
4. Gateway 关闭对应 Agent 隧道。
5. Selkies 清理该 Peer。
6. 创建 B 的新 ViewerConnection。

不需要撤销 Profile A 的 controller token，因为 A 的其他 ViewerConnection 仍然合法存在。

### 10.4 关闭、冻结和休眠

不使用浏览器心跳实现控制权续期。

- 页面关闭：WebSocket 和 PeerConnection 断开，Gateway 清理连接。
- 页面切换 Profile：显式关闭旧连接，再建立新连接。
- 页面进入后台：该页面暂停自身的视频接收和解码。
- 页面被冻结或丢弃：不依赖 `beforeunload` 或定时器执行清理；服务端在实际连接断开时清理。
- 电脑休眠：媒体连接可能中断，浏览器运行实例继续运行。
- 页面恢复：检查当前 Profile 运行状态，必要时重新建立 ViewerConnection。
- Gateway 重启：所有 ViewerConnection 重新建立，Browser Runtime 不停止。

Chrome 的冻结、丢弃和页面生命周期行为参考 [Chrome Page Lifecycle API](https://developer.chrome.com/docs/web-platform/page-lifecycle-api)。

______________________________________________________________________

# 第六部分：WebRTC、UDP 端口与 TURN

## 11. WebRTC 媒体通道

媒体通道直接使用 WebRTC，不通过 Caddy、FastAPI 或 Stream Gateway 转发视频帧。

Stream Gateway 只处理信令。媒体连接建立后，Chrome 与对应 Stream Runtime 通过 ICE 协商得到可达路径。

每个 Profile 的 Stream Runtime 使用一个 UDP mux 端口。Selkies 2.1.0 支持 `webrtc_udp_mux_port`，同一个运行时的多个 ViewerConnection 可以共享该 UDP 端口。

## 12. 动态 UDP 端口分配

Supervisor 使用 Docker Engine API 分配并发布媒体端口。

端口池：

```text
30000–30991/UDP
```

每个运行时分配一个端口，宿主机端口与容器内端口保持相同。

例如：

|Profile|Selkies UDP mux 端口|Docker 发布|
|---|---:|---|
|A|30000|`30000:30000/udp`|
|B|30001|`30001:30001/udp`|
|C|30002|`30002:30002/udp`|

Supervisor 为每个 Profile 设置：

```text
SELKIES_MODE=webrtc
SELKIES_ENABLE_DUAL_MODE=false
SELKIES_WEBRTC_UDP_MUX_PORT=<allocated_port>
```

该端口对同一个 Profile 的多个 ViewerConnection 共享。不同 Profile 使用不同的宿主机端口。

端口分配表由 Supervisor 管理，运行时停止后释放。Supervisor 重启后，先扫描现存容器和实际端口映射，再恢复分配表，禁止重复分配已被运行实例占用的端口。

## 13. ICE 地址配置

部署配置固定为：

```text
CBROWSER_WEBRTC_MODE=local|lan|public|relay-only
CBROWSER_WEBRTC_BIND_IP=<宿主机绑定地址>
CBROWSER_WEBRTC_ADVERTISE_IP=<外部客户端可达的地址>
```

### `local`

用于同一台宿主机上的 Chrome。

- UDP 端口绑定到 `127.0.0.1`。
- 宣告地址设置为 `127.0.0.1`。
- 不允许其他设备访问媒体端口。

### `lan`

用于同一局域网内的 Chrome。

- UDP 端口绑定到宿主机指定的局域网接口。
- `CBROWSER_WEBRTC_ADVERTISE_IP` 设置为该接口的实际 IP。
- 防火墙只允许指定局域网访问媒体端口。

### `public`

用于拥有可达公网地址或可配置静态端口转发的部署。

- UDP 端口按配置绑定。
- `SELKIES_WEBRTC_PUBLIC_IP` 设置为实际可达的公网 IP。
- 公网防火墙和 NAT 必须转发对应的 UDP 端口。
- TURN 作为直连失败时的备用媒体路径。

`webrtc_public_ip` 只负责修正 ICE host candidate 中的地址，不会自动建立 NAT 转发。公网 IP、宿主机端口、容器端口和防火墙规则必须一致。

### `relay-only`

用于无法可靠提供直接媒体路径的网络。

- Chrome 使用 TURN relay candidate。
- Stream Runtime 通过 TURN 服务建立自己的 relay candidate。
- 不发布每个 Browser Runtime 的直接媒体 UDP 端口。
- TURN 服务必须有公网可达的中继地址和端口范围。
- 双端 ICE 配置必须经过实际测试，确保 relay-to-relay 媒体连接成立。

该模式必须通过第 18 节的验证门槛后才允许发布。

Selkies 的 ICE 配置参数参考 [官方设置文档](https://docs.selkies.io/latest/reference/settings)。

## 14. TURN 服务

固定使用 coturn，提供：

- UDP/TCP 3478。
- TLS/TCP 5349。
- UDP 中继端口范围 50000–50999。

TURN 使用 REST HMAC 短期凭证。CBrowser 的凭证服务负责生成客户端凭证，Selkies 的 RTC 配置服务为运行时生成对应的 ICE 配置。

客户端凭证有效期固定为 10 分钟。运行时侧的 TURN 配置每 30 分钟刷新一次，确保运行中的 Browser Runtime 不依赖已经过期的 TURN 凭证。

Stream Gateway 不代理 TURN 媒体流量。

正式发布前必须分别验证：

1. 局域网直接连接。
2. 公网直接连接。
3. 直连失败后的 TURN 回退。
4. relay-only 模式。
5. TURN 凭证过期后的刷新与重连。

如果某种网络模式无法建立双端 ICE 连接，该模式不得标记为已支持。

______________________________________________________________________

# 第七部分：画面性能与资源控制

## 15. 默认画面策略

默认逻辑分辨率：

```text
1920×1080
DPR = 1
```

默认活跃画面帧率目标为 30 FPS，不再以 60 FPS 作为多实例运行的默认要求。

Selkies 允许的帧率范围：

```text
SELKIES_FRAMERATE=8,8-30
```

含义为初始 8 FPS，允许客户端在 8–30 FPS 范围内调整。

每个 ViewerConnection 独立调整自己的帧率。不能因为一个外部标签页处于后台，就降低另一个活跃标签页的帧率。

### 15.1 活动检测

前端根据用户输入和页面可见性调整该连接的帧率：

- 页面处于前台但无输入活动：8 FPS。
- 检测到键盘、鼠标或滚动活动：30 FPS。
- 连续 3 秒无输入活动：恢复 8 FPS。
- 页面进入后台：暂停该页面的视频接收和解码。
- 页面重新进入前台：先恢复 8 FPS，再根据活动调整到 30 FPS。

帧率调整使用 Selkies 支持的客户端设置接口，不修改 Profile 的浏览器逻辑屏幕尺寸，也不改变指纹配置。

## 16. 全局资源预算

Supervisor 维护系统资源使用情况，Stream Gateway 和 Stream Runtime 上报活动流数量及编码状态。

资源调度规则：

- CPU 利用率连续 15 秒超过 80%：将活跃流从 30 FPS 降到 20 FPS。
- CPU 仍连续超过 80%：降到 15 FPS。
- CPU 再次持续超过 80%：降到 8 FPS。
- CPU 利用率连续 60 秒低于 65%：每 30 秒恢复一个档位。
- 后台连接优先暂停视频传输。
- 不因资源压力停止浏览器进程。
- 不因单个 Stream Runtime 的编码延迟阻塞其他 Profile 的生命周期操作。

硬件编码优先使用可用的 VAAPI 或 NVIDIA NVENC。无硬件编码时使用已验证的软件 H.264 编码器。

Browser Runtime 与 Stream Runtime 分离，使媒体编码器可以使用 GPU，而浏览器数据和浏览器运行进程不必直接获得 GPU 设备权限。

### 16.1 性能基准

固定基准环境：

```text
Linux x86_64
16 vCPU
32 GiB RAM
无物理 GPU
```

必须测试：

|测试场景|验收要求|
|---|---|
|10 个 Profile 同时运行|全部正常启动并保持独立数据|
|10 个 ViewerConnection|全部建立连接，连接之间不串线|
|1 个活跃流 + 9 个后台流|活跃流目标 1080p30，后台流暂停视频|
|3 个活跃流|记录 CPU、延迟、帧率和内存，达到既定资源门槛|
|10 个活跃流|触发资源预算机制，系统保持响应，帧率按规则下降|
|8 小时运行|无数据损坏、不可恢复的运行时退出或跨 Profile 输入|

单活跃流的验收目标：

- 局域网 RTT 不超过 10 ms。
- 输入到画面反馈延迟 P95 不超过 100 ms。
- 运行时已就绪后的首次画面 P95 不超过 1 秒。

10 个 Profile 可以同时运行不等于 10 个任意复杂网站都能持续以 1080p30 软件编码。性能门槛必须在固定硬件和明确工作负载下测试。

______________________________________________________________________

# 第八部分：中文输入、快捷键与剪贴板

## 17. 中文输入法

不再采用“将输入法组合结果写入剪贴板，再发送粘贴快捷键”的方案。

CBrowser 直接使用 Selkies 2.1.0 的输入处理能力。

参考实现：

- [Selkies 输入处理器](https://github.com/selkies-project/selkies/blob/2.1.0/src/selkies/input_handler.py)
- [Selkies 键盘映射实现](https://github.com/selkies-project/selkies/blob/2.1.0/src/selkies/server_keysym_map.py)

输入链路：

```text
本地 Chrome 输入事件
    ↓
Selkies Web Client 输入适配器
    ↓
WebRTC 输入数据通道
    ↓
Selkies 服务端输入处理器
    ↓
XTEST / 虚拟键盘文本注入
    ↓
真实 CloakBrowser 窗口
```

Selkies 的输入处理器已经包含 X11 XTEST 键盘实现、键映射和虚拟键盘文本注入机制。CBrowser 不重新实现 X11 键盘注入。

必须验证中文 IME 的组合开始、组合更新、组合结束和最终文本提交。输入法组合期间不能将拼音原始按键和最终中文文本重复发送。

### 17.1 输入验收范围

以下场景全部使用真实 CloakBrowser 窗口测试：

1. 浏览器地址栏。
2. 普通网页 `<input>`。
3. `<textarea>`。
4. React/Vue 控制的受控输入框。
5. `contenteditable` 富文本编辑器。
6. 中文输入法候选词选择。
7. 中英文切换、退格和选区替换。
8. 输入过程中切换外部 Chrome 标签页。
9. 多个外部标签页同时连接同一浏览器时的输入行为。

验收标准是输入事件和最终文本正确，而不是只检查页面上是否出现了汉字。

## 18. 剪贴板

剪贴板与中文输入法完全分离。

Selkies 剪贴板配置：

```text
SELKIES_ENABLE_CLIPBOARD=true
SELKIES_CLIPBOARD_SEAMLESS=false
```

CBrowser 不启用默认的无缝双向同步，避免远程复制内容自动覆盖本机剪贴板。

主界面提供两个显式操作：

- “粘贴到远程”：读取用户明确选择发送的本机剪贴板内容，传入对应远程浏览器。
- “复制远程剪贴板”：读取当前远程浏览器剪贴板，再由用户操作写入本机剪贴板。

这些按钮属于 CBrowser 的应用 UI，不叠加在远程浏览器画面上。

Clipboard Bridge 使用 Selkies 原有剪贴板传输能力，不重新发明剪贴板协议。中文 IME 不调用 Clipboard Bridge。

如果 Chrome 拒绝剪贴板 API，页面显示一次性操作提示，用户明确点击后再执行。不得假装写入成功，也不得自动覆盖用户真实剪贴板。

______________________________________________________________________

# 第九部分：API 与后端代码结构

## 19. API 路由

固定采用版本化 REST API。

### Profile

|方法|路由|用途|
|---|---|---|
|`GET`|`/api/v1/profiles`|Profile 列表|
|`POST`|`/api/v1/profiles`|创建 Profile|
|`GET`|`/api/v1/profiles/{id}`|获取配置|
|`PATCH`|`/api/v1/profiles/{id}`|更新配置|
|`DELETE`|`/api/v1/profiles/{id}`|删除 Profile|
|`POST`|`/api/v1/profiles/{id}/duplicate`|复制 Profile|
|`POST`|`/api/v1/profiles/{id}/reset`|重置浏览器数据|
|`POST`|`/api/v1/profiles/reorder`|调整顺序|

### Browser Runtime

|方法|路由|用途|
|---|---|---|
|`POST`|`/api/v1/profiles/{id}/runtime/start`|启动浏览器|
|`POST`|`/api/v1/profiles/{id}/runtime/stop`|停止浏览器|
|`POST`|`/api/v1/profiles/{id}/runtime/restart`|重启浏览器|
|`GET`|`/api/v1/profiles/{id}/runtime`|获取运行状态|
|`GET`|`/api/v1/profiles/{id}/stream-config`|获取流媒体配置和 Profile 级 Token|

### ViewerConnection

ViewerConnection 不持久化到数据库。

Gateway 根据 WebSocket 连接建立和断开维护内存状态。连接数量通过内部状态接口查询。

|方法|路由|用途|
|---|---|---|
|`GET`|`/stream/{profileId}/signal`|建立信令 WebSocket|
|`GET`|`/api/v1/profiles/{id}/connections`|查询当前连接数|
|`GET`|`/api/v1/events`|SSE 运行状态事件|

### 文件和自动化

保留现有的 Profile 文件管理、代理测试、下载捕获、设置和自动化功能，统一迁移到 `/api/v1` 路由。

CDP 通过受控 API 代理访问，禁止直接暴露容器内部调试端口。

## 20. 后端目录结构

```text
backend/
├── cbrowser/
│   ├── app.py
│   ├── config.py
│   │
│   ├── api/
│   │   ├── dependencies.py
│   │   └── v1/
│   │       ├── auth.py
│   │       ├── profiles.py
│   │       ├── runtimes.py
│   │       ├── stream_config.py
│   │       ├── artifacts.py
│   │       ├── settings.py
│   │       └── automation.py
│   │
│   ├── domain/
│   │   ├── profile.py
│   │   ├── runtime.py
│   │   ├── artifact.py
│   │   ├── fingerprint.py
│   │   └── errors.py
│   │
│   ├── services/
│   │   ├── profile_service.py
│   │   ├── runtime_coordinator.py
│   │   ├── engine_artifact_service.py
│   │   ├── artifact_service.py
│   │   ├── download_service.py
│   │   ├── license_service.py
│   │   └── settings_service.py
│   │
│   ├── adapters/
│   │   ├── database/
│   │   ├── cloakbrowser/
│   │   ├── docker/
│   │   ├── filesystem/
│   │   └── selkies/
│   │
│   ├── supervisor/
│   │   ├── app.py
│   │   ├── container_factory.py
│   │   ├── port_allocator.py
│   │   ├── runtime_registry.py
│   │   └── event_reconciler.py
│   │
│   ├── stream_gateway/
│   │   ├── app.py
│   │   ├── auth.py
│   │   ├── runtime_registry.py
│   │   ├── signal_proxy.py
│   │   ├── agent_control.py
│   │   └── connection_registry.py
│   │
│   └── runtime_agent/
│       ├── browser_agent.py
│       ├── stream_agent.py
│       ├── browser_process.py
│       ├── display_manager.py
│       ├── stream_manager.py
│       └── health.py
│
├── migrations/
└── tests/
```

### 模块职责

- **API：** HTTP 参数校验、鉴权和响应，不直接操作 Docker。
- **Domain：** Profile、Runtime、Artifact 和配置版本的业务规则。
- **Services：** Profile 管理、运行时协调、文件管理和引擎授权。
- **Adapters：** SQLite、Docker、CloakBrowser、Selkies 和文件系统的具体实现。
- **Supervisor：** 唯一拥有 Docker Socket 的服务。
- **Stream Gateway：** 固定信令入口、运行时注册和 ViewerConnection 管理。
- **Runtime Agent：** 在对应容器内管理浏览器进程或媒体进程。

______________________________________________________________________

# 第十部分：前端架构

## 21. 前端目录

```text
frontend/src/
├── app/
│   ├── router.tsx
│   ├── providers.tsx
│   └── auth.ts
│
├── features/
│   ├── profiles/
│   │   ├── ProfileList.tsx
│   │   ├── ProfileEditor.tsx
│   │   ├── ProfileIdentitySection.tsx
│   │   ├── ProfileNetworkSection.tsx
│   │   ├── ProfileFingerprintSection.tsx
│   │   └── profileQueries.ts
│   │
│   ├── browser-session/
│   │   ├── BrowserSessionView.tsx
│   │   ├── SelkiesClientAdapter.ts
│   │   ├── ViewerConnection.ts
│   │   ├── InputAdapter.ts
│   │   └── ClipboardBridge.ts
│   │
│   ├── artifacts/
│   ├── automation/
│   └── settings/
│
├── shared/
│   ├── api/
│   │   ├── generated/
│   │   └── client.ts
│   ├── components/
│   └── i18n/
└── styles/
```

### 21.1 主界面

主界面保留 Profile 列表、运行状态和浏览器操控区域。

用户点击 Profile A 时，当前页面将 A 作为目标。点击 Profile B 时，当前页面切换为 B。其他外部 Chrome 标签页的状态不变。

主界面提供“在新标签页打开”操作，使用 Chrome 原生标签页创建机制打开相同的 CBrowser 页面，并传入当前 Profile ID。

### 21.2 远程画面组件

`BrowserSessionView` 只负责显示远程浏览器画面。

不包含：

- CBrowser 自己的内部标签栏。
- 仿制的远程浏览器地址栏。
- 第二套浏览器导航按钮。
- 覆盖在画面上的固定工具栏。
- 额外的内部浏览器标签页模型。

Selkies 的视频和输入能力通过 `SelkiesClientAdapter` 接入。CBrowser 只保留自己的 Profile 选择、连接状态和必要的应用级操作。

### 21.3 Selkies 前端集成

使用固定版本的 Selkies Web Client 核心作为媒体与输入适配基础。

CBrowser 不重写 WebRTC、SDP、ICE、媒体解码和输入协议。只维护一个薄适配层，将 Selkies 的连接、帧率、视频启停、IME 和剪贴板接口提供给 React。

如果官方 Web Client 的现有入口包含不需要的仪表盘或侧栏，则只维护独立的 CBrowser 客户端适配层，不复制或重写整个媒体引擎。

Selkies 源码遵循 MPL-2.0，定制时保留对应文件的许可证声明，并审计随镜像分发的依赖许可。

### 21.4 前端状态管理

TanStack Query 负责 Profile、配置和运行状态缓存。

SSE 推送 Profile 运行状态变化，前端收到事件后更新对应 Query Cache。页面断线重连后重新查询 API，不依赖旧的内存状态恢复服务器状态。

每个页面独立维护：

```text
selectedProfileId
viewerConnection
streamState
```

不将这些值写入跨标签页共享的 `localStorage`。

______________________________________________________________________

# 第十一部分：数据库与运行状态

## 22. SQLite 数据模型

使用 SQLAlchemy 2 + Alembic，保留单机 SQLite。

### 22.1 数据表

|表|职责|
|---|---|
|`profiles`|Profile 身份、名称、备注、标签和当前配置版本|
|`profile_config_versions`|不可变的浏览器配置快照|
|`profile_tags`|标签和颜色|
|`profile_runtimes`|期望状态、实际状态、运行实例 ID 和健康信息|
|`artifacts`|上传、下载和文件元数据|
|`settings`|全局设置|
|`runtime_events`|已持久化的运行事件|
|`audit_events`|创建、修改、启动、停止和删除等审计事件|

不创建 `leases` 表，不创建持久化的 `viewer_connections` 表。

ViewerConnection 由 Gateway 的内存注册表维护。Gateway 重启后连接消失，外部页面重新建立连接即可。

### 22.2 Profile 配置版本

每个 Profile 的指纹、代理、时区、语言、分辨率、GPU 模拟参数、扩展和启动参数保存为版本化配置。

运行时绑定一个明确的 `config_version`。运行期间修改启动参数只创建新版本，不直接修改正在运行的浏览器。

用户点击重启后，Supervisor 使用最新的配置版本创建新的运行实例。

## 23. 期望状态和实际状态

每个 Profile 具有两个独立状态：

```text
desired_state = running | stopped
observed_state = created | starting | running | stopping | stopped | failed
```

`desired_state` 表示用户期望，`observed_state` 表示实际运行情况。

### 23.1 主动停止

1. API 事务中先设置 `desired_state=stopped`。
2. Supervisor 接收停止命令。
3. 关闭该 Profile 的所有 ViewerConnection。
4. 正常停止 Stream Runtime。
5. 正常停止 Browser Runtime。
6. 回收媒体端口和容器资源。
7. 设置 `observed_state=stopped`。

### 23.2 用户直接关闭浏览器窗口

Browser Agent 监控 CloakBrowser 进程。

用户关闭最后一个浏览器窗口后，浏览器进程退出。Browser Agent 将退出原因、退出码、Runtime Instance ID 和事件序号写入持久化的运行事件文件，再退出容器。

Supervisor 收到容器退出事件后读取运行事件。

- 正常退出：将 `desired_state` 更新为 `stopped`。
- 异常退出：保留 `desired_state=running`，记录错误并进入恢复流程。

正常退出事件必须在 Supervisor 的恢复流程中优先处理，不能仅根据旧的 `desired_state=running` 重新启动浏览器。

### 23.3 异常退出恢复

- 异常退出后自动重试最多 3 次。
- 重试间隔固定为 2、10、30 秒。
- 连续 3 次失败后设置 `restart_blocked=true`。
- 用户手动重试时清除失败计数和阻断标记。
- Browser Runtime 的 Docker restart policy 固定为 `no`，由 Supervisor 决定是否重启。
- Stream Runtime 异常退出不自动停止 Browser Runtime；Supervisor 先尝试恢复媒体容器。
- 只有浏览器本身退出时，才执行浏览器级恢复。

Supervisor 重启后先处理未消费的运行事件，再检查 Docker 容器和数据库状态，最后执行启动恢复。这样可以避免用户主动关闭浏览器后被服务重启重新打开。

______________________________________________________________________

# 第十二部分：安全与网络隔离

## 24. Docker 服务网络

固定使用以下网络：

|网络|服务|
|---|---|
|`cbrowser-edge`|Caddy、API、Stream Gateway|
|`cbrowser-control`|API、Supervisor、Stream Gateway|
|`cbrowser-runtime-control`|Stream Gateway、各 Stream Agent|
|`browser-egress-{profileId}`|对应 Browser Runtime|
|`stream-egress-{profileId}`|对应 Stream Runtime|

Browser Runtime 不连接 API、Supervisor 或 Stream Gateway 的管理网络。

Stream Runtime 通过 `cbrowser-runtime-control` 主动连接 Gateway。它不开放供其他 Profile 访问的控制端口。

不同 Profile 的浏览器运行容器使用不同的出站网络，不能直接访问其他 Profile 的容器网络。

Stream Gateway 只接受已注册 Agent 的认证连接，不接受任意容器目标地址。

## 25. 服务认证

### 外部 Chrome

- 强制 HTTPS。
- 登录使用服务端会话 Cookie。
- Cookie 设置 `HttpOnly`、`Secure`、`SameSite=Strict`。
- WebSocket 严格验证 Origin。
- API 修改操作验证 CSRF Token。
- 浏览器操控页面必须通过登录鉴权。

### API 与 Supervisor

- 使用 mTLS。
- Supervisor 只接受固定的容器生命周期 RPC。
- Supervisor 是唯一挂载 Docker Socket 的服务。
- API 不直接执行 Docker 命令。

### Runtime Agent 与 Gateway

- 使用内部 CA 签发的运行时客户端证书。
- Agent 证书绑定 Profile ID 和 Runtime Instance ID。
- Gateway 校验证书身份、运行时注册状态和 Profile 匹配关系。
- Agent 不接受任意客户端命令，只响应固定的注册、信令隧道和状态请求。

### Selkies

- 设置独立的 `SELKIES_MASTER_TOKEN`。
- Master Token 只在对应 Stream Runtime 内使用。
- 每个 Profile 使用自己的 controller token。
- 不公开 Selkies 内部 HTTP API、Token 管理 API 或 CDP 端口。
- Gateway 只提供信令隧道，不提供通用 HTTP 代理。

## 26. Profile 出站网络

每个 Profile 的代理配置独立保存。

配置代理时，浏览器外网流量必须遵守对应的代理策略。默认不自动绕过所有私有网段。

宿主机内网访问需要明确的允许规则。容器不得访问其他 Profile 的数据目录，也不得通过开放的内部服务访问其他 Profile。

Docker 网络隔离不能单独保证指纹隔离。浏览器指纹仍需通过 CloakBrowser 的配置和实际检测测试验证。

______________________________________________________________________

# 第十三部分：保留现有功能与仓库改造

## 27. 现有功能的保留规则

这次改造保留 CBrowser 已有的核心业务能力：

- Profile 创建、编辑、删除和排序。
- 标签管理。
- 代理配置和代理连通性测试。
- 时区、语言、屏幕和指纹配置。
- CloakBrowser 授权和版本管理。
- 扩展路径与启动参数配置。
- 浏览器数据重置。
- Profile 复制，支持选择是否复制浏览器数据。
- 内部标签页恢复。
- 自动启动。
- 文件上传、下载、配额和文件列表。
- 下载捕获与 Artifact 归档。
- 自动化 CDP 接口。
- 中英文界面。
- 系统状态和错误诊断。
- 配置和浏览器数据备份恢复。

浏览器画面截图不再作为远程操控的主要手段。现有截图预览功能可以保留为管理列表中的辅助预览，但不能与实时 WebRTC 画面重复实现。

## 28. 现有文件的具体改造

|现有文件|改造方式|
|---|---|
|`backend/main.py`|拆分 API 路由、鉴权和业务服务；删除 RFB 解析和 VNC 代理|
|`backend/browser_manager.py`|拆分 Profile 业务、浏览器进程、引擎授权、截图和下载捕获|
|`backend/database.py`|改为 SQLAlchemy 2、Repository 和 Alembic|
|`backend/vnc_manager.py`|删除|
|`backend/artifacts.py`|保留配额和文件安全逻辑，迁移到 Artifact Service|
|`backend/downloads.py`|下载事件捕获迁移到 Browser Agent，元数据归档归 Artifact Service|
|`backend/runtime.py`|删除 native-window 和跨平台原生运行模式|
|`backend/models.py`|拆分 Domain Model、API Schema 和运行时协议模型|
|`backend/diagnostics.py`|保留并扩展结构化日志、运行时错误和 Trace ID|
|`backend/settings_store.py`|迁移到统一 Settings Service|
|`frontend/src/App.tsx`|改成路由和应用 Provider|
|`frontend/src/components/ProfileViewer.tsx`|删除 noVNC，改成 Selkies WebRTC 适配组件|
|`frontend/src/hooks/useProfiles.ts`|改为 TanStack Query hooks 和 SSE 状态更新|
|`frontend/src/lib/api.ts`|使用 OpenAPI 生成的 API 类型|
|`frontend/src/components/ProfileForm.tsx`|拆分为配置区块|
|`frontend/src/components/ProfileFiles.tsx`|保留功能，迁移到独立文件管理模块|
|`frontend/src/components/CdpEndpointButton.tsx`|保留功能，迁移到自动化管理模块|
|`frontend/src/components/NativeWindowStatus.tsx`|删除|
|`frontend/src/i18n.tsx`|保留并整理中英文资源|
|`Dockerfile`|拆成 API、Supervisor、Browser Runtime 和 Stream Runtime 构建文件|
|`docker-compose.yml`|改成 `compose.yaml`，定义常驻服务和网络|
|`entrypoint.sh`|删除旧的单容器启动和 Xvnc 清理逻辑|
|`app_entry.py`|删除原生应用入口|
|`run-macos.sh`、`run-windows.bat`|删除原生应用启动路径|
|`packaging/`|删除原生安装包构建流程|
|`.github/workflows/ci.yml`|改为前后端、Chrome E2E 和 Docker 集成测试|
|`.github/workflows/release.yml`|改为多架构容器镜像构建和发布|
|`README.md`|重写为 Docker + Chrome 部署说明|
|`DOCKER_DEPLOYMENT.md`|重写网络、运行时、备份、恢复和故障排查文档|

旧的 noVNC、KasmVNC 和 RFB 转换实现只有在新架构完成验收后才删除。

## 29. 代码质量规则

### Python

- Ruff 负责格式和静态检查。
- Mypy 对 Domain、Services 和协议层执行严格类型检查。
- Pydantic 2 负责 API Schema 校验。
- SQLAlchemy 2 负责数据库访问。
- Alembic 负责所有数据库迁移。
- 所有生命周期操作必须有幂等操作 ID。
- 所有外部进程必须有明确的超时、取消和清理逻辑。
- 不允许在 API 路由中直接操作 Docker、文件系统或浏览器进程。

### TypeScript

- ESLint、Prettier 和 TypeScript 严格模式。
- API 类型从 OpenAPI 生成。
- 连接状态和 Profile 运行状态分开管理。
- 不在组件中直接处理 Selkies 的底层 WebRTC 协议。
- 不使用跨标签页共享的全局当前 Profile 状态。
- 所有 WebSocket 和 PeerConnection 都必须在组件清理或目标切换时关闭。

### 依赖与许可

- Python 使用 `uv.lock`。
- 前端使用 `package-lock.json` 和 `npm ci`。
- Docker 基础镜像固定发行版和摘要。
- Selkies 固定提交。
- 所有随镜像分发的依赖都进行许可审计。
- CloakBrowser 二进制按照其许可条件获取和分发。

______________________________________________________________________

# 第十四部分：技术验证与验收

## 30. 第一阶段：单 Profile 技术验证

在独立分支 `spike/selkies-runtime` 中完成，不迁移数据库，不删除旧链路。

验证以下内容：

01. 在独立 Browser Runtime 中启动 CloakBrowser。
02. Stream Runtime 通过 X11 Socket 卷连接显示。
03. Selkies 捕获完整浏览器窗口，包括真实内部标签栏。
04. WebRTC 通过固定 Gateway 信令路径建立连接。
05. 外部 Chrome 能显示画面并发送键鼠输入。
06. 同一 Profile 的两个 Chrome 页面可以同时连接。
07. 两个页面使用同一个 Profile controller token 时，Selkies 正确接受两个控制 Peer。
08. 两个页面可以同时输入，不会互相断开。
09. 一个页面切换目标后，另一个页面继续操作原浏览器。
10. 中文输入不使用剪贴板模拟。
11. WebRTC 直连、TURN 回退和 relay-only 均按配置验证。
12. Browser Runtime 关闭后，Stream Runtime 正确报告显示丢失。
13. Gateway 重启后，Agent 自动重连，浏览器进程保持运行。
14. macOS OrbStack arm64 和 Linux x86_64 Docker 构建通过。

**以上全部通过后，才冻结正式架构。**

如果同一 Profile 的多个控制客户端无法使用同一个 Profile controller token 正常连接，必须先修复 Selkies 集成并重新验证，不得退回独占控制租约模型。

## 31. 第二阶段：外部标签页验收

固定执行以下测试：

### 测试 A：同一标签页切换目标

1. 外部标签 A 选择 Profile A。
2. 确认 A 的浏览器正常显示。
3. 点击 Profile B。
4. 确认标签 A 显示 B。
5. 确认 A 的浏览器进程仍然运行。
6. 确认 A 的内部标签页状态未变化。

### 测试 B：多个标签页操作不同浏览器

1. 标签 A 选择 Profile A。
2. 点击“在新标签页打开”，创建标签 B。
3. 标签 B 选择 Profile B。
4. 在 A 中导航网页。
5. 确认 B 的页面和状态不受影响。
6. 交换 A、B 的操控目标，再次验证。

### 测试 C：多个标签页操作同一个浏览器

1. 标签 A 连接 Profile A。
2. 标签 B 连接 Profile A。
3. 确认两个页面显示同一个真实浏览器窗口。
4. 在 A 中创建内部标签页。
5. 确认 B 显示相同内部标签页。
6. 在 B 中输入文字，确认 A 看到相同结果。
7. 关闭 A 的外部标签页。
8. 确认 B 仍然可以操作 A 的浏览器。
9. 确认 Profile A 的 Browser Runtime 没有停止。

### 测试 D：浏览器生命周期

1. 打开两个外部标签页，均连接 Profile A。
2. 在其中一个页面关闭连接。
3. 确认另一个页面仍然正常工作。
4. 在管理页面明确停止 Profile A。
5. 确认两个页面均显示浏览器已停止。
6. 重新启动 Profile A。
7. 确认两个页面可以重新连接。

以上测试必须全部通过。

## 32. 第三阶段：输入、剪贴板与媒体

### 输入

- 1000 次中文 IME 组合输入。
- 1000 次英文输入和快捷键测试。
- 地址栏、输入框、文本区域和富文本编辑器测试。
- 同一个浏览器被两个页面同时操作的输入测试。
- 页面切换和重新连接时的输入焦点测试。

### 剪贴板

- 文本双向传输。
- HTML 内容传输。
- 图片剪贴板传输。
- 用户剪贴板原内容保护。
- 后台标签页不覆盖本机剪贴板。
- API 权限拒绝时显示明确错误。

### 媒体

- WebRTC 直连。
- TURN 回退。
- relay-only。
- 运行时端口回收。
- Gateway 重启。
- 外部标签页关闭。
- 外部标签页冻结与恢复。
- 电脑休眠与恢复。
- 多连接共享同一浏览器。

## 33. 第四阶段：安全和隔离

必须通过以下测试：

01. 浏览器运行容器不挂载 Docker Socket。
02. 浏览器运行容器不能读取其他 Profile 数据目录。
03. Stream Runtime 不能读取 Browser Runtime 的 Profile 数据。
04. 外部客户端不能直接访问 Selkies 内部 HTTP API。
05. 外部客户端不能直接访问 CDP 调试端口。
06. Gateway 拒绝未经认证的 Agent。
07. Gateway 拒绝伪造 Profile ID 的信令连接。
08. Gateway 不接受客户端指定的任意上游 URL。
09. 过期登录 Cookie 不能建立新的信令连接。
10. 跨 Origin WebSocket 请求被拒绝。
11. Profile 停止后，旧信令隧道被关闭。
12. Browser Runtime 异常退出不会误判为用户主动停止。
13. 用户主动关闭浏览器后，服务重启不会重新打开该浏览器。
14. 浏览器数据复制、重置和删除时不会与运行中的进程竞争。

______________________________________________________________________

# 第十五部分：数据迁移与发布

## 34. 数据迁移流程

迁移前先停止旧版本和所有浏览器进程。

完整备份：

```text
~/.cbrowser/
├── profiles.db
├── settings.json
├── profiles/
├── artifacts/
└── logs/
```

迁移工具必须：

01. 支持 `--dry-run`。
02. 保留 Profile UUID。
03. 保留 Profile 名称、备注、标签和排序。
04. 保留指纹参数、代理、时区、语言、扩展和启动参数。
05. 保留所有浏览器用户数据目录。
06. 保留 Artifact 元数据和实际文件。
07. 校验迁移前后的文件校验和。
08. 校验 Profile、Tag、Artifact 数量。
09. 失败时恢复原始数据库和数据目录。
10. 在迁移成功前保留旧版本镜像。

运行中的 Profile 不允许执行复制、重置和删除文件操作。

## 35. 实施顺序

### 阶段 0：技术验证

建立单 Profile Spike，验证 X11 跨容器连接、Selkies、多连接共享、信令隧道、IME、ICE 和 TURN。

### 阶段 1：新后端骨架

建立 Domain、Service、Repository、Alembic 和 API。实现统一鉴权和配置版本管理。

### 阶段 2：运行时容器

实现 Browser Runtime、Stream Runtime、X11 Socket 卷、独立 Profile 数据卷和 Supervisor。

### 阶段 3：Stream Gateway

实现 Agent 注册、信令隧道、WebSocket 生命周期和运行时路由。

### 阶段 4：WebRTC 和输入

接入 Selkies 客户端，完成视频、输入、剪贴板、IME 和资源预算。

### 阶段 5：前端重构

实现主界面、Profile 切换、在新标签页打开、独立 ViewerConnection 和状态推送。

### 阶段 6：功能迁移

迁移 Profile 配置、代理测试、授权、下载、文件、CDP、备份和恢复。

### 阶段 7：迁移和验收

完成旧数据迁移，运行完整的功能、性能、安全和恢复测试。

### 阶段 8：删除旧实现

只有新版本全部验收通过后，才删除 noVNC、KasmVNC、RFB 解析器、旧 VNC Manager 和原生桌面运行路径。

______________________________________________________________________

# 第十六部分：最终架构结论

CBrowser v2.2 的正式架构由以下部分组成：

1. **React 主界面**：每个外部 Chrome 标签页拥有独立的目标选择状态。
2. **Profile Service**：管理浏览器配置和持久化数据。
3. **Browser Runtime**：运行真实 CloakBrowser 窗口。
4. **Stream Runtime**：通过 Selkies 提供远程画面和输入。
5. **Stream Gateway**：通过固定入口和 Agent 信令隧道连接任意动态运行时。
6. **Runtime Supervisor**：管理容器、端口、运行状态和恢复。
7. **SQLite**：保存配置、运行状态、Artifact 和审计数据。
8. **Caddy**：提供固定 HTTPS 入口。
9. **coturn**：提供 WebRTC 中继。

最终的数据关系是：

```text
Chrome 页面 A ── ViewerConnection A ──┐
                                     ├── BrowserRuntime A
Chrome 页面 C ── ViewerConnection C ──┘

Chrome 页面 B ── ViewerConnection B ───── BrowserRuntime B
```

一个外部页面可以自由切换目标。多个页面可以连接同一个 Profile。每个 Profile 的浏览器运行实例独立存在，连接关闭不会影响浏览器生命周期。

**这版不再包含独占控制权、控制租约、租约代次、接管等待或 Redis。** 它只保留必要的连接认证、信令路由和浏览器运行时状态管理。

最重要的实施原则仍然是：先验证单 Profile、多外部页面、同一浏览器多连接、中文输入和 WebRTC/TURN 的完整闭环，再开始大规模重构和数据迁移。这样可以在保证最终架构干净的同时，避免在最关键的技术集成尚未验证时就删除现有可用实现。
