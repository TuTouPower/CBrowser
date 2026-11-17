# 共享捕获策略与真实双 Peer 技术验证

## 问题

验证第18.9/10及第9章Profile级聚合：一个后台Peer不得拉低活动Peer，静止target8与持续动画30分离，全部隐藏或断开时实际暂停，全隐藏恢复先8再按motion升30。不能把默认恒30或mock管线字段当通过。

## 成功判据

- 真实双容器和同Google Chrome Context两页面，实际WebRTC decoded帧与服务端真实pipeline状态互证。
- 静止、60fps Canvas动画、0.5Hz慢闪真实对照；不手动设置has_motion。
- 一Peer STOP_VIDEO、另一活动，target30保持；所有Peer STOP_VIDEO/断开则真实pause；START_VIDEO后恢复。
- 官方捕获API实际调用，输入和可见性最终须走真实客户端链路；不能以UDS伪造活动替代正式通过。

## 尝试

- 原AsyncMock方案只验证自写类，不纳入E2E交付。
- 当前code为v1冻结快照：显式WebRTCService适配层，读取capture_module.stream_stats累计frames增量；关闭Turbo后根据真实damage动态调整。未调用破坏采样窗口的StreamWatch.rates。
- 独立快照初次因主控漏拷原目录已有test_page.html导致404/动画不运行，exit1。补齐原文件，未改实现/预期，再次真实重跑exit0。首次失败归因为打包缺陷，不据此否认作者历史日志。
- v1独立review为CONDITIONAL ACCEPT，并非最终全量PASS；作者v2正在解决下述缺口。此处保存已复核v1，后续最终交付变化必须重新review。

## 证据

2026-10-27T10:19:09+08:00独立Gemini在独立worktree完成完整fixture重跑，exit0，报告见independent_review.md。原始real_e2e.log在主仓.scratch/v2_orchestration/policy_review/.scratch/capture_policy_probe，不入库。

|对照|真实结果|范围|
|---|---|---|
|静止|target8，decoded0|damage模式实际无新帧，不能称输出8fps|
|持续Canvas动画且无键鼠|target30，decoded30|避免仅因无输入错误降8|
|0.5Hz慢闪|target8，decoded约0.5|不将低频闪烁长期视为视频|
|一Peer STOP_VIDEO另一活动|active_peers1，target30|真实Peer控制消息，尚未验证浏览器visibility事件|
|全部STOP_VIDEO|is_screen_capturing=false|真实capture暂停|
|START_VIDEO恢复|初次target8，随后motion30|瞬时状态与源代码顺序可见，未做调用序列追踪|
|全部页面关闭|peers0、capture=false|零观看者暂停|

复现先将code五文件完整复制到独立scratch，不直接在docs运行。只允许cbrowser-spike-capture前缀、localhost18084/UDP30008，无其它任务同端口运行：

```bash
mkdir -p .scratch/capture_policy_probe
cp docs/spikes/s005_capture_policy/code/* .scratch/capture_policy_probe/
uv run --no-project --with playwright --with aiohttp python .scratch/capture_policy_probe/test_e2e_real_pipeline.py
```

前提为s001构建的两个runtime:test镜像、本机Google Chrome和Docker。总timeout及finally清理在测试内。该脚本在宿主本scratch生成测试日志/X11目录。

## 结论

v1证明基于真实damage信号的共享8/30策略可行；第18.9/10底层机制有独立真实证据，但最终集成门禁未通过，不能冻结架构。

仍需修复/补测：

- 输入活动目前由UDS record_input绕过真实Peer，不能证明完整输入提升链路。
- STOP_VIDEO/START_VIDEO经真实DataChannel发送，但由测试手动发送，没有覆盖实际Page Visibility监听。
- 另一Peer仍活动时，后台Peer恢复没有显式IDR请求；弱网首帧风险尚未实测。
- \_resume_display_capture每次调用先set8，即使capture已在运行，新Peer加入可短暂影响现有活动流；需要统一控制与回归。
- 恢复调用顺序未做实际API序列追踪；防篡改只检查fps不等于120，未核对xrandr、decoder尺寸或Turbo状态。
- 独立日志最后一轮新peer active1而capture=false，不能据此宣称全断开后新连接恢复已通过。
- root/无Xauthority实验不证明生产隔离和权限。正式Profile资源策略、CPU降载、长压和完整IME仍须后续验收。

## 是否采纳

- 决定：是，仅采纳damage对照与聚合控制底层可行性，不采纳v1为生产实现或完整E2E验收。
- 理由：真实双Peer解码、实际pipeline API与三组画面对照闭环；缺口明确保留，v2修正中。
- 后续 task：t001
- 无需后续理由：不适用

## 关联 findings

- d005：恒定编码帧率不是运动信号，Turbo需与damage对照区分。
- d007：双真实页面媒体与输入底层能力可行，非全局策略通过依据。
