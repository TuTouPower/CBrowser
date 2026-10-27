> 范围更新：本报告保留对应实验快照及历史限制。用户随后明确豁免公网与原生Linux x86_64执行；当前有效门禁见t001/scope_adjustment.md及架构计划“执行调整”。未运行项不计为测试通过。

# Spike report

## 问题

核对固定 Selkies 2.1.0 协议能否满足 v2.3 第8–10章和第18.6–14项，区分源码、函数单测、实际网络与媒体端到端证据。

## 成功判据

官方固定提交逐项有准确出处；真实媒体、输入、多页面、UDP mux 和 TURN/ICE 更新行为需实际实验。源码存在与默认对象构造不能判定端到端通过。

## 尝试

- Gemini 协议 agent 拉取并检出固定提交 `6ee68a7a815956e6745e916741f13335e0b3ff53`，检查官方代码。
- 握手类函数单测使用 transport stub，只能支持握手条件推断，不能作为真实 WebSocket/媒体/输入验收。
- 主控纠正 UDP mux 与多页面输入假阳性分类，保留原始 ICE restart 要求，未采纳删减要求建议。
- 主控新增真实 UDP 实验 `code/ice_restart_probe.py`，不 mock 生产 ICE 逻辑。

## 证据

- 主控真实网络实验建立两端 ICE transport，发送接收载荷成功；对已有 transport 再次 start 传入新 ICE 参数，参数未更新，旧路径仍传输。退出码 0。
- 观察输出：`{"real_udp_before": true, "repeated_start_applied_new_credentials": false, "original_path_still_alive": true}`。
- 原始输出在主仓 `.scratch/v2_orchestration/ice_restart_probe.log`，未入库。事实及源码出处见 d003。
- 官方源码与逐项分级见下方 agent 报告；主控未将函数单测或源码证据当作媒体黑盒通过。

重跑方式（checkout 必须是上述固定提交；网络实验不产生用户数据）：

```bash
uv run --no-project --with aiohttp --with cryptography --with aiofiles --with pyopenssl --with watchdog --with psutil --with msgpack --with prometheus_client --with google-crc32c --with pyee --with pylibsrtp --with dnspython --with ifaddr python docs/spikes/s002_selkies_protocol/code/ice_restart_probe.py /path/to/pinned_selkies_checkout
```

## 结论

- 无独占输入租约与 Selkies display_owner 不冲突；后者负责显示配置，Stream Agent 必须掌握 Profile 全局调帧与固定分辨率。
- 默认配置对象与 UDP sendto 成功不能证明 UDP mux 多连接工作；需真实 ICE/candidate/媒体统计。
- 固定版本无现成 ICE restart 路径，第10.6验收尚未满足；已向用户询问保留真正 ICE restart 或明确批准 ViewerConnection 重建，未回复前保持原要求。
- 第18.6–14项均未因本报告被勾选；多页面、IME、帧率、TURN relay-to-relay 与公网网络仍需真测。

## 是否采纳

- 决定：是，采纳源码约束与真实网络实验结论，不采纳弱化用户目标的建议。
- 理由：直接核对固定源码并经真实 UDP 复现重复 start 不更新 ICE 参数。
- 后续 task：t001
- 无需后续理由：不适用

## 关联 findings

- d003：固定版本 ICE restart 支持缺口。

## 协议 agent 修正后报告

# Selkies 2.1.0 官方协议与 v2 架构方案验证报告

**验证对象**：官方 Selkies 2.1.0 固定 commit `6ee68a7a815956e6745e916741f13335e0b3ff53`\
**核对范围**：`docs/v2_architecture_plan.md` 第 8-10 章及第 18 章 6-14 项\
**验证状态划分**：

- `[已验证]`：握手函数逻辑通过真实对象单测（transport stub）验证；
- `[仅源码证据]`：源码明确支持且有精准文件行号证据，未起真实网络/媒体黑盒；
- `[需真测]`：涉及真实音视频编码、物理网络或端到端输入，需真实环境；
- `[设计矛盾]`：v2 计划设想与官方底层协议或实现存在冲突/未满足。

______________________________________________________________________

## 1. 验证结论总览表

