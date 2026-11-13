---
tid: "t055"
slug: "supervisor_runtime_robustness"
title: "Supervisor 运行时健壮性收口"
status: "done"
branch: "t055_supervisor_runtime_robustness"
worktree: ""
review_level: "full"
review_limit: "5"
verify_limit: "5"
diff_anchor: "1c0963845705e355ccdd7e1c3963533c9df7437a"
depends_on: ""
conflicts_with: "t051,t054,t057"
note: "来源 review_20261110_200842 adoption_decision A4-A13"
---

# Task 进展

front matter 只经 `task.py` 修改；reviewer 只写对应 `review_*.md`。

## 实施笔记

执行期记录关键步骤、决策、验证、阻塞和用户批准的新轮次上限。

创建期不预测实施步骤。只记有追溯价值的内容；无事项时写“无”。

### 引用核实（t028 要求：逐项核对，零虚假引用）

- task.md 上下文区给出的 2026-11-10 行号已按 t054 后现状逐项重核：`docker_adapter.py` 的 `_run_policy_helper` / `_install_network_policy`、`core.py` 的 `_ensure_media_attachment` / `_recover_attachment_offline` / 注册分支 / 恢复分支 / `forget_instance_events` / `_lookup_browser_container`、`automation_router.py` 的 finally 块、`runner.py` 的 PortAllocator 构造与两个 watcher、`socket_root.py` 的 `resolve_socket_root` / `prepare_socket_dir` 均已定位到当前行并据实实施；行号已漂移，以实施后文件为准。
- `automation_router.py` 在 `src/backend/cbrowser/api/v1/automation_router.py`（不在 supervisor/ 下）。
- `udp_mux.py` 在 `src/backend/cbrowser/udp_mux.py`（不在 supervisor/ 下）；`udp_mux_bounds()` 已被 `_udp_mux_helper_environment()` 等 6 处消费者共用，仅 runner 自解析。

### Spike 结论（task.md UNVERIFIED-SPIKE 已改写为已验证）

- 实验 `.scratch/spike_close_code.py`（websockets 17.4，验证 venv 实测）：(1) 对端先关 4403，本地 close 前读 `close_code`=4403；(2) 本地先 close（对端未关），close 后 `close_code`=1000（本地自发关码）；(3) 对端先关 4403 再本地 close，close 后仍为 4403。结论：读取点必须在本地 close 之前；A10 读取点定为 `automation_router.py` finally 块内 `upstream.close()` 之前，并以“客户端先断开”标志抑制透传。

### 关键设计决策

