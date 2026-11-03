# bundle_followup_q_evolution_03

## Summary

实际核对范围：docs/blueprint/persistence.md 全文、decisions.md（ADR 004）、docs/specs/runtime_persistence.md 与 storage_and_artifacts.md 及 specs_index（关键词全量 grep）、src/backend/migrations/versions/0001–0006 的 downgrade 实现、src/backend/cbrowser/adapters/database/migrations.py 迁移运行器、DOCKER_DEPLOYMENT.md §4、docs/guides 四篇（grep 零命中）、docs/v2_architecture_plan.md §15.5、docs/tasks/t010_v2_data_migration/task.md 与 note.md 状态，并以 grep 核对全仓 downgrade 调用方、迁移 CLI、备份演练记录。结论：怀疑成立。须区分两层：①迁移期备份——计划文档 §15.5 与 t010 的 AC-004/AC-005 有设计（备份覆盖 /data/cbrowser.db 等五项、失败恢复旧 DB 与目录、黑盒演练），但 t010 仍为 backlog（依赖 t009）、AC 全部未勾选、迁移 CLI 在代码中不存在，属未实施的设计；②切换后常态——生效契约层（blueprint/persistence.md 与全部 specs）没有任何 cbrowser.db 备份、恢复或版本回退条款，唯一的运维备份/恢复程序（DOCKER_DEPLOYMENT.md §4）只覆盖 legacy 部署的数据根 ~/.cbrowser，不覆盖 v2 的 /data/cbrowser.db；schema 版本回退方面，downgrade 部分不可逆（0006 为 no-op 不恢复被删键、0004 以常量默认值重建列不恢复逐行原值、0003 直接删列），且无任何代码调用 downgrade、无文档政策、迁移运行器升级前也不做数据库文件备份。仓内无任何 cbrowser.db 备份恢复的演练记录。应用内 profile_config_versions 不可变快照只提供 Profile 配置版本回退，不构成数据库级数据恢复或部署版本回退路径。

## Findings

No findings.

## evidence

```json
[
  "docs/blueprint/persistence.md 全文无 cbrowser.db 备份/恢复/版本回退条款；全文唯一『备份』是 L109 Profile 重置的 .reset-backup-<uuid> 目录改名（重置内部回滚机制），其余篇幅为单写者、状态收敛、幂等与脱敏契约",
  "docs/blueprint/decisions.md:40 ADR 004 仅以『极简运维，单文件备份』作为选 SQLite 的便利性理由，无备份程序、周期、保留策略或恢复步骤",
  "docs/specs/runtime_persistence.md:12 明示『非范围：旧系统用户数据迁移（由后续独立任务验收）』；对 runtime_persistence.md、storage_and_artifacts.md、specs_index.md 以『备份/恢复/backup/restore』grep 零命中，生效 spec 层无备份恢复契约",
  "src/backend/migrations/versions/0006_clean_snapshot_modes.py：upgrade 从 profile_config_versions 快照 JSON 中删除 runtime_mode/viewer_mode 两键，downgrade 为 pass 并注释『Removed keys were single-value constants; no data restoration is needed.』——单向迁移，不恢复旧键",
  "src/backend/migrations/versions/0004_remove_runtime_viewer_mode.py：downgrade 以 server_default 常量（docker/webrtc）重建两列，不恢复逐行原值；0003_artifact_storage.py downgrade 直接 drop_column sha256/storage_path（数据丢失）；0001/0002 downgrade 为 drop_table",
  "src/backend/cbrowser/adapters/database/migrations.py:25-42 run_database_migrations 只执行 command.upgrade(cfg, 'head')，升级前不复制或备份数据库文件；对 src/ 与 scripts/ grep『command.downgrade/downgrade(』在运行代码中零命中，downgrade 无调用入口",
  "DOCKER_DEPLOYMENT.md:85-108 §4『数据备份与恢复』的 tar 备份/恢复对象是现行 legacy 部署数据根 ~/.cbrowser（单容器、宿主机端口 56661、AUTH_TOKEN，全文未提 /data 与 cbrowser.db）；v2 数据库默认路径为 /data/cbrowser.db（src/backend/cbrowser/api/main.py:10，CBROWSER_DB_PATH 默认值），不在该流程覆盖范围内",
  "docs/v2_architecture_plan.md:989-1003 §15.5 要求备份覆盖 /data/cbrowser.db、/data/settings/、/data/profiles/、/data/artifacts/、/data/runtime-events/，且迁移工具失败时恢复旧数据库和目录——但这是 2026-10-27 计划文档对未建迁移工具的要求，未进入 blueprint/specs 生效契约，无具体操作程序",
  "docs/tasks/t010_v2_data_migration/task.md:30-31 AC-004/AC-005 将迁移期备份恢复与独立黑盒演练列为验收项，但 note.md front matter 记 status=backlog、depends_on=t009，AC 全部未勾选；task.md:82 finalization 清单把『docs/blueprint/persistence.md：迁移与回退契约』『DOCKER_DEPLOYMENT.md：停机/备份/恢复与切换步骤』列为 t010 收尾时才更新的文档，即切换后回退契约目前尚未成文",
  "阴性检索：src/ 与 scripts/ 中无迁移 CLI（dry-run/dry_run grep 零命中）；docs/pending、docs/findings 对『备份/backup』零命中；blueprint/specs/DOCKER_DEPLOYMENT.md 中无任何备份恢复演练记录"
]
```

## result

```json
"confirmed"
```
