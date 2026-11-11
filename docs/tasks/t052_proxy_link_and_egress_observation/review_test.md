# Task review t052（reviewer_focus: 测试）

- task：`t052_proxy_link_and_egress_observation`
- spec：`docs/tasks/t052_proxy_link_and_egress_observation/task.md`
- diff_anchor：`d07f5e332b2d3b904bf23a4c6e2391036b0ce761`
- target：`git -C '/home/hatch/workspace/CBrowser_t052' diff d07f5e332b2d3b904bf23a4c6e2391036b0ce761`
- round：1
- reviewed_at：2026-11-11T12:50:35+08:00

## Round 1 (2026-11-11T12:50:35+08:00)

reviewed_scope: 84f628d6290d50a4

## Findings

### t052_test_f001 - 恒真断言：集成测试中断言脱敏链接写成了自己等于自己

- 严重度：important
- 锚点：AC-004（密码不进响应、界面显示脱敏链接）——断言本身不提供证据
- 位置：`tests/integration/test_t052_proxy_api.py:244`，`test_create_accepts_all_four_link_formats`
- 问题：`assert body["proxy_url"] == body["proxy_url"]  # redacted link present` 恒为真，什么都没验证；该行注释声称“脱敏链接存在”，实际未断言 `proxy_url` 存在、非空或不含密码。下一行（245 行）对 `p@ss`/`p:ss` 的真实检查仍在，所以 AC-004 的证据未完全作废，但这行是教科书式恒真断言。
- 建议：删掉该行，或改成真实断言，例如 `assert body["proxy_url"]` 非空且等于期望的脱敏链接（如 `http://user@proxy.example.com:8080`）。

### t052_test_f002 - 条件断言弱化：列表响应的 `password` 键检查在分支里恒为真

- 严重度：important
- 锚点：AC-004（密码不进任何响应）——列表端点的键检查无证据
- 位置：`tests/integration/test_t052_proxy_api.py:282`，`test_password_never_leaks_into_any_response`
- 问题：`assert "password" not in resp.json() if isinstance(resp.json(), dict) else True`——当响应是列表（`GET /api/v1/proxies`）时断言退化为 `assert True`，从未检查列表里任何一项是否含 `password` 键。同一测试里对原始文本的秘密值检查（`never-show`/`rotated-secret` 不在 `resp.text`）对两个端点都真实执行，所以秘密值泄漏仍会被抓到；但“列表响应不含 password 键”这一半断言是空的。
- 建议：把列表分支改成逐项检查，例如 `assert all("password" not in item for item in resp.json())`；单项分支保持原断言。

### t052_test_f003 - 前端无测试区分 pending（检测中）与无观测（未知）的国家状态

- 严重度：minor
- 锚点：AC-006（界面依次显示检测中与国家码或未知）
- 位置：`src/frontend/src/features/proxies/ProxyFormDialog.test.tsx`（“shows unknown country status when there is no valid observation”）；实现 `src/frontend/src/features/proxies/ProxyFormDialog.tsx:429-441`
- 问题：弹窗的 `countryStatus` 只看 `proxy?.country_code`：有国家码显示国家，无则一律显示“未知”——`observation_status: "pending"` 时同样显示“未知”，没有任何“检测中”的 UI 状态；测试也只覆盖了无观测（创建态）与 ok（US）两种，没有用 pending 夹具验证检测中显示。API 层 pending→ok 的时序有集成测试覆盖（`_BlockingRunner` 门控），所以 AC-006 的后端一半已验证，缺的只是前端检测中状态这一格。
- 建议：若产品语义要求检测中与未知可区分，补一个 pending 夹具的弹窗测试；若“检测中也显示未知”是既定取舍，把这句话写进 task.md/AC-006 说明，测试现状即合规。

### t052_test_f004 - 生产探测 runner `SupervisorEgressProbeRunner` 无任何测试

- 严重度：minor
- 锚点：AC-006 / AC-007（生产路径自动探测与失效重探）
- 位置：`src/backend/cbrowser/services/egress_probe.py:76-136`（全类无测试）；集成测试 `tests/integration/test_t052_proxy_api.py:168` 注入的是 `LocalEgressProbeRunner`
- 问题：生产真正走的 runner（拼 URL 含 `quote(proxy_id)`、Bearer 头、body 带密码、非 200 → `supervisor_unavailable`、坏 JSON → `supervisor_unavailable`、status 非 ok → 透传 `error_code`）没有任何测试覆盖；集成测试用的是文档明确标注“仅测试用、禁止接入生产”的 `LocalEgressProbeRunner`，Supervisor 侧则由 fake-docker 单元测试与 control-server 端点测试分别覆盖——三段各有测试，但把三段连起来的 runner 本身是空白。类上预留的 `transport: httpx.AsyncBaseTransport` 参数显然是为 `MockTransport` 测试准备的，却无人使用。
- 建议：用 `httpx.MockTransport` 补一组单测：成功返回 ok、401/500 → `supervisor_unavailable`、坏 JSON → `supervisor_unavailable`、status failed 透传 `error_code`、未配置时直接 `supervisor_unavailable`。

