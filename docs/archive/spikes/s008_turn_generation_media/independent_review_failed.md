# 审查报告：Stage 2 真实 TURN / Chrome 媒体与 ICE 重启复核

**审查结论：FAIL（存在严重假绿风险与多项未覆盖缺陷）**  
**重跑真实套件状态：PASS（但断言逻辑存在致命缺陷，见对抗验证）**  
**审核员：独立评审 Agent (opencode / Gemini cpa/gemini-3.8-flash)**  
**日期：2026-10-27**  

---

## 1. 实际命令执行记录与 Exit Code

本次复核严格在 `.scratch/turn_media_review` 宿主目录内执行，未越界访问宿主 `/tmp`，未跨 worktree，未改动冻结代码，TMPDIR 限制为 `./tmp`。

| 步骤 | 执行命令 | 退出码 (Exit Code) | 真实耗时 | 核心观察 |
|---|---|---|---|---|
| 1 | `bash probe_work/start_coturn.sh` | 0 | ~2s | 启动 `cbrowser-spike-turn-coturn`，生成 private 0600 secret，绑定 172.29.0.10:3478 及 UDP 40000-40020 |
| 2 | `bash stage2_containers.sh` | 0 | ~1s | 启动 `cbrowser-spike-turn-browser` 与 `cbrowser-spike-turn-stream` (挂载 X11/Pulse/probe 目录) |
| 3 | `uv run --no-project --with playwright --with websockets python stage2_media_restart_probe.py` | 0 | ~14s | 真实 Chrome 启动，基线 1080p 视频帧增长，经历了两次重协商并在日志输出 `STAGE 2 PASS` |
| 4 | `uv run --no-project --with playwright --with websockets python adversarial_harness.py` | 0 | ~14s | **对抗验证**：Round 2 注入完全无效的凭证，原测试断言仍判定为通过（**复现假绿漏洞**） |
| 5 | `bash probe_work/cleanup.sh` | 0 | <1s | 容器、卷、网络全部清理，无任何孤立资源残留 |

---

## 2. 真实性验证深度核查（作者 PASS 是否真实）

### 2.1 真实成立的物理链路部分
1. **Chrome 客户端对象与上下文连续性**：
   - Chrome 端确实保持同一 `RTCPeerConnection` 实例（`pcProbeId` 始终为 `pc_4ogxnj58`，`pcCount == 1`），未发生页面刷新（Zero reload）。
   - 音频通过 `pc.ontrack` 挂载至 Web Audio 播放，440Hz 正弦波真实产生 `totalAudioEnergy > 0`。
   - 视频分辨率严格保持为 1920x1080。
2. **服务端 DTLS / Pacer / Media Track 保持**：
   - 服务端 `Stage2GenerationIceTransport` 成功劫持 `_recv` 与 `_send`，底层的 DTLS Transport 与 WebRTC Pacer 确实没有重建，避免了 Selkies 在 renegotiation 时崩溃。
3. **Turn Allocation 生命周期**：
   - Coturn 容器日志显示：
     - Round 1 创建 allocation: `172.29.0.10:40012` 与 `172.29.0.10:40003`。
     - Round 2 创建 allocation: `172.29.0.10:40014` 与 `172.29.0.10:40008`。
     - 旧 allocation 在新连接建立后触发 `REFRESH lifetime=0`，随后 Coturn 日志明确输出 `closed (2nd stage) ... allocation delete`，旧 allocation 确实释放。

---

## 3. 致命漏洞与假绿风险（Critical Flaw & False Green）

### 3.1 致命假绿复现：对抗测试（Adversarial Harness）验证
在 `adversarial_harness.py` 对抗测试中，我们在第二轮轮换时向服务端和客户端注入**伪造且非法的 TURN 凭证**（`invalid_user` / `invalid_secret_key_xxxx`）。Coturn 拒绝该凭证，服务端没有收集到任何 relay candidate（日志记录：`Generation 3 gathered 0 candidates (all relay: True)`）。

**然而，原作者的 `stage2_media_restart_probe.py` 判定逻辑依然判定测试通过（False-Green PASS）！**

```text
2026-10-27 11:53:19,922 [INFO] adversarial_harness: Triggering Round 2 with INVALID CREDENTIAL...
2026-10-27 11:53:19,931 [INFO] adversarial_harness: Server restart API returned: {'success': True, 'generation': 3, 'local_ufrag': 'u4vHJy69'}
2026-10-27 11:53:20,938 [INFO] adversarial_harness:   Adv Check [1s] State: connected (ICE: connected) | Local: relay, Remote: relay | frames: 37 (+7)
2026-10-27 11:53:21,948 [INFO] adversarial_harness:   Adv Check [2s] State: connected (ICE: connected) | Local: relay, Remote: relay | frames: 46 (+16)
2026-10-27 11:53:21,948 [WARNING] adversarial_harness: CRITICAL: Original probe's assertion criteria MET despite INVALID credentials!
```

### 3.2 假绿根因分析（精确源码行号）

在 `stage2_media_restart_probe.py` 第 362-385 行：
```python
362: for sec in range(25):
363:     await asyncio.sleep(1)
364:     r2_stats = await get_page_stats(page)
...
379:     if (
380:         c_state == "connected"
381:         and local_type == "relay"
382:         and remote_type == "relay"
383:         and f_decoded >= r2_frames_baseline + 15
384:         and energy > r2_energy_baseline
385:     ):
386:         r2_success = True
387:         break
```
1. **Make-before-break 残留欺骗**：
   WebRTC 规范要求平滑切换（make-before-break）。在发送新 Offer 期间，旧的 ICE candidate pair（第一轮建立的 relay pair）依然在传输数据，`pc.connectionState` 依然是 `connected`，`localCandidateType` 依然是 `relay`。
