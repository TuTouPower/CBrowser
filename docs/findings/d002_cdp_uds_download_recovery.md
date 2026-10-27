# d002 真实 Chrome 通过 UDS 下载及自动恢复可行

- 来源：t001 / s003_selkies_control；2026-10-27T01:26:38+08:00 主控独立复核

- 结论：独立 Python UDS 原型可代理 Chrome loopback CDP，捕获真实 HTTP 下载；外部客户端覆盖下载目录后断开，原型自动恢复默认策略，第二次下载回到默认目录。

- 证据：在 control 实验 worktree 用 `./.venv/bin/python .scratch/test_cdp_real.py` 重跑，退出码 0。两次下载分别收到 downloadWillBegin / completed，文件内容与测试 HTTP 服务字节一致；自动恢复收到 CDP 成功响应，第二次下载默认目录存在、外部覆盖目录为空。主控原始日志保存在主仓 `.scratch/v2_orchestration/root_cdp_verify.log`；可重跑代码见 s003 的 code/test_cdp_real.py。

- 影响：支持第18.15项底层技术可行性；原宿主版不能证明容器内CloakBrowser；容器补充见下文。不能证明正式 Browser Agent/Supervisor 协议、安全授权或完整第18.16/17通过。本条与d006合并覆盖AC-005技术实验；不能据此宣称生产完整恢复链路完成。

- 现状：有效

- 2026-10-27T10:41:13+08:00补充：主控在真实Docker CloakBrowser与独立Supervisor客户端容器通过共享volume UDS重跑，networknone/无PortBindings；recovery和独立override_control两case均exit0。见s003/container_download_report.md与code/container_uds。独立Gemini已真实重跑两case均exit0，五文件与重跑快照逐字节一致，报告s003/container_download_review.md；未扩大为正式授权/持久Artifact链路结论。
