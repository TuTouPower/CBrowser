# d009 coturn HMAC鉴权与双端relay UDP可真实互通

- 来源：t001 / s002_selkies_protocol，2026-10-27T10:52:39+08:00主控独立重跑固定Selkies 2.1.0 ICE低层传输与真实coturn。

- 结论：TURN REST HMAC-SHA1有效短期凭证可实际Allocate；错误密码和已过期凭证均明确401拒绝。两个独立TURN allocation经真实ChannelBind可双向中继随机UDP payload，字节匹配。

- 证据：s002/code/turn_auth_probe.py；主控.scratch/turn_auth_replay/verify_strict.log exit0，negative_cases_explicit_401=true，a_to_b_matched/b_to_a_matched=true。coturn在专属Docker网络172.29.0.10，无公网发布；主控未更改上游安装包。

- 影响：支持TURN鉴权与relay transport基础可行性；这不是RTCPeerConnection ICE候选选择、WebRTC媒体、凭证刷新或同PC ICE restart通过依据，第18.14仍未完成。实验TTL300秒用于加速测试，不改变生产24h/12h/提前6h计划。

- 现状：有效

- 实验镜像：coturn/coturn@sha256:bbefd3e1fdfdc0d58770fe01b581fd8b00d9f3a5580d00acb77cf719a6bc78e3。

- 后续（t024 文档收敛）：本条所述 TURN/ICE 代次机制已由 ADR 013（同机直连，见 docs/blueprint/decisions.md）整体删除；本条仅作历史实验事实保留，不再构成现行实现或验收要求，文中指向未来 task 的指令已失效。
