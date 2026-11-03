# CBrowser 全仓汇总（review_20261103_185924）

## 目标、范围与约束

- 审阅对象：CBrowser 仓库在 HEAD `b47340828820960adc6725407df72c6e11ee348c`（2026-11-03）的工作树快照。
- 范围：全仓重审。盘点 822 个文本文件、176,080 行（排除本轮 OUTDIR 自身与上轮归档的 `_meta/`），按职责与行为链分为 22 个审阅单元，每单元八视角（contracts / correctness / design / documentation / performance / robustness / security / tests）静态细查。
- 方法约束：全程静态审阅——不运行代码、测试、构建或 Docker，不使用浏览器。所有 finding 的 verification 均为 static 或 suspected；运行期结论不在本轮证据内。
- 产品目标（据仓内文档）：多身份 / 隐私隔离的浏览器配置（profile）管理系统，单机单人部署包络（ADR 013）；公网穿透与原生 Linux x86_64 验证为 NOT_RUN / USER_WAIVED，多处文档如实单列。
- 未知前提：真实部署规模、并发 profile 数、宿主机环境（macOS / OrbStack 为已知验证环境）未由用户给出；涉及规模与性能的判断均以代码结构与文档声明为据。

## 系统构成：两代并存

仓库内有两代实现并行存在，这是理解全部跨包结论的前提：

- **legacy 单体**（`src/backend/`，包名 `backend.*`）：`main.py`（1843 行）单文件 FastAPI 入口，承载 profile CRUD、浏览器启停、VNC/CDP WebSocket 代理、剪贴板中继、产物上传下载、设置、关机与 SPA 托管；`browser_manager.py` 管 CloakBrowser 持久上下文；`database.py` 是手写 SQLite DDL（profiles.db），以列集相等为唯一版本判据、整表重建迁移。唯一访问控制是 AUTH_TOKEN，未设置即全开放（代码注释明示为 local dev 语义）。
- **v2 多服务**（`src/backend/cbrowser/` + `src/frontend/`）：API 控制面（Profile CRUD 与不可变配置版本、Argon2 单管理员会话、按 profile 授权的自动化 token、SSE 事件流、RuntimeCoordinator 的 desired/observed 状态收敛）、Supervisor（唯一 Docker socket 持有者，双容器 Browser+Stream 生命周期、启动门禁、iptables 网络策略、恢复协调器）、Stream Runtime Agent（容器内 UDS 服务，CDP 代理与下载捕获）、Gateway（viewer 信令隧道、Agent 注册表、授权 fail-closed）、React/Vite 前端（外壳 + 业务功能层，SSE 以 fetch 流式读取实现续传）。
- **契约面**：两份 OpenAPI（公开 v1 + 内部）与三份协议 JSON Schema（runtime agent / supervisor / stream）由导出脚本从源码模型生成并入库；compose.yaml 与五份 Dockerfile 定义部署，其中 compose 只部署 legacy 单容器。
- **.repo_template 工具链**：随仓分发的仓库治理工具链——`repo_task` 包实现 task.py CLI 状态机（note.md front matter 为文档状态权威、dispatch ledger JSONL 为执行权威、tasks_index.json 为可重建的派生索引）、repo_sync / repo_cleanup / repo_hygiene 机械脚本、skill 注册表（registry.json 为角色与调用图唯一事实源）、review prompt 模板与门禁 hook，以及该工具链自身的模板测试套件。
- **文档与归档体系**：docs/blueprint（长期真相）+ docs/specs（生效契约，specs_index 在表即生效）+ docs/findings（d001–d026 实验事实登记）+ ADR 001–014；docs/archive/ 是只追加证据层（tasks 账本、spikes 快照、上一轮 review 归档），仓规要求归档字节不可变、错误只能以勘误节纠正。

## 主要数据流、控制流与信任边界

