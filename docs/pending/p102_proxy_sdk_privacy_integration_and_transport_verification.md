---
pid: "p102"
slug: "proxy_sdk_privacy_integration_and_transport_verification"
status: "closed"
resolution: "resolved"
reason: "已完成 Spike s022（linux-arm64 / cloakbrowser 0.6.4 + chromium-146.0.7680.177.3"
fix_ref: "main"
---
# p102 统一 Profile 出口与浏览器启动契约，先以 spike 验证代理隐私能力

- 来源：2026-11-15 用户讨论代理泄露与浏览器环境真实性后，明确要求“记录一个 pending，详细写”；随后要求更新架构根因，并明确询问是否应先执行 spike。继承单人、单机 Docker 产品范围。
- 现象：BrowserRunner 将代理仅作为 Chromium `--proxy-server` 参数传入，没有传给 CloakBrowser SDK 的 `proxy=`；浏览器联网配置与 SDK GeoIP/WebRTC 自动配置使用不同输入。曾尝试用 `proxy_enforced` 强制已配代理 Browser 出口收紧（`f04293f`），当日因破坏引擎启动 readiness 撤销（`047b4d1`），该机制不复存在。
- 影响：已配代理环境可能无法正确生成代理出口对应的 GeoIP/WebRTC 配置，出现启动失败、指纹与实际出口不一致等问题；运行期策略复核可能将正常的受限策略判为漂移并执行 fail-closed。网页 WebRTC、QUIC、DNS 是否实际绕过代理，尚无本次真实引擎抓包证据，不能写成已确认泄露。
- 根因：Profile 出口与浏览器启动契约分散。第一层，业务手工拼接代理 CLI，绕过官方 SDK 对代理、认证、GeoIP 与 WebRTC 的协调；第二层，启动、复核、恢复和 probe 分别重建出口策略，缺少统一的出口计划输入，易产生分歧；第三层，各层测试单独通过，却缺少“同一出口计划贯穿浏览器、辅助查询与网络边界”的端到端不变量。不能只补一处参数或一个布尔值后宣称根因闭环。
- 测试缺口：现有代理 URL 拼装、规则渲染、locale 参数传递、HTTP 代理 E2E 各自通过，但没有覆盖 SDK 代理输入与自动探测、启动与复核规则等价、探针真实网络约束以及网页 UDP/DNS 实际出口，详见测试缺口与验收矩阵。
- 线索：`.scratch/proxy_privacy_sdk_repro/reproduce.py`、`results.json`，以及同目录 `sdk_auth_branch_probe.py`、`sdk_auth_branch_results.json`；离线 SDK helper、认证分派与生产策略表达式复现，无 Docker 操作、真实浏览器启动、真实凭据或外网请求。
- 处理：main；resolution=resolved；reason=已完成 Spike s022（linux-arm64 / cloakbrowser 0.6.4 + chromium-146.0.7680.177.3；linux-x64 146.0.7680.177.5 记为 NOT_RUN / USER_WAIVED）并沉淀 d046/d047 与 ADR 038；落地 EgressPlan、BrowserRunner SDK proxy= 集成及 --disable-quic/--force-webrtc-ip-handling-policy=disable_non_proxied_udp，统一 startup/review/probe 双栈 proxy_enforced=True 并补全单测与 E2E；全量门禁与 E2E 已通过（all_passed=true）。
- 核对时间：2026-11-15T18:15:21+08:00。
- 核对基线：`60190da02dfff4a9edc90f959018ff633d1e779b`；CloakBrowser SDK `0.6.4`；Linux arm64 引擎 `146.0.7680.177.3`、Linux x64 引擎 `146.0.7680.177.5`，以 `src/backend/cbrowser/engine_artifacts.py` 为准。
- 关联：`docs/pending/p078_egress_proxy_enforcement_and_webrtc_dns_leak.md`、`docs/findings/d031_authenticated_socks5_supported.md`、`docs/pending/p060_proxy_link_first_egress_identity.md`。

## 用户目标与范围

已配代理环境使用真实代理出口；同一 Profile 维持稳定、自洽的浏览器身份，尽量保留自然的 WebRTC、QUIC、DNS 行为。代理不可用时允许报错或断网，不能悄悄回退宿主公网出口。

安全与真实性分别验证：页面显示代理 IP 不等于真实数据包经过代理；“未发现真实 IP”也不能单独证明浏览器行为自然。不能通过只改检测页可见值、无条件删除 WebRTC API 或统一关闭 QUIC 宣称完成目标。

