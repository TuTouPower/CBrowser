# bundle_global_architecture

## Summary

宏观判断：v2 的目标架构本身是成立的——控制面（API 唯一写库、不可变配置版本快照）、执行面（Supervisor 唯一持 Docker Socket、实例围栏、事件 spool+去重、对账恢复）、媒体面（Gateway/Agent 分离、ICE 代次轮换）的职责划分与信任边界设计，在 blueprint 与代码之间基本一致，且有真实 Docker E2E 证据链支撑；这是本仓最扎实的部分。但当前 HEAD 的系统级结构并不等于这套架构，原因有三。其一，唯一可出厂的部署产物是跨代拼接：生产 Dockerfile 把 v2 前端 bundle（单入口 main.tsx→app/router、/api/v1 + 会话/CSRF 客户端）装进只跑 legacy backend.main 的镜像，而 legacy 后端没有任何 /api/v1 路由、也不 import cbrowser 包，与它配套的 v1 前端反而是不可达死代码——发布工件由 COPY 行偶然决定，不由任何架构决策决定。其二，v2 的五服务拓扑没有任何可部署定义：全仓唯一的 compose 是 legacy 单服务，拓扑只存在于三份互相分叉的测试 fixture 里，t012 未完成意味着这套分解目前只被测试装配过、从未被部署装配过。其三，若干被蓝图宣称为不变量的接缝在代码里只是约定而非结构：Supervisor 上报 handler 与用户会话面共用同一批函数、授权取决于挂载位置，observed 状态的唯一上报权在构造上就不存在；Profile 这一核心实体同时有两个数据权威（profiles.db 运行时自动 DDL vs cbrowser.db+Alembic），桥接迁移 t010 仍是 backlog 而生效 spec 已把迁移工具写成已交付。此外契约体系呈不对称覆盖：数据面 happy path 有字节级漂移守卫，鉴权/错误语义与承载 TURN 凭证的信令 payload 却在契约之外；媒体面进程内状态（ICE 代次、agent 注册表）没有控制面那样的对账者，楔死后容器仍『健康』。结论：在 t010/t011/t012 落地并把部署工件收敛为单一栈之前，对本仓做任何『系统已按 v2 架构运行』的判断都不成立；架构风险不在 v2 设计，而在双栈共存期没有强制收敛的机制——文档、spec、CI、发布四条链都已各自与实现脱节，双栈的维护税会随时间复利。

## Findings

