# Task review t058（reviewer_focus: 测试）

- task：`t058_frontend_state_consistency`
- spec：`docs/tasks/t058_frontend_state_consistency/task.md`
- diff_anchor：`8ede5099cecb6c4116757fb9f36864c8c0642f0f`
- target：`git -C '/home/hatch/workspace/CBrowser_t058' diff 8ede5099cecb6c4116757fb9f36864c8c0642f0f`
- round：1
- reviewed_at：2026-11-13T03:35:20+08:00

## 独立重跑实数（本轮审阅方实测，非引用实施方数字）

- 前端全量 `npm test`（含 `test:types` 前置门禁，Node 26.13.0）：**80 文件、575 passed / 0 failed**，与实施方所称 575 passed / 0 failed 完全一致。日志：`.scratch/review_frontend.log`（EXIT 0）。
- 后端全量（审阅方两阶段独立重跑，`/tmp/t058rv` 短根 basetemp，gate venv Python 3.15.2）：Phase A（`-m "not serial"`，xdist 4 worker）**23 failed / 2076 passed / 8 skipped**（297.22s）；Phase B（`-m serial`，单进程）**1 failed / 67 passed**（29.67s）；合计 **24 failed / 2143 passed / 8 skipped**。日志：`.scratch/review_backend_parallel.log`、`.scratch/review_backend_serial.log`（JUnit：`.scratch/review_backend_parallel.xml`、`.scratch/review_backend_serial.xml`）。
- 模板契约 `pytest .repo_template/tests -q -m contract`：**257 passed / 1 skipped**，与实施方一致。日志：`.scratch/review_contract.log`。
- t034 + t058 分类（补 `~/.local/bin` 进 PATH 后单跑）：**7 passed**（t034 5 项 + t058 分类 2 项）。日志：`.scratch/review_t034.log`。

### 与 t056 基线（25 failed / 2140 passed / 8 skipped）的逐名对账

- 审阅方 24 failed = 基线一致的 23 项（agent_executor_chain 7、t028 4、normal_exit_replay 4、automation_probe_chain 3、automation_cdp_flow 2、repo_hygiene 1、automation_cdp 1、control_attendant_chain 1）+ t034×1。
- 基线 25 failed = 同样 23 项 + t034×2。唯一差额是 t034 少失败 1 项（该项为 PATH 缺 `uv` 的测量 artifact，见下）。
- 通过数：2140 → 2143 = 新增 2 项（t058 分类测试）+ t034 少失败 1 项。吻合。
- t045×2：审阅方重跑中**通过**（wheel 已存在，见 f001）；实施方第三轮时 wheel 缺失故失败。不是代码回归。
- `test_normal_exit_converges_to_desired_stopped_while_container_running`：审阅方重跑中 FAILED；该用例在 t056 基线即为失败项（normal_exit_replay 4 之一），且实施方三轮中表现为 ERROR→FAILED→FAILED，属既有 flaky，非 t058 回归。
- 结论：**零代码回归**。

### 实施方定稿日志完整性

- `.scratch/t058_backend_parallel3.log` 以 `25 failed, 2074 passed, 8 skipped` 正常结尾，`.scratch/t058_backend_serial3.log` 以 `1 failed, 67 passed` 正常结尾，两阶段合计 26 failed / 2141 passed，与实施方所称一致，无截断。实施方会话中出现的一次 process poll 超时失败记录未波及定稿日志，证据完整可信。

## Findings

### t058_test_f001 - 收尾报告的后端全量数字已过期：wheel 已补齐，t045 现已通过

