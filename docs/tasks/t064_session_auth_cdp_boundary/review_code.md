# Task review t064（reviewer_focus: 代码）

- task：`t064_session_auth_cdp_boundary`
- spec：`docs/tasks/t064_session_auth_cdp_boundary/task.md`
- diff_anchor：`680d850067075caf9356ee6c71771f6dc779c543`
- target：`git -C '/home/hatch/workspace/CBrowser_t064' diff 680d850067075caf9356ee6c71771f6dc779c543`
- round：1
- reviewed_at：2026-11-14T00:39:05+08:00

reviewed_scope: e979cc1914d912d9

## Findings

### t064_code_f001 - 渲染 Caddyfile 的 signal 块未用 route 包裹，Caddy 指令重排使删头在 forward_auth 回注之后执行，合法握手到 Gateway 时 grant 已被删

- 严重度：critical
- 锚点：AC-001「合法握手可用」与 AC-006「真实 Caddy/Chrome 链中登录、viewer 首帧、重连…均通过」；失败场景：合法用户经真实 Caddy 建立 viewer 握手，Gateway 恒回 401
- 位置：`src/backend/cbrowser/network_config.py:88`（`handle /stream/*/signal` 块起）至 `:100`：删头 `request_header -X-CBrowser-Authorized-Profile` / `-X-CBrowser-Viewer-Grant` 在 `:89-90`、`forward_auth` 在 `:92-97`、`reverse_proxy`（`header_up -Cookie`）在 `:98-100`，三者是 `handle` 块内的同级指令、无 `route` 包裹
- 问题：Caddyfile 适配时，`handle` 块内指令按 Caddy 硬编码的指令顺序重排、书写顺序不算数，只有 `route` 块保留书写顺序（Caddy 官方文档 Caddyfile Concepts：「directives are sorted according to a specific default directive order unless in a `route` block」）。官方 Directive order 列表（https://caddyserver.com/docs/caddyfile/directives ）的 middleware 段为 `basic_auth` → `forward_auth` → `request_header` → … → `handle`/`route` → … → `reverse_proxy`，即 `forward_auth` 先于 `request_header` 执行。`forward_auth` 的展开形态是在其自身的 reverse_proxy 处理中经 `handle_response` 用 `request_header` 把 `copy_headers` 的值写回原请求（官方 forward_auth 文档 Expanded form），写回发生在 forward_auth 处理器执行期间；排在其后的同级 `request_header -…` 删除指令随后执行，会把刚回注的 `X-CBrowser-Authorized-Profile` 与 `X-CBrowser-Viewer-Grant` 一并删掉，最后 `reverse_proxy` 交给 Gateway 的请求不带 grant——`src/backend/cbrowser/gateway/server.py` 的 grant 校验（缺 grant 回 401）使每一次经真实 Caddy 的合法握手恒失败。伪造防护不受此序影响（删头仍在代理之前执行、forward_auth 失败时不代理），坏的是合法路径本身。Caddy 社区已有同型陷阱的维护者答复（forward_auth 优先级高于 request_header、删头会删掉回注头、须用 route 块保序），与官方顺序表互相印证。云端证据无法发现此问题：`tests/unit/test_t064_edge_caddyfile.py` 只断言渲染文本中的指令存在与文本先后，集成测试绕过 Caddy 直连 Gateway/API，真实链 e2e 按 [deploy] 顺延 p094——本地补验时合法连接/首帧类用例会因此失败。blueprint/security/architecture 中「Caddy 先删伪造头、再 forward_auth 解析」的叙述描述的是书写意图，不是适配后的实际执行序，与实现不符。
- 建议：把 signal 块内容整体包进 `route { … }`（仍在 `handle /stream/*/signal` 内），使「删伪造头 → forward_auth → reverse_proxy」按书写顺序执行；同步扩展 `tests/unit/test_t064_edge_caddyfile.py` 断言 route 包裹存在，p094 本地补验时以真实 Caddy 适配结果（`caddy adapt` 的 handler 链顺序）或真实合法握手留证。

### t064_code_f002 - specs/access_control.md 写的 Gateway 校验顺序（先 grant 后 Origin）与实现及另两份 blueprint 相反

