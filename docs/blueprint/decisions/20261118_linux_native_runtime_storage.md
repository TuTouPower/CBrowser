# 029 Linux 原生运行存储：卷拓扑、typed mount 与可恢复迁移（2026-11-18，t080）

- 背景：现场 4 个 Browser 的 Chromium userDataDir、预览、事件、引擎缓存与字体均经 macOS 宿主目录 bind mount 读写，宿主/VM 文件共享路径承载 SQLite/LevelDB 的锁与 mmap 语义；ADR 028 只把控制面 SQLite 迁入 named volume，未覆盖浏览器实际状态。挂载来源由 Supervisor 以自身容器内路径充当 daemon 宿主路径（同路径挂载技巧），数据归属与宿主目录布局强耦合，目录缺失时 daemon 还会隐式创建 root 属主的空宿主目录充当挂载源。
- 选项：
    1. 保留宿主 bind mount，只调 VirtioFS/缓存参数或锁策略。
    2. 全部运行数据迁入按部署前缀命名的 Linux named volume，以 volume + 精确 subpath 的 typed mount 授权消费（本 ADR 采用）。
    3. 读写 daemon 私有卷物理路径（`_data` 目录）拼接挂载。
- 结论：采用选项 2。
    - **卷拓扑**（名称由部署资源前缀派生，与既有 DB 卷同规则）：`<prefix>-db` 保持独立（ADR 028 不变）；`<prefix>-data` 承载 Profile userDataDir、Artifact（上传/下载）、预览、runtime-events/outbox、快照、engine/GeoIP 缓存与必要持久控制状态（control 下的事件游标、操作日志、下载游标/死信、spool）；`<prefix>-fonts` 承载字体集（subpath 为 `<platform>/<set_id>`）；`<prefix>-runtime` 承载运行期文件，卷内布局冻结为 `<profile_id>/…`（X11/Pulse/实例运行目录）、`gates/<profile_id>/<instance>/<role_dir>`（策略 gate）、`sockets/…`（Agent UDS 根）、`.secrets/<profile_id>/…`（Profile 凭据）。终态事件/outbox 在 data 卷，不随运行期目录重建丢失。
    - **逻辑路径不变**：API 与 Supervisor 容器内逻辑路径保持 `/data`、`/fonts` 与既有 socket 根；Supervisor 的 data_root 成为纯容器内逻辑路径，不再是宿主路径。消费方只经 `storage_layout.MountPlanner` 把已校验的本地逻辑路径解析为 `(volume, subpath, target, read_only)` 的 typed mount；解析不出受管卷归属的路径在构造期拒绝（fail-closed），不存在回退到宿主 bind 的路径。Browser 只获得自身 Profile 的精确 subpath，Stream 不获得 Profile/Artifact/字体，字体对 Browser 只读且只给绑定集合。
    - **SDK 契约**：docker-py 7.2.0 的 `Mount(..., subpath=...)` 序列化为 `VolumeOptions.Subpath` 已由 s025 实证（结论 d050）；daemon 对 subpath 缺失/只读/UDS 的实际行为按 Engine ≥26 / API ≥1.45 公开契约冻结，真实 Engine 正负对照登记 p127 待本地补验，不以云端结果冒充。
    - **运行期边界**：Supervisor 重启不清空 runtime 卷；stale socket/gate 仅按所有权标签、实例 id 与活跃性证据清理（沿用既有 socket_root 清理契约）。Supervisor 仍是唯一 Docker Socket 持有者，API 仍是唯一 DB 写者，不新增通用远程文件服务。
    - **迁移**：`storage_migration` 工具提供只读盘点/dry-run、实际写者与容量/归属校验、恢复点可恢复验证、staging 拷贝、逐文件 SHA-256 摘要校验、journal 分阶段切换与幂等恢复/回退；任一前置校验失败在切换前中止并给出脱敏可定位原因。源宿主目录只读保留、不自动删除；跨 DB/data/fonts 的切换不是单一原子事务，以 journal + 旧集保留恢复一致状态，卷引用记入 release/恢复点记录。先证实备份可恢复，才允许改写指针或数据。
    - **字体衔接**：本 ADR 只把字体旧资产按原内容迁入 fonts 卷并保持 set_id 与绑定；发布权限、目录记录与审计由 t081 完成。正式运行不再从旧宿主字体根读取；宿主字体目录仅作显式导入/导出源。配置/凭据类小型只读挂载（`/run/secrets/*`）保留，但不得承载 Profile 热数据。
- 复查条件：p127 在真实 Engine 上完成正负对照后复查本 ADR 的 daemon 语义假设；若 subpath 缺失行为或只读隔离与公开契约不符，先修订本 ADR 与 MountPlanner 再继续部署，不退回宿主 bind。
- 替代：选项 1 留下文件共享路径承载热数据的根因；选项 3 依赖 daemon 私有实现，升级即碎，且绕过卷生命周期管理。
