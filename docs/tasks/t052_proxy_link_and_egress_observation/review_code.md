# Task review t052（reviewer_focus: 代码）

- task：`t052_proxy_link_and_egress_observation`
- spec：`docs/tasks/t052_proxy_link_and_egress_observation/task.md`
- diff_anchor：`d07f5e332b2d3b904bf23a4c6e2391036b0ce761`
- target：`git -C '<home>/workspace/CBrowser_t052' diff d07f5e332b2d3b904bf23a4c6e2391036b0ce761`
- round：1
- reviewed_at：2026-11-11T12:41:28+08:00

reviewed_scope: 84f628d6290d50a4

## Findings

### t052_code_f001 - 探测进行中界面从不显示“检测中”，AC-006 的“依次显示检测中”未实现

- 严重度：important
- 锚点：AC-006——“代理保存后自动探测出口，界面依次显示检测中与国家码或未知”
- 位置：`src/frontend/src/features/proxies/ProxyTable.tsx:82`、`src/frontend/src/features/proxies/ProxyFormDialog.tsx:430`、`src/frontend/src/features/browser-session/SessionDetailsPanel.tsx:158`
- 问题：后端已返回 `observation_status: "pending"`（`ProxyResponse` 有该字段，`repository.py` 的 `_current_observation` 会透传 pending 行），但前端没有任何非测试、非生成代码读取 `observation_status`（全仓 grep 仅测试文件与 `generated/cbrowser_v1.d.ts` 命中），前端也不存在“检测中”文案（`src/frontend/src` 内零命中）。三处国家展示位都只按 `country_code` 有无二选一：有则显示国家码、无则显示“未知”。复现路径：新建代理保存 → 后台自动探测进行中（观测行为 pending）→ 代理列表与弹窗国家状态均显示“未知”，从未出现“检测中”；探测完成后才跳变为国家码或继续“未知”。`progress.md` 称“pending 显示检测中”与代码事实不符。自动探测、失败显示未知、可手动重试、不猜测值这几部分已实现，缺的只是“检测中”这一显式中间态。
- 建议：最小修复：在 `ProxyTable` 地区列与 `ProxyFormDialog` 国家状态处按 `observation_status === "pending"` 渲染“检测中”（新增 i18n 键，en/zh 同步），`SessionDetailsPanel` 同理；补前端测试断言 pending 行显示“检测中”而非“未知”。

### t052_code_f002 - 探测 runner 抛非 EgressProbeError 时 pending 观测永久挂起，且后台路径把异常吞掉只记常量日志

- 严重度：important
- 锚点：AC-006 失败路径——“失败时显示未知并可重试”；行为缺陷：一次手动探测返回 500 且观测状态永久停在 pending，无 failed 行、无 error_code、无可诊断日志
- 位置：`src/backend/cbrowser/services/egress_probe.py:136-141`、`src/backend/cbrowser/services/profile_service.py:926`（`probe_proxy_egress`）、`src/backend/cbrowser/services/profile_service.py:1032-1040`（`_probe_safely`）
- 问题：`probe_proxy_egress` 先记 pending 行，再调 runner，但只 `except EgressProbeError`。`SupervisorEgressProbeRunner.probe` 在 `resp.json()` 返回非 dict（如 `[]`、字符串）时，`data.get(...)` 直接抛 `AttributeError`——已用 gate venv 实测复现：`httpx.MockTransport` 返回 `json=[]` 时 `probe()` 抛 `AttributeError: 'list' object has no attribute 'get'`，不是 `EgressProbeError`。后果分两路：手动探测（`POST /api/v1/proxies/{id}/probe`）时异常直达路由返回 500，pending 行之后没有任何 failed 行被记录，`observation_status` 永久停在 pending（pending 行无 `expires_at`，`observation_is_current` 只对 ok 行做失效判断，pending 永不过期）；后台自动探测时 `_probe_safely` 的 `except Exception` 捕获后只记 `logger.warning("Background egress probe failed: proxy=%s error_type=%s", proxy_id, "probe_error")`——`error_type` 是写死的常量 `"probe_error"`，异常类型、消息与堆栈全部丢弃，事后无法定位失败原因。触发条件虽窄（需 Supervisor 返回畸形 JSON 或记录观测时 DB 异常），但路径真实存在且修复成本极低。
- 建议：`SupervisorEgressProbeRunner.probe` 在 `resp.json()` 后先校验 `isinstance(data, dict)`，非 dict 即按 `supervisor_unavailable`（或新增 `probe_bad_response`）抛 `EgressProbeError`；`probe_proxy_egress` 对 runner 的非 `EgressProbeError` 异常兜底记一条 failed 观测（`error_code="probe_failed"`）再返回；`_probe_safely` 的日志改记真实异常（`exc_info=True` 或至少 `type(exc).__name__` 与 `str(exc)`）。

