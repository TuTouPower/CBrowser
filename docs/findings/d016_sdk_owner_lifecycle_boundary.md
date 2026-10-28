# d016 SDK owner异常消失可能使Chrome以0退出

- 来源：t003 / s010_cloakbrowser_exit_observation，独立Gemini原型与主控固定源码重跑。
- 结论：固定Linux arm64/CloakBrowser0.6.4环境中，launcher保留FD3/4可观察真实Chrome正常0与SIGKILL raw -9（规范化137）；SDK Python owner被SIGKILL后，Chrome因控制pipe关闭在0.5秒内以0退出，不能据Chrome0单独认定用户正常关闭。
- 证据：s010/code/probe.py SHA256 ef1bee2847c96e30ff4542ddf3f888bce332c414774086a08a272462dda36d5c，主控独立headless重跑5项exit0，owner-loss清理前5秒时间线保留。固定镜像与命令见s010报告。
- 影响：t003的UDS Agent重启必须与SDK owner/真实Chrome监控生命周期分离；t005不得将基础设施故障引发的Chrome0盲判为用户关闭、清除running意愿。wrapper是一种机制方案，不是唯一实现；需另验全部配置语义、版本/路径能力识别和正式持久化。
- 限制：不证明全部代理/扩展/DRM/humanize等价，未验完整UI/音频/XShm、Agent恢复、新生产镜像或Mac bind-root权限；原型状态文件没有fsync，不计六AC或掉电恢复通过。
- 后续真实 headful 复核：t003 Root 独立三场景 R2 在 Linux arm64、CloakBrowser0.6.4/Playwright1.64.1 上观察正常关闭0、Chrome SIGKILL137、SDK Node driver SIGKILL 后 Chrome0。正式 Runner 对最后一种产生 lifecycle/process_observation_lost、exit_code=null、state=error，不把基础设施退出当用户关闭。证据为 .scratch/t003_root_checks/runner_lifecycle/\*\_r2.log 与 manifest_r2.json，范围限该次源快照，未替代最终镜像验收。
- 后续消费：t005 必须将 lifecycle/error 收敛为错误观测并保留 running 意愿；不能直接套用 t002 的正常 exit0 停止意愿规则。本 task 不写数据库或跨模块修改 reducer。
- 现状：有效
