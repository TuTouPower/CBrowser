# CBrowser v2 双 Profile 隔离技术 Spike (Revision 3) 独立复核报告

- **复核环境**: Darwin arm64 (OrbStack Docker backend, Linux 内核沙箱)
- **复核模型**: Gemini `cpa/gemini-3.8-flash` (独立三审 Reviewer)
- **复核工作区**: `.scratch/isolation_review_v3`（宿主无 `/tmp` 写入，无生产/跟踪文件修改，无跨 worktree，临时路径限定本 scratch/tmp）
- **测试套件执行**: `python3 run_isolation_probe.py`
  - **实际退出码**: `0` (ExitCode 0)
  - **实测总耗时**: `17.6s`（作者先前 21.8s 经 logging 变更后重新实机重放）
  - **资源前缀清理**: 严格限定清理 `cbrowser-spike-isolation-*` 容器、网络与挂载卷，复核收尾无任何残留资源

---

## 一、源文件哈希与重放真实性校验 (Hash Replay & Audit)

由于在 Revision 3 作者测试通过（21.8s）后，主控将 `browser_runner.py` 内的 `print()` 输出重构为标准 `logging`（导致源码 SHA256 发生变化），本复核独立重新计算全部源码实际哈希，并执行全量实机重放：

| 文件名称 | 报告记录哈希 (作者预先) | 实际计算哈希 (复核前/后) | 一致性与重放状态 |
|---|---|---|---|
| `browser_runner.py` | `339e9fff2b8e5bff...` | `c6aac28d42e2fa11552c247d59c3b84cb2ff38b9df856f94e1fe8c98d257b91d` | **经 logging 改动重放更新** |
| `entry_browser.sh` | `6716f0e266f7d387...` | `6716f0e266f7d3870ab91bf767831fe1907eeae28b964e92248afac7621e84c1` | **精确一致** |
| `entry_stream.sh` | `1d705dfb1cbddc03...` | `1d705dfb1cbddc0352ef26b21fbc68289be18f8c3c1ceaab6617627f636a71aa` | **精确一致** |
| `run_isolation_probe.py` | `ced69e321c5a5fcd...` | `ced69e321c5a5fcd44a3e0de5ce4e0d512de9ed29491d77ce406437ff7eb9f7c` | **精确一致** |
| `audio_analyzer.py` | `c7507eab1c0fbe44...` | `c7507eab1c0fbe44e65b5939d8bc3ef9b30035c701372af0f9e142ebca0863e2` | **精确一致** |
| `test_cross_ipc.py` | `e40f77ba8c98c674...` | `e40f77ba8c98c674c3574b519e31537786e96c500245a1a276d0bb4c95f657a0` | **精确一致** |

实测重放后，`run_isolation_probe.py` 自动在收尾时重新计算并覆写 `report.md`，报告第 9.1 节当前哈希与实际哈希 100% 吻合，执行耗时更新为 `17.6s`。

---

## 二、Revision 3 核心改动核查：真实浏览器 WebAudio 替换 paplay