本条沿用 `p078` 已归档裁决，不修改归档记录，不重新要求未配代理环境使用不同出口。未配代理环境使用本机真实 IP 属预期行为；多个未配代理 Profile 共用宿主出口也不属于本条缺陷。`f04293f` 引入的 `proxy_enforced` iptables 出口收紧已撤销（`047b4d1`），现行出口边界依赖 Chromium `--proxy-server` 的 fail-closed 语义，不再在 iptables 层叠加收紧。

不在范围：独立桌面 app、Mihomo 节点管理、全局 VPN、多人协作、跨环境剪贴板、标签页管理、强制一 Profile 一公网 IP、为未配置代理环境自动购买或分配代理。不预设 TUN、sidecar、透明转发器或 watchdog 为必选实现，由 spike 证据决定是否需要；不将容器数量作为先决约束，优先保证职责清晰、出口可验证与实现最简。

“真实隐私指纹”在本条转化为可验证要求：真实浏览器内核运行、所选出口实际生效、指纹跨 API 自洽、同一 Profile 重启保持身份。CloakBrowser 修改 Chromium 指纹输出，不等于运行另一台真实硬件；不承诺与任意真机完全不可区分、任何网站永不识别或指定风控分数。

## Commit 演变与回归起点

下表来自历史源码、关键 diff 与 SDK 调用形状核对，描述机制演变，不否定各阶段原有安全需求，不修改历史归档。

|Commit|当时变化|本次定位|
|---|---|---|
|`8ff9fd2`|初始 BrowserRunner 使用官方 SDK `proxy=cfg.proxy`|SDK 可收到业务代理输入，作为历史基线|
|`5252f75`|仍保留 `proxy=cfg.proxy`|代理协调入口尚未丢失|
|`c30cf20`|首次移除 SDK `proxy=`，新增 `build_proxy_server_arg()` 与 `--proxy-server` 手工拼装|本次 SDK 代理/GeoIP/WebRTC 输入脱节的回归起点；不能错记为后续删除转发器才引入|
|`eb5ccfb`|引入认证转发器，SDK `proxy=` 仍未恢复|改变代理网络路径，但未解决官方 SDK 协调入口缺失|
|`c1df58a`|删除认证转发器，继续手工 CLI，仍未传 SDK `proxy=`；将 d031 的 SOCKS5 认证能力用于解释 HTTP/HTTPS 内联认证|SOCKS5 实测结论不能泛化为所有协议、平台与 build；需要回到官方 SDK 的精确版本分派|
|`75911f0`|统一拒绝带认证 HTTP/HTTPS 上游|当前失败封闭保护，真实新路径验证前保留；不能把手工内联失败等同官方 SDK 所有认证路径永久不支持|
|`f04293f`|新增代理态默认拒绝，只在 startup 传 `proxy_enforced`|收紧方向符合 p078 裁决，但遗漏 review/probe；实为破坏引擎启动链路（readiness 超窗），已在同日后撤回|
|`047b4d1`|撤销 `proxy_enforced`，恢复 browser 出口尾部 ACCEPT|实测出口全 DROP 断掉引擎启动所需链路；出口边界回归依赖 `--proxy-server` fail-closed，本条后续方案不得再以裸布尔值拼装切口|
|`60190da`|按单人单机产品裁决归档 p078 等条目|本条继承“无代理可直连、有代理不可旁路”边界，不复活已裁减范围|

## 已确认事实与复现

### 1. 代理命令行与 SDK `proxy=` 脱节

代码路径：

1. `src/backend/cbrowser/runtime_agent/runner.py:596` 调用 `resolve_proxy_server_arg()`。
2. `runner.py:706` 将返回值加入 `extra_args`，即 `--proxy-server=...`。
3. `runner.py:723` 调用 `launch_persistent_context_async(args=extra_args, geoip=cfg.geoip, ...)`，未传 `proxy=`。复现脚本通过 AST 核对该调用形状。
4. 本地安装 SDK `cloakbrowser/browser.py` 的 `maybe_resolve_geoip()` 只从 `proxy` 参数提取代理，不从 `args` 的 `--proxy-server` 提取；`_append_webrtc_exit_ip()` 将 GeoIP 返回 IP 注入 `--fingerprint-webrtc-ip`。

离线复现调用真实 SDK helper，仅 mock 出口查询。样本地址使用文档保留段，不是真实宿主或代理 IP：

