# 独立代码审查与真实重跑验证报告：Stage 2 TURN 代际轮换与媒体连续性修复审查

- **审查对象**：Stage 2 真实 TURN / Chrome 媒体与 ICE 重启（Final Revision: Generation Commit Fix）
- **审查环境**：工作区 `.scratch/turn_generation_review`，TMPDIR 限制为 `./tmp`，隔离于宿主 `/tmp`
- **模型**：Gemini `cpa/gemini-3.8-flash`
- **审查日期**：2026-10-27
- **审查结论**：**SCOPED PASS（代际切换与反假绿断言通过，附生产落地前置限制）**

---

## 1. 源码哈希与文件完整性 (SHA-256)

对本次复核涉及的所有 8 个关键源码和脚本进行哈希计算：

| 文件路径 | SHA-256 Checksum |
|---|---|
| `stage2_adapter.py` | `95999351b35582ff8ecb910cd56d996ef63e323115b96832a0b7f027b5df3b33` |
| `stage2_adversarial_probe.py` | `9cf69a45bbf80d3a94c5ffa48463fc6978dc4dafc9c1962aca838396b09967eb` |
| `stage2_containers.sh` | `e03650c4bd9bf27225b1ac438f2c482ceac0cf5fa79026536dc3192e82eae9a1` |
| `stage2_media_restart_probe.py` | `cc3d601dfd93600a69223a8aefaad0f46c2855234e2166c6096646bb1adc97d6` |
| `stage2_stream_entrypoint.sh` | `142e22dc05b0e2d420deb80bbca7a35115ed8eb2b22b2f25e83fce9b4d6f605e` |
| `stage2_stream_runner.py` | `d3af8eb29aa538fb208b8f56004d7d9412626924f3e339a25257100b4acc2eeb` |
| `probe_work/start_coturn.sh` | `176b24c96a8d928339e32e99b5e43e070ae76c3b84da19fead25aa3dc49523ad` |
| `probe_work/cleanup.sh` | `d8e3fc187cd57183e9a63602b04092a166f7d6607610d260fd2e138d27fe8dcf` |

---

## 2. 实际命令执行记录与结果

执行序列严格遵循审查契约，所有资源均为 `cbrowser-spike-turn-*`，并在 `finally` 阶段完成彻底清理。

| 步骤 | 执行命令 | 实际 Exit Code | 耗时 | 实际关键观察 |
|---|---|---|---|---|
| 1 | `bash probe_work/start_coturn.sh` | `0` | 2.1s | 生成独立 private 0600 secret 与配置文件 `turnserver.conf`（权限 0600），容器通过 `-c /etc/turnserver.conf` 启动，**无任何命令行 argv secret 暴露**。监听 172.29.0.10:3478 及 UDP 40000-40020。 |
| 2 | `bash stage2_containers.sh` | `0` | 1.1s | 启动 browser（X11/Pulse/TestPage 440Hz 音频与 1080p 动效）和 stream（搭载代际 ICE 适配器及 auxiliary 控制端口 18092）。 |
| 3 | `uv run --no-project --with playwright --with websockets python stage2_media_restart_probe.py` | `0` | 17.2s | **正常套件执行（严苛模式）**：<br>1. Chrome 建立基线：1080p、帧数 20、音频能量 1.5163。<br>2. Round 1：触发 generation 2，服务端 commit 完成并确认旧 gen 1 连接 `send_rejected=True`；Chrome selected pair 切换为 relay-relay 且 `usernameFragment=5if92qY8`；随后建立新代 baseline（帧数 28，能量 2.2009），在此基础上观测到新代真实增量（+17 帧，音频能量 +1.3028，pair 字节 +1.2MB）。<br>3. Round 2：触发 generation 3，ufrag 轮换为 `wNQRi9H0`，服务端 commit 完成并确认旧 gen 2 连接 `send_rejected=True`；Chrome selected pair 切换且 ufrag 匹配；在新代 baseline 上观测到独立增量（+15 帧，音频能量 +1.3039，pair 字节 +1.25MB）。<br>4. Client/Server PC 与 DTLS 句柄全程无任何改变（Zero Reload）。 |
| 4 | `uv run --no-project --with playwright --with websockets python stage2_adversarial_probe.py` | `1` | 15.6s | **对抗探针测试（负例验证）**：<br>1. 注入非法伪造凭证 `adversarial_invalid_user`。<br>2. Coturn 真实鉴权拦截：日志输出 `error 401: Unauthorized`。<br>3. 服务端采集 0 个 relay 候选，API 抛出 HTTP 400（`Zero relay candidates gathered for generation 3`）。<br>4. 探针持续观测 5 秒：记录到 make-before-break 旧媒体通道在 5 秒内继续流动（帧数持续增长 +39 帧，证实了前一版本假绿的根因）。<br>5. 检查服务端诊断：`generation_3_committed == False`，严格阻止了假绿；探针按照契约显式以退出码 `1` 退出，**确认并非通用异常或语法错误，而是真实的业务拦截通过**。 |
| 5 | `bash probe_work/cleanup.sh` | `0` | 0.8s | 释放容器、网络与卷，`docker ps -a` / `docker volume ls` / `docker network ls` 确认无任何遗留。 |

