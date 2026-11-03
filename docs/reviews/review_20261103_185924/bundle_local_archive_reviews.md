# bundle_local_archive_reviews

## responsibilities

- 本单元是上一轮（2026-11-02）intensive-review 的完整归档记录面：41 份生成的 bundle_*.md（22 局部 + 4 全局 + 13 精查 + 仓库汇总 + 交叉证伪）、汇总报告 review_intensive.md（2316 行），以及唯一非生成文档 adoption_decision.md（498 行，把 362 条 finding 合并为 54 个决策项并逐条映射）。
- 记录的职责是为该轮审阅提供可审计的终局证据链：局部结论 → 全局结论 → 定向精查（含 followup_sha256 绑定）→ Critical/High 独立证伪 → BLOCK 裁决 → 用户决策与处置去向。
- adoption_decision.md 同时是后续整改任务（t015–t018）的立项依据，其 A/R 编号被任务与归档 pending 引用为处置凭证。

## interfaces

- 文档间引用接口有三类：finding id（如 f_backend_core_01）、bundle 文件名+行号（如 bundle_local_backend_core.md L63–L67）、以及 _meta 产物的 SHA-256（question_decisions 的 followup_sha256、cross_validation 的 finding_sha256）。
- adoption 的 A/R 编号是跨文档接口：被本仓后续 task 与 pending 记录引用；但编号未按轮次命名空间隔离（见 f_archive_reviews_07）。

## dependencies

- bundle_*.md 均为 _meta JSON 的渲染产物，_meta 按仓规 gitignore 不入库；文档集的完整审计链因此部分依赖仓外产物（见 f_archive_reviews_05）。
- adoption 的多项闭环理由引用上一轮（2026-11-01）adoption 的 A 项编号与 fix commit，跨轮可追溯性依赖读者自行区分两套编号。

## flows

- 证据流：bundle_local_*（325 条）→ bundle_global_*（30 条）→ bundle_followup_q_*（13 份精查，新增 7 条）→ bundle_cross_validation（33 条 C/H 全 agree）→ review_intensive.md 汇总（362 条，Verdict BLOCK）→ adoption_decision.md 决策（采纳 48 / 不采纳 6 / 待决定 0）。
- 数字主链经本单元逐项复算成立：局部 325 + 全局 30 + 精查新增 7 = 362；严重度合计 C1/H32/M112/L173/I44 在 repository_summary、review_intensive 卷首与 adoption 卷首三处一致；41 份 bundle 的构成（22+4+13+1+1）与 Sources 清单一致。

## constraints

- 本单元为纯静态文档审阅：未运行任何生成/聚合脚本，未复算 _meta 哈希，未联网核对公开远程内容。
- 归档纪律（仓 AGENTS.md）：docs/reviews/ 报告入库、结论以原文为准；本单元只判定文档自身的内部一致性与结构健全性，不改判上一轮任何 finding 的技术结论。

## decisions

- 记录在案的轮次裁决：Verdict BLOCK、Coverage completed_with_limitations；唯一 Critical 为默认部署无认证局域网控制面（f_global_system_properties_01）。
- adoption 的决策标准引用户 2026-11-02 指定口径：追求最好架构、不以改动成本为不采纳理由，不采纳只保留三类（规则禁止 / 代码将随 t011 删除 / 设计上不应改附理由）。

## evidence

- adoption_decision.md 卷首与「基线与现场」段称交叉证伪 33 条全 agree，「合并说明」第 1 条却写「交叉证伪抽查 30 条全部 agree」；bundle_cross_validation.md 实际列 33 条、bundle_repository_summary.md 亦称 33 条（见 f_archive_reviews_01）。
- serve_spa 穿越的核实等级在记录内有三档：bundle_local_backend_core.md 中 f_backend_core_01 为 suspected；bundle_followup_q_system_properties_02 的结论为静态可达性确认；adoption_decision.md「基线与现场」却记录未带凭据请求返回 200 读出容器 hostname 的实测（reproduced 级陈述），且该实测只出现在决策文档内（见 f_archive_reviews_02）。
- 至少 4 份 local bundle 的 evidence 段中，viewfix 补审段落被截断在词中/句中：bundle_local_backend_core.md（止于「全套件零测试」）、bundle_local_backend_supervisor.md（止于「resource faul」）、bundle_local_backend_runtime_adapters.md（止于「此外 repo」）、bundle_local_backend_stream_gateway.md（止于 probe 文件路径中途）（见 f_archive_reviews_03）。
- adoption_decision.md 中 A13 行自称覆盖 6 条，但文末附表把 f_backend_core_04、f_backend_core_05、f_backend_core_12 等至少 8 条映射到 A13；「合并说明」第 3 条的「62 条子项逐条映射」与附表各 bundle 小计合计 362 条的规模不符（见 f_archive_reviews_04）。
- 正面事实：全部 43 份文件未发现任何凭据明文值；测试夹具密钥与 canary 均按位置/种类记录或已脱敏，与该轮审阅自述的凭据纪律一致。

