# Task review t054（reviewer_focus: 测试）

- task：`t054_deploy_time_network_config`
- spec：`docs/tasks/t054_deploy_time_network_config/task.md`
- diff_anchor：`e9320341a8b5c93d136fca64b1aad25825ec2898`
- target：`git -C '<home>/workspace/CBrowser_t054' diff e9320341a8b5c93d136fca64b1aad25825ec2898`
- round：1
- reviewed_at：2026-11-11T19:31:42+08:00

## Round 1 (2026-11-11T19:31:42+08:00)

### 审阅输入说明

- 仓库落点校验通过：`git rev-parse --show-toplevel` == `<home>/workspace/CBrowser_t054`。
- 11 个新交付文件派审前未执行 `git add -N`，不在 `git diff e932034` 输出中（`scripts/check_edge_subnet.py`、`src/backend/cbrowser/shared/__init__.py`、`src/backend/migrations/versions/0008_drop_network_transaction.py`、8 个 `test_t054_*` 测试文件）；本审阅直接读盘核查全部 11 个文件，并以范围指纹验证内容自派发后未变（见结论段）。`git status` 另有 `review_code.md`（代码路报告，流程文件，不计入指纹）。
- 独立实跑（验证 venv `~/workspace/.cb-venv-t051/bin/python`，`PYTHONPATH=src/backend:tests`；前端 Node 26.13.0）：
  - 新 t054 测试集（8 文件）：**38 passed**。
  - 改写相关套件（a24、t027、auth_api、a4_viewer_throttle、auth_client_ip、a4_control_plane、auth_service、control_migration、gateway_config、network_policy、a10、a6、t035、a16、a28、refactor_behavior_equivalence、gateway_endpoint、docker_build_contexts、baseline_fixture_regressions、stream_ice_config、stream_clipboard_policy、selkies_file_transfers）：**244 passed**。
  - 前端全量：**538 passed / 0 failed**（74 个测试文件）。
  - 后端全量（`tests/unit` + `tests/integration`）：**2014 passed / 25 failed / 8 skipped / 0 errors**；25 个失败名与实施方第二轮日志逐名完全一致，且全部属于既有环境相关组（agent_executor_chain 7、t028 4、normal_exit_replay 4、automation_probe_chain 3、t034 2、automation_cdp_flow 2、repo_hygiene 1、automation_cdp 1、control_attendant_chain 1），无一在 t054 改动文件内；其中 `test_repo_hygiene.py::test_tracked_files_do_not_leak_developer_home_paths` 的违规项经单跑核实全部来自 t051–t053 的旧 review 文件，零 t054 文件。
- 命名锁死核查通过：`com.cbrowser.deployment-id` 全仓零命中；编译内默认前缀 `cbrowser-t005`（`src/backend/cbrowser/supervisor/docker_adapter.py:234`、`runner.py:60/585`）未动；deploy.sh/compose 的 `${CBROWSER_PREFIX:-cbrowser}` 为 t051 已登记的不对称（A22 校验只作用部署输入），非本次偏离。

## Findings

### t054_test_f001 - edge 子网冲突预检与显式子网出路零行为覆盖

- 严重度：important
- 锚点：spec「风险与回退」——“edge 固定子网与宿主已有网络冲突；deploy.sh 预检子网冲突并给出可执行提示”；范围“deploy.sh 推导并注入 `CBROWSER_TRUSTED_PROXY_CIDRS`”（AC-009 的可信代理接线）
- 位置：`scripts/deploy.sh:149`（`derive_instance_identity` 无条件覆盖）、`scripts/deploy.sh:174-178`（冲突提示）、`tests/unit/test_t054_compose_deploy_structure.py:112-116`、`tests/unit/test_t027_release_controller.py:172-183`（fake `network` 分支无人调用）、`scripts/check_edge_subnet.py`（全文件零单测）
- 问题：三点可验证的事实。第一，`derive_instance_identity` 第 3 行输出无条件写入 `CBROWSER_EDGE_SUBNET`（`deploy.sh:149`），调用方显式传入的 `CBROWSER_EDGE_SUBNET` 环境值被丢弃。第二，`check_edge_subnet_conflict` 的拒绝文案明确指示用户“set an explicit CBROWSER_EDGE_SUBNET”（`deploy.sh:178`），该出路实际失效：用户按提示操作后仍得同一冲突拒绝，陷入死循环——这是已发生的真实缺陷（代码路 f001 同根），不是假设。第三，测试侧对整条冲突处理行为零行为覆盖：t027 的 fake docker 已备好 `network ls/inspect` 分支（`FAKE_NETWORK_IDS` / `FAKE_NETWORK_SUBNETS`，`test_t027_release_controller.py:172-183`），但全仓无任何测试设置这两个变量；唯一相关测试 `test_deploy_prechecks_edge_subnet_conflicts` 只断言 deploy.sh 文本含 `"check_edge_subnet_conflict"` 与 `"CBROWSER_EDGE_SUBNET"`（`test_t054_compose_deploy_structure.py:112-116`），文本存在不等于行为正确；`scripts/check_edge_subnet.py` 本身（重叠判定、Docker 枚举失败 fail-closed、macOS/Linux 接口解析）零单测。若存在“显式子网部署成功且 release env/manifest 记录该子网”的行为测试，该缺陷在实现期就应变红。
- 建议：t027 增加两例 fake-docker 行为测试：(a) `FAKE_NETWORK_SUBNETS` 含与派生 edge 子网重叠的子网 → deploy 被拒、无 release 记录、stderr 含可执行提示；(b) 显式 `CBROWSER_EDGE_SUBNET=172.25.0.0/16`（与派生值不同且无冲突）→ deploy 成功，release env 与 manifest 的 `edge_subnet` / `CBROWSER_TRUSTED_PROXY_CIDRS` 均为显式值；`check_edge_subnet.py` 补单测（重叠 / 不重叠 / 枚举失败 exit 2）。

### t054_test_f002 - 回退端口一致性缺判别测试

- 严重度：minor
- 锚点：AC-006——“rollback 后 Caddy 绑定的端口与目标 release 记录一致”
- 位置：`tests/unit/test_t027_release_controller.py:505-513`（`test_rollback_success_redeploys_previous_and_verifies`）、`:567-586`（`test_rollback_adopts_target_release_identity`）、`scripts/deploy.sh:881-890`（回退重渲染 + sha 校验）
- 问题：全部回退测试都在同一端口部署两次（rel-001/rel-002 均默认 56661；b-001/b-002 均 56662），无法区分“按目标端口重渲染”与“沿用当前端口”：若 `load_release_identity` 取错端口，sha 校验会在端口不同时拒绝，但在现有测试里 current == target，校验恒过；sha 不符拒绝分支（`deploy.sh:889-890`）零测试。注：sha 校验 fail-closed，错端口只会导致误拒、不会静默错服，故为覆盖缺口而非静默错误行为，定 minor。
- 建议：补一例：rel-001 用 56661 部署、rel-002 用 56662 部署、rollback → 成功且 `DATA_ROOT/network/Caddyfile` 首行含 56661、`CBROWSER_CADDYFILE_SHA256` 等于目标 manifest 值；再补一例：篡改目标 manifest `caddyfile_sha256` → rollback 被拒且磁盘/指针不动。

### t054_test_f003 - 共享 client_ip 两条防御分支失去唯一执行覆盖

