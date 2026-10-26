# CBrowser v2：完整架构重构与升级实施方案

**方案状态：最终技术决策**

**目标：Docker 部署、Google Chrome 作为唯一外部浏览器、独立隐私浏览器运行实例、最低长期技术债。**

## 1. 最终架构决策

本次改造采用一次完整的架构重构。保留 CloakBrowser 引擎和现有核心业务能力，删除旧的原生桌面运行路径及 VNC/RFB 兼容层，重新实现运行时隔离、远程画面传输和外部标签页会话管理。

| 技术层 | 最终选型 | 固定职责 |
|---|---|---|
| 外部客户端 | Google Chrome Stable | 使用 Chrome 原生标签页管理多个浏览器会话 |
| Web 前端 | React 19 + TypeScript + Vite | 配置管理页面和独立浏览器操控页面 |
| 前端路由 | React Router 7 | 区分管理、选择浏览器和浏览器操控路由 |
| 前端数据状态 | TanStack Query 5 | 管理 API 数据、缓存、更新和错误状态 |
| API 类型 | FastAPI OpenAPI + openapi-typescript | 从后端接口生成前端类型 |
| 控制后端 | Python 3.12 + FastAPI | 配置管理、会话授权、业务逻辑、文件管理 |
| 数据库 | SQLite + SQLAlchemy 2 + Alembic | 持久化配置、会话租约、运行状态和迁移 |
| 容器管理 | 独立 Runtime Supervisor + Docker SDK | 创建、停止、检查和恢复浏览器容器 |
| 浏览器运行时 | 每个配置对应一个独立容器 | 启动 CloakBrowser、虚拟显示和浏览器运行代理 |
| 远程显示 | Selkies 2.1.0，固定到官方发布提交 | 捕获真实浏览器窗口、视频编码、输入和 WebRTC |
| 媒体传输 | WebRTC + ICE + TURN | 低延迟画面传输和网络穿透 |
| TURN 服务 | coturn | NAT 穿透和媒体中继 |
| HTTPS 入口 | Caddy | TLS、静态前端、API 和信令路由 |
| 文件存储 | 宿主机持久化目录，每个配置独立子目录 | 浏览器数据、上传、下载和配置备份 |
| 自动化接口 | 独立授权的 CDP 代理 | Playwright/Puppeteer 自动化，不公开浏览器调试端口 |

