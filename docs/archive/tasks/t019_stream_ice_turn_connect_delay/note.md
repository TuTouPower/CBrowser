---
tid: "t019"
slug: "stream_ice_turn_connect_delay"
title: "修复 Stream 默认 STUN/TURN 导致的会话建立 5 秒延迟"
status: "done"
branch: "t019_stream_ice_turn_connect_delay"
worktree: ""
review_level: "full"
review_limit: "5"
verify_limit: "5"
diff_anchor: "c7ec89b02003fd32b7ce27b2369ed0f852d9cd4a"
depends_on: ""
conflicts_with: ""
note: "来源 p020：Selkies 默认外部 TURN allocation 超时阻塞每个新 PeerConnection 约 5s"
---

# Task 过程总账

front matter 只经 `task.py` 修改；reviewer 只写对应 `review_*.md`。

## 实施笔记

执行期记录关键步骤、决策、验证、阻塞和用户批准的新轮次上限。

创建期不预测实施步骤。只记有追溯价值的内容；无事项时写“无”。

### 实施（2026-11-03，attempt 1 / exec-main-20261103-t019）

- 根因沿用 p020 已核实结论：Selkies 2.1.0 默认外部 STUN/TURN（OpenRelay）的 allocation 超时使每个新 PeerConnection 的 offer 固定延迟约 5s；生产启动点唯一，为 `config/docker/stream_runtime/entrypoint.sh`。
- 实现（双层，与 file_transfers 的既有双层口径一致）：
  - `src/backend/cbrowser/supervisor/container_spec.py`：`stream_environment` 新增 `SELKIES_WEBRTC_ICE_LITE=true`。
  - `config/docker/stream_runtime/entrypoint.sh`：Selkies 环境区 export `SELKIES_WEBRTC_ICE_LITE=true`（附 ADR 013/t019 注释），exec 参数新增 `--webrtc-ice-lite`。
- 测试（TDD，先红后绿）：
  - 新增 `tests/unit/test_stream_ice_config.py`（首轮 3 条，review 后补至 4 条）：Supervisor env 启用 ICE-lite、entrypoint export+参数双写、entrypoint 活跃行不出现任何外部 STUN/TURN 配置、Supervisor stream_environment 键与值同样禁止外部 STUN/TURN（正则含 `webrtc[-_](turn|stun)` 与 `(turn|stun)[-_]?servers?` 前缀变体）。实现前 2 红 1 绿，实现后全过。
  - 新增 e2e `tests/e2e/test_frontend_app_e2e.py::test_t019_switch_and_refresh_first_frame_within_2s_host_only`：真实 Chrome 下侧边栏切换已运行 Profile 与同 Profile 刷新到首帧各 ≤2s，并断言 getStats 全候选集仅 `host` 类型、远端候选地址恒 `127.0.0.1`（覆盖 AC-001 候选集与 AC-002 时延）。
- 文档闭环：`docs/blueprint/stream_runtime.md`（ICE-lite 落实到启动参数的可验证描述）、`docs/blueprint/testing.md`（会话建立时延与候选类型黑盒断言要求）、`docs/specs/webrtc_remote_display.md`（ICE-lite 强制项累积）、`docs/specs_index.md`（webrtc_remote_display 关联 task 补 t019）。

### 验证（本机实测，云 VM：无 Docker、无 Mac Chrome）

- 模板契约：`pytest .repo_template/tests -q -m contract` → 169 passed。
- v2 unit：`pytest tests/unit -q` → 552 passed，2 failed。两条失败在干净 main（c7ec89b）同环境复跑同样失败，属存量环境性失败、与本 task 无关：`test_repo_hygiene.py::test_tracked_files_do_not_leak_developer_home_paths`（本机 home 路径口径）、`test_runtime_persistence_guards.py::test_terminal_storage_failure_propagates_instead_of_reporting_saved`（chmod 故障注入在本环境不生效）。本 task 新增及相邻测试（test_stream_ice_config、test_selkies_file_transfers、test_stream_clipboard_policy、test_stream_selkies_tokens）全过。
- v2 integration：`pytest tests/integration -q` → 79 passed。
- 前端：`NODE_OPTIONS=--no-experimental-webstorage npm test` → 20 文件 95 passed；`npm run build` 通过且 dist 新鲜度校验通过（构建未污染任何跟踪文件）。本机 Node v24（项目基准 Node 26），结果如实记录。
- 文档格式：`md_format.py --check` 漂移清单仅含两轮 review 的生成报告（存量冻结产物），本 task 改动的 md 文件无漂移。`git diff --check`（排除 docs/archive）干净。
- 黑盒（AC-001 候选集 / AC-002 时延）：`CBROWSER_RUN_E2E=1 scripts/run_gates.sh` 依赖 Docker、真实 Browser/Stream 镜像与同机 Mac Chrome，本云机不具备该环境，**按用户 2026-11-03 明确指令跳过并按 pass 计**；断言已由新增 e2e 用例承载，待具备 OrbStack/Mac Chrome 的环境执行。p020 已在本机 2.1.0 镜像实测 `--webrtc-ice-lite` 后 offer 0.015s，为 AC-002 的既有实测旁证。
- 环境补记：本机无 `uv`/`md_kx`，均临时装入 worktree `.scratch/`（venv 与 uv tool）后按 run_gates.sh 原命令口径执行，未改门禁脚本。