- 严重度：minor
- 锚点：AC-009——“API 与 Gateway 使用同一 client_ip 解析实现；不在可信 CIDR 内的对端发送的 XFF 不被采信”
- 位置：`src/backend/cbrowser/shared/client_ip.py:44`（`return "unknown"`）、`:53`（畸形 XFF hop 的 `except ValueError: continue`）；`tests/unit/test_a4_viewer_throttle.py` 被删的 `test_gateway_client_ip_matches_existing_auth_rules`（7 例参数化，含 `(None, "203.0.113.9", ...)` 与 `("10.0.0.1", "not-an-ip", ...)`）
- 问题：被删的双导入漂移测试是唯一执行这两条分支的测试（差分比较 gateway == auth）；新 `tests/unit/test_t054_shared_client_ip.py` 与 `tests/unit/test_auth_client_ip.py` 只覆盖有 peer + 合法 hop 的主路径；全仓 grep 确认无任何剩余测试调用 `resolve_client_ip(None, …)` 或传入畸形 hop。分支本身行为未变（逐字节搬移），故 minor。
- 建议：在 `test_t054_shared_client_ip.py` 补两例：`resolve_client_ip(None, "203.0.113.9", networks) == "unknown"`；畸形 hop 被跳过、取其余最左非可信 hop。

### t054_test_f004 - 设置页“无网络请求”断言空转

- 严重度：minor
- 锚点：AC-002——设置页只显示当前访问地址与端口
- 位置：`src/frontend/src/features/settings/SettingsPage.network.test.tsx:83`；`src/frontend/src/features/settings/SettingsPage.tsx:45-57`
- 问题：`expect(request).not.toHaveBeenCalledWith(expect.stringContaining("/api/v1/network"), expect.anything())` 中 `request` mock 在该测试里从未被调用——SettingsPage 新版不经过 `client.request` 取数（健康走 `client.health.check`，字体集走 `client.fontSets.list`）。该断言恒真：即使页面改回走 `request` 发网络请求以外的路径，它也发现不了。AC-002 的主证据（只读展示 live `window.location` 值 + 8 个表单 testId 不存在）是实的，本条只影响补充证据的可信度，故 minor。
- 建议：断言页面实际走的数据路径被调用（`health.check` / `fontSets.list` 各至少一次），或把 `request` 断言改为对 fetch 的 spy；二选一。

## 结论

- 前轮 finding 复核：无（Round 1）。
- 改测方向复核：无迁就实现的改测。逐项核查：`test_a6_error_contract.py` 的 404 探针改打现存 profile 路由（原网络路由已删），断言（404 + 结构化体）不变且实测通过；`test_t035_openapi_contract.py` 的 `PUBLIC_GROUPS` 删 `'network'`（该组已按 AC-001 删除），其余组断言不变；`test_control_migration.py` 删两测试均测已删的网络事务/恢复路径（`initialize_network_from_disk`、0003 crash backfill），新 `test_t054_migration.py` 覆盖 0008 删除语义；`test_a24_deploy_network_source.py` / `test_a16_protocol_drift.py` / `test_t027_release_controller.py` / `test_gateway_config.py` 的重写均为协议/签名随 spec 变更的同义改写，且 t027 指纹测试反向加强（生成器注释不变指纹、端口变指纹变）；`test_a28_daemon_host_port.py` 由“读已应用状态文件”改为断言 Gateway 同样收到 `CBROWSER_HTTPS_PORT`（加强）；`test_refactor_behavior_equivalence.py` 新增 `CBROWSER_WEBRTC_PUBLIC_IP == "127.0.0.1"` 断言（加强）；`test_a10_stream_egress.py` / `test_network_policy.py` 的 LAN 参数化去除与字段删除一致，并新增 `allow_lan_media` 拒绝测试。
- 本轮新发现：4 条（1 important + 3 minor）。
- 未进表的提示：
  - 派审程序缺口：11 个新交付文件派审前未执行 `git add -N`，不在 `git diff e932034` 输出中；本审阅直接读盘核查，并以范围指纹验证内容自派发后未变。建议链主在派发前补跑 `git add -N`。
  - `progress.md` 声称“前端全量 538 passed / 0 failed（77 个文件）”，实测 Test Files 74 passed（77 − 3 个整删文件）；538/0 本身与独立复跑一致，仅文件数一处笔误。
  - `tests/unit/test_network_policy.py:240` 的 `# type: ignore[call-arg]` 已调查：单行定点抑制，测试目的正是传入已删字段断言 `ValidationError` 拒绝，不属静默错误；放行。（同文件 `:56` 的同类抑制为基线既有。）
  - AC-005 字面量扫描范围（`.env.example` 与文档示例值除外）与实施记录口径一致；全仓复核剩余 `56661` 命中均为文档/归档/示例值，无代码定义点遗漏。
  - e2e 夹具 `tests/fixtures/gateway_probe/topology.py` 用 `DEFAULT_HTTPS_PORT` 渲染 Caddyfile 而 Gateway 取动态宿主端口：端口只出现在 Caddyfile 首行注释，served 行为不受影响，仅夹具注释值与宿主端口不一致，无测试意义。
  - t045 wheel 缓存为 gitignored 的 `.scratch` 内容（实施方已 out-of-band 补齐），worktree 重建后需重补，否则该 2 测试复失败；与本次改动无关。
  - 引用逐项核对：本报告引用的文件、行号、提交均已实地核对存在。
- 总体判断：测试层整体可信，回归与实施方一致，但 edge 子网冲突预检与显式子网出路零行为覆盖，已放行一个真实缺陷，需补行为测试后重审。
- 系统性 follow-up：无（四条均为本 task 内缺口，不跨 task）。

### AC 复验方式

- AC-001：TICK-VALID，re_verified。新 `test_t054_openapi_no_network.py` 对 live OpenAPI、入库导出与生成 d.ts 三处断言零 network 路径/模型；独立复跑 38 passed 含该文件。
- AC-002：TICK-VALID，re_verified。`SettingsPage.network.test.tsx` 断言只读展示 live `window.location` 值且 8 个表单 testId 不存在；前端全量独立复跑 538/0。
- AC-003：TICK-VALID，re_verified。compose 结构测试断言 Caddy 端口 `127.0.0.1:` 绑定且无通配发布；`test_refactor_behavior_equivalence.py:279` 断言 `stream_ports` 为 `{"30006/udp": ("127.0.0.1", 30006)}`；独立复跑通过。
- AC-004：TICK-VALID，re_verified。集成 `test_t054_origin_whitelist_deploy.py`：自定义端口 58888 下 API 与 Gateway 派生同一白名单，默认端口 Origin 403、部署端口 200，Gateway viewer 门 401 vs 403；独立复跑通过。
- AC-005：TICK-VALID，re_verified。`test_t054_no_default_port_literal.py` 断言全仓代码内 `56661` 字面量恰为一处（`DEFAULT_HTTPS_PORT` 定义）；独立复跑通过。
- AC-006：TICK-VALID，re_verified。t027 指纹测试：生成器追加注释后指纹不变、端口改为 56662 后指纹变化，且记录值等于渲染产物文件的 sha256；独立复跑 t027 51 passed。回退判别用例缺失记 minor f002，不影响本 AC 打勾成立。
- AC-007：TICK-VALID，re_verified。`test_t054_migration.py`：head 为 0008 单头，升级删光全部 `network.*` 行且保留无关行，删后 API 可启动；`test_gateway_config.py` 断言无 publication 方法与 `network_state_dir` 字段；独立复跑通过。
- AC-008：TICK-VALID，re_verified。`test_a4_viewer_throttle.py`（同 profile 不同来源隔离、XFF 链解析、不可信 peer 忽略伪造 XFF、十次阈值）与 `test_auth_client_ip.py`（按来源窗口与全局预算：a 锁定不影响 b）及 `test_auth_api.py` 登录限流；独立复跑通过。
- AC-009：TICK-VALID，re_verified。`test_t054_shared_client_ip.py` 断言旧双模块不存在、API 与 Gateway 的函数 `__module__` 均为共享模块、不可信 peer 的 XFF 不被采信；独立复跑通过。防御分支缺口记 minor f003。
- AC-010：TICK-VALID，trust_prior。[deploy] 真实部署，本机无 Docker/真实引擎无法独立复验；依赖实施侧替代证据：fake Docker 全流程部署（t027 51 passed，已独立复跑）、集成 Origin 测试（已独立复跑）、前端 538/0（已独立复跑）；progress.md 已写明“本机未验证、不得记为已验”，真实部署须用户机补验。