Selkies 固定使用 [官方 2.1.0 发布版本](https://github.com/selkies-project/selkies/releases/tag/2.1.0)，发布提交为 `6ee68a7a815956e6745e916741f13335e0b3ff53`。CBrowser 使用其 WebRTC 媒体能力和可嵌入的 Web Client，并通过独立适配层实现会话授权和生命周期管理。

### 明确不采用的技术

1. 不再使用 noVNC 作为主画面客户端。
2. 不再使用 KasmVNC 作为主远程显示服务。
3. 不再在 Python API 中解析、过滤和改写 RFB 消息。
4. 不重写 CloakBrowser 内核，不替换成未经指纹适配的普通 Chromium。
5. 不将浏览器启动和显示服务全部放在一个 Manager 容器中。
6. 不使用 Go 重写现有 Python 业务层。
7. 不引入 PostgreSQL、Redis、Kubernetes 或多节点集群。
8. 不开发 Electron、Tauri 或原生 macOS/Windows 客户端。
9. 不支持 Safari、Firefox 等外部浏览器的兼容性承诺，只验收 Chrome Stable。
10. 不实现 CBrowser 自己的外部浏览器标签栏。

这里选择 SQLite 而不是 PostgreSQL，是因为目标是单机 Docker 部署，数据库只有一个权威写入服务。SQLite WAL、事务、唯一约束和 Alembic 迁移足以满足该架构，不需要额外维护数据库服务。

---

## 2. 产品层面的不可变规则

整个系统必须严格区分两层标签页。

### 2.1 外部 Chrome 标签页

外部 Chrome 负责管理浏览器标签页。

CBrowser 提供浏览器配置列表和“在新标签页打开”操作。用户点击后，Chrome 原生打开一个新的 CBrowser 浏览器操控 URL。

例如：

| 外部 Chrome 标签页 | 对应的远程浏览器 |
|---|---|
| Chrome 标签页 A | 隐私浏览器 A |
| Chrome 标签页 B | 隐私浏览器 B |
| Chrome 标签页 C | 隐私浏览器 C |

每个外部标签页有自己的页面状态、控制会话、媒体连接和输入事件通道。

CBrowser 不在页面中绘制用于切换 A、B、C 的虚拟标签栏。标签切换完全由 Chrome 完成。

### 2.2 隐私浏览器内部标签页

每个远程浏览器运行真正的 CloakBrowser 图形窗口。

窗口中包含真实的内部标签栏、地址栏、后退和前进按钮、刷新按钮以及网页内容。用户通过真实的浏览器 UI 创建、关闭和切换内部标签页。

CBrowser 不模拟内部浏览器标签页，不将内部标签页实现成 React 路由，也不在浏览器画面上叠加另一套地址栏或浏览器工具栏。

### 2.3 浏览器操控页面的 UI

操控页面使用整个可用内容区域显示远程浏览器画面。

连接状态正常时，不显示 CBrowser 自己的顶部工具栏、侧边栏、悬浮按钮或伪造的浏览器控件。连接中断时才显示错误和重连界面。

配置编辑、代理测试、文件管理、CDP 自动化入口和运行状态放在管理页面，不放在远程浏览器画面上。

---

## 3. 目标系统架构

```text
Google Chrome Stable
│
├── /manage
│   └── 浏览器配置管理、代理、文件、运行状态
│
├── /open
│   └── 选择一个浏览器并绑定当前外部标签页
│
├── /browser/{profileId}
│   └── 只显示对应隐私浏览器的完整窗口画面
│
└── /api/v1/*
    └── 控制 API
          │
          ├── SQLite + Alembic
          │
          ├── Profile Service
          ├── Session Lease Service
          ├── Artifact Service
          ├── License / Engine Service
          └── Runtime Coordinator
                  │
                  ▼
           Runtime Supervisor
           唯一持有 Docker Socket
                  │
          ┌───────┴────────┐
          ▼                ▼
  Browser Runtime A   Browser Runtime B
  独立容器             独立容器
  ├── CloakBrowser     ├── CloakBrowser
  ├── Xvfb             ├── Xvfb
  ├── Openbox          ├── Openbox
  ├── Runtime Agent    ├── Runtime Agent
  └── Selkies          └── Selkies
          │                │
          └──── WebRTC ────┘
                   │
          Direct ICE / TURN
                   │
                   ▼
               coturn

Caddy：HTTPS、静态资源、API 和信令入口
```

每个浏览器配置对应一个独立的浏览器运行容器。运行容器内部包含一个浏览器运行代理和一个 Selkies 会话。

浏览器容器只挂载自己的数据目录和文件交换目录。它不能访问其他浏览器配置目录，不能访问 Docker Socket，也不对公网开放 HTTP、CDP 或内部控制 API。

控制 API 和 Runtime Supervisor 是两个独立的服务。API 不持有 Docker Socket，不能直接创建任意容器。

---

## 4. 浏览器运行时设计

### 4.1 每个 Profile 一个容器

浏览器配置创建后，系统为它分配稳定的 `profile_id`。运行时容器名称固定为：

```text
cbrowser-runtime-{profile_id}
```

容器标签至少包含：

- `com.cbrowser.managed=true`
- `com.cbrowser.profile-id={profile_id}`
- `com.cbrowser.config-version={version}`
- `com.cbrowser.runtime-image={digest}`

Runtime Supervisor 只能使用预先定义的运行时镜像和固定启动参数。客户端不能指定任意镜像、宿主机挂载、容器命令或网络模式。

每个浏览器容器内运行：

1. CloakBrowser Python 运行代理。
2. Xvfb 虚拟显示服务器。
3. Openbox 轻量窗口管理器。
4. Selkies 2.1.0。
5. 当前 Profile 的下载捕获和文件交换逻辑。

Xvfb 固定使用容器内显示 `:99`。由于每个 Profile 都在独立容器中，这个显示编号不会与其他 Profile 冲突。

Openbox 只负责窗口定位和最大化，不显示 Linux 桌面面板。浏览器窗口默认最大化，保留真正的浏览器内部 UI。

### 4.2 CloakBrowser 引擎管理

保留当前仓库对官方 `cloakbrowser` Python 包的调用方式和许可证逻辑。

将引擎版本、下载和许可证处理抽象成 `EngineArtifactService`：

- 引擎版本固定并写入运行时配置。
- 下载文件按版本和 SHA-256 标识。
- 同一版本的引擎二进制只下载一次，存放在共享的引擎缓存中。
- 引擎缓存写入由 Engine Service 独占管理；浏览器运行容器以只读方式使用已准备好的引擎文件。
- 每个运行时启动时读取授权密钥，并调用官方 CloakBrowser API。
- 不将付费引擎二进制直接打包进不允许再分发该二进制的公开镜像。
- 引擎升级必须经过独立的兼容性测试，不跟随未锁定的依赖自动升级。

许可证密钥不写入日志、不写入浏览器配置、不作为公开 API 返回值，也不直接暴露给前端。

### 4.3 Profile 数据隔离

宿主机数据目录固定为：

```text
/data/
├── cbrowser.db
├── settings/
├── engine-cache/
├── profiles/
│   ├── {profileId-A}/
│   │   ├── profile/
│   │   ├── exchange/
│   │   └── runtime.json
│   └── {profileId-B}/
│       ├── profile/
│       ├── exchange/
│       └── runtime.json
├── artifacts/
├── backups/
└── logs/
```

`profile/` 保存浏览器真实用户数据，包括 Cookie、网站存储、缓存和内部标签页恢复信息。

`exchange/` 保存供该浏览器使用的上传文件和待归档下载文件。

每个浏览器容器只挂载自己的 `profile/`、`exchange/` 和只读运行配置。管理服务负责创建、备份和复制目录。

浏览器运行时关闭时，所有浏览器数据仍保留在宿主机，不依赖容器可写层。

### 4.4 浏览器配置版本化

将 Profile 配置分成两类：

- **可实时修改的元数据：** 名称、备注、标签、排序。
- **需要重启的运行参数：** 指纹种子、代理、时区、语言、屏幕、GPU 模拟参数、扩展和浏览器启动参数。

每次运行绑定一个不可变的配置版本。运行期间修改启动参数只创建新配置版本，不直接改变现有浏览器进程的运行环境。

管理页面明确显示“当前运行版本”和“待生效版本”。只有用户明确执行重启后，新版本才应用到浏览器。

### 4.5 资源与网络

每个运行容器启用：

- 非 root 用户。
- `no-new-privileges`。
- 删除不需要的 Linux capabilities。
- 默认 seccomp 配置。
- 只读根文件系统。
- 独立的 `/tmp`、`/dev/shm` 和下载目录。
- 固定的 CPU、内存和进程数限制。
- 禁止挂载 Docker Socket。
- 禁止使用宿主机网络模式。
- 禁止公开 CDP 调试端口。

浏览器代理模式下，Chromium 只能使用该 Profile 的代理配置。代理绕过规则采用明确的逐 Profile 白名单，默认只允许必要的回环地址；不再默认绕过所有 `192.168.*`、`10.*` 和 `172.16.*` 私有网络地址。

Docker 容器提供的是进程、文件和网络命名空间隔离，不等同于独立虚拟机，也不自动保证网站无法关联浏览器指纹。

---

## 5. 远程画面传输

### 5.1 删除旧 VNC/RFB 主链路

当前仓库使用 noVNC 1.4.0 和 KasmVNC 1.3.3，后端需要自行解析 RFB 消息、过滤扩展消息，并转换 KasmVNC 的剪贴板消息。

新架构删除整个 RFB 兼容层。

Selkies 2.1.0 负责捕获远程浏览器窗口、编码画面和接收输入。CBrowser 只负责授权会话、绑定运行时和提供 WebRTC 信令入口。

媒体数据不再经过 Python API 的逐帧转发循环。

### 5.2 固定 WebRTC 传输

外部客户端只支持 Chrome Stable，因此媒体传输固定使用 WebRTC，不再保留 noVNC 或 WebSocket 全画面传输的备用实现。

传输方式：

1. Chrome 请求当前 Profile 的控制会话。
2. API 校验身份、Profile 绑定和控制租约。
3. API 签发短期信令票据。
4. Chrome 通过 `/stream/{sessionId}/signal` 建立 WebRTC 信令连接。
5. 信令网关将连接路由到对应 Runtime Agent。
6. 双方优先建立直接 ICE 媒体连接。
7. 直连失败时使用 coturn 的 TURN 中继。
8. 媒体使用 WebRTC 的 DTLS-SRTP 加密传输。

每个运行时分配独立 UDP 媒体端口，端口池固定为 `30000–30999`，每个运行时占用一个端口。Runtime Supervisor 负责分配、发布和回收端口。Selkies 适配层必须将实际监听端口与 ICE 广告端口配置为一致。

TURN 固定使用：

- UDP/TCP 3478。
- TLS/TCP 5349。
- UDP/TCP 中继端口范围 50000–59999。

Caddy 负责 HTTPS、API 和信令。它不代理实际视频帧。

### 5.3 画质和性能

固定运行参数：

- 默认逻辑屏幕分辨率：1920×1080。
- 默认 DPR：1。
- 活跃会话目标帧率：60 FPS。
- 编码器优先使用可用的硬件编码。
- 无可用硬件编码时使用软件编码。
- 静止画面保持高质量文字显示。
- 不将低分辨率画面强制拉伸成高分辨率。
- 外部窗口大小变化不自动改变 Profile 的指纹屏幕参数。

硬件加速按两条链路分别处理：浏览器自身的图形渲染，以及 Selkies 的视频编码。启用视频硬件编码不意味着浏览器自身已经启用 GPU 渲染，也不意味着浏览器不会暴露 GPU 指纹。

### 5.4 后台外部标签页

每个外部 Chrome 标签页只拥有自己的一个画面渲染器和一个媒体会话。

当该标签页进入后台：

1. 前端发送暂停画面的控制事件。
2. Runtime Agent 暂停该会话的连续画面捕获和编码。
3. Chrome 停止解码和绘制新帧。
4. 保留最后一帧画面、控制会话和远程浏览器进程。

当标签页重新进入前台：

1. 恢复媒体捕获。
2. 获取新画面或关键帧。
3. 先显示缓存画面，再恢复实时画面。
4. 重新确认当前控制租约后开放输入。

暂停媒体不会暂停远程网页的 JavaScript，也不会关闭浏览器。

多个外部 Chrome 窗口可以同时运行多个可见媒体会话。后台降帧和暂停按各自外部标签页的 `visibilityState` 执行，不设置全局的“只能有一个浏览器运行”。

---

## 6. 会话管理和生命周期

### 6.1 API 路由

固定使用以下路由：

| 路由 | 作用 |
|---|---|
| `/manage` | 配置管理页面 |
| `/open` | 选择一个浏览器并绑定当前外部标签页 |
| `/browser/{profileId}` | 操控指定的远程浏览器 |
| `/api/v1/profiles` | Profile 列表和创建 |
| `/api/v1/profiles/{id}` | Profile 读取、更新和删除 |
| `/api/v1/profiles/{id}/runtime/start` | 启动浏览器运行时 |
| `/api/v1/profiles/{id}/runtime/stop` | 停止浏览器运行时 |
| `/api/v1/profiles/{id}/runtime/restart` | 重启浏览器运行时 |
| `/api/v1/sessions` | 创建控制会话 |
| `/api/v1/sessions/{id}/heartbeat` | 更新控制租约 |
| `/api/v1/sessions/{id}/stream-ticket` | 签发一次性流媒体票据 |
| `/api/v1/profiles/{id}/files` | 文件列表、上传和下载 |
| `/api/v1/profiles/{id}/automation/cdp` | 授权的自动化连接 |
| `/api/v1/health/live` | 服务存活检查 |
| `/api/v1/health/ready` | 服务就绪检查 |

管理页面点击“在新标签页打开”时，使用普通的 `<a target="_blank" rel="noopener">` 链接打开 `/browser/{profileId}`。这样由 Chrome 原生创建标签页，不需要自建标签栏，也不依赖异步 `window.open` 避免弹窗拦截。

### 6.2 控制租约

每个 Profile 同一时刻只能有一个可写控制会话。

固定规则：

- 客户端每 5 秒发送一次心跳。
- 15 秒没有有效心跳时，将会话标记为断开。
- 断开后保留 30 秒重连窗口。
- 重连窗口内原会话恢复原有租约。
- 超过重连窗口后释放租约。
- 第二个标签页尝试控制同一 Profile 时，显示“该浏览器正在被其他标签页控制”。
- 用户必须明确执行接管，旧租约被撤销后新租约才能生效。

关闭外部 Chrome 标签页只释放控制租约，不停止浏览器容器。

### 6.3 运行状态机

每个 Profile 具有两个独立状态：

- `desired_state`：用户期望 `running` 或 `stopped`。
- `observed_state`：实际 `created`、`starting`、`running`、`stopping`、`stopped` 或 `failed`。

合法的启动流程：

```text
stopped → starting → running
                    ↘ failed

running → stopping → stopped
```

浏览器配置更新不直接修改运行时。启动、停止、重启都由 Runtime Coordinator 发起，并由 Supervisor 执行。

所有操作具有幂等操作 ID。同一 Profile 同一时刻只允许一个生命周期操作。运行状态不能只存放在 Python 进程内存中。

### 6.4 服务重启与浏览器恢复

Control API 重启时，不停止浏览器容器。

Runtime Supervisor 重启时，根据 Docker 容器标签和持久化的 `desired_state` 重新建立运行时状态。

Docker 主机重启后，Supervisor 重新启动期望处于运行状态的 Profile。

如果浏览器进程自身退出，Runtime Agent 上报实际状态。用户主动关闭浏览器后，系统将 Profile 标记为已停止，不会因为 Docker 的容器重启策略而无限重新启动浏览器。

---

## 7. 后端代码结构

现有 `backend/main.py` 和 `backend/browser_manager.py` 不再承担全部业务职责。

最终结构固定为：

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
│   │       ├── sessions.py
│   │       ├── artifacts.py
│   │       ├── settings.py
│   │       └── automation.py
│   │
│   ├── domain/
│   │   ├── profile.py
│   │   ├── runtime.py
│   │   ├── session.py
│   │   ├── artifact.py
│   │   ├── fingerprint.py
│   │   └── errors.py
│   │
│   ├── services/
│   │   ├── profile_service.py
│   │   ├── runtime_coordinator.py
│   │   ├── session_service.py
│   │   ├── license_service.py
│   │   ├── engine_artifact_service.py
│   │   ├── clipboard_service.py
│   │   ├── artifact_service.py
│   │   ├── download_service.py
│   │   └── automation_service.py
│   │
│   ├── adapters/
│   │   ├── database/
│   │   ├── docker/
│   │   ├── cloakbrowser/
│   │   ├── selkies/
│   │   └── filesystem/
│   │
│   ├── supervisor/
│   │   ├── app.py
│   │   ├── container_factory.py
│   │   ├── runtime_registry.py
│   │   └── port_allocator.py
│   │
│   └── runtime_agent/
│       ├── app.py
│       ├── browser_process.py
│       ├── display_manager.py
│       ├── stream_manager.py
│       ├── download_watcher.py
│       └── health.py
│
├── migrations/
└── tests/
```

### 模块边界

**API 层**

只负责 HTTP 请求、鉴权依赖、Pydantic 参数校验和响应。API 路由不直接访问 SQLite，不直接启动浏览器，也不直接操作 Docker。

**Domain 层**

定义 Profile、Runtime、Session、Artifact 和配置版本的业务规则。Domain 不依赖 FastAPI、Docker SDK 或浏览器进程。

**Services 层**

负责 Profile 创建、配置更新、运行时协调、会话租约、文件管理和授权业务。

**Adapters 层**

负责具体的 SQLite、Docker、CloakBrowser、Selkies 和文件系统集成。

**Supervisor**

是唯一拥有 Docker Socket 的服务，只接受固定的启动、停止、重启、检查和端口分配操作。它不能接受客户端任意传入的容器命令。

**Runtime Agent**

在单个 Profile 容器中启动和监控 CloakBrowser，管理 Xvfb、窗口定位、Selkies、下载捕获和文件交换。

这套结构不使用大量分布式服务，也不把 Docker 操作散落在业务代码中。

---

## 8. 数据库和数据迁移

### 8.1 数据库决策

保留单机 SQLite，改为 SQLAlchemy 2 + Alembic。

配置：

- 开启 WAL。
- 设置 `busy_timeout`。
- 所有写入使用事务。
- 使用外键和唯一约束。
- 通过 Alembic 执行版本化迁移。
- 不再通过手写 `DROP TABLE`、复制旧表和重建表来管理常规 schema 变更。

当前数据库的 Profile、Tag、Artifact 业务数据继续保留。新数据库结构增加运行时、会话和配置版本表。

### 8.2 新增数据表

| 表 | 用途 |
|---|---|
| `profiles` | Profile 基础信息、名称、标签和当前配置版本 |
| `profile_config_versions` | 不可变的指纹和运行配置快照 |
| `profile_tags` | 标签和颜色 |
| `profile_runtimes` | 容器 ID、期望状态、实际状态、错误和健康信息 |
| `control_sessions` | 外部 Chrome 标签页控制会话 |
| `control_leases` | 每个 Profile 的独占控制租约 |
| `artifacts` | 上传和下载文件元数据 |
| `settings` | 非秘密全局配置 |
| `audit_events` | 生命周期、配置和接管操作审计记录 |

代理密码和许可证密钥使用加密存储或受保护的密钥文件，不以明文写入 SQLite。

### 8.3 迁移旧数据

迁移必须保留现有的 `~/.cbrowser` 数据目录。

执行流程：

1. 停止旧版 Manager 和所有旧浏览器进程。
2. 完整备份当前 `/data` 目录，包括 SQLite、`profiles/`、`artifacts/` 和 `settings.json`。
3. 使用一次性迁移工具读取旧 `profiles.db`。
4. 保留所有 Profile UUID、名称、标签、排序、配置、备注和时间戳。
5. 保留现有浏览器用户数据目录，不重新生成 Cookie、网站存储或内部标签页状态。
6. 将旧表转换成新 schema，生成初始 `profile_config_versions`。
7. 保留所有 Artifact 元数据和实际文件。
8. 校验迁移前后 Profile、Tag、Artifact 的数量和文件校验和。
9. 校验通过后再启动新版本。
10. 迁移失败时恢复旧数据库和原始数据目录，旧版镜像仍可启动。

迁移工具必须支持 `--dry-run`。迁移不能在浏览器仍然写入用户数据时执行。

---

## 9. 前端代码重构

### 9.1 路由结构

前端采用以下路由：

```text
/manage
/manage/profiles/new
/manage/profiles/:profileId
/manage/profiles/:profileId/files
/manage/settings
/open
/browser/:profileId
/login
```

`/manage` 是配置管理界面。`/open` 是当前外部 Chrome 标签页的浏览器选择页。`/browser/:profileId` 是只显示一个远程浏览器窗口的操控页面。

外部 Chrome 标签页本身就是外层标签，不再由 React 实现外层标签栏。

### 9.2 前端目录

```text
frontend/src/
├── app/
│   ├── router.tsx
│   ├── providers.tsx
│   └── auth.ts
│
├── routes/
│   ├── ManageRoute.tsx
│   ├── BrowserPickerRoute.tsx
│   └── BrowserSessionRoute.tsx
│
├── features/
│   ├── profiles/
│   │   ├── ProfileList.tsx
│   │   ├── ProfileEditor.tsx
│   │   ├── ProfileIdentitySection.tsx
│   │   ├── ProfileNetworkSection.tsx
│   │   ├── ProfileFingerprintSection.tsx
│   │   ├── ProfileAdvancedSection.tsx
│   │   └── profileQueries.ts
│   │
│   ├── browser-session/
│   │   ├── BrowserSessionPage.tsx
│   │   ├── WebRTCClient.ts
│   │   ├── InputProxy.ts
│   │   ├── ClipboardBridge.ts
│   │   └── sessionQueries.ts
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

### 9.3 对现有前端文件的处理

- `App.tsx`：拆成 Router、应用 Provider 和各路由页面。
- `ProfileViewer.tsx`：替换为 `BrowserSessionPage.tsx`，删除 noVNC RFB 客户端和叠加在浏览器画面上的工具栏。
- `useProfiles.ts`：替换为 TanStack Query 的查询和 mutation hooks，删除每 3 秒重新拉取全部 Profile 的轮询。
- `api.ts`：改为 OpenAPI 生成类型与统一 API client。
- `ProfileForm.tsx`：拆分成身份、网络、指纹、浏览器行为和高级设置子组件。
- `ProfileFiles.tsx`：保留文件管理能力，迁移到独立的 Profile 文件管理页面。
- `CdpEndpointButton.tsx`：保留自动化能力，但只在授权的自动化页面中显示。
- `NativeWindowStatus.tsx`：删除。
- `LanguageToggle.tsx` 和中英文资源：保留。
- `frontend/package.json`：移除 `@novnc/novnc`，添加路由、查询缓存和 WebRTC 客户端依赖。

前端不再自行维护一份与后端不一致的 Profile 类型。生产构建前生成 API 类型，并运行 TypeScript 检查。

---

## 10. 输入法、快捷键与剪贴板

### 10.1 中文输入法

在浏览器操控页面实现独立的 `InputProxy`。

输入代理使用透明 `textarea` 接收 macOS 中文输入法的组合事件：

- `compositionstart`
- `compositionupdate`
- `compositionend`

组合期间不向远程浏览器转发拼音原始按键。组合结束后，提交完整 Unicode 文本，通过对应会话的文本注入通道发送给远程浏览器。

文本注入通过远程剪贴板和粘贴事件完成，保证地址栏和网页输入框都可以接收文本。代理根据远程鼠标位置更新本地输入法代理的位置，让候选框尽可能接近远程输入位置。

本地输入法候选框不能保证在所有网页和浏览器原生控件中与远程插入光标完全重合。系统不依赖实验性的 EditContext API。

### 10.2 快捷键

外部 Chrome 的系统快捷键和远程浏览器快捷键分开定义。

macOS 外部 Chrome 保留 `Cmd+T`、`Cmd+W`、`Cmd+L`、`Cmd+R`。这些操作不能被普通网页可靠地完全拦截。

远程浏览器提供明确的 `Ctrl` 快捷键映射：

- `Ctrl+T`：远程浏览器新建标签页。
- `Ctrl+W`：关闭远程浏览器当前标签页。
- `Ctrl+L`：聚焦远程浏览器地址栏。
- `Ctrl+R`：刷新远程页面。

映射在远程操控区域获得焦点时生效。所有事件绑定当前会话 ID 和租约代次，旧会话不能接收新输入。

### 10.3 剪贴板

Selkies 负责基本双向剪贴板传输，CBrowser 额外实现按会话隔离的 Clipboard Broker。

规则：

- 本机粘贴只读取用户明确触发的粘贴内容。
- 远程复制只写入当前可写控制会话对应的剪贴板。
- 后台 Chrome 标签页不能覆盖本机剪贴板。
- 文本、HTML 和图片通过明确的 MIME 类型传输。
- 使用事件序号和来源标记防止双向同步循环。
- 大文件使用独立文件传输，不进入剪贴板通道。
- 任何日志都不能记录剪贴板正文、Cookie、密码或代理凭证。

Chrome 的剪贴板 API 仍受安全上下文、权限和用户激活约束。写入被拒绝时，前端显示“点击写入本机剪贴板”，不假装操作成功。

---

## 11. 文件、下载和 CDP 自动化

### 11.1 文件管理

保留当前仓库的 Profile 文件功能，包括上传、下载、删除、配额和文件选择器入口。

`Artifact Service` 负责元数据、配额、文件名和磁盘空间管理。Runtime Agent 负责将上传文件提供给浏览器，并捕获浏览器下载。

文件上传和下载使用流式 HTTP 传输，不将大文件读入内存。

每个运行容器只挂载自己的 `exchange/` 目录。文件选择器需要的 GTK 书签由对应 Runtime Agent 在该容器内生成，而不是由管理容器修改浏览器容器之外的 GTK 配置。

浏览器下载捕获继续通过 CDP 下载事件实现。文件先写入临时文件，下载完成并校验后再原子发布到 Artifact Store。

### 11.2 CDP 自动化

保留 Playwright/Puppeteer 自动化能力。

CDP 只监听运行时容器内部的回环地址。外部客户端不能直接访问容器的调试端口。

自动化连接通过独立授权接口创建短期连接票据。API 校验 Profile 权限、票据范围和过期时间后，才允许建立 CDP WebSocket 代理。

自动化客户端不能直接控制 Runtime Supervisor，也不能访问其他 Profile 的 CDP 端点。

---

## 12. 鉴权、网络与安全

当前 `docker-compose.yml` 将 `56661:8080` 绑定到 `0.0.0.0`，同时 `AUTH_TOKEN` 可以为空。新架构不保留这种默认部署方式。

### 12.1 鉴权规则

- 所有管理页面、控制 API 和浏览器会话都要求登录。
- 使用 Argon2id 存储登录密码的哈希。
- 使用随机服务端会话和 `HttpOnly`、`Secure`、`SameSite=Strict` Cookie。
- 状态变更请求验证 CSRF Token 和 Origin。
- 仅对受信任的反向代理接受 `X-Forwarded-*`。
- 自动化使用独立 API Token，按 Profile 和权限范围授权。
- 浏览器会话票据短期有效且只能使用一次。
- `/api/v1/health/live` 只返回服务存活信息，不暴露 Profile 数量、版本或运行状态。

### 12.2 容器安全边界

Runtime Supervisor 是唯一挂载 Docker Socket 的服务。其 RPC 接口只允许创建、启动、停止、重启和检查由 CBrowser 管理的固定运行时。

浏览器运行容器：

- 不挂载 Docker Socket。
- 不挂载其他 Profile 的目录。
- 不使用 `privileged: true`。
- 不使用宿主机网络。
- 不公开 HTTP、CDP 或内部管理端口。
- 仅开放当前会话所需的 UDP 媒体端口。
- 使用自己的配置目录和代理设置。

### 12.3 日志与审计

所有服务输出结构化 JSON 日志，包含时间、服务名、Profile ID、操作 ID、Trace ID 和错误码。

日志不包含 Cookie、登录密码、许可证密钥、代理密码、剪贴板正文和网页表单内容。

保留 Profile 创建、修改、启动、停止、重启、复制、删除和控制权接管的审计事件。

---

## 13. Docker 部署结构

Docker Compose 固定部署以下常驻服务：

```text
caddy
cbrowser-api
cbrowser-supervisor
coturn
```

`browser-runtime` 不是常驻的单个 Compose 服务实例，而是由 Supervisor 按 Profile 动态创建的容器。每个运行时使用同一份经过锁定的运行时镜像。

前端静态文件由 Caddy 提供，API 由 FastAPI 提供。Supervisor 只连接内部控制网络，不暴露公网端口。

### 对现有 Docker 文件的改造

- `Dockerfile` 拆成控制 API、Supervisor 和 Browser Runtime 三个镜像构建文件。
- `docker-compose.yml` 改为 `compose.yaml`，定义常驻服务、网络、持久化目录和健康检查。
- `entrypoint.sh` 拆成各镜像自己的启动入口。
- 删除旧容器启动时全局清理 Xvnc 进程的逻辑。
- 只通过 Caddy 暴露 HTTPS 管理入口。
- 浏览器运行时的 HTTP、WebSocket 信令和 CDP 端点全部处于内部网络。
- 生产部署必须配置 HTTPS 和初始管理员凭证。
- 镜像构建支持 Linux amd64 和 arm64。
- Docker 基础镜像使用固定发行版、精确版本和镜像摘要。
- Python 使用 `uv.lock` 锁定依赖，前端使用 `package-lock.json` 和 `npm ci`。
- 不在生产构建中使用浮动的 `latest` 镜像标签。

当前 Mac 上的 OrbStack 可以继续用于本地 Docker 开发和功能验证。硬件编码能力以实际 Docker 主机可用的设备为准；性能基准测试使用配置明确的 Linux Docker 环境。

---

## 14. 现有仓库文件的明确处理方式

| 现有文件或目录 | 最终处理 |
|---|---|
| `backend/main.py` | 拆分成 API 路由、服务和适配器；删除 RFB 转换和 VNC 代理 |
| `backend/browser_manager.py` | 将 Profile 业务、引擎管理、运行时生命周期和下载捕获拆分 |
| `backend/database.py` | 替换为 SQLAlchemy 2、Alembic 和 Repository 层 |
| `backend/vnc_manager.py` | 删除 |
| `backend/artifacts.py` | 保留配额、路径校验和原子文件写入，重构为 Artifact Service |
| `backend/downloads.py` | 将下载事件监听迁移到 Runtime Agent，元数据归档保留在控制服务 |
| `backend/runtime.py` | 删除 native-window 和多平台运行模式，改为 Docker 配置 |
| `backend/models.py` | 拆分为 Domain Model、API Schema 和运行时协议模型 |
| `backend/tests/test_rfb.py` | 删除 RFB 测试，替换为 WebRTC 会话与输入协议测试 |
| `backend/tests/test_vnc_manager.py` | 删除，替换为 Runtime Supervisor 和容器生命周期测试 |
| `backend/tests/test_browser_manager.py` | 拆分为 Profile Service、Runtime Agent 和引擎适配测试 |
| `frontend/src/App.tsx` | 改为 Router 和应用 Provider |
| `frontend/src/components/ProfileViewer.tsx` | 重写为独立的 WebRTC 浏览器操控页面 |
| `frontend/src/components/ProfileForm.tsx` | 拆分为多个配置区块 |
| `frontend/src/lib/api.ts` | 替换为 OpenAPI 生成类型和统一 API client |
| `frontend/src/hooks/useProfiles.ts` | 替换为 TanStack Query hooks 和事件驱动的运行状态更新 |
| `frontend/src/components/NativeWindowStatus.tsx` | 删除 |
| `frontend/src/components/CdpEndpointButton.tsx` | 保留功能，迁移到自动化管理模块 |
| `frontend/src/components/ProfileFiles.tsx` | 保留功能，迁移到独立文件管理模块 |
| `frontend/src/i18n.tsx` | 保留中英文功能，按模块整理文案 |
| `Dockerfile` | 拆成三个独立镜像构建文件 |
| `docker-compose.yml` | 重构为新服务拓扑 |
| `entrypoint.sh` | 删除旧版单容器启动和 Xvnc 清理逻辑 |
| `app_entry.py` | 删除原生冻结应用入口 |
| `run-macos.sh`、`run-windows.bat` | 删除原生应用启动路径 |
| `packaging/` | 删除原生安装包构建逻辑 |
| `.github/workflows/ci.yml` | 改成 Linux Docker、前后端测试和集成测试流水线 |
| `.github/workflows/release.yml` | 改成多架构容器镜像构建和发布 |
| `README.md` | 重写成 Docker + Chrome 的唯一部署说明 |
| `DOCKER_DEPLOYMENT.md` | 重写成新架构、网络端口、迁移、备份和恢复手册 |
| `BINARY-LICENSE.md` | 保留并继续维护 CloakBrowser 二进制许可说明 |

---

## 15. 上游同步策略

当前 README 将 CBrowser 定义为 CloakBrowser Manager 的社区分支。完成这次重构后，不再直接合并上游 Manager 的 UI 和运行时实现，因为它们与新的 Profile 容器架构存在根本差异。

上游同步固定为三层：

1. **CloakBrowser 引擎：** 通过官方 Python 包和许可证接口接入，版本升级必须经过引擎适配测试。
2. **Selkies：** 固定官方发布提交，只通过明确的版本升级 PR 更新。
3. **CBrowser 自有业务：** Profile、配置、会话、文件和 UI 由本仓库维护，不复制上游 Manager 的业务实现。

新增 `docs/upstream-sync.md`，记录上游版本、升级原因、API 变化、许可变化和验证结果。上游同步不能直接覆盖本仓库的运行时适配层。

---

## 16. 测试与验收标准

所有功能测试的外部客户端固定为 macOS 或 Linux 上的 Google Chrome Stable。浏览器运行时使用 Linux Docker 容器。

### 16.1 外部与内部标签页

1. 从管理页面打开 10 个不同的 Profile，生成 10 个外部 Chrome 标签页。
2. 每个标签页只能操作绑定的 Profile。
3. 在 Profile A 内创建、关闭和切换内部标签页，不影响 Profile B。
4. 在外部 Chrome 中切换标签页时，恢复的是对应远程浏览器的画面。
5. 关闭外部标签页后，远程浏览器进程继续运行。
6. 刷新外部标签页后恢复原控制会话。
7. 两个外部标签页同时申请同一 Profile 的控制权时，第二个请求被拒绝，除非明确执行接管。
8. 外部标签页不存在由 CBrowser 实现的虚拟外层标签栏。

### 16.2 浏览器隔离

1. Profile A 与 Profile B 使用不同的浏览器用户数据目录。
2. A 中设置的 Cookie、Local Storage、IndexedDB、网站登录态和内部标签页状态不能出现在 B 中。
3. A 的代理配置修改不影响 B。
4. A 的浏览器容器不能访问 B 的用户数据目录。
5. 浏览器容器不能访问 Docker Socket 或其他 Profile 的 X11 显示。
6. 浏览器容器不暴露 CDP 调试端口。

### 16.3 媒体性能

固定基准环境：1920×1080、DPR 1、局域网 RTT 不超过 10 ms、丢包率不超过 0.1%。

| 指标 | 验收目标 |
|---|---|
| 活跃画面帧率 | 目标 60 FPS |
| 运行时已就绪后的首次画面 | P95 不超过 1000 ms |
| 输入到画面反馈延迟 | P95 不超过 100 ms |
| 外部标签页重新进入前台后的实时画面恢复 | P95 不超过 300 ms |
| 停止滚动后的静态清晰度修正 | P95 不超过 250 ms |
| WebRTC 直连失败时的 TURN 回退 | 5 秒内进入中继连接流程 |
| 10 个运行时的长时间稳定性 | 连续 8 小时无意外退出、数据损坏或会话串线 |

这些是测试门槛，不是对任意网络、主机和网站的无条件性能保证。

### 16.4 输入与剪贴板

1. 完成 1000 次中文组合输入测试，不能出现丢字、重复字或残留拼音。
2. 完成 1000 次纯文本剪贴板测试，校验 Unicode 内容逐字节一致。
3. 完成 HTML 和图片剪贴板测试。
4. 浏览器标签页隐藏时，不能覆盖本机剪贴板。
5. 浏览器地址栏和网页输入框都必须支持完整中文文本提交。
6. 剪贴板 API 被拒绝时必须显示明确的手动恢复操作。
7. 日志和审计记录中不得出现剪贴板正文。

### 16.5 生命周期和故障恢复

1. 关闭 Control API 后，浏览器容器继续运行。
2. 重启 Supervisor 后，现存容器状态重新被识别。
3. Docker 主机重启后，`desired_state=running` 的 Profile 恢复。
4. 浏览器进程崩溃后，系统显示实际失败状态，不伪造运行中状态。
5. 浏览器关闭后，Profile 的用户数据目录仍然完整。
6. 运行时重连不重复创建浏览器进程。
7. 两个生命周期操作同时发生时，只有一个操作获得该 Profile 的执行权。

### 16.6 代码质量

CI 固定运行：

- Ruff：Python 格式和静态检查。
- Mypy：Domain、Services 和协议层严格类型检查。
- Pytest：后端单元测试和集成测试。
- ESLint、Prettier 和 TypeScript 类型检查。
- Vitest：前端单元测试。
- Playwright：Chrome 端到端测试。
- Docker Compose 集成测试：启动容器、创建 Profile、打开浏览器、重连和关闭。
- 容器镜像安全扫描和第三方依赖许可审计。

Domain 和 Services 层覆盖率目标不低于 90%。所有核心会话状态转换、鉴权、数据迁移和文件隔离路径必须有专门测试。

---

## 17. 实施顺序

### 阶段一：建立新架构骨架

建立 Domain Model、SQLAlchemy/Alembic、API 路由和服务层。锁定所有依赖。先实现旧数据库读取和迁移工具，不修改原有用户数据。

### 阶段二：实现浏览器运行时

创建独立 Browser Runtime 镜像，实现 CloakBrowser 启动、Xvfb、Openbox、Runtime Agent 和健康检查。先验证单个 Profile 的完整窗口和持久化。

### 阶段三：接入 Selkies

集成 Selkies 2.1.0，配置 WebRTC、ICE 和 TURN。完成媒体端口分配、信令授权、输入事件和后台暂停恢复。删除旧 RFB 兼容代码。

### 阶段四：实现 Supervisor 和会话租约

实现容器生命周期、幂等操作、独占租约、重连窗口和运行状态恢复。确认 Control API 不持有 Docker Socket。

### 阶段五：实现外部 Chrome 标签页工作流

完成 `/manage`、`/open` 和 `/browser/{profileId}`。从管理页面打开新 Chrome 标签页，验证一对一会话绑定和真实的浏览器内部标签页。

### 阶段六：重构输入、剪贴板和文件管理

实现中文输入代理、双向剪贴板、下载捕获、文件交换和自动化 CDP 授权。

### 阶段七：安全与部署

完成强制鉴权、TLS、TURN 凭证、运行时权限、依赖锁定和容器镜像扫描。

### 阶段八：数据迁移和正式验收

对现有 `/data` 执行备份和 dry-run 迁移。验证 Profile、Cookie、文件、标签和配置完整后，启动新版本并运行完整验收测试。

---

## 18. 最终完成条件

只有同时满足以下条件，才允许将新版本标记为正式版本：

- 所有现有 Profile 数据和文件都完成迁移。
- 外部 Chrome 标签页与隐私浏览器实现严格的一对一绑定。
- 内部浏览器标签页由真实 CloakBrowser UI 管理。
- 旧 noVNC/RFB 兼容层全部删除。
- 浏览器容器和管理服务完成职责分离。
- Control API 不持有 Docker Socket。
- 浏览器在外部标签页关闭、刷新和 Control API 重启后保持正确状态。
- 剪贴板、中文输入和文件交换通过自动化测试。
- 认证、会话授权和 CDP 权限检查通过安全测试。
- 所有 CI、容器构建、迁移和恢复测试通过。
- README、Docker 部署手册、备份恢复手册和上游同步说明全部更新。

**最终结论：** CBrowser v2 是一个由 FastAPI 控制服务、独立 Runtime Supervisor、每个 Profile 一个浏览器运行容器、Selkies WebRTC 和 Chrome 外部标签页组成的单机 Docker 系统。它保留 CloakBrowser 的核心能力，删除旧的 VNC/RFB 兼容负担，以独立容器和显式会话租约保证浏览器隔离和控制正确性，并以明确的模块边界、版本化配置、数据库迁移和自动化测试控制长期技术债。