- v2 启动链：API 为唯一数据库写者；Supervisor 从 API 拉取不可变配置快照并校验身份 → 写 snapshot.json（0600）→ API 绑定新 runtime_instance → 分配 UDP mux 端口 → 建 per-profile 网络 → 容器在启动门禁后运行（网络策略 helper 先装 iptables 规则、ready.json 原子落盘后入口才放行）。
- v2 运行链：浏览器 viewer 经 Gateway 信令隧道接入 Stream Agent；Gateway 每个授权决策都回调 API（authorize_viewer / runtime 查询），API 不可达时一律 fail-closed；运行时事件以 (profile_id, runtime_instance_id, config_version) 为栅栏、UUIDv5 确定性 ID 幂等去重，权威来自 Supervisor 的 Docker/Agent 观测，沙箱内文件事件仅作诊断。
- v2 身份面：管理员口令 Argon2 校验、双层滑窗限速；会话与自动化 token 库内只存 SHA-256、明文只出现一次；CBROWSER_ALLOWED_ORIGINS 为空时启动直接失败；内部 RPC 令牌未配置时返回 503 而非放行。
- legacy 链：单进程内完成全部功能，宿主机控制端点（shutdown / open-external）与剪贴板、产物存储都在同一信任域内，防护依赖 AUTH_TOKEN 与部署侧回环绑定。
- 模板工具链执行主线：task add → start（建 worktree）→ attempt reserve/claim（exact identity 校验）→ finish（AC 与证据门禁，一个 task 恰一个执行 commit）→ cleanup-worktree → integrate（另行授权）；失败恢复由 recovery 只读分类驱动，证据过期只能 amend 同一执行 commit 修复。

## 局部 findings 概览

22 个单元共 268 条：Critical 0、High 4、Medium 52、Low 165、Info 47。High 全部集中在两个单元：

- backend_core（legacy）：f_01 剪贴板正文前 60 字符写进 manager.log，与 diagnostics 的脱敏承诺直接冲突；f_02 serve_spa 兜底路由无路径包含校验、疑似可未授权穿越读取应用文件（suspected，静态未复现，包内测试零覆盖）。
- contracts_deploy：f_01 Supervisor 镜像 Dockerfile COPY 了 launch_args.py 但 .dockerignore 白名单未放行，镜像构建缺文件；f_02 legacy 生产 Dockerfile `FROM cbrowser:latest` 与 compose 给自身输出的同名标签构成自引用。

## 系统影响与跨包主线

1. **被部署的系统与被审最深的系统不是同一个。** compose 只交付 legacy 单容器；v2 的四个运行时镜像没有任何部署路径（f_contracts_deploy_04），且 Supervisor 镜像按当前 Dockerfile/dockerignore 组合构建即缺文件（f_contracts_deploy_01）。v2 的架构、协议契约与测试在代码层成立，但从仓库现有部署工件出发，用户实际跑起来的仍是 legacy 面——而 legacy 面恰是本轮 High 与多条 Medium 的所在地（鉴权 opt-in f_backend_core_03、open-external 缺同源 CSRF 防护 f_backend_core_04、整表重建静默丢列数据 f_backend_core_05、配额检查与建行分离可被并发绕过 f_backend_core_06）。DOCKER_DEPLOYMENT.md 对绑定地址、暴露面与架构的描述与 compose 现状矛盾（f_contracts_deploy_05）。
2. **fail-closed 是 v2 的一致基调，legacy 不共享。** v2 各单元反复确认同一设计语言：启动失败关闭、授权失败关闭、账本损坏行拒绝继续、指纹算不出返回空串、审计写失败中止状态迁移。模板工具链（repo_task）同样以 fail-closed 校准。legacy 面则以「未配置即开放」为默认，部署侧缓解（回环绑定 + 注入 AUTH_TOKEN）不在代码单元内、且模板 .env 中 AUTH_TOKEN 默认空与其自身「Required」注释矛盾（f_contracts_deploy_03）。
3. **事件转发层是 v2 可靠性主线上的具体裂缝。** Supervisor 的 consume_disk_events 在事件被 API 拒绝时不推进游标、每秒无限重试（f_backend_supervisor_01）；EventForwarder 把全部非 200 的 4xx（含 401/403/429）一律分类为永久 REJECTED 并隔离，与产物转发器的可重试 4xx 集合口径不一致（f_backend_supervisor_02）。状态权威与幂等设计本身扎实，但投递分类这一环与整体基调不齐。
4. **测试体系整体强，盲区呈系统性形态：「生产恒走、测试恒绕」。** 四个 tests 视角 partial 单元经补审后结论一致：套件在已覆盖处是行为级、断言扎实的（真实 git、真实 DB、失败路径与回滚、确定性时钟），但一批生产必经分支在测试中恒被绕开——PUT/PATCH 的 launch_args 校验（与双校验器矛盾叠加，f_backend_api_auth_09）、CSRF 的 Referer 回退分支、内部 RPC 未配令牌的 503 分支、宿主机控制端点 open-external/shutdown 的成功路径、repo_state.py 的子目录 CWD 调用（恰是其路径基准缺陷 f_template_scripts_state_01 的所在面）、board.js 1135 行零行为测试、registry.json 角色过滤分支从未执行、prompt 合并编号路径从未被驱动。另有测试可信度问题：模板 E2E 套件的 review PASS 证据由测试支持代码合成、项目验证门禁被整体关闭（f_template_tests_01）；多处 fixture 重实现生产语义并与生产漂移（fixtures 的两套 Selkies shim 互相不一致、Gateway→API 假面无条件放行自动化授权、资源探针重实现配额投递链）；前端 dist 新鲜度门禁按文件名而非实际消费判定、多条 lane 可静默测旧 dist。
5. **文档与归档的漂移集中在「记录未随事实修订」。** handoff.md 整体过期一轮（仍称下一步 t015、pending 为空）；findings 登记表未随 ADR 013 修订，8 篇 TURN/ICE 类 finding 仍标「有效」且含已失效指令；blueprint/artifacts.md 的 chown 回退口径与 ADR 014 及 security.md 直接冲突。归档层内部亦有口径矛盾：上一轮 adoption_decision.md 对交叉证伪条数同文件内 33 与 30 两种口径、同一穿越漏洞的核实等级在记录集内有 suspected / 静态确认 / 现网实测三档从未对齐；t018 的闭环证据退化（AC-004 在自声明必需验证从未执行时打勾关闭、Review 处置表样板化、19 轮审查超记录上限无授权留痕）。
6. **模板工具链自身有真实缺陷，不只是文档问题。** repo_cleanup 主 walk 按仓库根相对路径剪枝、嵌套 node_modules 与 bulk 树不被剪枝，与其防误删承诺不符；user_prompts 编号在显示与 revoke 之间不是同一编号空间，revoke 可能作废错误条目且无回归测试；link-skills 路径下 _ensure_symlink 对真实目录直接 rmtree 且报告谎称原内容入回滚栈（该路径根本没有事务）；sync_opencode_commands 对 registry.json 用硬下标，缺登记时 KeyError 穿透 apply 的回滚例外集。

