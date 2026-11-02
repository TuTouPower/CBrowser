# bundle_global_evolution

## Summary

CBrowser's evolution risk is not code quality — the v2 core is well-built and the process apparatus (task ledgers, AC discipline, handoff chain, findings registry) is unusually mature for a single-author project. The risk is a widening gap between three clocks that no longer tick together: (1) the shipped clock is stopped — the only deployable artifact (compose + legacy stack) has been code-frozen since the 2026-10-26 reorganization and floats on unpinned >= dependencies; (2) the build clock is sprinting — 171 of 265 commits landed in one week (2026-W44), v2 features were still landing on HEAD day (2026-11-02, seamless clipboard), yet the entire cutover chain t009 (acceptance) → t010 (data migration) → t011 (remove legacy) → t012 (Docker release) sits at status backlog, and the frontier is being renegotiated downward instead (t014 dropped, t009 downgraded, both 2026-11-02); (3) the narrative clock runs ahead of both — an in-force spec already claims t010's migration tool as delivered with its AC checked, the blueprint ('current long-term truth') is wrong on at least two landed decisions within roughly a week of the burst, and CHANGELOG stops at 0.1.9 (2026-10-16), before v2 existed. Every month of delay raises the finishing cost, not through legacy code growth (frozen) but through acceptance-surface growth, doc-drift accumulation, and decay of the tacit knowledge concentrated in the burst week's ledgers. The test suite — the asset that should make the cutover safe — is itself least trustworthy exactly where the cutover will stress it: it couples to private internals, forks production semantics in fixtures, and silently skips its most expensive layers, so the first serious refactor risks teaching the maintainer to distrust or bypass it. The repo_template tooling shows the same inversion: its destructive commands (purge, cleanup, link-skills) carry the thinnest tests. Verdict:REQUEST-CHANGES trajectory — the project converges only if the cutover chain is started before the next feature lands; left as-is, the most likely future is a permanently 'almost shipped' v2, a rotting legacy deployment, and a documentation system whose structural freshness (same-day handoff, machine-maintained indices) lends false confidence to its semantic drift.

## Findings

- [High][90] docs/tasks/t010_v2_data_migration/note.md, docs/tasks/t011_v2_remove_legacy/note.md, docs/tasks/t012_v2_docker_release/note.md, docs/tasks/t009_v2_full_acceptance/note.md — 整个切换链（t009 验收→t010 数据迁移→t011 删 legacy→t012 正式发布）在 HEAD 全部仍为 backlog，而 v2 功能开发与范围下调在同一天继续：拖延成本随验收面增长、文档漂移累积与隐性知识衰减单调上升
  - ID: f_global_evolution_01; verification: static
  - Evidence: 四个 task 的 note.md front matter 在 HEAD(5136766) 均为 status: "backlog"（本轮实查）; HEAD 当日（2026-11-02）提交仍在落 v2 功能（7535802 feat(stream): seamless clipboard）并下调范围（856757d drop t014 remainder and downgrade t009；5136766 handoff 题为『t014 drop…t009 next』）——队列前沿在缩减验收面，而不是启动切换; legacy 侧 src/backend/main.py 与 v1 前端 App.tsx 自 2026-10-26 重组提交 524e34e 后零提交：legacy 代码已冻结，拖延成本不来自 legacy 增长，而来自 v2 验收面增长、文档漂移累积与 burst 期隐性知识衰减; 部署现实仍是 legacy：Docker 入口执行 uvicorn backend.main:app（repository_summary §1），即用户能跑的只有冻结栈; 精查 followup_q_evolution_01（confirmed）：docs/handoff.md 2026-11-02 节明言在跑的 cbrowser:latest 容器是旧版 VNC、v2 栈未运行；compose 数据根为 ~/.cbrowser（profiles.db + profiles/），t010 的迁移源集是作者真实在用的数据根而非近空集；但全仓无现网 Profile 数量、数据量或增长速率记录，数据累积速率不在本条论据内
  - Impact: t009 的验收面随每个新 v2 功能变大，t010 要对账的行为面随之上移；legacy 是当前唯一在跑的产品本体，拖延意味着已知的 legacy High（默认无鉴权、剪贴板日志）在局域网持续运行。成本上升的三根支柱是验收面增长、文档漂移累积（blueprint/spec 的错误陈述在无人纠正时会被后续 task 当作前提引用，见 f_02）与 burst 期隐性知识衰减；精查已证实迁移对象是真实在用的数据根，但其规模与增长速率无记录，故本条不以『每月新增数据』作为论据。最坏轨迹是 v2 永远『差最后四步』，而 legacy 部署长期无人收口。
  - Fix: 在下一个 v2 功能 task 之前先 start t009 并冻结验收面（新增功能只进 backlog 不进验收范围）；给 t010–t012 排定顺序与启动条件写入 handoff，使『下一步』不再是可无限下调的 t009 本身。