## uncertainties

- adoption 附表声称 362 条 finding 逐条且恰好映射一次：本单元抽查了多个 bundle 的小计与映射行（合计与小计均对齐），但未对 362 行做全量程序化去重核对，个别重复/漏映射不能完全排除。
- f_archive_reviews_02 中 adoption 记录的现网实测（穿越返回 200）是否确曾执行、执行环境为何，文档集内无第二处记录可互证；本单元只判定其与同一记录集内其他两处核实等级表述不一致。
- bundle 渲染截断（f_archive_reviews_03）的成因（渲染器长度上限或源 JSON 本身截断）无法从归档文档判定，_meta 源文件不在本单元文件清单内。

## Findings

- [Medium][95] docs/reviews/review_20261102_201727/adoption_decision.md（卷首基线表、「基线与现场」段 vs「合并说明」第 1 条） — adoption_decision.md 对交叉证伪条数自相矛盾：同文件内 33 条与 30 条两种口径
  - ID: f_archive_reviews_01; verification: static
  - Evidence: adoption_decision.md 卷首与基线段两处均称 33 条 Critical/High 经独立证伪全部 agree；「合并说明」第 1 条却写「交叉证伪抽查 30 条全部 agree」。; bundle_cross_validation.md 实际逐条列出 33 条且全为 agree；bundle_repository_summary.md 第 3 节亦称「All 33 Critical/High rows returned result=agree」。; 362 条构成中 Critical 1 + High 32 = 33，与 33 条口径吻合，30 条无任何出处。
  - Impact: 决策文档是后续整改的立项凭证，其自述的证伪覆盖数与审阅记录本身不符：只读合并说明的读者会低估证伪覆盖，且该错误位于解释 362→54 合并方法的核心段落，削弱整份决策记录的数字可信度。
  - Fix: 将合并说明第 1 条的「30 条」更正为「33 条」，并注明证伪对象为全部 Critical/High（非抽查）；后续轮次的决策文档在落笔前以程序化计数复算此类总数。

- [Medium][90] docs/reviews/review_20261102_201727/bundle_local_backend_core.md（f_backend_core_01）；bundle_followup_q_system_properties_02.md；adoption_decision.md「基线与现场」段 — 同一穿越漏洞的核实等级在记录集内有三档（suspected / 静态确认 / 现网实测 200），从未对齐
  - ID: f_archive_reviews_02; verification: static
  - Evidence: bundle_local_backend_core.md 中 f_backend_core_01 的 verification 为 suspected，uncertainties 明言未做运行时复现。; bundle_followup_q_system_properties_02.md 的结论是静态可达性确认（uvicorn 解码、Starlette 不折叠点段、serve_spa 无包含校验），仍非运行时复现；bundle_cross_validation.md 对 f_backend_core_01 的 agree 理由亦只引用该静态精查。; adoption_decision.md 却记录：对在跑旧版容器的未带凭据请求返回 200 并读出容器 hostname——这是 reproduced 级的实测陈述，只出现在决策文档一处，任何 bundle、精查或证伪记录均未收录该证据。
  - Impact: 同一事实在归档记录里同时以三种证据等级存在：按 bundle 读到的是「疑似」，按 adoption 读到的是「已实测可利用」。后续读者无法判断该漏洞在审阅时点究竟被证实到哪一层；若实测属实，审阅记录低估了证据强度，若不属实，决策文档夸大了基线事实——两种情况都损害记录的裁决效力。
  - Fix: 在 adoption 或 review_intensive 的勘误位置注明该实测的执行时间、环境与结果，并把 f_backend_core_01 的核实等级在记录中统一表述（如「静态确认 + 决策阶段补充现网实测」），使三档口径可追溯地衔接。

