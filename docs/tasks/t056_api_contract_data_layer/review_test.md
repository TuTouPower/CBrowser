# Task review t056（reviewer_focus: 测试）

- task：`t056_api_contract_data_layer`
- spec：`docs/tasks/t056_api_contract_data_layer/task.md`
- diff_anchor：`3fbcec1754e6e1d9f4bd0978eefe6bd654df965a`
- target：`git -C '/home/hatch/workspace/CBrowser_t056' diff 3fbcec1754e6e1d9f4bd0978eefe6bd654df965a`
- round：1
- reviewed_at：2026-11-12T04:53:45+08:00

## Findings

### t056_test_f001 - AC-004 字面字段名 error_reason 在树中不存在，实质由 last_coordinator_error 呈现

- 严重度：minor
- 锚点：AC-004（“Supervisor 返回的失败原因出现在 Profile 的 error_reason 中”）
- 位置：`docs/tasks/t056_api_contract_data_layer/task.md:51`；`src/backend/cbrowser/api/runtime_coordinator.py:75-81`；`tests/unit/test_t056_coordinator_errors.py`
- 问题：AC-004 字面要求的 `error_reason` 字段在整树不存在。已核实：基线 commit `3fbcec1` 上 `git grep error_reason` 只命中 `tests/unit/test_control_migration.py:218` 一处——那是 legacy network-operation settings JSON payload 里的键（t054 已随网络事务删除），不是 Profile 字段；`src/backend/cbrowser/domain/models.py:778,801` 与 `src/backend/cbrowser/api/v1/runtime_views.py` 的运行时视图字段是 `last_coordinator_error`。实现把下游 `error` 与 `message` 拼成 `"<error>: <message>"` 存入所存 last error，经 runtime 视图的 `last_coordinator_error` 呈现（docstring `runtime_coordinator.py:75-81` 明文写了这一映射），测试 `test_t056_coordinator_errors.py` 的 AC-004 测试断言所存错误恰好为 `"Supervisor start failed (503): runtime_unavailable: pool exhausted"`，`test_old_running_new_failed_keeps_error_until_new_running` 断言 `make_runtime_response(...).last_coordinator_error == error`——实质（下游失败原因在 Profile 视图可见）已被真实测试覆盖，缺口只在 AC 的字段名措辞与代码现状不符。
- 建议：按提示词“实现合理但与 spec 描述不符（spec 过时）→ 在 finding 里说明，处置为改 spec，不计 FAIL”处置：把 task.md AC-004 的 `error_reason` 改为 `last_coordinator_error`（或注明“即 runtime 视图的 last_coordinator_error”），不改实现、不改测试。本 finding 不阻断，AC-004 仍记 TICK-VALID。

### t056_test_f002 - AC-001 busy 等待测试未断言争用真实发生，存在理论上的空跑可能

- 严重度：minor
- 锚点：AC-001（迁移在另一连接持有写事务时等待 busy_timeout 后完成切换）
- 位置：`tests/unit/test_t056_migrations.py:103-147`（`test_migration_waits_out_busy_timeout`）
- 问题：测试用 holder 线程持 `BEGIN IMMEDIATE` 0.7 秒、主线程睡 0.15 秒后启动迁移，断言迁移完成、`released.is_set()` 且最终 `journal_mode == "wal"`。这三个断言本身都能区分新旧实现（无重试时 WAL 切换会立即报 `database is locked`，测试必红），但测试没有断言“迁移执行时 holder 确实持有锁”这一前提：如果 holder 线程启动被调度延迟超过迁移的 WAL 切换时刻，测试会在无争用下通过——即重试路径实际没跑也被记为通过。实践中 0.15 秒裕量相对线程启动（约毫秒级）很宽，空跑概率极低，但前提是隐式的，测试本身无法自证。
- 建议：补一个显式争用断言，例如记录 `run_database_migrations(db)` 调用的耗时并断言不小于约 0.5 秒（holder 在约 0.7 秒释放，真实等待下迁移只能在释放后完成 WAL 切换），或在 holder 内记录“迁移开始时锁仍被持有”的标记。只加断言，不改生产代码。

## 结论

