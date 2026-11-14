# Task review t065（reviewer_focus: 代码）

- task：`t065_proxy_credential_isolation`
- spec：`docs/tasks/t065_proxy_credential_isolation/task.md`
- diff_anchor：`a4726b33bbfa3e2262a7b5a450271f2c6fdeebe4`
- target：`git -C '<home>/workspace/CBrowser_t065' diff a4726b33bbfa3e2262a7b5a450271f2c6fdeebe4`
- round：5
- reviewed_at：2026-11-14T11:20:06+08:00

reviewed_scope: 4dd19121e8e93b53

## Findings

### t065_code_f001 - 升级前写在 runtime 目录的旧凭据文件从未删除，Browser 仍可经 rw 父目录挂载读到，AC-001 实现不完整

- 严重度：important
- 锚点：AC-001——Browser 的 argv、/proc、ps、环境、日志、异常及全部可读挂载无代理凭据；p082 的原问题正是“除凭据 ro bind 外还挂整个 runtime 目录，ro 只防写不防读”
- 位置：`src/backend/cbrowser/supervisor/core.py:2836-2910`（`start_profile` 写凭据/端点处，无 legacy 清理）、`src/backend/cbrowser/supervisor/volume_spec.py:35`（`browser_volumes` 仍把 `dirs["runtime"]` 整体 rw 挂到 `/run/cbrowser/runtime`）、`src/backend/cbrowser/supervisor/docker_adapter.py:1200-1236`（`prepare_profile_directories` 只建目录、不清理旧文件）
- 问题：本 task 之前每个带代理的 Profile 启动都会把凭据写到 `dirs["runtime"]/proxy_credentials.json`（旧代码 `creds_path = dirs["runtime"] / PROXY_CREDENTIALS_FILENAME`）。t065 把新凭据改写到 secret 目录（`data_root/runtime/.secrets/{profile_id}/`，与 per-profile runtime 目录是兄弟目录、不在其内，隔离方向正确），并删了专用 ro bind，但全 diff 中没有任何一处删除 `dirs["runtime"]/proxy_credentials.json`（diff 内唯一的 unlink 是新路径 secret 凭据与端点文件）。`browser_volumes` 仍把整个 per-profile runtime 目录 rw 挂进 Browser，因此升级后首次启动时，旧文件原样留在原地、Browser 内 `/run/cbrowser/runtime/proxy_credentials.json` 可读——这正是 p082 点名的泄漏向量，也是 AC-001 声称已封闭的路径。progress.md、ADR 036 与 `docs/specs/proxy_management.md` 第 9 节写的“runtime 目录残留旧凭据文件也被忽略、不挂载”在安全语义上不成立：Runner 确实不再读它（“被忽略”属实），但它仍被挂载、仍可读（“不挂载”不属实）。覆盖测试 `tests/unit/test_t065_proxy_forwarder_mounts.py:129`（`test_browser_container_mounts_no_credentials`）明明预置了 legacy 文件，却只断言 volumes 字典里没有名为 `proxy_credentials.json` 的挂载源、没有该 bind——父目录挂载本身不在断言里，测试通过的同时漏洞仍在，给出了虚假覆盖感。新 Profile（runtime 目录从未写过凭据）不受影响；只有升级前跑过代理的老 Profile 受影响。
- 建议：`start_profile` 写端点文件处（或 `prepare_profile_directories`）无条件删除 `dirs["runtime"]/proxy_credentials.json`（`unlink(missing_ok=True)`，与无代理分支删除 secret 凭据/端点文件同一处），并把 `test_browser_container_mounts_no_credentials` 改为断言启动后该文件在磁盘上已不存在（预置 legacy 文件、走 `start_profile`、断言文件消失），而不仅断言 volumes 字典。ADR 036 与 spec 第 9 节的“残留旧凭据文件也被忽略、不挂载”一句，改为“启动时删除 runtime 目录内的旧凭据文件”或删除该断言。

### t065_code_f002 - scheme 为 https 的上游被接受，但转发器从不做 TLS， plaintext CONNECT 发往 TLS 端口必然失败

- 严重度：minor
- 锚点：AC-002——实际引擎通过无认证本地入口使用 HTTP/HTTPS/SOCKS5 上游
- 位置：`src/backend/cbrowser/proxy_forwarder/forwarder.py:340-380`（`_open_http_upstream` 对 `http` 与 `https` 均用 `asyncio.open_connection` 明文 TCP）、`UpstreamConfig.from_dict`（`_PROXY_SCHEMES` 含 `https`，照单全收）、`src/backend/cbrowser/domain/proxy_endpoint.py:28`（产品级 `PROXY_SCHEMES = ("http", "https", "socks5")`，`https://user:pass@host:port` 是合法录入格式）
- 问题：产品接受 `https://` 上游（旧路径下 Chrome 对该上游做 TLS），但转发器对 `https` 上游与 `http` 上游完全同等处理：明文 TCP 发 CONNECT。TLS 上游收到明文后握手失败，`_open_http_upstream` 读不到 `HTTP/1.1 200` 即抛 `UpstreamError` 失败封闭——无凭据泄漏、无直连回退，方向是安全的，但该配置下的代理彻底不可用（旧行为可用）。spike s021 的“HTTP/HTTPS（CONNECT 隧道）”指的是 HTTPS 目标经 CONNECT 建隧道，未覆盖 `https` 上游本身；`tests/unit/test_t065_proxy_forwarder.py` 12 个用例中没有任何 `https` 上游用例。
- 建议：二选一并写测试：① `scheme == "https"` 时以 `ssl.create_default_context()` 包裹上游连接后再发 CONNECT（与 Chrome 原语义一致）；② 在 `UpstreamConfig.from_dict` 明确拒绝 `https` 并给出可读错误、同时在 spec/ADR 写明 `https` 上游暂不支持（不得静默接受后在请求时失败）。p098 的真实链矩阵若含 `https` 上游，应按修复后的语义验收。

### t065_code_f003 - SOCKS5 上游 + IPv6 字面目标被当成域名编码，ATYP 错误导致上游解析失败