|场景|SDK 接收的代理|已复现行为|
|---|---|---|
|已在 args 设置代理，GeoIP 开，时区/语言未同时显式指定|`None`|调用 `resolve_proxy_geo_with_ip(None)`；将 mock 的直接出口结果写入 WebRTC IP 参数|
|已在 args 设置代理，GeoIP 开，仅语言显式指定|`None`|仍调用直接出口语义的查询，显式语言保留，自动字段与 WebRTC IP 可能取错出口|
|已在 args 设置代理，GeoIP 开，时区与语言均显式指定|`None`|不做出口 IP 查询，返回 `exit_ip=None`，不会自动注入 WebRTC IP|
|已在 args 设置代理，GeoIP 关|`None`|不做 GeoIP/出口查询，不自动注入 WebRTC IP|
|对照：SDK `proxy=` 正确传入，时区/语言需推断|指定代理 URL|查询收到指定代理，WebRTC 参数使用该查询结果|
|对照：SDK `proxy=` 正确传入，时区/语言均显式指定|指定代理 URL|仍经指定代理查询出口 IP，供 WebRTC 参数使用|

分类：已确认 SDK 输入错误与自动配置行为。SDK 将 `None` 解释为本机直接出口，但实际环境中的请求是否能发出取决于容器网络策略。受限出口可能使查询失败并导致启动失败；其他网络配置可能返回非预期出口。离线 mock 不能证明当前运行容器已获得或泄露宿主 IP。

### 2. `--fingerprint-webrtc-ip=auto` 不是当前用户可用的补救开关

真实 SDK `_resolve_webrtc_args()` 在 `proxy=None` 时删除 `--fingerprint-webrtc-ip=auto`，不查询代理出口；正确传 `proxy=` 的对照可解析该参数。另经 `src/backend/cbrowser/launch_args.py` 实际校验，当前用户参数白名单拒绝此 flag。因此这是 SDK 接入契约线索，不能误报为所有现有 Profile 都会触发的独立 bug，也不能直接让用户在高级参数中填写它作为解决方案。

### 3. 启动策略与运行期复核不一致（`proxy_enforced` 路径已撤销）

以下为 `f04293f` 时期的复现事实，`047b4d1` 撤销 `proxy_enforced` 后相关代码分支已删除，问题不复现，但「生命周期各路径分别重建策略」的根因仍在，本条后续方案须以此为前提：

- `docker_adapter.py` 为已配代理 Browser 生成代理 TCP 端点及 Docker DNS 允许项；曾启动传 `proxy_enforced=bool(upstream_url)`（已删除）。
- `browser_policy_spec()` 重建复核策略时曾未传 `proxy_enforced`，按默认取 `False`（已随字段删除）。
- `network_policy.py` 曾在 browser 且 `proxy_enforced=False` 时生成公网尾部 ACCEPT、为 `True` 时生成尾部 DROP（已恢复为 browser 一律尾部 ACCEPT）。
- `verify_policy()` 对实时规则与期望规则做全等比较；`supervisor/core.py:615` 的巡检路径在不匹配时调用 `fail_close_container()`，并标记 `browser_policy_drift`；`core.py:1060` 的 readiness 路径也使用该策略。

复现脚本曾从生产 `start_browser_container()` 提取策略字典表达式，再调用 `browser_policy_spec()`、渲染器与 verifier，得出 startup `True`/复核 `False` 不一致。该差异已随字段撤销消失。

分类：历史复现已失效；遗留的是「各生命周期路径缺少统一出口计划」的结构性缺口，仍需本条 spike 与正式实现覆盖。

### 4. 出口探针尚未继承代理态出口约束（`proxy_enforced` 路径已撤销）

`f04293f` 时期 `_install_probe_network_policy()` 只传 browser role 与代理 `allowed_tcp`，遗漏 `proxy_enforced`，导致探针策略比 Browser 宽松。`047b4d1` 撤销 `proxy_enforced` 后二者同为 browser 尾部 ACCEPT，表面一致；但结构性缺口仍在：probe 与 Browser 各自由不同 helper 派生策略，缺少同一出口计划约束，未来启用任何代理态收紧时仍可能再次分歧。

现有 probe helper 自身仍显式使用代理发请求，策略较宽不等于已证明其请求必然直连。修复需覆盖“探针与 Browser 同网络视角”的既有要求，避免探针成功而 Browser 实际失败。

### 5. DNS 和 UDP 允许范围已确认，泄露结论待实测

已配代理启动策略仍显式允许 Docker DNS `127.0.0.11:53/udp`，且 IPv4 OUTPUT 提前允许 loopback。即使尾部 DROP 或阻断公网 53，也不能据此证明 Docker 内置解析器不会代容器查询外部域名。

