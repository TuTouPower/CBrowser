# 独立代码审查与真实重跑验证报告：Stage 2 TURN R3 Delta Review & Actual Replay

- **审查对象**：Stage 2 真实 TURN / Chrome 媒体与 ICE 重启（R3 Delta: Client Credential Log Removal & Strict PC/Track Reference Equivalence）
- **审查环境**：工作区 `.scratch/turn_reference_review`，TMPDIR 限制为本目录 `./tmp`，隔离于宿主 `/tmp`
- **模型**：Gemini `cpa/gemini-3.8-flash`
- **审查日期**：2026-10-27
- **审查结论**：**SCOPED PASS（R3 Delta 修复与全等对象断言全部通过，附生产落地前置限制）**

---

## 1. 源码哈希与文件完整性 (SHA-256)

对本次复核涉及的所有 8 个关键源码和脚本进行哈希计算：

| 文件路径 | SHA-256 Checksum | 变更状态（相比 turn_generation_review） |
|---|---|---|
| `stage2_media_restart_probe.py` | `0401909f546993dd9e1c06ddce78f3cccf3727e33f7d0f6fc9c21b7b0eb12847` | **Modified (R3 Delta 修复)** |
| `stage2_adapter.py` | `95999351b35582ff8ecb910cd56d996ef63e323115b96832a0b7f027b5df3b33` | Unchanged |
| `stage2_adversarial_probe.py` | `9cf69a45bbf80d3a94c5ffa48463fc6978dc4dafc9c1962aca838396b09967eb` | Unchanged |
| `stage2_containers.sh` | `e03650c4bd9bf27225b1ac438f2c482ceac0cf5fa79026536dc3192e82eae9a1` | Unchanged |
| `stage2_stream_entrypoint.sh` | `142e22dc05b0e2d420deb80bbca7a35115ed8eb2b22b2f25e83fce9b4d6f605e` | Unchanged |
| `stage2_stream_runner.py` | `d3af8eb29aa538fb208b8f56004d7d9412626924f3e339a25257100b4acc2eeb` | Unchanged |
| `probe_work/start_coturn.sh` | `176b24c96a8d928339e32e99b5e43e070ae76c3b84da19fead25aa3dc49523ad` | Unchanged |
| `probe_work/cleanup.sh` | `d8e3fc187cd57183e9a63602b04092a166f7d6607610d260fd2e138d27fe8dcf` | Unchanged |

---

## 2. R3 Delta 关键改动详细核实

通过对 `turn_generation_review` 与 `turn_reference_review` 的代码进行逐行对比，核实了作者在 R3 阶段交付的以下三项重要修复：

### 2.1 彻底移除客户端控制台敏感凭证打印 (Credential Leakage Fix)
- **前版缺陷**：前版 `stage2_media_restart_probe.py` 第 85 行包含：
  ```javascript
  console.log('[Probe Client] Applying pending ICE config on same PC before answer:', window.__pendingIceConfig);
  ```
  该语句会将包含明文 `username` 与 HMAC `credential` 的 `window.__pendingIceConfig` 对象完整打印至 Chrome 控制台和 Playwright 日志中。
- **R3 修复**：该行 `console.log` 已被**彻底删除**（同时删除了第 64 行关于 audio track 的多余控制台日志）。
- **静态扫描证据**：使用 `grep -rn "console\.log" .` 进行全局扫描，匹配结果为 0。测试运行期间 Chrome 控制台与日志中**无任何明文 secret、password 或完整 ICE credentials 泄露**。