---

## 3. 作者修复措施的有效性与深层审计

### 3.1 针对前版“第二轮假绿漏洞”的修复核实
在上一轮 review 中，作者的代码在第二轮收到无效凭证时，由于 make-before-break 旧链路仍在传输视频帧，测试直接读取全局或旧 baseline 判定 PASS。
在本次提交中，作者重构了以下机制，有效封堵了假绿通道：
1. **真实 Commit 栅栏（Step A / A2）**：
   - 源码位点：`stage2_media_restart_probe.py` 第 320-334 行、第 438-452 行；`stage2_adapter.py` 第 170-190 行。
   - 机制：客户端在发起 renegotiation 后，必须轮询等待服务端诊断接口返回 `committed_generation == target_gen`。只有当底层 `aioice` 真正完成新一轮 ICE 握手、建立新 pump、并且主动调用旧连接的 `close()`，并验证 `send(b"...")` 必须抛出 `ConnectionError`（`send_rejected=True`），服务端才会将 `committed_generation` 步进。
2. **Chrome 端 Selected Candidate Pair 与新 ufrag 强校验（Step B / B2）**：
   - 源码位点：`stage2_media_restart_probe.py` 第 337-357 行、第 454-476 行。
   - 机制：不仅检查 `localCandidate.candidateType == "relay"` 与 `remoteCandidate.candidateType == "relay"`，而且**严格校验 `remoteCandidate.usernameFragment == expected_local_ufrag`**。
   - **反假绿证明**：在对抗测试中，由于生成了未授权的 generation 3，Chrome 保持与旧代通信，`remoteCandidate.usernameFragment` 依然停留在 generation 2 的 ufrag，Step B 无法通过；而在正常测试中，`local_ufrag` 明确从 `5if92qY8`（Round 1）轮换为 `wNQRi9H0`（Round 2），Chrome 端 `getStats()` 抓取到的活动对与 SDP 新 Offer 严格一致。
3. **隔离的新代媒体基线再采样（Step C / D / C2 / D2）**：
   - 源码位点：`stage2_media_restart_probe.py` 第 359-396 行、第 477-515 行。
   - 机制：在 Step A（服务端 commit）和 Step B（客户端切换对）确认后，**重新抓取当前帧数、音频能量和候选对接收字节作为全新基线**。后续的 +15 帧、+0.1 音频能量和 +30000 候选对字节增长，必须完全在新代通道上产生。

### 3.2 凭证安全修复（Secret 命令行暴露问题）
- 源码位点：`probe_work/start_coturn.sh` 第 18-30 行、第 45-50 行。
- 修复验证：`SECRET` 不再作为 `--static-auth-secret="$SECRET"` 传入命令行参数。而是通过本地私有生成 `turnserver.conf`（权限 `chmod 600`），挂载为 `/etc/turnserver.conf:ro`。
- 执行 `docker inspect --format='{{.Args}}' cbrowser-spike-turn-coturn` 输出为 `[-c /etc/turnserver.conf --log-file=stdout]`，宿主 `ps aux` 与容器元数据中均无 secret 暴露。