当前代理态 `allowed_udp` 仅含 Docker DNS，未包含 SOCKS5 UDP relay。UDP ASSOCIATE 返回的 relay 地址/端口可以不同于代理 TCP 端点，单纯放行 TCP 代理 IP:port 不足以支持该链路。是否被引擎使用、relay 实际端点、现有规则是否导致 QUIC 回退或失败，必须用受控 SOCKS5 UDP 代理验证；不能直接认定 QUIC 已绕过代理，也不能为保留 QUIC 无条件放行全部 UDP。

### 6. SDK 认证分派区分架构与精确 build

新增离线脚本 `sdk_auth_branch_probe.py` 调用本地 SDK `0.6.4` 的真实 `_resolve_proxy_config()`，仅 patch `cloakbrowser.config.get_platform_tag`，显式传当前固定 `browser_version`，不启动浏览器、不连接代理。认证输入在内存生成，不写入结果。结果如下：

|平台与固定 build|带认证 HTTP|带认证 HTTPS|带认证 SOCKS5|
|---|---|---|---|
|`linux-arm64` / `146.0.7680.177.3`|生成 Playwright proxy dict，保留认证字段，不生成代理 CLI|同左|生成内联代理 CLI|
|`linux-x64` / `146.0.7680.177.5`|生成内联代理 CLI|同左|生成内联代理 CLI|

分派依据是 `cloakbrowser/config.py` 的 `HTTP_PROXY_INLINE_AUTH_MIN_VERSION`：`linux-x64` 阈值 `146.0.7680.177.5`，`linux-arm64` 阈值 `148.0.7778.215.3`。当前 arm64 build 未达到 HTTP 内联阈值，SDK 会选择另一条官方认证路径，并非必然不支持 HTTP 代理认证。

证据等级仅为 **SDK 分支已复现**，不是 **真实代理认证已通过**。Playwright 认证拦截、浏览器 build、协议与目标行为仍需 spike；x64 分派也不能替代 x64 真机/容器验证。`d031` 既有 arm64 手工 CLI 实验结论继续作为该路径证据，但不可扩大为所有官方 SDK 路径或所有平台结论。

## 上游能力与版本边界

本次上游资料来自会话中已核对的官方仓库 README、CHANGELOG 和本机安装 SDK 元数据。上游声明用于确定验证方向，不替代本仓真实网络实验。

|能力|上游信息|当前项目应如何判断|
|---|---|---|
|WebRTC 候选 IP 替换|0.3.20 记录引入 `--fingerprint-webrtc-ip` 与 GeoIP 自动注入|当前代内核有相关能力；先在 spike 中对照正确 SDK 输入，再检查候选与真实发包，两者分别验收|
|SOCKS5 UDP / QUIC|0.3.24 记录 Linux `146.0.7680.177.2` 支持 UDP ASSOCIATE 承载 QUIC/HTTP3|当前固定 146 后续 build 应纳入能力验证；代理端能力、relay、防火墙均需验证，不能套用未修改 Chromium 的 TCP-only 限制|
|普通代理目标域名解析|Chromium 文档说明普通 HTTP、SOCKS5 URL 请求可以由代理解析|需要检查其他组件直接 DNS、预解析、STUN/TURN 域名与 DoH 路径，不能由普通网页成功推出全量防漏|
|透明代理模式 DNS|本机 `cloakbrowser-0.6.4.dist-info/METADATA` 将 `--fingerprint-transparent-proxy-dns` 标为 `155.0.8059.39.1+`；透明代理主 flag 标为 151+|当前固定 146 不得直接套用；SDK 版本与浏览器二进制版本是两层，需逐项核实|
|DNS/connect/SSL timing 隐藏|上游列为代理检测信号处理|属于可见指纹处理，不证明 DNS 请求或数据流已通过代理|

Star 数量、宣传截图、检测页评分均不能当作安全审计或真实流量证据。现有证据不足以归因“内核完全没考虑隐私”，也不足以归因“所有泄露只由 cbrowser 接入造成”。

## 待验证路径

