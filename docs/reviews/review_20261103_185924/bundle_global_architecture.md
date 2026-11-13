# bundle_global_architecture

## Summary

v2 五服务内部的架构划分本身是自洽且经得起核对的：本视角回查源码确认，docker 客户端导入只出现在 cbrowser/supervisor 包内（Supervisor 唯一 Docker socket 持有者成立），v2 数据库写入全部经 API 的 Repository 层收口（API 唯一 DB 写者成立），desired/observed 分离、(profile_id, runtime_instance_id, config_version) 栅栏与 UUIDv5 幂等事件在 Supervisor、Runtime Agent、API 三侧口径一致，fail-closed 是贯穿 v2 与 repo_task 工具链的共同设计语言。架构层面的问题全部位于接缝处：其一，仓库唯一可部署的工件集只交付 legacy 一代，v2 架构没有可达的部署拓扑，被部署的系统与被设计/被测试的系统不是同一个；其二，两代各自持有数据权威与身份域，配额、文件名净化、下载状态机等跨切面策略双份实现且已分叉，产品整体信任姿态由较弱的 legacy 面决定；其三，事件投递的失败分类在两个 forwarder 之间口径矛盾，契约层是只生成不设门禁的单向产物且导出形式丢失了模型本身的判别力。汇总所列四条待核实线索中，本视角经源码核对闭合两条：read_secret_file 内部即对读入值做 strip（src/backend/cbrowser/secret_files.py），Gateway 控制令牌『恒不匹配』不成立，仅余调用约定不一致的噪声（见 f_global_architecture_09）；Gateway 代码中不存在 Selkies 地址、从不主动向 18096 发起连接，该端口仅作为 Stream 容器内 Selkies 监听的环境变量出现在 supervisor/container_spec.py:140，全部信令走 Agent 发起的 WebSocket，与 Stream 容器 INPUT 策略（回环/已建立/UDP mux）自洽。Supervisor 内部面的结构亦已核对：被复用的 v1 handler 经 add_api_route 注册到自带 dependencies=[Depends(require_supervisor)] 的同一 supervisor_router 上（src/backend/cbrowser/api/internal_supervisor.py），不存在『路由落在会话面而依赖落在别处』的结构性缺口，仅余框架合并语义与集成测试断言的核实，已立 question 派精查。

## Findings

- [High][85] compose.yaml；config/docker/（五个 Dockerfile）；docs/blueprint 与 AGENTS.md 声明的 v2 架构 — 可部署工件只交付 legacy 一代：v2 五服务架构在仓库内没有可达的部署拓扑，被部署的系统与被设计的系统不是同一个

    - ID: f_global_architecture_01; verification: static
    - Evidence: contracts_deploy 单元判定：compose.yaml 的唯一服务仍部署 legacy 单体（config/docker/Dockerfile + entrypoint.sh，容器内端口 8080），四个 v2 运行时镜像（browser/stream/gateway/supervisor）从未被 compose 引用，无任何部署路径（f_contracts_deploy_04）; Supervisor 镜像按当前 Dockerfile 与 .dockerignore 白名单组合构建即缺 launch_args.py（f_contracts_deploy_01，High），即便有人手工编排该镜像也无法建成; legacy 生产 Dockerfile 的 FROM cbrowser:latest 与 compose 给自身输出的同名标签构成自引用（f_contracts_deploy_02，High），legacy 这一代的部署链本身亦不自洽; DOCKER_DEPLOYMENT.md 对绑定地址、暴露面、前置条件与架构的描述与 compose 现状全面矛盾（f_contracts_deploy_05），照文档操作得到的是另一套系统; 仓库 AGENTS.md 将产品定义为『独立 Docker 容器沙箱 + Selkies WebRTC』的 v2 架构，blueprint/decisions.md 的 ADR 013/014 均以 v2 运行时为对象——文档与决策层描述的架构与部署层交付的架构互不对应
    - Impact: 架构投入（五服务划分、协议契约、四镜像、配套测试）无法从仓库工件转化为运行系统；实际运行面停留在 legacy 单体，其缺陷（见 f_global_architecture_03）即为产品的真实暴露面。任何基于『v2 已上线』假设的后续决策（安全评估、运维、演进规划）都会建立在错误前提上。
    - Fix: 二选一并落到工件层：或为 v2 五服务补齐可达的编排（如 compose profiles 或独立 compose 文件，含镜像构建修复与部署文档同步），使声明架构成为可部署架构；或在 blueprint/AGENTS.md 中明确 v2 为未交付状态、legacy 为当前产品面，并据此重排两侧的维护与安全投入。在此之前，DOCKER_DEPLOYMENT.md 应先与 compose 现状对齐，消除文档与工件的矛盾。