- 严重度：minor
- 锚点：门禁实数（实施方所称 26 failed / 2141 passed 与当前 worktree 状态不符）
- 位置：`docs/tasks/t058_frontend_state_consistency/progress.md`（收尾报告“后端全量”一节）；`.scratch/selkies_wheels/selkies-2.2.1-py3-none-any.whl`
- 问题：实施方第三轮后端全量时 wheel 缺失，t045×2 失败，合计 26 failed。但该 wheel 文件现已存在于 worktree 内，mtime 2026-11-13 03:12:53 CST（实施方会话期间、第三轮之后），SHA-256 `18503b5c1491a04194f0a45fa10c547ffe5b4a24f33496ce5d56e97370a6a3cd` 与 pin 完全一致（2169 个文件，真实 selkies 2.2.1 wheel）。审阅方独立重跑中 t045×2 均通过，合计为 **24 failed / 2143 passed**。progress.md 未记录 wheel 补齐事件，也未更新数字；且其中“无公开下载”的说法与事实不符——t056 实施方即用仓库自有 `scripts/vendor_selkies_web.py` 的 `download_wheel` 从 PyPI 取回同一文件（见 8ede509 内 t056 progress.md 第 121 行），本文件字节数 2,733,413 与之一致。
- 建议：finish 时以审阅方重跑数字（24 failed / 2143 passed / 8 skipped）为准写 handoff，或在 progress.md 补记 wheel 补齐事件与修正后的数字。不影响代码与 AC 判定。

## 结论

- 改测方向复核：无“迁就实现”的改测。全部被删/被改的既有测试均有 spec 驱动的归因并留痕（见下），且均有等价或更高层的新测试替代：
  - `ProfileForm.test.tsx`“submits the full values in edit mode”删除——与 A24（edit 只提交差分）直接冲突，由 `ProfileForm.t058.test.tsx` 的 AC-001/AC-002 精确 payload 断言替代。
  - 两条 `onDirtyRuntimeConfig` 用例删除——prop 随 `ConfigTab` 提交分支删除而删除，分类语义由 `profile_field_diff.test.ts` 覆盖（metadata-only 为 false、时区为 true、仅 `capture_preview` 为 false）。
  - `useBrowserSession.lifecycle.test.tsx`“only the one-shot mount bootstrap touches getRuntime”删除——A25 删除了挂载首检，由 t058 用例“hook 永不为 stage/错误读 runtime”替代。
  - `useBrowserSession.stages.test.tsx` 第 2 例（401 特判）删除——401 处理随首检移出 hook，归 `runtimeQuery` / SessionPage 的未授权流；SessionPage 层 `runtimeQuery.isError` 仍走 `LoadErrorView`，既有测试“runtime 请求失败显示 load-error 而非 stopped”覆盖。
  - `useBrowserSession.test.tsx` stage 映射 5 例与 A17 用例改写——断言的 stage 映射本身不变，驱动方式由 mock `getRuntime` 改为 `runtimeState` 输入；A17 的 `getRuntime` 调用次数 1→0 是 A25 规定的行为变更（hook 不再读 runtime），非迁就实现。
  - lifecycle / transportRecovery setup 补 `runtimeState: "running"`——A39 语义要求（首检未完成时不启动恢复），断言意图不变。
- 本轮新发现：1 条（minor，f001）。
- 未进表的提示：
  - `useBrowserSession.t058.test.tsx:240` 有一处 `toBeTruthy()`（AC-007 第二例对 `errorMessage` 的断言）。经核查为次要断言：该用例的核心证据是 stage 为 `runtime_not_ready`、reloadKey 为 0、`getRuntime` 零调用；stopped 的精确错误文案已由 AC-004 用例断言（`en.runtimeNotRunning` 替换后全等）。不构成覆盖弱化，不出 finding。
  - 实施方所称“目标测试 12 文件 82 项”经审阅方按前端全量日志逐文件核数实为 83 项（ProfileForm.t058 5、profile_field_diff 8、useProfilesQuery.t058 1、ProfileForm.test 10、ConfigTab.test 3、useBrowserSession.t058 10、useBrowserSession.test 6、lifecycle 6、stages 12、transportRecovery 4、app_error_boundary 13、logging 5），差 1 项为计数笔误，不影响结论。
  - `test_normal_exit_converges_to_desired_stopped_while_container_running` 为既有 flaky（基线即失败，三轮表现 ERROR→FAILED→FAILED），与 t058 无关；建议 follow-up 由链外任务处理，不阻塞本 task。
  - `scripts/run_gates.sh` 在 `ensure_selkies_wheel_cache` 处 fail-closed（实施方已记入环境跳过项）；审阅方因 wheel 现已存在未再复核该入口，不影响本轮结论。
