# Task review t064（reviewer_focus: 测试）

- task：`t064_session_auth_cdp_boundary`
- spec：`docs/tasks/t064_session_auth_cdp_boundary/task.md`
- diff_anchor：`680d850067075caf9356ee6c71771f6dc779c543`
- target：`git -C '/home/hatch/workspace/CBrowser_t064' diff 680d850067075caf9356ee6c71771f6dc779c543`
- round：1
- reviewed_at：2026-11-14T00:37:00+08:00

reviewed_scope: e979cc1914d912d9

## Findings

### t064_test_f001 - Gateway 集成层无「过期 grant 被拒」用例，过期仅在 shared 单元层覆盖

- 严重度：minor
- 锚点：AC-001「未授权/过期/撤销/跨 Profile viewer 握手被拒」
- 位置：`tests/integration/test_gateway_signaling.py:144`（`test_viewer_handshake_rejections_leave_no_session` 的拒绝矩阵无过期 grant 一例）；对照 `tests/unit/test_shared_viewer_grants.py:52`（`test_expired_grant_is_rejected`）、`src/backend/cbrowser/gateway/server.py` 验签调用点（diff 内 `grant_authority.verify(grant, profile_id)`）
- 问题：Gateway 拒绝矩阵已覆盖无 grant（401）、只有 Cookie（401）、伪造 grant（403）、跨 Profile（403）、可信头不一致（403）、坏 Origin（403）与未就绪（503），唯独「过期」只在 `ViewerGrantAuthority.verify` 单元层以注入 `now` 验证。Gateway 与单元层共用同一生产 `verify`、且 TTL 常量由 `tests/unit/test_shared_viewer_grants.py:27` 断言为 60 秒，属组合覆盖成立但集成层少一例的缺口，不是 AC 无覆盖，故标 minor。
- 建议：harness 支持以过去时刻签发 grant（`grant_authority.mint(profile_id, now=...)` 回拨 61 秒）后补一条 Gateway 403 用例，或在测试注释中明确声明过期由单元层＋同一 verify 调用点组合覆盖。

### t064_test_f002 - AC-004 的「信令/错误不提供 CDP 凭据」面无直接断言，仅页面数据面有覆盖

- 严重度：minor
- 锚点：AC-004「普通 viewer 页面/信令/错误不提供可用 CDP 连接凭据」
- 位置：`tests/integration/test_automation_api.py:61`（`test_ordinary_profile_surfaces_do_not_leak_cdp_endpoint_or_token` 只断言 Profile detail/list 响应）；对照 `src/backend/cbrowser/api/v1/automation_router.py:50`（全仓 `cdp_ws_path` 唯一产生点）
- 问题：新增不泄漏断言只覆盖普通 Profile 的 detail/list 两个响应面；AC-004 点名的信令握手响应与错误响应没有「不含 cdp_ws_path/token」的直接断言。经全仓 grep 核实 `cdp_ws_path` 仅由专用 Automation 状态端点产生、Gateway 信令错误体为固定文本，结构上无泄漏路径，故仅为断言面不完整，标 minor。
- 建议：顺手在 Gateway 拒绝用例或 Profile 错误响应（如不存在 Profile 的 404）上各加一条 `cdp_ws_path`/token 不出现的断言，把 AC-004 三个面都钉住。

### t064_test_f003 - 新增交付文件未做 git add -N，规定的 diff 命令看不到核心交付

- 严重度：minor
- 锚点：review scope 完整性（派审前须对新交付文件执行 `git add -N`）
- 位置：`git status --short` 的 `??` 项：`src/backend/cbrowser/api/internal_edge.py`、`src/backend/cbrowser/shared/viewer_grants.py`、`tests/integration/test_edge_viewer_authorize.py`、`tests/unit/test_shared_viewer_grants.py`、`tests/unit/test_t064_edge_caddyfile.py`、`docs/pending/todo/p094_t064_local_edge_cdp_verification.md`、`docs/spikes/s018_edge_viewer_authorization_proof/`、`docs/spikes/s019_chromium_loopback_host_origin_boundary/`
- 问题：全部新增实现与测试文件仍是未跟踪状态，单独执行 `git diff 680d850` 时不包含它们；本次审阅靠文件系统直读才看到完整交付。指纹（reviewed_scope）覆盖未跟踪内容、文件本身可读，故不构成 INCOMPLETE，但任何只跑 diff 的复核者都会漏审核心文件（与 t062_test_f005 同型）。
- 建议：实施方对上述新交付文件执行 `git add -N` 后再派下一轮审阅。

