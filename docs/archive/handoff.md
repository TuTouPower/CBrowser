# 项目交接记录（归档）

历史交接记录按时间追加。

## 2026-10-26T23:30:00+08:00 architect → developer

- 当前焦点：根据 repo_template 与 CBrowser v2 架构重构目录、清理废弃原生代码、落地 4 个核心 spec 与运维蓝图
- branch：main
- head_commit：3269eeb
- 已完成：
    1. 彻底删除废弃原生桌面与旧包装代码（run-\*.sh/bat, app_entry.py, packaging, build_native, entrypoint.sh, 旧 RFB 测试）；
    2. 重组 backend/cbrowser（分层架构）与 frontend/src 现代模块化目录；
    3. 建立 4 项核心生效需求契约（browser_isolation, webrtc_remote_display, chrome_external_tabs, storage_and_artifacts）并登记入 specs_index.md；
    4. 重写 DOCKER_DEPLOYMENT.md 为 v2 容器网络、拓扑与备份恢复手册；
    5. 完善 docs/blueprint/\*（架构全貌、ADR 001-006、领域术语、约定）；
    6. 验证模板工具链状态与 contract 测试（168 passed）。
- 未完成：待启动各 spec 对应的拆解 task 进行代码级实现。
- 陷阱：遵守 AGENTS.md 读写规则与分区协议；严禁私自在操控页面添加多余虚拟外层标签栏。
- 下一步：针对 baseline specs 规划后续 task 批次并执行实施。

## 2026-10-30T02:38:00+08:00 v2 架构计划执行交接（Codex 主控时期，t001–t005 过程记录）

- branch：main；head_commit：02d26c3（迁档时）

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

### 2026-10-30T01:06:55+08:00 t005真实网络证据纠偏与启动竞态修复

- branch=main，head_commit=05c8a52f4badb46893154d360e1d8ff4320e94ba（本次交接更新前）；t005仍branch=t005_v2_supervisor、head=84f84311815bff330a51bcd35da150fc8b4990b3、attempt1/execution8c2fd5e26cdc49f4bd8008edecd1d36e/ownerroot_v2_t005_20261029。未执行commit/finish，七AC未勾，正式Verify/full review0；独立预审不充当正式review。
- 真实重试作者已terminal：三档Docker Created-API updated_at为3.04/11.59/31.21秒，真实Supervisor进程SIGKILL returncode=-9、换PID、failure_count4阻断、手动恢复/正常关闭，87.02秒PASS。Root后续发现并修复API非200仍合成exit、cleanup上限仅记录不执行、singleton路径跟随其他Profile；3项真实逻辑RED后相关14PASS2.52秒。控制HTTP错误不再回显/记录完整异常，敏感canary先红后8PASS0.72秒。该87秒结果早于上述修复，当前源重试E2E仍须复验。
- 容器图Round4新增Browser PID断言真实失败：旧runner_info/socket令替换实例提前ready；Root补profile/instance/config_version/PID核对，相关16PASS2.31秒。当前整镜像Supervisor10=sha256:51075e9c19990b8d247fae63f5ee25eb8330d36f002652354056b84230f447a6，API03=b53bca10263588b8c364b697984c69630d239573ab8b1a70c28782756c50c785，Gateway02=dac21afe70d77cab6e55c2dfbb10d41f1785e5cf55cdc0c30466b3fc483ebf28；加强后的容器图Round5 PASS25.37秒（container_graph_round5.log），无源码overlay。新增导出脚本同步Supervisor JSON schema，stop两种fence必需；schema检查1PASS。
- **网络隔离证据纠正，不能略过**：Root发现旧RUNTIME_SERVER_SCRIPT主动过滤gateway来源，先前“普通bridge隔离已证明”结论无效。独立无过滤server同网/跨网均PONG；internal=True对照同网成功、跨网ENETUNREACH。已经工具创建d020_orbstack_bridge_reachability.md，当前AC-001/006网络部分未通过。普通bridge不能当强隔离；internal对照不能证明Browser上网与媒体都满足。透明代理是待证假设，不写成根因。
- 用户授权问题已通过异步问题发出，尚未收到答案：只临时把新测试网段198.19.254.0/24加入OrbStack network.proxy.exclude，实验后恢复原值空。原network_proxy=auto，macOS HTTP/HTTPS/SOCKS启用；该网段与现有Docker IPAM无重叠。方案.scratch/t005_api/proxy_exclusion_proposal.md，尚未写任何OrbStack设置。仓库外写入须明确授权，不因goal自动放宽。官方资料https://docs.orbstack.dev/docker/network#proxies；ego任务space0已正常finish，不复用已结束space。
- **当前两个验证lane及一个测试writer**：测试配置作者PID55415/exec62939/session ses_e7819b695ffeNbrwEZ2hzQaFsj，仅owned_files.json新测试/fixture及retry E2E，日志main/.scratch/v2_orchestration/t005_test_config.jsonl；Root不改其文件。独立源码预审PID58944/exec10629/session ses_e77666b69ffe3WdRC251TK9O4v，仅validation/.scratch/t005_pre_audit报告/实验，已给冻结生产副本；真实namespace网络策略研究PID60597/exec52723/session ses_e776180a5ffeJysDs9jL57L3hM，仅validation/.scratch/t005_net_policy，自有t005-nsp资源，不许host namespace/Socket/全局设置。恢复先核PID和最终stop，不因观察超时重启。
- 最新门禁未全绿：17真实HTTP PASS33.47秒；unit_checkpoint_3为192PASS/1FAIL（MockDockerAdapter仍写旧位置/缺代际runner_info导致严格ready超时，测试writer正在核fixture；不可把200预期改500制造绿）。全组合full_checkpoint_2为205PASS/1FAIL，后者是cleanup测试脆弱RPC响应序列，Root仅改按路径供响应的fixture，保留断言。当前生产Root Ruff E/F/W/I通过；全部最终门禁还未运行。旧uv.lock核明由恢复作者漏--no-project命令生成，已移.scratch/t005_recovery/generated_uv_lock_backup，未提交/删除用户资产。
- 自有泄漏be981097b0b4已由旧network_finalization JSONL精确确认是t005-net-9e0a2e91失败前登记异常遗留，核labels/无网络后仅删除此ID。未知pensive_satoshi42bbb06167ec与既有cbrowser/其他服务均未动。网络/竞态/重试证据已复制main/.scratch/v2_orchestration/t005_evidence_live/network_readiness_checkpoint，含SHA256 manifest，0700/0600。
- 下步：真实隔离修复及无过滤正负复验、当前重试/离线E2E重跑、预审处置、全门禁及最终文档/spec、冻结后正式独立review与一个执行commit。后续固定队列不变；公网/原生x86仅两项USER_WAIVED，容量/P95/8h/1000输入均仍未测。

### 2026-10-29T21:45:37+08:00 t005恢复接线与容器拓扑检查点

- 当前t005仍attempt1/execution8c2fd5e26cdc49f4bd8008edecd1d36e/ownerroot_v2_t005_20261029，branch=t005_v2_supervisor，head_commit=84f84311815bff330a51bcd35da150fc8b4990b3；尚无执行commit/finish，七AC未勾、正式Verify/full review0。此前恢复入口中的PID27347与candidate_02均已过时。

- 独立真实API离线黑盒已PASS39.35秒：实际停止API、UDS正常关闭、事件落盘、Supervisor SIGKILL、同DB恢复及无误重启；公共Gateway fixture改为Bearer鉴权和实例fence，三个host E2E与相关unit共8PASS136.13秒。fixture不代表t006正式Gateway完成。

- 新Supervisor容器+独立API/Gateway/coturn+双Profile完整拓扑PASS21.79秒（.scratch/t005_api/container_graph_round3.log）：仅Supervisor挂Docker Socket、无SQLite/SQLAlchemy，Browser独立egress网络、Stream仅媒体网络，实际infra IP下发，Viewer关闭握手先于Runtime删除、旧stop重放不杀新实例，Supervisor实际SIGKILL后恢复。该PASS使用Supervisor06=sha256:76ed6bb2733533fa52a84f9c39c93b47a979d3b3b7222cfabb2c1079c19415ec；之后源已变，且新增Browser PID/容器ID不变断言，必须重建重跑，不能冒充当前候选PASS。冷启动API fixture需sqlalchemy[asyncio]补greenlet；正式交付依赖检查留t012。

- 按明确架构计划“异常后自动重试三次2/10/30”收敛为首次异常+三次重试，failure_count记录异常总数4时阻断；不再等待旧计数问题答复。共享domain/runtime_policy用于API与Supervisor，无DB结构迁移。新真实SQLite四项生命周期语义+调度测试5PASS0.89秒，相关repo/core回归25PASS1.91秒。旧test_runtime_events_convergence_and_exit_contract及test_retry_policy_three_strikes整体删除，分别由新正常/异常/迟到/重放/heartbeat属性覆盖，未就地改旧预期制造绿。

- Root补原子快照/派生凭证写入（替换symlink而非跟随）、Profile目录别名和跨Profile特殊挂载拒绝，13PASS0.56秒；事件journal路径与内部profile/instance须一致，4PASS0.43秒。API无本地session状态改读权威running意愿，真实HTTP先RED后1PASS2.12秒。

- 恢复协调器首稿close锁死锁与快照RPC失败猜配置均由Root真实RED复现；作者修复后Root复验10PASS0.38秒。Runner已接tick/close。旧retry E2E只重建同进程对象，不能证明SIGKILL，已退回改真实subprocess及Docker创建时间/持久due证据，2/10/30实际时间仍未通过。

- 当前唯一生产writer为OpenCode恢复作者session ses_e78331402ffedLVqPXYz1O9UBW、PID41557/exec99923，独占recovery_coordinator.py、新retry E2E、新coordinator单元；日志main/.scratch/v2_orchestration/t005_recovery_actual_process.jsonl。另测试格式作者PID41730/exec17547独占其owned_files.json枚举的新test/fixture，日志t005_test_lint.jsonl；Root不触及上述写域。恢复前核PID及JSONL最终stop，不重复启动。Root拥有其余生产/文档。

- 下一步：真实重试黑盒闭环、当前源镜像重建及加强容器拓扑复验、完整门禁/文档/schema、冻结候选后独立full review；再按原队列t006→t007→t008→t013→t014→t009→t010→t011→t012继续。公网ICE与原生x86仅两项USER_WAIVED；容量/P95/8h/1000输入均未测，不宣称通过。

- **2026-10-29T19:55:18+08:00 t005真实CPU媒体子阶段完成**：实际Stream CPU配额压力经生产ResourceMonitor触发8FPS，官方Chrome 2秒解码 **60→16→56帧**，负载/配额恢复后解除限制。完整t004媒体用例含原三代TURN/IME等断言 **PASS107.48秒**；t005/.scratch/t005_api/stream_cpu_v6.log与其basetemp下supervisor_cpu_stream_proof.json保存5个精确raw窗口及派发记录。该证明当前为生产采样器→fixture Gateway WS→真实Stream/Chrome，不能充当Supervisor容器/Gateway HTTP全部接入完成；Root已开始服务接入但尚待完整重验。Docker SDK动态update不支持nano_cpus，真实用例改CFS；生产采样识别NanoCpus/CpuQuota+Period/CpusetCpus最紧实际预算，20单元通过。

- **fresh缓存单次初始化闭环**：无pin SDK ensure_binary会启动后台更新线程，fresh cache短helper退出139；精确原生崩溃栈未取得，线程与崩溃因果尚属推断，不能夸称native根因完全确认。初始化改为SDK平台get_chromium_version显式pin，与Runtime固定引擎一致；fresh私有诊断139→0，正式单次helper/GeoIP与相关RPC/资源/端口合跑 **25PASS2.05秒**（pinned_cache_formal.log）。Core作者添加“initializer失败再试一次”已被Root整体移除，不用重试掩盖失败。候选Supervisor镜像首版 **sha256:91d6d86e4592c5d8d67e01ff3d935ca70fdc1d8c698ab94c2ee57bf48e090b75** 构建/只读无网导入通过，无SQLAlchemy；之后Runner/事件/控制面已变，首版不能代表当前源。candidate_02正在构建，先读supervisor_image_build_02.log并inspect实际ID。Dockerfile专属ignore只传必要源码，未把.env/数据/缓存送入context。

- **Root新安全红绿**：事件ID路径穿越与旧实例normal事件误移除新本地session真实复现后修复；队列用哈希文件名、file+directory fsync，送达ACK日志跨进程恢复，避免每轮重传全Native Journal。原MockTransport测试绑定evt_1.json内部文件名已整体删除，新实际TCP listener离线/恢复、ACK重启与instance边界测试替代，相关6PASS0.50秒；控制面空/短key改为启动失败，auth+事件6PASS0.62秒。新增真实进程flock与SIGKILL释放2PASS0.04秒，Runner已串接控制目录锁；手动retry复用API受限PATCH runtime/desired-state及幂等操作记录，真实HTTP3PASS4.83秒，OpenAPI已重新导出。同一手动操作重放不能清掉后续新failure，不擅改待确认的三失败计数。

- **最新作者/所有权**：旧core Round3 PID11752已由Root核PID后SIGINT（出现缓存再试的掩盖实现），Round4 **PID16510/exec54151已terminal0stop**，报告t005/.scratch/t005_core/report_recovery.md。其4 E2E83.57秒含真实UDS close、双Profile SIGKILL端口恢复，但“offline”用例实际手写spool且未断API，不采纳离线恢复AC。网络作者 **session ses_e7973be5cffee9LsPRSPYw4gC3**（14210暂停、15757续行、27172最终复核）均terminal；补同网0.0.0.0正例/跨bridge负例、真实network_mode=none中途失败回滚，8实际/路径回归PASS7.17秒，报告.scratch/t005_network/report.md，Root已接管Adapter。Root独占全部生产源；唯一仍运行作者是 **offline PID27347/exec4543/title t005-real-api-offline-blackbox-20261029**，仅新test_supervisor_offline_recovery_e2e.py与offline_fixture.py及自身scratch，日志main/.scratch/v2_orchestration/t005_offline_blackbox.jsonl；恢复先核PID和最终stop，不重复启动。

- **下一步必须处理当前服务集成断点**：Root已给Runner配置必需Gateway control URL/外部key文件，Core的disconnect/quota不再空日志，周期ResourceMonitor与可查询decision已接入，API意愿/失败状态从真实RPC读取，普通启动不立即抹掉失败历史；旧host Gateway fixtures尚需补control HTTP endpoints和CLI新参数，否则旧E2E不能当当前源PASS。服务shutdown已改监测任一task异常/有界取消，不杀健康Runtime。真正Supervisor容器单Socket/无SQLite、多Profile共享infra动态接入实际Core路径、并发幂等stop及异常2/10/30仍未闭环。Root最新root_security_checkpoint.log需核结果；正式Verify/full review均0、七AC仍未勾、没有执行commit/finish，完整目标与固定后续队列不变。

- OpenCode edit绝对路径白名单误拦截已核原始工具拒绝日志，已告知用户；子任务按既有goal授权仅在写域内用Python完成，未改全局配置/模板。报告早期“deny优先级根因”未独立验证，已纠正为仅事实；私有bash的宽glob也有误触风险，后续修私有permission时需同时考虑相对路径、避免整段脚本误判，不把限制绕过当业务证明。

- **2026-10-29T15:13:48+08:00 t005安全与采样子阶段检查点**：Root已接管Adapter/path/port/resource及Agent凭证，production不再有dev-secret-token；外部Agent主密钥派生profile+runtime作用域HMAC，独立于API凭证。真实双Profile认证用例先PASS25.96秒，缓存约束修改后最新 **PASS25.06秒**（t005/.scratch/t005_api/cache_green_v3.log）：预置引擎/GeoIP物理复制到允许数据根内，所有bind源实际inspect均在根内，Browser缓存/GeoIP只读。缓存初始化由临时helper完成再交Runtime；首两轮失败日志保留，不将旧PASS冒充最新全门禁。

- 网络所有权实测：原同名网络会被直接复用/删除；新增实际Docker碰撞用例RED，改精确名称+managed-by/profile/prefix标签校验后2PASS。清理/扫描失败现在传播，不能吞错后回收端口；cache-init排除Runtime扫描。Root资源TDD修复host恢复不解限、前后台状态丢失、冷热容器互相覆盖、重复/缺失counter假窗口及counter重置假恢复。最新路径/凭证/资源单元+实际网络 **26PASS0.45秒**；独立实际NanoCpus采样1PASS3.73秒；ResourceMonitor异步采集、串行组合/实例派发与实际0.5CPU负载→空闲，加19资源单元 **20PASS11.25秒**。尚未接正式Gateway控制面/实际Stream降帧，AC007未通过；raw测量JSON持久化刚补，需重验新版本。

- **仅核心Round3作者当前活跃**：原core followup4654与recovery9212均已terminal；最新 **OpenCode PID11752/exec97786/session ses_e79dd4703ffe7lMlEknoXSms3l**，日志main/.scratch/v2_orchestration/t005_core_recovery_round3.jsonl。先核PID/最终stop再恢复，不能因观察超时重复启动。写域core/runner/control/event/retry/protocol与专属recovery测试/Dockerfile；Root独占Adapter/resource/AgentCredentials/API/原core_e2e。资源作者4192已terminal，Root接管其文件。上轮SIGKILL测试真实存活/重建通过，但正常退出直接POST、Gateway未鉴权且runner无持续循环，不能证明完整AC004；Root已补测试凭证/数据根，要求作者真实Chrome关闭、API离线持续重放、多Profile原端口恢复、全程finally和单协调者锁。两次失败泄漏自有Supervisor PID11335/11506已核argv后TERM；不动未知/既有容器。

- 执行边界问题已告知用户：核心旧子进程未遵守指定UV缓存，实际使用~/.cache/uv；外部缓存保留未删。私有OpenCode父包装器新增--env-root，强制uv/pip/python缓存、TMP/TEMP和禁写字节码均在code内，后续调用已使用；未改模板/全局配置。重试语义异步问题仍待答复：首次异常后完整2/10/30三次重试，或首次异常计入三失败而只两次重试；依赖计数暂不擅改，不声称30秒已实测。七AC仍未勾、Verify/full review0、无执行commit，原固定后续队列继续。

- **2026-10-29T13:51:52+08:00 t005 API白名单与子域复核阶段**：Root在登记t005 WT完成内部配置/快照/绑定/观测/事件受限路由，统一前缀 **/api/v1/internal/supervisor**、**Authorization Bearer外部文件token**，复用t002规范handler/事务，不授予Profile CRUD。真实HTTP与OpenAPI一致性合跑 **3PASS4.76秒**，导出schema已更新；新API模块/新HTTP测试Ruff通过，app.py两项原有E501未顺手修改。重放相同事件不能取消后续新的running意愿。Root接口真相文件main/.scratch/t005_preparation/root_api_contract.md，core_contract首稿旧公共路径/X-header与ignored_duplicate枚举不能直接当正式接口。

- **首轮作者已terminal，现为同会话续行，不能按旧PID恢复**：core首轮session **ses_e79dd4703ffe7lMlEknoXSms3l**/99949已terminal0stop；4unit+1Docker探针只有对象/IPC配置，API是MockTransport且created也计通过，Root不采纳为真实Runtime验收。已续行 **exec45995/PID4654**，log t005_core_followup.jsonl，要求真实uvicorn API与Browser/Stream ready/认证注册、停止/恢复，不能改弱断言。resource首轮session **ses_e79dd430bffepsQhMtOCJRaRmI**/99965已terminal0stop，6项burner/单测不证明真实Stream限帧；Root发现host busy缺失、无配额一核误归整机压力、采样窗口未实施/重复与跨容器counter等缺口，已续行 **exec92577/PID4192**，log t005_resource_followup.jsonl，补真实host/配额/窗口与机器JSON、精确自有清理/不可变镜像。初报精确数值缺原始JSON暂不采纳。两个续行仍需核实际PID/JSONL，观察超时不可重复启动。

- 当前t005仍 **attempt1/execution8c2fd5e26cdc49f4bd8008edecd1d36e/ownerroot_v2_t005_20261029**，WT/branch/base不变，strict preflight PASS；七AC全未勾、正式Verify/full review均0，未commit/finish。Root下步审真实API认证映射、统一数据根（草稿engine_cache外部resolve不能绕路径校验）、GeoIP与Runtime ready/事件重启闭环，再整合真实CPU到Stream降帧。完整目标保持active，t005后继续原队列。

