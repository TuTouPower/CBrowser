# CBrowser 全仓架构与实现认知汇总报告 (Repository Summary)

## 1. 目标、范围、约束与未知前提

### 1.1 核心目标

CBrowser 是面向隐私浏览器与多身份隔离的单机 Docker 容器化管理系统。系统以 Google Chrome 作为唯一官方支持的外部客户端，采用 Selkies WebRTC 传输低延迟远程画面（基于同机直连，完全去除 TURN/coturn），由独立 Docker 容器沙箱实现严格的 Profile 隔离与页面连接管理。

### 1.2 审阅范围

本次审查覆盖全仓纳入 Git 跟踪的全部 1339 个文件，涵盖：

- 后端业务服务、API 路由、鉴权体系、数据模型与迁移 (`backend_core`，38 文件)
- Docker 容器沙箱编排、UDS 守护代理、执行器与生命周期 (`backend_runtime_supervisor`，52 文件)
- WebRTC 信令网关、Stream 代理、网络与 UDP 多路复用 (`backend_stream_gateway`，26 文件)
- 前端核心基础设施、路由、全局状态、通信网关与基础组件 (`frontend_core_shared`，73 文件)
- 前端会话播放、Profile 配置管理、代理与自动化配置模块 (`frontend_features`，92 文件)
- 跨服务 OpenAPI / JSON Schema 契约、编排与发布运维脚本 (`contracts_deploy_infra`，55 文件)
- 单元测试套件与测试夹具 (`tests_unit_fixtures`，201 文件)
- 跨服务集成与端到端系统测试套件 (`tests_integration_e2e`，89 文件)
- 系统长期蓝图、需求规约说明书、设计规范与活动文档 (`specs_blueprint_docs`，88 文件)
- 模板工具链脚本、门禁与 CLI 任务扩展 (`repo_template_toolchain`，120 文件)
- 历史归档任务、过往调研 Spike 与已闭环评审记录 (`historical_archives_reviews`，504 文件)

### 1.3 核心架构约束与铁律

1. **架构至上**：始终选择最优雅彻底的顶层设计，忽略开发难度，拒绝临时补丁，零兼容负担。
2. **单一数据库写入者**：FastAPI 后端服务（`backend_core`）为系统唯一的 SQLite 数据库写入者；Supervisor 严禁挂载或操作数据库。
3. **单一 Docker Socket 持有者**：Supervisor 为系统内唯一持有并操作 Docker Socket 的组件；API 与前端严禁直接接触 Docker。
4. **沙箱容器零特权与环境隔离**：运行容器采用非 root (UID 1000)、只读根文件系统、`cap_drop: [ALL]`、`no-new-privileges`；iptables 规则由独立的不可变 helper 容器注入网络命名空间。
5. **同机直连与零外部媒体中继**：完全去除 TURN/coturn，WebRTC 仅允许 127.0.0.1 或受信局域网直连。
6. **真人优先控制权**：单调递增 generation 围栏，人工操作具备最高优先级，支持安全接管与降级。

______________________________________________________________________

## 2. 组件职责、依赖、主要数据流与信任边界

### 2.1 组件拓扑与职责划分

```
                [ 外部客户端 (Google Chrome / 自动化 Agent) ]
                                      │
                     HTTPS: 56661 (Caddy Gateway)
                                      ├── /api/* ──> [ API Core (FastAPI / SQLite) ]
                                      │                     │ (Internal RPC)
                                      │                     ▼
                                      ├── /stream/* ─> [ Stream Gateway (aiohttp) ]
                                      │                     ▲ (WebSocket 信令)
                                      │                     │
                    Docker 隔离沙箱    │         [ Supervisor (FastAPI / Docker SDK) ]
                  ┌───────────────────┴───────────┐         │ (Docker API)
                  │                               │         ▼
         [ Browser Container ] ── IPC ──> [ Stream Container ] (Selkies WebRTC)
         (Chrome + CloakBrowser)         (X11 抓屏 + GStreamer)
                  ▲
                  │ UDS (/run/.../agent.sock)
         [ Runtime Agent Daemon ]
```

### 2.2 核心控制流与数据流

1. **Profile 启动与收敛流**：
    - 客户端请求 `PATCH /api/v1/profiles/{id}/desired-state` (state="running")；
    - API 校验配置并持久化新不可变版本至 SQLite (`BEGIN IMMEDIATE` 事务)；
    - `RuntimeCoordinator` 触发对账，向 Supervisor 发起 HTTP POST `/supervisor/v1/profiles/start`；
    - Supervisor 分配 UDP 媒体端口，创建桥接媒体网络，先后拉起 Browser 容器与 Stream 容器；
    - Browser 容器通过 `startup_gate` 等待 helper 注入 iptables 规则后拉起业务进程；
    - Stream Agent 启动后向 Stream Gateway 注册存活，Supervisor 回传 observed 状态给 API；
    - API 写入审计记录并通过 SSE 端点 `/api/v1/events` 向前端全量广播。
