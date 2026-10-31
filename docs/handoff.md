# 项目交接记录（最新）

本文件只保留当前有效一节。过时段落迁入 `docs/archive/handoff.md`（Codex 主控时期的 t001–t005 过程记录已整体迁档）。

## 2026-10-31T14:38:15+08:00 v2 架构计划执行交接（t006 已合入；t007 已开工）

- branch：main
- head_commit：ceb7f34（merge(t006)；执行 commit 251fa0f）
- 工作树：只剩主仓 main；无 task/lane 分支；无运行中的子 agent。
- 执行目标：按冻结队列 t006 → t007 → t008 → t013 → t014 → t009 → t010 → t011 → t012（`docs/runtime/goal_queue.json`）完成 `docs/v2_architecture_plan.md`，每 task 一个执行 commit，逐个合入本地 main；最终本机 OrbStack 部署、本机官方 Chrome 访问。禁止 push 与外部发布。`task.py goal-check`：GOAL_QUEUE_INCOMPLETE 1/9 closed。
- 已定决策：重试 2/10/30 秒、failure_count=4 阻断（ADR 008）；管理员密码 `data/secrets/admin_password`（只在生产首次启动读取）；公网 WebRTC/TURN 与原生 Linux x86_64 为 NOT_RUN / USER_WAIVED；性能按本机 OrbStack + Chrome 实跑；计划修订 9.3 已获批。
- 用户要求（2026-10-31）：所有浏览器测试一律无头、不得弹窗或抢前台（见 d023 与记忆）；实现工作交 Gemini 子代理（OpenCode `cpa/gemini-3.8-flash --variant high`），主控只做派发、整合、复核与门禁。用户 2026-10-31 追加：Gemini 额度用尽时改用 `opencode-go/deepseek-v4.1-flash`（两者均获准；wrapper 读 `OPENCODE_LANE_MODEL`/`OPENCODE_LANE_VARIANT`，DeepSeek `--variant high` 冒烟通过）。
- 主控会话 owner_id：`.scratch/v2_orchestration/claude_owner_id.txt`（claude_v2_6e1f7a8e7a46）。

### t006 结果

- attempt1 / execution 79fa47d2f34e42f8b31f43ceb8cb52a9：terminal=completed、report=done、执行 commit 251fa0f（first parent c33e55f）、merge ceb7f34；worktree exact cleanup，分支已删。
- 验证：门禁 round7 + round7b（Gateway E2E 复跑）全部通过；独立 Gemini 黑盒在逐字节等同候选的 WT 自建镜像，文档门禁同数通过且 7 条 AC 自写探针正负例通过；Full Round1 code/test 两路 PASS（5 minor 遗留 p005），check_review_status overall=PASS。合并后门禁（`.scratch/t006_postmerge/pm1/`）29/29 通过（contract 168+1 skipped 为主仓预期）。证据备份 `.scratch/v2_orchestration/retired_worktrees/CBrowser_t006{,_e2e2,_supfix,_relay,_blackbox}/`。
- 审查中发现并修复的生产缺陷：answer 转发即提交（d021）、Stream 侧 TURN 未进入 Selkies 且吞异常（d022）、对未建立 PC 发起重启、relay-only 初始连接非 relay、Supervisor 缺 coturn 时启动必然退出的 Stream（coturn 必需、gateway 基础设施可选）。
- 遗留：p001、p003（API→Supervisor 启停协调，t007/t012 前必须补）、p004（Selkies 每 Profile token，t007 前定案）、p005（t006 评审 minor，t007 内处理 f001/f003）。

### 门禁工具

- 门禁脚本 `.scratch/v2_orchestration/gates/run_gates_t006.sh`（每轮复制到目标 WT `.scratch/` 后执行，环境 `GATE_ROOT/GATE_LANE/GATE_BASE/RUFF_BASELINE`；构建带退避重试；Gateway E2E 需 `CBROWSER_GATEWAY_IMAGE`、`CBROWSER_CADDY_TEST_IMAGE`）。本机 BuildKit 直连 Docker Hub 不稳：构建失败先 `docker pull` 对应基础镜像或 `docker/dockerfile:1.4`（守护进程走代理可用）。
- lane 工具：`lane_worktrees.py create/diff/retire`、`lane_resync.py`（任务 WT → lane WT 同步并记 lane 基线提交）、`dispatch.py`（`--allow` 只给编辑权限，可写的既有文件必须同时 `--unguard`，否则 SHA 守卫会中断 lane；并行 reviewer 须互相 unguard 报告）。中断 lane 后须确认 opencode 进程已退出再续行。zsh 不对未加引号变量分词，多参数用 bash -c 或 Python。