- 改测方向复核：本轮无“迁就实现”的改测。逐项核实如下（均有归因，且旧语义被等价或更高层的新测试替代）：
  - `tests/unit/test_a6_error_contract.py` 整文件重写：A15 废除了旧 shape（整包 `detail` 嵌套），属 spec 变更；2 个旧测试原样保留（plain-string detail 映射、503 retryable），其余删后重写为新 shape 覆盖，并新增真实 TestClient 层测试；新断言反而更严（多处 `"detail" not in body`），不是弱化。
  - `tests/unit/test_control_migration.py` 删除 2 个测试：A60 要求删除 0004“列已存在即跳过”分支与 0003 历史修补分支，被删测试的语义随之废除；新覆盖在 `tests/unit/test_t056_migrations.py`（0004 定义不符时失败且 stamp 停在 0003、0003 不动 legacy op 行），文件 docstring 已写明删除理由。
  - `tests/unit/test_t035_profile_domain.py` 删除 1 个测试（`test_proxy_connection_change_regenerates_versions_for_referencing_profiles`）：A17 废除了旧并集语义（所有引用者都生成新版本）；新覆盖在 `tests/unit/test_t056_proxy_password_impact.py`（只给当前引用者生成新版本，绑定-only 只发 runtime 事件）。
  - `tests/unit/test_runtime_coordinator_error_settle.py` 整文件删除（54 行）：旧语义是“读一次收敛的 runtime 即清除所存错误”（基线文件第 31-33 行 `get_last_error(p1, runtime=_converged()) is None`），A26 明确废除该语义；新覆盖在 `tests/unit/test_t056_coordinator_errors.py`（读不清错误、只在同版本 running 到达时清除）。
  - 机械适配：`display_number=1` fixture 补全（A21 模型必填）、`update_proxy` 返回值由 2 元组改为 3 元组解包（A17）、前端旧 shape fixture 改为新 shape（A15，同步补 `"detail" not in body` 断言）。均为契约变更驱动的适配，无断言弱化。
- 本轮新发现：2 条，均为 minor，无 critical / important。
- 未进表的提示：
  - 前端全量首跑曾出 1 个失败（`src/frontend/src/app/router.test.tsx:235`，`treats an unknown profileId as a normal detail route`：`expect(stubClient.profiles.get).toHaveBeenCalledWith("new")`，该断言未包在 `waitFor` 里，`findByTestId("profile-detail-view")` 返回后查询 effect 可能尚未触发，属时序竞态）。该文件不在 t056 diff 内、为既存测试；随后两次全量重跑（一次纯 vitest、一次完整 `npm test` 含类型门禁）均为 546/0，未复现。记为既存 flaky 观察，不进 finding。
  - Gateway live 路由、AC-005 真实引擎启动、AC-004 真实 Supervisor 502、AC-012 双客户端实时同步、AC-001 部署级锁争用：本机无 Docker / 真实浏览器 / 真实引擎，按环境门禁记为 env-skip，progress.md 已登记，不构成失败。
  - Gateway 的 agent 注册（`src/backend/cbrowser/gateway/server.py:448,453,466,476,485`）与 viewer signal（`:763`）握手端点返回纯文本 HTTP 状态而非 JSON `ErrorResponse`：已核实这些是 WebSocket 升级端点（握手失败响应体按协议不被解析），不在 A15 的 JSON API 错误契约面内；Gateway 全部 JSON 错误响应点均经 `_error_response` / `supervisor_fence_failure`（`:122,129,290,297,316,323,331,376`），与测试覆盖一致，不构成缺口。
  - `tests/unit/test_t056_idempotency.py` 中 `service._schedule_probe = lambda proxy_id: None`：已核实为测试隔离（中和后台探针，避免其异步 pending 行污染重放断言），重放逻辑本身（`find_recorded_operation` → 返回首次结果、不重记 observation）仍走真实代码，且 router 层测试用真实 service 未中和；不构成 mock 被测逻辑。
  - `git status` 有 1 个未跟踪文件 `docs/tasks/t056_api_contract_data_layer/review_code.md`：为并行 code reviewer 的报告，非实施交付物，不影响本轮审查范围完整性。
  - 锁定用户裁决核查：测试 / 前端 diff 中无 `com.cbrowser.deployment-id` 与 `cbrowser` 默认前缀出现，`com.cbrowser.instance-id` / `cbrowser-t005` 未被触碰，无违规。
