# CBrowser v2 双 Profile 隔离技术 Spike (Revision 4) 独立复核报告

- **复核环境**: Darwin arm64 (OrbStack Docker backend, Linux 内核沙箱)
- **复核模型**: Gemini `cpa/gemini-3.8-flash` (独立四审 Reviewer)
- **复核工作区**: `.scratch/isolation_review_r4`（宿主无 `/tmp` 写入，无生产/跟踪代码修改，无外部 agent 交互，临时路径限定本 scratch/tmp）
- **测试套件执行**: `python3 run_isolation_probe.py`
  - **实际退出码**: `0` (ExitCode 0)
  - **实测总耗时**: `19.1s`
  - **资源前缀清理**: 严格仅清理 `cbrowser-spike-isolation-*` 容器、网络与挂载卷，复核收尾无任何残留资源
- **复核判定**: **通过 (PASS)**

---

## 一、源文件哈希与重放真实性校验 (Hash Replay & Audit)

本复核严格基于 `.scratch/isolation_review_r4` 内冻结的 8 个交付源码文件与报告文件，执行独立 SHA256 计算与校验：

| 文件名称 | SHA256 校验和 | 交付状态 |
|---|---|---|
| `browser_runner.py` | `c6aac28d42e2fa11552c247d59c3b84cb2ff38b9df856f94e1fe8c98d257b91d` | 冻结未改动 (Frozen) |
| `entry_browser.sh` | `9afec3073bbdee94fd801bea03b5789dad91aa39ce8ff593cfbab2dbdd8aab93` | 冻结未改动 (Frozen) |
| `entry_stream.sh` | `1d705dfb1cbddc0352ef26b21fbc68289be18f8c3c1ceaab6617627f636a71aa` | 冻结未改动 (Frozen) |
| `run_isolation_probe.py` | `3303fbf4d69435fb04f86f76e7b3825b005c49c8d3604b3e85bb8b2896e0b573` | 冻结未改动 (Frozen) |
| `audio_analyzer.py` | `a8337f5b446f40659fdd43c0f5a28d1921aaff381c93eb010e4d77937ff06e3b` | 冻结未改动 (Frozen) |
| `test_cross_ipc.py` | `e40f77ba8c98c674c3574b519e31537786e96c500245a1a276d0bb4c95f657a0` | 冻结未改动 (Frozen) |
| `Dockerfile.isolation-browser` | `6609e7f86b2f112f496d78f8a8f5587304829673709ab2039f0291b11eb8e70e` | 冻结未改动 (Frozen) |
| `Dockerfile.isolation-stream` | `28c35f97f417897098264846bb2096d0c93aff705ce179448f519dacfb91d6a4` | 冻结未改动 (Frozen) |
| `fixture/test_mitshm.c` | `7e9cf4dd9bfbaf3b7ecf53f34475832db6240c4e51623a922d174e580c937ba5` | 冻结未改动 (Frozen) |
| `revision_03/recorded_a.raw` | `0c4a500b17c063037f44622696c666eae81e5e070d26c728a67787266a0f4a60` | 历史真实负例 (仅供复核) |
| `revision_03/recorded_b.raw` | `87219adf1147a24ed6a37639806fb43a35c15771837a8ac1bb2eb8e1271a775e` | 历史真实负例 (仅供复核) |

实测重放套件命令：
```bash
python3 run_isolation_probe.py
```
- **实际返回码**: `0`
- **实际执行总耗时**: `19.1s`
- **运行日志留存**: `.scratch/isolation_review_r4/reproduce.log`（日志中凭据已完全脱敏）
- **产物文件真实哈希**:
  - `recorded_a.raw`: `c373bad3ec0cb98499ea7eb886d994ec7e4b6eb42fd684e05235d78d2c4e2aa9` (96,000 bytes, S16LE 2ch 48000Hz, 0.5s)
  - `recorded_b.raw`: `06c02c4aefeb312fb780130d8044738c4e05c0970b5c0ed34181e72d2ffc1443` (96,000 bytes, S16LE 2ch 48000Hz, 0.5s)
  - `screenshot_a.png`: `a0762ff90784e58af3e2e39c03e414e5381a4cded153323096eb727bc55ff528` (1920x1080 渲染图)
  - `screenshot_b.png`: `46dac0cc7a11c9d0d3c0a271461fa28e0a0bc0689a01bea39c7eba938e2d5659` (1920x1080 渲染图)

