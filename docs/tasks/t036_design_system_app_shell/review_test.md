# Task review t036（reviewer_focus: 测试）

- task：`t036_design_system_app_shell`
- spec：`docs/tasks/t036_design_system_app_shell/task.md`
- diff_anchor：`95cccfc9f328290cbb13090ef960b0f22a129782`
- target：`git -C '<repo>_t036' diff --cached 95cccfc9f328290cbb13090ef960b0f22a129782`
- round：1
- reviewed_at：2026-11-06T15:42:00+08:00

reviewed_scope: 9faba922a99c099b

## Findings

零 finding。按测试轴复核：测试是否触达生产逻辑、TDD 先红后绿、旧测试逐用例处置、断言未被放宽、门禁证据与 AC 覆盖，未发现 critical / important / minor 级缺陷。

## 结论

- 本轮新发现：0 条。clean 范围内无 critical / important。
- 未进表的提示（纯观察，不阻断、无需处置）：
    - `tests/unit/test_t028_run_gates_evidence.py` 的 suite 列表预期新增 `design_lint` / `design_check` / `design_tokens`，并新增三条 `assert "npm run design:*" in log`；断言语义（evidence 模式跑全部 suite 并记录失败）未变，仅随门禁配置更新，非就地迎合实现输出。定向 4 passed、完整门禁 `unit` 全绿。
    - E2E 中 `create_profile_via_ui` 由 UI 表单改为 `POST /api/v1/profiles`，`stop_profile_via_header` 改为 `stop_profile_via_api`，`profile-item-*` 切换改为 `open_session` 直接导航；均为 plan 5.1 删除旧 UI 后的 fixture 构造变化，核心断言（双标签页 tab_id 独立、SSE 收敛、容器消失、首帧计时）一字未放宽。progress「测试处置清单」逐用例登记，符合 AGENTS「结构被删除的测试整体删除并写明理由、禁止就地改旧预期」。
    - `test_display_profile_size_requires_explicit_apply` 整体删除有明确理由（依赖旧顶栏 `display-pending-badge` / `display-apply-restart-btn`，t039 交付新 UI 时新增对应 E2E）；同文件不依赖 UI 的 `test_stream_entrypoint_rejects_missing_supervised_screen_config` 原样保留；`scopeMutationToProfile.test.ts` 5 用例接替被删除的 `AppLayout.isolation.test.tsx` 2 用例的隔离语义，无覆盖缺口。
    - `t019` 最终全量门禁 3.341s > 2s、定向 84.65s 通过，为 t032 已登记时序遗留；progress 如实登记且不归因 t036，按用户明确口径处理。`test_supervisor_recovery_e2e` 首轮全量偶发失败、定向 20s 通过，同属环境遗留并已登记。
    - 未发现 `assert` 放宽、`.skip` / `.only`、加长 timeout / 重试 / 容差、mock 掉被测逻辑等假绿手法；`design_tokens.test.mjs` 先红（模块不存在）后绿（5 用例），`theme.test.tsx` / `theme_boot.test.mjs` / `ui.test.tsx` / `AppLayout.shell.test.tsx` 均为新增真实断言。
- 总体判断：10 条 AC 均有可复核的自动测试与门禁证据；测试处置清单逐用例可追溯；完整门禁（含 E2E）已实跑并如实记录唯一 t032 遗留；review 处置表无未解决项。PASS。
- 系统性 follow-up：无。

### AC 复验方式

- AC-001：TICK-VALID，re_verified。`design_tokens.test.mjs` 与 `npm run design:lint`（0 error / 0 warning）实跑；AC-001 的 token 覆盖与双模式对比度由官方 lint 逐组件校验，非 mock。
- AC-002：TICK-VALID，re_verified。`design_tokens.test.mjs` 5 用例覆盖角色集合不等 / 未解析引用 / 无前缀颜色 / 官方 lint 报错 / 确定性生成；追加 stale marker 后 `design:check` 退出 1、恢复后通过；完整门禁三 design suite 全绿。
- AC-003：TICK-VALID，re_verified。progress 记录 20 文件源码扫描（0 命中）与构建产物扫描（默认调色板类 0、语义变量与 `.dark` 覆盖存在）的命令与结果；`frontend_build` 全绿。
- AC-004：TICK-VALID，re_verified。`theme.test.tsx` 3 用例（默认 dark / 三态持久化与 system 跟随 / 读取既有偏好）、`theme_boot.test.mjs` 4 用例（vm 实跑经典脚本、head 外链、无内联脚本）、`AppLayout.shell.test.tsx` 主题不写 color_scheme 用例。
- AC-005：TICK-VALID，re_verified。`AppLayout.shell.test.tsx` 5 用例含折叠恢复、拖宽 clamp 与持久化、窄屏抽屉、SSE 运行中数与警示横幅、主题不碰 Profile；`router.test.tsx` 导航 `<a href>` 断言。
- AC-006：TICK-VALID，re_verified。`AppLayout.shell.test.tsx` 的 SSE 警示横幅用例（`role="alert"`）+ `AppLayout.focus.test.tsx` iframe 焦点守卫用例（原样保留、仅补 theme mock），均触达生产组件。
- AC-007：TICK-VALID，re_verified。`router.test.tsx` 新路由表用例、旧路由删除用例、导航 `<a href>` 用例、config 重定向用例，全部走生产 `routes` 与真实组件。
- AC-008：TICK-VALID，re_verified。`ui.test.tsx` 5 用例走生产 Radix 包装组件，断言焦点陷阱 / 归还 / Esc / ARIA / Toast 单实例，未 mock 被测组件。
- AC-009：TICK-VALID，re_verified。progress 记录 dist `https?://` 与 13 个 woff2、内联脚本 0 的扫描命令与结果；`npm run build` + `verify:selkies --check-freshness` 门禁通过。
- AC-010：TICK-VALID，re_verified。`SettingsPage.test.tsx`（i18n 切换 + 2 个平台字体用例）、`auth_guard.test.tsx`（鉴权 / 登录跳转 / 401）、`test_frontend_app_auth_e2e.py`（真实栈登录守卫）共同覆盖；完整门禁 `frontend_test` 248 passed、E2E 95 passed。

## 第 2 轮复核（scope 重绑定）

- 交付内容仅因 `md_format.py --changed` 的 Markdown 格式规范化变化（`docs/blueprint/frontend.md`、`docs/specs/ui_design_system.md`），无任何实现 / 测试 / 契约代码变化；被审 diff 指纹由 `9faba922a99c099b` 重绑为 `187b5cfbff2c91cc`（已重跑 `render_review_prompts.py`）。
- 测试面未变：`npm test` 248 passed、完整门禁证据与 10 条 TICK-VALID 结论继续有效，TICK-VOID 仍为 0。
- 本轮无新 finding，总体结论保持 PASS。

reviewed_scope: 187b5cfbff2c91cc

coverage = 10 / 10

verdict: PASS
