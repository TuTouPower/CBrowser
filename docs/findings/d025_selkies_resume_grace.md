# d025 Selkies 2.1.0 resume 仅覆盖 3 秒异常断开，干净关闭会立即销毁会话

- 来源：t007 fix_fe 观察（p008）+ Selkies 2.1.0 源码核对
- 结论：Selkies 2.1.0 的 `SESSION_HOLD_S=3.0` 只在客户端 socket「无 close 帧被切断」时保留会话；Agent 主动 `close()` upstream 会走正常断开路径，立即 `remove_peer`，之后同 `resume_key` 重连只能得到 `SESSION_OK` 而非 `RESUMED`。
- 证据：`src/selkies/webrtc_signaling_server.py`（固定 commit `6ee68a7`）：`hold_session` 的注释与 `cut and await self.hold_session(...)` 条件；`_end_hold` 在 3 秒后 `remove_peer`；`_resume_locked` 要求目标 peer 仍在 `self.peers` 且 `peer_status == "session"`、partner server 存在。p008 观察到的日志顺序为 `peer server not found` → `SESSION_OK`。Agent 修复后单测 `tests/unit/test_stream_resume.py` 验证：viewer 隧道关闭时 upstream 保持打开，新连接以同 `resume_key` 得到 `RESUMED`。
- 影响：Stream Agent 必须在 viewer 隧道关闭/Gateway 断线后保留 loopback upstream 至 resume 窗口（当前 10 秒），不能立即干净关闭；窗口需覆盖前端 5 秒重连等待。窗口到期或 Agent 停止时必须关闭，避免僵尸 Selkies 会话。
- 现状：有效