coverage = 9/10

reviewed_scope: 57822b5d09726b8e

verdict: FAIL

## Round 2 (2026-11-11T20:05:29+08:00)

### 审阅输入说明

- 仓库落点校验通过：`git rev-parse --show-toplevel` == `<home>/workspace/CBrowser_t054`。
- 本轮为 Round 1 修复复审：逐条复核 test f001–f004 是否真修（diff/代码/实跑，不采信处置表自述），并扫描修复 diff 引入的新问题。
- 独立实跑（验证 venv `~/workspace/.cb-venv-t051/bin/python`，`PYTHONPATH=src/backend:tests`；前端 Node 26.13.0，`src/frontend` 内 `npm test`）：
  - Round 1 修复相关测试（t027 新 5 例 + `test_t054_check_edge_subnet.py` 5 例 + `test_t054_shared_client_ip.py` 全文件 8 例）：**18 passed**。
  - 先红验证：把 `scripts/deploy.sh` 的 f001 修复临时回退为修前无条件覆盖（备份/恢复，`cmp` 确认字节一致还原），(b) `test_deploy_uses_explicit_edge_subnet_when_set` 与 (c) `test_deploy_refuses_when_explicit_edge_subnet_overlaps` 均变红（2 failed），修后全绿。
  - 前端全量：**538 passed / 0 failed**（74 个测试文件，含 `test:types`）。
  - 后端全量（`tests/unit` + `tests/integration`）：**2026 passed / 25 failed / 8 skipped / 0 errors**，与修复方第三轮日志逐名一致；25 个失败按组与 Round 1 基线完全一致（agent_executor_chain 7、t028 4、normal_exit_replay 4、automation_probe_chain 3、t034 2、automation_cdp_flow 2、repo_hygiene 1、automation_cdp 1、control_attendant_chain 1），无一在 t054 改动文件内。
- 命名锁死核查通过：`com.cbrowser.deployment-id` 全仓零命中；编译内默认前缀 `cbrowser-t005` 未动。

## 前轮 finding 复核

- **t054_test_f001（important）——已消除**。`scripts/deploy.sh:148-153` 改为有条件赋值（显式值保留，仅未设置时派生）；t027 三例行为测试全部通过且真实可判别：(a) 派生子网重叠即拒、无 release 记录、stderr 含可执行提示；(b) 显式 `172.40.0.0/16` 部署成功且 release env 与 manifest 均记显式值（`assert explicit != derived` 守卫防偶然通过）；(c) 显式子网重叠即拒。先红验证见上：(b)(c) 修前确为红。`tests/unit/test_t054_check_edge_subnet.py` 5 例单测（无重叠 / Docker 重叠 / 宿主接口重叠 / 枚举失败 exit 2 / 非法候选 exit 2）均通过，`subprocess.run` 伪造边界正确。
- **t054_test_f002（minor）——已消除**。t027 两例均通过且可判别：`test_rollback_restores_target_port_not_current_port`（rel-001 用 56661、rel-002 用 56662、rollback 后 Caddyfile 首行含 `https_port 56661` 且 sha 等于 rel-001 manifest 值）；`test_rollback_refuses_on_caddyfile_sha_mismatch_without_touching_disk`（篡改目标 manifest `caddyfile_sha256` 后 rollback 被拒，磁盘 Caddyfile 与指针均不动）。sha 篡改例的先红以后者代码路径推理确认（修前回退先写 live 目录再校验 sha，磁盘必被改写，与断言矛盾），未做 live 回退探针。
- **t054_test_f003（minor）——已消除**。`tests/unit/test_t054_shared_client_ip.py:86-104` 两例通过，真实执行两条防御分支：peer 为 None → `"unknown"`；畸形 XFF hop 跳过取其余最左非可信 hop、全畸形链回落 peer。
- **t054_test_f004（minor）——已消除**。`SettingsPage.network.test.tsx:45-88`：从未被调用的 `client.request` 死 mock 已删，改为注入带 spy 的 client 并断言页面实际走的数据路径 `health.check` 与 `fontSets.list` 各至少调用一次。已核实 `SettingsPage.tsx:45-57` 确实调用这两条路径（`useFontSetsQuery` + `client.health.check` 的 useEffect），断言非空转：页面若停止取数，spy 不被调用即变红。前端全量 538/0 含该文件。

## Findings

### t054_test_f005 - edge 子网冲突预检把本实例已有的 edge 网络当成冲突，二次部署与回退在真实部署中被拒

- 严重度：important
- 锚点：AC-004——“修改 `.env` 中 `CBROWSER_HTTPS_PORT` 后重新部署，新端口生效”；AC-006——“rollback 后 Caddy 绑定的端口与目标 release 记录一致”；AC-010——“修改端口重新部署后可用新端口登录”；spec「风险与回退」——“edge 固定子网与宿主已有网络冲突；deploy.sh 预检子网冲突并给出可执行提示”
- 位置：`scripts/check_edge_subnet.py`（全文件，无自有网络排除）；`scripts/deploy.sh:176-188`（`check_edge_subnet_conflict`）、`:744`（`cmd_deploy` 调用点）、`:883`（`cmd_rollback` 调用点）；`compose.yaml:175-181`（edge 网络）；`tests/unit/test_t027_release_controller.py:172-183`（fake `network ls/inspect` 分支）
- 问题：预检把候选子网与**全部**已存在的 Docker 网络子网比对，不排除本实例自己的 edge 网络；而 compose 会为本实例创建名为 `${CBROWSER_PREFIX:-cbrowser}-edge`、子网恰为候选值的网络（`compose.yaml:175-181`）。因此首次部署成功后，同一实例的任何二次部署与回退都会被预检拒绝：
  - `cmd_deploy` 在 `check_prerequisites` / `derive_instance_identity` / `check_prefix_conflict` 之后、任何 compose up/down 之前调用 `check_edge_subnet_conflict`（`deploy.sh:744`）；`deploy_up_and_verify` 是唯一的 up 步骤，在检查之后（`:777`）。同一实例二次部署时派生值（或同一显式值）与已存在的自有 edge 网络子网完全相同，`overlaps()` 为真即拒绝。
  - `cmd_rollback` 同样在 `load_release_identity`（取目标 release 记录的子网，即同一值）之后、`deploy_up_and_verify` 之前调用该检查（`:883`），部署后回退同样被拒。
  - 实测复现：用 PATH 上的 fake `docker` 只返回本实例自有网络（`[{"Name": "cbrowser-t005-edge", "IPAM": {"Config": [{"Subnet": "172.23.0.0/16"}]}}]`），真实脚本 `python3 scripts/check_edge_subnet.py 172.23.0.0/16` 退出码 1，stderr 为 `edge subnet 172.23.0.0/16 overlaps Docker network subnet 172.23.0.0/16`；随即 `deploy.sh` 以 `Refusing to start` 拒绝。提示的两条出路对二次部署无效：换 prefix/data root 意味着另一个实例；只有改一个不同的显式子网能绕过（还会遗留旧 edge 网络无人清理）。
  - 测试侧对此零覆盖且**无法覆盖**：fake docker 的 `network ls` 只返回 `FAKE_NETWORK_IDS`（外来网络），`compose up` 假实现从不登记自有 edge 网络（`test_t027_release_controller.py:172-183`）；新补的回退端口测试在同一用例里连续部署 rel-001、rel-002 均通过，恰好证明假实现没有建模自有网络。AC-004/AC-006 的机制测试（端口变更、回退重渲染）本身是真实的，但它们跑在看不见自有网络的假实现上，测不到这条真实部署路径。