- **2026-10-29T13:34:59+08:00 t005首批实现恢复点**：core PID99949与resource PID99965仍活跃（各自20分钟首批检查点，不因观察超时重启）。两方接口稿已落.scratch/t005\_{core,resource}/{core,resource}_contract.md；核心已落path_validator/port_allocator/retry_policy/event_forwarder/docker_adapter/protocol等源码，CPU作者已落resource_policy与单元/真实Docker资源测试，但尚未由Root复核通过。Root已在t005 WT完成api/internal_supervisor.py与api/app.py内部认证首批TDD：真实HTTP先404 RED，再外部文件凭证/Bearer常量时间校验GREEN，**1PASS2.11秒**，日志.scratch/t005_api/auth_{red,green}.log；未经授权/错误凭证401，正确凭证200、不回显。Root新测试fixture setup也在finally精确回收。尚无完整生命周期/事件RPC通过，需统一core接口稿中的旧公共API路径与认证内部RPC，OpenAPI待路由稳定统一生成；七AC仍未勾，正式Verify/full review均0。禁止据源码文件存在或burner采样宣称AC通过；t005一个执行commit尚未创建。

- **2026-10-29T13:30:32+08:00 t003/t004集成阶段完成**：t004单执行commit **f0cbd452b9cf5c1bdc45ae220a11c6573f13be21**，first-parent为t003执行8ff9fd2；done/terminal completed/report done/exact cleanup全部完成。t003与t004链尾通过原生Git门禁合入main，merge **84f84311815bff330a51bcd35da150fc8b4990b3**，原t003/t004分支已由脚本删除，旧worktree已清理。正式Full Round1 code/test PASS，scope740fe6627e7735db，3minor关联t009/t012；报告原时间/引用及shell转义损坏均已由作者勘误恢复，未改生产源。

- **main合并后全门禁PASS**：doctor、169contract、384legacy、120unit、9HTTP、**13实际Runtime E2E/167.97秒**、**12实际Stream E2E/151.56秒**；既有服务health仍ok。原t003隐藏scratch音频依赖已在worktree清理后的main真实复验关闭。日志与稳定可读解释器保留main/.scratch/t004_integration_gates/；project_venv/media_venv是原已验证依赖环境的硬链接副本，prefix已核，不依赖被清理路径。首轮HTTP因继承SOCKS代理且缺socksio在初始化失败，按流程merge abort后重新准备；只清本机测试进程代理变量重验，前后merge tree同为6bc7644285dde28cba3e0e5f119231c3c9d4c3a4，失败日志保留。该次失败留下的9个自有API子进程已核精确路径/PID后SIGTERM回收，未动其他服务；旧fixture setup异常清理缺口由后续t009测试整理时处理。

- **当前t005已开工且strict preflight PASS**：worktree **/Users/karson/kar/code/CBrowser_t005**，branch=t005_v2_supervisor，base/diff_anchor=84f84311815bff330a51bcd35da150fc8b4990b3；**attempt1/execution_id=8c2fd5e26cdc49f4bd8008edecd1d36e/owner_id=root_v2_t005_20261029**。已reserve/claim，不重复start或reserve。task上下文已替换过时t001 active/通用UNVERIFIED-SPIKE为已验证002/003/004契约；认证RPC与CPU策略是本task自有实现，七AC尚全未勾。只读新validation WT=main/.scratch/v2_orchestration/t005_validation，branch=spike/t005_validation。

- **两个指定模型作者并行，写域互斥**：core wrapper42591/PID99949/session ses_e79dd4703ffe7lMlEknoXSms3l，仅Supervisor核心包（排除resource_policy.py）、supervisor Dockerfile/协议及专属core测试；resource wrapper77898/PID99965/session ses_e79dd430bffepsQhMtOCJRaRmI，仅resource_policy.py及专属resource测试。日志main/.scratch/v2_orchestration/t005\_{core,resource}\_implementation.jsonl。Root独占API内部RPC适配、API应用注册/OpenAPI、公共文档/Task/索引。作者先落core_contract.md/resource_contract.md并继续TDD/真实Docker，不将fixture或burner采样当全AC通过；20分钟首批可运行检查点。Root接下来收敛两接口并实现真实API侧RPC。禁止读.env软链、禁止改既有cbrowser/全局代理，写域仅~/kar/code。Docker资源再次实测10CPU/16819609600bytes，未扩大配额。

- 固定后续队列仍为 **t005→t006→t007→t008→t013→t014→t009→t010→t011→t012**。部署/性能/压力与最终旧链路移除都尚未完成，目标保持active；每完成阶段继续更新handoff。公网与原生x86执行仅两项USER_WAIVED，支持保留；其他验收不能缩减。

- **2026-10-29T10:07:00+08:00 正式三代Chrome TURN/项目门禁阶段完成，进入Full Round1**：正式chrome_relay.py已入库路径，三代gen2/3/4精确commit和旧代closed+sendreject后，才核新ufrag双relay/重新采样帧、音频、pair字节/同PC、DTLS、Track，保留全部复制标签/策略/IME/隔离断言。计划固定coturn4.6-alpine拉取为arm64实际4.6.3、ID **sha256:e2bca2f79a4269d7240de5872ab60a9305013ad37296d2acf14f9510874346be**；首次因旧版loopback+空CLI密码启动拒绝，隔离fixture补no-cli后完整 **PASS96.13秒**。当前镜像07其余11项真实E2E **PASS52.10秒**；9个Stream源SHA与07逐文件一致。无生产源码变更，不借4.18测试替代计划固定版本。

- 指定模型独立真实matrix session **ses_e7a9f67c6ffeEXhpqZCBKERrEW** 已terminal0/持久stop（观察器durable=false自然race已核最终JSONL）。冻结候选51文件SHA全部不变：正例完整 **PASS96.58秒**；server错误HMAC真实401/无freshOffer **预期exit1/47.41秒**，client错误HMAC真实401/无新代commit **预期exit1/65.26秒**。原connected/旧媒体不使负例假绿。报告metadata的Darwin24.x未经核实不采纳；核心JSON、401日志已Root复核。证据validation/.scratch/t004_relay_independent/；完整source/正式量具/独立proof已追加保护到main/.scratch/v2_orchestration/t004_evidence_live/，manifest含SHA，避免cleanup丢失。

- **项目门禁全PASS**：169contract、384legacy、120unit、9实际HTTP，t004/.scratch/t004_project_gates/results.json。全部新Stream源/测试Ruff E/F/W/I通过；新增schema导出与nullable注册/ACK/tunnel契约测试通过。蓝图stream_runtime、webrtc_remote_display、testing、验证指南/specs_index已更新，d019记录真实TURN映射与版本边界。六AC已按实证打勾，task仍active，未执行finish/commit/cleanup/集成。

- **下一步正式独立Full Round1/5**：两路OpenCode均只写各自review报告和自有scratch。code wrapper52743/PID86136/title t004-final-full-code-round1-20261029；test wrapper39548/PID86155/title t004-final-full-test-round1-20261029。日志main/.scratch/v2_orchestration/t004_final\_{code,test}\_review_r1.jsonl；审查scope **740fe6627e7735db**，覆盖当前全部交付。Root冻结源码，待报告复核/处置和checker；不得直接跳到done。后续一个执行commit、exact cleanup及已授权t003→t004链尾集成，再继续固定队列。P95/首帧/容量/8h/1000输入仍未实测，未豁免。

- **2026-10-29T09:54:00+08:00 复制标签真实媒体阶段完成**：独立OpenCode指定模型会话ses_e7aae040fffe4e87xAIEhzHtjm已terminal，冻结candidate完整真实E2E PASS86.25秒，Chrome原生window.open确实复制sessionStorage（无手工适配），新页自动独立ID并解码1920×1080；原两Peer引用/PC数量不变且音视频增长，关闭新页后恢复2viewer。Root已移入正式tests/e2e/test_stream_runtime_e2e.py，删除未使用的手工存储回退，完整正式复跑 **1PASS84.58秒**（镜像07），后续策略/8IME/剪贴板/刷新/独立静音/Agent重连与Stream暂停断言均保留。日志t004/.scratch/t004_root_checks/full_duplicate_policy_media.log，独立证据validation/.scratch/t004_duplicate_media/retained_evidence/。

- **TURN首轮403已定位测试地址映射并通过三次实际提交诊断**：补coturn原始日志复现403；将relay-ip从0.0.0.0改为真实容器172.30.0.10，并明确external-ip=127.0.0.1/172.30.0.10后同镜像07无生产源修改成功。Root新诊断连续generation2/3/4均出现精确commit+旧代closed/rejected，随后Chrome选中local/remote均relay、新ufrag匹配、真实视频帧/音频能量增长，同PC/DTLS/Track不变。证据t004/.scratch/t004_ice_media_gateway_diagnostic/run/28843ea0/relay_generations.json与root_relay_generations.log。只是诊断，尚须入库正式ICE量具、独立复验及单侧失效；不把首次commit瞬间旧stats算通过。旧报告所谓no-ip-check并非实际选项，未采纳。

- **schema同步阶段**：新增scripts/export_stream_protocol.py，从实际四种Pydantic wire envelope生成2020-12 schema，覆盖nullable注册/ACK/tunnel/control；两个契约测试PASS1.39秒。尚需相关门禁/Ruff收尾与协议边界文档；六AC未勾，正式Verify/full review仍0。Root仍独占生产源，当前无活跃OpenCode作者。

- **2026-10-29T09:39:10+08:00 完成帧率仲裁、隔离与真实Peer查找阶段**：当前源镜像 **sha256:072e86762d2f1810e86a2d20169d4be451b5a19e0ebabc880e882de63ac0d531**（cbrowser-t004-root-peer:20261029_07）。Native适配定向审查68638已terminal0/持久finish=stop，发现DISPLAY KeyError与全部spare按住仍可重绑；Root两项均先真实RED后修复：缺DISPLAY转安全RuntimeError，prebind先保护真实pressed槽和当前batch已绑定槽、无容量即拒绝；Xvfb真实按住全部槽不再被覆盖。相关 **47单元PASS0.72秒**；镜像06的XKB/ICE失败回收/三代Native DC relay/Chrome身份/完整媒体合跑 **12PASS100.83秒**（不是Chrome三代TURN）。

- Root新增真实Agent WS断线后新session重新注册、暂停整个自有Stream容器时Browser动画仍递增且PID/start_ticks不变，完整媒体 **PASS48.53秒**。AC003旧研究70222在15分钟未执行后由Root核PID中断，随后Root给具体focus并续行18927/PID75741/session ses_e7aec05d9ffel5yrQL5P0efRak，已terminal0/持久finish=stop：当前镜像06真实Gateway包→Native setter→两Chrome媒体 **PASS47.54秒**，cap15=30帧/2秒、解除=60帧/2秒，一连接hidden仍60帧/2秒、allhidden0、恢复收到新关键帧，Browser PID不变。报告对未知tab排序和底层捕获计数不能泛化，Root后续正式用例已改按HELLO tab_id映射、双页停增校验。

- **正式入库用例已覆盖真实客户端越权与隔离**：Root把策略阶段移入tests/e2e/test_stream_runtime_e2e.py，实际input DataChannel尝试_arg_fps,30与r,640,480不能突破cap15；两个外部viewport改640×480/1600×900后远端仍1920×1080；按真实TabID隐藏Page1时Page2继续、两页全隐藏都停增、未知viewer不得恢复、恢复先8+新关键帧。随后仍完成8IME/124字、剪贴板、刷新/静音/关闭/输入与Agent重连/Stream暂停。另将旧\_\_pcs[0]自比较改为实际connected PC引用+总数检查。当前镜像07该完整正式E2E **1PASS73.83秒**，日志full_capture_policy_and_media.log。正式Verify/full review仍0，AC暂未勾。

- **SDK真实字段错误已修**：诊断13193/PID72927/session ses_e7ae00ad7ffetpJTnWAeC6rI0n只做SDK源+MagicMock复现，不能当多Peer黑盒；Root实际两Chrome向生产Agent发ICE控制，镜像06为action=error **FAIL25.90秒**。真实SDK RTCApp metadata键是peer_conn；Root仅改精确读取，无pc兼容，整体删除伪造pc键的旧单元用例并记录理由、保留/新增严格错误形状拒绝测试。镜像07两个真实Peer均生成Offer **PASS26.41秒**（只证明准备/查找，不是完成ICE或relay）；47相关单元通过。证据native_peer_lookup_chrome_red2.log/green.log与peer_lookup_proof.json。

