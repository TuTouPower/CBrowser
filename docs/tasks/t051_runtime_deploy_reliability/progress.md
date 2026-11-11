---
tid: "t051"
slug: "runtime_deploy_reliability"
title: "运行时与部署可靠性：控制面 DB、字体挂载、沙箱诊断、实例归属与发布原子性"
status: "done"
branch: "t051_runtime_deploy_reliability"
worktree: ""
review_level: "full"
review_limit: "5"
verify_limit: "5"
diff_anchor: "3331ed3c12518849a416a0c74b6c844f033fc8c7"
depends_on: ""
conflicts_with: ""
note: "来源 p059、p063、p066、p068；用户 2026-11-10 选仅 DB 移入 named volume; ；扩充 review_20261110_200842 A3 A22 A43 A44 A55 A57 A58 A59"
---

# Task 进展

front matter 只经 `task.py` 修改；reviewer 只写对应 `review_*.md`。

## 实施笔记

执行期记录关键步骤、决策、验证、阻塞和用户批准的新轮次上限。

创建期不预测实施步骤。只记有追溯价值的内容；无事项时写“无”。

### 引用逐项核对（2026-11-11，t028 教训，本 task 第一步）

- p059/p063/p066/p068：存在，位于 `docs/archive/pending/`（已由 18e343f「转办 p059/p060/p063/p066-p069 至 t051-t053」从 todo 迁入 archive，即转办即归档）；`pending.py archive` 对其无可再归档的操作，见下「已归档来源」。
- `docs/reviews/review_20261110_200842/adoption_decision.md`：A3（L49）、A22（L201）、A43（L369）、A44（L377）、A55（L465）、A57（L481）、A58（L489）、A59（L497）均存在；A57 已确认 task.md 背景第 1、3 条措辞已按其修复说明改写（「高度疑似…尚未区分」+ AC-007 定性说明）。
- `compose.yaml`：DB bind mount `${CBROWSER_DATA_ROOT}:/data`（L25）、字体 env `${CBROWSER_DATA_ROOT}/fonts`（L19/L98）、字体 volume（L26/L105）属实；task.md 引用的行号有 ±1 漂移（18/26/27），实质属实。
- `scripts/deploy.sh`：`DATA_ROOT` 默认 `$ROOT/data/v2`（L50）属实；无 prefix 格式校验属实；`atomic_write`（L228）无 fsync、current/previous 两步写（L319-327）属实；`current_db_stamp` 对不可读库返回空串 fail-open（L176-177 注释自述）属实；无 `media_subnet_pool` 分配、无 `instance_id` 属实；`check_prefix_conflict`（L368）以 project 名 + `<prefix>-profiles` 豁免属实。
- `src/backend/cbrowser/supervisor/docker_adapter.py`：Stream 路径只保留 `type(exc).__name__`（L1604-1611）属实；Browser 路径未经脱敏拼接 `{e}`（L1383-1386）属实；cache initializer（L604-606）、X11 helper（L798-812）、策略 helper（L342-360）同样只留类名属实；网络创建/列举/检查（L846-990）多处为未经脱敏 `{e}`。
- `container_spec.py:64`：`com.docker.compose.service` 为静态传入值属实；`browser_labels`/`stream_labels` 已带 `com.cbrowser.profile-number`。
- `src/backend/cbrowser/adapters/database/session.py`：WAL（L58）属实（task.md 未写全路径，仅称 session.py）；`app.py:391` DBAPIError 处理器统一 500/`database_error`/`retryable=false`、日志只记类名与 `str(exc.orig)` 属实。
- `ProfileService._handle_db_error`（`services/profile_service.py:334`）：只识别 `SQLITE_BUSY`/`SQLITE_LOCKED`（主码 5/6）属实。
- `LoginPage.tsx`：实际路径为 `src/frontend/src/features/auth/LoginPage.tsx:30`，`setError(err.message)` 直接透传属实。
- `scripts/redact_evidence.py`：仅 Bearer、`cbrowser_session` cookie、token/password/secret 键值三类规则属实；无 URL userinfo、其它 cookie 名、含空格完整引号值、家目录路径规则。
- `.env.example:1`：`# CBrowser v2 deployment.` 属实；`0001_baseline_v2.py` 存在，revision `b7e1c9d4a2f3` 属实。
- E2E/夹具宿主读库位点：`tests/e2e/conftest.py`、`test_supervisor_recovery_e2e.py`、`test_artifact_delete_resume_e2e.py`、`test_supervisor_container_graph_e2e.py`、`tests/fixtures/*` 均含 `cbrowser.db`/`CBROWSER_DB_PATH` 引用属实；其中多数已用 tmp 路径，仅 `tests/fixtures/gateway_probe/topology.py:474` 的容器内 `/data/cbrowser.db` 需随新拓扑调整。
- 未能本地核实（环境缺口，非虚假引用）：`data/fonts` 有 windows/macos 两组、`data/v2/fonts` 为空——本机主仓与 worktree 均无 `data/` 目录（gitignore 的运行数据，只在用户机存在）；字体相关断言改用夹具字体集验证。
- 已归档来源：p059/p063/p066/p068 在 base 已处于 `docs/archive/pending/`（18e343f 转办时归档），闭环后无需也不得再执行 `pending.py archive`（来源不在 todo/parked 中）；收尾以本记录为准。

### 设计裁决：部署身份标签键（A59/AC-021 字面与现行语义冲突）——用户裁定驳回偏离，已按规定名修正

