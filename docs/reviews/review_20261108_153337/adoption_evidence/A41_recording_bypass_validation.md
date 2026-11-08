# A41 借鉴有界编码包录制旁路，先验证免重编码能力

- 工作树：分支 `adopt/w5-research`，base `main@7ae1e26`
- 决策来源：`docs/reviews/review_20261108_153337/adoption_decision.md` A41（726–748 行）、R18（925–934 行）、证据目录 W7–W11/C2/C3/C5/P2/P3（44–68 行）、「实施组织与验证要求」（936–957 行，950 行）
- 性质：**中立验证 / 技术可行性研究**。不是已选定录制架构、不是完整会话录像产品、不是输入重构。采纳范围为「复用已编码音视频、非阻塞有界录制旁路」的架构原则及隔离技术验证（732、735 行）；用户提出的是未来录像需求评估，本次没有立项或授权完整会话录像产品，也不默认开启录音 / 录像（732 行）。
- 结论类型：**静态证据 + NOT_RUN + 条件方案**。前一门未通过时，后续拓扑只能列为条件方案，不能登记成当前能力或绕过失败继续写生产实现（736 行）。不声称 PASS。
- 交付：只新增本报告；未修改任何生产源码；A41 **未记完成**。

## 0. 状态标注约定与硬边界

|标注|含义|
|---|---|
|静态证据|只读核验本仓源码、锁定 wheel（Python `zipfile` 内存提取）、`uv.lock`、Dockerfile、blueprint 得到的事实；**非运行通过**|
|NOT_RUN|本轮未执行，逐项给出具体原因（环境缺失或授权边界）|
|条件方案|仅在前置门通过或待确认契约满足后才成立的候选设计，未验证、非当前能力|

硬边界（须遵守）：

- 本机无真实 WebRTC 媒体 / 录制运行环境；**不执行真实录制、性能、慢盘 / 溢出实验**，所有未跑项标 NOT_RUN + 具体原因；严禁把静态源码核验写成运行通过或标 PASS。
- `produce_data` 是 Selkies 模块内回调，**不等于对外录制 API**（734 行）；不把它当成稳定录制订阅接口。
- 不预设任何候选胜出；不承诺零 CPU / 零复制 / 零延迟、不按未验证的 GStreamer appsink 或固定下载子目录直接接线、不把 48 kHz 采样率当已编码证明（R18 933 行）。
- 不把「录制是否计作独立消费者」、帧率 / 音频 / CPU 配额、生命周期新契约预设为已确认（738 行）。
- 不触碰用户真实数据 / 剪贴板 / Profile；只用隔离 Profile、测试字符串、测试剪贴板；不因研究修改真实 Profile 或生产数据（747 行）。
- 未决产品条件（谁可录制、持续或仅观看、是否录音、保留 / 配额策略）仍待正式立项，本报告不把它们预选为可上线功能（748 行）。

## 门 1——稳定接入

决策 737 行：定位固定版本实际编码帧与 Opus 回调，核对 codec / 参数集 / pts / dts / time_base、原生 buffer 所有权和可用接入机制；`produce_data` 内部可见只证明数据存在，不能作为已稳定订阅；需要扩展依赖时给出维护 / 构建 / 锁定 / 回滚方案。

### 1.1 静态证据：编码帧与音频回调位置

