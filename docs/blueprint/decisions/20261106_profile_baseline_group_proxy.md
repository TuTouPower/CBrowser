# 023 Profile 领域模型重建：单 baseline、Group/Proxy 引用与配置版本三分（2026-11-05，t035）

- 背景：`docs/plan_20261105_ui_redesign.md` WP06/WP07 要求 Profile 由「业务 Tag + 内嵌 proxy 字符串」改为「分组库 + 代理库引用」，代理密码需单一来源且不进快照/日志/SSE；同时迁移链 0001-0009 已累积 9 个修订，旧代 schema 与新模型不可增量兼容。AC-002 要求旧代 DB 失败封闭并输出重建指引。认证 SOCKS5 的引擎能力经正式 spike `s013_authenticated_socks5_engine_probe` 验证（finding `d031`）。
- 选项：① 保留 0001-0009 链并新增增量迁移 + 兼容读取；② 折叠为单 baseline、旧代 DB 失败封闭；③ 代理密码随版本快照复制；④ 认证 SOCKS5 一律 422 拒绝。
- 结论：
    - **破坏性升级不留兼容层**：迁移目录只保留 `0001_baseline.py`（revision `b7e1c9d4a2f3`，`down_revision=None`），删除 0001-0009。API 启动（`migrations.py` 的 `LegacySchemaError` + `REBUILD_GUIDANCE`）与 `scripts/deploy.sh`（只读探测 `alembic_version`）均对旧代 DB 失败封闭，不修改该 DB、不构建镜像、不移动 release 指针。**生产数据必须经用户批准的备份与迁移流程重建**，不自动升级、不静默删数据。
    - **release controller 按修订链判回退下限**：`current_revision_chain()` 读取当前源码树的修订 id，旧代 release（退役 0001-0009 head）拒绝作为回退目标；同代 release 之间的发布与回退通过。删除原 `applied_migration_version` 字符串比较机制。
    - **Proxy 凭据单一来源**：密码只存 `proxies` 表；配置版本快照只存 `proxy_id` 与 `proxy_credential_revision`（无代理时为 `None`），不含密码。`update_proxy` 改连接字段时在同一事务为引用 Profile 生成新版本并广播 SSE；改 name/region/notes 不生成。Supervisor 经只读 internal 端点取凭据，Runner 挂载 0600 `proxy_credentials.json`，revision 不一致或文件缺失即失败封闭 `proxy_credentials_changed`。
    - **配置版本三分**：只改元数据（name/notes/sort_order/group_id）、只改即时策略 `capture_preview`、或提交与当前值相同的运行配置，都不生成新版本、运行中不出现待应用；只有运行配置字段值变化才生成。
    - **认证 SOCKS5 走端到端分支**：Chromium 146 实测支持 `socks5://user:pass@host:port`（正确凭据 `loaded=True`、错误凭据 `net::ERR_SOCKS_CONNECTION_FAILED`），故 Runner 直接构造 `--proxy-server`，不采用 422 拒绝创建的降级路径。
- 复查条件：Chromium 主版本或指纹平台升级后重跑 `s013` 的三组实测（无认证 / 正确凭据 / 错误凭据），若引擎不再接受带认证 SOCKS5 则按 AC-008 回退到 API 422 分支；后续 schema 破坏性升级沿用「单 baseline + 旧代失败封闭 + 修订链回退下限」流程。
- 替代：①/③/④ 均不采用（兼容层与自动升级违背破坏性升级不留包袱原则；快照复制密码违背凭据单一来源；422 拒绝与实测引擎能力不符）。