- 严重度：minor
- 锚点：AC-002——IPv6 与 SOCKS 远端 DNS 语义正确
- 位置：`src/backend/cbrowser/proxy_forwarder/forwarder.py:383-420`（`_open_socks5_upstream` 的地址编码分支）、`forwarder.py:289-296`（`_handle_connect` 的 `rpartition(":")` 取 host，IPv6 字面量带方括号）
- 问题：IPv6 字面目标（如 CONNECT `[2001:db8::1]:443`，或 absolute-form 的 `http://[2001:db8::1]/`）经 SOCKS5 时，`socket.inet_aton(host)` 只认 IPv4 而抛错，代码随即把目标当域名以 ATYP 0x03 编码——CONNECT 路径下甚至带着方括号（`"[2001:db8::1]"`）当域名发给上游，上游解析失败即 `UpstreamError` 失败封闭。方向安全（无直连、无泄漏），但 SOCKS5 上游 + IPv6 目标的功能是坏的；spike 与单测的 IPv6 覆盖只做到 `http` 上游跑在 `::1`（`test_http_upstream_ipv6_and_special_chars`），未覆盖 SOCKS5 下的 IPv6 目标。HTTP 上游的 CONNECT 路径不受影响（`CONNECT [v6]:port` 原样转发即正确）。
- 建议：`_open_socks5_upstream` 中先 `socket.inet_pton(AF_INET6, ...)` 识别 IPv6 字面量并以 ATYP 0x04 + 16 字节地址编码；`_handle_connect` 解析目标时先剥方括号（IPv6 字面量去括号后再进编码分支）。补一个 SOCKS5 + IPv6 字面目标的桩用例。

### t065_code_f004 - progress.md 的 frontend 门禁摘要写错失败构成，单跑复绿证据未归档

- 严重度：minor
- 锚点：门禁证据核对——progress.md 收尾报告“frontend_test 并行 628 passed / 5 failed，5 条全为 5000ms 超时”
- 位置：`docs/tasks/t065_proxy_credential_isolation/progress.md`（收尾报告测试段）、`.scratch/gate_evidence_t065/logs/frontend_test.log:2766-2806`
- 问题：日志显示 5 条失败中 4 条是 `Test timed out in 5000ms`，第 5 条（`ProfileForm.t058.test.tsx` 的 “a timezone change carries its linked locale change, nothing else”）失败原因是 `AssertionError: expected "vi.fn()" to be called 1 times, but got 2 times`，不是超时。“5 条全为超时”的写法不属实（总数 628 passed / 5 failed 与日志一致，属实）。另外 progress.md 称“4 个文件单跑 18/18 通过”，该复跑的日志未归档进 `.scratch/gate_evidence_t065/`，本轮无法独立复核复跑结论（只核到并行跑日志）。
- 建议：把摘要改为“4 条超时 + 1 条 mock 调用次数断言失败（ProfileForm.t058，疑似负载下重复提交，单跑已复绿）”，并把 4 个文件的单跑日志（或命令与输出摘要）补归档到 evidence 目录。

## 结论

- 本轮新发现：4 条（1 important、3 minor）
- 未进表的提示：
    - 出口探测 helper 仍直接收原始凭据（t052 既有设计，非本 task 引入）：`docker_adapter.py:589-676` 的 probe helper 把 0600 凭据文件 ro 挂进一次性 helper 容器（`data_root/control/probe/{probe_id}/`，用后删除）。`docs/blueprint/security.md` 本轮已如实把它写为“唯一例外”，与 task 范围（Browser 隔离）不冲突，不进 finding。p098 若要收紧此口径，属后续 task 范畴。
    - 引用数字小偏差（不进 finding）：progress.md 称 `forwarder.py` 为 455 行，实测现为 500 行（实现后又有修改，数字未同步）。
    - `handle_client` 的 `readuntil(b"\r\n\r\n")` 未传长度上限，64K 检查只在定界符到达后生效；但唯一客户端是同一隔离 bridge 网络内的 Browser 容器，不构成实际威胁，仅作纵深提示。
    - `src/backend/cbrowser/proxy_forwarder/__pycache__/` 未跟踪且已被 `.gitignore` 排除，不影响指纹与交付。
    - 文件过大（按降级规则仅提示，不进 finding 表）：本 task 触及的存量文件本身已超阈值——`core.py` 现 3402 行、`docker_adapter.py` 现 2942 行、`runner.py` 1104 行、`deploy.sh` 1136 行；本 task 对其多为定点增改（core +189、docker_adapter +370/-、runner 净减），未见由本 task 新堆出的单文件膨胀缺陷。新包 `proxy_forwarder/forwarder.py` 500 行、stdlib only、单一职责，未超阈值。
    - 圈复杂度：本 task 新增/修改函数（`_open_http_upstream`、`_open_socks5_upstream`、`_handle_connect`、`_handle_absolute_form`、`create_proxy_forwarder`、`_replace_proxy_forwarder_only`、`proxy_forwarder_policy_spec`、`resolve_proxy_server_arg`）手算 CC 均 <10，无提示项。
    - 七视角扫描确认：安全（新 secret 目录 `runtime/.secrets/{profile_id}` 与 per-profile runtime 目录为兄弟目录、实测不在任何 Browser 挂载源之下；Runner 只读端点文件、`build_proxy_server_arg` 已删除且全仓无残留引用；转发器日志经 `redact`、错误路径 `_safe_target` 去 userinfo；`LoopbackMappingError` 文本经 `redact(upstream)` 且 `proxy_endpoint_from_credentials` 本就不含 userinfo；网络策略转发器入站仅 18080、出站仅上游 IP 字面量 + Docker DNS、Browser 出站仅转发器）、契约·Breaking（`resolve_proxy_server_arg` 签名改 endpoint_path，唯一调用点 `runner.py:511` 已同步；`NetworkPolicySpec` 的 `input_tcp_ports` 有 role 双向校验；旧测试按 TDD 规则整体删除并留 NOTE，未就地改预期）、性能·资源（转发器单进程单上游、无新增同步 IO 阻塞、relay FIRST_COMPLETED）、健壮性（上游不可达/407/认证失败/DNS 失败均关连接、无响应体、无直连；转发器缺失只重建转发器、预算 300 秒/3 次与 Stream 同型且 key 独立；启动顺序网络 → 转发器 → Browser → Stream、任一环节失败即启动失败封闭）均已扫过，除上表外未命中。
