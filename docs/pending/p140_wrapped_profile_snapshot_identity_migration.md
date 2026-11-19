---
pid: "p140"
slug: "wrapped_profile_snapshot_identity_migration"
status: "closed"
resolution: "transferred"
reason: "已核实范围并转交 t089"
fix_ref: "t089"
---
# p140 身份迁移漏改嵌套配置快照，存量环境启动返回 502

- 现象：升级后点击已有环境「启动」，界面显示 `Supervisor start failed (502): bad_gateway: Configuration query failed`。当前部署中，API 返回对应的 v1 快照（HTTP 200），Supervisor 在创建容器前校验失败。已读取日志和快照复现，未执行环境启动或写入部署数据。
- 影响：三个已停止环境（#22、#23、#24）的当前 v1 均无效。日区 #26 正在运行的 v3 校验通过，历史 v1/v2 仍无效。只要选择受影响的快照，显式启动与 `recovery_coordinator._load_profile_config` 恢复路径均会拒绝，日志已观察到两条路径报 `ValidationError`。迁移前置校验也会漏掉嵌套快照内强制 GPU 或无效字体绑定，可能按错误的平台或语言处理字体默认值。
- 根因：产品数据迁移缺陷。仓库创建、更新及代理凭据轮换都将配置存为 `{config, proxy_credential_revision}`。`0013_profile_identity.py` 的 `_blocking_entries` 与 `_rewrite_snapshots` 把顶层当成配置。数据库已到 `d7e3a91f4c62`，受影响行仅外层被补写，API 按运行契约解开 `config` 后仍交付 `gpu_family=auto` 及 `color_scheme=null`。现行 `ProfileConfig` 拒绝两者。合成数据库也证实嵌套 `gpu_family=nvidia` 逃过迁移前置校验。修复范围覆盖尚未运行原迁移的数据库，以及已盖章且遗留外层字段的数据库。保留快照版本和 `proxy_credential_revision`，按原迁移规则处理快照内平台、语言、字体、配色及无法等价转换的值。
- 测试缺口：`tests/unit/test_t075_migration.py` 的 11 个用例通过，快照夹具为顶层平铺 JSON。补生产写入形状下的迁移及补偿迁移验证，覆盖平铺历史、已盖章的外层误写、嵌套非法 GPU/字体的阻塞、代理凭据版本保留、按嵌套语言/平台派生 CJK 和字体，以及通过真实 API 快照读取后成功进入 Supervisor 启动与恢复流程。
- 线索：`.scratch/profile_start_and_identity/repro_migration.py` 用项目现有 Alembic 夹具复现平铺通过、嵌套失败和前置校验绕过。`.scratch/profile_start_and_identity/probe_snapshots.py`、`.scratch/profile_start_and_identity/probe_db.py` 分别以只读 RPC 和 SQLite `mode=ro` 核对当前部署，输出仅含字段与环境编号。
- 处理：t089；resolution=transferred；reason=已核实范围并转交 t089
