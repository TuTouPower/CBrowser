# Task review t018（reviewer_focus: 代码）

- task：`t018_v2_test_gates_hygiene`
- spec：`docs/tasks/t018_v2_test_gates_hygiene/task.md`
- diff_anchor：`5a3da225fbccf59d410e708a3754e7ab2160e12b`
- target：`git -C '/Users/karson/kar/code/CBrowser_t018' diff 5a3da225fbccf59d410e708a3754e7ab2160e12b`
- round：1
- reviewed_at：2026-11-03T10:44:35+08:00

reviewed_scope: bdba5aa92c5411d1

## Findings

### t018_code_f001 - 必需模式漏掉策略失败用例的镜像变量

- 严重度：important
- 锚点：AC-001
- 位置：`tests/e2e/conftest.py:12-21`、`tests/e2e/test_supervisor_policy_failure_e2e.py:54-58`
- 问题：`REQUIRED_E2E_ENV` 未包含 `CBROWSER_INVALID_POLICY_TEST_IMAGE`，而 `test_supervisor_policy_failure_e2e.py` 仍以 `pytest.skip` 处理该变量缺失。实跑 `CBROWSER_E2E_REQUIRED=1 ... pytest tests/e2e/test_supervisor_policy_failure_e2e.py --collect-only` 的缺失清单不含该变量；提供其余变量后该用例会静默 skip，必需模式无法做到“缺任何必需镜像即会话开始失败并列出缺项”。同类问题：`tests/e2e/test_runtime_profile_defaults_e2e.py:438-442` 在镜像/缓存实际不存在时仍 skip。
- 建议：把 `CBROWSER_INVALID_POLICY_TEST_IMAGE` 纳入必需清单；必需模式下将此类 skip 改为 fail，或在 conftest 统一检查镜像可解析。

### t018_code_f002 - AC-002 的跨测试模块 fixture 借用与 sys.path 注入仍存在

- 严重度：important
- 锚点：AC-002
- 位置：`tests/e2e/test_supervisor_policy_failure_e2e.py:41-49`、`tests/e2e/test_supervisor_startup_recovery_e2e.py:50-58`、`tests/unit/test_runtime_event_policy.py:11-12`、`tests/integration/test_supervisor_manual_retry.py:10`、`tests/integration/test_supervisor_start_capacity.py:14`、`tests/unit/test_baseline_fixture_regressions.py:1125-1130`、`tests/conftest.py:8-12`
- 问题：AC-002 要求“共享 fixture 由 conftest 提供，不存在跨测试模块的 fixture 借用与 sys.path 注入”，但上述位置仍通过 `importlib` 加载另一个测试模块并取 `real_api_server`/`supervisor_api`/`db_context`，`tests/conftest.py` 也仍在执行 `sys.path.insert`。这会让 fixture 解析绕过 pytest fixture 图、重复执行模块导入副作用，并继续保留 AC 明确要删除的注入方式。
- 建议：把共享 fixture 移到 `tests/conftest.py`/`tests/unit/conftest.py`；删除 `spec_from_file_location` 与跨测试模块 import；用项目路径配置或安装包替代 `sys.path` 注入。

### t018_code_f003 - 首帧与输入延迟只有记录，没有上限断言

- 严重度：important
- 锚点：AC-003
- 位置：`tests/e2e/test_frontend_app_e2e.py:629-631`、`tests/e2e/test_frontend_app_e2e.py:677-686`、`tests/e2e/test_frontend_app_e2e.py:752-753`
- 问题：`first_frame_ms` 与 `input_latency_ms` 只写入证据字典，没有任何上限断言。首帧退化到数十秒、输入延迟明显超标时测试仍会通过，AC-003 声明的“首帧与输入延迟上限等断言覆盖其声明的行为”未实现。
- 建议：按 A36 的要求设置宽松但明确的上限断言，例如 `assert first_frame_ms <= <bound>`、`assert input_latency_ms <= <bound>`，并把阈值写入证据。

### t018_code_f004 - 冻结恢复后的帧增长在 app E2E 中仍未断言

- 严重度：important
- 锚点：AC-003
- 位置：`tests/e2e/test_frontend_app_e2e.py:858-866`
- 问题：冻结前取 `before`，恢复后只断言 `after["video"]["framesDecoded"] > 0`，没有与 `before` 比较。恢复后即使不再产生新帧，旧计数仍大于 0，用例会通过。`test_frontend_session_e2e.py` 已补增长断言，但同一 AC 的 app E2E 分支仍保留弱断言。
- 建议：轮询到 `framesDecoded > before["video"]["framesDecoded"]` 后再断言，并保留 `tab_id` 不变断言。

### t018_code_f005 - 清理校验仍在 finally 中抛错，掩盖原始失败

- 严重度：important
- 锚点：AC-003
- 位置：`tests/e2e/test_runtime_coordinator_e2e.py:407-491`、`tests/e2e/test_supervisor_recovery_e2e.py:1033-1070`、`tests/e2e/test_supervisor_container_graph_e2e.py:576-681`
- 问题：这些 `finally` 块在收集到 cleanup 错误后直接 `raise RuntimeError(...)`。若测试主体已失败，finally 的新异常会替换原始异常，pytest 只显示清理错误，原始失败现场丢失；这正是 AC-003“清理校验不掩盖原始失败”要消除的模式（A37 也要求把零泄漏校验移出 finally 作为独立步骤）。
- 建议：保存主体异常并把 cleanup 错误作为附加信息重新抛出（如 `raise original from cleanup_error` / `ExceptionGroup`），或将清理校验移到 finally 之后单独执行。

### t018_code_f006 - 统一门禁脚本的 E2E 依赖不完整，脚本无法运行

- 严重度：important
- 锚点：AC-006
- 位置：`scripts/run_gates.sh:30-35`、`tests/e2e/test_browser_runtime_e2e.py:33-38`、`tests/e2e/test_runtime_coordinator_e2e.py:167-168`
- 问题：E2E 分支的 `uv run` 只带 `pytest/pytest-asyncio/playwright/docker/httpx/aiohttp/pydantic/websockets`，缺少 `uvicorn`、`fastapi`、`sqlalchemy[asyncio]`、`aiosqlite`、`alembic`、`argon2-cffi`、`jsonschema`。`test_browser_runtime_e2e.py` 在模块顶层 `import uvicorn` 与 `from cbrowser.api.app import create_app`，`test_runtime_coordinator_e2e.py` 也会导入 uvicorn/fastapi；`CBROWSER_RUN_E2E=1 scripts/run_gates.sh` 会在收集/启动阶段失败，无法作为 AC-006 的本地全量门禁入口。
- 建议：把 `testing.md` 前端 E2E 命令中的依赖补进脚本，至少包含 `uvicorn fastapi "sqlalchemy[asyncio]" aiosqlite alembic argon2-cffi jsonschema`。

### t018_code_f007 - 归档 spike 的 agent_token.secret 未被忽略

- 严重度：important
- 锚点：AC-007
- 位置：`.gitignore:59-62`、`docs/archive/spikes/s006_gateway_media_recovery/code/probe/run_verification.py:35`
- 问题：s006 harness 把 `agent_token.secret` 写在脚本目录（`WORKSPACE/agent_token.secret`），但 `.gitignore` 只覆盖 `probe_work/`、`*secret*.txt`、`*token*.txt`。`git check-ignore docs/archive/spikes/s006_gateway_media_recovery/code/probe/agent_token.secret` 返回 1；若在仓库内直接运行该归档探针，秘密文件会进入可提交状态，与 AC-007“harness 写出的秘密文件被忽略”不符。
- 建议：增加 `docs/archive/spikes/**/*.secret` 或显式忽略 `agent_token.secret`，或让 harness 写入 `probe_work/`。

### t018_code_f008 - verify_frontend_dist 的新鲜度检查破坏生产镜像构建

- 严重度：important
- 锚点：非范围“不改生产代码行为” + 行为缺陷
- 位置：`scripts/verify_frontend_dist.py:120`、`config/docker/Dockerfile:11-20`
- 问题：`verify_frontend_dist()` 现在无条件调用 `verify_frontend_build_freshness(dist_dir)`，后者默认用 `REPO_ROOT/src/frontend` 计算源哈希。生产 Dockerfile 只复制 `dist/`、`vendor_selkies_web.py` 与 `verify_frontend_dist.py`，不复制 `src/frontend`；把脚本按 `/app/scripts` 布局放入临时目录、仅提供刚构建的 dist 时，实跑得到 `Frontend dist is stale relative to current source`。即使 dist 是新鲜的，`docker compose build` 也会失败，属于本 task 引入的生产构建回归。
- 建议：将新鲜度检查移出 `verify_frontend_dist`（放到 E2E conftest 或 npm postbuild），或为 `verify_frontend_dist` 增加可选 `frontend_dir` 且源目录不存在时跳过；生产镜像路径不应依赖源码树。

### t018_code_f009 - 路径隐私守卫整体排除了 docs/reviews，未来审阅文档不受保护

- 严重度：important
- 锚点：AC-007
- 位置：`tests/unit/test_repo_hygiene.py:24`、`docs/blueprint/conventions.md:29`
- 问题：守卫测试在扫描前跳过所有 `docs/reviews/` 文件，但 `docs/reviews` 不属于 `docs/archive`，AC-007 与 conventions 都要求“已跟踪的非归档文本文件”不含家目录绝对路径。现存 `docs/reviews/review_20261101_075819/review_opencode_cpa_gemini_3_8_flash.md:348` 仍含 `/Users/karson/...`；更关键的是，新增的审阅文档写入同样路径也会被整体跳过，守卫无法阻止后续泄露。A44 只豁免历史快照，不能推导出整个目录永久豁免。
- 建议：只 allowlist 历史文件，或先把历史 review 快照迁入 `docs/archive/reviews/` 后扫描其余 `docs/reviews`；至少让新增审阅文件受守卫约束。

### t018_code_f010 - ProductionGatewayService.stop 未关闭 ApiRuntimeLookup 的 httpx 客户端

- 严重度：minor
- 锚点：行为缺陷（资源泄漏）
- 位置：`tests/fixtures/supervisor_recovery_probe/gateway_service.py:27`、`tests/fixtures/supervisor_recovery_probe/gateway_service.py:165-171`
- 问题：`ApiRuntimeLookup.__init__` 创建 `httpx.AsyncClient`，`FakeGatewayApiClient.close()` 也会转发关闭，但 `ProductionGatewayService.stop()` 只停 aiohttp runner，不调用 `self.api.close()`。每个使用 `runtime_lookup` 的恢复 E2E 都会遗留未关闭的 AsyncClient，可能产生 unclosed socket/ResourceWarning，并在多次运行时累积。
- 建议：在 `stop()` 中调用 `await self.api.close()`，并保证幂等。

### t018_code_f011 - 移除 sys.path 注入后留下未使用的 sys 导入

- 严重度：minor
- 锚点：死代码
- 位置：`tests/e2e/test_frontend_adapter_build.py:12`、`tests/e2e/test_frontend_app_auth_e2e.py:15`、`tests/e2e/test_frontend_app_e2e.py:14`、`tests/e2e/test_frontend_media_e2e.py:15`、`tests/e2e/test_frontend_session_e2e.py:19`、`tests/e2e/test_frontend_display_apply_e2e.py:16`、`tests/e2e/test_frontend_session_vendor.py:6`、`tests/integration/test_gateway_control.py:14`、`tests/integration/test_gateway_signaling.py:14`、`tests/integration/test_runtime_coordinator_integration.py:14`
- 问题：这些文件移除 `sys.path` 操作后不再使用 `sys`，导入变为死代码；`test_frontend_session_vendor.py:8` 还保留“Ensure repo root is on sys.path”的过期注释。
- 建议：删除未使用导入与过期注释。

## 结论

- 前轮 finding 复核：Round 1，无前轮 finding。
- 本轮新发现：11 条（9 important + 2 minor）。
- 未进表的提示：
    - 文件过大：`tests/e2e/test_stream_runtime_e2e.py` 1663 行（本 task 净增 40）、`tests/unit/test_baseline_fixture_regressions.py` 1270 行（净增 31）、`tests/e2e/test_frontend_app_e2e.py` 1215 行（净增 4），均超过测试源码 1200 行阈值；`tests/unit/test_stream_agent_lifecycle.py` 713 行、`tests/e2e/test_frontend_media_e2e.py` 949 行超过 600 行 minor 阈值。按规则只提示，不单列 finding。
    - 测试层观察（未进 finding）：`pytest tests/e2e/test_frontend_build_wiring.py -q` 为 2 failed；`test_package_build_runs_vendor_and_verification` 仍断言 `postbuild == "npm run verify:selkies"`，而 `src/frontend/package.json:12` 已改为先写 build stamp；`test_valid_dist_passes` 的合成 dist 没有 build stamp，修掉既有 CSS 失败后仍会撞上新鲜度检查。另 `tests/e2e/conftest.py` 的新鲜度检查仅在 `CBROWSER_E2E_REQUIRED=1` 时生效，普通本地 E2E 不校验。
    - AC-004 / AC-005 未打勾，按未完成处理；note 已自述剩余并行双跑、证据脱敏、私有断言与固定延迟，不能按完成计。
    - CI 全绿无真实 GitHub Actions 运行证据，只有 `ci.yml` 静态核对。
