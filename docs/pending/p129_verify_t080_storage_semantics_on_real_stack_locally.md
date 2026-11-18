---
pid: "p129"
slug: "verify_t080_storage_semantics_on_real_stack_locally"
status: "closed"
resolution: "resolved"
reason: "本地隔离真实部署（release 20261118212912-a0fed8e）补验 AC-003/005/007/008 全通过（compose 重建持久化与离线终态重放、clone/reset/delete/restore-point、迁移一致性与幂等性、371 个字体挂载校验与缺失集 422 拒绝），并修复 normal_exit 后立即启动 409/UDS 轮询竞态"
fix_ref: "main"
---
# p129 本地补验：真实部署上验证 t080 重启持久性、迁移身份一致性与新存储业务语义（AC-003/005/007/008）

- 来源：t080 遗留（云端无 Docker Engine，2026-11-18 用户裁定：云端做不了的登记 pending、留待本地统一补验）
- 内容：在隔离真实部署上补验 t080 其余 AC 的真实链路部分（云端已以单元/集成测试验证逻辑与契约面）：① AC-003：Supervisor/API/Gateway 重建及 Browser 停止再启动后，Cookie、localStorage、下载记录、预览与待投递终态事件按原业务语义保留，单独重启 Supervisor 不破坏存活实例通信或用户页面；② AC-005：对真实数据副本执行完整迁移后逐项比对 UUID、显示编号、seed、配置及绑定版本、部署归属、字体 set_id、Profile 文件摘要与 Artifact 引用，并重复运行迁移确认不再次复制已完成事务、不改变身份、不覆盖其他实例资源；③ AC-007：克隆、重置、停止并删除、上传/下载、预览和环境恢复点在新存储中保持既有语义（重置不删除 Artifact、克隆不复制活动锁/socket、删除失败仍可续跑且不触碰其他环境或共享资产）；④ AC-008：相同内容字体迁入后绑定不变，Browser 实际挂载内容摘要与导入内容一致，缺失字体资源不会被宿主空目录替代，新部署与迁移部署均能由同一卷引用契约定位资产。证据按 docs/blueprint/testing.md 脱敏保存并记录实际镜像 ID。
- 处理：main；resolution=resolved；reason=本地隔离真实部署（release 20261118212912-a0fed8e）补验 AC-003/005/007/008 全通过（compose 重建持久化与离线终态重放、clone/reset/delete/restore-point、迁移一致性与幂等性、371 个字体挂载校验与缺失集 422 拒绝），并修复 normal_exit 后立即启动 409/UDS 轮询竞态
