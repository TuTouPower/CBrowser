# 项目交接记录（最新）

本文件只保留当前有效一节。上一节已追加到 `docs/archive/handoff.md`。

## 2026-11-02T02:23:50+08:00 真实复验暴露夹具权限与终态权威缺口，继续直接修复

### 授权与队列

- branch：main；head_commit：`c697626c5dfefc4c6cc780a4508289f27e03f338`（本文另行提交）。用户已授权“不需要创建task 直接改”，继续完成完整目标；宿主goal已由用户恢复active，不重建goal，不重置冻结队列。
- t001–t007 done/integrated；剩余t008 → t013 → t014 → t009 → t010 → t011 → t012，无attempt。完整当前基线门禁前不start t008。仅本地merge，禁止push/外部发布。
- main仅交接文档推进，生产修复尚未commit/merge。原实现diff_anchor `a673edf`；旧生产cbrowser和其它项目资源保留。

### 已完成证据与当前真实失败

- core42文件component独立PASS，SHA `14ecd34472d674a347ac7086f3e3e8db381a49ba4aec10bab916b7a9b263b103`；真实SIGTERM退出E2E通过。初始R2完整门禁的unit399/integration62/legacy384/Vitest112/build/schema/Ruff E/F/W/I/Runtime13/Stream完整媒体及内核隔离均通过，但不代表最终候选全绿，原始证据均保留。
- 当前整合曾冻结combined R3 SHA `f035d505e94f26725631e7c567f84756ed3bda2ac675d4046d42ec7da035c560`，完整70文件；patch/meta在 `fix_dispatch/combined_candidate_r3.*`。main实现、两个review和独立validation已复制核对同hash。此hash后又加入端口component motion源一行，后续须重算，不能沿用旧review范围。
- `focused_visibility_r3/`：真实Gateway visibility/media、完整前端media/display四组全部通过；`focused_frontend_r3/` auth/display/ICE通过，app4pass1fail、media3pass1旧端口fail；后者已由端口补跑消除。
- `focused_recovery_r3/` 主控独立validation完整源码构建6新镜像、4实际import、前端npm ci/build、normal unit/integration均通过；offline/retry/三个SIGKILL恢复用例都在首次Runtime start 500/OSError，未进入业务验证。新frontend诊断stage已触发但RTP增长断言失败。工具session44340已自然退出1，所有日志/最终镜像ID/source patch保留，不能当总绿。
- 恢复夹具错误：主控此前误将Browser/Stream消费缓存RO约束施给Supervisor初始化端。真实生产 `_initialize_cache` 需chmod/write marker；既有container_graph正是Supervisor RW、Runtime消费者RO。`cache_mount_probe/result.json` 用同新Supervisor镜像/同真实cache/同capdrop复现只读chmod errno30。只能修夹具角色权限，不能改生产绕初始化或给Browser/Stream缓存写权限。
- 新诊断替换了整Browser pause，真实RTP/worker discard/零解码与media_no_frames已达到；R3静态页面缺运动源，P4加入现存animate_remote_fixture后R4的RTP总量从383455/364升至2347693/2480，但两个采样仍同瞬间。`focused_diagnostic_r4/` 失败已保留；须把真实增长纳入原45s观察条件，不能放宽>或伪造stats。session58382已退出1。

### 独立审查与新权威边界RED

- normal独立review：FAIL，报告core-review wt `.scratch/baseline_normal_review/report.md`。state.error/owner-loss但孤儿Chrome PID/CDP仍活时，原交叉检查丢error详情并误判running。要求仅stopped正常退出做反矛盾校验，error始终保留故障并重试；实施R6已修，12项unit+4integration、全unit395/integration66及明确E/F/W/I已通过，待重新独立review/真实Docker。
- normal reviewer还抓到75项新增E501，不能以裸Ruff默认通过冒充E/F/W/I。R6已逐项折行，源码新文件已add-N纳入diffcheck。
- fixture独立review对旧f035范围PASS，报告fixture-review wt `.scratch/baseline_fixture_review/report.md`，18项unit/579collection/相关E/F/W/I通过，未运行Docker。真实复验已揭露其未覆盖的Supervisor缓存writer权限与同步调用阻塞loop，旧PASS不能证明当前夹具实际可运行，须增量重审。
- 主控额外真实负例 `agent_version_probe/result.json`：runner_info版本1、同实例native状态版本2，health却200/版本1/stopped，掩盖版本矛盾；`agent_event_authority_probe/result.json`：实例原生状态文件缺失但summary running+exit journal，health仍200/stopped，违反事件仅诊断。原因 `get_instance_state` 的False模式仍在state None时隐式事件恢复。真实probe仅ASGI/磁盘边界，不冒充Docker正例。
- Linux事实已验证：`uds_host_probe_r3` 两Linux容器UDS OK而Mac宿主拒绝；`uds_long_path_probe` 197字符完整路径失败，O_DIRECTORY/O_NOFOLLOW目录FD别名OK；`chrome_transform_probe_r2` 仅Chrome接口contract_only（真实连接/丢编码帧/RTP/零解码），非产品媒体验收。所有临时容器精确标签回收。

