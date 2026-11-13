# Task review t056（reviewer_focus: 代码）

- task：`t056_api_contract_data_layer`
- spec：`docs/tasks/t056_api_contract_data_layer/task.md`
- diff_anchor：`3fbcec1754e6e1d9f4bd0978eefe6bd654df965a`
- target：`git -C '/home/hatch/workspace/CBrowser_t056' diff 3fbcec1754e6e1d9f4bd0978eefe6bd654df965a`
- round：1
- reviewed_at：2026-11-12T04:46:02+08:00

## Findings

### t056_code_f001 - OpenAPI 的 422 仍以 HTTPValidationError（`detail`）建档，与运行时统一 `details` 形状脱节

- 严重度：important
- 锚点：AC-003 / A15（“重新生成 OpenAPI 与前端类型并同步前端消费”；任务书测试策略要求“错误契约以 OpenAPI 结构与运行时响应双侧断言”）
- 位置：`schemas/openapi/cbrowser_v1.json:119`（422 → `#/components/schemas/HTTPValidationError`）、`src/frontend/src/shared/api/generated/cbrowser_v1.d.ts`（37 处 HTTPValidationError 引用，如 `:1759`、`:1947`、`:2097`）、`src/backend/cbrowser/api/app.py:647,661`（`contracted_openapi()` 以 `responses.setdefault("422", …)` 追加）
- 问题：运行时 422 经 `RequestValidationError` 处理器返回 `{error: "validation_error", message, details: [...], retryable: false}`（自跑 `tests/unit/test_a6_error_contract.py`、`tests/integration/test_t053_profile_locale_api.py` 通过）；但重新生成后的 OpenAPI 仍把全部带请求体/路径参数操作的 422 记为 `HTTPValidationError`（`{"detail": [...]}`）。t056 之前两者是一致的（旧运行时 422 即 `detail` 列表）；t056 把运行时形状改为 `details` 后未同步契约文档。根因在 `app.py:661`：`contracted_openapi()` 用 `setdefault` 追加 422，而 FastAPI 已自动生成 422 条目，`setdefault` 永不覆盖。代码生成客户端会把 422 类型化为 `{detail}`，读不到 `details`。
- 建议：`contracted_openapi()` 中对 422 用直接赋值覆盖为 `ValidationErrorResponse` 引用（而非 `setdefault`）；重新生成两份 OpenAPI 与前端类型；补一个 OpenAPI 结构断言（422 响应 schema 为 ValidationErrorResponse，全树无 HTTPValidationError 引用）。

### t056_code_f002 - create_group / create_proxy 的 IntegrityError 回退无界递归

- 严重度：minor
- 锚点：AC-007（幂等重放路径）
- 位置：`src/backend/cbrowser/adapters/database/repository.py:1169-1170`（`create_group`）、`:1670`（`create_proxy`）
- 问题：审计已记录、实体已删除、且同名已被另一实体占用时重放该操作 id：插入因名称唯一约束再次 IntegrityError → 处理器又查到同一审计、实体仍不存在 → 再次递归调用自身。递归调用沿用同一审计实体 id 与同一载荷重插，失败条件（同名占用）未变，循环直至 RecursionError（约 1000 层，每层伴随数据库往返），最终表现为 500 而非干净的 409 `group/proxy_name_in_use`。`create_profile` 无此问题（Profile 无唯一名称约束，每次重插取新 sequence 号）。前置条件窄（重放 + 已删 + 同名被占），失败是响亮的、无数据损坏，故 minor。
- 建议：回退分支中审计存在但实体已删除时不再无条件递归——名称冲突时直接 `raise ValueError("group/proxy name already exists")`；或将重建重试上限定为一次。

### t056_code_f003 - 迁移 0009 的 NULL 回填在“NULL 行 + 显示编号断档”并存时违反唯一索引，迁移失败

