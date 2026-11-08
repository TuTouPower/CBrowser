# bundle_local_backend_core

## responsibilities

- 管理 Profile、ProfileGroup、Proxy 实体配置、版本快照（不可变版本链）及生命周期意愿状态（desired_state）
- 作为系统中唯一的 SQLite 数据库写入者（开启 WAL 模式、busy_timeout=5000、BEGIN IMMEDIATE 写事务隔离）
- 管理管理员凭据（Argon2id 哈希、防时序哑元比对、滑动窗口限速）、用户登录会话及自动化凭证
- 维护真人优先控制权（Human-priority Control State，单调递增 generation 围栏，profile_controls 状态机）
- 提供环境缩略图（Preview，0600 权限、代次围栏）与 Artifact 产物存储（配额控制、两阶段原子落盘、断点恢复）
- 协调不可变字体集（Font Sets）完整性校验与 Profile 绑定
- 驱动网络配置版本状态机（Network Access Versioning, 127.0.0.1 / LAN 模式、Caddyfile 生成、Origin 派生）
- 通过 RuntimeCoordinator 与 Supervisor 通信协调容器沙箱启停、状态观测聚合及 SSE 实时广播

## interfaces

- GET /api/v1/health 服务健康探针
- POST /api/v1/auth/login, /logout, /session 用户会话接口
- GET/POST/DELETE /api/v1/automation/tokens 自动化凭证管理
- REST /api/v1/profiles/\* CRUD、克隆、重置、运行时状态与产物接口
- REST /api/v1/groups/*, /api/v1/proxies/* 实体管理接口
- GET /api/v1/font-sets 平台字体集只读清单
- GET /api/v1/events 运行时状态 SSE 实时广播
- WS /api/v1/automation/profiles/{id}/cdp CDP 隧道反向代理
- REST /api/v1/profiles/{id}/control/\* 真人优先控制权与弹窗交互
- REST /api/v1/internal/supervisor/\* 内部 Supervisor 专用 RPC
- REST /api/v1/internal/gateway/\* 内部 Gateway 专用 RPC

## dependencies

- FastAPI 0.115+
- Starlette
- Pydantic v2
- SQLAlchemy 2.0 (asyncio + aiosqlite)
- Alembic
- argon2-cffi
- httpx
- websockets

## flows

- 写控制流：客户端请求 -> require_csrf_and_origin -> ProfileService -> ProfileLockRegistry -> ProfileRepository -> write_transaction (BEGIN IMMEDIATE) -> 写入 SQLite -> RuntimeCoordinator.trigger_reconcile -> Supervisor RPC
- 事件流：Supervisor 调用 /api/v1/internal/supervisor/runtimes/events -> 写入 SQLite 审计表 -> emit_runtime_event_log -> RuntimeCoordinator.publish_profile_change -> SSE 客户端

## constraints

- 系统唯一 SQLite 写入者，严禁暴露或挂载 Docker Socket
- 敏感凭据严禁硬编码，禁止以明文记录进日志、响应体或异常中
- 严格受控 Origin 白名单，禁止非受信 Origin 写入

## decisions

- ADR 019: 真人优先控制权与单调递增 generation 围栏
- ADR 023: 单 baseline Alembic 修订，Profile 引用解耦的 Group/Proxy 实体
- ADR 024: 平台字体集 Content-Addressed 哈希与 Profile 绑定
- ADR 026: 局域网访问模式与动态 Caddy 反向代理重构

## evidence

- src/backend/cbrowser/api/app.py:76-220
- src/backend/cbrowser/api/runtime_coordinator.py:255-441,1144-1190
- src/backend/cbrowser/auth/service.py:109-232
- src/backend/cbrowser/services/profile_service.py:113-137,352-480
- src/backend/cbrowser/services/network_service.py:60-203
- src/backend/cbrowser/font_sets/manifest.py:143-156,272-345

## uncertainties

## Findings

- [Critical][95] src/backend/cbrowser/api/runtime_coordinator.py:1155,1157,1179,1181 — RuntimeCoordinator 致命 AttributeError 导致网络重构崩溃

    - ID: f_backend_core_attr_error; verification: static
    - Evidence: runtime_coordinator.py:1155: await self.client.post(url, headers=self.\_auth_headers(), ...); 类定义中仅初始化 self.\_client，从未定义 self.client 属性，亦从未定义 self.\_auth_headers() 方法
    - Impact: 管理员在受管 Docker 部署环境下执行网络模式切换（Local / LAN Switch）触发 rebuild_edge 时，任务必抛 AttributeError，网络重构直接中断并标记为失败
    - Fix: 在 RuntimeCoordinator 中添加 self.\_auth_headers() 方法或使用统一的私有认证头，并将 self.client 修正为 self.\_client

- [Critical][95] src/backend/cbrowser/api/v1/network_router.py:36; src/backend/cbrowser/api/app.py:415 — NetworkRouter 路由前缀缺失导致前端请求 404 与 Caddy 代理断裂

    - ID: f_backend_core_network_prefix; verification: static
    - Evidence: network_router.py:36 声明 prefix="/network"，app.py:415 直接 include_router 未传 prefix="/api/v1"; 前端 SettingsPage 全链请求 /api/v1/network/*，且 Caddyfile 仅反代 /api/* 与 /stream/\*
    - Impact: 前端网络设置与根证书下载端点在经过 Caddy 代理时全部 404，导致控制台无法获取网络配置与进行 LAN 模式切换
    - Fix: 将 network_router.py 的前缀改为 /api/v1/network 或在 app.py 挂载时显式添加 prefix="/api/v1"

- [High][90] src/backend/cbrowser/api/v1/control_router.py:74 — Control 模块自动化鉴权绕过代理 IP 解析导致限速伪造与 DoS 风险

    - ID: f_backend_core_control_client_ip; verification: static
    - Evidence: control_router.py:74 直接使用 request.client.host 作为 client_ip 传入 authorize_automation; 对比 auth_router.py 与 automation_router.py 均调用了 resolve_client_ip 解析受信任反向代理 X-Forwarded-For
    - Impact: 在反代部署下，request.client.host 恒为 Caddy 容器 IP。恶意外部请求向 control 路由灌入错误 Token 达到阈值后，Caddy IP 被全局限流，导致所有正常 Agent 遭遇连带拒绝服务
    - Fix: 引入 resolve_client_ip 并传入 request.headers.get("x-forwarded-for") 与 trusted_proxy_cidrs

- [High][90] src/backend/cbrowser/services/network_service.py:49,71-76,129-133 — NetworkService 崩溃导致活跃操作死锁与内存任务泄漏

    - ID: f_backend_core_network_active_leak; verification: static
    - Evidence: apply_configuration 生成后台任务后存入 self.\_background_tasks[op_id]，完成后未从字典移除; 若 API 进程在异步阶段异常终止，SQLite 中 active_op 永久处于非终态，重启后第 71-76 行冲突检查永久拦截后续任何 apply
    - Impact: 网络配置应用若遇异常崩溃，系统后续将永久无法再发起网络变更，且常驻后台任务字典只增不减
    - Fix: 为 \_background_tasks 增加完成回调清理，并在服务启动 lifespan 中回收未决孤儿 active_op 为 FAILED

- [High][90] src/backend/cbrowser/api/v1/font_sets_router.py:51-66; src/backend/cbrowser/font_sets/manifest.py:312-314 — GET /api/v1/font-sets 同步计算大文件 SHA-256 阻塞事件循环

    - ID: f_backend_core_font_sets_block; verification: static
    - Evidence: font_sets_router.py 的 list_font_sets 同步调用 check_font_set，对数百兆字体文件逐个同步计算 SHA-256; 未通过 asyncio.to_thread 移出主事件循环，亦未对不可变 Content-Addressed 字体集结果做缓存
    - Impact: 前端加载配置页或查询字体集时，FastAPI 主线程被同步 I/O 阻塞长达数百毫秒至数秒，导致并发请求与心跳包延迟
    - Fix: 在内存中基于 set_id 缓存已校验的字体集完整性状态，或在检查时使用 asyncio.to_thread 转移至工作线程

- [Medium][85] src/backend/cbrowser/api/v1/control_router.py:102,233; src/backend/cbrowser/api/app.py:394 — 控制权与实体路由器将 dict 传入 HTTPException.detail 破坏规范

    - ID: f_backend_core_http_exc_dict; verification: static
    - Evidence: control_router 抛出 HTTPException(detail={"code": exc.code, "message": str(exc)}); app.py 全局异常处理器直接执行 str(exc.detail)，响应体变为 Python repr 字符串（如 "{code: ...}"）
    - Impact: 客户端无法解析结构化错误码，破坏了 ErrorResponse 的 OpenAPI 契约与前端 Typed Client 的错误分支处理
    - Fix: 在全局 http_exception_handler 中支持对 dict 类型 detail 的解构提取，或统一抛出业务异常

- [Low][85] src/backend/cbrowser/api/v1/automation_router.py:158-166 — 自动化 Token 隧道注册遗漏 agent_instance_id 导致可观测性降级

    - ID: f_backend_core_automation_tunnel_agent_id; verification: static
    - Evidence: automation_cdp 成功解析出 token_id，但在调用 registry.register 时硬编码 agent_instance_id=None
    - Impact: 查询活跃自动化隧道列表时无法追踪到具体的 Token 身份 ID，降低审计可观测性
    - Fix: 将 registry.register 中的 agent_instance_id=None 替换为 agent_instance_id=token_id

- [High][95] src/backend/cbrowser/api/app.py:29,418; src/backend/cbrowser/api/v1/automation_router.py:21,250 — 违反零兼容负担铁律：偷偷保留 legacy_cdp_router 并用 include_in_schema=False 掩盖过时路径

    - ID: f_backend_core_legacy_cdp_router; verification: static
    - Evidence: app.py:418 显式调用 app.include_router(legacy_cdp_router, include_in_schema=False); automation_router.py:250 为旧路径 /profiles/{profile_id}/cdp 注册了 legacy_cdp_proxy WebSocket 路由; 直接违背核心架构铁律：'零兼容性负担：直接执行破坏性变更，完全不需要考虑前后兼容' 与 '架构设计层面不留兼容层：破坏性升级优于兼容包袱，直接移除过时路径'
    - Impact: 违背全仓架构铁律，在生产 API 中偷偷维持废弃的旧版 CDP 路由，增加维护割裂与潜在非授权访问风险
    - Fix: 彻底删除 legacy_cdp_router 及相关引用，仅保留 /api/v1/automation/profiles/{profile_id}/cdp

## views

```json
{
  "security": {
    "status": "completed",
    "reviewer": "agent_backend_core"
  },
  "correctness": {
    "status": "completed",
    "reviewer": "agent_backend_core"
  },
  "contracts": {
    "status": "completed",
    "reviewer": "agent_backend_core"
  },
  "performance": {
    "status": "completed",
    "reviewer": "agent_backend_core"
  },
  "design": {
    "status": "completed",
    "reviewer": "agent_backend_core"
  },
  "robustness": {
    "status": "completed",
    "reviewer": "agent_backend_core"
  },
  "tests": {
    "status": "completed",
    "reviewer": "agent_backend_core"
  },
  "documentation": {
    "status": "completed",
    "reviewer": "agent_backend_core"
  }
}
```

## files_reviewed

```json
[
  "src/backend/cbrowser/api/app.py",
  "src/backend/cbrowser/api/internal_artifacts.py",
  "src/backend/cbrowser/api/internal_gateway.py",
  "src/backend/cbrowser/api/internal_supervisor.py",
  "src/backend/cbrowser/api/main.py",
  "src/backend/cbrowser/api/runtime_coordinator.py",
  "src/backend/cbrowser/api/v1/artifact_router.py",
  "src/backend/cbrowser/api/v1/auth_router.py",
  "src/backend/cbrowser/api/v1/automation_router.py",
  "src/backend/cbrowser/api/v1/control_router.py",
  "src/backend/cbrowser/api/v1/deps.py",
  "src/backend/cbrowser/api/v1/font_sets_router.py",
  "src/backend/cbrowser/api/v1/groups_router.py",
  "src/backend/cbrowser/api/v1/network_router.py",
  "src/backend/cbrowser/api/v1/preview_router.py",
  "src/backend/cbrowser/api/v1/proxies_router.py",
  "src/backend/cbrowser/api/v1/router.py",
  "src/backend/cbrowser/api/v1/runtime_views.py",
  "src/backend/cbrowser/auth/__init__.py",
  "src/backend/cbrowser/auth/client_ip.py",
  "src/backend/cbrowser/auth/dependencies.py",
  "src/backend/cbrowser/auth/rate_limiter.py",
  "src/backend/cbrowser/auth/service.py",
  "src/backend/cbrowser/domain/models.py",
  "src/backend/cbrowser/domain/runtime_policy.py",
  "src/backend/cbrowser/font_sets/__init__.py",
  "src/backend/cbrowser/font_sets/manifest.py",
  "src/backend/cbrowser/runtime_event_log.py",
  "src/backend/cbrowser/services/artifact_service.py",
  "src/backend/cbrowser/services/control_service.py",
  "src/backend/cbrowser/services/network_service.py",
  "src/backend/cbrowser/services/profile_service.py",
  "src/backend/cbrowser/services/tunnel_registry.py",
  "src/backend/migrations/alembic.ini",
  "src/backend/migrations/env.py",
  "src/backend/migrations/script.py.mako",
  "src/backend/migrations/versions/0001_baseline_v2.py",
  "src/backend/migrations/versions/0002_fingerprint_platform.py"
]
```