### 当前实施进程与源码所有权

- core实现wt `/Users/karson/kar/code/CBrowser_baseline_fix`（fix/v2_baseline_gates），目前无实现actor；独立validation `/Users/karson/kar/code/CBrowser_baseline_validation` 当前无活动gate。候选已整合旧fixture r3、normal r2、端口r3（motion准备），继续整合时须reverse精确对应旧component patch，防叠加/覆盖。
- fixture wt `CBrowser_baseline_fixtures`，session `ses_e6a7c7e18ffeNQzGW5g1MCQkco`。R10 CLI启动database is locked/exit1，仅57字节错误，无工具执行，source SHA仍4cd6e2f；主控已立即报告用户，未改工具配置。R11有限同session重试当前dispatch15821/CLI15828，日志 `fixtures_round11.jsonl`；修Supervisor cache RW及五个恢复使用者将同步start/restart/sigkill/stop通过asyncio.to_thread移出宿主Gateway所在loop。仅offline fixture/自己新unit/三个恢复E2E写域。
- normal wt `CBrowser_normal_exit_fix`，session `ses_e68b60e1cffetua70w4uOzZVnU`。R6已exit0；R7当前dispatch19267，CLI见 `normal_exit_round7.jsonl.wrapper.log`。在原7路径外唯一新增授权event_storage.py：False模式不得隐式事件恢复；显式True的Runner/start防重复generation用途保持；Health拒绝metadata/native版本矛盾，既有StorageError->503。新测试仅自己的unit/integration，不改旧storage unit预期。必须复跑既有storage tests和明确E/F/W/I，不改协议/配置/其它模块。
- 端口/诊断wt `CBrowser_visibility_ports_fix`（detached a673），session `ses_e68924041ffe0GS6p3F6ChsLkd`。P4 exit0，仅加入运动源；P5当前dispatch17874，CLI见 `visibility_ports_round5.jsonl.wrapper.log`，只app E2E一个文件修采样条件。其它四端口测试修改已真跑通过，不再改。
- 所有OpenCode模型cpa/gemini-3.8-flash high，XDG/cache/TMPDIR在scratch。wrapper外层exit0不足，以cli_exit/JSON/report/实际证据核对。既往normal恢复命令漏unguard新测试导致守卫中止已按原域修调用；曾误写/tmp/cbr\_\*已披露、已自动清理并两次核查无残留，最终测试仅自身scratch，不沿用越界GREEN。

### Ruff范围与下一步

- Ruff实测0.17.3，原E/F/W/I筛选不等于当前默认规则全绿。默认main686项，旧中间候选683项，主要BLE/旧typing/ASYNC；JSON在 `ruff_full_main.json` / `ruff_full_candidate.json`，完整settings保留。已向用户异步询问按默认全清或仅E/F/W/I，尚未收到该选择；不把goal active当作答案。功能修复与真实验证继续，最终不能隐瞒默认规则失败。
- 等三路实际终止后重算component/combined SHA，源码各域无交集；新文件先add-N再diffcheck。补跑真正Linux恢复、native authority负例与诊断；独立review需绑定新最终hash。最后必须完整重建镜像/全门禁，包括尚未最终通过的恢复业务与新诊断，不能用窄测试支持总完成。
- 原完整驱动 `verify_candidate_r3.py` 输出fix_round3尚未启动；后续版本可另建输出，保留所有失败，不覆盖旧日志。Docker外层互斥，容器/网络残留都检查，发现泄漏停后续，不能全局prune。
- 8个自有wt仍在：main、baseline_fix、baseline_fixtures、baseline_validation、baseline_core_review、baseline_fixture_review、normal_exit_fix、visibility_ports_fix。最终基线一个执行commit本地merge main，备份scratch后规范清理，再按冻结队列task-run。公网TURN/原生x86 USER_WAIVED；8小时/1000次输入与剪贴板仍未执行，不宣称完成。