- 严重度：minor
- 锚点：A21 / AC-006 / AC-013（增量迁移先回填再改约束；回填注释自述目的为“NOT NULL 改列绝不在存量 NULL 行上失败”）
- 位置：`src/backend/migrations/versions/0009_profile_display_number_not_null.py:43,48`
- 问题：回填 SQL 对全部 Profile 算 `ROW_NUMBER() OVER (ORDER BY created_at, id)` 再赋给 NULL 行；删除产生的编号断档会使 NULL 行算出的序号撞上已有行的 `display_number`。已用系统 sqlite3 实测复现：A(d=1)、B(d=3)、C(NULL) → `IntegrityError: UNIQUE constraint failed: profiles.display_number`。前置条件需一个存量 NULL 行（0005 已回填全部行、创建总分配新号，正常路径无 NULL；仅手工改库等异常路径产生），失败是响亮的（迁移报错、无静默损坏），故 minor。
- 建议：只对 NULL 行编号并以现存最大值偏移，如 `COALESCE(MAX(display_number), 0) + ROW_NUMBER() OVER (ORDER BY created_at, id)` 在 NULL 子集上算。

## 结论

- 本轮新发现：3 条（1 important，2 minor）
- 未进表的提示：
  - 文件过大（结论段列出，不进 finding 表；生成物 `schemas/*.json` 已排除）：`src/backend/cbrowser/adapters/database/repository.py` 1898 行（本 task 净 +359）、`src/backend/cbrowser/api/runtime_coordinator.py` 1309 行（净 +145）、`src/backend/cbrowser/services/profile_service.py` 1192 行（净 +123）、`src/backend/cbrowser/agent_executor/session.py` 1013 行（净 +9）、`src/backend/cbrowser/gateway/server.py` 996 行（净 +17）、`src/backend/cbrowser/domain/models.py` 896 行（净 +7）、`src/backend/cbrowser/api/app.py` 668 行（净 +40）、`src/backend/cbrowser/supervisor/control_server.py` 661 行（净 +76）、`src/backend/cbrowser/services/control_service.py` 504 行（净 +8）、`scripts/deploy.sh` 990 行（净 +6）、`src/frontend/src/features/profiles/useProfilesQuery.ts` 645 行（净 +18）、`src/frontend/src/features/proxies/ProxyFormDialog.tsx` 668 行（净 +15）、`src/frontend/src/shared/api/sse.ts` 519 行（净 +58）。测试文件无一超 600 行（最大新建 `tests/unit/test_t056_migrations.py` 380 行）。
  - 圈复杂度（AST 近似 McCabe；≥10 结论提示，≥15 且本 task 增加分支为 minor——本次均只作结论提示，不进 finding 表）：`update_proxy`（repository.py）CC=19，t056 增加审计重放、versioned/runtime_only 分支与冻结修订查找分支；`_reconcile_stopped`（runtime_coordinator.py）CC=16，t056 改动其内错误记录调用，未确认新增分支，只提示；`_http_error_content`（app.py）CC=14；`_downstream_error_text`（runtime_coordinator.py）CC=13；`run_database_migrations`（migrations.py）CC=10。
  - 范围外观察（不进 finding 表，提请 chain runner 定夺）：锁定裁定复核——`com.cbrowser.deployment-id` 在代码/脚本/测试中零命中（49 处命中全在 t051–t055 的 review/progress 历史文档与 `decisions.md` 的引用性提及，非现行使用）；现行标签为 `com.cbrowser.instance-id`（`container_spec.py:109`）。但默认部署前缀存在一条 t054 遗留旁路：`scripts/deploy.sh:64`（`PREFIX="${CBROWSER_PREFIX:-cbrowser}"`，`:113` 导出并写入 release env）与 `compose.yaml:115`（supervisor 容器 `CBROWSER_PREFIX: ${CBROWSER_PREFIX:-cbrowser}`）使标准部署路径上的实际默认前缀为 `cbrowser`，经 `runner.py:621-622` 作为已提供前缀读入，绕过了编译期默认 `cbrowser-t005`。t056 未动该默认值（deploy.sh 本轮仅改注释），故不在本轮 finding 之列。
  - A60 的 0004 无条件建列与任务书一致（删容错分支、失败要响亮），`test_0004_fails_when_column_exists_with_wrong_definition` 已钉住；1a6ec51 时代旧库升级会在 0004 报重复列而非静默通过，属既定取舍。
  - `_proxy_used_by_bound` 不按 `observed_state` 过滤运行绑定版：与本 task 自带测试一致（`test_delete_proxy_still_refuses_bound_only_reference` 用仅绑定未上报 running 的 Profile 断言删除仍拒绝）；docstring“RUNNING bound version”措辞略宽于实现，但行为与测试一致，不作 finding。
  - `_reconcile_stopped` 的停稳分支无版本清除：仅在 desired=stopped 且 observed=stopped、无实例时触发，属停稳结算；A26 的版本绑定针对启动失败路径（AC-009），本轮复核未见冲突。
