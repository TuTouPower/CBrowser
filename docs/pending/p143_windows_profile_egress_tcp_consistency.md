---
pid: "p143"
slug: "windows_profile_egress_tcp_consistency"
status: "todo"
---
# p143 Windows 环境与区域出口的 TCP 连接特征一致性

- 来源：2026-11-19 美区 #76、日区 #77 全新 Windows 环境的实际页面对照。两者均用英文和关闭中文字体，已分别确认美国、日本出口。
- 内容：两个环境均触发检测站 `c_conn_os`，目标收到的 TCP SYN 被归类为 Linux 或 Android，而 UA 声明 Windows。运行链确认两者从沙箱经 HTTP 接入本机 Mihomo，再由上游区域代理出站。现有观测无法判定代理链中具体哪一跳建立面向目标的 TCP 会话。该连接发生在当前 Browser 可控边界之外。
- 前置：需要可控制的原生 Windows 执行机或 Windows 区域出口、能证明目标 TCP 会话由 Windows 网络栈发起的路由拓扑，以及可抓包的受控目标。当前美日代理仅提供 HTTP 接入，未证实可以控制其出站 TCP 栈。
- 验证：美日分别以原生 Windows 同版本对照抓取目标端 SYN 选项序列、窗口大小和缩放、MSS、TTL，核对实际公网出口地域，并独立验证 TLS/HTTP2、DNS、WebRTC 和代理失败封闭。浏览器身份与实际连接来源均须有证据。
- 线索：`.scratch/new_profile_comparison/us_detector.json`、`.scratch/new_profile_comparison/jp_detector.json`、[检测站判定逻辑](https://github.com/yt1988/who-are-you/blob/HEAD/src/infer.mjs#L298)。
- 处理：未开
