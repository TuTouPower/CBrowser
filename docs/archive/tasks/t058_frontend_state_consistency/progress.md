---
tid: "t058"
slug: "frontend_state_consistency"
title: "前端状态一致性收口"
status: "done"
branch: "t058_frontend_state_consistency"
worktree: ""
review_level: "full"
review_limit: "5"
verify_limit: "5"
diff_anchor: "8ede5099cecb6c4116757fb9f36864c8c0642f0f"
depends_on: ""
conflicts_with: "t053,t056,t059"
note: "来源 review_20261110_200842 adoption_decision A24 A25 A27 A39"
---

# Task 进展

front matter 只经 `task.py` 修改；reviewer 只写对应 `review_*.md`。

## 实施笔记

执行期记录关键步骤、决策、验证、阻塞和用户批准的新轮次上限。

创建期不预测实施步骤。只记有追溯价值的内容；无事项时写“无”。

### 引用逐项核对（2026-11-13，实施前）

逐项打开原文核实，task.md 上下文区引用与 adoption_decision A24/A25/A27/A39：

- `ProfileForm.tsx:53-58`（METADATA_KEYS）：内容相符，行号漂移 — 实际在 55–60 行（`name/notes/sort_order/group_id`）。
- `ConfigTab.tsx:44-62`：基本相符 — 实际 `handleSubmit` 在 41–64 行，`runtimeDirty ? 全量 : pickMetadata` 分支与 `setQueryData(detail)` 均在该区间内。
- `useProfilesQuery.ts:87-90`：基本相符 — 实际 `useUpdateProfileMutation` 的 `onSuccess` 在 87–95 行，`setQueryData(detail)` 在 91 行、`invalidateQueries(detail)` 在 93 行；引用区间少含末两行。
- `repository.py:116-120`：**不符** — 该区间实际是 `_match_operation_audit` 内部；三分常量实际在 73–77 行（`METADATA_FIELDS` 73、`INSTANT_FIELDS` 74、`CONFIG_VERSION_FIELDS` 75–77），内容（`capture_preview` 为唯一 instant 字段）与 A24 所述一致。后续实现以 73–77 行为准。
- `useBrowserSession.ts:150-168`：内容相符，起始行漂移 — 实际 `handleConnectionSignal` 在 137–168 行，帧信号守卫（`hasFrames` 且非 `connected`、effectiveStage 非 `stopping`/`error`）在该区间内。
- `useBrowserSession.ts:419-499`：**部分不符** — 该区间实际是消息处理器的 terminal 守卫（415 行起）与 `CBROWSER_WS_CLOSE` 分支（471–505 行）；挂载首检 `checkRuntime` 实际在 353–399 行，不在引用区间内。A39 所指的“首检前 WS_CLOSE 启动恢复轮询”路径（`handleInitialSignalingClose`，307–347 行）亦不在该区间内。
- `SessionPage.tsx`：相符 — `stage` 经 `deriveSessionStage(session.stage, runtime?.observed_state)` 派生，hook 得 `runtimeState: runtimeQuery.data?.observed_state ?? null`。
- `ErrorBoundary.tsx`：相符 — 无 `componentDidCatch`、无日志、无 `resetKey`，渲染异常即整页 `AppErrorPage`。
- `main.tsx`：相符 — `ErrorBoundary` 包在 `Providers` + `RouterProvider` 之外，根部兜底。
- `adoption_decision.md` A24（217 行）、A25（225 行）、A27（241 行）、A39（337 行）：均存在，修复说明与 task.md 范围一致；A24 自身位置标注 `ConfigTab.tsx:44-48,59-62` 与实测 41–64 行区间一致。
- task.md 称“审阅原文第 79–83、85、101 项”：adoption_decision.md 内无此编号体系，无法逐号核对；以 A24/A25/A27/A39 四条采纳项正文为准。

### 实施决策