- [Medium][95] docs/reviews/review_20261102_201727/bundle_local_backend_core.md；bundle_local_backend_supervisor.md；bundle_local_backend_runtime_adapters.md；bundle_local_backend_stream_gateway.md（均为 evidence 节的 viewfix 段落） — 多份 local bundle 的 evidence 段被截断在词中/句中，归档记录静默丢失 viewfix 补审证据
  - ID: f_archive_reviews_03; verification: static
  - Evidence: bundle_local_backend_supervisor.md 的 viewfix 段落止于「resource faul」——词中截断，其后内容缺失。; bundle_local_backend_core.md 的 viewfix 段落止于「SPA catch-all 静态托管（全套件零测试」，句中截断。; bundle_local_backend_runtime_adapters.md 止于「此外 repo」；bundle_local_backend_stream_gateway.md 止于一个 fixture 文件路径中途。四处均为 tests 视角补审（viewfix）的证据总结段落。
  - Impact: 归档 bundle 是该轮审阅唯一入库的证据形态；被截断的恰是四个单元 tests 视角的补审结论，读者无法从入库记录得知补审的完整覆盖结论，只能看到半截陈述。这类静默截断与文档集自述的「证据链完整可核」定位不符，且无任何截断标记提示读者。
  - Fix: 定位渲染截断成因（渲染器字段长度上限或源 JSON 截断），在后续轮次的 bundle 渲染中对超长 evidence 做完整输出或显式标注「（截断，见 _meta 源文件）」；本轮记录可追加勘误说明列明受影响的四个单元。

- [Low][85] docs/reviews/review_20261102_201727/adoption_decision.md（A13 行、「合并说明」第 3 条、文末附表 backend_core 节） — adoption 的决策项覆盖计数与文末附表映射不一致（A13 自称 6 条、附表实际映射 ≥8 条；「62 条子项」与附表 362 条规模不符）
  - ID: f_archive_reviews_04; verification: static
  - Evidence: A13 行自称「覆盖：6 条」并逐一列名（f_backend_core_05、f_backend_api_auth_08、f_contracts_deploy_02、Critical 本体、f_global_strategy_05、f_global_evolution_05）。; 文末附表 backend_core 节另把 f_backend_core_04 与 f_backend_core_12 也映射到 A13，即 A13 实际承接至少 8 条，与其行内自称的 6 条不符，且多出的两条未在 A13 的处置说明中出现。; 「合并说明」第 3 条称「62 条子项逐条映射见文末附表」，但附表按 bundle 分节的小计合计为 362 条，「62 条子项」的所指无法从文档内任何口径复算得出。
  - Impact: 按决策项统计整改进度（如「A13 完成即关闭 6 条」）会与按附表逐条销账的结果对不上；62 与 362 的规模落差使读者无法确认附表究竟是全量映射还是子集，逐条审计时必须自行全文复算。
  - Fix: 统一口径：决策行的覆盖数改为与附表映射一致的计数（或明确区分「主项/并入项」两类并分别计数），并把「62 条子项」更正为与附表规模一致的表述。

- [Low][90] docs/reviews/review_20261102_201727/bundle_global_*.md（question_decisions 的 followup_sha256）；bundle_cross_validation.md（finding_sha256）；bundle_repository_summary.md（synthesis 绑定说明） — 归档记录中的审计哈希链指向未入库的 _meta 产物，仓内读者无法复算验证
  - ID: f_archive_reviews_05; verification: static
  - Evidence: 四份 global bundle 的 question_decisions 均带 followup_sha256，其哈希对象是精查的 _meta JSON 定稿，而非同目录入库的 bundle_followup_*.md 渲染件。; bundle_cross_validation.md 每条记录带 finding_sha256，其来源 finding_index 同样是 _meta 产物；_meta/ 按仓规 gitignore 不入库（本轮新 OUTDIR 的 _meta 亦同）。; 结果是：只持有公开仓的读者能看到哈希值，却没有任何被哈希的原文可供复算，哈希链在归档形态下只剩装饰性。
  - Impact: 文档集以哈希绑定作为「结论绑定到确切证据版本」的完整性机制，但归档后该机制不可验证：读者无法区分哈希是对的但原文缺失，还是记录本身被改动过。审计价值低于其呈现形式给人的印象。
  - Fix: 在报告目录内落一份可复算的清单（如各 bundle 文件自身的 SHA-256 清单文件入库），或在 repository_summary 中明示哈希对象为未入库的 _meta 产物、归档读者应以 bundle 文本为准，避免高估可验证性。

