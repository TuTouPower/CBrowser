# 项目交接记录（最新）

本文件只保留当前有效一节。上一节已追加到 `docs/archive/handoff.md`。

## 2026-11-01T07:58:10+08:00 t007 已合入，准备 t001–t007 累计四模型审阅

### 一、当前状态

- branch：main；head_commit：`f420d7fb0767d1768a22a57ce552b21d86d62a72`（t007 merge，本文另行提交）。
- t001–t007 全部 done 且已合入 main。t007 执行 commit `faee1f3`，本次 merge commit `f420d7f`；`t007_v2_frontend_sessions` 已由 integrate 删除，仅剩 main 与主 worktree。
- t007 exact identity：attempt=1，execution_id=`1a08cbc562094e73ae64c8039127ed0a`；原执行 owner_id=`claude_v2_6e1f7a8e7a46`。本次沿原 identity 完成集成，未创建新 attempt。
- 合并后门禁：`.scratch/t007_postmerge/codex_pm1/summary.txt`，35 步全部 rc=0；六个镜像当前源码构建，ID 在同目录 `images.env`。契约 168 passed / 1 skipped，旧后端 384、unit 307、integration 55、Vitest 105；Runtime 13、Stream 19、Supervisor 生命周期 6 / 启动恢复 2 / 拓扑 8 / 网络策略 5 / 资源 5、Gateway 5、前端 E2E 22 全部通过。本轮无失败复跑；schema/codegen、Ruff、文档格式、diff、既有服务 health 与模板状态均通过。
- 门禁 runner 快照：`.scratch/v2_orchestration/gates/run_gates_t007_codex_pm1.sh`；输出 `.scratch/v2_orchestration/gates/t007_codex_pm1.out`。Docker 测试锁已释放。
- `task.py goal-check`：t006/t007 均 integrated，GOAL_QUEUE_INCOMPLETE 2/9 closed；后续七项无 attempt。

### 二、本次后续工作

1. 用户要求按 `/Users/karson/kar/code/my_file/coding_agent/skills_mine/my-review/SKILL.md` 将 t001–t007 **全部累计改动合在一起审阅，不按 task 拆分**。
2. 四路：Codex `gpt-6.1-sol`、OpenCode `cpa/gemini-3.8-flash`、`opencode-go/deepseek-v4.1-flash`、`opencode-go/muse-spark-1.3-contributor`；思考强度全部 high。用户确认每路上限 60 分钟。
3. 每路审同一冻结累计范围，以 t001 diff_anchor `3c8bdbc55570e85aaeb6365a3d512da9c0ce180c` 为基线，target 为本次交接提交后的 main。只读源码，仅写独立 review 报告；不做修复、不启动 t008、不 push。
4. my-review 原脚本仅内置 Claude/Kimi/Grok 路由；已向用户说明按指定 Codex/OpenCode 派发，保留输出目录、独立报告与超时状态流程。
5. 审阅完成后报告各路实际完成/超时情况与文件位置，不合并各路结论。审阅产物位置与运行状态以 `docs/reviews/review_*/_meta/_meta.json` 为准。

### 三、执行目标与硬约束（原升级目标；本次只授权合入 t007 与累计审阅）

