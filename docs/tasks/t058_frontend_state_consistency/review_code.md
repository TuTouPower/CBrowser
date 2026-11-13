# Task review t058（reviewer_focus: 代码）

- task：`t058_frontend_state_consistency`
- spec：`docs/tasks/t058_frontend_state_consistency/task.md`
- diff_anchor：`8ede509`
- target：`git -C '<home>/workspace/CBrowser_t058' diff 8ede509`
- round：1
- reviewed_at：2026-11-13T03:34:35+08:00

## Findings

本轮零 finding。

逐条核对后无 blocking / important / minor finding。以下逐 AC 的复核与审阅中核实的关键点见结论段。

## 结论

- 前轮 finding 复核：Round 1，无前轮。
- 本轮新发现：0 条。
- 未进表的提示：
  - 文件过大（仅提示，不进 finding 表）：`src/frontend/src/features/browser-session/useBrowserSession.ts` 653 行（基线 609 行，本 task 净 +44 行）；`src/frontend/src/features/profiles/ProfileForm.tsx` 751 行（基线 767 行，本 task 净 −16 行）。两文件在基线已超 400 行阈值；本 task 未因过大引发可观测缺陷，不出 finding。
  - 零引用导出（仅提示，不进 finding 表）：`profile_field_diff.ts` 的 `hasRuntimeConfigChange` 与 `classifyProfileField` 在生产代码中无调用方（`onDirtyRuntimeConfig` prop 与 ConfigTab 的 runtimeDirty 分支随本 task 删除后，唯一引用只剩 `profile_field_diff.test.ts`）。progress.md 称其语义由该函数“承接”与实际调用情况不符——函数本身正确且有测试覆盖，只是当前无生产消费方；建议后续 task 要么删除，要么由消费方（如下游 pending-apply 提示）接手。未造成行为不一致，不阻断。
  - 残留窗口（已核实可接受，不出 finding）：AC-005 的帧信号守卫以 `runtimeStateRef.current` 为准；首检完成前该值为 null，帧信号仍可推进连接态。已核实：已停止的后端不产生帧信号，AC-005 的测试场景（runtimeState 已为 stopped）不受影响；null 当作“未停止”处理是刻意保留的快速连接路径（P1-E），改动它会拖慢正常连接。AC-007 的 `wasConnectedRef` 分支同理：首检前只有真正连通过的会话才会走该分支，而连通过即意味着后端当时在运行。
  - 引用核对复核（实施方记录属实）：`repository.py:116-120` 确实不是三分常量（基线 116–120 行为 `_match_operation_audit` 的 docstring；常量在 73–77 行）；`useBrowserSession.ts:419-499`（基线）确实只覆盖 WS_CLOSE 分支与 `handleInitialSignalingClose` 调用点（498 行），挂载首检 `checkRuntime` 在基线 353–399 行、`handleInitialSignalingClose` 定义在 307 行，均不在引用区间内；`adoption_decision.md` 的 A24（217 行）、A25（225 行）、A27（241 行）、A39（337 行）均存在，与 task.md 范围一致；“审阅原文第 79–83、85、101 项”在 adoption_decision.md 内无此编号体系，实施方以四条采纳项正文为准的处理正确。
  - 范围：无范围外改动。改动面限于 profiles / browser-session / app boundary 与 router / 新日志通道 / 字段分类生成脚本与生成文件 / 测试；无后端生产代码改动；`SessionPage.tsx` 与 `main.tsx` 未动（根部兜底保留）；`useUpdateProfileMutation` 删 `invalidateQueries(profileKeys.runtime)` 一处，经核实无害（`config_version` 系运行实例绑定值，`repository.py:666-670` 禁止改绑；SSE 到达时 `useProfileEventsSync` 本就会 invalidate runtime）。
  - 旧测试处置：删除的 5 处旧测试语义均有替代覆盖并留痕（`ProfileForm.test.tsx` 全量提交用例由 `ProfileForm.t058.test.tsx` 的 AC-001/AC-002 用例替代；两条 `onDirtyRuntimeConfig` 用例的分类语义由 `profile_field_diff.test.ts` 覆盖；`useBrowserSession` 的 stage 映射 5 例改由 `runtimeState` 选项驱动，断言不变；401 特判随首检删除——401 由 `client.ts:144` 的全局 `onUnauthorized` 处理，与 hook 无关；挂载 bootstrap 用例由 AC-004 的“hook 永不为 stage/错误读 runtime”用例替代）。