- 总体判断：新隔离架构的方向正确且大部分已落地——secret 目录与 Browser 挂载无交集（实测验证）、Runner 只读无凭据端点、`build_proxy_server_arg` 已删、转发器协议三路（HTTP CONNECT、absolute-form、SOCKS5 远端 DNS）12/12 桩测试通过、失败全部封闭、第六镜像 manifest/env/compose 三处钉版一致、生命周期（创建/分组/标签/网络白名单/readiness/teardown/scan/清理）均已接线。但 f001 是 AC-001 核心主张的实现缺口：升级前遗留的 runtime 目录凭据文件仍可被 Browser 读到，AC-001 的打勾在升级场景下不成立，verdict 必须 FAIL。f002/f003 是 fail-closed 的功能边角缺口，f004 是门禁摘要笔误，均不单独阻断，但应在 Round 2 一并处理。
- 与 test 轴的分歧说明（供父级裁决 finish 口径）：test 轴本轮把 AC-001～004 全部记 TICK-VOID，理由是无真实部署证据、p098 未开。本 code 轴按派发简报明示的 t061/t066/t063/t069 先例口径复核——[deploy] 打勾的前提是实现完成＋云端可验部分实证＋真实拓扑登记 p098＋复验行明写未冒充已验——据此 AC-002/AC-004 记 TICK-VALID（实现与云端证据成立，真实测量属 p098），AC-001 记 TICK-VOID 是因为实现本身有缺口（f001），AC-003 记 TICK-VOID 是因为 reconcile/孤儿/重启等可 mock 验证的生命周期行为在云端零测试证据（[deploy] 豁免只覆盖真实拓扑，不覆盖可 mock 的逻辑）。两轴本轮 overall 均为 FAIL，Round 2 仍需进行；finish 时的 [deploy] 打勾口径请父级按本说明统一定夺。

### AC 复验方式

- AC-001：TICK-VOID，re_verified。task.md 已打勾，但实现不成立：新凭据落点正确（secret 目录经实测不在任何 Browser 挂载源之下；专用 ro bind 已删；Runner 只读端点文件、修订号漂移失败封闭，定向重跑 29 项 t065 测试通过），然而升级前遗留的 `dirs["runtime"]/proxy_credentials.json` 从未删除、经实测仍可通过 rw 父目录挂载在 Browser 内以 `/run/cbrowser/runtime/proxy_credentials.json` 读到（见 f001）；覆盖测试只断言 volumes 字典名、未覆盖父目录可达性。真实拓扑部分已登记 p098、复验行明写未冒充已验，该部分口径无问题。
- AC-002：TICK-VALID，re_verified。实现层已独立复验：转发器 HTTP CONNECT 隧道＋absolute-form 直发、SOCKS5 用户名/密码认证＋域名直通远端 DNS、特殊字符与 IPv6 上游（`::1`）桩测试通过；失败路径（407/上游不可达/认证失败/畸形请求）均关连接、无响应体、无直连；日志脱敏经 `redact`/`_safe_target`。附带两条 minor：f002（`https` 上游无 TLS）与 f003（SOCKS5 + IPv6 字面目标编码错误），均为 fail-closed 边角，待修。真实三协议上游验收登记 p098 第 2 项，未冒充已验。
- AC-003：TICK-VOID，re_verified。实现代码经逐项读核成立：启动顺序网络 → 转发器 → Browser → Stream（`core.py:2927-2940`）；reconcile 只重建转发器（`_replace_proxy_forwarder_only`，预算 300 秒/3 次、key 与 Stream 独立）；readiness 增 `proxy-forwarder` 检查与策略复核；teardown/`_confirm_sandbox_gone`/scan/`get_profile_containers`/cleanup 白名单均计入转发器；未配代理时 secret 凭据与端点文件双删。但云端可验的 reconcile/孤儿恢复/重启/未配代理模式行为零测试证据（`_replace_proxy_forwarder_only` 无任何测试调用；test 轴同判），[deploy] 豁免只覆盖真实拓扑、不覆盖可 mock 的生命周期逻辑，故打勾不成立。真实故障封闭验收登记 p098 第 3 项。
- AC-004：TICK-VALID，trust_prior。实现层：转发器为本机单跳、无新增同步阻塞；云端证据只有首包开销 smoke（<250ms 绝对阈值、无基线对比）。按派发简报的 [deploy] 先例，AC-004 的基线对比与报告属真实部署测量、登记 p098 第 4 项、复验行明写未冒充已验，打勾成立；但与 test 轴结论分歧（test 轴因无基线证据记 VOID），请父级统一定夺——p098 第 4 项必须实际跑出对比数字后才算真实链闭环。
- AC-005：TICK-VALID，re_verified。diff 未触及任何 Selkies 相关文件（pin/asset probe/wheel cache/controlled build/vendor 安全）；本轮用 gate venv 独立重跑 `test_t065_proxy_forwarder.py`、`test_t065_proxy_forwarder_mounts.py` 与 Selkies 五件套（`test_t063_selkies_controlled_build`、`test_t043_selkies_pin`、`test_t044_selkies_asset_probe`、`test_t045_selkies_wheel_cache`、`test_vendor_selkies_security`），58 passed；第六镜像钉版与 manifest/env 一致性已逐项核对（deploy.sh manifest 含 `proxy-forwarder`、env 含 `CBROWSER_PROXY_FORWARDER_IMAGE=sha256:`、compose.yaml 强制传入）。

coverage = 5 / 5

verdict: FAIL

## Round 1（code 轴·第二份独立审阅，2026-11-14T09:41:58+08:00）

本节为并行派发的第二份 code 轴独立审阅（与本文件上文的第一份 code 审阅同为 Round 1、互不知晓）。我独立读完了全部 diff（2094 行）与未跟踪新文件（`proxy_forwarder/` 包、`test_t065_*` 两测试、`docs/spikes/s021_*`、`docs/pending/todo/p098_*`），用 gate venv（`/tmp/t065_gate_venv`，`uv pip install -r scripts/gate-requirements.txt` 新建）重跑了 t065 相关 140 例单元测试（全过），并用本地桩对转发器做了 4 项实测探针（SOCKS5 IPv6、absolute-form 407、超大请求头、基础协议）。以下只写与上文不同的结论与新增 finding；与上文重复的 finding 不另立编号。

reviewed_scope: 96b7ac3770b9beb7

### 对上文 finding 的独立复核

- 上文 t065_code_f001（升级遗留 runtime 凭据文件可读）：独立确认成立，同意 important。我补充的证据：同函数已有对应先例却未照做——`core.py:2961` 在把 `agent_secret.txt` 移进 secret 目录时 unlink 了 runtime 目录下的旧文件；`test_browser_container_mounts_no_credentials`（`tests/unit/test_t065_proxy_forwarder_mounts.py:141-177`）预置了 legacy 文件却只断言 volumes 字典、未断言文件不可读，给了假信心。
- 上文 t065_code_f002（`https` 上游无 TLS）：事实确认成立，但我不同意 minor 定级，应为 important。`https://` 是产品合法录入格式（`domain/proxy_endpoint.py:28`），基线行为是 Chromium 对其做 TLS；t065 后该配置下全部请求失败（不是边角降级，是整类上游不可用），且 `UpstreamConfig` 接受 https 后静默失败。AC-002 点名了“HTTPS 上游”，缺失实现不是部署延期能覆盖的。
- 上文 t065_code_f003（SOCKS5 + IPv6 目标编码错误）：事实经我实测确认（桩 SOCKS5 收到 `('domain', b'[2001:db8::1]')` 与 `('domain', b'2001:db8::1')`，上游 rep=4 拒绝），但我不同意 minor 定级，应为 important。Chromium 对 IPv6 源站一律发方括号 CONNECT，因此 SOCKS5 上游 + IPv6 目标全量失败；AC-002 点名了 IPv6 语义正确，现有测试只覆盖“上游主机是 `::1`”，未覆盖 IPv6 目标。
- 上文 t065_code_f004（progress.md 前端门禁摘要笔误）：我未独立核查该条（未读 frontend 日志），不发表意见。