2. **WebRTC 画质信令与会话流**：
    - 前端挂载 Selkies iframe 并经 `adapter.ts` 拦截 WebSocket 连接至 `/stream/{id}/signal`；
    - Gateway 校验会话 Cookie，调用 API `/api/v1/internal/gateway/viewer-authorize` 校验授权；
    - Gateway 与 Stream Agent 建立隧道桥接，向本地 Selkies 进程 (18081) 注入 Controller Token；
    - 浏览器与 Selkies 协商 SDP/ICE，建立同机直连 WebRTC PeerConnection；
    - `LiveCapturePolicyAgent` 根据前台交互活动在 8 FPS 与 30 FPS 间动态仲裁，静止/后台时挂起抓屏。
3. **自动化 CDP 隧道与受控流**：
    - 外部 Agent 携带 Bearer Token 请求 `/api/v1/automation/profiles/{id}/cdp`；
    - API 校验 Token 权限与真人接管 generation 围栏，通过 WebSocket 转发至 Supervisor；
    - Supervisor 将请求路由至挂载的短路径 UDS `/run/.../agent.sock` 并连接内部 `runtime_agent`；
    - `runtime_agent` 的 `TunnelFilter` 执行白名单审计，拦截破坏性指令（如 `Browser.close`），转发至 Chrome 回环 CDP。

### 2.3 信任边界

- **外部非信任边界**：HTTPS 56661 暴露在公网或局域网，请求必须经过 Caddy TLS 终止、严格同源校验与 Session Cookie / CSRF Token / Bearer Token 鉴权。
- **内部管理信任边界**：API 与 Supervisor、Gateway 之间通过预共享密钥（Bearer Token / HMAC）通信；通信限于 Docker 内部网桥。
- **沙箱隔离信任边界**：Browser 容器运行不可信第三方网页代码，受到严格命名空间、只读根文件系统、网络 iptables 阻断规则以及 UDS 白名单审计的层层隔离。

______________________________________________________________________

## 3. 数据与状态权威、重要契约与关键取舍

### 3.1 状态与数据权威

- **配置与生命周期意愿权威**：SQLite 数据库为单一权威（`desired_state`, `config_version`），由 API 独占写入。
- **运行态物理权威**：Docker Engine 与容器真实进程为物理真实态；Supervisor 负责将物理观测态（`observed_state`）向意愿态持续对账收敛。
- **控制权状态权威**：`profile_controls` 数据库记录为控制权权威，单调递增 `generation` 具有排他围栏效应。

### 3.2 重要跨服务契约

- **OpenAPI v1**：`schemas/openapi/cbrowser_v1.json`，统一生成前端 Typed Client，严禁前端手写重叠 DTO。
- **Supervisor RPC 契约**：`schemas/runtime/supervisor_protocol.json`，定义启停、状态、网络重构等通信协议。
- **Stream 信令信封契约**：`schemas/stream/agent_protocol.json`，定义网关与代理间 TunnelEnvelope 结构。

### 3.3 关键技术取舍 (Trade-offs)

- **舍弃 TURN / 外部中继，选择同机直连**：彻底消除了外部 TURN 部署复杂度与 ICE 代次穿透失败风险，保证极致低延迟画面。
- **双容器架构（Browser + Stream 分离）**：牺牲了一定容器调度复杂度，实现了渲染捕获进程与浏览器主进程的故障域解耦与权限分离。
- **严格不可变发布与配置**：任何网络模式调整与版本发布均采用全新版本覆盖与原子指针切换，确保环境可回退。

______________________________________________________________________

## 4. 局部 Findings 的系统级影响、跨包冲突与关键隐患

在第一阶段 11 个单元的深入审阅中，共发现 65 项确凿问题。跨单元交织出的系统级主要隐患如下：

1. **网络重构与局域网接入链路存在全链路断裂风险 (BC-01, BC-02, SG-03, INFRA-03)**：

    - `RuntimeCoordinator` 存在致命 `AttributeError`（缺失 `self.client` 属性与 `_auth_headers()` 方法）；
    - `NetworkRouter` 路由前缀缺失 `/api/v1`，导致前端与 Caddy 代理 404；
    - Gateway 在冷启动无 `applied_network_version.json` 时将白名单置空引发 403；
    - `deploy_v2.sh` 在重新部署时遗漏提取 `https_port` 导致用户自定义端口被重置。
        *四者交织，导致网络模式从本地切换为 LAN 时，API、Gateway 与部署运维脚本全链路报错。*