|项|事实|来源|状态|
|---|---|---|---|
|管线拓扑|docstring：pixelflux 在自有 capture thread 编码 H.264，pcmflux 在自有 audio thread 编码 Opus，两者经 `call_soon_threadsafe` 回传 zero-copy buffer，交给 transport 的 `produce_data` 打包 RTP；pipeline 自持单调 pts 时钟（video 90 kHz `CLOCK_MONOTONIC` 锚点，audio epoch offset），`start_media_pipeline` 只开有消费者请求的 capture|wheel `selkies/webrtc_media_pipeline.py:22-45`|静态证据|
|视频编码帧回调|`_screen_capture_callback`：frame 拥有原生 buffer，以 zero-copy `memoryview` 跳过 `STRIPE_HEADER_LEN` 下发；keyframe 由 header 类型字节判定；pts 为 90 kHz、取 `frame.capture_ns`（`CLOCK_MONOTONIC`、pipeline 锚点），严格递增；`timing` / `dependency` / `codec` / `anchor` 随帧传递；`call_soon_threadsafe(functools.partial(self.produce_data, data_bytes, pts, "video", keyframe, ...))`；`produce_data` 把它包成 `EncodedPacket` 并保留引用使 frame 存活|wheel `webrtc_media_pipeline.py:616-670`（C3 616-670）|静态证据|
|Opus 音频回调|`audio_capture_callback`：pcmflux 的 Opus frame 以 zero-copy `memoryview` 下发，pts 用连续音频时钟 `_audio_rtp_pts`，`call_soon_threadsafe(self.produce_data, data_bytes, pts, kind)`，`kind` 为 `audio` / `audio_stereo`|wheel `webrtc_media_pipeline.py:970-999`（C3 970-999）|静态证据|
|`produce_data` 定义|`self.produce_data` 是 `Callable[..., None]` 实例属性，默认 lambda 仅 `logger.warning("unhandled produce_data")`；docstring 明确 "The transport wires `produce_data` ... before starting the pipeline"|wheel `webrtc_media_pipeline.py:250-252`、`:152-154`、`:170`|静态证据|
|transport 接线|`self.media_pipeline.produce_data = self.rtc_app.consume_data`；多显示器时闭包包装同一 `consume_data` 并带 `_did`|wheel `selkies/webrtc_mode.py:705`、`:2593-2597`|静态证据|
|`consume_data`|同步 sink；按 `display_id` 取 graph；video 构造 `EncodedPacket(buf, pts, Fraction(1, 90000), keyframe, timing, dependency, codec, anchor)` → `video_bridge.set_data`；audio 构造 `EncodedPacket(buf, pts, Fraction(1, 48000))` → `audio_bridge.set_data`；docstring 明确 `EncodedPacket` 引用 encoder buffer 不复制、packer 以 memoryview 遍历、无整帧拷贝|wheel `selkies/webrtc_engine.py:1522-1574`、`:1559`、`:1569`|静态证据|
|RTP 发送侧|`_next_encoded_frame` 读 `__track.recv()` → `encoder.pack(data)` → `RTCEncodedFrame(payloads, timestamp, ..., data.data)`；注释明确 "Tracks serve frames pixelflux/pcmflux have already encoded; the sender only packs them into RTP payloads ... no encode runs here"|wheel `selkies/webrtc/rtcrtpsender.py:1089-1123`（C3 1088-1123）|静态证据|

### 1.2 静态证据：codec / 参数集 / pts / dts / time_base / 原生 buffer 所有权

|项|事实|来源|状态|
|---|---|---|---|
|`EncodedPacket`|预编码媒体样本；`__slots__ = data, pts, dts, time_base, keyframe, timing, dependency, codec, anchor`；`dts = pts`；`data` 是 encoder 自身 buffer（buffer-protocol），**referenced and never copied**，packer 用 `memoryview(packet.data)`，仅 RTP payload 才 materialize bytes；`codec` 为 MIME；`keyframe` / `anchor` 语义见 docstring|wheel `selkies/webrtc/codecs/base.py:39-81`（C3 39-78）|静态证据|
|`Encoder.pack`|抽象接口「Packs frames a pixelflux/pcmflux encoder has already produced into RTP payloads. Encoding itself lives in those libraries, not here」|wheel `webrtc/codecs/base.py:90-98`|静态证据|
|H.264 打包|`convert_timebase(packet.pts, packet.time_base, VIDEO_TIME_BASE)`；Annex-B start code `b"\x00\x00\x01"`、zero-copy NAL walk over memoryview、STAP-A / FU-A packetize；`keyframe = any(nal[0] & 0x1F in (5, 7) ...)`（IDR / SPS）；`VIDEO_TIME_BASE = Fraction(1, VIDEO_CLOCK_RATE)`|wheel `webrtc/codecs/h264.py:54-64,189-249,267-273`、`webrtc/mediastreams.py:42`|静态证据|
|Opus 打包|`TIME_BASE = Fraction(1, SAMPLE_RATE)`；`convert_timebase(packet.pts, packet.time_base, TIME_BASE)`；`return [bytes(packet.data)]`，`keyframe=False`；即已编码 Opus 直接作 RTP payload、不编码|wheel `webrtc/codecs/opus.py:41,50-55`|静态证据|
|codec 候选集|`webrtc/codecs/` 含 av1 / g711 / g722 / h264 / h264_skip / h265 / opus / red / vp9 / vpx；但 pixelflux 实际编码由 `set_encoder` / `on_encoder_demoted` 决定，W11 只限定 Weblink 原生录制选择 H.264/H.265，不能据此推断任意 VP8 管线都有同样录制能力（56 行）|wheel `webrtc/codecs/` 成员、`webrtc_media_pipeline.py:254-256,417`、W11|静态证据 + 条件方案|