- 冲突事实：`com.cbrowser.instance-id` 已被 Browser/Stream 沙箱占用为**运行时实例 id**（每轮启动唯一），`core._lookup_browser_container`、`docker_adapter` 扫描/残留/恢复路径与多处 E2E 均以该键比对会话运行时 id；若按 A59 字面把部署 instance_id 写进同一键，运行时查找永不命中、重建/恢复全部失效。初版实现据此自造独立键 `com.cbrowser.deployment-id` 承载部署身份（AC-021 可测行为保留、仅键名偏离），并提交用户裁定。
- **用户裁定（2026-11-11）：驳回。用规定名 `com.cbrowser.instance-id`，不许新造键名绕过。已按裁定修正完毕。**
- 核查结论：两处 id **不是同一身份**——部署 instance_id 是 `sha256("cbrowser-instance-v1\0<prefix>\0<data_root>")[:32]` 确定性派生、跨 release 稳定；运行时 id 是每轮启动新生成的 `inst_<uuid12>`。故不走「统一为同一 id」，而是统一**键的语义**并让运行时 id 归位到它本就存在的通道，从根因消解冲突：
  - 键语义统一：`com.cbrowser.instance-id` 只表示**所属部署的 instance_id**。compose 四服务、网络、x11/cache-init helper，以及配置了部署身份时 Supervisor 创建的 Browser/Stream/policy-helper 沙箱，全部以该键携带部署 instance_id；未配置部署身份时沙箱不带该键（缺失即不认领，与 AC-021 一致，未配置模式沿用 prefix 归属回退）。归属判定（`_owns_deployment`、core lookup 的服务端过滤、network ownership、deploy.sh 冲突判定）全部以该键值 == 本实例 instance_id 为唯一依据。
  - 运行时 id 归位：它在容器创建时本就写入了**运行时配置**——Stream 环境变量 `CBROWSER_RUNTIME_INSTANCE_ID`、gated entrypoint 的 `--instance-id`、Browser 命令的 `--runtime-instance-id`（inspect 的 `Config` 与 list 摘要的 `Command` 串均可读回）。新增唯一读取点 `container_spec.container_runtime_instance_id(container)`（Config Env → Entrypoint/Cmd 参数 → Command 串回退），五处原标签读取点全部切换：core lookup 的候选匹配与 observed 值、扫描上报的 instance_id 与缺失拒绝、`_reclaim_created_stream` 与 `cleanup_stream_residue` 的身份核验、`_runtime_policy_ready` 的 gate 目录推导。标签从此不承载运行时 id，只带部署标签的容器不会被误认作任何运行时会话（新增提取器测试钉住）。
  - 两侧行为同时成立：AC-021（伪造 project + 身份不符拒绝、缺身份标签不认领——t027 与 supervisor_identity 套件）与运行时查找行为（p058 found/mismatch/missing、a8 终态观察、a9 残留回收、扫描恢复）均有测试钉住且全绿，见收尾报告测试数。
  - 附带收口：执行者 Area G 让 core lookup 无条件读 `self.docker.deployment_instance_id`，使不带该属性的 core 级 doubles（p058、a8 的 fake）抛 AttributeError 被吞成 unavailable——p058 红 3 条、a8 红 6 条系该遗留（执行者回归清单未含此两文件）；本次已按 doubles 契约补齐 `deployment_instance_id=None` 并把两处 fake 的运行时 id 迁入 Config 通道，两文件全绿。

### Area A 完成（2026-11-11）：共享脱敏 + 沙箱启动诊断（A58/AC-020、AC-011）

- 新模块 `src/backend/cbrowser/redact.py`：`redact(text)` 与 `docker_error_detail(exc)`（空串时回落类名）。规则顺序：URL userinfo → Bearer → Basic → Cookie/Set-Cookie 全部键值（保留 Expires/Path/Domain/Max-Age/SameSite 属性）→ 裸 `cbrowser_session`/`cbrowser_csrf` → 敏感键完整引号值（含空格，双/单引号）→ 敏感键无引号值 → 家目录路径（`/Users/<name>`、`/home/<name>`、`C:\Users\<name>` → `<home>`）。引号值正则分组为 prefix=1/value=2/closing=3，替换须用 `\1<redacted>\3`；键规则需 `(?![Bb]earer\b|[Bb]asic\b)` 前瞻以保留 scheme。
- `scripts/redact_evidence.py` 改为委托 `cbrowser.redact`（sys.path 引导沿 `scripts/import_font_set.py` 前例）；`redact()` 仍可 import（`tests/e2e/test_gateway_ac003_media_e2e.py:444` 引用）。
- 新测试 `tests/unit/test_t051_shared_redaction.py`（18 tests：参数化矩阵、幂等、`docker_error_detail`、脚本委托）全绿；`test_t051_docker_error_detail.py`（11 tests）全绿；`test_a9_stream_residue.py`、`test_t035_proxy_runtime.py`、`test_evidence_redaction.py` 回归全绿，合计 68 passed。
- `docker_adapter.py` 接线：policy install、`_run_policy_helper`、cache initializer、X11 helper（含 logger.error 的 `detail=` 字段）、网络创建/列举/检查/重建/挂接/断开、Browser/Stream 启动均改用 `docker_error_detail`；`StreamContainerResidueError` 新增可选 `cause_detail`（消息后缀，不改旧构造签名；a9 断言只验 `.residue`/`.cause_type`，不受影响）。同文件其余原始 `{e}` 拼接（媒体网络生命周期、infra 挂接、cleanup_network_by_name、scan inspect）同属 p059 缺陷类，一并脱敏；仅留类名的清理/扫描警告（socket root、移除/扫描失败）不在 AC-011 启动路径内，未动。`_install_network_policy` 的 helper.logs() 输出仍原样写 warning 日志（A4 范围，未动）。
- **A11 与 AC-011 的边界（全量 unit 回归时发现，2026-11-11）**：初版把 `_install_network_policy` 的 run 与 wait 合并为一个 try、统一含脱敏 detail，导致 `test_a11_policy_timeout.py` 3 失败（wait 超时的 transport 异常文本含 A11 构造的秘密 URL，共享规则不覆盖裸 token 路径段；且 `daemon down` 不应出现在消息中）。根因区分：`containers.run()` 失败是辅助容器**启动**失败（Docker API 错误，形态已知、A58 规则可覆盖）→ 含脱敏 detail（AC-011）；`helper.wait()` 超时是 transport 层错误（文本无界、可带任意 URL）→ 只留类名（A11「timeouts stay redacted」）。已把该函数拆为两个 try：run 失败含 detail、wait 失败只留类名；两路测试均不改动（A11 6 tests + `test_t051_docker_error_detail.py` 11 tests 合跑 35 passed，含 shared_redaction 18）。
- 补充说明：`test_redact_evidence_script_delegates_to_shared_rules` 的 `<redacted>` 计数期望为 `>= 4`（URL userinfo 把 proxy-user 与 s3cret 两个秘密合并为一个 marker，非实现缺失）。
- AC-020、AC-011 已验证，task.md 已打勾。

### Area B 完成（2026-11-11）：DB 错误分级 + API 503 + auth 有界重试（AC-005/AC-006/AC-007）