### 本节新增 Findings

### t065_code_f005 - absolute-form 经 HTTP 上游拿到 407 时，407 响应体被原样透传给 Browser

- 严重度：minor
- 锚点：AC-003（认证拒绝的失败封闭；另与 spike/ADR/`__init__.py`“均关闭连接、无响应体”不一致）
- 位置：`src/backend/cbrowser/proxy_forwarder/forwarder.py:270-322`（`_handle_absolute_form`）
- 问题：`_handle_absolute_form` 对 HTTP 上游建明文 TCP 后从不检查上游响应状态，直接 `_relay` 双向转发。实测复现：上游对 absolute-form GET 回 `407 + 5 字节体 "hello"`，Browser 侧完整收到 `HTTP/1.1 407 Proxy Authentication Required … hello`。而 CONNECT 路径（`_open_http_upstream`，`forwarder.py:350-381`）对 407 是明确关连接、无响应体；`__init__.py` 的失败封闭承诺也是“closes the client connection with no response body”。请求本身仍失败、无凭据泄漏、无直连回退，所以只定 minor；但同一 407 在两条路径行为不一致，且 407 响应体是上游可控内容。
- 建议：absolute-form 的 HTTP 上游路径先读响应头：非 2xx（至少 407）即关连接、不透传体；与 CONNECT 路径的失败封闭语义对齐。

### t065_code_f006 - 用户名无密码时 Basic 认证缺冒号，不合 RFC 7617

- 严重度：minor
- 锚点：行为缺陷（AC-002 上游认证互操作）
- 位置：`src/backend/cbrowser/proxy_forwarder/forwarder.py:99-103`（`UpstreamConfig.basic_auth`）
- 问题：`basic_auth` 在 `password is None` 时返回 `base64(username)`，即 `Basic base64("user")`；RFC 7617 要求 user-id 后恒有冒号（密码可空，应为 `base64("user:")`）。严格按 `:` 切分 userinfo 的上游会拒掉这类请求；旧路径里 Chromium 对仅用户名凭据发的是带冒号的形式。仅用户名的凭据较少见，且现有测试只覆盖有密码的情形，故定 minor。
- 建议：`secret = f"{self.username}:{self.password or ''}"`，即密码为 None 时仍保留冒号；补仅用户名桩测试。

### t065_code_f007 - 超大请求头触发未捕获的 LimitOverrunError，`_MAX_HEAD_BYTES` 检查是死代码

- 严重度：minor
- 锚点：行为缺陷（健壮性；AC-003 畸形请求失败封闭）
- 位置：`src/backend/cbrowser/proxy_forwarder/forwarder.py:179-233`（`handle_client`）
- 问题：`handle_client` 用 `readuntil(b"\r\n\r\n")` 读请求头，只捕获 `TimeoutError`/`IncompleteReadError`/`ConnectionError`。`StreamReader` 默认 limit 为 65536，与 `_MAX_HEAD_BYTES = 65536` 相等，所以超限请求头在返回前即抛 `asyncio.LimitOverrunError`（`ValueError` 子类，不在捕获之列），随后读到的 `len(head) > _MAX_HEAD_BYTES` 检查永不可达。实测复现：发送 70KB 请求头，事件循环报 `Unhandled exception in client_connected_cb ... LimitOverrunError('Separator is found, but chunk is longer than limit')`。连接本身随后关闭（客户端读到 `b''`），无挂起、无泄密，故定 minor；影响是每次超大畸形请求都在日志里留一条未处理异常栈。上文结论段只把 `readuntil` 未传上限记为纵深提示，未确认到该未捕获异常。
- 建议：捕获 `asyncio.LimitExceededError`（含 LimitOverrunError）并 `_close(writer)`；或把 `readuntil` 的 limit 参数显式设为 `_MAX_HEAD_BYTES` 并保留长度检查，二者取其一，不要两套机制并存且一套失效。

### t065_code_f008 - 新函数 create_proxy_forwarder 圈复杂度约 18

- 严重度：minor
- 锚点：圈复杂度标准（新建函数一上来 ≥ 15 → minor；按 prompt 手算规则：基数 1，每个 if/elif/for/while/catch/三元/短路与或约 +1）
- 位置：`src/backend/cbrowser/supervisor/docker_adapter.py:2233-2402`
- 问题：新建的 `create_proxy_forwarder` 圈复杂度约 18：镜像校验、secret 校验、0600 校验、上游解析、extra_hosts 分支、容器创建、策略安装、就绪等待、失败回收（嵌套 try/except + `isinstance` 分流 + loopback 专项）全挤在一个函数里。目前未观测到由该复杂度直接导致的行为缺陷，故只定 minor。注：上文结论称本 task 新增/修改函数手算 CC 均 <10，与按 prompt 规则的计数不符（本节计数含 catch 与短路与或，`_open_socks5_upstream` 约 19、`create_proxy_forwarder` 约 18、`from_dict` 约 15、`handle_client`/`_handle_absolute_form`/`read_forwarder_endpoint` 约 11），请父级按 prompt 规则为准。
- 建议：拆为校验（镜像/secret/0600/上游）、创建、策略安装+就绪、失败回收四个阶段，或把 loopback 错误映射抽为 helper。

### t065_code_f009 - 新函数 UpstreamConfig.from_dict 圈复杂度约 15

- 严重度：minor
- 锚点：圈复杂度标准（新建函数一上来 ≥ 15 → minor；计数规则同 f008）
- 位置：`src/backend/cbrowser/proxy_forwarder/forwarder.py:64-96`
- 问题：新建的 `from_dict` 圈复杂度约 15：8 组字段校验全为平铺的 `if` + 短路条件。校验本身是正确的（测试覆盖了 8 类坏输入），分支之间无嵌套、无状态耦合，故只定 minor。
- 建议：把逐字段校验抽为小函数表（如 `field: validator` 映射）或拆为 `_validate_scheme/_validate_host/...`，降低单函数分支数。

### 本节结论

