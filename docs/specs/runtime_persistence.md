# 需求规范：运行时状态与持久化契约 (runtime_persistence)

## 1. 业务目标与适用范围

本文档定义 CBrowser 架构重构在 `t002: v2_backend_foundation` 中累积实现的生产后端数据持久化、Profile 配置生命周期、运行状态模型、不可变版本快照、并发事务控制及结构化运行时诊断契约。

**适用范围**：

- `cbrowser-api` v1 核心控制接口及单机 SQLite WAL 数据持久化；
- Profile 配置版本、标签、运行时状态、Artifact 元数据、系统设置、运行事件及审计存储；
- 独立 API 进程在隔离测试目录与真实文件锁争用场景下的行为保证；
- **非范围**：旧系统用户数据迁移（由后续独立任务验收）、Docker 容器编排、WebRTC 媒体管线或旧入口废弃。

## 2. 可观察行为规范 (AC-001 ~ AC-006)

### 2.1 Profile CRUD 与数据完整性 (AC-001)

- **接口契约**：
    - `POST /api/v1/profiles`：创建新 Profile。配置字段保留计划 15.2 中有效字段；未提供指纹种子时随机生成整数；默认 `user_data_dir` 为 `/data/profiles/{profileId}/profile`；`sort_order` 正确持久化。
    - `GET /api/v1/profiles`：获取 Profile 列表。
    - `GET /api/v1/profiles/{id}`：获取单个 Profile 详情及标签。
    - `PUT /api/v1/profiles/{id}` 或 `PATCH /api/v1/profiles/{id}`：修改 Profile。
    - `DELETE /api/v1/profiles/{id}`：级联删除 Profile 及其关联标签、版本快照、运行时状态与运行事件（`runtime_events`）；`audit_events` 无外键关联，保留作为生命周期操作审计总账。
- **空值更新与校验边界**：
    - 可空字段（`notes`, `proxy`, `timezone`, `locale`, `color_scheme`）传入 `null` 时成功置空；
    - 非空字段（`gpu_family`, `name`, `screen_width`, `screen_height`）传入 `null`、空字符串或非法负数范围时，返回 HTTP 422 拒绝，已保存数据完全未受破坏。
    - `tags` 三态：字段缺席表示不修改现有标签；显式 `null` 与空数组 `[]` 均表示清空标签，并生成新的配置快照。
- **物理重启持久化**：
    - 经由独立 `uvicorn` 子进程启动服务，完成写入后终止该进程并重新拉起新实例加载同 SQLite 数据库文件，所有字段、版本号与标签内容完整保留。

### 2.2 不可变配置快照、幂等与事务原子性 (AC-002)

- **不可变配置快照**：
    - 每次成功创建或修改 Profile，均在 `profile_config_versions` 表中生成递增的版本快照记录（版本 1, 2, 3...）。
    - 快照完整序列化当前配置数据及关联标签列表。
    - 历史快照为只读不可变对象，后续对 Profile 的修改绝不改变早期版本快照的内容。
- **操作幂等控制**：
    - 客户端通过 `Idempotency-Key` / `X-Operation-ID` 头部或 `operation_id` 参数传递操作唯一标识。
    - 并发发送 5 个携带完全相同操作 ID 的创建请求，数据库严格只生成 1 条实体记录，所有并发请求返回同一实体结果，无 500 错误。
    - 若复用同一操作 ID 但携带不同的请求载荷发起请求，API 返回明确的 HTTP 409 Conflict。
- **事务原子性**：
    - 在外键违规或数据约束失败时，数据库连接完整回滚，绝不残留未挂载孤儿标签、半写版本记录或缺失主表的脏数据。

### 2.3 运行状态收敛与跨实例隔离 (AC-003)

- **状态模型**：
    - `desired_state`: `stopped` | `running`
    - `observed_state`: `stopped` | `starting` | `running` | `stopping` | `error`
    - `runtime_instance_id`: 实例标识符
    - `config_version`: 当前实际绑定的配置快照版本
    - `failure_count`: 连续失败次数计数器
    - `restart_blocked`: 连续失败达到 4 次后的熔断标记（ADR 008：首次异常 + 三次自动重试）
    - `last_exit_event_id`: 最近处理的退出事件 ID
- **意图与观测解耦**：
    - 设置 `desired_state=running` 不会臆造 `observed_state=running`（保持实际的 `stopped` 直至容器绑定启动）。
    - 用户手动启动操作清零 `failure_count` 并将 `restart_blocked` 重置为 `false`。
    - Profile 配置修改后，`profile_runtimes.config_version` 保持当前运行实例已绑定的快照版本，不随 Profile 配置修改自动跳跃。
- **事件消费收敛规则**：
    - **正常退出**（以 `exit_code=0` 为准）：`desired_state` 与 `observed_state` 均收敛为 `stopped`，`runtime_instance_id` 清空。
    - **异常退出**（`exit_code != 0`）：保留已有的 `desired_state`（若已为 `running` 则保持 `running`，若用户已主动发起停止置为 `stopped` 则严格保持 `stopped`，绝不翻转为 `running`）；`observed_state` 设为 `stopped`；`failure_count` 加 1；累计达到 4 次时触发 `restart_blocked=true`（ADR 008：failure_count 1/2/3 分别等待 2/10/30 秒重试，第 4 次失败阻断）。
    - **重复与晚到事件**：重复 `event_id` 被幂等丢弃并不二次转换状态；晚到达的旧实例事件（`runtime_instance_id` 不符）以及未在数据库建立有效快照的非法 `config_version`（如 999）均被安全拦截并记录，绝不破坏新实例的运行状态。
    - **非退出事件**：心跳事件（`heartbeat`）不触发退出或停机状态流转。

