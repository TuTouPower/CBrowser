# 捕获策略 (Capture Policy) R4 独立审计与黑盒复测报告

**审计结论**：**PASS**  
**审计基准快照目录**：`.scratch/native_policy_review_r4`  
**审计环境**：macOS (darwin/arm64) + OrbStack Docker + 物理 Google Chrome 141.0.7390.123  
**执行原则**：未修改任何交付源码与测试用例；专属 TMPDIR 限定于本 worktree `.scratch/` 目录；仅清理自身测试容器，未干涉其他端口实验容器。

---

## 一、交付文件 SHA256 校验清单

```
0893b25b4d80f09d2293c3b39638e269d76ec9476c546e26471f64081092728b  entrypoint_browser.sh
b63601a77b11a3b400dff909dcb8f8cede4378350d9790c821c63ea29cc1a153  entrypoint_stream.py
ca74a5cf57486c2b7211792146ae994301fa78b72d66820704f67b5bd61bb886  live_policy_agent.py
329d983b90c1a654b26045ec9482ce05392280295993cc8fb00237ee136e3e30  test_e2e_real_pipeline.py
138f95fe66045e8baa645bc320d3d34811453f4d3c8297f33a641b1f314850a2  native_visibility_e2e.py
7bca78ac28456611eda20d65544b85756c45d70f4720e2b3c132d7769748f56e  test_page.html
c0120cd81fb5a8b848835887209f35bdbefaa573f2b90afd7846703ac7a9af5a  report.md
845bade824feed69d2b317cd9af1ab3572f50c834da5a09f54743113310361f9  previous_review_r3.md
```

---

## 二、真实黑盒测试串行执行结果与指标

测试按指定命令串行执行，独占 18084 (TCP) 与 30008 (UDP)。

### 1. 套件 1：Core 端到端实跑套件 (`test_e2e_real_pipeline.py`)

- **执行命令**：
  ```bash
  TMPDIR="<repo>/.scratch/v2_orchestration/policy_review/.scratch/native_policy_review_r4/tmp" uv run --no-project --with playwright --with websockets python test_e2e_real_pipeline.py
  ```
- **实际退出码**：`0` (PASS)
- **执行耗时**：71.4 秒
- **日志落盘**：`.scratch/native_policy_review_r4/real_e2e.log`
- **全量 9 项场景实测观测**：
  - `Scenario 1` (静态 8 FPS)：`has_screen_motion=False`, `pipeline_fps=8.0`, 客户端解码 `0.5 FPS` (<= 8.5)。
  - `Scenario 2` (Canvas 动画 30 FPS)：`has_screen_motion=True`, `pipeline_fps=30.0`, 客户端解码 `29.4 FPS` (>= 15.0)。
  - `Scenario 3` (0.5Hz 低频闪烁对照)：`has_screen_motion=False`, 回落并稳定在 `8.0 FPS`, 客户端解码 `3.5 FPS`。
  - `Scenario 4` (DataChannel 输入穿透)：接收键鼠 DataChannel 指令，提频至 `30.0 FPS`，底层 X11 光标到达 `(250, 250)`，CloakBrowser DOM Oracle `inputCount` 从 0 增至 3。
  - `Scenario 5` (前台保护对抗后台)：Tab 2 发送 `STOP_VIDEO`，Tab 1 保持活跃，全局帧率维持 `30.0 FPS` 未被拉低 (`active_peers=1`)。
  - `Scenario 5b` (后台 Peer 恢复与 IDR)：Tab 2 发送 `START_VIDEO` 唤醒，未拉低活跃流，Tab 2 `framesDecoded` (143 -> 175) 持续递增。
  - `Scenario 6` (全部隐藏暂停抓屏)：Tab 1 也发送 `STOP_VIDEO`，`active_peers=0`，实际触发 `pause_screen_capture()`，`is_screen_capturing=False`。
  - `Scenario 7` (恢复抓屏严格有序)：Tab 1 发送 `START_VIDEO`，过滤后最新 Action Trace 证实 `set_framerate(8.0)` (index 0) 严格先于 `resume_screen_capture()` (index 1)，随后动画提频至 30.0 FPS，解码恢复至 `30.5 FPS`。
  - `Scenario 8 & 8b` (全部断开暂停与重新连接自愈)：关闭双 Tab 触发捕获暂停；新 Tab 重连后捕获恢复，解码稳定在 `31.0 FPS`。
  - `Scenario 9` (协议装甲与防篡改)：显式等待解码器首帧就绪 (`1920x1080`)，注入 `_arg_fps,120`、`r,800x600` 及 `SETTINGS (Turbo/120fps/800x600)`。指令均被剥离丢弃，物理 X11 与客户端解码尺寸严格坚守 `1920x1080`，静态对照安全回落 `8.0 FPS`。

