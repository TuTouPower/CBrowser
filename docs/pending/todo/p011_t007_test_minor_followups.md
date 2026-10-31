# p011 t007 Round 3 测试 minor 跟进

- 来源：t007 遗留（t007_test_f011、t007_test_f012 Round 3；t007_test_f013 Round 4；均 minor，两路 PASS）
- 内容：
    - t007_test_f011：`useProfileEventsSync` 每个 SSE 事件后使 `profileKeys.runtime(id)` 失效重取（修复 t007_code_f009 时加入），缺少断言该重取发生的 Vitest 回归测试。
    - t007_test_f012：`tests/e2e/test_frontend_session_e2e.py` 关闭页面后对 Browser/Stream 容器状态接受 `running` 或 `created`，宜收紧为 `running`（`test_frontend_app_e2e.py` 已严格断言）。
    - t007_test_f013：`audio_status.test.ts` 的 `samples()` 辅助函数丢弃 `totalAudioEnergy`，“静音不判故障”用例输入与名称不符（判定逻辑本身不读能量，结论不受影响），宜让辅助函数透传该字段。
        修复会改动已通过评审的审查范围，故不在 t007 收尾时处理；下次改前端会话或 SSE 的 task 内补齐。
- 处理：未开