- 建议：最小修复分两步。(1) 生产侧：`check_edge_subnet_conflict` / `check_edge_subnet.py` 增加排除参数，按网络名排除本实例自有 edge 网络（`${CBROWSER_PREFIX}-edge`），或按当前 release 记录的子网排除；外来网络的重叠仍拒绝。(2) 测试侧：fake docker 的 `network inspect` 返回含 `Name` 的网络记录（或新增 `FAKE_OWN_EDGE_SUBNET` 变量），补两例：同一实例连续部署两次成功（第二次不被自有网络拒绝）、部署后 rollback 成功；并补一例：自有网络存在时外来网络重叠仍被拒。

## 结论

- 前轮 finding 复核：f001/f002/f003/f004 全部已消除（逐条见上，diff/代码/实跑核实，不采信处置表自述）。
- 改测方向复核：无迁就实现的改测。修复 diff 只新增测试与替换一条空转断言为真实断言（f004，加强）；未弱化任何既有断言。新增行危险模式扫描干净：唯一 `# type: ignore[call-arg]` 是 Round 1 已调查放行的 `test_network_policy.py:240`（单行定点抑制，测试目的正是传入已删字段断言拒绝）。
- 本轮新发现：1 条（important，f005）。
- 未进表的提示：
  - 直接在仓库根执行 `npx vitest run <单文件>` 会因未加载 `src/frontend/vitest.config.ts`（jsdom 环境）导致 `localStorage` 未定义而失败，是我的调用方式问题，不是测试缺陷；正确调用为 `src/frontend` 内 `npm test`（已通过，538/0）。
  - `progress.md` 笔误已修正：前端全量 74 个文件（538 passed / 0 failed 不变），与独立复跑一致；处置表 6 行标准五列格式齐全。
  - 后端全量 25 个失败与 Round 1 基线逐名一致；其中 `test_repo_hygiene.py::test_tracked_files_do_not_leak_developer_home_paths` 的违规项 Round 1 已核实全部来自 t051–t053 旧 review 文件，零 t054 文件。
  - t045 wheel 缓存仍为 gitignored 的 `.scratch` 内容，worktree 重建后需重补（与本次改动无关）。
  - 引用逐项核对：本报告引用的文件、行号、提交均已实地核对存在。
- 总体判断：Round 1 的四条 finding 均已真实修复，但新发现的 f005 表明 edge 子网预检在真实部署中会拒绝一切二次部署与回退——AC-004/AC-006/AC-010 的重部署场景在真实环境不可行，且现有测试因假实现看不见自有网络而无法发现；须修复并补测试后重审。
- 系统性 follow-up：无（f005 为本 task 内缺口，不跨 task）。

### AC 复验方式

- AC-001：TICK-VALID，re_verified。新 `test_t054_openapi_no_network.py` 对 live OpenAPI、入库导出与生成 d.ts 三处断言零 network 路径/模型；独立复跑通过。
- AC-002：TICK-VALID，re_verified。`SettingsPage.network.test.tsx` 断言只读展示 live `window.location` 值且 8 个表单 testId 不存在，数据路径断言已由 f004 修复为真实调用；前端全量独立复跑 538/0。
- AC-003：TICK-VALID，re_verified。compose 结构测试断言 Caddy 端口 `127.0.0.1:` 绑定且无通配发布；`test_refactor_behavior_equivalence.py:279` 断言 `stream_ports` 为 `{"30006/udp": ("127.0.0.1", 30006)}`；独立复跑通过。
- AC-004：TICK-VOID，re_verified。端口变更机制测试本身是真实的，但真实部署中二次部署会被 edge 子网预检拒绝（f005：自有 edge 网络已存在时 `check_edge_subnet_conflict` 退出 1），“修改端口后重新部署，新端口生效”在真实环境不可行；假实现看不见自有网络，测试证据不足以支撑打勾。
- AC-005：TICK-VALID，re_verified。`test_t054_no_default_port_literal.py` 断言全仓代码内 `56661` 字面量恰为一处（`DEFAULT_HTTPS_PORT` 定义）；独立复跑通过。
- AC-006：TICK-VOID，re_verified。指纹随端口变化与回退重渲染机制测试是真实的，但真实部署中回退会被 edge 子网预检拒绝（f005：目标 release 记录的子网与已存在的自有 edge 网络相同），“rollback 后 Caddy 绑定的端口与目标 release 记录一致”在真实环境不可行；测试证据不足以支撑打勾。
- AC-007：TICK-VALID，re_verified。`test_t054_migration.py`：head 为 0008 单头，升级删光全部 `network.*` 行且保留无关行，删后 API 可启动；`test_gateway_config.py` 断言无 publication 方法与 `network_state_dir` 字段；独立复跑通过。
- AC-008：TICK-VALID，re_verified。`test_a4_viewer_throttle.py`（同 profile 不同来源隔离、XFF 链解析、不可信 peer 忽略伪造 XFF、十次阈值）与 `test_auth_client_ip.py`（按来源窗口与全局预算：a 锁定不影响 b）及 `test_auth_api.py` 登录限流；独立复跑通过。
- AC-009：TICK-VALID，re_verified。`test_t054_shared_client_ip.py` 断言旧双模块不存在、API 与 Gateway 的函数 `__module__` 均为共享模块、不可信 peer 的 XFF 不被采信，防御分支覆盖已由 f003 补齐；独立复跑通过。
- AC-010：TICK-VOID，trust_prior。[deploy] 真实部署，本机无 Docker/真实引擎无法独立复验；依赖的替代证据中重部署一节被 f005 证伪——“修改端口重新部署后可用新端口登录”在真实环境会被预检拒绝，且无真实部署证据；须用户机补验前先修 f005。

coverage = 7/10

reviewed_scope: 6842bf304600a6d0

verdict: FAIL

## Round 3 (2026-11-11T20:40:48+08:00)

### 审阅输入说明

