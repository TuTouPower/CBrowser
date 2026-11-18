---
slug: storage_and_artifacts
status: active
tasks: [baseline, t078, t080]
---
# 需求规范：数据持久化、迁移与文件交换 (storage_and_artifacts)

## 1. 业务目标与适用范围

本文档规定 cbrowser 的 SQLite WAL 数据库持久化、Alembic 迁移机制、历史数据平滑升级以及容器文件交换（Exchange）与下载捕获契约。

## 2. 行为契约

### 2.1 数据库持久化与并发

- 核心元数据持久化于宿主机 `/data/cbrowser.db`。
- 采用 SQLite 引擎，启动时必须开启 WAL 模式（`PRAGMA journal_mode=WAL`），并配置合理的 `busy_timeout`。
- 引入 SQLAlchemy 2.0 异步 ORM 并通过 Alembic 管理版本化数据库迁移。
- 禁止在业务中执行非版本化的临时建表或删表逻辑。
- 核心表结构包括：
    - `profiles`：Profile 基本元数据，含 `group_id` / `proxy_id` 标量引用（t035）
    - `profile_groups` / `proxies`：分组库与代理库条目（t035 取代业务 Tag 表与内嵌 proxy 字段）
    - `profile_config_versions`：不可变运行参数版本快照，不含密码与业务 Tag
    - `profile_runtimes`：期望状态与真实观测状态，含起停时间戳与浏览器版本字段（t035）
    - `runtime_events`：运行事件去重与退出事件记录（随 Profile 级联删除）
    - `artifacts`：上传与下载文件元数据
    - `profile_deletions`：删除意图与阶段结果（t078；每目标一行，含名称快照、失败阶段与分步清理明细，终结后保留作审计）
    - `audit_events`：生命周期操作审计（无外键，不随 Profile 删除）
    - `settings`：系统级键值配置
- 排他控制租约、控制会话与 StreamTicket 已废弃（ADR 007）；数据库不包含 `control_sessions`、`control_leases` 或 `stream_tickets` 表。

### 2.2 旧数据库迁移兼容

- 旧版 `profiles.db` 迁移工具归 t010，当前未实施；本节描述的是 t010 的交付契约，不代表已交付。
- **t035 修订（2026-11-05）**：迁移链已折叠为单一 baseline 修订 `b7e1c9d4a2f3`，业务 Tag 表与内嵌 `proxy` 字段已移除。旧 schema 代（0001-0009）数据库在 API 启动与部署时失败封闭并输出重建指引，不做自动升级、不修改该库；t010 式的自动迁移工具不再交付（ADR 023）。生产数据须经用户批准的备份与迁移流程重建。
- 迁移工具支持 `--dry-run` 模式，提前校验数据完整性。
- 迁移必须保留现有 Profile UUID、名称、分组与代理引用、指纹配置以及用户历史目录（Cookies, 网站存储），严禁重新生成指纹或清除登录态。

### 2.3 文件交换与下载捕获

- 宿主机为每个 Profile 提供独立的 Artifact 存储区；上传落 `uploads/{artifactId}/`，下载落 `downloads/{artifactId}/`，容器内对应 `/exchange/uploads/` 与 `/exchange/downloads/`。
- 用户通过 API 上传原始文件字节，原子写入并返回 Artifact ID 与容器内 `container_path`；不向调用方暴露宿主路径。
- 浏览器内触发的下载通过 CDP 下载事件捕获，事件携带 `size_bytes` 与 `sha256`；Supervisor 转发 API 入库，下载文件移入 Artifact 存储区并计入配额。
- Agent 启动或 CDP 会话重建后扫描 `/exchange/downloads` 一次，为缺少完成事件的已完成文件补登；临时文件后缀排除，按路径与校验和去重。
- Selkies 会话内文件传输显式关闭（`file_transfers=none`），文件只经 Artifact Service 进出 Profile。

### 2.4 自动化入口

- 外部 CDP 自动化使用独立 `cbat_` Bearer 凭证，经 `/api/v1/automation/profiles/{profileId}/cdp` 进入 API，再经 Supervisor 转发到 Agent UDS，最终到浏览器 loopback CDP。
- 旧 `/api/profiles/{profileId}/cdp` 仅作为薄适配转发同一授权入口；不发布旧 CDP 端口。

### 2.5 内容类型、删除与实例信任（t021）

