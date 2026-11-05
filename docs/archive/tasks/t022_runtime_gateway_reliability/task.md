# Task spec

## 背景

Runtime、Supervisor 与 Gateway 的成功/健康报告、重放、配额与资源边界存在耦合。将命令结果、观测状态、诊断事件和可选初始化结果分开，保证隔离条件下合法会话可恢复；默认搜索按用户 D1=B 失败不阻断浏览器。

## 契约区

### 范围

- Browser Agent/runner/CDP、Supervisor 生命周期/事件/网络/helper、Gateway 注册与 Viewer 清理、Stream 策略/停止及 SDK 适配。
- 私有 SSE 快照与实时历史交接、受验证缓存代次、stop 结果的全链路契约和生成产物。
- A55 端到端独立初始化状态、现有 Profile 页面提示与受控重试；本项需要的 API/前端最小接线由本 task 完成，不留到另一个 task 才可观察。

### 非范围

- 不整改、转报或同步 repo_template，不修改其脚本、hook、契约测试、模板规则或账本示例；不创建已拒绝 A36/R10 的后续任务。
- 不建设已拒绝 A37/R11 的正式备份、恢复、迁移演练、生产切换闭环；不执行生产停服、数据删除或外部发布。
- 不重开 t009/t010/t012，不恢复 legacy，不扩大单机/同机 Chrome 的部署包络，不恢复 TURN。
- 现有 t019 的 ICE 建链延迟、t020 的字体配置各自保持范围；本 task 不重复实现或把其验收顺带标为完成。

### 验收标准

<!-- 规范（门禁必留，不得删除） -->

只写可观察、可独立验证的行为；每条使用稳定且不复用的 `AC-NNN`。需真实部署或人工环境验证时在编号前加 `[deploy]`。创建时均为未勾选（`- [ ]`）；实施验证通过后由实施 Agent 就地打勾（`- [x]`）；由 Review Agent 独立复核打勾真实性。技术选型不作为行为 AC。review 判 FAIL 且需修改交付内容时，实施 Agent 撤回全部打勾，修复并重验后重新打勾；reviewer 用 `TICK-VALID` / `TICK-VOID` 逐条判定。

<!-- /规范 -->

- [x] AC-001（A3）：CDP 断线重连并重新设置下载行为后，只有收到匹配成功 ACK 才报告 rearm 健康；错误 ACK、无 ACK、超时及再次断线保持不健康，唯一 reader 不因自等待而死锁。
- [x] AC-002（A8）：诊断事件区分已接受、永久拒绝、暂不可用；永久语义拒绝只入死信一次并持久推进游标，暂不可用重试后可成功，认证/限流/网关故障不会被误判为永久语义拒绝；诊断投递不推进业务运行状态。
- [x] AC-003（A9）：X11 权限辅助容器仅持完成权限修正必需的能力，根文件系统只读且禁止提权；权限设置成功、失败和取消均有明确结果并清理受管 helper。
- [x] AC-004（A10）：同轮混合扫描合法、缺失与畸形 config-version 标签时，只拒用异常资源，其他 Profile 继续协调；未知身份资源不被接纳或批量删除。
- [x] AC-005（A11）：同实例生命周期冲突经真实控制 HTTP 返回 409，端口耗尽仍为 503，意外故障为 500；响应不依赖异常文案匹配且不泄露内部数据。
- [x] AC-006（A13）：非空但缺字段或字段类型错误的 Agent 元数据均以脱敏错误明确拒绝启动；完整合法元数据才能建立 CDP manager。
- [x] AC-007（A14）：活 PID、损坏、不可读或无法证明过期的 X11 锁及 socket 保留；仅能解析且确认进程不存在的锁被清理。
- [x] AC-008（A15）：Gateway 与 Agent 对原始数据、JSON 转义后的 envelope 及 WS 帧使用一致有界预算；边界内消息正常通过，超限连接按 1009 受控关闭且服务继续处理其他连接。
- [x] AC-009（A16）：批量关闭或发送中第一个 Viewer 失败不妨碍其余目标完成清理；Agent 不在线或发送失败明确返回 503；心跳使 registry 的 runtime_state 与上报一致。
- [x] AC-010（A34）：IPv4/IPv6 任一网络策略应用失败时，受管环境保持 DROP 且不放行，现有 teardown 完成清理；诊断准确指出失败 family、工具和退出码，并仅保存有界脱敏 stderr。
- [x] AC-011（A39）：真实 Gateway 与多个 Agent 在小限额、429、取消、超时及网关重启后最终全部合法恢复；成功握手不消耗失败额度或清除其他失败，未认证声称身份不能扩大无限状态；握手预留与重试资源在各结束路径释放。
- [x] AC-012（A44）：并发订阅的私有 SSE 快照不挤占共享实时历史，snapshot/live 交接无缺口、无倒退，窗口不足明确重建；引擎和 GeoIP 缓存只复用已验证不可变代次，未知或被改变的代次仍完整校验，新增代次不修改运行中旧挂载。
- [x] AC-013（A45）：过期 stop 返回明确 superseded_noop 并保护新实例，重放保持同一命令结果；仅实际停止或确认不存在时声明 stopped/absent，API 不把请求成功误作已观测停止。
- [x] AC-014（A47）：固定 SDK/Playwright 支持的 ABI 下，owner-loss、正常退出与 keymap 初始化顺序均有真实调用证据；不支持的结构或签名明确报告 unsupported ABI，不静默误判 driver dead，不把未知键池容量当无限。
- [x] AC-015（A48）：公开配额入口拒绝低于最小值、非有限与越界 FPS，None 仅解除限制；Stream stop 完整取消并等待后台任务、释放 Viewer 与 detached upstream，重复 stop 安全；协议与策略对身份、verb、时间和配额判断一致，实际 CPU 配额行为不受死代码删除影响。
- [x] AC-016（A55）：默认搜索初始化异常或超时后浏览器仍可用且原标签页继续运行，Profile 页面显示独立失败状态并允许受权限保护的重试；重试不重启浏览器，过期实例/越权请求被拒，只有验证成功才记录成功；关闭开关不执行，正常启动不覆盖用户后续手动选择。

