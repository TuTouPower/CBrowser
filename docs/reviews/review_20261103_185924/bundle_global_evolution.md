# bundle_global_evolution

## Summary

v2 为演进做了方向正确的投资（Alembic 版本化迁移、源码模型导出契约、fail-closed 基调、文档/执行双权威状态机），但演进路径的最后一公里未通：legacy→v2 切换链（t012 部署产物 → t009 正式验收 → t010 数据迁移与下线）在 tasks_index 中全部停留在 backlog，且链首的部署工件本身未就绪（Supervisor 镜像构建即坏、compose 无 v2 服务），当前唯一可部署面仍是 legacy。在双轨并存期持续运转的恰是全仓演进机制最弱的一面：legacy 数据层无版本、重建即静默丢数据。此外，四类『随每次变更发生的成本』均无机械保障、只靠人工纪律——架构决策向 findings/blueprint/spec/AC 的传播、入库契约与源码模型的新鲜度、测试 fixture 与生产语义的同步、模板分发失败后的事务善后；本轮证据显示人工纪律在 ADR 013 删除 coturn/TURN 一役中已在至少五个文档面漏改。结论：长期成本的主要来源不是 v2 的设计债，而是双轨并存期的持续时间（存量数据与 legacy 缺陷暴露面同步增长）与四类无门禁的人工传播面；切换链每推迟一轮，这两项都单调变差。

## Findings

- [High][90] docs/tasks_index.json；compose.yaml；config/docker/supervisor_runtime/Dockerfile.dockerignore — legacy→v2 切换链全部停留在 backlog 且链首前置条件未就绪，双轨并存期无收敛时点
  - ID: f_global_evolution_01; verification: static
  - Evidence: docs/tasks_index.json：t012（v2 正式部署产物与部署文档，depends_on t018）→ t009（正式拓扑验收，depends_on t012）→ t010（数据迁移、legacy 下线与正式切换，depends_on t009）三者 status 均为 backlog; f_contracts_deploy_04：compose.yaml 从不引用四个 v2 运行时镜像，v2 拓扑在本仓部署面内无任何成套运行方式；compose 唯一服务仍是 legacy 单容器（image cbrowser:latest + config/docker/Dockerfile）; f_contracts_deploy_01：Supervisor 镜像 Dockerfile COPY launch_args.py 但 .dockerignore 白名单未放行，链首 task（t012 部署产物）要交付的镜像按现工件构建即缺文件; blueprint decisions.md 记载『正式用户数据迁移仍由 t010 负责，当前仅隔离 v2 测试数据』；回查 src/backend/cbrowser/ 全包对 profiles.db 零引用，不存在任何现存迁移代码; 切换未完成期间 legacy 仍是唯一生产面，其缺陷面（f_backend_core_01/02 两条 High 及鉴权 opt-in、配额绕过等 Medium）持续暴露，且 profiles.db 存量数据随使用单调增长，最终迁移的存量规模只增不减
  - Impact: 项目主线（v2 正式切换）没有已启动的执行路径：不是缺设计，而是整条三环依赖链无一环开工，且第一环的输入工件就是坏的。双轨并存不是静态状态而是持续计息的状态——每多运行一轮 legacy，最终迁移要搬运的存量数据更多、legacy 面的安全与数据缺陷暴露更久、两套数据库与两套运行语义的维护面继续双倍存在。若无外力排期，这是全仓最大的长期成本来源。
  - Fix: 把 t012 的前置缺陷（镜像构建、compose v2 编排）作为链首小步先行落地并以真实 build 验证，再按 t012→t009→t010 顺序启动切换链；在切换完成前，明确 legacy 为『冻结演进、仅修安全/数据类缺陷』的维护口径，避免继续向 legacy 投入新功能加深存量绑定。