- 内容类型统一规范化（上传与下载入库共用）：去参数、转小写、缺省 `application/octet-stream`，仅拒绝非法 header 值；不再拒绝可执行类型或把下载强制重标为 octet-stream，声明类型按元数据保存（用户决策 D2=A）。用户侧下载响应恒为 `application/octet-stream` 附件 + `nosniff`，与记录类型无关。
- Artifact 删除为可恢复两阶段：先持久化 `delete_requested_at` 意图（迁移 0008），再删文件、删行；失败保留意图与文件，服务启动时续跑未完成意图；意图未完成期间重复调用幂等，完成后再次调用返回 404；记录路径逃逸时拒绝并保留意图，不递归删除异常目录。
- 下载报告实例信任：报告的 `runtime_instance_id` 必须是该 Profile 当前绑定或 `runtime_events` 历史中出现过的实例，未知/伪造实例在触碰文件前被拒绝（`rejected`）。

### 2.6 Linux 原生卷存储（t080 / ADR 029）

- 正式运行数据全部位于按部署前缀命名的 named volume：`<prefix>-db`（控制面 DB）、`<prefix>-data`（Profile 用户目录、Artifact、预览、事件/快照、引擎缓存）、`<prefix>-fonts`（字体集）、`<prefix>-runtime`（运行期文件、策略 gate、Agent socket、Profile 凭据）。宿主机目录不再承载热数据，只作迁移源与显式导入/导出源。
- 容器挂载一律是 volume + 精确 subpath 的 typed mount：Browser 只得自身 Profile 子树，Stream 不得任何 Profile/Artifact/字体，字体对 Browser 只读且只给绑定集合；挂载来源缺失/越界/符号链接逃逸在创建前拒绝，不创建空宿主源替代。
- 宿主旧布局经 `scripts/storage_migration.py` 一次性迁入：只读盘点/dry-run、实际写者与容量/归属校验、环境恢复点可恢复验证、staging 拷贝与逐文件 SHA-256 校验、journal 分阶段切换、幂等恢复与回退；源目录只读保留、不自动删除。迁移后 UUID、seed、配置版本、字体 set_id、Profile 文件摘要与 Artifact 引用保持一致。
- 克隆、重置、删除、上传/下载、预览与恢复点在新存储中保持 2.3/2.5 与 t066 的既有语义；重置不删 Artifact，克隆不复制活动锁/socket。

## 删除数据清理语义（t078）

- Profile 删除按固定顺序清理：Artifact 服务移除该 Profile 的全部文件与元数据 → 删除 Profile 数据目录与运行时目录 → 清理预览图 → 最后删除数据库行（级联配置版本、运行态与运行事件）。任一步失败即删除整体失败：不静默吞错、不删数据库行，已完成步骤记入删除意图的 `detail.steps`，重试时对已清理步骤幂等跳过。
- 删除失败不影响其他 Profile 的数据与运行实例；`profile_deletions` 行在终结（done/failed）后保留，作为删除结果的长期追踪记录，不随 Profile 行删除而消失。

## 3. 验收标准

- [x] AC-001：新数据库成功生成 WAL 文件，并发读取和写入不产生数据库锁表异常。
- [ ] AC-002：通过 Alembic 成功将数据库 schema 从旧版升级至新版，现有 Profile 与 Cookie 数据完好无损（旧库迁移工具归 t010，当前未交付）。
- [x] AC-003：用户通过 API 上传的文件原子写入对应 Profile Artifact 存储，返回 Artifact ID 与 `/exchange/uploads/...` 容器路径，失败不留半文件。远程页面点击文件输入框弹出 GTK 文件选择对话框，侧栏 `Uploads` 书签直达 `/exchange/uploads`（p014，真实容器 E2E `test_p014_file_input_opens_chooser_with_uploads_bookmark`）。
- [x] AC-004：浏览器中下载的文件能被 Runtime Agent 捕获（含校验和），Agent 重启后对账补登，重复事件不重复入库。
- [x] AC-005：外部自动化经独立凭证进入 Supervisor/UDS/loopback CDP，旧 CDP 入口仅转发新授权代理，不暴露公网 CDP 端口。
- [x] AC-006：Selkies 会话内文件传输显式关闭，客户端无入口，文件只能经 Artifact Service 进出 Profile。

## 前端上传失败报告（t023）

- 前端多文件上传顺序执行并在首个失败处停止；失败提示给出已成功数、失败文件名与未处理数，不输出文件内容。删除与上传等写操作携带每次调用独立生成的幂等键，自动重试复用同键。