|验证项|对应章节/条款|支持状态|结论分类|核心依据与源码定位|
|---|---|---|---|---|
|1. 多 Controller 共存|第 8.1 节、第 18 章第 6 项|原生支持|`[已验证]`|`enable_sharing=True` 时允许同 token 多个 controller 并存 (`webrtc_signaling_server.py:720, 1069`)，已通过握手函数单测验证。|
|2. client_tab_id 判定|第 8.2 节、第 18 章第 6, 7 项|原生支持|`[已验证]`|官方 `_beside()` 依据 `tab_id` 判定并存，相同则 evict (`webrtc_signaling_server.py:715-722, 1069`)，已通过握手函数单测验证。|
|3. resume_key 会话恢复|第 8.2 节、第 18 章第 7 项|原生支持|`[已验证]`|断连后保持 `_holds`，重连带相同 `resume_key` 恢复 (`webrtc_signaling_server.py:801-833`)，已通过握手函数单测验证。|
|4. 多页面同时输入|第 8.3 节、第 18 章第 8 项|原生支持|`[仅源码证据]`|数据通道消息送入 `on_message`，X11 事件排队处理 (`webrtc_mode.py:1718, 1729`)；未发真实输入，待集成真测。|
|5. 共享编码器调帧/owner|第 9 章、第 18 章第 9, 10 项|机制约束|`[仅源码证据]`|官方设 `_display_owner_tabs` 主导显示配置与流参数，非 owner 的 `_arg_fps` 直接丢弃 (`webrtc_mode.py:1722-1728`)。|
|6. IME 输入机制|第 1.2(8) 节、第 18 章验收项|原生支持|`[仅源码证据]`|采用 `co,end,<text>` 配合 `_type_text_xtest` 动态映射按键，非剪贴板粘贴 (`input_handler.py:9571-9590, 6079-6124`)。|
|7. UDP mux 单端口多会话|第 10.1 节、第 18 章第 12 项|原生支持|`[仅源码证据]`|源码支持 `webrtc_udp_mux_port` (`webrtc_engine.py:1652-1674`)，单端口靠 8 字符 ufrag 分流 (`ice.py:509-512`)；未测真包分流。|
|8. 公网候选地址 (ADVERTISE_IP)|第 10.2 节、第 18 章第 13 项|原生支持|`[仅源码证据]`|`webrtc_public_ip` 映射为 ICE 1:1 NAT host 地址 (`webrtc_engine.py:1726`, `ice.py:494`)。|
|9. TURN 凭证与 REST HMAC|第 10.5, 10.6 节、第 18 章第 14 项|原生支持|`[仅源码证据]`|支持静态 secret 及 REST API HMAC 凭证生成 (`webrtc_ice_config.py:209-290, 565-580`)。|
|10. relay-only 模式|第 10.6 节、第 18 章第 14 项|原生支持|`[仅源码证据]`|前端支持 `turn_switch=true` 锁 relay (`webrtc.js:1189-1194`)；服务端规则验证 `ice_lite` 禁配 TURN (`ice.py:500-503`)。|
|11. ICE Restart 协议支持|第 10.6 节、第 18 章第 14 项|**未满足**|`[设计矛盾]`|官方 WebRTC/ICE 协议无 `iceRestart` 协商支持，长连接故意不重启 (`webrtc_engine.py:1578-1580`)，计划要求未满足。|
|12. 媒体流真实打通|第 18 章第 6-14 项|需管线环境|`[需真测]`|需真实 Xvfb、PulseAudio、pixelflux 及真实 Chrome 客户端进行端到端黑盒验证。|

______________________________________________________________________

## 2. 深入分析与源码行号证据

### 2.1 多 Controller、页面身份与恢复（第 8 章，第 18 章第 6, 7 项）

- **判定状态**：`[已验证]`（握手函数单测 / transport stub）
- **源码依据**：
    - `src/selkies/webrtc_signaling_server.py:715-722`：
        ```python
        def _beside(self, peer: Any, client_type: Optional[str], tab_id: Optional[str]) -> bool:
            return (self.enable_sharing and client_type == "controller"
                    and getattr(peer, "client_type", None) == "controller"
                    and bool(tab_id) and bool(getattr(peer, "tab_id", None)) and peer.tab_id != tab_id)
        ```
    - `src/selkies/webrtc_signaling_server.py:1063-1071`：检查 slot/token 冲突时排除 `_beside(...)`，允许不同 `tab_id` 并存。
    - `src/selkies/webrtc_signaling_server.py:801-833`：`_resume_locked` 依据 `resume_key` 恢复原 session。
- **验证说明**：
    在 `.scratch/test_signaling_experiment.py` 中使用 `MockWs` 对 `WebRTCPeerManagement.hello_peer` 执行握手函数级单测：
    - 控制器 1 (`tab-111`) 与控制器 2 (`tab-222`) 同时成功注册，互不驱逐；
    - 相同 `tab_id` 再次握手精准触发旧连接 evict (code 4001, reason: `Superseded by a new connection for this player slot.`)；
    - 会话 hold 后携带原 `resume_key` 握手成功恢复 peer id 并接收 `RESUMED` 帧。
    - **边界说明**：本实验仅覆盖信令状态机与握手逻辑，非真实 WebSocket 网络或媒体黑盒。