- 目标：按冻结队列 t006 → t007 → t008 → t013 → t014 → t009 → t010 → t011 → t012（`docs/runtime/goal_queue.json`，不得改成员与顺序；t013/t014 串行）完成 `docs/v2_architecture_plan.md`；每 task 一个执行 commit，逐个合入本地 main；最终本机 OrbStack 部署、本机官方 Google Chrome 访问（登录 → 选 Profile → WebRTC 浏览）。完成判据：14 个 task 全部 done 并合入；只剩 main 分支与主 worktree；旧 VNC/RFB/原生桌面移除；生产构建本机可用；门禁与黑盒主控复核；`task.py goal-check` 输出 GOAL_QUEUE_COMPLETE。最终报告列每 task 的 commit、验证证据、USER_WAIVED 项与残余风险。
- 只能写 `~/kar/code` 以内；临时文件写各 worktree 的 `.scratch/`，不写 /tmp、~/.cache。
- 管理员密码 `/Users/karson/kar/code/CBrowser/data/secrets/admin_password`（0600，gitignore）：只在生产首次启动读取并以 Argon2id 保存；明文不得进日志、报告、测试快照；测试一律每次随机生成密码。缺其他 secret 停下来问用户，禁止自设默认值。
- 公网 WebRTC/TURN 与原生 Linux x86_64 记 NOT_RUN / USER_WAIVED。只部署本机，禁止 git push 与任何外部发布。
- task 状态只经 `.repo_template/scripts/task.py`；TDD 先红后绿；禁止就地改旧测试预期（旧语义失效整项删除并说明、另写新测试；本 task 新增的测试可补强）。`.repo_template` 工具链缺陷报告用户，不自行绕过或修改。
- task 执行 commit 的 first parent 必须是 diff_anchor；禁止在 task worktree merge/rebase main。时间戳一律 `date -Iseconds` 实取。
- Docker 只清理本任务前缀且标签核对过的对象；不碰其他项目容器（kkmail、new-api、haiwa-bot、lobechat 等）；来源不明网络 net_9335ab04/net_d876dc01/net_e5052de6、容器 test-shm-srv、旧 cbrowser 容器在 t011/t012 前不动。用户已授权 Docker 引擎无响应时重启 OrbStack。
- worktree 用完必须 `git worktree remove` + `git worktree prune`；删除前备份 `.scratch` 证据。发现 commit/worktree 混入无关改动立即停止报告用户。
- 每个阶段更新本文件（只留最新一节，旧节追加到 `docs/archive/handoff.md`）并在 main 提交 docs；记录子代理 PID/session。
- 用户偏好（`~/.claude/projects/-Users-karson-kar-code-CBrowser/memory/`）：所有浏览器测试一律无头，不得弹窗或抢前台；实现交子代理，主控只派发、整合、复核、门禁；子代理模型 `cpa/gemini-3.8-flash --variant high`，额度用尽改 `opencode-go/deepseek-v4.1-flash --variant high`（两者均获批；Gemini 早已耗尽，t007 全程用 DeepSeek）。
- 全局约定：中文简洁回复；不用 `git reset --hard` / `git checkout --` / 批量删除（除非用户确认）；新文件 snake_case；4 空格；日志不用 print；密钥不硬编码。

### 四、后续 task 要点

- t008（Artifacts/CDP 自动化，`docs/tasks/t008_v2_artifacts_automation/task.md`，4 条 AC）：Artifact 上传/下载/删除与配额、外部自动化经认证入口 → Supervisor → UDS → loopback CDP、Selkies `file_transfers=none`（Stream 入口已设 `SELKIES_FILE_TRANSFERS=none`，需补测试证据）、Agent 重启后扫描补登下载。前端 `/profiles/:id/files` 与 `/automation/:id` 目前是占位页（`features/artifacts`、`features/automation`）；设置页与新建页残留硬编码文案见 p007 可顺带收口。t008 需以 t007 合入后的 main 为基线开工。
- t013（复制/重置）、t014（剪贴板与完整输入）、t009（整机验收：容量/P95/8 小时/1000 次输入）、t010（旧数据迁移，先备份可恢复）、t011（移除旧 VNC/RFB/原生桌面与旧 UI 组件、旧测试）、t012（Compose 生产交付）。
- t012 必须：API 设置 `CBROWSER_SUPERVISOR_URL` + `CBROWSER_SUPERVISOR_TOKEN_FILE` + `CBROWSER_REQUIRE_SUPERVISOR=1`（未配置时 API 只显式禁用协调）；生产镜像构建固定 `scripts/vendor_selkies_web.py` → `npm run build`（p010；清单现位于 tests/fixtures 下，宜迁出）；处理 p006（`agent_secret.txt` 仍在挂进 Browser 的 runtime 目录）。