- 严重度：minor
- 锚点：行为缺陷（文档与实现不一致；两侧检查均 fail-closed，无越权）
- 位置：`docs/specs/access_control.md:39`（「Gateway 在本地验 grant 的签名、到期、Profile 绑定与 authorized Profile 头一致性，再验 Origin、Agent 和 runtime 就绪」）；实现 `src/backend/cbrowser/gateway/server.py:776-784` 先验 Origin、`:786-810` 后验 grant（基线既有顺序，本 task 未改）；`docs/blueprint/security.md:17` 与 `docs/blueprint/gateway.md` 的拒绝顺序均按 Origin → grant 书写，与实现一致
- 问题：同一交付内 access_control.md 把顺序写反。可观察差异仅在双重非法请求的错误先行性（坏 Origin + 缺 grant 时实现回 403 Origin 而非 401），不构成安全问题，但 finalization 的 spec 口径应与实现及其余 blueprint 统一。
- 建议：把 access_control.md:39 改为与实现一致的「先验 Origin，再验 grant 签名/到期/Profile 绑定与 authorized Profile 头一致性」；不建议为对齐该句改代码顺序（会动节流与错误语义）。

### t064_code_f003 - 内部 OpenAPI 把边缘解析端点的 security 标为仅 sessionCookie，未反映边缘证明要求

- 严重度：minor
- 锚点：行为缺陷（契约面描述不完整；端点实际行为正确，缺证明恒 403）
- 位置：`schemas/openapi/cbrowser_internal.json:5954-5958`（`/api/v1/internal/edge/viewer-authorize` 的 `security: [{sessionCookie: []}]`，路径起于 `:5907`）；端点实际双重要求在 `src/backend/cbrowser/api/internal_edge.py`（先验 `X-CBrowser-Edge-Proof`、再验会话 Cookie）
- 问题：再生后的内部 schema 把该端点描述成只需会话 Cookie，与 `docs/blueprint/gateway.md` 的「以 Caddy 独占呈现的边缘证明与浏览器会话共同授权」不一致；只带 Cookie 的直接调用实际回 403（本 reviewer 在 `tests/integration/test_edge_viewer_authorize.py` 覆盖下复跑确认缺/错证明恒 403）。schema 是生成物，根源在 app 的 OpenAPI security 标注未给 edge 路径单独口径。
- 建议：在 OpenAPI 生成侧为 `/api/v1/internal/edge/*` 标注边缘证明要求（或以扩展字段注明 proof 头为必需），再生 schema；不改端点行为。

## 结论

