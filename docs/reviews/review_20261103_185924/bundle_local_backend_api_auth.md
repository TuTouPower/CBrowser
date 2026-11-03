# bundle_local_backend_api_auth

## responsibilities

- v2 控制面 HTTP API 工厂与组合根（api/app.py）：装配数据库迁移、ProfileService、ArtifactService、AuthService、RuntimeCoordinator，注册统一错误响应契约与 OpenAPI 安全方案/错误响应补全。
- 用户面 v1 接口（api/v1/router.py）：Profile CRUD、配置版本、运行时 desired/observed 状态、SSE 事件流；全部经 profile_router 的会话+CSRF/Origin 依赖收口，写操作另带幂等 operation_id。
- 身份域（auth/）：单管理员 Argon2 口令登录（双层滑窗限速+时序哑元哈希）、SHA-256 哈希存储的会话与 CSRF token、按 Profile 授权的 cbat_ 自动化 token（创建/列表/吊销/审计）、viewer 与 automation 两条授权判定。
- 内部服务 RPC（api/internal_supervisor.py、internal_gateway.py、internal_artifacts.py）：以文件型 Bearer 服务令牌（≥32 字节、hmac.compare_digest、未配置时 503 fail-closed）向 Supervisor/Gateway 暴露运行时上报、viewer/automation 授权与下载 artifact 入库；Supervisor 面复用 v1 canonical handler 函数但仅挂内部前缀，不再挂到浏览器会话面。
- 运行时协调（api/runtime_coordinator.py）：向 Supervisor 发起 start/stop 对账（退避重试、轮次 operation_id、SSE 广播带 epoch 序列的事件历史回放）。
- 领域模型（domain/models.py）：Profile 配置与请求 DTO（extra=forbid、范围/模式校验、launch_args 白名单在 DTO 层校验）、运行时事件与 artifact 报告 DTO；domain/runtime_policy.py 定义自动重试延迟与失败阻断阈值的单一来源。

## interfaces

