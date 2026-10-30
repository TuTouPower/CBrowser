# 项目交接记录（最新）

本文件只保留当前有效一节。过时段落迁入 `docs/archive/handoff.md`（Codex 主控时期的 t001–t005 过程记录已整体迁档）。

## 2026-10-30T21:05:00+08:00 v2 架构计划执行交接（t006 实施中：会话接管与计划修订 9.3 已实施）

- branch：main
- head_commit：5c1f524（本次 docs 改动前）
- 工作树：主仓（main）、t006 WT（/Users/karson/kar/code/CBrowser_t006）、E2E lane WT（/Users/karson/kar/code/CBrowser_t006_e2e2，分支 lane/t006_e2e2，seed=t006 WT 21:10 状态）。
- 执行目标：按冻结队列 t006 → t007 → t008 → t013 → t014 → t009 → t010 → t011 → t012（`docs/runtime/goal_queue.json`）串行完成 `docs/v2_architecture_plan.md` 剩余内容，每 task 一个执行 commit，逐个合入本地 main；最终部署到本机 OrbStack，由本机官方 Chrome 访问。禁止 push 与外部发布。t001–t005 已完成并合入。
- 已定决策：重试 2/10/30 秒三次、failure_count=4 阻断、手动重试清除（ADR 008）；管理员密码 `data/secrets/admin_password`（0600，只在生产首次启动读取，测试一律随机）；公网 WebRTC/TURN 与原生 Linux x86_64 为 NOT_RUN / USER_WAIVED；性能按本机 OrbStack + Chrome 实跑；计划修订（2026-10-30，9.3 可见性只走 Selkies 原生、Gateway 不聚合活动、显式 Selkies 设置）已获批。
- 子 agent：OpenCode `cpa/gemini-3.8-flash --variant high`（思考强度 high，用户 21:00 重申），经 `.scratch/v2_orchestration/dispatch.py` → `run_opencode_observed.py`。
- 主控会话：claude 会话 1024a4ed（进程 92682，接替同进程内已中断的 e225b0f4）；owner_id 记录在 `.scratch/v2_orchestration/claude_owner_id.txt`（旧值备份 `claude_owner_id_prev_14b38abc09f2.txt`）。进程 3313（会话 5d707c61）是写计划修订与接手 prompt 的辅助会话，未持有任何 task。

### t006（branch=t006_v2_gateway_auth_rtc，base/diff_anchor=c33e55f）

- identity：attempt1 / execution_id=79fa47d2f34e42f8b31f43ceb8cb52a9 / owner_id=claude_v2_6e1f7a8e7a46（2026-10-30T20:50:19+08:00 `attempt claim --replace-owner claude_v2_14b38abc09f2 --confirm-stopped`）。不得重复 start/reserve；再换会话须 `--replace-owner claude_v2_6e1f7a8e7a46 --confirm-stopped`。
- 未提交工作在 t006 WT：71 个路径（新文件均 `git add -N`）。最新快照 `.scratch/v2_orchestration/t006/t006_wt_snapshot_20261030T2102.patch`（`git diff --binary c33e55f`，可在干净 c33e55f 上 `git apply` 复原；旧快照 2032/2046 保留）。
- 已完成（截至本节）：
    - 前期 lane（agent/gateway/gwfix/auth）整合与主控修正，详见 t006 note.md「开工、lane 拆分与整合」。
    - 计划修订 9.3 实施（先 RED 8 项、后 GREEN）：删除 Gateway 活动聚合（`gateway/activity.py`、页面 activity 帧、`VISIBILITY_UPDATE` 下发与 Agent 分支、协议动作与载荷，schema 重导出）；Agent 心跳新增取自 Selkies 的 `unpaused_video_consumers` / `capture_running`，注册后立即发送首个心跳；Gateway visibility 端点改读最近上报值（未上报 503，新注册不继承）；Supervisor gateway_client 契约不变。gateway.md、stream_runtime.md、webrtc_remote_display spec 已同步。旧语义测试整项删除并在 note 写明理由（含 t004 遗留 schema/hardening 用例与 stream E2E 的 Gateway visibility 段）。
    - 主控审查修正 auth lane 遗留：`test_supervisor_recovery_e2e.py` 两个用例引用未定义 `stack`（运行即 NameError）；`test_supervisor_core_e2e.py` E402；两文件 format。