### 五、t007 结果摘要（细节见 t007 分支 `docs/archive/tasks/t007_v2_frontend_sessions/note.md`）

- 交付：React Router 7 外壳 + 登录守卫（`RequireAuth`、`/login?next=` 同源校验）、OpenAPI 生成类型（`npm run generate:api`，禁止手写）、TanStack Query + SSE（事件 id `<epoch>:<seq>`，跨进程发快照）、页面独立 `?profileId=`、官方 Selkies 2.1.0 iframe + 单一来源适配层（`features/browser-session/adapter.ts` 经 `vite.selkies.config.ts` 构建为 IIFE `dist/selkies/selkies_adapter.js`；vendor 脚本只注入标签）、会话阶段诊断与独立音频状态、冻结恢复重建、ICE disconnected 5 秒宽限、每页静音（官方 pipelineControl STOP/START_AUDIO）、显示尺寸“应用并重启”、API Runtime Coordinator 驱动 Supervisor（p003 闭环）、每 Profile Selkies token + 安全模式 + Agent HELLO 代注入（d024，p004 闭环）、token 文件只挂给 Stream 且每实例新文件名 `runtime/.secrets/<profile>/selkies_tokens_<instance>.json`、Stream 分辨率取自 Profile 配置。
- 验证：最终门禁 r5 全绿（前端 E2E 21/22，唯一失败为 AC-001 静止画面出帧抖动，复跑 2/2，p013）；独立 DeepSeek 黑盒 r1 AC-001..010 自写探针全 PASS；Full review 5 轮，Round 5 两路 PASS 零 finding（reviewed_scope a006b995998b9c28）。
- 遗留 pending（在 t007 分支，合入后进 main）：p005（t006 minor）、p006（agent_secret 挂进 Browser）、p007（前端残留硬编码文案）、p008（Agent 隧道未触发 Selkies RESUMED）、p009（multi_viewer 固定 sleep 抖动）、p010（生产构建 vendor 步骤，归 t012）、p011（评审 minor）、p012（同 tab 驱逐关闭码偶发 1006）、p013（AC-001 静止画面出帧抖动）。
- 证据备份：`.scratch/v2_orchestration/retired_worktrees/CBrowser_t007/`（`project_gates/r1..r5`、`r*_rerun`、`r4_final`、`lane_evidence/<lane>/`、`t007_master/` 主控 RED/GREEN 与调试记录、黑盒 `lane_evidence/blackbox_r1/`）；lane 会话日志 `.scratch/v2_orchestration/t007_*_r*.jsonl`，prompt 在 `.scratch/v2_orchestration/t007/`。被叫停的合并后门禁残留输出 `.scratch/t007_postmerge/pm1/`（只到镜像构建，作废）。

### 六、已知偶发与环境注意（复跑归因，不放宽断言）

- `test_stream_runtime_e2e.py::test_stream_runtime_multi_viewer_e2e` 固定 sleep 2 秒（p009）；`test_browser_runtime_e2e.py::test_ac006_minimal_privileges_and_access_control` 偶发 Pulse 连接拒绝；`test_supervisor_namespace_policy_e2e.py` 偶发公网 IPv4 出站超时；`test_frontend_app_e2e.py::test_ac001_ac006...` 静止画面不出新帧（p013）；`test_stream_selkies_tokens_e2e.py` 同 tab 驱逐关闭码偶发 1006（p012）。
- 验证 worktree 内跑模板 contract 会有 2 项 `.env` 链接用例失败（TMPDIR 位于已登记 worktree 内，环境差异）。
- 本机 BuildKit 直连 Docker Hub 不稳：构建失败先 `docker pull` 基础镜像；用 sha256 当 FROM 会被当成远程仓库，需先 `docker tag`。
- 本机 OrbStack 单文件 bind mount：同一宿主路径被原子替换后立刻启动的新容器可能看到失效条目（t007 已改为每实例新文件名规避）。

### 七、编排工具与踩坑（`.scratch/v2_orchestration/`）