- 本轮新发现：3 条（1 critical、2 minor）
- 未进表的提示：文件过大——`src/backend/cbrowser/gateway/server.py` 1010 行，超实现源码 800 行阈值，本 task 净增 14 行（+21/−7）；`src/backend/cbrowser/api/app.py` 734 行，超 400 行 minor 阈值，本 task 净增约 17 行；两者均为基线既存大文件的小幅增量，按降级规则只在此提示、不进 finding 表。新文件 `src/backend/cbrowser/shared/viewer_grants.py` 125 行、`src/backend/cbrowser/api/internal_edge.py` 107 行、`src/backend/cbrowser/network_config.py` 118 行均未超阈值。圈复杂度：本 task 新增函数（grant mint/verify、边缘解析 handler）手算 CC 均 \<10，无 ≥15 函数。范围外观察：无。
- 基线失败归因抽查（应简报要求，不记 finding）：本 reviewer 在本 worktree 实跑复现三条且签名与简报一致——`tests/unit/test_repo_hygiene.py::test_tracked_files_do_not_leak_developer_home_paths` 失败点名 `docs/tasks/t062_control_plane_boundaries/review_code.md`/`review_test.md` 含 `/home/hatch/`（grep 实见该文件 :6、:70、:93 等行），t064 diff 未触该文件；`tests/unit/test_fontconfig.py::test_prepare_write_failure_returns_none_and_leaves_no_tmp` 失败，t064 diff 未触 fontconfig 实现与该测试；`tests/unit/test_t060_gate_boundaries.py::test_local_topology_profile_does_not_require_public_geoip` 失败为 `AttributeError: 'GatewayTopologyHarness' object has no attribute 'data_dir'`（`tests/fixtures/gateway_probe/topology.py:674`），t064 对该文件的改动仅新增两把秘密名与三处 env 注入（diff hunk 在 :150/:213/:434/:476 附近），未触 data_dir 定义（:100）与 :674 逻辑。三条归因成立。
- findings.py 阻断说法核实：`docs/findings/` 下确有 `d037_dockerignore_leaf_allowlists.md` 与 `d037_sqlite_extended_error_codes_and_log_safety.md`、`d038_deterministic_deployment_identity_and_media_pools.md` 与 `d038_target_engine_tab_visibility_unreliable.md` 两组同号不同条目（ls 实查），编号重复属基线既存。spike 报告质量：s018 对两候选按来源认证/重放窗口/到期撤销/Upgrade/客户端改动五维逐项对比并给出两跳秘密与唯一判定点结论，s019 对三条 CDP 路径分别给出不可达/被拒判定与配置级证据、引擎内拒绝明确顺延实测——结论均已回填 task.md 未知契约清单（无 UNVERIFIED 残留），以 spike 报告承载结论可接受。
- 复验摘要（实现层，本 reviewer 独立执行）：落点校验 `git rev-parse --show-toplevel`（worktree 内）= `/home/hatch/workspace/CBrowser_t064`、分支 `t064_session_auth_cdp_boundary`、diff 基线 `680d850`。自跑三组全过：grants/caddyfile/edge/compose 秘密挂载 32 passed；Gateway signaling/control/config/viewer throttle 40 passed（无 grant 401、只有 Cookie 401、伪造/跨 Profile/可信头不一致 403、就绪后建隧道、Agent register 独立认证回归均在内）；automation/auth/internal service config 29 passed（含 AC-004 新增普通 Profile detail/list 不含 cdp_ws_path 与 token 的断言）。逐项核对：grant 为 HMAC-SHA256（payload_b64 签名、compare_digest、先验签后解码、TTL 60 秒、claims 仅 v/profile_id/grant_id/exp、坏输入恒 None）；边缘端点先验证明（缺/错 403、未配置 503）、URI 正则锚定 + urlsplit 去 query + unquote、会话/Origin/Profile 只经 AuthService.authorize_viewer 判定、登出撤销后 401；旧端点与 GatewayApiClient.authorize_viewer 已删净（src grep 仅剩新 edge 端点与文档叙述，内部 schema 旧路径消失、新 edge 路径出现）；两跳秘密分发经 compose 复核为 edge_proof_key 仅 API 文件 + Caddy 进程环境、viewer_grant_key 仅 API+Gateway 文件，deploy.sh 只在 compose_with 调用时从秘密文件读入进程环境、不落盘不打印；Gateway 配置新增必填 viewer_grant_key_file，唯一入口 `gateway/__main__.py` 走 from_env，compose 与各测试 harness 均已接线；Agent register 处理函数与路由未被本 task 触及（diff 无该段改动且回归通过）；AC-005 面（snapshot/wait_for/extract、Selkies 同源、CSP、前端）在 diff 文件清单中零触及。唯一阻断项是 f001：上述每一跳单独都对，但经真实 Caddy 适配后的执行序把合法路径切断。
- 总体判断：每一跳的实现（grant 密码学、边缘端点、Gateway 验签、秘密分发、旧面删除）经独立复验均成立，但渲染 Caddyfile 的指令重排缺陷使真实边缘链的合法握手恒被拒，AC-001/AC-006 的打勾在当前交付上不成立，verdict FAIL；按 f001 建议以 route 包裹修复并补渲染契约断言后可重派复审，p094 的真实拓扑补验仍须在修复后执行。
- 系统性 follow-up：无（[deploy] 补验已登记 `docs/pending/todo/p094_t064_local_edge_cdp_verification.md`，实存且内容覆盖 AC-001/002/004 引擎部分/006；f001 的真实链验证并入 p094 第 1、2 项即可，不另立）

### AC 复验方式

