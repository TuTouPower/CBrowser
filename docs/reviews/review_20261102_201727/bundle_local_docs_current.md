# bundle_local_docs_current

## responsibilities

- 根入口文档：README（最短入口/部署）、AGENTS.md（全仓协作与文档规范）、CHANGELOG、LICENSE 与 BINARY-LICENSE
- docs/blueprint/ 15 篇：自称『当前长期真相』的架构、领域、持久化、网关、Supervisor、Stream/Browser Runtime、安全、前端、约定、决策（ADR）、测试门禁
- docs/specs/ 8 篇生效需求规范 + specs_index.md 注册表；docs/tasks/ t009–t012 任务契约与总账 + tasks_index.json
- docs/findings/ d001–d025 实验事实沉淀（一文件一条目）；docs/guides/ 4 篇验证/分析指南；docs/handoff.md 当前交接（只保留最新一节）；docs/pending/todo/p014
- docs/v2_architecture_plan.md（v2.3 架构总方案，含文首修订块）；docs/reviews/ 下 2026-10-27 与 2026-11-01 两轮历史审阅产物（含 adoption_decision）

## interfaces

- specs_index.md 是 spec 生效注册表：在表即生效，未在表即非规范
- tasks_index.json 由 .repo_template/scripts/task.py 生成，文件头声明权威来源为各 task note.md 的 front matter
- blueprint 与 specs 通过 ADR 编号（decisions.md）与 spec 名互相引用；findings 以 d 编号被 blueprint/spec/task 引用为事实依据
- handoff.md 只保留最新一节，旧节追加至 docs/archive/handoff.md；adoption_decision.md 以 A/D 编号把三路审阅发现映射为处置决定

## dependencies

- 文档正确性依赖 src/ 实现状态（src/backend/cbrowser、src/frontend）、schemas/ 落盘结构、compose.yaml 与 .env.example
- 任务契约依赖 .repo_template 任务系统与 docs/tasks_index.json 的生成流程
- v2 计划与 blueprint 的修订依赖用户决策记录（decisions.md ADR、v2_architecture_plan 文首修订块）

## flows

- 规划流：v2_architecture_plan → 拆分为 t001–t014 task 契约 → 实施 → findings/spec 同步 → 独立审阅 → adoption_decision → A26 类契约同步回写 spec/blueprint
- 交接流：handoff.md 最新节滚动更新，旧节归档；状态以 git HEAD 与 tasks_index 为校验基准
- 事实流：spike 实验 → findings d001–d025 沉淀 → blueprint/spec 引用为设计依据

## constraints

- AGENTS.md 文档纪律：三态分离（当前/过时/未来不得混杂）、单一权威、findings 一条目一文件且只新增与就地修订、handoff 须含 branch 与交出时 head_commit 且只保留最新一节
- 未来能力（t009–t012 backlog、v2 计划未实施部分）不得冒充当前事实；NOT_RUN / USER_WAIVED 不得写成 PASS
- 本审阅为纯静态：未运行任何程序、未修改仓内文件（输出 JSON 除外）、未使用浏览器

## decisions

- ADR 007：废弃控制租约/ControlSession，多 ViewerConnection 并发 controller
- ADR 008：异常重试 2/10/30 秒、第 4 次失败阻断（failure_count 达到 4）
- ADR 011：Chrome 固定 --no-sandbox 的取舍记录；ADR 012（2026-11-02）：剪贴板改 Selkies seamless 同步
- adoption D1 用户决策 A：删除 Profile 时级联删除 runtime_events、仅保留 audit_events（已落地至 spec 与代码）

## evidence