- 新模块 `src/backend/cbrowser/adapters/database/db_errors.py`：`classify_dbapi_error`（主码 = 扩展码 & 0xFF；瞬态当且仅当主码 ∈ {5 BUSY, 6 LOCKED, 10 IOERR}，含扩展码；无码时按 `sqlite_errorname` 回落）与 `retry_transient_db_errors`（async 装饰器，最多 3 次、退避 0.05s/0.1s，整方法重跑、每次新会话；仅瞬态 DBAPIError 重试）。
- `ProfileService._handle_db_error` 改用分级器：BUSY/LOCKED → `DatabaseLockError`（不变）；IOERR → 新 `DatabaseUnavailableError`（定义于 profile_service.py，与 DatabaseLockError 并列）；确定性错误原样重抛。
- `api/app.py`：DBAPIError 处理器按分级返回——瞬态 503（BUSY/LOCKED → `database_busy`，IOERR → `database_unavailable`，`retryable=true`，`Retry-After: 1`）；确定性错误仍 500 `database_error`/`retryable=false`。日志只记 `sqlite_errorcode`/`sqlite_errorname` + 方法/路径，**不再记 `str(exc.orig)`**（含 SQL 与绑定参数；`logger.exception` 的 traceback 行也会带 SQL 文本，故改用 `logger.error`/`logger.warning` 不带 exc_info）。新增 `DatabaseUnavailableError` 处理器（503 `database_unavailable`）。IntegrityError 仍走既有 409 处理器（Starlette 按 MRO 优先匹配）。
- `auth/service.py`：11 个方法加 `@retry_transient_db_errors`（has_admin、authenticate_admin、create_session、get_valid_session、revoke_session、create_automation_token、list_automation_tokens、revoke_automation_token、resolve_automation_token_id、authorize_automation、authorize_viewer）。速率限制在 DB 访问前判定（authenticate_admin/authorize_automation 均先查 limiter），重试不重复计数；create_session 每次尝试生成新 token（未提交的首尝试为无害孤儿）；authorize_automation 的拒绝审计写在重试时可能重复（可接受的审计噪声）。`init_admin_password` 未加（其内部 has_admin 已重试）。
- 测试 `tests/unit/test_t051_db_errors.py`（26 tests：分级矩阵含扩展码 261/517/262/778、重试 3 次上限/确定性不重试、API 503 形状与日志无秘密、ProfileService 映射、真实 SQLite 库上的登录重试恢复 + 持久失败 3 次后抛 + has_admin 重试）全绿；`test_auth_service.py`、`test_a6_error_contract.py` 回归全绿；`test_api_subprocess.py::test_ac004_sqlite_busy_timeout_contention_and_recovery`（真实 5s busy 超时 → 503 database_busy → 恢复）仍通过。合计本区 54 passed。
- 修正记录：测试数据 SQLITE_LOCKED_SHAREDCACHE 扩展码应为 262（6|256），初写 274 实为 SQLITE_READONLY 扩展码，已更正。
- AC-005、AC-006、AC-007 已验证，task.md 已打勾。

### Area C 完成（2026-11-11）：登录页 DB 503 友好提示（AC-008）

- `LoginPage.tsx`：catch 分支按 `ApiError.errorCode` 映射——`database_busy`/`database_unavailable` → 新 i18n 键 `loginDatabaseUnavailable`；其它错误保持既有 `err.message` 透传不变。
- `i18n.tsx`：en 加 `loginDatabaseUnavailable: "Database temporarily unavailable. Please try again in a moment."`，zh 加 `"数据库暂时不可用，请稍后再试。"`（en 为键源，`i18n.test.tsx` 的 en/zh 键集一致断言仍通过）。
- 新测试 `src/frontend/src/features/auth/LoginPage.test.tsx`（3 tests：503 database_busy / database_unavailable 显示友好文案且不出现后端原文；401 仍透传原文）全绿；`i18n.test.tsx` 全绿；`tsc -p tsconfig.test.json` 0 错。前端测试在 Node v24.22.1 下跑通（本机无 .mise.toml 要求的 Node 26.13.0；vitest 不依赖该版本）。
- AC-008 已验证，task.md 已打勾。

### Area D+E 完成（2026-11-11）：compose 拓扑 + deploy.sh 重写（AC-001/AC-002/AC-003/AC-004/AC-009/AC-010/AC-013/AC-014/AC-016/AC-017/AC-018/AC-021）

