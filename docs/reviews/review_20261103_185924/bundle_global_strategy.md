# bundle_global_strategy

## Summary

战略层面的问题不在工程质量而在排序与配比，前提为仓内声明与部署工件共同支持的「单机单人、legacy 是用户实际运行的系统」。三条主线：(1) 交付倒挂——唯一可部署产物是自 2026-10-26 起冻结的 legacy 单体，本轮全部 High 与鉴权/日志类 Medium 都落在它身上；五服务 v2（后端约 20k 行 + 前端约 15k 行 + 测试约 40k 行）没有任何部署路径，其发布链 t012→t009→t010 已于 2026-11-02 按用户批准定稿重构、t012 的前置 t018 也已完成，但三个任务仍全部 backlog，最近一波 t015–t018 的投入继续投向未部署系统的内部整改。(2) 验证配比与已交付风险反向：最重的测试资产压在从未交付的 v2 与被 macOS 宿主锁定的 E2E 上，唯一交付面的高危点（serve_spa、剪贴板日志、宿主机控制端点）零测试覆盖。(3) 治理与文档体系已与产品同体量（.repo_template 27.5k 行 + docs 48k 行，对照产品本体约 45k 行），且其人工维护流已被本轮多处漂移实证跟不上（handoff 过期一整轮、findings 登记未随 ADR 013 修订、blueprint 与 ADR 014 直接冲突）；该体量是否成立取决于 .repo_template 跨仓分摊这一仓外事实，见 q_strategy_01。正面对照：fail-closed 基调在 v2 与工具链一致、任务闭环与证据链成体系、ADR 013 的纠偏表明项目有能力砍掉自己投入最深的路线——缺的不是能力，是把发布与已交付面修复排到内部深化之前。

## Findings

- [High][80] compose.yaml；docs/tasks_index.json（t012/t009/t010）；src/backend/main.py 提交历史 — 交付倒挂：唯一可部署产物是已冻结的 legacy，五服务 v2 无部署路径且发布链已解锁仍未启动

    - ID: f_global_strategy_01; verification: static
    - Evidence: compose.yaml:6-11 唯一服务构建 legacy 单体（image cbrowser:latest、dockerfile config/docker/Dockerfile），f_contracts_deploy_04 确认四份 v2 运行时镜像无任何部署路径; f_contracts_deploy_02：legacy 生产 Dockerfile `FROM cbrowser:latest` 与 compose 自身输出同名标签自引用，全新环境构建依赖一个预先存在的同名基础镜像；f_contracts_deploy_01：Supervisor 镜像按当前 Dockerfile/.dockerignore 组合构建即缺 launch_args.py; git log 实测：src/backend/main.py 自 2026-10-26 重组提交 524e34e 后未再修改（冻结）；同期 v2 在 2026-11-02/03 完成 t015–t018 整改波（68816d8、6432a7a、5252f75 等）; docs/tasks_index.json：t012（v2 正式部署产物与部署文档）→t009（正式拓扑验收）→t010（数据迁移、legacy 下线与正式切换）三任务全部 backlog；t012 任务书已于 2026-11-02 按用户批准的 adoption 重构定稿、范围与 AC 完整，其前置依赖 t018 已完成——发布链处于可启动而未启动状态; 本轮缺陷分布与交付面重合：2 个 backend High（f_backend_core_01 剪贴板明文日志、f_backend_core_02 serve_spa 疑似穿越）及鉴权 opt-in、open-external 缺 CSRF、整表重建静默丢数据、配额可并发绕过（f_backend_core_03–06）全部位于 legacy；f_contracts_deploy_03 显示 legacy 的 AUTH_TOKEN 在 compose 插值中默认空（认证关闭）与其模板「Required」注释矛盾；f_contracts_deploy_05 显示 DOCKER_DEPLOYMENT.md 描述的部署与 compose 现状矛盾; 体量对照（git ls-files + wc 实测）：v2 后端 src/backend/cbrowser 19,991 行 + 前端 14,947 行 + tests/ 43,784 行的投入，在 t012 启动前不产生任何用户可见收益
    - Impact: 用户实际运行的系统是缺陷密度最高、维护已冻结的代际；投入最深的系统从未交付。每多一轮对未部署系统的深化审阅与整改，都在扩大「投入的系统」与「运行的系统」之间的风险差；且 legacy 构建自引用意味着新环境连这个过渡产物都无法确定性构建。缓解事实：compose 默认回环绑定（127.0.0.1:56661）与单机单人包络压低了暴露面，故未定 Critical。
    - Fix: 把 t012 提升为队列首项并启动，t009、t010 顺链跟进；发布链完成前冻结 v2 新增内部整改（阻断 t012 的缺陷除外）。切换完成前对 legacy 只做安全阻断级修复（AUTH_TOKEN 默认与模板口径、剪贴板日志脱敏、serve_spa 路径包含），并在 README 与 DOCKER_DEPLOYMENT 中明确标注 legacy 的过渡地位与切换计划，使文档描述与唯一可部署产物一致。