- 一致项：specs_index.md 8 行与 docs/specs/ 磁盘 8 文件一一对应；tasks_index.json 中 t009–t012 均为 backlog 且目录与磁盘一致，t009 depends_on=t013 与 handoff 说法一致
- 一致项：README.md:40 的 http://localhost:56661 与 compose.yaml:11 端口默认值 56661 一致；.env.example 与 config/.env.example 的 AUTH_TOKEN 均为空（无弱默认凭据），键集相同
- 一致项：blueprint/gateway.md 配置表 CBROWSER_GATEWAY_PORT 默认 18080 与 src/backend/cbrowser/gateway/endpoint.py 的 DEFAULT_GATEWAY_PORT=18080 一致
- 一致项：adoption_decision 多项『已落地』抽查属实——A26（browser_isolation 容器名/标签、runtime_persistence failure_count=4 与 resume_key 语义、删除 ControlSession 表述）、A27（architecture 时点锚点、ADR 011、testing.md 去硬编码计数）、A11（pyproject 已含 argon2-cffi 与 aiohttp）、A17（scripts/export_runtime_agent_protocol.py 存在）、A24（stream_agent 下已无 client_shim.py）
- 一致项：findings d001–d025 全部标注『现状：有效』，未发现被替代却未标记的条目；d003/d010 交叉引用规范
- 一致项：v2_architecture_plan 文首修订块明确声明优先于正文（8.4/19.3），且声明实现细节以 blueprint/specs 为准，属受控修订
- 不一致项：见 findings f_docs_current_01 至 f_docs_current_17，均附双边定位

## uncertainties

- 审阅早期怀疑的 stream entrypoint token 环境变量回退（原 adoption A31 相关）：现行 entrypoint 将 controller token 写 0600 tmpfs 文件、master token 经 SELKIES_MASTER_TOKEN 传入且 blueprint 有记载，静态证据不足以判定文档失真，未立项
- 旧版 src/backend/database.py（v2 包之外）是否含任何迁移工具未深查；f_docs_current_01 的结论范围限于生效 spec 对当前 v2 系统的陈述与 v2 包内实现
- findings d001–d025 做了替代/标记层面的全量核对，但其实验事实与代码的逐条深核属代码 unit 范围，本 unit 未逐条复验
- CHANGELOG 是否有意只记发布版本无法从仓内证实；f_docs_current_05 依据其文件头自述口径（记录全部重要变更）判定

## Findings

- [High][95] docs/specs/storage_and_artifacts.md:25-29 — 生效 spec 把尚未实施的旧库迁移工具写成已交付行为且 AC-002 已勾选通过
  - ID: f_docs_current_01; verification: static
  - Evidence: docs/specs/storage_and_artifacts.md:25-29 §2.2 以现在时陈述『升级工具支持对已有旧版 profiles.db 进行安全迁移』『支持 --dry-run』『保留 Cookie』; 同文件 :47 AC-002 已勾选 [x]：『通过 Alembic 成功将数据库 schema 从旧版升级至新版，现有 Profile 与 Cookie 数据完好无损』; docs/specs_index.md:9 将该 spec 列为生效规范（baseline, t008，更新时间 2026-11-02）; docs/tasks_index.json 中 t010_v2_data_migration 状态为 backlog，未实施; docs/blueprint/decisions.md:82（ADR 008 段）明确『正式用户数据迁移仍由 t010 负责』; src/backend/cbrowser/ 全树 grep dry_run/dry-run 零命中，v2 代码内不存在迁移工具
  - Impact: 读者与验收方会把 t010 的未来能力误认为当前事实；已勾选的 AC-002 构成虚假验收证据，违反三态纪律，是本 unit 最严重的文档失真。
  - Fix: 在 §2.2 与 AC-002 处标注『归 t010、当前未实施』或将该节移入未来计划；在 t010 真正交付并留存证据前取消 AC-002 勾选。

- [Medium][95] docs/blueprint/persistence.md:73-73 — blueprint 写 failure_count>=3 即 restart_blocked，与 ADR 008 及实现（第 4 次阻断）冲突
  - ID: f_docs_current_02; verification: static
  - Evidence: docs/blueprint/persistence.md:73：『若 failure_count >= 3，设置 restart_blocked = True』; docs/blueprint/decisions.md:82 ADR 008：failure_count 1/2/3 分别等待 2/10/30 秒，第 4 次异常阻断; docs/specs/runtime_persistence.md:60 已按 ADR 008 写明累计达到 4 次触发阻断; src/backend/cbrowser/domain/runtime_policy.py:5-6 AUTO_RETRY_DELAYS=(2,10,30)、BLOCK_AFTER=4；blueprint/supervisor.md 与之一致
  - Impact: blueprint 自称当前长期真相，按其验收会在第 3 次失败时预期阻断，与实现/测试必然冲突，误导后续开发与排障。
  - Fix: 将 persistence.md:73 改为与 ADR 008 一致的『第 4 次失败（failure_count 达到 4）阻断』并引用 ADR 008。

