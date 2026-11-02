# bundle_local_backend_api_auth

## responsibilities

- 实现事实：本单元是 CBrowser v2 的 HTTP 控制面与身份域——FastAPI 应用工厂与异常信封（api/app.py）、公开 v1 路由（profiles/versions/runtime/artifacts/automation/auth）、两条内部服务 RPC 面（supervisor、gateway）、管理员会话认证（Argon2 口令校验、登录限流、会话签发/校验/吊销）、CSRF+Origin 写请求守卫、自动化令牌（cbat_ 前缀）全生命周期、Viewer/Automation 授权裁决、运行时协调器（向 Supervisor 收敛 desired/observed 状态）与 SSE 事件广播、领域 DTO 与运行时重试策略常量。
- 文档声明（AGENTS.md，未在本单元内核实）：系统为单机 Docker 部署、Caddy 承担 TLS 与反向代理、Chrome 为唯一官方外部客户端；本单元代码仅能印证 API 默认绑定 127.0.0.1（api/main.py:16-18），网关侧行为不在本单元范围。
- 实现事实（正向）：口令用 Argon2 校验且无管理员时执行 dummy verify 防时序攻击（auth/service.py:128-136）；会话与自动化令牌均只存 SHA-256 哈希（service.py:143-165、212-244）；服务令牌比较用 hmac.compare_digest（internal_gateway.py:33-42、internal_supervisor.py:30-44）；会话 Cookie 为 HttpOnly+Secure+SameSite=Strict（api/v1/auth_router.py:87-94）；校验错误响应剥离原始输入值防秘密回显（api/app.py:262-282）。

## interfaces

