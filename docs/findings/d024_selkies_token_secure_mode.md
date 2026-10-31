# d024 Selkies 2.1.0 安全模式 token 与 Agent 代注入

- 来源：t007_v2_frontend_sessions spike lane `t007_spike_token`（Stream 镜像内真实实验），主控复跑 5 passed（2026-10-31）。
- 结论：设置 `SELKIES_MASTER_TOKEN`（或 `--master-token`）即进入安全模式；`/api/tokens` 需 `Authorization: Bearer <master>`，否则 401，未开安全模式时 404。`SELKIES_TOKENS_FILE` 为 JSON 对象 `{token: {"role": "controller", "slot": null, "mk_control": false}}`，属主须为 root 或进程用户、不得组/他人可写（0600/0644 可，0664/0666 被拒），只读根文件系统下可放 tmpfs `/tmp`，每秒轮询变化。WebRTC 客户端在首帧 `HELLO client {...}` 的 `client_token` 字段出示 token；缺失或错误以 Close 4001 `Invalid authentication token` 拒绝，viewer token 被降级为 viewer 且在 `enable_collab=false` 下不能绑定输入。Stream Agent 在 `_viewer_upstream_worker` 转发 HELLO 时补入 Profile 级 controller token 即可让不持有 token 的页面以 controller 接入，`client_tab_id`/`resume_key` 与重连 `_resume_locked` 不受影响；`enable_sharing=true` 下不同 `client_tab_id` 共用同一 controller token 并存，同 tab id 新连接驱逐旧连接。
- 证据：`.scratch/v2_orchestration/retired_worktrees/CBrowser_t007_spike_token/`（`test_selkies_tokens.py`、RED/GREEN 与主控复跑日志、report.md）；上游源码 `settings.py:608-618`、`websockets_mode.py:422-450,7564-7618`、`webrtc_signaling_server.py:715-723,760-833,999-1003,1058-1089`、`stream_server.py:2223-2230`。
- 影响：t007 AC-010 采用“Supervisor 生成 master/controller、Stream 入口写 tokens_file 并设 master、Agent 代注入 controller”的方案，页面与 Gateway 都不持有 Selkies token。
- 现状：有效，限固定 Selkies 2.1.0。