- **A7 注册宽限（未按审阅字面“两处一律保留 lost_at”）**：字面做法会破坏 t026 的 stale-grace 回归测试（`test_stale_registration_timestamp_does_not_defer_replacement_after_boundary`：过渡宽限必须在 gateway_unreachable 边界丢弃，否则同一名字重启的 fresh Stream 会被旧宽限延期替换）。改为区分恢复宽限与过渡宽限：`RegistrationState` 新增 `recovery_armed: bool = False`，仅恢复路径置位；两处 gateway 不可见分支（`MEDIA_ATTACH_GATEWAY_MISSING` 与 `registered is None`）在 `recovery_armed` 时保留 state（含 `lost_at`，不重置），否则按原样整对象 pop。宽限内到达的新注册经 `registered` 真值分支立即替换（`RegistrationState(known=True)`，不经过宽限判定）；宽限内未注册 Stream 仍走 `registration_recovery_grace` 等待，宽限到期后走 Stream-only 替换。AC-005 的“90s 内触发”指宽限锚定恢复时刻、到期触发，不因每轮收敛顺延。
- **A7 running 升级**：恢复预置 `starting`；`_reconcile_profile` 的 error-release 条件由 `observed_state == "error"` 扩为 `in ("error", "starting")`，terminal-observation dedupe 随释放一并清除（健康确认即证明该代际未终止，之后的新终态必须可上报；t026 f015 的统一逻辑）。升级后下一轮收敛经既有分支上报 running。
- **A5**：`_native_exit_instances` 的键是 3 元组 `(profile_id, instance_id, config_version)`，按 `(profile_id, instance_id)` 过滤；审阅字面的 2 元组比较永不相等，不可用。line ~2589 的 start 路径整 Profile 清理是有意的（新代际从零开始），未动。
- **A8 字段类型**：`BrowserContainerLookup.observed_instance_id` 由 `str | None` 改为 `tuple[str, ...] | None`（全部异实例 id，去重保序；FOUND 分支同步改为一元 tuple）。调用方日志行以逗号连接。删除不可达的 `except NotFound` 分支（docker-py `list` 对缺失返回空列表）及 `NotFound` 导入。
- **A4 `_install_network_policy` 末尾的 cleanup-error raise 保留**：既有测试 `test_helper_remove_failure_keeps_gate_closed` 断言安装成功但清理失败时 gate 不写 ready；审阅未要求改动，未动。A4 只改：`_run_policy_helper` finally 的 remove 包 try（仅记 warning，不覆盖 exit code）；安装失败分支在 raise 前抓 `helper.logs()`（截断 2000 字节、经共享 `redact()` 脱敏）记 error 日志；`_run_policy_helper` 非零分支的 warning 日志同步走同一脱敏 helper。边界（Round 1 code 审阅结论，不进 finding，AC-001 措辞不改）：超时/传输错误分支不抓 helper 日志——按既有脱敏策略仅报异常类型名，且 daemon 可能无响应时调 `helper.logs()` 有挂起风险；AC-001 的「失败分支」指非零退出分支。
- **A11**：runner 改调 `udp_mux_bounds()` 一次并传给 `PortAllocator`；未给 `udp_mux_bounds()` 加 `lru_cache`（既有测试用 monkeypatched env 逐例隔离，缓存会破坏隔离；env 在进程启动时固定，单次调用即是单一来源）。
- **A12**：slot 清理前校验属主（`managed_uid` 给定时比对 `st_uid`）、类型（须为 socket）、活跃性（connect 探针：成功为活跃，`ConnectionRefusedError`/`FileNotFoundError` 为陈旧，其余 OSError 按活跃 fail-closed）；符号链接、他人属主、非 socket、活跃 socket 均报 `SocketRootError` 且原样保留。`resolve_socket_root()` 增加最长 slot 路径校验（root + 20 字符 slot + `agent.sock` ≤ 100 字节），在 `PathValidator` 构造时（即 Supervisor 启动）生效。
- **A13**：`_close_stream_sync` 拆为每流关闭（`_close_container_stream_sync` / `_close_network_stream_sync`，幂等：取流即清槽），`_close_stream_sync` 保留为关停最终 pass（两流都关）；容器 watcher 的停机竞态抽为与网络版对称的 `_watch_container_events`；`_watch_network_events` 的 `close_streams` 参数改名为 `close_stream`（调用方均为位置传参，无影响）。

### 旧测试处置（按 AGENTS.md：语义失效的旧测试整体删除并写明理由，禁止就地改预期）

- 删除 `tests/unit/test_p058_browser_lookup.py::test_other_instance_is_a_fence_mismatch`：A8 契约变更（`observed_instance_id` 由 str 改为全部异实例 id 的 tuple），旧的 str 相等断言不再表达契约；后继覆盖为新文件 `test_lookup_reports_all_foreign_instances`（双异实例 tuple）与 `test_lookup_reports_single_foreign_instance_as_one_tuple`（单异实例一元 tuple）。
- 删除 `tests/unit/test_a36_socket_root.py::test_prepare_socket_dir_cleans_only_own_slot`：A12 契约变更（slot 内的常规文件不再是“陈旧 socket”而是冲突），旧测试把常规文件当陈旧项清理的语义失效；后继覆盖为新文件 `test_prepare_socket_dir_cleans_stale_socket_and_leaves_other_slots`（真实陈旧 socket 被清理、其他 slot 原样保留）。
- 删除 `tests/unit/test_a36_socket_root.py::test_prepare_agent_socket_dir_rejects_overlong_explicit_root`：A12 要求 socket root 长度在 Supervisor 启动时校验，过长 root 现在 `PathValidator` 构造时即报 `SocketRootError`，不再走到 `prepare_agent_socket_dir` 的 `DockerSandboxError` 包装；后继覆盖为新文件 `test_path_validator_construction_rejects_overlong_socket_root`。
- `tests/unit/test_a36_socket_root.py::test_resolve_socket_root_env_override` 仅改 fixture（`tmp_path` → `short_root`，期望 `root == custom` 未变）：pytest tmp_path 本就超过最长 slot 路径 bound，新契约下不是合法 root；改用短根后仍验证 env 覆盖生效。