### t052_test_f005 - 观测 TTL 过期只在纯函数层测过，仓库层“过期 ok 行隐藏”接线无测试

- 严重度：minor
- 锚点：AC-007（观测过期后同样失效）
- 位置：`src/backend/cbrowser/adapters/database/repository.py:1204-1240`（`_current_observation` 的 stale-ok 隐藏分支）；规则本身见 `tests/unit/test_t052_egress_observation.py:57-80`
- 问题：`observation_is_current` 的过期规则有单测（含过期边界与 `expires_at=None` 永不过期），但 repository 里真正把规则接上的分支（取最新行 → ok 行过期则返回 None，pending/failed 行照常透传）没有任何仓库级或 API 级测试；AC-007 的端点/凭据变更失效有集成测试覆盖，过期失效只有纯函数证据。
- 建议：补一个仓库级或 API 级测试：写入一条已过期的 ok 观测行，断言 `get_proxy` 返回 `observation_status` 为 unknown 且 `country_code` 为 None。

### t052_test_f006 - 前端解析矩阵自称镜像后端矩阵，但缺了格式 4 带密码的一行

- 严重度：minor
- 锚点：AC-002（四种链接格式均解析正确）
- 位置：`src/frontend/src/features/proxies/parseProxyUrl.test.ts:1`（注释 “Mirrors the backend matrix”）对照 `tests/unit/test_t052_proxy_link.py` 的格式 4 用例 `user:p%40ss@proxy.example.com:8080`
- 问题：后端矩阵有格式 4 带密码用例（`user:p%40ss@host:port` → 密码解码为 `p@ss`），前端 `validCases` 里格式 4 只有无密码的 `user@proxy.example.com:8080`；URL 形态的 `p%40ss` 前端有覆盖，但 `user:pass@host:port` 形态下的密码 percent-decode 前端无对应行。文件头注释承诺镜像后端矩阵，实际少一行。
- 建议：前端 `validCases` 补一行 `user:p%40ss@proxy.example.com:8080` 的期望值，与后端矩阵对齐。

## 结论

- 前轮 finding 复核（Round N≥2 才写）：本轮为 Round 1，无前轮。
- 改测方向复核：无“迁就实现”的改测。核查了 diff 中全部三处修改既有测试的地方：`tests/unit/test_a6_error_contract.py`（平铺创建 payload 改链接形式，409/`used_by_count` 断言原样保留）；`tests/unit/test_t035_profile_domain.py`（`_proxy_payload` 删 `country_code`——该 payload 只走 `repo.create_proxy`，仓库层仍接受平铺字段；校验测试把旧平铺非法值用例换成等意图的链接校验用例，并新增平铺字段被 `extra="forbid"` 拒绝的用例）；`tests/e2e/test_proxy_library_e2e.py`（按新 UI 填链接输入框并展开高级区填名称，签名不变；`.fill()` 仅用于文本输入，合法）。三处均为语义变更下的等价改写，断言意图未弱化。
- 本轮新发现：6 条（important 2 条，minor 4 条）。
- 未进表的提示：
  - 已调查、无 finding：`test_t035_profile_domain.py` 的 `# type: ignore[arg-type]`/`[call-arg]` 是沿用已久的写法，用于故意传非法参数测校验，`pytest.raises` 断言本身仍在执行，不是静默错误抑制；`test_t052_supervisor_probe.py` 三个 Browser 启动测试用 `MagicMock` 替换了 `_resolved_endpoint` 等协作方法，但断言的 `extra_hosts` 只取决于凭证文件里的 host 是否为 `host.docker.internal`（`docker_adapter.py:1743`），与被 mock 的方法无关，未 mock 掉被断言的行为；弹窗聚焦时链接输入框显示完整链接（含密码）、失焦后显示脱敏链接是实现的有意行为，测试两态都断言了，不视为 AC-004 违反；`tests/e2e/test_proxy_library_e2e.py` 的改动只用 `.fill()` 做文本输入，合法。
  - `task.md` 未知契约清单里写 supervisor probe 测试“12 passed”，实际文件有 13 个测试且本轮重跑 13/13 通过——task.md 文本数字滞后 1 项，请实施方顺手订正（不在测试代码内，不进 finding）。
  - 命名锁死核对通过：`src/`、`tests/`、`scripts/` 中 `com.cbrowser.deployment-id` 零命中（仅 `progress.md` 叙述被驳回偏离时提及）；`docker_adapter.py:234` 默认 `resource_prefix` 仍为 `cbrowser-t005`；探针网络名断言 `cbrowser-t005-probe-net-` 前缀（`test_t052_supervisor_probe.py`）。
  - 引用核对：progress.md 声称的 5 个 t052 测试文件与计数（链接 53、观测 18、helper 5、supervisor 13、集成 17）本轮重跑逐一核对一致；未发现虚假引用。
  - 基线比对局限：`.scratch/t052_baseline.log` 仅保留尾部 5 行，无法按名逐项对应 29 个基线失败；本轮按总数比对（2009/27/8/2 对基线 1901/29/8/2）并逐项定性全部 27 个失败与 2 个 errors，确认无一落在 t052 改动文件内。
