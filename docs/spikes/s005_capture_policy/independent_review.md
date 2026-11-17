# 捕获策略（Capture Policy）独立审计与黑盒复核报告

**评审基准与环境约束**：

- 审查目录：`<repo>/.scratch/v2_orchestration/policy_review/.scratch/capture_policy_probe`
- 评审角色：独立 Reviewer / 黑盒验证者（不 commit、不改生产代码、不访问其它 worktree、不替 author 修复实现与预期）
- 审计对象：
    - `live_policy_agent.py`（捕获策略 Agent 与 WebRTCService 适配层）
    - `entrypoint_stream.py`（Stream 运行时注入入口）
    - `entrypoint_browser.sh`（Browser 容器启动脚本）
    - `test_e2e_real_pipeline.py`（端到端实跑测试套件）
    - `test_page.html`（已补齐的测试基准页面）
    - `report.md`（交付验收报告）

______________________________________________________________________

## 1. 完整资产真实执行结果与命令退出码

在主控补齐 author 同快照基准页面 `test_page.html` 后，原样执行黑盒端到端测试：

### 1.1 执行命令

```bash
uv run --no-project --with playwright --with aiohttp python test_e2e_real_pipeline.py
```

### 1.2 执行结果与退出状态

- **真实命令 Exit Code**: `0`
- **控制台执行日志**：完整保存在当前 scratch 的 `real_e2e.log`
- **各场景实测表现**：
    1. `Scenario 1 (Static Scene Target 8.0 FPS)`: **PASS**（UDS pipeline_fps=8.0, 客户端 decoded FPS=0.0）
    2. `Scenario 2 (Canvas Animation 60fps -> Elevates 30.0 FPS)`: **PASS**（UDS pipeline_fps=30.0, motion_fps_estimate=8.0~29.8, 客户端实测 decoded FPS=30.0）
    3. `Scenario 3 (Low-Frequency 0.5Hz Blink -> Relaxes to 8.0 FPS)`: **PASS**（UDS pipeline_fps=8.0, motion_fps_estimate=0.0, 客户端实测 decoded FPS=0.5）
    4. `Scenario 4 (User Input Activity -> Elevates 30.0 FPS)`: **PASS**（UDS pipeline_fps=30.0）
    5. `Scenario 5 (Foreground Protection against Background Viewer)`: **PASS**（Tab 2 发送 STOP_VIDEO，Tab 1 仍活跃，全局 pipeline 维持 30.0 FPS）
    6. `Scenario 6 (All Viewers Hidden Pause)`: **PASS**（Tab 1 亦 STOP_VIDEO，active_peers=0，真实调用 `pause_screen_capture()`，`is_screen_capturing=False`）
    7. `Scenario 7 (Resumption Order)`: **PASS**（Tab 1 发送 START_VIDEO，初次恢复捕获时处于 8.0 FPS，随后画面运动升至 30.0 FPS）
    8. `Scenario 8 (All Disconnected Capture Pause)`: **PASS**（双 Tab 关闭触发 handle_peer_gone，total_peers=0，抓屏安全暂停）
    9. `Scenario 9 (Protocol Armor Verification)`: **PASS**（客户端注入 `_arg_fps,120` 与非法参数，pipeline_fps 未被篡改）

______________________________________________________________________

## 2. 深入源码核查：精确行号与调用链分析

通过容器内 inspect 对比官方基类 `selkies.webrtc_mode.WebRTCService`、`selkies.webrtc_media_pipeline.MediaPipelinePixel` 与作者实现的 `RealPolicyControlledWebRTCService`、`LiveCapturePolicyAgent`：

### 2.1 官方 Callback 与 Agent 控制权接管核查

- **官方基类实现**：
    - `selkies.webrtc_mode.WebRTCService.handle_video_consumer_active`（行 1877~1905）：
        官方逻辑在收到 `active=True` 时立即调用 `self._resume_display_capture(..., "consumer resume", idr_always=True)`；在收到 `active=False` 时检查 `all(p.get("video_paused", False) for p in self._display_consumers(display_id))`，若全部暂停则直接调用 `pipeline.pause_screen_capture()`。
    - `selkies.webrtc_mode.WebRTCService._settle_primary_consumers`（行 1940~1950）：
        在管道启动后（`start_display_media` 行 1264）同步检查所有 consumer 是否全部 paused，若是则调用 `pipeline.pause_screen_capture()`。
- **Author 适配层实现**：
    - `live_policy_agent.py:91-94`：
        ```python
        def setup_callbacks(self) -> None:
            super().setup_callbacks()
            self.rtc_app.on_video_consumer_active = self.handle_video_consumer_active
        ```
    - `live_policy_agent.py:95-108`：
        ```python
        async def handle_video_consumer_active(self, peer_id: str, display_id: str, active: bool) -> None:
            ...
            peer["video_paused"] = not active
            if sender is not None:
                sender._enabled = active
            if self.policy_agent:
                self.policy_agent.set_peer_active(peer_id, active)
        ```