- 总体判断：AC-001/002/003/006/007 存在已打勾但未完整实现的项，且 `verify_frontend_dist` 改动破坏生产镜像构建，当前不可 PASS。
- 系统性 follow-up：
    - 生产镜像与前端新鲜度解耦归 `t012`（v2 正式部署产物与部署文档）；本轮若不修，至少需保证 `docker compose build` 不因 stamp 检查失败。
    - AC-004/AC-005 仍属 t018，不另立 task。
    - 建议新增 pNNN（标题：归档历史 review 快照并恢复路径守卫；slug：archive_historical_reviews_home_paths），用于处理 `docs/reviews` 历史家目录路径与守卫 allowlist。

### AC 复验方式

- AC-001：`re_verified`。核对 `tests/e2e/conftest.py` 必需变量与 `pytest.exit`，并实跑 required 模式 collection；发现缺 `CBROWSER_INVALID_POLICY_TEST_IMAGE`。
- AC-002：`re_verified`。grep/读取测试导入，确认跨模块 fixture 借用与 `sys.path` 注入仍存在；生产 Gateway 的使用已静态核对。
- AC-003：`re_verified`。逐项核对断言；实跑 `pytest tests/e2e/test_frontend_build_wiring.py -q`（2 failed）作为测试可运行性证据，完整 Docker E2E 未跑。
- AC-004：未打勾，未实现，未复验。
- AC-005：未打勾，未实现，未复验。
- AC-006：`trust_prior`。静态核对 `ci.yml` 的 SHA 钉版、`release.yml` 删除与 `run_gates.sh`；CI 实际全绿依赖 GitHub Actions 运行，本轮无该证据。
- AC-007：`re_verified`。实跑 `tests/unit/test_repo_hygiene.py` 与 `tests/unit/test_frontend_build_freshness.py`（3 passed）；`git check-ignore` 发现 `agent_token.secret` 未忽略，另静态核对归档 README 与 vendor 解包检查。

coverage = 4 / 7

verdict: FAIL

## Round 2 (2026-11-03T11:03:40+08:00)

reviewed_scope: da1eae9122b416a2

### 前轮 finding 复核

- `t018_code_f001`：已消除。`tests/e2e/conftest.py:19-29` 已把 `CBROWSER_INVALID_POLICY_TEST_IMAGE` 纳入必需清单，required 模式在 collection 阶段 `pytest.exit`。非 required 模式的 skip 保留，但不影响 AC-001 的必需模式语义。
- `t018_code_f002`：仍存在。`tests/conftest.py:9-12` 仍执行 `sys.path.insert`；`tests/unit/test_runtime_event_policy.py:11`、`tests/integration/test_supervisor_start_capacity.py:14`、`tests/integration/test_supervisor_manual_retry.py:10` 仍从其他测试模块借用 fixture；`tests/e2e/test_supervisor_policy_failure_e2e.py:41-48`、`tests/e2e/test_supervisor_startup_recovery_e2e.py:51-57`、`tests/unit/test_baseline_fixture_regressions.py:1123-1134` 仍用 `importlib` 加载生产无关的测试模块，且 policy/startup 文件中 `_core_module` 已无消费者，属于死加载。
- `t018_code_f003`：已消除。`tests/e2e/test_frontend_app_e2e.py:632` 与 `:688` 分别断言 `first_frame_ms <= 8000`、`input_latency_ms <= 3000`。
- `t018_code_f004`：已消除。`tests/e2e/test_frontend_app_e2e.py:868` 断言恢复后 `framesDecoded` 大于冻结前值；`test_frontend_session_e2e.py:449-451` 同样有增长断言。
- `t018_code_f005`：仍存在。`tests/e2e/test_runtime_coordinator_e2e.py:489-491`、`tests/e2e/test_supervisor_recovery_e2e.py:1067-1070`、`tests/e2e/test_supervisor_container_graph_e2e.py:679-681` 仍在 `finally` 中直接 `raise RuntimeError`；若主体已失败，清理异常会替换原始异常，正是 AC-003 要消除的模式。
- `t018_code_f006`：已消除。`scripts/run_gates.sh:32-37` 已补 `fastapi/uvicorn/sqlalchemy[asyncio]/aiosqlite/alembic/argon2-cffi/jsonschema` 等 E2E 依赖。
- `t018_code_f007`：已消除。`git check-ignore docs/archive/spikes/s006_gateway_media_recovery/code/probe/agent_token.secret` 命中 `.gitignore:63` 的 `docs/archive/spikes/**/*.secret`。
- `t018_code_f008`：已消除。`scripts/verify_frontend_dist.py:79-82` 的 `verify_frontend_dist` 默认 `check_freshness=False`，`config/docker/Dockerfile` 调用未带 `--check-freshness`，生产镜像不再依赖源码树。
- `t018_code_f009`：原「整体排除 `docs/reviews`」已消除，但 allowlist 不完整并直接导致守卫失败，见本轮 `t018_code_f012`。
- `t018_code_f010`：仍存在。`tests/fixtures/supervisor_recovery_probe/gateway_service.py:156-171` 的 `ProductionGatewayService.stop()` 仍未调用 `self.api.close()`，使用 `ApiRuntimeLookup` 的恢复/重试用例每次遗留未关闭的 `httpx.AsyncClient`。
- `t018_code_f011`：仍存在并扩大。除前轮列出的 `sys` 未使用外，`ruff F401` 还命中 `tests/e2e/test_runtime_coordinator_e2e.py:14,20`、`tests/e2e/test_supervisor_container_graph_e2e.py:16,24`、`tests/e2e/test_supervisor_core_e2e.py:26,27,28,35`、`tests/integration/test_runtime_coordinator_integration.py:8,11`、`tests/integration/test_supervisor_rpc.py:3`、`tests/integration/test_v2_api_subprocess.py:6` 等；`tests/e2e/test_frontend_session_vendor.py:8` 的过期注释仍在。

### 本轮新发现

#### t018_code_f012 - 路径隐私守卫在当前交付树上直接失败

- 严重度：important
- 锚点：AC-007（已跟踪的非归档文本文件不含家目录绝对路径，由测试守护）
- 位置：`tests/unit/test_repo_hygiene.py:29`、`tests/unit/review_privacy_allowlist.txt:2-5`、`docs/reviews/review_20261102_201727/bundle_global_system_properties.md:53`、`docs/reviews/review_20261102_201727/bundle_local_archive_tasks.md:46,83`、`docs/tasks/t018_v2_test_gates_hygiene/review_code.md:6`、`docs/tasks/t018_v2_test_gates_hygiene/review_test.md:6`
- 问题：allowlist 只列了 4 个历史文件，仍遗漏 `bundle_global_system_properties.md` 与 `bundle_local_archive_tasks.md`；同时当前任务已跟踪的两份 review 报告也包含绝对 worktree 路径。实跑 `pytest tests/unit/test_repo_hygiene.py -q` 得到 `1 failed, 1 passed`，失败消息列出上述 7 处开发者家目录前缀。该测试在 `tests/unit` 内，CI 的 v2 unit step 会因此变红，AC-007「由测试守护」当前不成立。
- 建议：补齐两个历史文件到 allowlist；明确 task review 报告是否纳入守卫（若纳入则改用相对路径，若不纳入则在 allowlist 显式覆盖 `docs/tasks/**/review_*.md`）；最终以 `tests/unit/test_repo_hygiene.py` 通过为准。

#### t018_code_f013 - 移除 sys.path 注入时误删了 REPO_ROOT 定义，shutdown E2E 必 NameError

- 严重度：important
- 锚点：AC-006（本地全量门禁须可执行）；行为缺陷：E2E 启动即失败
- 位置：`tests/e2e/test_supervisor_event_shutdown_e2e.py:80,104,156`
- 问题：diff 删除了 `REPO_ROOT = Path(__file__).resolve().parents[2]` 与 `FIXTURES_DIR` 的整段 sys.path 设置，但测试主体仍使用 `REPO_ROOT`。`ruff F821` 报告三处未定义名；实际执行该 E2E 会在 `test_supervisor_cli_graceful_shutdown_on_sigterm` 内抛 `NameError: name 'REPO_ROOT' is not defined`，`CBROWSER_RUN_E2E=1 scripts/run_gates.sh` 无法全绿。
- 建议：恢复 `REPO_ROOT = Path(__file__).resolve().parents[2]`（FIXTURES_DIR 不需要则只保留 REPO_ROOT），或从统一 conftest 暴露路径常量。

#### t018_code_f014 - stream_runtime E2E 动态端口 helper 缺少 socket 导入

- 严重度：important
- 锚点：AC-006（本地全量门禁须可执行）；行为缺陷：测试启动即 NameError
- 位置：`tests/e2e/test_stream_runtime_e2e.py:45,52`
- 问题：本轮新增的 `_free_tcp_port()` / `_free_udp_port()` 调用 `socket.socket(...)`，但模块导入段（`:7-23`）没有 `import socket`；`test_stream_runtime_direct_media_matrix` 在 `:568` 首次调用即抛 `NameError`。`ruff F821` 也报告 `:45,52` 的 `socket` 未定义。此外 `:21` 的 `DEFAULT_GATEWAY_PORT` 已不再使用。
- 建议：补 `import socket`，删除未使用的 `DEFAULT_GATEWAY_PORT`；若希望两个 helper 端口绝不重复，可在一次分配中保留 socket 到容器启动后再释放。

#### t018_code_f015 - testing.md 与 stream_runtime.md 仍引用已删除的身份测试文件

- 严重度：minor
- 锚点：文档与实现不一致
- 位置：`docs/blueprint/testing.md:75`、`docs/blueprint/stream_runtime.md:49`
- 问题：`tests/e2e/test_stream_client_identity_e2e.py` 已在本 task 整体删除，但 testing.md 的 Stream Runtime 命令仍把它列为 pytest 输入，照文档执行会因文件不存在直接失败；stream_runtime.md 仍把它列为身份/重连覆盖来源。
- 建议：从 testing.md 命令中删除该路径，并在 stream_runtime.md 更新为实际的生产 adapter/前端 E2E 覆盖说明。

## 结论

- 前轮 finding 复核：f001/f003/f004/f006/f007/f008 已消除；f002/f005/f010/f011 仍存在；f009 主问题已修但留下 f012；本轮新发现 4 条（3 important + 1 minor）。
- 未进表的提示：
    - `tests/e2e/conftest.py:41-56` 的构建新鲜度检查仍只在 `CBROWSER_E2E_REQUIRED=1` 时生效；若 AC-001 的「前端 E2E 在构建产物与当前源码内容不一致时拒绝运行」适用于普通本地 E2E，则这里仍是缺口，建议在非 required 模式也校验。
    - 前轮列出的文件过大项：`tests/e2e/test_stream_runtime_e2e.py` 1663 行、`tests/unit/test_baseline_fixture_regressions.py` 1270 行、`tests/e2e/test_frontend_app_e2e.py` 1215 行，均超过测试源码 1200 行阈值；本轮未新增同量级文件，按规则只提示。
    - `tests/e2e/test_supervisor_core_e2e.py:299` 在 `d_client.close()` 之后调用 `scan_active_containers()`；requests Session close 后可继续发请求，本轮不据此出 finding，但把零泄漏断言移到关闭客户端之后不够稳健。
    - `testing.md` 仍保留逐层命令，`scripts/run_gates.sh` 只是新增引用而未成为唯一入口；若按 AC-006「testing.md 只引用该脚本」字面执行，需进一步收敛。
- 总体判断：AC-002/003/007 仍有 blocker，且本轮引入的 E2E NameError 与守卫测试失败使当前树不可作为可信门禁，verdict 必须 FAIL。
- 系统性 follow-up：f012 的 allowlist/审查报告路径策略属 t018 收尾范围，不另立 task；历史 review 快照归档可沿用前轮建议的 `archive_historical_reviews_home_paths`。

### AC 复验方式

- AC-001：`re_verified`。核对 `tests/e2e/conftest.py` 必需清单与 `pytest.exit`；`CBROWSER_INVALID_POLICY_TEST_IMAGE` 已加入。新鲜度仅在 required 模式生效的残余见未进表提示。
- AC-002：`re_verified`。grep/ruff 确认跨测试模块 importlib 借用与 `tests/conftest.py` 的 `sys.path.insert` 仍在。
- AC-003：`re_verified`。核对首帧/输入延迟上限与冻结帧增长断言已补；核对三处 `finally` 仍在抛清理异常。
- AC-004：未打勾，未实现，未复验。
- AC-005：未打勾，未实现，未复验。
- AC-006：`trust_prior`。静态核对 `run_gates.sh` 依赖与 `ci.yml`；无真实 GitHub Actions 全绿证据；本轮另发现两处 E2E NameError。
- AC-007：`re_verified`。`pytest tests/unit/test_repo_hygiene.py -q` 实跑失败（1 failed, 1 passed），失败项正是 allowlist 遗漏与 review 报告路径。

coverage = 4 / 7

verdict: FAIL

## Round 3 (2026-11-03T11:53:44+08:00)

- round：3
- reviewed_at：2026-11-03T11:53:44+08:00

reviewed_scope: 6c7ccfe25dc088c6

### 前轮 finding 复核