### t052_code_f003 - 新增 `DockerAdapter.run_egress_probe` 圈复杂度约 24

- 严重度：minor
- 锚点：圈复杂度标准（CC ≥ 15 且本 task 新建函数）
- 位置：`src/backend/cbrowser/supervisor/docker_adapter.py:463`
- 问题：手算近似 McCabe 约 24：proxy_id 校验、extra_hosts 三元、建网/建 helper 两个 try/except、loopback 错误映射的 `if/and/or`、host 括号处理、exec 线程 join 超时、exit_code 检查、JSON 解析 try/except、payload 类型与字段检查、finally 内 helper/network 两路清理 try/except。函数本身逻辑正确（fake-docker 测试 13 passed 已覆盖主要分支），但分支密度高，后续改动易漏分支。
- 建议：拆出“建 helper + 装策略”“exec 并解析单行 JSON”“清理”三个小函数，或把错误映射抽为独立 helper；不阻塞本轮。

### t052_code_f004 - 新增前端 `compressIpv6` 圈复杂度约 18

- 严重度：minor
- 锚点：圈复杂度标准（CC ≥ 15 且本 task 新建函数）
- 位置：`src/frontend/src/features/proxies/parseProxyUrl.ts:63`
- 问题：手算近似 McCabe 约 18（不含内嵌 `expandV4` 的约 5）：`::` 压缩分支、双 `::` 拒绝、头/尾展开空值检查、组格式校验、压缩/非压缩两路长度校验、零组最长游程扫描、左右拼接的多个空串分支。函数与后端 `ipaddress.compressed` 的对照测试已通过（前后端矩阵测试均绿），仅可读性风险。
- 建议：把“展开内嵌 IPv4”“最长零游程”拆为独立小函数；不阻塞本轮。

### t052_code_f005 - `list_proxies` 每行两次额外查询（N+1）

- 严重度：minor
- 锚点：性能与资源——循环内查库
- 位置：`src/backend/cbrowser/adapters/database/repository.py:1268-1290`
- 问题：`list_proxies` 的列表推导里对每个代理各发一次 `_proxy_used_by` 与一次 `_current_observation`（各为独立 SELECT）；`get_proxy`/`update_proxy` 返回路径同样各补一次观测查询。`_proxy_used_by` 的逐行查询是既有模式，本 task 又叠加了第二次逐行查询。代理库表规模小、观测查询走 `proxy_id` 索引，当前无可观测的性能故障。
- 建议：列表查询时用一次 `WHERE proxy_id IN (...)` 批量取各代理最新观测行再组装；不阻塞本轮。

### t052_code_f006 - task.md 未知契约清单称 supervisor 测试“12 passed”，实际为 13

- 严重度：minor
- 锚点：文档与实现不一致
- 位置：`docs/tasks/t052_proxy_link_and_egress_observation/task.md:99`
- 问题：该行写“fake-docker 单元测试（`tests/unit/test_t052_supervisor_probe.py`，12 passed）”，但本轮实测该文件 `--collect-only` 收集到 13 个测试，且 13 个全部通过（计入后端 t052 合计 106 passed）。`progress.md` 的“13 passed”正确，task.md 的数字 stale。
- 建议：把 task.md 该处改为 13 passed。

## 结论

