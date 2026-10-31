# p003 API 运行意愿变更后由谁触发 Supervisor 启动/停止 Runtime

- 来源：t006 主控审查（2026-10-31）；技术债自查
- 内容：API `PATCH /api/v1/profiles/{id}/runtime/desired-state` 只写入运行意愿；Supervisor 的 `start_profile` 只经 `/supervisor/v1/profiles/start` RPC 触发（要求 API 运行意愿为 running），而 API 侧没有任何调用 Supervisor 启动/停止 RPC 的代码，Supervisor 周期 `scan_and_reconcile_existing` 只收敛已存在的容器。现有 t005/t006 E2E 都由测试直接调用 Supervisor RPC 启动。正式部署（前端点“启动”→ 浏览器出现）需要明确的 API→Supervisor 协调路径（计划第 3、12 章“Runtime Coordinator（内部认证 RPC 通道）”），应在 t007 前端会话或 t012 部署前由对应 task 补齐并以真实 E2E 验证，不能以测试直调 RPC 冒充。
- 处理：t007；resolution=resolved；reason=t007 AC-009 由 API Runtime Coordinator 经内部 RPC 驱动 Supervisor 启停