- 总体判断：实现层整体扎实（A1 实验复现、A2 提交后发布、A15 运行时形状统一、A17 影响集、A21/A29/A60 迁移、A23/A26/A28/A31 均有可验证实现与自跑通过的测试），但存在 1 条 important：OpenAPI 的 422 契约仍是已删除的 `detail` 形状，与运行时 `details` 脱节，须修复后重审。
- 系统性 follow-up：建议标题「部署默认前缀与 cbrowser-t005 裁定对齐」，slug `deploy_default_prefix_cbrowser_t005`（非阻断；处理 deploy.sh:64 与 compose.yaml 的 `cbrowser` 默认值经 CBROWSER_PREFIX 旁路编译期默认的问题，t054 遗留）。

### AC 复验方式

- AC-001：TICK-VALID，trust_prior。busy_timeout 先行 + _switch_to_wal 有界重试已读码核实；自跑 holder 线程测试通过，且我以 sqlite3 实测 WAL 切换在持写锁下 0.000s 即报 database is locked，证实重试必要；部署级真实争用须用户机观察。
- AC-002：TICK-VALID，re_verified。control_service.claim 的 publish 已移出 write_transaction（提交后才 publish），自跑 test_control_service.py（含 test_renew_upgrade_publishes_only_after_commit）通过。
- AC-003：TICK-VALID，re_verified。自跑 test_a6_error_contract.py（13 测）与登录限流真实 429（rate_limited + Retry-After）通过；全部 API 处理器已读码核对统一形状。注：OpenAPI 的 422 文档仍是旧形状，见 f001（不影响运行时响应本身）。
- AC-004：TICK-VALID，trust_prior。全树 grep 证实 error_reason 字段在基线与本轮均不存在（仅决策文档措辞与旧网络操作 JSON 残留）；下游 error+message 经 _downstream_error_text 以 "<error>: <message>" 存入 last error、由 runtime 视图 last_coordinator_error 呈现，前端 SessionDetailsPanel/useRuntimeSnapshot 消费该字段；自跑 AC-004 测试（503 体 → "Supervisor start failed (503): runtime_unavailable: pool exhausted"）通过。真实 Supervisor 502 须用户机验证。
- AC-005：TICK-VALID，trust_prior。自跑 test_t056_proxy_password_impact.py（含 AC-005 端到端：改 A 密码不推进版本、随后 /start 200 收敛）通过；真实引擎启动须用户机验证。
- AC-006：TICK-VALID，re_verified。自跑 test_t056_migrations.py（NULL 行写库报 NOT NULL、领域模型缺 display_number 构造失败）通过；0009 回填的断档碰撞见 f003（minor，不影响本 AC 的两项断言）。
- AC-007：TICK-VALID，re_verified。自跑 test_t056_idempotency.py（组/代理创建/更新/删除重放与同键异参 409、删除重放 204）通过；重放后删除 + 同名占用再重放的递归边界见 f002（minor）。
- AC-008：TICK-VALID，re_verified。自跑前端 11 文件 100 测通过（含 GroupManagerDialog/ProxyFormDialog 在途禁用、ProfileCreateDialog 关闭重开复用同一键与同一 tick 双击只创建一次）。
- AC-009：TICK-VALID，re_verified。自跑 test_t056_coordinator_errors.py（7 测：裸读与 SSE 式读不清除、旧版在跑不结算新版错误、新版 running 后清除）通过；另核 stopped 收敛分支的无版本清除仅在 desired=stopped 时触发，不违本 AC 语义。
- AC-010：TICK-VALID，re_verified。自跑 test_t056_references.py（字段级 422、双字段同报、reorder 子集/未知/重复 422，含 router 层）通过。
- AC-011：TICK-VALID，re_verified。自跑 test_t056_migrations.py（缺 alembic_version 表/空表/空版本号均报 LegacySchemaError 附重建指引；空库正常升级）通过。
- AC-012：TICK-VALID，trust_prior。自跑 test_t056_reference_events.py（router 层写操作发布事件、探测不发布）与前端 SSE 引用事件/查询失效测试通过；双真实浏览器客户端端到端须用户机验证。
- AC-013：TICK-VALID，re_verified。自跑 test_t056_migrations.py（0004 错形列迁移失败且 stamp 停在 0003、全部 9 个 revision 的 downgrade() 均抛错、新库结构与改动前 golden 仅差 display_number NOT NULL）与 test_t054_migration.py（head 为 0009）通过。