- 本轮新发现：6 条（important 2 条，minor 4 条）
- 未进表的提示：
  - 文件过大（按规则只列不进表）：`src/backend/cbrowser/supervisor/docker_adapter.py` 全文件 2612 行、`src/backend/cbrowser/services/profile_service.py` 1043 行、`src/frontend/src/features/proxies/ProxyFormDialog.tsx` 649 行、`src/frontend/src/features/proxies/parseProxyUrl.ts` 422 行——四者均在本 task 净增行数且超 400 行阈值（docker_adapter/profile_service 超 800 行 important 阈值）。其中 docker_adapter 与 profile_service 本就庞大，本 task 的增量占比有限；未见因过大导致的可观测缺陷。
  - 前后端解析器有一处已验证的边缘分歧：后端 `_parse_port` 用 `\d+`（Python `\d` 含非 ASCII 数字），实测 `http://proxy.example.com:١٢٣`（阿拉伯数字）会被后端解析为端口 123，而前端 `/^\d+$/` 只认 ASCII 数字会拒绝。日常无影响（UI 拒绝、直接调 API 才接受），建议后端端口正则改 `[0-9]+` 以与前端锁步。
  - AC-004 的“密码不出现在 DOM”在静止态成立（失焦显示脱敏链接、响应/缓存/日志均不含密码），但聚焦编辑链接时输入框会短暂显示完整链接（含密码明文值）；这是实现方有意设计并经测试确认的行为（`ProxyFormDialog.tsx` 的 `onLinkFocus`），不是疏漏，提请注意。
  - AC-007 的过期路径只做“失效显示”（过期 ok 行不再返回），过期本身不触发自动重探，需用户手动重试；AC 文本的“同样失效”按此理解成立。
  - 审阅范围说明：10 个新文件在 `git status` 中仍为未跟踪（未执行 `git add -N`），不在 `git diff d07f5e3` 输出内；本轮已直接读文件全文核查（`domain/proxy_endpoint.py`、`domain/egress_observation.py`、`services/egress_probe.py`、`runtime_agent/egress_probe.py`、迁移 0006、5 个 t052 测试文件），内容可见，不构成 INCOMPLETE。
  - 命名锁死核查通过：`com.cbrowser.deployment-id` 在 `src/`、`config/`、`scripts/`、`compose.yaml` 中零命中，全仓仅 `progress.md` 与 `docs/blueprint/decisions.md:342` 的历史叙述中提及被驳回的偏离；`resource_prefix` 默认值仍为 `cbrowser-t005`（`docker_adapter.py:234`）；探测 helper 标签经 `_instance_label` 使用规定的 `com.cbrowser.instance-id`。
  - 未发现范围外行为或顺手改进：改动面集中在代理链接录入、出口观测、Supervisor 探测 helper 与前端弹窗；`country_code` 可写字段已在模型、ORM、迁移、OpenAPI、前端类型中全量移除，无残留引用（`grep` 验证旧 i18n 键亦无残留）。
- 总体判断：实现主体扎实（解析器前后端逐项对齐、凭据流转与脱敏到位、loopback 映射与策略放行完整、回归测试全绿），但 AC-006 的“检测中”中间态完全未在界面落地，且探测异常路径存在 pending 永久挂起的真实缺陷，两项 important 未解决，故判 FAIL。
- 系统性 follow-up：无（6 条 finding 均为本 task 内可修复项，无跨 task 基础设施缺口）。

### AC 复验方式