- [Medium][90] src/backend/database.py:122；src/backend/cbrowser/adapters/database/migrations.py — 唯一生产面的数据层无版本化迁移：列集相等整表重建静默丢列、无日志无备份，与 v2 Alembic 形成演进双轨
  - ID: f_global_evolution_02; verification: static
  - Evidence: f_backend_core_05：legacy init_db 以列集相等为唯一版本判据，列集不符即整表重建，列集之外的全部列数据被静默丢弃，无日志、无备份; backend_core 单元约束记录：『legacy 与 v2 两套数据库（profiles.db 手写 DDL vs cbrowser.db + Alembic）同仓并存，schema 演进互不感知』; v2 侧已有正轨机制：decisions.md 记载嵌入式 SQLite + WAL + Alembic 版本化迁移，migrations.py 在仓；但该机制只覆盖尚无正式用户数据的 v2 面; legacy 承载的是 profile 配置这一核心资产（代理凭据、指纹、备注），且在 t010 落地前它是唯一生产数据面，任何跨版本/跨栈切换启动一次即触发重建判定
  - Impact: 升级路径上存在不可恢复的静默数据损失点，且它位于当前唯一生产面：用户升级一次 legacy 版本就可能永久丢失列集外的 profile 资产且无任何告警或回滚材料。与 f_global_evolution_01 叠加：切换链推迟越久，legacy 存量越大，这一重建机制在存量上的单次破坏面也越大。v2 的 Alembic 投资无法对冲此风险，因为它管不到 legacy 的数据。
  - Fix: 在 t010 落地前给 legacy init_db 加最小护栏：重建前自动备份原库文件、丢弃列数据时写日志并计数、列集差异时优先 ALTER 增列而非整表重建；长期仍以 t010 的正式迁移收口，不再扩展 legacy schema。

- [Medium][95] scripts/run_gates.sh；scripts/export_openapi.py 等四个导出脚本；schemas/ — 入库契约无新鲜度门禁：导出脚本靠人工重跑，门禁不做重导出 diff，漂移既无检测也难协商
  - ID: f_global_evolution_03; verification: static
  - Evidence: 回查 scripts/run_gates.sh 全文：不含任何 export_openapi / export_*_protocol / schemas 引用，本地门禁从不重跑导出脚本或比对 diff（与 contracts_deploy 单元 uncertainties 中『no freshness gate exists in run_gates.sh』一致）; 契约面规模：两份 OpenAPI + 三份协议 JSON Schema 均由源码模型生成并入库，是五个服务间唯一的机器可读契约; f_contracts_deploy_08：三份协议 schema 的版本字段不一致（runtime agent 有 version，supervisor 与 stream 无），消费者无法统一做兼容协商; f_contracts_deploy_10：v1 OpenAPI 中 profile 运行时状态为裸字符串，而 supervisor 协议对同一字段用枚举，两面状态词汇漂移不会被 schema 检查发现；f_contracts_deploy_07：导出协议 schema 为未判别的 anyOf 联合，边界校验强度低于进程内 pydantic 模型
  - Impact: 服务还在演进期、协议字段仍在增删时，入库契约与源码模型脱节只是时间问题，且脱节发生时没有任何门禁会变红：消费方（前端生成类型、协议校验、后续新服务）会按过期契约开发，问题要到联调或运行时才暴露。版本字段不一致又使漂移发生后连『对端是什么版本』都无法统一判定，协商成本被迫靠人工。
  - Fix: 在 run_gates.sh（及 CI 对应环节）加入契约新鲜度门：重跑四个导出脚本后 git diff --exit-code schemas/，非空即红；同时统一三份协议 schema 的 version 字段约定，并让 v1 OpenAPI 的状态字段引用与 supervisor 协议同源的枚举定义。