---

## 二、音频时钟失配与物理重采样根因辨析 (Physics of Pitch & Resampling)

### 1. 对 R3 “重采样改变物理音高” 错误推论的技术澄清与否决
- **核心声学原理**: 标准的带时间插值的重采样（Resampling with sample-rate conversion, 如 sinc 插值或线性插值）**绝不改变物理播放的基频与音高**。440 Hz 的正弦波在 48000 Hz 采样下每秒有 440 个完整周期；经过正确重采样转为 44100 Hz 后，虽然每秒采样的点数从 48000 变为了 44100，但在以 44100 Hz 时钟播放时，其每秒依然输出 440 个完整正弦周期，物理音高恒定为 440 Hz。
- **历史 R3 测得 404.25 Hz / 808.5 Hz 的真实物理原因**:
  - 此前 R3 中并非发生了“正确的重采样改变了音高”，而是发生了**跨时钟无重采样的原始数据直通（Direct Sample Rate Mismatch / Headerless Interpretation Mismatch）**；
  - 当音频发生端以 48000 Hz 生产样本，而接收端（GStreamer / 测量器）在缺少重采样插件的情况下将该数据帧率直接声明/当作 44100 Hz 读取时：
    $$\text{Measured Frequency} = 440.0 \times \frac{44100}{48000} = 404.25 \text{ Hz}$$
    $$\text{Measured Frequency} = 880.0 \times \frac{44100}{48000} = 808.50 \text{ Hz}$$
  - **结论**: 必须明确否决“重采样改变物理音高”的伪科学解释。R3 测得 404 Hz 的物理本质是时钟不对齐导致的播放速度放慢 8.16%（下调 147 cents），而非重采样算法本身改变音高。

### 2. CloakBrowser 与 48000 Hz 的精确归因审查
- **审查结论**: **已知强关联（Known Association），非因果唯一性证明（Not Confirmed Single Root Cause）**。
- **实测证据**:
  - 在 PulseAudio 默认 44100 Hz 的运行环境中实测，CloakBrowser 启动后的 `window.AudioContext.sampleRate` 确为 `48000`；
  - 经由 PulseAudio Native 协议连接时，Chromium 向 PulseAudio 汇报的客户端音频流 `Sink Input` 规范确实为 `Sample Specification: float32le 2ch 48000Hz`；
  - 但是，现代 Chromium（以及大多 Linux 发行版下的 WebAudio 实现）在底层连接 PulseAudio / ALSA 时，若底层硬件或默认策略倾向 48000 Hz，其 AudioContext 默认构造通常固定为 48000 Hz；
  - 因此，“AudioContext 锁定 48000 Hz 是由 CloakBrowser 隐私反指纹补丁特异性修改引起”属于**已知强关联**，尚缺乏对 CloakBrowser 源码补丁的逆向唯一因果定性证据。在技术文档中应表述为“CloakBrowser WebAudio 在该 Linux 环境下固定输出 48000 Hz 采样时钟”，而不宜武断声称仅为反指纹补丁所致。

---

## 三、真实音频时钟与链路物理验证 (Ground Truth Audio Verification)

### 1. PulseAudio 服务端与 GStreamer 协商真实 Caps 深度检验
为了排除仅在前端或 CLI 欺骗（Spoofed properties）的可能性，本复核对运行中的容器内部音频服务状态执行了底层拓扑与协议协商探查：

1. **PulseAudio Daemon 与 Sink 状态 (`pactl info` & `pactl list sinks`)**:
   ```text
   Server Name: pulseaudio 17.0
   Default Sample Specification: s16le 2ch 48000Hz
   Default Sink: cbrowser_sink
   Default Source: cbrowser_sink.monitor
   
   Sink #0
       Name: cbrowser_sink
       Description: CBrowser_Virtual_Sink
       Sample Specification: s16le 2ch 48000Hz
       State: RUNNING
   ```