- AC-001：TICK-VALID，re_verified。弹窗默认只渲染链接/备注/只读国家状态，高级区默认折叠且无国家输入（ProxyFormDialog.tsx 渲染代码核对），前端相关测试 124 passed。
- AC-002：TICK-VALID，re_verified。前后端解析器逐项比对一致（四格式、IPv6 括号、percent-decode、错误码），后端矩阵 53 passed、前端 54 passed 均实跑通过。
- AC-003：TICK-VALID，re_verified。链接→高级字段（onLinkChange）与高级字段→链接（syncFromEndpoint）双向同步代码核对，前端相关测试实跑通过。
- AC-004：TICK-VALID，re_verified。ProxyResponse 无 password 字段、repr/str 只显脱敏链接、集成测试断言密码不在任何响应体（17 passed 实跑）；静止态界面显示脱敏链接（聚焦编辑时短暂显示完整链接，见结论提示）。
- AC-005：TICK-VALID，re_verified。名称默认 host:port（resolved_name / proxyDisplayName），手动名经 nameTouched 保护不被后续解析覆盖，前端相关测试实跑通过。
- AC-006：TICK-VOID，re_verified。保存后自动探测、失败显示未知、可手动重试、不猜测值均已实现，但“界面依次显示检测中”缺失：无任何界面代码读取 observation_status pending，三处国家展示位在探测中均显示“未知”而非“检测中”（见 f001）。
- AC-007：TICK-VALID，re_verified。端点/凭据变更记 pending 行并自动重探（profile_service.py），过期 ok 行经 observation_is_current（TTL 24h）失效不再返回；过期本身不自动重探，需手动重试。
- AC-008：TICK-VALID，re_verified。探测在 helper 内经代理访问回显（fetch_egress_ip 用显式 proxy_url、trust_env=False），受控回显+代理夹具集成测试实跑通过，观测取代理出口 203.0.113.7 而非 API 直连出口。
- AC-009：TICK-VALID，re_verified。探测路由拒绝任何非空 body（除 {} 外 422），服务端只按已存端点执行，控制面另有指纹校验（endpoint_mismatch）；负向集成测试实跑通过。
- AC-010：TICK-VALID，re_verified。loopback 映射为 host.docker.internal + extra_hosts host-gateway（启动与探测两路），策略仅放行映射地址:端口（_resolved_endpoint）；13 个 fake-docker 测试实跑通过；真实 Docker daemon 行为本机无环境，未验证，留待 AC-012 部署验证。
- AC-011：TICK-VALID，re_verified。映射失败时启动与探测两路均在执行前抛 LoopbackMappingError 并附处置提示；fake-docker 测试实跑通过；真实 daemon 拒绝行为本机无环境，未验证。
- AC-012：TICK-VOID，trust_prior。未打勾的 [deploy] AC，本机无 Docker/真实代理/公网出口，无法验证，依赖用户机真实部署端到端验证。

coverage = 11 / 12

verdict: FAIL

## Round 2 (2026-11-11T13:34:56+08:00)

- round：2
- reviewed_at：2026-11-11T13:34:56+08:00

reviewed_scope: 28e84db3286c2e6d

复核方法：落点仓库校验通过（`git rev-parse --show-toplevel` = `<home>/workspace/CBrowser_t052`）；逐条按 diff/代码/实跑核实，不采信 `progress.md` 处置表自述。实跑：后端 t052 全套 7 个文件 122 passed（`~/workspace/.cb-venv-t051/bin/python`，`PYTHONPATH=<worktree>/src/backend`，34.34s）；前端 4 个相关文件 96 passed（Node 26.13.0，`npx vitest run`，含解析矩阵 55）；f002 独立复现脚本（`httpx.MockTransport` 返回 `json=[]`）。

## Findings

### t052_code_f007 - `list_proxies` 批量观测查询无单代理行数上限，历史观测行会无限累积进列表查询

- 严重度：minor
- 锚点：行为缺陷——f005 修复引入的查询无界化（原单行路径有 `LIMIT 1`）
- 位置：`src/backend/cbrowser/adapters/database/repository.py:1246-1280`（`_current_observations`）
- 问题：`_current_observations` 用一次 `WHERE proxy_id IN (...)` 取回全部代理的**全部历史观测行**再取每代理最新一行，无单代理 `LIMIT`；全仓无任何观测行清理/保留期逻辑（`record_egress_observation` 只增不减）。每次探测新增一行，列表查询随时间推移每次都搬运并丢弃全部历史行（当前规模下无可观测故障：3 代理查询计数测试证实 1 次 SELECT，4 个仓库观测测试全绿）。
- 建议：改用按代理取最新一行的有界查询（如 `observed_at` 最大值子查询 / lateral join），或给观测表加保留期清理；不阻塞本轮。

## 结论

