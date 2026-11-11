> 与代码冲突时以代码与生效 spec 为准，并须同步修正本文。

# 持久化架构与单写者契约 (persistence)

本文定义 CBrowser 系统的持久化架构、数据库写入归属、t035 单一 baseline 修订创建的数据表模型、配置版本不可变快照及运行状态收敛契约。

## 1. 架构定位与单写者边界

- **单一写入者**：`cbrowser-api` 容器是系统中**唯一的 SQLite 业务数据库写入者**。
- **Supervisor 边界**：`cbrowser-supervisor` 严禁挂载或直接读写 SQLite 数据库文件。Supervisor 与 API 之间通过受控内部认证 RPC 进行通信：上报运行事件、上报观测状态、绑定运行实例、拉取配置快照。
- **连接与并发策略**：
    - 强制开启 SQLite WAL 模式（`PRAGMA journal_mode=WAL`）。
    - 设置忙等待超时为 5000 毫秒（`PRAGMA busy_timeout=5000`）。
    - **顺序（t056 A1）**：`busy_timeout` 必须先于 `journal_mode=WAL` 设置，且 WAL 切换本身不遵守 busy handler——切换失败时在 `busy_timeout` 窗口内有界重试，直至切换成功或超时。实测：只调换两行顺序仍会在锁争用时立即 `database is locked`。
    - 开启外键约束（`PRAGMA foreign_keys=ON`）。
    - 写入事务统一在连接层由 `BEGIN IMMEDIATE` 开启，确保读-改-写操作物理串行化执行，杜绝并发不相交 PATCH（如同时更新 name 与 notes）出现更新丢失（Lost Updates）。
    - 业务事务保持短小紧凑，**严格禁止在数据库事务内调用 Docker API 或等待浏览器/媒体管线启动**。
    - 当锁争用超时超过 5000ms 时，API 捕获 `OperationalError` 并向客户端返回标准的 HTTP 503 Service Unavailable 及 `Retry-After: 1` 响应头，指示客户端可重试，事务自动回滚，不造成事务悬挂或数据损坏。

## 2. 核心数据表结构 (SQLAlchemy 2.0 + Alembic)

迁移以 t035 的单 baseline 修订 `b7e1c9d4a2f3` 为起点（t035 AC-001）；空库 `alembic upgrade head` 后 schema 与 ORM autogenerate 无差异。t041 在 baseline 之上追加增量迁移 `0002_fingerprint_platform.py`：新增 `fingerprint_platform` / `font_set_id` 两列并删除 `font_bundle` 列。t056 追加增量迁移 `0009_profile_display_number_not_null.py`（revision `796adb0bf159`）：`display_number` 改为 NOT NULL。旧 schema 代（0001-0009）数据库在 API 启动与部署时失败封闭并输出重建指引，不自动升级、不修改该库（ADR 023）。系统数据库不包含任何独占控制租约（`leases`）或持久 `ViewerConnection`：

- **只进不退（t056 A60）**：全部修订的 `downgrade()` 一律抛明确的 unsupported-downgrade 错误，不再提供回退路径；`0004_preview_backoff.py` 的「列已存在则跳过」分支与 `0003_network_transaction.py` 的历史混合形态补丁分支已删除（升级输出结构不变）。
- **旧库守卫（t056 A29）**：数据库含业务表、但 `alembic_version` 表缺失 / 无行 / 版本号为空时，API 启动拒绝并抛 `LegacySchemaError` 附重建指引，不静默升级、不猜测版本。

01. `profiles`：
    - 字段：`id`, `name`, `fingerprint_seed`, `group_id`, `proxy_id`, `timezone`, `locale`, `screen_width`, `screen_height`, `gpu_family`, `humanize`, `human_preset`, `geoip`, `clipboard_sync`, `auto_launch`, `color_scheme`, `fingerprint_platform`, `font_set_id`, `launch_args`, `extension_paths`, `allow_3p_cookies`, `set_google_default`, `capture_preview`, `restore_session`, `transparent_proxy`, `portable_cookies`, `notes`, `user_data_dir`, `sort_order`, `display_number`, `current_config_version`, `created_at`, `updated_at`。
    - `group_id` / `proxy_id` 为可空外键引用（t035），取代已删除的业务 Tag 表与内嵌 `proxy` 字段；删除分组时 `group_id` 置 null，代理被引用时删除受限。
    - `display_number` 自 t056 起为 NOT NULL（迁移 `0009_profile_display_number_not_null.py`，revision `796adb0bf159`，增量迁移：先按确定性顺序回填存量 NULL 再改列约束）；领域模型 `Profile.display_number: int` 无默认值，读到 NULL 行时仓储抛明确错误，不静默补 1。
    - `fingerprint_platform` 默认 `windows`（`windows` / `macos`）；`font_set_id` 可空，引用同平台的不可变字体集；两者都属运行配置，修改任一生成新 `ProfileConfigVersion`（t041）。`font_bundle` 列已随 `0002_fingerprint_platform.py` 删除。默认 `user_data_dir` 为 `/data/profiles/{profileId}/profile`。