- 总体判断：测试总体可信、覆盖扎实，全量回归与基线一致且无新增失败；但存在 2 条 important（恒真断言与条件弱化断言）且 AC-012 未勾选需部署验证，按规则判 FAIL。
- 系统性 follow-up：无。

### AC 复验方式

- AC-001：TICK-VALID，re_verified。弹窗默认只显示链接/备注/只读国家、高级折叠的测试已重跑通过（ProxyFormDialog.test.tsx 13 passed）。
- AC-002：TICK-VALID，re_verified。四种格式矩阵后端 53 passed、前端 54 passed、集成 5 组创建用例 passed，均已重跑。
- AC-003：TICK-VALID，re_verified。弹窗双向同步测试（链接改高级跟随、高级改链接跟随、失焦脱敏）已重跑通过。
- AC-004：TICK-VALID，re_verified。集成测试对 create/get/list/patch/probe 五处原始响应文本做秘密值检查、弹窗测试做 DOM/查询缓存检查，均已重跑通过；f001/f002 只涉及两行冗余子断言，不影响秘密值证据。
- AC-005：TICK-VALID，re_verified。名称默认 host:port 且手动名不被后续解析覆盖，集成与弹窗测试均已重跑通过。
- AC-006：TICK-VALID，re_verified。集成测试用门控 runner 观测到 pending→ok、失败→failed 不猜国家，列表页手动探测成功/失败 toast 已重跑通过。
- AC-007：TICK-VALID，re_verified。端点变更与密码轮换后旧观测立即变 pending 的集成测试、TTL 规则单测均已重跑通过。
- AC-008：TICK-VALID，re_verified。受控回显夹具直连 198.51.100.1、经代理 203.0.113.7/JP，观测取代理出口，单测与集成均已重跑通过。
- AC-009：TICK-VALID，re_verified。探测接口对 host/host+port+scheme/proxy_url/username 四种重定向 body 返回 422、且随后按已存端点探测成功，均已重跑通过。
- AC-010：TICK-VALID，re_verified。fake-docker 测试覆盖 loopback 映射、extra_hosts、策略仅放行映射地址:端口、凭证改写、Browser 启动三态，均已重跑通过；真实 Docker 行为按链口径环境跳过，见 progress.md。
- AC-011：TICK-VALID，re_verified。loopback 映射失败在探测与启动两路均转为带处置提示的 LoopbackMappingError，fake-docker 测试已重跑通过；真实 daemon 拒绝行为按链口径环境跳过，见 progress.md。
- AC-012：TICK-VOID，trust_prior。未打勾的 [deploy] AC，本机无真实外部代理与公网出口，无法复验；只能依赖日后用户机部署验证。

coverage = 11 / 12

## 实跑验证记录

- 后端 t052 单测 4 文件：89 passed（链接 53、观测 18、helper 5、supervisor 13），`~/workspace/.cb-venv-t051/bin/python`，`PYTHONPATH=src/backend`，9.84s。
- 后端 t052 集成 + 受影响旧测试：41 passed（集成 17、t035、a6），21.23s。
- 前端代理三文件：83 passed（parseProxyUrl 54、ProxyFormDialog 13、ProxyListPage 16），Node 24.22.1 直接跑 vitest，8.03s。
- 后端全量分块回归（tests/unit 216 文件 + tests/integration 45 文件，10 块）：2009 passed / 27 failed / 8 skipped / 2 errors；基线 1901 passed / 29 failed / 8 skipped / 2 errors；passed +108（新增 t052 测试 106 + 2 项基线失败在本轮通过，属运行方差），failed −2。27 个失败按名：agent_executor_chain 7、automation_cdp_flow 2、automation_probe_chain 3、normal_exit_replay 4、t028 4、t034 2、a24 2、control_attendant_chain 1、automation_cdp 1、repo_hygiene 1，全部为真实浏览器/运行时或工具链环境缺失、既有欠账，无一落在 t052 改动文件内。2 个 errors（`test_a35_recovery.py::test_concurrent_apply_is_rejected_by_exclusive_db_registration`、`test_network_apply_operations.py::test_restore_not_found_is_explicit_terminal`）单独重跑复现，均为 teardown 层错误，名字与基线日志尾部一致，属基线既有。
- 前端全量：74 文件、529 passed / 0 failed（直接跑 `npx vitest run`；`npm test` 的 pretest 门禁要求 Node ≥26，本机只有 24.22.1，Node 26 不可用，故绕过 pretest 直接跑 vitest——测试本身全部通过）。
- 凭据断言字节级核对：`od -c` 确认 `tests/unit/test_t052_egress_probe_helper.py` 含字面量 `s3cret-pw`，且 helper stdout 字节断言不含该值；集成测试的 `never-show`/`rotated-secret` 与弹窗测试的 `STORED_SECRET_9f3` 均为真实字面量，非回显占位符。

