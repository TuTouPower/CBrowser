# d013 单一捕获仲裁可对接真实页面可见性和 damage 信号

- 来源：s005_capture_policy / t001
- 结论：固定SDK适配层以单一串行锁统一pause/resume/FPS，真实document.visibilitychange只经input channel发送官方STOP/START；实际set8→resume及随后motion30可由内部action trace与真实解码证明。
- 证据：六源冻结，独立Core9 exit0/71.4秒、最终Native7 exit0/24.9秒；主控相同六源原生7场景再跑exit0，路径见s005/report.md。首次Native两Peer握手失败保留，不能宣称无启动竞态。
- 影响：t004/t007可据此实现共享策略和薄visibility适配，不需要600ms强制锁8；首次启动/后台重连需正式覆盖。34.7ms提帧事件不等于第19章P95验收，平台容量/弱网/生产安全仍缺。
- 现状：有效