- AC-001：TICK-VOID，re_verified。云端各跳经自跑成立（grant 单元、边缘集成含登出撤销 401、Gateway 集成含只有 Cookie 401 与跨 Profile 403、Caddyfile 文本契约），但渲染 Caddyfile 因 f001 的指令重排在真实 Caddy 链上删掉回注 grant，「合法握手可用」在组装后的边缘契约上不成立，打勾作废；管理 Cookie Path=/ 未被改动（auth_router 仍 path="/"，本 reviewer 直读确认）。
- AC-002：TICK-VALID，re_verified。外部内部路径 404 由更具体 handle 先行（渲染契约自跑通过）、边缘证明缺/错 403 与未配置 503、Gateway 直连无 grant 401/伪造与跨 Profile 403、可信头不一致 403、Agent register 独立认证回归均经自跑集成组（40 passed）证实；伪造头防护在 f001 的重排下仍成立（删头仍先于代理执行）；真实拓扑部分按 [deploy] 顺延 p094（pending 实存且覆盖）。
- AC-004：TICK-VALID，re_verified。普通 Profile detail/list 不含 cdp_ws_path 与 token 的新增契约断言随 automation 组自跑通过（29 passed），专用 Automation 状态端点唯一披露面未变；CDP 本体不可达由 s019 配置走读（临时端口、回环监听、端口未发布）支撑且本 task 未动该面；真实引擎 Host/Origin 负向例已写入 e2e、云端 collect-only，按 [deploy] 顺延 p094。
- AC-005：TICK-VALID，re_verified。diff 文件清单对 snapshot/wait_for/extract、runtime_agent、Selkies 同源客户端与目标页 CSP 零触及，automation 链回归随自跑组通过，主世界与同源语义无从被本 task 改变。
- AC-006：TICK-VOID，re_verified。真实 Caddy/Chrome 链的登录后 viewer 首帧与重连都必须经 signal 路由完成握手，f001 使 Gateway 收不到 grant、恒回 401，首帧与重连在当前渲染下不可能通过；harness 与 e2e 已按新流就绪也改变不了适配后的执行序，打勾作废，真实链补验顺延 p094 须在 f001 修复后进行。

coverage = 5 / 5

verdict: FAIL

## Round 2

- round：2
- reviewed_at：2026-11-14T00:48:02+08:00
- 复核范围：Round 1 三条 finding（t064_code_f001/f002/f003）的修复成立性、本轮其余改动抽查（test_gateway_signaling 新增断言、gateway.md route 说明句）、AC-001/AC-006 重新判定；其余 AC 沿用 Round 1 判定并注明。
- 落点校验：`git rev-parse --show-toplevel` = `/home/hatch/workspace/CBrowser_t064`、分支 `t064_session_auth_cdp_boundary`、diff 基线 `680d850067075caf9356ee6c71771f6dc779c543`（同 Round 1）；实跑均在 worktree 内以 `PYTHONPATH=src/backend:tests/fixtures` + gate venv Python 执行。

### Finding 复核

#### t064_code_f001（critical）— 已修成立

- 位置实查：`src/backend/cbrowser/network_config.py:92-107`，`handle /stream/*/signal` 块内已整体包入 `route {`（:93），块内顺序为两条删头 `request_header -X-CBrowser-Authorized-Profile`（:94）/`-X-CBrowser-Viewer-Grant`（:95）→ `forward_auth`（:97，其子块 `uri`/`header_up X-CBrowser-Edge-Proof`/`copy_headers X-CBrowser-Authorized-Profile X-CBrowser-Viewer-Grant` 在 :98-100）→ `reverse_proxy`（:103，其子块 `header_up -Cookie` 在 :104），`route` 在 :106 闭合、`handle` 在 :107 闭合。
- 渲染实查：本 reviewer 直接调用 `generate_caddyfile(56661)` 打印全文，花括号 12 开 / 12 闭平衡；signal 切片内相对位置 route（34）< 删 grant 头（112）< forward_auth（165）< reverse_proxy（448），`header_up -Cookie` 位于 reverse_proxy 之后的子块内。缩进与嵌套语法正确：`route` 为 handle 的唯一子块，forward_auth 与 reverse_proxy 的子块各自闭合。
- Caddy 语义复核：`route` 内指令按声明序执行，删伪造头先于 forward_auth，与 Round 1 引用的官方默认指令序（forward_auth 先于 request_header）不再冲突；`forward_auth` 的 `copy_headers` 是其自身展开（reverse_proxy + handle_response 回写原请求）在处理器内部完成，route 包裹只改变它与同级 `request_header`/`reverse_proxy` 的相对序、不改变其回注行为，回注发生在删头之后故不再被删；`header_up -Cookie` 仍在 reverse_proxy 子块内、在代理到 Gateway 时生效，删 Cookie 语义不变。文件内 :83-90 的注释与 blueprint `docs/blueprint/gateway.md:42` 的 route 说明句均与此实现一致（gateway.md 抽查无回归，见下）。
- 测试实查：`tests/unit/test_t064_edge_caddyfile.py` 的 `test_signal_route_resolves_at_the_edge_and_strips_the_cookie`（:31 起）已补 `assert "route {" in signal`（:38）与顺序断言：删 grant 头 index < forward_auth index（:39-41）、forward_auth index < reverse_proxy index（:42），并保留 copy_headers、边缘证明头占位、header_up -Cookie 与 signal 先于普通 stream 路由的既有断言。本 reviewer 实跑该文件通过（计入下方 24 passed 合计）。

