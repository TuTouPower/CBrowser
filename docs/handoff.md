# 项目交接记录（最新）

本文件只保留当前有效一节。上一节已追加到 `docs/archive/handoff.md`。

## 2026-11-01T12:41:21+08:00 Runtime 门禁通过，Stream 门禁失败待闭环

### 当前状态

- branch：main；head_commit：`7819d3aefd66be3920f3b08a9faa7ac2e27bb656`（本文另行提交）。接手时工作区干净；当前另有一个独立只读审核 worktree。
- t001–t007 done 并已合入；冻结队列未修改，t006/t007 integrated，goal-check 为 GOAL_QUEUE_INCOMPLETE（2/9 closed）。
- 无 active attempt；t008 尚未 start/reserve/claim。剩余顺序：t008 → t013 → t014 → t009 → t010 → t011 → t012。
- 用户附件明确授权队列逐项本地合并；禁止 push 与外部发布。最终目标仍为完整 v2 本机 OrbStack + 官方 Chrome 交付。

### 本轮验证证据

- 证据目录：`.scratch/v2_baseline_20261101/`；源版本见 `source_commit.txt`，不可变镜像见 `images.env` 与六个 `.iid`。
- Browser、Stream、Supervisor、API fixture、正式 Gateway 与 Gateway fixture 均由当前源码重建成功；日志 `build_*.log`，汇总 `build_results.json`。
- 后端 unit：`unit_r2.log`，383 passed。旧后端 + integration：`backend_r2.log`，446 passed。
- Vitest：`vitest.log`，退出码 0。前端生产构建：`frontend_build.log`，退出码 0，prebuild vendor 与 postbuild verify 均执行；tsconfig.tsbuildinfo 已恢复到原 HEAD 字节。
- 模板契约：`contract.log`，168 passed、1 skipped、477 deselected。文档格式：`md_format.log`，格式一致。
- 五项生成契约：`schema_results.json`，OpenAPI、Stream/Supervisor/Runtime Agent 协议、前端生成类型均退出 0 且字节不变。
- Ruff 全量检查非零；`ruff_efwi.log` 在 E/F/W/I 范围为 90 errors，未修复或豁免；扩大默认规则检查另见 `ruff.log`。不得声称全门禁通过。
- 初始 unit/integration 因 basetemp 父目录未准备失败；已保留 `unit_initial_setup_failure.log` 等日志，补建目录后重跑通过。旧后端原 PYTHONPATH=src 缺 v2 包，补用 src:src/backend 后通过，未改业务代码或断言。

### 在运行与恢复入口

- 主控验证 runner：PID 73111，工具 session 82335，脚本 `.scratch/v2_baseline_20261101/run_checks.py`；外层 flock 为 `.scratch/docker_e2e.lock`，已实查由该 PID 持有。
- runner 串行运行 Runtime、Stream、Supervisor、Gateway 与前端真实 E2E；按 `check_results.json`、当前日志、实际 PID/session 判断状态。不要因观察超时重启；旧 unit/integration/legacy 失败项以上述 r2 日志为补跑证据。
- 独立后端补跑 session 49772 已 exit 0；unit 补跑 session 25178 已 exit 0。无实现子 agent。
- 旧生产 cbrowser、其他项目与来源不明容器/网络保留，未清理、未重启 OrbStack、未扩大 Docker 配额。

### 下一步

- 继续观察 session 82335，复核真实 E2E 正负例与当前候选镜像；失败先归因。补齐 lint 门禁结论后才能启动 t008。
- OpenCode 实际模型列表已确认存在 `cpa/gemini-3.8-flash`；后续实现按用户指定 OpenCode 模型派发独立 lane。
- 已读编排脚本；已知 observed wrapper 不能以外层退出码证明成功，须读 JSON error、cli_exit 与交付证据。未修改编排工具或 `.repo_template`。
- 公网穿透与原生 Linux x86_64 执行始终单列 NOT_RUN / USER_WAIVED；8小时与1000次输入/剪贴板尚未运行，不预先计通过。

### 最新失败阶段与独立审核

- Runtime：`runtime.log`，13 passed（167.80 秒），对应本轮当前源码镜像。
- Stream：`stream.log`，17 passed、2 failed（142.13 秒）。失败：`test_stream_runtime_multi_viewer_e2e` 的精确挂载清单漏新增 `/tmp/selkies_credentials.json`；`test_e2e_ac010_gateway_topology_runtime_in_secure_mode_with_chrome` 在 API 容器端口查询出现 KeyError `8000/tcp`。不得以放宽旧断言、缺镜像或未就绪充当有效负例。
- root 初步归因：`root_failure_triage.json`。Supervisor/Gateway/API Dockerfile 白名单未复制已被导入的根模块 `cbrowser.secret_files`（API 还导入 Gateway endpoint）；静态缺口已核对，实际 import/退出日志尚待独占 Docker 验证，不能宣称实测根因。
- Supervisor 门禁在 session 82335 中继续，已出现失败但尚未结束；后续 Gateway/前端 E2E 由同 runner 串行推进。当前未修改生产文件。
- 独立只读 lane：`/Users/karson/kar/code/CBrowser_baseline_audit`（detached HEAD 7819d3a），OpenCode `cpa/gemini-3.8-flash --variant high`；dispatch PID 76042、wrapper PID 76237、CLI PID 76238，工具 session 59258。
- lane 输出：主仓 `.scratch/v2_baseline_20261101/audit.jsonl`、`audit_wrapper.log`；报告目标为审核 worktree `.scratch/baseline_audit/report.md`。原 tracked 文件已 SHA 守卫，只允许写 lane scratch。XDG data/cache/state 重定向主仓 scratch，未改 observed wrapper；它只读全局 DB，因此仍以 JSON、CLI 实际退出与报告判定，不据外层 exit 0 采信成功。
- 无新增 task、无 attempt identity；未变更冻结队列。审核 worktree 用完须先备份 scratch，再 worktree remove/prune；不得遗留到最终交付。