- 新发现按脚本创建 **d017_native_xkb_named_spares、d018_selkies_native_peer_entry**，并补d014边界。核心证据32文件已复制到**main/.scratch/v2_orchestration/t004_evidence_live/**（目录0700、文件0600、manifest含SHA），避免task cleanup后消失；完整独立Native双轮证据仍在validation WT，不依赖t004 scratch运行。

- **下一步仅推进剩余真实场景，不宣称整task完成**：TURN续行43977/PID77403同session已terminal0/持久finish=stop，真实新offer/Chrome同PC答复及两端TURN allocation成功，但CHANNEL_BIND **403**、generation2无officially committed，因此零relay轮换通过。原报告建议重新加allow-loopback-peers/使用no-ip-check不采纳：Root核脚本已含allow-loopback-peers，实际coturn4.18 --help无no-ip-check；须查真实TURN日志/路由，不盲加未知选项。脚本.scratch/t004_ice_media_gateway_diagnostic/run_relay_diag.py与report_relay_replay.md保留，端口18961/18962/30961、TURN34861/42100–42140；所有CLI目前terminal，Root独占生产源。仍需真实复制标签媒体不误踢、三代Chrome relay及d012代栅栏、入库正式ICE量具、schema同步（现JSON未表达实际nullable/多种v2 envelope）、完整项目门禁/正式独立Verify/full review/一个执行commit/cleanup/链尾集成。

- **执行失误已告知用户**：首次Root ICE焦点漏mkdir TMPDIR，pytest回退写入 **/private/tmp/pytest-of-karson/pytest-0/test_gateway_ice_lookup_focus0/**，随后Chrome mkdtemp失败，该次不作ICE证据；自有测试容器已清理，外部目录保留未动。以后预建本lane tmp并显式--basetemp、cache_dir在code内，禁止未经授权清外部目录。原失败日志native_peer_lookup_chrome_red.log保留。

- **2026-10-29T08:37:27+08:00 原生多字中文/媒体阶段完成并获独立复验**：确定性错序真实根因不是等待不足，而是Native spare池含无XKB名称槽，xkbcomp序列化为重复key \<>并合并；19原始绑定前正确后损坏，只排除8仍损93。按实际xkbcomp keycodes非空名字过滤后17绑定前后全一致，保留preferred语义、evdev按有限容量分批；删除无效额外50ms等待/私有deadline，保留原SDK25ms settle于真实map替换后。生产修改仅Stream x11_keymap.py与x11-xkb-utils，未动Browser03。Root源镜像f1b136a1ff3a...真实双GoogleChrome扩大8次跨页提交124字、剪贴板不变、固定1920×1080双音视频增长、实际UDP候选、刷新/独立静音/关闭/生存页输入、Browser PID/start_ticks不变 **1PASS45.60秒**；真实Xvfb5轮17键位复用 **1PASS1.18秒**。证据t004/.scratch/t004_root_checks/keymap_named_complete_proof/与native_prebind_probe/，并保留此前各失败，不据此宣称P95/1000/8h。

- 当前完整公共基镜像 **sha256:a9fc26cf5d6d4d828dc9d5978d442e386ff48e8e940b39c9320b358a5087f1df**（tag cbrowser-t004-root-keymap:20261029_05），相对f1仅清除入口尾空行；9个Stream package源SHA全部与当前源一致（keymap_clean_image_source_provenance.json），x11_keymap SHA=5e106f99de12b69a7112eb7e32ceb1c54108e2aad2b7ed7bbb1fc96734eeb264。新增31交付文件已explicit git add -N，未提交实现。Root相关46单元/Ruff通过，新增XKB测试与媒体测试已格式化/移除未用读取并通过Ruff E/F/W/I、git diff --check。

- 独立冻结黑盒91434/PID68621/session ses_e7aefd9f2ffeiVy0p1S7wlP5zP已terminal0/JSONL持久finish=stop（wrapper自然退出race durable=false不等于未完成）。在独立validation WT仅替SDK18521/GW18522/UDP30521/资源前缀，无断言变化，candidate全部SHA复核未变；当前a9fc整镜像连续 **2PASS47.69秒+2PASS46.25秒**，均全新Profile。两轮8IME/剪贴板/刷新/PID与双remote candidate127.0.0.1:30521/UDP真实JSON一致，证据固化validation/.scratch/t004_keymap_frozen_blackbox/retained_evidence/run{1,2}/。原报告将续流Page2数字接到Page1、将纯map一致性称按键释放，Root在root_qualification.md勘误；不扩大为完整六AC或held-modifier/无丢帧证明。

- 最新定向源review35722/PID68638/session ses_e7aefd590ffeZYahXV1ndYwSDM仍活跃，仅validation/.scratch/t004_keymap_scoped_review_final读冻结Native适配，尚无结论；旧57233的PASS已被新修复/Root限定取代，不能复用。新AC003真实认证Gateway+捕获仲裁诊断9195/PID70222（log t004_policy_gateway_diagnostic.jsonl）仅t004/.scratch/t004_policy_gateway_diagnostic写自有候选，使用SDK18361/GW18362/UDP30361+Browser03+a9fc完整Stream，禁止生产源改动。Root持有全部生产源，接下来闭环策略/三代Chrome TURN/失联与暂停隔离。六AC当前仍全未勾、正式Verify/review均0，不重复start/reserve，t003→t004未集成。

- **2026-10-29T08:15:13+08:00 队列溢出回收阶段完成**：新增真实协调器测试先FAIL（worker已删但Gateway没close），修复后6项身份/回收单元PASS，全组六文件 **46PASS0.79秒**，Ruff E/F/W/I通过。关闭消息含当前v2 profile/instance/session与1013，bounded send。最新生产源候选镜像 **41a7f0f90556afd7fdf974598fc39d4e63356b46ce56b294733af2eaf27c97de**，public Python/Debian基底，未改Browser03。前一完整源镜像38c86e...的8实际ICE失败/取消/关闭、3代Native TURN机制及Chrome身份回归共 **10PASS50.39秒**（keymap_source_ice_identity.log）；不是3代Chrome媒体通过，源后改必须最终复验。

- **中文扩大验收尚FAIL，不能凭短文本绿收尾**：新加跨页6×20不同CJK（加最初中文/输入，共8次提交）及两真实Chrome选中remote ICE candidate固定127.0.0.1:30096/UDP。38c86e...首个20字因Native evdev text_room=0不分批而触发缺xdotool fallback，整体FAIL35.79秒；补有限spare容量镜像8f7500...后20字变为错误重排，FAIL37.63秒。再加重绑定settle候选41a7...仍同错序，FAIL36.19秒，不能认为延迟修复有效。定向review57233已terminal0/PASS，但Root另写root_qualification.md拒绝其未测10–20ms/无丢帧/1000次等泛化，报告不算正式full review。

- 新鲜Profile的fixture在Target.createTarget/close原页后两次Runtime.evaluate启动超时（21.16/20.06秒），原失败保留；测试改复用SDK初始页并Page/Runtime.enable，初轮X11窗口未激活导致ASCII失败32.18秒；加Page.bringToFront与外部页面激活后ASCII恢复，仍在20字错序，故未降低文本断言。当前Root运行独立诊断镜像dcb9eaff8bc8...（仅测试sitecustomize计数/map trace，含fixture字符，绝不交付生产），exec句柄以主控工具返回核对，日志keymap_batch_trace_media.log；下一步查Native真实room、分批和overlay映射，不再猜延迟。sixAC全未勾/正式Verify与review仍0。

- **2026-10-29T04:41:27+08:00 中文定位与整链诊断阶段完成**：旧core Binding候选整镜像42bd99381efe...，45单元PASS；当前v2 wire真实Chrome整体仍FAIL34.77秒在中文，Linux平台新鲜Profile对照也FAIL34.74秒，Trixie同业务源镜像076d90... FAIL43.59秒，故未修改Browser03/隐私平台。Root直接读服务端XKB已更新而活跃Chrome仍按旧映射；单纯XkbSetMap不生效，xkbcomp重新加载完整相同map后收到正确可信中文输入。Root诊断Stream镜像8fd4318299b5...仅增加x11-xkb-utils与Native prebind映射更新通知，真实双Chrome完整 **1PASS42.46秒**：两页中文composition/official co,end、X11剪贴板哨兵不变、刷新ID稳定且另一页同PC音视频增长、独立静音/关闭、生存页输入与Browser PID/start_ticks不变。证据t004/.scratch/t004_root_checks/ime_reload_complete_proof/与ime_reload_media_round1.log。不是六AC完整通过，尚无最终源镜像/正式review。

- Root正将Native映射刷新收进stream_agent/x11_keymap.py：固定SDK ABI、仅新overlay时使用有界xkbcomp双子进程，不记录map或中文，不使用剪贴板/DOM插入；生产Docker仅增x11-xkb-utils。未改Browser Runtime生产源。正式候选镜像keymap构建/实测待完成。旧独立IME43440与base52217因实验已超原时间范围由Root核PID argv后SIGINT，进程均已结束，非正常完整报告；原JSONL与全部失败保留。诊断容器291e72cf15d3当前由Root接管作最后XKB对照，后续仅exact cleanup；不再按下文旧running叙述重复启动。

- **最新完成阶段：t004身份/回收修复**。transport98387/PID45726已terminal0，交付候选整镜像c27b18ce9352...；Root接管全部生产源。Root另发现四项真实回归：空session被接受、tab/resume任一匹配误绑、旧SDK映射残留可删替代viewer、stop未等待worker/reader finalizer。新增测试4FAIL后逐项修复，增加无注册拒绝control；当前相关六组单元 **45PASS1.28秒**，日志t004/.scratch/t004_root_checks/stream_unit_binding_round{1,2}.log，第一轮两项旧草稿缺必填runtime_instance_id已补合法输入、原断言保留。去除PC别名猜测；连接任务登记Native tasks以随服务shutdown取消/等待。源已变化，c27b镜像不代表最新修复，须重建后实际Chrome复验；六AC仍全未勾，正式Verify/review仍0。

- **私有bridge媒体阶段部分实证**：Stream已改独立bridge、仅localhost发布30096/UDP；Native HTTP只在容器loopback，测试fixture用限定Docker exec取静态资源（非生产Gateway实现）。真实inspect确认UID1000/只读根/cap-drop ALL/独立PID、共享指定Browser IPC，仅XSocket/Xauthority/Pulse/secret挂载，无userdata/agent.sock/Docker socket。双页视频8→63帧、音频44265→143157字节且能量增长；整体测试仍在中文处FAIL33.98秒，不计PASS。证据t004/.scratch/t004_root_checks/private_bridge_media_proof.json及media_private_bridge_round1.log。修复fixture关闭WebSocket顺序，排除原60秒cleanup等待，旧耗时不作首帧性能值。

- 中文定位：Root低spare/小fingerprint seed诊断均FAIL，未采纳生产修改；Linux平台诊断因自有复用Profile遗留SingletonLock启动失败，无有效中文结论，未改隐私平台。独立IME23802/PID43440仍仅validation/.scratch/t004_ime_audit实验；新base37807/PID52217仅t004/.scratch/t004_base_diagnostic比较Bookworm/Trixie XKB栈（同引擎/包/业务源），尚无定根因/通过报告。恢复先核进程与JSONL，不重复启动、不把诊断当六AC通过。

- **main 仍仅业务集成 t001/t002**。t003 执行 commit 为 8ff9fd237dcd8e6d1093f3de7503f5b7f599b3e6，branch=t003_v2_browser_runtime；已done/terminal completed/report done/exact cleanup，分支保留，尚未集成。原执行attempt1/execution57e21d93a87e4ab1baf4f96f652bca99/ownerroot_v2_20261027，不重复执行。

- t003完整镜像03：sha256:f2a8d42810c13c8480b83e4308669c754e86b0fe4a24c6215159e43a8d1f5346，arm64。独立正式VerifyRound2六项PASS178.67秒；Full Round2 code/test PASS，scope=e934e9a6bcba7ff4，零finding、报告勘误保留。各reviewer独立80单元/HTTP通过。Root Mac宿主HTTP正例/CDP errno61拒绝/容器内正例+loopback监听通过。

- **t003合并后验证失败并已撤销合并**：doctor exit0；168 contract+1原有条件skip、384旧后端、71单元、9HTTP通过；Runtime E2E为1FAIL12PASS。唯一失败：tests/e2e/test_browser_runtime_e2e.py引用未入库.scratch/t003_implementation/audio_tools/audio_analyzer.py，原worktree现场掩盖依赖，清理后暴露。失败原日志.scratch/t003_integration_gates/declared_gates.log/result.json保留；main无pending merge，不恢复临时脚本伪造通过。

- **当前t004 active**：worktree /Users/karson/kar/code/CBrowser_t004，branch=t004_v2_stream_runtime，base/diff_anchor=8ff9fd237dcd8e6d1093f3de7503f5b7f599b3e6；attempt1，execution_id=c738656d4a2144cc9643f66c1b4831e9，owner_id=root_v2_t004_20261028，已reserve/claim，strict preflight PASS。固定队列未增加成员；按task-run后继以已完成前一分支为base，计划t003→t004链尾一起验收集成，保留t003历史。

- Root已在t004补正式共享tests/fixtures/runtime_probe/audio_analyzer.py（复用已验证s007算法），原Runtime E2E按文件定位并用sys.executable，不再引用历史scratch。全新worktree无audio_tools目录下，13项真实Runtime E2E全部PASS161.53秒；Ruff E/F/W/I和format通过，最后只做AST等价字符串换行。未提交，归入t004单次执行commit。证据t004/.scratch/t004_root_checks/runtime_clean_fixture_e2e.log/provenance；源归档未修改。

- t004首轮主体99316/PID872已terminal0且持久finish=stop；最后实际Chrome双页固定1920×1080视频解码PASS73.04秒，但audio=None、帧增长断言仅>=，不当完整媒体通过。Root已接管client_shim.py与媒体E2E；当前两名指定模型新会话并行且写域不重叠：transport84130/PID35472/session ses_e7c17b3f5ffe1McuB8n4ncIdu0仅Agent/config/protocol/boundary/Docker/schema及新严格测试；policy84524/PID35471/session ses_e7c17b3f2ffeWwUZC2iyPTuv4z仅policy.py/新策略测试。两者legacy Runtime/API/domain/compose有SHA guard，Root ICE/媒体/shim测试不归作者。当前主体仍需认证消息绑定、真正可复现镜像和完整捕获/输入实证。旧provider400及草稿失败日志保留，未修改全局配置。

- ICE原作者27506/PID95881已terminal0，Root接管ice_transport.py及其测试。错误URI回显私密值先2FAIL后修复，9单元PASS；真实SDK连续3次relay准备失败原先socket4→7且旧monitor被取消，修复后direct/sharedUDPmux两路均socket4→4、旧monitor保留、旧DataChannel可传输，随后同PC/DTLS/DataChannel正常重启至generation2。证据t004/.scratch/t004_root_checks/ice\_{error_privacy\_*,failure_real\_*,recovery_direct,recovery_mux}.log。诊断采用固定SDK镜像+明确helper挂载，尚不算完整Stream镜像或三代TURN媒体通过。新增正式fixture及E2E等待最终完整镜像复跑；5个Root所属ICE文件Ruff E/F/W/I、format通过。

- 独立验证worktree main/.scratch/v2_orchestration/t004_validation（spike/t004_validation），原6677/PID97202及续行86431/PID2968均已terminal0；后者持久JSONL含finish=stop，包装器CLI自然退出观测race标durable_finished=false，原始记录保留。独立校准音频工具正例440/880Hz、错频/错采样/缺失/空文件拒绝，并在全新独立cwd重放真实双Profile音频+Cookie重建AC001：1PASS/7deselected23.29秒，日志candidate_ac001_85395414.log。SHA已在报告记录；该证明只闭环共享fixture可移植性，不代指t004媒体。六AC量具仍PENDING_PRODUCER_BINDING，准备阶段原夸大结论已要求限定。

- ICE独立诊断65674/PID7490（session ses_e7de48ea8ffeQsJD02hDearHrX）已terminal0，确认pending关闭仅关新连接，以及真实TURN分配超时/取消泄漏。Root正式新增pending-close与TURN-timeout/cancel fixture，修复active连接清理及固定SDK TURN分配取消清理、gather drain。只读UID1000诊断direct/mux关闭后socket2→2；四种TURN失败/取消socket5→5且旧通道/monitor存活。9单元+8真实Docker正式测试入口全部PASS47.53秒，镜像sha256:8df3f4e20625d244556747ac33b22fb77be760eb4ffe26b9bfd819526b0aa8bd（集成package诊断镜像，非最终可复现Stream交付/媒体六AC）。日志t004/.scratch/t004_root_checks/ice_integrated_17_tests.log，首次失败及局部修复未完全解决cancel的日志均保留。独立新绿复验61854/PID9847已terminal0/持久finish=stop：UID/GID1000、镜像内helper SHA一致，direct关闭回基线2、mux附件0且关后回基线2、TURN失败/取消增量0且旧通道继续；原报告nonroot错误已勘误。TURN三代真实Chrome音视频仍未执行。

- Root补真实三代TURN机制：UID1000只读cap-drop全禁的两Selkies原生PC/DataChannel，经本地隔离coturn完成relay generations2/3/4；每代server/client不同HMAC凭证及relay端口、同PC/DTLS/DataChannel/mux、旧send拒绝。初次coturn禁全部cap导致二进制exec EPERM，证据保留；只对coturn加入NET_BIND_SERVICE后实际通过（本地镜像4.18.0），不代表正式依赖版本或Chrome媒体通过。正式新增fixture/E2E后与Chrome身份并发回归合跑2PASS3.98秒，日志client_identity_and_relay_formal.log。

- Root修复Web Locks同文档并发HELLO竞态：先真实Chrome同步发送两注册触发Timeout FAIL，再共享pending acquisition修复；原始HELLO保持逐字转发，复制文档只重映射自身ID，不踢原页面，重载保留ID。移除生产shim中测试专用PC/audio挂钩与无界日志。真实Chrome回归PASS，源/测试Ruff通过；它仍是身份机制测试，不代指媒体六AC。媒体E2E下一步补真实远端Canvas/WebAudio、严格帧和音频能量增长、刷新/关闭、原生IME及隔离。

- Root首次严格真实音视频阶段PASS76.63秒：新远端Canvas/WebAudio页面，双Google Chrome视频8→66/1→58帧（测量窗口2秒）、接收音频字节45249→144141/16725→116109且能量持续增加；首页面静音/关闭后另页149帧、音频264691字节且能量继续。Browser03与不可变Stream初版镜像477c51b32d35...（非新transport/policy最终交付）运行，无mock媒体。保存media_audio_first\_{source.py,proof.json,manifest.json,real.log}，不依赖轮转pytest tmp。该阶段只证明音视频/静音/关闭，尚不覆盖完整AC001输入/刷新、AC003策略或AC004 Chrome三代relay。

- policy首轮84524/PID35471已terminal0，19单元PASS；所谓Native检查仅构造真实SDK类、rtc_app=None，无真正pipeline/callback/FPS实证，Root已要求勘误。续行75821/PID40377/session仍ses_e7c17b3f2ffeWwUZC2iyPTuv4z，独占policy写域，使用18361/30361独立端口补实际XShm capture。Root媒体保留18096/18097/30096。Root当前7028在跑扩展媒体测试：真实双页键盘/中文组合、X11剪贴板哨兵、刷新与生存页输入，尚未判定通过。transport84130/PID35472继续。

- Root扩展中文IME实测仍FAIL：两页物理数字输入分别/交错到同一DOM均通过；原生可信compositionstart/textInput、官方co,end,中文均存在，但远端DOM为空。补外部激活/焦点和0.2秒预编辑停顿仍FAIL80.84秒；增加远端原生事件观测后看到pinyin/Backspace，再收到NUL key的F24/IntlRo，定位至X11 Unicode键映射/浏览器解释边界。未用粘贴或写DOM中文绕过。原始失败及定向复跑76.29秒均保留，ime_round2/备份不依赖tmp轮转。独立23802/PID43440在验证worktree仅.scratch/t004_ime_audit定位；Root已补NUL事件证据与Windows指纹平台/文字spare keycode差异假说，尚未定根因。

- policy75821/PID40377已terminal0；policy SHA e356e43f9c09b1daaaa8026e7560ec508b81d5f0a4b52d1483033d97897361a5，20单元与Ruff通过。实际原生capture机制probe使用旧spike Browser/Stream+自身测试控制UDS（不算Browser03默认生产入口/认证全链路）：静止damage0且配置8、持续motion检测后原生配置30、后台不降前台、cap15解除回30、全隐藏capture=False且计数停止、恢复set8先于resume。30为原生配置值，未据此声称Chrome实际30FPS或P95。报告勘误初轮rtc_app=None已记录。Root接管policy所有权，最终完整镜像与Chrome仍需复验。

- transport84130/PID35472已terminal0，public Python/Debian镜像556ef91da0a1aa0b2870e90f956362b50d860855ae3c3bf9cddc1a3a994f2068构建、29单元及缺Socket拒绝/UID1000 import通过；Root发现wire Pydantic未接入、可缺identity/version、SDK ws对象比较无效且sole-peer fallback可能误选、旧worker reader仍发close、Gateway失联留visibility、instance默认随机等未闭环点，不能收尾。续行98387/PID45726同session ses_e7c17b3f5ffe1McuB8n4ncIdu0修实际绑定/严格wire/真实WS回归及白名单构建上下文；不修改Root政策/IME/ICE文件。

- t004当前六AC未勾、正式Verify/review均0；下一步先观察以上进程/持久会话，不重复start/reserve。源接口及整镜像冻结后才派正式独立验收/full review，一个执行commit、exact cleanup、链尾主干验证，禁止push/正式部署。

- 测试引擎缓存已保存在main/.scratch/v2_orchestration/t003_engine_cache，671文件SHA逐一相等；t003原始证据备份t003_evidence_before_cleanup.tar.gz，444文件、0600、SHA256=908d0ac8ff9d206d810eab594a44ebc3504ce35a015f0c6bb74897600003f86d。验证worktree和日志仍在，不依赖已删除t003worktree。

- 后续必须闭环：t005只读引擎缓存初始化同时准备所需GeoIP资产，lifecycle/error不得清running意愿；t012统一Runner/Agent CLI日志ISO8601带时区格式（当前logging asctime仍旧格式，记录待修，不据此停媒体实施）。后续P95/8h/1000输入性能验收仍必做，未新增豁免。

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
- t002：done / integrated，唯一执行提交ee2aa47155848a775a15c1ec94c26ad77b4c2021，merge=914dde5fb9d4。原登记/Users/karson/kar/code/CBrowser_t002已exact cleanup，分支t002_v2_backend_foundation由集成脚本删除。权威交付现为main的docs/archive/tasks/t002_v2_backend_foundation/，不得恢复旧路径或重复start。
- 已闭环identity：attempt=1，execution_id=13f1211c2c0046629e9f68c9741d2514，owner_id=root_v2_20261027；ledger已有terminal completed/report done/cleanup/integrated。
- 最终验收：工作副本169契约+384旧后端+19单元+9真实HTTP通过；独立Verify Round4/5为9/9 PASS+SQL隐私PASS，manifest=c7e1228803978178adff71a7075f4de17226ea4bfa52c0a487600c07cd6c93ef。正式full Round2 code/test均PASS、0finding、scope=bfeffb3d43a6d56d，7视角/6AC独立复验；409文件监控无源变更。t002所有模型进程已终态。
- 合并后全部声明命令块退出0：168契约通过/1按主仓既有sync_state条件跳过、384旧后端、19单元、9真实HTTP通过，旧健康ok，task list及repo_sync status正常。日志.scratch/v2_orchestration/merge_t002/gates.log。跳过条件与t001主仓相同，未改测试；不把主仓配置状态与工作副本未初始化混淆。
- 过程证据：t002_evidence_before_cleanup.tar.gz（6556763字节、0600，排除缓存/临时目录，含固定候选和实际日志）；完整TDD及两轴审查消息保存在主仓.scratch/v2_orchestration/。前轮CWD错误、只读越界/checkout污染及恢复记录保留，不计有效PASS；schema已按冻结哈希恢复。CLI自然0与持久finish=stop分别核对。
- t003已active：登记worktree=/Users/karson/kar/code/CBrowser_t003，branch=t003_v2_browser_runtime，base/diff_anchor=226c8453097fb982835ccb254cea8a3f26d131b3；attempt=1，execution_id=57e21d93a87e4ab1baf4f96f652bca99，owner_id=root_v2_20261027，start/reserve/claim均完成。根据已验证d002/d004/d006/d011及t002最终快照消除过时未知标记，require-verified preflight PASS；六项业务AC未改、尚未勾。
- t003实施写域已拆分：Root独占Runner/参数安全/事件存储/模块入口及新增test_runtime_persistence_guards.py；Gemini进程48410/PID47419（session=ses_e7fbd2a96ffeyMAddPaIRGbucs，日志t003_split_uds_e2e.jsonl）仅改Agent/CDP/health、entrypoint/Dockerfile和真实E2E。77168因持久化失败被catch后仍宣称saved等具体偏差主动SIGINT（-2），确认旧进程结束后按新写域恢复；对子进程edit权限明确deny Root核心，禁止全目录格式化，避免重叠写。
- 旧86758误用旧镜像默认entrypoint的临时容器7c2cbf1b3e17已核实仅匿名卷、无hostbind/portbindings后exactstop并确认自动删除；正式cbrowser healthy。新子进程权限拒绝旧镜像命令/prune/Git回退，全局配置未改。
- Root核心阶段完成：先复现9项失败（另5通过），新增引擎两项失败和模块入口import失败，保留完整red日志。修复目录fsync所有错误failclosed、危险CSV feature过滤/私密输入不入日志、ID/版本前置校验、终态事件防误重启、持久化失败传播和主协程等待、过时run_agent入口。当前全tests/unit55 PASS，核心Ruff E/F/W/I与format通过；未改旧测试预期。
- Root真实Docker验证：只读统一cache按SDK当前Linux平台精确版本选择，ELF/架构与实际--version核查PASS；真实Browser.close=exit0、Chrome SIGKILL=exit137、SDKdriver SIGKILL引发Chrome0但记录lifecycle(None)/state error且Runner失败，三组均PASS，无mock。退出观察不把基础设施零退出交t002清意愿（t002拒绝exit_codeNone）。证据t003/.scratch/t003_root_checks/runner_lifecycle/\*\_r2.log、manifest_r2.json与core_delivery_manifest.json；均为固定旧镜像+Root当前核心只读overlay，不冒充新完整镜像/六AC，测试容器已自动清理。
- 新增独立Gemini进程49643/PID52073（session=ses_e7fa421cbffeGe5SkpRfEHP4Lm，日志t003_profile_defaults.jsonl），仅写新profile_defaults.py及独立真实E2E，补set_google_default功能、英文/中文设置UI与一次性不覆盖用户偏好；Root后续接线，其他writer不碰该两文件。没有读用户.env或启动新第二浏览器路径。
- 60738作者17单元与6个Docker测试函数通过，但主控逐行发现缺多Profile真实音频/XShm、健康负例、外部下载覆盖真实生效、Chrome异常退出等关键步骤；窗口高度断言改成root屏幕几何亦不足以证明Chrome窗口。候选被拒，6AC恢复未勾，正式Verify0/review0，不commit/finish。
- 之前实现83192因旧镜像默认entrypoint探针错误被Root主动SIGINT（-2），仅其新临时容器按ID停止，正式cbrowser保持healthy；83130因创建worktree外契约TMPDIR获权限拒绝后自然terminal0，公共跨目录契约测试改由Root执行，本登记worktree169 PASS（root_contract_gate.log）；61864因已确认的路径/进程/SDK语义偏差主动SIGINT（-2），保留草稿后同session恢复74490。上述均未重置attempt/轮次，正式Verify尚未开始。
- 独立验收位于.scratch/v2_orchestration/t003_validation（spike/t003_validation），session=ses_e810ce64effe5r9OxcJOiLo6Rz。UDS实验已完成；45609在主控提供哈希副本后terminal0/持久finishstop，声称FULL_HARNESS_IMPLEMENTED，但实际六函数缺大量主体（包括未启动B、无PCM、手动rearm冒充自动、未测SIGKILL），主控拒绝该声明。真实状态PARTIAL_BODIES，不计正式验收；87163已terminal0/持久finishstop，虽新增真实A/B音频和若干用例，仍将无socket容器内xwininfo失败错误宣称XShmAttach BadAccess，主控再次拒绝完整覆盖声明。当前fresh独立Gemini进程68647/PID45544、session=ses_e7fb8651bffe6Xm7yXVHRAeDHp补齐实际IPC成功/拒绝探针与所有剩余body，日志t003_blackbox_soundness.jsonl；状态仍PARTIAL_BODIES，未执行正式六AC。早期跨目录读取权限拒绝记录保留，未改全局权限。
- 独立SDK机制研究session=ses_e810542c9ffeEj0GHmgVLeriFQ（同t003_validation的独占.scratch/t003_sdk_exit），78283首稿与29822严谨版均已terminal0/持久finishstop。主控独立重跑冻结原版和格式化正式代码，五项严格检查均exit0；仅headless机制实验，不是正式镜像/六AC。已在t003登记worktree通过脚本创建d016和s010并归档：docs/archive/spikes/s010_cloakbrowser_exit_observation/，code SHA=ef1bee2847c96e30ff4542ddf3f888bce332c414774086a08a272462dda36d5c；暂未合入main。
- d016关键实证：真实Chrome正常关闭raw0、SIGKILL raw-9/规范化137可观测；仅杀SDK Python owner时，Chrome因pipe EOF在0.5秒内以0退出，清理前5秒记录保持。因此UDS Agent与SDK owner/Chrome监控生命周期必须分离，不能据Chrome0单独清running意愿。未证明全部代理/扩展/DRM/humanize等价，原型状态没有fsync，不当生产持久化。正式源码与Root输出已复制到实现worktree .scratch/t003_implementation/peer_sdk_exit_v2/供消费。
- s010归档首次write因新目录未入Git索引而git mv报empty；核对源完整/目标不存在后只对本spike/finding git add -N，再用原归档命令成功，源码哈希不变；未改模板或手动搬运。原始工具失败、旧过度声明和宽泛负例判据均保留于scratch，不冒充通过。
- UDS运输实测：非root Linux server能在Mac bind目录创建socket；Mac原生connect返回errno61；第二Linux peer通过同bind目录与独立named volume均完成echo。正式黑盒客户端采用Linux peer，持久Profile/cache/artifact/event仍用真实Mac bind根。未实测底层共享文件系统实现/零拷贝/性能，不能据此归因。原始源码与日志在validation/.scratch/t003_blackbox/transport_probe/，不计产品AC。
- 独立草稿预审20178已terminal0，末尾读取host/tmp获权限拒绝；主控审源码发现其脚本已写宿主/tmp/.X11-unix/X88，违反写域，已报告用户，文件保留不擅删。fsync结果为定向故障注入而非真实EIO；字段未引用仅候选语义风险；控制字符日志需精确canary判据，不能以换行计泄漏。57105已terminal0/持久finishstop，仅在专属runtime_pre_audit scratch完成有界报告，未再运行旧越界脚本，不计正式review。主控逐项复核并驳回同步fsync之间存在协程抢占等错误因果，报告及处置已复制到新实施者本地packet。
- 主控另实测不可变镜像4a76ae021ec3：UID1000、RO根、cap-drop ALL、network none，在全新Mac bind数据目录实际atomic写/readback、显式Linux目录fsync及坏JSON拒绝均PASS，容器已自动移除；storage_bind_probe.log保留。不代表掉电恢复/六AC；该平台具备成功目录fsync路径，不能以一般不支持为由吞错。
- 主控新无mock实证：冻结源码构造Runner时，version0、version-1与../escape_profile均在启动前获接受；精确危险flag获允许、唯一敏感canary进入日志。完整哈希、脚本、结果在t003/.scratch/t003_root_checks/snapshot_probe_manifest.json及snapshot_and_log_probe.log；这是旧草稿红证据，现已由Root新回归修复；未实际启动子系统，不当完整攻击/六AC证明。
- 主控草稿回归：Python3.14运行tests/unit共36 PASS（unit_draft_python314_20261028_0509.log），范围含已集成t002单元及t003当前单元；实现仍变化，非最终冻结门禁/六AC。首次命令误用系统Python3.9收集失败，原日志保留；未改代码迎合旧解释器。两个独立agent的跨目录权限拒绝通过主控提供受限本地源码快照解决，未修改全局权限/模板。
- 当前生产写域以Root核心、48410 UDS/E2E和49643新搜索初始化模块为准；各文件无重叠；恢复先核具体进程/持久会话/task.py recovery t003，不重复start/reserve。Docker实现资源cbrowser-t003-impl-、验收cbrowser-t003-bb-、SDK研究cbrowser-t003-sdk-各自具体IDs隔离；禁止全局清理、source .env或触及正式用户数据。

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

### 第三轮候选历史结果（最新以当前现场为准）

- 主控最新完整门禁退出0：169契约、384旧后端、19新单元、5真实HTTP集成通过；旧健康ok，task list正常，工作副本repo_sync仍未初始化（退出0，不是配置成功）。日志CBrowser_t002/.scratch/t002_gates/project_gates_candidate3.log。
- candidate3独立8项黑盒：持写锁GET返回200约11ms且锁仍持有；短锁写等待1.61秒成功，长锁约5.22秒返回503/Retry-After，释放后恢复；重复tag返回409且物理DB无半写。3个不同uvicorn PID均已终止，真实两次重启后完整配置/标签颜色、不可变快照、幂等、删除状态留存。
- 独立SQL日志探针：422响应无私密值回显，约束409，物理日志无注入敏感值泄漏。该测试覆盖边界见d015，不宣称所有未知Python异常绝不泄漏。
- 已补齐OpenAPI生成/校验文档、修正t002不依赖Docker/Chrome的可测试性，并在架构文档区分已新增后端基础与未切换的旧正式入口。全部AC由主控真实门禁暂勾，正式review须独立复核。

### 下一步与边界

1. 以本节顶部「当前恢复入口」为准，历史进程均已退出。确认02构建及实际 E2E 结果，再冻结最终候选；t001/t002 不重复执行。
2. 复核SDK真实进程退出观测、统一只读Linux引擎cache及Mac bind-root UID权限、完整Chrome UI/DPR1、UDS安全边界、下载覆盖恢复ACK及持久事件；未知外部契约须实证，不把原型或容器alive当正式AC通过。
3. 独立黑盒后完整code/test七视角审查，使用对应report/scratch权限白名单和交付哈希监视；一个执行commit、exact cleanup、已获授权的本地main集成，不push。
4. 每阶段完成立即更新本文件，失败阶段也记FAIL与恢复入口；项目级handoff不能替代task级handoff.json。
5. 管理员密码文件路径已异步询问，供t006/t012使用；当前不因此暂停后端工作，不自设生产默认密码。

- 工作区保护：主干写交接前干净。各task用户改动保留；临时uv.lock先核实来源和进程状态，避免将reviewer生成文件纳入交付指纹/提交。已完成t001未提交资产均已提交或备份，没有遗失清理。
- 全局约束：只写 `~/kar/code` 内；保持用户改动；使用 OpenCode 指定模型执行已授权子任务；不修改 `.repo_template` 绕过门禁，不把技术原型当成正式生产组件。

## 2026-10-30T20:46:00+08:00 v2 架构计划执行交接（t005 完成，t006 实施中暂停；计划修订已同步 task）

- branch：main
- head_commit：4229c91（本次 docs 改动前；t005 merge 为 2743ed7）
- 工作树：只剩主仓（main）与 t006 WT；E2E lane 已 retire，无其他 lane/分支。
- 执行目标：完成 docs/v2_architecture_plan.md 剩余 task t005→t006→t007→t008→t013→t014→t009→t010→t011→t012，每 task 一个执行 commit，逐个合入本地 main；最终部署到本机 OrbStack，由本机官方 Chrome 访问。禁止 push 与外部发布。
- 已定决策：重试为首次异常后 2/10/30 秒三次重试、failure_count=4 阻断、手动重试清除（ADR 008）；管理员密码在 data/secrets/admin_password（只在生产首次启动读取，测试一律随机密码）；公网 WebRTC/TURN 穿透与原生 Linux x86_64 执行为 USER_WAIVED（不能写成通过）；性能按本机 OrbStack + Chrome 实跑。
- 子 agent：OpenCode `cpa/gemini-3.8-flash --variant high`，经 `.scratch/v2_orchestration/dispatch.py`（权限白名单 + 全交付文件 SHA 守卫）→ `run_opencode_observed.py`（已补 `--variant high`，保留 `--env-root`）。主控 owner_id 记录在 `.scratch/v2_orchestration/claude_owner_id.txt`。

### 当前恢复入口

#### t005 已完成并合入 main

- 执行 commit 3b5576e9dd0990a21aaaa66965133e0a91bb2f5c；merge 2743ed7509f4（merge(t005)）；分支已由工具删除，worktree 已 exact cleanup。attempt1 terminal=completed、report=done。
- 验证：冻结候选主控全门禁（contract 169、legacy 384、unit 211、integration 21、Runtime 13、Stream 12〔Chrome 2 秒帧 59→16→60〕、Supervisor 生命周期 6、启动恢复 2、容器图等 8、内核策略 5、资源 5）；独立 OpenCode 黑盒在逐字节等同候选的 validation WT 自建镜像复跑同数通过并以 4 个自写探针验证 AC-001/002/003/005（重试实际 3.45/12.53/31.82 秒含真实 SIGKILL）；Full review Round1 两路 PASS（2 minor），Round2（md_kx 缩进与 p002 修复）两路 PASS，checker overall=PASS。合并后在 merged tree 复跑全套门禁全部通过（contract 168+1 skipped 为主仓 sync_state 预期行为）。
- 遗留：p001（RecoveryCoordinator.tick 复杂度，minor）；p002 已修并归档。Round2 两路 wrapper 因派发时未互相排除对方报告文件被 SHA 守卫中断（报告均已写完），今后 reviewer 派发需同时 unguard 两份报告。
- 证据备份：`.scratch/v2_orchestration/retired_worktrees/CBrowser_t005/scratch/`（日志/JSON/报告 28M）、`retired_worktrees/t005_validation/scratch/`（黑盒 1.6G）；GeoIP 缓存 `.scratch/v2_orchestration/geoip_cache/`；通用门禁 runner `.scratch/v2_orchestration/gates/run_gates_template.sh`（GATE_ROOT/GATE_LANE，按轮复制执行）。validation worktree 与 spike/t005_validation 已移除。

#### 计划修订（2026-10-30，用户批准）

- 来源：用户提供的外部开源项目调研文档（未入库，已按用户要求删除），经 Selkies 2.1.0 固定源码复核后修订 `docs/v2_architecture_plan.md`，修订记录在其开头“修订：开源项目调研意见复核”节。
- 核心变化：9.3 页面可见性只走 Selkies 原生每 Peer STOP_VIDEO/START_VIDEO，Gateway 不采集可见性/活动，Supervisor 前台状态改由 Agent 健康消息上报；8.1/8.4 显式设置 `SELKIES_ENABLE_DUAL_MODE=false`、`SELKIES_FILE_TRANSFERS=none`、剪贴板策略锁定（main 代码当前均未设置，2.1.0 默认分别为开启/upload,download/二进制开启）；7.5 内部协议边界；11.3 下载目录对账兜底；13.4 冻结恢复与连接诊断。
- 修订后的计划文件已原样复制进 t006 WT（与 main 内容一致，integrate 时双方同改可干净合并；供 t006 实施与 review 读取最新 9.3）；其他 main 侧改动（handoff、t007–t014 task）不进 t006 交付，integrate 时由 merge 带入。
- 已同步 task：t006 AC-007 改写与范围（WT 内）、t007 AC-004 改写+新增 AC-007/008、t008 新增 AC-003/004、t009 AC-004 补安全项、t014 范围收窄+新增 AC-005；t007–t012 与 t006 的“t001 仍 active”过时来源行已改为已完成。

#### t006（branch=t006_v2_gateway_auth_rtc，base/diff_anchor=c33e55f，worktree=/Users/karson/kar/code/CBrowser_t006）——暂停记录点 2026-10-30T20:46:00+08:00

- identity：attempt1 / execution_id=79fa47d2f34e42f8b31f43ceb8cb52a9 / owner_id=claude_v2_14b38abc09f2（已 reserve+claim；不得重复 start/reserve；恢复会话若换 owner 须 `attempt claim --replace-owner claude_v2_14b38abc09f2 --confirm-stopped`）。strict preflight PASS（UNVERIFIED-SPIKE 已改写为已验证结论）。尚无执行 commit，七 AC 均未勾，正式 Verify/full review 0。
- **未提交工作保存在 t006 WT**：68 个路径（+8199/-105，含计划修订后的 task.md/note.md 与同步的计划文件），新文件均已 `git add -N`。最新安全快照 `.scratch/v2_orchestration/t006/t006_wt_snapshot_20261030T2046.patch`（`git diff --binary c33e55f`，sha256 前缀 8a6605a735f2d126；旧快照 20261030T2032 保留），可在干净的 c33e55f 上 `git apply` 复原。
- 已合入 t006 WT 的内容：
    - 主控预置：stream_agent/protocol.py（RTC_CONFIG、注册字段 selkies_version/runtime_state/config_version/turn_host/turn_port、AgentHeartbeatPayload、IceServer/RtcConfigPayload）、schemas/stream/agent_protocol.json、tests/unit/test_stream_agent_protocol_v2.py；task.md 未知契约结论。
    - agent lane：Stream Agent 注册字段、10 秒 HEARTBEAT、1/2/4/8/16/30 退避、rtc_config 应用；entrypoint 要求 CBROWSER_CONFIG_VERSION。主控修正：恢复 schema 测试导入、selkies 版本只读安装元数据、心跳默认 10 秒断言、Supervisor docker_adapter 向 Stream 传 CBROWSER_CONFIG_VERSION（容器图 RED「Runtime start failed」→ GREEN 1 passed）。
    - gateway lane：src/backend/cbrowser/{gateway,rtc_config}、config/docker/gateway_runtime/、docs/blueprint/gateway.md 及单元/集成测试。
    - gwfix lane：Stream 侧 TURN 用 Agent 上报的 coturn 实际地址（删除 turn:coturn 默认，ADR 010）、Agent 回传包身份与 Viewer 归属核对、重注册关闭旧 session Viewer、新代凭证同步给 Agent、控制帧异常记录。
    - auth lane：src/backend/cbrowser/auth/、api/v1/auth_router.py、api/internal_gateway.py、迁移 0002_auth、OpenAPI 重导出、tests/fixtures/api_auth.py；12 个启动 API 的既有测试只加登录夹具（断言未改，已逐文件核对删除行）。主控修正：未配置 CBROWSER_ALLOWED_ORIGINS 启动失败（RED→GREEN）、新模块 ruff format、超长行折行、两个文件 EOF 空行。
    - 主控文档：docs/blueprint/security.md（新）、docs/specs/access_control.md（新）、ADR 010、webrtc_remote_display spec 信令/轮换/活动聚合段、architecture.md 现状、specs_index（webrtc_remote_display 增 t006，新增 access_control）、testing.md unit/integration 命令补 argon2-cffi（及 integration 的 sqlalchemy[asyncio]/websockets）、note.md 实施笔记。
- 已验证（合并态，Docker E2E 之前）：unit+integration 294 passed（`.scratch/t006_root/full_all_lanes.log`）、contract 169、legacy 384、Ruff 无新增（剩余 16 项与 main 基线相同）、diff --check 与 md_format 通过。auth 修正后又跑 285 passed（origins_green_full.log）。
- 已 retire 的 lane worktree（证据备份在 `.scratch/v2_orchestration/retired_worktrees/CBrowser_t006_{agent,gateway,auth,gwfix}/`，lane 分支已删）：agent、gateway、auth、gwfix。
- t006 E2E lane 于 2026-10-30T20:41:00+08:00 按用户要求 SIGINT 停止（无改动、无容器），2026-10-30T20:45 前已 `lane_worktrees.py retire`：WT 与 lane/t006_e2e 分支已删，证据备份 `.scratch/v2_orchestration/retired_worktrees/CBrowser_t006_e2e/`；原 prompt `.scratch/v2_orchestration/t006_dispatch/t006_e2e_prompt.md` 需按计划修订 9.3 改写后再用（不得续行旧 session）。当前无运行中的子 agent。
- **下一步（恢复顺序）**：
    1. 按 t006 note.md「2026-10-30T20:46 计划修订 9.3」待办移除 Gateway 活动聚合与 VISIBILITY_UPDATE 链路，Agent 心跳上报未暂停 consumer 数/捕获状态，Gateway visibility 端点改读该值；同步 gateway.md/stream_runtime.md/webrtc_remote_display spec。先 RED 后 GREEN，旧语义测试整项删除并说明。
    2. 改写 E2E prompt（AC-007 新语义），新建 E2E lane 执行；主控亲自复跑并核原始 JSON 证据（帧数、candidate 类型/地址、Generation committed 日志、Cookie 属性），增量合入 t006 WT 后 retire。
    3. 用 `.scratch/v2_orchestration/gates/run_gates_template.sh` 复制一份快照跑全套门禁（需补 Gateway 镜像构建与 Gateway E2E 步骤；Stream 镜像必须用当前源重建，因 entrypoint 与 Agent 已变）。testing.md 补 Gateway E2E 命令。
    4. 七 AC 按实证打勾 → `git add -N` → 渲染 review prompt → 派独立黑盒（validation worktree 复制候选）+ code/test full review（reviewer 派发需同时 unguard 两份报告）→ 处置 → handoff.json → finish → 一个执行 commit → attempt terminal/report → cleanup → integrate（合并后门禁）。
- 工具改进（本阶段）：dispatch.py 新增 `--unguard-changed`（lane 续行时排除其已改/新建文件）与 uv 缓存硬链接预灌；lane_worktrees.py（create/diff/retire，retire 不用 --force）；gates/run_gates_template.sh（GATE_ROOT/GATE_LANE，已加 argon2-cffi）。注意 zsh 不对未加引号变量分词，多参数派发用 bash -c。
- 本阶段构建的本地镜像（均可由源码重建，未清理）：t006-agent-stream:1（sha256:9489b9d4…）、t006-gateway-gateway:1（761dcc30…）、t006-gwfix-gateway:1（3ef22490…）、t006-gwfix-stream:1（9b37deea…）、t006-root-supervisor:cfgver（a2943b3a…）、cbrowser-gate-*:r1（t005 合并后门禁）、cbrowser-t005-*:final_round1。注意 t006 门禁须用当前源重建 Stream/Gateway/Supervisor/API 镜像，不能复用上述临时镜像冒充。
- 未触碰的既有对象：Docker 网络 cbrowser-t003-bb-aece4d57-net（带 t003 黑盒 run_id 标签、0 容器）与 net_9335ab04/net_d876dc01/net_e5052de6（无标签，来源不明）、容器 pensive_satoshi、test-shm-srv；旧 cbrowser 容器在 t011/t012 前不动。调研文档 `123.md` 已按用户要求删除，结论已并入计划修订记录。
- 会话目标：本会话的 /goal 仍为 active，停止时需由用户 `/goal clear` 或指示恢复。
- 已知风险：主机负载受 kkmail 等其他项目容器影响（13:00–19:46 曾致 Docker 引擎无响应），计时类测试与后续 t009 性能基准需记录负载；用户已授权必要时重启 OrbStack（本次因自行恢复未执行）。

#### 后续队列

- 通用工具：prompt 外壳 `.scratch/v2_orchestration/prompts/{implementer,reviewer,blackbox}_preamble.md`；lane 状态摘要 `python3 .scratch/v2_orchestration/lane_status.py <jsonl> --text`。门禁 runner 每轮复制快照执行，禁止在运行中修改（round1 曾因此重复一步）。
- 容量/P95/8 小时/1000 次输入等压力验收属 t009，尚未执行，不得宣称通过。
- 剩余队列：t006（实施中）→ t007 → t008 → t013 → t014 → t009 → t010 → t011 → t012。t007 前端契约草案 `.scratch/v2_orchestration/t007/contract_draft.md`（含 Selkies Web 资源构建期从固定 wheel 提取并校验哈希的定案与 lane 拆分）；Selkies 2.1.0 Web 客户端参考副本 `.scratch/v2_orchestration/selkies_web_ref/`（含 sha256_manifest.txt）。

## 2026-10-30T21:03:37+08:00 v2 架构计划执行交接（t006 实施中：会话接管、计划修订 9.3 与 ICE 提交确认已实施）

- branch：main
- head_commit：5c1f524（本次 docs 改动前）
- 工作树：主仓（main）、t006 WT（/Users/karson/kar/code/CBrowser_t006）、E2E lane WT（/Users/karson/kar/code/CBrowser_t006_e2e2，分支 lane/t006_e2e2，seed=t006 WT 2026-10-30T21:06:56+08:00 状态，早于下述 ICE 提交确认修复）。
- 执行目标：按冻结队列 t006 → t007 → t008 → t013 → t014 → t009 → t010 → t011 → t012（`docs/runtime/goal_queue.json`）串行完成 `docs/v2_architecture_plan.md` 剩余内容，每 task 一个执行 commit，逐个合入本地 main；最终部署到本机 OrbStack，由本机官方 Chrome 访问。禁止 push 与外部发布。t001–t005 已完成并合入。
- 已定决策：重试 2/10/30 秒三次、failure_count=4 阻断、手动重试清除（ADR 008）；管理员密码 `data/secrets/admin_password`（0600，只在生产首次启动读取，测试一律随机）；公网 WebRTC/TURN 与原生 Linux x86_64 为 NOT_RUN / USER_WAIVED；性能按本机 OrbStack + Chrome 实跑；计划修订（2026-10-30，9.3 可见性只走 Selkies 原生、Gateway 不聚合活动、显式 Selkies 设置）已获批。
- 子 agent：OpenCode `cpa/gemini-3.8-flash --variant high`（思考强度 high，用户 21:00 重申），经 `.scratch/v2_orchestration/dispatch.py` → `run_opencode_observed.py`。
- 主控会话：claude 会话 1024a4ed（进程 92682，接替同进程内已中断的 e225b0f4）；owner_id 记录在 `.scratch/v2_orchestration/claude_owner_id.txt`（旧值备份 `claude_owner_id_prev_14b38abc09f2.txt`）。进程 3313（会话 5d707c61）是写计划修订与接手 prompt 的辅助会话，未持有任何 task。

### t006（branch=t006_v2_gateway_auth_rtc，base/diff_anchor=c33e55f）

- identity：attempt1 / execution_id=79fa47d2f34e42f8b31f43ceb8cb52a9 / owner_id=claude_v2_6e1f7a8e7a46（2026-10-30T20:50:19+08:00 `attempt claim --replace-owner claude_v2_14b38abc09f2 --confirm-stopped`）。不得重复 start/reserve；再换会话须 `--replace-owner claude_v2_6e1f7a8e7a46 --confirm-stopped`。
- 未提交工作在 t006 WT：75 个路径（新文件均 `git add -N`）。最新快照 `.scratch/v2_orchestration/t006/t006_wt_snapshot_20261030T2116.patch`（`git diff --binary c33e55f`，可在干净 c33e55f 上 `git apply` 复原；旧快照 2032/2046 保留）。
- 已完成（截至本节）：
    - 前期 lane（agent/gateway/gwfix/auth）整合与主控修正，详见 t006 note.md「开工、lane 拆分与整合」。
    - 计划修订 9.3 实施（先 RED 8 项、后 GREEN）：删除 Gateway 活动聚合（`gateway/activity.py`、页面 activity 帧、`VISIBILITY_UPDATE` 下发与 Agent 分支、协议动作与载荷，schema 重导出）；Agent 心跳新增取自 Selkies 的 `unpaused_video_consumers` / `capture_running`，注册后立即发送首个心跳；Gateway visibility 端点改读最近上报值（未上报 503，新注册不继承）；Supervisor gateway_client 契约不变。gateway.md、stream_runtime.md、webrtc_remote_display spec 已同步。旧语义测试整项删除并在 note 写明理由（含 t004 遗留 schema/hardening 用例与 stream E2E 的 Gateway visibility 段）。
    - 主控审查修正 auth lane 遗留：`test_supervisor_recovery_e2e.py` 两个用例引用未定义 `stack`（运行即 NameError）；`test_supervisor_core_e2e.py` E402；两文件 format。
    - 主控审查发现并修复（21:16 记入 note）：Gateway 原把“answer 已转发”当成迁移成功并提交本代；现 Agent 等新 ICE 代真实接管（`ice_transport.wait_restart_commit`，20 秒）后回报新动作 `ice_restart_committed`，失败回报 error，Gateway 收到同代确认才提交，否则退避重试。RED→GREEN：Gateway 集成 2 项；真实 SDK `tests/e2e/test_stream_ice_commit_e2e.py`（修复后 Stream 镜像 sha256:a624db24… 1 passed，t004 ICE 失败回归 8 passed）。E2E lane 的 seed 早于此修复，合入后必须用当前源重建镜像复跑其 E2E。
- 已验证（WT 当前态，Docker E2E 前）：unit+integration 296 passed（`CBrowser_t006/.scratch/t006_commit/green_unit_integration.log`）；Ruff E,F,W,I 16 项（均为 main 基线 test_v2_api_subprocess E501）；ruff format、`git diff --check`、md_format 通过。
- E2E lane `t006_e2e2`（session ses_e73140c3bffezl2ty40n3Td8YL，WT /Users/karson/kar/code/CBrowser_t006_e2e2，分支 lane/t006_e2e2）：
    - r1（2026-10-30T21:07:06+08:00 派发，pid 30580，日志 `.scratch/v2_orchestration/t006_e2e2_r1.jsonl`）：交付 `tests/e2e/test_gateway_ac001_auth_e2e.py`（lane 自报 GREEN 1 passed，待主控复跑）、`test_gateway_ac003_media_e2e.py`（最后一次 FAILED：页面 25 秒无视频帧）、`tests/fixtures/gateway_probe/**`。2026-10-31T00:22:37 有一条外部消息进入该 opencode 会话（“你把那些容器都关了吗？那些用于开发测试使用的容器”），lane 答复其前缀对象已清理后，00:23:29 因模型服务端 400（Requests ending with a model turn are not supported）退出（cli_exit 1）。
    - 主控 2026-10-31T01:15:01+08:00 前后处理：删除 lane 遗留的无名容器 jovial_brattain（Docker SDK `caddy version` 探针未 remove，创建于 21:35，已核对命令来源）；同时观察到 pensive_satoshi 已不存在、new-api-local 约 00:19 停止，均非本会话操作。把 t006 WT 新增修复同步进 lane WT 并在 lane 分支记基线提交 3f19371。
    - r2（同 session 续行，pid 53017，日志 `.scratch/v2_orchestration/t006_e2e2_r2.jsonl`，prompt `.scratch/v2_orchestration/t006_dispatch/t006_e2e2_resume1.md`）：要求用当前源重建 Stream/Gateway 镜像、测试设施容器去掉冒用的 `com.cbrowser.managed-by=supervisor` 标签、AC-003 失败路径留存诊断后定位，继续 AC-003/005/007。中断后续行仍用 `dispatch.py --session ses_e73140c3bffezl2ty40n3Td8YL --unguard-changed`，不得新开重复 lane。
    - 用户反馈（2026-10-31T01:2x）：测试反复弹出 Chrome 窗口抢前台，要求无头或后台运行。主控中断 r2（pid 53017）并实测：无头官方 Chrome 156 切标签/最小化不改变 `document.visibilityState`，后台 `open -g` + CDP 方案的 `bring_to_front` 会抢前台，均不可用。定案：所有 E2E 一律 `headless=True`，禁止开窗/切前台/最小化；AC-007 可见性改为页面内覆盖 `document.visibilityState`/`hidden` 并派发 `visibilitychange`，由官方客户端自身发 STOP_VIDEO/START_VIDEO，服务端链路真实；“浏览器真实标签切换发出可见性事件”本次不重证，沿用 d013/s005（headful 实证），须在 note、评审与最终汇报中写明。
    - r3（2026-10-31T01:35:57+08:00 前派发，同 session，pid 59047，日志 `.scratch/v2_orchestration/t006_e2e2_r3.jsonl`，prompt `t006_dispatch/t006_e2e2_resume2.md`）。主控监控每 5 秒查杀非无头的测试 Chrome（`--remote-debugging-pipe` 且无 `--headless`）。
    - r4（2026-10-31T01:51:48+08:00，同 session，pid 69984，日志 `t006_e2e2_r4.jsonl`，prompt `t006_e2e2_resume3.md`）：主控中断 r3 并提示改用 t004 已验证的 `#overlayInput` 聚焦输入写法。注意：中断后须确认旧 opencode 进程已退出再续行（r3 的 59047 对 SIGINT 未及时退出，曾与 r4 重叠约 15 秒，经核对 session 消息无交叉写入，已 TERM 结束）。
    - r4 结果（06:11 核对）：AC-001、AC-003（双页各 +45 帧/2s、音频非零、selected pair 127.0.0.1:30000 直连 UDP mux、并发输入 "12"、Gateway SIGKILL 后 Browser PID 不变并 1s/2s 退避重注册）、AC-007（页面内可见性覆盖触发，端点 1/true→0/false→恢复）lane 自报 GREEN，待主控复跑；AC-005 暴露生产缺陷后停在该项。
    - 生产缺陷（主控核实并修复，见 t006 note）：Agent 以错误签名调用 Selkies `RTCApp.update_rtc_config` 且吞异常，`rtc_app` 未就绪时配置被静默跳过，relay-only 下 Stream 侧无 TURN。修复后真实 SDK `tests/e2e/test_stream_rtc_config_e2e.py` 通过（镜像 sha256:e3bb980a…），unit+integration 296 passed。lane 的 Mock 复现用例不采纳。同步工具改为 `.scratch/v2_orchestration/lane_resync.py`（lane 分支基线提交 31a30b3）。
    - r5（2026-10-31T06:17:00+08:00，同 session，pid 72835，日志 `t006_e2e2_r5.jsonl`，prompt `t006_e2e2_resume4.md`）：完成 AC-005（含 total-quota 负例）并用当前镜像复跑 AC-001/003/007。
    - r5 结果：修复后 relay-only 初始连接与第 2 代 Agent 侧提交已通，同 PC/Track 保持；卡在 Chrome 选中对新 ufrag 判据、初始连接偶发失败（疑为短轮换参数下初始 checking 期间即触发重启）与负例退避日志读取。主控 07:20 中断。
    - r6（2026-10-31T07:20:54+08:00，同 session，pid 89598，日志 `t006_e2e2_r6.jsonl`，prompt `t006_e2e2_resume5.md`）：按 t004 chrome_relay 流程从 restart offer 取 ufrag 判定新代选中对、首轮换到期安排在出帧之后、核对退避日志输出。
    - E2E lane 已收尾并 retire（交付合入 t006 WT，主控加强 AC-005/007 断言；证据 `.scratch/v2_orchestration/retired_worktrees/CBrowser_t006_e2e2/`）。
- 门禁：脚本 `.scratch/v2_orchestration/gates/run_gates_t006.sh`（每轮复制到 `CBrowser_t006/.scratch/t006_gates/run_roundN.sh`，环境 `GATE_ROOT/GATE_LANE/GATE_BASE=c33e55f/RUFF_BASELINE=16`）。round1–4 因 BuildKit 直连 Docker Hub 失败（已预拉前端与基础镜像、build 加重试）；round5 失败项与处置见 t006 note「门禁 round1–5 与修正」：stream_e2e 环境输入与 gateway 资源清单、OpenAPI 导出依赖已由主控修正，sup_lifecycle 6 项交 Gemini lane。
- supfix lane 已合入并 retire（主控回退 1 处计划外异常放宽）。门禁 round6（2026-10-31T11:12–11:32）：全部 Docker E2E 通过（runtime 13、stream 14、生命周期 6、启动恢复 2、容器图 8、网络策略 5、资源 5、Gateway E2E 5），contract 169、legacy 384、unit 255、integration 46；schema_openapi 失败为门禁脚本误用 `git diff --exit-code`（未提交改动必然有差），已修，导出 cmp 一致。证据 `CBrowser_t006/.scratch/t006_gates/round6/`。
- 主控核对 round6 原始证据发现 AC-005 缺口：relay-only 下第 1 代初始连接选中对为 prflx↔srflx，非双端 relay（只有重启后的新代 relay↔relay）；lane 测试初始判据被放宽掩盖。另 `tests/fixtures/gateway_probe/evidence.py` 写死已退役 worktree 绝对路径（主控已把证据移入 round6 目录并删除仓库外游离目录）。
- relay lane 已合入并 retire（主控收敛 Selkies 监控关闭逻辑、删 mock 单测）。门禁 round7 + round7b（Gateway E2E 复跑）全部通过：AC-005 第 1 代 relay↔relay，第 2/3 代轮换增量成立。七 AC 已按实证打勾，证据清单见 t006 note「门禁 round7 与 AC 实证打勾」；新增 finding d021–d023；strict preflight PASS。快照 `.scratch/v2_orchestration/t006/t006_wt_snapshot_20261031T1332.patch`。
- 运行中的子 agent（2026-10-31T13:33–13:34 派发，均 Gemini）：code reviewer pid 72293（日志 `t006_review_code_r1.jsonl`，报告 `docs/tasks/t006_v2_gateway_auth_rtc/review_code.md`）、test reviewer pid 72294（`t006_review_test_r1.jsonl`，`review_test.md`），两者在 t006 WT 只读运行，期间主控不得改 t006 WT；黑盒 lane pid 72951（验证 WT /Users/karson/kar/code/CBrowser_t006_blackbox，候选 98 文件 SHA 一致，日志 `t006_blackbox_r1.jsonl`，报告 `.scratch/t006_blackbox/report.md`）。
- 下一步：
    1. 等 E2E lane 交付；主控逐行审查并亲自复跑，核原始 JSON（帧数、candidate 类型/地址、Generation committed 日志、Cookie 属性、visibility 端点原始响应），增量合入 t006 WT 后 retire。
    2. 复制 `.scratch/v2_orchestration/gates/run_gates_template.sh` 快照跑全套门禁，补 Gateway 镜像构建与 Gateway E2E；Stream/Gateway/Supervisor/API 镜像用当前源重建（不得复用下方临时镜像）；testing.md 补 Gateway E2E 命令。
    3. 七 AC 按实证打勾 → `git add -N` → 渲染 review prompt → 独立黑盒（validation WT）+ code/test full review（两份报告同时 unguard）→ 处置 → handoff.json → finish → 一个执行 commit → attempt terminal/report → cleanup → integrate → 合并后门禁。
- 本地临时镜像（可由源码重建，未清理，禁止冒充门禁镜像）：t006-root-stream:commit-red / commit-green（本节 RED/GREEN 用）、t006-e2e-{api,gateway,stream,supervisor}:latest（上一轮已停 E2E lane 构建，handoff 先前漏记）、t006-agent-stream:1、t006-gateway-gateway:1、t006-gwfix-gateway:1、t006-gwfix-stream:1、t006-root-supervisor:cfgver、cbrowser-gate-*:r1、cbrowser-t005-*:final_round1。

### 遗留与环境

- 未触碰的既有对象：Docker 网络 net_9335ab04/net_d876dc01/net_e5052de6（无标签，来源不明）、容器 pensive_satoshi、test-shm-srv、旧 cbrowser 容器（t011/t012 前不动）。上一节记录的 `cbrowser-t003-bb-aece4d57-net` 在 21:00 核对时已不存在（非本会话删除）。
- p001（RecoveryCoordinator.tick 复杂度，minor）待办。p003（新增）：API 写入运行意愿后无代码调用 Supervisor 启动/停止 RPC，现有 E2E 均由测试直调 Supervisor RPC；须在 t007 或 t012 前补齐 API→Supervisor 协调并真实验证。p004（新增）：Stream 未配置计划 8.1 的每 Profile Selkies master/controller token（Selkies 仅 loopback、经认证隧道接入），t006 AC-001 的“master token 不返回前端”为空满足；须在 t007 前决定补齐 token 或以 ADR 记录取舍并经用户确认。
- 主机负载受 kkmail 等容器影响（曾致 Docker 引擎无响应），计时类测试与 t009 基准须记录负载；用户已授权引擎无响应时重启 OrbStack。
- 通用工具：prompt 外壳 `.scratch/v2_orchestration/prompts/`；lane 状态 `python3 .scratch/v2_orchestration/lane_status.py <jsonl> --text`；lane 管理 `lane_worktrees.py create/diff/retire`；门禁 runner 每轮复制快照，zsh 不对未加引号变量分词（多参数用 bash -c）。
- 后续 task 关键约束已写入各 task.md：t007 AC-008 `SELKIES_ENABLE_DUAL_MODE=false`；t008 AC-003 `SELKIES_FILE_TRANSFERS=none`；t014 AC-005 剪贴板策略锁定（二进制关闭）；每项须真实负例。Selkies 2.1.0 源码参考 `.scratch/v2_orchestration/t004_start_packet/upstream_selkies_2_1_0/`，Web 客户端参考 `.scratch/v2_orchestration/selkies_web_ref/`，t007 契约草案 `.scratch/v2_orchestration/t007/contract_draft.md`（可见性/活动上报内容按 9.3 改写）。容量/P95/8 小时/1000 次压力属 t009，未跑不得宣称通过。

## 2026-10-31T14:38:15+08:00 v2 架构计划执行交接（t006 已合入；t007 已开工）

- branch：main
- head_commit：ceb7f34（merge(t006)；执行 commit 251fa0f）
- 工作树：只剩主仓 main；无 task/lane 分支；无运行中的子 agent。
- 执行目标：按冻结队列 t006 → t007 → t008 → t013 → t014 → t009 → t010 → t011 → t012（`docs/runtime/goal_queue.json`）完成 `docs/v2_architecture_plan.md`，每 task 一个执行 commit，逐个合入本地 main；最终本机 OrbStack 部署、本机官方 Chrome 访问。禁止 push 与外部发布。`task.py goal-check`：GOAL_QUEUE_INCOMPLETE 1/9 closed。
- 已定决策：重试 2/10/30 秒、failure_count=4 阻断（ADR 008）；管理员密码 `data/secrets/admin_password`（只在生产首次启动读取）；公网 WebRTC/TURN 与原生 Linux x86_64 为 NOT_RUN / USER_WAIVED；性能按本机 OrbStack + Chrome 实跑；计划修订 9.3 已获批。
- 用户要求（2026-10-31）：所有浏览器测试一律无头、不得弹窗或抢前台（见 d023 与记忆）；实现工作交 Gemini 子代理（OpenCode `cpa/gemini-3.8-flash --variant high`），主控只做派发、整合、复核与门禁。用户 2026-10-31 追加：Gemini 额度用尽时改用 `opencode-go/deepseek-v4.1-flash`（两者均获准；wrapper 读 `OPENCODE_LANE_MODEL`/`OPENCODE_LANE_VARIANT`，DeepSeek `--variant high` 冒烟通过）。
- 主控会话 owner_id：`.scratch/v2_orchestration/claude_owner_id.txt`（claude_v2_6e1f7a8e7a46）。

### t006 结果

- attempt1 / execution 79fa47d2f34e42f8b31f43ceb8cb52a9：terminal=completed、report=done、执行 commit 251fa0f（first parent c33e55f）、merge ceb7f34；worktree exact cleanup，分支已删。
- 验证：门禁 round7 + round7b（Gateway E2E 复跑）全部通过；独立 Gemini 黑盒在逐字节等同候选的 WT 自建镜像，文档门禁同数通过且 7 条 AC 自写探针正负例通过；Full Round1 code/test 两路 PASS（5 minor 遗留 p005），check_review_status overall=PASS。合并后门禁（`.scratch/t006_postmerge/pm1/`）29/29 通过（contract 168+1 skipped 为主仓预期）。证据备份 `.scratch/v2_orchestration/retired_worktrees/CBrowser_t006{,_e2e2,_supfix,_relay,_blackbox}/`。
- 审查中发现并修复的生产缺陷：answer 转发即提交（d021）、Stream 侧 TURN 未进入 Selkies 且吞异常（d022）、对未建立 PC 发起重启、relay-only 初始连接非 relay、Supervisor 缺 coturn 时启动必然退出的 Stream（coturn 必需、gateway 基础设施可选）。
- 遗留：p001、p003（API→Supervisor 启停协调，t007/t012 前必须补）、p004（Selkies 每 Profile token，t007 前定案）、p005（t006 评审 minor，t007 内处理 f001/f003）。

### 门禁工具

- 门禁脚本 `.scratch/v2_orchestration/gates/run_gates_t006.sh`（每轮复制到目标 WT `.scratch/` 后执行，环境 `GATE_ROOT/GATE_LANE/GATE_BASE/RUFF_BASELINE`；构建带退避重试；Gateway E2E 需 `CBROWSER_GATEWAY_IMAGE`、`CBROWSER_CADDY_TEST_IMAGE`）。本机 BuildKit 直连 Docker Hub 不稳：构建失败先 `docker pull` 对应基础镜像或 `docker/dockerfile:1.4`（守护进程走代理可用）。
- lane 工具：`lane_worktrees.py create/diff/retire`、`lane_resync.py`（任务 WT → lane WT 同步并记 lane 基线提交）、`dispatch.py`（`--allow` 只给编辑权限，可写的既有文件必须同时 `--unguard`，否则 SHA 守卫会中断 lane；并行 reviewer 须互相 unguard 报告）。中断 lane 后须确认 opencode 进程已退出再续行。zsh 不对未加引号变量分词，多参数用 bash -c 或 Python。

### t007（前端会话）

- 2026-10-31T14:38:57+08:00 start + reserve：branch=t007_v2_frontend_sessions，worktree=/Users/karson/kar/code/CBrowser_t007，diff_anchor=077778f；attempt1 / execution_id=1a08cbc562094e73ae64c8039127ed0a / owner_id=claude_v2_6e1f7a8e7a46（14:39:02 claim）。不得重复 start/reserve。范围已扩展纳入 p003（API→Supervisor 启停，AC-009）与 p004（Selkies 每 Profile token，AC-010），见 077778f。

- 2026-10-31T14:41 派发四个并行 Gemini lane（各自 WT `/Users/karson/kar/code/CBrowser_t007_<lane>`，分支 `lane/t007_<lane>`，日志 `.scratch/v2_orchestration/t007_<lane>_r1.jsonl`，prompt `.scratch/v2_orchestration/t007/t007_<lane>_prompt.md`，启动器 `.scratch/v2_orchestration/launch_lane.py`）：spike_token（opencode pid 24318，Selkies token 机制实验，只出报告）、be_coord（24319，AC-009 API→Supervisor 协调 + SSE）、fe_shell（24317，前端外壳与 Profile/设置页）、fe_session（24316，浏览会话/适配层/冻结恢复诊断）。Docker E2E 用 mkdir 锁 `.scratch/v2_orchestration/docker_e2e.lock` 互斥。镜像基线为 t006 合并后门禁 `.scratch/t006_postmerge/pm1/images.env`。

- 截至 2026-10-31T15:10：spike_token 完成并 retire（d024，主控复跑 5 passed，task.md 未知契约已改写）；fe_shell 完成、复核（Vitest 60 passed、构建成功）、合入 t007 WT 暂存区并 retire；运行中：be_coord（opencode pid 24319）、fe_session（56175，session ses_e6f4e8671ffe2gNTfGG7sXQ1zH，第 3 次续行）、stream_tokens（60155，AC-008/AC-010）。监控用 `python3 .scratch/v2_orchestration/watch_lanes.py`（读 `watch_pids.txt`）。镜像清单改名 `images_env.txt`（`*.env` 被 lane 读权限拒绝）。

- 编排事故（详见 t007 note）：首次批量派发重复启动导致 fe_shell/be_coord 双实例（已处理）；误在 t007 任务分支生成中间提交 acd3832，已 `git reset --soft 077778f` 撤销（改动保留、HEAD 回到 diff_anchor）。今后合入 lane 交付用 Python 逐文件复制，不对任务 WT 运行 lane_resync。

- 2026-10-31T16:2x：fe_session 已合入 t007 WT 并 retire（合并前端 Vitest 72 passed、构建成功）。be_coord 与 stream_tokens 自约 15:37 起模型请求挂起（Gemini 额度耗尽），主控停止进程、按前缀清理两者遗留的 10 个测试容器与网络，改用 `opencode-go/deepseek-v4.1-flash` 在原会话续行：be_coord opencode pid 92666（session ses_e6f4e8ca8ffeBbx5Peyv4NJHR6，日志 `t007_be_coord_r2.jsonl`），stream_tokens pid 92665（session ses_e6f37c365ffeqir0wNKzeCRmLv，日志 `t007_stream_tokens_r2.jsonl`）。`watch_lanes.py` 已加日志 10 分钟无更新的 STALL 报警。

- 2026-10-31T16:5x：be_coord、stream_tokens 已复核并合入 t007 WT（后端 unit+integration 336 passed），全部 lane WT 已 retire；t007 WT 新文件已 `git add -N`（lane 种子只含已跟踪/意图添加的文件）。派发完整前端真实栈 E2E lane `t007_fe_e2e`（DeepSeek，opencode pid 14471，session ses_e6ed7fc48ffetsFEvPOyA6HQW9，WT /Users/karson/kar/code/CBrowser_t007_fe_e2e，日志 `t007_fe_e2e_r1.jsonl`）。待办：API Runtime Coordinator 为可选启用（`CBROWSER_SUPERVISOR_URL` + `CBROWSER_REQUIRE_SUPERVISOR=1`），t012 生产编排必须设置；`last_coordinator_error` 仅存内存。

- 2026-10-31T17:42:33+08:00：fe_e2e 完成（完整真实栈无头 E2E 5 passed，修复 PUT→PATCH、协调错误展示、诊断操作），已复核、合入 t007 WT 并 retire（证据 `CBrowser_t007/.scratch/lane_evidence/fe_e2e/`）；主控修正生成类型未重生成与硬编码文案。t007 全量门禁 r1 运行中（`.scratch/v2_orchestration/gates/run_gates_t007_r1.sh`，输出 `CBrowser_t007/.scratch/project_gates/r1/summary.txt`，持有 Docker 锁）。主控评审另发现两项 important，派 DeepSeek lane：adapter（opencode pid 30796，session ses_e6eac8d22ffeQBOIwi5BxNqCg6，WT `/Users/karson/kar/code/CBrowser_t007_adapter`，适配层收敛为 `adapter.ts` 单一来源）、auth（pid 32410，WT `/Users/karson/kar/code/CBrowser_t007_auth`，登录守卫/401 跳转/SSE 仅认证后运行）。t007 finalization 文档（frontend blueprint、profile_management spec、architecture 5.5、旧 chrome_external_tabs spec 归档）已写入 t007 WT。p005 不在 t007 契约内，保持开放。

- 2026-10-31T20:41:00+08:00：adapter、auth lane 已合入 t007 WT 并 retire（Vitest 82 passed）。门禁 r2（`CBrowser_t007/.scratch/project_gates/r2/`）除 coordinator E2E 因门禁脚本缺依赖外全部通过，补依赖复跑 1 passed（`r2_rerun/`）；门禁模板已修 PYTHONPATH/依赖、调整 vendor→build 顺序、增加前端生成类型漂移检查。lane 曾把编排 Docker 锁写进测试导致门禁自锁，已删除。AC 复核发现阻断缺口，派 DeepSeek lane：display（opencode pid 13335，session ses_e6e060640ffeZ0Svj3UCKCKDSJ，AC-004 Stream 分辨率写死 1920×1080 与“明确应用”）、media（pid 13336，session ses_e6e060645ffe92qomNF97ILFR5，经完整应用的可见性、AC-005 独立静音/内部标签页同步/音频故障状态）。

- 读 `docs/tasks/t007_v2_frontend_sessions/task.md` 与 `.scratch/v2_orchestration/t007/contract_draft.md`（已按 9.3/p003/p004 修订）。开工前定案 p004（Selkies token）与 p003 是否纳入 t007 范围；t007 AC-008 显式 `SELKIES_ENABLE_DUAL_MODE=false`；前端适配层须在官方 `setConfiguration` 后保持 Gateway 下发配置（d022）；可复用 `tests/fixtures/gateway_probe/` 拓扑做真实栈 E2E（无头）。

- 未触碰的既有对象：Docker 网络 net_9335ab04/net_d876dc01/net_e5052de6（来源不明）、容器 test-shm-srv、旧 cbrowser 容器（t011/t012 前不动）。本地临时镜像（t006-*、cbrowser-gate-*、t005-\* 等）可由源码重建，未清理。

---

# 项目交接记录（最新）

本文件只保留当前有效一节。过时段落迁入 `docs/archive/handoff.md`（上一节 2026-10-31T14:38:15+08:00 已于本次交接追加归档）。

## 2026-11-01T07:17:23+08:00 主控交接给下一位 coding agent（t007 已提交未合并；队列 2/9）

### 一、当前状态（接手先读，先核对再动手）

- branch：main，工作区干净（本 handoff 提交之后）。t007 **尚未合入 main**：`task.py integrate` 曾把合并结果暂存，合并后门禁开跑后被用户叫停，主控按工具指引 `git merge --abort` 撤销，main 回到合并前状态。
- t007 执行 commit：`faee1f3`，分支 `t007_v2_frontend_sessions`（first parent = diff_anchor `077778f`），已 finish（task 目录在该分支的 `docs/archive/tasks/t007_v2_frontend_sessions/`）。identity：attempt=1，execution_id=`1a08cbc562094e73ae64c8039127ed0a`，owner_id=`claude_v2_6e1f7a8e7a46`（`.scratch/v2_orchestration/claude_owner_id.txt`）。ledger 已有 terminal=completed、report=done（sha faee1f3）、worktree cleanup 完成；`task.py recovery t007` = phase closed。
- 工作树：只剩主仓 main；t007 与全部 lane worktree 已 remove + prune；无运行中的子代理；Docker 锁 `.scratch/v2_orchestration/docker_e2e.lock` 已释放；无本任务残留容器/网络。
- `task.py goal-check`：GOAL_QUEUE_INCOMPLETE 2/9 closed。

### 二、立即要做的事（按顺序）

1. 重新集成 t007（幂等重入）：`python3 .repo_template/scripts/task.py integrate --attempt 1 --execution-id 1a08cbc562094e73ae64c8039127ed0a t007`，输出“合并结果已准备但尚未 commit”。此时**不要改 main 上任何受控文件**（会混入 merge commit 或被 staged 范围校验拒绝）。

2. 跑合并后门禁（约 35 分钟）：

    ```bash
    O=/Users/karson/kar/code/CBrowser/.scratch/v2_orchestration
    cp $O/gates/run_gates_t007.sh $O/gates/run_gates_t007_pm2.sh
    until mkdir $O/docker_e2e.lock 2>/dev/null; do sleep 20; done
    cd /Users/karson/kar/code/CBrowser && GATE_ROOT=/Users/karson/kar/code/CBrowser \
      GATE_LANE=/Users/karson/kar/code/CBrowser/.scratch/t007_postmerge GATE_BASE=<integrate 前的 main HEAD> RUFF_BASELINE=0 \
      bash $O/gates/run_gates_t007_pm2.sh pm2 > $O/gates/t007_pm2.out 2>&1
    rmdir $O/docker_e2e.lock
    grep -v " rc=0 " .scratch/t007_postmerge/pm2/summary.txt
    ```

    预期：主仓 contract 可能为 168 passed + 1 skipped（t006 合并后同样，属主仓预期）；`health` 检查旧 cbrowser 容器 56661 端口。已知偶发项见第六节，失败先单独复跑归因，不要放宽断言。

3. 门禁通过：`python3 .repo_template/scripts/task.py integrate --attempt 1 --execution-id 1a08cbc562094e73ae64c8039127ed0a --continue t007`（生成 merge commit 并删除已合入分支）。出现真实失败：`git merge --abort`，按流程处理（已提交分支不得擅自 amend，需用户同意）。

4. 合并后更新本文件并单独提交 docs；`task.py goal-check` 核对进度。

5. 开 t008（见第四节）。

### 三、执行目标与硬约束（用户原始要求，全部仍然有效）

- 目标：按冻结队列 t006 → t007 → t008 → t013 → t014 → t009 → t010 → t011 → t012（`docs/runtime/goal_queue.json`，不得改成员与顺序；t013/t014 串行）完成 `docs/v2_architecture_plan.md`；每 task 一个执行 commit，逐个合入本地 main；最终本机 OrbStack 部署、本机官方 Google Chrome 访问（登录 → 选 Profile → WebRTC 浏览）。完成判据：14 个 task 全部 done 并合入；只剩 main 分支与主 worktree；旧 VNC/RFB/原生桌面移除；生产构建本机可用；门禁与黑盒主控复核；`task.py goal-check` 输出 GOAL_QUEUE_COMPLETE。最终报告列每 task 的 commit、验证证据、USER_WAIVED 项与残余风险。
- 只能写 `~/kar/code` 以内；临时文件写各 worktree 的 `.scratch/`，不写 /tmp、~/.cache。
- 管理员密码 `/Users/karson/kar/code/CBrowser/data/secrets/admin_password`（0600，gitignore）：只在生产首次启动读取并以 Argon2id 保存；明文不得进日志、报告、测试快照；测试一律每次随机生成密码。缺其他 secret 停下来问用户，禁止自设默认值。
- 公网 WebRTC/TURN 与原生 Linux x86_64 记 NOT_RUN / USER_WAIVED。只部署本机，禁止 git push 与任何外部发布。
- task 状态只经 `.repo_template/scripts/task.py`；TDD 先红后绿；禁止就地改旧测试预期（旧语义失效整项删除并说明、另写新测试；本 task 新增的测试可补强）。`.repo_template` 工具链缺陷报告用户，不自行绕过或修改。
- task 执行 commit 的 first parent 必须是 diff_anchor；禁止在 task worktree merge/rebase main。时间戳一律 `date -Iseconds` 实取。
- Docker 只清理本任务前缀且标签核对过的对象；不碰其他项目容器（kkmail、new-api、haiwa-bot、lobechat 等）；来源不明网络 net_9335ab04/net_d876dc01/net_e5052de6、容器 test-shm-srv、旧 cbrowser 容器在 t011/t012 前不动。用户已授权 Docker 引擎无响应时重启 OrbStack。
- worktree 用完必须 `git worktree remove` + `git worktree prune`；删除前备份 `.scratch` 证据。发现 commit/worktree 混入无关改动立即停止报告用户。
- 每个阶段更新本文件（只留最新一节，旧节追加到 `docs/archive/handoff.md`）并在 main 提交 docs；记录子代理 PID/session。
- 用户偏好（`~/.claude/projects/-Users-karson-kar-code-CBrowser/memory/`）：所有浏览器测试一律无头，不得弹窗或抢前台；实现交子代理，主控只派发、整合、复核、门禁；子代理模型 `cpa/gemini-3.8-flash --variant high`，额度用尽改 `opencode-go/deepseek-v4.1-flash --variant high`（两者均获批；Gemini 早已耗尽，t007 全程用 DeepSeek）。
- 全局约定：中文简洁回复；不用 `git reset --hard` / `git checkout --` / 批量删除（除非用户确认）；新文件 snake_case；4 空格；日志不用 print；密钥不硬编码。

### 四、后续 task 要点

- t008（Artifacts/CDP 自动化，`docs/tasks/t008_v2_artifacts_automation/task.md`，4 条 AC）：Artifact 上传/下载/删除与配额、外部自动化经认证入口 → Supervisor → UDS → loopback CDP、Selkies `file_transfers=none`（Stream 入口已设 `SELKIES_FILE_TRANSFERS=none`，需补测试证据）、Agent 重启后扫描补登下载。前端 `/profiles/:id/files` 与 `/automation/:id` 目前是占位页（`features/artifacts`、`features/automation`）；设置页与新建页残留硬编码文案见 p007 可顺带收口。t008 需以 t007 合入后的 main 为基线开工。
- t013（复制/重置）、t014（剪贴板与完整输入）、t009（整机验收：容量/P95/8 小时/1000 次输入）、t010（旧数据迁移，先备份可恢复）、t011（移除旧 VNC/RFB/原生桌面与旧 UI 组件、旧测试）、t012（Compose 生产交付）。
- t012 必须：API 设置 `CBROWSER_SUPERVISOR_URL` + `CBROWSER_SUPERVISOR_TOKEN_FILE` + `CBROWSER_REQUIRE_SUPERVISOR=1`（未配置时 API 只显式禁用协调）；生产镜像构建固定 `scripts/vendor_selkies_web.py` → `npm run build`（p010；清单现位于 tests/fixtures 下，宜迁出）；处理 p006（`agent_secret.txt` 仍在挂进 Browser 的 runtime 目录）。

### 五、t007 结果摘要（细节见 t007 分支 `docs/archive/tasks/t007_v2_frontend_sessions/note.md`）

- 交付：React Router 7 外壳 + 登录守卫（`RequireAuth`、`/login?next=` 同源校验）、OpenAPI 生成类型（`npm run generate:api`，禁止手写）、TanStack Query + SSE（事件 id `<epoch>:<seq>`，跨进程发快照）、页面独立 `?profileId=`、官方 Selkies 2.1.0 iframe + 单一来源适配层（`features/browser-session/adapter.ts` 经 `vite.selkies.config.ts` 构建为 IIFE `dist/selkies/selkies_adapter.js`；vendor 脚本只注入标签）、会话阶段诊断与独立音频状态、冻结恢复重建、ICE disconnected 5 秒宽限、每页静音（官方 pipelineControl STOP/START_AUDIO）、显示尺寸“应用并重启”、API Runtime Coordinator 驱动 Supervisor（p003 闭环）、每 Profile Selkies token + 安全模式 + Agent HELLO 代注入（d024，p004 闭环）、token 文件只挂给 Stream 且每实例新文件名 `runtime/.secrets/<profile>/selkies_tokens_<instance>.json`、Stream 分辨率取自 Profile 配置。
- 验证：最终门禁 r5 全绿（前端 E2E 21/22，唯一失败为 AC-001 静止画面出帧抖动，复跑 2/2，p013）；独立 DeepSeek 黑盒 r1 AC-001..010 自写探针全 PASS；Full review 5 轮，Round 5 两路 PASS 零 finding（reviewed_scope a006b995998b9c28）。
- 遗留 pending（在 t007 分支，合入后进 main）：p005（t006 minor）、p006（agent_secret 挂进 Browser）、p007（前端残留硬编码文案）、p008（Agent 隧道未触发 Selkies RESUMED）、p009（multi_viewer 固定 sleep 抖动）、p010（生产构建 vendor 步骤，归 t012）、p011（评审 minor）、p012（同 tab 驱逐关闭码偶发 1006）、p013（AC-001 静止画面出帧抖动）。
- 证据备份：`.scratch/v2_orchestration/retired_worktrees/CBrowser_t007/`（`project_gates/r1..r5`、`r*_rerun`、`r4_final`、`lane_evidence/<lane>/`、`t007_master/` 主控 RED/GREEN 与调试记录、黑盒 `lane_evidence/blackbox_r1/`）；lane 会话日志 `.scratch/v2_orchestration/t007_*_r*.jsonl`，prompt 在 `.scratch/v2_orchestration/t007/`。被叫停的合并后门禁残留输出 `.scratch/t007_postmerge/pm1/`（只到镜像构建，作废）。

### 六、已知偶发与环境注意（复跑归因，不放宽断言）

- `test_stream_runtime_e2e.py::test_stream_runtime_multi_viewer_e2e` 固定 sleep 2 秒（p009）；`test_browser_runtime_e2e.py::test_ac006_minimal_privileges_and_access_control` 偶发 Pulse 连接拒绝；`test_supervisor_namespace_policy_e2e.py` 偶发公网 IPv4 出站超时；`test_frontend_app_e2e.py::test_ac001_ac006...` 静止画面不出新帧（p013）；`test_stream_selkies_tokens_e2e.py` 同 tab 驱逐关闭码偶发 1006（p012）。
- 验证 worktree 内跑模板 contract 会有 2 项 `.env` 链接用例失败（TMPDIR 位于已登记 worktree 内，环境差异）。
- 本机 BuildKit 直连 Docker Hub 不稳：构建失败先 `docker pull` 基础镜像；用 sha256 当 FROM 会被当成远程仓库，需先 `docker tag`。
- 本机 OrbStack 单文件 bind mount：同一宿主路径被原子替换后立刻启动的新容器可能看到失效条目（t007 已改为每实例新文件名规避）。

### 七、编排工具与踩坑（`.scratch/v2_orchestration/`）

- 门禁：`gates/run_gates_t007.sh`（每轮复制为 `_rN.sh` 再跑；环境 `GATE_ROOT/GATE_LANE/GATE_BASE/RUFF_BASELINE`；镜像 ID 写入 `<lane>/images.env`）。顺序：构建镜像 → npm ci → Vitest → vendor → build（随后还原 `src/frontend/tsconfig.tsbuildinfo`）→ contract/legacy/unit/integration → Runtime/Stream/Supervisor/Gateway/前端 E2E → schema 与前端生成类型漂移 → ruff → md_format → diff_check → health → task list。t008 起复制一份按需增删测试文件。
- Docker 互斥：运行任何 Docker E2E 前 `mkdir docker_e2e.lock`（原子），结束 `rmdir`；**测试代码内不得自带锁或引用 `.scratch` 编排目录**（t007 曾因此门禁自锁）。
- lane：`lane_worktrees.py create <task_wt> <lane>` / `retire <lane_wt> <backup_dir>`；`launch_lane.py LANE WT PROMPT LOG OUT [ALLOW_GLOB...]`（环境变量 `OPENCODE_LANE_MODEL=opencode-go/deepseek-v4.1-flash OPENCODE_LANE_VARIANT=high`）；续行用 `dispatch.py ... --session <ses_id> --unguard-changed`（**lane 自己新建的文件若不加 `--unguard-changed` 会被 SHA 守卫误杀**）；并行 reviewer 须互相 unguard 两份报告，门禁并发时还要 unguard `tsconfig.tsbuildinfo` 与 schema 导出文件。prompt 模板：`t007/t007_fe_e2e_prompt.md` 前 30 行（写域与质量规则）+ `t007/lane_*_body.md` + `t007/common_tail.md`。
- 合入 lane：在 lane WT 比对 `git show HEAD:<f>` 与任务 WT 当前文件确认无冲突后 `cp -p`，新文件 `git add -N`；**不要对任务 WT 运行 `lane_resync.py`**。lane 常见问题：改测试夹具 Docker 前缀、未跑 ruff、模型连接 ECONNRESET（同会话续跑即可）。
- review：`render_review_prompts.py --task-dir ... --out-dir ...` 渲染后前置主控约束；`check_review_status.py` 判 PASS。**审查指纹包含 `docs/specs_index.md` 等非过程文档**（排除 note/handoff/review 报告/pending/findings/archive/.scratch），PASS 后改这些会变 stale；review 上限 5 轮，超出需用户批准。处置表只接受 `tNNN_code_fNNN` / `tNNN_test_fNNN` 编号。
- 收尾：handoff.json（task 目录）→ `preflight --require-verified --owner-id` → `finish` → 一个执行 commit → `attempt terminal --status completed` → `attempt report --status done --sha` → 备份 `.scratch` → `cleanup-worktree` → `integrate`（暂存）→ 合并后门禁 → `integrate --continue`。
- 工具链缺陷（已报告用户，本次经用户同意由主控补完）：`cleanup-worktree` 调用 `git worktree remove` 60 秒超时（含 node_modules/public 的前端 worktree），留下半删目录与 prunable 登记并提示“数据不一致”。后续若再超时须报告用户。
- zsh 不对未加引号变量分词，多参数循环用 `bash -c`；后台命令里用绝对路径（会话 cwd 可能变化）。

### 八、本地临时对象（可按前缀清理）

- 镜像：`t007-*`（lane 与门禁构建）、`cbrowser-gate-*`、`t007-master-dbg-stream:1`、`t007-master-dbg-stream-base:1`、`t007-master-supervisor:tokinst`、`t007-master-api:tokinst`、`t006-*`、`t005-*` 等，均可由源码重建，未清理。
- `.scratch/selkies_wheels/`：固定 Selkies 2.1.0 wheel 缓存（vendor 脚本默认路径）。
- `.scratch/v2_orchestration/handoff_backup/`：本次撤销合并前的 handoff 文件备份。

## 2026-11-01T07:58:10+08:00 t007 已合入，准备 t001–t007 累计四模型审阅

### 一、当前状态

- branch：main；head_commit：`f420d7fb0767d1768a22a57ce552b21d86d62a72`（t007 merge，本文另行提交）。
- t001–t007 全部 done 且已合入 main。t007 执行 commit `faee1f3`，本次 merge commit `f420d7f`；`t007_v2_frontend_sessions` 已由 integrate 删除，仅剩 main 与主 worktree。
- t007 exact identity：attempt=1，execution_id=`1a08cbc562094e73ae64c8039127ed0a`；原执行 owner_id=`claude_v2_6e1f7a8e7a46`。本次沿原 identity 完成集成，未创建新 attempt。
- 合并后门禁：`.scratch/t007_postmerge/codex_pm1/summary.txt`，35 步全部 rc=0；六个镜像当前源码构建，ID 在同目录 `images.env`。契约 168 passed / 1 skipped，旧后端 384、unit 307、integration 55、Vitest 105；Runtime 13、Stream 19、Supervisor 生命周期 6 / 启动恢复 2 / 拓扑 8 / 网络策略 5 / 资源 5、Gateway 5、前端 E2E 22 全部通过。本轮无失败复跑；schema/codegen、Ruff、文档格式、diff、既有服务 health 与模板状态均通过。
- 门禁 runner 快照：`.scratch/v2_orchestration/gates/run_gates_t007_codex_pm1.sh`；输出 `.scratch/v2_orchestration/gates/t007_codex_pm1.out`。Docker 测试锁已释放。
- `task.py goal-check`：t006/t007 均 integrated，GOAL_QUEUE_INCOMPLETE 2/9 closed；后续七项无 attempt。

### 二、本次后续工作

1. 用户要求按 `/Users/karson/kar/code/my_file/coding_agent/skills_mine/my-review/SKILL.md` 将 t001–t007 **全部累计改动合在一起审阅，不按 task 拆分**。
2. 四路：Codex `gpt-6.1-sol`、OpenCode `cpa/gemini-3.8-flash`、`opencode-go/deepseek-v4.1-flash`、`opencode-go/muse-spark-1.3-contributor`；思考强度全部 high。用户确认每路上限 60 分钟。
3. 每路审同一冻结累计范围，以 t001 diff_anchor `3c8bdbc55570e85aaeb6365a3d512da9c0ce180c` 为基线，target 为本次交接提交后的 main。只读源码，仅写独立 review 报告；不做修复、不启动 t008、不 push。
4. my-review 原脚本仅内置 Claude/Kimi/Grok 路由；已向用户说明按指定 Codex/OpenCode 派发，保留输出目录、独立报告与超时状态流程。
5. 审阅完成后报告各路实际完成/超时情况与文件位置，不合并各路结论。审阅产物位置与运行状态以 `docs/reviews/review_*/_meta/_meta.json` 为准。

### 三、执行目标与硬约束（原升级目标；本次只授权合入 t007 与累计审阅）

- 目标：按冻结队列 t006 → t007 → t008 → t013 → t014 → t009 → t010 → t011 → t012（`docs/runtime/goal_queue.json`，不得改成员与顺序；t013/t014 串行）完成 `docs/v2_architecture_plan.md`；每 task 一个执行 commit，逐个合入本地 main；最终本机 OrbStack 部署、本机官方 Google Chrome 访问（登录 → 选 Profile → WebRTC 浏览）。完成判据：14 个 task 全部 done 并合入；只剩 main 分支与主 worktree；旧 VNC/RFB/原生桌面移除；生产构建本机可用；门禁与黑盒主控复核；`task.py goal-check` 输出 GOAL_QUEUE_COMPLETE。最终报告列每 task 的 commit、验证证据、USER_WAIVED 项与残余风险。
- 只能写 `~/kar/code` 以内；临时文件写各 worktree 的 `.scratch/`，不写 /tmp、~/.cache。
- 管理员密码 `/Users/karson/kar/code/CBrowser/data/secrets/admin_password`（0600，gitignore）：只在生产首次启动读取并以 Argon2id 保存；明文不得进日志、报告、测试快照；测试一律每次随机生成密码。缺其他 secret 停下来问用户，禁止自设默认值。
- 公网 WebRTC/TURN 与原生 Linux x86_64 记 NOT_RUN / USER_WAIVED。只部署本机，禁止 git push 与任何外部发布。
- task 状态只经 `.repo_template/scripts/task.py`；TDD 先红后绿；禁止就地改旧测试预期（旧语义失效整项删除并说明、另写新测试；本 task 新增的测试可补强）。`.repo_template` 工具链缺陷报告用户，不自行绕过或修改。
- task 执行 commit 的 first parent 必须是 diff_anchor；禁止在 task worktree merge/rebase main。时间戳一律 `date -Iseconds` 实取。
- Docker 只清理本任务前缀且标签核对过的对象；不碰其他项目容器（kkmail、new-api、haiwa-bot、lobechat 等）；来源不明网络 net_9335ab04/net_d876dc01/net_e5052de6、容器 test-shm-srv、旧 cbrowser 容器在 t011/t012 前不动。用户已授权 Docker 引擎无响应时重启 OrbStack。
- worktree 用完必须 `git worktree remove` + `git worktree prune`；删除前备份 `.scratch` 证据。发现 commit/worktree 混入无关改动立即停止报告用户。
- 每个阶段更新本文件（只留最新一节，旧节追加到 `docs/archive/handoff.md`）并在 main 提交 docs；记录子代理 PID/session。
- 用户偏好（`~/.claude/projects/-Users-karson-kar-code-CBrowser/memory/`）：所有浏览器测试一律无头，不得弹窗或抢前台；实现交子代理，主控只派发、整合、复核、门禁；子代理模型 `cpa/gemini-3.8-flash --variant high`，额度用尽改 `opencode-go/deepseek-v4.1-flash --variant high`（两者均获批；Gemini 早已耗尽，t007 全程用 DeepSeek）。
- 全局约定：中文简洁回复；不用 `git reset --hard` / `git checkout --` / 批量删除（除非用户确认）；新文件 snake_case；4 空格；日志不用 print；密钥不硬编码。

### 四、后续 task 要点

- t008（Artifacts/CDP 自动化，`docs/tasks/t008_v2_artifacts_automation/task.md`，4 条 AC）：Artifact 上传/下载/删除与配额、外部自动化经认证入口 → Supervisor → UDS → loopback CDP、Selkies `file_transfers=none`（Stream 入口已设 `SELKIES_FILE_TRANSFERS=none`，需补测试证据）、Agent 重启后扫描补登下载。前端 `/profiles/:id/files` 与 `/automation/:id` 目前是占位页（`features/artifacts`、`features/automation`）；设置页与新建页残留硬编码文案见 p007 可顺带收口。t008 需以 t007 合入后的 main 为基线开工。
- t013（复制/重置）、t014（剪贴板与完整输入）、t009（整机验收：容量/P95/8 小时/1000 次输入）、t010（旧数据迁移，先备份可恢复）、t011（移除旧 VNC/RFB/原生桌面与旧 UI 组件、旧测试）、t012（Compose 生产交付）。
- t012 必须：API 设置 `CBROWSER_SUPERVISOR_URL` + `CBROWSER_SUPERVISOR_TOKEN_FILE` + `CBROWSER_REQUIRE_SUPERVISOR=1`（未配置时 API 只显式禁用协调）；生产镜像构建固定 `scripts/vendor_selkies_web.py` → `npm run build`（p010；清单现位于 tests/fixtures 下，宜迁出）；处理 p006（`agent_secret.txt` 仍在挂进 Browser 的 runtime 目录）。

### 五、t007 结果摘要（细节见 t007 分支 `docs/archive/tasks/t007_v2_frontend_sessions/note.md`）

- 交付：React Router 7 外壳 + 登录守卫（`RequireAuth`、`/login?next=` 同源校验）、OpenAPI 生成类型（`npm run generate:api`，禁止手写）、TanStack Query + SSE（事件 id `<epoch>:<seq>`，跨进程发快照）、页面独立 `?profileId=`、官方 Selkies 2.1.0 iframe + 单一来源适配层（`features/browser-session/adapter.ts` 经 `vite.selkies.config.ts` 构建为 IIFE `dist/selkies/selkies_adapter.js`；vendor 脚本只注入标签）、会话阶段诊断与独立音频状态、冻结恢复重建、ICE disconnected 5 秒宽限、每页静音（官方 pipelineControl STOP/START_AUDIO）、显示尺寸“应用并重启”、API Runtime Coordinator 驱动 Supervisor（p003 闭环）、每 Profile Selkies token + 安全模式 + Agent HELLO 代注入（d024，p004 闭环）、token 文件只挂给 Stream 且每实例新文件名 `runtime/.secrets/<profile>/selkies_tokens_<instance>.json`、Stream 分辨率取自 Profile 配置。
- 验证：最终门禁 r5 全绿（前端 E2E 21/22，唯一失败为 AC-001 静止画面出帧抖动，复跑 2/2，p013）；独立 DeepSeek 黑盒 r1 AC-001..010 自写探针全 PASS；Full review 5 轮，Round 5 两路 PASS 零 finding（reviewed_scope a006b995998b9c28）。
- 遗留 pending（在 t007 分支，合入后进 main）：p005（t006 minor）、p006（agent_secret 挂进 Browser）、p007（前端残留硬编码文案）、p008（Agent 隧道未触发 Selkies RESUMED）、p009（multi_viewer 固定 sleep 抖动）、p010（生产构建 vendor 步骤，归 t012）、p011（评审 minor）、p012（同 tab 驱逐关闭码偶发 1006）、p013（AC-001 静止画面出帧抖动）。
- 证据备份：`.scratch/v2_orchestration/retired_worktrees/CBrowser_t007/`（`project_gates/r1..r5`、`r*_rerun`、`r4_final`、`lane_evidence/<lane>/`、`t007_master/` 主控 RED/GREEN 与调试记录、黑盒 `lane_evidence/blackbox_r1/`）；lane 会话日志 `.scratch/v2_orchestration/t007_*_r*.jsonl`，prompt 在 `.scratch/v2_orchestration/t007/`。被叫停的合并后门禁残留输出 `.scratch/t007_postmerge/pm1/`（只到镜像构建，作废）。

### 六、已知偶发与环境注意（复跑归因，不放宽断言）

- `test_stream_runtime_e2e.py::test_stream_runtime_multi_viewer_e2e` 固定 sleep 2 秒（p009）；`test_browser_runtime_e2e.py::test_ac006_minimal_privileges_and_access_control` 偶发 Pulse 连接拒绝；`test_supervisor_namespace_policy_e2e.py` 偶发公网 IPv4 出站超时；`test_frontend_app_e2e.py::test_ac001_ac006...` 静止画面不出新帧（p013）；`test_stream_selkies_tokens_e2e.py` 同 tab 驱逐关闭码偶发 1006（p012）。
- 验证 worktree 内跑模板 contract 会有 2 项 `.env` 链接用例失败（TMPDIR 位于已登记 worktree 内，环境差异）。
- 本机 BuildKit 直连 Docker Hub 不稳：构建失败先 `docker pull` 基础镜像；用 sha256 当 FROM 会被当成远程仓库，需先 `docker tag`。
- 本机 OrbStack 单文件 bind mount：同一宿主路径被原子替换后立刻启动的新容器可能看到失效条目（t007 已改为每实例新文件名规避）。

### 七、编排工具与踩坑（`.scratch/v2_orchestration/`）

- 门禁：`gates/run_gates_t007.sh`（每轮复制为 `_rN.sh` 再跑；环境 `GATE_ROOT/GATE_LANE/GATE_BASE/RUFF_BASELINE`；镜像 ID 写入 `<lane>/images.env`）。顺序：构建镜像 → npm ci → Vitest → vendor → build（随后还原 `src/frontend/tsconfig.tsbuildinfo`）→ contract/legacy/unit/integration → Runtime/Stream/Supervisor/Gateway/前端 E2E → schema 与前端生成类型漂移 → ruff → md_format → diff_check → health → task list。t008 起复制一份按需增删测试文件。
- Docker 互斥：运行任何 Docker E2E 前 `mkdir docker_e2e.lock`（原子），结束 `rmdir`；**测试代码内不得自带锁或引用 `.scratch` 编排目录**（t007 曾因此门禁自锁）。
- lane：`lane_worktrees.py create <task_wt> <lane>` / `retire <lane_wt> <backup_dir>`；`launch_lane.py LANE WT PROMPT LOG OUT [ALLOW_GLOB...]`（环境变量 `OPENCODE_LANE_MODEL=opencode-go/deepseek-v4.1-flash OPENCODE_LANE_VARIANT=high`）；续行用 `dispatch.py ... --session <ses_id> --unguard-changed`（**lane 自己新建的文件若不加 `--unguard-changed` 会被 SHA 守卫误杀**）；并行 reviewer 须互相 unguard 两份报告，门禁并发时还要 unguard `tsconfig.tsbuildinfo` 与 schema 导出文件。prompt 模板：`t007/t007_fe_e2e_prompt.md` 前 30 行（写域与质量规则）+ `t007/lane_*_body.md` + `t007/common_tail.md`。
- 合入 lane：在 lane WT 比对 `git show HEAD:<f>` 与任务 WT 当前文件确认无冲突后 `cp -p`，新文件 `git add -N`；**不要对任务 WT 运行 `lane_resync.py`**。lane 常见问题：改测试夹具 Docker 前缀、未跑 ruff、模型连接 ECONNRESET（同会话续跑即可）。
- review：`render_review_prompts.py --task-dir ... --out-dir ...` 渲染后前置主控约束；`check_review_status.py` 判 PASS。**审查指纹包含 `docs/specs_index.md` 等非过程文档**（排除 note/handoff/review 报告/pending/findings/archive/.scratch），PASS 后改这些会变 stale；review 上限 5 轮，超出需用户批准。处置表只接受 `tNNN_code_fNNN` / `tNNN_test_fNNN` 编号。
- 收尾：handoff.json（task 目录）→ `preflight --require-verified --owner-id` → `finish` → 一个执行 commit → `attempt terminal --status completed` → `attempt report --status done --sha` → 备份 `.scratch` → `cleanup-worktree` → `integrate`（暂存）→ 合并后门禁 → `integrate --continue`。
- 工具链缺陷（已报告用户，本次经用户同意由主控补完）：`cleanup-worktree` 调用 `git worktree remove` 60 秒超时（含 node_modules/public 的前端 worktree），留下半删目录与 prunable 登记并提示“数据不一致”。后续若再超时须报告用户。
- zsh 不对未加引号变量分词，多参数循环用 `bash -c`；后台命令里用绝对路径（会话 cwd 可能变化）。

### 八、本地临时对象（可按前缀清理）

- 镜像：`t007-*`（lane 与门禁构建）、`cbrowser-gate-*`、`t007-master-dbg-stream:1`、`t007-master-dbg-stream-base:1`、`t007-master-supervisor:tokinst`、`t007-master-api:tokinst`、`t006-*`、`t005-*` 等，均可由源码重建，未清理。
- `.scratch/selkies_wheels/`：固定 Selkies 2.1.0 wheel 缓存（vendor 脚本默认路径）。
- `.scratch/v2_orchestration/handoff_backup/`：本次撤销合并前的 handoff 文件备份。


## 2026-11-01T12:27:04+08:00 累计审阅采纳完成，p008/p010 闭环

### 一、当前状态

- branch：main；head_commit：`2c3251569b1a9e6c1efc56c1e2d6922ef47cf1ff`（p010 merge；本文另行提交）。
- t001–t007 全部 done 并已合入 main。本轮完成：
    - t001–t007 累计三路审阅（`docs/reviews/review_20261101_075819/`）与 `adoption_decision.md` 决策落地。
    - A1–A31 全部实施；D1 按推荐 A 落地；R1–R8 按决策不实施。
    - A25 结构重构；p001、p005 闭环。
    - p008 Selkies resume 修复；p010 前端 vendor/build 接线修复。
- `docs/pending/todo/` 已清空；p001、p005–p013 全部归档到 `docs/archive/pending/`。
- 所有临时 worktree 已 `git worktree remove` + `prune`，adoption/p008/p010 分支已删除；未 push。

### 二、本轮提交

- 审阅报告与决策：`8352cb1`（review_20261101_075819）。
- 采纳轨道合并：`ed9d628`（docs A26/A27）、`5d5fe53`（build A11/A30）、`4c23b1b`（frontend A10/A28/A29）、`e6ccf6a`（backend A1–A9/A12–A24）。
- 结构重构：`d9f0034`（A25，merge `ef8e890`）。
- p008：`871ac3b`（merge `9e892a3`）。
- p010：`d26f90b`（merge `2c32515`）。
- 各采纳项在 main 历史中为独立 commit；A4/A5/A15/A24 有少量修正 commit（见 `git log --oneline`）。

### 三、验证结果

- 后端 unit：383 passed。
- 后端 integration：62 passed。
- 前端 Vitest：112 passed；`tsc -b` 通过。
- 前端构建：worktree 内实际执行 `npm run build --prefix src/frontend` 通过（prebuild vendor → tsc/vite → adapter IIFE → postbuild verify）。
- 前端构建接线测试：`tests/e2e/test_frontend_build_wiring.py` 8 passed；adapter/vendor 测试 13 passed。
- 未运行：需要不可变镜像/engine cache 的 Docker E2E、内核网络负例、真实 Chrome 前端 E2E；不得以历史 PASS 冒充本轮通过。

### 四、后续 task 队列

`docs/runtime/goal_queue.json` 顺序：t008 → t013 → t014 → t009 → t010 → t011 → t012。剩余 7 项均为 backlog，从当前 main 开工。

- t008（Artifacts/CDP 自动化）：以当前 main 为基线；前端 `/profiles/:id/files`、`/automation/:id` 仍是占位页；p007 已闭环。
- t013（复制/重置）、t014（剪贴板与完整输入）、t009（容量/P95/8h/1000 次输入）、t010（旧数据迁移，先备份可恢复）、t011（移除旧 VNC/RFB/原生桌面）、t012（Compose 生产交付）。
- t012 注意：
    - p006（agent_secret）与 p010（vendor/build）已闭环，不再需要在本 task 处理。
    - 前端生产构建必须走 `npm run build`（prebuild 自动 vendor、postbuild 自动校验）；清单在 `config/selkies/selkies_web_sha256.txt`。
    - `config/docker/Dockerfile` 已对 COPY 的 `dist/` 运行 `scripts/verify_frontend_dist.py`；Compose 不得绕过该校验。
    - API 仍需 `CBROWSER_SUPERVISOR_URL` + `CBROWSER_SUPERVISOR_TOKEN_FILE` + `CBROWSER_REQUIRE_SUPERVISOR=1`。

### 五、本轮架构变化（读代码前须知）

- 观测权威：Supervisor 以 Docker 容器状态/退出码与 Runtime Agent 进程监督为权威；磁盘事件只作诊断补充，不再直接驱动 `observed_state`/`desired_state`；`lifecycle/error` 收敛为 `observed_state=error` 并保留 `desired_state=running`；scan 对同实例会话短路；事件游标 + quarantine。
- Stream 出站：按 `CBROWSER_WEBRTC_MODE` 分档；relay-only 仅 Gateway/coturn/本实例 mux，local/lan/public 允许公共目的地址，私有/保留段始终 DROP。
- 停止/清理：Gateway 不可达时降级 teardown；端口释放走 finally；停止协调有上限。
- 配置：Gateway 端点单一来源，默认 18080；Origin 归一；不再硬编码 18097。
- 凭证/权限：`agent_secret` 在 `secrets/<profile>/agent_secret.txt`（0600，仅挂 Stream）；内部 token 强制 0600；宿主目录 chown 1000 + 0700/0750，x11 1777。
- 认证：受信代理 XFF + 每来源窗口 + 全局预算；429 带 Retry-After。
- TURN：轮换 future 校验 generation；current 过期 fail-closed；disconnect/stop 取消任务；upstream 关闭码透传。
- 数据：`runtime_events` 随 Profile 删除，`audit_events` 保留；tags 三态（缺席不改 / null 清空 / `[]` 清空）；failure_count 第 4 次阻断。
- 前端/构建：诊断数组有界、输入合并、i18n 补全、测试去固定 sleep；`npm run build` 已绑定 vendor/verify；Selkies manifest 在 `config/selkies/`。
- Selkies resume：viewer 隧道关闭/Gateway 断线后 Agent 保留 loopback upstream 10s，同 `tab_id`/`resume_key` 重连由 `RESUMED` 接管；见 d025。

### 六、环境与已知注意

- 前端构建需要 `python3` 与 Selkies wheel 缓存/网络；缓存默认 `.scratch/selkies_wheels/`。构建会改写 `src/frontend/tsconfig.tsbuildinfo`，提交前 `git show HEAD:...` 还原。
- p009（multi_viewer 固定 sleep）、p012（同 tab 驱逐关闭码）、p013（静止画面出帧）已修复并归档。
- 仍存在但未在本轮处理的偶发：`test_browser_runtime_e2e.py::test_ac006...` 偶发 Pulse 连接拒绝；`test_supervisor_namespace_policy_e2e.py` 偶发公网 IPv4 出站超时。复跑归因，不放宽断言。
- 本机 BuildKit 直连 Docker Hub 不稳：构建失败先 `docker pull` 基础镜像；sha256 不能直接当 FROM，需先 `docker tag`。
- Docker E2E 仍需外层互斥锁；测试代码不得自带锁或引用 `.scratch` 编排目录。

### 七、本地对象

- 本轮 worktree 已清理；`review/adoption-*`、`fix/p008-selkies-resume`、`fix/p010-selkies-vendor-wiring` 分支已删除。
- `.scratch/selkies_wheels/`：固定 wheel 缓存，可保留。
- 既有 t005/t006/t007 镜像与 `.scratch/v2_orchestration/` 证据仍在，按需清理；来源不明容器/网络继续不动。


## 2026-11-01T12:36:52+08:00 接手核对完成，当前 main 全量验证进行中

### 当前状态

- branch：main；head_commit：`4be9ee2dcb24035cc98b55d5e66dac29a1af1e08`（本文另行提交）。接手时工作区干净，仅 main 分支与主 worktree。
- t001–t007 done 并已合入；冻结队列未修改，t006/t007 integrated，goal-check 为 GOAL_QUEUE_INCOMPLETE（2/9 closed）。
- 无 active attempt；t008 尚未 start/reserve/claim。剩余顺序：t008 → t013 → t014 → t009 → t010 → t011 → t012。
- 用户附件明确授权队列逐项本地合并；禁止 push 与外部发布。最终目标仍为完整 v2 本机 OrbStack + 官方 Chrome 交付。

### 本轮验证证据

- 证据目录：`.scratch/v2_baseline_20261101/`；源版本见 `source_commit.txt`，不可变镜像见 `images.env` 与六个 `.iid`。
- Browser、Stream、Supervisor、API fixture、正式 Gateway 与 Gateway fixture 均由当前源码重建成功；日志 `build_*.log`，汇总 `build_results.json`。
- 后端 unit：`unit_r2.log`，383 passed。旧后端 + integration：`backend_r2.log`，446 passed。
- Vitest：`vitest.log`，退出码 0。前端生产构建：`frontend_build.log`，退出码 0，prebuild vendor 与 postbuild verify 均执行；tsconfig.tsbuildinfo 已恢复到原 HEAD 字节。
- 模板契约：`contract.log`，168 passed、1 skipped、477 deselected。文档格式：`md_format.log`，格式一致。
- 五项生成契约：`schema_results.json`，OpenAPI、Stream/Supervisor/Runtime Agent 协议、前端生成类型均退出 0 且字节不变。
- Ruff 全量检查非零；`ruff_efwi.log` 在 E/F/W/I 范围为 90 errors，未修复或豁免；扩大默认规则检查另见 `ruff.log`。不得声称全门禁通过。
- 初始 unit/integration 因 basetemp 父目录未准备失败；已保留 `unit_initial_setup_failure.log` 等日志，补建目录后重跑通过。旧后端原 PYTHONPATH=src 缺 v2 包，补用 src:src/backend 后通过，未改业务代码或断言。

### 在运行与恢复入口

- 主控验证 runner：PID 73111，工具 session 82335，脚本 `.scratch/v2_baseline_20261101/run_checks.py`；外层 flock 为 `.scratch/docker_e2e.lock`，已实查由该 PID 持有。
- runner 串行运行 Runtime、Stream、Supervisor、Gateway 与前端真实 E2E；按 `check_results.json`、当前日志、实际 PID/session 判断状态。不要因观察超时重启；旧 unit/integration/legacy 失败项以上述 r2 日志为补跑证据。
- 独立后端补跑 session 49772 已 exit 0；unit 补跑 session 25178 已 exit 0。无实现子 agent。
- 旧生产 cbrowser、其他项目与来源不明容器/网络保留，未清理、未重启 OrbStack、未扩大 Docker 配额。

### 下一步

- 继续观察 session 82335，复核真实 E2E 正负例与当前候选镜像；失败先归因。补齐 lint 门禁结论后才能启动 t008。
- OpenCode 实际模型列表已确认存在 `cpa/gemini-3.8-flash`；后续实现按用户指定 OpenCode 模型派发独立 lane。
- 已读编排脚本；已知 observed wrapper 不能以外层退出码证明成功，须读 JSON error、cli_exit 与交付证据。未修改编排工具或 `.repo_template`。
- 公网穿透与原生 Linux x86_64 执行始终单列 NOT_RUN / USER_WAIVED；8小时与1000次输入/剪贴板尚未运行，不预先计通过。


## 2026-11-01T12:41:21+08:00 Runtime 门禁通过，Stream 门禁失败待闭环

### 当前状态

- branch：main；head_commit：`7819d3aefd66be3920f3b08a9faa7ac2e27bb656`（本文另行提交）。接手时工作区干净；当前另有一个独立只读审核 worktree。
- t001–t007 done 并已合入；冻结队列未修改，t006/t007 integrated，goal-check 为 GOAL_QUEUE_INCOMPLETE（2/9 closed）。
- 无 active attempt；t008 尚未 start/reserve/claim。剩余顺序：t008 → t013 → t014 → t009 → t010 → t011 → t012。
- 用户附件明确授权队列逐项本地合并；禁止 push 与外部发布。最终目标仍为完整 v2 本机 OrbStack + 官方 Chrome 交付。

### 本轮验证证据

- 证据目录：`.scratch/v2_baseline_20261101/`；源版本见 `source_commit.txt`，不可变镜像见 `images.env` 与六个 `.iid`。
- Browser、Stream、Supervisor、API fixture、正式 Gateway 与 Gateway fixture 均由当前源码重建成功；日志 `build_*.log`，汇总 `build_results.json`。
- 后端 unit：`unit_r2.log`，383 passed。旧后端 + integration：`backend_r2.log`，446 passed。
- Vitest：`vitest.log`，退出码 0。前端生产构建：`frontend_build.log`，退出码 0，prebuild vendor 与 postbuild verify 均执行；tsconfig.tsbuildinfo 已恢复到原 HEAD 字节。
- 模板契约：`contract.log`，168 passed、1 skipped、477 deselected。文档格式：`md_format.log`，格式一致。
- 五项生成契约：`schema_results.json`，OpenAPI、Stream/Supervisor/Runtime Agent 协议、前端生成类型均退出 0 且字节不变。
- Ruff 全量检查非零；`ruff_efwi.log` 在 E/F/W/I 范围为 90 errors，未修复或豁免；扩大默认规则检查另见 `ruff.log`。不得声称全门禁通过。
- 初始 unit/integration 因 basetemp 父目录未准备失败；已保留 `unit_initial_setup_failure.log` 等日志，补建目录后重跑通过。旧后端原 PYTHONPATH=src 缺 v2 包，补用 src:src/backend 后通过，未改业务代码或断言。

### 在运行与恢复入口

- 主控验证 runner：PID 73111，工具 session 82335，脚本 `.scratch/v2_baseline_20261101/run_checks.py`；外层 flock 为 `.scratch/docker_e2e.lock`，已实查由该 PID 持有。
- runner 串行运行 Runtime、Stream、Supervisor、Gateway 与前端真实 E2E；按 `check_results.json`、当前日志、实际 PID/session 判断状态。不要因观察超时重启；旧 unit/integration/legacy 失败项以上述 r2 日志为补跑证据。
- 独立后端补跑 session 49772 已 exit 0；unit 补跑 session 25178 已 exit 0。无实现子 agent。
- 旧生产 cbrowser、其他项目与来源不明容器/网络保留，未清理、未重启 OrbStack、未扩大 Docker 配额。

### 下一步

- 继续观察 session 82335，复核真实 E2E 正负例与当前候选镜像；失败先归因。补齐 lint 门禁结论后才能启动 t008。
- OpenCode 实际模型列表已确认存在 `cpa/gemini-3.8-flash`；后续实现按用户指定 OpenCode 模型派发独立 lane。
- 已读编排脚本；已知 observed wrapper 不能以外层退出码证明成功，须读 JSON error、cli_exit 与交付证据。未修改编排工具或 `.repo_template`。
- 公网穿透与原生 Linux x86_64 执行始终单列 NOT_RUN / USER_WAIVED；8小时与1000次输入/剪贴板尚未运行，不预先计通过。

### 最新失败阶段与独立审核

- Runtime：`runtime.log`，13 passed（167.80 秒），对应本轮当前源码镜像。
- Stream：`stream.log`，17 passed、2 failed（142.13 秒）。失败：`test_stream_runtime_multi_viewer_e2e` 的精确挂载清单漏新增 `/tmp/selkies_credentials.json`；`test_e2e_ac010_gateway_topology_runtime_in_secure_mode_with_chrome` 在 API 容器端口查询出现 KeyError `8000/tcp`。不得以放宽旧断言、缺镜像或未就绪充当有效负例。
- root 初步归因：`root_failure_triage.json`。Supervisor/Gateway/API Dockerfile 白名单未复制已被导入的根模块 `cbrowser.secret_files`（API 还导入 Gateway endpoint）；静态缺口已核对，实际 import/退出日志尚待独占 Docker 验证，不能宣称实测根因。
- Supervisor 门禁在 session 82335 中继续，已出现失败但尚未结束；后续 Gateway/前端 E2E 由同 runner 串行推进。当前未修改生产文件。
- 独立只读 lane：`/Users/karson/kar/code/CBrowser_baseline_audit`（detached HEAD 7819d3a），OpenCode `cpa/gemini-3.8-flash --variant high`；dispatch PID 76042、wrapper PID 76237、CLI PID 76238，工具 session 59258。
- lane 输出：主仓 `.scratch/v2_baseline_20261101/audit.jsonl`、`audit_wrapper.log`；报告目标为审核 worktree `.scratch/baseline_audit/report.md`。原 tracked 文件已 SHA 守卫，只允许写 lane scratch。XDG data/cache/state 重定向主仓 scratch，未改 observed wrapper；它只读全局 DB，因此仍以 JSON、CLI 实际退出与报告判定，不据外层 exit 0 采信成功。
- 无新增 task、无 attempt identity；未变更冻结队列。审核 worktree 用完须先备份 scratch，再 worktree remove/prune；不得遗留到最终交付。


## 2026-11-01T12:44:25+08:00 main 前置门禁首轮结束，基线缺陷待修复授权

### 状态与范围

- branch：main；head_commit：`b80f72a30385c2758a3ebfc67e0bd43dcb888484`（本文另行提交）；生产源码、测试与冻结队列均未改动。
- t001–t007 done/integrated；goal-check 为 GOAL_QUEUE_INCOMPLETE（2/9 closed）。剩余 t008 → t013 → t014 → t009 → t010 → t011 → t012，均无 attempt。本地逐项合并已获附件授权；禁止 push。
- 已向用户异步请求独立基线修复授权：AGENTS.md 限定源码/测试只在 task 执行期修改，但附件要求完整门禁先于 t008；不擅自新增或改变冻结队列。用户尚未答复，不据自动 continuation 推定批准。

### 本轮证据与结果

- 目录 `.scratch/v2_baseline_20261101/`；实际生产源 `4be9ee2`，后续仅交接文档提交。镜像由该源构建；不可变 ID 为 `images.env`、六个 `.iid`，构建日志及 `build_results.json` 均保留。
- 后端 unit：383 passed（`unit_r2.log`）；旧后端 + integration：446 passed（`backend_r2.log`）。最初运行器目录/PYTHONPATH失误原日志保留，修正 scratch 环境后复跑，未改代码或断言。
- 模板 contract：168 passed、1 skipped；Vitest exit 0；生产前端构建含 vendor/postbuild verify exit 0；md_format 格式一致；五项 schema/codegen 重生成字节一致。tsconfig.tsbuildinfo 已恢复，工作区干净。
- Runtime Docker E2E：13 passed（167.80 秒）。Stream：17 passed、2 failed（142.13 秒）。Supervisor：17 passed、9 failed（161.28 秒）。Gateway：5 failed（27.80 秒）。前端：14 passed、4 failed、13 errors（21.68 秒）。旧生产健康检查 exit 0，不代表 v2 已交付。
- Ruff E/F/W/I：90 errors（`ruff_efwi.log`），全默认规则报告另见 `ruff.log`；未修复或豁免。
- 完整首轮 runner session 82335/PID73111 已结束，退出 0 仅代表脚本跑完，逐项失败见 `check_results.json`，不能计全门禁 PASS。

### 已确认缺陷

- 镜像实际 import 冒烟 `image_import_smoke.py` 在同一外层锁下执行，session21030 已结束：API 与测试 Gateway 缺 `cbrowser.gateway`；正式 Supervisor/Gateway 缺 `cbrowser.secret_files`。四镜像均 exit1，原始 `import_*.log` 与 `import_smoke_results.json` 已保存，实际 Docker 整镜像执行，无源码覆盖。
- Supervisor recovery 夹具仍用旧 Gateway 端口，真实子进程 ValueError `Gateway URL port does not match the configured Gateway port`；resource monitor fixture token 权限不符合0600；旧基础设施测试期待18097，实际18080；旧启动恢复测试期待missing_runtime而实际observed_error。
- Stream旧精确挂载断言漏新增凭证文件；修复须保留旧测试或整体删除注明替代覆盖，禁止就地改预期迁就实现。
- 拓扑初始化失败泄漏容器，coturn占用50000导致后续前端级联失败；不能计作网络安全负例或产品媒体失败。
- 初步归因与证据索引 `root_failure_triage.json`，独立审核报告待出。

### 资源、审核与下一步

- 主控已核对并清理本轮16个残留容器、6个空网络；精确清单 `cleanup_plan.json`，关键异常行 `cleanup_error_*.txt`。旧生产cbrowser、kkmail/haiwa及来源不明历史对象保留。
- 独立审核worktree：`/Users/karson/kar/code/CBrowser_baseline_audit`（detached HEAD 7819d3a），SHA守卫785文件，仅准写 `.scratch/baseline_audit/`；无tracked改动。
- 模型 `cpa/gemini-3.8-flash --variant high`，CLI PID76238、wrapper76237、dispatch76042，工具session59258仍活跃。日志主仓 `audit.jsonl` / `audit_wrapper.log`；目标报告审核worktree `.scratch/baseline_audit/report.md`。XDG运行数据/缓存重定向主仓scratch；不改observed wrapper，成功以JSON、CLI实际退出和报告判定，非外层exit0。
- 下一步：读取并复核独立审核，等待基线修复授权；获授权后独立worktree最小修复、review、重建并补跑全门禁，之后才start t008。审核结束备份scratch再worktree remove/prune。
- 本轮未改 `.repo_template`，未重启OrbStack或扩大配额。公网/原生Linux x86_64为NOT_RUN / USER_WAIVED；8小时与1000次IME/剪贴板未执行，不预计通过。


## 2026-11-01T12:45:06+08:00 前置失败与独立审核闭环，等待基线修复授权

### 状态与范围

- branch：main；head_commit：`79011e8026d6895170b9ee83afdd3dbe39a270a0`（本文另行提交）；生产源码、测试与冻结队列均未改动。
- t001–t007 done/integrated；goal-check 为 GOAL_QUEUE_INCOMPLETE（2/9 closed）。剩余 t008 → t013 → t014 → t009 → t010 → t011 → t012，均无 attempt。本地逐项合并已获附件授权；禁止 push。
- 已向用户异步请求独立基线修复授权：AGENTS.md 限定源码/测试只在 task 执行期修改，但附件要求完整门禁先于 t008；不擅自新增或改变冻结队列。用户尚未答复，不据自动 continuation 推定批准。

### 本轮证据与结果

- 目录 `.scratch/v2_baseline_20261101/`；实际生产源 `4be9ee2`，后续仅交接文档提交。镜像由该源构建；不可变 ID 为 `images.env`、六个 `.iid`，构建日志及 `build_results.json` 均保留。
- 后端 unit：383 passed（`unit_r2.log`）；旧后端 + integration：446 passed（`backend_r2.log`）。最初运行器目录/PYTHONPATH失误原日志保留，修正 scratch 环境后复跑，未改代码或断言。
- 模板 contract：168 passed、1 skipped；Vitest exit 0；生产前端构建含 vendor/postbuild verify exit 0；md_format 格式一致；五项 schema/codegen 重生成字节一致。tsconfig.tsbuildinfo 已恢复，工作区干净。
- Runtime Docker E2E：13 passed（167.80 秒）。Stream：17 passed、2 failed（142.13 秒）。Supervisor：17 passed、9 failed（161.28 秒）。Gateway：5 failed（27.80 秒）。前端：14 passed、4 failed、13 errors（21.68 秒）。旧生产健康检查 exit 0，不代表 v2 已交付。
- Ruff E/F/W/I：90 errors（`ruff_efwi.log`），全默认规则报告另见 `ruff.log`；未修复或豁免。
- 完整首轮 runner session 82335/PID73111 已结束，退出 0 仅代表脚本跑完，逐项失败见 `check_results.json`，不能计全门禁 PASS。

### 已确认缺陷

- 镜像实际 import 冒烟 `image_import_smoke.py` 在同一外层锁下执行，session21030 已结束：API 与测试 Gateway 缺 `cbrowser.gateway`；正式 Supervisor/Gateway 缺 `cbrowser.secret_files`。四镜像均 exit1，原始 `import_*.log` 与 `import_smoke_results.json` 已保存，实际 Docker 整镜像执行，无源码覆盖。
- Supervisor recovery 夹具仍用旧 Gateway 端口，真实子进程 ValueError `Gateway URL port does not match the configured Gateway port`；resource monitor fixture token 权限不符合0600；旧基础设施测试期待18097，实际18080；旧启动恢复测试期待missing_runtime而实际observed_error。
- Stream旧精确挂载断言漏新增凭证文件；修复须保留旧测试或整体删除注明替代覆盖，禁止就地改预期迁就实现。
- 拓扑初始化失败泄漏容器，coturn占用50000导致后续前端级联失败；不能计作网络安全负例或产品媒体失败。
- 初步归因与证据索引 `root_failure_triage.json`，独立审核已结束，报告及主控复核见下文。

### 资源、审核与下一步

- 主控已核对并清理本轮16个残留容器、6个空网络；精确清单 `cleanup_plan.json`，关键异常行 `cleanup_error_*.txt`。旧生产cbrowser、kkmail/haiwa及来源不明历史对象保留。
- 独立审核已结束：session59258、CLI PID76238已终止，实际cli_exit=0，durable_finished=False（wrapper只读全局DB，XDG隔离后的会话不在该DB中），不据外层退出码判断完成。最终report存在且已主控读取。
- 证据备份 `.scratch/v2_baseline_20261101/audit_evidence/`（report.md、guard.json、permission.json）；JSON与wrapper日志留主仓。审核worktree tracked文件无变化，已git worktree remove + prune；最终仅main和主worktree，无新增分支。
- 主控确认审核新增发现：supervisor/runner.py:187/192引用当前函数作用域不存在的d_client/docker_adapter，Ruff F821与源码对应；需补触达真实事件监听任务的RED测试后修复。policy.py中should_block_client_verb被动态重导出，禁止盲目ruff --fix删除。
- 审核报告部分计数与主控原始日志矛盾（Runtime应13通过、Vitest应112通过、Supervisor应17通过9失败、前端应14通过4失败13错误），均以本交接及原始日志为准。共享pytest缓存导致污染的因果未经证实，不采信；单独执行build/contract/schema等证据有效，不以未集成同一个runner否定。
- 下一步：等待基线修复授权；获授权后独立worktree最小修复、review、重建并补跑完整门禁，之后才start t008。无在飞测试/子代理；不得重复重启已结束句柄。
- 本轮未改 `.repo_template`，未重启OrbStack或扩大配额。公网/原生Linux x86_64为NOT_RUN / USER_WAIVED；8小时与1000次IME/剪贴板未执行，不预计通过。