| 核查维度 | 历史状态 (R2) | R3 现行实现与证据 | 独立技术判定 |
|---|---|---|---|
| **音频发生源** | 后台 `paplay` 循环将外部生成的 WAV 写入 `cbrowser_sink`（绕过浏览器沙箱） | `browser_runner.py`（第 116-147 行）：彻底移除 `generate_wav` 与 `paplay` 进程；启动参数增加 `--autoplay-policy=no-user-gesture-required`；通过 DOM 执行注入 `window.AudioContext`，创建 `OscillatorNode`（A=440Hz, B=880Hz）与 `GainNode`（gain=0.4），并断言 `AudioContext.state == 'running'` | **真实 WebAudio 驱动** |
| **残存伪阳性排除** | 存在脱离浏览器执行音频播放的风险 | 扫描整个运行环境与脚本，无任何后台 `paplay` 进程运行；DOM metrics 返回 `audioSource: "CloakBrowser WebAudio OscillatorNode"`，`audioSampleRate: 48000` | **伪阳性彻底杜绝** |
| **画面视听协同证据** | 静态截图无法反证音频运行 | 多模态读取 `screenshot_a.png` 与 `screenshot_b.png`：Chrome 标签页标题栏均显示**系统原生正在发声的扬声器（Speaker）小图标**，证实 Chromium 内部音频流水线已完全激活 | **UI 与音频强相关证实** |
| **PCM 振幅采样物理证据** | R2 固定 0.8 振幅 (max ~26213) | R3 实测 `recorded_a.raw` 与 `recorded_b.raw` 最大 PCM 振幅为 `13107`，精确对应 16-bit 满偏幅度乘以 GainNode `0.4` (`32767 * 0.4 = 13106.8`) | **完全对应 WebAudio Gain 0.4** |
| **PCM 频域与串扰分析** | 过零率基频估算 | 采样率 44.1kHz 录制下，实测 DFT 能量峰值分别为 `404 Hz` 与 `808 Hz`，精确对应浏览器 48kHz 时钟重采样至 44.1kHz（`440 * 44100 / 48000 = 404.25 Hz`；`880 * 44100 / 48000 = 808.5 Hz`）；A/B 交叉能量抑制比超过 `41 dB`（>120倍差异），无跨 Profile 串扰 | **高保真隔离验证** |

---

## 三、关键安全机制与隔离边界独立审计

### 1. PulseAudio 同 UID 自动放行机制与真正防线
- **底层行为验证**:
  - **负例 N3/N4 (UID 1001)**: 诊断探针以 UID 1001（镜像 streamuser 身份）持错误或无 Cookie 访问 Profile B 的 `pulse.sock` 时，PulseAudio 均显式返回 `Connection failure: Access denied`（退出码 1），验证了非同 UID 的严格鉴权。
  - **对照 OBS-Pulse (UID 1000)**: 探针以与服务端相同 UID (1000) 访问 Profile B 的 `pulse.sock` 时，即使注入错误的 Profile A Cookie，`pactl info` 仍以退出码 0 成功返回服务端信息。
- **报告与架构定性核查**:
  - `report.md` 第 6.1 节与第 9.2 节实事求是地记录了 PulseAudio `module-native-protocol-unix` 对同 UID 免密信任的特性，并明确强调：**PulseAudio Cookie 绝不是跨 Profile 防线**；
  - **真正的隔离防线是 Docker Volume 物理隔离与 Linux 文件系统 DAC**。主拓扑中 Profile A 仅挂载 `cbrowser-spike-isolation-a-pulse`，对 Profile B 的 socket 路径在文件系统层完全不可见。

### 2. X11 鉴权与跨 IPC MIT-SHM 正交隔离边界
- **底层行为验证**:
  - **负例 N1/N2**: 错误 Xauthority Cookie 触发 `Invalid MIT-MAGIC-COOKIE-1 key`（退出码 1）；无 Cookie 触发 `Authorization required, but no authorization protocol specified`（退出码 1）。
  - **跨 IPC 探针 (Sub-test 8a/8b/8c)**:
    - 8a: 持有 Profile A 正确 Cookie 在 Profile B IPC 空间中连接 `:91`，X11 协议握手成功，`xdpyinfo` 正常返回 `1920x1080 pixels`；
    - 8b: `test_mitshm --expect-shm-denied` 显式捕获 `BadAccess (error=10)`；
    - 8c: `pixelflux` 调用 `ScreenCapture.start_capture` 捕获 `X11Error Access (error_code: 10)`。
- **报告与架构定性核查**:
  - `report.md` 第 6.2 节与第 9.2 节明确指出：**跨 IPC 仅使得基于共享内存段（MIT-SHM）的零拷贝抓图失败，并不等同于阻断所有画面读取**；如果攻击者获得合法 Cookie 且能访问 UNIX Socket，仍可通过标准网络流（`XGetImage`）读取像素；
  - 画面防窥的第一道绝对防线是 **Xauthority 随机 32 位 Hex Cookie 认证** 与 **/tmp/.X11-unix 独立卷隔离**，IPC 隔离仅作为性能优化段的纵深防御。报告未作绝对化误导声明。

