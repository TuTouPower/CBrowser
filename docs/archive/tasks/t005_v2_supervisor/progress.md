---
tid: "t005"
slug: "v2_supervisor"
title: "实现唯一 Docker 协调者与运行事件恢复"
status: "done"
branch: "t005_v2_supervisor"
worktree: ""
review_level: "full"
review_limit: "5"
verify_limit: "5"
diff_anchor: "84f84311815bff330a51bcd35da150fc8b4990b3"
depends_on: "t004"
conflicts_with: ""
note: ""
---

# Task 进展

front matter 只经 `task.py` 修改；reviewer 只写对应 `review_*.md`。

## 实施笔记

执行期记录关键步骤、决策、验证、阻塞和用户批准的新轮次上限。

创建期不预测实施步骤。只记有追溯价值的内容；无事项时写“无”。

#### 2026-10-29T21:45:37+08:00 t005恢复接线与容器拓扑检查点

- 当前t005仍attempt1/execution8c2fd5e26cdc49f4bd8008edecd1d36e/ownerroot_v2_t005_20261029，branch=t005_v2_supervisor，head_commit=84f84311815bff330a51bcd35da150fc8b4990b3；尚无执行commit/finish，七AC未勾、正式Verify/full review0。此前恢复入口中的PID27347与candidate_02均已过时。
- 独立真实API离线黑盒已PASS39.35秒：实际停止API、UDS正常关闭、事件落盘、Supervisor SIGKILL、同DB恢复及无误重启；公共Gateway fixture改为Bearer鉴权和实例fence，三个host E2E与相关unit共8PASS136.13秒。fixture不代表t006正式Gateway完成。
- 新Supervisor容器+独立API/Gateway/coturn+双Profile完整拓扑PASS21.79秒（.scratch/t005_api/container_graph_round3.log）：仅Supervisor挂Docker Socket、无SQLite/SQLAlchemy，Browser独立egress网络、Stream仅媒体网络，实际infra IP下发，Viewer关闭握手先于Runtime删除、旧stop重放不杀新实例，Supervisor实际SIGKILL后恢复。该PASS使用Supervisor06=sha256:76ed6bb2733533fa52a84f9c39c93b47a979d3b3b7222cfabb2c1079c19415ec；之后源已变，且新增Browser PID/容器ID不变断言，必须重建重跑，不能冒充当前候选PASS。冷启动API fixture需sqlalchemy[asyncio]补greenlet；正式交付依赖检查留t012。
- 按明确架构计划“异常后自动重试三次2/10/30”收敛为首次异常+三次重试，failure_count记录异常总数4时阻断；不再等待旧计数问题答复。共享domain/runtime_policy用于API与Supervisor，无DB结构迁移。新真实SQLite四项生命周期语义+调度测试5PASS0.89秒，相关repo/core回归25PASS1.91秒。旧test_runtime_events_convergence_and_exit_contract及test_retry_policy_three_strikes整体删除，分别由新正常/异常/迟到/重放/heartbeat属性覆盖，未就地改旧预期制造绿。
- Root补原子快照/派生凭证写入（替换symlink而非跟随）、Profile目录别名和跨Profile特殊挂载拒绝，13PASS0.56秒；事件journal路径与内部profile/instance须一致，4PASS0.43秒。API无本地session状态改读权威running意愿，真实HTTP先RED后1PASS2.12秒。
- 恢复协调器首稿close锁死锁与快照RPC失败猜配置均由Root真实RED复现；作者修复后Root复验10PASS0.38秒。Runner已接tick/close。旧retry E2E只重建同进程对象，不能证明SIGKILL，已退回改真实subprocess及Docker创建时间/持久due证据，2/10/30实际时间仍未通过。
- 当前唯一生产writer为OpenCode恢复作者session ses_e78331402ffedLVqPXYz1O9UBW、PID41557/exec99923，独占recovery_coordinator.py、新retry E2E、新coordinator单元；日志main/.scratch/v2_orchestration/t005_recovery_actual_process.jsonl。另测试格式作者PID41730/exec17547独占其owned_files.json枚举的新test/fixture，日志t005_test_lint.jsonl；Root不触及上述写域。恢复前核PID及JSONL最终stop，不重复启动。Root拥有其余生产/文档。
- 下一步：真实重试黑盒闭环、当前源镜像重建及加强容器拓扑复验、完整门禁/文档/schema、冻结候选后独立full review；再按原队列t006→t007→t008→t013→t014→t009→t010→t011→t012继续。公网ICE与原生x86仅两项USER_WAIVED；容量/P95/8h/1000输入均未测，不宣称通过。