- 仓库落点校验通过：`git rev-parse --show-toplevel` == `<home>/workspace/CBrowser_t054`。
- 本轮为 Round 2 修复复审：逐条复核 test f005 是否真修（diff/代码/实跑，不采信处置表自述），复核 Round 1 的 f001–f004 是否仍消除，并扫描 f005 修复 diff 引入的新问题。
- 独立实跑（验证 venv `~/workspace/.cb-venv-t051/bin/python`，`PYTHONPATH=src/backend:tests`；前端 Node 26.13.0，`src/frontend` 内 `npm test`）：
  - f005 相关测试（t027 全文件 59 例 + `test_t054_check_edge_subnet.py` 9 例 + `test_t054_shared_client_ip.py` 8 例）：**76 passed**。
  - 脚本级探针：按 Round 2 审阅者原场景复现（PATH 上 fake `docker` 只返回本实例自有网络 `cbrowser-t005-edge` / `172.23.0.0/16`）——不带 flag 的真实脚本 exit 1（修前行为，stderr 为 `edge subnet 172.23.0.0/16 overlaps Docker network subnet 172.23.0.0/16`）；带 `--exclude-network cbrowser-t005-edge` 时 exit 0；带不匹配的排除名时 exit 1。
  - 部署级回退探针：临时去掉 `deploy.sh` 的 `--exclude-network "$PREFIX-edge"` 参数（事后 `cp` 还原，sha256 校验与探针前完全一致 `d84123390e99219006af3eee0fdacef139163dcf7ed1570c97aa47ccf3b4613f`），t027 新 3 例中 (a) 连续部署与 (b) 部署后回退均变红（2 failed），(c) 外来重叠仍拒保持绿；恢复后 3 例复绿。
  - 前端全量：**538 passed / 0 failed**（74 个测试文件，含 `test:types`；两次运行一致，第一次的 `tail -6` 截掉汇总行后重跑取数）。
  - 后端全量（`tests/unit` + `tests/integration`）：**2033 passed / 25 failed / 8 skipped / 0 errors**，与修复方第四轮日志总数一致；25 个失败另以失败文件子集重跑逐名核对，与修复方日志 `FAILED` 行逐行完全相同（agent_executor_chain 7、t028 4、normal_exit_replay 4、automation_probe_chain 3、t034 2、automation_cdp_flow 2、repo_hygiene 1、automation_cdp 1、control_attendant_chain 1），无一在 t054 改动文件内。
- 命名锁死核查通过：`com.cbrowser.deployment-id` 全仓零命中；编译内默认前缀 `cbrowser-t005`（`docker_adapter.py:234`、`runner.py:60/585`）未动。

## 前轮 finding 复核

- **t054_test_f005（important）——已消除**。生产侧与测试侧均已真实修复，不采信处置表自述：
  - 生产侧：`scripts/check_edge_subnet.py` 新增 `--exclude-network <name>` 参数；`scripts/deploy.sh:176-188` 的 `check_edge_subnet_conflict`（deploy 与 rollback 共用同一函数，两个调用点一次覆盖）传入 `--exclude-network "$PREFIX-edge"`。调用点顺序核实无误：`cmd_deploy` 在 `derive_instance_identity`（`:750`）之后调用（`:751`）；`cmd_rollback` 在 `load_release_identity "$target_env"`（`:809`，取目标 release 记录的子网）之后、`deploy_up_and_verify` 之前调用（`:889-890`）。排除判据为名与子网同时一致（见结论段对该偏离的核实）；外来网络永不排除；fail-closed 不变（Docker 枚举失败 exit 2、非法候选 exit 2）。
  - 测试侧：t027 fake docker 加 `FAKE_OWN_EDGE_SUBNET` 变量（`test_t027_release_controller.py:172-183`，`network ls` 多返回 `own-edge-net`，`inspect` 追加自有网络记录，Name 取 `${CBROWSER_PREFIX}-edge`，由 deploy.sh 导出继承）；3 例新测试全部通过且可判别（回退探针见上）：(a) `test_redeploy_succeeds_when_only_own_edge_network_exists`（同一实例连续部署两次成功，rel-002 成为 current，manifest 的 `edge_subnet` 等于派生值）；(b) `test_rollback_succeeds_when_only_own_edge_network_exists`（部署后 rollback 成功，current 回到 rel-001）；(c) `test_deploy_still_refuses_foreign_overlap_when_own_network_exists`（自有网络存在时外来同子网网络仍被拒，无 release 记录、无构建）。
  - `tests/unit/test_t054_check_edge_subnet.py` 新增 4 例单测全部通过：自有网络排除（名与子网一致 → exit 0）、外来同子网仍拒（exit 1）、陈旧同名不同子网仍拒且 stderr 含 `docker network rm cbrowser-t005-edge`、排除名不匹配仍拒（exit 1）。`subprocess.run` 伪造边界正确（`docker_names` 参数；无 Name 的记录仍按外来网络处理）。
  - compose 接线核实：`compose.yaml:175-181` 的 edge 网络名为 `${CBROWSER_PREFIX:-cbrowser}-edge`、子网为 `${CBROWSER_EDGE_SUBNET}`，与 deploy.sh 传入的 `"$PREFIX-edge"` 一致（PREFIX 默认 `cbrowser`）。
- **t054_test_f001（important）——仍消除**。t027 的 3 例行为测试（派生重叠拒、显式子网部署成功、显式重叠拒）与 `check_edge_subnet.py` 5 例单测均在 76 passed 内通过；`deploy.sh:148-153` 的有条件赋值未动。
- **t054_test_f002（minor）——仍消除**。回退端口判别测试（rel-001 56661 → rel-002 56662 → rollback 服务 56661 且 sha 等于目标 manifest）与 sha 篡改拒绝测试均在 t027 全文件 59 例内通过。
- **t054_test_f003（minor）——仍消除**。`test_t054_shared_client_ip.py` 全文件 8 例通过，含两条防御分支（peer 为 None → `"unknown"`、畸形 XFF hop 跳过）。
- **t054_test_f004（minor）——仍消除**。`SettingsPage.network.test.tsx:46-53/85-88`：死 mock 已删，注入带 spy 的 client 并断言 `health.check` 与 `fontSets.list` 各至少调用一次；前端全量 538/0 含该文件。

## Findings

本轮新发现：0 条。

## 结论

- 前轮 finding 复核：f005 已消除（逐条见上，diff/代码/实跑核实，不采信处置表自述）；f001–f004 仍消除。
- 改测方向复核：无迁就实现的改测。f005 修复 diff 只新增生产侧排除参数与测试（4 个文件 + progress.md 处置行），未弱化任何既有断言；新增行危险模式扫描干净：f005 触及文件内无 `.skip` / `.only` / `# type: ignore` / 恒真断言 / mock 自有模块（`test_t054_check_edge_subnet.py` 的 `monkeypatch` 只伪造系统边界 `subprocess.run`；t027 fake docker 是 shell 层面的系统边界 fake，符合本 task 既定做法）。
- 本轮新发现：0 条。
- 未进表的提示：
  - 与 Round 2 建议有一处有意的偏离，已核实合理：排除判据为名与子网**同时**一致，而非建议的纯按名排除。纯按名排除会在改换显式子网后放行一个同名不同子网的陈旧网络，让 compose 再以不透明方式失败；双条件判据下陈旧网络仍被拒并给出专属提示（`docker network rm <name>`）。三例单测分别覆盖了本判据的三个分支（排除/外来仍拒/陈旧仍拒），无 finding。
  - 已知边界（修复方已写入 progress.md，本审阅核实属实）：同名不同子网且**不重叠**的陈旧网络会通过预检（无子网重叠可判），随后 compose 会因子网名冲突失败——这是名字冲突而非子网冲突，不在预检的“子网重叠”契约内；且改数据根致派生子网变化的场景在前有 `check_prefix_conflict` 按 `com.cbrowser.instance-id` 挡住同前缀异实例（容器仍在时）。不进 finding。
  - `progress.md` 的 f005 处置行（标准五列格式，fix_ref 含 `scripts/check_edge_subnet.py:151`、`scripts/deploy.sh:176` 与两测试文件行号）已核对存在；行号与本审阅实地核对的代码位置一致。
  - `/tmp` 探针（fake docker 与 deploy.sh 备份）已清理；无 reviewer 临时 probe 文件残留（`git status` 无未跟踪交付文件）。
  - 引用逐项核对：本报告引用的文件、行号、提交均已实地核对存在。