### 1.3 可用接入机制（三种，均为条件方案，是否采用由结果决定）

|机制|说明|代价 / 未决|状态|
|---|---|---|---|
|M1 预编码样本层 hook `produce_data`|在 `MediaPipelinePixel.produce_data` / `rtc_app.consume_data` 处加第二消费者；当前为**单一 sink**、由 transport 启动时赋值（`webrtc_mode.py:705`、`:2593`），无注册 / 多消费者 API|私有属性单 sink，须 fan-out；类似 `x11_keymap.py` 的私有 ABI 适配风险；稳定性未验证|条件方案 / NOT_RUN|
|M2 扩展 `webrtc_mode.py` / `webrtc_engine.py`|在 `consume_data` 内把 `EncodedPacket` 旁路给录制消费者|改上游源码 → 派生依赖，须 §1.4 交付方案|条件方案 / NOT_RUN|
|M3 RTP 层订阅|订阅 `Encoder.pack` 输出 / `RTCEncodedFrame.payloads`（已是 RTP payloads）|须验证重排 / 去包 / 时钟及完整样本恢复（门 3）；不能把已有 RTP bytes 直接当文件内容（R18 931 行）|条件方案 / NOT_RUN|

### 1.4 需要扩展依赖时的维护 / 构建 / 锁定 / 回滚方案（737 行）

决策 689 行等价要求：本仓 `scripts/vendor_selkies_web.py` 只从锁定 wheel 提取前端资源，`uv.lock` / `requirements.txt` / Stream Dockerfile 消费上游包，**没有 Selkies 服务端源码构建与派生 wheel 发布流水线**；不假设本仓已有派生流水线（737 行）。逐项均为**条件方案 / NOT_RUN**（授权边界：本轮不执行构建或外部发布，956 行）：

|交付项|要求|状态|
|---|---|---|
|源码固定提交|pinned 上游源码提交与补丁基线|条件方案 / NOT_RUN|
|可重现构建|源码 → wheel 的确定性构建脚本与产物校验|条件方案 / NOT_RUN|
|包分发 / 哈希|派生 wheel 分发位置、SHA256、与 `uv.lock` / `PINNED_WHEEL_SHA256` 一致|条件方案 / NOT_RUN|
|依赖锁|`uv.lock`（`selkies==2.2.1` 见 `:1317-1344`）、`requirements.txt:69` 同步到派生版本与哈希|静态证据（现状）+ 条件方案|
|服务端安装与前端资源同源|Stream Dockerfile `pip install` 与 `vendor_selkies_web.py` 提取前端资源来自同一派生版本|条件方案 / NOT_RUN|
|许可证|固定 wheel `webrtc/codecs/base.py:1-32` 为 MPL-2.0 + aiortc / BSD 版权头；W13 记录 Weblink 为 MIT（58 行）|静态证据（现有）|
|升级 / 回滚|升级复核私有 ABI / 协议字符串（参照 `stream_runtime.md:47`）、可回退完整旧镜像 / 挂载|条件方案 / NOT_RUN|

**门 1 判定**：静态证据确认「预编码 H.264 / Opus 样本存在于 `produce_data` / `EncodedPacket` 层，且 `Encoder.pack` 只打包不编码」；但「稳定对外录制订阅接口」不存在——`produce_data` 是模块内 `Callable` 属性、单 sink、由 transport 启动接线（734 行）。接入机制是否稳定、是否需改依赖 **NOT_RUN**（需运行探针 / 依赖扩展实验）；只完成回调探针不能报完整独立录制可用（744 行）。**门 1 未通过（稳定接入未证明）**，后续拓扑只能列为条件方案。

## 门 2——捕获存续

决策 738 行：第一组实验严格保持现行 Viewer 策略，只在已有活跃流时证明旁路封装；无 Viewer / 全后台样本停止是预期观察，不得报录制完整。

### 2.1 静态证据

