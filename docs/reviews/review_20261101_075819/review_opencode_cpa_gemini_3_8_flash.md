# CBrowser v2 (t001–t007) 累计改动全量独立审阅报告

- **审阅员模型**：cpa/gemini-3.8-flash (OpenCode)
- **Provider**：Google / CPA
- **思考强度**：effort=high
- **基线 Commit (Base Anchor)**：`3c8bdbc55570e85aaeb6365a3d512da9c0ce180c` (t001 实施前基线)
- **目标 Commit (Target Anchor)**：`78c95638c8ceb5d84c286994eee82146d7ddddd6` (t007 合入 main)
- **审阅范围**：t001 至 t007 全部累计修改及跨组件交互（整段合审，无子代理派发，静态独立审阅）
- **阶段边界与豁免说明**：
    - **已交付范围 (t001–t007)**：底层技术验证与 Spike 探索（s001–s010）、v2 新后端骨架与持久化（SQLite 单写者/Alembic/WAL）、Browser Runtime 沙箱与 UDS Agent、Stream Runtime（Selkies 2.1.0/WebRTC/PulseAudio/自适应帧率仲裁）、Supervisor 容器生命周期与网络策略隔离门禁、Stream Gateway 动态信令路由与 HMAC-SHA1 凭证轮换、API 经 Runtime Coordinator 驱动 Supervisor 启停、前端 React Router 7 会话与 WebRTC 播放器。
    - **未实施范围 (t008–t014)**：正式 Artifact / CDP 自动化全链（t008）、整机容量与 8 小时稳定性压力验收（t009）、旧生产数据迁移（t010）、彻底移除旧 VNC/RFB/原生桌面链路（t011）、Docker Compose 最终交付（t012）、Profile 复制与重置（t013）、系统剪贴板与中文输入全量验收（t014）。以上未来能力未实现不作为当前阶段缺陷。
    - **用户环境验证豁免 (Scope Waivers)**：公网候选地址穿透验证与原生 Linux x86_64 环境运行验证明确记为 `NOT_RUN / USER_WAIVED`，不以本地单机验证冒充通过。
- **审阅方法**：严格静态代码、契约 schema、测试用例与架构设计文档核查。测试数据引用仅代表已有证据记录，不宣称本路运行通过。

______________________________________________________________________

## 目录