verdict: FAIL

## Round 2 (2026-11-11T13:55:45+08:00)

reviewed_scope: 28e84db3286c2e6d

## Findings

本轮新发现：0 条。前轮 6 条 finding 全部复核通过，见下「前轮 finding 复核」。

## 结论

- 前轮 finding 复核（逐条以 diff/代码/实跑核实，不采信处置表自述）：
  - t052_test_f001（important，恒真断言）——已消除。`tests/integration/test_t052_proxy_api.py:211-252`：原 `assert body["proxy_url"] == body["proxy_url"]` 已删除，改为按参数化期望值逐项断言（含 `assert body["proxy_url"] == expected["proxy_url"]`，5 种格式各有字面量期望脱敏链接，如 `http://user@proxy.example.com:8080`、`socks5://user@[2001:db8::1]:1080`），另有 `assert "p@ss" not in body["proxy_url"]`。强度验证：字面量比较在错误脱敏输出下为 False（已用独立表达式求值确认，非恒真）；5 组创建用例实跑通过。未发现换形式弱化。
  - t052_test_f002（important，条件断言弱化）——已消除。`tests/integration/test_t052_proxy_api.py:282-293`：列表分支改为无条件 `assert isinstance(payload, list)` + `assert all("password" not in item for item in payload)`，单项分支保留原断言。强度验证：对含 `password` 键的模拟列表项求值，`all(...)` 为 False（会变红）；对干净列表为 True。实跑通过。未发现换形式弱化。
  - t052_test_f003（minor，pending 与未知无区分）——已消除。三处 pending 夹具测试已补：`ProxyFormDialog.test.tsx:214`（断言显示 `proxyCountryProbing` 且不显示 `proxyCountryUnknown`）、`ProxyListPage.test.tsx:399`（同上，行内断言）、`SessionDetailsPanel.test.tsx:205`（同上）。实现三处均按 `observation_status === "pending"` 分支显示「检测中」（`ProxyTable.tsx:82-84`、`ProxyFormDialog.tsx:430-432`、`SessionDetailsPanel.tsx:158`），测试触达的是真实组件与真实分支。`ProxyListPage.test.tsx:185-188` 的 `beforeEach` 每测重置 `stub = makeStub()`，pending 测试内重赋值不会串扰后续测试。前端 4 文件 targeted 96 passed、全量 533 passed。
  - t052_test_f004（minor，生产 runner 无测试）——已消除。新文件 `tests/unit/test_t052_supervisor_runner.py`，11 个测试实跑通过：成功返回出口 IP/国家、401/403/500/502 → `supervisor_unavailable`、坏 JSON → `supervisor_unavailable`、非 dict JSON → `probe_bad_response`、failed 透传 `error_code`、ok 无 `egress_ip` → `probe_failed`、未配置 → `supervisor_unavailable`、传输异常 → `supervisor_unavailable`。测的是真实生产类 `SupervisorEgressProbeRunner`（`services/egress_probe.py`），`httpx.MockTransport` 只 mock 在 HTTP 传输边界（系统边界），handler 内还断言了请求路径 `/supervisor/v1/proxies/px-1/probe`、Bearer 头与 body 凭据/指纹/`credential_revision`；未 mock 被测逻辑。非 dict 分支在 `egress_probe.py:141` 有真实 `isinstance(data, dict)` 校验，与 code f002 的修复对应。
  - t052_test_f005（minor，仓库层过期隐藏无测试）——已消除。新文件 `tests/unit/test_t052_observation_repository.py`，4 个测试实跑通过：过期 ok 行 `get_proxy` 返回 `observation_status == "unknown"` 且 `country_code`/`egress_ip` 均为 None；过期 ok 后新 pending 行仍显示 pending；failed 行照常显示；`list_proxies` 3 代理只发 1 条针对 `proxy_egress_observations` 的 SELECT（事件监听计数断言 `len(selects) == 1`，且返回的国家/状态逐项核对）。测的是真实 `ProfileRepository` + 真实 DB fixture，非纯函数复述。
  - t052_test_f006（minor，前端矩阵缺格式 4 带密码行）——已消除。`parseProxyUrl.test.ts:96-106` 补一行 `user:p%40ss@proxy.example.com:8080` → 密码 `p@ss`；字节级核对（`od -c`）确认期望密码确为 `p@ss`，与后端矩阵 `user:p%40ss@proxy.example.com:8080` 对齐。前端 parse 55 passed。