- 前轮 finding 复核（Round 1 code 6 条，全部以 diff/代码/实跑核实为已消除）：
  - t052_code_f001（important，AC-006“检测中”缺失）——已消除。三处国家展示位均按 `observation_status === "pending"` 渲染“检测中”：`ProxyTable.tsx:82`、`ProxyFormDialog.tsx:430`（`countryStatus`）、`SessionDetailsPanel.tsx:158`（`proxyRegion`），与无观测的“未知”分支区分；i18n 键 `proxyCountryProbing` 英文 "Detecting"（`i18n.tsx:445`）/中文“检测中”（`i18n.tsx:933`）双语齐全；`ProxyResponse.observation_status` 经 `_to_domain_proxy`（`repository.py:1174`）与 `list_proxies` 批量路径（`:1318`）真实贯通到前端，`ProxyListPage.tsx:201` 将完整代理对象传给 `ProxyTable`。3 个新增 pending 夹具测试均断言显示“检测中”且不显示“未知”，前端实跑通过。
  - t052_code_f002（important，探测异常 pending 永久挂起）——已消除。`SupervisorEgressProbeRunner.probe` 在 `resp.json()` 后校验 `isinstance(data, dict)`，非 dict 抛受控 `EgressProbeError("probe_bad_response")`（`services/egress_probe.py:146`）；独立复现确认：`MockTransport` 返回 `json=[]` 时现为 `EgressProbeError code=probe_bad_response`，不再是 `AttributeError`。`probe_proxy_egress` 对非 `EgressProbeError` 异常兜底记 failed 观测（`error_code="probe_failed"`）后返回 200（`profile_service.py:963-985`）；集成测试 `test_probe_runner_unexpected_error_records_failed_not_500` 用抛 `AttributeError` 的 runner 实测手动探测返回 200 且 `observation_status == "failed"`，已在 122 passed 内。`_probe_safely` 日志改记真实异常类型与消息并带 `exc_info=True`（`:1052-1062`）；全仓 `"probe_error"` 写死常量零命中。
  - t052_code_f003（minor，`run_egress_probe` CC 约 24）——已消除。已拆为编排器 + 8 个小函数（`docker_adapter.py:463-760`）；同口径 AST 粗测：编排器 CC~3，`_create_probe_helper` 6、`_exec_probe_helper` 7、`_parse_probe_output` 7、`_cleanup_probe_resources` 5，其余 1–3，均 <15；13 个 fake-docker 测试全绿（在 122 passed 内）。拆分后 `_parse_probe_output` 对非 dict 输出同样抛受控错误，与 f002 口径一致。
  - t052_code_f004（minor，`compressIpv6` CC 约 18）——已消除。已拆为 `splitCompressedIpv6` / `expandEmbeddedV4` / `longestZeroRun` / `renderCompressedIpv6` + 编排器 `compressIpv6`（`parseProxyUrl.ts:64-160`）；`compressIpv6` 本体约 CC 7（<15）；解析矩阵 55 passed 前后端对照通过。
  - t052_code_f005（minor，`list_proxies` N+1）——已消除。新增 `_current_observations`，一次 `WHERE proxy_id IN (...)` 取各代理最新观测行（`repository.py:1246-1280`），`list_proxies` 改走批量组装（`:1318`）；过期 ok 隐藏规则抽为 `_visible_observation` 与单行路径共用（`:1205`）；查询计数测试证实 3 代理由 3 次观测 SELECT 降为 1 次（`test_t052_observation_repository.py:141`，在 122 passed 内）。单行 `get_proxy` / 更新路径仍用 `_current_observation`，属单行查询，非 N+1。
  - t052_code_f006（minor，task.md  supervisor 测试计数 12）——已消除。`task.md:99` 现写 13 passed；实测 `test_t052_supervisor_probe.py` 13 个测试全部通过（在 122 passed 内）。
- 本轮新发现：1 条（minor 1 条，f007；无 critical / important）
- 未进表的提示：
  - 文件过大（按规则只列不进表）：`src/backend/cbrowser/supervisor/docker_adapter.py` 全文件 2693 行、`src/backend/cbrowser/services/profile_service.py` 1043 行、`src/frontend/src/features/proxies/ProxyFormDialog.tsx` 649 行、`src/frontend/src/features/proxies/parseProxyUrl.ts` 422 行——四者均在本 task 净增行数且超 400 行阈值（docker_adapter/profile_service 超 800 行 important 阈值），与 Round 1 结论相同；未见因过大导致的可观测缺陷。
  - 圈复杂度：`run_egress_probe` CC~3、`compressIpv6` CC~7，均已降至 15 以下；本轮无 ≥15 的新建/改动函数。
  - Round 1 结论段的后端端口正则边缘分歧仍在：后端 `_parse_port` 仍用 `\d+`（`domain/proxy_endpoint.py:85`，Python `\d` 含非 ASCII 数字），前端 `/^\d+$/` 只认 ASCII；日常无影响（UI 拒绝、直接调 API 才接受），仍只作提示，不进 finding。
  - AC-004 的聚焦编辑时输入框短暂显示完整链接（含密码明文值）为有意设计（`onLinkFocus`），静止态仍显示脱敏链接；与 Round 1 结论相同。
  - AC-007 的过期路径只做失效显示，过期本身不触发自动重探，需手动重试；与 Round 1 结论相同。
  - 命名锁死核查通过：`git grep` 全跟踪树 `com.cbrowser.deployment-id` 零命中（仅 `progress.md` 与 `docs/blueprint/decisions.md:342` 的历史叙述提及被驳回的偏离）；`resource_prefix` 默认值仍为 `cbrowser-t005`（`docker_adapter.py:234`），无 `"cbrowser"` 默认前缀；`git diff --check` clean。
  - 未发现范围外行为或顺手改进；`country_code` 可写字段移除无残留（Round 1 已核）。