1. 实际 BrowserRunner 启动链中，SDK GeoIP 查询会失败、直连还是使用宿主已有路由；分别记录不同 GeoIP/显式时区语言组合，不能跨场景外推。
2. 当前固定 146 在正确接入下，网页 WebRTC 的 ICE host/srflx/relay 候选及 STUN、TURN、媒体数据实际出口；候选 IP 改写是否仅改变可见值、是否遗漏其他网页可见地址。
3. SOCKS5 UDP relay 可用、不可用、端口变化以及拒绝 UDP 时，QUIC/HTTP3 的真实连接、HTTP/2 回退与错误表现。能力不足时允许受控降级，禁止以降级为理由开放直连。
4. Browser DNS、Docker 内置 resolver、宿主转发、预解析、DoH、代理端解析的实际路径。DNS 检测页通常显示递归解析器出口，不能仅凭该值断言网站看到宿主真实 IP；解析器与网页出口也不必字面相同。
5. IPv6 是否具有未受同等约束的出口，代理域名多地址与地址变化时策略是否仍准确且失败封闭。
6. 未来启用任何代理态出口收紧后，巡检是否正确判定策略漂移，以及启动、恢复附着、readiness、probe 各路径行为是否一致（现状 `proxy_enforced` 已撤销，无额外收紧）。
7. 网页 WebRTC 与 Selkies 画面传输分别验证。二者运行于独立 Browser/Stream 容器；网页隐私修复不得误伤 Selkies 媒体与现有远程控制。

## 架构原则已明确，具体实现待 spike

遵循项目“架构至上、拒绝局部补丁、零兼容性负担”：从统一出口与启动契约修正，不以到处补参数、恢复自研认证转发器或累加协议特判掩盖根因；同时选择满足目标的最简实现，不为彻底而增加不必要层次。

1. **出口意图显式化**：明确 `direct` / `proxied`，不以 `None`、代理凭据文件读取失败或 SDK 参数缺失推导“允许直连”。已配置代理但信息缺失时失败封闭；无代理 Profile 保持既定本机出口行为。
2. **统一出口计划**：由同一 Profile 配置事实派生 SDK 输入、辅助查询要求与唯一 IPv4/IPv6 网络策略；公开快照与秘密材料分离，`credential_revision` 与凭据脱敏继续有效。计划的具体数据结构、模块落点和动态端点协调方式由 spike 后决定，不提前制造新抽象。
3. **生命周期共用**：启动、巡检、恢复附着、readiness、probe 使用同一出口计划与策略派生入口；probe 不能因 helper 不同而拥有更宽公网权限。代理意图不再由宽松默认掩盖。
4. **复用官方 SDK**：让成熟 SDK 根据真实平台与精确 build 协调代理、认证、GeoIP、WebRTC。验证通过后删除业务手工代理 CLI 旁路、重复认证禁用与重复策略分支，不保留新旧双启动路径；SDK 内部经验证的版本分派属于官方能力，不在业务层复制，也不误当作本仓遗留兼容层。
5. **保护有明确替换条件**：真实 spike 证明新官方路径之前，保留现有 HTTP/HTTPS 内联认证拒绝等失败封闭保护；验证成功后按能力矩阵替换，不把当前 guard 当作永久能力结论。保留何种协议需由真实契约决定，不能用一处 `proxy=` 修改或离线分支结果跳过认证验证。
6. **字段推断与防泄露解耦**：GeoIP 只控制地域字段自动推断；关闭 GeoIP、显式指定时区/语言都不能撤销代理出口与 WebRTC 防护。自动值须来自实际所选出口，显式用户值保留。
7. **自然功能与网络约束同时成立**：原生 WebRTC/QUIC 可用时保留；UDP relay 与 DNS bootstrap 只开放经过验证的必要路径，不放行任意 UDP、DNS 或公网出口。当前组合无法满足用户目标时，形成明确架构/引擎选型结论，不能以隐蔽降级削减目标。
8. **身份稳定**：同一 Profile 的 seed、已有存储与既有指纹身份保持，不借修复重新随机化。网页 WebRTC 与独立 Selkies 媒体分开约束。

## 实施前置：先 spike，再冻结方案与修改生产代码

本条有真实认证、SDK 辅助请求、网页 UDP、动态 relay 与 Docker DNS 等未验证外部契约，**必须先 spike 验证，再冻结实现方案并正式修改生产代码**。当前离线 helper 复现只确定回归机制，不能代替该前置。

依项目现行 `.repo_template/skills/task-work/SKILL.md`「实施」第 1 步和 task 模板「未知契约清单」：

1. 建 task 时将相关未知契约列为 `UNVERIFIED-SPIKE`，不是裸 `UNVERIFIED`；用户不可替代输入仍按 `UNVERIFIED-BLOCKING` 分类，不能伪装成可自行验证。
2. 可以在同一 task 内先做 spike，不强制另建独立 spike task。`task-work` 先实验，把标记改写为已验证结论与验证方式；随后用 `task.py preflight {tid} --owner-id {owner_id} --require-verified` 得到严格 PASS，才进入生产实施。
3. 一次性实验仅写 `.scratch/`；若建立正式 spike，必须经 `.repo_template/scripts/spikes.py new` 分配真实 sid，不手造编号或目录。正式 spike 补齐 `report.md`、finding、采纳结论、后续 tid 或无需后续理由，并依 repo-hygiene 流程归档；finding 创建走 `findings.py new`。
4. 方案冻结引用 spike 对应平台/build 的结论，明确剩余不支持与未完成项。未完成的必要契约不得被当成已验证来通过严格 preflight；若目标无法满足，先修订明确的架构/引擎选型结论。