#### t064_code_f002（minor）— 已修成立

- 位置实查：`docs/specs/access_control.md:39` 现为「Gateway 先验 Origin，再在本地验 grant 的签名、到期、Profile 绑定与 authorized Profile 头一致性，最后验 Agent 和 runtime 就绪」，与实现 `src/backend/cbrowser/gateway/server.py` 的顺序一致（:776-784 先验 Origin、:786 起后验 grant；本 reviewer 本轮 grep 直读该段行号确认），亦与 `docs/blueprint/security.md:17`、`docs/blueprint/gateway.md:49` 的拒绝顺序（Origin → grant）统一。Round 1 指出的同交付口径相反问题已消除，无代码顺序改动。

#### t064_code_f003（minor）— 已修成立

- 端点实查：`src/backend/cbrowser/api/internal_edge.py:64-66` 已加声明式参数 `presented_proof: Annotated[str | None, Header(alias=EDGE_PROOF_HEADER)]`，`EDGE_PROOF_HEADER = "X-CBrowser-Edge-Proof"`（`src/backend/cbrowser/shared/viewer_grants.py:37`）；端点行为未变，仍先验证明（缺/错恒 403、未配置恒 503，:70-82），证明参数在 OpenAPI 中为可选声明、运行时由端点自身 fail-closed 强制，与 Round 1 建议的「在生成侧标注边缘证明要求」口径一致。
- schema 实查：`schemas/openapi/cbrowser_internal.json:5916` 起，`/api/v1/internal/edge/viewer-authorize` 的 GET 已含 parameters 一条 `{name: "X-CBrowser-Edge-Proof", in: "header", required: false}`；本 reviewer 以 json 直读该 operation 确认（security 仍为 sessionCookie，证明要求现由参数声明承载）。
- 测试实查：`tests/unit/test_runtime_agent_protocol_export.py` 的 `test_internal_openapi_export_matches_checked_in_file` 已补断言（edge_params 含 `("X-CBrowser-Edge-Proof", "header")`），且该测试同时断言 live schema 与 checked-in 文件全等，再生未漂移。本 reviewer 实跑该文件通过（计入下方 24 passed 合计）。
- 行为回归实查：`tests/integration/test_edge_viewer_authorize.py` 8 例全过（计入下方 24 passed 合计）——缺/错证明 403 且不回注 grant 头、缺/假会话 401、坏 Origin 与未知 Profile 403、非 signal URI 403、正常 200 回注 authorized Profile 与 Gateway 可验 grant（且跨 Profile 验不过）、登出撤销后 401、旧端点 404、未配置 503，端点行为与 Round 1 复验一致、无回归。

### 本轮其余改动抽查（无回归、无新 finding）

- `tests/integration/test_gateway_signaling.py`：拒绝矩阵新增过期 grant 用例（以 `now=time.time() - 3600` 签发、TTL 60 秒，断言 403，:207-217）与 AC-004 无-cdp 断言（401/403 的 plain-HTTP 拒绝响应体小写不含 `cdp`，:220-229）。本 reviewer 实跑 `test_viewer_handshake_rejections_leave_no_session` 单例通过（计入下方 21 passed 合计），两处新断言均真实执行、非空转。
- `docs/blueprint/gateway.md:42`：新增 route 说明句「渲染后的 signal 块整体包在 route 内保声明序——Caddy 默认指令序把 forward_auth 排在 request_header 之前，不保序会把刚回注的授权头随即删掉」，与 network_config.py 实现及文件内注释三方一致。
- 连带回归组：`tests/unit/test_shared_viewer_grants.py` 与 `tests/integration/test_automation_api.py` 随同实跑通过（见下），grant 密码学与 automation 披露面无回归。

