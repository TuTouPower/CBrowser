# CBrowser v2 WebRTC Media E2E Tech Validation Independent Review

- **Reviewer**: Independent Blackbox Reviewer / Architecture Auditor
- **Model**: `cpa/gemini-3.8-flash`
- **Execution Date**: 2026-10-27
- **Worktree Scratch Path**: `<repo>/.scratch/v2_orchestration/review/.scratch/media_final_review`
- **Audit Target**: `media_e2e_probe.py`, `entrypoint_browser.sh`, `entrypoint_stream.sh`, `start_containers.sh`, `stop_containers.sh`

______________________________________________________________________

## 1. 实际执行记录 (Execution Log & Exit Code)

### 1.1 容器启动 (`bash start_containers.sh`)

- **命令**: `bash start_containers.sh`
- **Exit Code**: `0`
- **容器与网络状态**:
    - `cbrowser-spike-media-net`: Bridge 隔离网络创建成功。
    - `cbrowser-spike-media-browser`: 容器基于 `cbrowser-spike-runtime-browser:test` 成功启动，Xvfb (:99, 1920x1080x24) + PulseAudio (`/tmp/pulse/native`) + Openbox + CloakBrowser 正常运行。
    - `cbrowser-spike-media-stream`: 容器基于 `cbrowser-spike-runtime-stream:test` 成功启动，挂载共享 X11 与 Pulse 卷，绑定 `127.0.0.1:18081` (TCP) 与 `127.0.0.1:30006` (UDP)。

### 1.2 Probe 探针执行 (`uv run --no-project --with playwright python media_e2e_probe.py`)

- **命令**: `uv run --no-project --with playwright python media_e2e_probe.py`
- **Exit Code**: `0`
- **耗时**: 55.58 秒
- **控制台日志关键节点**:
    - `[Item 06] Connecting Tab 1 and Tab 2`: 第 12 秒两个 Tab 均转为 `connected`，分辨率稳定为 `1920x1080`；外部强制更改 viewport 为 800x600 后，WebRTC 接收分辨率保持 `1920x1080`（`fixed 1080p: True`）。
    - `[Item 12] UDP Mux`: 双方 remote candidate port 均为 `30006`，protocol 为 `udp`，检测到 host candidate 30006。
    - `[Item 04 / Audio]`: Tab 1 增长 63,756 bytes (`totalAudioEnergy=6.9786`)；Tab 2 增长 64,722 bytes (`totalAudioEnergy=6.8845`)。Tab 1 静音后，Tab 2 独立增长 48,300 bytes。
    - `[Item 08] Concurrent Input`:
        - 负例 (8.1): 仅由 Tab 1 发送 `111`，CDP 查得 DOM 值为 `'111'`（`count(1)==3, count(2)==0`，负例拦截生效）。
        - 正例 (8.2): Tab 1 发送 `111`，Tab 2 发送 `222`，CDP 查得 DOM 值为 `'121212'`（`count(1)==3, count(2)==3, len==6`，无粘键丢失）。
    - `[Item 07] WebLocks Guard, Freeze & Close`:
        - 7.1 刷新: Tab 1 重载后保持原 `tabId` (`57dcf3da-56db-4cb5-b633-1ab6113b5352`)。
        - 7.2 复制冲突: Page 3 携带 Tab 2 ID，WebLocks Guard 拦截碰撞（`action: remapped_collision`），重映射为新 UUID (`f4695136-6114-4438-a37e-ce3081a684fa`)，触发标准 code 1000 重连。官方 HELLO 原始字符串未经 rewrite 转发。
        - 7.4 CDP 挂起: Tab 2 执行 `Debugger.pause`，Page 4 携带 Tab 2 ID 进入，WebLocks 在内核层拦截（无需 Tab 2 执行 JS 广播），Page 4 自动重映射并连接成功；Tab 2 恢复后依然存活。
        - 7.5 首 Tab 关闭: Tab 1 关闭后，Tab 2 继续解码（frame growth 24 frames），音频继续增长（+48,784 bytes, energy +1.97），CloakBrowser 保持 11 个进程存活。
    - `[Items 09 & 10]`: 明确标记 `NOT_RUN`，本地测量观察为 8.0 FPS。
- **最终 Verdict**: `VERIFIED_PASS_WITH_NOT_RUN` (退出码 0)。

### 1.3 资源清理 (`bash stop_containers.sh`)

- **命令**: `bash stop_containers.sh`
- **Exit Code**: `0`
- **清理范围**: 仅清理 `cbrowser-spike-media-stream`、`cbrowser-spike-media-browser`、相关临时 volume 与 network，宿主无残留孤儿容器。

______________________________________________________________________

## 2. 源码行号级审核 (Source Code Audit)

### 2.1 同 Chrome Context 双 Tab 隔离与抗 Viewport Resize