### 基线一致的既存失败（非本 task 引入）

- `tests/unit/test_automation_cdp.py::test_supervisor_cdp_websocket_forwards_to_agent_uds`：在干净基线（stash 对照）上同样失败；属 t054 基线 25 个失败中的 “automation_cdp 1” 例。全量回归按名核对时计入基线，不计新增。

### 环境跳过项（按链规则 3：计为 pass，不呈报为待裁定）

- 黑盒门禁 `CBROWSER_RUN_E2E=1 scripts/run_gates.sh`：需真实 Docker/Chrome，本机无，跳过；用户机验证。
- 真实部署/真实引擎验证：本 task 全部 10 条 AC 均为 fake client / 注入异常的单测与真实 websocket 链路集成测试（task.md 可测试性声明：全部 AC 可自动测试），无需要真实部署或真实引擎验证的项。
- t045 wheel 缓存：本 worktree 新建时 `.scratch/selkies_wheels/` 为空（gitignored，不随 worktree 携带），全量回归中 2 个 t045 用例因此失败；已按既定做法用仓库自有 `scripts/vendor_selkies_web.py::download_wheel` 从 PyPI 取回 `selkies-2.2.1-py3-none-any.whl`（内置 SHA-256 校验，pin `18503b5c…a3cd` 通过），重跑 2 个用例通过。不计回归。
- a16 漂移门禁：全量回归中 `test_backend_contract_change_without_typescript_update_is_detected` 失败，原因是该用例执行时前端 `node_modules` 尚未安装（测试要求 `openapi-typescript` 可执行文件存在）；`npm ci --prefix src/frontend` 完成后重跑通过（同一文件 19 个用例全绿）。不计回归。

## Review 处置

每个结构化 finding 一行。`已修` 表示本 task 已修复；`遗留` 必须指向 `pNNN` 或 follow-up tid；`撤回` 必须写清理由。critical/important 未解决时不得 PASS。

### Round 1 (2026-11-11T23:30:00+08:00)

|finding_id|severity|status|rationale|fix_ref|
|---|---|---|---|---|
|t055_code_f001|minor|已修|`prepare_socket_dir` 的 `entry.stat()` 包进 try/except FileNotFoundError，条目在 exists() 与 stat() 之间消失视为已清理、直接返回 directory（与同函数 unlink 处一致）。新增竞态测试：`exists()` 返回 True 后立即删文件再调 `prepare_socket_dir`，断言不抛错且返回 directory。先红验证：去掉 try/except 后该测试变红。|src/backend/cbrowser/runtime_agent/socket_root.py:157；tests/unit/test_t055_socket_slot_cleanup.py:64|
|t055_test_f001|minor|已修|4 个新测试文件 docstring 的 AC 编号各减一与契约区对齐：CDP 三例 AC-008→AC-007、UDP mux 四例 AC-009→AC-008、socket slot 八例 AC-010→AC-009、watcher 两例 AC-011→AC-010；17 例主文件标签本来正确，未动。|tests/integration/test_t055_cdp_close_code.py:116；tests/unit/test_t055_udp_mux_single_source.py:66；tests/unit/test_t055_socket_slot_cleanup.py:50；tests/unit/test_t055_runner_watchers.py:65|
|t055_test_f002|minor|已修|`_FakeUpstream.close()` 改写 `close_code` 为 1000，钉住 AC-007 的读码顺序。先红验证：把生产代码读码移到 `upstream.close()` 之后，4403 测试变红；还原后 sha256 校验字节一致、复绿。注：fake 有意严于真实 websockets（spike 场景 3：对端 4403 在本地 close 后仍保留），docstring 已如实写明——fake 强制读码顺序，真实库在对端已关码时不改码。|tests/integration/test_t055_cdp_close_code.py:33|
|t055_test_f003|minor|已修|补 90s 宽限边界两例：`lost_at = now-89` 仍 defer、`now-91` 触发替换。先红验证：宽限常量改为 60s 时 89s 例变红、改为 120s 时 91s 例变红；还原 90.0 后复绿。|tests/unit/test_t055_supervisor_runtime_robustness.py:690|
|t055_test_f004|minor|已修|补 >2000 字节 helper 输出用例（首段标记 + 3000 字节填充 + 尾段标记 + 真实 SECRET），断言日志含尾段标记、不含首段标记、仍不含凭据。先红验证：截断改为取前 2000 字节后该测试变红。|tests/unit/test_t055_supervisor_runtime_robustness.py:167|