- `compose.yaml`：顶层 named volume `db`（`name: ${CBROWSER_PREFIX:-cbrowser}-db`），api 挂 `db:/data/db`、`CBROWSER_DB_PATH=/data/db/cbrowser.db`；字体改为独立部署输入 `${CBROWSER_FONTS_DIR:?}:/fonts:ro`、容器内 `CBROWSER_FONTS_DIR=/fonts`（api/supervisor）；四服务均带 `com.cbrowser.instance-id: ${CBROWSER_INSTANCE_ID:?}` 与 `com.cbrowser.media-subnet-pool: ${CBROWSER_MEDIA_SUBNET_POOL:?}` 标签。`api/app.py:174` 与 `api/main.py:10` 的 DB 默认路径同步为 `/data/db/cbrowser.db`；`stream_agent/boundary.py` 的 PROHIBITED_PATHS 增补 `/data/db/cbrowser.db`（旧路径保留）。
- 新脚本（各有单元测试 `tests/unit/test_t051_deploy_scripts.py`，11 tests 全绿）：`scripts/db_inspect.py`（stamp：缺失/未盖戳→空串 exit 0，现存不可读→stderr + 非零，A44 fail-closed）、`scripts/db_backup.py`（sqlite3 在线备份 API，只读源）、`scripts/db_restore.py`（复制备份回 volume，先删 -wal/-shm）、`scripts/check_font_sets.py`（用 `check_font_set` 逐集校验，缺失/无有效集只警告、永不阻塞，exit 0）。
- `scripts/deploy.sh` 重写（912 行，`bash -n` 通过）：
  - `DATA_ROOT` 默认 `$ROOT/data/instance`（A55）；`FONTS_DIR="${CBROWSER_FONTS_DIR:-$ROOT/data/fonts}"`。
  - prefix 校验（A22）：`^[a-z0-9][a-z0-9_]*$`（不含 `-`，采纳决定原文），变量赋值后、任何 Docker 操作前 fail-closed。**注意：该规则使既有夹具前缀 `inst-b` 非法**，t027 测试夹具的 CBROWSER_PREFIX 已改名 `inst_b`（compose project 仍为 `inst-b`，project 名不受该规则约束）；t032 真实双实例验证若用 `inst-b` 前缀也须改名，见遗留。
  - 身份派生：`derive_instance_identity` 用 python3 从材料串 `cbrowser-instance-v1\0<prefix>\0<data_root>` 取 sha256，前 32 hex 为 instance_id，`int(digest,16)%64` 得池序号、池为 `10.{192+index}.0.0/16`；写 release.env 与 manifest `instance` 块（新增 `instance_id`、`media_subnet_pool`）。
  - 冲突判定（A59/AC-021）：`docker ps` 取 6 列；instance-id 标签等于本实例 id 时认领，标签缺失时仅当项目为本实例项目才认领（早于标签的旧容器、数据根迁移重部署情形），标签存在且不符即拒绝；`<prefix>-profiles` project 名豁免已删除。媒体池重叠在同一扫描内判定（与 prefix 无关，己方 instance-id 跳过）。
  - stamp 检查改为容器内读取：先建 API 镜像 → `docker run`（volume 只读挂载 + scripts 只读挂载）跑 `db_inspect.py stamp`；`test_deploy_refuses_legacy_generation_database` 的 `_builds == []` 断言随之改为 1 个 api 构建（附理由：建镜像不改数据；无容器启动、无指针移动、DB 未动的安全属性保留）。
  - 备份（AC-003）：有 live stamp 时 `up` 前容器内在线备份至 `$DEPLOY_DIR/backups/cbrowser-<ts>.db`，路径记 manifest `database_backup`；无库跳过。新增 `deploy.sh restore <backup-file>` 子命令：读当前 release 身份与 API 镜像 → `compose down` → 容器内 `db_restore.py` 拷回 volume → 提示重新部署；无当前 release 时拒绝。
  - 旧库提示（AC-004）：volume 无库但 `$ROOT/data/v2/cbrowser.db` 或 `$DATA_ROOT/cbrowser.db` 存在时打印位置与处置（restore 或移开），永不删除/移动，部署继续。
  - 字体 preflight（AC-009/AC-010）：部署时跑 `check_font_sets.py`，只警告不阻塞；`CBROWSER_FONTS_DIR` 写入 release.env。
  - 指针（A43/AC-017）：`current_release`/`previous_release` 两文件改为单一 JSON `release_pointer.json`（`{"current": …, "previous": …|null}`），`atomic_write` 改为调 `cbrowser.supervisor.file_storage.atomic_write_text`（文件 + 父目录 fsync）；`read_pointer` 按字段读 JSON（缺失/损坏读作空串）；`activate_release` 一次写完。损坏指针文件时 fail-soft 替换（previous 丢失，测试已记录该行为）。
  - `load_release_identity` 增采 `CBROWSER_INSTANCE_ID`/`CBROWSER_MEDIA_SUBNET_POOL`/`CBROWSER_FONTS_DIR`。
- t027 fake harness 扩展：fake docker 增加 `run`（容器侧 `python3 /scripts/*.py` 在宿主执行，`-v` 挂载翻译：宿主路径直通、volume 名→`$STATE/volumes/<name>` 按需创建；退出码原样透传，`db_inspect.py` 的 fail-closed 依赖它）、`volume inspect/create`、`compose down`；`_make_fake_repo` 复制 4 个新脚本与 `font_sets/`；`_stamp_db` 改为向 fake volume 灌库；`_pointer` 读 JSON。**教训：`cbrowser/__init__.py` 不可复制进 fake 树**——它会把 fake 树的 `cbrowser` 变成常规包、遮住真实树经 PYTHONPATH 提供的 `network_config_cli`（原 harness 靠命名空间包合并），已在 harness 内写注释防回归。
- 测试：`test_t027_release_controller.py` 51 tests（含新增 19 个 t051 测试：prefix 校验、JSON 指针、损坏指针替换、池重叠拒绝/不重叠放行、伪造 project+错 id 拒绝、缺 id 不认领、同 project 错 id 拒绝、同 project 对 id 放行、备份+恢复往返、无当前 release 拒绝恢复、备份缺失拒绝恢复、损坏库部署/回滚拒绝、旧库提示、字体警告/有效集、身份跨 release 稳定、volume 可 inspect）+ `test_t051_deploy_scripts.py` 11 tests，合计 62 passed。
- AC-001、AC-002、AC-003、AC-004、AC-009、AC-010、AC-016、AC-017、AC-018、AC-021 已验证（AC-013 真实部署、AC-014 双实例真实 Docker 为环境跳过，见下），task.md 已打勾。

### Area F 完成（2026-11-11）：沙箱标签 service 编号 + instance-id（AC-012、AC-021）

- `sandbox_compose_labels(prefix, service, profile_number)` 的 `com.docker.compose.service` 改为 `<NNNN>-browser` / `<NNNN>-stream`（如 `0007-browser`）；`com.docker.compose.project` 仍为 `<prefix>-profiles`。docstring 说明归属判定不由伪造 project 决定（instance-id 标签为唯一依据）。
- `browser_labels`、`stream_labels`、`policy_helper_labels`、`x11_helper_labels`、`cache_init_labels` 均新增可选 `deployment_id: str | None = None`；有值时带 `com.cbrowser.instance-id` 标签，无值时标签缺席（非空串）。`com.cbrowser.instance-id` 不再承载运行时 id（运行时 id 已归位到容器运行时配置，见「设计裁决」）。
- 测试：`test_t050_sandbox_grouping.py`（service 断言 `0001-browser`/`0001-stream`；新增 `test_sandbox_labels_carry_deployment_id` 覆盖五类标签函数 + 未配置时缺席）与 `test_refactor_behavior_equivalence.py`（`0001-browser`）同步更新；与 docker-error-detail/a9/t035 套件合跑 76 passed。
- AC-012 已验证（instance-id 部分由 Area G 的 adapter 接线完成），task.md 已打勾。

### Area G 完成（2026-11-11）：Supervisor 身份、扫描归属与媒体网络超时（AC-014、AC-015、AC-016、AC-021）