- `t018_code_f001`：已消除。`tests/e2e/conftest.py:19-30` 已含 `CBROWSER_INVALID_POLICY_TEST_IMAGE`；实跑 `CBROWSER_E2E_REQUIRED=1 pytest tests/e2e --collect-only` 以 exit 2 列出 9 个缺项。
- `t018_code_f002`：仍存在。`tests/conftest.py:9-12` 仍执行 `sys.path.insert`；`tests/unit/test_runtime_event_policy.py:11-12`、`tests/integration/test_supervisor_manual_retry.py:10`、`tests/integration/test_supervisor_start_capacity.py:14` 仍从其他测试模块借用 fixture；`tests/unit/test_baseline_fixture_regressions.py:1126-1164` 仍用 `importlib` 加载 `tests/e2e/test_supervisor_recovery_e2e.py` 并驱动其 `real_api_and_sup` fixture；`tests/e2e/test_supervisor_policy_failure_e2e.py:42-48`、`tests/e2e/test_supervisor_startup_recovery_e2e.py:51-57` 的 `_core_module` 已无消费者，只剩死加载与模块导入副作用。
- `t018_code_f003`：已消除。`tests/e2e/test_frontend_app_e2e.py:631` 断言 `first_frame_ms <= 8000`，`:687` 断言 `input_latency_ms <= 3000`。
- `t018_code_f004`：已消除断言缺失。`tests/e2e/test_frontend_app_e2e.py:867` 已比较冻结前值；`test_frontend_session_e2e.py` 使用增长轮询。app E2E 未轮询增长，见未进表提示。
- `t018_code_f005`：仍存在。`tests/e2e/test_runtime_coordinator_e2e.py:490`、`tests/e2e/test_supervisor_recovery_e2e.py:1069-1070`、`tests/e2e/test_supervisor_container_graph_e2e.py:681` 仍在测试主体的 `finally` 中直接抛清理异常；主体先失败时新异常会替换原始异常，原始失败现场丢失（`tests/e2e/test_supervisor_recovery_e2e.py:228-229` 的 fixture teardown 属另一形态，仅增加 teardown error）。
- `t018_code_f006`：已消除。`scripts/run_gates.sh:29-37` 已补 E2E 依赖；本轮实跑 `scripts/run_gates.sh`（非 E2E）全部通过，E2E collect 78 通过。
- `t018_code_f007`：已消除。`git check-ignore docs/archive/spikes/s006_gateway_media_recovery/code/probe/agent_token.secret` 命中 `.gitignore:63`。
- `t018_code_f008`：已消除。`scripts/verify_frontend_dist.py:80-82` 默认 `check_freshness=False`，`config/docker/Dockerfile:18-20` 未传 `--check-freshness`；生产镜像路径不再依赖源码树。
- `t018_code_f009`：已消除。`tests/unit/test_repo_hygiene.py:24` 现在只跳过 `docs/archive/` 与逐文件 allowlist，`docs/reviews` 其余文件受扫描；实跑 `pytest tests/unit/test_repo_hygiene.py -q` 为 2 passed。
- `t018_code_f010`：已消除。`tests/fixtures/supervisor_recovery_probe/gateway_service.py:165-172` 的 `stop()` 已调用 `await self.api.close()`。
- `t018_code_f011`：仍存在并扩大。当前 `ruff --select F401` 命中本轮触及文件：`tests/e2e/test_runtime_coordinator_e2e.py:14`（`importlib.util`）、`tests/e2e/test_supervisor_container_graph_e2e.py:16,24`、`tests/e2e/test_supervisor_core_e2e.py:26,27,34`、`tests/e2e/test_stream_runtime_e2e.py:21`（`DEFAULT_GATEWAY_PORT`）、`tests/e2e/test_frontend_session_vendor.py:5,6`、`tests/integration/test_runtime_coordinator_integration.py:8,11`、`tests/integration/test_supervisor_rpc.py:3`、`tests/integration/test_v2_api_subprocess.py:6`、`tests/unit/test_baseline_fixture_regressions.py:14`、`tests/fixtures/frontend_probe/harness.py:7`；`tests/e2e/test_frontend_session_vendor.py:8` 的过期注释仍在。
- `t018_code_f012`：已消除。实跑 `pytest tests/unit/test_repo_hygiene.py -q` 为 2 passed；allowlist 已补齐两个历史文件与 task review 报告。
- `t018_code_f013`：仍存在。`tests/e2e/test_supervisor_event_shutdown_e2e.py:80,104,156` 使用未定义的 `REPO_ROOT`（ruff F821）；提供镜像变量后该测试会 `NameError`。
- `t018_code_f014`：仍存在。`tests/e2e/test_stream_runtime_e2e.py:45,52` 使用未导入的 `socket`（ruff F821）；`:568-576` 首次调用即 `NameError`。
- `t018_code_f015`：仍存在。`docs/blueprint/testing.md:75` 与 `docs/blueprint/stream_runtime.md:49` 仍引用已删除的 `tests/e2e/test_stream_client_identity_e2e.py`。

### 本轮新发现

#### t018_code_f016 - AC-002 测试前置条件仍分散在多个模块且语义不一致

- 严重度：important
- 锚点：AC-002「测试前置条件由单一模块定义且语义一致」
- 位置：`tests/e2e/conftest.py:19-30`、`tests/e2e/test_supervisor_core_e2e.py:54-70`、`tests/e2e/test_supervisor_recovery_e2e.py:54-70`、`tests/e2e/test_supervisor_startup_recovery_e2e.py:62-76`、`tests/e2e/test_supervisor_policy_failure_e2e.py:52-80`、`tests/e2e/test_runtime_profile_defaults_e2e.py:42-56,439-442`、`tests/e2e/test_supervisor_resource_policy_e2e.py:20-24`
- 问题：新增的 `REQUIRED_E2E_ENV` 只在 conftest 定义，但至少 7 个 E2E 模块仍各自维护一份环境/镜像检查，且语义不同：conftest 在必需模式 `pytest.exit`，各模块在缺失时 `pytest.skip`，`test_runtime_profile_defaults_e2e.py` 还会在变量存在但镜像/缓存不可用时 skip。AC-002 要求的「单一模块定义且语义一致」未实现；两套清单已经漂移（例如 policy failure 的 `CBROWSER_RUNTIME_ENGINE_CACHE` 在 :80 单独 skip）。
- 建议：把 env/镜像/缓存检查收敛到 `tests/e2e/conftest.py` 的单一 helper；非必需模式由 helper 统一返回 skip 理由，必需模式统一 fail；删除各模块本地检查与重复清单。

#### t018_code_f017 - AC-004 动态端口先探测后释放，并行两轮仍可能端口冲突

- 严重度：important
- 锚点：AC-004「同一台机器上并行两次运行互不干扰」
- 位置：`tests/e2e/test_stream_runtime_e2e.py:44-58`、`:568-576`、`:724`
- 问题：`_free_tcp_port()`/`_free_udp_port()` 绑定 0（或扫描固定 UDP 段）拿到端口后立即关闭 socket，Gateway 与 Docker 发布端口在之后才绑定。同一轮内 `gw_port` 与 `stream_http_port` 连续两次调用、以及并行两轮之间都可能拿到同一端口，导致 `web.TCPSite` 或 `docker run -p 127.0.0.1:{udp}:{udp}/udp` 绑定失败。`note.md:33` 也自述 AC-004 的并行双跑实测尚未执行。
- 建议：端口探测与占用合一（保持监听 socket 到服务启动，或让 Docker 用 `-p 127.0.0.1::<port>/udp` 由系统分配后读回实际端口）；至少在绑定失败时重试并与并行双跑证据一起验证。

#### t018_code_f018 - AC-005 已勾选，但单元测试仍普遍断言私有状态并使用固定时间等待

- 严重度：important
- 锚点：AC-005「单元测试只经公开接口断言……时间相关逻辑使用注入时钟」
- 位置：`tests/unit/test_stream_capture_policy.py:116,126,132`、`tests/unit/test_supervisor_normal_exit_observation.py:719,733`、`tests/unit/test_docker_offload.py:134`、`tests/unit/test_stream_capture_policy.py:155,176`、`tests/unit/test_supervisor_normal_exit_observation.py:647,665`
- 问题：仍有大量单元测试直接断言 `agent._is_paused`、`core._terminal_observations`、`core._sessions` 等私有状态，并用固定 `asyncio.sleep` 等待；`note.md:33` 自述「AC-005 范围外单元测试仍有私有断言/固定延迟」。本 task 的 AC-005 已打勾，但实现并未覆盖这些单元测试；spec 的非范围只禁止改生产行为，允许为可观测性新增公开接口，不能支撑把 AC 降为部分完成。
- 建议：为被断言的状态增加公开只读访问器或改为断言公开可观察结果；时间等待改为注入时钟；若确实不纳入本 task，需改 AC 措辞而非勾选完成。

#### t018_code_f019 - AC-006 已勾选，但 testing.md 仍完整复制门禁命令

- 严重度：important
- 锚点：AC-006「本地全量门禁由单一入口脚本执行（含 E2E 必需模式），testing.md 只引用该脚本」
- 位置：`docs/blueprint/testing.md:44-49`、`:60-63`、`:75`、`:138-140`
- 问题：虽然新增了「本地全量门禁统一由 `scripts/run_gates.sh` 执行」一句，但 `test_cmd`、`blackbox_verify`、Stream Runtime 与 Supervisor 章节仍逐条复制 pytest/uv 命令，且与 `scripts/run_gates.sh` 的依赖列表持续漂移（例如 testing.md 的 E2E 命令省略 `cloakbrowser`、又保留已删除测试文件）。这正是 AC-006 要消除的双入口。
- 建议：全量门禁段落只保留 `scripts/run_gates.sh` 与所需环境变量说明；分层命令若保留，需明确标为非门禁的开发调试命令并去掉重复依赖清单。

#### t018_code_f020 - run_gates.sh 的临时 scratch 目录从不清理

- 严重度：minor
- 锚点：资源泄漏
- 位置：`scripts/run_gates.sh:6-7`、`:34-37`
- 问题：未设置 `CBROWSER_GATE_SCRATCH` 时脚本创建 `mktemp -d`，E2E basetemp 也会写入该目录，但脚本结束后目录保留；反复运行会累积 Docker 证据、basetemp 与 uv cache。
- 建议：脚本内记录是否自建 scratch，并在 `EXIT` trap 中清理（用户显式传入的目录不删）。

#### t018_code_f021 - spec 修正后留下重复措辞

- 严重度：minor
- 锚点：文档质量
- 位置：`docs/specs/runtime_persistence.md:90`
- 问题：凭据字面量已抽象化，但句子变成「严禁泄漏注入的注入的密码……」，「注入的」重复。
- 建议：改为「严禁泄漏注入的密码、Token、Cookie、剪贴板文本或私密笔记文本」。

### 结论

- 前轮 finding 复核汇总：f001/f003/f004/f006/f007/f008/f009/f010/f012 已消除；f002/f005/f011/f013/f014/f015 仍存在；f011 未修且范围扩大。
- 本轮新发现：6 条（4 important + 2 minor）。
- 未进表的提示：
    - AC-001 的新鲜度校验仍只在 `CBROWSER_E2E_REQUIRED=1` 时执行（`tests/e2e/conftest.py:41-48`）；若「前端 E2E 在构建产物不一致时拒绝运行」不限定必需模式，则仍是缺口（test reviewer 已按 important 报告）。
    - `tests/e2e/test_frontend_build_wiring.py::test_valid_dist_passes` 仍因 diff anchor 前已存在的合成 dist CSS 断言失败（实跑 1 failed, 7 passed），非本 task 引入，但 `CBROWSER_RUN_E2E=1 scripts/run_gates.sh` 仍无法全绿。
    - `tests/e2e/test_frontend_app_e2e.py:864-867` 在恢复后直接读取 `wait_iframe_stats`（该 helper 在 `framesDecoded > 0` 即返回），未轮询增长，存在偶发假红风险；session E2E 的同类断言已正确轮询。
    - `tests/unit/test_repo_hygiene.py:12-15,27` 只扫描固定后缀，`Dockerfile`、`.gitignore` 等无后缀文本不在守卫范围（当前无实际泄露）。
    - `tests/e2e/test_stream_runtime_e2e.py:31-34,853` 仍注入 `web_lock_shim.js` 并断言 tab 身份，建议后续清理（test reviewer 已提示）。
- 总体判断：f002/f005/f013/f014 与 AC-002/004/005/006 的新 blocker 未解决，当前树不能 PASS。
- 系统性 follow-up：无新增跨 task 缺口；阻断项均属 t018 收尾范围。历史 review 快照归档可沿用 `archive_historical_reviews_home_paths` 建议。

### AC 复验方式