- 总体判断：f005 已真实修复——二次部署与回退不再被本实例自有 edge 网络拒绝，且外来重叠仍被拒；Round 1 的四条 finding 仍消除；AC-004/AC-006/AC-010 的打勾依据随修复恢复成立。
- 系统性 follow-up：无（f005 为本 task 内缺口，不跨 task）。

### AC 复验方式

- AC-001：TICK-VALID，re_verified。新 `test_t054_openapi_no_network.py` 对 live OpenAPI、入库导出与生成 d.ts 三处断言零 network 路径/模型；后端全量独立复跑 2033/25/8/0，零 t054 文件失败。
- AC-002：TICK-VALID，re_verified。`SettingsPage.network.test.tsx` 断言只读展示 live `window.location` 值且 8 个表单 testId 不存在，数据路径断言为真实调用（f004 修复仍有效）；前端全量独立复跑 538/0。
- AC-003：TICK-VALID，re_verified。compose 结构测试断言 Caddy 端口 `127.0.0.1:` 绑定且无通配发布；`test_refactor_behavior_equivalence.py:279` 断言 `stream_ports` 为 `{"30006/udp": ("127.0.0.1", 30006)}`；后端全量独立复跑通过。
- AC-004：TICK-VALID，re_verified。端口变更机制测试（集成 Origin 测试，自定义端口 58888）仍真实；Round 2 致 VOID 的唯一原因（f005：二次部署被自有网络拒绝）已消除——新测试 (a) 同一实例连续部署两次成功且第二次生效，独立复跑通过；“旧端口不可访问”的真实探测侧仍为环境跳过（见 progress.md），不影响本 AC 打勾成立。
- AC-005：TICK-VALID，re_verified。`test_t054_no_default_port_literal.py` 断言全仓代码内 `56661` 字面量恰为一处（`DEFAULT_HTTPS_PORT` 定义）；独立复跑通过。
- AC-006：TICK-VALID，re_verified。指纹随端口变化与回退重渲染机制测试仍真实；Round 2 致 VOID 的唯一原因（f005：回退被自有网络拒绝）已消除——新测试 (b) 部署后 rollback 成功且 current 回到目标，端口判别测试（56661/56662）独立复跑通过。
- AC-007：TICK-VALID，re_verified。`test_t054_migration.py`：head 为 0008 单头，升级删光全部 `network.*` 行且保留无关行，删后 API 可启动；`test_gateway_config.py` 断言无 publication 方法与 `network_state_dir` 字段；独立复跑通过。
- AC-008：TICK-VALID，re_verified。`test_a4_viewer_throttle.py`（同 profile 不同来源隔离、XFF 链解析、不可信 peer 忽略伪造 XFF、十次阈值）与 `test_auth_client_ip.py`（按来源窗口与全局预算：a 锁定不影响 b）及 `test_auth_api.py` 登录限流；后端全量独立复跑通过。
- AC-009：TICK-VALID，re_verified。`test_t054_shared_client_ip.py` 断言旧双模块不存在、API 与 Gateway 的函数 `__module__` 均为共享模块、不可信 peer 的 XFF 不被采信，防御分支覆盖已由 f003 补齐；独立复跑通过。
- AC-010：TICK-VALID，trust_prior。[deploy] 真实部署，本机无 Docker/真实引擎无法独立复验；依赖的替代证据中被 f005 证伪的重部署一节已恢复——fake Docker 连续部署与部署后回退均成功（t027 59 passed，已独立复跑）、集成 Origin 测试与前端 538/0（已独立复跑）；progress.md 已写明“本机未验证、不得记为已验”，真实部署须用户机补验。

coverage = 9/10

reviewed_scope: 2c64edb35387bb4a

verdict: PASS

## Round 4 (2026-11-11T21:11:29+08:00)

### 审阅输入说明

- 仓库落点校验通过：`git rev-parse --show-toplevel` == `<home>/workspace/CBrowser_t054`。
- 本轮为 Round 3 code f003 修复复审：`scripts/check_edge_subnet.py` 的 `main()` 圈复杂度约 23 → 拆分为 `_parse_args(argv)` 与 `_classify_overlaps(...)`；修复方未新增测试，称 9 例既有单测经 `main()` 覆盖抽出的分支、行为未变。本审阅不采信该自述，逐项实测核实。
- 独立实跑（验证 venv `~/workspace/.cb-venv-t051/bin/python`，`PYTHONPATH=src/backend:tests`；前端 Node 26.13.0，`src/frontend` 内 `npm test`）：
  - `test_t054_check_edge_subnet.py` 9 例：**9 passed**。
  - 行覆盖探针（`sys.settrace` 记录 9 例测试执行到的 `check_edge_subnet.py` 行号）：`_classify_overlaps` 四路（排除/陈旧/外来/无重叠）均经 `main()` 执行；`_parse_args` 的 5 个 `_UsageError` raise 点中仅缺候选（`:178`）被执行，`:169`（重复 flag / 缺值）与 `:173`（未知 flag / 第二位置参数）从未执行。
  - CLI 探针（真实脚本，不触 Docker）：重复 `--exclude-network`、缺值、未知 `--bogus`、第二位置参数、缺候选 5 种畸形入参均 exit 2 且 stderr 为 usage 文本；行为正确。
  - fake docker 入口探针（PATH 上 fake `docker` 只返回自有网络 `cbrowser-t005-edge` / `172.23.0.0/16`，fake `ip` 返回空）：不带 flag exit 1、带正确排除名 exit 0、带错名 exit 1；重构后入口行为未变。
  - 受影响批：**113 passed**（t027 全文件 59 + check_edge_subnet 9 + shared_client_ip 8 + a24 8 + compose 结构 10 + deploy_network_config + network_config_cli + migration + openapi + no_default_port_literal）。
  - 前端全量：**538 passed / 0 failed**（74 个测试文件，含 `test:types`）。
  - 后端全量（`tests/unit` + `tests/integration`）：**2033 passed / 25 failed / 8 skipped / 0 errors**；25 个失败另以 9 个失败文件子集重跑逐名核对，与修复方 R3 日志 `FAILED` 行逐行完全相同（agent_executor_chain 7、t028 4、normal_exit_replay 4、automation_probe_chain 3、t034 2、automation_cdp_flow 2、repo_hygiene 1、automation_cdp 1、control_attendant_chain 1），无一在 t054 改动文件内。
- 命名锁死核查通过：`com.cbrowser.deployment-id` 全仓零命中。

## 前轮 finding 复核

- **t054_test_f001（important）——仍消除**。t027 的 3 例行为测试（派生重叠拒、显式子网部署成功、显式重叠拒）与 `check_edge_subnet.py` 5 例单测均在 113 passed 内通过；`deploy.sh:148-153` 的有条件赋值未动。
- **t054_test_f002（minor）——仍消除**。回退端口判别测试（rel-001 56661 → rel-002 56662 → rollback 服务 56661 且 sha 等于目标 manifest）与 sha 篡改拒绝测试均在 t027 全文件 59 例内通过。
- **t054_test_f003（minor）——仍消除**。`test_t054_shared_client_ip.py` 全文件 8 例通过，含两条防御分支（peer 为 None → `"unknown"`、畸形 XFF hop 跳过）。
- **t054_test_f004（minor）——仍消除**。`SettingsPage.network.test.tsx` 的真实数据路径断言（`health.check` / `fontSets.list` 各至少调用一次）在前端全量 538/0 内通过。
- **t054_test_f005（important）——仍消除**。t027 的 3 例新测试（连续部署、部署后回退、外来重叠仍拒）与 `check_edge_subnet.py` 9 例单测均在 113 passed 内通过；本轮 fake docker 入口探针重验排除行为未因重构改变（不带 flag exit 1、正确排除 exit 0、错名 exit 1）。