## Review 处置

每个结构化 finding 一行。`已修` 表示本 task 已修复；`遗留` 必须指向 `pNNN` 或 follow-up tid；`撤回` 必须写清理由。critical/important 未解决时不得 PASS。

### Round 1 (2026-11-03T22:47:00+08:00)

code review：PASS，零 finding（review_code.md；其 scope 指纹因 f002/f003 修复过期，后经重签轮次在最终指纹 3f6ff49e67ef77c7 上重签 PASS）。test review：首轮 FAIL，3 条 finding，处置如下（f002/f003 已修并经 Round 2 确认消除；f001 经 Round 3 裁量撤回阻断性、遗留 p021 披露，最终 verdict PASS，详见 review_test.md Round 3 与收尾报告）。

|finding_id|severity|status|rationale|fix_ref|
|---|---|---|---|---|
|t019_test_f001|important|遗留|AC-001 候选集与 AC-002 时延的黑盒执行证据缺失：云 VM 无 Docker/Mac Chrome；按用户 2026-11-03 指令该门禁跳过并按 pass 计、AC 据此勾选，真实环境执行义务转入 p021 追踪|p021|
|t019_test_f002|minor|已修|e2e 远端候选断言补 protocol=udp 与 port 等于该 Profile 的 UDP mux 端口（自 Stream 容器 env 读取）|tests/e2e/test_frontend_app_e2e.py `_assert_host_only_candidates`|
|t019_test_f003|minor|已修|禁止项扫描扩至 Supervisor stream_environment 键与值，正则补 webrtc[-_](turn\|stun) 与 (turn\|stun)[-_]?servers? 前缀变体|tests/unit/test_stream_ice_config.py|

## 收尾报告

### 验收与验证

- task：[`task.md`](task.md)
- 结果：全部满足（AC-001 候选集条款与 AC-002 时延条款按用户指令以环境跳过计 pass，真实环境执行义务见 p021）
- 测试：模板契约 169 passed；v2 unit 552 passed / 2 failed（存量环境性失败，干净 main 基线同为 2 条）；v2 integration 79 passed；前端 Vitest 95 passed + build 通过
- 黑盒：`CBROWSER_RUN_E2E=1 scripts/run_gates.sh` 依赖 Docker 与同机 Mac Chrome，云 VM 不具备，按用户 2026-11-03 指令跳过并按 pass 计；断言承载于新增 e2e 用例，执行债务见 p021
- review：code review PASS（零 finding；Round 1 后因测试修复指纹过期，经重签轮次在最终 scope 3f6ff49e67ef77c7 上重签 PASS）；test review 三轮——首轮 FAIL（f001/f002/f003）→ f002/f003 已修并于 Round 2 确认消除；f001 经 Round 3 裁量：所有者指令改定环境门禁流程计分口径、两条原转 PASS 路径一条环境不可达一条与 finish/integrate 机械互斥，撤回阻断性、转为 p021 追踪的遗留披露项，最终 verdict PASS（coverage 1/3：AC-003 re_verified，AC-001/AC-002 trust_prior，保留合并前人工抽查建议）
- AC 判定：见 `task.md` 行内打勾

### 结果摘要

- Stream 启动双层启用 Selkies ICE-lite（Supervisor env + entrypoint export/CLI 参数），关闭默认外部 STUN/TURN 路径；unit 门禁双层禁止外部 STUN/TURN 配置回退。
- 遗留：p021（t019 黑盒用例真实环境执行证据）。

### 长期文档闭环

本 task 须出现在 specs_index 的关联 task 列；无长期 spec 变更时写 `- specs_index: not_applicable: 具体原因`。正式 spike 须有 report、现存 finding、采纳结论、后续 tid 或无需后续理由；finish 会检查这些引用。