## 结论

- 改测方向复核：逐项核对了 diff 中全部既有测试改写，结论为「整体换语义」而非就地改预期追随输出，无迁就实现的改测。具体判定：① `tests/integration/test_gateway_signaling.py` 保留原测试名与结构（基线与现版同为 `test_viewer_handshake_rejections_leave_no_session` 等），拒绝矩阵由 Cookie 语义整体换成 grant 语义且断言加密（新增只有 Cookie 401、伪造 403、跨 Profile 403、可信头不一致 403、未就绪两段 503），理由已在 progress 预告；② `tests/integration/test_auth_api.py::test_internal_gateway_endpoints` 删除旧 viewer-authorize 的 valid/bad-origin 断言、改为运行时面鉴权探针＋旧端点 404，被删语义由新文件 `tests/integration/test_edge_viewer_authorize.py` 在边缘层等价补回（happy path、坏 Origin、未知 Profile、登出撤销）；③ `tests/integration/test_internal_service_config.py` 探针面由 viewer-authorize 换成 runtime 端点，token 独立性断言由「viewer 200/allowed False」换成「runtime 404（已过 bearer 校验）」，未配置 503 语义由边缘端点未配置用例补回；④ Gateway harness（`tests/integration/test_gateway_fixtures.py`、`tests/fixtures/supervisor_recovery_probe/gateway_service.py`、`tests/unit/test_baseline_fixture_regressions.py`）删 FakeApi 的 viewer-authorize 面、改本地用生产 `ViewerGrantAuthority` 签发 grant，是机制迁移的夹具跟随，断言未弱化；⑤ e2e `test_gateway_ac001_auth_e2e.py` 删除旧 Gateway Cookie 拒绝体与 Gateway 日志断言（拒绝已前移到边缘、旧前提失效，progress 已说明），代之以状态码契约断言并新增伪造边缘头 401 与外部解析端点 404 两例、管理 Cookie 新增 `path == "/"` 断言——属已披露的语义迁移，但该文件云端未实跑（见 AC-006 顺延），其断言正确性待 p094 实跑证伪/证实。
- 危险模式扫描：新增与改动的测试中未命中恒真断言、删/反转 expect（上条已逐项归因的规格迁移除外）、注释掉断言、弱化断言、`.skip`/`.only`/`pytest.mark.skip` 新增、`type: ignore` 新增、mock 被测逻辑、阈值掩盖或条件跳过弱化断言；删除的测试面（旧 viewer-authorize HTTP 层、FakeApi viewer 面）均有新语义层等价或更高层替代，覆盖未丢。新测试均触达生产实现：grant 单元直测生产 `ViewerGrantAuthority`、边缘集成走真实 `create_app`＋TestClient＋真实 DB 登录/登出、Gateway 集成走真实 `create_gateway_app` 的 aiohttp 握手、Caddyfile 契约测生产 `generate_caddyfile` 渲染产物，mock 仅在 HTTP/容器边界。
- 复验摘要（本 reviewer 独立执行，落点 `git rev-parse --show-toplevel` = `/home/hatch/workspace/CBrowser_t064`，gate venv Python、`PYTHONPATH=src/backend:tests/fixtures`、`-n 0` 串行）：① `test_shared_viewer_grants.py`＋`test_t064_edge_caddyfile.py`＋`test_edge_viewer_authorize.py` 共 27 passed（与 progress 声称的 grant 15 例、边缘 8 例逐项对上：grant 文件 8 个测试函数＋7 例参数化垃圾输入 = 15）；② `test_gateway_signaling.py` 三例（拒绝矩阵、Agent register 坏 token、viewer 节流）＋`test_automation_api.py` 全文件＋`test_auth_api.py::test_internal_gateway_endpoints`＋`test_internal_service_config.py` 全文件共 18 passed；③ AC-005 回归抽跑 `test_agent_executor_refs.py`＋`test_agent_executor_cli.py` 共 27 passed；④ e2e 两文件 collect-only 14 例无错误（全树 102 例的数字未独立复跑，属 trust_prior）。合计独立实跑 72 passed＋14 collect。
- 非绿定性核实：`test_t060_gate_boundaries.py::test_local_topology_profile_does_not_require_public_geoip` 本轮单跑仍 FAILED，签名与 progress 声称逐字一致（`tests/fixtures/gateway_probe/topology.py:674` 的 `AttributeError: 'GatewayTopologyHarness' object has no attribute 'data_dir'`），定性为基线继承成立。其余非绿项（repo_hygiene/fontconfig 的 pristine 同签名复现、a16 的 npm ci 后单文件 15 passed、integration 16 errors 的串行分批复跑全过、前端四套件与 protocol_drift 修正环境后复跑全过、全量门禁总数 257/2031+64/183+2）本轮未逐项复跑，依赖 progress 记录与证据模式，属 trust_prior，不影响本 task 新增测试的可信判定。
- 本轮新发现：3 条（0 critical、0 important、3 minor）。
- 未进表的提示：① progress 实施笔记称 supervisor_recovery_probe 的 `FakeGatewayApiClient` 存在「重复类定义（第二份遮蔽第一份）已删被遮蔽份」，但直查基线 680d850 的 `tests/fixtures/supervisor_recovery_probe/gateway_service.py` 只有一份该类定义（基线第 57 行、现版第 61 行，类内方法亦无重复），该笔记与基线不符——属实施记录订正事项（code 轴/实施侧），不影响测试覆盖与本轴判定。② AC-001 中「过期会话」在边缘层无专门用例（只有缺失/伪造会话 401 与登出撤销 401），会话过期判定由未改动的 `AuthService.authorize_viewer` 既有覆盖承接，组合成立，仅作提示。
- 总体判断：旧测试改写均为预告过的整体语义迁移且新语义覆盖完整（无 grant、只有 Cookie、伪造、跨 Profile、可信头不一致、坏 Origin、就绪、登出撤销、旧端点 404、未配置 503、Agent register 回归、普通 Profile 不泄漏 cdp_ws_path 均有真实测试），本 reviewer 独立实跑 72 例全绿；[deploy] 四条 AC 的打勾按「云端验足＋p094 顺延」口径成立且顺延如实（progress 与收尾报告均明写真实 Caddy/Chrome 链未跑、登记 p094），无未解决 critical/important，test 轴 verdict PASS。
- 系统性 follow-up：无（[deploy] 顺延已登记 p094，不重复建议）。