- [Medium][92] docs/blueprint/persistence.md:42-42 — blueprint 仍称 runtime_events 不随 Profile 删除级联销毁，与已落地的 D1=A 决策相反
  - ID: f_docs_current_03; verification: static
  - Evidence: docs/blueprint/persistence.md:42：『历史事件与审计记录保留在数据库作为去重凭证与历史审计总账，不随单个 Profile 物理删除而级联销毁』; docs/reviews/review_20261101_075819/adoption_decision.md D1 用户决策为 A（级联删除 runtime_events、仅保留 audit_events），且已落地; docs/specs/runtime_persistence.md:23 与 :127 已按 D1 修订为级联删除 runtime_events; docs/specs/storage_and_artifacts.md §2.1 亦写 runtime_events『随 Profile 级联删除』；代码 RuntimeEventModel.profile_id 为 ondelete=CASCADE
  - Impact: 同一数据保留契约在 blueprint 与 spec/决策/代码之间双向矛盾，按 blueprint 实施会重新引入已被决策否决的孤儿事件保留行为。
  - Fix: 按 D1 决策修订 persistence.md:42，改为 runtime_events 随 Profile 级联删除、audit_events 独立保留。

- [Medium][95] docs/blueprint/conventions.md:18-22 — conventions.md 的 schema 落点表引用四个不存在的路径且全表缺 src/ 前缀
  - ID: f_docs_current_04; verification: static
  - Evidence: docs/blueprint/conventions.md:18 引用 schemas/webrtc/，磁盘 schemas/ 仅有 openapi、runtime、stream 三个子目录; :19 引用 backend/cbrowser/api/schemas/，src/backend/cbrowser/api/ 下无 schemas 目录; :22 引用 backend/cbrowser/config.py 与 config/schemas/，仓内均不存在; 全表路径缺 src/ 前缀：真实落点为 src/backend/cbrowser/domain/、src/frontend/src/shared/api/generated/ 等
  - Impact: 作为全仓规范入口的落点表整体不可用，新代码按表放置必然落错位置，规范权威性受损。
  - Fix: 按磁盘真实结构重写该表（schemas/openapi|runtime|stream、src/backend/...、src/frontend/...），并删除不存在的落点行。

- [Medium][88] CHANGELOG.md:3-8 — CHANGELOG 自称记录全部重要变更，但最新条目停在旧版 0.1.9（2026-10-16），整个 v2 重构无记录
  - ID: f_docs_current_05; verification: static
  - Evidence: CHANGELOG.md:3 声明『All notable changes to CBrowser are documented here』; CHANGELOG.md:8 最新条目为 ## [0.1.9] - 2026-10-16，内容为旧版原生/VNC 时代的 fork 变更；无 Unreleased 节; 2026-10-27 至 2026-11-02 的 v2 重构（t001–t008 合入 main、t014 剪贴板 seamless 等）在 CHANGELOG 中零记录
  - Impact: 发布与回溯时 CHANGELOG 呈现为现行记录实则停更，读者会误判当前版本与能力边界。
  - Fix: 补 Unreleased 节记录 v2 阶段变更，或在文件头明确声明其仅覆盖 0.1.x 旧版发布、v2 变更以 blueprint/handoff 为准。