本次只更新 pending：未分配 sid、未建立 task、未执行真实 spike，未创建 finding，也不把以下实验计划写成已完成。

### Spike 范围与最小实验计划

只对决定出口/启动架构的未知契约做受控实验，不把后文完整产品验收矩阵全部前置。保留最小身份连续性检查与 Selkies 冒烟，完整产品回归留在正式实现验收。

|实验|方法与需回答问题|
|---|---|
|固定版本与平台|记录 SDK、精确引擎 build、OS/arch、代理实现/版本及协议能力；当前 arm64/x64 分别成行。无法本机实跑的架构标未完成，声明支持平台的相关能力不得由另一架构推断|
|受控隔离拓扑|使用隔离 Docker 网络、受控代理、目标回显、STUN/TURN、DNS/DoH 与必要抓包点；SDK 辅助探测与 Browser 置于与生产等价的受限 netns，记录规则与出口。不能用宿主 curl 成功代替 Browser 同视角证据|
|启动路径 A/B|固定相同配置，对照当前手工 CLI 与官方 SDK `proxy=`；观察实际浏览器启动、代理访问与辅助请求。只改变待测契约，不能在对照中偷偷放宽出口|
|真实认证|HTTP/HTTPS/SOCKS5 分别验证无认证、正确/错误凭据及特殊字符；记录代理挑战、协商、转发与目标是否收到请求，不泄露凭据。区分手工内联失败、SDK 路径失败和代理本身不支持|
|GeoIP 与显式字段|GeoIP 开/关，时区与语言未指定、指定一项、两项均指定；辅助服务日志与抓包证明查询实际出口，显式值正确保留，GeoIP 关闭仍不撤防|
|网页 WebRTC|分别收集 ICE 可见候选与受控 STUN/TURN/媒体接收端来源，配合 netns 抓包；不能把候选替换当成真实媒体代理证据|
|QUIC 与动态 UDP relay|真实 SOCKS5 UDP ASSOCIATE 记录 relay 返回地址/端口，并改变 relay IP/端口；比较支持 UDP、不支持 UDP、relay 拒绝/失效场景。回答 relay 如何进入受控策略、是否安全更新、失败是否直连；不直接放行全部 UDP|
|DNS 与 DoH|唯一域名配受控权威日志、递归解析与抓包，覆盖 Docker DNS、代理端解析、预解析、DoH 及 STUN/TURN 域名；解释各查询路径。递归解析器 IP 不要求与网页出口字面相同|
|IPv4/IPv6|分别验证当前平台可运行的地址族及代理 bootstrap/实际目的连接；未执行明确标记，不由 IPv4 结果推断 IPv6|
|真实生命周期策略|对有/无代理分别检查 startup/review/恢复/probe 派生策略与实时规则；正常受限策略通过复核，真实漂移和代理/认证/relay 失败不能开放直连，probe 与 Browser 权限等价|
|边界冒烟|Profile 最小重启不重置既有 seed/身份；网页侧实验不破坏独立 Selkies 画面、输入与必要媒体链路，结果分别记录|

测试 HTTPS 代理时区分“与代理端 TLS 连接”与“通过 HTTP CONNECT 访问 HTTPS 网站”，避免将两种协议误记为同一能力。代理出口与目标源地址必须由受控接收端证据确认；外部检测页只辅助观察。

### Spike 输出、通过标准与失败处理

