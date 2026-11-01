# 需求规范：数据持久化、迁移与文件交换 (storage_and_artifacts)

## 1. 业务目标与适用范围

本文档规定 CBrowser 的 SQLite WAL 数据库持久化、Alembic 迁移机制、历史数据平滑升级以及容器文件交换（Exchange）与下载捕获契约。

## 2. 行为契约

### 2.1 数据库持久化与并发

- 核心元数据持久化于宿主机 `/data/cbrowser.db`。
- 采用 SQLite 引擎，启动时必须开启 WAL 模式（`PRAGMA journal_mode=WAL`），并配置合理的 `busy_timeout`。
- 引入 SQLAlchemy 2.0 异步 ORM 并通过 Alembic 管理版本化数据库迁移。
- 禁止在业务中执行非版本化的临时建表或删表逻辑。
- 核心表结构包括：
    - `profiles`：Profile 基本元数据
    - `profile_config_versions`：不可变运行参数版本快照
    - `profile_tags`：标签与分类
    - `profile_runtimes`：期望状态与真实观测状态
    - `runtime_events`：运行事件去重与退出事件记录（随 Profile 级联删除）
    - `artifacts`：上传与下载文件元数据
    - `audit_events`：生命周期操作审计（无外键，不随 Profile 删除）
- 排他控制租约、控制会话与 StreamTicket 已废弃（ADR 007）；数据库不包含 `control_sessions`、`control_leases` 或 `stream_tickets` 表。

### 2.2 旧数据库迁移兼容

- 升级工具支持对已有旧版 `profiles.db` 进行安全迁移。
- 迁移工具支持 `--dry-run` 模式，提前校验数据完整性。
- 迁移必须保留现有 Profile UUID、名称、标签、指纹配置以及用户历史目录（Cookies, 网站存储），严禁重新生成指纹或清除登录态。

### 2.3 文件交换与下载捕获

- 宿主机为每个 Profile 提供独立的 `exchange/` 目录供容器挂载。
- 用户通过 API 上传的文件原子写入 `exchange/`，并在容器内的 GTK 文件选择器中生成书签便捷访问。
- 浏览器内触发的下载通过 CDP 下载事件进行捕获，下载完成后原子移入 Artifact 存储区并计入配额限制。

## 3. 验收标准

- [ ] AC-001：新数据库成功生成 WAL 文件，并发读取和写入不产生数据库锁表异常。
- [ ] AC-002：通过 Alembic 成功将数据库 schema 从旧版升级至新版，现有 Profile 与 Cookie 数据完好无损。
- [ ] AC-003：用户通过 API 上传的文件能在容器内的文件选择对话框中被选择。
- [ ] AC-004：浏览器中下载的文件能被 Runtime Agent 准确捕获并体现在 Artifacts 列表中。