### Round 2 (2026-11-12T00:08:00+08:00)

|finding_id|severity|status|rationale|fix_ref|
|---|---|---|---|---|
|t055_code_f002|minor|已修|`managed_socket_target` 的 `os.lstat(str(directory))` 包进 try/except FileNotFoundError，目录在 open() 与 lstat() 之间消失视为 slot 不可用、按 open() ENOENT/ENOTDIR 同一语义 yield `str(sock)` 回落（调用方把非 socket 目标当不存在处理）。新增竞态测试：`os.lstat` 桩为对目录路径首次调用抛 FileNotFoundError，断言回落到普通 socket 路径且不抛裸异常。先红验证：去掉 guard 后该测试变红；还原后 sha256 校验字节一致。|src/backend/cbrowser/runtime_agent/socket_root.py:207；tests/unit/test_t055_socket_slot_cleanup.py:163|

### Round 3 (2026-11-12T01:06:00+08:00)

|finding_id|severity|status|rationale|fix_ref|
|---|---|---|---|---|
|t055_code_f003|minor|已修|`managed_socket_target` 的 fd/路径一致性校验（dev/ino 比对、ISDIR、0o022、uid/gid 四项）抽为 `_validate_slot_dir(fd_stat, path_stat, managed_uid, managed_gid)`，五条 `SocketRootError` 文本逐字保留；主函数圈复杂度 17→10（同审阅口径 AST 计数器复核：`prepare_socket_dir` 仍为 12，口径一致），helper 为 8，均低于 15。行为未变：受影响批 70 绿；f002 竞态测试先红验证——临时去掉 lstat guard 后变红，还原后 sha256 校验字节一致。|src/backend/cbrowser/runtime_agent/socket_root.py:186；src/backend/cbrowser/runtime_agent/socket_root.py:242|

### Round 4 (2026-11-12T01:24:00+08:00)

|finding_id|severity|status|rationale|fix_ref|
|---|---|---|---|---|
|t055_test_f005|minor|已修|给 `_validate_slot_dir` 补直接单测（`SimpleNamespace` 伪造 `stat_result`）：gid 不匹配 raise（match "group"）、happy path 返回 None、managed_gid=None 时不校验组。ISDIR 分支未补（经公开路径不可达，审阅确认不是缺口）。未改生产代码。先红验证：临时中性化 gid 检查后 gid 测试变红；还原后 sha256 校验字节一致。|tests/unit/test_t055_socket_slot_cleanup.py:208；tests/unit/test_t055_socket_slot_cleanup.py:221；tests/unit/test_t055_socket_slot_cleanup.py:234|

## 收尾报告

### 验收与验证