- [Medium][85] tests/unit、tests/integration、tests/e2e；src/backend/tests；tests/e2e/conftest.py required 门禁 — 验证投入与已交付风险成反比：最重测试资产压在未部署的 v2 与单一宿主锁定的 E2E，交付面高危点零覆盖

    - ID: f_global_strategy_02; verification: static
    - Evidence: 体量实测：tests/unit 17,201 行 + tests/integration 6,131 行 + tests/e2e 16,884 行 ≈ 40.2k 行测试几乎全部面向未部署的 v2；legacy 自有套件 src/backend/tests 仅 4,732 行; f_backend_core_15、f_backend_core_16：legacy 的 serve_spa 与剪贴板日志行为在其自有测试落点零覆盖，/api/open-external 零测试、/api/shutdown 只测拒绝路径——即本轮两个 backend High 的所在面恰是覆盖空白; f_tests_e2e_supervisor_03：E2E required 模式门禁要求 macOS Chrome 应用路径，Docker-only 的 supervisor 套件在任何非 macOS 宿主上都无法进入 required 模式；最重的 E2E 资产（16.9k 行）被单一宿主环境锁定，与 Linux 部署形态无交集; f_template_tests_01：模板 E2E 套件的 review PASS 证据由测试支持代码合成、项目验证门禁被整体关闭；汇总主线 4 另记录多处 fixture 重实现生产语义并与生产漂移（两套 Selkies shim 互相不一致、Gateway→API 假面无条件放行自动化授权、dist 新鲜度门禁按文件名判定可静默测旧 dist）
    - Impact: 测试绿灯最强的区域恰是用户从未运行的区域，已交付面的回归防线最薄；验证体系给出的「系统很稳固」信号与用户实际承担的风险不对应，容易误导后续投入继续向未交付面倾斜。
    - Fix: 切换前为 legacy 高危点补最小行为测试：serve_spa 路径包含校验、剪贴板日志脱敏断言、shutdown/open-external 同源成功路径。将 E2E required 门禁按套件拆分，Docker-only 套件不要求宿主 Chrome 路径，使重资产至少能在部署同族环境（Linux/Docker）上以 required 模式运行。

- [Medium][80] .repo_template/；docs/（blueprint、findings 登记、handoff.md、archive 账本） — 治理与文档体系已与产品本体同体量，其人工维护流在当前规模下已被多处漂移实证跟不上

    - ID: f_global_strategy_03; verification: static
    - Evidence: 体量实测（git ls-files + wc）：.repo_template 27,556 行（102 个文件，其中 py/js 24,947 行、自有测试 11,390 行）、docs 48,007 行；对照产品本体 v2 后端 19,991 + 前端 14,947 + legacy 后端约 10.5k ≈ 45k 行——治理与文档面合计约为产品本体的 1.7 倍; 漂移实证：f_docs_current_01（handoff.md 整体过期一轮，仍称下一步 t015、pending 为空）、f_docs_current_02（findings 登记表未随 ADR 013 修订，8 篇 TURN/ICE 类 finding 仍标有效且含已失效指令）、f_docs_current_03（blueprint/artifacts.md 的 chown 回退口径与 ADR 014 及 security.md 直接冲突）、f_docs_current_05/06（v2_architecture_plan 与 blueprint/architecture 内部表述与现状矛盾）; 归档层同类问题：上一轮 adoption_decision.md 对交叉证伪条数同文件内 33 与 30 两种口径、同一穿越漏洞核实等级三档从未对齐（汇总主线 5）；f_archive_tasks_02（t018 Review 处置表退化为样板文本、19 轮审查超记录上限无授权留痕）; 工具链自身缺陷具产品级破坏性：link-skills 路径下 \_ensure_symlink 对真实目录直接 rmtree 且报告谎称原内容入回滚栈（该路径无事务）、user_prompts 编号双空间使 revoke 可能作废错误条目、sync_opencode_commands 硬下标 KeyError 穿透回滚例外集（汇总主线 6）——治理层缺陷可直接销毁工作区内容，其修复同样要走完整的 task/review 流程
    - Impact: 单人维护下，治理层每产生一处漂移或缺陷，都消耗与产品开发同级的审查与修复预算；文档「长期真相」的可信度随漂移累积下降，每个后续 task 的上下文成本随之上升。注：.repo_template 若由多仓分摊，其体量论据需按分摊后重估（见 q_strategy_01）；但漂移与维护流跟不上的证据全部在本仓内独立成立，不依赖分摊答案。
    - Fix: 把高频漂移点从人工维护改为机械生成或门禁校验：handoff 最新节与 tasks_index/pending 的一致性、findings 登记与 ADR 替代链的一致性，在 task 收尾门禁中自动核对而非靠顺手更新。给模板工具链设简化触发条件：只保留有真实消费者的能力，破坏性路径（rmtree 类）按产品代码同级要求事务保护与回归测试。