#### 2026-10-30T01:06:55+08:00 t005真实网络证据纠偏与启动竞态修复

- branch=main，head_commit=05c8a52f4badb46893154d360e1d8ff4320e94ba（本次交接更新前）；t005仍branch=t005_v2_supervisor、head=84f84311815bff330a51bcd35da150fc8b4990b3、attempt1/execution8c2fd5e26cdc49f4bd8008edecd1d36e/ownerroot_v2_t005_20261029。未执行commit/finish，七AC未勾，正式Verify/full review0；独立预审不充当正式review。
- 真实重试作者已terminal：三档Docker Created-API updated_at为3.04/11.59/31.21秒，真实Supervisor进程SIGKILL returncode=-9、换PID、failure_count4阻断、手动恢复/正常关闭，87.02秒PASS。Root后续发现并修复API非200仍合成exit、cleanup上限仅记录不执行、singleton路径跟随其他Profile；3项真实逻辑RED后相关14PASS2.52秒。控制HTTP错误不再回显/记录完整异常，敏感canary先红后8PASS0.72秒。该87秒结果早于上述修复，当前源重试E2E仍须复验。
- 容器图Round4新增Browser PID断言真实失败：旧runner_info/socket令替换实例提前ready；Root补profile/instance/config_version/PID核对，相关16PASS2.31秒。当前整镜像Supervisor10=sha256:51075e9c19990b8d247fae63f5ee25eb8330d36f002652354056b84230f447a6，API03=b53bca10263588b8c364b697984c69630d239573ab8b1a70c28782756c50c785，Gateway02=dac21afe70d77cab6e55c2dfbb10d41f1785e5cf55cdc0c30466b3fc483ebf28；加强后的容器图Round5 PASS25.37秒（container_graph_round5.log），无源码overlay。新增导出脚本同步Supervisor JSON schema，stop两种fence必需；schema检查1PASS。
- **网络隔离证据纠正，不能略过**：Root发现旧RUNTIME_SERVER_SCRIPT主动过滤gateway来源，先前“普通bridge隔离已证明”结论无效。独立无过滤server同网/跨网均PONG；internal=True对照同网成功、跨网ENETUNREACH。已经工具创建d020_orbstack_bridge_reachability.md，当前AC-001/006网络部分未通过。普通bridge不能当强隔离；internal对照不能证明Browser上网与媒体都满足。透明代理是待证假设，不写成根因。
- 用户授权问题已通过异步问题发出，尚未收到答案：只临时把新测试网段198.19.254.0/24加入OrbStack network.proxy.exclude，实验后恢复原值空。原network_proxy=auto，macOS HTTP/HTTPS/SOCKS启用；该网段与现有Docker IPAM无重叠。方案.scratch/t005_api/proxy_exclusion_proposal.md，尚未写任何OrbStack设置。仓库外写入须明确授权，不因goal自动放宽。官方资料https://docs.orbstack.dev/docker/network#proxies；ego任务space0已正常finish，不复用已结束space。
- **当前两个验证lane及一个测试writer**：测试配置作者PID55415/exec62939/session ses_e7819b695ffeNbrwEZ2hzQaFsj，仅owned_files.json新测试/fixture及retry E2E，日志main/.scratch/v2_orchestration/t005_test_config.jsonl；Root不改其文件。独立源码预审PID58944/exec10629/session ses_e77666b69ffe3WdRC251TK9O4v，仅validation/.scratch/t005_pre_audit报告/实验，已给冻结生产副本；真实namespace网络策略研究PID60597/exec52723/session ses_e776180a5ffeJysDs9jL57L3hM，仅validation/.scratch/t005_net_policy，自有t005-nsp资源，不许host namespace/Socket/全局设置。恢复先核PID和最终stop，不因观察超时重启。
- 最新门禁未全绿：17真实HTTP PASS33.47秒；unit_checkpoint_3为192PASS/1FAIL（MockDockerAdapter仍写旧位置/缺代际runner_info导致严格ready超时，测试writer正在核fixture；不可把200预期改500制造绿）。全组合full_checkpoint_2为205PASS/1FAIL，后者是cleanup测试脆弱RPC响应序列，Root仅改按路径供响应的fixture，保留断言。当前生产Root Ruff E/F/W/I通过；全部最终门禁还未运行。旧uv.lock核明由恢复作者漏--no-project命令生成，已移.scratch/t005_recovery/generated_uv_lock_backup，未提交/删除用户资产。
- 自有泄漏be981097b0b4已由旧network_finalization JSONL精确确认是t005-net-9e0a2e91失败前登记异常遗留，核labels/无网络后仅删除此ID。未知pensive_satoshi42bbb06167ec与既有cbrowser/其他服务均未动。网络/竞态/重试证据已复制main/.scratch/v2_orchestration/t005_evidence_live/network_readiness_checkpoint，含SHA256 manifest，0700/0600。
- 下步：真实隔离修复及无过滤正负复验、当前重试/离线E2E重跑、预审处置、全门禁及最终文档/spec、冻结后正式独立review与一个执行commit。后续固定队列不变；公网/原生x86仅两项USER_WAIVED，容量/P95/8h/1000输入均仍未测。