- [Low][85] docs/reviews/review_20261102_201727/review_intensive.md（卷首 Coverage 行、Gaps 节、Limitations 节） — review_intensive.md 宣告「Gaps: None」与同文件的 completed_with_limitations 及长 Limitations 列表并存
  - ID: f_archive_reviews_06; verification: static
  - Evidence: 卷首 Coverage 为 completed_with_limitations，Limitations 节逐条传播了各单元约六十条限制与未核事项（未运行验证、key 级覆盖、跨单元未确认等）。; 同文件 Gaps 节却只有一句「None.」，未对「gap」与「limitation」的区分作任何说明。
  - Impact: 只读汇总节的读者会得到「无缺口」的结论，与同文件后段大量未核事项并存时构成自相张力的完整性表述；后续轮次若沿用该口径，覆盖缺口的登记纪律会被稀释。
  - Fix: 在 Gaps 节注明其口径（如「无单元级覆盖缺口；方法级限制见 Limitations」），或把生成型大文件的 key 级覆盖等事项按其性质登记为 gap 而非仅 limitation。

- [Low][90] docs/reviews/review_20261102_201727/adoption_decision.md（R2 行 vs A26 行） — adoption 内的跨轮编号碰撞：R2 理由引用的「A26」是上一轮编号，与本文自己的 A26 指向不同事项
  - ID: f_archive_reviews_07; verification: static
  - Evidence: R2（契约冻结不采纳）的理由写「specs/blueprint 的 A26 已同步」，此处 A26 指 2026-11-01 轮 adoption 的同名编号（契约同步回写项）。; 本文自己的 A26 是另一事项（f_docs_current_17：storage spec 表清单漏列 settings 表）。同一文档内「A26」一词两种所指，无任何轮次限定标注。
  - Impact: 按编号回查的读者（包括按 A 编号跟踪整改的 task 记录）会落到错误条目；随着轮次增多，两套 A/R 编号在同一仓内并存，碰撞只会加重。
  - Fix: 跨轮引用一律带轮次前缀（如「20261101-A26」），或在 R2 理由中把所指写成事项名而非裸编号；本文 A 编号在被其他文档引用时亦建议带本轮日期前缀。

- [Low][80] docs/reviews/review_20261102_201727/adoption_decision.md「基线与现场」段 — adoption 在修复落地前，把对当时现网部署可直接使用的未授权穿越请求路径写进了公开仓记录
  - ID: f_archive_reviews_08; verification: static
  - Evidence: 该段原文给出了完整的编码穿越请求路径（/%2e%2e/…/etc/hostname 形态）并确认对在跑容器返回 200；该文档随审阅报告 commit 进入公开仓库时，对应修复尚未落地（修复属其后整改轮次）。; 同记录集的其他文件对同一漏洞只作代码级描述（serve_spa 无包含校验），唯 adoption 提供了可直接照抄的现网验证路径与成功结果。
  - Impact: 在漏洞仍可利用的窗口内，公开记录等于向任何仓库读者提供了现成的未授权文件读取入口与「已验证可用」的背书；对默认部署在局域网的身份存储应用，这缩短了从发现到利用的距离。定级 Low 是因为利用仍需能触达部署所在网络。
  - Fix: 后续轮次的决策/基线文档对未修复漏洞只记录验证结论与环境，不写可照抄的完整利用路径；确需留存复现细节时放不入库的过程区（_meta），修复落地后再补入公开记录。

- [Info][95] docs/reviews/review_20261102_201727/adoption_decision.md（决策表「finding」列与文末附表定位列） — adoption 附表以 bundle 行号作为 finding 定位锚点，生成产物行号不稳定
  - ID: f_archive_reviews_09; verification: static
  - Evidence: 决策表与附表大量使用「bundle_local_backend_core.md L63–L67」式定位；bundle 为 _meta JSON 的渲染产物，任一 finding 文本变动都会使后续行号整体漂移。; 同一文档内 finding id 本已唯一且稳定（如 f_backend_core_04），行号定位不提供额外信息却引入失效模式。
  - Impact: 本轮记录因基线冻结尚可使用；但任何对 bundle 的再生成或修订都会使 adoption 的全部行号引用静默失效，且失效无从察觉。
  - Fix: 后续轮次的决策文档只以 finding id 为定位锚点，行号至多作为落笔时的一次性辅助并注明生成时点。

## views