- [High][88] docs/blueprint/persistence.md:42-73, docs/specs/storage_and_artifacts.md:25-29, CHANGELOG.md:7 — 文档系统结构上自纠正、语义上自欺：索引/handoff 由脚本维护且当日新鲜，但内容级真相在 burst 后约一周内已多处失真，后来者会按错误事实施工
  - ID: f_global_evolution_02; verification: static
  - Evidence: docs/handoff.md 最新一节为 2026-11-02T20:12，与 HEAD 同日——结构纪律真实有效（本轮实查）; blueprint 自称『当前长期真相』，却仍写 failure_count>=3 阻断（ADR 008/代码/spec 均为第 4 次）且仍称 runtime_events 不随 Profile 删除级联（D1 决策已落地 spec 与代码，blueprint 未同步）——docs_current 单元实证; 生效 spec storage_and_artifacts.md 把 t010 才交付的迁移工具写成已交付且 AC-002 已勾选——三态纪律实锤违规（docs_current High）; CHANGELOG 停在 [0.1.9] - 2026-10-16，整个 v2 重构（171 提交的一周）零记录（本轮实查）; 门禁命令在 blueprint/testing.md 中硬编码开发者个人路径 $HOME/kar/code/.scratch——文档连『如何验证』都不可移植
  - Impact: 该仓的主要消费者是未来的 agent 会话与协作者，他们按 AGENTS.md 规则『写代码前读 blueprint、spec 在表即生效』行事——错误层恰好是被指定为权威的层。结构新鲜（handoff 当日更新）会给内容失真盖上可信印章：这是文档系统最危险的失效模式，比明显过期更难防。
  - Fix: 把 blueprint 的承重断言（阈值、级联语义、交付状态）纳入 task 收尾的强制对账清单，或降级 blueprint 自我定位为『设计意图』并以 spec+代码为真相；CHANGELOG 至少补记 v2 未发布段；spec 中引用未交付能力的 AC 不得勾选，改为指向对应 backlog tid。