### 开工现场与计划

- branch=t005_v2_supervisor，base/diff_anchor=84f84311815bff330a51bcd35da150fc8b4990b3；attempt1，execution_id=8c2fd5e26cdc49f4bd8008edecd1d36e，owner_id=root_v2_t005_20261029。登记WT=<repo>_t005，已reserve/claim，不重复启动。
- 前置t003/t004已合并；main实际169contract、384legacy、120unit、9HTTP、13Runtime、12Stream通过。原worktree已清理，不依赖其scratch fixture。可读稳定测试解释器在main/.scratch/t004_integration_gates/{project_venv,media_venv}/bin/python。
- 主机只写~/kar/code；禁止读/source本WT的.env软链，不访问或停止既有cbrowser容器。实际数据根、容器和网络都用新前缀，失败后先查状态再精确回滚，不使用prune。
- 定义认证RPC及持久事件/路径契约 → 真实HTTP拒绝和路径逃逸验证；唯一Docker协调器、幂等端口/网络/双容器生命周期 → 真实双Profile与并发/回滚；重启扫描、事件恢复、退出分类和2/10/30重试 → 独立API/Supervisor进程SIGKILL与离线重放；真实CPU窗口和配额 → 实际降帧/恢复、低负载和后台对照；全门禁、独立黑盒及full review → 一个执行commit、cleanup和本地合入。
- 正常Browser关闭才清desired state；driver失联即使Chrome退出0也可能lifecycle/error，不得误清运行意愿。GeoIP engine-cache初始化纳入真实启动检查；Native日志格式统一和t004 CLI体积minor由t012交付入口整理时处理。
- 七AC仍未勾，CPU、重试、恢复不以配置或mock代替实测。后续容量、P95、8h和1000输入不提前承诺。

无

## Review 处置

每个结构化 finding 一行。`已修` 表示本 task 已修复；`遗留` 必须指向 `pNNN` 或 follow-up tid；`撤回` 必须写清理由。critical/important 未解决时不得 PASS。

### Round 1 (2026-10-30T10:10:00+08:00)

|finding_id|severity|status|rationale|fix_ref|
|---|---|---|---|---|
|t005_code_f001|minor|遗留|tick 复杂度高但全路径真实 E2E 覆盖、无已知缺陷，冻结后重构会使整套 Docker 验证失效|p001|
|t005_test_f001|minor|已修|两处残留检查改为无条件断言（不存在目录 glob 为空），真实 E2E 复跑 1 passed|tests/e2e/test_supervisor_policy_failure_e2e.py:175|