### AC 复验方式

- AC-001：TICK-VALID，re_verified。task.md 已打勾；云端部分经独立复跑成立——grant 单元 15 例（绑定/过期/防伪造/无会话材料）、边缘集成 8 例（含登出撤销后 401）、Gateway 拒绝矩阵与合法握手建隧道、Caddyfile 契约断言 Cookie 删除且 e2e 断言管理 Cookie Path=/ 不变；真实 Caddy/Chrome 链按 [deploy] 顺延 p094（pending 实存、内容覆盖登录/首帧/重连/退出撤销）。
- AC-002：TICK-VALID，re_verified。task.md 已打勾；Caddyfile 契约（内部路径 404 先于 /api 代理、signal 路由先删伪造头再 forward_auth）、边缘端点证明校验（缺/错证明 403、未配置 503）、Gateway 直连无 grant 401/伪造 403、Agent register 独立认证回归均在本轮复跑集合内通过；真实拓扑顺延 p094。
- AC-004：TICK-VALID，re_verified。task.md 已打勾；普通 Profile detail/list 不含 cdp_ws_path 与 token 的新断言、专用 Automation 状态端点唯一披露、automation token 拒绝矩阵在本轮复跑集合内通过（信令/错误面的断言缺口见 f002，minor）；真实引擎 Host/Origin 负向例 `test_t064_cdp_loopback_host_origin_boundaries` 已写且 collect-only 通过（本轮实证两 e2e 文件共 14 例收集无错误），实跑顺延 p094。
- AC-005：TICK-VALID，re_verified。task.md 已打勾；diff 未触达 snapshot/wait_for/extract 与同源客户端代码（`git diff 680d850 --name-only` 无 agent_executor/session 与前端同源文件），既有 wait_for/extract 链测试存在于 `tests/integration/test_agent_executor_chain.py`，本轮抽跑 executor refs/cli 单元 27 passed；integration 全链与前端套件的通过数字采信 progress 门禁记录。
- AC-006：TICK-VALID，trust_prior。task.md 已打勾；云端仅完成前置（真实拓扑 harness 与 e2e 用例已按新流改写、collect-only 通过，本轮实证收集无错误），真实 Caddy/Chrome 登录/首帧/重连/退出撤销/认证自动化与 WebRTC UDP 均未实跑——progress 与收尾报告对此如实表述并登记 p094 补验，未冒充已验；打勾按 [deploy] 顺延口径（与 t062 先例一致）成立，但本 AC 的行为证据全部待 p094 落地后才可复验。