- 已验证（WT 当前态，Docker E2E 前）：unit+integration 294 passed（`CBrowser_t006/.scratch/t006_93/green_unit_integration.log`）；Ruff E,F,W,I 16 项（均为 main 基线 test_v2_api_subprocess E501）；ruff format、`git diff --check`、md_format 通过。
- 运行中的子 agent（2026-10-30T21:16 派发）：E2E lane `t006_e2e2`，opencode_pid 30580，session ses_e73140c3bffezl2ty40n3Td8YL，日志 `.scratch/v2_orchestration/t006_e2e2_r1.jsonl`（状态摘要 `python3 .scratch/v2_orchestration/lane_status.py <该文件> --text`），prompt `.scratch/v2_orchestration/t006_dispatch/t006_e2e2_prompt.md`（按 9.3 改写；镜像全部当前源重建；Docker 前缀 t006-e2e2；AC-005 负例用 coturn total-quota）。中断后续行用 `dispatch.py --session ses_e73140c3bffezl2ty40n3Td8YL --unguard-changed`，不得新开重复 lane。
- 下一步：
    1. 等 E2E lane 交付；主控逐行审查并亲自复跑，核原始 JSON（帧数、candidate 类型/地址、Generation committed 日志、Cookie 属性、visibility 端点原始响应），增量合入 t006 WT 后 retire。
    2. 复制 `.scratch/v2_orchestration/gates/run_gates_template.sh` 快照跑全套门禁，补 Gateway 镜像构建与 Gateway E2E；Stream/Gateway/Supervisor/API 镜像用当前源重建（不得复用下方临时镜像）；testing.md 补 Gateway E2E 命令。
    3. 七 AC 按实证打勾 → `git add -N` → 渲染 review prompt → 独立黑盒（validation WT）+ code/test full review（两份报告同时 unguard）→ 处置 → handoff.json → finish → 一个执行 commit → attempt terminal/report → cleanup → integrate → 合并后门禁。
- 本地临时镜像（可由源码重建，未清理，禁止冒充门禁镜像）：t006-agent-stream:1、t006-gateway-gateway:1、t006-gwfix-gateway:1、t006-gwfix-stream:1、t006-root-supervisor:cfgver、cbrowser-gate-*:r1、cbrowser-t005-*:final_round1。

### 遗留与环境

- 未触碰的既有对象：Docker 网络 net_9335ab04/net_d876dc01/net_e5052de6（无标签，来源不明）、容器 pensive_satoshi、test-shm-srv、旧 cbrowser 容器（t011/t012 前不动）。上一节记录的 `cbrowser-t003-bb-aece4d57-net` 在 21:00 核对时已不存在（非本会话删除）。
- p001（RecoveryCoordinator.tick 复杂度，minor）待办。
- 主机负载受 kkmail 等容器影响（曾致 Docker 引擎无响应），计时类测试与 t009 基准须记录负载；用户已授权引擎无响应时重启 OrbStack。
- 通用工具：prompt 外壳 `.scratch/v2_orchestration/prompts/`；lane 状态 `python3 .scratch/v2_orchestration/lane_status.py <jsonl> --text`；lane 管理 `lane_worktrees.py create/diff/retire`；门禁 runner 每轮复制快照，zsh 不对未加引号变量分词（多参数用 bash -c）。
- 后续 task 关键约束已写入各 task.md：t007 AC-008 `SELKIES_ENABLE_DUAL_MODE=false`；t008 AC-003 `SELKIES_FILE_TRANSFERS=none`；t014 AC-005 剪贴板策略锁定（二进制关闭）；每项须真实负例。Selkies 2.1.0 源码参考 `.scratch/v2_orchestration/t004_start_packet/upstream_selkies_2_1_0/`，Web 客户端参考 `.scratch/v2_orchestration/selkies_web_ref/`，t007 契约草案 `.scratch/v2_orchestration/t007/contract_draft.md`（可见性/活动上报内容按 9.3 改写）。容量/P95/8 小时/1000 次压力属 t009，未跑不得宣称通过。