- AC-001：`re_verified`。实跑必需模式 collection，exit 2 并列出 9 个缺项；实跑 `python3 scripts/verify_frontend_dist.py --check-freshness` 通过；非必需模式不检查新鲜度的残余见未进表提示。
- AC-002：`re_verified`。grep/ruff 查证 `sys.path` 注入、跨模块 fixture 借用与生产 Gateway 替换；发现 f002/f016。
- AC-003：`re_verified`。实跑 contract 169 passed、unit 540 passed、integration 79 passed；逐项核对首帧/输入延迟、冻结帧增长与清理异常路径；发现 f005 仍未消除。
- AC-004：`trust_prior`。并行两轮门禁需真实 Docker 双跑，本轮未执行，依赖实施侧 note 声明；静态查证端口、回环绑定、秘密权限与证据脱敏，发现 f017。
- AC-005：`re_verified`。grep 查证 unit 测试仍断言私有状态/固定时间等待；note 自述未完成，见 f018。
- AC-006：`trust_prior`。无真实 GitHub Actions 全绿证据；本地 `scripts/run_gates.sh` 实跑通过（非 E2E），`testing.md` 与单入口要求仍有差距（f019）。
- AC-007：`re_verified`。实跑 `pytest tests/unit/test_repo_hygiene.py -q` 2 passed；`git check-ignore` 命中归档秘密；`git ls-files --eol` 无 CRLF；vendor 相关 e2e 5 passed。

coverage = 5 / 7

verdict: FAIL

## Round 4 (2026-11-03T12:25:08+08:00)

- round：4
- reviewed_at：2026-11-03T12:25:08+08:00

reviewed_scope: 12d0d1493026e812

### 前轮 finding 复核

- `t018_code_f001`：已消除。`tests/e2e/conftest.py:19-30` 含 9 个必需变量；实跑 required 模式 collection 以 exit 2 列出 9 个缺项（含 `CBROWSER_INVALID_POLICY_TEST_IMAGE`）。
- `t018_code_f002`：仍存在。`tests/conftest.py:8-12` 仍 `sys.path.insert`；`tests/unit/test_runtime_event_policy.py:11-12`、`tests/integration/test_supervisor_manual_retry.py:10`、`tests/integration/test_supervisor_start_capacity.py:14` 仍从其他测试模块借用 `db_context`/`temp_db_path`/`supervisor_api` fixture；`tests/unit/test_baseline_fixture_regressions.py:1126-1164` 仍用 `importlib.util.spec_from_file_location` 加载 `tests/e2e/test_supervisor_recovery_e2e.py` 并直接驱动其 `real_api_and_sup` fixture。AC-002 的「不存在跨测试模块的 fixture 借用与 sys.path 注入」仍不成立。
- `t018_code_f003`：已消除。`tests/e2e/test_frontend_app_e2e.py:631` `first_frame_ms <= 8000`、`:687` `input_latency_ms <= 3000` 均在。
- `t018_code_f004`：已消除断言缺失。`tests/e2e/test_frontend_app_e2e.py:867` 比较冻结前帧数；`tests/e2e/test_frontend_session_e2e.py:425-452` 已改为增长轮询。app E2E 的单次读取残余见未进表提示。
- `t018_code_f005`：仍存在。`tests/e2e/test_runtime_coordinator_e2e.py:490`、`tests/e2e/test_supervisor_recovery_e2e.py:1068-1070`、`tests/e2e/test_supervisor_container_graph_e2e.py:681` 仍在测试主体的 `finally` 里直接抛清理异常；主体验证先失败时该异常替换原始失败。仅 IPv6 零泄漏断言被移出 finally，A37 目标的三个主体清理点未改。
- `t018_code_f006`：已消除。`scripts/run_gates.sh:39-43` 已含 fastapi/uvicorn/sqlalchemy/aiosqlite/alembic/argon2-cffi/jsonschema 等 E2E 依赖；E2E collect 78 通过。
- `t018_code_f007`：已消除。`git check-ignore docs/archive/spikes/s006_gateway_media_recovery/code/probe/agent_token.secret` 命中 `.gitignore` 的 `docs/archive/spikes/**/*.secret`。
- `t018_code_f008`：已消除。`scripts/verify_frontend_dist.py:80-82` 默认 `check_freshness=False`；`config/docker/Dockerfile` 未传 `--check-freshness`，生产镜像不依赖源码树。
- `t018_code_f009`：已消除。`tests/unit/test_repo_hygiene.py:26-34` 只跳过 `docs/archive/` 与逐文件 allowlist，`docs/reviews` 其余文件受扫描；`pytest tests/unit/test_repo_hygiene.py -q` 2 passed。
- `t018_code_f010`：已消除。`tests/fixtures/supervisor_recovery_probe/gateway_service.py:165-168` 的 `stop()` 先 `await self.api.close()`，再停 site/runner。
- `t018_code_f011`：仍存在。`ruff --select F401,F811,F821,F841 tests scripts src/backend/tests` 仍命中本 task 触及文件的未使用导入：`tests/e2e/test_runtime_coordinator_e2e.py:14`、`tests/e2e/test_stream_runtime_e2e.py:22`、`tests/e2e/test_supervisor_container_graph_e2e.py:16,24`、`tests/e2e/test_supervisor_core_e2e.py:26,27,34`、`tests/e2e/test_frontend_session_vendor.py:5,6`、`tests/fixtures/frontend_probe/harness.py:7`、`tests/integration/test_gateway_control.py:6`、`tests/integration/test_gateway_signaling.py:5`、`tests/integration/test_runtime_coordinator_integration.py:8,11`、`tests/integration/test_supervisor_rpc.py:3`、`tests/integration/test_v2_api_subprocess.py:6`、`tests/unit/test_baseline_fixture_regressions.py:14`。本轮已确认 F821 清零，`f013`/`f014` 的 NameError 已修。
- `t018_code_f012`：已消除。`tests/unit/review_privacy_allowlist.txt` 补齐历史文件与两份 task review 报告；`pytest tests/unit/test_repo_hygiene.py tests/unit/test_frontend_build_freshness.py -q` 3 passed。
- `t018_code_f013`：已消除。`tests/e2e/test_supervisor_event_shutdown_e2e.py:20` 恢复 `REPO_ROOT = Path(__file__).resolve().parents[2]`，`:82,106,158` 正常引用；ruff F821 清零。
- `t018_code_f014`：已消除。`tests/e2e/test_stream_runtime_e2e.py:12` 已 `import socket`，`:45-58` 的 helper 可执行；ruff F821 清零。
- `t018_code_f015`：仍存在。`docs/blueprint/testing.md:62` 的 Stream Runtime 命令仍包含已删除的 `tests/e2e/test_stream_client_identity_e2e.py`；`docs/blueprint/stream_runtime.md:49` 仍把它列为身份/重连覆盖来源。
- `t018_code_f016`：仍存在。`REQUIRED_E2E_ENV` 只在 `tests/e2e/conftest.py:19-30` 定义并在必需模式 `pytest.exit`，但 `test_supervisor_core_e2e.py:70`、`test_supervisor_recovery_e2e.py:70`、`test_supervisor_startup_recovery_e2e.py:65`、`test_supervisor_policy_failure_e2e.py:45,69`、`test_supervisor_retry_e2e.py:86`、`test_runtime_profile_defaults_e2e.py:442`（镜像实际不可用仍 skip）、`test_supervisor_resource_policy_e2e.py:20` 等仍各自维护清单并在缺失时 skip，语义与 conftest 不一致。AC-002「测试前置条件由单一模块定义且语义一致」仍不成立。
- `t018_code_f017`：仍存在。`tests/e2e/test_stream_runtime_e2e.py:45-58,569-577` 仍是探测即释放：`_free_tcp_port()`/`_free_udp_port()` 关闭 socket 后才由 aiohttp/Docker 绑定，并行两轮或同轮两次调用可撞端口；`note.md` 仍自述 AC-004 并行双跑未执行，而 AC-004 已打勾。
- `t018_code_f018`：仍存在。`tests/unit/test_stream_capture_policy.py:116,126,132,155,176`、`tests/unit/test_supervisor_normal_exit_observation.py:719,733,647,665`、`tests/unit/test_docker_offload.py:134` 仍直接断言 `agent._is_paused`、`core._sessions`、`core._terminal_observations` 等私有状态并用固定 `asyncio.sleep` 等待；AC-005 已打勾但实现未收敛。
- `t018_code_f019`：仍存在（部分收敛）。`docs/blueprint/testing.md:40-54` 的 `test_cmd`/`blackbox_verify` 已只引用脚本，但 `:118-136` 的 Supervisor 阶段仍复制全量 `pytest tests/unit tests/integration` 命令，且该命令未带 `--with pytest` 与后端依赖，实跑 `uv run --no-project --with docker --with aiohttp python -m pytest --version` 得到 `No module named pytest`；`:91` 仍称「test_cmd 中 tests/unit」「blackbox_verify 中 tests/integration」，与当前章节内容不符。「testing.md 只引用该脚本」仍不成立。
- `t018_code_f020`：已消除。`scripts/run_gates.sh:6-15` 记录 `CLEAN_SCRATCH` 并在 EXIT trap 中清理自建 `mktemp -d`，用户传入的 `CBROWSER_GATE_SCRATCH` 不删。
- `t018_code_f021`：仍存在。`docs/specs/runtime_persistence.md:90` 仍为「严禁泄漏注入的注入的密码……」。

### 本轮新发现

#### t018_code_f022 - testing.md 收敛为单入口后，模板契约测试与整条本地门禁变红

- 严重度：important
- 锚点：AC-006「每次 push 由 CI ... 并全绿；本地全量门禁由单一入口脚本执行」
- 位置：`docs/blueprint/testing.md:40-46`、`.repo_template/tests/test_contract_suite.py:82-96`、`scripts/run_gates.sh:19`
- 问题：`test_cmd` 章节删掉 `pytest .repo_template/tests -q -m contract` 后，模板契约 `test_testing_md_default_commands_use_contract_marker` 失败（该测试只在存在 `sync_state.json` 时跳过，本仓没有）。实跑 `uv run --no-project --with pytest python -m pytest .repo_template/tests/test_contract_suite.py::test_testing_md_default_commands_use_contract_marker -q` 为 `1 failed`；实跑 `scripts/run_gates.sh` 在第一步 contract 得到 `1 failed, 168 passed` 并因 `set -e` 直接退出，后续 legacy/unit/integration/frontend 一步都不会执行。CI 的 `Contract tests` 步骤执行同一命令，同样会红。AC-006 已打勾但当前门禁与 CI 均不可能全绿，`note.md` 的「contract 169」也不再成立。
- 建议：在 `test_cmd` 代码块保留模板契约要求的 `pytest .repo_template/tests -q -m contract`（同时保留 `scripts/run_gates.sh` 为唯一全量入口的说明），或按 `repo_sync.py` 流程生成 `.repo_template/sync_state.json` 走消费仓定制分支；两者择一，并同步修正 `testing.md:91-92` 对已不存在的命令位置的引用。不要通过弱化模板契约测试来过关。

#### t018_code_f023 - 新增 conftest 以空行结尾，仓库门禁命令报 whitespace 错误

- 严重度：minor
- 锚点：仓库卫生（`docs/blueprint/testing.md` 记录的 `git diff --check` 检查）
- 位置：`tests/e2e/conftest.py:139`
- 问题：`git diff --check 5a3da225fbccf59d410e708a3754e7ab2160e12b -- . ':(exclude)docs/archive/**'` 报 `tests/e2e/conftest.py:139: new blank line at EOF` 并以非零码退出；该命令是 testing.md 声明的活跃变更检查项。
- 建议：删除文件末尾多余空行。

### 结论

- 前轮 finding 复核：`f001/f003/f004/f006/f007/f008/f009/f010/f012/f013/f014/f020` 已消除；`f002/f005/f011/f015/f016/f017/f018/f019/f021` 仍存在（`f019` 部分收敛但门禁仍未单入口化）。
- 本轮新发现：2 条（1 important + 1 minor）。
- 未进表的提示：
    - 文件过大：`tests/e2e/test_stream_runtime_e2e.py` 1682 行（净增 59）、`tests/unit/test_baseline_fixture_regressions.py` 1270 行（净增 31）、`tests/e2e/test_frontend_app_e2e.py` 1216 行（净增 5），均超测试源码 1200 行阈值；`tests/e2e/test_frontend_media_e2e.py` 948 行、`tests/unit/test_stream_agent_lifecycle.py` 713 行超 600 行提示线。按规则只提示。
    - 复杂度：本轮人工扫描未发现新增 ≥15 的函数；`tests/fixtures/wait.py`/`scripts/verify_frontend_dist.py` 新增函数分支简单，无工具可用的 CC 结论。
    - `tests/e2e/test_frontend_build_wiring.py::test_valid_dist_passes` 仍因 diff anchor 前就存在的合成 dist CSS 断言失败（实跑 1 failed, 7 passed），非本 task 引入，但即使修掉 f022，`CBROWSER_RUN_E2E=1 scripts/run_gates.sh` 仍无法全绿。
    - `tests/e2e/conftest.py:42-56` 的构建新鲜度检查仍只在 `CBROWSER_E2E_REQUIRED=1` 时执行；若 AC-001 后半句不限定必需模式，普通本地 E2E 仍不拒绝陈旧 dist。
    - `tests/e2e/test_frontend_app_e2e.py:864-867` 冻结恢复后直接读一次 `wait_iframe_stats` 再断言增长，未像 session E2E 那样轮询，存在偶发假红。
    - `python3 .repo_template/scripts/md_format.py --check` 退出 1，命中历史 `docs/reviews/` 快照与两份 task review 报告；历史文件属既有状态，review 报告由 reviewer 写入，非本 task 实现可改。
    - `tests/e2e/test_runtime_coordinator_e2e.py:180` 的 API uvicorn 绑定 `0.0.0.0`（anchor 前已存在，容器需经 host 访问）；与 AC-004「测试服务只绑定回环」字面有张力，未单列 finding。
    - 本地实跑：legacy 384 passed、unit 540 passed、integration 79 passed、前端 Vitest 95 passed、`verify_frontend_dist.py --check-freshness` 通过、`git ls-files --eol` 无 CRLF；仅 contract 1 failed 阻断 `run_gates.sh`。