```json
{
  "contracts": {
    "reviewer": "6b5663fd-a48b-4804-9eb9-d97e4dccde8a",
    "status": "completed"
  },
  "correctness": {
    "reviewer": "6b5663fd-a48b-4804-9eb9-d97e4dccde8a",
    "status": "completed"
  },
  "design": {
    "reviewer": "6b5663fd-a48b-4804-9eb9-d97e4dccde8a",
    "status": "completed"
  },
  "documentation": {
    "reviewer": "6b5663fd-a48b-4804-9eb9-d97e4dccde8a",
    "status": "completed"
  },
  "performance": {
    "reason": "本单元全部为审阅报告与决策文档，无可执行代码或运行时性能面；文档规模与冗余（review_intensive.md 全文复刻各 bundle）已在 documentation 视角下评估。",
    "reviewer": "6b5663fd-a48b-4804-9eb9-d97e4dccde8a",
    "status": "not_applicable"
  },
  "robustness": {
    "reviewer": "6b5663fd-a48b-4804-9eb9-d97e4dccde8a",
    "status": "completed"
  },
  "security": {
    "reviewer": "6b5663fd-a48b-4804-9eb9-d97e4dccde8a",
    "status": "completed"
  },
  "tests": {
    "reviewer": "6b5663fd-a48b-4804-9eb9-d97e4dccde8a",
    "status": "completed"
  }
}
```

## files_reviewed

```json
[
  "docs/reviews/review_20261102_201727/adoption_decision.md",
  "docs/reviews/review_20261102_201727/bundle_cross_validation.md",
  "docs/reviews/review_20261102_201727/bundle_followup_q_architecture_01.md",
  "docs/reviews/review_20261102_201727/bundle_followup_q_architecture_02.md",
  "docs/reviews/review_20261102_201727/bundle_followup_q_architecture_03.md",
  "docs/reviews/review_20261102_201727/bundle_followup_q_architecture_04.md",
  "docs/reviews/review_20261102_201727/bundle_followup_q_evolution_01.md",
  "docs/reviews/review_20261102_201727/bundle_followup_q_evolution_02.md",
  "docs/reviews/review_20261102_201727/bundle_followup_q_evolution_03.md",
  "docs/reviews/review_20261102_201727/bundle_followup_q_strategy_01.md",
  "docs/reviews/review_20261102_201727/bundle_followup_q_strategy_02.md",
  "docs/reviews/review_20261102_201727/bundle_followup_q_strategy_03.md",
  "docs/reviews/review_20261102_201727/bundle_followup_q_system_properties_01.md",
  "docs/reviews/review_20261102_201727/bundle_followup_q_system_properties_02.md",
  "docs/reviews/review_20261102_201727/bundle_followup_q_system_properties_03.md",
  "docs/reviews/review_20261102_201727/bundle_global_architecture.md",
  "docs/reviews/review_20261102_201727/bundle_global_evolution.md",
  "docs/reviews/review_20261102_201727/bundle_global_strategy.md",
  "docs/reviews/review_20261102_201727/bundle_global_system_properties.md",
  "docs/reviews/review_20261102_201727/bundle_local_archive_spikes.md",
  "docs/reviews/review_20261102_201727/bundle_local_archive_tasks.md",
  "docs/reviews/review_20261102_201727/bundle_local_backend_api_auth.md",
  "docs/reviews/review_20261102_201727/bundle_local_backend_core.md",
  "docs/reviews/review_20261102_201727/bundle_local_backend_runtime_adapters.md",
  "docs/reviews/review_20261102_201727/bundle_local_backend_stream_gateway.md",
  "docs/reviews/review_20261102_201727/bundle_local_backend_supervisor.md",
  "docs/reviews/review_20261102_201727/bundle_local_backend_tests.md",
  "docs/reviews/review_20261102_201727/bundle_local_contracts_deploy.md",
  "docs/reviews/review_20261102_201727/bundle_local_docs_current.md",
  "docs/reviews/review_20261102_201727/bundle_local_frontend_features.md",
  "docs/reviews/review_20261102_201727/bundle_local_frontend_shell.md",
  "docs/reviews/review_20261102_201727/bundle_local_repo_ops.md",
  "docs/reviews/review_20261102_201727/bundle_local_template_scripts_ops.md",
  "docs/reviews/review_20261102_201727/bundle_local_template_scripts_state.md",
  "docs/reviews/review_20261102_201727/bundle_local_template_support.md",
  "docs/reviews/review_20261102_201727/bundle_local_template_tests.md",
  "docs/reviews/review_20261102_201727/bundle_local_tests_e2e_stream_frontend.md",
  "docs/reviews/review_20261102_201727/bundle_local_tests_e2e_supervisor.md",
  "docs/reviews/review_20261102_201727/bundle_local_tests_integration_fixtures.md",
  "docs/reviews/review_20261102_201727/bundle_local_tests_unit_stream_api.md",
  "docs/reviews/review_20261102_201727/bundle_local_tests_unit_supervisor_runtime.md",
  "docs/reviews/review_20261102_201727/bundle_repository_summary.md",
  "docs/reviews/review_20261102_201727/review_intensive.md"
]
```
