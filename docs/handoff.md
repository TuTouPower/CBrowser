# 项目交接记录（最新）

本文件只保留当前有效一节。过时段落由 `repo-hygiene` 迁入 `docs/archive/handoff.md`。

## 2026-10-28T03:11:40+08:00 v2 架构计划执行交接

- branch：main
- head_commit：e76e860（更新本交接前主干HEAD；最新业务集成仍为t001的2fb32ba）
- 交接更新约定：每完成一个阶段立即更新本文件（用户最新明确要求），包含该阶段提交、实际验证、遗留项及下一步。
- 执行目标：完成 `docs/v2_architecture_plan.md`，最终部署到当前 Mac 的 OrbStack Docker，由同机 Chrome 访问。t001 技术验证已完成并合入；正式 v2 业务实现尚未合入，下一阶段 t002。

### 最新用户决定

- 公网穿透、原生 Linux x86_64 执行记 `NOT_RUN / USER_WAIVED`，不再阻塞实施，不得记为实测通过；保留相关功能及构建支持。
- 基准：M1 Max、10 核、64GiB；OrbStack 实际 10 CPU、约 15.66GiB，Linux aarch64，CPU 编码。1/3/10 活跃流逐级测容量，保留单流 1080p30、反馈 P95≤100ms、首帧 P95≤1秒、8小时压力及1000次 IME/剪贴板验收。这些是目标，尚未完成正式性能验收。
- 本地部署为最终交付；外部推送、公网发布须另获明确授权。旧环境阻塞记录已被上述决定取代，不再索要被豁免环境。

### 已完成与验证

- 主干已登记14个 task 及依赖：t001→t002→t003→t004→t005→t006→t007→t008→t013/t014→t009→t010→t011→t012；t013/t014 存在并发冲突，依工具生成计划执行。
- 最近提交：`ece7eaa` 记录环境豁免；`df439af` 调整本地性能基准及 t009/t012 契约，文档已独立审查。
- t001 工作副本有9项已归档 spike、d001–d014 findings、验证矩阵与蓝图/spec 更新，已随执行提交 d7ee99c 合入主干（merge 2fb32ba）。
- 基线回归：模板169通过、后端384通过、前端49通过。前端 Node26 需 `NODE_OPTIONS=--no-experimental-webstorage`；模板测试 TMPDIR 使用 Git 工作副本之外目录，避免已有 fixture 受真实 worktree 影响。
- t001 工作副本 doctor/test/blackbox 命令块通过；该副本 repo_sync status 报未初始化。合并后主仓独立命令块退出0：168 passed/1 skipped 契约、384后端、健康ok；主仓存在原有被忽略 sync_state，repo_sync status读取固定本地来源。不能混淆两处环境。模板默认命令测试因主仓已有sync_state按原有条件跳过，未修改测试。

### 当前现场与恢复入口

- t001：done / integrated。执行提交 d7ee99c16e02defd9d034eec519e328f33823f87，集成提交 2fb32ba4bf98。原登记工作副本已 exact cleanup，分支由集成脚本删除；不得再访问旧路径当作执行现场。
- 权威交付：docs/archive/tasks/t001_v2_runtime_validation/（task、note、handoff.json、两轴review、矩阵、范围调整），9项实验在 docs/archive/spikes/，d001–d014 在 docs/findings/。
- 已完成 identity：attempt=1，execution_id=f5cd74fec7234b418c76206a08cff06b；owner_id=root_v2_20261027。ledger已有terminal completed/report done/integrated；不再 reserve t001。
- 正式Round2双轴最终PASS，指纹bdaea2ca98d286a6。code初审两条失实finding已撤回，一条minor供t006生产Gateway参考。test实际重跑Core/Native及媒体、隔离、下载、恢复、TURN负例；矩阵环境项单独查验。全部审查进程terminal exit0。
- 原始过程证据：主仓 .scratch/v2_orchestration/ 中JSONL与merge_t001/gates.log；清理前另备份 t001_scratch_evidence.tar.gz（权限0600，排除缓存/临时目录；运行期socket不可归档，不作为测试资产）。scratch仅本机恢复，不替代Git/task状态。
- t002已active：/Users/karson/kar/code/CBrowser_t002，branch=t002_v2_backend_foundation，diff_anchor=d3ca80b0141c19a715a90c71ba2f5862c1c79711；attempt=1，execution_id=13f1211c2c0046629e9f68c9741d2514，owner_id=root_v2_20261027。沿用当前attempt，不重复start/reserve。
- OpenCode实现session：ses_e82dd5473ffeX6ZEkqtLVe1bBD。96159、33841及最新lint90433均已完成。90433持久会话finish=stop，保存t002_lint_final.json后中断残留CLI PID66191，terminal子进程-2；不冒充自然exit0。14新增Python文件Ruff check/format均通过；diagnostics新增问题已修，13项既有基线保留。
- Verify Round3已实际执行：冻结manifest=3459bd7d3659e1d6528fc2f4c12d587a98c3124abd5d67bf6b764b85d5f6461f，8/8通过且无finding，主控核验冻结文件与当前源码一致。报告worker31492正在收尾；前两轮失败证据保留，上限仍5轮。
- 正式full code/test Round1已按实际最终范围完整提示派发：code进程46906/PID95420/session=ses_e813a6e91ffecjvQTYnIF2wNuY；test进程61687/PID95529/session=ses_e813a3ddfffeo3WagRl7MAmvtg。两者只读源码，各写对应review和专属scratch，最终报告尚未回收，不finish/集成。
- t003只读准备64619/纠正29622均terminal0，未start t003。日志在主仓.scratch/v2_orchestration/；恢复先查实际进程、checkpoint与task.py recovery。