- [Medium][90] docs/findings/；docs/blueprint/；docs/specs/；docs/v2_architecture_plan.md；docs/handoff.md；docs/tasks/t009_v2_full_acceptance/ — 架构决策向下游文档的传播全靠人工且已在 ADR 013 一役多面漏改，后续每次架构变更都要重复支付全额传播成本
  - ID: f_global_evolution_04; verification: static
  - Evidence: f_docs_current_02：ADR 013 删除 coturn/TURN 凭证轮换/ICE 代次接管后，findings 登记表中 8 篇 TURN/ICE 类 finding 仍标『有效』且含已失效指令，按现文执行可能复活已删除机制; f_docs_current_03：blueprint/artifacts.md 仍写 chown 失败回退 0755/0644，与 ADR 014 及 security.md 直接冲突——安全类删除决定在被约定为『当前长期真相』的文档里未传播; f_docs_current_05/06/07：v2_architecture_plan.md 正文仍以 TURN 轮换为现行设计且无替代标注；blueprint/architecture.md 两处残留旧表述；specs/webrtc_remote_display.md 仍称适配层处理已被删除的 RTC 配置; f_docs_current_04：t009（全量验收 task）的 AC-005 仍要求验证已删除的 coturn/凭证切换，字面不可执行，验收期必然临时改口径; f_docs_current_01：handoff.md 整体过期一轮（仍称下一步 t015、pending 为空）；f_docs_current_09：CHANGELOG 最新条目止于 v2 之前的 [0.1.9]（2026-10-16）
  - Impact: 文档体系的层级设计本身合理（ADR 定夺、blueprint 为长期真相、specs 在表即生效、findings 登记事实），但决定作出后的横向修订没有任何机械检查点，传播成本是 O(受影响文档面数）的人工逐处比对，且已实证会漏：漏改面不是无关紧要的角落，而是后续 task 的约束来源（findings)、验收口径（spec/AC）与实现依据（blueprint)。架构还在快速演进期（ADR 已至 014），每次变更都按同一模式重复支付并重复漏改，读者对『现行文档可信』的信心会被持续侵蚀，最终使整套文档制度贬值。
  - Fix: 给架构级 ADR 增加收尾清单机制：ADR 条目必须列出受影响的 blueprint/spec/findings/plan/AC 面并逐项勾销（可由 task 收尾门禁校验 ADR 中声明的传播面已修订）；对 findings 登记表增加与 ADR 的交叉引用字段，状态修订随 ADR 落地同 commit 完成。

- [Medium][90] tests/fixtures/；tests/e2e/；tests/integration/ — 测试资产以『重实现生产语义』的 fixture 为主要形态，同步负担随生产演进持续放大且漂移方向是假绿
  - ID: f_global_evolution_05; verification: static
  - Evidence: f_tests_integration_fixtures_02：两套测试本地 Selkies client shim 重实现生产 adapter 的标签身份语义且彼此不一致，被验证的其实是 shim 的行为而非生产 adapter; f_tests_integration_fixtures_03：同一 Gateway→API 内部面有两套不一致的 fake，其中 HTTP fake 无条件放行 automation 授权且忽略 viewer origin，弱于生产语义; f_tests_integration_fixtures_07：Supervisor 的 Docker 边界在单元内有至少四套手搓 fake，各自独立漂移；f_tests_integration_fixtures_01：资源探针重实现 supervisor→gateway→agent 配额投递链而非行使生产链; f_tests_e2e_stream_frontend_03/04：AC-010 在测试内重实现 StreamAgent、stream 运行时套件以 GatewayMockServer + Web Locks shim 验证标签/媒体语义，均非生产代码; 新鲜度保障同样脆弱：f_tests_e2e_stream_frontend_01 的 dist 门禁按测试文件名含 'frontend' 判定而非实际消费（今日成立纯属命名巧合）；f_tests_integration_fixtures_04 多条 lane 声称查 freshness 实则未查，可静默测旧 dist
  - Impact: 这批 fixture 不是简单的测试代码重复，而是生产语义的第二份、第三份实现：生产每次修改协议信封、授权判定、标签仲裁或配额投递，这些副本都必须有人记得手工跟随；漏跟随的后果不是测试变红，而是测试继续全绿地验证旧语义——测试资产从演进护栏转为演进负债的速度取决于生产变更频率，而本仓正处协议与拓扑仍在变动的阶段。维护成本随生产演进超线性增长（副本数 × 变更面），是长期成本中最隐蔽的一项。
  - Fix: 按『离生产越近越优先』的顺序收敛副本：Gateway→API 假面与 Selkies shim 各保留一套并由生产类型/契约 schema 驱动校验，资源探针与 AC-010 改为行使生产投递链与生产 agent；dist freshness 门禁改为按 lane 实际消费声明（harness 层统一断言 build stamp）而非文件名约定。