### 可测试性声明

<!-- 规范（门禁必留，不得删除） -->

逐条说明不可自动测试的 AC 及替代验证；全部可测则写“全部 AC 可自动测试”。

<!-- /规范 -->

全部 AC 可自动测试；真实 Docker/Chrome、数据库与 HTTP 调用使用隔离数据根及受控故障注入，缺前提明确未验证，不将静态检查或 skip 作为真实运行证据。

## 上下文区

- 来源：用户 2026-11-03 明确要求为全部采纳项合并立项；[review_20261103_185924 决策](../../reviews/review_20261103_185924/adoption_decision.md)；本组 A3、A8、A9、A10、A11、A13、A14、A15、A16、A34、A39、A44、A45、A47、A48、A55。原 D1=B、原 D2=A 已按用户选择写回；本轮仅创建 backlog，不授权实施或提交。

### 采纳项承接与设计边界

|采纳项|主验收|来源 finding|
|---|---|---|
|A3|AC-001|f_backend_runtime_adapters_03|
|A8|AC-002|f_backend_supervisor_01, f_backend_supervisor_02, f_global_architecture_04, f_global_system_properties_03|
|A9|AC-003|f_backend_supervisor_04|
|A10|AC-004|f_backend_supervisor_06|
|A11|AC-005|f_backend_supervisor_07|
|A13|AC-006|f_backend_runtime_adapters_05|
|A14|AC-007|f_backend_runtime_adapters_12|
|A15|AC-008|f_backend_stream_gateway_02|
|A16|AC-009|f_backend_stream_gateway_03, f_backend_stream_gateway_07|
|A34|AC-010|f_backend_supervisor_09|
|A39|AC-011|f_backend_stream_gateway_01, f_followup_q_system_properties_03_01|
|A44|AC-012|f_backend_api_auth_05, f_backend_supervisor_05, f_global_system_properties_07, f_tests_unit_stream_api_08|
|A45|AC-013|f_backend_supervisor_03, f_global_architecture_05|
|A47|AC-014|f_backend_runtime_adapters_06, f_tests_integration_fixtures_13, f_backend_stream_gateway_05|
|A48|AC-015|f_backend_stream_gateway_04, f_backend_stream_gateway_06, f_backend_stream_gateway_08, f_backend_stream_gateway_09, f_backend_stream_gateway_10, f_backend_supervisor_11|
|A55|AC-016|f_backend_runtime_adapters_02|