|项|事实|来源|状态|
|---|---|---|---|
|无活跃 Viewer 暂停捕获|`policy.py` Rule 1：`active_peers = [pid for pid, st in self.peers.items() if st.get("active")]`；`has_visible = len(active_peers) > 0`；`if not has_visible` → 记录 `pause_screen_capture` / reason `all_peers_inactive_or_gone`，调用 `p.pause_screen_capture()`，置 `_is_paused = True`，`return`|`src/backend/cbrowser/stream_agent/policy.py:544-573`（C5 / 734 行指向 554-573）|静态证据|
|恢复策略|Rule 2：有活跃 peer 但 capture 暂停 → 先 `set_framerate(8.0)` 再 resume|`policy.py:575-584`|静态证据|
|pipeline 启停语义|docstring：pipeline 是 display 的 media graph，两路 capture 逐个启停；`pause_screen_capture` / `pause_audio_capture` 停对应 capture 而 pipeline 保持运行；「a session whose policy starts video or audio off never captures what nobody receives」|wheel `webrtc_media_pipeline.py:33-38`|静态证据|

### 2.2 判定与待确认契约

- 无 Viewer / 全后台时样本停止是**预期观察**，不得报录制完整（738 行）。本仓也没有把录制注册为捕获消费者（734 行）；C3 / C5 证据一致（61、63 行）。
- 「录制是否计作独立消费者」、帧率 / 音频 / CPU 配额、生命周期新契约须**先提出并确认**，不在本报告预设（738 行）。
- 录制生命周期不由某 Viewer 对象拥有，**不等于**捕获可脱离所有 Viewer 持续（738 行）；条件目标拓扑（742 行）中「无消费者捕获暂停、低权限 Stream、媒体不经 API 转发」在正式变更前保持。
- 第一组实验（保持现行 Viewer 策略、仅在已有活跃流时证明旁路封装）：**NOT_RUN**（本机无真实 WebRTC 媒体 / Viewer 运行环境；授权边界禁止真实录制实验）。

**门 2 判定**：静态证据确认现行策略；「独立消费者」契约未定，**门 2 未通过**。后续门 3 / 4 / 5 与条件目标拓扑只能列为条件方案（736 行）。

## 门 3——隔离旁路

决策 739 行：**只有门 1 / 2 条件满足后**才验证；队列或 worker 不被当作已有代码落点。本轮门 1 / 2 未通过，本节只能列**条件方案**，不登记成当前能力。

|条件方案要素|要求|对照证据|状态|
|---|---|---|---|
|拓扑|预编码样本 → 独立有界队列 → 封装写入 worker；**只是候选**，非现有代码落点|739 行|条件方案|
|包数 / 字节上限|采用包数 / 字节数双重上限；W7 的 32 包 / 8 MiB 是上游策略，不直接成为本项目默认（52 行）|W7|条件方案|
|非阻塞|`try_send` 不等待录制消费者，不阻塞捕获 / 发送；溢出或慢盘只失败录制|W7、739 行|条件方案|
|RTP 前样本|门 1 的 `produce_data` / `EncodedPacket` 属 RTP 前预编码样本，可避免去包|静态证据 §1|条件方案|
|仅有 RTP 时|若只能取到 RTP payloads（M3），须验证重排 / 去包 / 时钟及完整样本恢复；R18 明确不能把已有 RTP bytes 直接当文件内容（931 行）|C3、R18|条件方案 / NOT_RUN|
|故障隔离|溢出、慢盘、writer 崩溃只失败录制，不影响 Viewer 媒体|739、746 行|条件方案 / NOT_RUN|

**门 3 判定**：条件方案（门 1 / 2 未通过）；全部运行验证 **NOT_RUN**。

## 门 4——容器与音频

决策 740 行；本轮门 1 / 2 未通过，封装与音频运行验证只能列为条件方案，但 codec / 术语的静态证据如实给出。