### 2.2 共享编码器调帧与 display_owner 机制（第 9 章，第 18 章第 9, 10 项）

- **判定状态**：`[仅源码证据]`
- **源码依据**：
    - `src/selkies/webrtc_mode.py:1694-1697`：定义 `OWNER_ONLY_PREFIXES = ("SETTINGS,", "r,", "s,")` 与 `STREAM_VERB_PREFIXES = ("_arg_fps,", "vb,", "ab,", "_crf,", "_rc,")`。
    - `src/selkies/webrtc_mode.py:1720-1728`：
        ```python
        tab = self._peer_tabs.get(conn_id)
        owner = self._display_owner_tabs.get(display_id)
        if tab and owner and tab != owner:
            peer = self.rtc_app.peer_connections.get(conn_id) if self.rtc_app else None
            if msg.startswith("SETTINGS,"):
                return self._settings_beside_owner(msg, display_id, peer)
            if peer is not None and msg.startswith(self.OWNER_ONLY_PREFIXES):
                peer.setdefault("held_owner_messages", {})[msg.split(",", 1)[0]] = msg
            return None  # 非 owner 的 STREAM_VERB_PREFIXES (含 _arg_fps) 直接被忽略丢弃！
        ```
    - `src/selkies/webrtc_mode.py:1812-1837`：原 owner 离开后触发 `_succeed_display_owner`，将 display 主权转移给 oldest controller。
- **分析结论与架构边界**：
    - 官方底层 `_display_owner_tabs` 是针对\*\*显示配置与流参数（分辨率、DPI、FPS、比特率）\*\*的主权控制，**并非业务层输入独占租约**。所有连接的键鼠输入依然并行送入 X11（行 1718）。
    - 该机制与 v2 架构中“无独占输入租约”并不冲突；但要求全局帧率与固定分辨率调整**必须由 StreamAgent 统一接管**（调用内部 API 或以 display_owner 身份下发），禁止前端任意非 owner 连接直接向 DataChannel 投递 `_arg_fps`。业务层切勿恢复任何独占输入租约。

### 2.3 多页面输入与 IME 机制（第 1.2(8) 节、第 8.3 节、第 18 章第 8 项）

- **判定状态**：`[仅源码证据]`
- **源码依据**：
    - 键鼠输入消息直接由 `webrtc_mode.py:1718` 转发至 `input_handler.on_message`，多连接事件到达 X11 队列自然交织。
    - IME 方面，`addons/selkies-web-core/lib/input.js:2553-2575` 在 `compositionend` 发送 `co,end,<text>`。
    - 服务端 `src/selkies/input_handler.py:9571-9590` 接收 `co,end` 后调用 `_type_text_xtest(text)`（行 6079-6124），通过 XTEST 在 X11 keymap spare keysym overlay 插槽动态绑定字符生成击键，不走剪贴板粘贴模拟。真实键鼠与 IME 打通需真测环境。

### 2.4 WebRTC UDP mux 单端口多会话（第 10.1 节，第 18 章第 12 项）

- **判定状态**：`[仅源码证据]`
- **源码依据**：
    - `src/selkies/settings.py:967` 定义 `webrtc_udp_mux_port`。
    - `src/selkies/webrtc_engine.py:1652-1677` 初始化 `UdpMux` 并监听单一端口。
    - `src/selkies/ice/ice.py:509-512` 源码明确规定在共享 socket 下，会话隔离完全依赖 8 字符的 `local_username`（ufrag）。
- **降级说明**：此前实验仅读取默认配置对象，未实际绑定物理端口及分流真实 UDP 包，故严格定级为源码证据，待 Spike 容器真测。

### 2.5 coturn、relay-only 与 ICE Restart（第 10.5, 10.6 节，第 18 章第 14 项）

- **判定状态**：`[仅源码证据 / 设计矛盾]`
- **源码依据**：
    - **TURN REST HMAC**：`src/selkies/webrtc_ice_config.py:209-290, 565-580` 原生支持生成 HMAC 短期凭证。
    - **relay-only 约束**：前端 `turn_switch=true` 强制 `iceTransportPolicy=relay` (`webrtc.js:1189-1194`)；`src/selkies/ice/ice.py:500-503` 规定 `ice_lite` 严禁配置 TURN，在 `test_webrtc_protocol_rules.py` 中规则验证通过（抛出 ValueError）。
    - **ICE Restart 未满足**：
        - v2 plan 10.6 节要求：“在现有凭证到期前 6 小时执行 ICE 重启，切换到新凭证”。
        - 检索官方代码库，`restart_ice`、`iceRestart`、`ice_restart` 均无协议支持。
        - `src/selkies/webrtc_engine.py:1578-1580` 明确记录官方设计约束：
            ```python
            # Live sessions deliberately keep their established ICE: their TURN allocations
            # stay valid, and forcing an ICE restart on refresh would drop working streams.
            ```
            官方 `update_rtc_config()`（行 1573-1589）仅用于新创建连接，对既有会话不提供 ICE Restart。