- 总体判断：实现完整覆盖 7 条 AC，无范围外行为，无可观测缺陷；PASS。
- 系统性 follow-up：无。

### AC 复验方式

- AC-001：TICK-VALID，re_verified。`ProfileForm.tsx:301` 编辑时只提交 `diffProfileValues(values, baseline)`；时区改动经 `ProfileForm.tsx:438-445` 联动改写 locale，差分同时含两者；后端 `router.py:417` 以 `model_dump(exclude_unset=True)` 只传已供字段，`repository.py:479` 只合并 supplied patch 字段。证据测试：`ProfileForm.t058.test.tsx`（时区-only、时区+locale）、`ConfigTab.test.tsx`（只改名字时 PATCH 只含名字）。
- AC-002：TICK-VALID，re_verified。`capture_preview` 在后端 `INSTANT_FIELDS`（`repository.py:74`），生成文件逐字节受 `test_t058_profile_field_classification.py` 守护；仅 `CONFIG_VERSION_FIELDS` 变化才建新版本（`repository.py:486`），`capture_preview` 改动只自增 `capture_preview_epoch`（518 行起）。证据测试：`ProfileForm.t058.test.tsx`（仅切 `capture_preview` 时提交体只含该字段）。
- AC-003：TICK-VALID，re_verified。`useProfilesQuery.ts:87-95` 的 `onSuccess` 先 `await cancelQueries(detail)` 再 `setQueryData(detail)`，不再 invalidate detail。证据测试：`useProfilesQuery.t058.test.tsx`（在途旧 GET 在保存后 resolve，缓存仍为保存值，且无 detail refetch）。
- AC-004：TICK-VALID，re_verified。挂载首检 `checkRuntime` 已删除，hook 不再为 stage/错误读 runtime（`useBrowserSession.ts:402-440` 的派生效应只读 `options.runtimeState`）；`runtimeState` 为空时不写任何错误；`SessionPage.tsx:93,99-101` 已把 `runtimeQuery.data?.observed_state` 作为唯一来源传入。证据测试：`useBrowserSession.t058.test.tsx`（running/error/stopped/恢复 4 项）与 `useBrowserSession.test.tsx` 的 stage 映射 5 例。
- AC-005：TICK-VALID，re_verified。帧信号守卫新增 `runtimeStateRef.current !== "stopped" && !== "error"`（`useBrowserSession.ts:178-185`）。证据测试：`useBrowserSession.t058.test.tsx`（stopped 时 stage 不动且不发音频 pipeline 控制消息；running 对照组正常连接并启动音频）。
- AC-006：TICK-VALID，re_verified。`ErrorBoundary.componentDidCatch` 经 `frontendLog.logError` 记录（`ErrorBoundary.tsx:37-43`）；`RouteErrorBoundary` 以 `location.key` 作 resetKey；`router.tsx` 全部 3 条顶层路由与 `/` 下 10 条子路由逐一包裹；根部 boundary 保留在 `main.tsx` 之外。证据测试：`app_error_boundary.test.tsx`（/boom→/ok 导航恢复、日志断言、顶层与子路由结构断言）。
- AC-007：TICK-VALID，re_verified。首检未完成时 WS_CLOSE 只写 `diagnostics.signalingCloseCode`，不启动恢复（`useBrowserSession.ts:537-540`）；首检定版非 running 或其后变 stopped/error 时取消同 generation 恢复轮询（`useBrowserSession.ts:324-353`，poll 每次 await 后复核取消旗标）。证据测试：`useBrowserSession.t058.test.tsx`（1006 预检只记录、定版 stopped 保持诊断态、2100ms 内零新增 `getRuntime` 调用）。

coverage = 7 / 7

verdict: PASS

reviewed_scope: ac647fb75e006a79
reviewed_scope: 81de8955c56d4188
