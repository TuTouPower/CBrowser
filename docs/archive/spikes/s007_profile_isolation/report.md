> 范围更新：本报告保留对应实验快照及历史限制。用户随后明确豁免公网与原生Linux x86_64执行；当前有效门禁见t001/scope_adjustment.md及架构计划“执行调整”。未运行项不计为测试通过。

# 双 Profile IPC、X11 与浏览器音频隔离

## 问题

验证同Profile Browser/Stream共享IPC/X11与虚拟音频，不同Profile不能访问对方显示、音频及用户数据。范围为OrbStack arm64技术观察，不是完整生产安全验收。

## 成功判据

- 两组非root、只读根容器运行真实CloakBrowser，1920×1080显示/DPR1；Stream真实XShm/pixelflux至少8帧。
- Xauthority正确/错误/缺失有正负例；跨IPC XShmAttach明确BadAccess，不能据此断言普通XGetImage也被阻断。
- 实际浏览器WebAudio进入独立Pulse监视源，实际采样参数与测量一致；目标440/880Hz误差≤1%，异频/错误采样率负例拒绝。
- 不挂载其他Profile的Socket/用户数据，真实跨Profile负例失败；保留同UID Pulse绕过Cookie的机制边界。

## 尝试

- v1 data URL未编码#导致白屏，且夸大Cookie/IPC防护，拒绝。
- v2修正URL/只读与认证边界，独立19.3秒exit0，但仅paplay音源。
- v3改实际CloakBrowser WebAudio，独立17.6秒exit0；主控DFT确认声明44100时峰值404/808而目标440/880，10%容差误放行，拒绝音高结论。
- v4明确Pulse daemon/Sink/录制48000Hz，1%门禁与测量负例，独立19.1秒exit0。历史PCM缺失可静默跳测却报PASS，继续拒绝最终版本。
- v5整项替换历史文件依赖，用本轮真实48000 PCM故意声明44100做必跑拒绝校准，不提交二进制。移除未证实反指纹因果和夸大报告措辞，最终九源冻结独立复验。

## 证据

- 最终九源与作者/独立快照逐字节一致。独立纯净目录无revision_03，真实四容器完整重跑19.0秒（wall20.3秒）exit0，见independent_review_final.md；原始日志主仓gateway_review/.scratch/isolation_review_r5。
- A/B真实Chrome UI及DOM背景rgb(16,32,64)/rgb(64,32,16)，AudioContext running；低层XShmGetImage正例、pixelflux真实通过XShm捕获，跨IPC明确BadAccess。
- R4独立额外运行pactl/gst-v确认Daemon/Sink为s16le双声道48000、Chromium sink-input float32le双声道48000、GStreamer实际caps S16LE双声道48000；不是只读前端sampleRate属性或命令字符串。
- R5 A/B各96000字节、24000帧实际PCM；估频440.15/880.32Hz（误差约0.035%/0.036%），异频能量比0.000109/0.000051，低于0.01门禁。错误44100声明测得约404.39Hz，1%门禁明确拒绝；异频目标也拒绝。
- 四容器UID1000、rootfs只读、no-new-privileges，无Docker Socket/host网络/PID/发布端口；CDP内核仅127.0.0.1:9222，Xvfb无TCP监听，Stream不挂用户数据。A/B卷及哨兵互不可见。
- UID1001错误/缺失Pulse cookie拒绝，同UID1000可绕过cookie；主要边界为独立Socket卷/DAC。合法Xauth和Socket泄露时普通XGetImage仍可能读取，IPC不是完整画面防窥。

复现：先把code复制到独立scratch并保留fixture子目录，s001两个基础镜像已构建后运行python3 run_isolation_probe.py。脚本只管理cbrowser-spike-isolation资源并在finally清理。当前复现无需历史PCM，不直接在docs运行。

## 结论

- 真实共享IPC/XShm、Xauthority/专属卷、非root/只读与浏览器音频捕获技术观察通过，AC-001可据此勾选。
- 默认配置音高偏差的具体实现根因未获源码定位；只采纳显式48000全链路和实际采样结果，不采纳“反指纹补丁唯一导致”或“正确重采样改变音高”的推论。
- R4报告曾将能量比2.5e-7换成\<-130dB，错误；不采纳该数值。R5已纠正，主要证据为实际频率/能量比及采样参数。
- 该实验四容器共专属实验网桥，不证明正式每Profile网络和公网；PCM不是完整WebRTC生产证明，s004另有音视频链路证据。原生Linux x86_64/第19章容量与8小时仍未运行，不冻结架构。

## 是否采纳

- 决定：是，仅采纳隔离/显示/浏览器音频技术可行性与实测边界。
- 理由：最终独立真实重跑和必跑测量负例通过，九源一致，历史错误保留。
- 后续 task：t001
- 无需后续理由：不适用

## 关联 findings

- d011：Socket/Xauthority/IPC/Pulse边界与48000音频实证。