以下为已采纳修复边界；具体结构选择以满足当前需求的最简单长期实现为准，不以开发时间或改动规模降级。

- **A3 · CDP 重连后仅在 rearm ACK 成功时报告健康**：在 cdp_proxy.py 记录重连 rearm 命令 ID，发送时保持不健康，唯一 reader 收到匹配 result 后才置 True；error、断线和超时保持 False。禁止在唯一 reader 内同步等待自己消费 ACK；补成功/error/无 ACK 测试。
- **A8 · 统一事件投递结果并终结永久拒绝事件**：EventForwarder 暴露明确三态结果并保留既有调用契约的单一路径；401/403/408/429 与 5xx 留待重试，确定语义拒绝入死信。consume_disk_events 对永久拒绝隔离原文件、推进并持久化游标；暂不可用保持待投递。测试单次死信、重启重放、暂失败后成功；不允许诊断事件推进业务状态。API 503 分类由 A6 处理。
- **A9 · 收紧 X11 权限辅助容器权限**：docker_adapter.py 的 helper 设置 cap_drop ALL、仅实测 chmod 必需 capabilities、read_only 与 no-new-privileges，加受管理标签；验证权限修正成功、失败明确报错与 helper 清理，不照抄多余 CHOWN 权限。
- **A10 · 异常 Docker 标签只隔离当前资源**：扫描边界校验缺失/非数值 config-version，记录脱敏诊断并逐资源拒绝使用；恢复循环继续处理其他 Profile。补缺失、畸形、有效标签混合扫描测试，确保未知身份不被采用或批量删除。
- **A11 · 生命周期冲突返回明确 HTTP 409**：core.py 使用明确生命周期冲突异常，control_server.py 映射 409；保留端口耗尽 503、意外故障 500；补 HTTP 状态与无内部数据泄漏断言，避免匹配 RuntimeError 文案。
- **A13 · Agent 元数据缺字段时明确拒启动**：agent.py 在轮询结束后校验必需字段与类型，再构造 CDP manager；缺字段统一抛脱敏元数据错误。补非空缺字段、非法类型、完整记录路径。
- **A14 · 无法证明过期的 X11 锁不得删除**：runner.py 仅在可解析 PID 且已确认不存在时清理；存在但不可读/不可解析则拒绝并给出明确错误；补有效活进程、死 PID、损坏锁、读失败测试，验证 socket 保留。
- **A15 · 统一隧道数据与 envelope 上限，受控处理超限**：protocol.py 明确原始 envelope、data、WS 三层预算；Gateway 构造前检查并捕获校验错误，以 1009 关闭超限连接；Agent 使用同一预算。覆盖 JSON 转义膨胀与边界值，不把数据上限简单提高到无界。
- **A16 · Gateway 控制操作逐目标完成清理**：server.py 对各 viewer close/send 独立处理并继续后续目标；Agent 不在线/发送失败返回明确 503；心跳同步 runtime_state。补第一个 viewer 失败其余仍关闭、Agent 发送失败和心跳更新测试。
- **A34 · 网络策略失败保留受限诊断与关闭默认值**：network_policy.py 错误记录失败 family/tool/exit_code 与受限脱敏 stderr；明确第二 family 失败时保持 DROP 并由现有 teardown 清理，不 flush 放行。补 IPv6 失败时 gate 未放行与错误来源准确测试。
- **A39 · 注册防滥用与合法恢复分别建模**：registry.py/server.py 将来源限流拆为有界在途握手及失败尝试记录；成功只释放本次预留，不清除其他失败历史；所有结束/超时/取消路径释放资源。身份验证成功后以 API 确认的 Profile/instance 做有界注册替换与恢复控制，不能按攻击者提供的字符串扩展桶。agent 保留有界退避并加入可测试 jitter，避免同步重试波；真实 Gateway+多个真实 Agent 小桶测试覆盖 429、窗口过期、取消和最终全部恢复，另测网关重启。新容量值依据测量，无任意提高阈值。
- **A44 · SSE 快照不占用实时历史，缓存验证绑定受控代次**：runtime_coordinator.py 用一次一致数据库读生成私有 snapshot 事件，携带明确 live 基点，不把 N 条私有快照写入全局历史；订阅注册、基点与缓冲回放定义同一顺序，实时发布只持短锁。先用并发测试证明 snapshot/live 无缺口、无倒退、双订阅不互相挤压，再改变前端 snapshot 消费与生成契约；历史窗口不足时显式重建，不静默丢事件。引擎/GeoIP 缓存由 Supervisor 初始化、校验后作为不可变代次只读挂载，更新创建新代次并原子切换；每次启动验证受信代次和根身份，未知/改变仍完整校验，禁止仅用根 mtime 跳过后代检查。版本/产物读开销由 A4，游标淘汰由 A12 处理。
- **A45 · 过期 stop 是明确的命令结果，不伪装成已观测停止**：StopProfileResponse/OperationJournal 明确 stopped、already_absent、superseded_noop 等命令结果：只有实际停止或确认目标不存在才声明 stopped/absent，session 已替代时返回 superseded_noop，旧请求重放返回该命令结果且绝不触碰新实例。API coordinator/recovery 显式消费结果并继续按权威观测收敛，不把 HTTP 200 等同“目标已停止”。同步导出 schema；旧测试整体替换并记录旧 contract 被新语义取代，新增新 session 保留、幂等重放与不虚报观测用例。残留容器定向回收只有精确 Profile+instance 归属证据才可执行。
- **A47 · SDK 私有接口集中适配，升级能力有可执行证据**：将 Playwright/SDK driver 读取与 Selkies keymap/入口适配分别封装在各自职责模块，做版本与所需结构/签名检查，unsupported ABI 明确拒启动并脱敏诊断，不能静默当作 driver dead。真实固定镜像覆盖 owner-loss、正常退出、\_spare_keycodes 尚未初始化及 text_room/prebind 顺序；若 None 可达，按 SDK 原规则初始化同一备用键池后计算，不伪造容量。probes 复用受约束适配能力但使用独立外部行为 oracle；形成可重跑升级矩阵与隔离演练流程，不因本项自动升级 Selkies/CloakBrowser 版本。
- **A48 · Stream 策略不变量和关闭职责只有一个入口**：policy.py 与协议使用同一 FPS 规则，公开 set_supervisor_quota 严格拒绝低于 min、非有限和上界越界值；None 仅表示解除限制。StreamAgent 只保留可 await 的完整 stop，移除无消费者 close，取消/等待所有后台任务并释放 viewers/detached upstream。合并 verb 判定、身份字段类型/校验与 ISO 时间来源，删除冗余 Exception 元组；纯 fence/授权输入判定模块化，handler 保留 I/O。确认无外部契约消费者后删未用 calculate_cpu_percent 及仅验证旧函数的原测试，保留实际 quota 算法的独立行为覆盖与删除理由，不改旧预期伪装原测试仍有效。
- **A55 · 默认搜索初始化失败不阻断浏览器，明确提示并支持重试（原 D1=B）**：把默认搜索初始化从浏览器 readiness 的成功条件中分离；为初始化设置有界执行时间与条件等待，失败记录脱敏、可观察的独立状态，不改变浏览器可用性。状态经类型化契约呈现到 Profile 页面，提供受现有身份权限保护、绑定目标实例且可幂等调用的重试操作；重试不重启浏览器、不干扰已有标签页，只有验证 Google 成为默认后才写成功 marker。set_google_default=false 不执行；成功 marker 保持首次初始化语义，正常启动不覆盖用户后续手动选择。补超时/异常不阻断启动、界面提示、拒绝越权/过期实例重试、重试成功与失败状态、用户后续选择保留的真实调用路径回归；不新增任意搜索引擎配置功能。