---

### 2. 套件 2：原生 Chrome Visibility E2E 套件 (`native_visibility_e2e.py`)

- **执行命令**：
  ```bash
  TMPDIR="<repo>/.scratch/v2_orchestration/policy_review/.scratch/native_policy_review_r4/tmp" uv run --no-project --with websockets python native_visibility_e2e.py
  ```
- **实际退出码**：`0` (PASS)
- **执行耗时**：24.9 秒
- **日志落盘**：`.scratch/native_policy_review_r4/native_visibility_e2e.log`
- **全量 7 项场景实测观测**：
  - `V-1` (同窗双 Tab 原生 doc.hidden 对应 active=1)：同窗双 Tab（windowId `1453834022` 相同），Tab 2 激活（`hidden: false`），Tab 1 处于后台（`hidden: true`），服务端 `active_peers=1`，动画维持 `30.0 FPS`。
  - `V-2` (持续动画前后台解码分流)：2.0s 内前台 Tab 2 解码 +60 帧且字节递增（+226KB），后台 Tab 1 解码增量严格停滞（+0 帧）。
  - `V-3` (Tab 切换互换且维持 30 FPS)：CDP 激活 Tab 1，前后台互换；Tab 1 解码 +60 帧，Tab 2 停滞 +0 帧；全局帧率稳定在 `30.0 FPS`。
  - `V-4` (最小化窗口全部隐藏实际暂停)：`Browser.setWindowBounds` 最小化窗口，双 Tab 原生事件触发 `hidden: true`，Adapter 发送 `STOP_VIDEO`，服务端 `active_peers=0`，实际触发 `pause_screen_capture()`，`is_screen_capturing=False`。
  - `V-5` (窗口恢复有序唤醒与动画提频)：恢复窗口并激活 Tab 1，截断时间戳过滤后审计证实：`set_framerate(8.0)` 先于 `resume_screen_capture()`；随后动画提频至 30.0 FPS，解码恢复增长（+43 帧，+428KB）。
  - `V-6` (关闭一 Tab 另一 Tab 持续)：CDP `Target.closeTarget` 关闭 Tab 2，剩余 Tab 1 持续捕获，`total_peers=1`, `active_peers=1`, `is_screen_capturing=True`。
  - `V-7` (全部关闭暂停抓屏且 CloakBrowser 存活)：关闭 Tab 1，所有连接断开，捕获暂停；CDP loopback 校验证实内部 CloakBrowser 容器进程保持存活（exit=0, targets=1）。

---

## 三、R4 重点修复机制深度验证

### 1. 废除 600ms 人为假等待 (No Grace Period)
- **代码核查**：`live_policy_agent.py` 中 `self.resume_grace_period` 与 `in_resume_grace` 已彻底删除。
- **实测时序验证**：
  在 `native_visibility_e2e.log` Scenario 5 中：
  - `set_framerate(8.0)`：`802793.792697`
  - `resume_screen_capture()`：`802793.792731`
  - 动态运动检测提频 `set_framerate(30.0)`：`802793.827439`
  **实测提频延迟仅为 34.7 毫秒**，未施加任何人为 600ms 锁定，首帧自然从 8 FPS 启动并在检测到持续运动后极速升频，完全符合第 19 章延迟指标要求。

