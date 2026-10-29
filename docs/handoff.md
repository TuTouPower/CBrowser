# 项目交接记录（最新）

本文件只保留当前有效一节。过时段落迁入 `docs/archive/handoff.md`（Codex 主控时期的 t001–t005 过程记录已整体迁档）。

## 2026-10-30T05:55:00+08:00 v2 架构计划执行交接（新主控接管）

- branch：main
- head_commit：02d26c3（本次 docs commit 前）
- 执行目标：完成 docs/v2_architecture_plan.md 剩余 task t005→t006→t007→t008→t013→t014→t009→t010→t011→t012，每 task 一个执行 commit，逐个合入本地 main；最终部署到本机 OrbStack，由本机官方 Chrome 访问。禁止 push 与外部发布。
- 已定决策：重试为首次异常后 2/10/30 秒三次重试、failure_count=4 阻断、手动重试清除（ADR 008）；管理员密码在 data/secrets/admin_password（只在生产首次启动读取，测试一律随机密码）；公网 WebRTC/TURN 穿透与原生 Linux x86_64 执行为 USER_WAIVED（不能写成通过）；性能按本机 OrbStack + Chrome 实跑。
- 子 agent：OpenCode `cpa/gemini-3.8-flash --variant high`，经 `.scratch/v2_orchestration/dispatch.py`（权限白名单 + 全交付文件 SHA 守卫）→ `run_opencode_observed.py`（已补 `--variant high`，保留 `--env-root`）。主控 owner_id 记录在 `.scratch/v2_orchestration/claude_owner_id.txt`。

### 当前恢复入口

#### t005（branch=t005_v2_supervisor，head=84f8431，worktree=/Users/karson/kar/code/CBrowser_t005）

- identity：attempt1 / execution_id=8c2fd5e26cdc49f4bd8008edecd1d36e；2026-10-30T05:20:32+08:00 由新主控 `attempt claim --replace-owner root_v2_t005_20261029 --confirm-stopped` 接管，owner_id=claude_v2_14b38abc09f2（原 Codex 会话及其 OpenCode 子进程均已停止，已核进程表）。strict preflight PASS。不得重复 start/reserve。
- 冻结候选全门禁（t005 WT `.scratch/t005_final/round1/summary.txt`）：contract 169、legacy 384、unit 211、integration 21、Runtime E2E 13、Stream 媒体 12（Chrome 2 秒帧 59→16→60）、Supervisor 生命周期 6（SIGKILL/API 离线/2/10/30 重试/failure_count=4）、启动恢复 2、容器图等 8、内核网络策略 5、资源 5 均 passed；Supervisor/OpenAPI schema 导出一致；Ruff、md_format、diff --check 通过。镜像：Supervisor sha256:9cfd93d9dbe3…、API fixture sha256:2396ed5cffc5…、Gateway fixture sha256:8e7946aea2e0…（当前源构建），Browser03 f2a8d42810c1…、Stream07 072e86762d2f…、coturn 4.6.3 e2bca2f79a42…。
- 主控补强（只加断言）：同 Profile 三路并发重复 start 幂等、UDP 端口内外一致且两 Profile 互异、Runtime RestartPolicy=no、Supervisor `/resources` 决策 HTTP 查询与测量窗口一致；testing.md 修正 contract 行（模板契约）、legacy/Stream/OpenAPI 命令依赖。七 AC 已按实证打勾，review scope=fc9c501c863e0460。
- 正在运行（恢复先核 PID 与 JSONL 最终 stop，不得重复派发）：
    - 独立黑盒：wrapper PID 30090 / opencode PID 30110 / session ses_e7663e0e0ffesEOxpy2HrEDCB1；在 validation WT `/Users/karson/kar/code/CBrowser/.scratch/v2_orchestration/t005_validation`（已 apply 候选补丁，588 文件逐字节等同 t005 WT），只写其 `.scratch/t005_blackbox/`；日志 `.scratch/v2_orchestration/t005_blackbox_r1.jsonl`。
    - code review Round1：wrapper 30091 / opencode 30113 / ses_e7663e0d1ffeoEYZnyEUWgRZH6；只写 review_code.md；日志 `.scratch/v2_orchestration/t005_review_code_r1.jsonl`。
    - test review Round1：wrapper 30092 / opencode 30111 / ses_e7663e0e9ffehbXOgOCriVZ4i7；只写 review_test.md；日志 `.scratch/v2_orchestration/t005_review_test_r1.jsonl`。
    - 三个 lane 均以 SHA 守卫 t005 交付文件：lane 运行期间主控不得修改 t005 WT 交付文件。
- 下一步：主控复核黑盒日志与两份 review（逐条核证据）→ 处置 finding（如改动交付则重跑受影响门禁并重新 review）→ check_review_status PASS → handoff.json → finish → 一个执行 commit → attempt terminal/report → exact cleanup（先备份 WT `.scratch` 证据与 GeoIP 缓存 `.scratch/t005_core/engine_cache/geoip` 到 main `.scratch/v2_orchestration/`）→ integrate 合入 main → 合并后门禁。
- 遗留：validation WT（branch spike/t005_validation）在 t005 黑盒结束后备份 `.scratch` 到 `.scratch/v2_orchestration/retired_worktrees/t005_validation/` 再 `git worktree remove` + `prune`。现存 Docker 网络 cbrowser-t003-bb-aece4d57-net、net_9335ab04、net_d876dc01、net_e5052de6 与容器 pensive_satoshi、test-shm-srv 来源未核实，未触碰；旧 cbrowser 容器在 t011/t012 切换前不动。

#### 后续队列

- t006 接口契约草案：`.scratch/v2_orchestration/t006/contract_draft.md`（auth / gateway / agent_rtc / e2e 四 lane）。t006 task.md 含 UNVERIFIED-SPIKE，开工前需改写为已验证结论。
- 容量/P95/8 小时/1000 次输入等压力验收属 t009，尚未执行，不得宣称通过。
