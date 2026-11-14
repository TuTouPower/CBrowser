# p100 t061 后 frontend_session E2E 断言过时（假 Profile id 停在 transient stage）

- 来源：gate4 真实补验新发现（2026-11-14）
- 内容：`tests/e2e/test_frontend_session_e2e.py::test_frontend_session_freeze_resume_and_diagnostics:622` 断言未就绪 Profile 诊断浮层里 `[data-testid="sess-stage-action-reconnect"]` 存在，实测为 None（gate4 单跑稳定复现）。**真实根因**：该用例使用伪造 id `/session/stopped-or-unready-profile-id`，在 E2E harness 下页面停在 t061 AC-002 的 transient waiting stage（`checking_runtime`），按 `SessionStagePanel.tsx:57-66` 的 `WAITING_STAGES` 设计**不渲染任何 action 按钮**；reconnect 与其后的 view-status 两条断言从未成立过（view-status 因前者先失败而从未执行）。用**真实存在且停止的 Profile** 在生产栈实测则进入 `runtime_not_ready`，正确渲染 `launch` + `view-status`、无 reconnect（`.scratch/terminal_deploy_slices/p090_p100_real_profile.log`）。判定：测试预期基于错误的 stage 假设，非产品缺陷、非 dist 陈旧（gate4/gate5 `frontend_build=0`）。按 AGENTS.md「禁止就地把旧测试预期改成当前实现的输出」，不内联改断言凑绿；处理方式为整体删除失效断言块并写明理由 + 新增覆盖 AC-002 真实语义的 E2E 用例。
- 处理：683aa10；resolution=resolved；reason=整体删除假 Profile id 下失效断言并新增覆盖 t061 AC-002 真实语义的 E2E 用例，frontend_session 整文件 4 passed、gate5 全绿

## 终局补验证据（gate5，最终结论）

- 修订（提交 `683aa10`）：整体删除 `reconnect` / `view-status` 两条失效断言并在原处写明根因；新增 `test_frontend_session_unready_waiting_stage_has_no_action_buttons`，用真实 DOM 查询断言 `sess-diag-overlay` 可见、title 属于合法未就绪/检查中集合、且 `[data-testid^="sess-stage-action"]` 集合为空（t061 AC-002 transient stage 正确行为）。旧用例的 overlay / title 断言原样保留。
- `test_frontend_session_e2e.py` 整文件单跑 `4 passed in 117.05s`；gate5 全量 e2e 105 用例 0 failed / 2 skipped、`GATE_EXIT=0`。
- t061 AC-003 矩阵另由生产栈真实 Chrome 探测留证（launch + view-status 存在、reconnect 不存在），见 p090 终局证据段。
