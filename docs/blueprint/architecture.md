# 架构

CBrowser 是面向隐私浏览器与多身份隔离的远程浏览器管理系统。采用单机 Docker 架构，以 Google Chrome 作为唯一官方支持的外部标签页客户端，通过 Selkies 2.1.0 WebRTC 实现低延迟远程画面传输，由独立容器实现严格的 Profile 隔离。

## 1. 上游来源与开源技术依赖矩阵

本项目由 TuTouPower 维护，基于上游仓库 [CloakHQ/CloakBrowser-Manager](https://github.com/CloakHQ/CloakBrowser-Manager) 重构演进。各层关键依赖的开源仓库及技术说明如下：

|依赖层级|组件名称|开源/官方仓库|选型版本 / Commit|职责与架构边界|
|---|---|---|---|---|
|**上游衍生来源**|CloakBrowser-Manager|[CloakHQ/CloakBrowser-Manager](https://github.com/CloakHQ/CloakBrowser-Manager)|0.1.8+ (分支基线)|业务模型原型；v2 已彻底解除对上游 UI 与单容器 VNC 运行时的同步，独立演进|
|**隐私指纹引擎**|CloakBrowser Engine|[PyPI: cloakbrowser](https://pypi.org/project/cloakbrowser/)|`>=0.6.3`|底层真实隐身浏览器内核与指纹随机对抗引擎（许可参见 `BINARY-LICENSE.md`）|
|**远程画面捕获**|Selkies WebRTC|[selkies-project/selkies](https://github.com/selkies-project/selkies)|Release `2.1.0` (`6ee68a7a`)|捕获 Xvfb 画面、低延迟硬件/软件视频编码、WebRTC 媒体协商与输入控制协议|
|**NAT 中继穿透**|coturn|[coturn/coturn](https://github.com/coturn/coturn)|`4.6-alpine`|STUN / TURN 协议实现，保障非对称 NAT 与跨网段 WebRTC 媒体中继|
|**边缘反向代理**|Caddy|[caddyserver/caddy](https://github.com/caddyserver/caddy)|`2-alpine`|自动化 TLS、SPA 前端静态资源服务与 WebSocket 信令代理入口|
|**模板与工作流**|repo_template|本地 `../repo_template`|当前工作流基线|消费仓规范：task 状态机驱动、轻量契约门禁、specs/blueprint 规范|
|**文档格式化**|md_kx|[TuTouPower/md_kx](https://github.com/TuTouPower/md_kx)|PyPI `md-kx`|Markdown 文档自动化规范与一致性门禁检查|

## 2. 系统整体拓扑

```text
Google Chrome Stable（宿主端）
│
├── /manage                           # 浏览器配置、标签、文件管理与运行监控
├── /open                             # 浏览器快捷选择与会话绑定
├── /browser/{profileId}              # 纯净操控界面（仅显示远程 CloakBrowser 真实窗口）
└── /api/v1/*                         # 控制 API
      │
      ├── Caddy 反向代理（TLS、静态前端托管、API/信令路由）
      │     │
      │     ▼
      ├── cbrowser-api（FastAPI）
      │     ├── SQLite (WAL) + Alembic 持久化
      │     ├── Profile Service / Session Lease Service
      │     ├── Artifact Service / Engine Artifact Service
      │     └── Runtime Coordinator
      │           │ (内部网络 RPC)
      │           ▼
      ├── cbrowser-supervisor（独立容器，唯一挂载 Docker Socket）
      │     ├── Container Factory & Lifecycle Management
      │     ├── Runtime Registry
      │     └── UDP 媒体端口分配器 (30000-30999)
      │           │
      │     ┌─────┴────────────────┐
      │     ▼                      ▼
      │  cbrowser-runtime-A     cbrowser-runtime-B  (按 Profile 动态创建)
      │  ├── CloakBrowser       ├── CloakBrowser
      │  ├── Xvfb (:99)         ├── Xvfb (:99)
      │  ├── Openbox            ├── Openbox
      │  ├── Runtime Agent      ├── Runtime Agent
      │  └── Selkies 2.1.0      └── Selkies 2.1.0
      │         │                      │
      │         └────── WebRTC ────────┘
      │                    │
      ▼                    ▼
   coturn（TURN / STUN 中继，端口 3478 / 5349，媒体范围 50000-50100）
```

## 3. 核心模块与职责划分

|模块|进程/容器|职责与安全边界|
|---|---|---|
|**Caddy**|边缘反向代理|统一暴露 HTTPS 端口，托管前端静态资源，反向代理 API 及 WebSocket 信令，不处理实际视频帧|
|**Control API**|`cbrowser-api` 容器|HTTP 接口、用户鉴权、Profile CRUD、会话租约分配、文件上传下载。**严格禁止挂载 Docker Socket**|
|**Runtime Supervisor**|`cbrowser-supervisor` 容器|宿主机唯一持有 Docker Socket 的服务，仅响应内部受限 RPC，管理运行时容器生命周期与端口分配|
|**Browser Runtime**|`cbrowser-runtime-{id}` 容器|运行特定 Profile 的独立沙箱，包含真实 CloakBrowser、Xvfb 虚拟屏幕、Openbox 窗口管理器与 Selkies 捕获层|
|**Runtime Agent**|运行容器内常驻守护|监听 CDP 下载事件、同步剪贴板、代理中文输入法组合、上报容器健康状态|
|**coturn**|`coturn` 容器|提供 STUN/TURN 中继，保障非对称 NAT 或受限局域网环境下的 WebRTC 媒体连通|

## 4. 标签页体系与前端路由设计

系统严格区分两层标签页：

- **外部原生 Chrome 标签页**：用户宿主机通过 `<a target="_blank">` 在新标签打开 `/browser/{profileId}`。页面全屏渲染远程画面，严禁绘制虚拟标签栏或顶部工具栏。
- **内部隐私浏览器标签页**：远程容器内运行 CloakBrowser 真实图形窗口，用户通过真实的 Chrome UI 创建、切换与关闭内部标签页。

### 路由规划

|路由路径|组件角色|界面与交互行为|
|---|---|---|
|`/manage`|管理主页面|配置列表、编辑表单、网络代理配置、文件交换与系统审计|
|`/open`|快捷选择页|快速选择 Profile 并绑定到当前外部 Chrome 标签页|
|`/browser/{profileId}`|独立操控页|无任何装饰 UI，自适应铺满显示对应远程浏览器的 60 FPS 画面|

## 5. 远程画面传输与后台管理

1. **WebRTC 直连与中继**：优先通过 ICE 直连，直连受阻自动回退至 Coturn STUN/TURN 中继（DTLS-SRTP 加密）。
2. **后台标签页自动休眠**：
    - 当 Chrome 标签页变为不可见（`hidden`）时，前端发送暂停事件，容器停止画面捕获与视频编码，节约 CPU/GPU 开销，同时保持浏览器内核网络与脚本运行。
    - 重新进入前台（`visible`）时请求新关键帧，300ms 内恢复流畅实时渲染。
3. **中文输入代理与剪贴板**：
    - 透明输入代理拦截输入法组合（Composition）过程，组合完毕后以完整 Unicode 文本注入，防拼音丢字。
    - 双向剪贴板按控制会话隔离，后台标签页禁止修改宿主剪贴板。

## 6. 隔离与安全边界

1. **容器隔离**：每个 Profile 对应专属容器与独立卷目录（`/data/profiles/{id}/profile` 与 `/data/profiles/{id}/exchange`），禁止跨 Profile 挂载。
2. **权限最小化**：浏览器运行容器采用非 root 用户运行，开启 `no-new-privileges`，删除多余 Linux capabilities，只读根文件系统。
3. **网络与调试限制**：浏览器容器不开放公网端口，CDP 仅监听容器内回环（`127.0.0.1`），外部自动化通过 Control API 统一鉴权代理访问。
4. **控制租约**：每个 Profile 同一时刻仅允许一个活跃写控制会话（Heartbeat 5s，断开容限 15s，重连窗口 30s）。