- **默认前缀裁决（A22 冲突）**：历史默认 `cbrowser-t005` 含连字符，在 A22 规则 `^[a-z0-9][a-z0-9_]*$` 下非法。若 `DockerAdapter.__init__` 校验前缀（A22 要求 Supervisor 启动校验），默认构造必报错。初版裁决：默认前缀改为 `cbrowser`（与 compose 默认前缀一致；生产环境 compose 恒以 `CBROWSER_PREFIX` 显式传入，实际名称不变）。改动面：`docker_adapter.py:204`、`runner.py:59/537`、`tests/fixtures/docker_doubles.py:68` 默认值；`test_t026_media_network_adapter.py:24` 的 PREFIX 常量；`test_t050_sandbox_grouping.py:78-79` 的容器名断言（`cbrowser-0007-browser`/`-stream`）；`docs/specs/browser_isolation.md:15` 的默认说明。保留未改：`scripts/gate_container_cleanup.py:40` 的 `cbrowser-t005-` 清理模式（须继续匹配旧容器名）；`test_p057_runner_container_events.py`、`test_t026_runner_network_events.py` 的 PREFIX 常量（仅作事件名匹配字符串，不进 adapter 校验）。
- **用户裁定（2026-11-11）：驳回改名，默认部署前缀改回 `cbrowser-t005`。已按裁定修正完毕。** 根因处理：A22 的校验对象是**部署输入**，不是编译内默认——默认前缀是先于 A22 存在的既定部署标识，让它被一条输入校验规则反噬正是初版被迫改名的根源。现口径：deploy.sh 校验其 `CBROWSER_PREFIX` 输入（其自身默认 `cbrowser` 满足规则，未动）；Supervisor 启动（runner main）只对显式提供的前缀（`--prefix` 或 `CBROWSER_PREFIX`）在持锁与任何 Docker 操作前校验，无显式值时用编译内默认 `cbrowser-t005` 且不校验；`DockerAdapter` 构造不再是校验入口（收到的已是校验后的值或默认）。AC-016 的可测行为（deploy.sh 与 Supervisor 启动对非法显式前缀 fail-closed）保留，新增 runner main 的 env 通道拒绝与默认前缀钉住测试。恢复面：adapter/runner（`run_supervisor` 与 `--prefix` 解析）/docker_doubles 三处默认值、`test_t026_media_network_adapter.py` 的 PREFIX、`test_t050_sandbox_grouping.py` 的容器名断言、browser_isolation.md 与 conventions.md 的默认说明。如实记录的不对称：deploy.sh 与 compose 的默认前缀仍是 `cbrowser`——经 `git show HEAD:` 核对，它们在基线即为 `cbrowser`、不属本次偏离（执行者未动）；且若把 deploy.sh 默认改成 `cbrowser-t005`，脚本会按 A22 拒绝自己的默认值，故维持现状、仅在此登记。
- **共享校验**：`container_spec.py` 新增 `validate_resource_prefix(prefix)`（正则 `^[a-z0-9][a-z0-9_]*$`，不符抛 ValueError）与 `RESOURCE_PREFIX_PATTERN`。仅入口校验（`DockerAdapter.__init__`、`runner.py main()` 在锁与任何 Docker 调用前）；纯标签 helper 故意不校验——t050 的 `browser_labels("inst-b", …)` 直接调用仍须工作。
- **`DockerAdapter.__init__`**：新增 `deployment_instance_id: str | None = None`（env 回落 `CBROWSER_INSTANCE_ID`）、`network_timeout: float | None = None`（默认 30.0，env 回落 `CBROWSER_DOCKER_NETWORK_TIMEOUT`，非法值回落 30.0）；`resource_prefix` 默认 `cbrowser` 且经 `validate_resource_prefix` 校验。
- **扫描归属（A59/AC-021）**：新增 `_owns_deployment(labels)`（配置了 deployment id 时仅当标签值相等才认领；缺失/不符→跳过/保留，永不认领/删除；未配置时旧行为）。`scan_active_containers`（缺失/不符记 warning 跳过）、`_cleanup_orphan_helpers`（仅删己方 helper）、`scan_gateway_containers` 均接线；`network_spec.py` 的 `network_labels`/`network_ownership_matches` 新增可选 `deployment_id`（任一方提供时 instance-id 为唯一判定；均无时沿用旧名+prefix+managed-by 判定），`_require_network_ownership` 透传；`core._lookup_browser_container` 在配置时把 `com.cbrowser.instance-id=<id>` 加入服务端 list 过滤器。
- **升级说明（A59 字面语义）**：t051 之前创建的沙箱/网络无 instance-id 标签，新 Supervisor 不认领（扫描跳过、重建拒绝触碰），属 A59「缺失标签即不认领」的直接后果；旧资源由既有 orphan 处理路径处置，本 task 不做祖父化兼容。
- **媒体网络超时重构（A3/AC-015）**：`_ensure_media_network` 不再跨 Docker 调用持有 `_media_network_lock`。锁内只做 get+allocate+reserve（新增 `_reserved_subnets` 集合防并发同子网分配，成功/失败均释放预留，成功后网络已进 Docker list 故无需保留）；锁外经新 `_docker_call`（daemon 线程 + `join(timeout)`）执行 `networks.create`，挂起时抛 `DockerSandboxError("… timed out …")`、不阻塞其它 Profile；冲突仍为单次创建、不重试（`create` 调用计数断言由 AC-011 旧测试保留）。`_used_subnets` 改经 `_docker_call` + 计入预留子网。`_docker_call` 原样重抛 NotFound/APIError 等原始异常，仅超时转为 DockerSandboxError。
- **runner 接线**：`run_supervisor` 新增 `deployment_instance_id` 与 `network_timeout` 参数并透传给 DockerAdapter；`main()` 新增 `--deployment-instance-id`（默认 `CBROWSER_INSTANCE_ID`）与 `--docker-network-timeout`（float，默认 None→env/adapter 默认），并在锁与任何 Docker 调用前校验 `--prefix`。
- **未采纳的计划项（附理由）**：未给 runner 的 `docker.from_env()` 加 client 级 timeout——同一 client 被事件流（`client.events(decode=True)`）长期持有，30s 读超时会在无事件静默期误断流；`_docker_call` 的线程 join 超时是正确的界。
- **标签接线**：`docker_adapter.py` 六处调用点（policy helper L375、cache init L634、X11 L831、browser L1470、stream L1675、策略 helper L2024）与两处网络标签（`_ensure_network`、`_ensure_media_network`）均传 `deployment_id=self.deployment_instance_id`。
- 测试：新 `tests/unit/test_t051_supervisor_identity.py`（33 tests：前缀校验矩阵、adapter 构造拒绝/默认/env 回落、三处扫描过滤、helper 清理仅删己方、browser 启动标签 + `0001-browser` service、network labels/ownership 矩阵、阻塞式 fake 下 create 超时 0.2s 内失败且并发 fast profile 成功、预留释放、并发三 profile 分配不同子网、core lookup 过滤器有/无、runner main 透传 + 连字符前缀拒绝）全绿。回归合跑 214 passed（t050、t026 媒体网络/地址池/事件、p057、a9、t035、docker doubles contract、t051 脱敏/DB/部署脚本、t027 控制器、refactor 等价）。
- AC-014、AC-015、AC-016、AC-021 已验证（AC-014/AC-015 的真实 Docker 部分为环境跳过，见下），task.md 已打勾。