- **技术事实与风险定级**：
    - **正面**：Author 在 `handle_video_consumer_active` 中**移除了官方原版的直接 pause/resume 分支**，改为将状态更新到 `LiveCapturePolicyAgent.peers`，由 Agent 的 `_reconciliation_loop`（行 259-294）统一仲裁，确实避免了官方与 Agent 在 consumer active 事件上的直接双重触发冲突。
    - **残留竞态/状态同步边界**：
        1. **信令断开时的对账滞后**：在 `live_policy_agent.py:109-114`，`handle_peer_gone` 仅调用 `self.policy_agent.remove_peer(peer_id)`。真正的 `pause_screen_capture` 依赖 Agent 的周期对账轮询（200ms `asyncio.sleep(0.2)`，行 261）。断开至停止抓屏存在最多 200ms 的对账窗口。这在一般场景可接受，但并非即时原子停止。
        2. **唤醒时的 IDR 关键帧时延**：当捕获已处于运行中（例如 Tab 1 正在看动画，Tab 2 从后台切回前台），官方原版代码（行 1899）会无条件调用 `_resume_display_capture(..., idr_always=True)` 触发 `request_idr_for_display`，确保切回前台的 Peer 能够立即拿到 IDR 帧重置解码器。而在 Author 实现中，`handle_video_consumer_active` 仅标记 `set_peer_active(peer_id, True)`，Agent 发现 `p.is_screen_capturing()` 已为 True 便直接跳过（行 278-281），导致切回前台的 Peer 不会收到显式请求的 IDR 帧，必须依赖 WebRTC 底层 PLI 丢包重传回退，在弱网下可能导致前台切回时瞬间花屏或黑屏数秒。

### 2.2 恢复顺序（先 set 8 再 resume）核查

- **实现位点**：`live_policy_agent.py:116-134`
    ```python
    124:             await pipeline.set_framerate(8.0)
    125:             if self.policy_agent:
    126:                 self.policy_agent.current_fps = 8.0
    127:             restarted = await pipeline.resume_screen_capture()
    ```
- **技术事实**：
    - 源码确实严格遵循了先 `pipeline.set_framerate(8.0)`，再执行 `pipeline.resume_screen_capture()` 的物理顺序。
    - 官方 `MediaPipelinePixel.start_screen_capture()` 内部调用 `generate_capture_settings()` 时会读取 `self.framerate` 作为 `CaptureSettings` 的初始帧率。因此预先将 `pipeline.framerate` 置为 8.0 能够保证 pixelflux 启动时的初始帧率为 8，消除了默认 30/60 FPS 唤醒闪烁。
    - **实现正确性**：代码逻辑实现正确。

### 2.3 协议装甲（Protocol Armor）拦截核查

- **实现位点**：`live_policy_agent.py:53-67`
    - 拦截列表 `FORBIDDEN_PEER_PREFIXES = ("_arg_fps,", "r,", "s,", "_rc,", "_crf,", "vb,", "ab,")`
    - SETTINGS 过滤 `("framerate", "manual_width", "manual_height", "manual_resolution", "scaling_dpi", "video_streaming_mode")`
- **技术事实**：
    - 官方数据通道消息格式中，`_arg_fps,` 用于设置客户端指定帧率，`r,` 用于分辨率重设，`SETTINGS,` 用于全局流设置。
    - Author 在 `_on_peer_data_message` 入口处对字符串消息进行了前缀拦截和 JSON 键值清洗，有效阻止了客户端通过前端注入非法 FPS、修改桌面分辨率或强开 `video_streaming_mode=true`（Turbo）。

______________________________________________________________________

## 3. 测试覆盖缺口与不严谨断言清单（Test Gaps）

虽然测试全量执行 Exit 0，但作为严格独立审阅，必须指出测试实现中的覆盖漏洞与断言不足：

### 缺口 1：输入验证走 UDS 伪造，未走真实 Peer DataChannel

- **代码位点**：`test_e2e_real_pipeline.py:86-94`, `test_e2e_real_pipeline.py:335`
- **事实证据**：
    ```python
    def trigger_uds_input():
        cmd = ["docker", "exec", STREAM_CONTAINER, "python3", "-c",
               "s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)\n"
               "s.connect('/tmp/capture_policy_agent.sock')\n"
               "s.sendall(json.dumps({'cmd': 'record_input'}).encode() + b'\\n')\n"]
    ```
    在 `Scenario 4` 中，测试通过宿主机 `docker exec` 直连 UDS 套接字发送 `record_input` 指令提升帧率。
- **缺失门禁**：这绕过了 `RealPolicyControlledWebRTCService._on_peer_data_message`（`live_policy_agent.py:69-72`）对真实键鼠消息（`"kd,"`, `"ku,"`, `"m,"` 等）的解析与放行逻辑。应通过 Playwright 页面中的 DataChannel 发送实际的鼠标/键盘报文来验证该链路。

### 缺口 2：恢复顺序仅查瞬时状态，未做顺序跟踪断言

