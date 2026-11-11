# d038 确定性部署身份与每实例媒体子网池：sha256 身份派生，instance-id 为唯一归属依据

- 来源：t051（2026-11-11），review_20261110_200842 的 A59（归属只凭可伪造标签）与 A3（双实例媒体池重叠）。
- 结论：**部署身份由材料串 `cbrowser-instance-v1\0<prefix>\0<data_root>` 的 sha256 前 32 hex 确定性派生，跨 release 稳定、跨（prefix, data_root）区分；媒体子网池按 `pool_index = sha256(identity) mod 64` 得 `10.{192+index}.0.0/16`，两实例池互不重叠可由部署前静态判定。归属判定以 `com.cbrowser.instance-id` 标签值 == 本实例 instance_id 为唯一依据；每轮唯一的运行时 id 不占标签，写入容器运行时配置（Stream 环境变量、gated entrypoint、Browser 命令参数），经 `container_runtime_instance_id` 读取。**
- 证据：
    - 身份派生：`scripts/deploy.sh` 的 `derive_instance_identity`（python3）与 t027 fake harness 的 `_instance_identity` 用同一材料串逐字节对照，测试断言身份跨 release 稳定、manifest 的 `instance` 块含 `instance_id` 与 `media_subnet_pool`。
    - 池分配：默认单实例池为 `10.251.0.0/16`（Supervisor 默认）；部署派生池覆盖 `10.192.0.0/16`–`10.255.0.0/16` 的 64 个 /16 池；deploy.sh 在同一扫描内判定池重叠（与 prefix 无关，己方 instance-id 跳过），重叠即拒绝。
    - 键分离的必要性：`com.cbrowser.instance-id` 已被 Browser/Stream 沙箱占用为运行时实例 id，`core._lookup_browser_container`、扫描/残留/恢复路径与多处 E2E 均以该键比对会话运行时 id；若把部署 instance_id 写进同一键，运行时查找永不命中。裁决见 t051 progress.md「设计裁决：部署身份标签键」。
    - 扫描语义：配置了 deployment id 时，缺失或不符标签的资源不被认领、不删除、不清理（`DockerAdapter._owns_deployment`、`scan_active_containers`、`_cleanup_orphan_helpers`、`scan_gateway_containers`、`core._lookup_browser_container` 的服务端过滤器、`network_ownership_matches`）；t051 之前创建的无标签资源升级后不被认领，由既有 orphan 路径处置。
- 影响：deploy.sh 冲突判定、compose 服务标签、Supervisor 扫描/清理/查找、媒体网络标签均以 instance-id 为准；后续多实例部署、t032 真实双实例验证须用同一身份材料串，prefix 须匹配 `^[a-z0-9][a-z0-9_]*$`（不含连字符）。
- 现状：有效
- 复查条件：身份材料串、池数量（64）或池基址变更时，须同步改 deploy.sh、fake harness 与本文；真实双实例并存须在用户机验证（AC-014 真实部分本机未跑）。