2. **基线采样时机错误**：
   作者在 `trigger_server_restart` 之后**立即**记录 `r2_frames_baseline`（第 357 行），但在新 ICE 轮协商握手完成（甚至是彻底失败）之前，旧通道仍在源源不断地送帧（2 秒内帧数轻松增加 16 帧）。因此，循环在第 1~2 秒就直接命中了 `f_decoded >= r2_frames_baseline + 15`！
3. **缺少关键协商状态断言**：
   - 未断言 Chrome 端当前 `selectedCandidatePairId` 对应的 local/remote candidate 是否属于**新的 generation**（新 ufrag / 新 allocation 端口）。
   - 未等待服务端 `generation 3` 真正进入 active 状态（通过 aux API 或日志检查）。
   - 未在**新一代连接真正 commit 并关闭旧连接之后**重新拉取 baseline。
   - 导致即使第二轮凭证完全错误、新连接根本无法建立，原套件依然由于旧连接在继续传输而错误判定 PASS。

---

## 4. 架构设计与代码缺陷审计

### 4.1 适配器私有变量侵入性与官方原生兼容性
- **源码位点**：`stage2_adapter.py` 第 92-101 行：
  ```python
  92:  monitor = self._RTCIceTransport__monitor_task
  ...
  100: self._RTCIceTransport__iceGatherer = gatherer
  101: self._connection = gatherer._connection
  ```
- **问题**：大量使用了 Python 私有重整名称（Name Mangling，如 `_RTCIceTransport__monitor_task`、`_RTCIceTransport__iceGatherer`）。这并非 Selkies / aioice 官方原生支持的公共 API。一旦底层库进行小版本重构或变量重命名，该机制将直接崩溃。

### 4.2 配置对称性误导（Client / Server 配置分别作用）
- 在 `stage2_media_restart_probe.py` 第 273-290 行与第 339-354 行中，客户端与服务端传入了相同的 `turn:172.29.0.10:3478`。
- **缺口**：在生产环境中，服务端与客户端往往处于完全不同的网络拓扑（例如客户端在公网 NAT 之后，服务端在内网或特定机房），需要配置不同的 ICE servers 甚至使用不同的中继域。当前测试中双端同值，无法证明 client/server RTC 配置能够完全解耦独立部署。

### 4.3 生产周期调度未覆盖（Scheduler 24h / 12h / 提前 6h）
- 本次 Stage 2 仅验证了单进程生命周期内瞬间触发的 2 次连续 restart。
- **缺口**：真正的凭证轮换系统（24 小时寿命、12 小时轮换、过期前 6 小时平滑过渡）涉及定时任务调度器、时钟漂移、异步凭证失效队列等，当前代码**完全未测试**任何调度逻辑。

### 4.4 公网与复杂 NAT 未覆盖（Private Docker ≠ 公网可用）
- 当前测试运行在 OrbStack / Docker 内部虚拟网络 `172.29.0.0/16`。
- 所有 UDP 报文直连直通，RTT < 1ms，无丢包、无抖动、无 Symmetric NAT、无防火墙截断 UDP。
- **缺口**：内网 Docker 容器间直通不等于公网 WebRTC 穿透通过。公网部署面临的端口受限 NAT、防火墙阻断 UDP 需回退 TCP/TLS TURN 等场景均未经过任何实际验证。

### 4.5 安全漏洞：Secret 命令行传参泄漏风险
- **源码位点**：`probe_work/start_coturn.sh` 第 41 行：
  ```bash
  --static-auth-secret="$SECRET" \
  ```
- **风险分析**：通过命令行参数将 secret 传入容器进程。在多用户主机或容器宿主上，通过 `ps aux`、`/proc/<pid>/cmdline` 或容器 inspect 即可直接读取明文 secret。应当改用环境变量文件（`--env-file`）或挂载 private 0600 配置文件，避免通过 argv 暴露敏感凭证。

### 4.6 异常与清理完整性
- **源码位点**：`stage2_adapter.py` 第 160-165 行：
  在 `stop()` 中对 `retired_connections` 进行了清理，但在 `prepare_restart` 失败或发生未捕获异常时，部分中间生成的 `RTCIceGatherer` 与 TURN 资源未进入 try/finally 保证回收。

---

## 5. 总结与改进要求

| 评审维度 | 状态 | 评估详情 |
|---|---|---|
| **真实重跑媒体流** | 部分通过 | 真实 1080p 视频与音频能够通过中继传输，DTLS 连接保持成功 |
| **断言真实有效性** | **FAIL** | **严重假绿**：第二轮断言在伪造非法凭证下依然 PASS，逻辑严重缺陷 |
| **测试覆盖完整度** | **INCOMPLETE** | 缺少 Scheduler 定时调度、缺少公网 NAT 测试、双端配置未解耦 |
| **生产级规范** | **FAIL** | 私有内部属性侵入、命令行传据泄露 secret、异常清理保护欠缺 |

**最终判定：FAIL**。原套件不能作为合规凭据，必须重写第二轮与多代轮换的判定断言（强制在新代 candidate pair 成为 active 且旧代完全 closed 之后重新观测媒体增量），并补齐凭证调度与真实网络场景验证。