- 本节新发现：5 条（全部 minor：f005、f006、f007、f008、f009）；另对上文 f002、f003 的定级持异议（应为 important 而非 minor，理由见上），对上文 f001 同意 important。
- 未进表的提示：
  - 文件过大（结论段提示，不进表）：`docker_adapter.py` 2942 行（本 task 净 +260 行：315 增 / 55 删）、`core.py` 3402 行（净 +179 行）；新建 `proxy_forwarder/forwarder.py` 500 行，已超实现源码 400 行 minor 阈值（上文“未超阈值”一说不准确；按降级规则仍只提示，不进表）；新建测试 `test_t065_proxy_forwarder.py` 657 行、`test_t065_proxy_forwarder_mounts.py` 658 行（均超测试 600 行 minor 阈值）。
  - 圈复杂度 ≥ 10 提示（不进表）：`_open_socks5_upstream` 约 19（已产出可观测缺陷，见上文 f003，不另立复杂度 finding）；`handle_client` 约 11、`_handle_absolute_form` 约 11、`read_forwarder_endpoint` 约 11；`start_profile` 约 33、`start_browser_container` 约 16（既存巨函数，本 task 仅增少量分支，不另立 finding）。
  - 范围外观察（测试层，test 轴注意，不进 code finding 表）：`tests/unit/test_t035_proxy_runtime.py` 的 `test_credentials_revision_mismatch_fails_closed` 现为空转通过——它向新签名的 `resolve_proxy_server_arg` 传入凭据文件（scheme socks5），新实现因“非端点文件”而非修订号比对而拒绝；修订号比对本身由新测试 `test_runner_fails_closed_on_endpoint_problems` 的 stale-revision 用例覆盖，旧测试名实不符。
  - 与上文的分歧（请父级裁决）：① f002/f003 定级（上文 minor，本节 important）；② AC-002/AC-004 的打勾口径（上文按 t061/t066/t063/t069 先例记 TICK-VALID，本节认为实现缺失与证据缺失本身即 VOID，见下 AC 行）；③ AC-003（上文因 reconcile 等零测试证据记 VOID，本节认为 code 轴看实现层，实现与云端证据成立，记 VALID）。两节 overall 均为 FAIL，Round 2 仍需进行。
- 总体判断：FAIL——上文 f001（important）未解决，且本节复核 AC-001/AC-002/AC-004 打勾作废；本节新增 5 条 minor 不单独阻断。
- 系统性 follow-up：无（本节 5 条均为 t065 内缺口；s021 结论未入 findings 的工具链缺陷已挂 p093 第 6 项，不重复报告）。

### AC 复验方式

- AC-001：TICK-VOID，re_verified。专用 bind 已删、secret 目录隔离、Runner 只读端点文件均已实现，但升级路径的旧凭据文件仍留在 Browser 可读的 runtime 目录内（上文 f001），AC-001 点名的父挂载读取路径未封闭。
- AC-002：TICK-VOID，re_verified。HTTP/HTTPS 目的地 CONNECT、SOCKS5 远端 DNS、特殊字符已由本地桩测试实证；但 SOCKS5 的 IPv6 目标恒失败（上文 f003）、scheme=https 上游无 TLS（上文 f002），两处 AC 点名语义缺失实现且无测试覆盖——缺失实现不是部署延期，[deploy] 先例口径不能覆盖。
- AC-003：TICK-VALID，re_verified。407、SOCKS5 认证失败、上游宕机、畸形请求均关连接、无直连（本地桩实证，我重跑 t065 相关 140 例全过）；转发器缺失只重建转发器、teardown/scan/readiness 计入转发器；absolute-form 407 透传响应体为 minor 偏差（本节 f005），请求仍失败、无直连回退，不推翻 AC。reconcile 分支缺直接单元测试是测试覆盖缺口，归 test 轴，不构成 code 轴的实现缺失。
- AC-004：TICK-VOID，re_verified。交付内容中无任何基线对比：无 pre-t065 成功率/首包延迟基线、无 407 往返报告；唯一测量是 5 样本 loopback smoke（中位数 <250ms，无基线对照），AC-004 要求的对比报告不存在，已顺延 p098；“先例”属于 implementer 自述，不能作为打勾证据。
- AC-005：TICK-VALID，re_verified。diff 未碰 Selkies 固定制品/SHA256 校验、未新增 CDN；我重跑 t063 Selkies 受控构建与 t068 pinning：16 通过，2 失败为 t068 的 linux-x64 引擎构建未进 ADR 021 manifest（与 t065 改动面无交集的既存平台差异）。

coverage = 5/5

verdict: FAIL

## Round 3 (2026-11-14T10:43:59+08:00)

code 轴·确认轮。

本节为确认轮：独立复核 Round 1 两份 code 审阅的 9 条 finding（f001～f009）是否真正消除，不采信 progress.md 处置表自述。方法：逐条读声称修改的生产代码（文件:行），核对配套测试是否真实断言所称行为（非 mock 掉被测逻辑），并用 gate venv（`<home>/workspace/CBrowser/.scratch/gate_venv/bin/python`，`PYTHONPATH=src/backend`）独立重跑三件套 `tests/unit/test_t065_proxy_forwarder.py`、`tests/unit/test_t065_proxy_forwarder_mounts.py`、`tests/unit/test_t065_proxy_forwarder_lifecycle.py`：**45 passed**（协议 17、挂载 17、生命周期 11）。

reviewed_scope: c6aaa3c19097122d

### 前轮 finding 复核