- [High][85] tests/unit (coordinator 系列), tests/fixtures/gateway_fixture.py, tests/e2e (supervisor/stream 两组) — 测试套件的可演进性债务集中在切换最需要动的地方：私有内部耦合、夹具分叉生产语义、整层静默 skip——第一次认真重构就可能让套件信誉崩塌
  - ID: f_global_evolution_03; verification: static
  - Evidence: coordinator 测试直接置 _running、调私有 reconcile、按 tick() 内部调用顺序编排 api.get side-effect 列表（tests_unit_supervisor_runtime Medium）：行为不变的重构会成片变红，形状不变的回归能绿; 集成层 SupervisorGatewayFixture 的 visibility 语义与生产 Gateway 不同源（tests_integration_fixtures High）；tab 仲裁测的是已与生产 adapter 分叉的 web_lock_shim（tests_e2e_stream_frontend）; supervisor 与 stream 两组 E2E 靠环境变量存在与否 skip，CI 从不提供这些变量，整层可绿着零覆盖（两单元各一条 High 相互印证）; viewfix 补审四单元一致结论：本轮主要生产缺陷（对账隔离、serve_spa、sanitizer 穿透、ICE restart_pending 楔死、心跳单 try 等）全部没有能抓住它们的回归测试; domain/repository 测试用 create_all 建表而非跑迁移，模型↔迁移漂移——恰是 t010 的核心风险——结构上不可检; 精查 followup_q_evolution_03 分布统计：严格口径 7 条私有内部耦合 finding 横跨 5/6 个测试单元、至少 17 个测试文件，质心在 supervisor/coordinator，stream/gateway 次之，另有对钉版 Selkies 库 name-mangled 私有 API 的耦合；v2 runtime_agent 与 v2 API 本体基本干净，无直接耦合 finding
  - Impact: 爆炸半径按精查分布收窄：凡触碰 supervisor/gateway/stream 的切换步（t010 的 coordinator/repository 对账面、t011 的 legacy 删除面）都会触发私有内部耦合；只动 v2 runtime_agent 或 API 路由层的步骤基本不会触发。触发时套件要么成片假红（维护者学会批量改预期或 skip，与 AGENTS.md『禁止就地把旧预期改成实现输出』的纪律正面冲突），要么假绿放行。套件从资产变负债的转折点通常就是这种时刻，且一旦维护者开始不信任它，后续所有 task 的门禁都随之贬值。
  - Fix: 在切换链启动前做一轮测试去耦：coordinator 测试改走公开 tick/状态面、夹具 visibility 改为复用生产 Gateway 或删除自研实现、E2E 环境门控改为缺变量即 fail（或在 CI 提供镜像变量）、repository 测试改跑 Alembic 迁移建表。

- [Medium][82] .repo_template/scripts (repo_task/ledger.py:22-49, repo_cleanup, repo_sync, link-skills, purge) — repo_template 的破坏性命令恰是测试最薄处，而全仓未来每一次 task/归档/同步操作都要经过它们——工具链事故会直接摧毁流程所要保护的状态
  - ID: f_global_evolution_04; verification: static
  - Evidence: ledger _read_unlocked 遇 OSError 静默返回空事件列表，reserve 会从 1 重分配 attempt 号，与损坏行路径的 fail-closed 设计自相矛盾（template_scripts_state High）; repo_cleanup 剪枝按根相对路径匹配，嵌套 node_modules/data 不剪枝、未点名垃圾可在 apply 时被默认类别删除；repo_sync 跟随目标侧文件软链可写出仓外且不在回滚范围；link-skills 无事务却能 rmtree 真实目录且报告谎称已入回滚栈（template_scripts_ops 三条 Medium）; purge 的全部拒绝护栏在测试中被 stub 成放行、零覆盖；drop 有一条手工模拟的假测试；review 证据由 fixture 伪造 PASS 且项目门禁在夹具中被整体禁用（template_tests）; AGENTS.md 规定 task/pending/findings 的状态迁移只经这些脚本——它们是单点
  - Impact: 该工具链同时服务于本仓与模板的未来消费仓；一次 purge/cleanup 误删或 ledger 重号，损坏的是任务账簿与 git 历史本身——即全仓最成熟的证据链资产。且因其『平时都好用』，事故发生时更可能被误判为使用者错误而非工具缺陷。
  - Fix: 按破坏性排序补护栏测试：purge 拒绝分支先行（不 stub）、ledger 读失败改 fail-closed 抛错、cleanup/sync/link-skills 在动手前做目标包含与软链检查并让报告如实反映事务覆盖范围。

