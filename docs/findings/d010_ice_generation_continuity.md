# d010 同SDK PC/DTLS可经显式适配器跨三轮新ICE代持续DataChannel

- 来源：t001 / s002_selkies_protocol；2026-10-27T11:14:21+08:00主控真实Docker实验，退出码0。
- 结论：固定Selkies 2.1.0 SDK进程内显式ICE generation适配器，可保持相同PC/SCTP/DTLS/ICE外层对象和DataChannel，经标准createOffer/setLocalDescription/setRemoteDescription/Answer交换三次新ICE凭证；关闭旧ICE后每轮10条新payload精确收到，旧Connection.send明确拒绝。
- 证据：s002/code/datachannel_restart_probe.py，task worktree.scratch/ice_generation_probe/datachannel_three_rounds.log；successful_ice_restarts=3、post_restart_exact_packets=30。首次无旧remote参数过滤时真实连接失败，修正setLocalDescription在新Answer前触发旧remote连接的竞态后通过。SDK安装文件未改，只注入测试进程内显式类。
- 影响：原生SDK缺口d003仍有效；此适配器涉及固定版本私有字段，属于实验，不是生产可直接采用接口。这里只证明本机host UDP、SCTP/DTLS数据连续，不证明真实媒体、Chrome、relay-only、TURN刷新或公网，第18.14未通过。
- 现状：有效

- 后续（t024 文档收敛）：本条所述 TURN/ICE 代次机制已由 ADR 013（同机直连，见 docs/blueprint/decisions.md）整体删除；本条仅作历史实验事实保留，不再构成现行实现或验收要求，文中指向未来 task 的指令已失效。