- 总体判断：13 条 AC 均有真实、可信的测试支撑，危险模式扫描干净，独立重跑的回归与实施方宣称一致（后端 25 失败与 t055 基线逐名一致、零新增；前端 546/0）。仅 2 条 minor（AC-004 字段名措辞、AC-001 测试前提显式化），不阻断。
- 系统性 follow-up：无。

### AC 复验方式

- AC-001：TICK-VALID，re_verified。`tests/unit/test_t056_migrations.py` 的 pragma 顺序测试（busy_timeout 在 WAL 切换之前）与 holder 线程持 BEGIN IMMEDIATE 0.7s 下迁移完成并切到 WAL 的测试均已独立重跑通过。
- AC-002：TICK-VALID，re_verified。`tests/unit/test_control_service.py::test_renew_upgrade_publishes_only_after_commit` 独立重跑通过：提交失败时无事件、不持久化；提交成功时发布。
- AC-003：TICK-VALID，re_verified。`tests/unit/test_a6_error_contract.py` 13 个测试独立重跑通过：handler 层 + 真实 TestClient 层，error / message / retryable 齐全、details 不重复顶层字段、429 → rate_limited + Retry-After（含真实登录 5 次失败后 429）。
- AC-004：TICK-VALID，re_verified。Supervisor 401 / 404 / 422 经真实 ASGI 传输返回统一形状（`tests/unit/test_t056_error_contract_services.py`）；Gateway 纯函数层 `_error_response` / `supervisor_fence_failure` 形状一致；Coordinator 保留下游 error + message 并经 `last_coordinator_error` 呈现（`tests/unit/test_t056_coordinator_errors.py` 的 AC-004 测试）；字段名映射见 t056_test_f001。
- AC-005：TICK-VALID，re_verified。`tests/unit/test_t056_proxy_password_impact.py` 4 个测试独立重跑通过：改密只给当前引用者生成新版本、绑定-only 只发 runtime 事件、冻结修订跟随快照自身代理、AC-005 端到端 MockTransport /start 200 → CONVERGED。
- AC-006：TICK-VALID，re_verified。`tests/unit/test_t056_migrations.py`：NULL display_number 写库报 IntegrityError（NOT NULL）、领域模型缺 display_number 构造报 ValidationError；独立重跑通过。
- AC-007：TICK-VALID，re_verified。`tests/unit/test_t056_idempotency.py` 15 个测试独立重跑通过：repo / service / router 三层重放返回首次结果且无重复记录，同键不同参数 409。
- AC-008：TICK-VALID，re_verified。前端组件测试独立重跑通过：GroupManagerDialog 与 ProxyFormDialog 写操作在途时提交按钮禁用、二次点击不重复创建；ProfileCreateDialog 同 tick 双提交只创建一次、关闭重开沿用同一幂等键。
- AC-009：TICK-VALID，re_verified。`tests/unit/test_t056_coordinator_errors.py` 7 个测试独立重跑通过：旧版 running、新版失败时多次裸读与 SSE 式读取均返回错误，直到新版成功 running 才清除。
- AC-010：TICK-VALID，re_verified。`tests/unit/test_t056_references.py` 9 个测试独立重跑通过：service 层与 router 层均返回字段级 422（loc 指向 group_id / proxy_id / ordered_ids），无 detail 包。
- AC-011：TICK-VALID，re_verified。`tests/unit/test_t056_migrations.py` 3 个 LegacySchemaError 测试独立重跑通过（缺 alembic_version 表、空表、空 version_num），均含重建指引；空库仍可正常升级的反例测试亦通过。
- AC-012：TICK-VALID，re_verified。后端 `tests/unit/test_t056_reference_events.py`（coordinator 真实 broadcaster + router 层）与前端 `src/frontend/src/shared/api/sse.reference.test.ts`（真实本地 HTTP 服务器 + 真实 SSE 客户端）及 `useProfilesQuery.test.tsx` 查询失效测试均独立重跑通过。
- AC-013：TICK-VALID，re_verified。`tests/unit/test_t056_migrations.py`：0004 列定义不符时迁移失败且 stamp 停在 0003、全部 revision 的 `downgrade()` 抛 RuntimeError、全新库结构与 golden 对比仅 display_number NOT NULL 一处差异；独立重跑通过。

