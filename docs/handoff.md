# 项目交接记录（最新）

本文件只保留当前有效一节。过时段落由 `repo-hygiene` 迁入 `docs/archive/handoff.md`。

## 2026-10-29T19:55:18+08:00 v2 架构计划执行交接

- branch：main
- head_commit：7f2459d8de7af47410210e38b5cc06aa33c692ca（本次交接更新前main；t001–t004已集成，t005实施中未提交；task分支head仍84f84311815bff330a51bcd35da150fc8b4990b3）
- 交接更新约定：每完成一个阶段立即更新本文件（用户最新明确要求），包含该阶段提交、实际验证、遗留项及下一步。
- 执行目标：完成 docs/v2_architecture_plan.md，最终部署到当前Mac的OrbStack Docker，由同机官方Chrome访问。t001–t004已完成并合入main，旧正式入口尚未切换；当前实施t005 Supervisor，按固定队列继续后续全部任务。

### 当前恢复入口（覆盖下文历史阶段状态）

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