两路 reviewer（code ses_e7663e0d1ffeoEYZnyEUWgRZH6、test ses_e7663e0e9ffehbXOgOCriVZ4i7，OpenCode cpa/gemini-3.8-flash --variant high）均 verdict PASS，scope=fc9c501c863e0460。主控复核：code 报告把三路并发重复 start 的证据误引为 container_graph_round5.log（实际为本轮新增断言，证据在 round1 sup_graph.log/graph_ports.log），属引用错误，不改变结论。

### Round 2 (2026-10-30T10:35:00+08:00)

Round 2 零 finding。增量：md_kx 对 tests/fixtures/supervisor_recovery_probe/gateway_contract.md 的列表缩进格式化；按 t005_test_f001 改 tests/e2e/test_supervisor_policy_failure_e2e.py 为无条件断言并真实复跑 1 passed。code/test 两路续用 Round 1 session 复审均 verdict PASS，scope=0c131820c44b993e。两路 wrapper 均在对方合法写入其报告后被 SHA 守卫中断（主控派发时未同时排除另一路报告文件，属主控配置疏漏）；中断发生在各自报告写完之后，主控已核对两份 Round 2 小节完整，其余交付文件无变化。

## 收尾报告

### 验收与验证

- task：[`task.md`](task.md)
- 结果：全部满足
- 测试：主控冻结候选 round1（t005 WT `.scratch/t005_final/round1/`）：contract 169、legacy 384、unit 211、integration 21、Runtime E2E 13、Stream 12、Supervisor 生命周期 6、启动恢复 2、容器图等 8（端口断言复跑 1）、内核策略 5、资源 5 passed；schema 导出一致；Ruff/md_format/diff --check 通过。
- 黑盒：独立 OpenCode 黑盒（ses_e7663e0e0ffesEOxpy2HrEDCB1）在逐字节等同候选的 validation WT 自建镜像（Supervisor sha256:90a77d2feb26…、API sha256:c68e11f94908…、Gateway sha256:8a6af8c48f24…）复跑全部文档门禁同数通过，并以 4 个自写探针验证 AC-001/002/003/005（路径逃逸 0 容器、端口池耗尽 503、三路并发启动仅 2 容器且端口内外一致、未授权 401、重试实际间隔 3.45/12.53/31.82 秒含 SIGKILL、failure_count=4 阻断与手动清除）；无残留资源。主控核对其原始日志与 JSON 一致。证据 `main/.scratch/v2_orchestration/t005_validation/.scratch/t005_blackbox/`（cleanup 前备份）。
- review：Round 1 code/test 均 PASS；t005_code_f001 遗留 p001，t005_test_f001 已修。Round 2 复审 md_kx 缩进与 p002 修复增量。
- AC 判定：见 `task.md` 行内打勾

### 结果摘要

- 七 AC 全部真实验证通过；遗留 p001（minor）。公网 ICE 与原生 Linux x86_64 仅两项 USER_WAIVED；容量/P95/8 小时/1000 次输入由 t009 验收。
- specs_index：runtime_lifecycle 行新增 t005；blueprint supervisor.md、testing.md、decisions 008/009、finding d020 已更新。

### 长期文档闭环

本 task 须出现在 specs_index 的关联 task 列；无长期 spec 变更时写 `- specs_index: not_applicable: 具体原因`。正式 spike 须有 report、现存 finding、采纳结论、后续 tid 或无需后续理由；finish 会检查这些引用。

### API内部认证首批红绿

Root独占api/internal_supervisor.py与api/app.py接入，新增真实子进程HTTP测试tests/integration/test_supervisor_rpc.py。先RED：目标health路由404而预期401；实现外部文件读取、SecretStr保管及常量时间Bearer校验后GREEN：1PASS2.11秒，缺失/错误凭证401且不回显token，正确外部文件凭证200。fixture将setup失败也放在finally回收，避免旧测试异常前yield遗留进程问题。日志.scratch/t005_api/auth\_{red,green}.log。

当前只是内部认证基础，不代表配置/绑定/事件RPC已完成；尚需对接core_contract.md。OpenAPI导出在路由稳定后统一生成，暂不声称API全门禁通过。Core与resource作者各自协议草稿在其lane，Root需统一HTTP API Bearer与Supervisor控制header角色、真实批量reconcile字段，不能用未鉴权的旧公共路径冒充认证RPC。