- **分析结论与后续路径**：
    v2 plan 的定期 ICE Restart 属于**计划要求未被官方协议栈满足**。后续实施路径须二选一由用户决策：
    1. **方案 A（扩展实现）**：在 vendored `src/selkies/webrtc` 与 `ice` 补充标准的 ICE restart 重协商协议支持，并通过真网实测验证；
    2. **方案 B（遵循官方策略）**：用户决策调整计划，长连接维持既有 coturn allocation 活跃心跳，凭证轮转仅作用于新建连接。

______________________________________________________________________

## 3. 需真测项目（第一阶段 Spike 容器环境清单）

以下项目已有源码级证据，但需在具有 Xvfb、PulseAudio、pixelflux 与 Chrome 的容器集成环境中进行黑盒验证：

1. **多页面同时输入真实击键交织与 X11 响应**（第 18 章第 8 项）；
2. **UDP mux 单端口下真实 WebRTC 媒体流与多客户端分流**（第 18 章第 12 项）；
3. **真实 coturn relay-to-relay 媒体与数据通道打通**（第 18 章第 14 项）；
4. **中文输入法 XTEST 动态映射打通**（第 18 章验收项）。

## TURN鉴权与relay低层补充

主控已独立重跑真实coturn：有效REST HMAC短期凭证实际Allocate成功；坏密码/过期凭证均明确401；两个独立allocation双向随机UDP经relay转发后字节匹配。补强版本要求两负例均401，任意网络错误不算通过，exit0。源代码code/turn_auth_probe.py，事实见d009。

此实验调用固定官方Selkies ICE TURN底层实现、手工执行真实ChannelBind；不是伪造服务器或mock，但也没有运行RTCPeerConnection/DTLS/SRTP/媒体。因此不能把relay UDP PASS改称WebRTC relay-only或ICE restart PASS。公网、双端relay媒体、同PC新ICE凭证/分配仍验证中。

复现依赖固定2.1.0源码和独立运行coturn。将该脚本复制到隔离scratch/probe_work/，将固定源码放scratch/selkies_src/src；在容器挂该scratch为/probe，使用支持依赖的cbrowser-spike-runtime-stream:test镜像：

```bash
python3 /probe/probe_work/turn_auth_probe.py <TURN内部地址:端口> /probe/probe_work/turn_secret.txt
```

secret文件仅本地私有、权限0600，不提交或打印。TURN监听只在专属隔离网络/localhost，示例不提供任何默认有效凭证；公网测试须使用用户提供的正式测试配置。主控原始运行使用专属cbrowser-spike-turn-net的172.29.0.10:3478，未修改该网络或其它会话；重跑命令必须使用自己的测试coturn，勿覆盖现有服务。

## 同PC标准SDP跨ICE代补充实验

主控增加code/datachannel_restart_probe.py：保持PC、SCTP、DTLS、外层ICE及DataChannel对象，在双方创建新ICE gatherer，通过原SDK标准Offer/Answer交换新ufrag/password，三次关闭旧代后各10条独特DataChannel payload完整收到，旧Connection.send明确ConnectionError。真实Docker运行exit0，事实d010。

稳定_recv共享队列与每代真实recv pump使DTLS不再永久等待旧socket；稳定_send在新代连接后切换。首轮失败显示setLocalDescription会在新Answer之前用旧remoteIce启动连接，需要显式等待新远端凭证，不能只重置\_\_start。此为固定SDK私有接口实验，不修改安装包，不等于官方原生支持。

```bash
mkdir -p .scratch/ice_generation_probe
cp docs/spikes/s002_selkies_protocol/code/datachannel_restart_probe.py .scratch/ice_generation_probe/
docker run --rm --name cbrowser-spike-ice-generation --mount "type=bind,src=$PWD/.scratch/ice_generation_probe,dst=/probe,readonly" --entrypoint python3 cbrowser-spike-runtime-stream:test /probe/datachannel_restart_probe.py
```

范围严格限本机host UDP和DataChannel；最终Chrome/Selkies真实音视频、单端口mux、双relay候选及TURN新凭证仍须完整实验。另一次尝试直接用通用未编码AudioStreamTrack/VideoStreamTrack在原生SDK做媒体对照失败，因为该fork只接收预编码EncodedPacket、RemoteStreamTrack也不负责解码；失败日志保留，不归咎为ICE适配失败。真实媒体需接入官方pixelflux/pcmflux或真实编码fixture。