- t065_code_f001（important，升级遗留 runtime 凭据文件可读）：**已消除**。`src/backend/cbrowser/supervisor/core.py:2885-2892` 在 `start_profile` 写端点前无条件 `(dirs["runtime"] / PROXY_CREDENTIALS_FILENAME).unlink(missing_ok=True)`，位于 `proxy_credentials is not None` 分支之外、有代理与无代理启动均执行，并附注释说明 rw 父目录挂载下残留即仍可读；与 `agent_secret.txt` 旧文件清理（同函数 `:2971`）同一模式。测试 `tests/unit/test_t065_proxy_forwarder_mounts.py:489-491,617-622`（`test_start_profile_with_proxy_writes_secret_and_endpoint`）走真实 `start_profile`，预置旧文件后断言 `not (dirs["runtime"] / "proxy_credentials.json").exists()`，同时断言 secret 目录新文件 0600 与无凭据端点文件内容；我重跑该文件 17/17 通过。ADR 036（`docs/blueprint/decisions.md:476-479`）与 spec 第 9 节（`docs/specs/proxy_management.md:63`）均已改为“无条件删除，不依赖‘忽略’”，原不成立表述已订正。
- t065_code_f002（important，`https` 上游无 TLS）：**已消除**。`src/backend/cbrowser/proxy_forwarder/forwarder.py:424-433` 新增 `_tls_context`（scheme https 时 `ssl.create_default_context()`，否则 None）；`_open_http_upstream`（`:452`）与 `_open_http_proxy_tcp`（`:416`）的 `asyncio.open_connection` 均传 `ssl=_tls_context(config)`，覆盖 CONNECT 与 absolute-form 两条路径。测试 `tests/unit/test_t065_proxy_forwarder.py:646-699`（`test_https_upstream_wraps_tls`）用 openssl 自签证书搭真实 fake TLS 上游，断言 `proxy.tls_seen == [True]`（CONNECT）与 `[True, True]`（absolute-form），且明文 CONNECT 不可能通过该上游的 TLS 握手；我重跑通过。注：该测试为绕过自签证书校验而 monkeypatch `ssl.create_default_context` 为 unverified context——被测的 TLS 包裹行为本身仍真实（服务端强制 TLS），仅生产默认校验未在该用例内被验证；属 test 轴可注明的口径点，不构成 code 缺陷。
- t065_code_f003（important，SOCKS5 + IPv6 目标编码错误）：**已消除**。`_handle_connect`（`forwarder.py:303-307`）先剥方括号；`_open_socks5_upstream`（`:522-534`）先 `socket.inet_pton(AF_INET6, host)` 成功即 ATYP 0x04 + 16 字节，失败才试 IPv4（0x01）、再当域名（0x03）；`_bracket_host`（`:277-285`）保证 HTTP CONNECT 行仍带方括号。测试 `:598-628`（`test_socks5_ipv6_literal_target_uses_atyp4`）对 `[2001:db8::1]:443` 断言 `socks.address_types == [(0x04, inet_pton(...))]` 且 `requested == ["2001:db8::1:443"]`，同时端到端拿到 origin 响应；我重跑通过。
- t065_code_f004（minor，progress.md 前端门禁摘要写错）：**已消除**。progress.md 收尾报告现为“frontend_test 并行 628 passed / 5 failed：4 条 5000ms 超时＋1 条 ProfileForm.t058 mock 调用次数断言失败（期望 1 次、实调 2 次）”。单跑日志 `.scratch/gate_evidence_t065/logs/frontend_test_single_run.log` 已归档，我独立核对：4 个文件（ProfileCreateDialog 7、ConfigTab 3、ProfileForm.t058 5、SettingsPage 3）合计 18 passed、全部 exit 0，与“4 个文件单跑 18/18 通过”一致。
- t065_code_f005（minor，absolute-form 407 响应体透传）：**已消除**。`_handle_absolute_form`（`forwarder.py:361-392`）对 HTTP/HTTPS 上游先读响应头：407 抛 `UpstreamAuthError`，其他非 2xx 抛 `UpstreamError`，均不向 Browser 写任何字节；`handle_client`（`:248-257`）捕获这两类异常后仅 `_close(writer)`。测试 `:701-728`（`test_absolute_form_407_body_is_not_relayed`）用错密码触发 407 + 5 字节体 `b"hello"`，断言 Browser 侧收到 `b""` 且 origin 零连接；我重跑通过。
- t065_code_f006（minor，用户名无密码 Basic 缺冒号）：**已消除**。`UpstreamConfig.basic_auth`（`forwarder.py:122-129`）现为 `f"{self.username}:{self.password or ''}"`，附 RFC 7617 注释。测试 `:730-757` 断言仅用户名时为 `base64(b"user:")`、无凭据时为 None；我重跑通过。
- t065_code_f007（minor，超大请求头未捕获 LimitOverrunError）：**已消除**。`handle_client`（`forwarder.py:206-220`）的 except 增加 `asyncio.LimitOverrunError`，并注释说明长度检查仅为第二层；`_handle_absolute_form` 的上游读头处（`:375`）同样捕获。测试 `:757-783` 发 70KB 请求头，断言连接关闭且无未处理异常；我重跑通过。残留一点见本轮新发现 f010（同一族的第三处 `readuntil` 漏捕获，minor，不阻断）。
- t065_code_f008（minor，`create_proxy_forwarder` 圈复杂度约 18）：**已消除**。`docker_adapter.py:2235-2284` 的 `create_proxy_forwarder` 现为编排器（校验 → 创建 → 策略安装 → 失败回收），按 prompt 手算 CC 约 2（基数 1 + 1 个 except）；拆出的助手 `_validate_forwarder_image`（`:2286`，CC 约 3）、`_load_forwarder_upstream`（`:2298`，CC 约 6）、`_run_forwarder_container`（`:2333`，CC 约 2）、`_install_forwarder_policy`（`:2397`，CC 1）、`_reclaim_failed_forwarder`（`:2428`，CC 约 8）均 <15。挂载测试 17/17 重跑通过，行为未见回归。
- t065_code_f009（minor，`UpstreamConfig.from_dict` 圈复杂度约 15）：**已消除**。`from_dict`（`forwarder.py:105-120`）现仅做 dict 检查后委托 6 个小校验函数（`:55-94`，每函数 CC ≤3：scheme/host/port/username/password/revision）；`from_dict` 本身 CC 约 2。校验语义与 Round 1 复核的“8 类坏输入”一致（`test_config_validation_fails_closed` 在重跑的 45 例内通过）。

### 本轮新发现

### t065_code_f010 - `_open_http_upstream` 的 CONNECT 握手读头仍未捕获 LimitOverrunError

- 严重度：minor
- 锚点：行为缺陷（健壮性；f007 同族残留，修复时三处 `readuntil` 只补了两处）
- 位置：`src/backend/cbrowser/proxy_forwarder/forwarder.py:469-474`
- 问题：`forwarder.py` 内三处 `readuntil(b"\r\n\r\n")`：`handle_client`（`:206`）与 `_handle_absolute_form` 的上游读头（`:369`）在 f007 修复中均已捕获 `asyncio.LimitOverrunError`，但 `_open_http_upstream` 的 CONNECT 握手读头（`:469-474`）except 仍只有 `(TimeoutError, IncompleteReadError, ConnectionError)`。上游若返回超 64 KiB 的 CONNECT 响应头，`LimitOverrunError`（`ValueError` 子类）既不在此处被捕，也不在 `handle_client` 的外层 except（只捕 `UpstreamError`/`UpstreamAuthError`/`ConnectionError`/`IncompleteReadError`/`TimeoutError`）之列，将以未处理异常逃出 `handle_client`、在事件循环日志留栈，且客户端 writer 未被显式关闭（Browser 侧 CONNECT 挂起直至自身超时）。概率极低（上游是运营方配置的代理，CONNECT 响应头超 64 KiB 属于病态），无泄漏、无直连回退，故 minor，不阻断本轮 PASS；建议与 f007 同法补捕获并转为 `UpstreamError`。
- 建议：`:473` 的 except 元组补 `asyncio.LimitOverrunError`，与另两处 `readuntil` 对齐。