02. `profile_groups`：
    - 字段：`id`, `name`, `color`, `sort_order`, `created_at`, `updated_at`；名称唯一、颜色取自调色板、可排序。
03. `proxies`：
    - 字段：`id`, `name`, `scheme`, `host`, `port`, `username`, `password`, `credential_revision`, `country_code`, `region_label`, `notes`, `created_at`, `updated_at`；名称唯一，密码是凭据的唯一存储点。
04. `profile_config_versions`：
    - 字段：`id`, `profile_id`, `version`, `snapshot`, `created_at`。`(profile_id, version)` 唯一约束。
    - `snapshot` 是不可变 JSON：含 `config` 与 `proxy_credential_revision`（无代理时为 null），**不含密码、不含业务 Tag**。只有运行配置字段值变化才生成新版本；元数据（name/notes/sort_order/group_id）、`capture_preview` 或提交相同运行配置都不生成（t035 AC-006）。历史快照严格只读。
05. `profile_runtimes`：
    - 字段：`profile_id` (PK), `desired_state`, `observed_state`, `runtime_instance_id`, `config_version`, `failure_count`, `restart_blocked`, `last_exit_event_id`, `last_started_at`, `last_stopped_at`, `browser_product`, `browser_user_agent`, `updated_at`。
    - 维护 Profile 的用户意向状态与实际观测运行状态。`config_version` 严格代表当前运行实例实际绑定的配置快照版本；`last_started_at` / `last_stopped_at` 为 ISO 8601 带时区，浏览器版本字段来自容器内 CDP `Browser.getVersion`（t035 AC-009/010）。
06. `artifacts`：
    - 字段：`id`, `profile_id`, `name`, `size`, `kind`, `state`, `content_type`, `picker_name`, `sha256`, `storage_path`, `delete_requested_at`, `created_at`。
    - 存储 Profile 关联文件的元数据索引，二进制文件存放在对应文件卷。`delete_requested_at` 是持久化删除意图：先落意图、再删文件、最后删行；服务启动时续跑未完成意图。
07. `settings`：`key` (PK), `value`, `updated_at`；系统级键值配置。
08. `runtime_events`：
    - 字段：`event_id` (PK), `profile_id`, `runtime_instance_id`, `event_type`, `exit_code`, `exit_reason`, `config_version`, `payload`, `created_at`。
    - 持久化运行期退出/生命周期事件，通过 `event_id` 主键执行物理去重；随 Profile 级联删除，审计总账由独立 `audit_events` 承担。
09. `audit_events`：
    - 字段：`id` (PK), `entity_type`, `entity_id`, `action`, `actor`, `details`, `created_at`；记录关键操作审计与幂等性校验签名。
10. `profile_controls`：`profile_id` (PK), `owner`, `generation`, `agent_instance_id`, `agent_session_id`, `handoff_reason`, `handoff_detail`, `agent_reclaim_allowed`, `pending_supervisor_close`, `updated_at`。
11. 认证与自动化表：`admins`（`id`, `username`, `password_hash`, `created_at`, `updated_at`）、`sessions`（`id`, `token_hash`, `csrf_token`, `expires_at`, `created_at`）、`automation_tokens`（`id`, `name`, `token_hash`, `profile_ids`, `revoked`, `created_at`, `revoked_at`, `expires_at`）。

## 3. 运行状态分离与状态收敛契约

### 3.1 意图与观测状态解耦

- `desired_state`（用户意图）：取值 `stopped` 或 `running`。
- `observed_state`（实际观测）：取值 `stopped`、`starting`、`running`、`stopping`、`error`。
- **意图不臆造观测**：
    - 用户调用启动接口仅将 `desired_state` 置为 `running`，`observed_state` 必须保持当前的实际状态（如 `stopped`），严禁在容器未启动前臆造 `observed_state=running`。
    - 用户手动启动操作重置 `failure_count=0` 并解除 `restart_blocked=False`。
    - 用户调用停止接口将 `desired_state` 置为 `stopped`，`observed_state` 依然反映运行中容器，直到容器实际停止事件到达。

### 3.2 Supervisor 观测与实例绑定契约

- **实例绑定（Bind Instance）**：Supervisor 在拉起容器前向 API 申请或提交绑定 `runtime_instance_id` 与目标 `config_version`；API 校验该版本快照是否存在，并标记 `observed_state=starting`。
    - **实例防覆盖保护**：若当前 Profile 已存在且处于 `running` 状态的活跃实例，严禁被无 CAS 校验的其他实例绑定盲目覆盖；已被替代的历史实例 ID 不得重新绑定，返回 HTTP 409 Conflict。
    - **同实例幂等绑定**：同一实例携带相同配置版本重复发起绑定为幂等无操作，严禁将已处于 `running` 的状态倒退为 `starting`。