2. **浏览器音频流挂载真实状态 (`pactl list sink-inputs`)**:
   ```text
   Sink Input #0
       Driver: protocol-native.c
       Client: Chromium (process.binary = "chrome", process.user = "cbrowser")
       Sample Specification: float32le 2ch 48000Hz
       Resample method: copy
   ```
   **关键物理证据**: `Resample method: copy`。这证明因为 PulseAudio 服务端已原生配置为 48000 Hz，浏览器直出的 48000 Hz 音频流在 PulseAudio 内部无需任何重采样插值，以零失真原生拷贝进入 `cbrowser_sink`。
3. **GStreamer 录制管道动态协商 Caps (`gst-launch-1.0 -v`)**:
   ```text
   /GstPipeline:pipeline0/GstPulseSrc:pulsesrc0.GstPad:src:
       caps = audio/x-raw, format=(string)S16LE, layout=(string)interleaved, rate=(int)48000, channels=(int)2
   ```
   全链路（Browser WebAudio $\rightarrow$ Pulse Native Protocol $\rightarrow$ Virtual Null Sink $\rightarrow$ GStreamer pulsesrc $\rightarrow$ filesink）真实在 **48000 Hz 原生采样率** 下完成握手与录制。

### 2. 独立纯数学基频测量 (Independent DFT & Zero-Crossing)
复核人使用完全独立的数学工具（独立编写纯 Python DFT 频谱分析与过零率，不依赖交付包的估算逻辑），对产物 `recorded_a.raw` 与 `recorded_b.raw` 进行分析：

- **基准时钟声明**: 48,000 Hz, S16LE, 立体声。
- **Profile A (期望 440.0 Hz)**:
  - 总采样点数: 24,000 帧 (0.500 秒，96,000 字节)
  - RMS 振幅: `9268.2 / 32768` (28.28% 满偏，精确对应 GainNode 0.4: $32767 \times 0.4 \times \frac{1}{\sqrt{2}} \approx 9268$)
  - 独立微积分过零率 (ZCR): `440.73 Hz`
  - 独立归一化自相关 (Autocorr): `440.33 Hz`
  - 独立高密度离散傅里叶变换 (DFT Peak): `440.00 Hz`
  - 物理频率绝对误差: `0.00 Hz ~ 0.33 Hz` (相对误差 **0.075%**，严苛满足 1.0% 门禁)
  - 串扰分析: 880 Hz 能量相对 440 Hz 衰减比为 $2.54 \times 10^{-7}$ (<-130 dB)，无 Profile B 串扰。

- **Profile B (期望 880.0 Hz)**:
  - 总采样点数: 24,000 帧 (0.500 秒，96,000 字节)
  - RMS 振幅: `9268.2 / 32768` (28.28% 满偏)
  - 独立微积分过零率 (ZCR): `880.73 Hz`
  - 独立归一化自相关 (Autocorr): `880.25 Hz`
  - 独立高密度离散傅里叶变换 (DFT Peak): `880.00 Hz`
  - 物理频率绝对误差: `0.00 Hz ~ 0.25 Hz` (相对误差 **0.028%**，严苛满足 1.0% 门禁)
  - 串扰分析: 440 Hz 能量相对 880 Hz 衰减比为 $2.76 \times 10^{-7}$ (<-130 dB)，无 Profile A 串扰。

---

## 四、标定负例与测量验证器全量校验 (Calibration & Negative Gates)

为防止测量工具本身存在“死循环硬编码”、“无论输入何值均返回期望值”的假阳性漏洞，复核人在当前环境中合成了 5 组纯校验用途的合成 PCM 样本（在测试后立即清除，绝不作为媒体证明提交）：

| 标定样本测试用例 | 输入特征 | 预期行为 | 测量器实测表现 | 判定 |
|---|---|---|---|---|
| **C1: 标准合成 440Hz** | 48kHz, 正弦 440Hz, gain 0.4 | 1% 门禁正向通过 | Autocorr: 440.60 Hz (误差 0.136% <= 1%) | **PASS** |
| **C2: 物理错音高 (404.25Hz)** | 48kHz, 正弦 404.25Hz | 1% 门禁确定性拦截 | 捕获 404.76 Hz (误差 8.01% > 1%) 抛出 AssertionError | **PASS (拦截成功)** |
| **C3: 全零静音样本** | 48kHz, 0.5s 全 0x00 字节 | 拒绝无信号 | 检出 Non-zero: 0.0% 抛出 AssertionError | **PASS (拦截成功)** |
| **C4: 混频串扰样本** | 440Hz 与 880Hz 各 50% 混频 | 检出异频失真 | ZCR 与 Autocorr 偏离 99.97% 抛出 AssertionError | **PASS (拦截成功)** |
| **C5: 错误采样率声明** | 48kHz 440Hz 样本以 44100 声明 | 检出时钟偏离 | 测得 404.80 Hz 抛出 AssertionError | **PASS (拦截成功)** |