## 结论

- 前轮 finding 复核：9/9 已消除（f001 important、f002/f003 important、f004～f009 minor）；本轮新发现：1 条 minor（f010，非阻断）。
- 未进表的提示：
    - f002 测试的 monkeypatch 说明见 f002 复核注（TLS 包裹真实，生产默认校验不在该用例内验证）；test 轴若要收紧可补一个不断言校验豁免的说明，不属 code 缺陷。
    - 文件过大 / 圈复杂度（结论段提示，不进表）：`core.py` 3412 行、`docker_adapter.py` 3009 行仍超阈值，但本 task 仅定点增改，未新堆单文件膨胀缺陷；新建 `forwarder.py` 607 行超 400 行 minor 阈值（stdlib only、单一职责，按降级规则只提示）。
    - 七视角扫描确认：安全（secret 目录与 Browser 挂载无交集、旧文件已删、日志脱敏、非 2xx 不透传体）、契约·Breaking（无公开签名变更）、性能·资源（TLS 只在 https 上游建连时一次握手、无新增同步阻塞）、架构（f008/f009 拆分后职责清晰）、健壮性（除 f010 外三处读头均已捕获 LimitOverrunError）均已扫过，除 f010 外未命中。
- 总体判断：9 条前轮 finding 均已由代码与真实断言测试证实消除，AC-001～005 打勾在云端可验层面成立（真实拓扑部分已登记 p098 且未冒充已验）；仅剩 1 条 minor 新发现，不阻断。verdict: PASS。
- 系统性 follow-up：无（f010 为 t065 内一处 minor，由 implementer 在后续 task 或收尾中顺手补捕获即可，不另立 tid）。

### AC 复验方式

- AC-001：TICK-VALID，re_verified。f001 已消除：`core.py:2890` 无条件删除 runtime 目录旧凭据文件，真实 `start_profile` 测试预置旧文件断言启动后消失（mounts.py:622），我重跑 17/17；secret 目录隔离与专用 bind 已删沿用 Round 1 实证。真实 Docker/Chrome 拓扑验收登记 p098 第 1 项，未冒充已验。
- AC-002：TICK-VALID，re_verified。f002/f003 已消除：https 上游真实 TLS 握手测试与 SOCKS5 IPv6 ATYP 0x04 测试均在我重跑的 45 例内通过；f005/f006 同轮消除；HTTP CONNECT、absolute-form、SOCKS5 远端 DNS 沿用 Round 1 桩实证。真实三协议上游验收登记 p098 第 2 项，未冒充已验。
- AC-003：TICK-VALID，re_verified。Round 1 第一份审阅记 VOID 的理由（reconcile/孤儿/重启等云端零测试证据）已被新建的 `tests/unit/test_t065_proxy_forwarder_lifecycle.py`（11 测试，调真实 `core._reconcile_profile`/`_replace_proxy_forwarder_only`，仅 Docker 客户端为 fake）消除，我重跑 11/11 通过；f005/f007 失败封闭同轮补齐。真实故障封闭验收登记 p098 第 3 项，未冒充已验。至此两份 Round 1 审阅对 AC-003 的分歧（VOID vs VALID）已收敛为 VALID。
- AC-004：TICK-VALID，trust_prior。按父级 2026-11-14 09:46 裁决：基线对比属 p098 真实部署测量（p098 第 4 项已明确承接，smoke 测试已改名 `test_first_byte_smoke_reports_latency_samples`、只报告样本不冒充基线）；云端可验部分（转发器本机单跳、无新增同步阻塞、smoke 5/5 存活）在我重跑的 45 例内通过。至此两份 Round 1 审阅对 AC-004 的分歧（VALID vs VOID）按父级裁决收敛为 VALID。
- AC-005：TICK-VALID，re_verified。diff 未触及任何 Selkies 固定制品/SHA256 校验、未新增 CDN；我重跑 t065 三件套 45/45 通过，Selkies 回归沿用 Round 1 的 58 passed 实证与 progress.md 收尾报告的门禁重跑（contract 257 passed、unit 2221 passed/5 failed 与基线同签名）。

coverage = 4/5

verdict: PASS

## Round 4 (2026-11-14T11:09:04+08:00)

确认轮：只复核 Round 3 新发现 f010 的修复，不重审 f001～f009（Round 3 已收敛）；三件套重跑确认本次改动未破坏前轮结论。

reviewed_scope: 4dd19121e8e93b53

### t065_code_f010 复核 — 已消除

- 证据（代码）：`forwarder.py` 三处 `readuntil(b"\r\n\r\n")` 现全部捕获 `asyncio.LimitOverrunError`：`handle_client`（:206，except :211）、`_handle_absolute_form` 的上游读头（:369，except :375）、`_open_http_upstream` 的 CONNECT 握手读头（:470，except :475，含 `asyncio.LimitOverrunError,  # f010: third readuntil site; f007 fixed the other two`）。第三处 except 现为 `(TimeoutError, IncompleteReadError, LimitOverrunError, ConnectionError)`，先 `_close(writer)` 再转 `UpstreamError("upstream closed the CONNECT handshake")`——失败封闭，与另两处对齐。
- 证据（SOCKS5 无同类问题）：`_open_socks5_upstream` 及后续握手只用定长 `readexactly`（:504/:521/:545/:550/:552/:554/:557）；全文件 grep 核实 `readuntil` 仅上述三处，无第四处。
- 证据（测试真实断言，非空转）：新测试 `tests/unit/test_t065_proxy_forwarder.py::test_oversized_connect_response_head_fails_closed`（:785）用假上游回 70 KiB CONNECT 响应头（超 64 KiB 限），断言 Browser 侧 `read()` 得 `b""`、且 asyncio 错误日志中无 `LimitOverrunError`；上游在响应后保持连接 0.5s，挂起型失败也会暴露为超时而非快过。
- 反向验证（我方复做）：临时删掉 :475 的 `LimitOverrunError` 项后，该测试 FAIL，栈顶为 `asyncio/streams.py readuntil` 抛 `LimitOverrunError: Separator is found, but chunk is longer than limit`；恢复该行后测试通过。注：反向验证中途备份文件一度未含该行（原因未明，疑为工具层执行次序异常），我以本轮开局读到的原文逐字补回该行，并以行数 612、:475 行原文、三件套 46/46 三项校验恢复无误；生产代码净改动为零。
- 处置行：progress.md Review 处置表已有 `t065_code_f010` 一行（minor/已修，列出修复、测试与反向验证），checker 上轮判 INCOMPLETE 的唯一原因已补齐。
- 结论：f010 已消除；本轮无新 finding。