|项|静态证据 / 判定|来源|状态|
|---|---|---|---|
|按实际 codec 决定容器|video 为 pixelflux H.264（docstring `:24`、H.264 Annex-B packer），audio 为 pcmflux Opus（`:25`、`opus.py`）；MKV / MP4 候选须按实际 codec 决定；P3 指出 matroskamux / mp4mux 输入要求与 codec 支持不同，不是改扩展名；W11 不能推断任意 VP8 管线都有同样录制能力|wheel 源码、P3（66 行）、W10（55 行）、W11（56 行）|静态证据 + 条件方案|
|关键帧起始|`h264.py:273` keyframe 为 NAL 5 / 7；`webrtc_media_pipeline.py:647-649` keyframe 来自 header；W7 从关键帧开始|wheel 源码、W7|静态证据 + 条件方案 / NOT_RUN|
|参数集 / NAL framing|`h264.py:64,228-249` 为 Annex-B start-code + zero-copy NAL walk；W10 证明参数集归一与 NAL 长度前缀转换；MP4 需 AVCC 长度前缀与 SPS / PPS 参数集；W10 仅归因参数集 / NAL 转换，全链封装须结合 W7–W9（55 行）|wheel 源码、W10|静态证据 + 条件方案 / NOT_RUN|
|音视频同步|video pts 90 kHz `CLOCK_MONOTONIC` 锚点、audio 连续时钟 epoch offset（`webrtc_media_pipeline.py:28-31`）；同步与时间戳正确性须验证|wheel 源码|条件方案 / NOT_RUN|
|8 / 30 变帧率|`policy.py:578` 恢复时 `set_framerate(8.0)`；docstring 说明 fps 变化不回退 pts（`:28-31,630-631`）；变帧率封装须验证|本仓 + wheel 源码|静态证据 + 条件方案 / NOT_RUN|
|静止与静音间隙 / 代次切换|pixelflux damage-gated、capture restart 时 pts 锚点保持；录制须处理间隙与代次切换、退出收尾|wheel `webrtc_media_pipeline.py:33-38,628-634`|条件方案 / NOT_RUN|
|encodedAudio 分支|复用已编码 Opus 本身不编码（`opus.py:53-55`、`base.py:90-98`）；W8 / W9 的 encodedAudio 可复用原编码|wheel 源码、W8（53 行）、W9（54 行）|静态证据|
|PCM → Opus 术语|PCM → Opus 是对该 PCM 的**首次编码**，若为录像另开则是新增 CPU 编码成本，不称「把编码音轨重新编码」；混音 / 重采样 / 转换原有压缩音轨需另列成本；从已存在压缩音轨解码再编码才属重编码（W9、R18 932 行、979 行修订）|W9、R18|静态证据（术语）|
|R18 拒绝的字面方案|如实保留：不承诺零 CPU / 零复制 / 零延迟；不按未验证 GStreamer appsink（P2 仅说明 tee 分支需独立 queue，不作为当前 Selkies 已有 appsink 证据）或固定下载子目录直接接线；不把 48 kHz 采样率当已编码证明；默认再抓屏解码再编码不能包装成免重编码方案（933 行）|R18、P2（65 行）|静态证据（如实保留）|

**门 4 判定**：codec / 音频术语有静态证据；封装、同步、变帧率、间隙与代次切换、CPU 成本测量均为**条件方案 / NOT_RUN**（门 1 / 2 未通过）。

## 门 5——受管存储

决策 741 行、C2（60 行）：当前 Stream 无 `/exchange`，Artifact 补登不扫描 recordings 子目录。

### 5.1 静态证据

|项|事实|来源|状态|
|---|---|---|---|
|Stream 无 `/exchange` / 无可写 staging|`stream_volumes` 仅返回 gate（ro）、x11 socket（ro）、xauth（ro）、pulse（ro）、secret（ro）、selkies 凭据（ro）；**无 `/exchange`、无任何可写数据挂载**。`/exchange/downloads`（rw）只出现在 `browser_volumes`|`src/backend/cbrowser/supervisor/volume_spec.py:47-66`、`:33-34`|静态证据|
|Artifact 容器路径与单写者|容器内路径固定为 `/exchange/uploads` 与 `/exchange/downloads`；CDP 下载完成事件经 `DownloadArtifactForwarder` 翻路径，经内部 Supervisor RPC 提交 API；API 侧按 `(profile, sha256, storage_path)` 去重，单写者登记 `kind=download`|`docs/blueprint/artifacts.md:15,31,34-35`|静态证据|
|补登只扫直接子文件|Agent 启动 / 终端重放 / CDP 会话重建时扫描 `/exchange/downloads` 的**直接子文件**一次，为缺少完成事件的已完成文件生成补登事件；**Artifact 子目录不参与扫描** → 不自动接纳 `recordings` 子目录|`docs/blueprint/artifacts.md:33`|静态证据|
|配额 / 实例围栏|单文件 256 MiB、每 Profile 200 个 / 2 GiB，磁盘保留 16 MiB；报告实例 `runtime_instance_id` 须为可信实例，未知 / 伪造实例在触碰任何文件前 `rejected`；跨 Profile 返回 404；删除为 DB 意图驱动的两阶段可恢复操作|`artifacts.md:24,36,23,38-41`|静态证据|