- [Medium][90] docs/guides/browser_isolation_analysis.md:66-72 — 自标 Active 的隔离方案指南仍把已被否决的 KasmVNC 升级列为待办方向
  - ID: f_docs_current_06; verification: static
  - Evidence: docs/guides/browser_isolation_analysis.md:3 状态为 Active（2026-10-26 技术选型与多方案评估）; :66-72 TODO 仍提议『升级 KasmVNC 至满血完全体』：前端弃 noVNC 改接 KasmVNC 官方 Web 客户端、打开 H.264/WebRTC 端口; 最终选定架构（Docker 双容器 + Selkies WebRTC，见 docs/blueprint/decisions.md ADR 002/007 与 docs/blueprint/architecture.md）不在该指南评估的三方案之内
  - Impact: Active 状态的指南会把后续读者引向已否决的技术路线，与现行架构正面冲突。
  - Fix: 将该指南状态改为 Superseded/历史评估并链接现行 blueprint，或删除 KasmVNC TODO 并补记最终选型结论。

- [Medium][90] docs/blueprint/testing.md:34-58 — 权威门禁命令硬编码开发者个人机器绝对路径 $HOME/kar/code/.scratch/...
  - ID: f_docs_current_07; verification: static
  - Evidence: docs/blueprint/testing.md:34、:45、:58 三处门禁命令均为 export TMPDIR="$HOME/kar/code/.scratch/cbrowser_t00X_contract_tmp"; 该路径绑定特定开发者（用户名 kar）的家目录布局，其他机器/贡献者照抄即指向不存在或不可写目录
  - Impact: blueprint 门禁不可移植：任何非原作者环境按文档执行都会在临时目录一步失败；同时公开仓暴露了开发者本地目录结构。
  - Fix: 改为仓内相对路径（如 "$PWD/.scratch/..." 或 mktemp -d 方案），与 AGENTS.md 中 .scratch 的仓内约定对齐。

- [Low][92] docs/blueprint/domain.md:12-12 — domain.md 的 ObservedState 枚举与 persistence/代码不一致（多 created/failed、缺 error）
  - ID: f_docs_current_08; verification: static
  - Evidence: docs/blueprint/domain.md:12：ObservedState 为 created / starting / running / stopping / stopped / failed; docs/blueprint/persistence.md:52：observed_state 取值 stopped、starting、running、stopping、error; src/backend/cbrowser/domain/models.py 中 Literal 为 stopped/starting/running/stopping/error，与 persistence 一致
  - Impact: 领域模型文档给出第三套状态集，按 domain.md 对接的读者会预期不存在的 created/failed 态、漏掉真实的 error 态。
  - Fix: 将 domain.md:12 的枚举改为 stopped/starting/running/stopping/error，与 persistence.md 及代码对齐。

- [Low][90] docs/specs/v2_runtime_validation.md:133-133 — t001 spec 仍以现在时声称 v2 服务代码『均未合入生产代码库』，在当前 HEAD 已不实
  - ID: f_docs_current_09; verification: static
  - Evidence: docs/specs/v2_runtime_validation.md:133 §5：正式 cbrowser-api/supervisor/stream-gateway 服务代码、Alembic 迁移与前端重构组件『均未合入生产代码库』; 该陈述仅在 t001 时点成立且无时点标记；t002–t007 已合入 main（见 docs/handoff.md 与 adoption_decision 落地记录），src/backend/cbrowser/ 下服务代码俱在; 该 spec 仍在 docs/specs_index.md 中列为生效
  - Impact: 生效 spec 中的过期现状陈述会误导读者判断 v2 的实际交付状态。
  - Fix: 为 §5 加注时点（如『截至 t001 验收时点』）或改为历史语气，并链接当前实现状态出处。

- [Low][95] docs/handoff.md:5-10 — 最新交接节自述 head_commit 7535802，但包含该节的提交实为 5136766，head_commit 未计入交接提交自身
  - ID: f_docs_current_10; verification: static
  - Evidence: docs/handoff.md:5 节标题为 2026-11-02T20:12:30+08:00；:9 写 branch main、交出时 head_commit 7535802（本交接单独提交）; git log 显示 HEAD 5136766『docs: hand off t014 drop, seamless clipboard and t009 next』即该交接提交本身，7535802 是其父提交; 仓规则（AGENTS.md 交接规范）要求 handoff 记录交出时的 head_commit；按字面读，文件描述的并非当前 HEAD
  - Impact: 接手者按 handoff 核对仓库状态时会对不上 HEAD，削弱交接的可核验性（属自引用口径问题，非内容错误）。
  - Fix: 统一口径：或写明『正文基于 7535802、本节以其后一提交落地』，或在交接流程中以占位+amend 方式使 head_commit 与落地提交一致。

