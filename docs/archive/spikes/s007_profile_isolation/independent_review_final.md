# CBrowser v2 双 Profile 隔离技术 Spike (Revision 5) 独立复核报告

- **复核环境**: Darwin arm64 (OrbStack Docker backend, Linux 内核沙箱)
- **复核模型**: Gemini `cpa/gemini-3.8-flash` (独立五审 Reviewer)
- **复核工作区**: `.scratch/isolation_review_r5`（宿主无 `/tmp` 写入，TMPDIR 严格限定于本 scratch 专有目录，无生产/跟踪代码修改，无外部 agent 交互）
- **测试套件执行**: `python3 run_isolation_probe.py`
  - **实际退出码**: `0` (ExitCode 0)
  - **实测总耗时**: `19.0s`（探针内部计时；宿主 wall-clock `20.3s`）
  - **资源前缀清理**: 自动清理 `cbrowser-spike-isolation-*` 容器、网络与数据卷，复核收尾无任何残留资源
- **复核判定**: **通过 (PASS)**

---

## 一、源文件哈希与重放真实性校验 (Source Hashes & Audit)

本复核在纯净的 `.scratch/isolation_review_r5` 目录下进行，不包含任何历史 `revision_03` 目录或二进制媒体文件。对交付的 9 个核心源码及测试用例执行 SHA256 校验：

| 文件名称 | SHA256 校验和 | 交付状态与说明 |
|---|---|---|
| `browser_runner.py` | `c6aac28d42e2fa11552c247d59c3b84cb2ff38b9df856f94e1fe8c98d257b91d` | 冻结未改动 (Frozen) |
| `entry_browser.sh` | `9afec3073bbdee94fd801bea03b5789dad91aa39ce8ff593cfbab2dbdd8aab93` | 冻结未改动 (Frozen) |
| `entry_stream.sh` | `1d705dfb1cbddc0352ef26b21fbc68289be18f8c3c1ceaab6617627f636a71aa` | 冻结未改动 (Frozen) |
| `run_isolation_probe.py` | `4a79e7a171afcad4bb86aaba67ce9f28821da2e3932183b7b325627984764eef` | R5 根因修复（替换归档二进制依赖为动态失配校准、剔除夸大断言） |
| `audio_analyzer.py` | `a8337f5b446f40659fdd43c0f5a28d1921aaff381c93eb010e4d77937ff06e3b` | 冻结未改动 (Frozen) |
| `test_cross_ipc.py` | `e40f77ba8c98c674c3574b519e31537786e96c500245a1a276d0bb4c95f657a0` | 冻结未改动 (Frozen) |
| `Dockerfile.isolation-browser` | `6609e7f86b2f112f496d78f8a8f5587304829673709ab2039f0291b11eb8e70e` | 冻结未改动 (Frozen) |
| `Dockerfile.isolation-stream` | `28c35f97f417897098264846bb2096d0c93aff705ce179448f519dacfb91d6a4` | 冻结未改动 (Frozen) |
| `fixture/test_mitshm.c` | `7e9cf4dd9bfbaf3b7ecf53f34475832db6240c4e51623a922d174e580c937ba5` | 冻结未改动 (Frozen) |

实测重放套件命令：
```bash
python3 run_isolation_probe.py
```
- **实际返回码**: `0`
- **探针总耗时**: `19.0s`
- **运行日志留存**: `.scratch/isolation_review_r5/reproduce.log`（凭据完全脱敏）
- **产物文件真实哈希**:
  - `recorded_a.raw`: `0dc3bfa5a33cf0580ad0796e3f475143e757057e8d656708cda40fafceeb7c28` (96,000 bytes, S16LE 2ch 48000Hz, 0.5s)
  - `recorded_b.raw`: `698b65a33e6f242a96e56aba0b0a3a490f70c8cf6a6f91e54bf8222f777b8f7c` (96,000 bytes, S16LE 2ch 48000Hz, 0.5s)
  - `screenshot_a.png`: `a0762ff90784e58af3e2e39c03e414e5381a4cded153323096eb727bc55ff528` (1920x1080 渲染图，与 R4 完全字节一致)
  - `screenshot_b.png`: `46dac0cc7a11c9d0d3c0a271461fa28e0a0bc0689a01bea39c7eba938e2d5659` (1920x1080 渲染图，与 R4 完全字节一致)
  - `inspect_topology.json`: `c029fb8f0b8e1612084ce427b2e44f637ca3ee8d5a0ac4d9d9a181c90f9af324`
  - `report.md`: `c80e1239d0b50e811ffa7bb1f42fd6337198046fa5169170ed7136d19ad8f668`