此外，针对 Revision 3 的历史真实缺陷文件 `revision_03/recorded_a.raw`（22050 帧，44.1kHz 录制）：
- 在 `run_isolation_probe.py` 阶段 4 运行 `--expect-fail` 时，正确测量出其实际音高为 404.76 Hz（相对 440Hz 误差 8.01%），被 1% 严苛门禁确定性拦截拒绝（PASS）。

---

## 五、历史条件跳步与真实性审计缺陷报告 (Reproducibility & Truthfulness Gap)

在代码审查与历史产物比对中，复核人发现了一项关键的可重现性与真实性缺陷：

### 1. 缺陷现象定位
在 `run_isolation_probe.py` 第 458-466 行：
```python
# 7c. Negative check 2: Historical failing evidence (revision_03/recorded_a.raw with 8.2% pitch error must fail under 1% tolerance)
hist_pcm_a = os.path.join(SCRATCH_DIR, "revision_03", "recorded_a.raw")
if os.path.exists(hist_pcm_a):
    neg_hist_a = run_cmd([...])
```
- **问题**: 测试脚本对 `revision_03/recorded_a.raw` 的存在性进行了 `if os.path.exists()` 保护。若该二进制文件不存在，代码将**静默跳过**该测试；
- **真实性缺口**: 报告 `report.md` 第 3.1 节却无条件声称：*“负例门禁验证: 异频（880Hz）断言及历史 404Hz 缺陷样本均被 1% 门禁确定性拦截（PASS）”*。
- **架构冲突**: 二进制产物（raw PCM）不属于且严禁进入版本控制代码仓库（遵循 repo 规范：不提交二进制运行产物）；若未来清理了 `.scratch` 历史产物，该测试将被静默跳过，但生成的报告仍宣称其已执行。

### 2. 最小改动修复建议 (Proposed Minimal Fix - No Binary Commit)
**方案**: 严禁提交历史二进制 raw 文件到 git 仓库。改在测试运行期由 `audio_analyzer.py` 或测试前置根据数学公式在内存/临时目录动态合成一段代表 404.25 Hz（440Hz 在 44.1kHz 时钟下失配速度）的合成负例 PCM 样本进行门禁拒绝校验：
```python
# Minimal Fix for Reproducibility: Synthetic wrong-pitch fixture generated dynamically
def generate_pitch_negative_fixture(tmp_path: str, freq: float = 404.25, sample_rate: int = 48000, duration: float = 0.5):
    import struct, math
    num_samples = int(sample_rate * duration)
    with open(tmp_path, "wb") as f:
        for i in range(num_samples):
            val = int(13107 * math.sin(2 * math.pi * freq * i / sample_rate))
            f.write(struct.pack("<hh", val, val))
```
使用动态合成负例替代对历史文件系统路径的硬依赖，既满足了纯净代码仓不含二进制产物的要求，又确保了负例测试在任何全新克隆环境下 100% 可重现、绝不跳步。

---

## 六、全量安全基准与多 Profile 隔离断言审计

复核人对历次评审建立的核心安全基准进行了逐项交叉比对：

1. **全链路非 Root 与只读根文件系统**:
   - `cbrowser-spike-isolation-browser-a/b` 与 `cbrowser-spike-isolation-stream-a/b` 4 个容器运行时显式声明并运行在 `Config.User: 1000:1000`；
   - 4 容器全部开启 `HostConfig.ReadonlyRootfs: true` 与 `no-new-privileges: true`；
   - 可写区域严格限定在内存 tmpfs (`/tmp:rw,exec,nosuid,nodev,size=512m`)、`/dev/shm` (1GiB) 及专有数据卷。