- [Low][95] docs/reviews/review_20261101_075819/adoption_decision.md:70-84 — D1 已决策并落地，却仍挂在『待决定项（请先决策）』标题下，且决策行尾重复了一个 A
  - ID: f_docs_current_11; verification: static
  - Evidence: adoption_decision.md:70 标题为『## 待决定项（请先决策）』，:17 引言仍称仅保留 D1 作为待决定项; :84 D1 条目内已记录『用户决策：A（审批通过时确认按推荐 A 执行）A』——行尾多一个重复的 A; 该决策已实际落地：docs/specs/runtime_persistence.md:23、:127 已按 D1 修订，代码 FK 为 CASCADE
  - Impact: 只读标题/引言的读者会误以为 D1 仍悬而未决，可能重复发起决策或按未决状态行事。
  - Fix: 将 D1 移入已决策区或在标题处标注『已决策：A（日期）』，并删除决策行尾重复的 A。

- [Low][90] docs/specs/storage_and_artifacts.md:48-48 — AC-003 已勾选通过，但其正文自带『待确认』的未闭环子项（p014）
  - ID: f_docs_current_12; verification: static
  - Evidence: docs/specs/storage_and_artifacts.md:48：『- [x] AC-003：……容器内 GTK 文件选择器可达性待确认，见 p014。』; docs/pending/todo/p014_v2_upload_picker_access.md 仍在 pending 区，未关闭
  - Impact: 勾选状态与正文证据自相矛盾：验收记录显示通过，实际仍有一项可达性未验证，后续无人再跟进的风险高。
  - Fix: 将 AC-003 改为部分通过/未勾选并注明待 p014 闭环，或把待确认子项拆为独立未勾选 AC。

- [Info][85] docs/v2_architecture_plan.md:476-486 — v2 计划 §8.4 正文仍是已被修订作废的剪贴板旧策略，仅靠文首修订块覆盖
  - ID: f_docs_current_13; verification: static
  - Evidence: docs/v2_architecture_plan.md:47-52 修订块声明优先于 8.4 与 19.3 原文（剪贴板改 seamless 同步、原内容保护条款作废，decisions 012）; §8.4 正文 :476-486 未加任何『已修订』内联标记，深链直达该节的读者会读到作废策略
  - Impact: 局部阅读时可能按作废策略实施或验收；全文通读则无碍，故仅记 Info。
  - Fix: 在 §8.4 与 §19.3 原文节首各加一行『本节已被文首 2026-11-02 修订块替代』标记。

- [Info][90] docs/specs/runtime_persistence.md:90-90 — spec 内嵌形似真实凭据的合成 canary 字面量，公开仓会被秘密扫描器误报
  - ID: f_docs_current_14; verification: static
  - Evidence: docs/specs/runtime_persistence.md:90 的日志脱敏 AC 中直接写入密码/Token/Cookie/剪贴板四类合成测试值（形如 SECRET_TOKEN_... 的占位串，值本身为测试夹具、非真实凭据，此处不复述）
  - Impact: 无真实泄漏，但自动化 secret 扫描与人工初筛会反复命中同一位置，产生告警噪声并掩盖真问题。
  - Fix: 改为不具凭据形态的抽象描述（如『注入的测试密码/Token（值见测试夹具）』），真实夹具值只留测试代码。