### 有意不测

- repo_template 整改、正式备份恢复/切换与已拒绝项：用户明确排除，不新建相关测试。
- 公网/跨主机媒体与原生 x86 环境：不扩大现行单机包络，沿用已记录用户豁免，不宣称实测。

### 测试策略

- 用真实控制 HTTP、并发订阅和断线重放证明 ACK/命令结果/观测状态的差异；注入 ACK 错误、永久拒绝、读取失败、SDK 不兼容及多 Viewer 部分失败。
- 隔离 Docker/Chrome 验证 X11/helper 最小权限、IPv6 策略失败不放行、固定 SDK owner-loss/keymap、缓存新旧代次与注册小桶恢复；不采用真实生产数据根。
- 真实浏览器设置调用注入超时/异常，证明浏览器仍可用；经实际权限入口重试并验证提示状态、实例 fence、成功 marker 和后续手动选择保留。
- 配套前端 SSE 消费随 A44 的生产者契约同步；只以新状态契约验证，保持实时无缺口与既有运行事件 fail-closed。

### 未知契约清单

<!-- 规范（门禁必留，不得删除） -->

未核实的外部契约标为 `UNVERIFIED-BLOCKING` 或 `UNVERIFIED-SPIKE`；核实后改写为结论和验证方式。无则写“无”。