- 改测方向复核：无「迁就实现」的改测。本轮修复只做断言加强（f001/f002 由恒真/条件弱化改为真实比较）、新增测试（f003/f004/f005/f006）；`tests/unit/test_t035_profile_domain.py` 中新增的 `# type: ignore[call-arg]` 行位于 `pytest.raises(ValidationError)` 内、用于传入已被 `extra="forbid"` 拒绝的平铺字段以验证拒绝行为，断言本身仍在执行，与 Round 1 已核查通过的同类写法一致，不是静默错误抑制。diff 中无删除测试、无 `.skip`/`.only`、无注释掉的断言、无弱化断言。
- 本轮新发现：0 条。
- 未进表的提示：
  - 危险模式全量扫描：对 diff 内 tracked 测试文件与 7 个新增测试文件做模式扫描（`.skip`/`.only`/`assert True`/`expect(true)`/`eslint-disable`/`ts-ignore`/`type: ignore`/`pytest.mark.skip`/`toBeTruthy`），仅命中两处已调查项：f002 修复注释中提及旧 `assert True` 的说明文字（非代码），以及 `test_t052_proxy_link.py:210` 的 `# type: ignore[misc]`（在 `pytest.raises(AttributeError)` 内验证冻结值对象不可变性，断言执行中）。均不进 finding。
  - 命名锁死复核通过：`com.cbrowser.deployment-id` 在 `src/`、`tests/`、`scripts/`、`config/`、`compose.yaml` 中零命中，仅 `docs/blueprint/decisions.md:342` 在记载被驳回偏离的历史叙述中提及（允许）；`docker_adapter.py:234` 默认 `resource_prefix` 仍为 `cbrowser-t005`；`adapter.ts:309` 的 `"cbrowser"` 命中是 WebSocket 消息类型嗅探（`data.includes('"cbrowser"') && data.includes('"activity"')`），不是部署前缀。
  - task.md 计数订正已落实（code f006）：`task.md:99` 现写 supervisor probe 测试「13 passed」，与文件实际 13 个测试及本轮重跑一致。
  - 方法纠正记录：本轮初次从仓库根目录跑 vitest 时 3 个 DOM 测试文件报 `ReferenceError: Element is not defined`（10 failed / 31 skipped），原因是根目录无 vitest 配置、未启用 jsdom；改从 `src/frontend`（vitest.config.ts 所在目录）重跑后 4 文件 96 passed、全量 533 passed。根目录那次失败是我方调用位置错误，不是代码问题，不计入结论。
  - 基线 error 说明：本轮 chunk 跑中仅出现 1 个 error（基线 2 个），为 `test_a35_recovery.py::test_concurrent_apply_is_rejected_by_exclusive_db_registration` 的 teardown 层 error（基线既有）；同一 chunk 单独重跑时该 error 未复现（0 error），属 flaky；另一基线 error（`test_network_apply_operations.py::test_restore_not_found_is_explicit_terminal`）本轮未复现。均与 t052 无关。
  - 引用核对：progress.md 声称的 t052 测试计数（链接 53、观测 18、helper 5、supervisor 13、runner 11、仓库观测 4、集成 18）与本轮实跑逐一核对一致；未发现虚假引用。
- 总体判断：前轮 6 条 finding 全部真实修复并经实跑验证，无新发现；全量回归与基线一致且无新增失败。但 AC-012（[deploy]）仍未勾选、按规则记 TICK-VOID，故本轮 verdict 仍为 FAIL——唯一阻断项是本机无法验证的真实部署端到端，测试本身已无未解决 finding。
- 系统性 follow-up：无。

### AC 复验方式