coverage = 4 / 5

建议合并前人工抽查 trust_prior 项

verdict: PASS

## Round 2

- round：2
- reviewed_at：2026-11-14T00:49:00+08:00
- 落点：`git rev-parse --show-toplevel` = `/home/hatch/workspace/CBrowser_t064`，分支 `t064_session_auth_cdp_boundary`；Python 为 `/home/hatch/workspace/CBrowser/.scratch/gate_venv/bin/python`，`PYTHONPATH=src/backend:tests/fixtures`，全部复跑串行 `-n 0`。
- 范围：只复核 Round 1 本轴三条 minor 的修复、抽验 code 轴 f001 的修复证据面、核对 progress 的 Round 1 修复复验数字，并对 AC-001 与 AC-006 重新判定 TICK；其余 AC 沿用 Round 1 判定并注明。本轮未改实现、测试或除本文件外的任何文档。

### 逐条复核结论

- t064_test_f001（Gateway 集成层缺过期 grant 用例）：**已修确认**。直读 `tests/integration/test_gateway_signaling.py:207-217`：拒绝矩阵在可信头不一致 403 之后新增过期一例，注释「An expired grant (minted beyond its 60-second TTL) -> 403」，以 `harness.grant_authority.mint(profile_id, now=time.time() - 3600)` 签发（回拨 3600 秒，远超 `src/backend/cbrowser/shared/viewer_grants.py:32` 的 `GRANT_TTL_SECONDS = 60`；`mint` 的 `now` 参数与 `exp = issued + GRANT_TTL_SECONDS` 见同文件 `:79`、`:85`），断言握手抛 `WSServerHandshakeError` 且 `status == 403`。签发用的 `grant_authority` 与 harness 的 Gateway 验签同源（Round 1 已核）。本轮单跑该拒绝矩阵用例 1 passed、全文件 16 passed（见实跑），过期例在通过集合内。此前「过期仅单元层覆盖」的组合缺口已在集成层闭合。
- t064_test_f002（AC-004 信令/错误面无 CDP 断言）：**已修确认**。直读 `tests/integration/test_gateway_signaling.py:220-229`：同一拒绝矩阵用例内新增段，注释「Rejection responses carry no CDP material (t064 AC-004)」，对信令 URL 以普通 HTTP GET 复现两类拒绝——无 grant 得 401、伪造 grant 得 403——并各断言 `"cdp" not in (await resp.text()).lower()`。`cdp` 子串断言覆盖 `cdp_ws_path` 与任何含 cdp 字样的端点/凭据名泄漏，与 progress 处置行（`progress.md:75`「补 401/403 拒绝响应体无 cdp 断言」）逐字对上。本轮实跑通过（同上 1 passed / 16 passed）。说明一点边界：该断言钉的是拒绝响应体不含 CDP 材料标识，裸 token 值本身不带 cdp 字样不在此断言射程内，但 Round 1 已全仓核实 Gateway 信令错误体为固定文本、无 token 产生路径，此射程与风险面相符，不另立 finding。
- t064_test_f003（新文件未跟踪、单独 diff 不可见）：**已修确认（按处置口径）**。`progress.md:76` 的 Round 1 处置行已写明「收尾时全部交付文件 git add 暂存（finish 前置动作）」，与本轮派审口径一致：暂存发生在 finish 前，复核时点不验证暂存本身。本轮 `git status --short` 实见核心新文件仍为 `??`（`src/backend/cbrowser/api/internal_edge.py`、`src/backend/cbrowser/shared/viewer_grants.py`、`tests/unit/test_t064_edge_caddyfile.py` 等），属 finish 前的预期状态，不据此判未修；提醒 finish 时须按该行执行暂存，否则 f003 在归档口径上重新打开。
- t064_code_f001 修复证据面抽验（code 轴 critical，非本轴 finding）：**抽验通过**。实现侧 `src/backend/cbrowser/network_config.py:92-93` 的 `handle /stream/*/signal` 块内已整体包入 `route {{`，删伪造头（`:94-95`）→ `forward_auth`（`:97`）→ `reverse_proxy`（其后，含 `header_up -Cookie`）按声明序排列，文件内注释亦写明 route 保序理由。契约测 `tests/unit/test_t064_edge_caddyfile.py:38-42` 新增断言：`"route {" in signal`、删 `X-CBrowser-Viewer-Grant` 头的位置先于 `forward_auth`、`forward_auth` 先于 `reverse_proxy`。本轮单跑该文件 4 passed。渲染契约层面的保序证据成立；真实 Caddy 适配/握手留证仍归 p094（见 AC-001/006 判定），本抽验不冒充真实链已验。
- progress Round 1 修复复验数字核对（`progress.md:78`：一组 54 passed、一组 23 passed）：**两组均逐字复现**（派审只要求抽一组，本轮两组都跑了）。54 passed 组＝`test_t064_edge_caddyfile`＋`test_edge_viewer_authorize`＋`test_gateway_signaling`＋`test_automation_api`＋`test_runtime_agent_protocol_export`＋`test_t054_deploy_network_config`，本轮实跑 54 passed；23 passed 组＝`test_t054_origin_whitelist_deploy`＋`test_a25_compose_secret_mounts`＋`test_shared_viewer_grants`，本轮实跑 23 passed。数字与 progress 声称完全一致，无虚报。