- 总体判断：7 条 AC 均有真实、可信的测试支撑，独立重跑门禁与实施方数字对质一致（差额仅为环境项 t045/t034，均已逐项验证），无 blocking finding。
- 系统性 follow-up：无。

### AC 复验方式

- AC-001：TICK-VALID，re_verified。`ProfileForm.t058.test.tsx` 两例精确断言提交体（仅改时区时 `{ timezone }` 全等、时区+联动 locale 时 `{ timezone, locale }` 全等）；后端半由既有 `test_disjoint_concurrent_patch_name_and_notes`（5 轮并发不相交 patch，两字段均保留）与 `repository.py:479`“只合并 supplied patch 字段”覆盖。审阅方前端全量重跑通过。
- AC-002：TICK-VALID，re_verified。`ProfileForm.t058.test.tsx` 仅切 `capture_preview` 时提交体全等于 `{ capture_preview: false }`；`profile_field_diff.test.ts` 断言其分类为 instant；`test_t058_profile_field_classification.py` 断言生成文件与后端常量逐字节一致且三分覆盖全部 `ProfileConfig` 字段；既有 `test_capture_preview_epoch_bumps_without_config_version` 断言只切该字段时 epoch 自增且不建新版本。审阅方重跑通过（分类测试 2 passed；后端全量中上述既有用例均通过）。
- AC-003：TICK-VALID，re_verified。`useProfilesQuery.t058.test.tsx`：真实 QueryClient 下在途旧 GET 在保存后 resolve，缓存仍为保存值，且保存未触发 detail refetch（`get` 调用次数保持 2）。此为 task.md“有意不测”声明的时序替代测试，合法。审阅方前端全量重跑通过。
- AC-004：TICK-VALID，re_verified。`useBrowserSession.t058.test.tsx` 5 例：running/error/stopped/恢复四态下 stage 与错误文案均由同一份 `runtimeState` 输入派生，无数据时无错误文案，且 hook 全程零次调用 `getRuntime`；SessionPage 层 `runtimeState: runtimeQuery.data?.observed_state ?? null`（`SessionPage.tsx:101`）为唯一来源，`runtimeQuery.isError` 走 `LoadErrorView`（既有测试“runtime 请求失败显示 load-error 而非 stopped”覆盖）。审阅方前端全量重跑通过。
- AC-005：TICK-VALID，re_verified。`useBrowserSession.t058.test.tsx` 2 例：stopped 时迟到帧信号下 stage 保持 `media_no_frames` 且音频 `postMessage` 零调用；running 对照组同帧信号下进入 `connected` 并发送 `pipelineControl/audio enabled`。帧信号经真实 iframe `__getWebRTCStats` 桩与 `diagnosticsSource.setActive`（生产暴露的真实 API）驱动。审阅方前端全量重跑通过。
- AC-006：TICK-VALID，re_verified。`app_error_boundary.test.tsx` 13 例：真实 RouterProvider 下 boom 路由只显示错误页、错误写入 `frontendLog`（`logError` 调用 1 次且 `getEntries()` 含该条目）、导航到 /ok 后恢复；并结构断言真实 `routes` 的每条顶层路由与每条嵌套子路由 element 均为 `RouteErrorBoundary`、每条顶层路由均有 `errorElement`。审阅方前端全量重跑通过。
- AC-007：TICK-VALID，re_verified。`useBrowserSession.t058.test.tsx` 3 例：首检前 WS 1006 只写 `diagnostics.signalingCloseCode`、不启动恢复（stage 与 reloadKey 不变，`getRuntime` 零调用）；首检定版为 stopped 时诊断态保持；首检定版为非 running 时取消同 generation 恢复轮询——覆盖 2100ms 真实时长（超过 2000ms 轮询间隔），其后 `getRuntime` 零新增调用。审阅方前端全量重跑通过。

coverage = 7 / 7

verdict: PASS

reviewed_scope: ac647fb75e006a79
reviewed_scope: 81de8955c56d4188