### 3. 主拓扑全容器加固与网络隔离证据
基于 `inspect_topology.json` 与内核网络栈 `/proc/net/tcp` 的独立比对：
- **全链路非 root**: 4 个容器（Browser A/B, Stream A/B）运行时 `Config.User` 均为 `1000:1000`。
- **只读根文件系统**: 4 个容器全部声明 `HostConfig.ReadonlyRootfs: true`，写操作仅限内存 tmpfs (`/tmp`, `/dev/shm`) 及专有数据卷。
- **无提权与无敏感挂载**: 全部具备 `no-new-privileges: true`；无任何容器挂载 `/var/run/docker.sock`；Stream 容器挂载列表中完全排除 `/data/profile`。
- **网络与端口审计**:
  - `PortBindings` 严格为空 `{}`；
  - `/proc/net/tcp` 证实 CDP 严格绑定 `127.0.0.1:9222`（`0100007F:2406`），无公网监听；
  - Xvfb 端口 6091/6092 在内核监听表中完全缺席，证实 `-nolisten tcp` 物理生效；
  - Browser A 向 Browser B（`cbrowser-profile-b:9222`）跨容器发起的 TCP 握手返回 `ConnectionRefusedError`。

---

## 四、渲染质量与日志脱敏复核 (Visual & Secret Masking)

1. **真实 UI 渲染复核**:
   - `screenshot_a.png` (深蓝主题 `#102040`, Profile Identifier `A`, 标题 `CBrowser Cloak Profile A 1080p`)；
   - `screenshot_b.png` (深红棕主题 `#402010`, Profile Identifier `B`, 标题 `CBrowser Cloak Profile B 1080p`)；
   - 两张截图均为真实 Chromium 1080p 窗口，非白屏、非透明，背景主色匹配率 >67%，非白色像素占比 >88%，DOM 与截图色彩高度吻合。
2. **凭据安全与日志脱敏**:
   - `reproduce.log` 中所有 32 位及以上十六进制 Cookie、容器 64 位 SHA256 ID、镜像 Digest 均被精准脱敏为 `[REDACTED_COOKIE_HEX]`；无任何私钥、Cookie 明文泄露。

---

## 五、架构定位与生产准入边界说明 (Scoped Technical Verdict)

1. **技术范围**: 本次 Spike 仅在单机 Docker 模拟环境（Xvfb / PulseAudio 虚拟声卡）下验证了 Linux 容器内核层（UID、只读 rootfs、IPC 隔离、卷隔离、网络端口）的安全隔离边界。
2. **非生产冻结**:
   - 原始 PCM 采样与虚拟声卡验证**绝不等于 WebRTC 生产端到端媒体管道已就绪**（WebRTC 音画流传输、STUN/TURN NAT 穿透由 `s004` spike 单独验证）；
   - 本技术验证通过**不豁免 CBrowser 全 17 项生产门禁**；
   - 系统采用独立沙箱容器与动态生命周期，无独占租约机制。

---

## 六、复核结论

- **执行命令**: `python3 run_isolation_probe.py`
- **实际退出码**: `0`
- **实际总耗时**: `17.6s`
- **残留资源**: `0` (所有容器、网络、卷均已按规范清理完毕)

本次 Revision 3 成功将音频输入源从外部 `paplay` 切换为真实浏览器沙箱内 `WebAudio AudioContext (440Hz / 880Hz)`，排除了伪阳性，真实 UI 与 PCM 频域分析协同吻合；哈希重放吻合；报告对 PulseAudio 同 UID 旁路和 X11 画面防窥边界的定性诚实严谨，无夸大或跳步断言。

Spike 双 Profile 隔离技术复核判定为: **通过 (PASS)**。