coverage = 13 / 13

## 自跑实数（本 reviewer 独立执行）

- 后端新改测试（13 个文件）：114 passed，0 failed（139.54s）。文件：test_t056_migrations、test_t056_coordinator_errors、test_t056_error_contract_services、test_t056_idempotency、test_t056_proxy_password_impact、test_t056_reference_events、test_t056_references、test_a6_error_contract、test_control_service、test_control_migration、test_t035_profile_domain、test_t054_migration、test_agent_executor_control。
- 后端其余改动测试 + OpenAPI 同步测试（9 个文件）：86 passed，0 failed（46.64s）。含 `test_exported_openapi_schema_matches_live_app` 与 `test_internal_openapi_export_matches_checked_in_file`，即签入的 OpenAPI 文件与 live app 一致。
- 后端全量（`tests/unit tests/integration`，默认 basetemp）：25 failed / 2136 passed / 8 skipped（460.57s）。25 个 FAILED 逐名与实施方 `t056_full_backend2.log` 的 25 个完全相同，且全部落在 9 组 t055 基线失败内（agent_executor_chain 7、t028 4、normal_exit_replay 4、automation_probe_chain 3、t034 2、automation_cdp_flow 2、repo_hygiene 1、automation_cdp 1、control_attendant_chain 1），零新增失败。repo_hygiene 的 1 个失败是已知流程文件问题（审阅报告含绝对路径），非交付物缺陷。
- 前端新改测试（11 个文件）：100 passed，0 failed。含 sse.reference.test.ts（真实本地 HTTP 服务器 + 真实 SSE 客户端）、ProfileCreateDialog（双提交去重、关闭重开沿用同一键）、GroupManagerDialog / ProxyFormDialog（在途禁用）、useProfilesQuery A31 查询失效。
- 前端全量：共跑 3 次。首跑 `npm test`（含类型门禁）：1 failed / 545 passed，失败为既存 `router.test.tsx` flaky（见未进表的提示）；随后纯 vitest 全量与完整 `npm test` 全量重跑均为 75 文件 546 passed、0 failed。最终确认 546/0。

## 危险模式扫描

- 对 `tests/` 与 `src/frontend/` 的 diff 新增行做 grep 扫描：`.skip(` / `.only(` / `assert True` / `expect(true)` / `# type: ignore` / `@ts-ignore` / `eslint-disable` / `@pytest.mark.skip` / 注释掉的 expect，零命中。
- 删测试：4 处，均有 spec 归因且有等价或更高层替代（见“改测方向复核”），无无归因删除。
- 弱化断言：无。A15 相关的旧 shape fixture 改动同步补了 `"detail" not in body` 断言，实为加强。
- mock 边界：`httpx.MockTransport`（外部 Supervisor / 网关边界）、`httpx.ASGITransport`（真实 app）、`TestClient`（真实 app）、真实本地 HTTP 服务器 + 真实 SSE 客户端均在系统边界；`_schedule_probe` 中和与 `write_transaction` 故障注入已逐项核实为隔离手段、未 mock 被测逻辑本身（见未进表的提示）。

reviewed_scope: 3d2d4dd1de72709d

verdict: PASS

## Round 2 (2026-11-12T05:50:44+08:00)

### 前轮 finding 复核