2. **沙箱容器清理故障与端口释放时序引发的端口串扰风险 (SUP-01, SUP-03)**：

    - Supervisor 在容器清理异常（`teardown_error`）时依然在 `finally` 块中调用 `ports.release()` 释放宿主 UDP 端口；
    - Stream 单容器局部替换失败时遗留孤儿容器并持续占用端口；
        *导致宿主机 UDP 端口被分配给新 Profile，引发跨 Profile 画面流串扰或 Docker 启动端口冲突。*

3. **反向代理 IP 解析穿透缺位导致的连带 DoS 风险 (BC-03, SG-01)**：

    - `control_router.py` 自动化鉴权与 `gateway/server.py` Viewer 限流均未正确调用 `resolve_client_ip`，直接提取 Caddy 代理 IP 进行限速与封禁；
        *外部攻击者向某个 Profile 发送恶意请求触发限流后，整个 Caddy 代理 IP 被拉黑，导致同一网关下的所有正常用户和 Agent 全体遭遇拒绝服务。*

4. **协议导出脚本与契约 Schema 存在严重漂移盲区 (INFRA-01, INFRA-02, TEST-02)**：

    - Supervisor 协议导出脚本遗漏了 8 个核心端点模型，Stream 协议导出脚本遗漏了 `AgentHumanInputTakeoverEnvelope`；
    - 单元测试使用硬编码白名单进行比对，导致协议缺失在门禁中被掩盖。

5. **前端内存泄漏与生命周期管理缺陷 (FE-01, FE-02, FE-03, FE-04)**：

    - `SettingsPage` 轮询计时器闭包泄漏且无卸载清理；
    - `useBrowserSession` 卸载时遗漏 `transportRecoveryTimerRef` 清理，`mountedRef` 逻辑失真；
    - 会话页与底层 Hook 存在状态机分流，导致已停止 Profile 依然在后台轮询 WebRTC 指标。

______________________________________________________________________

### 4.6 违反核心架构铁律的典型违背点专项总结

对照核心架构三铁律：

- **架构至上**：始终选择最优雅、彻底、纯粹的顶层设计，完全忽略开发难度与工作量。
- **拒绝妥协**：严禁使用临时补丁或局部修补来规避底层重构；发现设计缺陷必须从根因修正。
- **零兼容性负担**：直接执行破坏性变更，完全不需要考虑前后兼容。

本次审阅进一步深挖出以下 4 项直接违背铁律的关键位点：

1. **偷留旧路由兼容层并隐藏文档 (`f_backend_core_legacy_cdp_router`)**：
    `app.py:418` 偷偷挂载了 `legacy_cdp_router`（映射 `/api/profiles/{id}/cdp`），并通过 `include_in_schema=False` 刻意在 OpenAPI Schema 中隐瞒。这是典型的“背负历史兼容包袱”、“未彻底切断旧路径”的违背铁律行为。
2. **保留上游旧项目 localStorage 存储键迁移代码 (`f_frontend_legacy_cbm_locale_key`)**：
    `i18n.tsx:924` 依然保留了针对旧仓 `CloakHQ/CloakBrowser-Manager` 的 `cbm.locale` 历史存储键迁移逻辑与单元测试。CBrowser 是全新破坏性重构系统，无须承担上游历史兼容负担。
3. **运行时 AST 源码反射与猴子补丁 (`f_stream_agent_x11_keymap_monkeypatch`)**：
    `x11_keymap.py` 为了解决上游 Selkies 2.2.1 丢键问题，未选择定制 wheel 或向上游修复根因，而是在运行时通过 Python `ast` 模块反编译上游内部类 `__init__` 进行私有属性嗅探，并在内存中动态替换私有方法。属于严重违背“拒绝妥协”的打补丁行为。
4. **使用 /proc/self/fd 魔法路径规避 socket 长度限制 (`f_supervisor_sun_path_proc_fd_hack`)**：
    `path_validator.py` 为了绕过 `sockaddr_un.sun_path` 108 字节限制，采用 `O_PATH` 打开目录后拼接 `/proc/self/fd/{fd}/...` 魔法路径，而非从架构根因规范沙箱目录深度与命名空间。属于典型的临时规避修补。

## 5. 覆盖限制与证据回查入口

- **证据核对规范**：所有 Findings 均在各单元 `_meta/local_<uid>.json` 与根目录 `bundle_local_<uid>.md` 中提供了精确代码行号与可验证测试逻辑。
- **运行环境限制说明**：本审阅基于静态代码分析、历史执行回执与架构蓝图推导，未在真实硬件上拉起完整 Docker 容器集群执行端到端物理破坏注入（属于 static/suspected 验证）。

## Local uncertainty resolutions

```json
{}
```