Root API对接草稿用例校准：core_contract把重复事件描述成ignored_duplicate，实际t002既有RuntimeEventResponse为status=ok/outcome=duplicate。Root原新增草稿先误用status字段，再沿草稿误用枚举，尚不满足正式协议；未改任何t002业务输出或旧测试迎合。已整体删除该未提交草稿函数，重写test_authenticated_rpc_replay_does_not_cancel_new_running_intent：正常exit确实把running改stopped，新运行意愿后重放同event_id不能再次清意愿，直接观察持久状态与last_exit_event_id，不用猜测返回枚举造绿。原失败日志lifecycle_green.log保留。内部受限RPC复用t002规范handler和事务，仅配置读取/运行上报白名单，无Profile CRUD授权。

### 首批子域复核与续行

#### 2026-10-29T15:13:48+08:00 Root复核更新

#### 2026-10-29T19:55:18+08:00 Root真实媒体与安全检查点

实际Stream CPU压力经ResourceMonitor限制8FPS，官方Chrome两秒frames60→16→56，完整原媒体E2E PASS107.48秒，日志.scratch/t005_api/stream_cpu_v6.log、对应basetemp/supervisor_cpu_stream_proof.json保留5个精确raw窗口。该证明当前经fixture Gateway WS，不等同Supervisor容器+Gateway HTTP全路径已过。Docker SDK动态update没有nano_cpus参数，改实际CFS限额并识别Nano/CFS/Cpuset最紧预算；对应20单元PASS。

缓存freshhelper139复现后，检查SDK代码确认unpinned ensure_binary启动后台updater；线程与native退出139因果未有精确栈，不能夸称已确认。显式pin get_chromium_version与Runtime同引擎后fresh诊断退出0，正式单次helper初始化/GeoIP及相关测试25PASS2.05秒。Core作者缓存失败再试一次实现已整体删除，不能掩盖已知问题。首个Supervisor整镜像91d6d86e4592...构建/只读无网导入通过且无SQLAlchemy；源随后更新，candidate_02须重新inspect，不把旧镜像当当前源。专属Dockerfile.dockerignore仅送必要Python源，避免.env/数据/缓存进入context。

Root新增事件安全TDD：event_id穿越与旧instance normal事件移除新session两项RED后修复；队列哈希文件名、file+dir fsync、持久送达ACK。整体删除旧MockTransport test_event_forwarder_offline_spool_and_replay，因为其内部原始ID文件名预期已不安全，替换成真实TCP listener断开/重连及ACK重启测试，未把旧断言就地改哈希制造绿；相关6PASS0.50秒。新增控制面空/弱外部key拒启动与实际header认证，相关6PASS0.62秒；真实进程flock/SIGKILL恢复2PASS0.04秒。API新增受限PATCH runtime/desired-state复用既有规范handler/幂等事务，手动重试元数据真实HTTP3PASS4.83秒，OpenAPI导出同步；不把pending的重试计数规则擅自改掉。

核心Round4已terminal，其旧“offline”用例实为直接写spool、未断API，Root不采纳；新的独立offline作者PID27347/exec4543仅新E2E/helper/scratch，必须真正停API+真实UDS关闭+SIGKILL Supervisor+同DB恢复。网络作者最终8回归PASS7.17秒，Root已复核补上同网可达正例/跨bridge负例、真实none网络中途失败回滚；占位Gateway/coturn仅证明网络契约，正式Gateway由t006交付。Root已接管所有生产源，Runner/HTTP Gateway控制/资源decision/元数据恢复/单协调者锁当前仍集成中，旧fixtures缺新Gateway控制参数不能作为最新源通过。七AC仍全未勾、Verify/full review0，无执行commit/finish。

配置问题已告知用户：OpenCode edit白名单误拒绝已核日志，根因优先级尚未独立验证，不采纳作者早期猜测；goal授权下只在指定写域通过Python编辑，未改全局或模板。所有cache/TMP由父wrapper强制在code内；早期外部cache保留未删。

