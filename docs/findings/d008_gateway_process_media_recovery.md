# d008 独立信令隧道与 Gateway 重启可保持实际浏览器进程

- 来源：t001 / s006_gateway_media_recovery，2026-10-27T10:28:49+08:00独立Gemini真实重跑12项、exit0。
- 结论：Gateway与Agent独立进程传输官方Selkies信令，真实双页面selected remote均UDP30007且解码增长；Gateway被SIGKILL重启后Agent自动注册，实际Chrome主进程PID/start_ticks及Browser容器ID/StartedAt保持不变，页面显式重建连接后恢复解码。
- 证据：s006/code四个probe与三个media_fixture源文件。两tab均53→234帧，首页关闭次页474帧；实际Chrome PID49/start_ticks78629999前后相同；无Agent503和错误端口9999拒绝均实测。主控修正/proc对空格重写argv解析后独立重跑exit0，失败保留在独立review实验目录。
- 影响：支持动态Agent隧道与Gateway重启隔离；仅本机视频/页面显式重建，不证明原PC ICE restart、音频恢复、公网/TURN、时延或全部安全攻击面。正式架构仍需后续完整验收。
- 现状：有效
