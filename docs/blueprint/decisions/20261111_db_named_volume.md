# 028 运行时与部署可靠性：控制面 DB 进 named volume、部署身份与发布原子性（2026-11-11，t051）

- 背景：p068（2026-11-10 18:37–18:51 登录与 `/auth/session` 持续 500，日志 `disk I/O error`，自愈后 `integrity_check` 正常）根因高度疑似 WAL `-shm` wal-index 跨宿主/VM bind mount（macOS → OrbStack VM）的 mmap 与锁语义失稳；日志未记 SQLite 扩展错误码，无法区分 `SQLITE_IOERR_SHMMAP` 与 `SQLITE_IOERR_READ/WRITE`。同时应用层放大故障：`api/app.py` 的 `DBAPIError` 处理器把非 `IntegrityError` 一律映射为 500 `database_error` / `retryable=false`，`AuthService` 无重试，前端直接透传后端英文错误。review_20261110_200842 另指出：部署归属判定只凭可伪造标签（A59）、prefix 无校验且与派生命名空间重叠（A22）、发布指针两步写无 fsync（A43）、不可读库 fail-open（A44）、数据根仍带代际标识（A55）、证据与 Docker 错误脱敏规则分散（A58）。
- 选项：
    1. 数据库留在宿主 bind mount，只加错误码日志与重试。
    2. 数据库迁入 compose named volume `db`，并补齐错误分级、备份/恢复、部署身份、指针原子化与去代际化（本 task 采用）。
    3. 把 `com.cbrowser.instance-id` 复用为部署身份（A59 字面）。
- 结论：采用选项 2。
    - **数据库位置**：`cbrowser.db`（含 `-wal` / `-shm`）进 named volume `db`（`name: ${CBROWSER_PREFIX:-cbrowser}-db`），API 挂载 `db:/data/db`、`CBROWSER_DB_PATH=/data/db/cbrowser.db`；字体改为独立部署输入 `${CBROWSER_FONTS_DIR}:/fonts:ro`。WAL 的 `-shm` 与数据库始终同文件系统、同机。
    - **部署身份**：`instance_id = sha256("cbrowser-instance-v1\0<prefix>\0<data_root>")[:32]`（跨 release 稳定、跨实例区分），媒体子网池按 `pool_index = sha256(identity) mod 64` 得 `10.{192+index}.0.0/16`；写入 release env 与 manifest。归属判定以 `com.cbrowser.instance-id` 标签值 == 本实例 instance_id 为唯一依据（AC-021 规定的键名），删除 project 名豁免。运行时 id 随之归位：每轮唯一的运行时实例 id 不再占用该标签，改由容器运行时配置承载（Stream 环境变量 `CBROWSER_RUNTIME_INSTANCE_ID`、gated entrypoint `--instance-id`、Browser 命令 `--runtime-instance-id`），扫描/查找/回收经 `container_runtime_instance_id` 从配置读取，两身份各行其道、互不冒充。（2026-11-11 用户裁定：初版实现以语义冲突为由自造 `com.cbrowser.deployment-id` 键、并把默认前缀改为 `cbrowser`，均被驳回；本 ADR 按规定键名与默认部署前缀 `cbrowser-t005` 落定。）
    - **发布原子性**：`current_release` / `previous_release` 两文件改为单一 JSON `release_pointer.json`（`{"current": …, "previous": …|null}`），原子写含文件与父目录 fsync；损坏指针 fail-soft 替换。部署前容器内在线备份数据库并记入 manifest，`deploy.sh restore` 可恢复；旧宿主库只提示、不删除/移动。schema 检查先建 API 镜像再以只读挂载读 stamp，不可读库 fail-closed。
    - **错误分级**：`SQLITE_BUSY` / `SQLITE_LOCKED` / `SQLITE_IOERR`（含扩展码，按扩展码 & 0xFF 取主码）为瞬时错误 → 503（`database_busy` / `database_unavailable`）、`retryable=true`、`Retry-After: 1`；确定性错误仍 500 / 409。`AuthService` 对瞬时错误有界重试（最多 3 次）；登录页对两类 503 显示本地化文案。日志只记 SQLite 错误码名 + 方法/路径，永不记 SQL 文本与绑定参数（`str(exc.orig)` 与 `logger.exception` 的 traceback 行都会带 SQL）。
    - **前缀规则**：部署输入的资源 prefix 须匹配 `^[a-z0-9][a-z0-9_]*$`（不含连字符，避免与 `<prefix>-profiles` / `<prefix>-<NNNN>` 命名空间重叠），deploy.sh 与 Supervisor 启动都在任何 Docker 操作前校验；默认部署前缀 `cbrowser-t005` 是编译内既定标识、先于该规则存在，不在校验之列（deploy.sh 自身的默认 `cbrowser` 满足规则，校验其输入不变）。
    - **媒体网络超时**：Docker 网络调用以 30 秒为限（`CBROWSER_DOCKER_NETWORK_TIMEOUT` 可配）；分配锁只覆盖 get+分配+预留，创建在锁外执行，挂起时仅该次启动失败；创建冲突为错误，不重试。
    - **去代际化**：产品无代际标识；迁移文件改名 `0001_baseline.py`（原名含代际后缀，revision `b7e1c9d4a2f3` 不变），现行文档/源码/脚本中的代际自指清除，由 hygiene 测试守护；例外仅 deploy.sh 的旧库探测（须写出真实旧路径）与对应断言。
- 复查条件：真实部署（AC-013）、双实例真实 Docker（AC-014）、真实 Docker 挂起（AC-015）均未在本机验证（无 Docker 环境），须在用户机按 t032 演练补验；升级后 t051 之前创建的沙箱/网络无 instance-id 部署标签，新 Supervisor 不认领，属 A59 字面语义，由既有 orphan 路径处置。
- 替代：选项 1 留下 bind mount 失稳根因，只治标；选项 3 破坏运行时实例查找。指针两文件 + 无 fsync、不可读库 fail-open、project 名豁免均不保留。
