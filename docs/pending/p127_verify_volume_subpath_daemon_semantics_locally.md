---
pid: "p127"
slug: "verify_volume_subpath_daemon_semantics_locally"
status: "closed"
resolution: "resolved"
reason: "本地 OrbStack 真实 Docker 与 release 20261118212912-a0fed8e 隔离链路上完成 6/6 正负验证（missing subpath 报错不建目录、Browser/Stream subpath 与 EROFS 只读强制、UDS 重启保活、MountPlanner 逃逸零容器创建拦截），并修复 runtime 卷 gate subpath 校验及运行目录属主"
fix_ref: "main"
---
# p127 本地补验：真实 Engine 上验证 volume subpath daemon 语义（t080 AC-001/002/009）

- 来源：t080 遗留（云端无 Docker Engine，2026-11-18 用户裁定：云端做不了的登记 pending、留待本地统一补验）
- 内容：在隔离真实 Engine（OrbStack/Linux arm64）上对 t080 的卷拓扑做正负对照：① subpath 不存在时 daemon 的行为（不得静默创建宿主空目录替代）；② Browser A 以 volume subpath 挂载时无法访问 Profile B 与父数据根，Stream 无任何 Profile/Artifact/字体挂载；③ 只读 subpath 挂载在容器内确实不可写；④ UDS/X11/Pulse 文件经 runtime 卷 subpath 挂载后 Browser/Stream 可达，Supervisor 重启不破坏存活实例 socket；⑤ 符号链接逃逸在创建前被 MountPlanner 拒绝。证据按 docs/blueprint/testing.md 脱敏保存并记录实际镜像 ID，对应 t080 AC-001、AC-002、AC-009 的真实链路部分。
- 处理：main；resolution=resolved；reason=本地 OrbStack 真实 Docker 与 release 20261118212912-a0fed8e 隔离链路上完成 6/6 正负验证（missing subpath 报错不建目录、Browser/Stream subpath 与 EROFS 只读强制、UDS 重启保活、MountPlanner 逃逸零容器创建拦截），并修复 runtime 卷 gate subpath 校验及运行目录属主
