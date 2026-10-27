# d011 Profile 显示与音频边界依赖专属 Socket 卷和 Xauthority

- 来源：s007_profile_isolation / t001
- 结论：同Profile共享IPC实际使用XShm，不同Profile依赖独立Socket卷/Xauthority；Pulse同UID可绕过Cookie，IPC仅阻断XShm。显式48000音频链路可捕获真实浏览器440/880Hz且误差≤1%。
- 证据：最终九源一致、独立纯净目录19.0秒exit0；四容器非root/只读、认证与IPC正负例、实际pactl/gst协商参数，最终估频440.15/880.32Hz；本轮PCM错误声明44100必跑校准拒绝，不依赖历史二进制。s007报告保留R3的404/808与R4静默跳步失败处置。
- 影响：t003/t004/t005须专属卷和明确认证/采样边界，不把Cookie/IPC当绝对防护；不采纳未获源码定位的反指纹因果或错误dB推论。AC-001技术观察通过，正式网络/公网、原生Linux与第19章仍缺。
- 现状：有效