coverage = 9 / 13

trust_prior 4 项（AC-001、AC-004、AC-005、AC-012）占比 30.7%：建议合并前人工抽查 trust_prior 项（均为真实部署/引擎/双浏览器 residue，单元层替代证据已自跑通过）。

reviewed_scope: 3d2d4dd1de72709d

verdict: FAIL

## 更正记录（2026-11-12T04:48:43+08:00）

- 结论段“范围外观察”中关于默认部署前缀的一条表述有误：`deploy.sh:64` 与 `compose.yaml` 的 `cbrowser` 默认值并非“t054 遗留”——t051 两轮审阅已核对（`docs/tasks/t051_runtime_deploy_reliability/review_code.md:61,124`）其为基线既有行为（`git show 3331ed3:scripts/deploy.sh:48`、`3331ed3:compose.yaml:13,42,47` 均已含该默认值），并裁定不判 finding；本轮复核确认该基线事实。本更正不改动上文原文，仅修正定性。
- 机制本身的描述无误（deploy.sh 导出 `CBROWSER_PREFIX` → `runner.py:621-622` 作已提供前缀读入，绕过编译期默认 `cbrowser-t005`），但定性应为“基线既有、t051 已裁定不判 finding 的行为”，而非本轮新发现的 t054 遗留问题。
- 相应 follow-up 建议（slug `deploy_default_prefix_cbrowser_t005`）撤回主动立项：仅当用户另行裁定要改基线默认值时再立项，本轮及本链不主动推进。

## Round 2 (2026-11-12T05:50:27+08:00)

- round：2
- reviewed_at：2026-11-12T05:50:27+08:00
- 复审方式：逐项从 diff/代码/实跑复核 Round 1 的 f001–f003 修复；三处修复各做一次“还原则红”探针（临时还原则代码/文件，跑新测试，字节级恢复并 sha256 校验），探针文件均已恢复，`git status` 仍为 80 项改动、无新增未跟踪文件；`/tmp` 下自建 pytest basetemp 已清理。

### 前轮 finding 复核

#### t056_code_f001 —— 已消除