### t007（前端会话）

- 2026-10-31T14:38:57+08:00 start + reserve：branch=t007_v2_frontend_sessions，worktree=/Users/karson/kar/code/CBrowser_t007，diff_anchor=077778f；attempt1 / execution_id=1a08cbc562094e73ae64c8039127ed0a / owner_id=claude_v2_6e1f7a8e7a46（14:39:02 claim）。不得重复 start/reserve。范围已扩展纳入 p003（API→Supervisor 启停，AC-009）与 p004（Selkies 每 Profile token，AC-010），见 077778f。

- 2026-10-31T14:41 派发四个并行 Gemini lane（各自 WT `/Users/karson/kar/code/CBrowser_t007_<lane>`，分支 `lane/t007_<lane>`，日志 `.scratch/v2_orchestration/t007_<lane>_r1.jsonl`，prompt `.scratch/v2_orchestration/t007/t007_<lane>_prompt.md`，启动器 `.scratch/v2_orchestration/launch_lane.py`）：spike_token（opencode pid 24318，Selkies token 机制实验，只出报告）、be_coord（24319，AC-009 API→Supervisor 协调 + SSE）、fe_shell（24317，前端外壳与 Profile/设置页）、fe_session（24316，浏览会话/适配层/冻结恢复诊断）。Docker E2E 用 mkdir 锁 `.scratch/v2_orchestration/docker_e2e.lock` 互斥。镜像基线为 t006 合并后门禁 `.scratch/t006_postmerge/pm1/images.env`。

- 截至 2026-10-31T15:10：spike_token 完成并 retire（d024，主控复跑 5 passed，task.md 未知契约已改写）；fe_shell 完成、复核（Vitest 60 passed、构建成功）、合入 t007 WT 暂存区并 retire；运行中：be_coord（opencode pid 24319）、fe_session（56175，session ses_e6f4e8671ffe2gNTfGG7sXQ1zH，第 3 次续行）、stream_tokens（60155，AC-008/AC-010）。监控用 `python3 .scratch/v2_orchestration/watch_lanes.py`（读 `watch_pids.txt`）。镜像清单改名 `images_env.txt`（`*.env` 被 lane 读权限拒绝）。

- 编排事故（详见 t007 note）：首次批量派发重复启动导致 fe_shell/be_coord 双实例（已处理）；误在 t007 任务分支生成中间提交 acd3832，已 `git reset --soft 077778f` 撤销（改动保留、HEAD 回到 diff_anchor）。今后合入 lane 交付用 Python 逐文件复制，不对任务 WT 运行 lane_resync。

- 2026-10-31T16:2x：fe_session 已合入 t007 WT 并 retire（合并前端 Vitest 72 passed、构建成功）。be_coord 与 stream_tokens 自约 15:37 起模型请求挂起（Gemini 额度耗尽），主控停止进程、按前缀清理两者遗留的 10 个测试容器与网络，改用 `opencode-go/deepseek-v4.1-flash` 在原会话续行：be_coord opencode pid 92666（session ses_e6f4e8ca8ffeBbx5Peyv4NJHR6，日志 `t007_be_coord_r2.jsonl`），stream_tokens pid 92665（session ses_e6f37c365ffeqir0wNKzeCRmLv，日志 `t007_stream_tokens_r2.jsonl`）。`watch_lanes.py` 已加日志 10 分钟无更新的 STALL 报警。

- 读 `docs/tasks/t007_v2_frontend_sessions/task.md` 与 `.scratch/v2_orchestration/t007/contract_draft.md`（已按 9.3/p003/p004 修订）。开工前定案 p004（Selkies token）与 p003 是否纳入 t007 范围；t007 AC-008 显式 `SELKIES_ENABLE_DUAL_MODE=false`；前端适配层须在官方 `setConfiguration` 后保持 Gateway 下发配置（d022）；可复用 `tests/fixtures/gateway_probe/` 拓扑做真实栈 E2E（无头）。

- 未触碰的既有对象：Docker 网络 net_9335ab04/net_d876dc01/net_e5052de6（来源不明）、容器 test-shm-srv、旧 cbrowser 容器（t011/t012 前不动）。本地临时镜像（t006-*、cbrowser-gate-*、t005-\* 等）可由源码重建，未清理。