- 能力矩阵按 **OS/arch + 精确 build + SDK 版本 + 代理协议 + 认证方式 + UDP + DNS 路径** 逐项记录 `VERIFIED` / `UNSUPPORTED` / `未完成`，同时关联原始证据与适用范围。`UNSUPPORTED` 要有完成实验的明确否定证据；环境缺失、超时或受阻只能标未完成。
- 输出脱敏版本与拓扑、启动输入摘要、实际规则、pcap 摘要、代理与目标接收端日志、权威 DNS 查询、失败注入及恢复结果。上游声明、离线分派、真实浏览器/网络实验分别标明，不混为同一证据等级。
- 报告必须回答：官方 SDK 路径能否在受限 netns 内完成代理认证和辅助请求，保留所需自然 WebRTC/QUIC/DNS 行为；动态 UDP relay 与 DNS 能否被明确约束；代理失败能否持续阻断直连；同一出口计划能否驱动 startup/review/恢复/probe。
- 通过指已验证必要组合能够同时满足真实出口、自然功能与失败封闭，或对不支持组合形成明确且符合用户目标的架构处理结论。必要场景未完成、检测页变绿、只看到替换后的候选、仅离线 SDK 分支正确，都不是通过。
- 如果当前 SDK/引擎或网络能力无法满足要求，返回架构/引擎选型结论，说明证据与未满足目标；不默认恢复自研认证转发器，不默认增加 TUN/sidecar/watchdog，也不默认禁用全部 WebRTC/QUIC。由证据选择满足目标的最简职责划分，不以历史实现或容器数量绑定设计。

## 现有测试为何漏过

|现有覆盖|已覆盖内容|本次缺口与应补层级|
|---|---|---|
|`tests/unit/test_t035_proxy_runtime.py`|代理 URL 拼装、编码、认证限制、凭据版本等|未验证 SDK `proxy=` 与浏览器参数一致；补触达真实 Runner SDK 调用边界及 SDK 自动探测输入的单测|
|`tests/unit/test_t053_fontconfig_locale.py`|捕获 SDK launch kwargs，验证 locale/timezone/GeoIP 与 fontconfig 传递|捕获存在，但断言围绕语言，SDK 被替身截断；补有代理组合及 helper 契约，不应声称完全没有 SDK 参数测试|
|`tests/e2e/test_browser_runtime_e2e.py` 的 t035 代理测试|受控 HTTP 代理实际转发、CDP 版本等|`create_snapshot_file()` 默认 `geoip=False`，t035 未覆盖开启自动 GeoIP；未覆盖 UDP/STUN/DNS，也未证明整个 Supervisor 巡检链|
|`tests/unit/test_network_policy.py`|browser 出口尾部 ACCEPT、其他 role 尾部 DROP、IPv6 渲染等|仅检查构造 spec 的渲染结果，未从真实 startup/review/probe 方法取输入做等价验证；`proxy_enforced` 相关两例已随撤销删除|
|`tests/unit/test_t026_network_policy_verify.py`|实时规则比较、规范化与 fail-closed|缺“生命周期各路径派生策略等价”的回归|
|`tests/unit/test_t026_supervisor_convergence.py` 等|策略不匹配触发收敛处理|double 只按 role 返回预设结果，未连接真实 adapter 策略、真实 renderer 与 verifier|
|`tests/unit/test_t052_supervisor_probe.py`|helper 创建、代理允许项、执行与清理|断言 `allowed_tcp`，未断言默认拒绝、IPv6 或与 Browser 策略等价；需补探针旁路负例|

## 验收矩阵

下表是未来修复验收要求，本次登记仅完成离线复现与源码核对；未完成项不得写成已通过。

|场景|必须验证结果与证据|
|---|---|
|无代理 Profile|继续使用本机出口，正常启动；不自动分配代理、不强制各环境不同 IP|
|有代理，GeoIP 开，时区/语言未指定或仅指定一项|网页请求、SDK 出口查询、自动字段来源同一所选出口；显式值保留；使用受控不同出口对照，不能只断言参数字符串|
|有代理，GeoIP 开，时区/语言均显式指定|两项保留；WebRTC 防护仍可确定正确出口，不因跳过地域推断失去保护|
|有代理，GeoIP 关|不发无授权的地域探测；仍维持代理出口边界与网页防漏，不能依赖 GeoIP 开关作为唯一保护|
|SOCKS5 无认证/有认证、错误凭据|支持组合真实通行；错误凭据失败封闭；日志及证据不含凭据|
|HTTP/HTTPS 代理|spike 验证通过的官方 SDK 组合真实通行；验证新路径前保留现有拒绝保护。区分平台/build 与具体认证路径，不把手工内联失败泛化为整体不支持；通过后移除被替代的重复禁用逻辑|
|代理 IP 字面量/域名、多 A/AAAA、解析变化|端点解析和允许项对应实际连接；bootstrap 查询范围可说明；解析或更新失败不开放直连|
|IPv4 / IPv6|两族分别测试网页、STUN、DNS 与直连负例；未部署或未执行的场景标为未完成，不支持结论须有对应否定证据，不能把未执行记成通过|
|WebRTC|受控 STUN/TURN 与网页 ICE 数据联合容器抓包；候选与实际数据出口分别断言，无宿主公网地址旁路；保留所支持的正常会话能力|
|QUIC / HTTP3，代理支持 UDP|真实 SOCKS5 UDP ASSOCIATE 与 relay 日志证明通过代理；防火墙只允许合法 relay，目标接收端证明来源|
|代理不支持 UDP或 relay 不可达|有明确错误或正常 TCP/HTTP2 降级，无公网 UDP 直连；不承诺所有 HTTP 代理承载 QUIC|
|DNS / DoH / 预解析|唯一测试域名、受控权威 DNS 日志及容器/宿主抓包证明查询路径；识别 Docker DNS 转发与代理 DNS；不要求解析器 IP 与网页出口字面相同|
|代理停止、认证失败、relay 失效、重启恢复|网页和辅助查询不回退宿主直连；可观测错误与恢复行为准确；直连负例必须确认被阻断|
|启动、巡检、恢复附着与 readiness|相同代理配置生成等价 IPv4/IPv6 策略；正常受限策略不被误判漂移，真实策略缺失仍执行失败封闭|
|出口 probe|与实际 Browser 约束相符；受控尝试绕过代理失败；不能只看到探针返回正确 IP 就认定策略相同|
|Profile 重启与指纹一致性|seed、已有存储与既有身份保持；UA/Client Hints、平台、字体、屏幕、时区、语言、WebRTC 可见值不产生新矛盾；能力与真机差异如实记录|
|Selkies|既有画面、音频、输入与连接恢复正常；独立验证 Stream 媒体，不将其 ICE 结果冒充网页 WebRTC 验收|

