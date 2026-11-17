# 004 采用 SQLite WAL + Alembic 作为单机持久化方案（2026-10-26）

- 背景：cbrowser 定位为单机 Docker 部署的隐私浏览器控制平台，写入端唯一受 Control API 调度，无需分布式数据库开销。
- 选项：
    1. 引入外部 PostgreSQL 或 Redis。
    2. 使用嵌入式 SQLite，启用 WAL 模式并配合 Alembic 进行版本化迁移。
- 结论：采用选项 2。极简运维，单文件备份，性能与并发满足单机高可用需求。
- 替代：无