- **t056_test_f001（AC-004 字段名）——已消除。** 三项逐项核实：(a) task.md 的 diff 显示 AC 文本唯一改动就是 AC-004 的 `error_reason` → `last_coordinator_error`，其余 12 条 AC 只有打勾变化，无其他措辞改动；(b) 生产字段确为 `last_coordinator_error`：`src/backend/cbrowser/domain/models.py:785,808`（两处模型字段）、`src/backend/cbrowser/api/v1/runtime_views.py:91`（视图透传）、`src/backend/cbrowser/api/runtime_coordinator.py:75-81`（docstring 明文写了下游 `error: message` 经 `last_coordinator_error` 呈现的映射）；全树 grep `error_reason`，生产代码中无此字段，仅剩 `runtime_coordinator.py:76` docstring 的描述性措辞、`test_t056_coordinator_errors.py:2,216` 的文件/测试 docstring，以及 `test_t056_migrations.py:229` 的 legacy settings JSON 夹具键（t054 已删的网络操作 payload）；(c) progress.md 记录在案且基本准确：处置表 `progress.md:180`、核实记录 `:199`、复核 `:205` 均有。一处可忽略的行号漂移：`:199` 引用 `domain/models.py:778,801`，实际为 `:785,808`（修复轮编辑导致行号上移），实质无误，不作 finding。A15 契约区 bullet 的“写入 error_reason”按 progress.md 记录保留 adoption 决策原文措辞，未改动——属范围说明文字，非 AC，接受此处置。
- **t056_test_f002（AC-001 争用断言）——已消除，且断言确为可区分的。** `tests/unit/test_t056_migrations.py:135-147`：`started = time.monotonic()` 包住 `run_database_migrations(db)`，断言 `elapsed >= 0.5`（注释写明 holder 约 0.7s 释放、真实等待约 0.55s）。我自跑 5 次 pytest 均通过；另用 /tmp 复现脚本跑 10 次，elapsed 稳定在 0.566–0.570s（±2ms）。我自己做的两组探针（字节均以 sha256 恢复验证）：探针 A 把 `migrations.py:137` 的 `_switch_to_wal` 超时改为 0（禁用有界重试）→ 测试 FAILED；探针 B 把 holder 的 `time.sleep(0.7)` 改为 0（无争用空跑）→ 测试 FAILED，失败信息正是新断言本身：`AssertionError: migration did not wait out the holder: 0.014s`（与修复方声称的 0.014s 一致）。修复后两文件 sha256 与探针前完全一致（`migrations.py` d60d80c1…、`test_t056_migrations.py` 0c2b988f…）。阈值余量约 66ms，观测抖动仅 ±2ms，15 次全部通过，稳定；余量偏薄列入未进表的提示，不作 finding。

### code findings 的测试侧复核（Round 1 code f001–f003 的新增测试）

- **code f001（OpenAPI 422 断言）——测试真实且非空。** `tests/unit/test_t035_openapi_contract.py:68-108` 的 `test_openapi_422_is_validation_error_response_not_http_validation_error`：对 live app 双 variant（public/internal）逐个操作断言每个 422 均为 `ValidationErrorResponse`，并对签入的两份 JSON 做同样的原文与结构断言，且全树无 `HTTPValidationError`。自跑通过。非空验证：基线 `3fbcec1` 的 `cbrowser_v1.json` 含 37 处 `HTTPValidationError`、仅 6 处 `ValidationErrorResponse`；当前两文件为 42/53 处 `ValidationErrorResponse`、0 处 `HTTPValidationError`，与修复方声称一致；前端生成类型 `src/frontend/src/shared/api/generated/cbrowser_v1.d.ts` 同为 42/0。
- **code f002（两组 409-not-500 重放测试）——测试真实且非空。** `tests/unit/test_t056_idempotency.py:112`（group）与 `:199`（proxy）：同 operation_id 创建 → 删除 → 另一实体占用同名 → 原 operation_id 重放，断言 `ValueError("group/proxy name already exists")`。自跑通过。非空验证：若无修复，重放会递归至 RecursionError 而非 ValueError，`pytest.raises(ValueError)` 必然失败；修复方的 red-before 探针（2 failed，62.12s）与该机制一致。
- **code f003（0009 回填断档测试）——测试真实且非空，SQL 偏离成立。** `tests/unit/test_t056_migrations.py:376` 的 `test_0009_backfill_skips_existing_numbers_with_gaps`（0008 建库，A=1、B=3、C=NULL，迁移后断言 C=4）：自跑通过。非空验证：我在 /tmp 用系统 sqlite3 3.45.1 复现旧回填 SQL 在同一场景下报 `IntegrityError: UNIQUE constraint failed: profiles.display_number`。reviewer 字面建议（`COALESCE(MAX(display_number), 0) + ROW_NUMBER() OVER (...)` 在 NULL 子集上算）确不可直接用：裸写进 UPDATE SET 报 `OperationalError: misuse of window function ROW_NUMBER()`；放进标量子查询则静默算错值（NULL 子集上的 MAX 为 NULL → 0+1=1，撞上已有行）——修复方声称的报错措辞（misuse of aggregate: MAX()）与我的实测措辞不完全相同（取决于具体写法），但“字面建议不可用”的实质成立。修复方改用 Python 预读 max 作绑定参数 + 一次性 `UPDATE ... FROM` 算号，我在 /tmp 验证同一场景得 C=4，正确。偏离合理，测试有效。