### 复验摘要（本 reviewer 独立实跑）

- 第一组：`tests/unit/test_t064_edge_caddyfile.py` + `tests/unit/test_runtime_agent_protocol_export.py` + `tests/integration/test_edge_viewer_authorize.py`，合计 **24 passed**（collect 实数 4 + 12 + 8），1 条既有 StarletteDeprecationWarning。
- 第二组：`tests/integration/test_gateway_signaling.py::test_viewer_handshake_rejections_leave_no_session` + `tests/unit/test_shared_viewer_grants.py` + `tests/integration/test_automation_api.py`，合计 **21 passed**，同一既有 warning。
- 与实施方 progress.md 记载的 Round 1 修复复验数字（54 + 23 passed）方向一致，本 reviewer 的独立子集复跑未见失败；真实 Caddy/Chrome 链仍未在云端实跑，按既定口径顺延 p094（须在本次 f001 修复后的渲染上执行），不影响本轮云端判定。

### AC 复验方式（Round 2）

- AC-001：TICK-VALID，re_verified。Round 1 的 TICK-VOID 唯一理由（f001 指令重排删 grant）已修复成立：route 保序经渲染直查与渲染契约测试证实，云端各跳（grant 单元、边缘集成含登出撤销 401、Gateway 集成含只有 Cookie 401 与跨 Profile/过期 403）本轮复跑全过；管理 Cookie Path=/ 未被改动同 Round 1 直读结论。真实 Caddy/Chrome 链部分按 [deploy] 口径顺延 p094，与 Round 1 对 AC-002/004 的顺延处理一致。
- AC-006：TICK-VALID，re_verified。Round 1 的 TICK-VOID 唯一理由同为 f001，现已解除：signal 握手的边缘链在渲染契约层面成立，harness 与 e2e 已按新流就绪（Round 1 已核）；真实 Caddy/Chrome 登录、首帧、重连、退出撤销与认证自动化实跑按 [deploy] 口径顺延 p094，须以修复后渲染执行。
- AC-002：TICK-VALID，re_verified。沿用 Round 1 判定（注明：本轮边缘端点 403/503 与 Gateway 过期 grant 403 复跑为其提供了同向新证据，无反证）。
- AC-004：TICK-VALID，re_verified。沿用 Round 1 判定（注明：本轮新增的拒绝响应无-cdp 断言实跑通过，automation 组复跑全过，无反证）。
- AC-005：TICK-VALID，trust_prior。沿用 Round 1 判定（本轮改动未触该面，无新证据变化）。

coverage = 5 / 5

verdict: PASS

## Round 3

- round：3
- reviewed_at：2026-11-14T02:38:11+08:00
- 性质：确认轮（非全量重审）。触发原因：finish 门禁判 INCOMPLETE——本文件与 review_test.md 的 `reviewed_scope:` 均仍停在 Round 1 时点指纹，门禁要求最后一轮报告指纹等于最终交付指纹。本轮只做三件事：独立复算指纹、核对 Round 2 审阅字节与当前交付字节的同一性、抽验 Round 2 结论在当前字节上仍成立；不改 Round 1/2 任何内容，不新增 finding 审阅。
- 落点校验：`git rev-parse --show-toplevel`（worktree 内）= `/home/hatch/workspace/CBrowser_t064`、分支 `t064_session_auth_cdp_boundary`、diff 基线 `680d850067075caf9356ee6c71771f6dc779c543`（同 Round 1/2）。

reviewed_scope: 3cd6ec932d29a297

### 指纹复算与字节同一性核对