## Findings

### t054_test_f006 - _parse_args 四个畸形入参分支零提交测试

- 严重度：minor
- 锚点：「覆盖可更广」——`_parse_args` 文档化契约（`scripts/check_edge_subnet.py:156-159` 的 docstring：对重复 / 缺值 `--exclude-network`、未知 `--flag`、第二位置参数、缺候选抛 `_UsageError`）；无对应 AC 违反，不阻断
- 位置：`scripts/check_edge_subnet.py:169`、`scripts/check_edge_subnet.py:173`（两处 `raise _UsageError` 从未执行）；`tests/unit/test_t054_check_edge_subnet.py`（缺失用例）
- 问题：行覆盖实证（`sys.settrace`，9 例测试全程）：`_parse_args` 被执行到的行是 `:161-168`、`:170-172`、`:175-179`，`:169` 与 `:173` 两行 raise 从未执行。docstring 承诺的 5 种错误情形中，重复 `--exclude-network`、flag 缺值、未知 `--flag`、第二位置参数四种在提交的测试里零覆盖；仅缺候选（`:178`）由 `test_invalid_candidate_returns_two`（`main([])`）覆盖。修复方的 10 场景 CLI 验证是一次性探针，未落为回归测试——后续改动 `_parse_args` 时这四条分支静默退化，无测试可拦。注意：行为本身正确，本审阅 CLI 实测 5 种畸形入参均 exit 2 + usage 文本，故不是假绿也不是行为缺陷，是回归防护缺口。`_classify_overlaps` 则已全分支经 `main()` 覆盖（settrace：排除 `:211`、陈旧 `:213-214`、外来 `:215`、无重叠 `:204-205` 均执行），不缺测试，接受无直接单测。
- 建议：`test_t054_check_edge_subnet.py` 补 4 例（或 1 例参数化）：重复 flag、缺值、未知 flag、第二位置参数均 exit 2 且 stderr 含 usage。`main()` 内调 `_parse_args`，不触 subprocess，无需伪造。

## 结论

- 前轮 finding 复核：f001–f005 全部仍消除（逐条见上，diff/代码/实跑核实，不采信处置表自述）。
- 改测方向复核：无迁就实现的改测。本轮修复 diff 未改任何测试文件（无新增、无修改、无删除）；危险模式扫描：三测试文件（`test_t054_check_edge_subnet.py` / `test_t027_release_controller.py` / `test_t054_shared_client_ip.py`）内无 `.skip` / `.only` / `# type: ignore`（grep 命中仅为注释与测试名中的 "only" 单词）；全仓唯一 `# type: ignore[call-arg]` 仍为 Round 1 已调查放行的 `test_network_policy.py:240`（未动）。
- 本轮新发现：1 条（minor，f006）。
- 未进表的提示：
  - `test_repo_hygiene.py::test_tracked_files_do_not_leak_developer_home_paths` 的违规集合现已包含 t054 自身的 `review_code.md` / `review_test.md`（与 t051–t053 相同原因：审阅报告内含 `<home>/` 绝对路径）；该测试在基线中已红，属流程文件问题，不影响任务交付物；Round 1“零 t054 文件”的说法已不再成立，特此更正记录。
  - `/tmp` 探针（fake docker、`r4trace.py`、pytest basetemp）已清理，现 11%。
  - 引用逐项核对：本报告引用的文件、行号均已实地核对存在。
- 总体判断：f003 重构行为未变、测试侧仍可信；仅 `_parse_args` 四个错误分支缺提交测试，minor 不阻断。
- 系统性 follow-up：无（f006 为本 task 内缺口，不跨 task）。

### AC 复验方式

- AC-001：TICK-VALID，re_verified。`test_t054_openapi_no_network.py` 在受影响批 113 passed 内通过；后端全量独立复跑 2033/25/8/0。
- AC-002：TICK-VALID，re_verified。`SettingsPage.network.test.tsx` 断言只读展示 live `window.location` 值且 8 个表单 testId 不存在，数据路径断言为真实调用；前端全量独立复跑 538/0。
- AC-003：TICK-VALID，re_verified。compose 结构测试在受影响批 113 passed 内通过，断言 Caddy 端口 `127.0.0.1:` 绑定；`test_refactor_behavior_equivalence.py:279` 断言 `stream_ports` 为 `{"30006/udp": ("127.0.0.1", 30006)}`，在后端全量内通过。
- AC-004：TICK-VALID，re_verified。集成 Origin 测试（自定义端口 58888）在后端全量内通过且不在 25 个失败内；t027 连续部署测试（f005 修复）在 113 passed 内通过。
- AC-005：TICK-VALID，re_verified。`test_t054_no_default_port_literal.py` 在受影响批 113 passed 内通过，断言全仓代码内 `56661` 字面量恰为一处。
- AC-006：TICK-VALID，re_verified。t027 指纹测试与回退端口判别测试（56661/56662）在 113 passed 内通过；部署后回退测试（f005 修复）同样通过。
- AC-007：TICK-VALID，re_verified。`test_t054_migration.py` 在受影响批 113 passed 内通过：head 为 0008 单头，升级删光全部 `network.*` 行且保留无关行，删后 API 可启动。
- AC-008：TICK-VALID，re_verified。`test_a4_viewer_throttle.py` 与 `test_auth_client_ip.py` 在后端全量内通过且不在 25 个失败内（同 profile 不同来源隔离、a 锁定不影响 b）。
- AC-009：TICK-VALID，re_verified。`test_t054_shared_client_ip.py` 在受影响批 113 passed 内通过，断言旧双模块不存在、API 与 Gateway 的函数 `__module__` 均为共享模块、不可信 peer 的 XFF 不被采信，防御分支覆盖仍在。
- AC-010：TICK-VALID，trust_prior。[deploy] 真实部署，本机无 Docker/真实引擎无法独立复验；依赖的替代证据仍成立——fake Docker 连续部署与部署后回退均成功（t027 59 passed，已独立复跑）、集成 Origin 测试与前端 538/0（已独立复跑）；progress.md 已写明“本机未验证、不得记为已验”，真实部署须用户机补验。

coverage = 9/10

reviewed_scope: e5c994e577897427

verdict: PASS

## Round 5 (2026-11-11T21:49:05+08:00)

### 审阅输入说明