- [Medium][90] src/backend/database.py（legacy 手写 DDL）；src/backend/cbrowser/adapters/database/（v2 SQLAlchemy/Alembic）；src/backend/artifacts.py 与 src/backend/cbrowser/adapters/filesystem/artifact_store.py — 两套数据权威同仓并存且互不感知：legacy profiles.db 与 v2 cbrowser.db 各自演进，配额、文件名净化、下载捕获等跨切面策略双份实现并已分叉

    - ID: f_global_architecture_02; verification: static
    - Evidence: backend_core 单元约束记录：legacy 与 v2 两套数据库同仓并存，schema 演进互不感知；legacy init_db 以列集相等为唯一版本判据、整表重建迁移，v2 走 Alembic 链（0001–0006），两侧无任何同步或映射机制; 同一产品概念双份实现：legacy artifacts.py/downloads.py 实现每-profile 产物存储（流式落盘、配额、CDP 下载状态机），v2 artifact_store.py/ArtifactService 实现同一职责（原子发布、配额、下载 ingest），safe_filename 净化规则亦各有一份; 双份实现已经分叉：legacy 上传路径配额检查与建行分离、并发可绕过上限（f_backend_core_06），v2 上传路径在建行前即刻复检配额（backend_runtime_adapters 单元 Flow 记录）——同一策略在两代中 rigor 不同; legacy init_db 整表重建静默丢弃列集之外的全部列数据、无日志无备份（f_backend_core_05），v2 侧则以不可变配置版本 + Alembic 管理演进，两代的数据演进纪律不在同一水平
    - Impact: 任何跨切面策略的修订都必须在两处同步实施且无机制保证同步，实际已出现一侧修好一侧未修的分叉；两套 profile/artifact 语义并存使『哪个是权威』在迁移完成前长期含糊，数据迁移路径（legacy profiles.db → cbrowser.db）亦无工件承接。
    - Fix: 在 blueprint 中明确双轨的终局与迁移路径（legacy 数据是否迁移、两代并存的期限与边界），并把配额、文件名净化等跨切面策略抽为两侧共用的单一实现或至少建立对照清单；在迁移完成前，策略级缺陷修复应强制双侧核对。

- [Medium][90] src/backend/main.py:143-147（AuthMiddleware）；src/backend/cbrowser/auth/（v2 身份域）；.env.example:15 — 两代信任边界基调断裂：v2 全链 fail-closed 与 legacy 的 opt-in 鉴权分属两个互不相认的身份域，产品整体信任姿态由较弱一代决定

    - ID: f_global_architecture_03; verification: static
    - Evidence: legacy 唯一访问控制是 AUTH_TOKEN，未设置时全部 /api/\* 无条件放行（f_backend_core_03），代码注释自述为 local dev 语义，但该进程同时承载宿主机控制端点（shutdown/open-external）与剪贴板中继; 部署模板 .env.example 中 AUTH_TOKEN 默认空，而其自身注释称该项为 'Required'（f_contracts_deploy_03）——缓解完全依赖部署者自觉注入与 compose 回环绑定，均不在代码权威内; legacy 内部防护亦不齐：/api/open-external 缺少 /api/shutdown 已有的同源 CSRF 防护（f_backend_core_04）；剪贴板正文写进 manager.log 与同代 diagnostics 模块的脱敏承诺直接冲突（f_backend_core_01，High）; v2 身份域为独立的一套：Argon2 管理员会话 + 按 profile 授权的自动化 token + 文件型服务令牌，与 legacy 的 AUTH_TOKEN 互不相认；同一产品、同一用户面对两个身份系统，无共享的安全基线抽象
    - Impact: 只要 legacy 面仍是可部署面（见 f_global_architecture_01），产品的实际信任边界就由 opt-in 一代决定：一次未注入 AUTH_TOKEN 的部署即得到无鉴权的局域网远程控制面，v2 侧再严密的 fail-closed 设计也无法收口这一暴露。两套身份域并存还使权限审计与凭据轮换无统一抓手。
    - Fix: 为两代设立共同的最低安全基线并落到代码：legacy 启动时 AUTH_TOKEN 为空应默认拒绝启动或至少拒绝宿主机控制端点（与 v2『未配置即 503/拒启动』口径一致）；open-external 补齐与 shutdown 相同的同源校验；剪贴板日志按 diagnostics 既有脱敏承诺收口。长期以 f_global_architecture_01 的部署收敛消除双身份域。

