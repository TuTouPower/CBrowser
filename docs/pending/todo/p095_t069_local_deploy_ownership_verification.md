# p095 t069 合入后本地真实部署补验部署归属严格化

- 来源：t069 遗留
- 内容：t069 的 AC-003 是 [deploy] 验收，云端执行环境无 Docker，只完成了代码与单元/契约层证据（归属矩阵、未配置不认领、启动缺身份在 Docker 变更前失败、deploy.sh 豁免段删除的静态断言），不能冒充真实部署已验。合入后须在本地 Mac 的隔离 Docker 拓扑中实跑并留证：缺失、为空或不匹配 `CBROWSER_INSTANCE_ID` 的存量容器与网络不被 Supervisor 认领或删除；Supervisor 在未配置部署身份时于任何 Docker 变更前启动失败；带合法匹配 instance-id 的资源可被正常恢复清理（scan/prune/孤儿 helper 清理）；deploy.sh 前缀冲突检查对无标签历史容器不再按 compose project 豁免认领。
- 处理：未开
