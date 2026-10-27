# Stage 2 Split RTC Configuration & ICE Restart Review Report

**Review Status**: **PASS (Scoped Verification)**  
**Review Target**: Split RTC Configuration & Same-PC ICE Restart Implementation (`.scratch/split_rtc_review`)  
**Scope Boundary**: This verification proves host vs internal Docker TURN configuration separation, short-lived REST credentials per round/role, and zero-reload multi-generation ICE restarts under local published host (`127.0.0.1:13478`) vs internal network (`172.29.0.10:3478`). It does **not** evaluate public NAT traversal, TCP/TLS TURN transport, 24-hour background scheduler leases, Linux production host environment, or P95 latency SLAs.

---

## 1. 源码与产物 SHA-256 校验和 (Frozen Source & Artifact Integrity)

9 个基线源文件保持原样未修改，SHA-256 与基线完全一致：

```text
95999351b35582ff8ecb910cd56d996ef63e323115b96832a0b7f027b5df3b33  stage2_adapter.py
fbeaf0a2494665bbbeaa331e6f0b1b8f28ac6b8f5d8ac699d202f03b8907d355  stage2_adversarial_probe.py
12ff6b2291034ca41468cc1be3cba9aad049c9f6b4d9f58322cd801a78b849c3  stage2_containers.sh
659ed6427ff464fc3ce59aeecfdb4c77100a94c9d43b10e11d80a5ff659b5ab0  stage2_media_restart_probe.py
142e22dc05b0e2d420deb80bbca7a35115ed8eb2b22b2f25e83fce9b4d6f605e  stage2_stream_entrypoint.sh
d3af8eb29aa538fb208b8f56004d7d9412626924f3e339a25257100b4acc2eeb  stage2_stream_runner.py
dcbc7d70b330cb2834c3e393b5b354239210ccf58551783ab74abf7a215b5810  media_fixture/entrypoint_browser.sh
cf343324d087a3534a01fce66ea5796cd7cfecf59167d742636e29a9e5c3adb1  probe_work/cleanup.sh
02dfe507271fed914ff6e192d53683bc6b11567bb13cefaf7fafa3721a8a7ca1  probe_work/start_coturn.sh
```

---

## 2. 独立复现命令、执行耗时与退出码

所有执行严格限定于隔离 TMPDIR (`.scratch/split_rtc_review/tmp`)，无外部代码写入或 Git 变动。

| 步骤 | 执行命令 | 耗时 | 退出码 | 判定 |
|---|---|---|---|---|
| **1. 启动 Coturn** | `/Users/karson/kar/code/CBrowser/.scratch/v2_orchestration/review/.scratch/split_rtc_review/probe_work/start_coturn.sh` | 2.8s | 0 | 成功启动独立网络与私网 IP 172.29.0.10 |
| **2. 启动服务容器** | `/Users/karson/kar/code/CBrowser/.scratch/v2_orchestration/review/.scratch/split_rtc_review/stage2_containers.sh` | 3.1s | 0 | 浏览器与 Selkies 流服务容器就绪，辅助控制端口 18092 响应正常 |
| **3. 双代重启正常探针** | `TMPDIR=.../tmp uv run --no-project --with playwright --with websockets python3 stage2_media_restart_probe.py` | 17.5s | 0 | 验证双代重启、对象引用不变性与换代后独立媒体流量增长 |
| **4. 单侧失效对抗探针** | `TMPDIR=.../tmp uv run --no-project --with playwright --with websockets python3 stage2_adversarial_probe.py` | 33.3s | 1 | 契约预期退出码 1（两组单侧失效均被有效拦截，无 False Green） |
| **5. 资源清理** | `/Users/karson/kar/code/CBrowser/.scratch/v2_orchestration/review/.scratch/split_rtc_review/probe_work/cleanup.sh` | 1.9s | 0 | `cbrowser-spike-rtc-split-*` 容器、网络与卷全部清理完毕 |

---

## 3. 分离配置拓扑与凭据轮换验证 (Split Configuration & Credentials)

### 3.1 URL 与网络拓扑隔离
- **外部客户端 (Chrome)**：通过宿主机端口映射连接 `turn:127.0.0.1:13478?transport=udp`。
- **内部服务端 (Selkies 容器)**：通过 Docker 内网直接连接 `turn:172.29.0.10:3478?transport=udp`。
- **断言成立**：`CLIENT_TURN_URL != SERVER_TURN_URL`，两端 ICE 配置完全解耦。

### 3.2 轮换 REST 凭据独立性
每一代重启均动态生成独立 short-lived REST HMAC 凭据：
- **Generation 2 (Round 1)**：
  - Client Username: `1793086874:client_r1`
  - Server Username: `1793086874:server_r1`
  - 校验：`client_u1 != server_u1`，`client_p1 != server_p1`
- **Generation 3 (Round 2)**：
  - Client Username: `1793086879:client_r2`
  - Server Username: `1793086879:server_r2`
  - 校验：`client_u2 != server_u2`，`client_u2 != client_u1`，`server_u2 != server_u1`
- **Coturn 日志印证**：
  - Coturn 容器日志显示对应的 `ALLOCATE` 成功包：
    `user <1793086874:server_r1>`、`user <1793086874:client_r1>`、`user <1793086879:client_r2>`、`user <1793086879:server_r2>`。
  - 旧连接在换代提交后被显式发送 `REFRESH lifetime=0` 释放分配，无陈旧连接残留。

---

## 4. WebRTC 媒体流与对象引用不变性 (Media & Object Invariance)

