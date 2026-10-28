# 项目交接记录（最新）

本文件只保留当前有效一节。过时段落由 `repo-hygiene` 迁入 `docs/archive/handoff.md`。

## 2026-10-29T03:24:34+08:00 v2 架构计划执行交接

- branch：main
- head_commit：dad2197（本次交接更新前main；业务仅t001/t002，t003→t004待链尾集成）
- 交接更新约定：每完成一个阶段立即更新本文件（用户最新明确要求），包含该阶段提交、实际验证、遗留项及下一步。
- 执行目标：完成 `docs/v2_architecture_plan.md`，最终部署到当前 Mac 的 OrbStack Docker，由同机 Chrome 访问。t001 技术验证、t002 后端持久化基础均已完成并合入；旧正式Docker入口尚未切换；当前实施t004 Stream Runtime，t003待链尾集成。

### 当前恢复入口（覆盖下文历史阶段状态）

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