### 5.2 候选输出（条件方案）

|要素|要求|状态|
|---|---|---|
|最小 staging 挂载 / 写入者|由 Supervisor 分配最小必要 staging 挂载与写入者（当前 `stream_volumes` 全 ro，须新契约）|条件方案 / NOT_RUN|
|封装校验后登记|完成并封装校验后，经受限事件 / RPC 交 API 单写者登记；不能直接把子目录当作现有自动登记入口（741 行）|条件方案 / NOT_RUN|
|路径 / 实例 / 配额围栏|保留路径围栏、可信实例校验、配额；不能绕过 `(profile, sha256, storage_path)` 去重与 404 隔离|条件方案 / NOT_RUN|
|完成事件幂等|与 `artifacts.md:34` 去重语义一致；Artifact 读取 / 删除按 `:27,38-41` 验收|条件方案 / NOT_RUN|

**门 5 判定**：静态证据确认「Stream 无 `/exchange`、Artifact 不扫描 recordings 子目录」；候选交付链为**条件方案**（门 1–4 未通过），全部运行验证 **NOT_RUN**。

## 条件目标拓扑（742 行）

在已验证接入机制及捕获消费者契约的前提下，单 Profile 编码样本可同时服务 RTP 与一个受管录制旁路；这是**研究待证设计，不是固定依赖现有功能**。无消费者捕获暂停、低权限 Stream、媒体不经 API 转发等现行契约在正式变更前保持。状态：**条件方案**。

## 5 道门逐门状态汇总

|门|静态证据|判定|后续门处理|
|---|---|---|---|
|门 1 稳定接入|编码帧 / Opus 回调、`EncodedPacket` buffer 所有权、单 sink 接线已定位|**未通过**（稳定接入未证明；`produce_data` 非对外录制 API；接入稳定性 / 依赖扩展 NOT_RUN）|门 2–5 只能列条件方案|
|门 2 捕获存续|`policy.py:544-573` 无活跃 Viewer 暂停捕获已定位|**未通过**（独立消费者 / 配额 / 生命周期契约未确认；有 / 无 Viewer 实验 NOT_RUN）|门 3–5 只能列条件方案|
|门 3 隔离旁路|RTP 前样本存在（静态）|条件方案（门 1 / 2 未通过）；有界队列 / 非阻塞 / 溢出 / RTP 恢复 NOT_RUN|仅条件方案|
|门 4 容器与音频|codec / 参数集 / NAL framing / 编码术语已定位|条件方案 + 静态证据；封装 / 同步 / 变帧率 / CPU 成本 NOT_RUN|仅条件方案|
|门 5 受管存储|Stream 无 `/exchange`、Artifact 不扫子目录已定位|条件方案 + 静态证据；最小挂载 / 受限 RPC / 幂等 NOT_RUN|仅条件方案|

## 技术验收清单（743–747 行逐项）

|验收项|状态|说明|
|---|---|---|
|接入机制是否稳定 / 是否需改依赖；只完成回调探针不能报完整独立录制可用|静态证据 + NOT_RUN|门 1：单 sink 内部接线为静态事实；稳定性 / 依赖扩展未跑（744 行）|
|有 / 无 Viewer 两类实验差异|静态证据 + NOT_RUN|门 2：`policy.py:544-573`；无 Viewer 样本停止为预期观察，不报录制完整（738、744 行）|
|是否增加新视频或音频编码（用编码器 / 采集调用证据判断）|静态证据 + NOT_RUN|`Encoder.pack` 不编码、`opus.py` 已编码 Opus 直接打包、encodedAudio 复用不编码；PCM → Opus 另开是新增 CPU 成本；运行测量 NOT_RUN（745、932 行）|
|产物独立解复用 / 解码与时间戳正确；不依赖「免重编码」口号推断性能|NOT_RUN|门 4；本机无录制运行环境（745 行）|
|同场景 CPU / 内存 / 队列 / 磁盘与 Viewer 媒体指标|NOT_RUN|门 4；无录制 / 性能运行环境（746 行）|
|慢 / 满盘、溢出、writer 崩溃、Stream 替换、codec / 分辨率变化、退出收尾；失败片段标 partial / failed，不能宣称完整审计|NOT_RUN|门 3 / 4；无故障注入环境（746 行）|
|Profile 授权隔离、最小挂载、完成事件幂等与 Artifact 读取 / 删除；不因研究修改真实 Profile / 剪贴板 / 生产数据|静态证据 + NOT_RUN|门 5：`volume_spec.py`、`artifacts.md` 为静态事实；运行验证 NOT_RUN（747 行）|