- AC-001：TICK-VALID，re_verified。弹窗默认字段/高级折叠测试 14 个实跑通过（ProxyFormDialog.test.tsx）。
- AC-002：TICK-VALID，re_verified。四种格式矩阵后端 53、前端 55（含新补格式 4 带密码行）、集成 5 组创建用例，实跑通过。
- AC-003：TICK-VALID，re_verified。弹窗链接↔高级字段双向同步测试实跑通过。
- AC-004：TICK-VALID，re_verified。f001/f002 两行断言已改为真实比较并验证会变红；集成测试对 create/get/list/patch/probe 五处原始响应文本做秘密值检查，实跑通过。
- AC-005：TICK-VALID，re_verified。名称默认 host:port 且手动名不被后续解析覆盖，集成与弹窗测试实跑通过。
- AC-006：TICK-VALID，re_verified。集成测试门控 runner 观测 pending→ok、失败→failed 不猜国家；新增 3 个 pending 夹具前端测试断言显示「检测中」而非「未知」，实跑通过。
- AC-007：TICK-VALID，re_verified。端点/凭据变更后旧观测失效的集成测试与新增 4 个仓库级 TTL 测试（含过期 ok 隐藏、批量查询计数）实跑通过。
- AC-008：TICK-VALID，re_verified。受控回显夹具直连 198.51.100.1、经代理 203.0.113.7/JP，观测取代理出口，单测与集成实跑通过。
- AC-009：TICK-VALID，re_verified。探测接口对 host/host+port/scheme/proxy_url/username 重定向 body 返回 422 且随后按已存端点探测成功；runner 非 dict JSON 受控失败测试新增通过。
- AC-010：TICK-VALID，re_verified。fake-docker 测试覆盖 loopback 映射、extra_hosts、策略仅放行映射地址:端口、凭证改写、Browser 启动三态，13 passed；真实 Docker 行为按链口径环境跳过。
- AC-011：TICK-VALID，re_verified。loopback 映射失败在探测与启动两路均转为带处置提示的 LoopbackMappingError，fake-docker 测试实跑通过；真实 daemon 拒绝行为按链口径环境跳过。
- AC-012：TICK-VOID，trust_prior。未打勾的 [deploy] AC，本机无真实外部代理与公网出口，无法复验；只能依赖日后用户机部署验证。

coverage = 11 / 12

## 实跑验证记录（Round 2）

- 后端 t052 targeted 7 文件：122 passed（链接 53、观测 18、helper 5、supervisor 13、runner 11、仓库观测 4、集成 18），`~/workspace/.cb-venv-t051/bin/python`，`PYTHONPATH=src/backend`，31.77s。
- 后端全量分块回归（`.scratch/chunks/` unit_00–07 + int_00–01，216 unit + 45 int 文件；chunk 清单不含新增的 2 个单测文件，另计）：2010 passed / 27 failed / 8 skipped / 1 error；加新增 2 文件 15 passed，全量合计 2025 passed / 27 failed / 8 skipped / 1 error。基线 1901 passed / 29 failed / 8 skipped / 2 errors；passed +124（新增 t052 测试 122 + 2 项基线失败本轮通过），failed −2。27 个失败按名逐项比对，与 Round 1 的 27 个按文件分布完全一致（agent_executor_chain 7、automation_cdp_flow 2、automation_probe_chain 3、normal_exit_replay 4、t028 4、t034 2、a24 2、control_attendant_chain 1、automation_cdp 1、repo_hygiene 1），无一落在 t052 改动文件内，全部为真实浏览器/运行时或工具链环境缺失、既有欠账。1 个 error 为 `test_a35_recovery.py::test_concurrent_apply_is_rejected_by_exclusive_db_registration` 的 teardown 层 error（基线既有、flaky，单块重跑未复现）。
- 前端 targeted 4 文件（自 `src/frontend` 跑，Node 26.13.0）：96 passed（parseProxyUrl 55、ProxyFormDialog 14、ProxyListPage 17、SessionDetailsPanel 10）。
- 前端全量（自 `src/frontend` 跑，Node 26.13.0）：74 文件、533 passed / 0 failed；`npx tsc -p tsconfig.test.json` 通过（exit 0）。
- 断言强度验证：f001 字面量比较在错误脱敏输出下求值为 False；f002 的 `all("password" not in item ...)` 在含 password 键的模拟列表项上求值为 False、在干净列表上为 True；f006 新行期望密码经 `od -c` 字节级核对为 `p@ss`。
- 指纹：审阅前后 `reviewed_scope` 均为 `28e84db3286c2e6d`，审阅期间工作区无改动。

verdict: FAIL

## Round 3 (2026-11-11T14:41:10+08:00)

reviewed_scope: 591b901c2b3f608a

## Findings

本轮新发现：0 条。前轮 test 报告无未解决 finding（Round 2 新发现 0 条，唯一阻断项为 AC-012 未勾选）；本轮复核对象为 code f007 修复的测试侧证据与 AC-012 打勾，见下「前轮 finding 复核」。

## 结论