### 环境跳过（本机无 Docker、无真实部署环境，按链口径跳过按 pass 计，不得记为已验）

- AC-013 真实部署：整项跳过。替代验证：AC-001 compose 结构断言（DB 在 named volume）、deploy.sh fake-Docker 全流程测试（46 tests）、AC-009/AC-010 字体 preflight 测试。真实部署（登录、Profile 出图、`docker inspect`、设置页字体集、OrbStack 分组）须在用户机验证。
- AC-014 双实例真实 Docker：真实 daemon 部分跳过。替代验证：deploy.sh fake 扫描测试（池重叠拒绝/不重叠放行，`test_t027_release_controller.py`）、Area G 并发三 profile 分配不同子网测试。同一 daemon 上两实例并发启动 Profile 须在用户机验证。
- AC-015 真实 Docker 挂起：真实 daemon 挂起部分跳过。替代验证：Area G 阻塞式 fake client 测试（create 挂起 0.2s 超时、并发 fast profile 不受阻、预留释放）。真实 daemon 挂起行为须在用户机验证。
- AC-017 指针崩溃一致性：fake-Docker 中断注入测试已覆盖（损坏指针替换测试）；真实部署中断注入未做。
- 黑盒 `CBROWSER_RUN_E2E=1 scripts/run_gates.sh`：本机无 Docker/镜像/Chrome，未跑；以相关非 E2E 套件替代，见收尾报告。

### Area H 完成（2026-11-11）：去代际化（A55/AC-019）

- 迁移文件改名：`src/backend/migrations/versions/0001_baseline_v2.py` → `0001_baseline.py`（`git mv`；revision `b7e1c9d4a2f3`、`down_revision=None`、`BASELINE_REVISION` 不变，已用 venv Python 导入验证）；文件内 docstring 与 `0004_preview_backoff.py:3`、`docs/blueprint/decisions.md:276` 的引用同步改名。
- 现行面代际标识清除（35 处改动，另加宽扫复核）：`.env.example:1`、`README.md:29,35`、`CHANGELOG.md:11`（`[2.0.0]` SemVer 头保留）、`DOCKER_DEPLOYMENT.md:69,92,95,97`（`data/test-v2` → `data/test-instance`，与同节 `config/deploy/test-instance` 对齐；其余 `data/v2` → `data/instance`）、`.gitignore:72`（`data/v2/` → `data/instance/`）、`config/docker/browser_runtime/Dockerfile:1`、blueprint（frontend.md:3、gateway.md:3、persistence.md:5、supervisor.md:3、security.md:3——宽扫发现 `v2 用户鉴权`，原计划模式未覆盖，已补模式 `v2 用户`）、specs（browser_isolation.md:5、profile_management.md:3）、源码 docstring 9 处（models.py、api/app.py、api/main.py:1——宽扫发现 `Control API v2`，已补模式 `API v2`、runtime_coordinator.py、api/v1/router.py、auth/__init__.py、domain/models.py、gateway/__init__.py、runtime_event_log.py、alembic.ini）、测试（audio_analyzer.py、test_domain_and_repository.py、test_control_migration.py:260 注释、`test_docker_build_contexts.py:145-146` 敏感路径夹具 → `data/instance/...`）。
- 未动（明确排除）：`docs/archive/`、`docs/tasks/`、`docs/reviews/`、`docs/pending/`、`docs/handoff.md:13`（历史交接记录）、`.repo_template/`；协议版本（Stream/Agent `version="v2"`、`Literal["v2"]`、`protocol_version="v2"`、`source_version: "v2"`、隧道 v2、前端构建戳 v2 格式）；库版本（SQLAlchemy 2.0、Pydantic v2）；API `version="2.0.0"` 与 `[2.0.0]` 发布头；`/api/v1`；历史 task slug。
- 遗留字面例外（非代际自指，测试内白名单 + 注释写明理由）：`scripts/deploy.sh:294` 的 AC-004 旧库探测仍须写出真实旧路径 `$ROOT/data/v2/cbrowser.db`（用户机旧库确在此处，改名即漏检），`test_t027_release_controller.py:1328` 断言该路径出现在部署输出，`docs/specs/release_deployment.md` 的 AC-004 契约行写出同一旧路径以便从 spec 可测。原计划「无白名单」因此处证据改为「仅此三处白名单」。
- Area J 复核时 hygiene 测试另抓出 4 处我自己新写的文档自指（conventions.md 的模式举例、decisions.md ADR 028 背景与去代际化两处、persistence.md §6 的迁移文件改名注），已改写措辞避开字面；release_deployment.md 的 AC-004 旧路径行则补进白名单（第 3 处）。测试按设计工作。
- 0004_preview_backoff.py:12 与 test_control_migration.py:260 的 `live data/v2` 注释改写为「1a6ec51 时代的 live 数据库」（路径与注释要点无关——要点是当时的库形态）。
- 新测试 `tests/unit/test_t051_generation_hygiene.py`（1 test：扫描 `.env.example`、`README.md`、`CHANGELOG.md`、`DOCKER_DEPLOYMENT.md`、`.gitignore`、`docs/blueprint/`、`docs/specs/`、`docs/guides/`、`src/`、`scripts/`、`config/`、`compose.yaml`、`tests/` 的 15 个模式，含自排除与上述两处白名单）先红后绿；`test_control_migration.py` + `test_docker_build_contexts.py` 合跑 15 passed。
- AC-019 已验证，task.md 已打勾（21/21 全打勾）。

### Area I 完成（2026-11-11）：E2E/夹具 DB 路径（AC-001）

- `tests/fixtures/gateway_probe/topology.py:474` 的容器内 `CBROWSER_DB_PATH: /data/cbrowser.db` → `/data/db/cbrowser.db`（与 compose 新拓扑一致）。其余夹具均用 tmp 路径或独立挂载，不受影响；`scripts/run_gates.sh` 无需改动（它 unset 产品 `CBROWSER_FONTS_DIR`、向 E2E 传 `CBROWSER_E2E_FONTS_DIR`；deploy.sh 恒在 release env 内设置字体目录；gates 从不直接调 compose）。

