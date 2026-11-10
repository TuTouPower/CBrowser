# p057 Supervisor 容器事件自激导致扫描空转

- 现象：只要有一个 Profile 在运行，Supervisor 就会持续创建/销毁 `cbrowser-policy-*` 临时容器，`Container scan found N containers` 从 30s 兜底退化为约 2–3s 一次；Docker 容器管理界面里策略 helper 不断闪现，CPU 被持续占用。
- 影响：所有正式部署；单 Profile 即触发，与 t049 无关（t049 前已存在）。不影响业务正确性，但放大开销并干扰排障观察。
- 根因：`supervisor/runner.py` 的容器事件 watcher 对带 `com.cbrowser.prefix` 标签容器的**全部**事件无条件 `scan_wakeup.set()`。触发源有两类非拓扑事件：① Docker healthcheck 的 `exec_create/exec_start/exec_die`（api/gateway/supervisor 每 5s）；② Supervisor 自己为策略校验创建的 `role=network-policy` helper 的 create/start/die/destroy。每次扫描的 `verify_container_policy` 又会创建 helper，产生新事件再次唤醒扫描，形成自激循环。已扫同类：network watcher 已按 `{prefix}-net-` 过滤，无同类缺口；容器 watcher 缺少“拓扑事件语义”过滤是唯一根因位点。
- 测试缺口：现有 `tests/unit/test_t026_runner_network_events.py` 只覆盖网络事件匹配，没有容器事件触发策略测试。应补纯谓词单测，覆盖：healthcheck exec 事件、policy/x11/cache-init helper 角色、非本 prefix、api/caddy 角色不触发；browser/stream/gateway 的 create/start/restart/die/destroy/kill/pause/unpause/rename 触发。
- 线索：`docker events --filter label=com.cbrowser.prefix=cbrowser` 观察 `cbrowser-policy-*` 每 2–3s 起停；`docker logs cbrowser-supervisor` 扫描同频。
- 处理：main；resolution=resolved；reason=runner 容器事件改为拓扑谓词触发（仅 browser/stream/gateway 的 create/start/restart/die/destroy/kill/stop/oom/pause/unpause/rename），剔除 healthcheck exec_* 与 supervisor 自身 policy/x11/cache-init helper 事件，补 11 条纯谓词单测