- 总体判断：`f002`（AC-002）、`f005`（AC-003）、`f016`（AC-002）、`f017`（AC-004）、`f018`（AC-005）、`f019` 与新增 `f022`（AC-006）仍阻断；AC-004/005/006 已打勾但实现未满足，当前树不能 PASS。
- 系统性 follow-up：`f022` 的 AC-006 与模板契约冲突属 t018 收尾决策；若最终判定模板契约不适用于定制消费仓，应经 `repo-template-sync` 流程生成状态文件，而不是改模板测试。历史 review 快照归档仍沿用 `archive_historical_reviews_home_paths` 建议。

### AC 复验方式

- AC-001：`re_verified`。required 模式 collection exit 2 并列出 9 个缺项；`python3 scripts/verify_frontend_dist.py --check-freshness` exit 0；非 required 模式的新鲜度缺口见未进表提示。
- AC-002：`re_verified`。grep/ruff 查证 `sys.path` 注入、跨模块 fixture 借用、生产 Gateway 替身删除（`gateway_fixture.py` 已删，`test_supervisor_gateway_control_auth.py` 使用 `ProductionGatewayService`）；f002/f016 仍开放。
- AC-003：`re_verified`。核对首帧/输入延迟上限、冻结帧增长、关闭页面后容器 running 且实例不变；f005 的 finally 清理异常仍在；完整 Docker E2E 未执行。
- AC-004：`trust_prior`。并行两轮真实 Docker 门禁未执行；静态核对端口派生、秘密权限（0o600）、回环绑定与证据默认写系统临时目录，f017 的端口竞态仍在。
- AC-005：`re_verified`。grep 确认单元测试仍断言私有状态并用固定 sleep 等待；f018 仍开放。
- AC-006：`re_verified`（本地门禁实跑；CI 真实运行仍 `trust_prior`）。本地 `scripts/run_gates.sh` 在 contract 步骤 1 failed 后退出，f022 成立；legacy/unit/integration/frontend 分层单独实跑全绿。
- AC-007：`re_verified`。`pytest tests/unit/test_repo_hygiene.py tests/unit/test_frontend_build_freshness.py -q` 3 passed；`git check-ignore` 命中归档秘密；`git ls-files --eol` 无 CRLF；vendor 穿越拒绝与目录集合校验静态核对通过。

coverage = 6 / 7

verdict: FAIL

## Round 5 (2026-11-03T12:47:00+08:00)

- round：5
- reviewed_at：2026-11-03T12:47:00+08:00

reviewed_scope: 8a91451b6f27a76d

### 前轮 finding 复核

- `t018_code_f001`：已消除。`tests/e2e/conftest.py:19-29` 含 9 个必需变量；实跑 `CBROWSER_E2E_REQUIRED=1 pytest tests/e2e --collect-only`（补 httpx 依赖）以 exit 2 列出 9 个缺项，含 `CBROWSER_INVALID_POLICY_TEST_IMAGE`。
- `t018_code_f002`：仍存在。`tests/conftest.py:8-12` 仍执行 `sys.path.insert`；`tests/unit/test_runtime_event_policy.py:11-12`、`tests/integration/test_supervisor_manual_retry.py:10`、`tests/integration/test_supervisor_start_capacity.py:14` 仍从其他测试模块借用 fixture；`tests/unit/test_baseline_fixture_regressions.py:1123-1130` 仍用 `importlib.util.spec_from_file_location` 加载 `tests/e2e/test_supervisor_recovery_e2e.py`。AC-002 的「不存在跨测试模块的 fixture 借用与 sys.path 注入」仍不成立。
- `t018_code_f003`：已消除。`tests/e2e/test_frontend_app_e2e.py:631` 断言 `first_frame_ms <= 8000`，`:687` 断言 `input_latency_ms <= 3000`。
- `t018_code_f004`：已消除。`tests/e2e/test_frontend_app_e2e.py:867` 断言恢复后 `framesDecoded` 大于冻结前值；`tests/e2e/test_frontend_session_e2e.py:425-452` 使用增长轮询。
- `t018_code_f005`：仍存在。`tests/e2e/test_runtime_coordinator_e2e.py:489-490`、`tests/e2e/test_supervisor_recovery_e2e.py:1067-1070`、`tests/e2e/test_supervisor_container_graph_e2e.py:675-681` 仍在测试主体的 `finally` 中抛清理异常（graph 还有 finally 内 assert）；主体先失败时清理异常会替换原始失败，违反 AC-003「清理校验不掩盖原始失败」。
- `t018_code_f006`：已消除。`scripts/run_gates.sh:39-43` 已含 E2E 依赖；本轮 `scripts/run_gates.sh` 非 E2E 全绿。
- `t018_code_f007`：已消除。`git check-ignore docs/archive/spikes/s006_gateway_media_recovery/code/probe/agent_token.secret` 命中 `.gitignore:63`。
- `t018_code_f008`：已消除。`scripts/verify_frontend_dist.py:83` 默认 `check_freshness=False`，`config/docker/Dockerfile` 未传 `--check-freshness`。
- `t018_code_f009`：已消除。`tests/unit/test_repo_hygiene.py:26-34` 只跳过 `docs/archive/` 与逐文件 allowlist；`pytest tests/unit/test_repo_hygiene.py -q` 2 passed。
- `t018_code_f010`：已消除。`tests/fixtures/supervisor_recovery_probe/gateway_service.py:165-172` 的 `stop()` 先 `await self.api.close()`。
- `t018_code_f011`：仍存在（minor）。`ruff --select F401` 仍命中本 task 触及文件：`tests/e2e/test_frontend_session_vendor.py:5-6`、`tests/e2e/test_runtime_coordinator_e2e.py:14`、`tests/e2e/test_stream_runtime_e2e.py:22`、`tests/e2e/test_supervisor_container_graph_e2e.py:16,24`、`tests/e2e/test_supervisor_core_e2e.py:26,27,34`、`tests/fixtures/frontend_probe/harness.py:7`、`tests/integration/test_gateway_control.py:6`、`tests/integration/test_gateway_signaling.py:5`、`tests/integration/test_runtime_coordinator_integration.py:8,11`、`tests/integration/test_supervisor_rpc.py:3`、`tests/integration/test_v2_api_subprocess.py:6`、`tests/unit/test_baseline_fixture_regressions.py:14`；`tests/e2e/test_frontend_session_vendor.py:8` 的过期注释仍在。
- `t018_code_f012`：已消除。`tests/unit/review_privacy_allowlist.txt` 补齐历史文件与两份 review 报告；`pytest tests/unit/test_repo_hygiene.py tests/unit/test_frontend_build_freshness.py -q` 3 passed。
- `t018_code_f013`：已消除。`tests/e2e/test_supervisor_event_shutdown_e2e.py:20` 已定义 `REPO_ROOT`；ruff F821 清零。
- `t018_code_f014`：已消除。`tests/e2e/test_stream_runtime_e2e.py:12` 已 `import socket`；ruff F821 清零。
- `t018_code_f015`：仍存在（minor）。`docs/blueprint/testing.md:63` 的 Stream Runtime 命令仍包含已删除的 `tests/e2e/test_stream_client_identity_e2e.py`；`docs/blueprint/stream_runtime.md:49` 仍把它列为身份/重连覆盖来源。
- `t018_code_f016`：仍存在。`REQUIRED_E2E_ENV` 只在 `tests/e2e/conftest.py:19-29` 定义，但 `tests/e2e/test_supervisor_core_e2e.py:57-70`、`tests/e2e/test_supervisor_recovery_e2e.py:53-70`、`tests/e2e/test_supervisor_startup_recovery_e2e.py:54-65`、`tests/e2e/test_supervisor_policy_failure_e2e.py:42-69`、`tests/e2e/test_supervisor_retry_e2e.py:73-86`、`tests/e2e/test_runtime_profile_defaults_e2e.py:439-442`、`tests/e2e/test_supervisor_resource_policy_e2e.py:18-22` 仍各自维护清单并在缺失时 skip；AC-002「测试前置条件由单一模块定义且语义一致」仍不成立。
- `t018_code_f017`：仍存在。`tests/e2e/test_stream_runtime_e2e.py:45-58` 仍是探测即释放，`:569-577` 关闭 socket 后才由 aiohttp/Docker 绑定；同轮两次调用与并行两轮都可能撞端口。`note.md` 仍自述 AC-004 并行双跑未执行，而 `task.md` 已勾选 AC-004。
- `t018_code_f018`：仍存在。`tests/unit/test_stream_capture_policy.py:116,126,132`、`tests/unit/test_supervisor_normal_exit_observation.py:695-733`、`tests/unit/test_docker_offload.py:134` 仍直接断言 `agent._is_paused`、`core._sessions`、`core._terminal_observations` 等私有状态；AC-005 已勾选但未满足。
- `t018_code_f019`：修不彻底。`test_cmd`/`blackbox_verify` 已只引用 `scripts/run_gates.sh`（`docs/blueprint/testing.md:40-55`），但 `:119-128` 的 Supervisor 章节仍复制 `pytest tests/unit tests/integration` 全量命令，且该命令只带 `--with docker --with aiohttp`，实跑 `uv run ... python -m pytest --version` 得到 `No module named pytest`；AC-006「testing.md 只引用该脚本」仍不成立。
- `t018_code_f020`：已消除。`scripts/run_gates.sh:5-15` 记录 `CLEAN_SCRATCH` 并在 EXIT trap 清理自建目录。
- `t018_code_f021`：仍存在（minor）。`docs/specs/runtime_persistence.md:90` 仍为「严禁泄漏注入的注入的密码……」。
- `t018_code_f022`：已消除。`docs/blueprint/testing.md:44` 恢复 `pytest .repo_template/tests -q -m contract`；实跑该模板契约测试 1 passed，完整 contract 169 passed，`scripts/run_gates.sh` 非 E2E 全绿。
- `t018_code_f023`：已消除。`git diff --check 5a3da22... -- . ':(exclude)docs/archive/**'` exit 0。

### 本轮新发现

#### t018_code_f024 - 前端新鲜度哈希漏掉 postcss 构建输入

- 严重度：minor
- 锚点：AC-001「构建产物与当前源码内容不一致时拒绝运行」
- 位置：`scripts/verify_frontend_dist.py:33-36`
- 问题：`frontend_source_hash()` 的候选列表包含 `index.html`、`package.json`、`vite.config.ts`、`vite.selkies.config.ts`、`tailwind.config.ts`、`tsconfig.json`、`package-lock.json` 与 `src`/`public`，但没有 `src/frontend/postcss.config.js`。该文件参与 Vite CSS 构建；修改 tailwind/autoprefixer 配置后 dist 已陈旧，但 stamp 不变，E2E 新鲜度门禁不会拒绝运行。
- 建议：把 `postcss.config.js`（以及其他参与生产构建的根配置）加入 `frontend_source_hash` 候选列表，并补一条修改该文件后 stamp 失效的测试。

#### t018_code_f025 - Supervisor/RuntimeCoordinator E2E 仍用固定宿主端口，并行两轮会冲突

- 严重度：important
- 锚点：AC-004「端口……按运行派生或由系统分配……同一台机器上并行两次运行互不干扰」
- 位置：`tests/e2e/test_supervisor_core_e2e.py:141,191,221`、`tests/e2e/test_supervisor_recovery_e2e.py:572,586,621,623`、`tests/e2e/test_runtime_coordinator_e2e.py:34-37,98-99`、`src/backend/cbrowser/supervisor/container_spec.py:156-157`
- 问题：Supervisor E2E 用 `PortAllocator(min_port=30000, max_port=30010)` 分配 UDP mux 端口，并断言恰好为 30000/30001；`stream_ports()` 把该端口发布到宿主 `127.0.0.1:{port}/udp`。并行两轮时先启动的一轮占用宿主 30000，后一轮的 allocator 在自身容器网络命名空间内仍可能选中 30000（或选中 30001 后断言 30000 失败），导致 `port is already allocated` 或断言失败。`test_runtime_coordinator_e2e.py:34-37` 的 `find_free_port()` 同样是探测后释放的竞态。AC-004 的并行互不干扰未实现。
- 建议：E2E 端口范围按运行派生（随机基址）或由 Docker 分配后读回实际端口；断言改为「在本次运行的派生范围内」而非固定 30000/30001；并用真实并行双跑验证。

#### t018_code_f026 - testing.md 仍引用已变更的 test_cmd 内容