- 修复位置：`src/backend/cbrowser/api/app.py:664-713`（`contracted_openapi()`）。422 归一化改为直接赋值（`responses["422"] = {... "$ref": "#/components/schemas/ValidationErrorResponse" ...}`，保留原 description），覆盖所有已存在 422 的操作，包括 GET 与 internal 路由；随后以全树 `$ref` 扫描确认 `HTTPValidationError` / `ValidationError` 无引用后从 components 删除。
- 完整性实测（自写脚本读两份签入文件 + live app）：`cbrowser_v1.json` 47 个操作中有 422 的 40 个全部指向 `ValidationErrorResponse`，无 422 的 7 个均为无请求体/无校验参数的 GET（`/api/v1/health`、`/api/v1/profiles`、`/api/v1/groups`、`/api/v1/proxies`、`/api/v1/font-sets`、`/api/v1/auth/session`、`/api/v1/automation/tokens`），live app 同样不为其生成 422，故无遗漏；`cbrowser_internal.json` 60 个操作中有 422 的 51 个全部指向 `ValidationErrorResponse`，无 422 的 9 个同为上述 GET 加 2 个 internal GET；两份文件 components 中均无 `HTTPValidationError` / `ValidationError`。全树 grep：`HTTPValidationError` 只剩 `app.py` 注释与测试文件断言文本，无任何模式/夹具引用；`ValidationErrorResponse` 在 `cbrowser_v1.json` 出现 42 处、`cbrowser_internal.json` 53 处、前端 `.d.ts` 42 处，`.d.ts` 中 `HTTPValidationError` 为 0 处。
- 新断言真实：`tests/unit/test_t035_openapi_contract.py::test_openapi_422_is_validation_error_response_not_http_validation_error` 自跑通过；将其断言逻辑作用于基线 `3fbcec1` 的旧文件时失败（旧文件含 `HTTPValidationError` 引用与 422 → `HTTPValidationError`），且临时把两份签入文件恢复为基线版本后该测试与两项同步测试（`test_protocol_artifacts_are_current_and_read_only`、`test_internal_openapi_export_matches_checked_in_file`）均 FAILED，恢复后 sha256 与探针前一致（`a44ee702…` / `7672986b…`）。
- 同步性自跑：`test_t035_openapi_contract.py` + `test_runtime_agent_protocol_export.py` 17 passed；`test_a16_protocol_drift.py::test_protocol_artifacts_are_current_and_read_only` 通过。

#### t056_code_f002 —— 已消除

- 修复位置：`src/backend/cbrowser/adapters/database/repository.py:1115-1194`（`create_group`）、`:1636-1713`（`create_proxy`）。审计存在、实体已删时先查同名是否被占：被占或 `_allow_rebuild` 已耗尽 → 直接 `raise ValueError("group/proxy name already exists")`；否则以 `_allow_rebuild=False` 递归重建一次，重建上限为一次。路由层已核实：`groups_router.py:45-53` 与 `proxies_router.py:50` 把 `create` 的 ValueError 映射为 409 `group_name_in_use` / `proxy_name_in_use`。
- 新测试真实：两项新测试自跑通过；临时把两处守卫还原为 Round 1 无条件递归后两项测试均 FAILED（62.51s），恢复后 sha256 与探针前一致（`ac703deae1…`，与修复方记录的哈希一致）。失败形态说明：单测重跑只取 group 一项时，实际抛错为 `sqlalchemy.exc.TimeoutError: QueuePool limit of size 5 overflow 10 reached, connection timed out, timeout 30.00`（31.31s）——每层递归持有一个未释放的 session，连接池先于约 1000 层递归上限耗尽；Round 1 报告与修复方所称“直至 RecursionError”的机理描述在细节上不准，但结论一致：无修复时该场景是响亮的 500 级失败而非干净 409，测试能有效区分。`_allow_rebuild` 无外部调用点（全树仅 `repository.py` 内引用），私有参数未外泄。

#### t056_code_f003 —— 已消除