- [Medium][92] src/backend/requirements.txt:1-8, src/frontend/package.json (dependencies) — 钉版姿态与部署现实倒挂：未部署的 v2 栈 digest 钉版+版本锁定，实际部署的 legacy 栈依赖全为浮动区间，冻结代码会在无人注视下被依赖漂移改变行为
  - ID: f_global_evolution_05; verification: static
  - Evidence: src/backend/requirements.txt 全部为 >= 区间（fastapi>=0.115.0、pydantic>=2.0、cloakbrowser[geoip]>=0.6.3、websockets>=14.0 等），无 lock 文件（本轮实查）; 前端 dependencies 全为 ^ 区间；与之对照，v2 四个 runtime 镜像 digest 钉版、requirements 全量版本锁定（contracts_deploy/repo_ops 正面确认）; 生产镜像本身 FROM cbrowser:latest 无 digest（contracts_deploy High）：基础镜像与 Python 依赖双层浮动; legacy 代码自 2026-10-26 冻结——意味着未来任何一次生产镜像重建，都是『新依赖跑旧代码』且无 CI 门禁能拦住（CI 路径已失效，f_repo_ops_01）
  - Impact: cloakbrowser/fastapi/pydantic 任一上游 minor 变更都可能让重建出的生产镜像行为漂移甚至起不来，而此时团队注意力全在 v2，故障定位会被误导向配置/环境。冻结期越长，首次重建的漂移面越大，与 f_01 的拖延成本叠加。
  - Fix: 给 legacy 栈生成并入库一份当前可运行的完整 lock（pip freeze 等价物）并钉住基础镜像 digest——这是冻结资产的标准保存动作，成本一小时量级；或在 t012 中明确 legacy 镜像只增不重建。

- [Medium][80] git 历史（2026-W44: 171/265 提交）, docs/tasks/archive/t001_v2_runtime_validation/note.md, docs/archive/ — big-bang 式作者集中：全仓 64% 的提交在一周内由单作者+agent 会话产出，设计理由沉淀在体量巨大的过程账簿里，新接手者的成本主要是考古而非读码
  - ID: f_global_evolution_06; verification: static
  - Evidence: git log 统计：总 265 提交，其中 2026-W44 单周 171 条；历史起点 2026-03-12（上游血统），v2 主体在一个 burst 内成形（本轮实查）; 关键理由载体是归档账簿（如 t001 note.md 单文件数百行过程记录）与 d001–d025 findings——密度高但无压缩层；本应承担压缩职责的 blueprint 已被证明不可靠（f_02）; 归档 handoff 含 32 处开发者本机绝对路径与 session id/PID（archive_tasks）——账簿是为原作者的连续性写的，不是为新读者写的; t014 在 HEAD 当日被 drop 且仅部分合并（e7f58ce partial merge → 856757d drop remainder）：burst 式推进的范围反复在链尾持续发生
  - Impact: 若作者中断数月或引入协作者，接手者须先重建『v2 为何如此、哪些已验证、哪些是叙述超前』的图景，而最短路径（blueprint/spec）恰好失真。知识衰减速度与 f_01 的切换拖延相乘：拖得越久，重启切换链的考古成本越高。
  - Fix: 在 t009 验收范围内加一项有界产出：一份由验收过程生成的 v2 现状实录（已验证行为清单+未验证清单），替代 blueprint 成为新读者的入口；归档账簿保持原样作证据层，不再承担导读职责。

- [Low][78] docs/pending/todo/ (仅 p014), docs/pending/archive/ (p011) — pending/findings 闭环机制存在『纸面闭环』先例且当前队列近乎为空：resolved 信号的可信度在缓慢贬值
  - ID: f_global_evolution_07; verification: static
  - Evidence: p011 标 resolution=resolved 归档，但其 reason 自认子项 f012 未做，且 live 侧无任何承接（archive_tasks Medium，本轮复核 live todo 仅 p014、parked 为空）; p001 与 p005 的 resolution reason 逐字相同且主语错位（复制粘贴）——闭环文本未被当作证据对待（archive_tasks Low）; 本轮静态审阅在同一代码基线产出 325 条 findings，而 live pending 队列只有 1 条：已知债务与在册队列之间没有稳定的回流通道，债务主要活在 review 报告里，而报告按仓规会被 repo-hygiene 迁入 archive
  - Impact: 机制本身设计良好（脚本迁移、一条目一文件），但若『resolved』可以无验证地写入、review 债务又不回流 pending，长期看账簿的信号价值衰减为仪式价值——与 spec AC 假勾选（f_02）是同一种失效在不同子系统的复现。
  - Fix: pending archive 时要求 resolution 附可回查证据（commit/测试/后继 pNNN），脚本侧至少校验 reason 非空且不与他条目重复；每轮 review 的 High/Medium 应有显式去向（pNNN 或当场驳回记录），而非随报告归档沉底。