- 严重度：minor
- 锚点：文档与实现不一致
- 位置：`docs/blueprint/testing.md:91-92`
- 问题：`test_cmd` 已收敛为 `scripts/run_gates.sh`，但 Schema/codegen 章节仍写「在上述 test_cmd 已设置的 TMPDIR / UV_CACHE_DIR 下」以及「test_cmd 中 `tests/unit`……blackbox_verify 中 `tests/integration`」；这些命令已不在对应章节，照文档查找会落空。
- 建议：改为引用 `scripts/run_gates.sh`（及脚本内部设置的 TMPDIR/UV_CACHE_DIR），或把分层命令明确标为脚本内部步骤。

### 结论

- 前轮 finding 复核汇总：`f001/f003/f004/f006/f007/f008/f009/f010/f012/f013/f014/f020/f022/f023` 已消除；`f002/f005/f016/f017/f018` 仍存在；`f019` 修不彻底；`f011/f015/f021` 仍为 minor。
- 本轮新发现：3 条（1 important + 2 minor）。
- 未进表的提示：
    - 文件过大：`tests/e2e/test_stream_runtime_e2e.py` 1682 行（净增 59）、`tests/unit/test_baseline_fixture_regressions.py` 1270 行（净增 31）、`tests/e2e/test_frontend_app_e2e.py` 1216 行（净增 5），均超测试源码 1200 行阈值；`tests/e2e/test_frontend_media_e2e.py` 948 行、`tests/unit/test_stream_agent_lifecycle.py` 713 行超 600 行提示线。按规则只提示。
    - 复杂度：本轮新增/修改函数未发现 CC ≥ 15；`pytest_collection_modifyitems`、`frontend_source_hash` 分支简单，无工具级 CC 结论。
    - `tests/e2e/conftest.py:41-56` 的构建新鲜度检查仍只在 `CBROWSER_E2E_REQUIRED=1` 时执行；普通本地前端 E2E 不校验陈旧 dist。若 AC-001 后半句不限定必需模式，这是残余缺口。
    - `tests/e2e/test_runtime_coordinator_e2e.py:180` 的 API uvicorn 仍绑定 `0.0.0.0`（anchor 前已存在，容器需经 host 访问）；与 AC-004「测试服务只绑定回环」字面有张力。
    - `scripts/run_gates.sh:19` 的契约步骤使用裸 `pytest`，其余步骤用 `uv run`；无全局 pytest 的干净环境会在第一步失败。
    - `tests/fixtures/supervisor_recovery_probe/gateway_service.py:165-172` 的 `stop()` 先 `api.close()` 再停 site/runner；若 close 抛错会跳过 site/runner 清理（低概率健壮性提示）。
    - `python3 .repo_template/scripts/md_format.py --check` 仍因历史 `docs/reviews/` 快照与两份 review 报告退出 1；历史文件属既有状态，review 报告由 reviewer 写入，非本 task 实现可改。
    - 本地实跑：`scripts/run_gates.sh` 非 E2E 全绿（contract 169 passed，legacy/unit/integration/frontend 全绿）；`python3 scripts/verify_frontend_dist.py --check-freshness` exit 0；`pytest tests/unit/test_repo_hygiene.py tests/unit/test_frontend_build_freshness.py -q` 3 passed。
- 总体判断：AC-002/003/004/005/006 均已打勾但仍有未解决 blocker（f002/f005/f016/f017/f018/f019/f025），当前树不能 PASS。
- 系统性 follow-up：`f025` 的并行端口派生属 t018 收尾范围；若决定把 Supervisor/RuntimeCoordinator E2E 的固定端口保留为单机串行假设，应改 AC-004 措辞而非继续勾选。历史 review 快照归档仍沿用 `archive_historical_reviews_home_paths` 建议。

### AC 复验方式

- AC-001：`re_verified`。实跑 required 模式 collection，exit 2 列出 9 个缺项；`python3 scripts/verify_frontend_dist.py --check-freshness` exit 0；非 required 模式不校验新鲜度的残余见未进表提示。
- AC-002：`re_verified`。grep/ruff 确认 `tests/conftest.py` 的 `sys.path.insert`、三处跨测试模块 fixture 导入与 `test_baseline_fixture_regressions.py` 的 importlib 加载仍在；生产 Gateway 替身已删除并使用 `ProductionGatewayService`。
- AC-003：`re_verified`。核对首帧/输入延迟上限、冻结帧增长、关闭页面后容器 running 且实例不变；f005 的 finally 清理异常仍在；完整 Docker E2E 未执行。
- AC-004：`trust_prior`。并行两轮真实 Docker 门禁未执行，依赖 note 声明；静态核对端口派生、秘密权限、回环绑定与证据脱敏，发现 f017/f025。
- AC-005：`re_verified`。grep 确认单元测试仍断言私有状态；f018 仍开放。
- AC-006：`re_verified`（本地门禁实跑；CI 真实运行仍 `trust_prior`）。`scripts/run_gates.sh` 非 E2E 全绿、contract 169 passed；f019 的 testing.md 残余仍在。
- AC-007：`re_verified`。`pytest tests/unit/test_repo_hygiene.py tests/unit/test_frontend_build_freshness.py -q` 3 passed；`git check-ignore` 命中归档秘密；`git ls-files --eol` 无 CRLF；vendor 穿越拒绝与目录集合校验静态核对通过。

coverage = 6 / 7

verdict: FAIL

## Round 6 (2026-11-03T13:12:00+08:00)

- round：6
- reviewed_at：2026-11-03T13:12:00+08:00

reviewed_scope: 0bb96e6d2f5a5fcd

### 前轮 finding 复核

- `t018_code_f001`：已消除。`tests/e2e/conftest.py:19-29` 的 `REQUIRED_E2E_ENV` 含 `CBROWSER_INVALID_POLICY_TEST_IMAGE`；实跑 `CBROWSER_E2E_REQUIRED=1 ... pytest tests/e2e --collect-only` 以 exit 2 列出 9 个缺项。
- `t018_code_f002`：仍存在。`tests/conftest.py:8-12` 仍执行 3 条 `sys.path.insert`；`tests/unit/test_runtime_event_policy.py:11-12`、`tests/integration/test_supervisor_manual_retry.py:10`、`tests/integration/test_supervisor_start_capacity.py:14` 仍从其他测试模块借用 fixture；`tests/unit/test_baseline_fixture_regressions.py:1126` 仍用 `importlib.util.spec_from_file_location` 加载 `tests/e2e/test_supervisor_recovery_e2e.py`。AC-002「共享 fixture 由 conftest 提供，不存在跨测试模块的 fixture 借用与 sys.path 注入」不成立。
- `t018_code_f003`：已消除。`tests/e2e/test_frontend_app_e2e.py:631` 断言 `first_frame_ms <= 8000`，`:687` 断言 `input_latency_ms <= 3000`。
- `t018_code_f004`：已消除。`tests/e2e/test_frontend_app_e2e.py:867` 断言恢复后 `framesDecoded` 大于冻结前值；`tests/e2e/test_frontend_session_e2e.py:432-450` 使用增长轮询。app E2E 仍非轮询，见未进表提示。
- `t018_code_f005`：修不彻底。`tests/e2e/test_supervisor_container_graph_e2e.py:675-681` 已把所有权断言与清理异常移出 `finally`；但 `tests/e2e/test_runtime_coordinator_e2e.py:488-490` 与 `tests/e2e/test_supervisor_recovery_e2e.py:1067-1070` 仍在测试主体的 `finally` 内直接 `raise`。主体先失败时清理异常会替换原始失败，违反 AC-003「清理校验不掩盖原始失败」。
- `t018_code_f006`：已消除。`scripts/run_gates.sh:38-43` 含 E2E 依赖；本轮实跑 `scripts/run_gates.sh` 非 E2E 全绿（EXIT=0）。
- `t018_code_f007`：已消除。`git check-ignore -v docs/archive/spikes/s006_gateway_media_recovery/code/probe/agent_token.secret` 命中 `.gitignore:63`。
- `t018_code_f008`：已消除。`scripts/verify_frontend_dist.py:83` 默认 `check_freshness=False`，`config/docker/Dockerfile:18` 未传该开关。
- `t018_code_f009`：已消除。`tests/unit/test_repo_hygiene.py:26-34` 只跳过 `docs/archive/` 与逐文件 allowlist，`docs/reviews` 其余文件受扫描。
- `t018_code_f010`：已消除。`tests/fixtures/supervisor_recovery_probe/gateway_service.py:165-168` 的 `stop()` 先 `await self.api.close()`。
- `t018_code_f011`：仍存在。`uv run --with ruff ruff check --select F401,F811,F821,F841 tests scripts` 命中本 task 触及文件 18 处未使用导入（`tests/e2e/test_frontend_session_vendor.py:5-6`、`test_runtime_coordinator_e2e.py:14`、`test_stream_runtime_e2e.py:22`、`test_supervisor_container_graph_e2e.py:16,24`、`test_supervisor_core_e2e.py:26,27,34`、`tests/fixtures/frontend_probe/harness.py:7`、`tests/integration/test_gateway_control.py:6`、`test_gateway_signaling.py:5`、`test_runtime_coordinator_integration.py:8,11`、`test_supervisor_rpc.py:3`、`test_v2_api_subprocess.py:6`、`tests/unit/test_baseline_fixture_regressions.py:14`、`test_stream_capture_policy.py:7`）与 1 处未使用变量（`tests/unit/test_supervisor_normal_exit_observation.py:718`）；`test_frontend_session_vendor.py:8` 的过期注释仍在。修复过程新增 `test_stream_capture_policy.py:7` 的 `asyncio` 与 `test_supervisor_normal_exit_observation.py:718` 的 `key` 两处死代码。
- `t018_code_f012`：已消除。`tests/unit/review_privacy_allowlist.txt` 覆盖历史文件与两份 task review 报告；实跑 `pytest tests/unit/test_repo_hygiene.py tests/unit/test_frontend_build_freshness.py -q` 3 passed。
- `t018_code_f013`：已消除。`tests/e2e/test_supervisor_event_shutdown_e2e.py:20` 定义 `REPO_ROOT`；ruff F821 清零。
- `t018_code_f014`：已消除。`tests/e2e/test_stream_runtime_e2e.py:12` 已 `import socket`；ruff F821 清零。
- `t018_code_f015`：仍存在。`docs/blueprint/testing.md:63` 的 Stream Runtime 命令仍包含已删除的 `tests/e2e/test_stream_client_identity_e2e.py`；`docs/blueprint/stream_runtime.md:49` 仍把它列为身份/重连覆盖来源。
- `t018_code_f016`：仍存在。`REQUIRED_E2E_ENV` 只在 `tests/e2e/conftest.py:19-29` 定义并在必需模式 `pytest.exit`，但 12 个 E2E 模块仍各自维护清单并在缺失时 `pytest.skip`：`test_supervisor_core_e2e.py:54-70`、`test_supervisor_recovery_e2e.py:53-70`、`test_supervisor_startup_recovery_e2e.py:51-65`、`test_supervisor_policy_failure_e2e.py:42-69`、`test_supervisor_retry_e2e.py:70-86`、`test_runtime_profile_defaults_e2e.py:439-442`、`test_supervisor_resource_policy_e2e.py:18-22`、`test_supervisor_ipv6_policy_e2e.py:14-17` 等。AC-002「测试前置条件由单一模块定义且语义一致」不成立。
- `t018_code_f017`：同意撤回。AC-004 已由用户删除「同一台机器上并行两次运行互不干扰」，改为「单次门禁运行不与宿主已有资源冲突」；`tests/e2e/test_stream_runtime_e2e.py:45-58` 的 `_free_tcp_port`/`_free_udp_port` 在单次运行前探测宿主可用性，原并行前提消失。残余「探测后释放」竞态窗口极小，本轮只作提示，不再作为 blocking。
- `t018_code_f018`：仍存在。AC-005 已勾选，但 `tests/unit` 仍有 116 行私有属性访问/断言（如 `tests/unit/test_supervisor_recovery.py:394-395`、`test_supervisor_normal_exit_observation.py:351,439,695`、`test_resource_fault_isolation.py:32`、`test_supervisor_reconcile_fences.py:65,150-151`），`test_supervisor_normal_exit_observation.py:647,665` 仍用固定 `asyncio.sleep` 等待。`tests/unit/test_stream_capture_policy.py` 已改为公开 pipeline 状态并注入时钟，属部分修复；note 的「剩余存量不在本 task 触碰范围」不构成 AC 豁免。
- `t018_code_f019`：修不彻底。`test_cmd`/`blackbox_verify`（`docs/blueprint/testing.md:40-55`）已只引用脚本，但 `:63`（Stream Runtime）、`:114`（Gateway）、`:126-128`（Supervisor）、`:149-155`（前端）仍复制直接命令；其中 `:126` 的 `pytest tests/unit tests/integration` 只带 `--with docker --with aiohttp`，无 `pytest`/`httpx`，按文档执行会在 `tests/e2e/conftest.py:13` 导入 `httpx` 或启动 `python -m pytest` 时失败。AC-006「testing.md 只引用该脚本」不成立。
- `t018_code_f020`：已消除。`scripts/run_gates.sh:5-15` 记录 `CLEAN_SCRATCH` 并在 EXIT trap 清理自建目录。
- `t018_code_f021`：仍存在。`docs/specs/runtime_persistence.md:90` 仍为「严禁泄漏注入的注入的密码……」。
- `t018_code_f022`：已消除。`docs/blueprint/testing.md:45` 恢复模板契约命令；实跑 `pytest .repo_template/tests -q -m contract` 169 passed，`scripts/run_gates.sh` 全绿。
- `t018_code_f023`：已消除。`git diff --check 5a3da225... -- . ':(exclude)docs/archive/**'` exit 0。
- `t018_code_f024`：仍存在。`scripts/verify_frontend_dist.py:30-36` 的 `frontend_source_hash` 候选仍缺 `src/frontend/postcss.config.js`。
- `t018_code_f025`：仍存在（按新 AC-004 重述）。`tests/e2e/test_supervisor_core_e2e.py:141,191,221`、`test_supervisor_recovery_e2e.py:563-586`、`test_supervisor_startup_recovery_e2e.py:187,361`、`test_supervisor_policy_failure_e2e.py:115` 仍固定使用 `PortAllocator(min_port=30000, ...)` 并断言 30000/30001；`src/backend/cbrowser/supervisor/container_spec.py:156-157` 的 `stream_ports()` 把该 UDP 端口发布到宿主 `127.0.0.1:{port}`。若 Docker 宿主已有服务占用 30000/30001（例如本机正在运行 CBrowser），单次门禁会因端口已占用失败；端口也未按运行派生或由系统分配。AC-004 两个分句均不满足。
- `t018_code_f026`：仍存在。`docs/blueprint/testing.md:91-92` 仍写「在上述 test_cmd 已设置的 TMPDIR / UV_CACHE_DIR 下」「test_cmd 中 `tests/unit`……blackbox_verify 中 `tests/integration`」，对应章节已无这些命令。