- A24 分类来源：采用 codegen 路由（task.md 允许的“经生成类型”）：新增 `scripts/export_profile_field_classification.py`，从后端 `repository.py` 的 `METADATA_FIELDS` / `INSTANT_FIELDS` / `CONFIG_VERSION_FIELDS` 生成 `src/frontend/src/shared/api/generated/profile_field_classification.ts`；后端单测断言生成文件与后端常量逐值一致且三分覆盖全部 `ProfileConfig` 字段。未选新增 API 端点：分类是静态事实，运行时拉取徒增依赖；本仓已有 OpenAPI codegen + `check:api` 同款先例。
- A24 提交形态：`ProfileForm` 在 edit 模式只把与 `initial` 的差分传给 `onSubmit`；`ConfigTab` 删除 `runtimeDirty` / `pickMetadata` 分支（差分本身已含分类信息）；`onDirtyRuntimeConfig` prop 随之删除（唯一消费方即 `ConfigTab` 的提交分支），其语义由 `profile_field_diff.ts` 的 `hasRuntimeConfigChange`（纯函数，分类驱动）承接并单测覆盖。
- A25：删除 hook 内挂载首检 `checkRuntime`（含其 401 特判与三条错误文案写入）；stage 与错误文案改为由 `options.runtimeState`（即 SessionPage 的 `runtimeQuery.data`）派生的 effect 驱动，仅在等待态（`checking_runtime` / `runtime_not_ready` / `reconnecting`）推进；`runtimeState` 为空时不写任何错误（AC-004）。`SessionPage` 本身不改：它已把 `runtimeQuery` 作为唯一来源传入。
- A27 日志通道：前端此前无日志通道（仅 `sse.ts` 有 `console.error` 调试输出；后端无前端日志端点）。新建 `src/frontend/src/shared/logging.ts`（有界内存环 + `window` 自定义事件，可供诊断面订阅；不打 console），`ErrorBoundary.componentDidCatch` 经此通道记录。
- A39：首检完成 = `runtimeState` 首次非空；完成前 `WS_CLOSE` 只写诊断记录（`diagnostics.signalingCloseCode`）不启动恢复；首检定版非 `running`（或其后变为 `stopped`/`error`）时取消同 generation 的恢复轮询（清 timer + 代次旗标，poll 循环每次迭代复核）。
- 工具链：本机原无 uv / Python 3.15 / Node 26 / `node_modules`，已在 worktree `.scratch/toolchain` 内装好 uv 0.13.8、CPython 3.15.2、Node v26.13.0（`.scratch` 已 gitignore，不入库）；门禁仍走 `scripts/run_gates.sh`，`node_modules` 另行 `npm ci`。

### 旧测试处置（语义随 task 变更，逐条留痕）

- `ProfileForm.test.tsx`“submits the full values in edit mode”：与 A24（edit 只提交差分）直接冲突，删除；由新增 `ProfileForm.t058.test.tsx` 的 AC-001/AC-002 用例替代。
- `ProfileForm.test.tsx` 两条 `onDirtyRuntimeConfig` 用例：prop 随 `ConfigTab` 分支删除而删除；分类语义改由 `profile_field_diff.test.ts` 覆盖（metadata-only 为 false、时区为 true、仅 `capture_preview` 为 false）。
- `useBrowserSession.test.tsx` 的 stage 映射 5 例：改由 `runtimeState` 选项驱动（断言不变）；A17 用例改写：hook 不再读 runtime，断言改为挂载后 `getRuntime` 零调用且语言切换不改 stage。
- `useBrowserSession.lifecycle.test.tsx`“only the one-shot mount bootstrap touches getRuntime”：A25 删除挂载首检，该测试语义作废，删除；由新增 t058 用例“hook 永不为 stage/错误读 runtime”替代。
- `useBrowserSession.stages.test.tsx` 第 2 例（401 特判）：401 处理随首检删除而移出 hook（归 `runtimeQuery` / SessionPage 的未授权流），hook 层删除；SessionPage 层 `runtimeQuery.isError` 仍走 `LoadErrorView`，不新增用例。
- `useBrowserSession.transportRecovery.test.tsx` 与 lifecycle “clears the transport recovery timer”：setup 补 `runtimeState: "running"`（A39 下首检未完成时不启动恢复，旧 setup 无 runtime 输入，断言意图不变）。