- 门禁：`gates/run_gates_t007.sh`（每轮复制为 `_rN.sh` 再跑；环境 `GATE_ROOT/GATE_LANE/GATE_BASE/RUFF_BASELINE`；镜像 ID 写入 `<lane>/images.env`）。顺序：构建镜像 → npm ci → Vitest → vendor → build（随后还原 `src/frontend/tsconfig.tsbuildinfo`）→ contract/legacy/unit/integration → Runtime/Stream/Supervisor/Gateway/前端 E2E → schema 与前端生成类型漂移 → ruff → md_format → diff_check → health → task list。t008 起复制一份按需增删测试文件。
- Docker 互斥：运行任何 Docker E2E 前 `mkdir docker_e2e.lock`（原子），结束 `rmdir`；**测试代码内不得自带锁或引用 `.scratch` 编排目录**（t007 曾因此门禁自锁）。
- lane：`lane_worktrees.py create <task_wt> <lane>` / `retire <lane_wt> <backup_dir>`；`launch_lane.py LANE WT PROMPT LOG OUT [ALLOW_GLOB...]`（环境变量 `OPENCODE_LANE_MODEL=opencode-go/deepseek-v4.1-flash OPENCODE_LANE_VARIANT=high`）；续行用 `dispatch.py ... --session <ses_id> --unguard-changed`（**lane 自己新建的文件若不加 `--unguard-changed` 会被 SHA 守卫误杀**）；并行 reviewer 须互相 unguard 两份报告，门禁并发时还要 unguard `tsconfig.tsbuildinfo` 与 schema 导出文件。prompt 模板：`t007/t007_fe_e2e_prompt.md` 前 30 行（写域与质量规则）+ `t007/lane_*_body.md` + `t007/common_tail.md`。
- 合入 lane：在 lane WT 比对 `git show HEAD:<f>` 与任务 WT 当前文件确认无冲突后 `cp -p`，新文件 `git add -N`；**不要对任务 WT 运行 `lane_resync.py`**。lane 常见问题：改测试夹具 Docker 前缀、未跑 ruff、模型连接 ECONNRESET（同会话续跑即可）。
- review：`render_review_prompts.py --task-dir ... --out-dir ...` 渲染后前置主控约束；`check_review_status.py` 判 PASS。**审查指纹包含 `docs/specs_index.md` 等非过程文档**（排除 note/handoff/review 报告/pending/findings/archive/.scratch），PASS 后改这些会变 stale；review 上限 5 轮，超出需用户批准。处置表只接受 `tNNN_code_fNNN` / `tNNN_test_fNNN` 编号。
- 收尾：handoff.json（task 目录）→ `preflight --require-verified --owner-id` → `finish` → 一个执行 commit → `attempt terminal --status completed` → `attempt report --status done --sha` → 备份 `.scratch` → `cleanup-worktree` → `integrate`（暂存）→ 合并后门禁 → `integrate --continue`。
- 工具链缺陷（已报告用户，本次经用户同意由主控补完）：`cleanup-worktree` 调用 `git worktree remove` 60 秒超时（含 node_modules/public 的前端 worktree），留下半删目录与 prunable 登记并提示“数据不一致”。后续若再超时须报告用户。
- zsh 不对未加引号变量分词，多参数循环用 `bash -c`；后台命令里用绝对路径（会话 cwd 可能变化）。

### 八、本地临时对象（可按前缀清理）

- 镜像：`t007-*`（lane 与门禁构建）、`cbrowser-gate-*`、`t007-master-dbg-stream:1`、`t007-master-dbg-stream-base:1`、`t007-master-supervisor:tokinst`、`t007-master-api:tokinst`、`t006-*`、`t005-*` 等，均可由源码重建，未清理。
- `.scratch/selkies_wheels/`：固定 Selkies 2.1.0 wheel 缓存（vendor 脚本默认路径）。
- `.scratch/v2_orchestration/handoff_backup/`：本次撤销合并前的 handoff 文件备份。