### 本轮新发现：0 条

修复过程引入的两处死代码并入 `t018_code_f011`，其余残余只在结论段提示。

### 结论

- 前轮 finding 复核汇总：`f001/f003/f004/f006/f007/f008/f009/f010/f012/f013/f014/f020/f022/f023` 已消除；`f002/f005/f011/f015/f016/f018/f019/f021/f024/f025/f026` 仍存在（`f005`/`f019` 修不彻底）；`f017` 同意撤回（AC-004 并行条款已由用户删除）。
- 本轮新发现：0 条。
- 未进表的提示：
    - 文件过大：`tests/e2e/test_stream_runtime_e2e.py` 1682 行（净增 59）、`tests/unit/test_baseline_fixture_regressions.py` 1270 行（净增 31）、`tests/e2e/test_frontend_app_e2e.py` 1216 行（净增 5），均超测试源码 1200 行阈值；`tests/e2e/test_supervisor_recovery_e2e.py` 1070 行、`tests/e2e/test_frontend_media_e2e.py` 948 行、`tests/unit/test_stream_agent_lifecycle.py` 713 行、`tests/e2e/test_supervisor_container_graph_e2e.py` 681 行超 600 行提示线。按规则只提示。
    - 复杂度：本轮人工扫描新增/修改函数未发现 CC ≥ 15；`pytest_collection_modifyitems`、`real_api_server`、`frontend_source_hash`、`_redact` 分支均低于 minor 阈值。
    - AC-001 的构建新鲜度检查仍只在 `CBROWSER_E2E_REQUIRED=1` 时执行（`tests/e2e/conftest.py:42-50`）；若「前端 E2E 在构建产物不一致时拒绝运行」不限定必需模式，普通本地前端 E2E 仍不校验陈旧 dist。
    - `tests/e2e/test_runtime_coordinator_e2e.py:180` 的 uvicorn 仍绑定 `0.0.0.0`（anchor 前已存在，容器需经 `host.docker.internal` 访问），与 AC-004「测试服务只绑定回环」字面有张力，本轮不单列 finding。
    - `tests/e2e/test_supervisor_ipv6_policy_e2e.py:151-156` 在 `client.close()` 之后用同一 Docker client 做零泄漏查询，属健壮性风险（requests session close 后通常可重建连接），本轮不单列 finding。
    - `scripts/run_gates.sh:19` 的契约步骤使用裸 `pytest`，其余步骤用 `uv run`；无全局 pytest 的干净环境会在第一步失败。
    - `python3 .repo_template/scripts/md_format.py --check` 仍 exit 1，命中历史 `docs/reviews/` 快照与两份 task review 报告（历史状态 + reviewer 产物，非本 task 实现可改）。
    - `tests/e2e/test_frontend_app_e2e.py:864-867` 冻结恢复后只读一次统计再断言增长，未像 session E2E 那样轮询，存在偶发假红风险。
    - `docs/blueprint/testing.md:147,153` 仍称 `src/frontend/tsconfig.tsbuildinfo` 已入库，但该文件当前未跟踪且被 `.gitignore:57` 忽略；属 anchor 前既有文档状态，非本 task diff 引入。
    - 本地实跑：`scripts/run_gates.sh` 非 E2E 全绿（contract 169、legacy/unit/integration/frontend 全绿）；`pytest tests/e2e/test_frontend_build_wiring.py -q` 8 passed；`pytest tests/unit/test_repo_hygiene.py tests/unit/test_frontend_build_freshness.py -q` 3 passed；`python3 scripts/verify_frontend_dist.py --check-freshness` exit 0；`git diff --check` exit 0；ruff F821 清零。完整 Docker E2E 未执行（缺镜像/Chrome 前置）。
- 总体判断：AC-002/003/004/005/006 已打勾但仍有未解决 blocker（f002/f005/f016/f018/f019/f025），当前树不能 PASS。
- 系统性 follow-up：无新增跨 task 缺口；阻断项均属 t018 收尾范围。历史 review 快照归档仍沿用 `archive_historical_reviews_home_paths` 建议。

### AC 复验方式

- AC-001：`re_verified`。实跑 required 模式 collection（exit 2 列出 9 个缺项，含 `CBROWSER_INVALID_POLICY_TEST_IMAGE`）；实跑 `python3 scripts/verify_frontend_dist.py --check-freshness` exit 0；`tests/e2e/test_frontend_build_wiring.py` 8 passed。非 required 模式不校验新鲜度的残余见未进表提示。
- AC-002：`re_verified`。核对 `tests/conftest.py` 的 `sys.path.insert`、3 处跨测试模块 fixture 导入与 `test_baseline_fixture_regressions.py` 的 importlib 加载仍在；生产 Gateway 替身文件（`gateway_fixture.py`、`gateway_container.py`、`gateway_runtime.Dockerfile`）已删除，Supervisor 集成/恢复 E2E 驱动 `ProductionGatewayService`。
- AC-003：`re_verified`。核对首帧/输入延迟上限、冻结帧增长、IPv6 无条件下阻断、退避上下限、关闭页面后容器 running 且实例不变；f005 的两处 `finally` 清理异常仍在；完整 Docker E2E 未执行。
- AC-004：`trust_prior`。本轮未跑真实 Docker 门禁（缺镜像/Chrome 前置），依赖实施侧环境与静态检查；静态核对端口派生、秘密权限（0600）、证据脱敏与回环绑定，发现 f025 的固定端口。建议合并前人工抽查该项。
- AC-005：`re_verified`。grep 确认 `tests/unit` 仍有 116 行私有属性访问与固定 sleep；`test_stream_capture_policy.py` 已部分改为公开接口与注入时钟，f018 仍开放。
- AC-006：`re_verified`。实跑 `scripts/run_gates.sh` 非 E2E 全绿；`.github/workflows/`（含 `ci.yml`、`release.yml`）已删除；required 模式 collection 证明 E2E 必需模式生效；f019 的 testing.md 多入口残余仍在。真实 E2E 全量未执行。
- AC-007：`re_verified`。`pytest tests/unit/test_repo_hygiene.py tests/unit/test_frontend_build_freshness.py -q` 3 passed；`git check-ignore` 命中归档秘密；`git ls-files --eol` 无 CRLF；vendor 解包穿越拒绝/清单集合校验静态核对；spec 凭据字面量已抽象化。

coverage = 6 / 7

verdict: FAIL

## Round 7 (2026-11-03T13:47:27+08:00)

reviewed_scope: 67b51ace6478e8ad

### 前轮 finding 复核

- `t018_code_f001`：已消除。`tests/e2e/conftest.py:19-29` 的 `REQUIRED_E2E_ENV` 含 9 个变量；实跑 `CBROWSER_E2E_REQUIRED=1 ... pytest tests/e2e --collect-only` 以 exit 2 列出 9 个缺项，含 `CBROWSER_INVALID_POLICY_TEST_IMAGE`。
- `t018_code_f002`：仍存在。`tests/unit/test_baseline_fixture_regressions.py:1126-1140` 仍用 `importlib.util.spec_from_file_location` 加载 `tests/e2e/test_supervisor_recovery_e2e.py` 并直接驱动其 `real_api_and_sup` fixture；`tests/e2e/test_supervisor_recovery_e2e.py:92` 的 fixture 未移入 conftest。AC-002「不存在跨测试模块的 fixture 借用」不成立。`tests/conftest.py` 的 `sys.path.insert` 已删除，`pyproject.toml` 的 `pythonpath` 替代了该注入。
- `t018_code_f003`：已消除。`tests/e2e/test_frontend_app_e2e.py:631` 断言 `first_frame_ms <= 8000`，`:687` 断言 `input_latency_ms <= 3000`。
- `t018_code_f004`：已消除。`tests/e2e/test_frontend_app_e2e.py:867` 断言恢复后 `framesDecoded` 大于冻结前值；`test_frontend_session_e2e.py:432-450` 使用增长轮询。app E2E 仍为单次读取，见未进表提示。
- `t018_code_f005`：已消除。`tests/e2e/test_runtime_coordinator_e2e.py:488-490`、`tests/e2e/test_supervisor_recovery_e2e.py:1067-1070`、`tests/e2e/test_supervisor_container_graph_e2e.py:675-681` 的清理异常与所有权断言已移出 `finally`，主体先失败时原始异常不再被替换。
- `t018_code_f006`：已消除。`scripts/run_gates.sh:38-43` 含 E2E 依赖；本轮实跑 `scripts/run_gates.sh` 非 E2E 全绿（EXIT=0）。
- `t018_code_f007`：已消除。`git check-ignore -v docs/archive/spikes/s006_gateway_media_recovery/code/probe/agent_token.secret` 命中 `.gitignore:63`。
- `t018_code_f008`：已消除。`scripts/verify_frontend_dist.py:83` 默认 `check_freshness=False`，`config/docker/Dockerfile:18` 未传该开关。
- `t018_code_f009`：已消除。`tests/unit/test_repo_hygiene.py:26-34` 只跳过 `docs/archive/` 与逐文件 allowlist，`docs/reviews` 其余文件受扫描。
- `t018_code_f010`：已消除。`tests/fixtures/supervisor_recovery_probe/gateway_service.py:165-168` 的 `stop()` 先 `await self.api.close()`。
- `t018_code_f011`：仍存在（minor）。`uv run --with ruff ruff check --select F401,F811,F821,F841 tests scripts` 仍命中本 task 触及文件：`tests/e2e/test_stream_x11_keymap_e2e.py:4,9`、`tests/e2e/test_supervisor_resource_capacity_e2e.py:3,8`、`tests/e2e/test_supervisor_resource_monitor_e2e.py:5`、`tests/integration/test_gateway_control.py:6`、`tests/integration/test_gateway_signaling.py:5`、`tests/integration/test_runtime_coordinator_integration.py:8,11`、`tests/integration/test_supervisor_rpc.py:3,5,7,8`、`tests/integration/test_v2_api_subprocess.py:6`。`tests/e2e/test_frontend_session_vendor.py:8` 的「Ensure repo root is on sys.path」过期注释仍在；`tests/fixtures/frontend_probe/harness.py:12` 的 `FIXTURES_DIR` 已无消费者。
- `t018_code_f012`：已消除。`tests/unit/review_privacy_allowlist.txt` 覆盖历史文件与两份 task review 报告；实跑 `pytest tests/unit/test_repo_hygiene.py tests/unit/test_frontend_build_freshness.py -q` 3 passed。
- `t018_code_f013`：已消除。`tests/e2e/test_supervisor_event_shutdown_e2e.py:20` 定义 `REPO_ROOT`；ruff F821 清零。
- `t018_code_f014`：已消除。`tests/e2e/test_stream_runtime_e2e.py:12` 已 `import socket`；ruff F821 清零。
- `t018_code_f015`：仍存在（minor）。`docs/blueprint/stream_runtime.md:49` 仍把已删除的 `tests/e2e/test_stream_client_identity_e2e.py` 列为身份/重连覆盖来源；`docs/blueprint/testing.md` 的对应命令已收敛。
- `t018_code_f016`：仍存在。`tests/e2e/conftest.py:19-29` 的 `REQUIRED_E2E_ENV` 与 `tests/fixtures/e2e_env.py:11-26` 的 `require_e2e_env` 是两套定义；`tests/e2e/test_supervisor_event_shutdown_e2e.py:49-59`、`tests/e2e/test_frontend_display_apply_e2e.py:281`、`tests/e2e/test_stream_runtime_e2e.py:37-39` 仍各自读取/断言镜像变量，`tests/e2e/test_runtime_profile_defaults_e2e.py:442` 仍在必需模式下 `pytest.skip`。AC-002「测试前置条件由单一模块定义且语义一致」不成立。
- `t018_code_f017`：同意撤回。AC-004 的「同一台机器上并行两次运行互不干扰」已由用户删除；本报告不再按并行前提判定 `_free_tcp_port`/`_free_udp_port` 的探测即释放竞态。
- `t018_code_f018`：已消除（断言层）。`tests/unit/test_stream_capture_policy.py`、`test_supervisor_recovery_coordinator.py`、`test_stream_agent_lifecycle.py`、`test_runtime_agent_faults.py` 已改用公开访问器/注入时钟；`core.get_session`、`terminal_observation_acknowledged` 等公开接口已落地。残余私有读取只在轮询条件或测试 setup 中（`test_stream_resume.py:150,209`、`test_runtime_coordinator_background_tasks.py:49`、`test_runtime_coordinator_stop_paths.py:221`、`test_supervisor_startup_recovery.py:49-54`），见未进表提示。
- `t018_code_f019`：已消除。`docs/blueprint/testing.md:40-55` 的 `test_cmd`/`blackbox_verify` 只引用 `scripts/run_gates.sh` 与模板契约标记行，各阶段章节也只保留统一入口。
- `t018_code_f020`：已消除。`scripts/run_gates.sh:5-15` 记录 `CLEAN_SCRATCH` 并在 EXIT trap 清理自建目录。
- `t018_code_f021`：仍存在（minor）。`docs/specs/runtime_persistence.md:90` 仍为「严禁泄漏注入的注入的密码……」。
- `t018_code_f022`：已消除。`docs/blueprint/testing.md:45` 恢复模板契约命令；实跑 contract 169 passed，`scripts/run_gates.sh` 全绿。
- `t018_code_f023`：已消除。`git diff --check 5a3da225... -- . ':(exclude)docs/archive/**'` exit 0。
- `t018_code_f024`：仍存在（minor）。`scripts/verify_frontend_dist.py:30-36` 的 `frontend_source_hash` 候选仍缺 `src/frontend/postcss.config.js`。
- `t018_code_f025`：仍存在。`tests/e2e/test_supervisor_offline_recovery_e2e.py:145` 与 `tests/e2e/test_supervisor_retry_e2e.py:167` 的 `RealSupervisorContainer` 仍未传 `udp_mux_min_port/max_port`，沿用 `tests/fixtures/supervisor_recovery_probe/offline_fixture.py:342-343` 的默认 30000-30991；宿主已有服务占用 30000 时单次门禁仍会冲突。其余 Supervisor E2E 已改为运行内空闲范围，但该范围本身越界，见 `t018_code_f027`。
- `t018_code_f026`：仍存在（minor）。`docs/blueprint/testing.md:90-91` 仍写「在上述 test_cmd 已设置的 TMPDIR / UV_CACHE_DIR 下」「test_cmd 中 `tests/unit`……blackbox_verify 中 `tests/integration`」，对应章节已无这些命令。

