# d006 已落盘事件在 API 离线与 Supervisor 进程重启后可恢复

- 来源：t001 / s003_selkies_control，2026-10-27T02:31:53+08:00 主控重跑及独立 Gemini 黑盒。
- 结论：单实例真实 Docker CloakBrowser 经 UDS/CDP 正常退出，API 离线时将事件持久化，Supervisor 在队列落盘后、HTTP 发送前被 SIGKILL，重启后可送达 API 并收敛 stopped；多轮 reconcile 不误自启。
- 证据：s003/code/recovery_probe 三文件，主控 root_recovery_verify.log exit0；独立 s003/recovery_review.md 重跑29.3秒 exit0。实际新容器实例在线后旧事件被拒，重复事件不重复修改状态；容器挂载不含 API SQLite。
- 影响：证明分离单写者 DB 与持久事件回传可行，后续生产恢复链路必须补充 observed running、异常退出退避/熔断及多事件队列互斥。SIGKILL 位点在落盘后，不能推断写入中途断电无损或文件并发无丢事件。
- 现状：有效