- [Info][90] docs/archive/spikes/s002、s005、s008；docs/spikes/s011；blueprint/decisions.md ADR 013 — 协议层验证投入曾集中于后被 ADR 013 删除的 TURN/ICE 路线，且最深投入落在上游私有内部结构上

    - ID: f_global_strategy_04; verification: static
    - Evidence: archive_spikes 单元：s002 为 TURN auth/ICE restart 协议探针，s008 为整套 TURN 凭证代次接管（含对抗性单侧失效矩阵），s005/s008 的适配器依赖 Selkies name-mangled 私有属性（_RTCIceTransport_\_\* 等）; ADR 013（2026-11-02）删除 coturn、TURN 凭证轮换、ICE 代次接管与 Selkies 私有 ABI 补丁，媒体改同机直连，替代 ADR 010；docs_current 单元确认该替代链已按约定标注; 删除依据来自 spike 机制自身：s011 直连回环媒体矩阵证明同机直连可行，成为 t015 删除 TURN 的依据——探针先行起到了止损作用
    - Impact: 这是已发生的沉没投入而非现存缺陷，spike 机制本身完成了纠偏。留下的战略教训是单向的：对第三方上游私有内部结构（name-mangled 属性、私有 ABI）的适配是全部投入中上游变更风险最高的一类，s005/s008 的深度恰好集中于此。
    - Fix: 无需对现存代码动作；后续 spike 立项时在报告中显式标注对上游私有 API/内部结构的依赖面，并将其作为采纳门槛的一部分，避免再次在最高上游风险面做最深投入。

## questions

```json
[
  {
    "counterevidence": "若仓内材料显示存在多个活跃消费仓且同步关系在册，则体量按平台投资计，f_global_strategy_03 的体量论据撤销（其漂移与维护流论据仍独立成立）",
    "evidence_needed": "仓内可核对的消费/同步记录：.repo_template/docs 中关于消费仓与同步关系的说明、repo_sync 的 last_synced_commit 来源记录、usage.md 中对宿主仓数量的表述",
    "id": "q_strategy_01",
    "question": ".repo_template 工具链目前有几个活跃消费仓、分摊关系如何？其 27.5k 行体量是跨仓平台投资，还是实际只服务 CBrowser 一个仓？",
    "units": [
      "template_support",
      "template_scripts_ops",
      "template_scripts_state"
    ]
  },
  {
    "counterevidence": "若 ADR 明确记载拆分对应具体威胁模型（如 Supervisor 独占 docker socket、Agent 崩溃域隔离、Gateway 授权面收敛），则拆分成本有据，本怀疑不成立",
    "evidence_needed": "docs/blueprint/architecture.md 与 docs/blueprint/decisions.md（ADR）中关于服务拆分、docker socket 独占与信任边界的原文表述",
    "id": "q_strategy_02",
    "question": "五服务拆分（API / Supervisor / Gateway / Stream Runtime Agent / 前端）相对单机单人部署包络的成文理由在哪里，是否覆盖进程数、内部 RPC 与令牌鉴权面的长期成本？",
    "units": [
      "docs_current",
      "backend_supervisor",
      "backend_stream_gateway",
      "backend_api_auth"
    ]
  },
  {
    "counterevidence": "若已有成文决定明确 legacy 下线时点与切换前风险接受范围，则 f_global_strategy_01 中对 legacy 修复优先级的建议应调整为「只需保证切换前风险在已接受范围内」，而非逐项修复",
    "evidence_needed": "docs/tasks/t010_v2_data_migration/task.md 契约区与 blueprint/decisions.md 中对 legacy 处置与期间风险接受的成文表述",
    "id": "q_strategy_03",
    "question": "legacy 的正式定位是「t010 切换后下线」还是「长期双轨维护」？若为下线，其现存安全类 Medium（鉴权 opt-in、open-external 缺 CSRF、整表重建丢数据、配额可绕过）的处置策略是否为「不修、靠切换消除」，该策略有无成文记录？",
    "units": [
      "backend_core",
      "docs_current",
      "contracts_deploy"
    ]
  },
  {
    "counterevidence": "若仓内成文目标包含多用户或显著并发规模，则本视角多项以单机单人为前提的配比判断需按该规模重估",
    "evidence_needed": "README、AGENTS.md、blueprint 中对部署规模与使用者范围的成文表述，以及 E2E 验收（如 t009 任务书）中声明的并发/压力目标数值",
    "id": "q_strategy_04",
    "question": "仓内是否有实际部署规模的记录（profile 总数、并发会话上限、使用者人数），足以支撑五服务拓扑与 40k 行测试投入的规模前提？",
    "units": [
      "docs_current",
      "tests_e2e_supervisor"
    ]
  }
]
```