### 接手核查（2026-11-13，第三次派发：前两任中途停住后继续）

- 工作区核对：25 项未提交（15 改 + 10 新增）与派发时一致；未重做已完成部分。目标测试先跑：12 文件 83 项全过（ProfileForm.t058 / profile_field_diff / useProfilesQuery.t058 / ProfileForm / ConfigTab / useBrowserSession.t058 / useBrowserSession / lifecycle / stages / transportRecovery / app_error_boundary / logging）。
- 后端分类测试：`tests/unit/test_t058_profile_field_classification.py` 2 passed；生成文件与后端常量逐字节一致（测试断言），三分覆盖全部 `ProfileConfig` 字段。
- AC-001 后端半：`update_profile` 只合并 supplied patch 字段（`repository.py:479` 附近 “Merge ONLY the supplied patch fields”），增量提交不会以旧值写回他方修改。
- AC-002 后端半：仅 `CONFIG_VERSION_FIELDS` 变化才建新版本（`repository.py:486`）；`capture_preview` 在 `INSTANT_FIELDS`（74 行），单改它不建新版本；另有 `capture_preview_epoch` 自增（518 行起）。
- A25 单一权威核实：`SessionPage.tsx:93,99-101` 已把 `runtimeQuery.data?.observed_state` 作为唯一 `runtimeState` 传入 hook。
- `useUpdateProfileMutation` 删 `invalidateQueries(profileKeys.runtime)` 的复核：`ProfileRuntimeResponse.config_version` 取自运行实例绑定的 `rt.config_version`（`runtime_views.py:81`；`repository.py:666-670` 禁止改绑已存在实例的版本），Profile 保存不改变它，删 invalidate 只是省一次无变化的 refetch；且 SSE 事件到达时 `useProfileEventsSync` 本就会 invalidate runtime。保留删除，不恢复。
- 门禁入口：`scripts/run_gates.sh` 在 `ensure_selkies_wheel_cache` 处 fail-closed 退出——本机无 2.2.1 wheel（主仓缓存仅有 2.1.0），与 t056 同款环境限制；改按 t056 先例直接跑各套件（contract / unit / integration / design_lint / design_check / npm test / build），E2E 与 real_engine 因无 Docker 跳过。
- AC-006 补强（接手后复核发现）：原实现只包了三条顶层路由，`/` 下 10 条子路由共用父级 boundary——子路由渲染异常会连 AppLayout 一起卸掉，不符合“只有该路由显示错误页”的字面要求。已把 10 条子路由逐一包上 `RouteErrorBoundary`（导航仍以 `location.key` 复位），并在 `app_error_boundary.test.tsx` 增加结构断言（每条子路由 element 均为 `RouteErrorBoundary`）；该文件现 13 项通过。
- 后端全量第一轮（默认 basetemp，`t058_backend_parallel.log` / `t058_backend_serial.log`）：Phase A 29 failed / 2069 passed / 8 skipped / 1 error（332s），Phase B 1 failed / 67 passed。失败按名与 t056 基线组对比：executor_chain 7、t028 4、normal_exit 4（3 failed + 1 error 同组）、probe_chain 3、cdp_flow 2、repo_hygiene 1、automation_cdp 1、attendant 1 均与基线一致；t034 仅 1（基线 2，少一个是改进）；额外两组须定性：t045×2、t055×5。
- t045×2 定性为既有环境失败（已证）：断言本 worktree `.scratch/selkies_wheels/selkies-2.2.1-py3-none-any.whl` 存在；该 wheel 本机无处可寻（主仓缓存仅 2.1.0、无公开下载）。在基线提交 8ede509 的干净 worktree（已建后删除）上原样复跑：同样 2 failed / 2 passed，与 t058 改动无关。
- t055×5 疑为测量方式问题：失败根因为 `OSError: AF_UNIX path too long`——默认 basetemp 路径 `/tmp/pytest-of-root/pytest-1/popen-gwN/…` 过长，超 Unix socket 108 字节上限；门禁脚本 `run_gate_suite` 用的是 worktree 内短 basetemp。已用短 basetemp（`.scratch/basetemp2/{parallel,serial}`）重跑全量，待结果。
- 第二轮（worktree 内短 basetemp，`t058_backend_parallel2.log`）：Phase A2 31 failed / 2068 passed / 8 skipped（429s）。与第一轮逐名对比：新增 2 项——`test_normal_exit_converges_to_desired_stopped_while_container_running`（第一轮是同组 ERROR，属同一条 flaky 用例的不同表现）与 `test_ac009_api_supervisor_start_and_stop_coordination`；t055 仍 5 项全败。根因再算：socket 路径 = basetemp 根 + `/<20 字节 slot>/agent.sock`，代码自限 100 字节（`socket_root.py:23 SUN_PATH_BYTE_LIMIT`），worktree 内 basetemp 根已 111 字节，仍超限——须用 /tmp 下短根。AC009 单跑通过（2.52s），属负载下 flaky，第一轮通过、第二轮失败。
- 第三轮（/tmp 短根，`t058_backend_parallel3.log` / `t058_backend_serial3.log`）：Phase A3 25 failed / 2074 passed / 8 skipped（292s），Phase B3 1 failed / 67 passed。合计 26 failed / 2141 passed / 8 skipped / 0 error。按名与 t056 基线（25 failed / 2140 passed / 8 skipped）逐项对比：executor_chain 7、cdp_flow 2、probe_chain 3、attendant 1、normal_exit 4、automation_cdp 1、repo_hygiene 1、t028 4 全部一致；t034 仅 1（基线 2）；t045 2 项为上述已证的既有环境失败；t055 0 项。通过数验算：2140 + 新增 2（分类测试）− t045 失败 2 + t034 少失败 1 = 2141，吻合。另：第三轮中唯一的 t034 失败（`test_each_requirements_is_the_uv_lock_export`）是调用方 PATH 未含 `uv` 导致子进程找不到可执行文件——补上 `~/.local/bin` 后该文件 5 项全过；`generate_requirements.sh --check` 同理因本机无 `mise` 而无法执行（权威检查即 t034 单测，已过）。
- 类型门禁修复（接手后复核发现）：前任只跑了 vitest，未跑 `npm test` 里的类型门禁，`tsc -p tsconfig.test.json` 报 9 项错误：`ErrorBoundary.tsx:43`（`ErrorInfo.componentStack` 为 `string | null`，日志通道不接受 null）——已把 `logging.ts` 的 context 类型放宽为 `string | null` 并归一为 undefined；`app_error_boundary.test.tsx:161/170`、`logging.test.ts:42/55/56`（`mock.calls[0]` / `entries[N]` 的 noUncheckedIndexedAccess）——已按仓内既有惯例补 `!`；`useBrowserSession.t058.test.tsx:171/193`（`contentWindow` 可为 null）——已按仓内惯例改为 `as Window`；`ProfileForm.test.tsx:114`——前任删用例后遗留的孤儿 `profile()` 辅助函数，已删除（`ProfileResponse` 导入仍被他处使用，保留）。修后 `npm run test:types` 通过。
- 前端全量（`npm test`，含类型门禁）：575 passed / 0 failed（t056 基线 546；+29 = 新增 34 − 删除 5，见旧测试处置与 AC-006 补强）。
- design_lint：0 error / 0 warning；design_check：design_tokens.css up to date；`npm run build` 通过（含 verify:selkies 与前端 dist 校验）。
- 模板契约：`pytest .repo_template/tests -q -m contract` 257 passed / 1 skipped。

