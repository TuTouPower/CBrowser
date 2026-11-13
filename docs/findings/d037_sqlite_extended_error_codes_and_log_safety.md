# d037 SQLite 扩展错误码分级与日志安全：主码取扩展码 & 0xFF，str(exc.orig) 与 traceback 行均含 SQL

- 来源：t051（2026-11-11），p068 故障定性需求（AC-007）：日志须含 SQLite 错误码名以区分 `SQLITE_IOERR_SHMMAP` 与 `SQLITE_IOERR_READ/WRITE`，但不得含 SQL 与绑定参数。
- 结论：**SQLite 扩展错误码的主码 = 扩展码 & 0xFF；瞬态当且仅当主码 ∈ {5 BUSY, 6 LOCKED, 10 IOERR}，含扩展码（如 261/517/262/778）；无码时按 `sqlite_errorname` 回落。`str(exc.orig)` 含 SQL 文本与绑定参数，禁止记入日志；`logger.exception` 的 traceback 行同样会带 SQL 文本，数据库错误日志须用不带 exc_info 的 `logger.error` / `logger.warning`。**
- 证据：
    - SQLAlchemy `DBAPIError` 的 `orig` 为 `sqlite3.OperationalError`，其 `sqlite_errorcode` 为扩展码（如 `SQLITE_BUSY_SNAPSHOT` 517 = 5 | 512、`SQLITE_LOCKED_SHAREDCACHE` 262 = 6 | 256、`SQLITE_IOERR_SHMMAP` 778 = 10 | 768）；主码 5/6/10 的判定须先 `& 0xFF`，直接比对扩展码会漏判。实现见 `src/backend/cbrowser/adapters/database/db_errors.py` 的 `classify_dbapi_error`，测试 `tests/unit/test_t051_db_errors.py` 覆盖扩展码矩阵。
    - 修正记录：`SQLITE_LOCKED_SHAREDCACHE` 扩展码为 262（6|256），不是 274（274 是 `SQLITE_READONLY` 系扩展码附近值，易混淆）。
    - 日志安全：`api/app.py` 的 DBAPIError 处理器只记 `sqlite_errorcode` / `sqlite_errorname` + 方法/路径；实测 `str(exc.orig)` 含触发语句与绑定参数，故旧代码记 `str(exc.orig)` 的行为已删除。
- 影响：API 503 分级（`database_busy` / `database_unavailable`，`retryable=true`，`Retry-After: 1`）、`ProfileService._handle_db_error`、`AuthService` 有界重试（最多 3 次）均用同一分级器；后续数据库错误日志与重试判定须复用 `classify_dbapi_error` / `retry_transient_db_errors`，不得各写一套。
- 现状：有效
- 复查条件：SQLAlchemy 或 sqlite3 的错误码属性命名变化时重跑分级矩阵测试。
