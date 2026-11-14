# p100 t061 改 stage action 矩阵后 frontend_session E2E 断言过时

- 来源：gate4 真实补验新发现（2026-11-14）
- 内容：`tests/e2e/test_frontend_session_e2e.py::test_frontend_session_freeze_resume_and_diagnostics:622` 断言未就绪 Profile 诊断浮层里 `[data-testid="sess-stage-action-reconnect"]` 存在，实测为 None（单跑稳定复现）。根因：t061 AC-003 把 action 矩阵改为 `runtime_not_ready` → `launch` + `view-status`、`stopping` → `view-status`，仅 default 分支保留 reconnect（`SessionStagePanel.tsx:57-66`）；前端单测 `SessionStagePanel.test.tsx:81-92/112-124` 已同步新矩阵，该 E2E 断言未同步。判定：测试预期过时，非产品缺陷、非 dist 陈旧（gate4 `frontend_build=0`）。按 AGENTS.md「禁止就地把旧测试预期改成当前实现的输出」，不得内联改断言凑绿；须整体删除该过时断言并写明理由，或新增覆盖新语义的 E2E 用例（`launch` + `view-status` 存在、reconnect 不存在）。
- 处理：未开