### Round 1 处置补记（2026-11-13，t058_test_f001）

- wheel 补齐事件：`selkies-2.2.1-py3-none-any.whl` 于 2026-11-13 03:12:53 CST 出现在 worktree 内（`.scratch/selkies_wheels/`，2,733,413 字节），SHA-256 `18503b5c1491a04194f0a45fa10c547ffe5b4a24f33496ce5d56e97370a6a3cd` 与 pin 一致（已当场 sha256sum 核实）；此前第三轮全量时该文件缺失，t045×2 因此失败。审阅方独立重跑（/tmp/t058rv 短根）t045×2 均通过，当前真实后端全量数字为 **24 failed / 2143 passed / 8 skipped**，收尾报告已据此更正。
- “无公开下载”说法更正：实施笔记中“该 wheel 本机无处可寻（主仓缓存仅 2.1.0、无公开下载）”不成立——t056 即用仓库自有 `scripts/vendor_selkies_web.py` 的 `download_wheel` 从 PyPI 取回同一文件（2,733,413 字节、同一 SHA-256；见 8ede509 内 t056 progress.md 第 121 行）。本轮 wheel 的具体来源未追踪（03:12:53 出现在 worktree 内），不影响数字结论。


## Review 处置

每个结构化 finding 一行。`已修` 表示本 task 已修复；`遗留` 必须指向 `pNNN` 或 follow-up tid；`撤回` 必须写清理由。critical/important 未解决时不得 PASS。