### 3.3 对象句柄与 DTLS 连续性核查
- 客户端：`window.__peerConnections` 长度严格为 1，`pc.__probeId` 始终为 `pc_621wz4f5`，`window.__restartCount` 正确自增到 2，页面无 reload。
- 服务端：`query_server_peers()` 返回的 `server_pc_id` 始终为 `281472969121360`，`server_dtls_id` 始终为 `28147296242288`。虽然在 Python 内部这些是对象的内存地址（author report 中曾疑虑为何相同，实际上同一个长生命周期 Python 对象在内存中地址不发生改变是预期行为），这证明了 `pc.sctp.transport` 和 `RTCPeerConnection` 确实没有销毁重建。

---

## 4. 架构局限性与待办项清单（Scope Limitations）

虽然本次 Spike 在功能验证和反假绿测试上表现优异，但根据工程落地标准，必须明确以下非生产特性与后续工程任务：

1. **私有字段侵入性（Monkey Patch 限制）**：
   - 源码位点：`stage2_adapter.py` 第 99-105 行、第 126-127 行；`stage2_stream_runner.py` 第 28 行、第 111 行。
   - 现象：适配器深度访问了 `self._RTCIceTransport__monitor_task`、`self._RTCIceTransport__iceGatherer`、`peer_conn._RTCPeerConnection__iceTransports`。
   - 影响：这是针对 Selkies 2.1.0 内部 aioice / webrtc 实现的特定补丁，并非 SDK 官方公共 API。上游若有内部重构可能破坏兼容性，后续应向上游反馈或维护专有 patch 包。
2. **凭证调度器缺口（Scheduler Out-of-Scope）**：
   - 源码位点：`stage2_media_restart_probe.py` 第 94-102 行。
   - 现象：凭证仅由 probe 临时基于当前时间计算（TTL=120s）。
   - 影响：生产环境规范要求的 24 小时生命周期、12 小时定时轮换、提前 6 小时平滑过渡的后台 Scheduler 逻辑属于业务调度层，本 Spike 仅验证了 WebRTC 传输层协议的可行性，未包含后台调度任务。
3. **真实公网与 NAT 穿透环境未测**：
   - 当前测试运行在 OrbStack / Docker 虚拟网桥 `172.29.0.0/16`，无丢包、无抖动、无 Symmetric NAT、无 UDP 防火墙。
   - 内网穿透成功不代表公网在各种运营商 NAT 拓扑下 100% 成功，仍需在预发公网环境验证。
4. **客户端与服务端配置独立解耦**：
   - 当前测试中 client 与 server 使用相同的 `turn:172.29.0.10:3478`。生产环境中客户端连接公网域名，服务端可能连接内网 IP，需在网关层进一步支持拆分配置。

---

## 5. 审查判定与结论

| 审查项 | 判定 | 评语 |
|---|---|---|
| 真实媒体重跑与退出码 | **PASS** | 退出码 0，真实 1080p 视频与音频解码增长，无 Mock |
| 对抗探针与假绿防护 | **PASS** | 退出码 1，真实 Coturn 401 拦截，彻底消除了 make-before-break 假绿 |
| Secret 凭证安全性 | **PASS** | 私有 0600 conf 挂载，消除 argv 泄露风险 |
| 资源生命周期清理 | **PASS** | 容器/网络/卷彻底清理无残留 |
| 生产成熟度与调度 | **INCOMPLETE** | 实验性猴子补丁、缺后台轮换 Scheduler、缺真实公网 NAT 测试 |

**综合评审意见**：**SCOPED PASS**。
作者对第二轮假绿的根因分析准确，所采取的“代际 Commit 栅栏 + Selected Pair ufrag 强绑定 + 新代独立增量基线”方案坚实有效，对抗测试能严格拦截非法凭证；安全上消除了命令行凭证泄露。该实现满足 Spike 阶段的技术验证目标，准予结项并转入架构蓝图与生产适配器设计阶段。