<!-- /规范 -->

- 已核实（A47 spike，2026-11-04）：对固定 Selkies 2.1.0 官方 wheel（PyPI，sha256 `8bde6207ca921cb2f38c3204fafe18d40b5578165894818ae1ca9e46fca7b966`，与 `config/docker/stream_runtime/requirements.txt` 钉版一致）源码逐行核对 `selkies/input_handler.py`：`_XTestKeyboard._spare_keycodes` 在 `__init__` 置 None、`invalidate_mapping()`（外部 keymap 变更）重置为 None，None 可达；SDK 全部消费点（`prebind`、`text_room`、`_free_spares`、`_overlay_keycode` 等）统一按「None 时先调用 `_find_spare_keycodes()` 初始化同一备用键池再计算」的原规则处理，容量恒为有限 `len(_spare_keycodes)`，不存在无限语义（原生 evdev `text_room` 返回 0 只是「不走 overlay 文本通道」的信号，非容量无限）。文本输入路径顺序为先 `text_room()` 后 `prebind(runs[0])`（input_handler.py 文本发送路径），两者各自带 None 惰性初始化。探针与源码副本留 `.scratch/a47_probe/`（本机无 Docker，真实镜像内 X 显示调用证据按用户豁免口径另立 pending 追踪）。结论：适配层在 None 时按 SDK 原规则初始化同一键池后计算；未知/未初始化容量不得当无限；结构或签名不符明确报 unsupported ABI。

### 风险与回退

- 风险：SSE 基点、重放游标及 stop 结果变更可能丢事件或影响新实例；SDK 假设、权限收紧与缓存代次可能影响启动；搜索设置的 best-effort 不能掩盖真正启动失败。
- 回退：先在隔离实例保留可检查的事件、命令结果和缓存旧代次；失败拒绝使用未知资源、不放松网络默认拒绝。只恢复经过验证的代码/受信代次，不能清空游标或批量 teardown 替代实例；搜索重试失败仅更新独立状态。

### 依赖与约束

- 依赖控制 API task 的每消息导出入口与服务身份契约，再同步本组 stop/SSE/初始化状态，避免建立第二套 schema 权威。
- 与 t019 共用 Stream 入口/SDK 回归，与 t020 共用 runner 和 Profile 状态；显式排斥并行写相同文件，不吸收或更改两者 AC。
- 固定当前 SDK 与单机直连边界；真实镜像/引擎缓存为测试前提，缺失明确未执行，不将 skip 视为通过。

### Finalization 时更新的 blueprint

- `docs/blueprint/browser_runtime.md`：非关键搜索初始化、marker、重试、CDP rearm 与安全启动。
- `docs/blueprint/supervisor.md`：命令结果与观测分离、helper/标签/策略及缓存代次。
- `docs/blueprint/gateway.md`：注册失败预算、恢复、消息预算及逐目标清理。
- `docs/blueprint/stream_runtime.md`：配额与唯一 stop、SDK 适配边界，不改 t019 的 ICE 目标。
- `docs/blueprint/frontend.md`：初始化告警/重试及 SSE snapshot/live 消费事实。
- `docs/blueprint/decisions.md`：记录 D1=B 与状态成功条件，不新增无需求兼容层。
- `docs/blueprint/testing.md`：故障矩阵、SDK ABI、实时交接和真实恢复验证。