## 跨包冲突与待核实线索（保留原文，不擅自统一）

- **Gateway 控制令牌比对可能恒不匹配**（backend_stream_gateway:0）：gateway/server.py 将 `read_secret_file(gateway_token_file)` 的返回值直接 .encode() 比对，而 gateway/api_client.py 对同一函数结果显式 .strip()；secret_files 的实现位于 backend 单元，本单元未核对该函数是否 strip 尾随空白。若不 strip 且令牌文件带尾随换行，Supervisor 控制端点将不可用。需跨单元精查 secret_files 实现与两处调用方。
- **Supervisor 内部面的鉴权依赖框架传播语义**（backend_api_auth:0）：该面通过 add_api_route 复用 v1 handler，授权完全依赖 FastAPI 路由级 dependencies 对其传播生效；本轮按框架既定语义与兄弟单元集成测试静态判定生效、未运行验证。若传播不成立，该面将无鉴权，影响面大，值得以运行证据复核——但本轮静态约束下只能列为线索。
- **Gateway 与 Selkies 的连接方向**（backend_supervisor:0 与 backend_stream_gateway 汇总）：Stream 侧 INPUT iptables 策略只接受回环、已建立连接与 UDP mux 端口；设计看似假设 Stream 主动向 Gateway 发起信令，但 Gateway 是否会新开 TCP 连接到 Selkies（18096）无法从任一单元单独确认。两侧单元都把这一问留给了对方。
- **serve_spa 穿越的运行期可达性**（backend_core:0）：取决于随仓 Starlette/uvicorn 对 %2e%2e%2f 的解码与点段处理，静态未复现；归档记录集内对同一漏洞的核实等级表述亦不一致（见主线 5），本轮维持 suspected。
- **幂等键的跨端语义**（frontend_features:1 与 backend 幂等设计）：前端确实会产生「同 Idempotency-Key、不同请求体/路径」的组合；后端以 sig_hash 不匹配抛 IdempotencyConflictError 收口（backend_runtime_adapters 汇总），两端组合后的用户可见行为（冲突报错还是静默回放）未在任一单元内闭环。
- **duplicate profile 的 fingerprint_seed 语义**（backend_runtime_adapters:1）：克隆沿用源 seed 是产品定义问题（有意共享指纹还是应发新 seed），代码单元内无法判定。
- **归档任务的实体修复未独立复核**（archive_tasks:1）：p006 / p008 以具体 commit 关闭，其挂载代码的实体修复在 backend/supervisor 单元范围内，归档单元仅核对了处置链形式完整。