- **源码位点**:
    - `media_e2e_probe.py:305-323`: 使用 `p.chromium.launch_persistent_context` 统一初始化单会话共享 Profile (`user_data_dir=PROFILE_DIR`)，分别创建 `page1` 与 `page2`。
    - `media_e2e_probe.py:358-364`: 执行 `await page1.set_viewport_size({"width": 800, "height": 600})`，随后检查 `get_page_webrtc_stats` 中 `inboundVideo.frameWidth` 与 `frameHeight`。
    - `entrypoint_stream.sh:31-33`: Selkies 参数配置 `--enable-resize=false --manual-width 1920 --manual-height 1080`，从服务端物理拒绝客户端 resize 请求。
- **判定**: **合格**。两 Tab 共享 Cookie/Cache 但处于不同 DOM 上下文，外部窗口缩放不改变远端 1920x1080 分辨率。

### 2.2 真实 CloakBrowser CDP 验证与并发输入断言

- **源码位点**:
    - `media_e2e_probe.py:230-261`: `query_cdp_dom_input_value()` 通过 `docker exec cbrowser-spike-media-browser python3` 连接容器内 `127.0.0.1:9222/json`，读取 Chrome 内部真实 `#spike-input` 的 `value`。非 Playwright 客户端本地模拟，也非 mock。
    - `media_e2e_probe.py:477-493`: **负例检查**。仅向 Tab 1 发送 3 个字符，断言 CDP 获取到的 DOM 字符串仅含 `'111'` 且 `count("2") == 0`，排除了单 Tab 假冒双端并发的可能。
    - `media_e2e_probe.py:497-515`: **严格计数断言**。Tab 1 输入 `111`，Tab 2 输入 `222`，严格断言 `count_1 == 3 and count_2 == 3 and len(val_pos) == 6 and set(val_pos) == {"1", "2"}`。实际产出 `'121212'` 严丝合缝。
- **判定**: **合格**。完全避免了 mock 与字符丢失掩盖问题。

### 2.3 真实音频流、能量增长与 Mute/Close 隔离

- **源码位点**:
    - `entrypoint_browser.sh:80-99`: 真实 Web Audio API 产生 440Hz 正弦波振荡器 (`osc.frequency.setValueAtTime(440, ...)`)，输出至默认音频链路。
    - `entrypoint_browser.sh:8-11`: 启动 PulseAudio 并通过 `module-native-protocol-unix` 导出至共享 Unix Socket `/tmp/pulse/native`。
    - `entrypoint_stream.sh:34`: Selkies 绑定 `--audio-device-name auto_null.monitor` 捕获该物理混音流并编码 Opus RTP。
    - `media_e2e_probe.py:47-61`: Hook `RTCPeerConnection.track`，将 inbound audio track 挂载到真实的 `<audio autoplay>` 节点，驱动 Chrome 内部 WebRTC 音频解码流水线。
    - `media_e2e_probe.py:434-437, 442-458`: 测量 `inboundAudio.bytesReceived` 和 `inboundAudio.totalAudioEnergy` 4 秒增长。随后将 Tab 1 静音 (`a.muted = true`)，测量 Tab 2 依然以 48,300 bytes 速率增长。
    - `media_e2e_probe.py:693-706`: Tab 1 关闭后，Tab 2 音频继续保持 bytes 与 energy 增长。
- **判定**: **合格**。不存在 mock 音频，确为端到端 PCM->Opus->RTP->Client Decode 全链路。

### 2.4 WebLocks Guard 架构、竞态/死锁与 HELLO 未改写审查

- **源码位点**:
    - `media_e2e_probe.py:67-84`:
        ```javascript
        async function acquireTabWebLock(tabId) {
            if (myCurrentLockedId === tabId) return true;
            const lockName = 'cbrowser_tab_lock_' + tabId;
            return new Promise((resolve) => {
                navigator.locks.request(lockName, { ifAvailable: true }, (lock) => {
                    if (!lock) {
                        resolve(false);
                        return;
                    }
                    myCurrentLockedId = tabId;
                    resolve(true);
                    return new Promise((rel) => { myHeldLockRelease = rel; });
                });
            });
        }
        ```
    - `media_e2e_probe.py:86-114`:
        - 拦截 `WebSocket.send(data)`，当捕获 `data.startsWith('HELLO')` 时，先查询 `sessionStorage.getItem('selkies_tab_id')`。
        - 若获取 lock 失败（`!acquired`）：直接判定为 Tab 碰撞。立即执行 `sessionStorage.setItem('selkies_tab_id', crypto.randomUUID())`，并调用 `this.close(1000, 'tab_collision_remap')`。**未发送被拦截的旧 HELLO**。
        - 若获取 lock 成功：直接执行 `super.send(data)`，不做任何 `JSON.parse` 或修改。