### t002 第一轮候选验证结果

- 作者新增单元/独立HTTP测试15通过、旧后端384通过；未完成正式独立review，不能据此收尾。
- Verify Round1候选黑盒：最终7项中3通过/4失败，进程89822已terminal。实际发现并发不相交PATCH丢失已确认修改、跨Profile复用幂等键静默跳过、错误绑定/配置代际、ID形状的敏感字符串进入事件日志。另一次中途运行出现并发重复exit的500，最终重跑未再出现，按竞态记录，不能当已闭环。
- 已验证正例：真实SQLite持锁1.5秒后请求成功、超过5秒返回可重试503、释放后恢复；重复tag导致SQL约束失败后无半写数据。完整原始stdout与有限保留的物理日志见control/.scratch/t002_blackbox_candidate；早期失败运行日志被harness覆盖，后续必须每轮独立目录保存。
- 主控另以真实独立HTTP复现旧启动意愿重放清除failure_count、迟到bind覆盖新实例，证据在主仓.scratch/t002_replay_audit/。
- harness也存在待纠正口径：stale_instance优先返回且未改状态并非错误；最初OpenAPI仅比较path集合，不足以证明完整响应契约；原生进程启动日志不证明迁移后logger仍有效。41513同一旧冻结候选补验已结束，独立目录run_20261027_121633_ce5ead结果为2/7通过、5/7失败，明确重现并发重复exit的500；不代表新修正版失败或通过。
- 生产修正与独立harness各写自身worktree/scratch，源码冻结副本互不干扰。主控另修harness通过条件遗漏：重放使用同一幂等键且必须保留失败计数；合法CAS切换先确认新实例运行；缺用例或finding不能退出成功。修订仅做语法检查，等待新生产候选实际执行。
- t003准备稿经主控纠正SDK缓存环境变量、导入副作用、Xauth长度和事件落盘等失实项；仅为条件化准备，使用前仍按实际源码与t002最终契约核对。
- 后续本地管理员密码文件路径已异步询问，供t006/t012使用；当前不因该信息暂停后端工作，不自设生产默认密码。

### t002 第二轮验证与最新修复

