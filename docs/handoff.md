# 项目交接记录（最新）

本文件只维护当前有效上下文，历史由 Git 保存。

## 2026-11-19T02:15:00+08:00 本地线收尾验证与远端合入

- 当前焦点：cbrowser 本地真实链路验证与远端 `origin/main` 合入收尾全部完成（`t075`、`t083`、`t081`、`t082` 等已合入 `main` 并推送；`p127`、`p129`、`p130`、`p131`、`p132`、`p133`、`p134`、`p135`、`p136`、`p137` 共 10 条条目全部闭环，当前 `todo` 待办清零，8 条 `parked` 条目保持原位）。
- branch：`main`。
- head_commit：`8181b1737d169034776af362bed645e879d77d4c`（本交接文档记录该已完成全量门禁与本地闭环推送的主干提交，随后以独立 `docs(handoff)` 提交推送至 `origin/main`）。
- 已完成：
    - 集成测试失败定性：`tests/integration/test_font_sets_api.py` 在 `-n 4` 并行下的 `sqlite3.OperationalError: database is locked` 经隔离复跑（`-n 0` 全套及 10 轮目标用例全过，`-n 4` 5 轮复跑第 3 轮复现）确认属既有 `t081` 缺陷，非本批回归；根因为 `src/backend/cbrowser/adapters/database/font_repository.py` 中 `apply_audit_verdict` 缺少 `write_transaction(session)`（`BEGIN IMMEDIATE`），与并发写事务冲突触发 SQLite WAL `SQLITE_BUSY_SNAPSHOT`。按指令保留现场如实记录。
    - 按关注点提交、合入与修复：`7e919fd`（p130/p136 删除批次成员关系分离与并发竞态修复，迁移 `0012`）；`54fa1ec`（命名卷属主初始化、gate subpath 校验、正常退出竞态修复与 `docs/findings/d052_policy_agent_net_admin_and_pause_isolation.md` / ADR 039）；`ad4ff6b`（p127/p129/p131/p132/p133 闭环）；`9af0098`（合入 `origin/main` 的 t075/t083/ebeb744 并将 `0012` 接续至 t075 `d75a0013f001` 之后，补齐 macOS `/data` 只读测试兼容）；`2092a35`（修复 `scripts/steady_state_probe.py` 去掉 `-q` 以兼容 `--format "{{json .}}"`、纳入 Compose 服务容器、并将 `with_rchar` 的 `cat /proc/1/io` 纳入 `measurement_exec_ids`）；`8181b17`（闭环 p134/p135/p137 并回填 `docs/spikes/s026_gpu_platform_capability/report.md`）。
    - 隔离真实栈补验：p127（6/6）、p129（5/5）、p131（4/4，143 份 Windows 字体 / 600.17 s 零字体正文读取）、p132（4/4，d052 实证）、p133（7/7，8 Policy Agent 600 s 稳态 + 4 类故障）于合入前正式栈通过；合入并重新部署后，p137（7/7，AC-009 双平台字体隔离/CJK 开关/GPU 矩阵/`color_scheme` 独立性/迁移阻断与回滚）、p134（600 s 稳态：`policy_helper_churn_events=0`、`policy_agent_churn_events=0`、`stack_execs=0`、`font_audit_logs=[]`、Browser/Stream 状态与下载完整）、p135（8/8，API/Gateway/Supervisor 重启、丢通知 `1.54 s` 兜底收敛、双栈漂移 `30.59 s` fail-closed、单 Profile 阻断隔离）全部通过。
    - 全量门禁：合入提交 `9af0098` 及 `8181b17` 均通过 `scripts/run_gates.sh` 9/9 套件（最近完整门禁 `run_id=4ca4631558de45a5a8f972baa141ac1e`：`protocol_drift_check`、`requirements_check`、`contract` 388 passed / 1 skipped、`unit` 2372+84 passed / 13 skipped 共 2469 cases、`integration` 206+4 passed / 18 skipped 共 228 cases、`design_lint`、`design_check`、`frontend_test` 85 files / 693 passed、`frontend_build` 全部 `exit 0`；`real_engine` 默认不跑，由上述独立真实 Docker + Chrome 链路替代覆盖）。
- 部署上下文：主机主部署（小写数据根 `data/instance`）当前运行 `release 20261119011954-9af0098`，DB 迁移版本为 `d7e3a91f4c62`，核心 4 服务（api / gateway / supervisor / caddy）均处于 `running`，Supervisor readiness 与 API health 均正常；已采纳 Windows（143 文件）与 macOS（371 文件）两套 `verified` 字体集；受保护 Profile `#22/#23/#24/#26` 全程保持 `stopped` 及配置/绑定/proxy 完整不变。后续仅修改了宿主机探针脚本 `scripts/steady_state_probe.py`、单元测试及文档，未进运行中容器镜像。
- 未完成：`src/backend/cbrowser/adapters/database/font_repository.py` 中 `apply_audit_verdict` 缺失 `write_transaction(session)` 的 `t081` 既有并发锁升级隐患（需单立缺陷修复 task 处理，避免与其余写入并发时偶发 `SQLITE_BUSY_SNAPSHOT`）；如后续调整容器内运行代码，需重新发布并按需触发 `CBROWSER_REQUIRE_REAL_ENGINE=1`。
- 陷阱：
    - 主库已在合入部署演练中校验从 `d83a2c12b083` 阻断门禁、修复升级至 `d7e3a91f4c62` 与回滚恢复链路，勿在未核对 `alembic_version` 的情况下手工改表。
    - OrbStack 在宿主同时运行多栈与多套双网桥 Profile 容器时，`vmgr.log` 于 P4 快速停启重配置窗口出现过归属于 `cb134-net-*` / `cb134-browser-net-*` 的 `failed to add network (error="too many interfaces")`（该次 P4 仍于 10.71 s 正常启动与就绪）；排查宿主机日志须按当前容器/网络 ID 严格过滤归属。
    - `tests/integration/test_font_sets_api.py` 在 `-n 4` 高并发下受上述 `t081` WAL 写锁竞态影响可能偶发失败，`-n 0` 串行执行可稳定通过。
    - 模板 sync 事务维持 `applied` 状态，8 条 `parked` pending（p031 / p038 / p039 / p040 / p041 / p043 / p045 / p053）继续保持原位。
- 下一步：如需消除 `test_font_sets_api.py` 在 `-n 4` 下的偶发锁竞争，可另开 task 为 `apply_audit_verdict` 补齐 `write_transaction(session)` 并增加并发回归测试；日常开发继续依据 `docs/blueprint/` 与门禁规范推进。