### 2.4 SQLite 锁竞争、Busy-Timeout 与忙等待 (AC-004)

- **物理参数设置**：
    - 数据库文件物理验证 `PRAGMA journal_mode=WAL` 与 `PRAGMA busy_timeout=5000`。
- **锁争用忙等待验证**：
    - 在外部通过独立 SQLite 连接持有排他写锁（`BEGIN IMMEDIATE`）保持 1.5 秒：API 写入请求自动执行忙等待重试，在锁释放后成功提交（耗时 1.4s ~ 4.5s 之间），返回 201 Created。
    - 外部持有排他锁保持 6.0 秒（超过 5000ms 超时阈值）：API 请求在 ~5.0 秒处超时并返回标准的 HTTP 503 Service Unavailable，响应头包含 `Retry-After: 1`，响应体包含 `{"error": "database_busy", "retryable": true}`，严禁抛出未捕获异常或泄露底层 SQL 语法细节。
    - 锁释放后，后续写请求立即成功执行，数据库连接池无未关闭悬挂事务。

### 2.5 空目录自启、契约导出与数据隔离 (AC-005)

- **全新目录自启**：
    - 在完全干净、不存在任何文件的空目录中指定数据库路径，独立 API 进程自动创建目录结构、执行 Alembic 迁移并完成 8 张核心数据表的创建。
- **OpenAPI 契约一致性**：
    - API 运行时动态提供 `/openapi.json` 规范；
    - 导出工具 `scripts/export_openapi.py` 直接从 FastAPI 应用实例导出契约至 `schemas/openapi/cbrowser_v1.json`；
    - 所有新路由结构与参数定义符合 OpenAPI 3.1 契约规范。
- **正式数据目录零污染**：
    - 本任务所有测试与验证均在专属临时目录执行，基线目录文件与正式数据目录变动为 0。

### 2.6 结构化运行时诊断与敏感数据脱敏 (AC-006)

- **幂等与加载边界（t021）**：
    - create/update/set_desired_state 三个写入点的审计匹配收敛为单一 helper；目标已删除后的重放语义确定：update 重放返回已删除，create 重放按审计实体 ID 重建同一身份（含并发竞争恢复），异签名同 ID 仍 409。
    - Profile 集合关系（tags/versions/runtime/artifacts）统一 `noload` + `passive_deletes`，删除依赖外键级联，普通读取只显式加载 tags；下载去重下推到 SQL 的 `(profile, sha256, storage_path)` 精确匹配；`utc_now_iso` 以领域层为唯一实现。
- **结构化机器解析**：
    - API 消费运行时事件时，向 stderr 输出机器可解析的 JSON 日志：`RUNTIME_EVENT_JSON: {"event_id": ..., "profile_id": ..., "runtime_instance_id": ..., "event_type": ..., "exit_code": ..., "exit_reason": ..., "config_version": ..., "outcome": ..., "timestamp": ...}`。发射器位于包内 `cbrowser/runtime_event_log.py`（t021 迁入，旧顶层 `diagnostics` 模块已删除）。
- **数据脱敏与安全防御**：
    - 字段由严格白名单过滤，`exit_reason` 经由安全枚举白名单清洗，未知非白名单原因归一化为 `custom_reason`；
    - 系统日志、标准输出以及 HTTP 4xx/5xx 错误响应体中严禁泄漏注入的密码、Token、Cookie、剪贴板文本或私密笔记文本；
    - 全局异常处理器不输出带参数的 SQL 跟踪日志。

## 3. 运维与验证命令

### 3.1 独立数据库迁移与初始化

```bash
PYTHONPATH=src/backend uv run --no-project python -c "
from cbrowser.adapters.database.migrations import run_database_migrations
run_database_migrations('/path/to/cbrowser.db')
"
```

### 3.2 动态导出 OpenAPI 契约

```bash
PYTHONPATH=src/backend uv run --no-project python scripts/export_openapi.py
```

### 3.3 启动独立 API 服务

```bash
CBROWSER_DB_PATH="/path/to/cbrowser.db" CBROWSER_PORT=56661 PYTHONPATH=src/backend uv run --no-project python -m uvicorn cbrowser.api.main:app --host 127.0.0.1 --port 56661
```

### 3.4 运行后端单元与集成测试套件

```bash
PYTHONPATH=src/backend uv run --no-project --with pytest --with pytest-asyncio --with httpx --with aiosqlite --with sqlalchemy --with alembic --with fastapi --with pydantic --with uvicorn --with jsonschema pytest tests/ -s -v
```

## 4. 验收证据

本节不复制验收状态，避免与历史记录产生第二份可漂移的勾选。AC-001 ~ AC-006 的验收证据以已归档 task 与独立 review 为准：

- t002 的六项 AC 在 `docs/archive/tasks/t002_v2_backend_foundation/task.md` 中由实施与独立 review 复核后勾选；正式 review 结论见同目录 `review_code.md` 与 `review_test.md`。
- 本 spec 的后续修订（`failure_count=4`、`tags` 三态、删除 Profile 时级联删除 `runtime_events` 而保留 `audit_events`）属于 review `review_20261101_075819` 的 A12/A26/D1 契约同步，实现与验收由对应修复 task 及其 review 证据承担，不回填为 t002 历史通过。