### 2.2 严格的客户端 PC 与 Receiver Track 真实对象全等断言 (True Object Reference Equivalence)
- **前版缺陷**：前版仅依靠随机生成的字符串 `pc.__probeId`（如 `pc_621wz4f5`）和 `pcCount == 1` 判断对象不变，无法彻底排除内部对象被代理或重建但保留相同属性的可能性，且未校验媒体音视频 Track 对象是否重建。
- **R3 修复**：
  1. 源码第 61 行：在首个 PC 实例化时，显式保存全局句柄：`if (!window.__firstPC) window.__firstPC = pc;`。
  2. 源码第 271 行：在 Phase 1 基线建立后，捕获初始所有 Receiver Track 对象：
     ```javascript
     window.__initialTracks = window.__firstPC.getReceivers().map(r => r.track);
     if (window.__initialTracks.length < 2) throw new Error('Missing audio/video receiver tracks');
     ```
  3. 源码第 151-152 行与第 403-404 行、第 524-525 行：在 `get_page_stats` 中增加了物理全等断言：
     ```javascript
     samePCReference: pc === window.__firstPC,
     sameTrackReferences: !!window.__initialTracks &&
       window.__initialTracks.length === pc.getReceivers().length &&
       pc.getReceivers().every((r, i) => r.track === window.__initialTracks[i]),
     ```
     并在 Python 侧进行硬断言：
     ```python
     assert r1_stats["samePCReference"], "Client PC reference changed"
     assert r1_stats["sameTrackReferences"], "Client receiver track references changed"
     ```
- **实际执行证据**：在经历 2 次完整的服务端 Offer / 客户端 Answer 代际重启后，`samePCReference` 与 `sameTrackReferences` 均严格返回 `True`，证实物理 `RTCPeerConnection` 与其绑定的 `audio`/`video` Receiver Track 实例全流程保持同一引用，未发生重新附加或内存重建。

### 2.3 最终汇总数据采样点修复 (Growth Sample Fix)
- **前版缺陷**：在 Step D / D2 循环中，当媒体增长条件满足后，前版未将当前的 `cur` 更新赋值给 `r1_stats` / `r2_stats`，导致最终生成的 JSONL 报告中 `final_frames_decoded` 输出的是 Step C 采样点的值（53 帧），而非最终实际测得的媒体增长帧数。
- **R3 修复**：源码第 394 行与第 515 行新增：
  ```python
  r1_stats = cur
  ...
  r2_stats = cur
  ```
- **实际执行证据**：最终 JSONL 中的 `final_frames_decoded` 正确记录为 `70`（包含了完整的 +16 帧新代增长），真实反映了最新一代的媒体状态。

---

## 3. 实际命令执行记录与退出码验证

| 序号 | 执行命令 | 实际 Exit Code | 耗时 | 关键观察与验证结果 |
|---|---|---|---|---|
| 1 | `bash probe_work/start_coturn.sh` | `0` | 2.0s | 生成独立 private 0600 secret 与 0600 `turnserver.conf` 挂载配置文件。容器参数通过 `-c /etc/turnserver.conf` 传入，宿主 `ps aux` / 容器 inspect 无 argv 泄露。端口 172.29.0.10:3478 及 UDP 40000-40020 准备就绪。 |
| 2 | `bash stage2_containers.sh` | `0` | 1.1s | 启动 `cbrowser-spike-turn-browser` 与 `cbrowser-spike-turn-stream`，共享 X11/Pulse 虚拟环境。 |
| 3 | `uv run --no-project --with playwright --with websockets python stage2_media_restart_probe.py` | `0` | 16.0s | **主套件严格重跑**：<br>1. 基线建立：1080p 视频（21 帧）、音频能量 1.6187、捕获 2 个 Receiver Track。<br>2. Round 1：触发 generation 2，服务端 commit 完成且确认旧 gen 1 连接 `send_rejected=True`；Chrome selected pair 切换为 relay-relay 且 `usernameFragment=EttbpbB3`；在新 baseline（30 帧）上完成新代增量观测（+16 帧、音频能量 +1.3227、pair 字节 +1.2MB）；断言 `samePCReference` 与 `sameTrackReferences` 均为 `True`。<br>3. Round 2：触发 generation 3，ufrag 轮换为 `r7DFRoNN`，服务端 commit 完成且确认旧 gen 2 连接 `send_rejected=True`；Chrome selected pair 切换；在新 baseline（54 帧）上完成新代增量观测（+16 帧、音频能量 +1.2961、pair 字节 +1.12MB）；断言 `samePCReference` 与 `sameTrackReferences` 保持为 `True`。<br>4. 最终写入 `stage2_result.jsonl`，`webrtc_media: "PASS"`。 |
| 4 | `uv run --no-project --with playwright --with websockets python stage2_adversarial_probe.py` | `1` | 15.6s | **对抗探针测试**：<br>1. 注入非法伪造凭证 `adversarial_invalid_user`。<br>2. Coturn 核心日志实时截获：`401: Unauthorized`。<br>3. 服务端 API 返回 HTTP 400（`Zero relay candidates gathered for generation 3`），`generation_3_committed == False`。<br>4. 连续 5 秒观测到旧代通道因 make-before-break 继续送帧（+40 帧），证实旧流连续性事实。<br>5. 探针验证新代未提交且旧媒体被识别，按规范契约以退出码 `1` 退出，**确认退出并非由 generic exception 或语法错误导致**。 |
| 5 | `bash probe_work/cleanup.sh` | `0` | 0.8s | 释放全部容器、卷及网络，`docker ps -a` / `docker volume ls` / `docker network ls` 确认无任何残留。 |

