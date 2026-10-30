# 项目交接记录（最新）

本文件只保留当前有效一节。过时段落迁入 `docs/archive/handoff.md`（Codex 主控时期的 t001–t005 过程记录已整体迁档）。

## 2026-10-30T10:30:00+08:00 v2 架构计划执行交接（t005 完成，t006 开工）

- branch：main
- head_commit：2743ed7（t005 merge，本次 docs commit 前）
- 执行目标：完成 docs/v2_architecture_plan.md 剩余 task t005→t006→t007→t008→t013→t014→t009→t010→t011→t012，每 task 一个执行 commit，逐个合入本地 main；最终部署到本机 OrbStack，由本机官方 Chrome 访问。禁止 push 与外部发布。
- 已定决策：重试为首次异常后 2/10/30 秒三次重试、failure_count=4 阻断、手动重试清除（ADR 008）；管理员密码在 data/secrets/admin_password（只在生产首次启动读取，测试一律随机密码）；公网 WebRTC/TURN 穿透与原生 Linux x86_64 执行为 USER_WAIVED（不能写成通过）；性能按本机 OrbStack + Chrome 实跑。
- 子 agent：OpenCode `cpa/gemini-3.8-flash --variant high`，经 `.scratch/v2_orchestration/dispatch.py`（权限白名单 + 全交付文件 SHA 守卫）→ `run_opencode_observed.py`（已补 `--variant high`，保留 `--env-root`）。主控 owner_id 记录在 `.scratch/v2_orchestration/claude_owner_id.txt`。

### 当前恢复入口

#### t005 已完成并合入 main

- 执行 commit 3b5576e9dd0990a21aaaa66965133e0a91bb2f5c；merge 2743ed7509f4（merge(t005)）；分支已由工具删除，worktree 已 exact cleanup。attempt1 terminal=completed、report=done。
- 验证：冻结候选主控全门禁（contract 169、legacy 384、unit 211、integration 21、Runtime 13、Stream 12〔Chrome 2 秒帧 59→16→60〕、Supervisor 生命周期 6、启动恢复 2、容器图等 8、内核策略 5、资源 5）；独立 OpenCode 黑盒在逐字节等同候选的 validation WT 自建镜像复跑同数通过并以 4 个自写探针验证 AC-001/002/003/005（重试实际 3.45/12.53/31.82 秒含真实 SIGKILL）；Full review Round1 两路 PASS（2 minor），Round2（md_kx 缩进与 p002 修复）两路 PASS，checker overall=PASS。合并后在 merged tree 复跑全套门禁全部通过（contract 168+1 skipped 为主仓 sync_state 预期行为）。
- 遗留：p001（RecoveryCoordinator.tick 复杂度，minor）；p002 已修并归档。Round2 两路 wrapper 因派发时未互相排除对方报告文件被 SHA 守卫中断（报告均已写完），今后 reviewer 派发需同时 unguard 两份报告。
- 证据备份：`.scratch/v2_orchestration/retired_worktrees/CBrowser_t005/scratch/`（日志/JSON/报告 28M）、`retired_worktrees/t005_validation/scratch/`（黑盒 1.6G）；GeoIP 缓存 `.scratch/v2_orchestration/geoip_cache/`；通用门禁 runner `.scratch/v2_orchestration/gates/run_gates_template.sh`（GATE_ROOT/GATE_LANE，按轮复制执行）。validation worktree 与 spike/t005_validation 已移除。

#### 后续队列

- t006 接口契约草案：`.scratch/v2_orchestration/t006/contract_draft.md`（auth / gateway〔含 rtc_config 与轮换调度〕/ agent / e2e 四 lane；Gateway 以 API 内部 runtime 绑定判定当前实例，RTC 配置由 Gateway 连接时下发，不新增 API rtc-config 路由）。auth lane prompt 已写 `.scratch/v2_orchestration/t006/lane_auth_body.md`（含现有 12 个启动 API 的测试迁移到共享登录夹具），gateway/agent lane prompt 未写。派发前主控先在 t006 WT 改 `stream_agent/protocol.py`（RTC_CONFIG、注册字段 selkies_version/runtime_state/config_version、HEARTBEAT 载荷）并导出 schema。t006 task.md 含 UNVERIFIED-SPIKE，开工前需改写为已验证结论。
- 通用工具：prompt 外壳 `.scratch/v2_orchestration/prompts/{implementer,reviewer,blackbox}_preamble.md`；lane 状态摘要 `python3 .scratch/v2_orchestration/lane_status.py <jsonl> --text`。门禁 runner 每轮复制快照执行，禁止在运行中修改（round1 曾因此重复一步）。
- 容量/P95/8 小时/1000 次输入等压力验收属 t009，尚未执行，不得宣称通过。