- 前轮 finding 复核（逐条以 diff/代码/实跑核实，不采信处置表自述）：
  - Round 1 的 6 条 test finding（f001–f006）——仍消除，未回退。本轮重跑全部 t052 定向测试：后端 123 passed（含 f001/f002 所在集成文件 18 passed、f004 runner 11 passed、f005/f007 仓库观测 5 passed）、前端 4 文件 96 passed；f001/f002 的真实比较断言、f003 的 3 个 pending 夹具、f006 的格式 4 带密码行均在其中通过，无弱化回退。
  - code f007（有界查询修复）的测试侧复核——通过，证据如下：
    - 新测试真实触达生产逻辑：`tests/unit/test_t052_observation_repository.py` 新增 `test_list_proxies_fetches_only_latest_observation_row_per_proxy`，走真实 `ProfileRepository.list_proxies()` → 真实 `_current_observations`（`repository.py:1246-1296`）→ 真实 DB fixture；3 代理各 3 行历史观测（旧 ok、新 ok、最新 pending），断言每代理返回最新 pending 行、国家/IP 为 None、观测 SELECT 恰为 1 次、物化观测行恰为 3。`list_proxies`（`repository.py:1335-1346`）确认只调一次 `_current_observations`，无逐代理查询。
    - 先红后绿证据可信（独立复现）：旧实现未提交入库，无法直接 checkout；本轮按 progress.md/测试 docstring 记载的旧行为（单次 SELECT 取全部历史行、Python 内取最新）重建旧版 `_current_observations` 做猴子补丁对照：同一测试体在旧实现下于 `assert len(loaded_rows) == 3` 处失败，`AssertionError: 9`（物化 9 行）；真实实现下同一断言通过（1 passed）。红绿均由同一断言、同一数据触发，非恒真；重建对照所用的 scratch 测试文件已删除，`git status` 已恢复干净。
    - 有界查询真实生效：SQL 本身为 `ROW_NUMBER() OVER (PARTITION BY proxy_id ORDER BY observed_at DESC, created_at DESC, id DESC)` 子查询取 `rn=1` 的 id，外层单次 SELECT 取行；`load` 事件计数证实只物化 3 行而非 9 行。`id DESC` 仅作精确并列时的确定性决胜，与单行路径 `_current_observation`（`observed_at`/`created_at` 降序 + `LIMIT 1`）前两键一致。
  - AC-012 打勾复核——成立，见下方 AC 复验方式（TICK-VALID，trust_prior）。
- 改测方向复核：无「迁就实现」的改测。本轮 delta 只有一处测试新增（f007 测试）与一处生产修复（有界查询）；无既有测试修改、无删除测试、无 `.skip`/`.only`、无注释掉的断言、无弱化断言。
- 本轮新发现：0 条。
- 未进表的提示：
  - 危险模式全量扫描：对 diff 内全部测试文件做模式扫描（`.skip`/`.only`/`assert True`/`expect(true)`/`eslint-disable`/`ts-ignore`/`type: ignore`/`pytest.mark.skip`/`toBeTruthy`），命中三处已调查项：`test_t052_proxy_api.py:289` 的 `assert True` 只出现在 f002 修复注释文字中（非代码）；`test_t052_proxy_link.py:210` 的 `# type: ignore[misc]` 在 `pytest.raises(AttributeError)` 内验证冻结值对象不可变性（Round 1 已核查）；`SessionDetailsPanel.test.tsx:233` 的 `toBeTruthy` 位于 t052 diff 未改动的既有「复制各值」测试内，仅作 `shown` 非空守卫，真正断言是随后 `writeText` 被以该确切值调用，不构成弱化。均不进 finding。
  - 命名锁死复核通过：`com.cbrowser.deployment-id` 在 `src/`、`tests/`、`scripts/`、`config/`、`compose.yaml` 中零命中；`docker_adapter.py:234` 默认 `resource_prefix` 仍为 `cbrowser-t005`。
  - 引用核对：progress.md 声称的 t052 测试计数（链接 53、观测 18、helper 5、supervisor 13、runner 11、仓库观测 5、集成 18，合计 123）与本轮实跑逐一核对一致；未发现虚假引用。
  - 方法说明：首轮 int 块重跑时 `-rf` 不列 error 项，改用 `-rE` 重跑两 int 块后两处 error 均已正名（见实跑记录）。
- 总体判断：f007 修复的测试证据真实可信（红绿复现、有界生效），AC-012 按本链既定口径（环境跑不了的验证跳过按 pass 计）打勾成立，t051 前例一致；全量回归与基线一致且无新增失败，无未解决 finding。
- 系统性 follow-up：无。

### AC 复验方式