- **观测上报（Report Observed State）**：Supervisor 在检测到容器实际就绪或变化时上报 `observed_state`。若上报的 `runtime_instance_id` 与数据库当前绑定实例不匹配，作为过期实例拒绝（HTTP 409 Conflict）。

### 3.3 退出事件收敛

- **正常退出**（`exit_code == 0`）：
    - 目标与观测双收敛：`desired_state = stopped`, `observed_state = stopped`, `runtime_instance_id = None`。
    - 记录 `last_exit_event_id`，清零 `failure_count`。防止服务重启后因残留 `desired_state=running` 误重新拉起已关闭浏览器。
- **异常退出**（`exit_code != 0`）：
    - 保留已有的 `desired_state`（若原本为 running 则仍为 running，若用户已主动发起停止置为 stopped 则严格保持 stopped，绝不被晚到的异常崩溃推翻为 running）。
    - `observed_state = stopped`, `runtime_instance_id = None`。
    - `failure_count` 递增 1；第 4 次异常（首次异常后三次重试均失败）设置 `restart_blocked = True` 触发熔断保护（ADR 008）。
- **配置版本与跨实例严格比对**：
    - 退出事件所声明的 `config_version` 必须与该实例实际绑定的 `config_version` 完全一致；若试图以上报未实际应用到容器的配置版本触发退出，API 识别为 `invalid_config_version` 并拒绝，不改变状态机。
    - 重复的 `event_id` 被物理去重，返回 duplicate，不再重复转换状态机或累加计数；多并发重复事件安全仲裁，不抛出未捕获 500。
    - 晚到达的旧实例事件（`event.runtime_instance_id != current.runtime_instance_id`）记录入事件日志，但不改变当前新实例的状态或计数。
    - 非退出事件（如 heartbeat）仅记录并响应成功，绝不误触发生命周期状态停止或异常计数。

## 4. 幂等性控制与并发保护

- **操作幂等（Operation ID）**：
    - API 支持请求头 `Idempotency-Key` / `X-Operation-ID` 或 Query 参数 `operation_id`。
    - 请求指纹严格覆盖：`action`（操作动作）+ `target`（目标 Profile ID）+ 归一化 `payload`。
    - 同一操作 ID 针对同一目标且载荷一致时，API 幂等重放既有处理结果，不产生重复实体或多余版本。
    - 若同一操作 ID 被复用于不同目标 Profile、不同动作或不同载荷，API 返回明确的 HTTP 409 Conflict（`idempotency_conflict`），阻止跨实体污染。
    - 重放启动意图（`desired_state=running`）的旧操作 ID 时，保持幂等重放语义，**严禁将崩溃累积的 `failure_count` 清零**；仅全新的手动启动请求可重置失败计数与阻断标记。
    - 三个写入点（create/update/set_desired_state）的审计匹配共用单一 helper（t021）；目标已删除后的重放有确定性语义：update 重放返回已删除（None），create 重放按审计中的实体 ID 确定性重建同一身份，不生成新 ID。
    - **分组与代理同等语义（t056 A23）**：group / proxy 的 create / update / delete 同样支持 `Idempotency-Key`，同一 helper 与同一审计表；重放时不重复触发探测等副作用。`POST /groups/reorder` 不带幂等键（全量替换、服务层校验全集，见 domain.md）。
- **查询加载边界（t021，t035 修订）**：
    - Profile 集合关系（versions/runtime/artifacts）统一 `lazy="noload"` + `passive_deletes=True`：删除走数据库外键级联（`ON DELETE CASCADE` + `foreign_keys` pragma），普通读取不隐式整表加载集合；`group_id` / `proxy_id` 是标量外键引用，不再有业务 Tag 集合（t035）。
    - 下载去重在 SQL 层按 `(profile, sha256, storage_path)` 精确过滤，不再把候选集拉回内存逐条比对。
- **并发版本分配**：
    - Profile 采用仅传递修改字段并在 `BEGIN IMMEDIATE` 事务内就地合并的方式，杜绝了预读导致的更新丢失；更新版本号自动计算最新最大版本号递增，并在并发冲突时安全重试。

## 5. 结构化诊断与敏感数据脱敏