### 实跑命令与实数

落点均为 `cd ~/workspace/CBrowser_t064` 之后，命令前缀统一为 `PYTHONPATH=src/backend:tests/fixtures /home/hatch/workspace/CBrowser/.scratch/gate_venv/bin/python -m pytest <targets> -n 0 -q`：

|目标|结果|
|---|---|
|`tests/unit/test_t064_edge_caddyfile.py`|4 passed in 0.72s|
|`tests/integration/test_gateway_signaling.py::test_viewer_handshake_rejections_leave_no_session`|1 passed in 3.20s|
|`tests/integration/test_gateway_signaling.py`（全文件）|16 passed in 18.44s|
|`tests/integration/test_t054_origin_whitelist_deploy.py`＋`tests/unit/test_a25_compose_secret_mounts.py`＋`tests/unit/test_shared_viewer_grants.py`（progress 23 passed 组）|23 passed in 14.13s|
|`tests/unit/test_t064_edge_caddyfile.py`＋`tests/integration/test_edge_viewer_authorize.py`＋`tests/integration/test_gateway_signaling.py`＋`tests/integration/test_automation_api.py`＋`tests/unit/test_runtime_agent_protocol_export.py`＋`tests/unit/test_t054_deploy_network_config.py`（progress 54 passed 组）|54 passed in 113.26s|