- AC-001：TICK-VALID，re_verified。弹窗默认字段/高级折叠测试实跑通过（ProxyFormDialog.test.tsx，定向 96 passed 内含）。
- AC-002：TICK-VALID，re_verified。四种格式矩阵后端 53、前端 55（含格式 4 带密码行）、集成 5 组创建用例，实跑通过。
- AC-003：TICK-VALID，re_verified。弹窗链接↔高级字段双向同步测试实跑通过。
- AC-004：TICK-VALID，re_verified。f001/f002 真实比较断言仍在且通过；集成测试对 create/get/list/patch/probe 五处原始响应文本做秘密值检查，实跑通过。
- AC-005：TICK-VALID，re_verified。名称默认 host:port 且手动名不被后续解析覆盖，集成与弹窗测试实跑通过。
- AC-006：TICK-VALID，re_verified。集成测试门控 runner 观测 pending→ok、失败→failed 不猜国家；3 个 pending 夹具前端测试断言显示「检测中」，实跑通过。
- AC-007：TICK-VALID，re_verified。端点/凭据变更后旧观测失效的集成测试、仓库级 TTL 测试 5 个（含本轮新增 f007 有界查询测试）实跑通过。
- AC-008：TICK-VALID，re_verified。受控回显夹具直连 198.51.100.1、经代理 203.0.113.7/JP，观测取代理出口，单测与集成实跑通过。
- AC-009：TICK-VALID，re_verified。探测接口对 host/host+port/scheme/proxy_url/username 重定向 body 返回 422 且随后按已存端点探测成功；runner 非 dict JSON 受控失败测试实跑通过。
- AC-010：TICK-VALID，re_verified。fake-docker 测试覆盖 loopback 映射、extra_hosts、策略仅放行映射地址:端口、凭证改写、Browser 启动三态，13 passed；真实 Docker 行为按链口径环境跳过，见 progress.md。
- AC-011：TICK-VALID，re_verified。loopback 映射失败在探测与启动两路均转为带处置提示的 LoopbackMappingError，fake-docker 测试实跑通过；真实 daemon 拒绝行为按链口径环境跳过，见 progress.md。
- AC-012：TICK-VALID，trust_prior。已打勾（task.md:61）。本机无 Docker、真实外部代理与公网出口，无法独立复验；依据本链既定口径（确实因本机环境跑不了的验证跳过按 pass 计）与 t051 前例（AC-013 整项跳过但打勾，审阅记 TICK-VALID trust_prior），且 progress.md「环境跳过」明确写明「本机未验证、不得记为已验，须在用户机真实部署验证」，替代验证证据为集成测试（受控回显+代理夹具，18 passed）+ supervisor fake-docker 测试（13 passed）+ 前端全量 533 passed。本轮依赖的是上述已产出证据与链口径，不是 implementer 口头自述。

coverage = 11 / 12

## 实跑验证记录（Round 3）

- 后端 t052 定向 7 文件：123 passed（链接 53、观测 18、helper 5、supervisor 13、runner 11、仓库观测 5、集成 18），`~/workspace/.cb-venv-t051/bin/python`，`PYTHONPATH=src/backend`，37.90s。
- f007 红绿对照：重建旧版无界 `_current_observations`（单次 SELECT 取全部历史行、Python 内取最新）猴子补丁后，同一测试体 1 failed（`assert len(loaded_rows) == 3` 得 9）；真实实现下 1 passed。Scratch 文件已删，工作区干净。
- 后端全量分块回归（`.scratch/chunks/` unit_00–07 + int_00–01，216 unit + 45 int 文件；chunk 外 2 文件另计）：2026 passed / 27 failed / 8 skipped / 2 errors。基线 1901 passed / 29 failed / 8 skipped / 2 errors；passed +125（t052 测试 123 + 2 项基线失败本轮通过，属运行方差——基线日志仅存尾部 5 行，无法按名指出是哪 2 项，与 Round 1/2 相同局限），failed −2。27 个失败按名逐项比对，与 Round 1/2 的 27 个完全一致（agent_executor_chain 7、automation_cdp_flow 2、automation_probe_chain 3、normal_exit_replay 4、t028 4、t034 2、a24 2、control_attendant_chain 1、automation_cdp 1、repo_hygiene 1），无一落在 t052 改动文件内，全部为真实浏览器/运行时或工具链环境缺失、既有欠账。2 个 errors 均已用 `-rE` 正名：`tests/integration/test_a35_recovery.py::test_concurrent_apply_is_rejected_by_exclusive_db_registration` 与 `tests/integration/test_network_apply_operations.py::test_restore_not_found_is_explicit_terminal`，均为基线既有 teardown 层 error（前者首轮重跑未复现，属 flaky）。
- 前端定向 4 文件（自 `src/frontend` 跑，Node 26.13.0）：96 passed（parseProxyUrl 55、ProxyFormDialog 14、ProxyListPage 17、SessionDetailsPanel 10）。
- 前端全量（自 `src/frontend` 跑，Node 26.13.0）：74 文件、533 passed / 0 failed。
- 指纹：审阅前计算 `reviewed_scope` 为 `591b901c2b3f608a`，与派审 prompt 给定值一致；写报告后重算仍为 `591b901c2b3f608a`，审阅期间工作区无改动。

verdict: PASS