- 仓库落点校验通过：`git rev-parse --show-toplevel` == `<home>/workspace/CBrowser_t054`。
- 本轮为 Round 4 test f006 修复复审（最后一轮，max_review_round=5）：`tests/unit/test_t054_check_edge_subnet.py` 新增 1 例参数化测试 `test_parse_args_usage_errors_return_two`（:253），4 个入参覆盖 `_parse_args` 的 4 种 `_UsageError` 情形，各断言 exit 2 且 stderr 含 usage 文本，并以 guard 断言解析失败前不触 subprocess；修复方称未改任何生产代码。本审阅不采信该自述，逐项实测核实。
- 独立实跑（验证 venv `~/workspace/.cb-venv-t051/bin/python`，`PYTHONPATH=src/backend:tests`；前端 Node 26.13.0，`src/frontend` 内 `npm test`）：
  - `test_t054_check_edge_subnet.py`：**13 passed**（9 既有 + 4 新增）。
  - 受影响批：**117 passed**（t027 全文件 59 + check_edge_subnet 13 + shared_client_ip 8 + a24 8 + compose 结构 10 + deploy_network_config + network_config_cli + migration + openapi + no_default_port_literal）。
  - 前端全量：**538 passed / 0 failed**（74 个测试文件，含 `test:types`）。
  - 后端全量（`tests/unit` + `tests/integration`）：**2037 passed / 25 failed / 8 skipped / 0 errors**（422.48s，日志 `.scratch/r5_backend_full.log`）；25 个失败与修复方 R3 日志 `FAILED` 行逐名完全相同（agent_executor_chain 7、t028 4、normal_exit_replay 4、automation_probe_chain 3、t034 2、automation_cdp_flow 2、repo_hygiene 1、automation_cdp 1、control_attendant_chain 1），零 t054 / check_edge_subnet / deploy 相关失败。
  - 行覆盖探针（`sys.settrace`，R4 审阅同款方法）：4 例新测试执行 `_parse_args` 时 `:169` 与 `:173` 两行 raise 均被命中（命中行 `:161-168`、`:169`、`:170-172`、`:173`、`:175-176`），各入参均 exit 2。
  - 变异探针（/tmp 副本，不动仓库）：把 `:169` 与 `:173` 两处 `raise _UsageError` 中性化后，4 例入参中 3 例 exit 0、1 例（缺值）抛 `IndexError`——4 例全部不再通过，证实测试非空转、raise 是承重逻辑。
- 命名锁死核查通过：`com.cbrowser.deployment-id` 全仓零命中；`56661` 只剩 `src/backend/cbrowser/network_config.py:15` 一处定义。
- 改动面核实：`scripts/check_edge_subnet.py` mtime 停在 12:42（R3 f003 重构轮），`scripts/deploy.sh` / `test_t027_release_controller.py` / `test_t054_shared_client_ip.py` mtime 均早于 R4 修复轮；本轮修复只改了 `tests/unit/test_t054_check_edge_subnet.py`（mtime 13:13）与 progress.md 流程文件。`git status` 无未跟踪交付文件，diff 可见范围完整。

## 前轮 finding 复核

- **t054_test_f006（minor）——已消除**。4 例参数化测试真实且非空转：settrace 证实 `:169`（重复 flag / 缺值）与 `:173`（未知 flag / 第二位置参数）两行 raise 均被执行；变异探针证实去掉 raise 后 4 例全败。guard 真实：13 例测试在 `subprocess.run` 被 monkeypatch 为必抛错桩的前提下全绿，证实解析失败前不枚举网络（若 `main()` 先调 subprocess，测试会直接报错而非通过）。行号核实：`raise _UsageError` 确在 `:169`、`:173`、`:178`，与测试注释一致。
- **t054_test_f001–f005——仍消除**。f001（t027 3 例行为测试 + check_edge_subnet 5 例单测）、f002（回退端口判别 + sha 篡改拒绝）、f003（client_ip 两条防御分支）、f004（设置页真实数据路径断言）、f005（t027 连续部署 / 部署后回退 / 外来重叠仍拒 + check_edge_subnet 4 例单测）均在受影响批 117 passed 与后端全量 2037/25/8/0 内通过。

## Findings

本轮新发现：0 条。

## 结论

- 前轮 finding 复核：f006 已消除，f001–f005 全部仍消除（逐条见上，diff/代码/实跑核实，不采信处置表自述）。
- 改测方向复核：无迁就实现的改测。本轮修复只新增 1 例参数化测试，未改任何生产代码与既有测试；危险模式扫描：新增测试内无 `.skip` / `.only` / `# type: ignore` / `assert True`；monkeypatch 只伪造系统边界 `subprocess.run`，且是“必抛错”的 guard 桩而非行为 mock，不掩盖真实交互。
- 本轮新发现：0 条。
- 未进表的提示：
  - 后端全量首轮在 8 分 40 秒处被 runtime 重启打断（exec-log 0 字节、/tmp 日志随 tmpfs 清空，无确认结果）；已重跑，日志改写 `.scratch/r5_backend_full.log`（磁盘持久），得 2037/25/8/0。/tmp 探针文件已清理，现 43%。
  - `test_repo_hygiene.py` 的 1 个失败仍为 Round 4 已记录的流程文件问题（审阅报告内含 `<home>/` 绝对路径），基线已红，不影响任务交付物。
  - 引用逐项核对：本报告引用的文件、行号均已实地核对存在。
- 总体判断：f006 的回归防护缺口已由真实可判别的参数化测试补齐；全量回归与命名锁死均无新增问题；本轮为最后一轮，双路均无未解决 finding，具备 finalize 条件。
- 系统性 follow-up：无。

### AC 复验方式

- AC-001：TICK-VALID，re_verified。`test_t054_openapi_no_network.py` 在受影响批 117 passed 内通过；后端全量独立复跑 2037/25/8/0。
- AC-002：TICK-VALID，re_verified。`SettingsPage.network.test.tsx` 断言只读展示 live `window.location` 值且 8 个表单 testId 不存在，数据路径断言为真实调用；前端全量独立复跑 538/0。
- AC-003：TICK-VALID，re_verified。compose 结构测试在受影响批 117 passed 内通过，断言 Caddy 端口 `127.0.0.1:` 绑定；`test_refactor_behavior_equivalence.py:279` 断言 `stream_ports` 为 `{"30006/udp": ("127.0.0.1", 30006)}`，在后端全量内通过。
- AC-004：TICK-VALID，re_verified。集成 Origin 测试（自定义端口 58888）在后端全量内通过且不在 25 个失败内；t027 连续部署测试（f005 修复）在 117 passed 内通过。
- AC-005：TICK-VALID，re_verified。`test_t054_no_default_port_literal.py` 在受影响批 117 passed 内通过；独立 grep 核实 `56661` 只剩 `network_config.py:15` 一处定义。
- AC-006：TICK-VALID，re_verified。t027 指纹测试与回退端口判别测试（56661/56662）在 117 passed 内通过；部署后回退测试（f005 修复）同样通过。
- AC-007：TICK-VALID，re_verified。`test_t054_migration.py` 在受影响批 117 passed 内通过：head 为 0008 单头，升级删光全部 `network.*` 行且保留无关行，删后 API 可启动。
- AC-008：TICK-VALID，re_verified。`test_a4_viewer_throttle.py` 与 `test_auth_client_ip.py` 在后端全量内通过且不在 25 个失败内（同 profile 不同来源隔离、a 锁定不影响 b）。
- AC-009：TICK-VALID，re_verified。`test_t054_shared_client_ip.py` 在受影响批 117 passed 内通过，断言旧双模块不存在、API 与 Gateway 的函数 `__module__` 均为共享模块、不可信 peer 的 XFF 不被采信，防御分支覆盖仍在。
- AC-010：TICK-VALID，trust_prior。[deploy] 真实部署，本机无 Docker/真实引擎无法独立复验；依赖的替代证据仍成立——fake Docker 连续部署与部署后回退均成功（t027 59 passed，已独立复跑）、集成 Origin 测试与前端 538/0（已独立复跑）；progress.md 已写明“本机未验证、不得记为已验”，真实部署须用户机补验。

coverage = 9/10

reviewed_scope: 1e4028e691635540

verdict: PASS