- 公开面（均在 /api/v1）：POST /auth/login（口令换会话 Cookie + CSRF token）、POST /auth/logout、GET /auth/session、POST/GET /automation/tokens、DELETE /automation/tokens/{token_id}、profiles CRUD 与 versions/duplicate/reset/stop、PATCH profiles/{id}/runtime/desired-state、POST /runtimes/bind|observed|events、profiles/{id}/artifacts 的上传/列表/下载/删除、GET /profiles/{id}/automation、GET /events（SSE）、GET /health（唯一免认证公开端点）。
- 内部面（include_in_schema=False）：/api/v1/internal/supervisor/*（Bearer 服务令牌，复用 v1 handler 子集 + artifacts/downloads 上报）、/api/v1/internal/gateway/*（Bearer 服务令牌，viewer-authorize / automation-authorize / profiles/{id}/runtime）。
- WebSocket 面：/api/v1/automation/profiles/{profile_id}/cdp 与旧路径 /api/profiles/{profile_id}/cdp，以 cbat_ 令牌在握手期授权后向 Supervisor 透传 CDP（api/v1/automation_router.py:83-167）。
- 错误信封统一为 {error, message, retryable}（api/app.py:186-317 的异常处理器族），与 domain/models.py 的 ErrorResponse/ValidationErrorResponse 对应。

## dependencies

- cbrowser.services.profile_service.ProfileService 与 cbrowser.services.artifact_service.ArtifactService（经 app.state 与 dependency_overrides 注入，api/app.py:126-159）。
- cbrowser.adapters.database 的 ORM 模型与 write_transaction（auth/service.py 直接读写 Admin/Session/AutomationToken/AuditEvent/Profile 表）。
- cbrowser.gateway.endpoint.normalize_origin/normalize_origins（Origin 归一化的单一来源，auth/dependencies.py:63-71 与 app.py:95-102 共用）。
- cbrowser.secret_files.read_secret_file（相邻文件，已核对：拒绝组/其他可读权限、最小 32 字节）供 supervisor/gateway 令牌文件读取。
- 第三方：FastAPI/Starlette、SQLAlchemy async、argon2-cffi、httpx（协调器 RPC，timeout=10s、trust_env=False）、websockets（CDP 隧道）。

## flows

- 登录：POST /auth/login → resolve_client_ip（仅信任 CBROWSER_TRUSTED_PROXY_CIDRS 内的 XFF）→ AuthService.authenticate_admin（限流层检查→Argon2 校验→失败计数）→ create_session 写会话行 → 设置 cbrowser_session（HttpOnly）与 cbrowser_csrf（可读）两个 Cookie 并在响应体返回 csrf_token。
- 写请求守卫：profile_router 与 auth/artifact 写路由经 require_csrf_and_origin——先 require_user_session 校验 Cookie 会话，再对 POST/PUT/PATCH/DELETE 比较 X-CSRF-Token（hmac.compare_digest）并校验 Origin/Referer 归一化后属于 app.state.allowed_origins；allowed_origins 为空时 lifespan 直接拒绝启动（app.py:95-102）。
- 自动化授权：CDP WebSocket 或 Gateway RPC 携带 cbat_ 令牌 → authorize_automation 按 token_hash 查行、查吊销、比对 profile_ids 白名单、确认 profile 存在；每次拒绝都写一条 AuditEvent（见 finding f_backend_api_auth_01）。
- 运行时收敛：desired-state 变更 → RuntimeCoordinator.trigger_reconcile → 带 Supervisor Bearer 令牌 POST /supervisor/v1/profiles/start|stop（指数退避，running 意图默认不限重试、stopped 默认 5 次）→ 结果经 RuntimeEventBroadcaster（1000 条环形历史 + 每订阅者 100 队列）推给 SSE 订阅者。
- 内部 Supervisor RPC：supervisor_router 以 require_supervisor 为唯一守卫，直接挂载 v1 的 list/get profile、get version、get runtime、set desired-state、bind、observed、events 八个 handler 函数（internal_supervisor.py:57-99）。

## constraints

- 单一管理员模型：用户名固定为 admin（auth/service.py:43-55、97-109），无多用户/角色概念，所有会话权限等价。
- 启动硬约束：CBROWSER_ALLOWED_ORIGINS 必须至少含一个归一化后合法的 Origin，否则应用拒绝启动（api/app.py:95-102）。
- 服务令牌文件：supervisor/gateway 令牌经文件注入，文件权限不得含组/其他位且内容 ≥32 字节（secret_files.read_secret_file）；未配置时对应内部面返回 503 而非降级放行（internal_gateway.py:28-44、internal_supervisor.py:30-44）。
- 会话绝对过期 12 小时（create_session 默认 expire_hours=12），无滑动续期、无并发会话上限；自动化令牌无过期、仅靠吊销失效（见 finding f_backend_api_auth_05）。
- 限流与事件广播均为进程内内存状态（auth/rate_limiter.py、runtime_coordinator.py:33-46），隐含单进程部署假设；多 worker 部署将使限流预算与 SSE 历史按进程分裂（代码内未声明该约束）。

## decisions

- 授权挂载点决策：handler 函数自身不带任何认证依赖，认证完全由所挂载 Router 的 dependencies 决定——profile_router 统一挂 require_csrf_and_origin（api/v1/router.py:56），supervisor_router 只挂 require_supervisor 并复用同一批 handler（internal_supervisor.py:57-99）。该决策使同一 handler 在两个面上获得不同授权语义（见 finding f_backend_api_auth_02）。
- CSRF 采用服务端会话行内的 csrf_token 与请求头常时比较，而非 Cookie 双提交比较；cbrowser_csrf Cookie 仅供前端读取回填（auth/dependencies.py:44-56、auth_router.py:95-102）。
- 幂等键三通道归一：Idempotency-Key 头优先于 X-Operation-ID 头、再于 operation_id 查询参数（api/v1/runtime_views.py:26-33），且该契约已写入 OpenAPI 参数表（schemas 中 21 处参数记录已核对）。
- 内部面不进公开契约：supervisor/gateway/internal-artifacts 三个 Router 均 include_in_schema=False，schemas/openapi/cbrowser_v1.json 只覆盖公开面（见 finding f_backend_api_auth_11）。

## evidence

- src/backend/cbrowser/auth/service.py:106-141（限流+Argon2+dummy verify 登录校验）
- src/backend/cbrowser/auth/service.py:307-371（authorize_automation 与每次拒绝写审计 _record_auth_denied）
- src/backend/cbrowser/auth/dependencies.py:39-79（会话+CSRF+Origin 守卫全实现）
- src/backend/cbrowser/api/v1/router.py:56（profile_router 统一守卫）、706-835（bind/observed/events 三个运行时上报 handler）
- src/backend/cbrowser/api/internal_supervisor.py:57-99（复用 v1 handler 的挂载表）
- src/backend/cbrowser/api/app.py:95-102（allowed_origins 启动硬约束）、161-193（FastAPI 构造未限制 docs/openapi）
- schemas/openapi/cbrowser_v1.json 全量 22 条路径与 components 已程序化核对：securitySchemes 为空、无任何 operation 级 security；POST /api/v1/auth/login 仅声明 200/422（文件第 1805 行起）
- tests/unit/test_auth_service.py、tests/unit/test_auth_client_ip.py、tests/integration/test_auth_api.py 的测试名清单已核对（限流、CSRF、XFF、内部 gateway、秘密不回显等有用例名对应；文件内容属其他单元未细读）

## uncertainties

- Caddy 网关是否对外屏蔽 /docs、/openapi.json 与 /api/v1/internal/* 路径不在本单元文件内，finding f_backend_api_auth_08 的实际可达性取决于该配置。
- 带 chunked 编码（无 Content-Length）的 artifact 上传是否在 ArtifactService 内被限额，本单元只能确认 router 层对带长度请求做了 413 预检（api/v1/artifact_router.py:69-82），服务层实现属其他单元。
- src/backend/tests/test_auth.py 所测的 legacy backend 包是否仍在部署产物中，影响 finding f_backend_api_auth_13 的定性（死测试 vs 旧面活测试）；本单元仅确认其与 v2 代码无引用关系。
- repo 根 tests/ 下本单元的单测/集成测试仅核对了文件与用例名存在性，未逐行审阅断言质量，断言有效性由对应测试单元负责。

## Findings

- [Medium][90] src/backend/cbrowser/auth/service.py:307-371 — 每次被拒绝的自动化授权都会写一条审计数据库记录，未认证请求可放大为无界 DB 写入
  - ID: f_backend_api_auth_01; verification: static
  - Evidence: authorize_automation 对 invalid_token_format、token_not_found、token_revoked、profile_unauthorized、profile_not_found 五种拒绝一律调用 _record_auth_denied（service.py:307-353），后者在 write_transaction 中 INSERT 一条 AuditEventModel（service.py:357-371）。; 两个调用入口均在身份确认前可达：CDP WebSocket 握手（api/v1/automation_router.py:83-95，任意来源可发起）和 Gateway automation-authorize RPC（api/internal_gateway.py:110-127）。; 授权路径无限流、无去重、无审计写入上限；令牌格式校验仅要求 cbat_ 前缀（service.py:310），随机后缀即可稳定触发 SELECT + INSERT。
  - Impact: 未认证攻击者（或经 Gateway 的外部 Viewer 侧请求）可批量提交伪造令牌，迫使 SQLite 持续执行写事务：审计表无界增长、写锁竞争拖慢全部控制面请求（含合法登录与 profile 操作），构成低成本拒绝服务放大。
  - Fix: 对未命中任何令牌行（unknown/token_not_found）的拒绝改为仅日志不落库，或对审计写入加聚合/采样与按来源限流；至少为 entity_id='unknown' 的拒绝设置独立上限并给 AuditEvent 表加保留策略。

- [Medium][85] src/backend/cbrowser/api/v1/router.py:706-835 — Supervisor 运行时上报端点同时挂在用户会话面上，且 handler 自身无授权、授权语义完全取决于挂载的 Router
  - ID: f_backend_api_auth_02; verification: static
  - Evidence: bind_runtime、report_observed_state、report_runtime_event 三个本属 Supervisor 上报通道的 handler 定义在 profile_router 上（router.py:706-835），profile_router 的唯一守卫是管理员会话+CSRF（router.py:56 的 require_csrf_and_origin），因此浏览器会话可直接绑定运行时实例、伪造 observed 状态与 exit 事件。; 同一批 handler 函数又被 internal_supervisor.py:57-99 原样挂到只挂 require_supervisor 的 supervisor_router 上；handler 签名内没有任何认证依赖，授权是挂载约定而非代码属性——未来任一处误挂载即静默失去对应守卫。; internal_supervisor.py:57-58 的注释自述该服务面意图为『配置读取、运行时意图与上报，永不 Profile CRUD』，但反向边界（用户面不得行使 Supervisor 上报权）在代码中不存在。
  - Impact: 在单管理员模型下影响受限，但它使强度弱得多的浏览器会话凭据（Cookie，可经 XSS/CSRF 面获得）等价于 32 字节文件注入的 Supervisor 服务令牌，可伪造实例绑定与退出事件干扰运行时收敛与自动重启策略；同时挂载式授权使后续维护极易误开放端点。
  - Fix: 将 bind/observed/events 从 profile_router 拆到独立的 service-only Router（仅 require_supervisor），用户面如需保留应另设显式只读/意图端点；或给 handler 增加显式授权依赖参数，使授权随函数走而非随挂载走。

- [Medium][95] schemas/openapi/cbrowser_v1.json:1-3612 — OpenAPI 契约完全未声明任何安全方案，与实现的会话+CSRF+Bearer 认证现实脱节
  - ID: f_backend_api_auth_03; verification: static
  - Evidence: 程序化核对 cbrowser_v1.json：components.securitySchemes 为空对象、全文件无顶层 security、22 条路径的全部 operation 均无 security 字段。; 实现侧除 POST /auth/login 与 GET /health 外所有公开路由都要求 cbrowser_session Cookie，写操作还要求 X-CSRF-Token 头与合法 Origin（auth/dependencies.py:39-79、api/v1/router.py:56）；内部面要求 Bearer 服务令牌（internal_gateway.py:22、internal_supervisor.py:21）。; 契约中同样没有 X-CSRF-Token 头参数（已核对全部 operation 参数表，仅有 Idempotency-Key/X-Operation-ID/operation_id 共 21 处）。
  - Impact: schemas/ 是跨服务接口契约权威位置；前端、网关与第三方消费方从契约无法得知认证方式与 CSRF 要求，生成的客户端默认不带凭据，契约驱动的测试/网关校验也会把 401/403 当作实现违约，长期必然漂移。
  - Fix: 在契约中定义 cookie 会话（apiKey/cookie: cbrowser_session）、CSRF 头与内部 Bearer 三个 securitySchemes，并给除 login/health 外的 operation 标注 security 与 X-CSRF-Token 参数；契约变更走 AGENTS.md 规定的 task 流程。

- [Medium][95] schemas/openapi/cbrowser_v1.json:1805-1950 — 契约声明的响应码集合系统性遗漏实现实际返回的 401/403/404/413/429/507
  - ID: f_backend_api_auth_04; verification: static
  - Evidence: POST /api/v1/auth/login 契约仅 200/422（cbrowser_v1.json:1805 起），实现实际返回 401（凭据错误）与 429+Retry-After（限流）（api/v1/auth_router.py:64-80）。; GET /api/v1/auth/session 契约仅 200，实现在无会话时返回 401（auth_router.py:131-138 经 require_user_session）；全契约仅 GET /events 一处声明 401，无任何 operation 声明 403（CSRF/Origin 失败，auth/dependencies.py:50-75）。; DELETE /api/v1/automation/tokens/{token_id} 契约仅 204/422，实现对不存在/已吊销返回 404（auth_router.py:196-209）；artifacts 四个 operation 契约仅 200/201/204/422，实现经 _raise_artifact_error 返回 400/404/413/507（api/v1/artifact_router.py:37-46）。
  - Impact: 消费方按契约处理错误分支时会漏掉最常见的失败模式（未登录、限流、配额超限），前端与网关的重试/提示逻辑与真实行为不一致；429 的 Retry-After 语义未入契约使限流退避无法被正确实现。
  - Fix: 按各 handler 的实际异常映射逐 operation 补齐响应码与 ErrorResponse 引用，重点补 login 的 401/429（含 Retry-After 头定义）、全部需认证 operation 的 401/403、tokens DELETE 的 404、artifacts 的 400/404/413/507；后续以契约-实现一致性检查防再漂移。

- [Low][90] src/backend/cbrowser/auth/service.py:212-244 — 自动化令牌没有过期时间，只能靠人工吊销失效
  - ID: f_backend_api_auth_05; verification: static
  - Evidence: create_automation_token 创建的 AutomationTokenModel 只含 created_at/revoked/revoked_at，无 expires_at（service.py:212-244）。; authorize_automation 的放行条件只有『哈希命中、未吊销、profile 在白名单、profile 存在』，不查任何时效（service.py:307-353）。; 对比用户会话有 12 小时绝对过期（service.py:143-165），长期凭据反而无时效约束。
  - Impact: cbat_ 令牌一旦泄漏（日志、脚本仓库、CI 变量），在被人工发现并吊销前可无限期接管其白名单内 profile 的完整 CDP 控制权，且系统无到期自动失效兜底。
  - Fix: 给令牌增加 expires_at（创建时可配 TTL、设默认上限），authorize_automation 中按过期拒绝并写审计；或在 spec 明确记录『永不过期』为有意决策及补偿控制（轮换流程）。

- [Low][90] src/backend/cbrowser/auth/service.py:167-197 — 过期会话行从不清理，sessions 表随登录次数无界增长
  - ID: f_backend_api_auth_06; verification: static
  - Evidence: get_valid_session 对过期行只是返回 None，不删除该行（service.py:167-197）；create_session 每次登录 INSERT 一行新会话（service.py:143-165）。; 全 service 内只有 revoke_session 按 token 删除（登出路径），无任何按 expires_at 的批量清理或启动时清扫。
  - Impact: 长期运行后 sessions 表积累大量已过期行，每次会话校验按 token_hash 查询虽走索引、影响有限，但表与库文件持续膨胀，且残留的过期 token 哈希扩大了离线比对面。
  - Fix: 在 get_valid_session 命中过期行时顺带删除，或在 lifespan 启动/定时任务中按 expires_at 批量清扫；同时可考虑登录时吊销同管理员的旧会话。

- [Low][80] src/backend/cbrowser/auth/rate_limiter.py:65-77 — retry_after_seconds 未先修剪全局失败队列即按其长度与队首计算等待时间
  - ID: f_backend_api_auth_07; verification: static
  - Evidence: retry_after_seconds 对 per-source 队列先 _trim 再判断（rate_limiter.py:68-71），但对全局队列直接用 len(self._global_failures) 与 self._global_failures[0] 计算（rate_limiter.py:72-75），中间没有按 global_window_seconds 修剪。; rate_limit_layer 调用时虽会修剪全局队列（rate_limiter.py:56），但 retry_after 是在 authenticate_admin 返回 rate_limited 后由路由层再次独立调用（auth/service.py:143-144、api/v1/auth_router.py:70-74），两次调用之间窗口边界可跨越。
  - Impact: 在全局窗口刚过期而 per-source 仍触发限流的边界场景，Retry-After 可能把已过期的全局等待叠加进去，给出远大于实际需要的等待秒数，误导客户端退避（仅影响提示值，不影响放行判定）。
  - Fix: retry_after_seconds 开头对全局队列执行与 rate_limit_layer 相同的 _trim(now - global_window_seconds) 后再计算。

- [Low][70] src/backend/cbrowser/api/app.py:161-170 — FastAPI 默认开放 /docs 与 /openapi.json，未认证即可获取完整 API 结构
  - ID: f_backend_api_auth_08; verification: suspected
  - Evidence: create_app 构造 FastAPI 时未设置 docs_url/redoc_url/openapi_url（app.py:161-170），Starlette 默认在 /docs、/redoc、/openapi.json 提供交互文档与完整 schema。; 应用默认绑定 127.0.0.1（api/main.py:16-18），但 AGENTS.md 声明经 Caddy 反向代理对外提供界面，代理是否屏蔽这三个路径不在本单元代码内。
  - Impact: 若 Caddy 按前缀透传 /docs 或 /openapi.json，未认证访问者可拿到含内部端点形态、参数与错误模型的完整 API 地图，降低攻击侦察成本（内部 Router 虽 include_in_schema=False 不出现在 schema 中，但公开面全量暴露）。
  - Fix: 在 create_app 中显式关闭或收敛 docs/openapi 暴露（如 docs_url=None、openapi_url=None），或确认并记录网关层屏蔽规则后在本处注明依据。

- [Low][85] src/backend/cbrowser/api/internal_supervisor.py:30-36 — 内部守卫在 app.state 未初始化时抛 AttributeError/RuntimeError，落成无语义的 500 而非 503
  - ID: f_backend_api_auth_09; verification: static
  - Evidence: require_supervisor 直接属性访问 request.app.state.supervisor_token（internal_supervisor.py:34），state 未设置时抛 AttributeError，只能被 app.py:304-317 的兜底处理器变成 internal_server_error。; 同类模式：get_auth_service 在 auth_service 缺失时 raise RuntimeError（auth/dependencies.py:12-16），而 internal_artifacts 的 get_artifact_service 对同类情况明确返回 503（api/internal_artifacts.py:20-24），处理口径不一致。; 对比 require_gateway 对 token 为 None 的情况显式返回 503『not configured』（internal_gateway.py:31-36），说明代码库已有正确范式未被这两处采用。
  - Impact: 测试、局部挂载或 lifespan 异常中断等场景下，内部 RPC 与全部需认证路由以 500 形式失败，掩盖『服务未配置』的真实原因，误导网关侧的重试与告警判断。
  - Fix: require_supervisor 改用 getattr(request.app.state, 'supervisor_token', None) 并在 None 时走既有 503 分支；get_auth_service 同步改为抛 HTTPException(503) 或保持 RuntimeError 但在应用层映射为 503。

- [Info][90] src/backend/cbrowser/api/runtime_coordinator.py:153-165 — RuntimeCoordinator 将 Supervisor 的 SecretStr 令牌摊平为普通 str 属性长期持有
  - ID: f_backend_api_auth_10; verification: static
  - Evidence: 构造时 token_val 经 get_secret_value() 取出并存入 self._token_str（runtime_coordinator.py:153-165），后续所有 RPC 直接用该明文属性拼 Authorization 头（runtime_coordinator.py:382、425、461）。; 其余持有方均以 SecretStr 形态保存同一令牌（app.state.supervisor_token、read_supervisor_token 返回 SecretStr，internal_supervisor.py:18-24），唯独协调器放弃了 SecretStr 对 repr/日志意外的遮蔽。
  - Impact: 对象被日志、调试转储或异常上下文打印时，明文令牌失去最后一道遮蔽；当前代码未发现直接打印协调器对象的路径，故仅为纵深防御层面的弱化。
  - Fix: 协调器内部保留 SecretStr，仅在构造请求头时临时 get_secret_value()；或明确 __repr__ 排除令牌字段。

- [Info][90] src/backend/cbrowser/api/internal_gateway.py:49-52 — 内部面与 CDP WebSocket 同处 /api/v1 命名空间却完全不在 v1 契约清单内
  - ID: f_backend_api_auth_11; verification: static
  - Evidence: gateway_router 前缀 /api/v1/internal/gateway（internal_gateway.py:49-52）、supervisor_router 前缀 /api/v1/internal/supervisor（internal_supervisor.py:52-55）、CDP WebSocket 在 /api/v1/automation/profiles/{profile_id}/cdp（automation_router.py:83），三者均不在 schemas/openapi/cbrowser_v1.json 的 22 条路径中（已全量核对）。; 三个 Router 以 include_in_schema=False 注册（api/app.py:336-341），运行时生成的 /openapi.json 同样不含内部面。
  - Impact: 以 cbrowser_v1.json 作为 /api/v1 全量清单的消费方（审计、网关路由核对、契约测试）会漏掉权限最高的内部面与 CDP 通道；该遗漏若为有意，应在契约文件或 schemas 目录中显式声明内部面另行管理的位置。
  - Fix: 在 schemas/ 下为内部面单独立契约文件或在 cbrowser_v1.json 的 info.description 中声明内部面不纳入本契约及其权威定义位置。

- [Low][60] src/backend/cbrowser/api/runtime_coordinator.py:82-125 — SSE 订阅的初始快照与实时队列存在乱序窗口，快照事件占用序号却不入历史使续传语义含糊
  - ID: f_backend_api_auth_12; verification: suspected
  - Evidence: subscribe 先把队列加入 _subscribers（runtime_coordinator.py:84-85），再 await initial_snapshot_provider 生成快照（runtime_coordinator.py:104-120）；此间 publish 的实时事件进入队列，要在快照全部 yield 后才被消费，客户端可能在收到较新快照后又收到较旧的排队事件，状态短暂回退。; 快照事件在锁内占用 _next_event_id 序号（runtime_coordinator.py:113-116）但从未 append 到 _history；重连时以快照 id 作 Last-Event-ID，_parse 与历史区间判断（runtime_coordinator.py:92-102）基于 history 的 min/max 序号，可能命中区间而回放出与快照时点不严格对应的事件段。
  - Impact: 前端运行时状态可能短暂闪回旧值；断线续传在快照边界附近的行为未经定义，极端情况下重复或跳过个别状态事件（状态类事件可被后续全量覆盖，故影响限于短暂不一致）。
  - Fix: 快照生成期间先不注册队列、待快照完成后注册并补发注册间隙的事件，或让快照事件同样进入 _history 并明确 Last-Event-ID 指向快照 id 时的回放语义，并补对应时序测试。

- [Info][90] src/backend/tests/test_auth.py:1-46 — 名为 test_auth.py 的后端测试文件测的是 legacy 上游 backend 包，与本单元 v2 认证实现无任何引用关系
  - ID: f_backend_api_auth_13; verification: static
  - Evidence: src/backend/tests/test_auth.py 的 fixture 导入 from backend import main 并 monkeypatch main.AUTH_TOKEN、main.browser_mgr（test_auth.py:12-44），断言 /api/auth/status、Bearer token、auth_token Cookie 等上游旧设计（test_auth.py:47-151）。; 本单元 v2 实现（cbrowser 包的口令登录、cbrowser_session Cookie、CSRF 头、cbat_ 令牌）在该文件中零引用；v2 的实际覆盖在 repo 根 tests/unit/test_auth_service.py、tests/unit/test_auth_client_ip.py、tests/integration/test_auth_api.py（本次仅核对存在性与用例名）。
  - Impact: 按文件名统计认证覆盖率会误判：该文件给人『认证已有测试』的印象却不执行 v2 任何一行代码；若 legacy 包已退役，它还是持续消耗 CI 的死测试（其存废取决于 legacy 包是否仍部署，见 summary.uncertainties）。
  - Fix: 由 legacy 包所属单元确认该文件去留；若 legacy 已退役，随包一并删除或迁入 archive 并在测试清单中注明 v2 认证覆盖的真实位置。

## views

```json
{
  "contracts": {
    "reviewer": "cd0bd460-7331-48aa-99bc-4718c9f7c941",
    "status": "completed"
  },
  "correctness": {
    "reviewer": "cd0bd460-7331-48aa-99bc-4718c9f7c941",
    "status": "completed"
  },
  "design": {
    "reviewer": "cd0bd460-7331-48aa-99bc-4718c9f7c941",
    "status": "completed"
  },
  "documentation": {
    "reviewer": "cd0bd460-7331-48aa-99bc-4718c9f7c941",
    "status": "completed"
  },
  "performance": {
    "reviewer": "cd0bd460-7331-48aa-99bc-4718c9f7c941",
    "status": "completed"
  },
  "robustness": {
    "reviewer": "cd0bd460-7331-48aa-99bc-4718c9f7c941",
    "status": "completed"
  },
  "security": {
    "reviewer": "cd0bd460-7331-48aa-99bc-4718c9f7c941",
    "status": "completed"
  },
  "tests": {
    "reviewer": "cd0bd460-7331-48aa-99bc-4718c9f7c941",
    "status": "completed"
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
  "src/backend/cbrowser/api/v1/router.py",
  "src/backend/cbrowser/api/v1/runtime_views.py",
  "src/backend/cbrowser/auth/__init__.py",
  "src/backend/cbrowser/auth/client_ip.py",
  "src/backend/cbrowser/auth/dependencies.py",
  "src/backend/cbrowser/auth/rate_limiter.py",
  "src/backend/cbrowser/auth/service.py",
  "src/backend/cbrowser/domain/models.py",
  "src/backend/cbrowser/domain/runtime_policy.py"
]
```