### OpenAPI 滞后争议调查（修复方“签入文件修复前已滞后” vs Round 1 test review“86 passed 含同步测试”）

结论：**Round 1 test review 正确；修复方的“已滞后”结论不成立。** 证据链：

1. 修复方引用的“旧文件 8 处”数字与**基线 commit `3fbcec1` 的文件完全一致**（`git show 3fbcec1:schemas/openapi/cbrowser_v1.json` 含 8 处 `"name": "Idempotency-Key"`；当前文件 14 处，internal 文件基线 9 处、当前 15 处，diff 两文件各 +6 处）。“旧文件 8 处”最可信的解释是修复方恢复的是基线版本，而非修复前的实施版本。
2. 实施方自己的 progress.md:144 已记录：Phase 3 再生成时 A23 参数尚未落地导致滞后，**实施期内已重跑 `scripts/export_openapi.py` 闭环**（“两文件现与 live 完全一致（`live == checked` 已验证）”），即送审前文件已同步。
3. 实施方全量日志 `.scratch/t056_full_backend2.log`（11-11 20:15，送审前）：25 failed / 2136 passed，两项同步测试不在 FAILED 清单中——若当时文件缺 6 个参数，深层相等断言 `live == checked` 必然失败。
4. Round 1 test review（20:49）明确把两项同步测试列入自跑的 86 个测试且全部通过。
5. 我自己的探针 C：把 `cbrowser_v1.json` 临时换成基线版本 → `test_exported_openapi_schema_matches_live_app` FAILED；恢复当前文件（sha256 a44ee702… 验证一致）→ 两项同步测试均 PASSED。基线文件复现了修复方的观测，说明其观测可由“恢复了错误版本”完整解释。
6. 方法论上该探针还有第二处缺陷：f001 修复本身改了 live app 的 422 形状，修复后拿任何修复前的文件去比对都会失败，探针无法区分“修复前已滞后”与“修复导致漂移”。

处置：不立 finding；当前两份签入文件与 live app 深层一致（两项同步测试自跑通过），滞后已闭环；重生成本身仍是必要的（422 修复所需）。progress.md:189 的该条附带发现措辞与事实不符，建议 chain runner 在收尾时更正记录（非交付物缺陷，不阻断）。

### 本轮新发现

0 条。

### 改测方向复核

本轮无“迁就实现”的改测。修复轮对测试的改动全部是新增或加强：f002 在既有测试中追加耗时断言（原有 `released.is_set()` 与 `journal_mode == "wal"` 断言原样保留）；f003、两组 409 测试、422 断言均为新增测试；无既有断言被修改、删除或弱化。危险模式扫描：对 `tests/` 与 `src/frontend/` 的 diff 新增行 grep `.skip(` / `.only(` / `assert True` / `expect(true)` / `# type: ignore` / `@ts-ignore` / `eslint-disable` / `@pytest.mark.skip` / 注释掉的 expect，零命中；修复轮无删测试。

### 结论