---

## 二、R4 报告缺口与 R5 根因修复审计 (Truthfulness & Gap Fix Audit)

### 1. 历史跳步缺陷与 R5 闭环验证
- **R4 缺陷事实**: R4 中测试脚本使用 `if os.path.exists(hist_pcm_a)` 检测历史缺陷文件 `revision_03/recorded_a.raw`。当仓库遵循“不提交二进制产物”规范清理该文件后，该分支将发生**静默跳步**，而生成的报告却依然无条件宣称“历史缺陷样本被确定性拦截”。
- **R5 修复方案验证**:
  - `run_isolation_probe.py` 彻底移除了对外部 `revision_03/recorded_a.raw` 的依赖与判断逻辑；
  - 采用**动态时钟失配校准机制**：直接使用本轮运行中由 CloakBrowser 实时输出的真值 PCM 产物 `raw_a_host`（48000 Hz, 440 Hz 音频），以错误的采样率（`--rate 44100`）声明并传入 `audio_analyzer.py`，断言期望频率 440.0 Hz 且容差为严苛的 1.0%（`--tolerance 0.01 --expect-fail`）；
  - 实测运行日志确证执行：
    ```text
    + python3 audio_analyzer.py recorded_a.raw 440.0 --rate 44100 --tolerance 0.01 --expect-fail
      [audio_analyzer] File recorded_a.raw: size=96000 bytes, nominal rate=44100Hz
      [audio_analyzer] Measured Autocorrelation Freq : 404.39 Hz
      [audio_analyzer] Measured Zero-Crossing Freq    : 404.54 Hz
      [audio_analyzer] Expected Freq: 440.0 Hz, Tolerance: 1.0% (max err: 4.40 Hz)
      [audio_analyzer] Frequency Error: 35.61 Hz (8.093%)
      [audio_analyzer] NEGATIVE CHECK PASS: Frequency 404.39Hz correctly REJECTED against 440.0Hz (8.09% error > 1.0%).
    Profile A: Rate-mismatch calibration rejected this run's 48000Hz PCM declared as 44100Hz.
    ```
  - `report.md` 真实反映测试事实：明确记录校准状态为 `PASS`，不再谎称执行了历史归档二进制，且实现了纯代码重现，零二进制提交。

### 2. 未证实归因与修饰词修正核对
- **CloakBrowser 反指纹归因修正**: `report.md` 修正为“此前默认配置出现的频率偏差已观察到，但具体内部实现根因未获源码定位”，删除了推论性的反指纹补丁特异因果声称。
- **频率门禁表述规范**: 删除了硬编码的 `<0.1%` 夸大说法，修正为“允许误差 <=1.0%，实际估计值见测量日志”（本次实测误差为 0.035% 与 0.036%）。
- **Xauth 修饰词修正**: 删除了“不可突破 (unbreakable)”这一主观绝对化修饰词，客观表述为“主要防线”。

---

## 三、音频时钟与声学指标严谨复核 (Audio Metrology Audit)

### 1. 时钟一致性与实测指标
全链路在 48000 Hz 原生采样率下运行：
- **Profile A (期望 440.0 Hz)**:
  - 采样帧数: 24,000 (0.500s, 96,000 bytes)
  - RMS 振幅: `9268.2 / 32768` (28.3% 满偏，精确对应 GainNode 0.4)
  - 自相关测得频率: `440.15 Hz`（误差 `0.035%` $\le 1.0\%$）
  - 过零率 (ZCR) 测得频率: `440.31 Hz`
  - 异频串扰检查 (880 Hz): Goertzel 能量比为 `0.000109`（$-39.6\text{ dB}$），远低于 0.01 阈值；高密度 DFT 单频点能量比为 $1.62 \times 10^{-14}$（$-137.9\text{ dB}$）。