### 本轮新发现

#### t018_code_f027 - free_udp_port_span 返回超出协议允许范围的端口，四个 Supervisor E2E 在创建 Stream 容器时必失败

- 严重度：important
- 锚点：AC-004「端口……按运行派生或由系统分配」+ AC-006「本地全量门禁可执行」；行为缺陷：`NetworkPolicySpec` 校验拒绝
- 位置：`tests/fixtures/e2e_env.py:29-42`、`tests/e2e/test_supervisor_core_e2e.py:133`、`tests/e2e/test_supervisor_recovery_e2e.py:291,522,763`、`tests/e2e/test_supervisor_startup_recovery_e2e.py:182,357`、`tests/e2e/test_supervisor_policy_failure_e2e.py:113`、`src/backend/cbrowser/supervisor/network_policy.py:88`、`src/backend/cbrowser/supervisor/protocol.py:26`、`src/backend/cbrowser/stream_agent/config.py:107-108`
- 问题：`free_udp_port_span()` 默认从 `start=32000` 扫描，但所有下游校验都把 UDP mux 端口限制在 `[30000, 30991]`。实跑 `PYTHONPATH=tests/fixtures:src/backend ... free_udp_port_span(2)` 返回 `32000`；`NetworkPolicySpec(role="stream", udp_mux_port=32000)` 抛 `ValidationError: Input should be less than or equal to 30991`。`SupervisorCore.start_profile` → `DockerAdapter.start_stream_container` → `_install_network_policy` 会对该 policy 做同样的 `model_validate`，因此上述四个 E2E 文件在创建 Stream 容器时直接失败；`StartProfileResponse` 与 `StreamAgentConfig` 也会拒绝同一端口。最新提交新增的 `CBROWSER_UDP_MUX_MIN/MAX_PORT` 只放宽了 `PortAllocator` 的范围，没有同步协议/网络策略/Agent 校验，属于用测试辅助函数引入的确定性红灯。
- 建议：把 `free_udp_port_span()` 的默认扫描范围改为 `[30000, 30991]`（例如 `start=30000, end=30991`），并补一条单元测试断言返回的 `base` 与 `base+count-1` 都在协议允许范围内；若确实要扩大生产端口范围，则必须同时修改 `protocol.py`、`network_policy.py`、`stream_agent/config.py` 与文档，不能只改测试 helper。

#### t018_code_f028 - namespace policy E2E 仍有固定 sleep 后断言进程状态的模式

- 严重度：minor
- 锚点：AC-003「测试中不存在固定 sleep 后断言状态的模式」
- 位置：`tests/e2e/test_supervisor_namespace_policy_e2e.py:173-176,192-196,209-213,226-230,245-249`
- 问题：`time.sleep(0.3); assert proc.poll() is None`、`time.sleep(0.1)` 后写 marker 再断言 gate 行为，仍是固定等待后读取状态；同 task 其他文件已用 `wait_until`/`poll_until` 或显式注释说明负断言采样窗口，本文件既无有界轮询也无注释。该模式在慢机器上可能把“gate 尚未退出”误判为“gate 接受了非法 marker”。
- 建议：对负断言保留固定采样窗口时补注释说明其必要性，或改为在可控事件（子进程输出/文件出现）上做有界等待；至少不要无说明地 `sleep` 后直接断言。

#### t018_code_f029 - 连续两次探测空闲 TCP 端口可能返回同一端口

- 严重度：minor
- 锚点：AC-004「单次门禁运行不与宿主已有资源冲突」
- 位置：`tests/e2e/test_stream_runtime_e2e.py:44-48,568-569`、`tests/e2e/test_runtime_coordinator_e2e.py:33-37,97-98`
- 问题：`_free_tcp_port()`/`find_free_port()` 绑定 `0` 后立即关闭 socket；同一轮紧接着再调用一次时，操作系统可能复用同一端口，导致 Gateway 与 Stream HTTP 服务、Supervisor 与 API 宿主端口相同并在绑定阶段冲突。单次运行不涉及并行双跑，但同轮内两次调用仍是竞态。
- 建议：一次调用分配多个端口并保持监听 socket 到服务启动，或对重复端口做重试；至少在返回前确认两个端口不同。

#### t018_code_f030 - run_gates.sh 第一步依赖未声明的全局 pytest

- 严重度：minor
- 锚点：AC-006「本地全量门禁由单一入口脚本执行」
- 位置：`scripts/run_gates.sh:19`
- 问题：契约步骤使用裸 `pytest`，其余步骤用 `uv run --no-project`；`pyproject.toml` 没有把 pytest 声明为运行依赖。干净环境/仅安装项目依赖的机器会在第一步 `pytest: command not found` 失败，无法作为可复现的单一入口。
- 建议：第一步同样使用 `uv run --no-project --with pytest python -m pytest .repo_template/tests -q -m contract`，保留模板契约命令语义即可。

### 结论

- 前轮 finding 复核汇总：`f001/f003/f004/f005/f006/f007/f008/f009/f010/f012/f013/f014/f019/f020/f022/f023` 已消除；`f002/f016/f025` 仍为 important；`f011/f015/f021/f024/f026` 仍为 minor；`f017` 同意撤回；`f018` 断言层已消除，残余私有读取仅作提示。
- 本轮新发现：4 条（1 important + 3 minor）。
- 未进表的提示：
    - 文件过大：`tests/e2e/test_stream_runtime_e2e.py` 1681 行、`tests/unit/test_baseline_fixture_regressions.py` 1270 行、`tests/e2e/test_frontend_app_e2e.py` 1216 行，均超测试源码 1200 行阈值；`tests/e2e/test_supervisor_recovery_e2e.py` 1075 行、`tests/e2e/test_frontend_media_e2e.py` 948 行、`tests/unit/test_stream_agent_lifecycle.py` 713 行、`tests/e2e/test_supervisor_container_graph_e2e.py` 679 行超 600 行提示线。按规则只提示。
    - 复杂度：本轮人工扫描新增/修改函数未发现 CC ≥ 15；`free_udp_port_span`、`_redact`、`pytest_collection_modifyitems` 分支均低于 minor 阈值。
    - AC-001 的前端新鲜度检查仍只在 `CBROWSER_E2E_REQUIRED=1` 时执行（`tests/e2e/conftest.py:41-50`）；普通本地前端 E2E 不校验陈旧 dist。
    - `tests/e2e/test_frontend_app_e2e.py:864-867` 冻结恢复后只读一次统计再断言增长，未像 session E2E 那样轮询，存在偶发假红风险。
    - `tests/e2e/test_supervisor_core_e2e.py:289-295` 在 `d_client.close()` 之后用同一 Docker client 做零泄漏查询；docker-py 7.2 可继续发请求，但属脆弱写法。
    - `src/backend/cbrowser/supervisor/runner.py:108-111` 新增 `CBROWSER_UDP_MUX_MIN/MAX_PORT` 生产行为开关；note 有记录，但非范围只允许“为可观测性新增公开接口”，该开关不是可观测性接口，建议后续在 blueprint/decisions 或 spec 中明确其测试专用语义。
    - `tests/e2e/test_runtime_profile_defaults_e2e.py:439-442` 仍在必需模式下 `pytest.skip`，且默认镜像/缓存路径指向 `.scratch`；该文件不在本 task diff，属既有测试前置条件缺口。
    - `python3 .repo_template/scripts/md_format.py --check` 仍 exit 1，命中历史 `docs/reviews/` 快照；历史文件属既有状态，非本 task 实现可改。
    - 本地实跑：`scripts/run_gates.sh` 非 E2E 全绿（contract 169、legacy 384、unit 540、integration 79、frontend Vitest 95 + build）；required 模式 collection exit 2 列出 9 个缺项；`python3 scripts/verify_frontend_dist.py --check-freshness` exit 0；`git diff --check` exit 0；ruff F821 清零。完整 Docker E2E 未执行（缺镜像/Chrome 前置），`t018_code_f027` 为静态+最小复现证据。
- 总体判断：AC-004 的新端口隔离实现把四个 E2E 直接推入确定性失败（f027），且 AC-002 的 fixture 借用/前置条件单一来源（f002/f016）与离线/重试 E2E 固定端口（f025）仍未解决；当前树不能 PASS。
- 系统性 follow-up：无新增跨 task 缺口；`f027` 的端口范围修复属 t018 收尾范围。历史 review 快照归档仍沿用 `archive_historical_reviews_home_paths` 建议。

### AC 复验方式

- AC-001：`re_verified`。实跑 required 模式 collection（exit 2 列出 9 个缺项，含 `CBROWSER_INVALID_POLICY_TEST_IMAGE`）；`python3 scripts/verify_frontend_dist.py --check-freshness` exit 0；`scripts/run_gates.sh` 中前端 build/verify 通过。非 required 模式不校验新鲜度的残余见未进表提示。
- AC-002：`re_verified`。grep/ruff 确认 `tests/conftest.py` 的 `sys.path.insert` 已删除，但 `test_baseline_fixture_regressions.py` 仍 importlib 借用 E2E fixture，且前置条件仍有两套定义；f002/f016 开放。
- AC-003：`re_verified`（代码层）。核对首帧/输入延迟上限、冻结帧增长、IPv6 无条件下阻断、退避上下限、关闭页面后容器 running 且实例不变；f005 已消除；f028 的固定 sleep 负断言仍在；完整 Docker E2E 未执行。
- AC-004：`trust_prior`。本轮未跑真实 Docker 门禁（缺镜像/Chrome 前置），依赖实施侧环境与静态检查；静态核对秘密权限、证据脱敏与回环绑定，复现 f027 的端口越界与 f025 的固定端口。建议合并前人工抽查该项。
- AC-005：`re_verified`。实跑 `scripts/run_gates.sh` 的 unit 层 540 passed；grep 确认断言已改用公开访问器/注入时钟，残余私有读取仅在轮询与 setup；f018 按断言层视为已消除。
- AC-006：`re_verified`（本地非 E2E）。`scripts/run_gates.sh` EXIT=0，`.github/workflows/` 已删除，required 模式生效；完整 E2E 未执行，f030 的裸 pytest 与 f027 的端口越界仍影响入口可复现性。
- AC-007：`re_verified`。`pytest tests/unit/test_repo_hygiene.py tests/unit/test_frontend_build_freshness.py -q` 3 passed；`git check-ignore` 命中归档秘密；`git ls-files --eol` 无 CRLF；vendor 解包穿越拒绝/清单集合校验静态核对；spec 凭据字面量已抽象化。

coverage = 6 / 7

verdict: FAIL