- 修复位置：`src/backend/migrations/versions/0009_profile_display_number_not_null.py:33-62`。回填改为 Python 预读 `COALESCE(MAX(display_number), 0)` 作绑定参数，单条 `UPDATE ... FROM (SELECT id, ROW_NUMBER() OVER (ORDER BY created_at, id) FROM profiles WHERE display_number IS NULL)` 一次性编号。
- 偏离裁定：修复方未按建议字面 SQL 写，理由成立。自测系统 sqlite3 3.45.1：建议字面 SQL（`COALESCE(MAX(display_number), 0) + ROW_NUMBER() OVER (...)` 同层）报 `OperationalError: misuse of window function ROW_NUMBER()`（修复方引用的报错措辞为 `misuse of aggregate: MAX()`，措辞有出入，拒绝本身属实）；且 NULL 集合在逐行 UPDATE 中会缩小，字面写法即使合法也不可靠。已实现形式自测：A(1)、B(3)、C(NULL) → C=4；A(1)、B(3)、C(NULL)、D(NULL) → C=4、D=5，无碰撞。
- 新测试真实：`tests/unit/test_t056_migrations.py::test_0009_backfill_skips_existing_numbers_with_gaps` 自跑通过；临时把 0009 还原为 Round 1 全行编号 SQL 后该测试 FAILED（`sqlite3.IntegrityError: UNIQUE constraint failed: profiles.display_number`，0.75s），恢复后 sha256 与探针前一致（`58a2bbd7…`，与修复方记录的哈希一致）。

#### OpenAPI 滞后争议——已查清，不构成 Round 1 test review 的矛盾

- 修复方称“签入的 OpenAPI 文件在修复前已滞后（6 个分组/代理写操作缺 A23 `Idempotency-Key` 参数，旧文件 8 处、新文件 14 处），旧文件恢复后两项同步测试 FAILED，与 Round 1 test review‘86 passed 含同步测试’不符，原因未查”。
- 查证结论：滞后本身属实，但“旧文件”指的是基线 `3fbcec1` 的文件，不是 Round 1 送审时的文件。实测基线 `cbrowser_v1.json` 确为 8 个带 `Idempotency-Key` 参数的操作（全为 profile 写操作），新文件为 14 个（新增 `POST/PATCH/DELETE /api/v1/groups`、`POST/PATCH/DELETE /api/v1/proxies`）；基线文件另有 4 个操作的 422 已是 `ValidationErrorResponse`（手写声明），其余为 `HTTPValidationError`。
- 无矛盾的理由有三：(1) 6 处 `Idempotency-Key` 参数来自 `groups_router.py` / `proxies_router.py` 的路由声明，属 Round 1 实现内容（`git diff 3fbcec1` 在这两文件命中 6 处），修复轮未动路由签名，故 Round 1 的 live app 同样输出 14 处；(2) 实施方 `progress.md:144` 已记录 Phase 5 在送审前重跑 `scripts/export_openapi.py` 使签入文件与 live 一致（`live == checked` 已验证）；(3) Round 1 test review 明确写了同步测试通过（`test_exported_openapi_schema_matches_live_app`、`test_internal_openapi_export_matches_checked_in_file`），与 Round 1 送审文件已再生成一致。修复方探针恢复的是基线文件，对 t056 live app 必然失败——这是基线先于特性的正常状态，不是 Round 1 漏审的证据。本轮无需任何动作；修复方在 `progress.md` 的“原因未查”备注可视为已解释。

### 本轮新发现

本轮新发现：0 条。

### 未进表的提示