主干已集成t001–t004；本task仍attempt1/execution8c2fd5e26cdc49f4bd8008edecd1d36e/ownerroot_v2_t005_20261029，七AC未勾。Root接管Adapter/资源/凭证，核心作者仅core/runner/control/event/protocol及recovery测试。外部Agent主密钥派生profile+runtime作用域凭证；移除草稿dev-secret-token。统一数据根拒绝引擎/GeoIP外部路径和后代symlink逃逸，Runtime只读缓存；真实双Profile最新PASS25.06秒。临时helper先完成SDK缓存初始化，再只读交付Runtime。缓存初始化首两轮真实失败保留cache_actual.log/cache_network_green.log，不能用单测替代实际初始化；修helper等待/退出/清理后cache_green_v3.log通过。

真实Docker同名网络碰撞RED后增加精确所有权校验；查删错误传播，不再清理失败仍谎报端口释放。网络2项实际测试通过。CPU原先多输入状态有真实缺陷：host恢复、visibility保存、冷热容器压力聚合、counter重复/缺失/reset；新Root回归先红后绿。整体删除作者test_host_wide_overload_throttles_profile，因为Profile未注册时条件断言直接True且有未使用d2；新test_registered_profile_requires_two_host_pressure_windows从已注册Profile观察首窗不限制/第二窗限制，不修改旧业务输出迎合断言。路径/凭证/资源与实际网络26PASS0.45秒；新ResourceMonitor异步采样、串行policy组合/实例派发，实际0.5CPU容器负载→空闲与19单元20PASS11.25秒，尚无实际Stream降帧证明。Monitor是对已测算法的新增采集编排，直接用实际Docker验证，未编造RED记录。新增raw窗口JSON保存后需重跑。

核心recovery报告虽有真实SIGKILL/容器存活，但测试直接POST normal事件且Gateway不校验凭证，runner仅启动消费一次后await shutdown，因此不采纳为完整事件闭环。Root已补fixture作用域认证、允许根内物理缓存和images显式env；下一核心Round3需真实normal close、API离线持久重放、多Profile原端口恢复、持续协调、setup失败finally清理。PID11335/11506是失败用例泄漏的自有Supervisor，已核精确argv后TERM；未知服务不动。当前CLI PID11752，日志main/.scratch/v2_orchestration/t005_core_recovery_round3.jsonl，恢复先核终态。

执行边界缺陷已告知用户：旧核心uv进程用了~/.cache/uv，保留未擅删外部缓存；私有父包装器--env-root已强制所有后续子进程uv/pip/cache/TMP写code内，未改模板或全局配置。需求重试计数歧义已异步询问用户，未获答复前不改三失败计数、不宣称2/10/30全实测。正式Verify/full review仍0，AC007真实Stream与AC003实际Supervisor容器单Socket/无SQLite还需独立实测。

Root API内部配置/快照/绑定/观测/事件白名单路由复用既有规范handler，真实HTTP验证及导出OpenAPI深度一致性合跑3PASS4.76秒；schema已由scripts/export_openapi.py生成。新api/internal_supervisor.py和新HTTP测试Ruff E/F/W/I通过，app.py全文件仍有两项原有E501（原description/注释行），未顺手改动旧源码或关闭规则。

核心作者首轮terminal0（ses_e79dd4703ffe7lMlEknoXSms3l），4单元与1Docker对象/IPC配置探针通过，但HTTP为MockTransport、Browser状态允许created，不能证明真实Runtime ready/认证RPC/事件恢复。报告不采纳为AC通过；已同会话续行，要求真实API+真实Browser/Stream ready，接口采用Root内部前缀/Bearer而非旧公共路径。当前PID4654/exec45995，日志main/.scratch/v2_orchestration/t005_core_followup.jsonl。

资源作者首轮terminal0（ses_e79dd430bffepsQhMtOCJRaRmI），6单元/burner测试只证明有限窗口。Root发现未采真实host busy、无quota一核100%误当整机压力、min_measurement_interval未用、按Profile混合容器历史/重复counter、配置缺校验与共享前缀宽清理等实际缺口，首版报告精确数字缺原始JSON不采纳。已同会话续行补RED→GREEN及精确自有资源/不可变镜像/真实host作用域和机器证据，真实Stream降帧仍未证明。当前PID4192/exec92577，日志main/.scratch/v2_orchestration/t005_resource_followup.jsonl。