真实网络实验使用受控代理、回显服务、STUN/TURN、DNS 与必要抓包，保存脱敏摘要、版本、拓扑、规则和失败注入结果。外部检测页仅作辅助观察，不能代替传输证据；无需把任意商业网站检测通过率作为闭环门槛。

## 复现步骤与材料

从仓库根执行：

```sh
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B .scratch/proxy_privacy_sdk_repro/reproduce.py
```

脚本禁止 socket connect 与 DNS 查询，mock SDK 的出口服务，读取真实 SDK helper、真实启动策略表达式与 adapter 复核/probe 方法。结果写入 `.scratch/proxy_privacy_sdk_repro/results.json`，应包含：SDK `0.6.4`、6 个 GeoIP/显式字段组合、`proxy` keyword 缺失、auto flag 与白名单对照、Docker DNS/loopback 允许项，以及 `live_browser_leak_verified=false`。`proxy_enforced` 的 startup/review 不等与 probe 默认 ACCEPT 属撤销前复现，`047b4d1` 后不再复现。

SDK 认证分派新增离线对照：

```sh
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B .scratch/proxy_privacy_sdk_repro/sdk_auth_branch_probe.py
```

结果单独保存在 `sdk_auth_branch_results.json`，不覆盖原复现结果。6 个平台/协议分支断言通过；仅证明当前 SDK 如何分派，`real_proxy_auth_verified=false`、`real_browser_launched=false`，尚未完成正式 spike。

`.scratch/` 材料仅作当前机器研究线索，不入库；立项时将必要复现转成触达生产逻辑的正式回归，不能依赖已忽略目录才能复核需求。

## 参考与证据边界

- [CloakBrowser README](https://github.com/CloakHQ/CloakBrowser)：上游 WebRTC、SOCKS5 UDP、指纹与代理能力声明，随版本变化；不作为本仓实际生效证明。
- [CloakBrowser CHANGELOG](https://github.com/CloakHQ/CloakBrowser/blob/main/CHANGELOG.md)：0.3.20、0.3.24 等历史引入记录；固定二进制仍需实测。
- 本地 SDK `cloakbrowser/browser.py`、`cloakbrowser/geoip.py` 及 `cloakbrowser-0.6.4.dist-info/METADATA`：SDK 分支行为与 flag 最低二进制版本；不把包版本当作二进制版本。
- [Chromium 代理文档](https://chromium.googlesource.com/chromium/src/+/HEAD/net/docs/proxy.md)：固定代理、解析与 fallback 语义；单一固定代理不可达通常报错，不能把“代理断开必然回退直连”当通用事实。
- [Chromium SOCKS 配置说明](https://www.chromium.org/developers/design-documents/network-stack/socks-proxy/)：URL 代理与其他 DNS 组件区分；部分历史说明不能直接覆盖 CloakBrowser 自定义 UDP 实现。
- [RFC 8828](https://www.rfc-editor.org/rfc/rfc8828.html)：WebRTC 地址暴露、代理旁路条件与功能/隐私权衡；地址改写与网络出口约束须分别验证。