- 文件过大（结论段列出，不进 finding 表；生成物 `schemas/*.json` 已排除）：与 Round 1 相同，修复轮未新增超阈文件。`src/backend/cbrowser/adapters/database/repository.py` 1898 行、`src/backend/cbrowser/api/runtime_coordinator.py` 1309 行、`src/backend/cbrowser/services/profile_service.py` 1192 行、`src/backend/cbrowser/agent_executor/session.py` 1013 行、`src/backend/cbrowser/gateway/server.py` 996 行、`src/backend/cbrowser/domain/models.py` 896 行、`src/backend/cbrowser/api/app.py` 668 行、`src/backend/cbrowser/supervisor/control_server.py` 661 行、`src/backend/cbrowser/services/control_service.py` 504 行、`scripts/deploy.sh` 990 行、`src/frontend/src/features/profiles/useProfilesQuery.ts` 645 行、`src/frontend/src/features/profiles/ProxyFormDialog.tsx` 668 行、`src/frontend/src/shared/api/sse.ts` 519 行。测试文件无一超 600 行。
- 圈复杂度：本轮修复未新增 ≥15 的函数分支。`contracted_openapi` 的 422 归一化循环与 orphan 收集均为平铺循环，无新增嵌套分支；`create_group` / `create_proxy` 的异常处理分支各 +1（`name_taken or not _allow_rebuild` 判断），未跨阈值。
- 观察（不进 finding 表）：`create_group` / `create_proxy` 的重建二次失败（`_allow_rebuild=False` 时再次 IntegrityError）统一报 `ValueError("group/proxy name already exists")`，即使二次失败并非名字冲突（如 id 碰撞）。该路径实际不可达（重建沿用审计 entity_id，uuid 碰撞可忽略；其余约束与首次失败同源且已被名字检查前置），且行为仍是有界 409 而非 500，故只作记录，不判 finding。
- 观察（不进 finding 表）：`runtime_coordinator.py:76` docstring 仍写 "the Profile's error_reason"，实际字段为 `last_coordinator_error`（task.md AC-004 已在修复轮改为 `last_coordinator_error`）。仅措辞残留，不影响行为，不判 finding。
- 观察（不进 finding 表）：修复方探针记录中两处措辞与实测有出入——f002 红前探针“约 1000 层递归”实际先撞连接池 30s 超时；f003 建议 SQL 的 sqlite 报错实为 `misuse of window function ROW_NUMBER()` 而非 `misuse of aggregate: MAX()`。均不影响修复正确性与测试有效性，只作记录。
- 锁定裁定复核：`com.cbrowser.deployment-id` 在 `src/`、`scripts/`、`compose.yaml`、`tests/` 中零命中；现行标签为 `com.cbrowser.instance-id`。`deploy.sh` / `compose.yaml` 的 `cbrowser` 默认前缀为 t051 已裁定的基线既有行为，不判 finding，不改动。
- 环境跳过（按链规则计 pass）：AC-005 真实引擎启动、AC-004 真实 Supervisor 502、AC-012 双真实客户端实时同步、Gateway 真实路由、bind-only 改密冻结拒绝、黑盒门禁、AC-001 部署级锁争用——本机无 Docker/真实引擎/真实浏览器，均未验证，见 AC 复验 trust_prior 项。

### 总体判断

Round 1 的 1 条 important 与 2 条 minor 均已消除：f001 的 422 契约已全量归一化为 `ValidationErrorResponse` 且签入文件与 live app 同步；f002 的重建递归已有名字检查与一次上限，新测试在还原则代码下确为红；f003 的回填已避开断档碰撞，偏离建议字面 SQL 的理由经 sqlite3 3.45.1 实测成立，新测试在还原则 SQL 下确为红。本轮无新 finding。全量回归与修复方声称一致。

### 系统性 follow-up

无。

### AC 复验方式