- Verify Round2冻结快照：control/.scratch/t002_blackbox_candidate_2/，manifest=f3c76c2b0b266586b60746d87added4ed56824b443e278558e2117110b771118。独立黑盒6/7通过，唯一失败为静态OpenAPI导出未同步实际RuntimeEventResponse；完整响应schema校验8项通过。真实SQL约束异常返回409，物理日志未出现测试私密字符串。该结论只适用于该冻结快照。
- 96159修复typed DB异常出口后，作者自测15单元+5独立HTTP通过；主控完整门禁169契约+384旧后端+15单元+5独立HTTP通过。主控门禁早于33841后续改动，不能替代最终候选验收。日志：CBrowser_t002/.scratch/t002_gates/project_gates_fixed.log；最初遗漏jsonschema依赖导致的失败日志保留。
- 独立静态预审42071结束，采纳普通读取误用BEGIN IMMEDIATE、不可达404、无效重试和重复索引等问题；其中“导出完全一致”“Profile删除级联删除事件”等失实结论已在t002_pre_audit_disposition.md驳回。预审不替代正式canonical review。
- 33841已terminal0：普通读取改BEGIN，7类写操作使用BEGIN IMMEDIATE；移除无效IntegrityError重试和重复索引，重导OpenAPI，并增加live/export深度一致性与持写锁并发读测试。作者报告169契约+384旧后端+19单元+5真实HTTP通过；尚未完成最终独立复核，不勾选剩余AC。
- 新增已验证发现d015（SQL异常日志边界）、runtime_persistence spec及索引，均在t002工作副本，未合入main。t002仍active，尚无执行commit，未finish、cleanup或集成。
- 最新主控Ruff结果：CBrowser_t002/.scratch/t002_gates/ruff_check.json，共102项。先区分新增代码问题与既有diagnostics问题，再精准处理；完成格式和相关回归后冻结candidate3，避免冻结后再次变更交付源码。
- 新阶段完成：candidate3独立harness准备，目录control/.scratch/t002_blackbox_candidate_3/。原7项业务用例保留，第6项新增持写锁期间真实GET低于1秒且锁未释放；第8项新增真实服务两次重启、完整字段/标签颜色持久化、幂等重放、非法PATCH完整响应不变与旧快照不变。主控补强所有输入字段比较、持锁Event成功断言、PID/退出码记录与追加物理日志。仅语法/准备，未执行产品验收。
- OpenCode CLI异常：87336测试准备任务的持久会话已finish=stop并保存最终答复，但CLI继续存活且JSONL为空。主控先以只读数据库查证并保存t002_blackbox3_prepare_final.json，再仅SIGINT已完成任务的PID66364；包装进程terminal，子进程返回-2，不冒充自然exit0。未修改全局配置。90433仍未完成，不能按同法提前中断。
- 本轮主控模板契约169通过（.scratch/t002_gates/contract_latest.log）。补齐testing.md的实际OpenAPI导出/校验命令，修正task可测试性及t001已完成上下文；未改AC业务范围。
- 本节与第一轮记录中“等待新候选执行”等描述是历史阶段状态；当前恢复入口以下方下一步为准。

### 最新阶段结果

- 主控最新完整门禁退出0：169契约、384旧后端、19新单元、5真实HTTP集成通过；旧健康ok，task list正常，工作副本repo_sync仍未初始化（退出0，不是配置成功）。日志CBrowser_t002/.scratch/t002_gates/project_gates_candidate3.log。
- candidate3独立8项黑盒：持写锁GET返回200约11ms且锁仍持有；短锁写等待1.61秒成功，长锁约5.22秒返回503/Retry-After，释放后恢复；重复tag返回409且物理DB无半写。3个不同uvicorn PID均已终止，真实两次重启后完整配置/标签颜色、不可变快照、幂等、删除状态留存。
- 独立SQL日志探针：422响应无私密值回显，约束409，物理日志无注入敏感值泄漏。该测试覆盖边界见d015，不宣称所有未知Python异常绝不泄漏。
- 已补齐OpenAPI生成/校验文档、修正t002不依赖Docker/Chrome的可测试性，并在架构文档区分已新增后端基础与未切换的旧正式入口。全部AC由主控真实门禁暂勾，正式review须独立复核。

### 下一步与边界

1. 观察三项现有worker（31492、46906、61687）实际终态和持久会话，不重复派发；OpenCode CLI存在任务结束后不退出/JSON为空问题，观察器run_opencode_observed.py仅在持久最终答复finish=stop后保存证据、中断残留CLI，绝不杀仍在运行的模型任务。未修改全局配置。
2. 回收正式code/test报告，核对最终reviewed_scope和finding处置。失败则按原5轮上限修复重审，不以静态预审代正式通过。
3. 通过后写task级handoff.json、唯一执行commit、exact cleanup与已获授权的本地main集成。不push。t002完成前不start t003。
4. 每阶段完成立即更新本文件，失败阶段也记FAIL与恢复入口；项目级handoff不能替代task级handoff.json。
5. 管理员密码文件路径已异步询问，供t006/t012使用；当前不因此暂停后端工作，不自设生产默认密码。

- 工作区保护：主干写交接前干净。各task用户改动保留；临时uv.lock先核实来源和进程状态，避免将reviewer生成文件纳入交付指纹/提交。已完成t001未提交资产均已提交或备份，没有遗失清理。
- 全局约束：只写 `~/kar/code` 内；保持用户改动；使用 OpenCode 指定模型执行已授权子任务；不修改 `.repo_template` 绕过门禁，不把技术原型当成正式生产组件。