- [Medium][95] src/backend/cbrowser/supervisor/event_forwarder.py:175-196；src/backend/cbrowser/supervisor/core.py:640-682 — 事件投递语义无单一权威：两个 forwarder 对 API 4xx 的失败分类口径矛盾，runtime 事件被拒后游标不推进、每秒无限重试

    - ID: f_global_architecture_04; verification: static
    - Evidence: EventForwarder 把全部非 200 且低于 500 的状态（含 401/403/429）一律分类为永久 REJECTED 并隔离事件，与 DownloadArtifactForwarder 的可重试 4xx 集合口径不一致（f_backend_supervisor_02）——同一进程内两条投递链对同一失败语义各表一枝; consume_disk_events 在 EventForwarder 报告 REJECTED 时不推进 (mtime_ns, name) 游标，被拒事件每秒重复投递、无限重试（f_backend_supervisor_01），与 spool-first + 隔离的既定设计意图互相抵消; 对照面：事件的身份与状态语义本身有单一权威——UUIDv5 确定性 ID、(profile_id, runtime_instance_id, config_version) 栅栏、API 侧 consume_runtime_event 去重在三方一致；唯独投递失败分类这一环没有任何模块或契约声明为权威
    - Impact: 令牌过期/轮换（401）或限流（429）这类可恢复失败会被当作永久拒绝：事件进隔离区或陷入 1s 重试循环，运行时终局观测（失败计数、restart_blocked）可能延迟或丢失，侵蚀 desired/observed 收敛这一核心机制的可信度。
    - Fix: 把投递失败分类收敛为单一实现供两个 forwarder 共用：401/403/429 与 5xx 按可重试处理（退避重试），仅 400/422 类语义拒绝进隔离；REJECTED 终局必须推进磁盘游标并留审计记录，避免同一事件无限重投。

- [Medium][90] src/backend/cbrowser/supervisor/core.py:1090-1102 — 持久化操作日志可为未检查、未拆卸的实例记下 'stopped' 终局，与『observed 权威须源于实际观测』的设计原则相悖

    - ID: f_global_architecture_05; verification: static
    - Evidence: stop_profile 在内存 session 追踪的是另一实例时，会为请求中的实例直接写入 OperationJournal 的 durable 'stopped' 结果，而从未检查或拆卸该实例（f_backend_supervisor_03）; 同单元的设计声明与此相反：API 是意图与失败核算的权威，Supervisor 只合成有栅栏的终局观测；Agent 健康状态须经实时 PID/CDP 探针交叉验证后才被信任（backend_runtime_adapters 单元约束记录）——观测必须源于实测是贯穿 v2 的原则; OperationJournal 的定位是 durable idempotency 依据（stop 流程以 journal complete 收尾），一条未源于实测的终局记录会被后续对账与恢复逻辑当作事实消费
    - Impact: 持久层出现『账面已停、实际未停』的权威记录，恢复协调器与对账回路据此可能跳过对真实运行中实例的清理，形成孤儿容器与状态漂移；且该记录具备 durable 形式，比内存态不一致更难被发现和纠正。
    - Fix: stop_profile 在 session 追踪实例与请求实例不一致时，应先按请求实例做实际检查（Docker 标签扫描/状态查询）再决定 journal 内容；无法确认时记为未执行/需对账而非 'stopped'，让 OperationJournal 的每条终局都可追溯到一次实际观测。