- AC-001：TICK-VALID，trust_prior。busy_timeout 先行 + `_switch_to_wal` 有界重试已读码核实；Round 1 已自跑 holder 线程测试；修复轮新增的持续时间断言（`test_t056_migrations.py:147`，`elapsed >= 0.5`）在本轮受影响套件内通过；部署级真实争用须用户机观察。
- AC-002：TICK-VALID，re_verified。`control_service.claim` 的 publish 在提交后才执行（Round 1 已读码核实）；本轮受影响套件含 `test_control_service.py`（含提交后发布断言），135 项全过。
- AC-003：TICK-VALID，re_verified。本轮自跑 `test_a6_error_contract.py` 与 `test_t035_openapi_contract.py` 通过；live app 双变体全部 422 均已核为 `ValidationErrorResponse`，无 `HTTPValidationError` 残留。
- AC-004：TICK-VALID，trust_prior。task.md AC-004 措辞已改为 `last_coordinator_error`，与实现一致（全树 grep 证实 `error_reason` 字段不存在，仅 `runtime_coordinator.py:76` docstring 措辞残留）；下游 error+message 经 `last_coordinator_error` 呈现（Round 1 已核实）；真实 Supervisor 502 须用户机验证。
- AC-005：TICK-VALID，trust_prior。本轮受影响套件含 `test_t056_proxy_password_impact.py`（改 A 密码不推进版本、随后启动收敛），全过；真实引擎启动须用户机验证。
- AC-006：TICK-VALID，re_verified。本轮自跑 `test_t056_migrations.py` 全文件通过（含 NULL 行写库报 NOT NULL、领域模型缺 `display_number` 构造失败、新回填断档测试）。
- AC-007：TICK-VALID，re_verified。本轮自跑 `test_t056_idempotency.py` 全文件通过（含两项 f002 新测试及重放/同键异参 409）；还原则探针证实新测试有效。
- AC-008：TICK-VALID，re_verified。前端全量 546/0 通过（含 GroupManagerDialog/ProxyFormDialog 在途禁用、ProfileCreateDialog 关闭重开复用同一键）。
- AC-009：TICK-VALID，re_verified。本轮自跑 `test_t056_coordinator_errors.py` 通过（裸读与 SSE 式读不清除、旧版在跑不结算新版错误、新版 running 后清除）。
- AC-010：TICK-VALID，re_verified。本轮自跑 `test_t056_references.py` 通过（字段级 422、reorder 子集/未知/重复 422，含 router 层）。
- AC-011：TICK-VALID，re_verified。本轮自跑 `test_t056_migrations.py` 通过（缺 alembic_version 表/空表/空版本号均报 `LegacySchemaError` 附重建指引）。
- AC-012：TICK-VALID，trust_prior。本轮自跑 `test_t056_reference_events.py` 与前端 SSE 引用事件/查询失效测试通过；双真实浏览器客户端端到端须用户机验证。
- AC-013：TICK-VALID，re_verified。本轮自跑 `test_t056_migrations.py` 与 `test_t054_migration.py` 通过（0004 错形列迁移失败、全部 9 个 revision 的 `downgrade()` 均抛错、新库结构 golden 对比）。

coverage = 9 / 13

trust_prior 4 项（AC-001、AC-004、AC-005、AC-012）占比 30.7%：建议合并前人工抽查 trust_prior 项（均为真实部署/引擎/双浏览器 residue，单元层替代证据已自跑通过）。

### 本轮自跑数字

- 受影响后端套件（14 个文件：`test_t056_*` 6 个 + `test_a6_error_contract` + `test_a16_protocol_drift` + `test_t035_openapi_contract` + `test_runtime_agent_protocol_export` + `test_control_service` + `test_agent_executor_control` + `test_t054_migration` + `test_control_migration`）：135 passed，0 failed（54.41s）。
- 后端全量（`tests/unit` + `tests/integration`）：2140 passed，25 failed，8 skipped（697.37s）。25 个失败按名与 t055 基线完全一致：agent_executor_chain 7、t028 4、normal_exit_replay 4、automation_probe_chain 3、t034 2、automation_cdp_flow 2、repo_hygiene 1、automation_cdp 1、control_attendant_chain 1；零新增失败。
- 前端全量（`src/frontend` 内 `npm test`，Node v26.13.0）：75 个文件、546 passed，0 failed（258.19s）。
- 还原则探针：f001（基线 OpenAPI 文件）3 项同步/断言测试 FAILED；f002（还原则守卫）2 项新测试 FAILED（62.51s）；f003（还原则 SQL）1 项新测试 FAILED（`IntegrityError`，0.75s）；探针后文件均 sha256 恢复，`git status` 无新增项。

reviewed_scope: 72cc8c4e992e1853

verdict: PASS