- [Low][85] src/frontend/src/App.tsx + src/frontend/src/components/ (v1 树), src/frontend/src/app/ (v2 树) — v1 死前端树（约 2900 行、不可达）与双份 API 客户端/登录页/设置 UI 长期在树：每次搜索驱动开发与工具扫描都会双份命中，演进摩擦持续存在
  - ID: f_global_evolution_08; verification: static
  - Evidence: main.tsx 只挂 v2 的 app/router+providers，v1 树形成以死 App.tsx 为根的封闭导入图（frontend_shell High，从演进视角降为 Low：不影响运行，但影响每一次后续修改）; 仓内已有先例：ci.yml 的路径混淆正是新旧布局并存期的产物（f_repo_ops_01）；tsconfig.tsbuildinfo 仍记录重构前文件集（frontend_shell Medium）; t011（删 legacy）backlog 未启动（f_01），意味着这棵死树没有已排期的删除时点
  - Impact: agent 与人类用 grep 定位实现时会同时命中死活两份（如两个 LoginPage），改错副本的风险随时间累积；同理 legacy 后端与 v2 包的同名概念（两套 profile 存储）在 t011 前一直是新读者的固定陷阱。
  - Fix: 不必等 t011 全量启动：把 v1 前端树单独作为一个可独立验证的删除 commit 先行（入口不可达已有 grep 证据），或至少在死树根加 DEPRECATED 标记文件并从 tsconfig/搜索面排除。

## questions

```json
[
  {
    "counterevidence": "若文档证据表明作者已全量在 v2 拓扑上自用且 legacy 仅作发布残留，则 f_01 应改判为『切换链拖延主要成本在叙述面而非数据面』",
    "evidence_needed": "handoff/蓝图中关于实际部署形态的陈述、compose 与 .env.example 的使用说明、docs 中是否提到现网 Profile 数量或迁移dry-run记录",
    "id": "q_evolution_01",
    "question": "legacy 栈是否仍有真实用户数据在积累（作者本人日常部署跑的是否就是根 compose 的 legacy 镜像、profiles.db 里是否有在用 Profile）？若 legacy 实际上已无人使用、作者日常跑的是 v2 开发拓扑，则 t010 的数据迁移近乎空集、t011 成本骤降，f_01 的『成本单调上升』判断需下调；反之每个月都有新数据进入待迁移库。",
    "units": [
      "contracts_deploy",
      "docs_current",
      "backend_core"
    ]
  },
  {
    "counterevidence": "若 doctor 实际包含 blueprint 承重断言（如 failure_count 阈值）与代码的交叉校验且有运行记录，则 f_02 中 blueprint 部分应降级",
    "evidence_needed": "docs/blueprint/testing.md 的 doctor_cmd 具体命令、对应脚本（repo_task doctor 等）的校验项清单、template_tests 中对 doctor 的覆盖",
    "id": "q_evolution_02",
    "question": "仓内的 doctor/门禁命令实际校验哪些文档一致性？若 doctor 已覆盖 specs_index↔文件、tasks_index↔目录等结构校验但不覆盖 blueprint 内容断言，则 f_02 的结论是『校验面与失真面错位』；若连结构校验也不存在或未被运行，则失真范围比当前判断更大。",
    "units": [
      "template_scripts_state",
      "template_tests",
      "docs_current"
    ]
  },
  {
    "counterevidence": "若耦合仅见于 supervisor/coordinator 相关 2–3 个文件且其余单元均为行为级断言，则 f_03 应收窄为模块级 Medium",
    "evidence_needed": "各测试单元 local 结果中『断言/操作私有成员（_ 前缀属性、私有方法、name-mangled 属性）』类 finding 的单元分布统计",
    "id": "q_evolution_03",
    "question": "私有内部耦合的测试集中在 coordinator 一个模块，还是遍布 v2 各模块（gateway、runtime_agent、api）？集中则 f_03 的重构爆炸半径有限、可作为 t009 前的有界清理；遍布则切换链每一步都会触发。",
    "units": [
      "tests_unit_supervisor_runtime",
      "tests_unit_stream_api",
      "backend_tests"
    ]
  }
]
```