---

## 4. 架构局限性与合规性审查（生产落地前置条件）

尽管 R3 版本在技术实现、对象全等性、媒体连续性以及反假绿测试上完整闭环，但必须再次重申以下**工程与架构层面的限制**，严禁以本次 Spike 结论替代生产环境交付：

1. **底层私有接口依赖限制（Non-standard Monkey Patching）**：
   - 源码位点：`stage2_adapter.py` 第 99-105 行、第 126-127 行。
   - 现象：适配器高度依赖 Python 名称修饰私有属性（`_RTCIceTransport__monitor_task`、`_RTCIceTransport__iceGatherer`、`_RTCPeerConnection__iceTransports`）。
   - 限制：这属于工程验证层面的针对性 Monkey-patch，非官方公共 API。后续生产落地必须评估上游 Selkies 2.1.0 版本的升级维护成本，或者将补丁上游化。
2. **凭证调度系统未实装（Scheduler Not Tested / Out of Scope）**：
   - 现象：当前测试中 TURN REST 凭证由 probe 脚本在单次会话内实时计算（TTL=120s）。
   - 限制：生产系统所需的 24 小时生命周期、12 小时定时轮换、提前 6 小时平滑过渡的后台守护进程（Scheduler）及集群时钟漂移处理，尚未在本 Spike 范围内核验。
3. **公网与复杂 NAT 穿透环境未核验**：
   - 当前测试全部基于 OrbStack / Docker 虚拟内网 `172.29.0.0/16`。
   - 内网 Docker 桥接直连无法代表公网复杂 Symmetric NAT、UDP 端口受限防火墙或多运营商路由场景。生产环境上线前必须在预发公网环境进行端到端穿透测试。
4. **17 项生产质量门禁（Quality Gate）依然生效**：
   - 本次通过仅限 Spike 维度的“功能与协议可行性验证”（Scoped Pass），不代表可以提前冻结阶段或绕过系统蓝图中的 17 项工程质量门禁。

---

## 5. 审查判定与结论

| 审查维度 | 判定结论 | 判定依据与实际证据 |
|---|---|---|
| **R3 Delta 修复** | **PASS** | 彻底移除敏感凭证 console.log；实现基于 JS `===` 的物理 PC 与 Track 实例全等校验；修复 final 采样点统计 |
| **正常重跑套件** | **PASS** | 退出码 0，全流程零页面刷新，1080p 视频与音频在新代通道上产生真实解码与字节增量 |
| **对抗探针测试** | **PASS** | 退出码 1，真实 Coturn 401 拦截，排除旧通道 make-before-break 假绿干扰，逻辑严密 |
| **凭证与配置安全** | **PASS** | 私有 0600 conf 挂载，无 argv / log / console 明文暴露 |
| **测试资源清理** | **PASS** | 退出后无任何 `cbrowser-spike-turn-*` 孤立资源残留 |
| **生产级完备度** | **INCOMPLETE** | 明确记录 Monkey Patch 局限性、未测后台 Scheduler、未测公网 NAT，保留限制清单 |

**最终综合判定**：**SCOPED PASS**。
Stage 2 的 R3 Delta 修复工作精准、扎实，彻底排除了代码层面的凭证泄露隐患，建立了基于物理对象全等（`===`）的强力断言，并在对抗性测试中表现出坚固的防御能力。准予收尾当前 Spike 阶段。