- [High][85] config/docker/Dockerfile:1-27, config/docker/entrypoint.sh:27, src/frontend/index.html, src/frontend/src/main.tsx, src/frontend/src/shared/api/client.ts:133-200, src/backend/main.py:530-1298 — 出厂部署工件是跨代拼接：v2 前端 bundle 装进只运行 legacy 后端的镜像，两栈在部署边界互不兼容
  - ID: f_global_architecture_01; verification: static
  - Evidence: config/docker/Dockerfile 将 src/frontend/dist/ 拷入镜像，entrypoint.sh:27 执行 `uvicorn backend.main:app`；前端唯一入口 index.html 加载 /src/main.tsx，main.tsx 只挂载 app/router + app/providers（v2 应用）; v2 前端 API 客户端（shared/api/client.ts）全部调用 /api/v1/* 并使用 Cookie 会话 + CSRF；而 legacy src/backend/main.py 的路由面只有未版本化的 /api/*（/api/auth/login、/api/profiles、/api/shutdown 等），全文件无 /api/v1 路由，也不 import cbrowser 包（已逐项 grep 核对）; 与 legacy 后端配套的 v1 前端（src/App.tsx + components/*，约 2900 行）从 main.tsx 不可达（frontend_shell 单元已证闭合导入图），即出厂 bundle 根本不是 v1 界面; Dockerfile 的构建期校验（verify_frontend_dist.py）只核对 Selkies 静态资源与哈希清单，不核对前端与后端的 API 代际是否匹配；compose.yaml 同样只定义 legacy 单服务
  - Impact: 按官方路径部署得到的前端在登录第一步即调用 legacy 不存在的 /api/v1/auth 接口，产品按自身发布工件不可用；更深层的影响是『系统』在部署边界没有定义——任何一栈的单独正确性都不能推出工件的正确性，且没有门禁能发现这种跨代错配（CI 本身也已因路径失效整体不可用）
  - Fix: 在 t012 收敛前先立一道代际一致性门禁：构建期断言 dist 内 API 基路径与镜像内后端实际路由面相交非空（或直接断言 entrypoint 目标与 dist 的代际标记一致）；中期二选一——要么发布工件切到 cbrowser.api.main + v2 拓扑，要么前端构建临时切回与 legacy 匹配的入口，并把该决定写入 blueprint/decisions，避免 COPY 行继续冒充架构决策

- [High][90] src/backend/cbrowser/api/v1/router.py:56,706-835, src/backend/cbrowser/api/internal_supervisor.py:48-99 — 授权是挂载位置的属性而非操作的属性：Supervisor 上报 handler 同时挂在管理员会话面，observed 状态『唯一上报者』接缝在构造上不成立
  - ID: f_global_architecture_02; verification: static
  - Evidence: f_backend_api_auth_02：bind_runtime、report_observed_state、report_runtime_event 三个 Supervisor 上报 handler 定义在 profile_router 上，该 router 的唯一守卫是管理员会话 + CSRF（router.py:56 require_csrf_and_origin），浏览器会话可直接绑定运行时实例、伪造 observed 状态与 exit 事件; 同一批 handler 函数又被 internal_supervisor.py:57-99 原样复用到只挂 require_supervisor（服务 Bearer）的 supervisor_router 上；handler 签名内无任何授权依赖，两个信任面靠『同一个函数被 include 到哪个 router』区分; internal_supervisor.py 的注释自述该服务面意图为配置读取/意图/上报且永不 Profile CRUD，但反向边界（用户面不得行使上报权）在代码中不存在对应物; v2 恢复语义把 observed 状态与 exit 事件当作事实来源（正常 exit 清除 desired、异常 exit 触发 2/10/30 重试与阻断），伪造上报可直接驱动对账与恢复决策
  - Impact: 蓝图的核心状态所有权模型（API 记 desired、Supervisor 报 observed、Runtime Agent 产事件）依赖上报通道的排他性；当前实现里任何持有管理员会话的浏览器上下文（含被 XSS/CSRF 残余风险命中的会话）都能伪造运行时事实，且未来任何一次误挂载都会静默改变某个操作的信任面——这是边界完整性缺陷，不是单个端点的鉴权疏漏
  - Fix: 把授权下沉为操作级不变量：上报类 handler 自身声明服务身份依赖（Depends(require_supervisor) 写进 handler 或专用子 router），用户面 router 不再复用同一批函数对象；如确需同面提供只读视图，另写只读 handler。补一条架构测试：枚举全部路由，断言上报类路径只出现在服务面挂载下

- [Medium][95] compose.yaml, config/docker/supervisor_runtime/Dockerfile, config/docker/gateway_runtime/Dockerfile, config/docker/browser_runtime/, config/docker/stream_runtime/, tests/fixtures/ — v2 五服务分解没有可部署定义：拓扑只存在于三份互相分叉的测试 fixture 中，从未被部署装配过
  - ID: f_global_architecture_03; verification: static
  - Evidence: 全仓仅有一份 compose.yaml 且只定义 legacy 单服务；v2 只有各 runtime 的独立 Dockerfile 与 cbrowser/api/main.py 这个『Production entrypoint』，没有任何把 API/Supervisor/Gateway/coturn/Caddy 按蓝图接线（secret 文件、端口、网络、数据根）的部署工件; 五服务拓扑目前只在 tests/fixtures 的 harness 里被装配，且 frontend_probe/harness.py 与 gateway_probe/topology.py 各自重复实现整套容器图、turnserver.conf 在三处生成并已出现 relay 端口范围不一致（tests_integration_fixtures 单元证据）; 仓库任务体系自认 t012（正式 Docker 发布）未完成、t009 已降级；即按项目自己的账本，v2 拓扑的唯一装配证据来自测试
  - Impact: 分解的粒度成本（七个进程、secret 文件网、UDS、spool、内部 RPC）已经付出，但其收益（隔离性、可独立替换）从未在真实部署中兑现；t012 落地时必须从测试代码反推生产拓扑，而 fixture 已经分叉，届时『以哪份 fixture 为准』本身会成为无权威答案的问题
  - Fix: 把拓扑定义从 fixture 中抽出为单一权威工件（一份 v2 compose 或等价的拓扑清单文件），fixture 改为消费该工件而非各自重写；在 t012 完成前，至少将三份 harness 的容器图/turnserver.conf 生成收敛到一份共享实现，消除继续分叉的通道

- [Medium][95] src/backend/database.py, src/backend/cbrowser/ (SQLAlchemy/Alembic 数据层), docs/specs/storage_and_artifacts.md:25-29, docs/tasks/ (t010 backlog) — 核心实体 Profile 存在两个数据权威且桥未建：legacy 侧 schema 权威被运行时自动 DDL 反转，v2 侧迁移仍是 backlog 而 spec 已按已交付叙述
  - ID: f_global_architecture_04; verification: static
  - Evidence: legacy database.py 按列集差异自动重建表（启动时以代码为准修正 schema，静默丢列方向且无测试），v2 使用 SQLAlchemy 模型 + Alembic 迁移——同一实体两套 schema 治理哲学完全相反; 两套存储（profiles.db 与 cbrowser.db）的 Profile schema 已分叉，修复只落一侧（backend_core 单元的双栈 High 证据）；桥接任务 t010（数据迁移）仍是 backlog，t011（删 legacy）未启动; docs_current 单元证实：生效 spec storage_and_artifacts.md 已把 t010 才交付的迁移工具（--dry-run、保留 Cookie）写成已交付行为且 AC-002 已勾选——文档层已提前宣布桥存在
  - Impact: 过渡期没有终点约束时，双存储不是迁移状态而是永久状态：出厂镜像持续把用户数据写进未来必须被营救的 legacy 存储，新功能每落一处都要先选边，且 spec 的提前勾选使『迁移已完成』的假象进入长期真相层，后续真正做 t010 时连需求基线都被污染
  - Fix: 给双栈共存设硬性收敛条件并写进 decisions：例如冻结 legacy 存储的 schema 变更（database.py 自动重建改为显式版本断言、启动不兼容即报错），t010 完成前禁止在任一栈新增 Profile 字段；先行纠正 storage_and_artifacts.md 的三态违规，把迁移工具改回未交付表述并取消 AC 勾选

- [Medium][90] schemas/openapi/cbrowser_v1.json, schemas/stream/agent_protocol.json, src/backend/cbrowser/api/v1/ (auth dependencies), docs/blueprint/ (testing.md 门禁命令) — 契约体系覆盖不对称：数据面 happy path 有字节级漂移守卫，鉴权/错误语义与承载 TURN 凭证的信令 payload 在契约之外
  - ID: f_global_architecture_05; verification: static
  - Evidence: 正面基线：OpenAPI 路由与实现 29/29 对齐、三份协议 schema 与生成脚本逐字一致且有漂移守卫测试、前端生成类型与 OpenAPI 路径集 22/22 无漂移（contracts_deploy、frontend_shell 单元）; f_backend_api_auth_03/04：导出的 OpenAPI 中 securitySchemes 为空、无任何 operation 声明 security、无 X-CSRF-Token 参数，且系统性遗漏实现实际返回的 401/403/404/413/429/507——生成客户端在类型层面无法表达鉴权与失败语义; contracts_deploy 单元：stream 线协议 schema 只覆盖信封，payload 为 dict[str, Any]，承载 TURN 凭证的具名 payload 类型不在导出契约内——最敏感的数据恰是契约盲区; 内部 RPC 面以 include_in_schema=False 整体排除在 OpenAPI 之外（app.py:336-340），服务间契约仅靠 supervisor/runtime 两份手写 protocol schema + 复用同一批 handler 函数维持，无独立漂移门禁覆盖挂载面
  - Impact: 契约给人的完备印象（29/29、字节钉版）只对读路径成立；任何按契约生成的新消费者（客户端、测试、未来的第二实现）都会在鉴权、限流、错误处理上与真实系统脱节，而 TURN 凭证 payload 的无契约状态意味着 Gateway/Agent 任一侧改字段都不会触发任何门禁
  - Fix: 把安全语义纳入导出契约：为 OpenAPI 补 securitySchemes、每 operation 的 security 与 CSRF 头参数、以及实现实际返回的错误响应码，并加一条『契约响应码 ⊇ 实现可达响应码』的守卫测试；为 stream 协议补具名 payload schema（至少覆盖凭证类消息）并纳入现有漂移守卫机制

- [Medium][80] src/backend/cbrowser/gateway/ (server.py, config.py), src/backend/cbrowser/stream_agent/agent.py:378-407, src/backend/cbrowser/stream_agent/ice_transport.py:427-512, src/backend/cbrowser/supervisor/ (recovery_coordinator) — 媒体面没有对账者：控制面有 Supervisor 持续对账，Gateway 进程内状态（ICE 代次轮换、agent 注册表）楔死后无人收敛，容器仍显示健康
  - ID: f_global_architecture_06; verification: static
  - Evidence: backend_stream_gateway 单元：ICE 代次接管失败后 restart_pending 永久为 True，后续 prepare_restart 一律抛『still pending』，凭证轮换楔死直到凭证过期、流死亡（ice_transport.py:427-512）；agent 心跳循环被单个 try/except 包住整圈，一次瞬时错误即永久停跳，约 30s 后被 Gateway 逐出并掉光其 viewer（agent.py:378-407）; 对照面：Supervisor 对容器面有 reconcile 循环 + OperationJournal + 恢复协调器，任何单点异常被隔离并收敛（backend_supervisor 单元）；Gateway 的代次/agent 状态没有任何等价的外部对账或自愈入口，进程存活即被视为健康; RTC 轮换时序参数（lifetime/interval/lead，含 NaN）无有限性/顺序校验，配置错误可致网关整体离线或轮换静默失效（gateway/config.py:96-118）——同为『状态机无外部监督』的表现
  - Impact: 系统的可靠性叙事建立在控制面的对账设计上，但用户实际感知的可用性（画面是否还在）在媒体面；媒体面故障模式是『进程健康、状态楔死、流静默死亡』，与现有健康检查/恢复机制正交，运维侧无法从 Supervisor 的恢复语义中获益
  - Fix: 给媒体面补最小对账：Gateway 暴露代次状态与 agent 注册表的可观测快照，restart_pending 增加超时自清/强制重置路径，心跳循环改为单次迭代级 try/except 并对连续失败上报；或把代次楔死纳入 Supervisor 的健康判定，使容器级恢复能覆盖进程内楔死

- [Medium][85] .repo_template/scripts/ (repo_task/ledger.py:22-49, repo_cleanup, repo_sync, link-skills), .repo_template/tests/, docs/tasks/, docs/pending/ — repo_template 是与产品同仓的第二套状态权威系统：其破坏性命令作用于同一棵树，而其拒绝护栏恰是全仓测试最薄处，缺陷经 sync 向消费仓传播
  - ID: f_global_architecture_07; verification: static
  - Evidence: 按仓内 AGENTS.md，task/pending/findings 的状态权威在 docs/ 文件 + .repo_template/scripts 状态机，skills 经软链进入三个 agent 宿主——这套『开发流程操作系统』与浏览器产品共用一个仓库、一套门禁、一次审阅; template_scripts_state 单元 High：ledger _read_unlocked 遇 OSError 静默返回空事件列表，账本不可读时 attempt 号从 1 重新分配，破坏其自述的 fail-closed 不变量——状态机的根基操作是 fail-open 的; template_tests 单元：purge 的全部拒绝护栏在测试中被 stub 成放行、drop 有一条从不调用 cmd_drop 的手工模拟假测试、review 证据由 fixture 伪造 PASS 且项目门禁在夹具中被整体禁用；template_scripts_ops 单元：repo_cleanup 剪枝可误删嵌套目录、repo_sync 跟随目标侧软链写出仓外且不在回滚范围、link-skills 无事务却能 rmtree 真实目录且报告谎称已入回滚栈; 该工具链按设计经 repo_sync 同步到其他消费仓，本仓既是它的开发地也是它的第一个受害者，缺陷的爆炸半径超出本仓
  - Impact: 产品侧用『唯一写者 + 围栏 + 日志』精心守护运行时状态，流程侧守护仓库状态的却是 fail-open 的账本与未被真实测试覆盖的破坏性命令；一次 purge/cleanup/sync 误动毁掉的是任务账本与审阅证据链本身——即证明产品正确性的那套记录。两套系统的信任要求不同却共享同一道（且已失效的）CI 门禁
  - Fix: 把工具链按独立系统对待：ledger 读失败改为 fail-closed 并补真实拒绝路径测试（purge 护栏禁止 stub 成放行、至少一条端到端拒绝用例走真实 git 仓）；破坏性命令统一要求事务/回滚覆盖或显式 dry-run 默认；模板变更在本仓之外至少一个消费仓做同步冒烟后再发布

## questions

```json
[
  {
    "counterevidence": "若存在第二个构建入口、构建期 API 基路径注入，或基础镜像的 dist 覆盖顺序使最终生效的是 v1 前端，则 f_global_architecture_01 的『工件不可用』结论降级为『双前端共存的文档问题』",
    "evidence_needed": "release.yml 全部构建步骤、cbrowser:latest 基础镜像的来源定义（仓内或上游）及其 frontend/dist 内容构成、任何 vite 构建参数或入口覆盖",
    "id": "q_architecture_01",
    "question": "发布链（release.yml / CI / 基础镜像 cbrowser:latest 的来源）中是否存在任何一步会生成不同于 src/main.tsx 入口的前端 bundle、改写 API 基路径，或让基础镜像自带与 legacy 后端配套的前端，从而使出厂工件实际不是跨代拼接？",
    "units": [
      "contracts_deploy",
      "frontend_shell",
      "repo_ops"
    ]
  },
  {
    "counterevidence": "若存在这样一份与 fixture 一致的部署工件，f_global_architecture_03 应降级为『拓扑定义未被 CI/fixture 共同消费』而非『不存在』",
    "evidence_needed": "非测试路径下对 v2 服务编排的完整检索：compose 片段、启动脚本、runbook 中的具体命令序列，以及它们与 fixture 拓扑的一致性",
    "id": "q_architecture_02",
    "question": "仓内（docs/guides、scripts、spikes 报告或任何非 tests 路径）是否存在一份可执行的 v2 拓扑装配说明或脚本，已经被实际用于在本机以五服务形态运行 v2，而不仅仅是 fixture？",
    "units": [
      "contracts_deploy",
      "docs_current",
      "tests_integration_fixtures"
    ]
  },
  {
    "counterevidence": "若信封带版本字段且读取侧有显式兼容/拒绝逻辑并有测试，则该通道与 WS 协议同等受契约治理，f_global_architecture_05 的『契约盲区』范围相应收窄",
    "evidence_needed": "spool 文件的实际字段结构与写入/读取两侧代码、protocol schema（schemas/runtime/*）是否覆盖磁盘信封、错位版本的测试用例",
    "id": "q_architecture_03",
    "question": "Runtime Agent → Supervisor → API 的磁盘 spool 事件信封（event_forwarder 的 {key}.json）是否有版本号或 schema 约束，单容器滚动替换造成版本错位时是拒绝、兼容还是静默丢弃？",
    "units": [
      "backend_supervisor",
      "backend_runtime_adapters",
      "contracts_deploy"
    ]
  },
  {
    "counterevidence": "若无任何合法调用方，f_global_architecture_02 的修复成本降为直接摘除挂载；若存在承重调用，则问题升级为『用户面与服务面共用写路径』的设计冲突，需先拆分用例再收边界",
    "evidence_needed": "前端源码与 e2e 中对这三条路径在 /api/v1/profiles 面上的调用检索，以及 API 侧调用日志/测试中对该挂载的依赖",
    "id": "q_architecture_04",
    "question": "挂在管理员会话面上的 Supervisor 上报 handler（bind_runtime、report_observed_state、report_runtime_event）是否被 v2 前端或任何合法用户面流程实际调用，即该会话面挂载是承重设计还是纯冗余暴露？",
    "units": [
      "backend_api_auth",
      "frontend_features",
      "frontend_shell"
    ]
  }
]
```

## question_decisions

```json
{
  "q_architecture_01": {
    "result": "refuted",
    "reason": "采纳精查的穷尽式否定结论：release.yml 的 Docker job 未设 file: 而根 Dockerfile 不存在、原生打包 job 引用的 packaging/ 脚本在 HEAD 不存在，发布链根本不构建 config/docker/Dockerfile、更不运行任何前端构建；全仓唯一前端构建为 package.json 的 build 脚本，唯一 HTML 入口 index.html→/src/main.tsx，vite.config.ts 无 base/define/rollupOptions.input 覆盖且 src 内 VITE_/import.meta.env 零命中，API 基路径无改写机制；Dockerfile 的目录 COPY 会覆盖同相对路径的 index.html，legacy main.py 经 bundle_dir() 伺服的正是该合并后 dist。问题预设的三条候选反证（基础镜像自带 legacy 前端、compose 同名 tag 直跑旧镜像、dev proxy 转发）逐条不成立：前者无法越过 COPY 覆盖且无 dist 时 COPY 直接使构建失败，后者是原样运行旧上游应用而非本仓构建产物，proxy 不进入 dist。cbrowser:latest 在仓内无任何定义出处，该事实加重的是同名 tag 问题（已由 contracts_deploy 记录），不改变跨代拼接结论。 Effect: none — f_global_architecture_01 的措辞与严重度（High）不作任何修改，原判断完整维持。",
    "followup_sha256": "44eef557c45d0973d2b2d53290852a39b02cc7cf845357444494c585a6ebbda3",
    "decision": "upheld",
    "followup": "followup_q_architecture_01.json"
  },
  "q_architecture_02": {
    "result": "confirmed",
    "reason": "采纳精查的全仓+git 历史检索结论：五服务拓扑在仓内只实现了一次，即 tests/fixtures/gateway_probe/topology.py（镜像以 CBROWSER_*_TEST_IMAGE 环境变量注入 digest、secret 运行时临时生成，是夹具形态）；生产侧 Caddyfile 与 turnserver.conf 均不存在（全仓 Caddyfile 只有 fixture 生成器）；scripts/ 无任何启动/编排脚本，无 Makefile/justfile，workflows 不构建任何 *_runtime 镜像；README 与 DOCKER_DEPLOYMENT.md 只给 legacy 根 compose 路径，四份 guides 均为单镜像构建+验证探针；仓内 t012 自述『正式compose/五服务镜像、Caddy/coturn配置』为 backlog 未开工。问题预设的反证（blueprint/计划的设计描述、handoff 记录的本机多容器运行、supervisor_validation 指南）经核对分别属于设计文档、用 fixture 本身驱动的运行、单镜像构建说明，均不构成夹具之外的可执行装配工件。 Effect: none — f_global_architecture_03 的措辞与严重度（Medium）不变；精查新 finding f_followup_q_architecture_02_01（Medium：v2 API 常驻服务的唯一镜像定义是测试 fixture 且被验证指南列为正式构建入口）予以采纳，作为本 finding『拓扑只存在于 fixture』的具体锚点补强证据链，不另行改写原 finding。",
    "followup_sha256": "4aecf5a9b03feacc37d4ae90cec3f1bea66998b61545329f150371a0719b7724",
    "decision": "upheld",
    "followup": "followup_q_architecture_02.json"
  },
  "q_architecture_03": {
    "result": "confirmed",
    "reason": "治理面疑点成立：两个 forwarder 的磁盘信封均无 version 字段（emit_event 写入的 8 键 dict 与两个 Record 模型皆无信封版本，config_version 是配置代次而非信封版本）；schemas/runtime/agent_protocol.json 的文档级 \"version\": \"2.0.0\" 从未被写入 spool 文件、读取侧也不校验任何 schema 文件，两侧只用当前代码的 pydantic 模型（extra=\"forbid\"）校验，错位版本测试为零。但问题中『拒绝、兼容还是静默丢弃』的单一答案不成立，失败姿态按通道分裂，必须分别记录：EventForwarder 侧是拒绝并隔离——校验失败移入 spool/quarantine（reason=\"schema\"）并留 warning 日志、文件保留可人工恢复，不是静默丢弃；真正静默的是 DownloadArtifactForwarder 侧——解析失败无任何日志、无隔离副本，且把 unparsed 标记持久化进 download_cursors.json，文件此后即使被修复也永久跳过，与同仓 EventStorage 对同一批文件的 fail-loud 姿态不一致。 Effect: 现有 findings 与 summary 无措辞需改：经 grep 复核，global_architecture.json 中没有任何 finding 把 EVENT spool 描述为静默丢弃（文中唯一『静默丢列』指 legacy database.py 的自动 DDL，与本问题无关），故按精查口径在此 decision 中明确纠正潜在误读——事件侧=有隔离留痕的拒绝、下载侧=静默永久丢弃。f_global_architecture_05 的『契约盲区』范围不收窄（信封确证在 schema 治理之外）。分裂行为以精查新 findings 进入记录并予以采纳：f_followup_q_architecture_03_01（Medium，下载侧静默永久丢弃）、f_followup_q_architecture_03_02（Low，事件信封无版本治理且 quarantine 分支无测试）。",
    "followup_sha256": "8270f39a148b929b52f1003721642b90a287b4d2b78fce60503f09a41f970f23",
    "decision": "adjusted",
    "followup": "followup_q_architecture_03.json"
  },
  "q_architecture_04": {
    "result": "confirmed",
    "reason": "采纳精查结论：生产 Supervisor 的全部上报只走内部面（core.py 与 event_forwarder.py 均 POST /api/v1/internal/supervisor/*，由 require_supervisor 服务令牌守卫），全部 Supervisor 行为测试同样只用内部面前缀；v2 前端手写代码对三条会话面路径零调用（命中仅在生成的 .d.ts 与 OpenAPI schema 机械产物中）。会话面挂载的唯一消费者是验收测试 test_v2_api_subprocess.py（AC-003/AC-006），它以管理员会话扮演 Supervisor 发起 bind/observed/events，属测试便利而非任何合法用户面流程——且该测试本身即是会话面越权可行性的活体演示。故挂载为纯冗余暴露，原判断成立且被强化。 Effect: f_global_architecture_02 的措辞与严重度（High）不变；其修复路径落入问题反证预设的低成本分支——直接摘除会话面挂载——但附一个前置条件：先把 test_v2_api_subprocess.py 的这批场景迁到内部面（为其 harness 配置 Supervisor 令牌），否则摘除会先撞红 AC 级测试。该前置条件由精查新 finding f_followup_q_architecture_04_01（Low）记录并予以采纳。",
    "followup_sha256": "2787e447d857926cbf265b51a64b22cb5d73d081d5ba81dcf8754bd5773788d3",
    "decision": "upheld",
    "followup": "followup_q_architecture_04.json"
  }
}
```