## question_decisions

```json
{
  "q_evolution_01": {
    "result": "confirmed",
    "reason": "精查 confirmed 本问题的部署形态一半：handoff（2026-11-02）明言在跑的 cbrowser:latest 容器为旧版 VNC、v2 栈未运行，DOCKER_DEPLOYMENT.md 与 compose 确认唯一数据根是 legacy 格式的 ~/.cbrowser——问题中『legacy 已无人使用、作者日常跑 v2 开发拓扑、t010 迁移近乎空集』的反设被证伪，f_01 的判断方向维持。但精查同时确认全仓无任何现网 Profile 数量、数据量或增长速率记录，『每个月都有新数据进入待迁移库』的强形式无证据支撑，不能作为成本上升的论据。 Effect: f_global_evolution_01 的标题与影响已改写：成本单调上升改为立足于部署形态（legacy 是唯一现网产品、迁移源集是真实在用的数据根）＋验收面增长＋文档漂移累积＋隐性知识衰减；证据列表已补入精查结论，并明确数据累积速率不在论据内。",
    "followup_sha256": "a32292e5309c091558b2b8a77b3138f0a6126f2a145da13201ddb14a50c7bbeb",
    "decision": "adjusted",
    "followup": "followup_q_evolution_01.json"
  },
  "q_evolution_02": {
    "result": "confirmed",
    "reason": "精查 confirmed 且结论强于原问题的较轻分支：仓内不存在 repo_task doctor 子命令，blueprint/testing.md 的 doctor_cmd 只是项目自定义命令块，本体仅做环境前置（pytest --collect-only 收集契约测试、command -v md_kx），对索引、目录与文档内容零校验；blueprint 承重断言（failure_count 阈值、级联语义）与代码/ADR 的交叉校验全仓不存在——问题给出的降级反证条件不成立。归因有一处修正：结构一致性的保障来自 task 状态机 finish 时的 specs_index 硬校验与 tasks_index 派生重建，而非任何 doctor 检查；这与 f_02『结构上自纠正、语义上自欺』的观察一致，不改变结论方向。精查另立一条 Medium（门禁命令在 task 生命周期内从不被执行，唯一执行器是 repo_sync），记于精查文件自身。 Effect: f_global_evolution_02 维持原文与 High 等级；其反证条件已被精查排除，结论无需收窄。",
    "followup_sha256": "bc58e7f7e5e8334d3286ca537dd93f5c90497a09a6a61e782f40974cc912e140",
    "decision": "upheld",
    "followup": "followup_q_evolution_02.json"
  },
  "q_evolution_03": {
    "result": "confirmed",
    "reason": "精查 confirmed 主分布并否定收窄反证：私有内部耦合横跨 5/6 个测试单元、至少 17 个测试文件（严格口径 7 条 finding），远超『仅 coordinator 2–3 个文件』的反证条件。但分布不均：质心在 supervisor/coordinator，stream/gateway 次之，另含对钉版 Selkies 库 name-mangled 私有 API 的耦合；v2 runtime_agent 与 v2 API 本体基本干净。故原判断隐含的『切换链每一步都会触发』属过强表述，须按模块收窄。 Effect: f_global_evolution_03 的影响已改写：爆炸半径限定为触碰 supervisor/gateway/stream 的切换步，runtime_agent 与 API 步骤基本不触发；证据列表已补入精查的分布统计。标题与 High 等级维持——切换链的核心步骤恰落在耦合最密的模块上。",
    "followup_sha256": "08ca7a0b373a5249a24b3157bc7c3b73650681f5a5a947df550d7ceaa6fd8485",
    "decision": "adjusted",
    "followup": "followup_q_evolution_03.json"
  }
}
```
