> 范围更新：本报告保留对应实验快照及历史限制。用户随后明确豁免公网与原生Linux x86_64执行；当前有效门禁见t001/scope_adjustment.md及架构计划“执行调整”。未运行项不计为测试通过。

# 真实 Gateway/Agent 信令与进程重启验证

## 问题

验证第18.11/12以及Gateway重启不停止浏览器：Agent主动向独立Gateway注册，官方Selkies信令经透明隧道转发，真实Chrome双页面通过指定UDP mux接收画面；Gateway SIGKILL重启后Agent自动注册，原CloakBrowser持续运行，页面可重新建立ViewerConnection。

## 成功判据

- Gateway、Agent为独立宿主进程，不以进程内runner重建冒充进程崩溃。
- 两页真实decoded与bytes两时点增长；两个selected remote candidate均UDP30007，错误端口负例不得通过。
- 无Agent时明确HTTP503；Gateway SIGKILL后Agent PID存活/自动重注册，Browser实际Chrome主进程PID和启动ticks、容器ID及StartedAt保持不变。
- 不用任意异常、HTTP存活或HELLO计数替代完整SDP/ICE信令和实际媒体；任何fatal或缺项必须非零。

## 尝试

- 旧版Echo只有传输机制证据，不是Selkies媒体通过依据；跨Profile注入、slow handshake和JSON扩展边界分别补过真实网络回归。
- 首次真媒体候选被主控拒绝：UDP失败分支也PASS，重启只重建进程内HTTP runner，入口无失败非零门禁。
- 作者改独立进程后，主控再次补强非503异常不得PASS、fatal_error必须FAIL且12项齐备、实际应用180秒总timeout。
- 原PID检查是pgrep Python test_cloak_loop.py，不是Chrome。主控改读/proc/\*/exe及start_ticks；首轮因Cloak子进程重写cmdline为空格字符串而误识别8个main，独立重跑exit1。修正NUL/空格归一并排除--type=子进程后，同一独立reviewer再次真实重跑。
- 交付code/probe四文件与最新独立重跑快照逐字节一致；code/media_fixture提供完整三文件Browser夹具。未拷贝token、日志或运行数据。

## 证据

2026-10-27T10:28:49+08:00，独立Gemini实际重跑12项通过、exit0，主控核对真实命令结果和自动报告；最终独立源码审查与黑盒报告见independent_review.md。原始日志在主仓.scratch/v2_orchestration/review_gateway_chrome_identity_fix.jsonl及gateway_review/.scratch/gateway_media_probe。

- 同一ChromeContext两tab，Tab1 53→234 frames、180054→245755 bytes；Tab2 53→234 frames、184291→250035 bytes。首tab关闭后次tab继续至474帧。
- 两个selected remote candidates均UDP30007；expected9999时validator拒绝。
- Gateway独立进程SIGKILL，Agent未重启并重新注册；页面显式goto重新建立连接后恢复13帧解码。
- Browser容器ID保持1e6730351f871be3061476886d45217d7318c9e0b5c6180278582724389e5fce；实际Chrome main PID49、start_ticks78629999前后相同；容器StartedAt保持2026-10-27T02:28:14.424334174Z。
- 60条Agent轨迹覆盖HELLO/SESSION/SDP/ICE双向消息类别、长度与SHA256摘要，不记录完整凭证/SDP。

复现需已有s001两个runtime:test镜像、本机GoogleChrome、uv和Docker。完整复制后运行，TMPDIR固定在允许scratch内；勿直接从docs运行：

```bash
mkdir -p .scratch/gateway_probe
cp -R docs/spikes/s006_gateway_media_recovery/code/probe docs/spikes/s006_gateway_media_recovery/code/media_fixture .scratch/gateway_probe/
mkdir -p .scratch/gateway_probe/probe/tmp
TMPDIR="$PWD/.scratch/gateway_probe/probe/tmp" uv run --no-project --with aiohttp --with playwright python .scratch/gateway_probe/probe/run_verification.py
```

固定localhost18082/18083、UDP30007和cbrowser-spike-gateway-media前缀，禁止同实验并行运行。真实进程/容器清理在finally。临时secret自动随机生成，仅本地实验，不是公网生产凭证。

## 结论

- 独立Gateway/Agent透明信令、真实媒体UDP映射和Gateway崩溃后Browser不重启的技术原型通过。
- 页面恢复为显式重新导航/新ViewerConnection，不是原PeerConnection ICE restart，不证明自动无缝恢复或时延目标。
- 本实验只检查视频；音频在s004独立验证，未覆盖Gateway重启后音频恢复。
- 当前轨迹证明Agent双向传输及真实媒体握手，不是端到端逐字节双侧摘要审计。sanitize_packet仅过滤自有envelope顶层key，不能证明opaque信令不含secret。
- 本次Origin/跨Profile/慢队列主要静态审查；早前另组20真实网络回归及边界实验通过，不能混称本次12项覆盖全部安全攻击面。
- localhost不能证明公网/TURN或原生Linux；正式鉴权、Supervisor网络、资源限制与生产安全仍待验证，AC-004未勾选。

## 是否采纳

- 决定：是，仅采纳独立信令隧道与Gateway重启不停止Browser的技术可行性。
- 理由：真实三进程、双容器与双Chrome页，SIGKILL前后实际Chrome身份和媒体重建闭环。
- 后续 task：t001
- 无需后续理由：不适用

## 关联 findings

- d008：Gateway/Agent独立进程崩溃恢复与实际Browser身份持续。
- d003：固定SDK ICE restart缺口；本实验页面重建不替代该要求。