## 覆盖与限制

- 纯静态审阅：未运行任何代码、测试、构建或 Docker 校验；套件在 HEAD 的实际通过状态未经执行验证，多处 flake / 时序类判断标为 suspected。
- spikes 与 tasks 归档引用的运行证据（.scratch 下的门禁日志、黑盒原始 JSON）不在仓库内，归档单元只能核对账本间一致性与与当前代码的吻合，无法复核原始日志本身。
- 上一轮审阅的 _meta 产物按仓规不入库，归档 bundle 的完整审计链部分依赖仓外产物（f_archive_reviews_05）；本轮对归档文档只判定其内部一致性，不改判其技术结论。
- 75 条单元 uncertainties 中，3 条（backend_core:2、template_scripts_state:1、template_scripts_ops:1）已由 synthesis 的 uncertainty_resolutions 处置（均为 tests 视角 partial 经独立补审闭合，有补审记录与新增 finding 为据）；其余未处置项按契约自动传播为最终报告的限制。
- 本轮审阅不包含对上轮审阅结论的回归对照；归档文档作为本仓的普通文档单元按其自身一致性受审。

## 证据入口

- 单元计划与盘点：`_meta/unit_plan.json`、`_meta/inventory.json`、`_meta/review_plan.json`
- 局部结果（每单元 summary + findings + 八视角执行记录）：`_meta/local_<unit_id>.json`（22 份）
- 局部聚合概览：`_meta/local_overview.md`
- 本汇总的输入绑定：`_meta/synthesis.json`（各 local 文件 SHA-256 与本文件 SHA-256）

## Local uncertainty resolutions

```json
{
  "backend_core:2": {
    "reason": "tests 视角的 partial 已由独立 viewfix 补审闭合：补审者全量通读 backend_tests 单元 11 个文件（约 4,700 行）并对 main.py 全部路由及 open-external/shutdown/serve_spa/env_file 关键字在 src/backend/tests、tests/unit、tests/integration 三处定点 grep 核对，views.tests 已置 completed，定点结论（serve_spa 与剪贴板日志零覆盖）已立为 f_backend_core_15 并新增 f_backend_core_16–19。",
    "evidence": [
      "local_backend_core.json views.tests（reviewer 35a17c6b-39b6-48e2-8c67-a3ce425b7866）",
      "local_backend_core.json summary.uncertainties[3] 补审记录",
      "local_backend_core.json findings f_backend_core_15–19"
    ]
  },
  "template_scripts_state:1": {
    "reason": "tests 视角的 partial 已由独立 viewfix 补审闭合：补审者通读 template_tests 单元中实际测试本单元代码的 23 个测试文件并以 grep 核对各模块测试引用分布，views.tests 已置 completed，覆盖空白已立为 f_template_scripts_state_17–20。",
    "evidence": [
      "local_template_scripts_state.json views.tests（reviewer c9728a76-4372-4866-9499-a834848de156）",
      "local_template_scripts_state.json summary.uncertainties[4] 补审记录",
      "local_template_scripts_state.json findings f_template_scripts_state_17–20"
    ]
  },
  "template_scripts_ops:1": {
    "reason": "tests 断言质量已由独立 viewfix 补审静态核对：补审者通读实际行使本单元代码的测试文件（test_repo_cleanup/test_repo_sync/test_repo_hygiene/test_check_review_status/test_render_review_prompts/test_md_format/test_precommit_hook/review_support 全文及 test_pending、test_design_regressions、test_review_report_regressions 相关段落），并回查 repo_sync.py、repo_cleanup.py、md_format.py 对应实现行逐项核对覆盖缺口，views.tests 已置 completed，缺口已立为 f_template_scripts_ops_13–19；『未运行测试验证』一层由 synthesis 的静态审阅限制统一承载。",
    "evidence": [
      "local_template_scripts_ops.json views.tests（reviewer 4b21145b-832c-44ca-a165-cb5f5adf6b4c）",
      "local_template_scripts_ops.json summary.uncertainties[3] 补审记录",
      "local_template_scripts_ops.json findings f_template_scripts_ops_13–19"
    ]
  }
}
```