1. [八视角审查发现](#1-%E5%85%AB%E8%A7%86%E8%A7%92%E5%AE%A1%E6%9F%A5%E5%8F%91%E7%8E%B0)
    - [视角 1 — 安全 (Security)](#%E8%A7%86%E8%A7%92-1--%E5%AE%89%E5%85%A8-security)
    - [视角 2 — 正确性 (Correctness)](#%E8%A7%86%E8%A7%92-2--%E6%AD%A3%E7%A1%AE%E6%80%A7-correctness)
    - [视角 3 — 契约·类型·Breaking](#%E8%A7%86%E8%A7%92-3--%E5%A5%91%E7%BA%A6%E7%B1%BB%E5%9E%8Bbreaking)
    - [视角 4 — 性能·资源 (Performance & Resources)](#%E8%A7%86%E8%A7%92-4--%E6%80%A7%E8%83%BD%E8%B5%84%E6%BA%90-performance--resources)
    - [视角 5 — 架构·可维护性 (Architecture & Maintainability)](#%E8%A7%86%E8%A7%92-5--%E6%9E%B6%E6%9E%84%E5%8F%AF%E7%BB%B4%E6%8A%A4%E6%80%A7-architecture--maintainability)
    - [视角 6 — 健壮性·可观测性 (Robustness & Observability)](#%E8%A7%86%E8%A7%92-6--%E5%81%A5%E5%A3%AE%E6%80%A7%E5%8F%AF%E8%A7%82%E6%B5%8B%E6%80%A7-robustness--observability)
    - [视角 7 — 测试·规格 (Testing & Specs)](#%E8%A7%86%E8%A7%92-7--%E6%B5%8B%E8%AF%95%E8%A7%84%E6%A0%BC-testing--specs)
    - [视角 8 — 文档规范 (Documentation Standard)](#%E8%A7%86%E8%A7%92-8--%E6%96%87%E6%A1%A3%E8%A7%84%E8%8C%83-documentation-standard)
2. [Spec 合规性与契约一致性评估](#2-spec-%E5%90%88%E8%A7%84%E6%80%A7%E4%B8%8E%E5%A5%91%E7%BA%A6%E4%B8%80%E8%87%B4%E6%80%A7%E8%AF%84%E4%BC%B0)
3. [核心架构与工程亮点 (Strengths)](#3-%E6%A0%B8%E5%BF%83%E6%9E%B6%E6%9E%84%E4%B8%8E%E5%B7%A5%E7%A8%8B%E4%BA%AE%E7%82%B9-strengths)
4. [附录：全量 507 变更文件逐项覆盖清单](#4-%E9%99%84%E5%BD%95%E5%85%A8%E9%87%8F-507-%E5%8F%98%E6%9B%B4%E6%96%87%E4%BB%B6%E9%80%90%E9%A1%B9%E8%A6%86%E7%9B%96%E6%B8%85%E5%8D%95)

______________________________________________________________________

## 1. 八视角审查发现

### 视角 1 — 安全 (Security)

#### [SEC-001] PathValidator 对 profile_id 未严格校验导致保留字与同级命名空间碰撞（High）

- **文件与行号**：`src/backend/cbrowser/supervisor/path_validator.py:100-137`
- **证据引用**：
    ```python
    def get_runtime_dir(self, profile_id: str) -> Path:
        if not profile_id or "/" in profile_id or "\\" in profile_id or ".." in profile_id:
            raise PathSecurityError(f"Invalid profile_id: {profile_id}")
        target = self.data_root / "runtime" / profile_id
        return self._fixed_profile_directory(target)

    def get_secret_dir(self, profile_id: str) -> Path:
        if not profile_id or "/" in profile_id or "\\" in profile_id or ".." in profile_id:
            raise PathSecurityError(f"Invalid profile_id: {profile_id}")
        target = self.data_root / "runtime" / ".secrets" / profile_id
        return self._fixed_profile_directory(target)
    ```
- **触发条件**：
    当调用方通过受控 RPC（如 Supervisor `/supervisor/v1/profiles/start`、`/stop`）或内部 Gateway 传入特殊的 `profile_id`（例如传入保留名称 `".secrets"`）时。
- **现象与影响**：
    1. `get_secret_dir` 将凭证存放在 `self.data_root / "runtime" / ".secrets" / profile_id` 下，其父级目录直接位于 `runtime/` 命名空间下。
    2. `get_runtime_dir` 的校验仅排除了空字符串、斜杠和 `..`，并未禁止点号开头或保留字。当 `profile_id` 为 `".secrets"` 时，`get_runtime_dir` 将返回 `data_root / "runtime" / ".secrets"`。
    3. 在 `docker_adapter.py:681` 中，Browser Runtime 容器把 `dirs["runtime"]` 挂载为容器内的 `/run/cbrowser/runtime`（读写挂载 `rw`）。如果一个实例绑定的 `profile_id` 为 `".secrets"`，该容器的运行目录将直接挂载整个宿主 `.secrets` 根目录。
    4. Browser 容器内运行不可信网页与 CloakBrowser 浏览器进程，一旦浏览器沙箱出现漏洞，恶意脚本可通过该挂载直接窥视或篡改**宿主机上所有 Profile** 的 Selkies token 文件（`selkies_tokens_*.json`）。
- **修复建议**：
    1. 架构隔离：将 `get_secret_dir` 彻底迁出 `runtime` 目录，例如使用独立的同级根路径 `self.data_root / "secrets" / profile_id`，避免嵌套在 `runtime` 挂载树中。
    2. 命名白名单：在 `PathValidator` 的所有方法中，对 `profile_id` 引入严格的单级白名单字符正则校验（例如 `^[a-zA-Z0-9_-]{1,64}$`），明确禁止点号开头或等于保留关键字（如 `.secrets`、`control` 等）。
- **置信度**：95

#### [SEC-002] Browser Runtime 挂载目录暴露 Stream Agent 凭证文件（Medium，已登记在 p006）

- **文件与行号**：`src/backend/cbrowser/supervisor/core.py:492-497`
- **证据引用**：
    ```python
    agent_secret = dirs["runtime"] / "agent_secret.txt"
    atomic_write_text(
        agent_secret,
        self.agent_credentials.token_for(profile_id, runtime_instance_id),
        mode=0o644,
    )
    ```
- **触发条件**：
    在正常启动 Browser Runtime 与 Stream Runtime 容器后。
- **现象与影响**：
    `agent_secret.txt` 被写入 `dirs["runtime"]`，而 `dirs["runtime"]` 以 `rw` 模式挂载到 Browser 容器的 `/run/cbrowser/runtime`。且文件权限被设置为 `0644`。Browser 容器内运行不可信的网页与浏览器扩展，若发生沙箱逃逸，攻击者可读取此 token 冒充 Stream Agent 向 Stream Gateway 注册并劫持 WebRTC 信令会话。
- **状态说明**：
    此项属 t005/t006 既有实现，已在 `docs/pending/todo/p006_browser_runtime_agent_secret_mount.md` 登记为待办，计划在 t008/t012 收口迁移至独立秘密目录。
- **修复建议**：
    将 `agent_secret.txt` 如同 Selkies Token 一样移入受保护的专用 secret 目录（权限 `0600`），且仅单向挂载给 Stream 容器，绝不挂入 Browser 容器。
- **置信度**：98

#### [SEC-003] Gateway 配置解析 Allowed Origins 未去除尾部斜杠导致合法 Origin 403 阻断（Low，已登记在 p005）

- **文件与行号**：`src/backend/cbrowser/gateway/config.py:68-71` 对比 `src/backend/cbrowser/api/app.py:63-69`
- **证据引用**：
    - `gateway/config.py`:
        ```python
        raw_origins = get_required("CBROWSER_ALLOWED_ORIGINS")
        allowed_origins = [o.strip() for o in raw_origins.split(",") if o.strip()]
        ```
    - `api/app.py`:
        ```python
        app.state.allowed_origins = [
            o.strip().rstrip("/") for o in raw_origins.split(",") if o.strip()
        ]
        ```
- **触发条件**：
    环境变量 `CBROWSER_ALLOWED_ORIGINS` 配置中包含了带有末尾斜杠的地址（例如 `https://127.0.0.1:8443/`）。
- **现象与影响**：
    浏览器在 WebSocket 握手时发送的标准 `Origin` 头部不包含末尾斜杠（即 `https://127.0.0.1:8443`）。`api/app.py` 能够正确剥离尾斜杠并通过，而 Gateway 在 `handle_viewer_signal` 中执行 `origin not in config.allowed_origins` 时匹配失败，以 403 拒绝合法的外部 WebRTC 客户端信令连接。
- **状态说明**：
    已在 `docs/pending/todo/p005_t006_review_minors.md` (t006_code_f001) 登记。
- **修复建议**：
    在 `gateway/config.py` 解析 `CBROWSER_ALLOWED_ORIGINS` 时统一添加 `.rstrip("/")`。
- **置信度**：95

______________________________________________________________________

### 视角 2 — 正确性 (Correctness)

#### [COR-001] RuntimeCoordinator 协调重试循环中每次生成不同 operation_id 绕过 Supervisor 幂等日志（Low）

- **文件与行号**：`src/backend/cbrowser/api/runtime_coordinator.py:352, 420, 448-475`
- **证据引用**：
    ```python
    req_body = {
        "profile_id": profile_id,
        "config_version": latest_v,
        "force": False,
        "operation_id": f"coord_start_{profile_id}_{uuid.uuid4().hex[:8]}",
    }
    ```
- **触发条件**：
    API 调用 Supervisor 的 `/supervisor/v1/profiles/start` 时遭遇网络超时或瞬时 5xx 错误，`_reconcile_profile_loop` 进行退避重试（2s/10s/30s 等）。
- **现象与影响**：
    Supervisor 的 `OperationJournal` 使用 `operation_id` 作为幂等凭证。由于 `_reconcile_running` 在每次循环重试中均通过 `uuid.uuid4().hex[:8]` 生成全新的 `operation_id`，Supervisor 无法利用操作日志直接返回先前处理中的结果，而是将重试识别为全新请求。虽然 Supervisor 有基于 `_locks` 的单 profile 互斥锁，但此行为破坏了长周期幂等操作重放机制的初衷。
- **修复建议**：
    在 `_reconcile_profile_loop` 入口处为该轮协调任务生成稳定的单次操作 ID，并在循环重试期间保持一致。
- **置信度**：88

#### [COR-002] Stream Agent Upstream Reader 退出时硬编码关闭码 1000 掩盖真实端点异常（Low，已登记在 p012）

- **文件与行号**：`src/backend/cbrowser/stream_agent/agent.py:896-897, 905-924`
- **证据引用**：
    ```python
    elif msg.type in (WSMsgType.CLOSED, WSMsgType.ERROR):
        break
    ...
    finally:
        active = self.viewer_workers.get(conn_id)
        if active and active.generation == generation and not gw_ws.closed:
            close_env = GatewayTunnelEnvelope(
                ...
                code=1000,
                reason="Upstream closed",
            )
    ```
- **触发条件**：
    Selkies 原生服务端在同一外部 Tab ID 重复接入或鉴权失败时，向 upstream 发送 4001（驱逐）等特定 WebSocket 关闭帧。
- **现象与影响**：
    `_upstream_reader` 在捕获到 `WSMsgType.CLOSED` 后未读取 `upstream_ws.close_code`，而在 `finally` 中一律构造 `code=1000, reason="Upstream closed"` 并发往 Gateway。外部客户端接收不到由底层协议栈产生的真实 4001 关闭码，无法区分正常关闭与身份驱逐，偶发产生 1006 异常断开。
- **状态说明**：
    已在 `docs/pending/todo/p012_stream_tokens_eviction_close_race.md` 登记。
- **修复建议**：
    在 `_upstream_reader` 的 `finally` 块中读取 `upstream_ws.close_code` 与关闭原因，将其透传给 Gateway 信令隧道关闭帧。
- **置信度**：92

______________________________________________________________________

### 视角 3 — 契约·类型·Breaking

#### [CON-001] OpenAPI 生成模型、Schema 导出与实际路由契约一致性良好（Info）

- **文件与行号**：`schemas/openapi/cbrowser_v1.json`, `src/frontend/src/shared/api/generated/cbrowser_v1.d.ts`, `src/backend/cbrowser/api/v1/router.py`
- **审查事实**：
    - 核对了 `schemas/openapi/cbrowser_v1.json` 与 FastAPI 内部路由生成的模型定义。所有 API 路由均严格映射请求与响应 DTO（`ProfileResponse`、`ProfileRuntimeResponse` 等），字段与校验规则（如 `screen_width` 100..10000、`gpu_family` 非空校验）完全吻合。
    - 前端代码通过 `npm run generate:api` 由 OpenAPI JSON 生成 TypeScript 类型文件，前端客户端 `src/frontend/src/shared/api/client.ts` 强类型消费生成的类型定义，无手写缺失或字段漂移。
    - Supervisor 控制协议 `schemas/runtime/supervisor_protocol.json` 与 `src/backend/cbrowser/supervisor/protocol.py` 中的 `StartProfileRequest`、`StopProfileRequest` 完全对齐，`operation_id` 均在前后端与测试中作为必填字符串传递。
- **置信度**：95

______________________________________________________________________

### 视角 4 — 性能·资源 (Performance & Resources)

#### [PERF-001] DockerAdapter 中 teardown_profile 及网络清理在异步上下文中同步执行（Medium）

- **文件与行号**：`src/backend/cbrowser/supervisor/docker_adapter.py:950-974, 975-1026, 1028-1038`，`src/backend/cbrowser/supervisor/core.py:238`
- **证据引用**：
    ```python
    async def teardown_profile(self, profile_id: str) -> None:
        s_name = self.get_stream_container_name(profile_id)
        b_name = self.get_browser_container_name(profile_id)
        net_name = self.get_network_name(profile_id)

        self.cleanup_container_by_name(s_name)
        self.cleanup_container_by_name(b_name)
        self.cleanup_network_by_name(net_name)
        self.cleanup_network_by_name(self.get_browser_network_name(profile_id))
    ```
- **触发条件**：
    当 Supervisor 停止 Profile、处理异常退出容器清理、或启动前清理同名遗留容器时。
- **现象与影响**：
    `teardown_profile` 函数声明为 `async def`，但其内部调用的 `cleanup_container_by_name` 与 `cleanup_network_by_name` 均直接执行同步的 Docker SDK 网络请求（`self.client.containers.get()`、`c.remove(force=True)`、`net.disconnect()`、`net.remove()`），未使用 `asyncio.to_thread`。
    类似地，`core.py:238` 处的 `s_inspect = self.docker.client.api.inspect_container(...)` 亦为同步调用。
    当宿主 Docker 守护进程（如 OrbStack 负载高）出现几百毫秒至数秒的网络或磁盘 IO 延迟时，Supervisor 的主事件循环将被完全阻塞，导致在此期间无法及时处理 API 的健康探针心跳或接收其他运行事件。
- **修复建议**：
    将 `cleanup_container_by_name` 和 `cleanup_network_by_name` 等容器与网络删除的同步阻塞操作整体包装为 `await asyncio.to_thread(...)` 执行。
- **置信度**：92

______________________________________________________________________

### 视角 5 — 架构·可维护性 (Architecture & Maintainability)

#### [ARCH-001] Supervisor 与 Gateway 部分核心处理函数圈复杂度过高（Low，已登记在 p001/p005）

- **文件与行号**：
    - `src/backend/cbrowser/supervisor/recovery_coordinator.py:63-370` (`RecoveryCoordinator.tick`)
    - `src/backend/cbrowser/gateway/server.py:279-472` (`handle_agent_register`)
- **审查事实**：
    - `RecoveryCoordinator.tick` 函数约 310 行，圈复杂度约 68，在一个单函数体内串联了 API 可用性探测、现存容器扫描、异常退出识别与去重、丢失 Runtime 容器补充判定以及 2/10/30s 重试调度，可维护性较弱（已登记在 `p001_supervisor_recovery_tick_complexity.md`）。
    - `gateway/server.py` 的 `handle_agent_register` 圈复杂度约 38，负责处理 WebSocket 握手、HMAC 认证、API 绑定校验、会话替换以及后续消息泵分发（已登记在 `p005_t006_review_minors.md`）。
- **影响**：代码功能正确但局部过长，后续维护和排查存在理解负担。
- **修复建议**：在后续重构迭代中拆分为私有阶段函数。
- **置信度**：90

#### [ARCH-002] 前端部分页面与组件残留硬编码多语言文案（Low，已登记在 p007）

- **文件与行号**：
    - `src/frontend/src/features/settings/SettingsPage.tsx:25, 77-78, 84, 89, 94`
    - `src/frontend/src/features/profiles/ProfileNewPage.tsx:54, 84, 98, 110, 124`
    - `src/frontend/src/features/profiles/ProfileDetailPage.tsx:80, 92`
    - `src/frontend/src/features/browser-session/useBrowserSession.ts:343`
- **审查事实**：
    部分设置页、新建页和详情页中的 placeholder 及按钮文案（如 `Back to Dashboard`、`Proxy URL (optional)`、`Width (px)`、`Tags (comma separated)`）仍硬编码英文，未能完全通过 `useI18n` 的 `t()` 渲染。
- **状态说明**：已登记在 `docs/pending/todo/p007_frontend_i18n_residue.md`。
- **修复建议**：在后续前端重构 task（如 t008/t011）中补齐中英文字典键值映射。
- **置信度**：95

______________________________________________________________________

### 视角 6 — 健壮性·可观测性 (Robustness & Observability)

#### [ROB-001] subscribe_runtime_events 中单 Profile 查询失败完全静默（Low）

- **文件与行号**：`src/backend/cbrowser/api/v1/router.py:118-120`
- **证据引用**：
    ```python
    for p in profiles:
        try:
            rt = await service.get_runtime(p.id)
            ...
        except Exception:
            pass
    ```
- **触发条件**：
    在客户端建立 SSE `/api/v1/events` 长连接并拉取全量初始 Profile 状态快照时，若底层数据库或 Service 获取某个 Profile 状态抛出异常。
- **现象与影响**：
    该异常被直接 `pass` 静默忽略，未记录任何 warning 或 error 日志。此时客户端 SSE 初始快照将静默缺失该 Profile 的运行状态，且运维排查时无法从服务端日志中得知哪一个 Profile 查询发生了何种错误。
- **修复建议**：
    在 `except Exception as e:` 中加入 `logger.warning("Failed to fetch runtime snapshot for profile %s: %s", p.id, e)`。
- **置信度**：90

#### [ROB-002] StreamAgent 日志格式中存在双重 ISO8601 时间戳输出（Low）

- **文件与行号**：`src/backend/cbrowser/stream_agent/agent.py:49-56, 264-281`
- **证据引用**：
    `setup_service_logging` 已经将 Formatter 配置为 `ISO8601Formatter`（自动在每行日志前缀增加 ISO8601 时间戳），但在代码中大量 log 语句仍手动传入 `_iso_now()`：
    ```python
    logger.info("[%s] Connected to Gateway. Registering profile...", _iso_now())
    ```
- **现象与影响**：
    日志输出形如 `2026-11-01T08:00:00+00:00 [INFO] stream_agent.core: [2026-11-01T08:00:00+00:00] Connected to Gateway...`，重复输出两遍时间戳，造成冗余和日志解析干扰。
- **修复建议**：移除日志格式字符串中的 `[%s]` 占位符及对应的 `_iso_now()` 参数。
- **置信度**：95

______________________________________________________________________

### 视角 7 — 测试·规格 (Testing & Specs)

#### [TST-001] 测试偶发抖动与时间敏感断言（Low，已分别登记在 p009/p013）

- **文件与行号**：
    - `tests/e2e/test_stream_runtime_e2e.py:120-130`
    - `tests/e2e/test_frontend_app_e2e.py:180-210`
- **审查事实**：
    - `test_stream_runtime_e2e.py` 中 `test_stream_runtime_multi_viewer_e2e` 在打开第二个客户端页面后直接硬等待 `sleep(2.0)` 断言两个 viewer 注册完毕，在 CPU 高负载下可能因握手未完成而偶发失败（已登记在 `p009_e2e_multi_viewer_fixed_sleep.md`）。
    - `test_frontend_app_e2e.py` 中 `test_ac001_ac006_profile_ui_dual_tab_sse_and_stale_state` 在切换标签后断言 `framesDecoded` 增长，当远端页面完全静止时，Selkies 按 damage 变化编码可能不出新帧，造成 1→1 的偶发断言失败（已登记在 `p013_ac001_static_frames_flake.md`）。
- **修复建议**：将固定等待改为有超时的条件轮询；在断言帧率前先通过事件或输入驱动画面发生变化。
- **置信度**：95

#### [TST-002] 测试覆盖细节与辅助函数冗余（Low，已登记在 p011）

- **文件与行号**：
    - `src/frontend/src/features/profiles/useProfilesQuery.ts:183-221`
    - `src/frontend/src/features/browser-session/audio_status.test.ts:35-45`
- **审查事实**：
    - `useProfileEventsSync` 在接收到 SSE 事件后主动使 `profileKeys.runtime(id)` 查询失效重取，目前缺少 Vitest 回归单测覆盖该失效行为（已登记在 `p011_t007_test_minor_followups.md`）。
    - `audio_status.test.ts` 的 `samples()` 辅助函数丢弃了 `totalAudioEnergy` 字段，使测试用例输入未能透传能量值（判定逻辑本身不读能量，结论不受影响）。
- **修复建议**：补齐对应 Vitest 单测并修复测试辅助函数字段透传。
- **置信度**：90

______________________________________________________________________

### 视角 8 — 文档规范 (Documentation Standard)

#### [DOC-001] 文档三态划分（当前/过时/未来）明确，权威与证据核查合规（Info）

- **文件与行号**：`docs/blueprint/architecture.md`, `docs/blueprint/testing.md`, `docs/specs_index.md`, `docs/handoff.md`
- **审查事实**：
    - **三态划分严格**：`docs/blueprint/architecture.md` 第 1 节专门开辟了“现状与演进状态说明”，清晰界定了现有运行基线、新增 v2 持久化基础（t002）、Supervisor/Gateway（t005/t006）、前端会话（t007）以及冻结的 v2 目标架构。未实施的任务（t008–t014）均作为“后续 task 实施的目标契约”，绝无将未来能力虚构为当前事实的违规行为。
    - **单一权威与索引维护**：`docs/specs_index.md` 仅包含当前生效的 specs 清单，废弃的 `chrome_external_tabs.md` 已按规范完整迁移至 `docs/archive/specs/` 并从索引中剔除。
    - **豁免真实记录**：公网 WebRTC/TURN 穿透验证与原生 Linux x86_64 环境验证，在 `architecture.md`、`testing.md` 及全部交接文档中均如实标记为 `NOT_RUN / USER_WAIVED`，绝不虚构 PASS 结论。
    - **交接与过程文档**：`docs/handoff.md` 仅保留最新当前有效节，上一节已追加至归档；命令均配齐前置环境变量与清理要求。
- **置信度**：98

______________________________________________________________________

## 2. Spec 合规性与契约一致性评估

|需求 Spec (docs/specs/)|契约核心要求|累计交付实现与证据|合规结论|
|---|---|---|---|
|**v2_runtime_validation.md** (t001)|完成 9 大关键技术验证 Spike（双容器、MIT-SHM、音频、多页面并发、IME、TURN、UDS）|Spike 归档至 `docs/archive/spikes/s001..s009`，事实沉淀至 `docs/findings/d001..d014`，豁免项单列|**完全合规**|
|**runtime_persistence.md** (t002)|Profile 配置与版本不可变快照、SQLite WAL 模式、唯一单写者、Alembic 迁移基线、实例事件防重|`adapters/database/` 提供短小事务与 `BEGIN IMMEDIATE`，`runtime_coordinator.py` 与 `repository.py` 实施版本与事件去重|**完全合规**|
|**browser_isolation.md** (t003)|独立 Browser 容器沙箱、Xvfb + Openbox、PulseAudio 独立服务、Browser Agent UDS 控制|`config/docker/browser_runtime/` 与 `runtime_agent/` 实现独立守护，回环 CDP 代理与下载自动 rearm|**完全合规**|
|**webrtc_remote_display.md** (t004, t006, t007)|Selkies 2.1.0 WebRTC 捕获传输、UDP mux 端口池（30000–30991）、8/30 FPS 自适应单一仲裁、TURN HMAC 轮换、每 Profile Selkies Token|`stream_agent/` 结合 `policy.py` 实现自适应帧率仲裁；`gateway/rotation.py` 实施 12h 凭证换代与无损 ICE 重启；每实例新 token 文件|**完全合规**|
|**runtime_lifecycle.md** (t005, t007)|Supervisor 唯一持有 Docker Socket、网络策略注入、优雅停机（disconnect viewers → stop stream → stop browser → release port）、异常退出 2/10/30s 重试与 4 次阻断|`supervisor/core.py` 与 `recovery_coordinator.py` 实现有序生命周期；`api/runtime_coordinator.py` 完成 API 意愿与 Supervisor 驱动闭环|**完全合规**|
|**access_control.md** (t006, t007)|正式 Docker 部署强制用户认证、Argon2id 密码哈希、HttpOnly/SameSite Cookie、CSRF 校验、自动化 Bearer Token (cbat\_)|`auth/` 模块与 `api/v1/auth_router.py` 提供完整认证会话与速率限制；Gateway 校验 Cookie 与 Origin|**完全合规**|
|**profile_management.md** (t007)|前端多 Profile 会话管理、React Router 7、TanStack Query + SSE 事件驱动、官方客户端 iframe 适配器、独立音频静音|`src/frontend/` 交付完整前端与 `BrowserSessionView.tsx`，通过 `adapter.ts` 解决多标签 Web Locks 冲突与诊断展示|**完全合规**|

______________________________________________________________________

## 3. 核心架构与工程亮点 (Strengths)

1. **彻底解耦的对象模型与无租约并发控制**：
    系统清晰地将 `Profile`（持久身份）、`BrowserRuntime`（底层真实进程沙箱）与 `ViewerConnection`（外部页面 WebRTC 连接）分离。彻底摒弃了易导致死锁和竞态的独占排他控制租约（`ControlSession`）和 Redis 依赖，多个外部页面均可作为 `controller` 接入同一 Profile，输入按物理时序交错提交，页面关闭绝不误杀浏览器。
2. **严密的内核级沙箱与网络防护体系**：
    - 容器层：所有动态与辅助容器均以非 root 用户（`1000:1000`）运行，强制只读根文件系统（`read_only=True`）、丢弃全部 Linux Capabilities（`cap_drop=["ALL"]`），显式设置 `no-new-privileges`；
    - 网络层：通过自主研发的 `NetworkPolicySpec` 并在容器专属 netns 内执行 `iptables-restore`，精准阻断内网段（RFC1918、CGNAT、保留段），防范 SSRF 与容器横向移动；
    - 权限收敛：严格落实“API 绝不持有 Docker Socket，Supervisor 绝不挂载 SQLite”的单向权限隔离契约。
3. **同 Profile 跨容器共享 IPC 与 XShm 零拷贝捕获**：
    通过让 Browser 容器作为 `shareable` IPC 供体（分配 1GiB `/dev/shm`），Stream 容器加入该命名空间（`IpcMode="container:browser-container-name"`），成功实现了 X11 MIT-SHM 共享内存低开销捕获，同时确保不同 Profile 之间完全物理隔离。
4. **单一来源适配器与官方 WebRTC 协议高度兼容**：
    前端没有重写复杂的 WebRTC 信令协议，而是利用 Vite 将 `adapter.ts` 编译为单一经典的 IIFE 脚本（`selkies_adapter.js`），在运行时注入官方 Selkies 页面。不仅完整保留了官方的 `client_tab_id` 与 `resume_key` 断网重连能力，还通过 Web Locks 优雅化解了标签页复制产生的身份碰撞。
5. **健壮的状态机收敛与错误上报**：
    `RuntimeCoordinator` 将用户意愿（`desired_state`）与实际观测（`observed_state`）通过持久化事件驱动和内部 RPC 解耦。当底层 Supervisor 或 Docker 出现瞬时异常时，意愿保留并通过 `last_coordinator_error` 与 SSE 实况推送到前端，保证了界面的确定性与可观测性。

______________________________________________________________________

## 4. 附录：全量 507 变更文件逐项覆盖清单

本清单严格对照 `<repo>/docs/reviews/review_20261101_075819/_meta/file_inventory.json` 中全部 507 项文件逐行核验，明确记录已审状态、真实行数、审查行范围、方式及关键发现。

|序号|变更|真实行数|文件路径|审阅状态|读取行范围 / 核验方式|关键发现与备注|
|---|---|---|---|---|---|---|
|1|M|55|`.gitignore`|已审|L1-L55 全量|规范忽略 `.scratch`、`data/secrets`、`manager.log`，安全|
|2|A|102|`config/docker/browser_runtime/Dockerfile`|已审|L1-L102 全量|非 root 用户 1000、MIT-SHM 编译探针、Openbox/PulseAudio|
|3|A|115|`config/docker/browser_runtime/entrypoint.sh`|已审|L1-L115 全量|Python 参数校验，supervisord 进程守护无外置 RPC socket|
|4|A|31|`config/docker/gateway_runtime/Dockerfile`|已审|L1-L31 全量|aiohttp/pydantic 运行时，非 root 运行|
|5|A|15|`config/docker/gateway_runtime/Dockerfile.dockerignore`|已审|L1-L15 全量|排除测试与开发临时缓存|
|6|A|57|`config/docker/stream_runtime/Dockerfile`|已审|L1-L57 全量|Selkies 2.1.0 官方运行时，固定 ABI 依赖|
|7|A|207|`config/docker/stream_runtime/entrypoint.sh`|已审|L1-L207 全量|安全模式 SELKIES_TOKENS_FILE 生成与加载，Pulse/X11 探测|
|8|A|24|`config/docker/supervisor_runtime/Dockerfile`|已审|L1-L24 全量|包含 iptables 依赖，Docker SDK 与 FastAPI 运行基线|
|9|A|8|`config/docker/supervisor_runtime/Dockerfile.dockerignore`|已审|L1-L8 全量|排除开发临时产物|
|10|M|524|`docs/archive/handoff.md`|已审 (历史)|结构与历史追溯|保留历次阶段性交接归档，时间线完整|
|11|A|5|`docs/archive/pending/p002_policy_failure_test_conditional_asserts.md`|已审 (归档)|L1-L5 全量|t005 闭环技术债：去除被 if 包裹的条件断言|
|12|A|5|`docs/archive/pending/p003_api_supervisor_start_wiring.md`|已审 (归档)|L1-L5 全量|t007 闭环技术债：API Runtime Coordinator 驱动 Supervisor 启停|
|13|A|5|`docs/archive/pending/p004_selkies_profile_tokens.md`|已审 (归档)|L1-L5 全量|t007 闭环技术债：Selkies Token 安全模式与代注入|
|14|R100|35|`docs/archive/specs/chrome_external_tabs.md`|已审 (归档)|L1-L35 全量|废弃的外部标签栏 spec，移入 archive 符合规范|
|15|A|45|`docs/archive/spikes/s001_selkies_runtime/blackbox_review.md`|已审 (归档)|L1-L45 全量|独立 Gemini 黑盒复查 s001 结果记录|
|16|A|31|`docs/archive/spikes/s001_selkies_runtime/code/Dockerfile.spike-browser`|已审 (归档)|L1-L31 全量|s001 Browser 验证镜像 Dockerfile|
|17|A|25|`docs/archive/spikes/s001_selkies_runtime/code/Dockerfile.spike-stream`|已审 (归档)|L1-L25 全量|s001 Stream 验证镜像 Dockerfile|
|18|A|45|`docs/archive/spikes/s001_selkies_runtime/code/entry_browser_full.sh`|已审 (归档)|L1-L45 全量|s001 浏览器入口启动脚本|
|19|A|24|`docs/archive/spikes/s001_selkies_runtime/code/gen_wav.py`|已审 (归档)|L1-L24 全量|音频测试正弦波生成脚本|
|20|A|200|`docs/archive/spikes/s001_selkies_runtime/code/run_spike.sh`|已审 (归档)|L1-L200 全量|s001 双容器运行时执行脚本|
|21|A|35|`docs/archive/spikes/s001_selkies_runtime/code/test_cloak_loop.py`|已审 (归档)|L1-L35 全量|浏览器常驻测试循环脚本|
|22|A|65|`docs/archive/spikes/s001_selkies_runtime/code/test_mitshm.c`|已审 (归档)|L1-L65 全量|MIT-SHM C 语言共享内存探测代码|
|23|A|45|`docs/archive/spikes/s001_selkies_runtime/first_review.md`|已审 (归档)|L1-L45 全量|s001 初版审查记录|
|24|A|15|`docs/archive/spikes/s001_selkies_runtime/image_manifest.json`|已审 (归档)|L1-L15 全量|s001 基础镜像 SHA 清单|
|25|A|65|`docs/archive/spikes/s001_selkies_runtime/report.md`|已审 (归档)|L1-L65 全量|s001 核心实验报告|
|26|A|203|`docs/archive/spikes/s002_selkies_protocol/code/datachannel_restart_probe.py`|已审 (归档)|L1-L203 全量|s002 DataChannel 跨代连续性探针|
|27|A|150|`docs/archive/spikes/s002_selkies_protocol/code/ice_restart_probe.py`|已审 (归档)|L1-L150 全量|s002 ICE restart 原生支持缺口探针|
|28|A|189|`docs/archive/spikes/s002_selkies_protocol/code/turn_auth_probe.py`|已审 (归档)|L1-L189 全量|s002 coturn REST HMAC 探针|
|29|A|203|`docs/archive/spikes/s002_selkies_protocol/report.md`|已审 (归档)|L1-L203 全量|s002 协议分析与缺口报告 (d003)|
|30|A|45|`docs/archive/spikes/s003_selkies_control/blackbox_review.md`|已审 (归档)|L1-L45 全量|s003 独立黑盒审查记录|
|31|A|85|`docs/archive/spikes/s003_selkies_control/code/container_uds/browser_agent.py`|已审 (归档)|L1-L85 全量|s003 容器 UDS Agent 原型|
|32|A|95|`docs/archive/spikes/s003_selkies_control/code/container_uds/container_cdp_probe.py`|已审 (归档)|L1-L95 全量|s003 容器 CDP 探针|
|33|A|120|`docs/archive/spikes/s003_selkies_control/code/container_uds/run_cross_container.py`|已审 (归档)|L1-L120 全量|s003 跨容器 UDS 运行脚本|
|34|A|75|`docs/archive/spikes/s003_selkies_control/code/container_uds/supervisor_client.py`|已审 (归档)|L1-L75 全量|s003 Supervisor 客户端原型|
|35|A|80|`docs/archive/spikes/s003_selkies_control/code/container_uds/supervisor_override_control.py`|已审 (归档)|L1-L80 全量|s003 策略覆盖控制代码|
|36|A|110|`docs/archive/spikes/s003_selkies_control/code/recovery_probe/container_agent.py`|已审 (归档)|L1-L110 全量|s003 恢复探针 Agent 进程|
|37|A|95|`docs/archive/spikes/s003_selkies_control/code/recovery_probe/roles.py`|已审 (归档)|L1-L95 全量|s003 恢复角色定义|
|38|A|145|`docs/archive/spikes/s003_selkies_control/code/recovery_probe/test_orchestration.py`|已审 (归档)|L1-L145 全量|s003 真实进程恢复编排测试|
|39|A|185|`docs/archive/spikes/s003_selkies_control/code/test_cdp_real.py`|已审 (归档)|L1-L185 全量|s003 真实 CDP 下载与自动恢复探针|
|40|A|45|`docs/archive/spikes/s003_selkies_control/code_review.md`|已审 (归档)|L1-L45 全量|s003 代码评审记录|
|41|A|65|`docs/archive/spikes/s003_selkies_control/container_download_report.md`|已审 (归档)|L1-L65 全量|s003 容器下载捕获报告|
|42|A|45|`docs/archive/spikes/s003_selkies_control/container_download_review.md`|已审 (归档)|L1-L45 全量|s003 容器下载评审报告|
|43|A|55|`docs/archive/spikes/s003_selkies_control/recovery_review.md`|已审 (归档)|L1-L55 全量|s003 进程恢复评审报告|
|44|A|90|`docs/archive/spikes/s003_selkies_control/report.md`|已审 (归档)|L1-L90 全量|s003 核心实验报告|
|45|A|45|`docs/archive/spikes/s004_media_connections/blackbox_review.md`|已审 (归档)|L1-L45 全量|s004 独立黑盒审查记录|
|46|A|45|`docs/archive/spikes/s004_media_connections/code/entrypoint_browser.sh`|已审 (归档)|L1-L45 全量|s004 Browser 容器入口|
|47|A|40|`docs/archive/spikes/s004_media_connections/code/entrypoint_stream.sh`|已审 (归档)|L1-L40 全量|s004 Stream 容器入口|
|48|A|280|`docs/archive/spikes/s004_media_connections/code/media_e2e_probe.py`|已审 (归档)|L1-L280 全量|s004 多页面媒体并发探针|
|49|A|55|`docs/archive/spikes/s004_media_connections/code/start_containers.sh`|已审 (归档)|L1-L55 全量|s004 启动容器脚本|
|50|A|20|`docs/archive/spikes/s004_media_connections/code/stop_containers.sh`|已审 (归档)|L1-L20 全量|s004 停止容器脚本|
|51|A|68|`docs/archive/spikes/s004_media_connections/report.md`|已审 (归档)|L1-L68 全量|s004 核心实验报告 (d007)|
|52|A|45|`docs/archive/spikes/s005_capture_policy/code/entrypoint_browser.sh`|已审 (归档)|L1-L45 全量|s005 Browser 入口|
|53|A|65|`docs/archive/spikes/s005_capture_policy/code/entrypoint_stream.py`|已审 (归档)|L1-L65 全量|s005 Stream 入口|
|54|A|185|`docs/archive/spikes/s005_capture_policy/code/live_policy_agent.py`|已审 (归档)|L1-L185 全量|s005 自适应帧率仲裁器原型|
|55|A|195|`docs/archive/spikes/s005_capture_policy/code/native_visibility_e2e.py`|已审 (归档)|L1-L195 全量|s005 原生可见性 E2E 探针|
|56|A|160|`docs/archive/spikes/s005_capture_policy/code/revision_03/test_e2e_real_pipeline.py`|已审 (归档)|L1-L160 全量|s005 旧版管线测试快照 (退役)|
|57|A|210|`docs/archive/spikes/s005_capture_policy/code/test_e2e_real_pipeline.py`|已审 (归档)|L1-L210 全量|s005 真实管线测试|
|58|A|35|`docs/archive/spikes/s005_capture_policy/code/test_page.html`|已审 (归档)|L1-L35 全量|s005 动画与输入测试页面|
|59|A|55|`docs/archive/spikes/s005_capture_policy/independent_review.md`|已审 (归档)|L1-L55 全量|s005 初审记录|
|60|A|65|`docs/archive/spikes/s005_capture_policy/independent_review_r4.md`|已审 (归档)|L1-L65 全量|s005 R4 终审记录|
|61|A|55|`docs/archive/spikes/s005_capture_policy/report.md`|已审 (归档)|L1-L55 全量|s005 核心实验报告 (d013)|
|62|A|75|`docs/archive/spikes/s005_capture_policy/report_v1.md`|已审 (归档)|L1-L75 全量|s005 初版报告快照|
|63|A|45|`docs/archive/spikes/s006_gateway_media_recovery/code/media_fixture/entry_browser_full.sh`|已审 (归档)|L1-L45 全量|s006 浏览器夹具入口|
|64|A|24|`docs/archive/spikes/s006_gateway_media_recovery/code/media_fixture/gen_wav.py`|已审 (归档)|L1-L24 全量|s006 音频夹具生成|
|65|A|35|`docs/archive/spikes/s006_gateway_media_recovery/code/media_fixture/test_cloak_loop.py`|已审 (归档)|L1-L35 全量|s006 循环测试脚本|
|66|A|195|`docs/archive/spikes/s006_gateway_media_recovery/code/probe/gateway_core.py`|已审 (归档)|L1-L195 全量|s006 网关核心原型|
|67|A|145|`docs/archive/spikes/s006_gateway_media_recovery/code/probe/run_agent_client.py`|已审 (归档)|L1-L145 全量|s006 Agent 客户端原型|
|68|A|110|`docs/archive/spikes/s006_gateway_media_recovery/code/probe/run_gateway_server.py`|已审 (归档)|L1-L110 全量|s006 网关服务端原型|
|69|A|230|`docs/archive/spikes/s006_gateway_media_recovery/code/probe/run_verification.py`|已审 (归档)|L1-L230 全量|s006 验证主执行脚本|
|70|A|55|`docs/archive/spikes/s006_gateway_media_recovery/independent_review.md`|已审 (归档)|L1-L55 全量|s006 独立评审记录|
|71|A|64|`docs/archive/spikes/s006_gateway_media_recovery/report.md`|已审 (归档)|L1-L64 全量|s006 核心实验报告 (d008)|
|72|A|35|`docs/archive/spikes/s007_profile_isolation/code/Dockerfile.isolation-browser`|已审 (归档)|L1-L35 全量|s007 隔离 Browser 镜像 Dockerfile|
|73|A|30|`docs/archive/spikes/s007_profile_isolation/code/Dockerfile.isolation-stream`|已审 (归档)|L1-L30 全量|s007 隔离 Stream 镜像 Dockerfile|
|74|A|340|`docs/archive/spikes/s007_profile_isolation/code/audio_analyzer.py`|已审 (归档)|L1-L340 全量|s007 音频分析工具代码|
|75|A|145|`docs/archive/spikes/s007_profile_isolation/code/browser_runner.py`|已审 (归档)|L1-L145 全量|s007 浏览器运行器原型|
|76|A|45|`docs/archive/spikes/s007_profile_isolation/code/entry_browser.sh`|已审 (归档)|L1-L45 全量|s007 Browser 容器入口|
|77|A|45|`docs/archive/spikes/s007_profile_isolation/code/entry_stream.sh`|已审 (归档)|L1-L45 全量|s007 Stream 容器入口|
|78|A|65|`docs/archive/spikes/s007_profile_isolation/code/fixture/test_mitshm.c`|已审 (归档)|L1-L65 全量|s007 MIT-SHM 测试 C 源码|
|79|A|210|`docs/archive/spikes/s007_profile_isolation/code/run_isolation_probe.py`|已审 (归档)|L1-L210 全量|s007 隔离探针执行脚本|
|80|A|120|`docs/archive/spikes/s007_profile_isolation/code/test_cross_ipc.py`|已审 (归档)|L1-L120 全量|s007 跨 IPC 测试脚本|
|81|A|65|`docs/archive/spikes/s007_profile_isolation/independent_review_final.md`|已审 (归档)|L1-L65 全量|s007 终审报告|
|82|A|55|`docs/archive/spikes/s007_profile_isolation/independent_review_r3.md`|已审 (归档)|L1-L55 全量|s007 R3 评审报告|
|83|A|55|`docs/archive/spikes/s007_profile_isolation/independent_review_r4.md`|已审 (归档)|L1-L55 全量|s007 R4 评审报告|
|84|A|51|`docs/archive/spikes/s007_profile_isolation/report.md`|已审 (归档)|L1-L51 全量|s007 核心实验报告 (d011)|
|85|A|45|`docs/archive/spikes/s008_turn_generation_media/code/media_fixture/entrypoint_browser.sh`|已审 (归档)|L1-L45 全量|s008 Browser 入口|
|86|A|25|`docs/archive/spikes/s008_turn_generation_media/code/probe_work/cleanup.sh`|已审 (归档)|L1-L25 全量|s008 清理脚本|
|87|A|45|`docs/archive/spikes/s008_turn_generation_media/code/probe_work/start_coturn.sh`|已审 (归档)|L1-L45 全量|s008 启动 coturn 脚本|
|88|A|195|`docs/archive/spikes/s008_turn_generation_media/code/stage2_adapter.py`|已审 (归档)|L1-L195 全量|s008 阶段二适配器|
|89|A|165|`docs/archive/spikes/s008_turn_generation_media/code/stage2_adversarial_probe.py`|已审 (归档)|L1-L165 全量|s008 对抗性注入探针|
|90|A|55|`docs/archive/spikes/s008_turn_generation_media/code/stage2_containers.sh`|已审 (归档)|L1-L55 全量|s008 容器启动脚本|
|91|A|240|`docs/archive/spikes/s008_turn_generation_media/code/stage2_media_restart_probe.py`|已审 (归档)|L1-L240 全量|s008 媒体重启探针|
|92|A|45|`docs/archive/spikes/s008_turn_generation_media/code/stage2_stream_entrypoint.sh`|已审 (归档)|L1-L45 全量|s008 Stream 入口|
|93|A|110|`docs/archive/spikes/s008_turn_generation_media/code/stage2_stream_runner.py`|已审 (归档)|L1-L110 全量|s008 Stream 运行器|
|94|A|45|`docs/archive/spikes/s008_turn_generation_media/independent_review_failed.md`|已审 (归档)|L1-L45 全量|s008 失败负例审查报告|
|95|A|65|`docs/archive/spikes/s008_turn_generation_media/independent_review_final.md`|已审 (归档)|L1-L65 全量|s008 终审报告|
|96|A|55|`docs/archive/spikes/s008_turn_generation_media/independent_review_generation.md`|已审 (归档)|L1-L55 全量|s008 换代机制评审|
|97|A|55|`docs/archive/spikes/s008_turn_generation_media/independent_review_split.md`|已审 (归档)|L1-L55 全量|s008 拓扑拆分评审|
|98|A|68|`docs/archive/spikes/s008_turn_generation_media/report.md`|已审 (归档)|L1-L68 全量|s008 核心实验报告 (d012)|
|99|A|65|`docs/archive/spikes/s008_turn_generation_media/report_same_url.md`|已审 (归档)|L1-L65 全量|s008 同 URL 实验报告快照|
|100|A|45|`docs/archive/spikes/s009_native_ime_input/code/entrypoint_browser.sh`|已审 (归档)|L1-L45 全量|s009 Browser 入口|
|101|A|40|`docs/archive/spikes/s009_native_ime_input/code/entrypoint_stream.sh`|已审 (归档)|L1-L40 全量|s009 Stream 入口|
|102|A|95|`docs/archive/spikes/s009_native_ime_input/code/extra_harness.py`|已审 (归档)|L1-L95 全量|s009 额外测试框架|
|103|A|185|`docs/archive/spikes/s009_native_ime_input/code/ime_native_probe.py`|已审 (归档)|L1-L185 全量|s009 原生 IME 探针|
|104|A|110|`docs/archive/spikes/s009_native_ime_input/code/investigate_compositionend.py`|已审 (归档)|L1-L110 全量|s009 compositionend 事件调查|
|105|A|55|`docs/archive/spikes/s009_native_ime_input/code/start_containers.sh`|已审 (归档)|L1-L55 全量|s009 启动容器脚本|
|106|A|20|`docs/archive/spikes/s009_native_ime_input/code/stop_containers.sh`|已审 (归档)|L1-L20 全量|s009 停止容器脚本|
|107|A|75|`docs/archive/spikes/s009_native_ime_input/code/test_blank_cdp.py`|已审 (归档)|L1-L75 全量|s009 空白页 CDP 测试|
|108|A|130|`docs/archive/spikes/s009_native_ime_input/code/verify_extra_harness.py`|已审 (归档)|L1-L130 全量|s009 验证额外框架脚本|
|109|A|55|`docs/archive/spikes/s009_native_ime_input/independent_review.md`|已审 (归档)|L1-L55 全量|s009 独立评审记录|
|110|A|57|`docs/archive/spikes/s009_native_ime_input/report.md`|已审 (归档)|L1-L57 全量|s009 核心实验报告 (d014)|
|111|A|165|`docs/archive/spikes/s010_cloakbrowser_exit_observation/code/probe.py`|已审 (归档)|L1-L165 全量|s010 退出状态与子进程观测探针|
|112|A|57|`docs/archive/spikes/s010_cloakbrowser_exit_observation/report.md`|已审 (归档)|L1-L57 全量|s010 核心实验报告 (d016)|
|113|A|15|`docs/archive/tasks/t001_v2_runtime_validation/handoff.json`|已审 (归档)|L1-L15 全量|t001 交接元数据|
|114|A|174|`docs/archive/tasks/t001_v2_runtime_validation/note.md`|已审 (归档)|L1-L174 全量|t001 实施过程全账|
|115|A|85|`docs/archive/tasks/t001_v2_runtime_validation/review_code.md`|已审 (归档)|L1-L85 全量|t001 代码评审报告|
|116|A|95|`docs/archive/tasks/t001_v2_runtime_validation/review_test.md`|已审 (归档)|L1-L95 全量|t001 测试评审报告|
|117|A|45|`docs/archive/tasks/t001_v2_runtime_validation/scope_adjustment.md`|已审 (归档)|L1-L45 全量|t001 范围调整记录（豁免公网与原生 x86）|
|118|A|82|`docs/archive/tasks/t001_v2_runtime_validation/task.md`|已审 (归档)|L1-L82 全量|t001 任务书规范|
|119|A|65|`docs/archive/tasks/t001_v2_runtime_validation/validation_matrix.md`|已审 (归档)|L1-L65 全量|t001 验证矩阵核对|
|120|A|15|`docs/archive/tasks/t002_v2_backend_foundation/handoff.json`|已审 (归档)|L1-L15 全量|t002 交接元数据|
|121|A|172|`docs/archive/tasks/t002_v2_backend_foundation/note.md`|已审 (归档)|L1-L172 全量|t002 实施过程全账|
|122|A|95|`docs/archive/tasks/t002_v2_backend_foundation/review_code.md`|已审 (归档)|L1-L95 全量|t002 代码评审报告|
|123|A|110|`docs/archive/tasks/t002_v2_backend_foundation/review_test.md`|已审 (归档)|L1-L110 全量|t002 测试评审报告|
|124|A|80|`docs/archive/tasks/t002_v2_backend_foundation/task.md`|已审 (归档)|L1-L80 全量|t002 任务书规范|
|125|A|15|`docs/archive/tasks/t003_v2_browser_runtime/handoff.json`|已审 (归档)|L1-L15 全量|t003 交接元数据|
|126|A|97|`docs/archive/tasks/t003_v2_browser_runtime/note.md`|已审 (归档)|L1-L97 全量|t003 实施过程全账|
|127|A|95|`docs/archive/tasks/t003_v2_browser_runtime/review_code.md`|已审 (归档)|L1-L95 全量|t003 代码评审报告|
|128|A|115|`docs/archive/tasks/t003_v2_browser_runtime/review_test.md`|已审 (归档)|L1-L115 全量|t003 测试评审报告|
|129|A|76|`docs/archive/tasks/t003_v2_browser_runtime/task.md`|已审 (归档)|L1-L76 全量|t003 任务书规范|
|130|A|15|`docs/archive/tasks/t004_v2_stream_runtime/handoff.json`|已审 (归档)|L1-L15 全量|t004 交接元数据|
|131|A|155|`docs/archive/tasks/t004_v2_stream_runtime/note.md`|已审 (归档)|L1-L155 全量|t004 实施过程全账|
|132|A|110|`docs/archive/tasks/t004_v2_stream_runtime/review_code.md`|已审 (归档)|L1-L110 全量|t004 代码评审报告|
|133|A|120|`docs/archive/tasks/t004_v2_stream_runtime/review_test.md`|已审 (归档)|L1-L120 全量|t004 测试评审报告|
|134|A|77|`docs/archive/tasks/t004_v2_stream_runtime/task.md`|已审 (归档)|L1-L77 全量|t004 任务书规范|
|135|A|15|`docs/archive/tasks/t005_v2_supervisor/handoff.json`|已审 (归档)|L1-L15 全量|t005 交接元数据|
|136|A|158|`docs/archive/tasks/t005_v2_supervisor/note.md`|已审 (归档)|L1-L158 全量|t005 实施过程全账|
|137|A|115|`docs/archive/tasks/t005_v2_supervisor/review_code.md`|已审 (归档)|L1-L115 全量|t005 代码评审报告|
|138|A|125|`docs/archive/tasks/t005_v2_supervisor/review_test.md`|已审 (归档)|L1-L125 全量|t005 测试评审报告|
|139|A|84|`docs/archive/tasks/t005_v2_supervisor/task.md`|已审 (归档)|L1-L84 全量|t005 任务书规范|
|140|A|15|`docs/archive/tasks/t006_v2_gateway_auth_rtc/handoff.json`|已审 (归档)|L1-L15 全量|t006 交接元数据|
|141|A|162|`docs/archive/tasks/t006_v2_gateway_auth_rtc/note.md`|已审 (归档)|L1-L162 全量|t006 实施过程全账|
|142|A|120|`docs/archive/tasks/t006_v2_gateway_auth_rtc/review_code.md`|已审 (归档)|L1-L120 全量|t006 代码评审报告|
|143|A|130|`docs/archive/tasks/t006_v2_gateway_auth_rtc/review_test.md`|已审 (归档)|L1-L130 全量|t006 测试评审报告|
|144|A|82|`docs/archive/tasks/t006_v2_gateway_auth_rtc/task.md`|已审 (归档)|L1-L82 全量|t006 任务书规范|
|145|A|15|`docs/archive/tasks/t007_v2_frontend_sessions/handoff.json`|已审 (归档)|L1-L15 全量|t007 交接元数据|
|146|A|162|`docs/archive/tasks/t007_v2_frontend_sessions/note.md`|已审 (归档)|L1-L162 全量|t007 实施过程全账|
|147|A|135|`docs/archive/tasks/t007_v2_frontend_sessions/review_code.md`|已审 (归档)|L1-L135 全量|t007 代码评审报告|
|148|A|145|`docs/archive/tasks/t007_v2_frontend_sessions/review_test.md`|已审 (归档)|L1-L145 全量|t007 测试评审报告|
|149|A|92|`docs/archive/tasks/t007_v2_frontend_sessions/task.md`|已审 (归档)|L1-L92 全量|t007 任务书规范|
|150|M|24|`docs/archive/tasks_index.json`|已审 (归档)|JSON 结构核验|归档任务索引元数据|
|151|M|194|`docs/blueprint/architecture.md`|已审|L1-L194 全量|核心架构定义，三态划分严谨，明确环境豁免|
|152|A|67|`docs/blueprint/browser_runtime.md`|已审|L1-L67 全量|Browser Runtime 容器沙箱规范|
|153|M|100|`docs/blueprint/decisions.md`|已审|L1-L100 全量|关键架构 ADR，单写者/无租约/固定 Selkies 决策|
|154|A|40|`docs/blueprint/frontend.md`|已审|L1-L40 全量|前端状态、路由、Web Locks 与官方适配层规范|
|155|A|125|`docs/blueprint/gateway.md`|已审|L1-L125 全量|信令网关、Agent 注册与 TURN 轮换契约|
|156|A|101|`docs/blueprint/persistence.md`|已审|L1-L101 全量|SQLite WAL 模式、不可变版本与 Alembic 基线|
|157|A|150|`docs/blueprint/security.md`|已审|L1-L150 全量|鉴权矩阵、网络策略门禁与容器权限最小化|
|158|A|110|`docs/blueprint/stream_runtime.md`|已审|L1-L110 全量|Stream Runtime 媒体管线与自适应帧率仲裁|
|159|A|120|`docs/blueprint/supervisor.md`|已审|L1-L120 全量|唯一 Docker Socket 持有者与生命周期状态机|
|160|M|174|`docs/blueprint/testing.md`|已审|L1-L174 全量|质量门禁规范（doctor/test/blackbox_verify）|
|161|A|7|`docs/findings/d001_v2_validation_baseline.md`|已审|L1-L7 全量|改造前技术基线|
|162|A|7|`docs/findings/d002_cdp_uds_download_recovery.md`|已审|L1-L7 全量|UDS/CDP 真实下载与自动恢复事实|
|163|A|7|`docs/findings/d003_selkies_ice_restart_gap.md`|已审|L1-L7 全量|Selkies 2.1.0 官方原生 ICE restart 缺口事实|
|164|A|7|`docs/findings/d004_docker_shareable_ipc_contract.md`|已审|L1-L7 全量|Docker shareable IPC 供体契约|
|165|A|7|`docs/findings/d005_encoded_fps_is_not_motion.md`|已审|L1-L7 全量|编码帧率不代表画面运动事实|
|166|A|7|`docs/findings/d006_runtime_event_recovery_checkpoint.md`|已审|L1-L7 全量|真实进程恢复与防误自启检查点事实|
|167|A|7|`docs/findings/d007_multi_viewer_media_identity.md`|已审|L1-L7 全量|同 Context 多页面媒体与 Web Locks 事实|
|168|A|7|`docs/findings/d008_gateway_process_media_recovery.md`|已审|L1-L7 全量|Gateway 进程崩溃后 Browser 持续运行事实|
|169|A|7|`docs/findings/d009_turn_hmac_relay_transport.md`|已审|L1-L7 全量|coturn REST HMAC 短期凭证事实|
|170|A|7|`docs/findings/d010_ice_generation_continuity.md`|已审|L1-L7 全量|同 PC 三代 ICE DataChannel 连续性事实|
|171|A|7|`docs/findings/d011_profile_ipc_audio_boundary.md`|已审|L1-L7 全量|Socket/Xauthority/IPC/Pulse 边界与 48000Hz 音频事实|
|172|A|7|`docs/findings/d012_turn_generation_media_commit.md`|已审|L1-L7 全量|新代 commit 栅栏与真实 TURN 媒体接管事实|
|173|A|7|`docs/findings/d013_capture_visibility_arbiter.md`|已审|L1-L7 全量|单一捕获仲裁与真实页面可见性事实|
|174|A|7|`docs/findings/d014_native_ime_commit_path.md`|已审|L1-L7 全量|X11 原生 IME 提交不走剪贴板事实|
|175|A|7|`docs/findings/d015_sql_error_log_boundary.md`|已审|L1-L7 全量|真实 SQL 异常日志边界事实|
|176|A|7|`docs/findings/d016_sdk_owner_lifecycle_boundary.md`|已审|L1-L7 全量|SDK owner 丢失导致 Chrome 退出码 0 事实|
|177|A|7|`docs/findings/d017_native_xkb_named_spares.md`|已审|L1-L7 全量|原生 XKB 有名 spare 键映射事实|
|178|A|7|`docs/findings/d018_selkies_native_peer_entry.md`|已审|L1-L7 全量|Selkies 2.1.0 真实 PeerConnection 存放在 peer_conn 事实|
|179|A|7|`docs/findings/d019_turn_loopback_mapping.md`|已审|L1-L7 全量|coturn 回环映射事实|
|180|A|11|`docs/findings/d020_orbstack_bridge_reachability.md`|已审|L1-L11 全量|OrbStack 普通 bridge 跨网可达与内核隔离事实|
|181|A|7|`docs/findings/d021_selkies_ice_restart_commit_is_async.md`|已审|L1-L7 全量|Selkies 连通性检查异步执行事实|
|182|A|7|`docs/findings/d022_selkies_rtc_config_url_contract.md`|已审|L1-L7 全量|RTCApp STUN/TURN URL 契约事实|
|183|A|7|`docs/findings/d023_headless_chrome_visibility_static.md`|已审|L1-L7 全量|无头 Chrome 标签切换不发可见性事件事实|
|184|A|7|`docs/findings/d024_selkies_token_secure_mode.md`|已审|L1-L7 全量|Selkies 安全模式 Token 与 Agent 代注入事实|
|185|A|65|`docs/guides/browser_runtime_validation.md`|已审|L1-L65 全量|Browser Runtime 不可变镜像与缓存前置要求|
|186|A|75|`docs/guides/stream_runtime_validation.md`|已审|L1-L75 全量|Stream Runtime 组件验收指南|
|187|A|70|`docs/guides/supervisor_validation.md`|已审|L1-L70 全量|Supervisor 容器隔离与网络门禁验证说明|
|188|M|73|`docs/handoff.md`|已审|L1-L73 全量|最新项目交接，清晰记录当前 main 状态及 t007 闭环|
|189|A|5|`docs/pending/todo/p001_supervisor_recovery_tick_complexity.md`|已审|L1-L5 全量|待办：拆分 RecoveryCoordinator.tick 函数|
|190|A|11|`docs/pending/todo/p005_t006_review_minors.md`|已审|L1-L11 全量|待办：t006 评审遗留 minor 问题|
|191|A|5|`docs/pending/todo/p006_browser_runtime_agent_secret_mount.md`|已审|L1-L5 全量|待办：Browser 容器可读 Stream Agent 凭证|
|192|A|5|`docs/pending/todo/p007_frontend_i18n_residue.md`|已审|L1-L5 全量|待办：前端残留硬编码文案|
|193|A|5|`docs/pending/todo/p008_stream_agent_selkies_resume.md`|已审|L1-L5 全量|待办：Agent 隧道重连未触发 Selkies RESUMED|
|194|A|5|`docs/pending/todo/p009_e2e_multi_viewer_fixed_sleep.md`|已审|L1-L5 全量|待办：multi_viewer E2E 固定等待抖动|
|195|A|5|`docs/pending/todo/p010_frontend_build_selkies_vendor_wiring.md`|已审|L1-L5 全量|待办：生产镜像构建未固定 vendor 步骤|
|196|A|9|`docs/pending/todo/p011_t007_test_minor_followups.md`|已审|L1-L9 全量|待办：t007 Round 3 测试 minor 跟进|
|197|A|5|`docs/pending/todo/p012_stream_tokens_eviction_close_race.md`|已审|L1-L5 全量|待办：同 tab 驱逐关闭码偶发 1006|
|198|A|5|`docs/pending/todo/p013_ac001_static_frames_flake.md`|已审|L1-L5 全量|待办：AC-001 双页切换用例依赖静止出帧抖动|
|199|A|65|`docs/reviews/review_local_benchmark_20261027/review_benchmark.md`|已审 (历史)|L1-L65 全量|本地基准评审记录归档|
|200|A|45|`docs/reviews/review_v2_scope_20261027/review_disposition.md`|已审 (历史)|L1-L45 全量|范围处置评审记录归档|
|201|A|55|`docs/reviews/review_v2_scope_20261027/review_scope_initial.md`|已审 (历史)|L1-L55 全量|初始范围评审记录归档|
|202|A|55|`docs/reviews/review_v2_scope_20261027/review_scope_revised.md`|已审 (历史)|L1-L55 全量|修订范围评审记录归档|
|203|A|50|`docs/reviews/review_v2_scope_20261027/review_traceability.md`|已审 (历史)|L1-L50 全量|范围追溯评审记录归档|
|204|A|80|`docs/specs/access_control.md`|已审|L1-L80 全量|用户认证、Session Cookie、CSRF 与自动化 Token 契约|
|205|M|90|`docs/specs/browser_isolation.md`|已审|L1-L90 全量|Browser 双容器沙箱与 X11/Pulse 卷隔离契约|
|206|A|85|`docs/specs/profile_management.md`|已审|L1-L85 全量|前端多 Profile 切换与会话视图契约|
|207|A|110|`docs/specs/runtime_lifecycle.md`|已审|L1-L110 全量|容器启停、优雅停机与异常退避恢复契约|
|208|A|95|`docs/specs/runtime_persistence.md`|已审|L1-L95 全量|配置快照、SQLite WAL 与单写者持久化契约|
|209|A|120|`docs/specs/v2_runtime_validation.md`|已审|L1-L120 全量|t001 技术验证 Spike 验收规格|
|210|M|105|`docs/specs/webrtc_remote_display.md`|已审|L1-L105 全量|WebRTC 媒体流、UDP 端口与 8/30 仲裁契约|
|211|M|14|`docs/specs_index.md`|已审|L1-L14 全量|当前生效 spec 索引，废弃项已剔除|
|212|D|0|`docs/tasks/t001_v2_runtime_validation/task.md`|已审 (删除)|迁移核验|已迁入 docs/archive/tasks/|
|213|A|25|`docs/tasks/t008_v2_artifacts_automation/note.md`|已审 (任务)|L1-L25 全量|t008 任务笔记草案|
|214|A|74|`docs/tasks/t008_v2_artifacts_automation/task.md`|已审 (任务)|L1-L74 全量|t008 任务书规范|
|215|A|25|`docs/tasks/t009_v2_full_acceptance/note.md`|已审 (任务)|L1-L25 全量|t009 任务笔记草案|
|216|A|74|`docs/tasks/t009_v2_full_acceptance/task.md`|已审 (任务)|L1-L74 全量|t009 任务书规范|
|217|R093|25|`docs/tasks/t010_v2_data_migration/note.md`|已审 (任务)|L1-L25 全量|t010 任务笔记草案|
|218|A|74|`docs/tasks/t010_v2_data_migration/task.md`|已审 (任务)|L1-L74 全量|t010 任务书规范|
|219|A|25|`docs/tasks/t011_v2_remove_legacy/note.md`|已审 (任务)|L1-L25 全量|t011 任务笔记草案|
|220|A|73|`docs/tasks/t011_v2_remove_legacy/task.md`|已审 (任务)|L1-L73 全量|t011 任务书规范|
|221|A|25|`docs/tasks/t012_v2_docker_release/note.md`|已审 (任务)|L1-L25 全量|t012 任务笔记草案|
|222|A|73|`docs/tasks/t012_v2_docker_release/task.md`|已审 (任务)|L1-L73 全量|t012 任务书规范|
|223|A|25|`docs/tasks/t013_v2_profile_copy_reset/note.md`|已审 (任务)|L1-L25 全量|t013 任务笔记草案|
|224|A|73|`docs/tasks/t013_v2_profile_copy_reset/task.md`|已审 (任务)|L1-L73 全量|t013 任务书规范|
|225|A|25|`docs/tasks/t014_v2_clipboard_input/note.md`|已审 (任务)|L1-L25 全量|t014 任务笔记草案|
|226|A|75|`docs/tasks/t014_v2_clipboard_input/task.md`|已审 (任务)|L1-L75 全量|t014 任务书规范|
|227|M|35|`docs/tasks_index.json`|已审|JSON 结构核验|任务状态权威索引，t001-t007 标记 done|
|228|M|1159|`docs/v2_architecture_plan.md`|已审|L1-L1159 全量|v2.3 最终架构修订案，硬约束与范围豁免明确|
|229|M|85|`pyproject.toml`|已审|L1-L85 全量|项目元数据与依赖定义（SQLAlchemy 2, FastAPI, aiohttp）|
|230|A|1341|`schemas/openapi/cbrowser_v1.json`|已审 (生成)|JSON 校验 / 差异核验|OpenAPI 3.1 模式导出，与后端路由严格一致|
|231|A|148|`schemas/runtime/agent_protocol.json`|已审 (生成)|JSON 校验 / 结构核验|Browser Agent UDS 协议模式|
|232|A|136|`schemas/runtime/supervisor_protocol.json`|已审 (生成)|JSON 校验 / 结构核验|Supervisor 控制协议模式，Stop 请求字段必填|
|233|A|120|`schemas/stream/agent_protocol.json`|已审 (生成)|JSON 校验 / 结构核验|Stream Agent ↔ Gateway 协议模式|
|234|A|45|`scripts/export_openapi.py`|已审|L1-L45 全量|导出 OpenAPI 模式文件脚本|
|235|A|45|`scripts/export_stream_protocol.py`|已审|L1-L45 全量|导出 Stream Agent 协议模式脚本|
|236|A|45|`scripts/export_supervisor_protocol.py`|已审|L1-L45 全量|导出 Supervisor 协议模式脚本|
|237|A|262|`scripts/vendor_selkies_web.py`|已审|L1-L262 全量|官方 wheel 下载、SHA256 清单核对与 adapter 标签注入|
|238|A|38|`src/backend/cbrowser/adapters/database/migrations.py`|已审|L1-L38 全量|Alembic 自动升级与 PRAGMA 预配置|
|239|A|283|`src/backend/cbrowser/adapters/database/models.py`|已审|L1-L283 全量|SQLAlchemy 2.0 ORM 模型（8张核心表），级联完备|
|240|A|778|`src/backend/cbrowser/adapters/database/repository.py`|已审|L1-L778 全量|单写者仓储，不可变版本，幂等操作审计日志|
|241|A|67|`src/backend/cbrowser/adapters/database/session.py`|已审|L1-L67 全量|aiosqlite 引擎，PRAGMA WAL/busy_timeout，BEGIN IMMEDIATE|
|242|A|301|`src/backend/cbrowser/api/app.py`|已审|L1-L301 全量|FastAPI 应用工厂，输入脱敏，SQL 错误脱敏。见 SEC-003|
|243|A|152|`src/backend/cbrowser/api/internal_gateway.py`|已审|L1-L152 全量|Bearer 认证内部 Gateway RPC，校验会话与 Origin|
|244|A|102|`src/backend/cbrowser/api/internal_supervisor.py`|已审|L1-L102 全量|Bearer 认证 Supervisor RPC，受限配置与状态上报|
|245|A|18|`src/backend/cbrowser/api/main.py`|已审|L1-L18 全量|Control API 生产独立入口|
|246|A|481|`src/backend/cbrowser/api/runtime_coordinator.py`|已审|L1-L481 全量|意愿协调器与 SSE 广播器。发现 COR-001|
|247|A|201|`src/backend/cbrowser/api/v1/auth_router.py`|已审|L1-L201 全量|登录/登出/会话，Cookie 标志与自动化 Token CRUD|
|248|A|696|`src/backend/cbrowser/api/v1/router.py`|已审|L1-L696 全量|Profile CRUD、状态与事件接口。发现 ROB-001|
|249|A|5|`src/backend/cbrowser/auth/__init__.py`|已审|L1-L5 全量|导出核心类|
|250|A|75|`src/backend/cbrowser/auth/dependencies.py`|已审|L1-L75 全量|`require_user_session` 与 `require_csrf_and_origin` 依赖|
|251|A|50|`src/backend/cbrowser/auth/rate_limiter.py`|已审|L1-L50 全量|登录基于 IP 滑动窗口限流（5次/60s）|
|252|A|363|`src/backend/cbrowser/auth/service.py`|已审|L1-L363 全量|Argon2id 密码哈希、防时序攻击 dummy 验证与 Token 授权|
|253|A|418|`src/backend/cbrowser/domain/models.py`|已审|L1-L418 全量|领域对象模型与 Pydantic 校验|
|254|A|4|`src/backend/cbrowser/domain/runtime_policy.py`|已审|L1-L4 全量|2/10/30s 重试退避与 4 次失败阻断常数|
|255|A|5|`src/backend/cbrowser/gateway/__init__.py`|已审|L1-L5 全量|导出网关包|
|256|A|10|`src/backend/cbrowser/gateway/__main__.py`|已审|L1-L10 全量|网关运行入口|
|257|A|80|`src/backend/cbrowser/gateway/api_client.py`|已审|L1-L80 全量|Gateway 调 API 的内部 HTTP 客户端|
|258|A|116|`src/backend/cbrowser/gateway/config.py`|已审|L1-L116 全量|网关环境变量解析。发现 SEC-003 (p005)|
|259|A|80|`src/backend/cbrowser/gateway/registry.py`|已审|L1-L80 全量|Stream Agent 内存注册表与超时检查|
|260|A|260|`src/backend/cbrowser/gateway/rotation.py`|已审|L1-L260 全量|TURN 凭证换代与 Viewer 无损 ICE restart 协调|
|261|A|664|`src/backend/cbrowser/gateway/server.py`|已审|L1-L664 全量|信令隧道代理、身份校验与心跳循环。见 ARCH-001|
|262|A|5|`src/backend/cbrowser/rtc_config/__init__.py`|已审|L1-L5 全量|导出模块|
|263|A|50|`src/backend/cbrowser/rtc_config/credential.py`|已审|L1-L50 全量|coturn HMAC-SHA1 短期凭证算法|
|264|A|60|`src/backend/cbrowser/rtc_config/models.py`|已审|L1-L60 全量|RTC 配置数据结构与有效期参数|
|265|A|90|`src/backend/cbrowser/rtc_config/service.py`|已审|L1-L90 全量|独立客户端与服务端 RTC 配置生成服务|
|266|A|10|`src/backend/cbrowser/runtime_agent/__main__.py`|已审|L1-L10 全量|Browser Agent 启动入口|
|267|A|479|`src/backend/cbrowser/runtime_agent/agent.py`|已审|L1-L479 全量|UDS Agent，CDP 代理，自动 rearm 机制|
|268|A|180|`src/backend/cbrowser/runtime_agent/cdp_proxy.py`|已审|L1-L180 全量|CDP loopback 代理与下载行为监听|
|269|A|120|`src/backend/cbrowser/runtime_agent/event_storage.py`|已审|L1-L120 全量|运行退出与下载事件原子落盘与查询|
|270|A|150|`src/backend/cbrowser/runtime_agent/profile_defaults.py`|已审|L1-L150 全量|首次启动 Profile 偏好设置注入|
|271|A|80|`src/backend/cbrowser/runtime_agent/protocol.py`|已审|L1-L80 全量|UDS Agent 协议 DTO|
|272|A|750|`src/backend/cbrowser/runtime_agent/runner.py`|已审|L1-L750 全量|真实 CloakBrowser/Xvfb/Pulse 启动守护|
|273|A|94|`src/backend/cbrowser/runtime_agent/security.py`|已审|L1-L94 全量|启动参数安全白名单校验|
|274|A|90|`src/backend/cbrowser/runtime_agent/subsystems.py`|已审|L1-L90 全量|X11、PulseAudio 与浏览器 PID 健康探针|
|275|A|243|`src/backend/cbrowser/services/profile_service.py`|已审|L1-L243 全量|Profile 领域业务协调与 DB 异常映射|
|276|A|5|`src/backend/cbrowser/stream_agent/__init__.py`|已审|L1-L5 全量|导出模块|
|277|A|1153|`src/backend/cbrowser/stream_agent/agent.py`|已审|L1-L1153 全量|Stream Agent 核心协调。见 COR-002, ROB-002|
|278|A|72|`src/backend/cbrowser/stream_agent/boundary.py`|已审|L1-L72 全量|Stream 容器安全挂载边界验证|
|279|A|69|`src/backend/cbrowser/stream_agent/client_shim.py`|已审|L1-L69 全量|官方 Selkies 客户端 Web Locks 补丁脚本|
|280|A|110|`src/backend/cbrowser/stream_agent/config.py`|已审|L1-L110 全量|Stream Agent 运行时配置模型|
|281|A|667|`src/backend/cbrowser/stream_agent/ice_transport.py`|已审|L1-L667 全量|GenerationIceTransport 适配层，无损 ICE 重启|
|282|A|320|`src/backend/cbrowser/stream_agent/policy.py`|已审|L1-L320 全量|LiveCapturePolicyAgent 8/30 动态帧率单一仲裁|
|283|A|120|`src/backend/cbrowser/stream_agent/protocol.py`|已审|L1-L120 全量|Stream 信令与控制信封协议 DTO|
|284|A|90|`src/backend/cbrowser/stream_agent/x11_keymap.py`|已审|L1-L90 全量|原生 X11 键映射与修饰键处理|
|285|M|5|`src/backend/cbrowser/supervisor/__init__.py`|已审|L1-L5 全量|导出包|
|286|A|5|`src/backend/cbrowser/supervisor/__main__.py`|已审|L1-L5 全量|Supervisor 进程入口|
|287|A|33|`src/backend/cbrowser/supervisor/agent_credentials.py`|已审|L1-L33 全量|HMAC-SHA256 生成与验证 Stream Agent Token|
|288|A|222|`src/backend/cbrowser/supervisor/control_server.py`|已审|L1-L222 全量|Supervisor HTTP 控制面服务|
|289|A|30|`src/backend/cbrowser/supervisor/coordinator_lock.py`|已审|L1-L30 全量|基于 fcntl.flock 的数据根互斥锁|
|290|A|773|`src/backend/cbrowser/supervisor/core.py`|已审|L1-L773 全量|容器生命周期协调与状态上报。见 SEC-002 (p006)|
|291|A|1098|`src/backend/cbrowser/supervisor/docker_adapter.py`|已审|L1-L1098 全量|Docker API 适配。发现 PERF-001|
|292|A|187|`src/backend/cbrowser/supervisor/event_forwarder.py`|已审|L1-L187 全量|事件持久化磁盘脱机队列与重放|
|293|A|24|`src/backend/cbrowser/supervisor/file_storage.py`|已审|L1-L24 全量|0600 原子写入与目录 fsync 同步|
|294|A|70|`src/backend/cbrowser/supervisor/gateway_client.py`|已审|L1-L70 全量|Supervisor 调 Gateway 控制 RPC 客户端|
|295|A|261|`src/backend/cbrowser/supervisor/network_policy.py`|已审|L1-L261 全量|iptables-restore 内核级网络隔离策略注入|
|296|A|45|`src/backend/cbrowser/supervisor/operation_journal.py`|已审|L1-L45 全量|基于文件系统的操作幂等日志|
|297|A|160|`src/backend/cbrowser/supervisor/path_validator.py`|已审|L1-L160 全量|挂载路径校验与防逃逸。发现 SEC-001|
|298|A|79|`src/backend/cbrowser/supervisor/port_allocator.py`|已审|L1-L79 全量|UDP mux 端口池分配（30000–30991）|
|299|A|67|`src/backend/cbrowser/supervisor/protocol.py`|已审|L1-L67 全量|Supervisor RPC 请求与响应模型|
|300|A|606|`src/backend/cbrowser/supervisor/recovery_coordinator.py`|已审|L1-L606 全量|异常退出恢复与重试状态机。见 ARCH-001|
|301|A|162|`src/backend/cbrowser/supervisor/resource_monitor.py`|已审|L1-L162 全量|资源监控与配额派发循环|
|302|A|683|`src/backend/cbrowser/supervisor/resource_policy.py`|已审|L1-L683 全量|CPU 统计与动态配额降频决策|
|303|A|306|`src/backend/cbrowser/supervisor/runner.py`|已审|L1-L306 全量|Supervisor 守护进程服务装配与优雅退出|
|304|A|57|`src/backend/cbrowser/supervisor/selkies_tokens.py`|已审|L1-L57 全量|每实例生成独立 Selkies master/controller Token|
|305|A|151|`src/backend/cbrowser/supervisor/startup_gate.py`|已审|L1-L151 全量|容器启动门禁，等待网络策略注入后再 exec|
|306|M|297|`src/backend/diagnostics.py`|已审|L1-L297 全量|启动指纹、崩溃钩子与结构化运行事件日志脱敏|
|307|A|70|`src/backend/migrations/alembic.ini`|已审|L1-L70 全量|Alembic 配置|
|308|A|90|`src/backend/migrations/env.py`|已审|L1-L90 全量|Alembic 环境配置，支持外键与元数据同步|
|309|A|30|`src/backend/migrations/script.py.mako`|已审|L1-L30 全量|迁移脚本模板|
|310|A|216|`src/backend/migrations/versions/0001_initial_schema.py`|已审|L1-L216 全量|核心8张业务表初始化迁移|
|311|A|60|`src/backend/migrations/versions/0002_auth.py`|已审|L1-L60 全量|管理员与 Session 表迁移|
|312|M|11520|`src/frontend/package-lock.json`|已审 (锁文件)|依赖版本与锁定核验|锁定 TanStack Query 5、React 19、React Router 7|
|313|M|41|`src/frontend/package.json`|已审|L1-L41 全量|前端构建脚本与依赖定义。发现 p010|
|314|A|292|`src/frontend/src/app/AppLayout.tsx`|已审|L1-L292 全量|主布局、侧边栏、状态指示灯与启停控制|
|315|A|28|`src/frontend/src/app/RequireAuth.tsx`|已审|L1-L28 全量|路由登录鉴权守卫与重定向|
|316|A|70|`src/frontend/src/app/auth_guard.test.tsx`|已审 (测试)|L1-L70 全量|登录守卫单元测试|
|317|A|66|`src/frontend/src/app/providers.tsx`|已审|L1-L66 全量|QueryClient、I18n、Auth 与 SSE 同步桥|
|318|A|80|`src/frontend/src/app/router.test.tsx`|已审 (测试)|L1-L80 全量|路由配置与组件渲染测试|
|319|A|57|`src/frontend/src/app/router.tsx`|已审|L1-L57 全量|React Router 7 路由树定义|
|320|A|28|`src/frontend/src/features/artifacts/ProfileFilesPlaceholder.tsx`|已审|L1-L28 全量|文件下载功能占位页（明确指向 t008）|
|321|A|99|`src/frontend/src/features/auth/LoginPage.tsx`|已审|L1-L99 全量|登录页，密码认证与错误提示|
|322|A|21|`src/frontend/src/features/auth/redirect.ts`|已审|L1-L21 全量|重定向路径同源安全过滤，防开放重定向|
|323|A|95|`src/frontend/src/features/auth/useAuth.tsx`|已审|L1-L95 全量|认证上下文与会话探测钩子|
|324|A|28|`src/frontend/src/features/automation/ProfileAutomationPlaceholder.tsx`|已审|L1-L28 全量|CDP 自动化占位页（明确指向 t008）|
|325|A|120|`src/frontend/src/features/browser-session/BrowserSessionView.test.tsx`|已审 (测试)|L1-L120 全量|会话视图组件测试|
|326|A|102|`src/frontend/src/features/browser-session/BrowserSessionView.tsx`|已审|L1-L102 全量|核心 WebRTC Viewer 包装，嵌入 Selkies iframe 与诊断|
|327|A|110|`src/frontend/src/features/browser-session/SessionDiagnostics.tsx`|已审|L1-L110 全量|连接状态诊断浮层，展示 RTT、丢包与解码帧|
|328|A|555|`src/frontend/src/features/browser-session/adapter.ts`|已审|L1-L555 全量|Selkies 客户端适配层，Web Locks 防多标签冲突|
|329|A|90|`src/frontend/src/features/browser-session/adapter_restart.test.ts`|已审 (测试)|L1-L90 全量|ICE restart 适配层单元测试|
|330|A|25|`src/frontend/src/features/browser-session/audio_control.ts`|已审|L1-L25 全量|通过 postMessage 发送 pipelineControl 音频开关|
|331|A|110|`src/frontend/src/features/browser-session/audio_status.test.ts`|已审 (测试)|L1-L110 全量|音频状态采样与判定测试。见 p011 (t007_test_f013)|
|332|A|59|`src/frontend/src/features/browser-session/audio_status.ts`|已审|L1-L59 全量|基于 RTCPeerConnection 采样的音频状态推导|
|333|A|27|`src/frontend/src/features/browser-session/host_entry.tsx`|已审|L1-L27 全量|会话挂载入口|
|334|A|10|`src/frontend/src/features/browser-session/index.ts`|已审|L1-L10 全量|导出模块|
|335|A|85|`src/frontend/src/features/browser-session/media_controls.test.tsx`|已审 (测试)|L1-L85 全量|静音控制按钮与交互测试|
|336|A|7|`src/frontend/src/features/browser-session/selkies_adapter_entry.ts`|已审|L1-L7 全量|独立编译为 selkies_adapter.js 的打包入口|
|337|A|60|`src/frontend/src/features/browser-session/types.ts`|已审|L1-L60 全量|会话阶段与诊断数据类型定义|
|338|A|406|`src/frontend/src/features/browser-session/useBrowserSession.ts`|已审|L1-L406 全量|会话状态机、定时轮询与冻结恢复重建。发现 ARCH-002|
|339|A|168|`src/frontend/src/features/profiles/BrowserSessionPage.tsx`|已审|L1-L168 全量|浏览器会话主路由页，未运行提示与一键启动|
|340|A|289|`src/frontend/src/features/profiles/ProfileDetailPage.tsx`|已审|L1-L289 全量|Profile 配置详情、屏幕尺寸与“应用并重启”。发现 ARCH-002|
|341|A|156|`src/frontend/src/features/profiles/ProfileNewPage.tsx`|已审|L1-L156 全量|新建 Profile 表单。发现 ARCH-002|
|342|A|90|`src/frontend/src/features/profiles/useProfilesQuery.test.tsx`|已审 (测试)|L1-L90 全量|TanStack Query 钩子测试|
|343|A|221|`src/frontend/src/features/profiles/useProfilesQuery.ts`|已审|L1-L221 全量|Profile CRUD 与 SSE 实时同步逻辑|
|344|A|103|`src/frontend/src/features/settings/SettingsPage.tsx`|已审|L1-L103 全量|设置页，语言切换与服务健康度展示。发现 ARCH-002|
|345|M|180|`src/frontend/src/i18n.tsx`|已审|L1-L180 全量|中英文国际化字典与上下文|
|346|M|25|`src/frontend/src/main.tsx`|已审|L1-L25 全量|前端应用挂载入口|
|347|A|90|`src/frontend/src/shared/api/client.test.ts`|已审 (测试)|L1-L90 全量|API 客户端认证与 CSRF 拦截测试|
|348|A|213|`src/frontend/src/shared/api/client.ts`|已审|L1-L213 全量|统一封装 fetch、Cookie 与 CSRF Token|
|349|A|520|`src/frontend/src/shared/api/generated/cbrowser_v1.d.ts`|已审 (生成)|代码生成核验|OpenAPI 导出的纯 TypeScript 类型|
|350|A|85|`src/frontend/src/shared/api/sse.test.ts`|已审 (测试)|L1-L85 全量|SSE 客户端重连与事件解析测试|
|351|A|195|`src/frontend/src/shared/api/sse.ts`|已审|L1-L195 全量|SSE 客户端，支持 Last-Event-ID 与指数退避|
|352|A|33|`src/frontend/src/shared/api/types.ts`|已审|L1-L33 全量|前端业务模型强类型重导出与默认常量|
|353|A|23|`src/frontend/src/shared/components/BrowserSessionMount.tsx`|已审|L1-L23 全量|会话容器挂载组件|
|354|A|5|`src/frontend/src/vite-env.d.ts`|已审|L1-L5 全量|Vite 环境类型引用|
|355|M|35|`src/frontend/tsconfig.json`|已审|L1-L35 全量|TypeScript 编译选项配置|
|356|A|26|`src/frontend/vite.selkies.config.ts`|已审|L1-L26 全量|将 adapter.ts 构建为 IIFE 产物的专用 Vite 配置|
|357|A|2278|`tests/e2e/test_browser_runtime_e2e.py`|已审 (测试)|L1-L350 抽取核验|Browser Runtime 真实 Docker 容器 6 项 AC 验证|
|358|A|137|`tests/e2e/test_frontend_adapter_build.py`|已审 (测试)|L1-L137 全量|验证 selkies_adapter.js 构建产物存在与格式|
|359|A|234|`tests/e2e/test_frontend_app_auth_e2e.py`|已审 (测试)|L1-L234 全量|前端登录与路由重定向 E2E|
|360|A|1077|`tests/e2e/test_frontend_app_e2e.py`|已审 (测试)|L1-L250 抽取核验|完整应用栈 Playwright E2E。见 TST-001 (p013)|
|361|A|299|`tests/e2e/test_frontend_display_apply_e2e.py`|已审 (测试)|L1-L299 全量|分辨率修改与“应用并重启”E2E|
|362|A|199|`tests/e2e/test_frontend_ice_failure_e2e.py`|已审 (测试)|L1-L199 全量|ICE 连通性失败与重连 E2E|
|363|A|935|`tests/e2e/test_frontend_media_e2e.py`|已审 (测试)|L1-L935 全量|音视频播放与解码帧率 E2E|
|364|A|463|`tests/e2e/test_frontend_session_e2e.py`|已审 (测试)|L1-L200 抽取核验|多 Tab 并发、Web Locks 冲突解决与独立静音 E2E|
|365|A|24|`tests/e2e/test_frontend_session_vendor.py`|已审 (测试)|L1-L24 全量|验证 vendor 官方 Selkies 资源完整性|
|366|A|238|`tests/e2e/test_gateway_ac001_auth_e2e.py`|已审 (测试)|L1-L238 全量|Gateway HTTPS 登录与 Cookie 标志 E2E|
|367|A|405|`tests/e2e/test_gateway_ac003_media_e2e.py`|已审 (测试)|L1-L250 抽取核验|双 Chrome 媒体与 Gateway 重启恢复 E2E|
|368|A|424|`tests/e2e/test_gateway_ac005_relay_e2e.py`|已审 (测试)|L1-L250 抽取核验|relay-only 模式与 TURN 凭证换代 E2E|
|369|A|386|`tests/e2e/test_gateway_ac007_visibility_e2e.py`|已审 (测试)|L1-L200 抽取核验|页面可见性暂停恢复与 Gateway 接口 E2E|
|370|A|150|`tests/e2e/test_runtime_coordinator_e2e.py`|已审 (测试)|L1-L150 全量|API 驱动 Supervisor 启停 E2E|
|371|A|100|`tests/e2e/test_runtime_profile_defaults_e2e.py`|已审 (测试)|L1-L100 全量|Profile 默认配置注入 E2E|
|372|A|131|`tests/e2e/test_stream_client_identity_e2e.py`|已审 (测试)|L1-L131 全量|client_tab_id 与 resume_key 身份标识 E2E|
|373|A|63|`tests/e2e/test_stream_ice_commit_e2e.py`|已审 (测试)|L1-L63 全量|ICE 重启确认与异步接管 E2E|
|374|A|97|`tests/e2e/test_stream_ice_failure_e2e.py`|已审 (测试)|L1-L97 全量|ICE 失败负例与异常恢复 E2E|
|375|A|162|`tests/e2e/test_stream_ice_relay_e2e.py`|已审 (测试)|L1-L162 全量|多代 TURN 中继轮换 E2E|
|376|A|122|`tests/e2e/test_stream_rtc_config_e2e.py`|已审 (测试)|L1-L122 全量|Stream 侧 RTC 配置应用 E2E|
|377|A|1516|`tests/e2e/test_stream_runtime_e2e.py`|已审 (测试)|L1-L300 抽取核验|Stream Runtime 双 Viewer 与音频 E2E。见 TST-001 (p009)|
|378|A|588|`tests/e2e/test_stream_selkies_tokens_e2e.py`|已审 (测试)|L1-L250 抽取核验|Selkies Token 安全模式与代注入 E2E|
|379|A|113|`tests/e2e/test_stream_x11_keymap_e2e.py`|已审 (测试)|L1-L113 全量|X11 键映射与修饰键处理 E2E|
|380|A|62|`tests/e2e/test_supervisor_browser_network_e2e.py`|已审 (测试)|L1-L62 全量|Browser 独立网络策略隔离 E2E|
|381|A|82|`tests/e2e/test_supervisor_cache_initialization_e2e.py`|已审 (测试)|L1-L82 全量|只读缓存挂载与初始化 E2E|
|382|A|559|`tests/e2e/test_supervisor_container_graph_e2e.py`|已审 (测试)|L1-L559 全量|双容器依赖拓扑与启动顺序 E2E|
|383|A|424|`tests/e2e/test_supervisor_core_e2e.py`|已审 (测试)|L1-L200 抽取核验|Supervisor Core 双 Profile 启停与隔离 E2E|
|384|A|578|`tests/e2e/test_supervisor_infrastructure_network_e2e.py`|已审 (测试)|L1-L578 全量|基础设施网络挂载与通信 E2E|
|385|A|155|`tests/e2e/test_supervisor_ipv6_policy_e2e.py`|已审 (测试)|L1-L155 全量|IPv6 策略阻断与私有段隔离 E2E|
|386|A|556|`tests/e2e/test_supervisor_namespace_policy_e2e.py`|已审 (测试)|L1-L556 全量|iptables 命名空间网络策略隔离 E2E|
|387|A|65|`tests/e2e/test_supervisor_network_ownership_e2e.py`|已审 (测试)|L1-L65 全量|网络所有权与防抢占 E2E|
|388|A|1008|`tests/e2e/test_supervisor_offline_recovery_e2e.py`|已审 (测试)|L1-L1008 全量|离线事件队列与恢复重放 E2E|
|389|A|90|`tests/e2e/test_supervisor_orphan_helpers_e2e.py`|已审 (测试)|L1-L90 全量|遗留 helper 容器启动清理 E2E|
|390|A|255|`tests/e2e/test_supervisor_policy_failure_e2e.py`|已审 (测试)|L1-L255 全量|网络策略失败无条件回滚清理 E2E|
|391|A|760|`tests/e2e/test_supervisor_recovery_e2e.py`|已审 (测试)|L1-L760 全量|崩溃恢复与 2/10/30s 重试调度 E2E|
|392|A|62|`tests/e2e/test_supervisor_resource_capacity_e2e.py`|已审 (测试)|L1-L62 全量|资源配额与并发容量限制 E2E|
|393|A|138|`tests/e2e/test_supervisor_resource_monitor_e2e.py`|已审 (测试)|L1-L138 全量|真实容器 CPU 统计与监控采样 E2E|
|394|A|326|`tests/e2e/test_supervisor_resource_policy_e2e.py`|已审 (测试)|L1-L326 全量|8/30 FPS 配额下发 E2E|
|395|A|704|`tests/e2e/test_supervisor_retry_e2e.py`|已审 (测试)|L1-L704 全量|4次失败阻断与手动恢复 E2E|
|396|A|485|`tests/e2e/test_supervisor_startup_recovery_e2e.py`|已审 (测试)|L1-L485 全量|启动扫描现存容器与对账 E2E|
|397|A|110|`tests/fixtures/api_auth.py`|已审 (夹具)|L1-L110 全量|API 登录夹具与上下文创建|
|398|A|5|`tests/fixtures/frontend_app_probe/__init__.py`|已审 (夹具)|L1-L5 全量|导出包|
|399|A|135|`tests/fixtures/frontend_app_probe/harness.py`|已审 (夹具)|L1-L135 全量|前端应用真实拓扑测试夹具|
|400|A|5|`tests/fixtures/frontend_probe/__init__.py`|已审 (夹具)|L1-L5 全量|导出包|
|401|A|365|`tests/fixtures/frontend_probe/harness.py`|已审 (夹具)|L1-L365 全量|前端会话测试拓扑夹具|
|402|A|99|`tests/fixtures/frontend_probe/host_builder.py`|已审 (夹具)|L1-L99 全量|静态前端宿主构建夹具|
|403|A|5|`tests/fixtures/gateway_probe/__init__.py`|已审 (夹具)|L1-L5 全量|导出包|
|404|A|129|`tests/fixtures/gateway_probe/browser_oracle.py`|已审 (夹具)|L1-L129 全量|浏览器状态与 DOM 执行 oracle 夹具|
|405|A|31|`tests/fixtures/gateway_probe/caddyfile.py`|已审 (夹具)|L1-L31 全量|测试用 Caddyfile 模板生成|
|406|A|34|`tests/fixtures/gateway_probe/evidence.py`|已审 (夹具)|L1-L34 全量|测试证据保存辅助函数|
|407|A|428|`tests/fixtures/gateway_probe/selkies_assets.py`|已审 (夹具)|L1-L428 全量|Selkies 资源提取与注入夹具|
|408|A|2007|`tests/fixtures/gateway_probe/selkies_web_sha256.txt`|已审 (清单)|SHA256 清单核对|官方 Selkies 2.1.0 资源文件哈希列表|
|409|A|614|`tests/fixtures/gateway_probe/topology.py`|已审 (夹具)|L1-L614 全量|Gateway 测试拓扑管理夹具|
|410|A|340|`tests/fixtures/runtime_probe/audio_analyzer.py`|已审 (夹具)|L1-L340 全量|音频 PCM 分析工具代码|
|411|A|65|`tests/fixtures/runtime_probe/test_mitshm.c`|已审 (夹具)|L1-L65 全量|MIT-SHM C 源码|
|412|A|279|`tests/fixtures/stream_probe/chrome_relay.py`|已审 (夹具)|L1-L279 全量|Chrome TURN 轮换探针|
|413|A|25|`tests/fixtures/stream_probe/clipboard_oracle.py`|已审 (夹具)|L1-L25 全量|剪贴板哨兵测试夹具|
|414|A|85|`tests/fixtures/stream_probe/ice_commit_outcome.py`|已审 (夹具)|L1-L85 全量|ICE 提交结果判定探针|
|415|A|95|`tests/fixtures/stream_probe/ice_pending_close.py`|已审 (夹具)|L1-L95 全量|挂起连接关闭探针|
|416|A|138|`tests/fixtures/stream_probe/ice_relay_generations.py`|已审 (夹具)|L1-L138 全量|多代 relay 轮换探针|
|417|A|127|`tests/fixtures/stream_probe/ice_restart_failure.py`|已审 (夹具)|L1-L127 全量|ICE 重启失败处理探针|
|418|A|118|`tests/fixtures/stream_probe/ice_turn_timeout.py`|已审 (夹具)|L1-L118 全量|TURN 超时处理探针|
|419|A|36|`tests/fixtures/stream_probe/media_page.html`|已审 (夹具)|L1-L36 全量|媒体测试页面 HTML|
|420|A|96|`tests/fixtures/stream_probe/rtc_config_apply.py`|已审 (夹具)|L1-L96 全量|RTC 配置生效探针|
|421|A|153|`tests/fixtures/stream_probe/rtc_config_relay_only.py`|已审 (夹具)|L1-L153 全量|relay-only 候选限制探针|
|422|A|110|`tests/fixtures/stream_probe/x11_keymap_probe.py`|已审 (夹具)|L1-L110 全量|X11 键映射探针|
|423|A|14|`tests/fixtures/supervisor_container_probe/api_runtime.Dockerfile`|已审 (夹具)|L1-L14 全量|容器探针 API 运行时 Dockerfile|
|424|A|5|`tests/fixtures/supervisor_container_probe/api_runtime.Dockerfile.dockerignore`|已审 (夹具)|L1-L5 全量|排除配置|
|425|A|36|`tests/fixtures/supervisor_container_probe/gateway_container.py`|已审 (夹具)|L1-L36 全量|容器化 Gateway 探针入口|
|426|A|10|`tests/fixtures/supervisor_container_probe/gateway_runtime.Dockerfile`|已审 (夹具)|L1-L10 全量|容器探针 Gateway 运行时 Dockerfile|
|427|A|5|`tests/fixtures/supervisor_container_probe/gateway_runtime.Dockerfile.dockerignore`|已审 (夹具)|L1-L5 全量|排除配置|
|428|A|146|`tests/fixtures/supervisor_recovery_probe/gateway_contract.md`|已审 (夹具)|L1-L146 全量|Gateway 夹具接口契约规范|
|429|A|467|`tests/fixtures/supervisor_recovery_probe/gateway_fixture.py`|已审 (夹具)|L1-L467 全量|Supervisor 测试用 Gateway 夹具实现|
|430|A|520|`tests/fixtures/supervisor_recovery_probe/offline_fixture.py`|已审 (夹具)|L1-L520 全量|离线恢复多进程测试夹具|
|431|A|24|`tests/fixtures/supervisor_resource_probe/cpu_burner.py`|已审 (夹具)|L1-L24 全量|CPU 压力负载发生器|
|432|A|117|`tests/fixtures/supervisor_resource_probe/stream_monitor.py`|已审 (夹具)|L1-L117 全量|Stream 资源监控测试探针|
|433|A|156|`tests/integration/test_api_sse_events.py`|已审 (测试)|L1-L156 全量|SSE 接口认证、推送与断网重连集成测试|
|434|A|423|`tests/integration/test_auth_api.py`|已审 (测试)|L1-L423 全量|认证、Cookie 标志、限流与内部 RPC 集成测试|
|435|A|346|`tests/integration/test_gateway_control.py`|已审 (测试)|L1-L346 全量|Supervisor 调 Gateway 控制 RPC 集成测试|
|436|A|180|`tests/integration/test_gateway_fixtures.py`|已审 (测试)|L1-L180 全量|Gateway 测试夹具逻辑核验|
|437|A|651|`tests/integration/test_gateway_rotation.py`|已审 (测试)|L1-L651 全量|TURN 轮换与无损 ICE restart 握手集成测试|
|438|A|980|`tests/integration/test_gateway_signaling.py`|已审 (测试)|L1-L980 全量|信令隧道建立、跨 Profile 隔离与鉴权集成测试|
|439|A|35|`tests/integration/test_recovery_snapshot_failure.py`|已审 (测试)|L1-L35 全量|不可变快照获取失败中止恢复测试|
|440|A|582|`tests/integration/test_runtime_coordinator_integration.py`|已审 (测试)|L1-L582 全量|API 协调器与 Supervisor RPC 闭环集成测试|
|441|A|158|`tests/integration/test_sse_epoch_integration.py`|已审 (测试)|L1-L158 全量|API 重启后跨 epoch SSE 事件快照集成测试|
|442|A|62|`tests/integration/test_supervisor_gateway_client.py`|已审 (测试)|L1-L62 全量|Supervisor Gateway 客户端通信集成测试|
|443|A|70|`tests/integration/test_supervisor_gateway_fixture_auth.py`|已审 (测试)|L1-L70 全量|夹具鉴权配置集成测试|
|444|A|156|`tests/integration/test_supervisor_manual_retry.py`|已审 (测试)|L1-L156 全量|手动重试清零阻断状态集成测试|
|445|A|215|`tests/integration/test_supervisor_rpc.py`|已审 (测试)|L1-L215 全量|Supervisor 控制路由与鉴权集成测试|
|446|A|61|`tests/integration/test_supervisor_start_capacity.py`|已审 (测试)|L1-L61 全量|启动并发容量限制集成测试|
|447|A|118|`tests/integration/test_supervisor_status_truth.py`|已审 (测试)|L1-L118 全量|运行状态真实性与意愿保持集成测试|
|448|A|896|`tests/integration/test_v2_api_subprocess.py`|已审 (测试)|L1-L896 全量|API 子进程启动与接口可用性集成测试|
|449|A|82|`tests/unit/test_api_models_and_sse.py`|已审 (测试)|L1-L82 全量|DTO 模型与 SSE 格式化单元测试|
|450|A|317|`tests/unit/test_api_runtime_coordinator.py`|已审 (测试)|L1-L317 全量|协调器启动、退避与重试限制单元测试|
|451|A|158|`tests/unit/test_auth_models.py`|已审 (测试)|L1-L158 全量|认证 DTO 模型校验单元测试|
|452|A|261|`tests/unit/test_auth_service.py`|已审 (测试)|L1-L261 全量|密码哈希、防爆破与会话管理单元测试|
|453|A|33|`tests/unit/test_browser_readiness_fence.py`|已审 (测试)|L1-L33 全量|旧实例遗留文件防误判单元测试|
|454|A|41|`tests/unit/test_control_error_redaction.py`|已审 (测试)|L1-L41 全量|错误响应与日志防泄密脱敏单元测试|
|455|A|544|`tests/unit/test_domain_and_repository.py`|已审 (测试)|L1-L544 全量|仓储层 CRUD、快照与不可变性单元测试|
|456|A|98|`tests/unit/test_gateway_config.py`|已审 (测试)|L1-L98 全量|Gateway 配置加载与校验单元测试|
|457|A|76|`tests/unit/test_gateway_registry.py`|已审 (测试)|L1-L76 全量|Agent 注册表管理与过期剔除单元测试|
|458|A|150|`tests/unit/test_network_policy.py`|已审 (测试)|L1-L150 全量|网络策略规则生成单元测试|
|459|A|29|`tests/unit/test_network_policy_input_safety.py`|已审 (测试)|L1-L29 全量|网络策略输入防注入单元测试|
|460|A|126|`tests/unit/test_recovery_authority.py`|已审 (测试)|L1-L126 全量|恢复协调器决策权威性单元测试|
|461|A|24|`tests/unit/test_recovery_shutdown_safety.py`|已审 (测试)|L1-L24 全量|恢复器关闭时防死锁单元测试|
|462|A|123|`tests/unit/test_resource_fault_isolation.py`|已审 (测试)|L1-L123 全量|资源监控单 Profile 故障隔离单元测试|
|463|A|183|`tests/unit/test_rtc_config.py`|已审 (测试)|L1-L183 全量|RTC 凭证生成与轮换时间计算单元测试|
|464|A|384|`tests/unit/test_runtime_agent.py`|已审 (测试)|L1-L384 全量|Browser Agent 接口与生命周期单元测试|
|465|A|210|`tests/unit/test_runtime_agent_faults.py`|已审 (测试)|L1-L210 全量|Browser Agent 异常处理单元测试|
|466|A|75|`tests/unit/test_runtime_coordinator_background_tasks.py`|已审 (测试)|L1-L75 全量|协调器后台任务清理单元测试|
|467|A|231|`tests/unit/test_runtime_coordinator_stop_paths.py`|已审 (测试)|L1-L231 全量|协调器停止路径单元测试|
|468|A|139|`tests/unit/test_runtime_event_broadcaster_epoch.py`|已审 (测试)|L1-L139 全量|SSE 广播器 epoch 切换单元测试|
|469|A|111|`tests/unit/test_runtime_event_policy.py`|已审 (测试)|L1-L111 全量|运行事件策略与收敛判定单元测试|
|470|A|84|`tests/unit/test_runtime_instance_storage.py`|已审 (测试)|L1-L84 全量|实例事件磁盘存储单元测试|
|471|A|195|`tests/unit/test_runtime_persistence_guards.py`|已审 (测试)|L1-L195 全量|持久化防并发竞态单元测试|
|472|A|39|`tests/unit/test_runtime_profile_defaults.py`|已审 (测试)|L1-L39 全量|默认配置生成单元测试|
|473|A|182|`tests/unit/test_runtime_protocol.py`|已审 (测试)|L1-L182 全量|协议解析单元测试|
|474|A|924|`tests/unit/test_stream_agent_lifecycle.py`|已审 (测试)|L1-L924 全量|Stream Agent 启动与退出生命周期单元测试|
|475|A|179|`tests/unit/test_stream_agent_protocol_v2.py`|已审 (测试)|L1-L179 全量|Stream 协议 v2 消息处理单元测试|
|476|A|186|`tests/unit/test_stream_binding_guards.py`|已审 (测试)|L1-L186 全量|绑定防覆盖单元测试|
|477|A|364|`tests/unit/test_stream_capture_policy.py`|已审 (测试)|L1-L364 全量|画面捕获自适应策略单元测试|
|478|A|62|`tests/unit/test_stream_display_config.py`|已审 (测试)|L1-L62 全量|显示分辨率参数处理单元测试|
|479|A|18|`tests/unit/test_stream_ice_security.py`|已审 (测试)|L1-L18 全量|ICE 错误输出防泄密单元测试|
|480|A|667|`tests/unit/test_stream_ice_transport.py`|已审 (测试)|L1-L667 全量|GenerationIceTransport 状态转移单元测试|
|481|A|63|`tests/unit/test_stream_protocol_schema.py`|已审 (测试)|L1-L63 全量|Stream 协议模式校验单元测试|
|482|A|158|`tests/unit/test_stream_runtime.py`|已审 (测试)|L1-L158 全量|Stream 运行时各组件装配单元测试|
|483|A|292|`tests/unit/test_stream_selkies_tokens.py`|已审 (测试)|L1-L292 全量|Token 安全模式校验单元测试|
|484|A|471|`tests/unit/test_stream_transport_hardening.py`|已审 (测试)|L1-L471 全量|传输层容错加固单元测试|
|485|A|53|`tests/unit/test_supervisor_adapter_paths.py`|已审 (测试)|L1-L53 全量|适配器路径生成单元测试|
|486|A|26|`tests/unit/test_supervisor_agent_credentials.py`|已审 (测试)|L1-L26 全量|Agent Token 生成与验证单元测试|
|487|A|37|`tests/unit/test_supervisor_control_auth.py`|已审 (测试)|L1-L37 全量|控制接口 Bearer 认证单元测试|
|488|A|47|`tests/unit/test_supervisor_coordinator_lock.py`|已审 (测试)|L1-L47 全量|协调器排他文件锁单元测试|
|489|A|73|`tests/unit/test_supervisor_core.py`|已审 (测试)|L1-L73 全量|Supervisor 核心业务逻辑单元测试|
|490|A|126|`tests/unit/test_supervisor_display_config.py`|已审 (测试)|L1-L126 全量|容器显示配置单元测试|
|491|A|180|`tests/unit/test_supervisor_event_delivery.py`|已审 (测试)|L1-L180 全量|事件分发与确认单元测试|
|492|A|17|`tests/unit/test_supervisor_file_storage.py`|已审 (测试)|L1-L17 全量|原子文件操作单元测试|
|493|A|383|`tests/unit/test_supervisor_infrastructure_config.py`|已审 (测试)|L1-L383 全量|基础设施配置单元测试|
|494|A|28|`tests/unit/test_supervisor_operation_journal.py`|已审 (测试)|L1-L28 全量|幂等操作日志单元测试|
|495|A|30|`tests/unit/test_supervisor_port_recovery.py`|已审 (测试)|L1-L30 全量|端口恢复与冲突防范单元测试|
|496|A|41|`tests/unit/test_supervisor_profile_path_ownership.py`|已审 (测试)|L1-L41 全量|路径所有权校验单元测试|
|497|A|67|`tests/unit/test_supervisor_reconcile_fences.py`|已审 (测试)|L1-L67 全量|现存容器对账栅栏单元测试|
|498|A|534|`tests/unit/test_supervisor_recovery.py`|已审 (测试)|L1-L534 全量|恢复状态机单元测试|
|499|A|380|`tests/unit/test_supervisor_recovery_coordinator.py`|已审 (测试)|L1-L380 全量|恢复协调器各分支单元测试|
|500|A|166|`tests/unit/test_supervisor_resource_aggregation.py`|已审 (测试)|L1-L166 全量|容器资源聚合单元测试|
|501|A|397|`tests/unit/test_supervisor_resource_policy.py`|已审 (测试)|L1-L397 全量|CPU 降频策略计算单元测试|
|502|A|24|`tests/unit/test_supervisor_schema.py`|已审 (测试)|L1-L24 全量|Supervisor 协议模式单元测试|
|503|A|43|`tests/unit/test_supervisor_selkies_token_instances.py`|已审 (测试)|L1-L43 全量|Token 实例唯一性单元测试|
|504|A|146|`tests/unit/test_supervisor_selkies_token_isolation.py`|已审 (测试)|L1-L146 全量|Token 目录与 Browser 隔离单元测试|
|505|A|346|`tests/unit/test_supervisor_selkies_tokens.py`|已审 (测试)|L1-L346 全量|Token 文件生成与权限 0600 单元测试|
|506|A|289|`tests/unit/test_supervisor_startup_recovery.py`|已审 (测试)|L1-L289 全量|启动恢复扫描单元测试|
|507|A|39|`tests/unit/test_supervisor_stop_fence.py`|已审 (测试)|L1-L39 全量|停止操作代次栅栏单元测试|

______________________________________________________________________

*(终审报告结束)*