### Area J 完成（2026-11-11）：finalization 文档与 findings

- specs_index：runtime_lifecycle、release_deployment、access_control、fingerprint_platform、browser_isolation 五行登记 t051（2026-11-11）。browser_isolation 另因 Area G 的默认前缀改名与 instance-id 标签清单列入。
- specs：runtime_lifecycle 新增 t051 节（部署身份标签、归属唯一依据、service 编号、prefix 规则、媒体网络超时、helper 回收）；release_deployment 更新指针描述为单一 JSON、修正实例隔离行的 teardown 表述（Supervisor 从不 teardown 异部署沙箱）、新增 t051 节（named volume、字体独立输入、确定性身份与池、冲突判定、schema 检查、备份/恢复、旧库提示、prefix 校验）；fingerprint_platform 新增 §2.6（字体独立部署输入）；access_control 新增 t051 节（DB 分级 503、登录重试、日志安全、登录页本地化文案）。
- blueprint：persistence 新增 §6（存储位置、备份/恢复、错误分级、日志定性、迁移文件改名）；architecture §3.1 后新增 §3.2（部署身份/DB/指针）、§5.4 的 service 表述修正为编号形式、拓扑图注 named volume；supervisor 新增「部署身份、扫描归属与媒体网络超时（t051）」节、helper 清理句补 instance-id；conventions §3 新增产品无代际标识与部署身份/前缀两条；decisions 新增 ADR 028；testing 新增 t051 验收映射表（AC-001~021 → 测试/证据，含三项环境跳过说明）。
- findings：`findings.py new` 抽取 d037（SQLite 扩展码分级与日志安全）、d038（确定性部署身份与每实例媒体子网池）。
- 收尾 lint：默认 ruff 0.17.4（仓库门禁不跑 ruff、无 ruff 配置；本次为自查）扫改动文件 17 项——其中 12 项为我引入的已修（测试文件 import 排序/未用 import、两处 `subprocess.run` 补 `check=False`、redact_evidence.py 去多余 `# noqa: E402`、runner.py import 排序），其余 5 项为基线已有（docker_adapter I001/RUF100/RUF015、core I001、redact_evidence EXE001，均以 `git show HEAD:` 对照验证，未动）。`git diff --check` clean；前端 `tsc -p tsconfig.test.json` 0 错。
- 全部 21 条 AC 已在 task.md 打勾（AC-013/AC-014/AC-015 的真实环境部分按链口径跳过按 pass 计，见「环境跳过」）。

## Review 处置

每个结构化 finding 一行。`已修` 表示本 task 已修复；`遗留` 必须指向 `pNNN` 或 follow-up tid；`撤回` 必须写清理由。critical/important 未解决时不得 PASS。

### Round 1 (2026-11-11T09:23:10+08:00)

|finding_id|severity|status|rationale|fix_ref|
|---|---|---|---|---|
|t051_code_f001|important|已修|同 project 容器按 instance-id 判定：标签等于本实例 id 或缺失且项目为本实例项目时认领，标签存在且不符即拒绝|scripts/deploy.sh:527,571；tests/unit/test_t027_release_controller.py:1346,1364|
|t051_code_f002|important|已修|supervisor environment 增加 CBROWSER_INSTANCE_ID 与 CBROWSER_MEDIA_SUBNET_POOL（release env 有值可传）；CBROWSER_DOCKER_NETWORK_TIMEOUT 未进 release env，故不透传|compose.yaml:109,110；tests/unit/test_t027_release_controller.py:924,928|
|t051_code_f003|important|已修|_BEARER_RE/_BASIC_RE 加 re.IGNORECASE；小写 bearer/basic 各补矩阵用例，单 marker、无双重脱敏|src/backend/cbrowser/redact.py:41,42；tests/unit/test_t051_shared_redaction.py:51-65|
|t051_code_f004|minor|已修|.gitignore 增加 release_pointer.json 与 backups/，退役两行保留|.gitignore:72,73|
|t051_code_f005|minor|已修|两 spec 默认前缀区分 deploy.sh/compose 默认 cbrowser 与 Supervisor 默认 cbrowser-t005；runtime_lifecycle:60 补 instance-id 前提；progress.md Area D+E/F/G/J 的 deployment-id 现行表述改回 instance-id，supervisor_identity 口径 29→33|docs/specs/runtime_lifecycle.md:60,67；docs/specs/release_deployment.md:52,55；docs/tasks/t051_runtime_deploy_reliability/progress.md|
|t051_test_f001|minor|已修|脱敏委托测试 marker 计数由 >= 4 改为 == 4|tests/unit/test_t051_shared_redaction.py:178|
|t051_test_f002|minor|已修|无当前 release 测试只断言实际命中的 No current release（须先备好备份文件才命中该分支）；另立备份缺失分支测试（有当前 release + 备份不存在 → does not exist）|tests/unit/test_t027_release_controller.py:1399,1413|
|t051_test_f003|minor|已修|补部署级损坏库拒测：deploy 与 rollback 各一，损坏库拒绝、无 compose up、无指针移动、库字节不变；fake docker run 退出码原样透传（此前恒 exit 0 会吞掉 db_inspect 的 fail-closed）|tests/unit/test_t027_release_controller.py:1010,1054|

### Round 2 (2026-11-11T09:49:34+08:00)

- code 审阅 PASS、0 finding；test 审阅 PASS，仅 1 条 minor（t051_test_f004，见下，误报撤回）。

|finding_id|severity|status|rationale|fix_ref|
|---|---|---|---|---|
|t051_test_f004|minor|撤回|误报，无需改动。该行输入本就是真实存在的无引号秘密值，并非审阅报告所称的占位符输入：磁盘字节转储（od）与 base64 编码复核一致，102 行输入含真实秘密，`leaked` 列与 `kept` 列与之对应；生产规则实测可将其脱敏为 `kept` 形态，矩阵 21 tests 实跑全绿，该行真实触达 `_UNQUOTED_RE`。审阅报告的说法源于审阅侧读到的工具输出渲染层把形如 `password=<值>` 的文本改写为占位符（本轮复核中同一行在 grep/sed 回显里也被改写为占位符，只有 od 字节转储与 base64 呈现了原值）。|tests/unit/test_t051_shared_redaction.py:101-105|

## 收尾报告

### 验收与验证