- 前轮 finding 复核：t056_test_f001、t056_test_f002 均已消除（均以 diff/代码/自跑实测核实，不采信处置表自述）；code f001–f003 的新增测试均真实、非空，f003 的 SQL 偏离经独立验证成立。
- OpenAPI 滞后争议已查清：Round 1 结论成立，修复方“修复前已滞后”的说法不成立（最可能是恢复了基线版本做探针），当前文件与 live app 一致；建议 chain runner 更正 progress.md:189 的措辞，不阻断。
- 改测方向复核：无。
- 本轮新发现：0 条。
- 未进表的提示：
  - f002 的 0.5s 阈值余量约 66ms（实测等待 0.566–0.570s，15 次抖动 ±2ms）：本机稳定，但理论上若主线程 sleep  overshoot 超过约 66ms 会误红；阈值由 Round 1 建议值（约 0.5s）定死且无法再抬高（真实等待约 0.55s），属可接受的固有余量，仅作记录。
  - 前端全量首跑 2 failed / 544 passed（75 文件），失败均为 5000ms 超时：`ProfileForm.test.tsx`（renders the four sections…）与 `SettingsPage.test.tsx`（switches remaining i18n labels…）；两文件均不在 t056 diff 内，失败时正与两路后端全量（本轮 + 并行 code review）争抢 1.5 核 CPU，文件耗时 21.9s 明显被饿死。单独重跑两文件 16/16 通过，确认为负载导致的 flaky 超时，与 t056 无关；Round 1 亦有同类 flaky（router.test.tsx），属既存现象。
  - progress.md:199 的行号漂移（`domain/models.py:778,801` 实际为 `:785,808`），实质无误，不作 finding。
  - 锁定用户裁决核查：src/tests/scripts/compose 的 diff 中 `com.cbrowser.deployment-id` 零命中；`cbrowser` 默认前缀为基线行为，本轮未动，无违规。
  - 环境门禁（与 Round 1 一致）：Gateway live 路由、AC-005 真实引擎启动、AC-004 真实 Supervisor 502、AC-012 双客户端实时同步、AC-001 部署级锁争用、黑盒门禁，本机无 Docker / 真实浏览器 / 真实引擎，记为 env-skip，progress.md 已登记，不构成失败。
  - `git status` 无残留探针/临时文件（未跟踪文件仅两份 Round 1 审阅报告与本次新增的 Round 2 报告本身）；我的三组探针文件均已以 sha256 恢复验证，/tmp 备份已清理。
- 总体判断：前轮 2 条 minor 均已真正消除，code 修复的新增测试均真实非空，OpenAPI 争议已查清且当前状态正确，危险模式扫描干净，独立重跑的回归与修复方宣称一致（后端 2140/25/8/0、失败逐名与基线一致；前端 546/0 扣除负载 flaky 后成立）。无未解决的 critical / important，13 条 AC 全部 TICK-VALID。
- 系统性 follow-up：无。

### AC 复验方式

- AC-001：TICK-VALID，re_verified。`test_migration_waits_out_busy_timeout` 自跑 5 次通过 + 10 次复现耗时 0.566–0.570s；自做探针 A（重试超时置 0）与探针 B（holder 睡眠置 0）均 FAILED，且探针 B 失败点正是新断言（0.014s）。
- AC-002：TICK-VALID，re_verified。`test_control_service.py::test_renew_upgrade_publishes_only_after_commit` 所在套件在受影响套件重跑（117 passed）与后端全量（2140 passed）中通过。
- AC-003：TICK-VALID，re_verified。`test_a6_error_contract.py` 13 个测试重跑通过；新增 422 断言自跑通过（live 双 variant + 签入文件）。
- AC-004：TICK-VALID，re_verified。生产字段确为 `last_coordinator_error`（`domain/models.py:785,808`、`runtime_views.py:91`），AC 文本已改为该字段名；`test_t056_coordinator_errors.py` 的 AC-004 测试在套件重跑中通过。
- AC-005：TICK-VALID，re_verified。`test_t056_proxy_password_impact.py` 4 个测试在受影响套件重跑中通过。
- AC-006：TICK-VALID，re_verified。`test_t056_migrations.py` 的 NULL 写库 / 模型构造失败测试与新增 0009 断档回填测试（C=4）自跑通过；旧回填 SQL 在 /tmp 复现报 IntegrityError。
- AC-007：TICK-VALID，re_verified。`test_t056_idempotency.py` 17 个测试重跑通过，含新增的两组 409-not-500 重放测试。
- AC-008：TICK-VALID，re_verified。前端在途禁用与幂等键复用组件测试在前端全量中通过（544 passed，2 超时 flaky 不在 diff 文件内且单独重跑通过）。
- AC-009：TICK-VALID，re_verified。`test_t056_coordinator_errors.py` 7 个测试在受影响套件重跑中通过。
- AC-010：TICK-VALID，re_verified。`test_t056_references.py` 9 个测试在受影响套件重跑中通过。
- AC-011：TICK-VALID，re_verified。`test_t056_migrations.py` 的 LegacySchemaError 三组测试在受影响套件重跑中通过。
- AC-012：TICK-VALID，re_verified。`test_t056_reference_events.py` 与前端 `sse.reference.test.ts` 及查询失效测试在前后端全量中通过；两项 OpenAPI 同步测试自跑通过。
- AC-013：TICK-VALID，re_verified。`test_t056_migrations.py` 的 0004 错形列失败、全部 revision downgrade 抛错、新库结构 golden 对比测试在受影响套件重跑与后端全量中通过。