- task：[`task.md`](task.md)
- 结果：全部满足
- 测试：后端全量 `tests/unit tests/integration`：2067 通过 / 28 失败 / 8 跳过（542.72s，日志 `.scratch/t055_backend_full.log`）；28 个失败中 25 个与 t054 基线同名（agent_executor_chain 7、t028 4、normal_exit_replay 4、automation_probe_chain 3、t034 2、automation_cdp_flow 2、repo_hygiene 1、automation_cdp 1、control_attendant_chain 1），另 3 个为环境件缺失（t045 wheel 缓存 2、a16 需前端 node_modules 1），补齐后重跑全部通过 → 有效回归 2070 通过 / 25 失败 / 8 跳过 / 0 错误，与基线一致，零新增失败。Round 1 修复后：定向测试 40 个全绿（t055 新测试 36 个 + 竞态 1 + 宽限边界 2 + 截断 1）；后端全量第六轮 2074 通过 / 25 失败 / 8 跳过 / 0 错误（531.99s，日志 `.scratch/t055_r1fix_backend_full.log`，2074 = 2070 + 4 新增用例，25 个失败逐名与基线一致）；前端全量：538 通过 / 0 失败（74 文件，`npm test`，Node 26.13.0）。Round 2 修复后：定向测试 70 个全绿（t055 新测试 41 个 + p058/a36 相关批 29 个）；后端全量第七轮 2075 通过 / 25 失败 / 8 跳过 / 0 错误（429.34s，日志 `.scratch/t055_r2fix_backend_full.log`，2075 = 2074 + 1 新增用例，25 个失败逐名与基线一致，分组为 executor chain 7、t028 4、normal_exit_replay 4、probe chain 3、t034 2、cdp_flow 2、repo_hygiene 1、automation_cdp 1、attendant chain 1，零 t055 相关失败）；前端全量重跑：538 通过 / 0 失败（74 文件）。Round 3 修复后：定向测试 70 个全绿（t055 新测试 41 个 + p058/a36 相关批 29 个）；后端全量第八轮 2075 通过 / 25 失败 / 8 跳过 / 0 错误（430.49s，日志 `.scratch/t055_r3fix_backend_full.log`，2075 与 R2 修复轮一致，25 个失败逐名与基线完全相同）；前端全量重跑：538 通过 / 0 失败（74 文件，日志 `.scratch/t055_r3fix_frontend_full.log`）。注：首轮全量后端曾出 2 个 `test_api_subprocess.py` teardown ERROR（2073 通过 / 2 错误），单跑该文件 4 绿、第二轮全量 0 错误，属子进程类 flaky teardown（与 t051 基线同类），非回归。Round 4 修复后：定向测试 73 个全绿（t055 新测试 44 个 + p058/a36 相关批 29 个）；后端全量第九轮 2078 通过 / 25 失败 / 8 跳过 / 0 错误（532.78s，日志 `.scratch/t055_r4fix_backend_full.log`，2078 = 2075 + 3 新增用例，25 个失败与 R3 修复轮日志逐名完全相同，零 t055 相关失败）；前端全量重跑：538 通过 / 0 失败（74 文件，日志 `.scratch/t055_r4fix_frontend_full.log`）。
- 黑盒：`CBROWSER_RUN_E2E=1 scripts/run_gates.sh` 需真实 Docker/Chrome，本机无，已跳过（计 pass，见环境跳过项）。
- review：Round 1 双路 PASS（code 1 条 minor f001、test 4 条 minor f001–f004），5 条 finding 已全部修复并重验（见「Review 处置」Round 1 表）；Round 2 双路 PASS（code 1 条 minor f002、test 0 新发现），f002 已修复并重验（见「Review 处置」Round 2 表）；Round 3 双路 PASS（code 1 条 minor f003、test 0 新发现），f003 已修复并重验（见「Review 处置」Round 3 表）；Round 4 双路 PASS（code 0 新发现、test 1 条 minor f005），f005 已修复并重验（见「Review 处置」Round 4 表），待 chain runner 派发 Round 5 复审。
- AC 判定：AC-001–AC-010 全部打勾（task.md 行内）

### 结果摘要

- Spike 已验证：websockets 17.4 实测，关码须在本地 close 前读取；A10 据此实现。
- A4–A8、A10–A13 全部实现；Round 1 双路 PASS 的 5 条 minor finding（code f001、test f001–f004）、Round 2 的 1 条 minor finding（code f002）与 Round 3 的 1 条 minor finding（code f003，`managed_socket_target` 圈复杂度 17）已全部修复并重验（先红验证均已做，见「Review 处置」Round 1/2/3 表）；无新增失败；无待用户裁定项。AC-001 措辞未动（超时分支不抓 helper 日志的边界已记入实施笔记）。
- 长期文档：`docs/blueprint/supervisor.md`（UDP mux 单一来源、恢复预置 starting、注册宽限、t055 收口段）、`docs/blueprint/automation.md`（CDP 关码透传语义）、`docs/specs/runtime_lifecycle.md`（恢复/观测收口）已更新；`docs/specs_index.md` 的 runtime_lifecycle 行已登记 t055。

### 长期文档闭环

- specs_index: runtime_lifecycle 行已登记 t055（2026-11-11）。
- 正式 spike：`.scratch/spike_close_code.py`（已验证，结论已写入 task.md，替代 UNVERIFIED-SPIKE 条目；无后续 tid）。
