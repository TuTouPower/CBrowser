# 012 剪贴板开启时采用 Selkies seamless 双向自动同步（2026-11-02T20:09:33+08:00）

- 背景：t014 为保护本机原剪贴板锁定 `clipboard_seamless=false|locked`，结果本机与远程浏览器之间不能直接 Cmd+C/V，只能经 Selkies 侧栏剪贴板框手动搬运。cbrowser 仅供单一用户在本机使用。
- 选项：
    1. 保持 seamless 关闭，只经侧栏剪贴板框显式传输。
    2. Profile `clipboard_sync` 开启时使用 Selkies seamless 双向自动同步，服务端锁定。
- 结论：采用选项 2（用户决定）。`SELKIES_CLIPBOARD_SEAMLESS=true|locked`；`clipboard_sync` 关闭时 `enable_clipboard=false`，双向仍无传输；二进制剪贴板保持 `false|locked`。接受的代价：会话页获得焦点时本机剪贴板内容会发往该 Profile 的远程浏览器，远端复制会覆盖本机剪贴板；需要隔离的 Profile 关闭 `clipboard_sync`。原计划 19.3「用户剪贴板原内容保护」「后台页面不自动覆盖本机剪贴板」作废。
- 替代：t014 的 seamless 关闭策略。