- [Medium][88] .repo_template/scripts/repo_sync.py（sync_opencode_commands、sync_dir/sync_skill、_ensure_symlink） — 模板分发同步机制的失败模式集中在演进中间态，且失败后留悬挂事务需人工善后
  - ID: f_global_evolution_06; verification: static
  - Evidence: f_template_scripts_ops_04：sync_opencode_commands 对 registry.json 用 roles[name] 硬下标，registry 与 skills 目录不一致（模板演进中的常见中间态）时 KeyError 穿透 apply 的回滚例外集，apply 中途崩溃、已写文件不回滚、事务悬挂为 begun 状态，后续操作需人工清理; f_template_scripts_ops_05：sync_dir/sync_skill 复制时不处理目标侧文件软链，copy2 跟随软链写出 .repo_template 树外，该目标不在 FileTransaction 快照清单内，回滚覆盖不到; f_template_scripts_ops_03：link-skills 路径下 _ensure_symlink 对宿主位真实目录直接 rmtree 且报告谎称『原内容入回滚栈』，该路径根本没有事务——与 apply 共用同一函数却无同等安全等级; f_template_scripts_ops_14：registry.json 角色过滤分支（生产恒走）在测试套件中从未执行，模板演进最常触及的这条路径无回归网
  - Impact: .repo_template 是要持续向本仓及未来消费仓分发演进的工具链，sync 不是一次性动作而是每次模板升级都要重复走的路径。当前失败模式的触发条件恰是演进本身（registry 与目录短暂不一致、消费侧残留软链），失败代价也不是『修正后重试』而是人工清理悬挂事务与核对未回滚的半成品写入。演进频率越高，这条链的期望善后成本越高，且会在消费仓侧放大（每个消费仓各付一份）。
  - Fix: apply 开始前先跑 skill_registry 的一致性校验（其本就能以 ValueError 报告 registry/目录不一致），把中间态拦截在写盘之前；roles 访问统一改 .get 并显式报错；为 link-skills 路径接入与 apply 同级的事务或至少在 rmtree 前强制备份并如实报告；补 registry 过滤分支的回归测试。

- [Low][85] docs/archive/tasks/；docs/archive/reviews/；docs/archive/pending/ — 归档只追加纪律的纠正机制未被实际执行，记录可信度随轮次单调衰减且编号空间随轮次必然碰撞
  - ID: f_global_evolution_07; verification: static
  - Evidence: 仓规（AGENTS.md）：docs/archive/ 内部文件只准新增，账本错误只能以勘误节纠正——纠正成本被制度性地定为『追加一份新记录并期望读者交叉阅读』; f_archive_tasks_02/04：t018 Review 处置表退化为样板文本、19 轮审查超记录上限 5 轮无授权留痕；t015 收尾与 handoff.json 仍称 Round 2 PASS，与实际 6/5 轮且 Round 3 曾推翻该 PASS 不符——两处均未见勘误节追加; f_archive_tasks_05/06：p011 以 resolved 关闭但子项自认未做且无承接；p001 的关闭理由与 p005 逐字相同、以 p005 为主语，单项审计无法确认其关闭依据; f_archive_reviews_01/04/07：adoption_decision.md 对交叉证伪条数同文件内 33 与 30 两种口径并存；决策项计数与附表映射不一致；跨轮 A/R 编号碰撞（上一轮 A26 与本轮 A26 指向不同事项），且单元明确指出『随着轮次增多，两套编号在同一仓内并存，碰撞只会加重』; f_archive_tasks_11：多份归档账本保留模板示例行，污染 finding id 空间，自动解析处置表的工具会读到不存在的 finding
  - Impact: 归档层是后续整改立项与审计回查的依据层，其价值完全取决于记录可信度。现行纪律把纠错成本设得很高（原文不可改、只能追加勘误），而收尾环节又没有对勘误落地的校验，于是已发现的错误大多原地保留：读者每引用一份旧账本都要自行甄别其口径。编号不按轮次隔离命名空间，使碰撞成为随轮次必然加重的结构性问题。这不是单点文档卫生，而是审计基础设施随时间贬值的演进成本。
  - Fix: 给 task/review 收尾门禁增加账本一致性校验（处置表逐条可解析、轮次与预算账目与 attempt 记录对齐、关闭理由非模板复制）；决策编号改为带轮次前缀的命名空间（如 R20261103-A26）并在新轮 adoption 中只引用带前缀编号；已发现的现存错误按纪律补写勘误节而非留待读者甄别。