## question_decisions

```json
{
  "q_strategy_01": {
    "followup_sha256": "792503112dce2d04dff19b698417e376c7f6e0f2ba131f6bbefc1d0ce373b944",
    "reason": "采用精查证据：仓内只能证明工具链按跨仓平台形态设计（模板源头是仓外独立仓，蓝图记为本地 ../repo_template，消费机制靠显式传参）、CBrowser 自我定位为消费仓之一（AGENTS.md 模板声明），但仓内从未枚举、命名或计数任何消费仓；且 usage.md 规定的可审计同步记录（应入库的 .repo_template/sync_manifest.json、本机 sync_state.json 中的 last_synced_commit）在 CBrowser 自身全部缺失，.repo_template 在全部 git 历史中只有一个导入提交（524e34e）此后零同步提交。对 f_global_strategy_03 的影响须分两半看：其体量论据（.repo_template 27.5k 行、治理与文档合计约为产品本体 1.7 倍，若实际只服务单仓则属过度投入）随本问悬置——既不能按多仓平台投资撤销，也不能按单仓服务坐实，定论需仓外证据（模板源仓的消费/同步记录或各候选消费仓各自的 sync_manifest.json）；但该 finding 的漂移与维护流论据独立成立、维持不变：handoff 过期一整轮、findings 登记未随 ADR 013 修订、blueprint 与 ADR 014 直接冲突、归档层口径矛盾、t018 处置表退化为样板文本、工具链自身的破坏性缺陷，全部为仓内证据，不依赖分摊答案；且同步记录链在本仓自身断裂（规定应入库的 manifest 与本机 state 皆不存在）本身即是维护流跟不上的新增一例，反而加强漂移一侧。不影响本路其他 finding：f_global_strategy_01、f_global_strategy_02、f_global_strategy_04 均不以分摊事实为据。",
    "result": "insufficient"
  },
  "q_strategy_02": {
    "followup_sha256": "17070d24b4c6fe076720adb1ca8591dbf08406c7ab77cc8ebec27885ef989275",
    "reason": "采用精查证据：五服务拆分的成文理由存在且对应具体威胁模型，恰中本问预设的反证条件——ADR 001 以单容器共享导致环境污染、端口竞争、指纹泄露与崩溃连锁反应为背景确立每 Profile 独立容器；ADR 007 冻结 v2 时明文 API 为唯一 SQLite 写入者、Supervisor 为唯一 Docker Socket 持有者，并以 shareable IPC 切断媒体容器对浏览器用户数据的直接挂载；architecture.md §4/§6 把边界写成硬约束（API 严格禁止挂载 Docker Socket、Supervisor 仅响应内部受限认证 RPC 且严格禁止读写 SQLite、Gateway 进程异常重启不影响底层浏览器进程即崩溃域隔离）；security.md 设有成文威胁模型，ADR 010 另载 Gateway 无状态、实例真相只在 API 的分离理由；单机单人包络本身亦成文（ADR 013、architecture.md §7.1）。据此，本路 summary 中隐含的『拆分相对单机单人包络的复杂度是否相称』之怀疑撤销：拆分是该包络内以最小权限与隔离为据的成文决定，不构成无据投入。如实保留一处残余（不改变裁决、亦不另立 finding）：无任何文档把常驻进程数或服务间令牌面（security.md:8 列明至少 4 个服务间令牌文件，另有管理员口令文件与每 Profile 派生凭证）作为长期成本项盘点权衡，ADR 013 的成本测试只施于媒体面、未施于控制面拆分本身——此为理由文档的成本侧未展开，建议后续在 ADR 中补记，不影响拆分合理性结论。对本路其他判断无削弱：f_global_strategy_01 的核心是发布链未启动而非拆分无据；f_global_strategy_03 涉及的是治理文档维护漂移，与拆分理由的存在性无关。",
    "result": "refuted"
  },
  "q_strategy_03": {
    "followup_sha256": "e7d272c1b2683fa0d8ce36646fbf77069d00b1210c22ec39d83ae6acc5f01a1e",
    "reason": "采用精查证据：legacy 的正式定位成文明确——不是长期双轨，而是随 t010（已并入原 t011『移除 legacy』，tasks_index 标题即『数据迁移、legacy 下线与正式切换』，现为 backlog、硬依赖 t009）在正式切换时整体删除下线；『不修、靠删除消除』的处置策略由用户 2026-11-02 审批的 adoption R1 成文（明列含自动重建表丢列即整表重建丢数据，其文件 scope 覆盖本问四条安全类 Medium 所在文件，理由为修改即将删除且无法部署的代码不减少任何技术债；『配额可绕过』虽未逐字列举，但落在 R1 声明的文件 scope 内且 finding→决策映射表按类映射至 R1/A48）；在跑暴露由 A48 单独以运维缓解处置（compose 端口改绑 127.0.0.1、README 与 .env.example 把 AUTH_TOKEN 标为必填、明言 legacy 代码不改由 t011 删除），t010 上下文区另记录用户同日决定直接停用在跑的旧版容器（docker compose stop，容器与数据根保留供迁移）——切换前风险是『缓解＋停用』而非裸接受。据此调整 f_global_strategy_01 的修复优先级表述（finding 本身不在本步修改）：其 fix 中『切换完成前对 legacy 只做安全阻断级修复（AUTH_TOKEN 默认与模板口径、剪贴板日志脱敏、serve_spa 路径包含）』应调整为只需保证切换前风险处于已记录的接受/缓解范围内（旧版容器保持停用、回环绑定、AUTH_TOKEN 必填口径），legacy 代码侧不需要逐项修复，预算应让位于推进发布链本身；f_global_strategy_01 的核心判断（交付倒挂、发布链 t012→t009→t010 已解锁仍未启动、应把 t012 提为队列首项并在发布链完成前冻结 v2 新增内部整改）不受本问影响，维持。两点精度保留：『下线时点』为 t010 里程碑口径、无日历日期，实际时点取决于 t009 完成；处置策略的成文载体是 adoption_decision.md 与 t010 上下文区，decisions.md（ADR）内无专门条目，属记录位置问题，不改变『已有成文决定』的裁决。同理，f_global_strategy_02 中『切换前为 legacy 高危点补最小行为测试』的建议应收敛为仅当切换前风险超出已记录缓解范围时才需要，该 finding 的主体（测试资产压在未部署面、E2E 被单一宿主锁定）独立成立、维持。",
    "result": "refuted"
  },
  "q_strategy_04": {
    "followup_sha256": "4347c470e7133bf3c530952cd79c8234c877a13c3e7dcd266385d07d9381d82e",
    "reason": "采用精查证据：仓内不存在任何支撑五服务拓扑与约 40k 行测试投入的部署规模记录——没有 profile 总数、没有作为需求的并发会话上限、没有使用者人数的成文数值；仓内唯一的规模定性记录恰为反面，ADR 013 明文单机单人包络（『CBrowser 的唯一目标是同一台 Mac 上的单一用户』，多主机场景被定性为未存在的场景而拒绝为其付费），AGENTS.md 的『单机 Docker 管理系统』、architecture.md 的『单机 Docker 架构』、ADR 004 以单机为前提的 SQLite 选型，口径一致；对 README 与现行文档以『多用户/多人/团队/multi-user/tenant』检索零命中。仓内仅有的规模数值是 t009/v2 计划的容量探边界目标（1/3/10 活跃流、10 个 Profile，在本机 Mac/OrbStack 上找边界），属验收探针而非部署规模需求，且 t009 的 AC-001/AC-002 至今未勾选、未执行，未落定为规模事实；本问预设的反证（仓内成文目标包含多用户或显著并发规模）未出现。据此，本视角多项以单机单人为前提的配比判断——f_global_strategy_01 的交付倒挂、f_global_strategy_02 的验证投入与已交付风险成反比、f_global_strategy_03 的治理体量相对单人维护的负担——前提成立，全部维持，无需按更大规模重估。附带观察（不改变裁决、不另立 finding）：t009 task.md 引用的 docs/specs/v2_acceptance.md 在仓内不存在，容量验收的成文落点缺失，可并入 f_global_strategy_03 的文档漂移例证范围。",
    "result": "confirmed"
  }
}
```