- [Info][92] docs/reviews/review_20261101_075819/review_opencode_cpa_gemini_3_8_flash.md:348-348 — 历史文档含开发者绝对路径与内网 IP 等低敏环境信息
  - ID: f_docs_current_15; verification: static
  - Evidence: review_opencode_cpa_gemini_3_8_flash.md:348 引用开发者本机绝对路径 /Users/karson/kar/code/CBrowser/...（含用户名）; docs/findings/d020_orbstack_bridge_reachability.md:5 记录内网目标地址 192.168.237.2；docs/findings/d009_turn_hmac_relay_transport.md:7 记录 Docker 网络地址 172.29.0.10（均为 RFC1918 临时实验地址）
  - Impact: 敏感度低（内网临时地址与本机路径），不构成凭据泄漏；仅在公开仓卫生层面值得知悉。
  - Fix: 可保留作历史证据；如做公开仓清理轮次，将绝对路径改为相对路径、内网地址改为占位段。

- [Info][98] docs/blueprint/architecture.md:141-147 — architecture.md 第 5 章小节编号倒置：5.5 排在 5.4 之前
  - ID: f_docs_current_16; verification: static
  - Evidence: docs/blueprint/architecture.md:141 为 ### 5.5 运行意愿协调（Runtime Coordinator），:147 才为 ### 5.4 协议兼容与 API 演进
  - Impact: 纯编号顺序瑕疵，不影响内容正确性，但引用『architecture.md §5.4』时易产生定位混乱。
  - Fix: 将两节编号对调或重排为 5.4 协调、5.5 协议兼容，并同步文内交叉引用。

- [Low][88] docs/specs/storage_and_artifacts.md:15-22 — storage spec §2.1 核心表清单只有 7 张，漏列 settings 表
  - ID: f_docs_current_17; verification: static
  - Evidence: docs/specs/storage_and_artifacts.md:15-22 列 profiles、profile_config_versions、profile_tags、profile_runtimes、runtime_events、artifacts、audit_events 共 7 张; docs/blueprint/persistence.md:37-39 将 settings 列为第 6 张核心表（共 8 张），代码中 settings 表实际存在
  - Impact: 按 storage spec 理解数据模型的读者会漏掉系统级设置表；属同一事实双处表述不一致的小漂移。
  - Fix: 在 §2.1 补入 settings 表一行，或声明该清单仅列 Profile 域表、完整清单以 persistence.md 为准。

## views

```json
{
  "security": {
    "status": "completed",
    "reviewer": "0d04b289-68cc-4978-8e8e-23494e28a7a4"
  },
  "correctness": {
    "status": "completed",
    "reviewer": "0d04b289-68cc-4978-8e8e-23494e28a7a4"
  },
  "contracts": {
    "status": "completed",
    "reviewer": "0d04b289-68cc-4978-8e8e-23494e28a7a4"
  },
  "performance": {
    "status": "not_applicable",
    "reviewer": "0d04b289-68cc-4978-8e8e-23494e28a7a4",
    "reason": "本 unit 仅含文档，无可执行代码或性能敏感产物；性能验收口径文档（t009 契约、benchmark 评审）的一致性已在 documentation/tests 视角下核对。"
  },
  "design": {
    "status": "completed",
    "reviewer": "0d04b289-68cc-4978-8e8e-23494e28a7a4"
  },
  "robustness": {
    "status": "not_applicable",
    "reviewer": "0d04b289-68cc-4978-8e8e-23494e28a7a4",
    "reason": "本 unit 无运行时行为；文档流程层面的失效模式（状态过期、索引漂移、交接失真）已在 documentation/correctness 视角下覆盖。"
  },
  "tests": {
    "status": "completed",
    "reviewer": "0d04b289-68cc-4978-8e8e-23494e28a7a4"
  },
  "documentation": {
    "status": "completed",
    "reviewer": "0d04b289-68cc-4978-8e8e-23494e28a7a4"
  }
}
```

## files_reviewed