- **安全结构化日志**：
    - API 消费运行时事件时，通过标准 Python 日志组件（`cbrowser.events`）输出单行机器可读的 JSON 日志（`RUNTIME_EVENT_JSON: {...}`），禁止绕过日志体系使用底层 `sys.stderr.write`。发射器位于包内 `cbrowser/runtime_event_log.py`（t021 自旧顶层 `diagnostics` 模块迁入，旧模块已删除）。
    - 启动阶段配置 Alembic `fileConfig(..., disable_existing_loggers=False)`，保障应用日志体系在迁移后不被静默注销。
    - 字段受严格白名单约束：`event_id`, `profile_id`, `runtime_instance_id`, `event_type`, `exit_code`, `exit_reason`, `config_version`, `outcome`, `timestamp`。
- **严格脱敏与 ID 安全表示**：
    - 标准 UUID 与已知系统安全格式 ID 保留原值输出；对于非标准规范的任意不透明 ID，采用单向不可逆哈希（`id_hash_<sha256[:12]>`）进行安全表示，既保持日志跨行关联性，又杜绝在 ID 字段内注入敏感 Token/Cookie 泄漏。
    - 退出原因（`exit_reason`）通过安全枚举白名单清洗，未知非白名单原因归一化为 `custom_reason`，阻止注入任意私密载荷。
    - 全局异常处理器不向日志或响应体泄漏 SQL 绑定参数或堆栈细节。
    - 请求校验失败（HTTP 422）响应体剔除原始输入反射，防止日志和错误体回显敏感密码、Token、Cookie 或剪贴板字符串。

## 6. 控制面数据库存储位置与错误分级（t051）

- **存储位置**：控制面数据库（含 `-wal` / `-shm`）位于 compose named volume `db`（`name: ${CBROWSER_PREFIX:-cbrowser}-db`），API 挂载 `db:/data/db`、`CBROWSER_DB_PATH=/data/db/cbrowser.db`；数据库文件不位于任何宿主 bind mount 上。根因：SQLite WAL 要求所有进程同机共享内存，`-shm` wal-index 跨宿主/VM bind mount（macOS → OrbStack VM）时 mmap 与锁语义失稳（p068：2026-11-10 登录持续 500 `disk I/O error`，自愈后 `integrity_check` 正常）；named volume 使数据库、WAL 与 `-shm` 始终同文件系统、同机。
- **部署前备份与恢复**：`deploy.sh` 在 `up` 前对有 live stamp 的数据库做容器内在线备份（`sqlite3 Connection.backup()`），副本存宿主可取得的 `$DEPLOY_DIR/backups/cbrowser-<ts>.db`，路径记入 manifest `database_backup`；`deploy.sh restore <backup-file>` 可把备份拷回 volume（须有当前 release，永不删除备份文件）。volume 无库但宿主旧路径存在时部署提示旧库位置与处置方式，旧文件不被删除、移动或覆盖。
- **错误分级**：`SQLITE_BUSY` / `SQLITE_LOCKED` / `SQLITE_IOERR`（含扩展码，按扩展码 & 0xFF 取主码）为瞬时错误，API 返回 503（`database_busy` / `database_unavailable`）、`retryable=true`、`Retry-After: 1`；确定性错误仍 500 `database_error` / `retryable=false`，`IntegrityError` 仍 409。锁争用超过 `busy_timeout=5000` 时仍按 §1 返回 503（错误码现为 `database_busy`）。
- **日志定性**：数据库错误日志包含 SQLite 错误码名（`sqlite_errorcode` / `sqlite_errorname`）、请求方法与路径，不包含 SQL 文本、绑定参数值、密码或会话 token。`str(exc.orig)` 含 SQL 与绑定参数，禁止记入日志；`logger.exception` 的 traceback 行同样会带 SQL 文本，故数据库错误日志用不带 exc_info 的 `logger.error` / `logger.warning`。
- **迁移文件**：单 baseline 修订 `b7e1c9d4a2f3` 的文件名为 `0001_baseline.py`（t051 由带代际后缀的旧名改名，revision 不变；产品无代际标识）。

## Profile 复制与重置的目录一致性

- 配置复制只写数据库：新 Profile ID、配置版本、标签与同一指纹种子；`user_data_dir` 指向新 ID 的空目录，不复制源用户数据或 Artifact。
- 状态复制在源 `desired_state` 与 `observed_state` 均为 stopped 时执行；跳过 `SingletonLock`、`SingletonCookie`、`SingletonSocket`，按符号链接原样复制，并用相对路径 + SHA-256 + 大小清单逐项比对源与副本。复制后再次校验源未启动，失败或并发启动时删除未发布副本。
- 重置先把源 `user_data_dir` 原子重命名为同目录 `.reset-backup-<uuid>`，再更新指纹种子并生成新配置版本；成功后删除备份，数据库或文件操作失败时删除新目录并把备份改名回原位。Artifact 存储独立，不随重置删除。
- 复制/重置操作使用 `Idempotency-Key` 复用审计记录；重复请求返回已有结果，不产生重复 Profile。