- [Medium][85] schemas/（openapi/cbrowser_v1.json、cbrowser_internal.json，runtime/ 与 stream/ 协议 schema）；scripts/export\_\*.py；scripts/run_gates.sh — 契约层是单向生成物而非权威：导出 schema 无新鲜度门禁，且导出形式丢失判别力，与实现各自漂移无从察觉

    - ID: f_global_architecture_06; verification: static
    - Evidence: 契约生成流为单向导出：源码模型 → 四个 export 脚本 → 入库 schema；contracts_deploy 单元依赖记录明确『被审单元内没有任何机制校验新鲜度』，run_gates.sh 不含 schema 新鲜度检查（其单元 uncertainty 亦同）; 协议 schema 导出为无判别 anyOf 联合，校验无法区分消息类型（f_contracts_deploy_07）；版本字段不一致——runtime agent schema 有 version、supervisor 与 stream schema 没有（f_contracts_deploy_08）; 内部 OpenAPI 定义了 per-service 的 bearer <redacted> 但无任何实现使用，全部操作塌缩为单一 serviceBearer（f_contracts_deploy_09），与实现侧确实存在的三套独立服务令牌（Supervisor/Gateway/API）不对应; 同一状态字段在契约两侧形态不一：v1 OpenAPI 中 profile runtime 状态是裸字符串，supervisor 协议中同字段是枚举（f_contracts_deploy_10）; 覆盖不均：stream 协议在测试层有『pydantic 模型 / 导出 schema / 线上流量』三层等价钉扎（tests_unit_stream_api 单元记录），OpenAPI 与 supervisor/runtime 协议没有同等闭环
    - Impact: schemas/ 在仓规中被定为跨服务接口契约（改契约走 task 流程），但门禁缺位使入库 schema 可以静默落后于实现，消费方（前端手写客户端、测试 harness、外部调用者）按过期或弱化契约工作时不会有任何信号；无判别联合与裸字符串使契约层无法承担跨服务校验职责，权威实际仍在各服务代码内部，契约只是其不保鲜的投影。
    - Fix: 在 run_gates.sh 或 CI 中加 schema 新鲜度门禁（重跑 export 后 diff 非空即失败）；协议 schema 导出时保留 discriminator 并统一版本字段策略；内部 OpenAPI 的安全方案与实现的三令牌现实对齐，或删去未被使用的 per-service 方案声明；runtime 状态字段在 v1 OpenAPI 中改为与协议侧一致的枚举。

- [Low][90] src/backend/cbrowser/domain/models.py:307-352；src/backend/cbrowser/launch_args.py — launch_args 白名单的『拒绝还是丢弃』策略权威不单一：更新 DTO 同时注册严格与宽松两个校验器，语义取决于 pydantic 校验器执行顺序

    - ID: f_global_architecture_07; verification: static
    - Evidence: ProfileUpdateRequest 同时挂 validate_launch_args（越界抛 422）与 filter_launch_args（越界静默丢弃）两个 after 校验器，必有一个被另一个短路成死代码，更新路径的实际语义取决于校验器顺序这一实现细节（f_backend_api_auth_01）; 对照分工原本清晰：ProfileCreateRequest 只用 validate、ProfileConfig 读取路径只用 filter、Runner 启动前再做一次 validate（backend_runtime_adapters 单元约束记录）——规则实现单一（launch_args.py 一处），但策略选择散落在各 DTO 上; 该路径零测试覆盖（f_backend_api_auth_09），语义即便因重构翻转也不会被察觉
    - Impact: 同一安全白名单在创建与更新两条路径上可能给出 422 与 200 静默丢弃两种结果，客户端会误以为越界参数已生效；策略权威不单一使后续维护者无法从任何一处代码断定系统的对外承诺。
    - Fix: 更新 DTO 只保留一个校验器（建议与创建路径统一为 validate 严格拒绝），filter 仅保留在历史数据读取路径；把『写入严格、读取宽容』的策略声明写回 launch_args.py 模块文档，使策略权威回到规则实现处。

