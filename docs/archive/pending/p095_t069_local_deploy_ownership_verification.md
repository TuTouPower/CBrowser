# p095 t069 合入后本地真实部署补验部署归属严格化

- 来源：t069 遗留
- 内容：t069 的 AC-003 是 [deploy] 验收，云端执行环境无 Docker，只完成了代码与单元/契约层证据（归属矩阵、未配置不认领、启动缺身份在 Docker 变更前失败、deploy.sh 豁免段删除的静态断言），不能冒充真实部署已验。合入后须在本地 Mac 的隔离 Docker 拓扑中实跑并留证：缺失、为空或不匹配 `CBROWSER_INSTANCE_ID` 的存量容器与网络不被 Supervisor 认领或删除；Supervisor 在未配置部署身份时于任何 Docker 变更前启动失败；带合法匹配 instance-id 的资源可被正常恢复清理（scan/prune/孤儿 helper 清理）；deploy.sh 前缀冲突检查对无标签历史容器不再按 compose project 豁免认领。
- 处理：683aa10；resolution=resolved；reason=gate5 归属 E2E 全绿，且 deploy.sh 无标签历史容器 prefix 冲突专项验证通过：同 compose project 不再豁免认领
- 时间：2026-11-14T22:36:00+08:00

## 终局补验证据（gate5 / 真实部署栈，最终结论；取代下方 gate4 阶段性记录）

- 无标签历史容器专项（`.scratch/terminal_deploy_slices/p095_prefix_conflict.log`）：用 `docker create` 造一个**已停止的存量容器** `cbrowser-legacy-unlabeled`，带 `com.cbrowser.prefix=cbrowser` 与 `com.docker.compose.project=cbrowser`、但**无** `com.cbrowser.instance-id` label；`bash scripts/deploy.sh deploy` 在 build 之前被 `check_prefix_conflict` 正确拒绝：`Refusing to start: resource prefix 'cbrowser' is already used by instance (compose project 'cbrowser', container 'cbrowser-legacy-unlabeled').` → 证明同 compose project 不再豁免认领（`scripts/deploy.sh:649-660` 的 t069 严格归属）。随后删除该容器，原栈 4 容器未受影响。
- 真实部署：Release `20261114212243-78d4f8c` 由 deploy.sh 派生 `CBROWSER_INSTANCE_ID=7891c8df023eb500f1a5f5ec12176583`、media pool `10.223.0.0/16`、edge subnet `172.25.0.0/16` 并写入每个控制面服务/网络的 `com.cbrowser.instance-id` label；4 容器 healthy。
- gate5 中 `test_supervisor_network_ownership_e2e.py` 2 例、`test_supervisor_orphan_helpers_e2e.py`、`test_supervisor_reconciliation_e2e.py` 2 例、`test_supervisor_container_graph_e2e.py::...instance_fenced_lifecycle` 全绿（e2e 105/0），覆盖「缺失/空/不匹配身份不被认领」「未配置身份在 Docker 变更前启动失败」「带匹配 instance-id 的资源可 scan/prune/孤儿 helper 恢复清理」。

## 本地补验证据（gate4）

- 已验：gate4 E2E 中 `test_supervisor_network_ownership_e2e.py` 2 例、`test_supervisor_orphan_helpers_e2e.py`、`test_supervisor_reconciliation_e2e.py` 2 例、`test_supervisor_container_graph_e2e.py::test_authoritative_gateway_port_credentials_and_instance_fenced_lifecycle` 全绿；`ee94faf` 把 t069 `deployment_instance_id` 统一为生产同名 `CBROWSER_INSTANCE_ID` 并经 `tests/e2e/conftest.py` 确定性注入全部 harness（含 `frontend_probe`/`frontend_app_probe`/`supervisor_recovery_probe`），验证「缺失/空/不匹配身份的资源不被 Supervisor 认领或删除」「未配置身份在 Docker 变更前启动失败」「带匹配 instance-id 的资源可 scan/prune/孤儿 helper 恢复清理」。此前 `scripts/deploy.sh` 亦正确拒绝 prefix 冲突（`Refusing to start: resource prefix 'cbrowser' is already used by instance ...`）。
- 卡点：「deploy.sh 前缀冲突检查对无标签历史容器不再按 compose project 豁免认领」需在真实部署栈构造无标签历史容器后跑 deploy.sh；本批未启动生产栈，未验。