### 4.1 客户端与服务端对象引用
- **客户端不变性**：
  - `RTCPeerConnection` 实例对象完全相同（`pc_probe_id: pc_51wrifzs`，`samePCReference === true`，`pcCount === 1`）。
  - 音频与视频 `Receiver.track` 引用完全保持一致（`sameTrackReferences === true`）。
  - 整个多代重启过程无页面刷新或跳转（`zero_page_reload: true`）。
- **服务端不变性**：
  - 服务端 `RTCPeerConnection` 实例内存 ID 稳定：`281473478320416`。
  - 服务端 `RTCDtlsTransport` 实例内存 ID 稳定：`281473533714576`。

### 4.2 中继对切换与旧代关闭
- 每次重启动态生成新 `local_ufrag`（Gen 2: `y4iq1FOL`，Gen 3: `evE9ly59`）。
- 客户端 `selectedCandidatePair` 严格更新为 relay <-> relay，且 remote candidate `usernameFragment` 匹配当前代 ufrag。
- 服务端 `committed_generation` 递增推进：
  - 换代时旧连接调用 `previous.close()` 终止底层传输。
  - 旧代显式发送写入拦截测试包：`send_rejected=True`（抛出 `ConnectionError`），证明旧链路完全断开并拒绝任何残留写入。

### 4.3 隔离基线媒体流量增长
换代提交后立即抓取新 baseline，在纯新代通道上测量指标增量：
- **Generation 2**：
  - 1080p 解码帧数增长：`+16` 帧（从 46 增至 62）
  - 440Hz 音频能量增长：`+1.3023`（从 3.6171 增至 4.9194）
  - Candidate Pair 传输字节增量：`+1,020,028` bytes
- **Generation 3**：
  - 1080p 解码帧数增长：`+17` 帧（从 70 增至 87）
  - 440Hz 音频能量增长：`+1.3019`（从 5.5871 增至 6.8890）
  - Candidate Pair 传输字节增量：`+978,842` bytes

---

## 5. 单侧凭据对抗矩阵验证 (Auth Negative Matrix)

通过两轮独立会话验证单侧凭据失效时的严格防御机制：

### 5.1 Session 1: Server Valid / Client Bad
- **行为**：服务端生成合法中继候选并向客户端发送 Offer；客户端使用错误密码向 Coturn 请求中继候选。
- **Coturn 反应**：Coturn 日志捕获 `ERROR Cannot find credentials of user <adv_s1_bad_client_user>`，返回 `error 401: Unauthorized`。
- **结果**：客户端无法完成新代中继协商，未切换 Candidate Pair。服务端 `committed_generation` 保持为 1（未晋升至 2）。
- **旧代媒体隔离**：旧代媒体在旧通道上持续解码（+49 帧），探针严格将其判定为旧媒体连续性，未计入新代提交，防止 False Green。

### 5.2 Session 2: Server Bad / Client Valid
- **环境隔离**：经 `stage2_containers.sh` 重启完全重置容器状态。
- **行为**：客户端预置有效凭据；服务端配置错误凭据并尝试执行 `prepare_restart`。
- **Coturn 反应**：Coturn 拦截服务端请求，返回 401 Unauthorized，服务端中继候选收集数为 0。
- **接口防护**：`prepare_restart` 抛出 `RuntimeError: Zero relay candidates gathered for generation 2`。辅助控制接口 `/restart_ice` 严格返回 `HTTP 400 Bad Request`。
- **客户端行为精确边界确认**：由于服务端在发出 SDP Offer 前即被 400 拦截报错，服务端未向信令通道推送 Offer，因此客户端的 `setRemoteDescription` hook 并不触发，客户端挂起的配置未实际向 Coturn 发起申请。探针与评审记录准确记录此机制，不虚夸 Session 2 存在有效客户端中继分配（该通路已由正常探针充分证明）。
- **结果**：服务端 `committed_generation` 保持为 1。旧代媒体持续流动（+40 帧）不计入新代提交，False Green 被完全杜绝。

---

## 6. 安全性与资源清理审计 (Security & Sanitation Audit)

1. **命名与作用域隔离**：
   - 容器名称均使用 `cbrowser-spike-rtc-split-*` 前缀。
   - 网络 `cbrowser-spike-rtc-split-net` (172.29.0.0/16) 与卷 `cbrowser-spike-rtc-split-*` 完全限定。
   - 端口占用：`18091`、`18092`、`30016`、`13478`、`40000-40020`，无端口逃逸。
   - 并行测试保护：未触碰宿主机其他任务的容器（如 `cbrowser-spike-isolation-*`）。
2. **凭据安全与零泄漏**：
   - Coturn 密钥通过 `chmod 600` 专用配置文件（`turnserver.conf`）挂载，未在 `docker run` 命令行参数中暴露 `--static-auth-secret`。
   - 辅助控制服务 `/health` 与 `/peers` 及 `get_diagnostics()` 仅暴露 generation、ufrag 与状态，不暴露任何密码或密钥。
   - 控制台标准输出、日志输出、`stage2_result.jsonl` 与 `adversarial_result.json` 中均不含密码字符串或 static auth secret。
3. **最终资源清理**：
   - `probe_work/cleanup.sh` 执行后，所有 `cbrowser-spike-rtc-split-*` 容器、网络与数据卷均已清理释放。

---

## 7. 结论

本项变更在本地环境下完全证实了客户端与服务端 RTC 配置分离的可行性，以及基于 `Stage2GenerationIceTransport` 实现的零刷新、保长连接、安全隔离的多代 WebRTC ICE 重启能力，单侧失效对抗矩阵表现稳健。

**评审结论：PASS**