- **代码位点**：`test_e2e_real_pipeline.py:382-410`（Scenario 7）
- **事实证据**：
    测试在发送 `START_VIDEO` 后轮询 `query_uds_state()` 直至捕获恢复，随后断言 `st7["pipeline_fps"] == 8.0`。
- **缺失门禁**：因在暂停期间 `self.current_fps` 本就被赋为 8.0，若实现颠倒了先 resume 后 set 8，该测试由于采样时延极可能依旧观察到 8.0 而显示 PASS。测试缺乏对底层方法调用序列的直接检验或插桩验证。

### 缺口 3：Page Visibility 未走真实浏览器隐藏事件

- **代码位点**：`test_e2e_real_pipeline.py:348-358`, `368-370`
- **事实证据**：
    测试采用在页面内通过 JS 查找 RTCPeerConnection 并直接向 DataChannel `send('STOP_VIDEO')` 的方式模拟隐藏。
- **缺失门禁**：虽然在服务端收到的消息格式与官方客户端一致，但这未覆盖前端 `visibilitychange` 事件监听器是否正确触发发送 `STOP_VIDEO` 的全链路。

### 缺口 4：协议装甲断言范围较弱

- **代码位点**：`test_e2e_real_pipeline.py:442`
- **事实证据**：
    `assert st9["pipeline_fps"] != 120` 仅断言帧率未变为 120。未断言 `video_streaming_mode` 是否依然保持为 `false`，也未检验 X11 分辨率是否未被修改为 800x600。

______________________________________________________________________

## 4. 通过的严格边界与 Author 后续处理建议

### 4.1 已通过验证的严格技术边界（Verified Strict Boundaries）

1. **多身份真实双连接与前台保护有效**：
    - 同一 Chrome 实例内两个 Tab 同时建立 WebRTC 连接，服务端正确识别为 2 个独立的 PeerConnection。
    - 当一个 Peer 处于 STOP_VIDEO（后台）而另一个处于 START_VIDEO（前台）时，前台画面的 30 FPS 运动帧率得到完全保护，未被后台 Peer 拖慢。
2. **真正的 Damage-Gated 动态判定**：
    - 依赖真实 X11 Damage 累积帧率进行动态升降频有效：
        - 静止画面：Damage 帧为 0，服务端 target 维持在 8.0 FPS，客户端 decoded 帧率为 0.0 FPS。
        - 60fps 持续 Canvas 动画：Damage 帧率达到 ~30 fps，服务端 target 升至 30.0 FPS，客户端解码帧率达到 30.0 FPS。
        - 0.5Hz 低频闪烁（每 2 秒一次脉冲）：未达到 6.0 fps 运动阈值，系统在 idle timeout 后稳定降频至 8.0 FPS，客户端解码帧率为 0.5 FPS，与高频动画形成清晰对比。
3. **真实抓屏生命周期管控**：
    - 当全部 Viewers 隐藏（所有 Peer 均为 STOP_VIDEO）或全部断开（连接关闭）时，服务端真实调用 `pause_screen_capture()`，抓屏彻底停止，不再产生画面捕获开销。

### 4.2 建议 Author 后续处理项（Action Items for Author）

1. **修复后台切回前台的 IDR 刷新漏洞**：
    - 在 `RealPolicyControlledWebRTCService.handle_video_consumer_active` 中，若 `active=True` 且当前捕获已在运行（`pipeline.is_screen_capturing() is True`），应补充调用 `await self.request_idr_for_display(display_id)`，确保切回可见的 Peer 能够立即收到关键帧，避免画面解码滞后。
2. **补齐真实 DataChannel 输入端到端门禁**：
    - 在 `test_e2e_real_pipeline.py` 的 Scenario 4 中，改用 `page.evaluate("pc.__send_channel.send('m,100,100')")` 发送原生鼠标移动指令替代 UDS 的 `trigger_uds_input()`，使测试覆盖完整的输入协议链路。
3. **严密化协议装甲断言**：
    - 在 Scenario 9 中增加对 `video_streaming_mode` 和显示尺寸的明确断言，确保即使客户端发送非法尺寸和模式设置，服务端的当前模式与物理尺寸均保持不变。

______________________________________________________________________

## 5. 审查结论

- **命令执行结果**：`test_e2e_real_pipeline.py` 在包含完整 fixture 下**真实执行通过，Exit Code 0**。
- **评审判定**：**CONDITIONAL ACCEPT（有条件通过 / 需跟进测试与 IDR 完善）**。
- **总体评价**：核心控制机制（基于 Damage 的 8/30 动态帧率、双 Tab 前台保护、全隐藏/断开真实暂停、8 FPS 唤醒重启、协议装甲过滤）在真实物理容器与真实 Google Chrome 客户端拓扑下均已得到有效验证。测试中存在的 UDS 替代输入与顺序断言不足属于测试严谨性缺口，已在上述处理项中明确标出，不阻塞当前阶段的架构可行性确认。