2. **PulseAudio 同 UID 自动放行机制与防线退守**:
   - 探针以 UID 1001 持错误 Cookie 或空 Cookie 访问 Profile B Pulse Socket 时，均被强制拒绝并抛出 `Access denied`（退出码 1，N3/N4 通过）；
   - 探针以同 UID (1000) 持错误 Cookie 访问 Profile B 时，由于 PulseAudio `module-native-protocol-unix` 底层机制，确实自动免密放行；
   - **防线退守验证**: 报告和测试真实反映了该机制。生产多 Profile 隔离绝不依赖 Pulse Cookie，而是严格依靠 Docker Volume 隔离（Profile A 仅挂载 `cbrowser-spike-isolation-a-pulse`，无法在文件系统层触达 Profile B 的 Socket）。
3. **X11 认证与跨 IPC MIT-SHM 正交隔离**:
   - 探针持错误 Cookie 连接 X11 抛出 `Invalid MIT-MAGIC-COOKIE-1 key`（N1 通过）；无 Cookie 抛出 `Authorization required`（N2 通过）；
   - 探针持 Profile A 正确 Cookie 在 Profile B IPC 空间中连接 `:91`：X11 协议成功连接（`1920x1080 pixels`），但底层 `XShmAttach` 捕获 `BadAccess (error=10)`，Pixelflux 捕获 `X11Error Access (error_code: 10)`；
   - **防窥防线澄清**: IPC 隔离仅阻断共享内存零拷贝；物理防窥的第一道防线仍为 Xauthority Cookie 与 UNIX Socket 卷隔离。
4. **网络与 CDP 回环隔离**:
   - `/proc/net/tcp` 证实 CDP 严格监听在 `127.0.0.1:9222`（十六进制 `0100007F:2406`）；
   - Xvfb 端口 6091/6092 在内核监听列表中完全不存在（`-nolisten tcp` 生效）；
   - Browser A 向 Browser B（`cbrowser-profile-b:9222`）跨容器发起 TCP 握手直接被内核拒绝（`ConnectionRefusedError`）。
5. **持久化数据隔离**:
   - Browser A 与 Browser B 的 Profile 卷完全独立，哨兵文件互不可读；
   - Stream A 与 Stream B 挂载点经 `docker inspect` 审计，绝不包含 `/data/profile`。

---

## 七、架构定位与生产准入边界声明 (Production Gateway Boundaries)

1. **测试证明的真实技术范围**:
   - 本测试证实了在单机 Linux 容器沙箱内，CloakBrowser WebAudio 可以与 48000 Hz 原生 PulseAudio Virtual Sink 对齐时钟，在 1.0% 音高容差下提供高保真音频输出；
   - 证实了 4 容器在非 root、只读 rootfs、独立 Volume、独立 IPC 下的安全边界有效性。
2. **生产准入边界强调 (Production Non-Bypass)**:
   - **原始 PCM 采集绝不等于 WebRTC 生产管道就绪**: 生产客户端依赖 WebRTC 实时音视频流、ICE/STUN/TURN NAT 中继、动态带宽自适应与 Opus 编码传输（由后续 `s004` 等 spike 验证）；
   - **全 17 门禁保持约束**: 本隔离验证不能豁免公网 TLS、Caddy 反向代理网关编排、动态生命周期监控等全 17 项生产质量门禁；
   - **无租约架构**: CBrowser v2 始终保持单沙箱多容器动态生命周期，杜绝独占租约设计。

---

## 八、复核结论

- **执行指令**: `python3 run_isolation_probe.py`
- **实际退出码**: `0` (ExitCode 0)
- **实际总耗时**: `19.1s`
- **残留资源**: `0` (所有容器、网桥与临时数据卷均在 finally 块完成清理)
- **判定结果**: **通过 (PASS)**。

测试完整证实了 48000 Hz 物理时钟对齐下的真实音频输出，否决了“重采样改变物理音高”的错误假说；1% 门禁经过了真实负例和合成标定样本的全面检验；各层容器安全基准与隔离断言保持严谨成立。针对报告中历史二进制负例的静默跳步风险，已给出无需提交二进制资产的最小动态生成修复方案。