### 2. 单一幂等串行控制器与互斥锁 (Single Controller / FPS Mutex)
- **代码核查**：
  - `LiveCapturePolicyAgent` 初始化 `self._control_lock = asyncio.Lock()`。
  - 所有状态变更（`handle_video_consumer_active`, `handle_consumers_changed`, `handle_peer_gone`, `_resume_display_capture`, `record_input`, `_reconciliation_loop`）统一收敛至 `reconcile_capture_state(caller=...)`，外层受 `async with self._control_lock` 严格互斥保护。
  - 全工程不存在绕过 Controller 直接调用 `pipeline.pause_screen_capture()` 或 `pipeline.set_framerate()` 的旁路。
- **状态脱节修复**：暂停抓屏时不再粗暴修改 `self.current_fps = 8.0`，UDS 查询返回的 `pipeline_fps` 与 `current_fps` 均维持底层真实状态（暂停时如实记录 30.0），并在 resume 时由 `set_framerate(8.0)` 统一同步，彻底消除了 R3 审计指出的状态脱节隐患。

### 3. DataChannel 专属通道过滤 (Input Channel Only)
- **代码核查**：`native_visibility_e2e.py` 中 `setupDataChannel` 增加守卫：
  ```javascript
  if (dc.label !== 'input') return;
  ```
- **实测验证**：过滤了 `pointer` 等其他辅助通道，严格限定仅在官方 `input` 控制通道握手完成后发送 `STOP_VIDEO`/`START_VIDEO`。

### 4. 真实 Action Trace 审计隔离
- **机制验证**：Scenario 7 与 Native V-5 在触发恢复前通过 UDS 采样截取 `last_action_time = pre_actions[-1]["time"]`，断言时仅对 `a["time"] > last_action_time` 的新增调用进行索引排序比较。
- **时钟隔离**：仅在容器内部 `time.monotonic()` 维度进行增量截断比较，不进行宿主与容器间跨系统单调时钟的伪比较。

### 5. 协议装甲与客户端尺寸无遮蔽校验
- **代码核查**：`test_e2e_real_pipeline.py` Scenario 9 删除了 R3 的 `if frameWidth > 0` 宽松跳过，改为循环等待真实解码就绪，显式断言首帧尺寸与攻击后尺寸严格为 `1920x1080`。
- **攻击防御实测**：注入 `_arg_fps,120`、`r,800x600` 及 `SETTINGS (Turbo)` 后，DataChannel 确认发送成功，X11 与解码器几何尺寸维持 1920x1080，静态对照下成功回落至 8.0 FPS，证实 Turbo 模式已被安全剥离。

### 6. 旧 Scenario 10 退役与 Native 7 项替代
- 原版 Selkies 官方客户端未适配 Tab 切换 visibility 的历史用例 Scenario 10 已从 Core 套件彻底移除（行数由 936 行缩减至 740 行）；
- 原生 Chrome Page Visibility 已由独立的 `native_visibility_e2e.py` 7 项全量实测闭环覆盖。

---

## 四、实测边界与观测限制 (Limitations)

1. **Native Chrome 后台 Tab 的 WebRTC 握手时延**：
   在同窗双 Tab 启动初期，未获得焦点的后台 Tab 会受到 Chrome 原生 Background Tab Throttling 限制。实测建立 WebRTC 完整连接需约 10 秒（测试脚本内设置了 60 次轮询 * 0.3s = 18s 窗口）。若宿主极端高负载导致握手超过 18 秒，可能偶发握手等待超时。生产环境集成至前端 ViewerConnection 时，应在 Tab 切换或获得焦点时即时激活连接。
2. **性能验收定位**：
   `test_e2e_real_pipeline.py` 与 `native_visibility_e2e.py` 的通过证明了**捕获策略状态机在各种网络/输入/视窗变化下的逻辑正确性与鲁棒性**，不等于高并发、长时间弱网丢包下的音画同步压力测试。

---

## 五、环境清理验证

- 已确认测试临时容器 `cbrowser-spike-capture-browser`、`cbrowser-spike-capture` 已由 `finally` 块彻底销毁；
- 宿主其他并发实验容器（如 coturn / turn stream / postgres 等）完好运行未受干扰；
- Git 工作区保持干净，无追踪文件受损。
