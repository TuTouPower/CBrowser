# 项目交接记录（最新）

本文件只保留当前有效一节。过时段落迁入 `docs/archive/handoff.md`（Codex 主控时期的 t001–t005 过程记录已整体迁档）。

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