- 总体判断：Round 1 的 2 条 important 与 4 条 minor 全部真实修复并经实跑验证，本轮仅新增 1 条 minor（f007 查询无界化，当前无可观测故障）；但 AC-012 仍为未打勾的 [deploy] AC，本机无 Docker/真实代理/公网出口无法验证，按机器门禁任一 TICK-VOID 即 FAIL，故本轮 verdict 仍为 FAIL——FAIL 的唯一驱动项是 AC-012 的部署验证缺口，不是代码缺陷。
- 系统性 follow-up：无（f007 为本 task 内可修复项，无跨 task 基础设施缺口）。

### AC 复验方式

- AC-001：TICK-VALID，re_verified。弹窗默认只渲染链接/备注/只读国家状态，高级区默认折叠且无国家输入；前端 4 文件 96 passed 实跑。
- AC-002：TICK-VALID，re_verified。前后端解析器矩阵一致（四格式、IPv6、特殊字符密码）；后端 53 + 前端 55 均实跑通过。
- AC-003：TICK-VALID，re_verified。链接↔高级字段双向同步代码核对，前端相关测试实跑通过。
- AC-004：TICK-VALID，re_verified。响应/缓存/日志均不含密码，静止态显示脱敏链接；集成测试 18 passed 实跑。
- AC-005：TICK-VALID，re_verified。名称默认 host:port，手动名经 nameTouched 保护；前端相关测试实跑通过。
- AC-006：TICK-VALID，re_verified。三处展示位 pending 时均渲染“检测中”（f001 已消除）；3 个 pending 夹具测试实跑通过； exploding-runner 集成测试证实手动探测异常返回 200 且记 failed 观测，可重试。
- AC-007：TICK-VALID，re_verified。端点/凭据变更记 pending 行并自动重探，过期 ok 行经 `_visible_observation` 隐藏；仓库观测测试 4 passed 实跑。
- AC-008：TICK-VALID，re_verified。探测在 helper 内经代理访问回显，受控回显+代理夹具集成测试实跑通过，观测取代理出口而非 API 出口。
- AC-009：TICK-VALID，re_verified。探测路由拒绝非空 body（422），服务端只按已存端点执行；负向集成测试实跑通过。
- AC-010：TICK-VALID，re_verified。loopback 映射 + 策略仅放行映射地址:端口；13 个 fake-docker 测试实跑通过；真实 Docker daemon 行为本机无环境，未验证。
- AC-011：TICK-VALID，re_verified。映射失败时启动与探测两路均在执行前抛 LoopbackMappingError 并附处置提示；fake-docker 测试实跑通过；真实 daemon 拒绝行为本机无环境，未验证。
- AC-012：TICK-VOID，trust_prior。未打勾的 [deploy] AC，本机无 Docker/真实代理/公网出口，无法验证，依赖用户机真实部署端到端验证。

coverage = 11 / 12

verdict: FAIL

## Round 3 (2026-11-11T14:22:38+08:00)

- round：3
- reviewed_at：2026-11-11T14:22:38+08:00

reviewed_scope: 591b901c2b3f608a

