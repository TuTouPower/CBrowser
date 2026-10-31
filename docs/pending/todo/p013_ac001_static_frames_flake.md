# p013 AC-001 双页切换用例依赖静止画面出新帧

- 来源：t007 最终门禁 r5 观察（`frontend_e2e` 1 failed，同用例复跑 2/2 passed，`.scratch/project_gates/r5_rerun/`）
- 内容：`tests/e2e/test_frontend_app_e2e.py::test_ac001_ac006_profile_ui_dual_tab_sse_and_stale_state` 在 A 页切换到 B 后等待 2 秒，断言 B 页 `framesDecoded` 增长；远端为静止页面时 Selkies 按画面变化捕获，可长时间不出新帧（观测 1→1），形成偶发失败。应在测量前驱动远端画面变化（如经 CDP 输入或切换运动页面）再断言帧数增长，并同时断言 B 页 tab_id 与 PeerConnection 状态不变。t007 已达 review 轮次上限，改测会使审查范围失效，故留待后续前端 task 处理。
- 处理：未开
