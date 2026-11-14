# d045 db_restore.py 无校验直覆会毁活库，环境级恢复改用 restore_point 恢复点

- 来源：t066_profile_identity_state 的 DB backup/restore 演练（2026-11-13）
- 结论：`scripts/db_backup.py` 在线 backup 可用（integrity ok、stamp 796adb0bf159）；`scripts/db_restore.py` 无校验直接覆盖 —— 把备份文件改坏 7 字节后执行恢复，活库随即不可读（`database disk image is malformed`）且原数据已毁。故环境级恢复不能以「tar + db_restore」为契约。
- 证据：`docs/archive/tasks/t066_profile_identity_state/task.md:82` 的未知契约清单；定稿协议实现见 `scripts/restore_point.py`。
- 影响：环境备份/恢复走 `restore_point.py` 恢复点（无写者时取同一恢复点、staging 全量校验哈希/完整性/版本/空间、带 journal 成套切换、中断回滚、旧集保留 `.pre-restore-<switch-id>`）；`db_backup`/`db_restore` 仅保留给发布流程的 DB 单件备份/回退。
- 现状：有效
