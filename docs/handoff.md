# 项目交接记录（最新）

本文件只保留当前有效一节。上一节已追加到 `docs/archive/handoff.md`。

## 2026-11-01T22:14:18+08:00 基线继续修复：真实端口链已通，补Linux UDS与恢复夹具

### 授权与状态

- branch：main；head_commit：`f74bab47399410f976b5cbd4329d556133d66119`（本文另行提交）。用户“不需要创建task 直接改”，再次“继续”；直接修基线，不建task、不改冻结队列、不push，本地merge已授权。
- t001–t007 done/integrated；剩余t008 → t013 → t014 → t009 → t010 → t011 → t012，无attempt。先完整基线绿再start t008。8小时与1000次输入/剪贴板仍待实际验证；公网TURN/原生Linux x86_64为USER_WAIVED。
- main只有文档推进；生产修复尚未commit/merge。全部实现diff_anchor `a673edf`。宿主goal历史blocked不代表目标完成，工具无active恢复参数；实际工作持续推进，不重建goal或task队列。

### 当前快照与完成证据

- 核心实现wt `CBrowser_baseline_fix`，branch `fix/v2_baseline_gates`，当前已整合fixture round6快照 `fixture_candidate_r2.patch`，SHA256 `a7cc0a8f87ba5ff015eef9ea3c765e9fb8c484d7c8788a8495cc45c5e56b9c25`。旧fixture_candidate.patch已reverse --check后精确替换，原证据保留。
- 核心component `core_candidate_r3.patch` SHA256 `14ecd34472d674a347ac7086f3e3e8db381a49ba4aec10bab916b7a9b263b103`，42文件；独立core review R3 PASS，报告core-review wt `.scratch/baseline_core_review/report.md`，cli_exit0。新退出用例实际主控1 passed in4.33s，证据 `focused_round1/`。
- 主控R2全门禁证据 `fix_round2/`：6镜像构建、4闭包中的3实际import、contract169、unit399、integration62、legacy384、Vitest112、build/schema/Ruff/md、Runtime13与完整Stream媒体均通过，失败与未执行见归档上一节；旧snapshot不得冒充最终绿。
- 主控补跑 `focused_unrun_r2/`：resource capacity/monitor/policy、startup全通过；retry真实Chrome正常关闭后desired未stopped（1fail111.81s），与offline recovery同一生产缺陷。无标签容器/网络残留。
- 主控端口整合补跑 `focused_ports_r2/`：真实Supervisor容器图、Selkies tokens、Gateway auth/media/relay、frontend session通过；ac007 visibility仍直接inspect旧18097失败；frontend app几组缺dist是主控准备错误，不是业务RED。
- 主控已在候选wt重新npm ci/build exit0，恢复tracked tsbuildinfo原字节，证据 `frontend_build_r3/`。`focused_frontend_r3/` 真实官方Chrome headless已结束：auth/display_apply/ice_failure通过；media3通过1旧端口失败；app4通过1失败，工具session97635退出1。失败ac007诊断用例pause整个Browser触发真实Supervisor container_exit/retry，原容器删除，等待媒体无画面超时、unpause404；API SQLite已只读证实Lifecycle Profile记录container_exit。不能放宽产品断言，需隔离媒体故障注入。

### 新验证的平台事实

- 所有证据根为主仓 `.scratch/v2_baseline_20261101/`。
- `uds_host_probe_r3/result.json`：server明确listen-ready，同一Unix socket在独立Linux两容器间roundtrip OK；macOS宿主is_socket=True，path90，connect errno61。测试Supervisor放macOS进程无法代表生产Linux UDS边界。
- `uds_long_path_probe/result.json`：Linux同一共享socket，197字符完整path报AF_UNIX path too long；经过O_DIRECTORY/O_NOFOLLOW目录FD的`/proc/self/fd/<fd>/agent.sock`连接OK。容器均精确标签清理，未写生产数据。
- R2正常关闭Profile已有实例state.json stopped/0/normal；无需recover_terminal=True从磁盘event重建终态。磁盘事件只诊断；API唯一业务DB写者，Supervisor以Docker+Agent真实进程观测为准。