Root下一步审API客户端实际认证/事件字段映射与统一数据根；engine_cache当前草稿仍直接resolve外部路径，应确保所有mount位于允许统一数据根，不能由初始化配置绕过PathValidator。源所有权保持不交叉，正式Verify/review均0，七AC全未勾。

#### 2026-10-30T02:38:00+08:00 t005 内核隔离与异常恢复检查点

- branch=main，head_commit=978a53a（本次交接更新前）；t005 branch=t005_v2_supervisor、head=84f84311815bff330a51bcd35da150fc8b4990b3，attempt1/execution8c2fd5e26cdc49f4bd8008edecd1d36e/ownerroot_v2_t005_20261029。尚无执行commit/finish，七AC未勾、正式Verify/full review0，目标与固定后续队列不变。
- 已采用 Runtime 自有 netns IPv4/IPv6 filter + 业务启动 gate，不更改 OrbStack 全局设置。临时 helper 仅授 NET_ADMIN、无 Docker Socket；Browser/Stream 保持 UID1000、只读根、cap-drop ALL。原代理排除许可不再是实施前提，代理因果仍未证实。旧按来源过滤的应用负例已移除，普通 bridge 跨网可达事实保留为 d020。
- 定向实证：Supervisor12=sha256:805aff11a1b2e3d3f846a6fe9f19b4556a4bae11a54cf7adf96f6641f9fb09b5，无过滤网络组合7PASS13.46秒、命名空间黑盒3PASS26.80秒；IPv6 私有 echo 原宽泛 ICMPv6 规则先红，收窄邻居发现后绿，允许 TCP 仍 PONG，重复安装拒绝且原策略保留。公网 IPv6 GUA 未测，不能泛化。
- Supervisor13=sha256:aab6a25bb7c0c36c910c82895b8281469fa295fe30386edc4a214b084c030cfd，容器图 Round7 1PASS30.44秒：真实双 Profile 的 Browser/Stream 四种跨 Profile TCP 访问拒绝、目标 loopback 正例；Viewer ACK 后停止、旧停止重放不杀新实例、实际 SIGKILL 重启保持容器 ID/Browser PID/端口。源之后变化，13不是最终镜像，必须重建复验。
- 已移除未使用的本地 RetryPolicyManager 及仅测试该缓存的原型测试，API 仍为唯一失败计数/阻断权威。真实 HTTP 复现并修复旧手动操作重放绕过新阻断、bind 后端口耗尽遗留实例、旧本地会话覆盖 API 当前代际状态。资源采样/RPC故障按 Profile 隔离，不把不可采样当低负载。定向日志保留红绿，最新完整unit+integration为232PASS43.93秒（当时恢复作者仍修改，非冻结最终门禁）。
- 新启动锁内孤立 helper 清理已真实 Docker 红绿1PASS3.23秒，核 prefix/managed-by/角色/随机名称后只移除 cache-init/network-policy；Runtime/Gateway/非本方对象均保留，名称不符拒绝。只接启动阶段，周期扫描不调用。
- 当前唯一生产writer：OpenCode cpa/gemini-3.8-flash session ses_e77162b3cffeN67GwOZxxgVal7，续行PID72897/exec80334；独占 recovery_coordinator.py、新startup_recovery unit/E2E，自有scratch。原PID71093已SIGINT结束，原因是加入了明确禁止的Mock兼容getattr分支，已要求删除并直接使用Core真实接口。Root更新其余旧fixture输入，持有Core/Adapter/runner/其他文件。日志main/.scratch/v2_orchestration/t005_startup_recovery_corrected.jsonl；恢复先核实际PID与finish，不重复启动。
- 该writer闭环API已bind但Browser尚未创建即SIGKILL的恢复，以及Native正常退出首次POST503时优先于合成异常；Core提供has_native_exit提示，真实HTTP故障代理与Docker空扫描证明尚待结果。旧55415/58944/60597/63400/66325作者均terminal，Root已接管其文件。
- namespace作者曾漏--no-project生成uv.lock，已按JSONL命令/mtime确认后移入t005/.scratch/t005_api/generated_namespace_uv_lock_backup；不提交。自有历史namespace helper泄漏d176653eda66/c7a21f75b91c已按证据精确回收，未知pensive_satoshi与既有cbrowser未动。
- 最新日志已复制main/.scratch/v2_orchestration/t005_evidence_live/kernel_recovery_checkpoint，0700/0600与SHA256 manifest。下一步：完成startup recovery真实证明、重建当前Supervisor镜像、最终单元/HTTP/Host恢复/重试/CPU到Chrome/容器图门禁、文档spec、冻结后独立full review、单次执行commit及授权本地集成。公网/原生x86仅两项USER_WAIVED，容量/P95/8h/1000输入仍未测。