- [Low][85] scripts/run_gates.sh:19；src/backend/requirements.txt 与 pyproject.toml；.env.example 与 config/.env.example — 版本基线多处不锁定或双份维护，长期复现性随上游与时间漂移
  - ID: f_global_evolution_08; verification: static
  - Evidence: f_contracts_deploy_06：run_gates.sh 用未 pin 的包组装测试环境，门禁结果随上游发版漂移，『红』可能只是环境变了而非代码回归，绿也不能证明环境与既往一致; f_backend_core_11：legacy requirements.txt 与 pyproject.toml 依赖声明漂移，同一包版本约束冲突且集合互不一致，不同安装路径解析出不同依赖组合（且框架行为差异会改变如 serve_spa 穿越可达性等结论的前提）; f_contracts_deploy_13：四个 v2 运行时中 stream 镜像的 pydantic patch 版本与其余三者漂移，同一协议负载在不同服务上由不同 pydantic 构建校验/序列化; f_contracts_deploy_11：.env.example 在仓库根与 config/ 各存一份字节相同副本且无同步机制，两份可独立编辑，迟早漂移（AUTH_TOKEN『Required』措辞正是只会改一处的典型文本）
  - Impact: 单项都很小，但形态一致：同一事实（依赖版本、环境模板）存在两个以上无机械绑定的副本或不锁定来源。时间越久，『在我这能跑』『门禁时红时绿』类不可复现问题的归因成本越高，并会侵蚀门禁作为演进护栏的信号价值——与 f_global_evolution_03/05 同属『靠纪律维持一致性』的负债，只是落在版本面。
  - Fix: 门禁环境改用仓内锁文件安装（与运行时 requirements.in→txt 同一机制）；legacy 二选一保留单一依赖声明源（pyproject 为准、requirements 由其生成）；.env.example 只保留一份、另一处改软链或在门禁中 diff 两份。

## questions

```json
[
  {
    "counterevidence": "task.md 已含逐项迁移 AC、校验与回滚要求，则迁移契约已就绪、只待排期，本问撤销，仅保留 f_global_evolution_01 中『链未启动』的部分",
    "evidence_needed": "docs/tasks/t010_v2_data_migration/task.md 的契约区与 AC 原文：是否逐项列出迁移对象（profiles.db 行、profile 浏览器状态目录、artifacts 字节与索引）、迁移后校验与回滚条款",
    "id": "q_evolution_01",
    "question": "t010（数据迁移、legacy 下线与正式切换）的 task 契约是否已定义 profiles.db 存量数据、浏览器状态目录与 artifacts 的逐项迁移范围、校验方式与失败回滚，还是目前仅有标题级规划？",
    "units": [
      "docs_current",
      "backend_core"
    ]
  },
  {
    "counterevidence": "存在已记录的上游升级演练/版本变更 task 且 probes 只依赖上游公开接口，则升级路径已验证，本问撤销",
    "evidence_needed": "Selkies pin 的变更历史或升级 spike 记录；f_tests_integration_fixtures_13 所述 probes 依赖 vendored selkies 私有内部的具体位点清单；ADR 中关于上游版本锁定的取舍原文",
    "id": "q_evolution_02",
    "question": "上游 Selkies 2.1.0 与 CloakBrowser 的升级路径是否可行：vendored Selkies web 资产、stream probes 对上游私有内部的依赖面有多大，仓内有无上游版本升级的演练或兼容记录？",
    "units": [
      "contracts_deploy",
      "tests_integration_fixtures",
      "archive_spikes"
    ]
  },
  {
    "counterevidence": "已有成文的备份/恢复或回退契约（含演练记录），则回退路径成立，本问撤销",
    "evidence_needed": "blueprint/specs 中关于 cbrowser.db 备份、恢复或版本回退的契约原文；migrations 中 downgrade 的实际实现口径；切换 runbook 类文档是否存在",
    "id": "q_evolution_03",
    "question": "v2 数据层已确立单向迁移取舍（部分迁移 downgrade 不恢复旧键）之下，正式切换后若需版本回退或数据恢复，有无备份/恢复路径的设计或记录？",
    "units": [
      "backend_api_auth",
      "backend_runtime_adapters"
    ]
  },
  {
    "counterevidence": "脚本中存在显式格式版本校验或迁移分支，或 usage.md/architecture.md 有成文的格式兼容政策，则本问撤销",
    "evidence_needed": "repo_sync.py 与 repo_task 解析 registry/front matter/ledger 的代码位点：是否存在格式版本字段、版本校验或旧格式迁移分支；模板侧是否有格式变更的兼容政策文档",
    "id": "q_evolution_04",
    "question": "模板格式（registry.json 结构、task note.md front matter、dispatch ledger 行格式）发生演进时，repo_sync/repo_task 对旧格式消费仓有无版本识别、显式拒绝或迁移行为，还是默认新旧格式同构、遇到旧格式时行为未定义？",
    "units": [
      "template_scripts_ops",
      "template_scripts_state"
    ]
  }
]
```