coverage = 13 / 13

## 自跑实数（Round 2，本 reviewer 独立执行）

- 关键新增测试 7 个一次跑过：`test_migration_waits_out_busy_timeout`、`test_0009_backfill_skips_existing_numbers_with_gaps`、两组 409-not-500 重放测试、422 断言、两项 OpenAPI 同步测试（3.91s）。
- f002 耗时测试：pytest 自跑 5 次全过；/tmp 复现脚本 10 次，elapsed 0.566–0.570s。
- 探针 A（`_switch_to_wal` 超时置 0）：1 failed；探针 B（holder 睡眠置 0）：1 failed，`AssertionError: migration did not wait out the holder: 0.014s`；探针 C（`cbrowser_v1.json` 换基线版）：同步测试 1 failed，恢复后 2 passed。探针后文件均 sha256 恢复验证。
- f003 SQL 验证（/tmp，系统 sqlite3 3.45.1）：旧回填 SQL 在 A=1、B=3、C=NULL 场景报 `IntegrityError: UNIQUE constraint failed`；reviewer 字面建议裸写报 `OperationalError: misuse of window function ROW_NUMBER()`，子查询写法静默算错值 1；修复方替代写法得 C=4。
- 受影响后端套件（13 文件）：117 passed（Round 1 为 114，+3 恰为修复轮新增的 3 个后端测试）；另 9 文件组 94 passed（含重叠文件）；受影响测试共收集 95 个，与修复方“95 passed”一致。
- 后端全量（`tests/unit tests/integration`，默认 basetemp）：25 failed / 2140 passed / 8 skipped（911.06s，因与并行 code review 全量争抢 CPU 而变慢）。25 个 FAILED 与修复方全量日志逐名完全相同，且全落在 9 组 t055 基线失败内（agent_executor_chain 7、t028 4、normal_exit_replay 4、automation_probe_chain 3、t034 2、automation_cdp_flow 2、repo_hygiene 1、automation_cdp 1、control_attendant_chain 1），零新增失败。
- 前端全量（`npm test`，含类型门禁）：75 文件，544 passed / 2 failed（243.03s）；2 个失败均为 5000ms 超时的非 diff 文件 flaky，单独重跑 16/16 通过（见结论未进表的提示）。

## 危险模式扫描（Round 2）

- 对 `tests/` 与 `src/frontend/` 的 diff 新增行做 grep 扫描：`.skip(` / `.only(` / `assert True` / `expect(true)` / `# type: ignore` / `@ts-ignore` / `eslint-disable` / `@pytest.mark.skip` / 注释掉的 expect，零命中。
- 删测试：修复轮 0 处删除；实现轮的 4 处删除已在 Round 1 复核（均有 spec 归因与等价替代）。
- 弱化断言：无。修复轮只新增断言/测试，未动既有断言。
- mock 边界：本轮新增测试未引入新 mock（409 测试走真实 repo + 真实 SQLite，422 断言走真实 live app + 签入文件原文，0009 测试走真实 alembic 迁移）。

reviewed_scope: 72cc8c4e992e1853

verdict: PASS