### 三件套重跑

- 命令：`PYTHONPATH=src/backend <home>/workspace/CBrowser/.scratch/gate_venv/bin/python -m pytest tests/unit/test_t065_proxy_forwarder.py tests/unit/test_t065_proxy_forwarder_mounts.py tests/unit/test_t065_proxy_forwarder_lifecycle.py -q`
- 结果：46 passed（协议 18、挂载 17、生命周期 11），与实现者所称 46/46 一致；新测试单跑通过，反向验证单跑失败（见上）。

### AC 表

- AC-001～005 维持 Round 3 结论，全 TICK-VALID（AC-001～004 按 Round 3 口径，AC-005 re_verified；真实 Docker/Chrome/引擎拓扑验收仍登记 p098，不冒充已验）。本次改动只触及 `_open_http_upstream` 一处 except 与一个新增测试，未动 f001～f009 修复点；三件套 46/46 通过即未破坏前轮结论的证据。

### AC 复验方式

- AC-001：TICK-VALID，re_verified。本轮改动未动 f001 修复点（`core.py:2890` 删旧凭据文件）与挂载隔离；我重跑挂载套件 17/17 通过。
- AC-002：TICK-VALID，re_verified。协议套件 18/18 通过（含新测试；https 真实 TLS、SOCKS5 IPv6 测试均在内）；f010 的 CONNECT 失败封闭现由新测试覆盖。
- AC-003：TICK-VALID，re_verified。生命周期套件 11/11 通过；f010 补齐后三处读头失败封闭均有测试覆盖。
- AC-004：TICK-VALID，trust_prior。按父级 2026-11-14 09:46 裁决，基线对比属 p098 真实部署测量；云端可验部分（转发器本机单跳、无新增同步阻塞）未受本轮改动影响。
- AC-005：TICK-VALID，re_verified。本轮 diff 未触及任何 Selkies 固定制品/SHA256 校验、未新增 CDN；三件套 46/46 通过。

coverage = 5/5

verdict: PASS

## Round 5 (2026-11-14T11:20:06+08:00)

确认轮：复算 reviewed_scope 指纹并确认 Round 4 结论仍成立；自 Round 4 以来唯一改动是主会话补填 progress.md 收尾报告的两行文字（结果行把“确认轮 Round 4 待执行”改为已完成、review 行填入 Round 4 实测结论），无任何代码或测试改动。

reviewed_scope: 4dd19121e8e93b53

### 指纹复算

- 用 `repo_task.monitoring.review_scope_fingerprint`（diff_anchor `a4726b33bbfa3e2262a7b5a450271f2c6fdeebe4`，与 progress.md front matter 一致）对当前 worktree 独立重算：`4dd19121e8e93b53`，与 Round 4 指纹逐字一致。
- 变化核对：自 Round 4（11:09:04）后唯一改动的文件是 `docs/tasks/t065_proxy_credential_isolation/progress.md`（mtime 11:17:43）；其余文件 mtime 均在 Round 4 之前（forwarder.py 11:08:36、test_t065_proxy_forwarder.py 10:51:45、core.py 09:57:05、review_code.md 11:11:54 与 review_test.md 11:13:07 为两轴 Round 4 节落盘）。按 `monitoring._review_scope_path` 口径，progress.md 与 review 文件同属 REVIEW_PROCESS_FILES、排除在指纹之外，故指纹不变；补填本身未使指纹失效。
- checker 实测（本轮落盘前）：`review_level=full、code_verdict=PASS、test_verdict=PASS、overall=PASS、review_scope=ok、ac_review=ok、round=4、next_action=finalize`。

### Round 4 结论复核

- f010 消除状态仍在位：`forwarder.py:469-477` CONNECT 握手 except 含 `asyncio.LimitOverrunError`（附 f010 注释，注明为三处 `readuntil` 中第三处），先 `_close(writer)` 再转 `UpstreamError("upstream closed the CONNECT handshake")`；SOCKS5 段只用定长 `readexactly`，无同类问题。
- f001～f009 修复点抽查仍在位：`core.py:2890-2892` 无条件删除 runtime 目录旧凭据文件（附注释说明 rw 父目录挂载下残留仍可读）；`forwarder.py:424-433` `_tls_context`（https 上游包 TLS，`:416`/`:452` 两处传入）；`:522-534` SOCKS5 IPv6 先 `socket.inet_pton(AF_INET6)` 走 ATYP 0x04；`basic_auth` 恒拼冒号（RFC 7617）；`create_proxy_forwarder` 与 `UpstreamConfig.from_dict` 已拆分为小编排器与小校验函数。
- 三件套重跑：`PYTHONPATH=src/backend` + gate venv（`<home>/workspace/CBrowser/.scratch/gate_venv/bin/python`），`tests/unit/test_t065_proxy_forwarder.py tests/unit/test_t065_proxy_forwarder_mounts.py tests/unit/test_t065_proxy_forwarder_lifecycle.py -q` → **46 passed**（协议 18、挂载 17、生命周期 11），与 Round 4 的 46/46 一致。
- 本轮无新 finding。

### 结论

- 指纹与 Round 4 一致，Round 4 的 PASS 结论仍成立；AC-001～005 打勾在云端可验层面成立（真实拓扑部分已登记 p098 且未冒充已验）。verdict: PASS。

### AC 复验方式

- AC-001：TICK-VALID，re_verified。f001 修复点仍在位（`core.py:2890` 无条件删旧凭据文件）；挂载套件 17/17 在本轮重跑的 46 例内通过；真实 Docker/Chrome 拓扑验收登记 p098 第 1 项，未冒充已验。
- AC-002：TICK-VALID，re_verified。协议套件 18/18 在本轮重跑的 46 例内通过（含 https 真实 TLS、SOCKS5 IPv6 ATYP 0x04 测试）；真实三协议上游验收登记 p098 第 2 项，未冒充已验。
- AC-003：TICK-VALID，re_verified。生命周期套件 11/11 在本轮重跑的 46 例内通过；f010 补齐后三处读头失败封闭均有测试覆盖；真实故障封闭验收登记 p098 第 3 项，未冒充已验。
- AC-004：TICK-VALID，trust_prior。按父级 2026-11-14 09:46 裁决，基线对比属 p098 真实部署测量（p098 第 4 项已明确承接）；云端可验部分（转发器本机单跳、无新增同步阻塞）未受自 Round 4 以来的改动影响。
- AC-005：TICK-VALID，re_verified。自 Round 4 以来无任何代码改动，diff 仍未触及任何 Selkies 固定制品/SHA256 校验、未新增 CDN；三件套 46/46 通过。

coverage = 5/5

verdict: PASS