各次调用相互重叠（拒绝矩阵用例同时计入全文件与 54 passed 组），不做跨调用加总；可独立引用的总数是两组 progress 数字 54＋23 与两个单文件数字 4、16。

### AC TICK 判定（Round 2）

- AC-001：**TICK-VALID，re_verified（云端组装层）**。task.md 已重新打勾。Round 1 时 code 轴因 Caddyfile 指令重排判 TICK-VOID，其根因本轮经抽验确认已除：渲染产物 signal 块 route 保序（实现 `:92-97`＋契约断言 `:38-42`＋单跑 4 passed），合法握手在组装后的边缘契约上不再被删头切断；本轴 f001 修复又补齐「过期」在 Gateway 集成层的直接证据（403，实跑通过），AC-001 点名的未授权/过期/撤销/跨 Profile 在云端各层均有实测（grant 单元、边缘集成含登出撤销、Gateway 拒绝矩阵全量、合法握手建隧道均在 54 passed 组内）。真实 Caddy/Chrome 链仍未实跑，按 `[deploy]`＋p094 口径顺延成立：`docs/pending/todo/p094_t064_local_edge_cdp_verification.md` 实存，内容覆盖真实 Caddy 边缘拒绝、Cookie `Path=/`、合法登录/首帧/重连/退出撤销。在此口径下打勾成立。
- AC-006：**TICK-VALID，云端前置 re_verified、真实链 trust_prior**。task.md 已重新打勾。Round 1 本轴判 TICK-VALID（trust_prior）、code 轴因同一 f001 判 TICK-VOID；f001 修复后，阻断真实链合法握手的已知缺陷已在渲染契约层排除，harness 与 e2e 用例按新流就绪的状态未变，54 passed 组复跑全过。打勾按 `[deploy]`＋p094 顺延口径成立，但须明记：登录、首帧、重连、退出撤销、认证自动化与 WebRTC UDP 的真实链行为证据仍全部待 p094 落地，本判定不表示真实链已验。
- AC-002：TICK-VALID，沿用 Round 1（re_verified）。本轮 54/23 两组复跑含边缘解析、Gateway 直连拒绝、t054 部署网络配置等相关文件且全过，无回归迹象；真实拓扑部分顺延 p094 不变。
- AC-004：TICK-VALID，沿用 Round 1 判定且本轮因 f002 修复补强。信令/错误面原为 Round 1 唯一断言缺口，现已有 401/403 拒绝响应体无 `cdp` 的直接断言并实跑通过；其余面（普通 Profile detail/list 不泄漏、真实引擎 Host/Origin 负向例顺延 p094）与 Round 1 相同。
- AC-005：TICK-VALID，沿用 Round 1（re_verified）。Round 1 之后的全部修复改动（Caddyfile route、signaling 测试补例、specs 顺序句、内部 schema 声明）均未触 snapshot/wait_for/extract 与同源客户端面，沿用成立。

coverage = 5 / 5

### Round 2 结论

- 本轮新发现：0 条。Round 1 本轴三条 minor（f001/f002/f003）全部确认已修，code 轴 critical f001 的修复证据面抽验通过，progress 的 54 passed＋23 passed 两组复验数字均独立复现。
- 总体判断：测试轴在 Round 1 提出的覆盖缺口已逐项闭合，且闭合方式均为新增真实断言/用例而非改预期或弱化断言（过期例走生产 `mint`＋真实 Gateway 握手、CDP 断言走真实拒绝响应体、Caddyfile 断言走生产 `generate_caddyfile` 渲染产物）；AC-001 与 AC-006 在 `[deploy]`＋p094 口径下重新打勾成立，真实链未验的事实在 progress、p094 与本节中均如实保留。

verdict: PASS

## Round 3