复核方法：落点仓库校验通过（`git -C '<home>/workspace/CBrowser_t052' rev-parse --show-toplevel` = `<home>/workspace/CBrowser_t052`）；逐条按 diff/代码/实跑核实，不采信 `progress.md` 处置表自述。实跑：后端 t052 全套 7 个文件 123 passed（`~/workspace/.cb-venv-t051/bin/python`，`PYTHONPATH=<worktree>/src/backend`，34.19s，较 Round 2 的 122 passed 增加恰好 1 个，即 f007 新增测试）；前端 4 个相关文件 96 passed（Node 26.13.0，`npx vitest run`，11.49s，与 Round 2 持平）。

## Findings

本轮新发现：0 条。

## 结论

- 前轮 finding 复核（Round 2 code 仅 1 条 minor）：
  - t052_code_f007（minor，`_current_observations` 无界取全部历史观测行）——已消除。`repository.py:1246-1296` 的 `_current_observations` 现用 `ROW_NUMBER() OVER (PARTITION BY proxy_id ORDER BY observed_at DESC, created_at DESC, id DESC)` 子查询取每代理 rn=1 的 id，外层单次 SELECT 取行；实测新测试 `test_list_proxies_fetches_only_latest_observation_row_per_proxy`（`tests/unit/test_t052_observation_repository.py:183`）通过：3 代理各 3 行历史观测（共 9 行）时列表仍返回各代理最新一行（pending，`country_code`/`egress_ip` 均为 None），观测 SELECT 恰好 1 次，物化观测行恰好 3 行。测试断言本身真实：返回值断言（最新 pending 行）+ 语句计数断言（1 次 SELECT）+ `load` 事件计数断言（3 行物化），无恒真断言、无 mock 被测逻辑。排序口径与单行路径 `_current_observation`（`LIMIT 1`，`repository.py:1225-1243`）一致，`id DESC` 只作精确并列时的确定性决胜；`_visible_observation` 过期隐藏规则在批量路径逐行复用，与单行路径共用同一函数。未引入保留期清理（处置表已明说不引入，与 f007 建议的二选一相符；历史行仍无限累积，但列表查询已不再搬运它们，属已知非阻塞欠账）。
  - Round 1 的 6 条 finding 仍消除（抽查核实，未复发）：f001 三处展示位仍按 `observation_status === "pending"` 渲染“检测中”（`ProxyTable.tsx:82`、`ProxyFormDialog.tsx:430`、`SessionDetailsPanel.tsx:158`，i18n 键 `proxyCountryProbing`）；f002 `probe_bad_response` 校验仍在（`services/egress_probe.py:146`），`"probe_error"` 写死常量全仓 `src/backend/` 零命中，`probe_failed` 兜底仍在（`profile_service.py:980`）。
- 本轮新发现：0 条（无 critical / important / minor）
- 未进表的提示：
  - 文件过大（按规则只列不进表）：`src/backend/cbrowser/supervisor/docker_adapter.py` 全文件 2693 行、`src/backend/cbrowser/services/profile_service.py` 1065 行、`src/frontend/src/features/proxies/ProxyFormDialog.tsx` 653 行、`src/frontend/src/features/proxies/parseProxyUrl.ts` 439 行——四者均在本 task 净增行数且超 400 行阈值（docker_adapter/profile_service 超 800 行 important 阈值）。注意：Round 1/2 报告所列后三者行数（1043/649/422）为 stale 数字（系 Round 1 测量值被 Round 2 原样沿用），本次实测为 1065/653/439，差值来自 Round 1 修复本身（f001/f002/f004 的新增分支与拆分），不是 Round 2 之后的新改动；未见因过大导致的可观测缺陷。
  - 排序决胜口径的微小不一致（不进 finding，无可观测缺陷）：批量路径在 `observed_at` 与 `created_at` 均精确并列时以 `id DESC` 决胜，单行路径无第三排序键；且观测行 `id` 为随机 UUID（`models.py:75`，`id=str(uuid.uuid4())`），`id DESC` 是确定性但非“最新插入”的决胜。两条时间戳均为微秒精度 ISO 字符串（`utc_now_iso`），精确并列需两次记录落在同一微秒内，现实中无法触发；列表与单行路径因此不会实际分歧。建议后续如统一口径，两路共用同一排序键即可。
  - Round 1/2 结论段的其余提示仍在：后端 `_parse_port` 仍用 `\d+`（Python `\d` 含非 ASCII 数字）与前端 `/^\d+$/` 的边缘分歧；AC-004 聚焦编辑时输入框短暂显示完整链接为有意设计；AC-007 过期只做失效显示、不自动重探，需手动重试。
  - 命名锁死核查通过：`com.cbrowser.deployment-id` 在 `src/`、`config/`、`scripts/`、`compose.yaml` 中零命中，全仓仅 `docs/blueprint/decisions.md:342` 的历史叙述中提及被驳回的偏离；`resource_prefix` 默认值仍为 `cbrowser-t005`（`docker_adapter.py:234`）；`git diff --check` clean。
  - 未发现范围外行为或顺手改进；修复改动面仅限 `repository.py` 的 `_current_observations` 与 1 个后端单测文件（与处置表所述一致，前端零改动）。