## question_decisions

```json
{
  "q_evolution_01": {
    "result": "refuted",
    "reason": "采用精查对 t010 task.md 契约区全文的逐行核对：迁移对象已逐项列明（AC-001 清点 Profile/Tag/Artifact 与旧字段映射、AC-002 计划 15.2 全部有效字段与浏览器状态迁移无丢失、AC-003 运行状态映射规则），校验方式成文（AC-004 备份校验后恢复到独立空数据根且源文件 hash/数量与恢复结果一致、AC-005 以真实旧格式 fixture 对 dry-run/成功迁移/重复执行/失败回滚/备份恢复独立黑盒验证），失败回滚成文（AC-004 故障注入任一步失败恢复旧 DB 和目录、task.md:74 切换失败恢复旧数据根并重新启用旧版容器）；未执行仅因 status=backlog、depends_on=t009。据此回判 refuted：f_global_evolution_01 中涉及 t010 的含义收窄为仅保留『切换链未启动、链首工件未就绪、无现存迁移代码』，删除任何『迁移契约仅标题级规划/尚未就绪』的读法——瓶颈在排期与依赖，不在契约设计；f_global_evolution_01 的 High 定级与『双轨并存无收敛时点』的结论不变，本路其余 findings 不受影响。",
    "followup_sha256": "dfddbfd480f66fcdc48fc6cc6cebf082c9c7793846b9fb7d862a93e541edfcc9"
  },
  "q_evolution_02": {
    "result": "confirmed",
    "reason": "采用精查的版本史与私有耦合面核对：git log -S 显示 Selkies 2.1.0 与 CloakBrowser 0.6.4 两处 pin 自引入以来从未 bump，仓内无任何升级演练/版本变更记录（仅 d017 与 browser_runtime.md 的『升级须重验』指示）；私有依赖面不止 probes——生产 stream_agent/x11_keymap.py 对 _XTestKeyboard 的 prebind/text_room/_find_spare_keycodes 三个私有方法做 monkeypatch 并读写 _spare_keycodes，agent.py 直接 import selkies.__main__ 与 selkies.webrtc_mode.WebRTCService。据此回判 confirmed，并为宏观判断新增权重：前任 summary 所列四类『随每次变更发生的成本』（决策传播、契约新鲜度、fixture 同步、模板分发善后）之外，上游版本演进构成第五类无机械保障的经常性成本；缓解事实同时成立（私有耦合是 ADR 007 成文接受的取舍、最大一块私有 ABI 耦合已由 ADR 013 主动切除、vendoring 已机械化为双重 sha256 校验 + 2007 行清单再生），故定性为『纸面可行、从未走过』而非路径不可行。首次 bump 还将与 f_global_evolution_01 的切换链相遇（pin 随 t012 部署进入生产面），放大切换后早期的演进风险；与 f_global_evolution_05 中 probes 的私有依赖属同一风险形态在生产侧的对应面，不改动任何既有 finding。",
    "followup_sha256": "820aed50ac3ff7461562b4f962ff1b4b5b1e2f96d6579a7f5e538323dc49c798"
  },
  "q_evolution_03": {
    "result": "confirmed",
    "reason": "采用精查的两层区分结论：迁移期备份在 v2 架构计划 §15.5 与 t010 AC-004/AC-005 中有设计（覆盖 /data/cbrowser.db 等五项、失败恢复旧 DB 与目录、黑盒演练），但 t010 仍为 backlog、AC 全部未勾选、迁移 CLI 不存在，属未实施的设计；切换后常态则全面缺失——生效契约层（blueprint/persistence.md 与全部 specs）对 cbrowser.db 备份、恢复或版本回退零条款，唯一运维备份程序（DOCKER_DEPLOYMENT.md §4）只覆盖 legacy 数据根 ~/.cbrowser 而非 v2 的 /data/cbrowser.db，0006 downgrade 为 no-op 不恢复被删键、0004 以常量默认值重建列、0003 直接删列，运行代码无任何 downgrade 调用、迁移运行器升级前不备份数据库文件，仓内无任何演练记录。据此回判 confirmed，并加重宏观判断中『回退路径』一腿：t010 切换是一扇单向门——切换完成时 legacy 回退面随下线消失，而 v2 侧没有数据库级恢复底线接续，这使 f_global_evolution_01 所述双轨收敛的终点自带数据风险，也意味着 f_global_evolution_02 的 legacy 数据层风险不会随切换自动终结、而是被『无备份的单向迁移』接续。本回判不新增 finding，新增权重记于本路宏观判断。",
    "followup_sha256": "6b9f2c5b0b9ff77fa0fa13fc713cf6042c234eed2babc2dd15a894fe0d498979"
  },
  "q_evolution_04": {
    "result": "refuted",
    "reason": "采用精查的分项核对：workflow schema / task front matter 有 usage.md:104 成文政策『不做运行时兼容、sync 时强制迁移、拒绝双轨解析』，且 repo_sync.py 有整节强制迁移实现（_migrate_task_text 删除旧字段 schedule_status、blocked 改写 active、补轮次上限字段，_inspect_workflow_task_dir 处理旧布局 spec.md→task.md+note.md，force_migrate_workflow_tasks 覆盖 tasks 与 archive/tasks 且有已登记 worktree 或无法安全迁移时整体拒绝）；registry.json 无 version 字段，但随模板树硬同步整体覆盖、结构不一致或未知 role 即 ValueError 显式拒绝，不存在消费仓旧格式长期存续的面。『默认新旧同构、旧格式行为未定义』对主格式不成立，回判 refuted。唯一例外是 dispatch ledger：无 version 字段、不在 sync 强制迁移覆盖内、旧格式行靠 project_attempts 的投影 skip 静默容忍，与成文政策口径不一致，精查已单独立 Low finding f_followup_q_evolution_04_01。与 f_global_evolution_06 的关系：属同一『演进中间态』风险形态的第四个面——f_06 的三项机制（registry 硬下标 KeyError 穿透回滚例外集、软链 copy2 写出事务快照外、link-skills 无事务 rmtree 且谎报回滚）发生在同步写盘路径、失败后留悬挂事务需人工善后，ledger 例外发生在数据面、失败模式是静默丢弃而非 fail-closed；两者不互相否定或重复，ledger 例外反而印证 f_06『失败模式集中在演进中间态』的判断。另注：精查对 repo_sync registry 两处解析的核对（状态侧 roles.get 容错 / 同步侧 roles[name] 硬下标）与 f_06 所据局部证据 f_template_scripts_ops_04 一致。f_global_evolution_06 的结论与范围不变。",
    "followup_sha256": "875099696b8f09b6eb9b4e1b2dd912f4d7dfc19c4c96355f203bd2ff98c1bb5a"
  }
}
```