- 独立复算：本 reviewer 在 worktree 内运行 `review_scope_fingerprint('680d850067075caf9356ee6c71771f6dc779c543', 'docs/tasks/t064_session_auth_cdp_boundary')`（`.repo_template/scripts` 的 `repo_task.monitoring`），结果为 `3cd6ec932d29a297`，与主会话实算值逐字一致。本段 `reviewed_scope:` 即以此复算值为准。
- mtime 核对：以 diff 基线列出的全部交付文件（实现、测试、长期文档、schema，含未跟踪新文件）实查落盘时间，除实施侧 `progress.md`（Round 2 处置与收尾记录，2026-11-14 00:50:13 CST 落盘，属审阅结果的记录动作、非交付内容变更）外，最晚为 `docs/blueprint/gateway.md` 的 2026-11-14 00:44:32 CST，全部早于 Round 2 两份报告的落盘时间（review_test.md 00:49:40 CST、review_code.md 00:51:37 CST，Asia/Shanghai）。
- 结论：Round 2 审阅的交付字节与当前交付字节是同一批，Round 2 之后交付内容未再变动；Round 1/2 报告里的旧指纹 `e979cc1914d912d9` 是 Round 1 时点指纹未随 Round 1 修复更新的落盘缺口，不是字节差异。本轮以新指纹补记于此，门禁所指缺口闭合。

### f001 修复面抽验（当前字节直读）

- `src/backend/cbrowser/network_config.py:92-107`：`handle /stream/*/signal` 块内仍整体包入 `route {`（:93），块内顺序为两条删头 `request_header -X-CBrowser-Authorized-Profile`（:94）/`-X-CBrowser-Viewer-Grant`（:95）→ `forward_auth`（:97）→ `reverse_proxy`（:103，其子块 `header_up -Cookie` 在 :104），与 Round 2 实查一致，f001 修复面在当前字节上未回退。
- `tests/unit/test_t064_edge_caddyfile.py:38-42`：route/顺序断言仍在——`"route {" in signal`、删 grant 头 index < forward_auth index、forward_auth index < reverse_proxy index，与 Round 2 实查一致。

### 复跑摘要（本 reviewer 独立实跑）

- 命令（worktree 内）：`CBROWSER_GATE_ENV_READY=1 CBROWSER_GATE_SCRATCH=$PWD/.scratch/gate_scratch PYTHONPATH=src/backend:tests/fixtures ~/workspace/CBrowser/.scratch/gate_venv/bin/python -m pytest tests/unit/test_t064_edge_caddyfile.py tests/integration/test_edge_viewer_authorize.py -q -p no:cacheprovider`，结果 **12 passed**（Caddyfile 契约 4 例＋边缘解析集成 8 例），1 条既有 StarletteDeprecationWarning。与 Round 2 第一组（同两文件计入 24 passed，另含 protocol export 12 例）同向、无失败。

### AC 复验方式（Round 3）

- AC-001：TICK-VALID，re_verified。本轮复跑边缘解析集成 8 例全过（缺/假会话 401、坏 Origin 与未知 Profile 403、登出撤销后 401、正常 200 回注可验 grant）且 Caddyfile 契约 4 例全过、route 保序经直读再证，Round 2 判定在当前字节上成立；真实 Caddy/Chrome 链部分按 [deploy] 口径顺延 p094，口径不变、不表示已验。
- AC-002：TICK-VALID，re_verified。本轮复跑集合覆盖边缘证明缺/错 403 与未配置 503（边缘集成 8 例）及外部内部路径 404 先于 /api 代理的渲染契约断言（Caddyfile 4 例），全过；Gateway 直连拒绝与 Agent register 回归沿用 Round 2 复跑证据（指纹与 mtime 核对确认字节未变）；真实拓扑部分顺延 p094，口径不变。
- AC-004：TICK-VALID，trust_prior。本轮未复跑 automation 组，沿用 Round 2 判定（普通 Profile 不泄漏断言与拒绝响应无-cdp 断言均已实跑通过），且指纹一致确认其审阅字节即当前字节、无新证据变化；真实引擎 Host/Origin 负向实跑顺延 p094，口径不变。
- AC-005：TICK-VALID，trust_prior。沿用 Round 2 判定；本轮核对确认交付字节自 Round 2 未变、该面（snapshot/wait_for/extract 与同源客户端）在 diff 中零触及的结论不变，无新证据变化。
- AC-006：TICK-VALID，re_verified。Round 1 TICK-VOID 的唯一理由 f001 经本轮直读＋契约复跑再证已解除，harness 与 e2e 按新流就绪状态不变；真实 Caddy/Chrome 登录、首帧、重连、退出撤销与认证自动化实跑按 [deploy] 口径顺延 p094，须以修复后渲染执行，本判定不表示真实链已验。

coverage = 5 / 5

verdict: PASS