```json
[
  "AGENTS.md",
  "BINARY-LICENSE.md",
  "CHANGELOG.md",
  "LICENSE",
  "README.md",
  "docs/blueprint/architecture.md",
  "docs/blueprint/artifacts.md",
  "docs/blueprint/automation.md",
  "docs/blueprint/browser_runtime.md",
  "docs/blueprint/conventions.md",
  "docs/blueprint/decisions.md",
  "docs/blueprint/domain.md",
  "docs/blueprint/frontend.md",
  "docs/blueprint/gateway.md",
  "docs/blueprint/persistence.md",
  "docs/blueprint/security.md",
  "docs/blueprint/stream_runtime.md",
  "docs/blueprint/supervisor.md",
  "docs/blueprint/testing.md",
  "docs/findings/d001_v2_validation_baseline.md",
  "docs/findings/d002_cdp_uds_download_recovery.md",
  "docs/findings/d003_selkies_ice_restart_gap.md",
  "docs/findings/d004_docker_shareable_ipc_contract.md",
  "docs/findings/d005_encoded_fps_is_not_motion.md",
  "docs/findings/d006_runtime_event_recovery_checkpoint.md",
  "docs/findings/d007_multi_viewer_media_identity.md",
  "docs/findings/d008_gateway_process_media_recovery.md",
  "docs/findings/d009_turn_hmac_relay_transport.md",
  "docs/findings/d010_ice_generation_continuity.md",
  "docs/findings/d011_profile_ipc_audio_boundary.md",
  "docs/findings/d012_turn_generation_media_commit.md",
  "docs/findings/d013_capture_visibility_arbiter.md",
  "docs/findings/d014_native_ime_commit_path.md",
  "docs/findings/d015_sql_error_log_boundary.md",
  "docs/findings/d016_sdk_owner_lifecycle_boundary.md",
  "docs/findings/d017_native_xkb_named_spares.md",
  "docs/findings/d018_selkies_native_peer_entry.md",
  "docs/findings/d019_turn_loopback_mapping.md",
  "docs/findings/d020_orbstack_bridge_reachability.md",
  "docs/findings/d021_selkies_ice_restart_commit_is_async.md",
  "docs/findings/d022_selkies_rtc_config_url_contract.md",
  "docs/findings/d023_headless_chrome_visibility_static.md",
  "docs/findings/d024_selkies_token_secure_mode.md",
  "docs/findings/d025_selkies_resume_grace.md",
  "docs/guides/browser_isolation_analysis.md",
  "docs/guides/browser_runtime_validation.md",
  "docs/guides/stream_runtime_validation.md",
  "docs/guides/supervisor_validation.md",
  "docs/handoff.md",
  "docs/pending/todo/p014_v2_upload_picker_access.md",
  "docs/reviews/review_20261101_075819/adoption_decision.md",
  "docs/reviews/review_20261101_075819/review_opencode_cpa_gemini_3_8_flash.md",
  "docs/reviews/review_20261101_075819/review_opencode_opencode_go_deepseek_v4_1_flash.md",
  "docs/reviews/review_20261101_075819/review_opencode_opencode_go_muse_spark_1_3_contributor.md",
  "docs/reviews/review_local_benchmark_20261027/review_benchmark.md",
  "docs/reviews/review_v2_scope_20261027/review_disposition.md",
  "docs/reviews/review_v2_scope_20261027/review_scope_initial.md",
  "docs/reviews/review_v2_scope_20261027/review_scope_revised.md",
  "docs/reviews/review_v2_scope_20261027/review_traceability.md",
  "docs/specs/access_control.md",
  "docs/specs/browser_isolation.md",
  "docs/specs/profile_management.md",
  "docs/specs/runtime_lifecycle.md",
  "docs/specs/runtime_persistence.md",
  "docs/specs/storage_and_artifacts.md",
  "docs/specs/v2_runtime_validation.md",
  "docs/specs/webrtc_remote_display.md",
  "docs/specs_index.md",
  "docs/tasks/t009_v2_full_acceptance/note.md",
  "docs/tasks/t009_v2_full_acceptance/task.md",
  "docs/tasks/t010_v2_data_migration/note.md",
  "docs/tasks/t010_v2_data_migration/task.md",
  "docs/tasks/t011_v2_remove_legacy/note.md",
  "docs/tasks/t011_v2_remove_legacy/task.md",
  "docs/tasks/t012_v2_docker_release/note.md",
  "docs/tasks/t012_v2_docker_release/task.md",
  "docs/tasks_index.json",
  "docs/v2_architecture_plan.md"
]
```
