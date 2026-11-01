# p009 multi_viewer E2E 固定等待导致偶发失败

- 来源：t007 门禁观察（t004 既有用例）
- 内容：`tests/e2e/test_stream_runtime_e2e.py::test_stream_runtime_multi_viewer_e2e` 在开第二个页面后固定 `sleep(2.0)` 即断言两个 viewer 已注册，负载下偶发一个 viewer 在 HELLO 前断开（Selkies 记 `Invalid hello message type`）。应改为有上限的轮询等待条件成立；属 t004 既有测试，按规范修改等待方式不改断言。
- 处理：323efaa；resolution=resolved；reason=A28 将 multi_viewer 的固定 sleep 改为带超时的 viewer/媒体条件轮询