- round：3
- reviewed_at：2026-11-14T02:38:37+08:00
- reviewed_scope: 3cd6ec932d29a297
- 落点：`git rev-parse --show-toplevel` = `/home/hatch/workspace/CBrowser_t064`，分支 `t064_session_auth_cdp_boundary`，diff 基线 `680d850067075caf9356ee6c71771f6dc779c543`。
- 确认范围与方法：本轮为确认轮，不全量重审、不改实现。只做三件事——独立复算 reviewed_scope 指纹、核对 Round 2 审阅字节与当前交付字节的同一性、独立复跑 progress.md 记载的两组定向套件；AC 判定沿用 Round 2 结论，仅按门禁格式在本轮小节重新逐条列出。
- 指纹复算：在 worktree 内运行 `review_scope_fingerprint('680d850067075caf9356ee6c71771f6dc779c543', 'docs/tasks/t064_session_auth_cdp_boundary')`（`.repo_template/scripts` 的 `repo_task.monitoring`），独立复算值为 `3cd6ec932d29a297`，与主会话实算值一致；Round 1/2 报告中的旧指纹 `e979cc1914d912d9` 为 Round 1 修复前的时点指纹，本轮以复算值替换确认。
- 字节同一性核对：交付内容文件（实现、测试与长期文档，不含 progress/review 过程文件）的最新 mtime 为 2026-11-14 00:44:32 CST（`docs/blueprint/gateway.md`），其余均不晚于此时点，全部早于 Round 2 两份报告的落盘时间（review_test.md 00:49:40 CST、review_code.md 00:51:37 CST）。即 Round 2 审阅的字节与当前交付字节为同一批，Round 1 修复后未再发生交付内容变更，字节同一性成立。
- 定向套件复跑（本 reviewer 独立执行，命令口径与派审一致：`CBROWSER_GATE_ENV_READY=1`、`CBROWSER_GATE_SCRATCH=$PWD/.scratch/gate_scratch`、`PYTHONPATH=src/backend:tests/fixtures`、gate venv Python、`-q -p no:cacheprovider`）：54 组（`test_t064_edge_caddyfile.py`、`test_edge_viewer_authorize.py`、`test_gateway_signaling.py`、`test_automation_api.py`、`test_runtime_agent_protocol_export.py`、`test_t054_deploy_network_config.py`）实跑 **54 passed**；23 组（`test_t054_origin_whitelist_deploy.py`、`test_a25_compose_secret_mounts.py`、`test_shared_viewer_grants.py`）实跑 **23 passed**。两组实数与 progress.md 记载（54 与 23）逐字一致，无失败、无跳过异常。
- 本轮新发现：0 条；未改 Round 1/2 任何内容，未改实现、测试、progress 与 task.md。

### AC 复验方式（Round 3）

- AC-001：TICK-VALID，re_verified。本轮 54 passed 组复跑含 grant 单元、边缘集成（登出撤销后 401）、Gateway 拒绝矩阵与合法握手及 Caddyfile route 保序契约，云端证据成立；真实 Caddy/Chrome 链按 [deploy] 口径顺延 p094，未在本轮实跑、不表示已验。
- AC-002：TICK-VALID，re_verified。本轮 54/23 两组复跑含内部路径 404 与伪造头删除的 Caddyfile 契约、边缘证明校验、Gateway 直连拒绝、Agent register 回归与 t054 部署网络配置，全过；真实拓扑部分按 [deploy] 口径顺延 p094。
- AC-004：TICK-VALID，re_verified。本轮 54 passed 组含普通 Profile 不泄漏 cdp_ws_path/token 断言、信令拒绝响应体无 cdp 断言与 automation token 拒绝矩阵，全过；真实引擎 Host/Origin 负向实跑按 [deploy] 口径顺延 p094。
- AC-005：TICK-VALID，re_verified。Round 1/2 已核 diff 未触 snapshot/wait_for/extract 与同源客户端面，本轮字节同一性核对确认该面自 Round 2 后无变更，沿用判定成立。
- AC-006：TICK-VALID，trust_prior。云端前置（新流 harness 与 e2e 用例就绪、54 passed 组复跑全过）已经本轮复核，但真实 Caddy/Chrome 登录、首帧、重连、退出撤销、认证自动化与 WebRTC UDP 均未实跑，按 [deploy] 口径顺延 p094，本判定不表示真实链已验。

coverage = 5 / 5

verdict: PASS
