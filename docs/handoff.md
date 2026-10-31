# 项目交接记录（最新）

本文件只保留当前有效一节。过时段落迁入 `docs/archive/handoff.md`（Codex 主控时期的 t001–t005 过程记录已整体迁档）。

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
- 运行中的子 agent：Gemini lane `t006_relay`（2026-10-31T11:33:58+08:00 派发，pid 42477，WT /Users/karson/kar/code/CBrowser_t006_relay，日志 `.scratch/v2_orchestration/t006_relay_r1.jsonl`，prompt `t006_dispatch/t006_relay_prompt.md`）：Stream 侧 rtc_config 携带仅 relay 意图并在初始 PC 限制 relay 候选、测试页保持 Gateway 策略、AC-005 恢复初始双端 relay 判据、修证据目录。
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
