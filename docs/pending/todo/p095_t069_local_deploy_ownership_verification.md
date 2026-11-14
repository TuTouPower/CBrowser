# p095 t069 合入后本地真实部署补验部署归属严格化

- 来源：t069 遗留
- 内容：t069 的 AC-003 是 [deploy] 验收，云端执行环境无 Docker，只完成了代码与单元/契约层证据（归属矩阵、未配置不认领、启动缺身份在 Docker 变更前失败、deploy.sh 豁免段删除的静态断言），不能冒充真实部署已验。合入后须在本地 Mac 的隔离 Docker 拓扑中实跑并留证：缺失、为空或不匹配 `CBROWSER_INSTANCE_ID` 的存量容器与网络不被 Supervisor 认领或删除；Supervisor 在未配置部署身份时于任何 Docker 变更前启动失败；带合法匹配 instance-id 的资源可被正常恢复清理（scan/prune/孤儿 helper 清理）；deploy.sh 前缀冲突检查对无标签历史容器不再按 compose project 豁免认领。
- 处理：归属严格化主体已由 E2E 补验通过；deploy.sh 前缀冲突专项切片未跑
- 时间：2026-11-14T19:07:00+08:00

## 本地补验证据（gate4）

- 已验：gate4 E2E 中 `test_supervisor_network_ownership_e2e.py` 2 例、`test_supervisor_orphan_helpers_e2e.py`、`test_supervisor_reconciliation_e2e.py` 2 例、`test_supervisor_container_graph_e2e.py::test_authoritative_gateway_port_credentials_and_instance_fenced_lifecycle` 全绿；`ee94faf` 把 t069 `deployment_instance_id` 统一为生产同名 `CBROWSER_INSTANCE_ID` 并经 `tests/e2e/conftest.py` 确定性注入全部 harness（含 `frontend_probe`/`frontend_app_probe`/`supervisor_recovery_probe`），验证「缺失/空/不匹配身份的资源不被 Supervisor 认领或删除」「未配置身份在 Docker 变更前启动失败」「带匹配 instance-id 的资源可 scan/prune/孤儿 helper 恢复清理」。此前 `scripts/deploy.sh` 亦正确拒绝 prefix 冲突（`Refusing to start: resource prefix 'cbrowser' is already used by instance ...`）。
- 卡点：「deploy.sh 前缀冲突检查对无标签历史容器不再按 compose project 豁免认领」需在真实部署栈构造无标签历史容器后跑 deploy.sh；本批未启动生产栈，未验。
