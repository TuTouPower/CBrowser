> 范围更新：本报告保留对应实验快照及历史限制。用户随后明确豁免公网与原生Linux x86_64执行；当前有效门禁见t001/scope_adjustment.md及架构计划“执行调整”。未运行项不计为测试通过。

# Spike report

## 问题

验证第18.1–5、12项双容器 CloakBrowser、IPC/X11、MIT-SHM、音频、固定显示与 UDP mux。区分组件机制与完整 WebRTC 音视频验收。

## 成功判据

- 真实 CloakBrowser 窗口完整位于1920×1080显示内，DPR1，保留内部地址栏与标签栏。
- 同Profile跨容器XShm实际捕获；无共享IPC负例有确切拒绝原因，不把任意Docker失败当隔离通过。
- 已知音频跨容器采到非零PCM，随后仍须验证Selkies编码与Chrome接收，不能只检查sink连接。
- UDP mux需真实多连接ICE/媒体统计；端口监听、HTTP200和sendto不能替代。

## 尝试

- 原始报告 allPASS 被主控退回；独立 reviewer 亦判定不成立，见 first_review.md。原始版本吞掉音频错误，UDP无接收观察，MIT-SHM负例泛化失败原因，窗口1928×1211超出显示。
- 修正 strict run_spike.sh：严格错误传播、X11同步错误处理、pixelflux跨IPC负例、实际持续正弦波播放与PCM采样、localhost端口发布。
- 修正浏览器采用 no_viewport，保留真实UI，窗口1920×1080 at(0,0)，DOM测得DPR1。主控检查截图确认地址栏、标签栏和内容完整可见。
- 音频严格首次录音全零并断言失败；调整持续播放时序后通过，原失败日志保留，不弱化断言。
- 最终脚本经 agent、主控独立重跑、独立 Gemini 黑盒三个执行方验证。独立黑盒见 blackbox_review.md，退出码0。

## 证据

|检查|最终观察|可支持结论|
|---|---|---|
|真实浏览器与显示|Xvfb1920×1080；窗口1920×1080 at(0,0)；DPR1；UI垂直空间125px|本机arm64原型实际呈现真实浏览器UI|
|同IPC捕获|C XShmGetImage取到像素；pixelflux捕获8帧；PNG119598字节|实际XShm捕获机制通过|
|不同IPC负例|X11可访问；pixelflux Attach报Access/error_code10；C报告SHM拒绝|当前实验中未共享IPC不能使用该捕获路径；不代表全部Profile安全边界|
|跨容器音频|主控采集88200字节，83744字节非零（94.9%）；独立黑盒95.0%|PulseAudio/PCM跨容器机制通过，不证明Selkies或Chrome音频|
|网络配置|仅127.0.0.1映射HTTP18080和UDP30005；容器UDP7535监听|端口配置证据，不证明媒体分流|
|清理|专属容器、命名卷与网络已回收；镜像保留复用|未影响现有cbrowser与其他服务|

- 主控原始日志：主仓 `.scratch/v2_orchestration/root_runtime_verify.log`；独立黑盒原始日志：主仓 `.scratch/v2_orchestration/review/.scratch/runtime_reproduce/reproduce.log`。日志、截图、PCM和编译二进制不入库。
- 可重跑源码：code/ 内7项源文件；仅复用本机既有 cbrowser:latest 基线镜像，实际 cloakbrowser0.6.4/Chromium146 与 selkies2.1.0。不能据此推断其他内核二进制、CPU架构或正式镜像通过。
- Docker IPC供体必须显式 shareable，消费者使用 container:<id>；见d004。

先复制到独立 `.scratch` 再运行，防止测试数据写入文档目录。脚本独占 cbrowser-spike-runtime 前缀，禁止该前缀并发运行：

```bash
mkdir -p .scratch
runtime_probe_dir=$(mktemp -d "$PWD/.scratch/runtime_probe_XXXXXX")
cp -R docs/spikes/s001_selkies_runtime/code/. "$runtime_probe_dir/"
bash "$runtime_probe_dir/run_spike.sh"
```

## 结论

- 第18.1–3底层运行/捕获机制已有真实证据；第18.5静态窗口和显示几何通过，仍需多页面尺寸变化下确认固定显示。
- 第18.4只完成跨容器PCM子项，Selkies编码后客户端音频仍未完成。
- 第18.12只完成端口配置，真实多路媒体分流由独立media实验继续验证。
- 仍为root、无Profile级Xauthority完整防护的技术原型，不能冻结正式沙箱安全结论，AC-001仍未完成。未迁移数据、删除旧链路或切换正式服务。
- 独立初审关于镜像/编译产物保留的意见不计运行失败：均为受限实验资产，不入库；镜像按后续实验需要保留。全黑像素不必然代表捕获失败，需结合协议结果与已知场景判断。

## 是否采纳

- 决定：是，采纳已验证组件机制，不采纳完整WebRTC或正式隔离已通过结论。
- 理由：实际Docker/X11/PCM、主控重跑与独立黑盒证据一致，限制明确。
- 后续 task：t001
- 无需后续理由：不适用

## 关联 findings

- d004：Docker IPC供体必须显式shareable。