- POST /api/v1/auth/login|logout、GET /api/v1/auth/session；POST/GET /api/v1/automation/tokens、DELETE /api/v1/automation/tokens/{id}
- POST/GET/PUT/PATCH/DELETE /api/v1/profiles*（含 duplicate/reset/versions/runtime/desired-state/stop）、GET /api/v1/health、GET /api/v1/events（SSE）
- GET/POST/DELETE /api/v1/profiles/{id}/artifacts*（上传为原始流+filename 查询参数，预检 Content-Length）
- WS /api/v1/automation/profiles/{id}/cdp 与 legacy 别名 WS /api/profiles/{id}/cdp（cbat_ Bearer 授权后以 Supervisor 令牌向 Supervisor 开隧道）
- 内部：GET/POST/PATCH /api/v1/internal/supervisor/*（profiles 读、versions、runtime、desired-state、runtimes/bind|observed|events、artifacts/downloads、health），POST /api/v1/internal/gateway/viewer-authorize|automation-authorize、GET /api/v1/internal/gateway/profiles/{id}/runtime

## dependencies

- cbrowser.services.profile_service / artifact_service（业务与文件存储在他单元）
- cbrowser.adapters.database（repository、session、models、migrations）、cbrowser.secret_files.read_secret_file
- cbrowser.launch_args.validate_launch_args / filter_launch_args（白名单单一实现，域外文件）
- cbrowser.gateway.endpoint.normalize_origin(s)（Origin 规范化单一实现，域外文件）
- argon2-cffi、httpx（协调器出站）、websockets（CDP 隧道）、FastAPI/Starlette、SQLAlchemy async

## flows

- 登录：resolve_client_ip（仅可信代理才采信 XFF）→ AuthService.authenticate_admin（先限速判定，后 Argon2 校验，失败计数）→ create_session（token 只存 SHA-256）→ 下发 cbrowser_session（HttpOnly+Secure+Strict）与 cbrowser_csrf（可读）双 cookie。
- 写请求：require_user_session（cookie→哈希查会话+过期）→ require_csrf_and_origin（写方法才校验 X-CSRF-Token 常量时间比较与 Origin 规范化后命中 allowed_origins，缺失时回退 Referer）→ handler → service 层事务 → coordinator.publish/trigger_reconcile。
- Supervisor 上报：Bearer 服务令牌 → 复用 v1 handler（bind/observed/event/desired-state）→ ProfileService 实例围栏/版本校验 → coordinator 发布 SSE 变更。
- Automation CDP：WS 握手取 Bearer cbat_ → authorize_automation（限速→哈希查 token→吊销/过期/Profile 授权/存在性，拒绝写审计）→ 以 Supervisor 令牌连 Supervisor WS 双向转发，首个方向结束即拆隧道。
- SSE 订阅：会话鉴权 → Last-Event-ID 在同 epoch 历史内则回放缺口，否则在广播锁内构建全量快照事件后注册订阅队列，15s ping 保活。

## constraints

- CBROWSER_ALLOWED_ORIGINS 为空时 lifespan 直接抛错拒启动（fail-closed）；内部 RPC 令牌未配置时一律 503 而非放行。
- 会话与自动化 token 明文只在创建/登录响应出现一次，库内只存 SHA-256；管理员口令文件 ≥12 字节、无管理员且无口令文件时启动失败。
- launch_args 白名单为唯一治理面：创建/更新请求 DTO 用 validate_launch_args 严格拒绝，ProfileConfig 读取路径用 filter_launch_args 丢弃历史越界值。
- API 默认关闭 /docs、/redoc、/openapi.json（CBROWSER_API_DOCS=1 才开）；生产入口默认绑定 127.0.0.1:56661。

## decisions

- 内部 Supervisor 面通过 add_api_route 复用 v1 handler 函数实现单一事务语义，授权完全由挂载面的 router 级依赖承担（会话面不再注册 bind/observed/events）。
- 错误契约集中化：app.py 异常处理器统一输出 {error,message,retryable}，校验错误剥离原始输入值防泄漏，OpenAPI 契约由 contracted_openapi 后处理补齐安全方案与逐路径错误响应。
- CDP 隧道授权与传输分离：automation token 只做准入，向上游转发时替换为 Supervisor 服务令牌，客户端不接触内部凭据。

## evidence

- src/backend/cbrowser/api/app.py:69-187（lifespan 装配与 fail-closed 起始条件）、296-370（统一错误契约与 OpenAPI 后处理）
- src/backend/cbrowser/api/internal_supervisor.py:28-99（服务令牌校验与 handler 复用挂载表）
- src/backend/cbrowser/auth/dependencies.py:24-82（会话与 CSRF/Origin 依赖链）
- src/backend/cbrowser/auth/service.py:100-141（限速+Argon2 登录）、322-397（自动化授权与拒绝审计）
- src/backend/cbrowser/api/v1/router.py:56-124（SSE 订阅）、594-771（仅内部面使用的 bind/observed/event handler 定义）
- git log: 5252f75 feat(t016) harden backend control plane, models and runtime storage 为本单元最近主要变更

## uncertainties

- Supervisor 内部面的鉴权完全依赖 FastAPI 路由级 dependencies 对 add_api_route 注册路由的传播语义：本轮按框架既定语义与兄弟单元集成测试（test_supervisor_observation_authority.py 等实际引用该面）静态判定其生效，未运行验证；若传播不成立，该面将无鉴权——影响面大，建议全局/测试阶段以运行证据复核。
- artifact 上传对无 Content-Length 的 chunked 请求（size_hint=0）是否在流式读取中强制单文件上限，取决于 ArtifactService 实现（本单元外），本层预检仅覆盖带长度头的请求。
- Gateway 向 viewer-authorize 转发的 Origin 是否恒为浏览器规范序列化形式，决定 f_backend_api_auth_02 是实际可用性缺陷还是仅不一致风险；Gateway 代码在本单元外，未核对。
- tests 视角由独立 viewfix 补审完成（原审阅者因本单元不含测试文件将其标为 partial）：补审逐行阅读了 tests/unit/test_auth_service.py、test_auth_client_ip.py、test_auth_models.py、test_api_models_and_sse.py、test_automation_cdp.py、test_api_runtime_coordinator.py、test_runtime_coordinator_error_responses.py，tests/integration/test_auth_api.py、test_automation_api.py、test_automation_cdp_flow.py、test_artifacts_api.py、test_api_sse_events.py、test_sse_epoch_integration.py、test_supervisor_rpc.py、test_supervisor_observation_authority.py、test_profile_patch_semantics.py、test_runtime_coordinator_integration.py、test_v2_api_subprocess.py，以及 test_runtime_agent_protocol_export.py 中的 OpenAPI 契约用例，并以 grep 核对 launch_args 更新路径、Referer、内部 503 三个覆盖点；结论为 completed，新增测试视角 findings f_backend_api_auth_09 至 _12。附带确认：src/backend/tests/（backend_tests 单元）全部 import 的是 legacy backend.* 包，对本单元 cbrowser.* 代码零覆盖，本单元的实际测试全部位于 tests/ 下。

## Findings

- [Low][80] src/backend/cbrowser/domain/models.py:307-352 — ProfileUpdateRequest 对 launch_args 同时注册严格拒绝与静默丢弃两个校验器，更新语义自相矛盾
  - ID: f_backend_api_auth_01; verification: static
  - Evidence: ProfileUpdateRequest.validate_updated_launch_arguments（models.py:307）调用 validate_launch_args：越界参数抛 InvalidLaunchArgument（→422）; 同一 DTO 的 normalize_launch_arguments（models.py:351）调用 filter_launch_args：同一越界参数被静默丢弃；其注释自述用途是『旧行读取时丢弃』，但该类是写入请求 DTO 而非读取模型; 两个 after 校验器同挂一个字段时必有一个被另一个短路：若 filter 先行，validate 永远看不到越界值、严格拒绝成为死代码，且与 ProfileCreateRequest（仅 validate、返回 422）行为不一致；若 validate 先行，filter 在 API 路径上成为死代码; 对照 ProfileConfig.normalize_launch_arguments（models.py:91）只用 filter、ProfileCreateRequest 只用 validate，分工原本清晰，更新 DTO 同时背两者属复制粘连
  - Impact: PATCH /profiles/{id} 提交越界 launch_args 时到底是 422 还是 200 静默丢弃，取决于 pydantic 校验器执行顺序这一实现细节，与 DTO 注释宣称的『新写入严格校验』契约不符；客户端可能误以为参数已生效。白名单本身在两种顺序下都不会被穿透，故无安全影响。
  - Fix: 删除 ProfileUpdateRequest.normalize_launch_arguments（更新路径与创建路径统一走 validate_launch_args 严格拒绝）；读取侧的 filter 保留在 ProfileConfig/仓储层即可。若产品意图是更新时静默丢弃，则应反之删除 validate 并同步修改注释与创建路径口径，二者只能留一。

- [Low][75] src/backend/cbrowser/auth/service.py:298-320 — authorize_viewer 用未规范化的 Origin 原字符串与已规范化的 allowed_origins 精确比对，与 CSRF 路径的 Origin 校验口径不一致
  - ID: f_backend_api_auth_02; verification: static
  - Evidence: app.py lifespan 用 normalize_origins() 生成 app.state.allowed_origins（gateway/endpoint.py:31-41：小写 host、剥离默认端口与尾斜杠）; AuthService.authorize_viewer（service.py:310）直接 `if origin not in allowed_origins`，origin 来自 Gateway 的 ViewerAuthorizeRequest 原样转发，未调用 normalize_origin; 对照 auth/dependencies.py:66-74 的 CSRF/Origin 校验先 normalize_origin(origin) 再比对——同一系统两条 Origin 判定口径不同
  - Impact: 若 Gateway 转发的 Origin 带有默认端口（如 https://host:443）、尾斜杠或大小写差异，合法 viewer 会被 invalid_origin 拒绝（fail-closed 方向，不构成绕过）；是否实际触发取决于 Gateway 的转发形式，本单元外未核对。
  - Fix: authorize_viewer 内先对 origin 做 normalize_origin（ValueError 时按 invalid_origin 拒绝），与 dependencies 的判定共用同一规范化函数。

- [Low][85] src/backend/cbrowser/api/internal_gateway.py:115-125 — Gateway 内部 automation 授权把 client_ip 硬编码为常量，per-source 限速桶被全体客户端共享
  - ID: f_backend_api_auth_03; verification: static
  - Evidence: internal_gateway.automation_authorize 调用 authorize_automation 时传 client_ip="internal-gateway"（internal_gateway.py:123），不透传真实客户端来源; AuthService._automation_limiter 按 client_ip 分桶（service.py:322-397）：经 Gateway 的全部自动化授权共用一个桶，任一来源 10 次失败/60s 即让所有经 Gateway 的授权被 rate_limited; authorize_automation 成功时 record_success(client_ip) 直接清除该桶全部失败记录（rate_limiter.py:87-89），任一成功又会清掉其他来源累积的失败计数，per-source 语义双向失效; 对照直连 WS 路径 automation_router.automation_cdp 使用 resolve_client_ip 解析真实来源——两条授权路径口径不一致
  - Impact: 经 Gateway 的自动化准入失去按来源节流能力：单个坏 token 的重试可对全体 Gateway 客户端造成长达约一分钟的授权拒绝；失败计数也可被任意成功请求清零，削弱在线猜测的累积阻断。
  - Fix: 在 AutomationAuthorizeRequest 中增加可选 client_ip 字段由 Gateway 透传其解析出的客户端来源；缺省时退化为按 token 哈希分桶，而非全体共享一个常量子桶。

- [Low][85] src/backend/cbrowser/auth/service.py:100-141 — Argon2 口令校验在 async 登录路径上同步执行，阻塞事件循环
  - ID: f_backend_api_auth_04; verification: static
  - Evidence: AuthService.authenticate_admin 是 async 方法，但 self.ph.verify(...)（service.py:129、136）为 CPU 密集的同步调用，未经 run_in_executor/to_thread 卸载; LoginRequest.password（auth_router.py:22）无 max_length 约束，超长口令输入同样直接进入 Argon2 校验，放大单次阻塞成本; 同一进程内还承载 SSE 长连接与 RuntimeCoordinator 的对账/发布任务，登录尝试（含被限速前的每次失败）都会让整个 API 停顿一个 Argon2 时长（默认参数约百毫秒级）
  - Impact: 影响有界：限速器在校验前判定，单来源 5 次/分钟、全局 20 次/15 分钟后不再进入校验；但窗口内每次尝试仍造成全 API 可感知的停顿，且合法管理员登录本身也必付此成本。属健壮性/性能瑕疵，非可用性事故。
  - Fix: 将 ph.verify/ph.hash 放入 asyncio.to_thread 执行；同时给 LoginRequest.password 加合理的 max_length（如 1024）。

- [Low][80] src/backend/cbrowser/api/runtime_coordinator.py:73-131 — SSE 订阅在广播锁内构建全量快照且快照事件挤占历史环，订阅/重连会短暂阻塞全体事件发布
  - ID: f_backend_api_auth_05; verification: static
  - Evidence: RuntimeEventBroadcaster.subscribe 在持有 self._lock 期间 await initial_snapshot_provider()（runtime_coordinator.py:102-122），而 v1/router.py 的 get_initial_snapshots 对每个 Profile 逐个做 DB 查询（get_runtime）; publish() 需要同一把锁（runtime_coordinator.py:56-71）：任一无 Last-Event-ID 的新订阅在快照构建期间会阻塞所有实时事件发布，快照规模随 Profile 数线性增长; 快照事件以正式事件 ID 写入 maxlen=1000 的 _history 环（runtime_coordinator.py:111-121）：每次全新订阅注入 N 条快照事件，真实事件被更快挤出回放窗口，Last-Event-ID 续传的可用范围随之缩短; 锁内构建的注释说明其目的是避免快照与实时事件之间的缺口——取舍本身有据，但代价未被限制（无快照规模上限、无锁外预构建）
  - Impact: 单机单管理员场景下表现为 UI 重连瞬间事件延迟与偶发续传失效（客户端退回全量刷新），不构成数据错误；Profile 数量增长后该抖动线性放大。
  - Fix: 快照数据在锁外预先查询，锁内只做订阅注册与『快照基点序号』记录、随后补发基点之后的实时事件；或给快照事件使用独立通道不写入回放历史环。具体方案需与前端续传语义一并验证。

- [Low][85] src/backend/cbrowser/api/app.py:296-348 — 统一错误处理器把全部 503 标为 database_busy 且 retryable=true，永久性配置错误被误报为可重试
  - ID: f_backend_api_auth_06; verification: static
  - Evidence: http_exception_handler 的映射表（app.py:296-305）将 503 固定映射为 error="database_busy"，且 retryable 按 status_code==503 置 true（app.py:343-348）; 但本单元多处 503 与数据库无关且为永久性配置问题：require_supervisor/require_gateway 的『RPC is not configured』（internal_supervisor.py:36、internal_gateway.py:33-36）、get_auth_service/get_artifact_service 的『is not configured』（dependencies.py:15-21、artifact_router.py:26-31）; 反之 401/403/429 不在映射表内、一律回退为含糊的 http_error，与 contracted_openapi 对外宣称的统一 ErrorResponse 语义（逐状态码描述）不完全对应
  - Impact: 客户端（含 Supervisor/Gateway 的重试逻辑与前端）会把『服务令牌未配置』这类需人工介入的错误当作数据库忙而无限重试/误报状态，掩盖真实故障原因；属契约准确性问题，不影响鉴权与数据。
  - Fix: 让 503 的 error 名与 retryable 由抛出方区分：数据库忙走 DatabaseLockError 专用处理器（已有），配置类 503 应使用独立 error 名（如 service_not_configured）且 retryable=false；或在 HTTPException detail 中携带机器可读的 error 代码由处理器透传。

- [Low][65] src/backend/cbrowser/api/internal_artifacts.py:24-53 — 下载 artifact 上报携带的 runtime_instance_id 从未被校验，内部入库路径不对当前实例设围栏
  - ID: f_backend_api_auth_07; verification: suspected
  - Evidence: ArtifactDownloadReport（domain/models.py:189-203）强制要求 runtime_instance_id 字段，表明契约意图把上报绑定到产生下载的运行时实例; report_download（internal_artifacts.py:30-53）调用 service.ingest_download 时只传 profile_id/path/name/sha256/size/content_type，runtime_instance_id 被完全忽略，未与该 Profile 当前绑定的实例比对; 对照运行时状态面上报（bind/observed）有 StaleInstanceError/expected_current_instance 的实例围栏（router.py:594-660 与 service 层），下载入库路径没有对应围栏
  - Impact: 已终止实例迟到的下载上报仍会被入库（同文件重复上报由 ArtifactService 的去重结果 duplicate 兜底，属本单元外实现）；若旧实例与新实例先后在同一 Profile 产生同名不同内容的下载，旧上报可能把过期文件登记为该 Profile 的 artifact。调用方仅限持有 Supervisor 令牌的服务进程，故为纵深防御缺口而非外部可达漏洞。
  - Fix: report_download 在入库前校验 payload.runtime_instance_id 与 Profile 当前 runtime_instance_id 一致（或把该参数下传 ingest_download 在服务层校验），不一致时返回 outcome=rejected 并记录原因。

- [Info][85] src/backend/cbrowser/auth/service.py:322-397 — 自动化授权拒绝的审计覆盖不对称：高频猜测路径不留痕，部分拒绝路径每次写一条审计记录
  - ID: f_backend_api_auth_08; verification: static
  - Evidence: authorize_automation 对 token_revoked/token_expired/profile_unauthorized/profile_not_found 四种拒绝调用 _record_auth_denied 写 AuditEventModel（service.py:353-377），每次拒绝多一次 DB 写事务; 而 token_not_found（service.py:344-350）与格式非法（service.py:327-333）两种拒绝只记 logger.warning 不写审计——恰是令牌在线猜测时最常见的返回路径，审计系统对其不可见; 被审计的拒绝写放大受 _automation_limiter 全局 200 次/分钟上限约束，上限不低：持续拒绝流量可产生同等速率的审计行增长
  - Impact: 审计轨迹在最需要取证的猜测场景缺失、在其他场景又以逐条写库方式增长；功能与安全边界不受影响，属可观测性一致性问题。
  - Fix: 统一策略：或将 token_not_found/格式非法也纳入审计（并对同 token+同原因做聚合/采样以控量），或把逐条审计降级为限速器计数+结构化日志、仅保留状态迁移类事件（吊销/过期命中）入库。二选一并在代码注释中写明口径。

- [Medium][90] tests/integration/test_v2_api_subprocess.py:188（仅创建路径）；更新路径无对应用例 — 更新路径（PUT/PATCH）的 launch_args 白名单校验零测试覆盖，与 f_01 的双校验器矛盾叠加后更新语义无任何回归网
  - ID: f_backend_api_auth_09; verification: static
  - Evidence: 全仓测试中对越界 launch_args 的负例只有一处：test_v2_api_subprocess.py:188 在 POST /api/v1/profiles 以 --load-extension=/tmp/evil 断言 422，钉住的是 ProfileCreateRequest（models.py:252-255 仅 validate_launch_args 严格拒绝）; grep tests/ 与 src/backend/tests/：没有任何用例以 PUT/PATCH 提交 launch_args（更无越界值），ProfileUpdateRequest 也从未被测试直接引用；test_profile_patch_semantics.py 只覆盖 name/tags 的 PATCH 语义; ProfileUpdateRequest 对同一字段同时挂 validate_launch_args（models.py:305-308）与 filter_launch_args（models.py:349-354）两个 after 校验器（见 f_backend_api_auth_01），实际生效语义取决于校验器执行顺序这一实现细节
  - Impact: 更新路径提交越界 launch_args 到底是 422 还是 200 静默丢弃，目前由未声明的校验器顺序决定且无测试钉住；任一侧重构（删校验器、调整顺序、pydantic 升级改变校验器语义）都能无声翻转这个安全白名单字段的写入语义，测试全绿也发现不了。
  - Fix: 在 f_backend_api_auth_01 收敛为单一语义后补回归网：HTTP 层 PUT 与 PATCH 各一条越界 launch_args（如 --load-extension=）用例，断言收敛后的唯一预期（422，或参数被丢弃且响应与落库均不含该值）；另补 DTO 层参数化用例直接钉住 ProfileUpdateRequest 的校验结果。

- [Low][90] src/backend/cbrowser/auth/dependencies.py:65-67（require_csrf_and_origin 的 Referer 回退分支） — CSRF/Origin 依赖的 Referer 回退分支无任何测试覆盖
  - ID: f_backend_api_auth_10; verification: static
  - Evidence: dependencies.py:48-67：写请求缺 Origin 时回退解析 Referer 头，按其 scheme+netloc 与 allowed_origins 比对; grep tests/ 与 src/backend/tests/ 全文无 Referer/referer 出现；现有负例（test_auth_api.py 中 logout 无 Origin→403、desired-state 错 Origin→403）都是 Origin 与 Referer 双缺、或 Origin 明确错误，从未走回退分支
  - Impact: 回退分支若回归（误收外站 Referer、或误拒合法的 Referer-only 客户端），现有测试全绿无感；该分支是同源校验的第二条代码路径，长期无覆盖容易与主路径口径漂移（如 f_backend_api_auth_02 式的规范化不一致）。
  - Fix: 补三条用例：无 Origin + 允许列表内 Referer → 写请求放行；无 Origin + 外站 Referer → 403；无 Origin + 畸形 Referer → 403。

- [Low][85] src/backend/cbrowser/api/internal_supervisor.py:36、internal_gateway.py:36-37、internal_artifacts.py:23 — 内部 RPC 未配置令牌时的 503 fail-closed 分支无测试覆盖
  - ID: f_backend_api_auth_11; verification: static
  - Evidence: 三个内部路由模块在服务令牌/服务未配置时分别 raise 503（Supervisor/Gateway/Artifact RPC is not configured），原审阅将其列为结构性 fail-closed 保障; 所有调用内部端点的测试 fixture 都先写好令牌文件（tests/integration/conftest.py 的 supervisor_api、test_auth_api.py 的 auth_env、test_artifacts_api.py 的 artifact_env）；未配令牌建 app 的用例（test_automation_api.py、test_api_sse_events.py、test_sse_epoch_integration.py）从不请求内部端点; grep 测试全文无对这三处 503 状态/文案的断言；唯一相邻覆盖是 AuthService 依赖缺失的 503（test_auth_service.py::test_missing_auth_service_returns_503），属不同代码路径
  - Impact: fail-closed 默认若回归为 401/500 或未捕获异常，测试无感；且与 f_backend_api_auth_06（全部 503 被统一标为 database_busy 且 retryable）叠加时，该分支实际返回的错误形态也从未被断言钉住。
  - Fix: 以未传 supervisor_token_file/gateway_token_file 的 create_app 各补一条用例：对三个内部面各取一个端点，断言 503 及统一错误体形态。

- [Low][85] tests/integration/test_auth_api.py::test_internal_gateway_endpoints（viewer-authorize 用例组） — viewer-authorize 的 Origin 规范化变体（尾斜杠等）无测试，f_02 的比对口径不一致无回归网
  - ID: f_backend_api_auth_12; verification: static
  - Evidence: 现有 viewer-authorize 用例只用与 allowed_origins 逐字相同的 Origin 和完全外站的 https://attacker.site 两种取值（test_auth_api.py::test_internal_gateway_endpoints、test_auth_service.py::test_viewer_and_automation_authorize）; CSRF 路径已有尾斜杠变体被接受的专门用例（test_auth_api.py::test_allowed_origin_with_trailing_slash_is_accepted），而走 authorize_viewer 的 Gateway 内部路径没有对应变体用例; f_backend_api_auth_02 已指出 authorize_viewer 用未规范化的 Origin 原字符串与已规范化的 allowed_origins 精确比对；该不一致目前无任何测试能暴露
  - Impact: Gateway 转发的 Origin 只要带尾斜杠等规范化差异，合法 viewer 即被拒（invalid_origin），且该行为无论修复还是恶化都不会被测试捕获；原审阅留下的『Gateway 转发 Origin 是否恒为规范序列化形式』不确定项也因此无从收敛。
  - Fix: 在 test_internal_gateway_endpoints 补 viewer-authorize 的尾斜杠 Origin 用例，断言与 CSRF 路径一致的预期（规范化后命中即 allowed=true），并在 f_backend_api_auth_02 修复后保留为回归网。

## views

```json
{
  "security": {
    "status": "completed",
    "reviewer": "2d96648c-e1de-4f61-b621-2efda0c10561"
  },
  "correctness": {
    "status": "completed",
    "reviewer": "2d96648c-e1de-4f61-b621-2efda0c10561"
  },
  "contracts": {
    "status": "completed",
    "reviewer": "2d96648c-e1de-4f61-b621-2efda0c10561"
  },
  "performance": {
    "status": "completed",
    "reviewer": "2d96648c-e1de-4f61-b621-2efda0c10561"
  },
  "design": {
    "status": "completed",
    "reviewer": "2d96648c-e1de-4f61-b621-2efda0c10561"
  },
  "robustness": {
    "status": "completed",
    "reviewer": "2d96648c-e1de-4f61-b621-2efda0c10561"
  },
  "tests": {
    "status": "completed",
    "reviewer": "42a3f699-6ef2-449e-a417-498fd1b847bf"
  },
  "documentation": {
    "status": "completed",
    "reviewer": "2d96648c-e1de-4f61-b621-2efda0c10561"
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