### Round 1 (2026-11-13T03:44:00+08:00)

|finding_id|severity|status|rationale|fix_ref|
|---|---|---|---|---|
|t058_test_f001|minor|已修|收尾报告后端全量数字以审阅方独立重跑为准更正为 24 failed / 2143 passed / 8 skipped；wheel 补齐事件与“无公开下载”说法更正见实施笔记补记|progress.md:81-84|

## 收尾报告

### 验收与验证

- task：[`task.md`](task.md)
- 结果：7 条 AC 全部实现并单测验证（AC 打勾见 task.md）
- 测试：目标测试 12 文件 83 项全过；后端分类测试 2 passed；前端全量 `npm test`（含类型门禁）575 passed / 0 failed；后端全量（审阅方独立重跑，/tmp/t058rv 短根）24 failed / 2143 passed / 8 skipped / 0 error——按名与 t056 基线逐项对比，零代码回归（t045×2 已通过，wheel 于 03:12:53 补齐；其余 23 项失败与基线逐名一致；t034×1 为调用方 PATH 缺 `uv` 的测量 artifact，补 PATH 后 5 项全过）；模板契约 257 passed / 1 skipped；design_lint 0 error / 0 warning；design_check 通过；`npm run build` 通过
- 黑盒：本机跳过（无 Docker / 真实部署 / 真实 Chrome，见环境跳过项），用户机复核
- review：待主 agent 另行派发双路审阅（Round 1 code/test）
- AC 判定：见 `task.md` 行内打勾

### 结果摘要

- 实施范围：A24（增量提交、后端生成分类、保存 cancel + 不 invalidate detail）、A25（stage/错误文案同源于 runtimeQuery、帧信号 stopped/error 守卫）、A27（ErrorBoundary 日志通道、路由级 boundary、路由切换复位）、A39（首检前 WS_CLOSE 只记录、首检定版非 running 取消同 generation 恢复轮询）全部完成；7 条 AC 全部单测验证。
- 接手后补强两件：AC-006 子路由逐一加 boundary（原实现只包顶层路由）；类型门禁 9 项错误全部修复（前任未跑 `npm test` 的类型部分）。
- 关键发现两件：`useUpdateProfileMutation` 删 runtime invalidate 经复核无害（`config_version` 系运行实例绑定值，保存不改变它）；后端全量失败的定性——t045×2 为缺失 2.2.1 wheel 夹具（基线提交原样复现）、t055×5 为 basetemp 路径超 100 字节自限（短根重跑全过）、t034×1 为调用方 PATH 缺 `uv`。
- 未动：t057；未合并、未推送、未提交（工作区保持未提交状态，待审阅与 finish）。

### 长期文档闭环

- 待 finish 时更新：`docs/blueprint/frontend.md`、`docs/specs/profile_management.md`、`docs/specs/webrtc_remote_display.md`、`docs/specs_index.md`（task.md「Finalization 时更新的 blueprint」一节）。
