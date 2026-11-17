# Task review t004（reviewer_focus: 测试）

- task：`t004_v2_stream_runtime`
- spec：`docs/tasks/t004_v2_stream_runtime/task.md`
- diff_anchor：`8ff9fd237dcd8e6d1093f3de7503f5b7f599b3e6`
- target：`git -C '<repo>_t004' diff 8ff9fd237dcd8e6d1093f3de7503f5b7f599b3e6`
- round：Round 1
- reviewed_at：2026-10-29T10:15:00+08:00（勘误：前缀时间未核实，实际复核修正时间戳：2026-10-29T13:09:12+08:00）

reviewed_scope: 740fe6627e7735db

## Findings

### t004_test_f001 - 综合端到端测试用例单函数超千行，多阶段断言失败定位成本高

- 严重度：minor
- 锚点：测试结构清晰度与可维护性
- 位置：`tests/e2e/test_stream_runtime_e2e.py:410-1553` (`test_stream_runtime_multi_viewer_e2e`)
- 问题：`test_stream_runtime_multi_viewer_e2e` 将 AC-001 至 AC-006 串联在单个异步测试函数内运行，行数达到 1144 行。虽然各个阶段产出了证据 JSON（如 `active_media_phase.json`、`duplicate_tab_media_proof.json`、`policy_proof.json`、`ascii_attempt.json`、`ime_attempt_*.json` 以及内嵌 isolation 字段的 `media_proof.json` 等）且断言具有独立性，但在中途断言失败时排查与重新分段执行成本较高。
- 建议：后续 task 或重构阶段可考虑将各验证阶段抽象为带上下文 fixture 的独立测试方法，或保留总体验收的同时抽取阶段断言 helper。

## 结论

- 前轮 finding 复核：Round 1 无前轮 finding。
- 改测方向复核：无。唯一修改的已有测试为 `tests/e2e/test_browser_runtime_e2e.py`，改动内容为将历史临时 scratch 分析器路径替换为正式入库的共享测试 fixture `tests/fixtures/runtime_probe/audio_analyzer.py`，并将 `python3` 替换为环境解释器 `sys.executable`，所有原音频频点（440Hz/880Hz/负例/错采样率）断言逻辑完全保留，未发生迁就实现的改测行为。
- 本轮新发现：1 条（minor，非阻断）。
- 独立单测验证：reviewer 使用完整环境解释器执行本 task 7 个 stream 相关单元测试文件（`test_stream_*.py`），49 项单测全部 PASS，耗时 0.95 秒，无告警与失败；Docker 端到端容器测试未在 reviewer 进程中重复拉起，避免多进程抢占固定端口与网络资源，端到端行为均通过静态代码/断言核对并诚实列为 `trust_prior`。
- 未进表的提示：无。
- 总体判断：全部 6 条行为 AC 均具备真实、可信、端到端的双 Google Chrome Stable 页面及真实 Docker 容器环境测试验证支撑。未发现恒真断言、弱化断言、无理由跳过测试或伪造 mock 等危险模式。

### AC 复验方式

- AC-001：`trust_prior`，依赖实施侧与验证会话的实际容器与 Google Chrome 真实解码运行记录及日志证据（`tests/e2e/test_stream_runtime_e2e.py:794-870`，双页首连 `framesDecoded > 0` 且 1920x1080，`totalAudioEnergy > 0`，首页关闭后第二页继续解码且接收音频，浏览器进程 PID 保持不变）。
- AC-002：`re_verified`，查证 Playwright 独立测试 `tests/e2e/test_stream_client_identity_e2e.py` 核心断言（Web Locks 仲裁下同文档并发 HELLO 与复制标签页 ID 重映射）；查证 `tests/e2e/test_stream_runtime_e2e.py:903-1039` 断言逻辑（`window.open` 复制标签页时 ID 重映射且原 PC 连接不被踢除、远端分辨率恒定 1920x1080）；真实容器执行记录取 `trust_prior`。
- AC-003：`re_verified`，reviewer 独立复验通过单测 `tests/unit/test_stream_capture_policy.py` 与 `test_stream_runtime.py`（覆盖 8/30 FPS 状态切换与先 set_fps(8) 后 resume 状态机，全 PASS）；查证 E2E `tests/e2e/test_stream_runtime_e2e.py:1100-1216` 真实 policy 消息、动静画面切换与全隐藏停止解码断言，真实容器执行记录取 `trust_prior`。
- AC-004：`trust_prior`，依赖实施侧及独立验证会话中 `tests/e2e/test_stream_ice_relay_e2e.py` 与 `tests/fixtures/stream_probe/chrome_relay.py` 真实运行证据（单 Profile 同一 UDP mux 端口 30000+ 分配，三代 coturn relay 凭证轮转，同 PC/DTLS/Track 且双侧 candidate 为 relay）。
- AC-005：`trust_prior`，依赖实施侧真实 Google Chrome CDP 运行记录（`tests/e2e/test_stream_runtime_e2e.py:1218-1371`，CDP `Input.imeSetComposition` / `Input.insertText` 通过 X11 XTest 产生输入，同时由 `clipboard_oracle.py` 验证 X11 剪贴板未被篡改；独立静音控制与首页关闭音频连续性）。
- AC-006：`re_verified`，reviewer 独立复验通过单测 `tests/unit/test_stream_transport_hardening.py`（验证只读挂载与边界路径阻断）；查证 E2E `tests/e2e/test_stream_runtime_e2e.py:871-899,1456-1495` Docker inspect 检查断言（无 docker.sock 或用户数据目录）及 Agent 重连/Stream 暂停断言；真实容器运行记录取 `trust_prior`。

coverage = 3 / 6 (50.0%)
建议合并前人工抽查 trust_prior 项。

- 系统性 follow-up：无

verdict: PASS