- 总体判断：Round 2 唯一遗留 minor f007 已真实修复并经实跑验证，本轮零新发现；AC-012 已按本链既定口径（环境跑不了的验证跳过按 pass 计、在 task 记录中如实注明）打勾，`task.md:61` 现为 `- [x]`，`progress.md`「环境跳过」明文写清“本机未验证、不得记为已验，须在用户机真实部署验证”，替代验证证据真实存在（受控回显+代理夹具集成测试 18 passed、supervisor fake-docker 测试 13 passed，均在本轮 123 passed 内实跑通过），与 t051 前例（AC-013 整项跳过但打勾，Round 2 审阅记 TICK-VALID trust_prior）口径一致，故 AC-012 判 TICK-VALID trust_prior。本轮 verdict 为 PASS；真实部署端到端仍须在用户机验证，该欠账已登记在 progress.md，不属代码缺陷。
- 系统性 follow-up：无。

### AC 复验方式

- AC-001：TICK-VALID，re_verified。弹窗默认只渲染链接/备注/只读国家状态，高级区默认折叠且无国家输入；前端 4 文件 96 passed 实跑。
- AC-002：TICK-VALID，re_verified。前后端解析器矩阵一致（四格式、IPv6、特殊字符密码）；后端 53 + 前端 55 均实跑通过。
- AC-003：TICK-VALID，re_verified。链接↔高级字段双向同步代码核对，前端相关测试实跑通过。
- AC-004：TICK-VALID，re_verified。响应/缓存/日志均不含密码，静止态显示脱敏链接；集成测试 18 passed 实跑。
- AC-005：TICK-VALID，re_verified。名称默认 host:port，手动名经 nameTouched 保护；前端相关测试实跑通过。
- AC-006：TICK-VALID，re_verified。三处展示位 pending 时均渲染“检测中”（f001 已消除且本轮抽查仍在）；3 个 pending 夹具测试实跑通过。
- AC-007：TICK-VALID，re_verified。端点/凭据变更记 pending 行并自动重探，过期 ok 行经 `_visible_observation` 隐藏；仓库观测测试 5 passed 实跑（含 f007 新增测试）。
- AC-008：TICK-VALID，re_verified。探测在 helper 内经代理访问回显，受控回显+代理夹具集成测试实跑通过，观测取代理出口而非 API 出口。
- AC-009：TICK-VALID，re_verified。探测路由拒绝非空 body（422），服务端只按已存端点执行；负向集成测试实跑通过。
- AC-010：TICK-VALID，re_verified。loopback 映射 + 策略仅放行映射地址:端口；13 个 fake-docker 测试实跑通过；真实 Docker daemon 行为本机无环境，未验证，留待用户机部署验证。
- AC-011：TICK-VALID，re_verified。映射失败时启动与探测两路均在执行前抛 LoopbackMappingError 并附处置提示；fake-docker 测试实跑通过；真实 daemon 拒绝行为本机无环境，未验证。
- AC-012：TICK-VALID，trust_prior。[deploy] AC 已按链口径打勾（task.md:61 为 [x]）；本机无 Docker/真实代理/公网出口无法独立复验，依赖的替代证据为集成测试 18 passed（受控回显+代理夹具）与 supervisor fake-docker 测试 13 passed（均在本轮实跑内），progress.md「环境跳过」明文“本机未验证、不得记为已验，须在用户机真实部署验证”，与 t051 AC-013 前例口径一致。

coverage = 11 / 12

verdict: PASS
