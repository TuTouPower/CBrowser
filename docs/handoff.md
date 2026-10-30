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

#### t006（branch=t006_v2_gateway_auth_rtc，base/diff_anchor=c33e55f，worktree=/Users/karson/kar/code/CBrowser_t006）

- identity：attempt1 / execution_id=79fa47d2f34e42f8b31f43ceb8cb52a9 / owner_id=claude_v2_14b38abc09f2（已 reserve+claim，不得重复 start/reserve）。UNVERIFIED-SPIKE 已改写为已验证结论（前置协议、d003/d007/d008/d009/d010/d012/d018/d019、argon2id 实测），strict preflight PASS。
- 主控预置（t006 WT 未提交）：stream_agent/protocol.py 新增 AgentAction.RTC_CONFIG、注册字段 selkies_version/runtime_state/config_version、AgentHeartbeatPayload、IceServer/RtcConfigPayload（凭证 SecretStr）；schemas/stream/agent_protocol.json 重新导出；tests/unit/test_stream_agent_protocol_v2.py 先 RED 后 GREEN 6 passed。此时 agent.py 尚未补新字段，由 agent lane 完成。
- 接口契约 `.scratch/v2_orchestration/t006/contract_draft.md`。三个实现 lane（各自独立 worktree，lane 分支 lane/<name> 仅含种子 commit，不进 task 分支；完成后由主控 `lane_worktrees.py diff` 取增量合入 t006 WT，再 retire）：
    - auth：WT /Users/karson/kar/code/CBrowser_t006_auth，session ses_e755e1089ffevyCMuhxHWWKCqJ，续行 wrapper PID 9366 / opencode PID 9379，日志 `.scratch/v2_orchestration/t006_auth_r1b.jsonl`（首启 t006_auth_r1.jsonl 因主控守卫配置错误被中断，未改文件）。
    - gateway（含 rtc_config 与轮换）：WT /Users/karson/kar/code/CBrowser_t006_gateway，session ses_e755e10f0ffe14kMcwhDaswpM2，wrapper PID 3022 / opencode PID 3041，日志 `t006_gateway_r1.jsonl`。
    - agent：WT /Users/karson/kar/code/CBrowser_t006_agent，session ses_e755e10fbffeSIS9q3Yy3T509N，续行 wrapper PID 9367 / opencode PID 9378，日志 `t006_agent_r1b.jsonl`。
- 2026-10-30T15:20:00+08:00 进度：agent lane 已完成并 retire（证据 `retired_worktrees/CBrowser_t006_agent/`），增量已合入 t006 WT；主控补 4 处修正：恢复被改成 importorskip 的 schema 测试、心跳默认 10 秒断言、`resolve_selkies_version` 只读安装元数据（先 RED 后 GREEN）、Supervisor 向 Stream 传 `CBROWSER_CONFIG_VERSION`（新 Stream 镜像 9489b9d4 下容器图先真实 RED「Runtime start failed」后 GREEN 1 passed，Supervisor 临时镜像 a2943b3a）。gateway lane 已完成（报告本 lane 22 passed，镜像 761dcc30），增量已合入 t006 WT 但尚未 retire、尚未逐项复核。auth lane 仍在运行（opencode PID 9379）。合入后 unit+integration 复跑 269 passed / 1 failed（`test_v2_api_subprocess::test_ac004_sqlite_busy_timeout_contention_and_recovery` 计时断言，单跑时两个方向均失败，判定为主机过载导致，非 t006 改动；需在负载正常后复验）。两个由主控中断测试遗留的孤儿 uvicorn（cwd=CBrowser_t006）已核实后终止。
- **环境阻塞（2026-10-30 约 13:00 起）**：OrbStack Docker 引擎无响应超过 2 小时（`docker ps`/`docker info` 不返回，kkmail 的 docker compose 调用同样卡住），主机负载 100–135、CPU 空闲约 0.6%（contactsd 100%、两个非本项目 `opencode --yolo` 会话各约 50–80%）。所有 Docker E2E 暂停；未重启 OrbStack（会中断 kkmail/new-api/旧 cbrowser 等其他服务），等待用户决定。
- 恢复规则：先核 PID 与 JSONL 最终 stop、各 lane `.scratch/<lane>/report.md`；不采信 lane 自述，主控复跑。之后：整合三路增量 → 真实 E2E lane（两 Chrome 页独立隧道、Gateway SIGKILL 恢复、relay-only 两次凭证切换、TLS 登录 Cookie）→ 全门禁 → 独立黑盒 + full review → 一个执行 commit → 合入。

#### 后续队列

- 通用工具：prompt 外壳 `.scratch/v2_orchestration/prompts/{implementer,reviewer,blackbox}_preamble.md`；lane 状态摘要 `python3 .scratch/v2_orchestration/lane_status.py <jsonl> --text`。门禁 runner 每轮复制快照执行，禁止在运行中修改（round1 曾因此重复一步）。
- 容量/P95/8 小时/1000 次输入等压力验收属 t009，尚未执行，不得宣称通过。