## 交付与未决产品条件

- 本报告交付：固定版本接入缺口（门 1 单 sink / 无对外录制 API）、候选实现（M1 / M2 / M3、门 3 有界旁路、门 5 受管交付链）、实验结果（本轮全部 NOT_RUN）、依赖 / 捕获 / Artifact 契约变更清单（§1.4、门 2、门 5）及结论（5 道门汇总）。
- 未决产品条件仍待正式立项（748 行）：谁可录制、持续或仅观看、是否录音、保留 / 配额策略。本报告**不把这些条件预选为可上线功能**，不默认开启录音 / 录像（732 行）。
- 「复用已编码音视频」原则成立不等于「免重编码 = 零 CPU」；R18 拒绝的是不成立的字面前提，不否定未来采用已验证封装组件或其它可满足需求的实现（934 行）。

## NOT_RUN 清单与原因

|项|原因|
|---|---|
|接入稳定性探针 / `produce_data` fan-out / 依赖扩展实验|本机无真实 WebRTC 媒体管线；授权边界禁止改依赖 / 构建 / 发布；门 1 未通过|
|有 Viewer 第一组旁路封装实验、无 Viewer 预期观察复核|本机无真实 Viewer / 录制运行环境；授权边界禁止真实录制实验（738、954 行）|
|有界队列、非阻塞、溢出 / 慢盘 / writer 崩溃故障注入|门 1 / 2 未通过，后续只能列条件方案；无故障注入环境（736、746 行）|
|MKV / MP4 封装、关键帧起始、参数集 / NAL framing、音视频同步、变帧率、静止 / 静音间隙、代次切换、退出收尾|无真实录制产物与解复用 / 解码环境（745、746 行）|
|CPU / 内存 / 队列 / 磁盘与 Viewer 媒体指标同场景对比|无性能实验环境；不承诺零 CPU / 零复制 / 零延迟（933 行）|
|最小 staging 挂载、受限事件 / RPC 登记、完成事件幂等、Artifact 读取 / 删除、Profile 授权隔离|门 1–4 未通过；不触碰真实 Profile / 生产数据（747 行）|
|派生包源码固定 / 可重现构建 / 分发 / 锁 / 升级 / 回滚|授权边界：本轮不执行构建或外部发布（737、956 行）|

## 验收标准对照

|决策验收要求|状态|依据|
|---|---|---|
|门 1 稳定接入：定位编码帧 / Opus 回调、codec / 参数集 / pts / dts / time_base / buffer 所有权 / 接入机制；`produce_data` 非对外 API；扩展依赖给方案|静态证据 + 条件方案 / NOT_RUN|门 1|
|门 2 捕获存续：`policy.py:554-573`、无 Viewer 样本停止为预期观察、独立消费者 / 配额 / 生命周期契约先提出并确认|静态证据 + NOT_RUN|门 2|
|门 3 隔离旁路：有界队列 / 包数字节上限 / 不阻塞 / 溢出只失败录制 / RTP 前样本 / 仅有 RTP 须恢复完整样本|条件方案 / NOT_RUN|门 3|
|门 4 容器与音频：按实际 codec 选 MKV/MP4、关键帧、参数集 / NAL、同步、8/30 变帧率、静止静音、代次切换；encodedAudio 不编码、PCM→Opus 首次编码另列成本；R18 字面方案如实保留|静态证据 + 条件方案 / NOT_RUN|门 4、R18|
|门 5 受管存储：`volume_spec.py` 证明无 `/exchange`、`artifacts.md` 补登只扫直接子文件、最小挂载 / 受限 RPC / 单写者 / 围栏|静态证据 + 条件方案 / NOT_RUN|门 5|
|技术验收清单逐项标 NOT_RUN 或静态证据|静态证据 / NOT_RUN|技术验收清单|
|交付接入缺口 / 候选实现 / 实验结果 / 契约变更清单 / 结论；产品条件待立项、不预选为可上线功能|静态证据 / 条件方案|交付与未决产品条件|
|不承诺零 CPU、不把内部回调当稳定 API、不标 PASS、未跑实验标 NOT_RUN、不改生产源码|静态证据|§0、全文；改动自检见交付回执|
