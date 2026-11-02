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

- 宿主机为每个 Profile 提供独立的 Artifact 存储区；上传落 `uploads/{artifactId}/`，下载落 `downloads/{artifactId}/`，容器内对应 `/exchange/uploads/` 与 `/exchange/downloads/`。
- 用户通过 API 上传原始文件字节，原子写入并返回 Artifact ID 与容器内 `container_path`；不向调用方暴露宿主路径。
- 浏览器内触发的下载通过 CDP 下载事件捕获，事件携带 `size_bytes` 与 `sha256`；Supervisor 转发 API 入库，下载文件移入 Artifact 存储区并计入配额。
- Agent 启动或 CDP 会话重建后扫描 `/exchange/downloads` 一次，为缺少完成事件的已完成文件补登；临时文件后缀排除，按路径与校验和去重。
- Selkies 会话内文件传输显式关闭（`file_transfers=none`），文件只经 Artifact Service 进出 Profile。

### 2.4 自动化入口

- 外部 CDP 自动化使用独立 `cbat_` Bearer 凭证，经 `/api/v1/automation/profiles/{profileId}/cdp` 进入 API，再经 Supervisor 转发到 Agent UDS，最终到浏览器 loopback CDP。
- 旧 `/api/profiles/{profileId}/cdp` 仅作为薄适配转发同一授权入口；不发布旧 CDP 端口。

## 3. 验收标准

- [x] AC-001：新数据库成功生成 WAL 文件，并发读取和写入不产生数据库锁表异常。
- [x] AC-002：通过 Alembic 成功将数据库 schema 从旧版升级至新版，现有 Profile 与 Cookie 数据完好无损。
- [x] AC-003：用户通过 API 上传的文件原子写入对应 Profile Artifact 存储，返回 Artifact ID 与 `/exchange/uploads/...` 容器路径，失败不留半文件。容器内 GTK 文件选择器可达性待确认，见 p014。
- [x] AC-004：浏览器中下载的文件能被 Runtime Agent 捕获（含校验和），Agent 重启后对账补登，重复事件不重复入库。
- [x] AC-005：外部自动化经独立凭证进入 Supervisor/UDS/loopback CDP，旧 CDP 入口仅转发新授权代理，不暴露公网 CDP 端口。
- [x] AC-006：Selkies 会话内文件传输显式关闭，客户端无入口，文件只能经 Artifact Service 进出 Profile。