- task：[`task.md`](task.md)
- 结果：全部满足（21/21 AC 已打勾；AC-013/AC-014/AC-015 的真实环境部分按链口径跳过按 pass 计，见「环境跳过」，不得记为已验）
- 测试：Round 1 修复后重跑——t027 控制器 51 passed（原 46 + 新增 5）；t051 六套件 103 tests（shared_redaction 21、deploy_scripts 11、db_errors 26、docker_error_detail 11、supervisor_identity 33、generation_hygiene 1）全绿；改动面回归 17 文件合跑 217 passed；全量 `tests/unit` + `tests/integration`（不含 t027，PYTHONPATH 指 `src/backend`）：1850 passed / 29 failed / 8 skipped / 2 errors，失败清单与基线分类逐项一致、无新增（见「命名偏离修正后复验」订正）；前端未动，vitest/tsc 沿用实施期结果（vitest 8 passed、tsc 0 错）；`git diff --check` clean；默认 ruff 0.17.4 自查：我引入的 12 项已修，余 5 项为基线已有（见 Area J）。
- 命名偏离修正后复验（2026-11-11，用户裁定驳回两项偏离后；数字经两轮全量复跑一致后订正）：受影响核心面（supervisor_identity、t050、p058、a8、a9、docker_boundaries、refactor_equivalence、doubles contract、observation_authority）终态单独复跑全绿（其中 p058、a8 系修正前红灯、本次收口，见「设计裁决」修正记录）；t027 单跑 51 passed（Round 1 修复后，新增 5 个测试）。Round 1 修复后全量重跑（2026-11-11，PYTHONPATH 指 `src/backend`）：全量 `tests/unit` + `tests/integration`（不含 t027）1850 passed / 29 failed / 8 skipped / 2 errors；与订正基线（1845 passed / 31 failed）相比 passed +5（新增脱敏矩阵 3 + 两处 venv 伪影在本轮带 PYTHONPATH 后通过）、failed −2（同两处伪影），29 failed 与 2 errors 的清单与基线分类逐项一致、无新增失败。全量 `tests/unit` + `tests/integration`（不含 t027，uv.lock 锁定依赖版本、本机 Python 3.12 自建 venv）：1845 passed / 31 failed / 8 skipped / 2 errors，31 failed 与 2 errors 均与本次两项命名修正无关，分类如下——① 浏览器/运行时环境缺失 14（agent_executor_chain 7、automation_cdp_flow 2、automation_probe_chain 3、control_attendant_chain 1、unit automation_cdp 1：需真实 Chromium/托管运行时，本机无，执行者黑盒口径同）；② 工具链/解释器环境 8（t028 gates 4 需 uv+Python 3.15+npm；t034 2 为 uv 缺失与 3.12≠3.15 断言；t045 2 为 `.scratch` Selkies wheel 缓存缺失）；③ 验证 venv 未安装项目包的子进程 import 伪影 2（runtime_persistence_guards、coordinator_lock，PYTHONPATH 指 src/backend 后实测全过）；④ 既有欠账 7（normal_exit_replay 4：replay 的 fake 未实现 Area C 新增的 `DockerAdapter.inspect_media_network`，回退 core lookup 至执行者原版实测同样失败；a24_deploy_network_source 2：回退 deploy.sh 至执行者原版实测同样失败；repo_hygiene 1：违规为归档 pending 文档与 Area A 脱敏测试夹具中的家目录字面，非本次改动文件）；⑤ 2 errors 为 a35_recovery、network_apply_operations 的 teardown 期 SQLAlchemy 连接池 KeyError（测试本体 passed，库/解释器层问题）。真实 Docker / E2E 本机未跑（无 Docker 环境），按既有口径记环境跳过；e2e 三文件（frontend/retry/browser_runtime）已按新语义同步标签读取方式，待用户机 E2E 复验。
- 黑盒：未跑——`CBROWSER_RUN_E2E=1 scripts/run_gates.sh` 本机无 Docker/镜像/Chrome，无法执行；以相关非 E2E 套件（上述聚焦 217 passed + t027 51 passed）替代，真实部署验证须在用户机进行。
- review：Round 1 实况——code FAIL（3 important + 2 minor）、test PASS（3 minor），8 条 finding 已全部修复并重验；Round 2 实况——code PASS（0 finding）、test PASS（1 minor t051_test_f004，经字节级复核证实为误报已撤回，见「Review 处置」Round 2）。两路均 PASS。
- AC 判定：见 `task.md` 行内打勾（21/21）

### 结果摘要

- t051 全部 21 条 AC 已实现并验证（task.md 21/21 打勾）；改动见 `git status`（新文件 13 个已 `git add -N`，其余为修改）；两项偏离已经用户裁定（2026-11-11）**驳回并按规定名修正完毕**：① 部署身份标签键改回 `com.cbrowser.instance-id`（键语义统一为部署身份、运行时 id 归位到容器运行时配置，根因处理见「设计裁决」节修正记录）；② 默认部署前缀改回 `cbrowser-t005`（A22 校验只作用于部署输入，根因处理见 Area G「默认前缀裁决」的修正记录）。Round 1 审阅（code FAIL/test PASS）8 条 finding 已全部修复：deploy.sh 同 project 归属检查按 instance-id 判定、compose 向 Supervisor 容器透传身份与媒体池、小写 bearer/basic 脱敏、.gitignore 补指针文件与备份目录、两 spec 默认前缀区分与 progress.md 术语/计数订正、脱敏 marker 计数精确为 4、restore 双分支拆分各钉一条文案、部署级损坏库 deploy/rollback 拒测（并修 fake docker run 退出码透传）；重跑 t027 51 passed、全量 1850 passed / 29 failed（与基线同类、无新增失败）；Round 2 审阅方全量复跑（含 t027）1901 passed / 29 failed / 8 skipped / 2 errors，清单与基线分类逐项一致、无新增失败，改动面 17 文件合跑 244 passed。Round 2 code PASS（0 finding）、test PASS（f004 误报撤回）。遗留：AC-013 真实部署、AC-014 双实例真实 Docker、AC-015 真实 Docker 挂起须在用户机验证；t032 真实双实例验证若用 `inst-b` 前缀须改名；升级后旧沙箱/网络无 instance-id 部署标签不被认领。

### 长期文档闭环

在 specs_index 行的 task 清单中登记当前 tid（格式见 `.repo_template/docs/usage.md`）；无长期 spec 变更时写 `- specs_index: not_applicable: 具体原因`。正式 spike 须有 report、现存 finding、采纳结论、后续 tid 或无需后续理由；finish 会检查这些引用。
