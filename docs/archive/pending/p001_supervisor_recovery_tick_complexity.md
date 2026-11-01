# p001 拆分 RecoveryCoordinator.tick 多阶段恢复逻辑

- 来源：t005 遗留（t005_code_f001，minor）
- 内容：`src/backend/cbrowser/supervisor/recovery_coordinator.py` 的 `RecoveryCoordinator.tick` 约 310 行、圈复杂度约 68，串联 API 探测、容器扫描分类、异常退出识别、缺失 Runtime 补偿与 2/10/30 重试调度。当前真实 E2E 全部覆盖且无已知缺陷；t005 冻结后不再重构以免使已完成的整套 Docker 验证失效。后续在触及恢复逻辑时按阶段拆为私有方法并保持现有 E2E 不改预期。同类提示：`ResourcePolicyService.record_stats`、`SupervisorCore.scan_and_reconcile_existing`/`start_profile`、`docker_adapter.py` 1024 行。
- 处理：review/adoption-refactor；resolution=resolved；reason=A25 完成结构性拆分：recovery tick 按 observe/classify/schedule 拆分；docker_adapter 提取 volume/network/container spec；stream_agent 提取 messaging；policy/router 提取纯函数；p005 的 f001/f002/f003 与复杂度项均已在 main 闭环。