- [Low][80] src/frontend（profiles 数据层 hook）；src/backend/cbrowser/adapters/database/repository.py（audit-row sig_hash 幂等） — 幂等键契约的键作用域两端无主：前端按 hook 实例共享 Idempotency-Key，后端按『一 key 对应一逻辑操作』校验 sig_hash，合法异参并发会被判为幂等冲突

    - ID: f_global_architecture_08; verification: static
    - Evidence: 前端 Idempotency-Key 按 hook 实例共享，同一实例的并发异参调用会复用同一把 key（f_frontend_features_01）; 后端幂等以 audit_events 行的 sig_hash（action+target+payload 的 sha256）判定：同 key 重放同载荷返回已提交结果，载荷不一致抛 IdempotencyConflictError（backend_runtime_adapters 单元 Decisions 记录）; 两端组合的结果是：用户在同一页面内的两个不同合法操作若并发发出，会以 409 幂等冲突告终——该行为在任何一侧的单元审阅内都未闭环，双方都假设对方的键使用方式与自己预期一致
    - Impact: 幂等契约缺少键作用域的共同定义（每操作一 key 还是每会话一 key），前端的键生成策略与后端的冲突语义直接相撞时，失败表现为莫名 409，用户与排障者都难以归因；后续任一端调整键策略都会静默改变全链语义。
    - Fix: 在契约层明确键作用域为『每逻辑操作一 key』：前端在每次 mutation 调用时生成新 key（重试同一操作时才复用），并把该约定写入内部 OpenAPI 的 Idempotency-Key 参数说明；后端保持现有 sig_hash 校验不变。

- [Info][98] src/backend/cbrowser/secret_files.py:25；src/backend/cbrowser/gateway/server.py:80-84；src/backend/cbrowser/gateway/api_client.py:22-24 — 线索核对闭环：read_secret_file 内部已做 strip，Gateway 控制令牌『恒不匹配』不成立，残留仅为同一函数两处调用约定不一致

    - ID: f_global_architecture_09; verification: static
    - Evidence: 本视角回查源码：read_secret_file 的实现为 target.read_text(encoding='utf-8').strip() 后再校验最小长度并返回（src/backend/cbrowser/secret_files.py），函数内部已经剥离尾随空白; gateway/server.py 将返回值直接 .encode() 作控制令牌比对、api_client.py 对同一函数结果再显式 .strip()——两者结果恒等，汇总 backend_stream_gateway:0 所担心的『令牌文件带尾随换行时 Bearer 比对恒不匹配』不成立; 残留问题仅为可维护性：同一函数的后处理约定在两个调用点不一致，容易让后续读者重复产生本轮这种跨单元疑虑
    - Impact: 无功能影响；记录此项为该跨包线索的正式关闭依据，避免后续审阅重复立项。调用约定不一致本身可能在未来某次重构（如下沉 strip 到调用方）时引入真实分叉。
    - Fix: 删除 api_client.py 的冗余 .strip() 并在 read_secret_file 的 docstring 中明示『返回值已 strip』，使约定单点声明。

- [Info][75] .repo_template/scripts/repo_task/（lifecycle start 与 ledger/attempts） — repo_task 双权威链上 start 事件为 best-effort 写入，是执行权威中唯一的非 fail-closed 环节，完整性依赖事后 import 重建

    - ID: f_global_architecture_10; verification: static
    - Evidence: 执行主线记录：start 阶段写 ledger start 事件为 best-effort（template_scripts_state 单元 Flow），而同包其他审计写入失败即中止状态迁移（同单元约束记录：审计写失败中止状态迁移、ledger 损坏行拒绝继续）; 双权威划分本身自洽且多处校验一致：文档状态以 front matter 为准、执行状态以 ledger exact identity 为准、派生索引可重建、integrate 门禁做 base_sha/diff_anchor/分支 tip 三方等值校验（同单元 Decisions 记录）; ledger 丢失时存在 import 重建路径（有 done 分支与 handoff 时重建三事件），但针对『仅 start 事件缺失、其余事件齐全』的局部缺口没有专门校验点
    - Impact: 执行权威链的完整性在一个环节上依赖事后补救而非写入时保证：start 事件静默缺失时，attempt/reserve 之后的事件链失去起点锚，recovery 分类与审计追溯需靠 import 路径兜底，属于设计一致性上的单点例外而非现行故障。
    - Fix: 将 start 的 ledger 写入改为与其他审计写入一致的 fail-closed（写失败即中止 start），或在 reserve 时校验 start 事件存在性并显式报错，使执行权威链无静默缺口。