- **竞态、死锁与证据审查**:
    1. **是否存在死锁**:
        - 锁请求采用 `{ ifAvailable: true }`，属于非阻塞探测。若已被持有，立即进入 `if (!lock)` 返回 `false`，绝不排队挂起，彻底消除了两个 Tab 互相争抢导致的死锁隐患。
    2. **是否存在竞态 (Race Condition)**:
        - 锁生命周期通过返回一个未完成的 `Promise ((rel) => { myHeldLockRelease = rel; })` 维持。只要 Tab 页面活着，Lock 保持占用。当页面销毁、关闭或崩溃时，浏览器内核自动释放该 WebLock。
        - 刷新场景下：旧页面卸载时内核释放锁，新页面加载时请求锁立即成功，保留原 ID。
    3. **HELLO Unchanged 证据是否充分**:
        - `media_e2e_probe.py:104-106`: 锁获取成功后，将未经任何改动的原始 `data` 直接推入 `window.__rawForwardedHellos`，并调用 `super.send(data)`。
        - `media_e2e_probe.py:604-609`: 探针读取 Page 3 转发的 HELLO，断言 `all(rh.startswith("HELLO client {") for rh in raw_hellos_p3)`，且 JSON 结构完全保持 Selkies 官方原样。
    4. **CDP Debugger.pause 语义审查**:
        - `media_e2e_probe.py:628-659`: 采用 CDP `Debugger.pause`。
        - **重要技术边界说明**：`Debugger.pause` 仅暂停 V8 JavaScript 线程事件循环，**并非**底层的 Page Lifecycle Freeze（非 OS 级 freeze 或 Chrome Tab Discarding）。
        - **WebLocks 的优势机制**：WebLocks 注册在 Chrome 浏览器内核/RenderProcess 锁管理器中。当 JS 被 `Debugger.pause` 挂起时，原页面的 Lock 依然有效持有在浏览器内核中。新页面（Page 4）加载时调用 `navigator.locks.request(..., { ifAvailable: true })`，由浏览器内核主进程裁定，直接返回 `lock === null`，无需原页面运行 JS 参与协调或广播。因此该测试有效验证了“原页面完全失去响应/无法执行广播事件时，新页面依然能无竞态判定冲突”。
- **判定**: **合格且严谨**。

### 2.5 09/10 NOT_RUN 状态

- **源码位点**:
    - `media_e2e_probe.py:725-736`:
        - `item_09_background_tab`: 标记为 `NOT_RUN`。理由：纯 Selkies 2.1.0 不含 Profile 级 Stream Agent 动态聚合调度器。
        - `item_10_video_no_input_framerate`: 标记为 `NOT_RUN`。理由：纯 Selkies 2.1.0 帧率静态受限于启动参数 (`--framerate 8,8-30`)，动态 8 FPS idle 节流与视频动态覆盖需后续 Stream Agent Activity Aggregator 落地。
    - `media_e2e_probe.py:753-762`: 整体判定逻辑明确要求 `all(s == "NOT_RUN" for s in deferred_statuses)`，最终 Verdict 设为 `VERIFIED_PASS_WITH_NOT_RUN`。
- **判定**: **合格**。未虚报全面完成，准确反映当前阶段真实能力边界。

______________________________________________________________________

## 3. 可复现缺陷、限制与边界分析 (Defects & Limitations)

1. **PulseAudio root 运行告警**:
    - `docker logs cbrowser-spike-media-browser` 产生告警：`W: [pulseaudio] main.c: This program is not intended to be run as root (unless --system is specified).`
    - **影响**: 容器内以 root 启动 pulse 虽功能正常，但在后续正式生产镜像中建议采用专门非 root 运行时用户，或以 `--system` 守护进程参数规范化。
2. **WebLocks 单会话约束**:
    - WebLocks 的作用域为同 Origin (协议+域名+端口)。当前实现 `cbrowser_tab_lock_{tabId}` 有效防范了同 Origin 下的多 Tab 冲突与跨 Tab 复制。若未来用户通过多域名或不同端口访问同一会话，WebLocks 将按 Origin 隔离，需在 Gateway/Ingress 层统一保持 Origin 归一。
3. **Debugger.pause 真实度限定**:
    - 正如审核要点所述，CDP `Debugger.pause` 仅阻断 JS 执行流，网络和浏览器内部 IPC 并未被内核挂起（非 cgroup freeze）。虽然足以证明 WebLocks 依赖浏览器内核状态而非用户空间 JS 心跳，但在未来涉及全系统极度低功耗休眠验证时，需注意该语义区别。

______________________________________________________________________

## 4. 结论 (Verdict)

- **实际执行退出码**: `0`
- **断言状态**:
    - `item_06_two_clients`: **PASS** (1920x1080 锁定，双端持续解码)
    - `item_07_refresh_duplicate_close`: **PASS** (刷新保 ID，复制自动重映射，官方 HELLO 原样转发，首 Tab 关闭不伤次 Tab 与 CloakBrowser)
    - `item_08_concurrent_input`: **PASS** (负例拦截有效，正例 111+222 恰好 6 字符无丢失，经容器 CDP 闭环直读)
    - `item_12_udp_mux`: **PASS** (UDP 30006 端口汇聚验证通过)
    - `item_04_audio_non_silent`: **PASS** (440Hz 真实正弦波，字节与能量双增长，Mute 隔离验证通过)
    - `item_09_background_tab`: **NOT_RUN** (保持阶段现状)
    - `item_10_video_no_input_framerate`: **NOT_RUN** (保持阶段现状)
- **综合评定**: **VERIFIED_PASS_WITH_NOT_RUN**。源码实现无假设与虚标，满足黑盒验证与架构规范要求。