- **Profile B (期望 880.0 Hz)**:
  - 采样帧数: 24,000 (0.500s, 96,000 bytes)
  - RMS 振幅: `9268.2 / 32768` (28.3% 满偏)
  - 自相关测得频率: `880.32 Hz`（误差 `0.036%` $\le 1.0\%$）
  - 过零率 (ZCR) 测得频率: `880.22 Hz`
  - 异频串扰检查 (440 Hz): Goertzel 能量比为 `0.000051`（$-42.9\text{ dB}$），远低于 0.01 阈值；高密度 DFT 单频点能量比为 $1.15 \times 10^{-14}$（$-139.4\text{ dB}$）。

### 2. 声学与能量比换算修正说明
- 前序复核曾出现将 $2.5 \times 10^{-7}$ 能量比误写为“<-130 dB”的计算失误（按声学功率定义，$10 \log_{10}(2.5 \times 10^{-7}) \approx -66.0\text{ dB}$，而非 $-130\text{ dB}$）。
- 本复核严格遵循物理与数学标准：直接援引 `audio_analyzer.py` 内部基于 Goertzel 算法实测的真实能量比（`0.000109` 与 `0.000051`），不再引入未经验证的错误单位换算。

---

## 四、安全基准与多 Profile 隔离断言交叉审计 (Security Audit)

主拓扑与诊断探针验证的全部安全断言保持成立且与 R4 完全一致：

1. **容器基线安全**:
   - 4 容器全部在 `1000:1000` 非 root 身份下运行；
   - 全部声明 `ReadonlyRootfs: true` 与 `no-new-privileges: true`；
   - 端口映射 `PortBindings` 为空，CDP 严格绑定容器本地 `127.0.0.1:9222`；Xvfb `-nolisten tcp` 彻底关闭网络监听。
2. **PulseAudio 安全与防线退守**:
   - N3/N4 证实：跨 UID (1001) 携带错误或空 Cookie 访问 PulseAudio 时被内核/协议层强制拒绝（`Access denied`，Exit 1）；
   - OBS-Pulse 证实：同 UID (1000) 访问 PulseAudio 时服务端跳过 Cookie 校验；多 Profile 隔离真实依靠独立 Docker Volume（`cbrowser-spike-isolation-a/b-pulse`）进行隔离。
3. **X11 认证与跨 IPC 隔离**:
   - N1/N2 证实：错误 Cookie 导致 `Invalid MIT-MAGIC-COOKIE-1 key`，无 Cookie 导致 `Authorization required`；
   - N5 (Cross-IPC 8a/8b/8c) 证实：跨 IPC 命名空间连接 X11 时，基础协议虽然能认证成功，但底层 MIT-SHM 扩展强制拒绝并抛出 `BadAccess (error=10)`，Pixelflux 捕获阶段明确报错拦截。
4. **数据卷隔离**:
   - 哨兵文件互不可达（Profile A 无法读 `sentinel-b.txt`，Profile B 无法读 `sentinel-a.txt`）；
   - Stream 容器不挂载用户数据卷 `/data/profile`。

---

## 五、生产准入边界说明 (Production Non-Bypass)

1. **测试证明的真实技术范围**:
   - 验证了单机 Linux 容器沙箱内 CloakBrowser WebAudio 与 48000 Hz 原生 PulseAudio 虚拟链路的时钟一致性与 1.0% 音高门禁；
   - 验证了非 root、只读 rootfs、独立 Volume、独立 IPC 的多 Profile 边界隔离。
2. **生产质量全 17 门禁保持约束**:
   - 本测试属于单机沙箱隔离 spike，绝不代表 WebRTC 生产链路就绪；
   - 生产环境仍必须完整打通 ICE/STUN/TURN NAT 穿透、Opus 编码、生产 Caddy 网关以及动态生命周期管理等全 17 项生产质量门禁；
   - CBrowser 架构始终坚持单沙箱多容器动态生命周期，杜绝独占租约设计。

---

## 六、复核结论

- **执行指令**: `python3 run_isolation_probe.py`
- **实际退出码**: `0` (ExitCode 0)
- **实际总耗时**: `19.0s`
- **残留资源**: `0` (所有容器、网络与挂载卷完全自动清理)
- **判定结果**: **通过 (PASS)**

R5 版本彻底修复了 R4 中因缺失历史二进制导致的静默跳步缺陷，以本轮真值 PCM 动态失配校准实现了 100% 可重现、绝不跳步的负例门禁；剔除了夸大与未证实的物理因果归因；全量功能、音质与安全基准保持真实成立。