## questions

```json
[
  {
    "counterevidence": "找到任一可实际执行的 v2 五服务编排工件（哪怕是未被 compose 引用的独立部署脚本或任务交付物），即推翻『无部署路径』并将该 finding 降为『默认部署路径仍指向 legacy』",
    "evidence_needed": "全仓检索四个 v2 运行时镜像名与 Dockerfile 路径在 compose.yaml 之外的可执行引用（部署脚本、任务书交付物、指南中的实际编排命令），并核对 docs/tasks 现行任务书（t009/t010/t012）是否包含 v2 部署交付",
    "id": "q_architecture_01",
    "question": "仓库中是否存在 contracts_deploy 单元范围之外的 v2 部署路径（另一份 compose、部署脚本、systemd/启动脚本或以交付 v2 编排为目标的 task 书），使 f_global_architecture_01 的『无部署路径』结论需要降级？",
    "units": [
      "contracts_deploy",
      "docs_current"
    ]
  },
  {
    "counterevidence": "存在未带令牌请求内部端点并断言被拒的集成用例，或 FastAPI 源码/文档确认 add_api_route 合并 router dependencies，即可关闭本问题；反之若用例全部携带正确令牌且无拒绝断言，则该面的鉴权在本轮证据下仍属未验证",
    "evidence_needed": "核对 tests/integration 中调用内部 Supervisor 面的用例（test_supervisor_rpc、test_supervisor_observation_authority 等）是否包含无令牌/错令牌请求并断言 401 或 503；并确认随仓 FastAPI 版本的 APIRouter.add_api_route 对 router 级 dependencies 的合并行为",
    "id": "q_architecture_02",
    "question": "Supervisor 内部面经 add_api_route 注册到自带 require_supervisor 依赖的 supervisor_router 后，该路由级依赖在随仓 FastAPI 版本下是否确实对这些路由生效，且集成测试是否断言过未授权请求被拒（401/503）？",
    "units": [
      "backend_api_auth",
      "tests_integration_fixtures"
    ]
  },
  {
    "counterevidence": "若 Gateway 转发前已做 normalize_origin 或转发的是规范化后的白名单值，则未规范化比对永不误拒，f_backend_api_auth_02 降为纯口径不一致；若转发原始头，则带默认端口/尾斜杠的合法 Origin 会被实际拒绝",
    "evidence_needed": "读 gateway/server.py 的 viewer 接入路径，确认其放入 ViewerAuthorizeRequest 的 origin 取自何处（原始请求头、registry 中的白名单命中值还是 normalize_origin 的输出），并与 auth/service.py:310 的未规范化精确比对对照",
    "id": "q_architecture_03",
    "question": "Gateway 在调用 viewer-authorize 时转发的 Origin 是浏览器原始头还是已规范化的值？这决定 f_backend_api_auth_02（authorize_viewer 未规范化比对）是实际可用性缺陷还是仅口径不一致。",
    "units": [
      "backend_stream_gateway",
      "backend_api_auth"
    ]
  },
  {
    "counterevidence": "spec/blueprint 明确写明克隆共享 seed 或应新发 seed 任一者，即可据此关闭问题并决定是否立 finding；若文档无定义，则该语义只能由用户裁决",
    "evidence_needed": "检索 docs/specs、docs/blueprint 与 duplicate 相关 task 书中对克隆后 fingerprint_seed 的定义或验收标准，并对照 reset_profile 已实现的『按 operation_id 确定性重播 seed』口径（同文件内 reset 与 duplicate 两条路径的 seed 策略是否被有意区分）",
    "id": "q_architecture_04",
    "question": "duplicate profile 沿用源 fingerprint_seed 是产品有意定义（克隆即共享指纹身份）还是实现疏漏（克隆应获新 seed）？仓内 spec/blueprint 是否有明确定义？",
    "units": [
      "backend_runtime_adapters",
      "docs_current"
    ]
  }
]
```