#### 2026-10-30T05:45:00+08:00 主控接管、AC 证据补强与冻结前全门禁

- Codex 会话额度耗尽停止后，由新主控核实无存活 CBrowser OpenCode/Codex 进程，`attempt claim --replace-owner root_v2_t005_20261029 --confirm-stopped` 接管，新 owner_id=claude_v2_14b38abc09f2；identity 仍 attempt1/execution8c2fd5e26cdc49f4bd8008edecd1d36e，strict preflight PASS。
- 证据缺口补强（只加强断言，未改既有预期）：容器图新增同 Profile 三路并发重复 start 返回同一实例与同一 Browser 容器、仅一对 Browser/Stream；两 Profile UDP 端口互异，Stream 实际 PortBindings 与容器内 `CBROWSER_UDP_MUX_PORT` 一致且 Browser 无端口发布；Browser/Stream 实际 RestartPolicy=no。资源监控真实容器 E2E 新增经 Supervisor 控制面 `/resources` 的 Bearer HTTP 查询，节流/恢复两次决策的 measurement_window_sec、timestamp、sample_count 与对应采样窗口一致，未认证 401。
- testing.md 命令修正：t005 改写的 contract 两行违反模板契约 `test_testing_md_default_commands_use_contract_marker`（主仓因 gitignored sync_state.json 跳过、worktree 内实际执行），恢复为模板规定的裸 `pytest` 形式；legacy 补 websockets；Stream 媒体用例因新 CPU 证明依赖 docker/httpx；OpenAPI 生成命令在 Python 3.14 需 `sqlalchemy[asyncio]`（greenlet）。导出结果与入库 schema 字节一致。
- 冻结前全门禁（`.scratch/t005_final/round1/`，Supervisor=sha256:9cfd93d9dbe3…，API fixture=sha256:2396ed5cffc5…，Gateway fixture=sha256:8e7946aea2e0…，均由当前源构建；Browser03=sha256:f2a8d42810c1…、Stream07=sha256:072e86762d2f…、coturn4.6.3=sha256:e2bca2f79a42…）：doctor PASS；contract 169 passed；legacy 384 passed；unit 211 passed；integration 21 passed；Runtime E2E 13 passed；Stream 媒体 12 passed（169.12 秒，CPU 证明 Chrome 2 秒帧 59→16→60，配额 None→8→None）；Supervisor 生命周期 6 passed（229.15 秒，含 SIGKILL、API 离线、2/10/30 重试与 failure_count=4）；启动恢复 2 passed；容器图/基础网络/归属/Browser 网络/缓存 8 passed，补端口断言后容器图复跑 1 passed；内核网络策略 5 passed；资源 5 passed；Supervisor schema 导出一致；Ruff E/F/W/I、md_format、git diff --check 通过；既有服务 health ok。
- round1 运行中曾在原地修改运行中的 bash 门禁脚本，导致 integration 步骤被重复执行一次（两次均 21 passed）；此后每轮复制脚本快照执行。contract/legacy/stream/OpenAPI 的修正命令单独补跑，日志 `*_fixed.log`。
- 七 AC 均按上述实际生产路径证据打勾；正式独立黑盒与 full review 尚未执行。公网 ICE 与原生 Linux x86_64 仅两项 USER_WAIVED；容量/P95/8 小时/1000 次输入属 t009，不在本 task 宣称。