### 当前实现lane与守卫

- 原core session已完成；core wt无活动实现者，可由主控整合，但当前frontend gate运行期间不修改候选源码。
- fixture wt `CBrowser_baseline_fixtures`，branch `fix/v2_baseline_fixtures`，session `ses_e6a7c7e18ffeNQzGW5g1MCQkco`。round6 exit0，12新回归与全unit395、contract/lint通过；抽取精确标签清理helper、network reload失败拒删、去掉AST参数扫描、三inline CLI显式端口。round7正将RealSupervisorProcess升级真实Linux Supervisor容器，更新offline/retry/三恢复E2E；不可变镜像，不源码bind、不Popen兼容壳、实际SIGKILL inspect，保留全部业务断言。启动 `fixtures_round7_launch.json` dispatch41895/CLI41902。
- normal wt `CBrowser_normal_exit_fix`，branch `fix/v2_normal_exit_observation`，session `ses_e68b60e1cffetua70w4uOzZVnU`。round1/3主控有意SIGINT用于拒绝journal权威、重复逻辑与MagicMock生产兼容；round2因主控恢复参数漏unguard两个新测试被守卫停止，已按原写域修调用，未改工具。round4当前dispatch43517/CLI43524，见 `normal_exit_round4_launch.json`。允许四生产路径（core/recovery_coordinator/recovery_rules/agent）、两个新测试，额外只授权旧test_supervisor_recovery_coordinator.py补AsyncMock依赖，不准改业务预期。要求目录FD长UDS、真正ACK后去重、409非ACK、identity mismatch拒绝、normal ACK后清理、healthy B保留、owner-loss误0仍error。
- normal旧新测试曾硬编码/tmp/cbr\_\*，违反写域，主控已报告用户并中止；其finally已清理，主控两次只读检查无残留/无在飞旧pytest。要求round4移入自身scratch，禁止ignore_errors，旧越界测试不作最终证据。不得静默掩盖。
- 新端口lane wt `CBrowser_visibility_ports_fix`（detached a673），session从 `visibility_ports_round1.jsonl`读；dispatch44583/CLI44815。仅ac007 visibility、ac003 media、frontend media、frontend display apply四E2E，修直接旧端口依赖，保留/强化媒体与安全断言，语义失效node整体替换记录映射。不得改其它lane文件。完成后可同session追加app ac007故障注入修复，但须先精确授权新路径。
- 所有OpenCode模型已授权cpa/gemini-3.8-flash high，XDG/tmp/cache重定向scratch；核对actual cli_exit/JSON/report，外层exit0不足。当前3个外部actor并发，勿额外启动第4个。

### 整合与后续

- 8个自有wt：main、baseline_fix、baseline_fixtures、baseline_validation、baseline_core_review、baseline_fixture_review、normal_exit_fix、visibility_ports_fix。review/validation旧报告只绑定原hash；新fixture/normal/端口scope须独立终审，主控亲读源码和实际测试。
- 等对应actor与候选gate终止再整合，保留旧patch/失败日志；更新fixture须reverse当前fixture_candidate_r2.patch，再check/apply新patch。normal与端口路径无交集，核对后apply。新增文件先git add -N再算完整SHA。
- 新全门禁驱动 `fix_dispatch/verify_candidate_r3.py`已准备，输出fix_round3，重建6最终镜像、4实际import、完整gate、旧生产health、源snapshot不变核对；同时检查新容器与网络残留，有泄漏立即停。尚未启动，不能覆盖R2。
- 生产最终review+全门禁绿后，baseline一个执行commit、本地merge main、备份证据后规范清理wt/分支，再按task-run冻结顺序继续。旧生产cbrowser及其它项目容器健康，未改Docker配额/全局配置/生产secret，不push、不改.repo_template。