## question_decisions

```json
{
  "q_architecture_01": {
    "followup_sha256": "e317ffbb39e047b61f98bb30a60c5142e31edc17a2e45267e1752ae98d5b9b54",
    "reason": "采纳精查的全仓核对：全仓仅一份 compose.yaml（唯一服务为 legacy）；四个 *_runtime Dockerfile 在 config/docker 之外的引用只有归档 task 的写域声明（明示不含正式 compose）、blueprint 的后续 task 对接说明、guides 的单镜像验证构建命令与单测打包断言，无一处是可执行编排；仓内无 systemd/launchd/Makefile 等其他编排器，scripts/ 无部署脚本。仓库自身定案同向：docs/blueprint/architecture.md 明言正式编排由后续 task 实施、独立组件测试通过不能代表整套部署完成；正式编排被定为 backlog 任务 t012 的待产出物（正式 compose、含 API 在内的全部生产镜像、Caddy 配置、单一权威拓扑定义），t012/t009/t010 均为 backlog 且部署相关 AC 全未勾选；API 至今无生产 Dockerfile，测试拓扑中的 API 容器使用 tests/fixtures 下的夹具镜像。对最接近的反证候选裁定不成立：tests/fixtures/gateway_probe/topology.py 的 GatewayTopologyHarness 虽能组装 Gateway+API+Supervisor+Caddy 真实容器拓扑，但它不构建任何镜像（六个镜像 ID 须外部预构建后经环境变量注入）、API 为夹具镜像、拓扑是每轮 E2E 验证的临时实例并受 E2E 门禁约束，属测试基础设施，不满足本 question 反证条件中『可实际执行的 v2 五服务编排工件』口径。对 f_global_architecture_01 的影响：维持 High、不降级；仅措辞精确化——其『没有可达的部署拓扑』应读作『无面向运维的部署路径，五服务仅在 E2E 夹具拓扑中被组装过』，finding 原文与严重度不变。连带影响：f_global_architecture_02、f_global_architecture_03 以『legacy 仍是唯一可部署面』为前提的影响论证继续成立，无需调整。",
    "result": "refuted"
  },
  "q_architecture_02": {
    "followup_sha256": "52eedba6aa0bbb4e971bfd13be8f053fd641f55dd0e89d611c436ac8bf26e29f",
    "reason": "采纳精查的双路证据，本 question 反证条件的两个析取项同时满足，怀疑关闭。其一，框架合并语义确定成立：随仓钉版 FastAPI 0.162.0 的 routing.py 确认 APIRouter.add_api_route 无条件先以 self.dependencies.copy() 初始化路由依赖集再合并单路由 dependencies（声明下限 0.115.0 同有此行，全版本区间行为一致），internal_supervisor.py 的 8 条 add_api_route 路由与 /health 装饰器路由（装饰器亦委托 add_api_route）受同一路由级 dependencies=[Depends(require_supervisor)] 保护，不存在传播分叉。其二，集成测试已断言未授权被拒：tests/integration/test_supervisor_rpc.py 在真实 uvicorn 子进程上对 add_api_route 注册的 PATCH desired-state 与 GET /profiles 断言无令牌请求返回 401，对 /health 断言无令牌/错令牌 401（含 WWW-Authenticate: Bearer）与正确令牌 200——若依赖未传播，这些请求将直达 handler 返回 200，断言本身即传播失效的回归哨兵。连带确认原 summary 的结构性判断：被复用的 v1 handler 与 require_supervisor 依赖同挂在 supervisor_router 上，不存在『路由落在会话面而依赖落在别处』的缺口，该内部面的鉴权在本轮证据下已验证成立。残余覆盖缺口如实记录（不改变裁决、不另立 finding）：bind/observed/events 三条写路径未见各自的无令牌 401 断言（仅有带正确令牌的 200 流，但与已被负向断言的兄弟路由走同一注册循环与同一合并依赖，属尚未逐条补测而非机制差异），且 require_supervisor 的 503 未配置分支在全部测试中无断言——列为后续补负向断言的测试建议。影响范围：本路其余 findings 均不以该内部面鉴权未验证为前提（f_global_architecture_03 的两代信任基调论证针对 legacy 面与两代身份域的划分），故本关闭不触发任何连带调整。",
    "result": "refuted"
  },
  "q_architecture_03": {
    "followup_sha256": "e3a4958800d8934084ef992a170715b06060b9c7dc8f64c558a2dc3e1092289c",
    "reason": "采纳精查对 viewer 接入完整调用链的静态核对：gateway/server.py 取浏览器原始 Origin 头后立即以 normalize_origin 规范化，此后 raw 值不再被使用，先以规范化值对 Gateway 自身白名单（配置加载时已由 normalize_origins 规范化）校验，再经 gateway/api_client.py 原样写入请求体转发；API 侧 internal_gateway 的 ViewerAuthorizeRequest.origin 为无校验器的纯 str 字段、handler 原样透传，而比对的另一侧 app.state.allowed_origins 在启动时同样由 normalize_origins 生成——即 auth/service.py:310 的未规范化精确比对实际比较的是两个规范化值，带默认端口（80/443 被剥离）或尾斜杠（path 仅允许空或 '/'）的合法 Origin 在 Gateway 侧已被归一，不可能因该比对被误拒；全仓检索确认生产环境中 /viewer-authorize 的唯一调用方就是这条 Gateway 链，不存在绕过规范化的转发路径，故『实际可用性缺陷』不成立。对关联 finding 的影响（本回判仅记录结论，局部报告原文不改）：局部 finding f_backend_api_auth_02 定性下调——由潜在的实际可用性缺陷改判为纯口径/分层一致性问题：AuthService.authorize_viewer 本层不做规范化、隐性依赖全部调用方预先规范化，当前唯一生产调用链满足该前提；只有未来新增直达调用方传入原始头时才会转化为误拒，属潜在一致性隐患而非现存缺陷。对本路其他判断的影响：本路 findings 未以 f_backend_api_auth_02 的可用性缺陷定性作为论据，此下调不触发任何连带修改，架构宏观判断维持不变。",
    "result": "refuted"
  },
  "q_architecture_04": {
    "followup_sha256": "86e3e56bf893d0db65db00e3062ace24abc71e3444af91b66e38c74212f82959",
    "reason": "不立 finding 的裁决依据：克隆沿用源 fingerprint_seed 是产品有意定义而非实现疏漏。两处独立权威文档明文规定同一口径——生效 spec docs/specs/profile_management.md:30 写明配置复制『保留全部有效配置字段、标签与同一指纹种子』（该 spec 在 specs_index.md 生效清单内，按仓规在表即生效），docs/blueprint/persistence.md:107 独立复述『配置复制只写数据库：新 Profile ID、配置版本、标签与同一指纹种子』；且两份文档均在紧邻条目对 reset 给出相反口径（更新/重新生成指纹种子），证明 duplicate 与 reset 的 seed 策略是被有意区分的设计分工：复制保留同一指纹身份、重置换新指纹身份。实现与文档逐项一致：profile_service.py 的 duplicate_profile 以源配置 model_dump 仅覆写 name、seed 原样沿用，reset_profile 以 operation_id 确定性重播或随机生成新 seed，t013 归档交付记录亦按此记载；对 docs/specs 与 docs/blueprint 全量 grep『指纹种子/fingerprint_seed』无任何『克隆应新发 seed』表述，全仓 seed 规则仅三条（创建未提供则随机生成、复制保留、重置重生）。影响：原 question 中 backend_runtime_adapters 单元留下的跨包不确定项就此关闭——实现与产品定义无矛盾，无需立 finding，本 question 预设的『文档无定义则只能由用户裁决』分支不触发；本路宏观判断与全部 findings 均不受影响。",
    "result": "refuted"
  }
}
```
