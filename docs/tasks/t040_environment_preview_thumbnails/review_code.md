# Task review t040（reviewer_focus: 代码）

- task：`t040_environment_preview_thumbnails`
- spec：`docs/tasks/t040_environment_preview_thumbnails/task.md`
- diff_anchor：`d9e0843545275d26f64d7b2932fa933c4e3263fb`
- target：`git -C '<repo_root>' diff d9e0843545275d26f64d7b2932fa933c4e3263fb`
- round：1
- reviewed_at：2026-11-08T02:10:00+08:00

reviewed_scope: dd68f28d604368f2

## Findings

### t040_code_f001 - PATCH 吞掉整个策略应用异常，失败时 200 成功且无补偿

- 严重度：important
- 锚点：AC-004（运行中关闭 `capture_preview` 后立即停止采集、删除已有预览）；行为缺陷（策略应用失败时状态不一致且用户/运维无感知）
- 位置：`src/backend/cbrowser/api/v1/router.py:407-419`、`src/backend/cbrowser/api/v1/router.py:66-95`
- 问题：`update_profile` 把 `_apply_preview_policy` 整段包在 `except Exception: logger.warning(...)` 里，随后仍 `return ProfileResponse.from_domain(p)`（200）。`_apply_preview_policy` 含四步：本地 `write_policy(policy.json)`、`clear_preview` + `clear_preview_capture`、`coordinator.request_preview_policy`（Supervisor HTTP，非 200 时 `raise RuntimeError`，`runtime_coordinator.py:1605-1606`）。任一步失败都被吞，无重试、无失败态、无 reconcile 补发（全仓仅 `router.py:94` 一处调用 `request_preview_policy`，已 grep 核实）。可复现：关闭 `capture_preview` 时 Supervisor 控制面返回 503/连接超时 → PATCH 200，但 UDS 即时下发未发生；若共享 `policy.json` 写入同时失败，DB `capture_preview_epoch` 已 +1 而文件仍 `enabled=True` 旧代次，`PreviewCaptureLoop.capture_once`（`preview_capture.py:2221`）只读文件 → 继续每 15s 采集并 `commit_preview`，旧帧持续落盘。读取端点因 DB epoch 与文件 epoch 不匹配恒 404，掩盖不一致；采集不停、隐私帧不停，用户无从得知。属 swallowed error + 失败状态不一致。
- 建议：最小修复——本地 `write_policy` / `clear_preview` / `clear_preview_capture` 失败应让请求失败（5xx）或回滚已递增的 DB 代次；`request_preview_policy` 失败应保留「待下发」状态并在 coordinator reconcile 补发，而非静默成功。至少把 warning 升级为带 `profile_id`/`epoch` 的结构化失败并暴露到 runtime 状态，禁止 `except Exception` 后照常返回 200。

### t040_code_f002 - 策略文件多写者无代次单调保护，且写在 instance/request_id fence 之前

- 严重度：important
- 锚点：AC-004；不变量「API 是权威，持久化 `capture_preview` 与递增的策略代次」「采集、落盘、通知、读取四环节都校验策略代次与 runtime 实例」
- 位置：`src/backend/cbrowser/supervisor/core.py:1806-1858`（`apply_preview_policy`，`write_policy` 在 `:1815`）、`src/backend/cbrowser/api/v1/router.py:81`、`src/backend/cbrowser/services/profile_service.py:533`
- 问题：`apply_preview_policy` 无条件 `write_policy(directory, policy)`（`:1815`）后才做 instance fence 与 duplicate `request_id` fence（`:1819-1835`），全程不比较 `request.epoch` 与文件当前 `policy.epoch`，也不比较 `runtime_instance_id` 是否前进。`policy.json` 有三处写者（API PATCH、`bind_runtime_instance`、Supervisor `apply_preview_policy`），共享同一宿主机目录，无单调性保护。可复现（乱序）：用户连续关闭（epoch=1 disabled）再开启（epoch=2 enabled），两个 sync POST 乱序到达 Supervisor，epoch=1 最后到 → 文件被回写为 `enabled=False/epoch=1`，且 instance 仍匹配故 UDS 下发 `set_policy(enabled=False)`，DB 已是 `enabled=True/epoch=2`。Agent 读文件停止采集，读取端点 DB epoch=2 与文件 epoch=1 不匹配恒 404，预览再不恢复，除非再次 PATCH 或重启。可复现（stale instance）：迟到旧实例 sync 的 instance fence 只跳过 UDS 下发，但 `write_policy` 已在 `return` 前把文件写成旧 instance/旧 epoch；`enabled=False` 时还先 `clear_preview` 删掉当前有效帧。新实例 Agent 按文件旧 instance 采集，`meta.runtime_instance_id` 与 DB `runtime.runtime_instance_id` 不符被 `record_preview_capture`（`repository.py:1403-1409`）拒绝，前端不刷新。`request_id` fence 只拦完全相同 ID 的重复，拦不住不同 epoch 的乱序。单测 `test_stale_instance_and_duplicate_request_fence_control_dispatch` 只断言 `control_calls`，未断言文件未被回写。
- 建议：最小修复——`apply_preview_policy` 写文件前先 `read_policy`，仅当 `request.epoch > current.epoch`（或 epoch 相等且 instance 匹配）才写并下发；把 instance / duplicate fence 前置到任何写操作之前，disabled 的 `clear_preview` 只在 fence 通过后执行。API 侧 `router.py:81` 与 `bind_runtime_instance` 的写入同样加单调保护，杜绝旧请求覆盖新代次。

### t040_code_f003 - UDS 下发的内存策略是死状态，即时下发退化为「写共享文件 + 唤醒」

- 严重度：minor
- 锚点：行为缺陷（策略即时下发通道不参与采集决策）+ 架构/死状态
- 位置：`src/backend/cbrowser/runtime_agent/preview_capture.py:2197-2218`（`set_policy` / `self._policy` / `self.instance_id`）、`src/backend/cbrowser/runtime_agent/preview_capture.py:2220-2223`（`capture_once` 只读文件）、`src/backend/cbrowser/runtime_agent/agent.py` 的 `/control preview_policy` 分支
- 问题：Supervisor 经 UDS `/control` 下发 `action=preview_policy`（enabled/epoch/runtime_instance_id/request_id），`agent.py` 仅调 `preview_loop.set_policy(...)` 把值存进 `self._policy` 并 `_wake.set()`；但 `capture_once` 从不读 `self._policy`，开头直接 `read_policy(self.directory)` 读共享 `policy.json` 决定 enabled/epoch/instance，`self.instance_id` 构造参数同样未被消费。`self._policy` 仅被 `policy` property 与单测 `test_control_preview_policy_updates_in_memory_policy` 断言，不影响任何采集行为。后果：UDS 实质只当唤醒信号，「策略变化即时下发给运行中的 Agent」完全依赖 API/Supervisor 写共享 `policy.json` 且该目录对 Browser 容器可见；当前单机拓扑（API `/data`、Supervisor `${CBROWSER_DATA_ROOT}`、Browser `/data/preview` 同指宿主 `${ROOT}/profiles/{id}/preview`）成立，但文件写入失败、拓扑不再共享、或 f002 的 instance fence 跳过 UDS 时，运行中的 Agent 最多滞后一个 15s 周期且内存策略无力纠正。
- 建议：最小修复——二选一：`capture_once` 以 `self._policy`（UDS 为准）覆盖文件读取，或 `set_policy` 同时 `_atomic_write` 一份 `policy.json` 并删除死状态；测试中改为断言下发真正改变下一轮采集行为，而非只断言 `loop.policy`。

## 结论

- 前轮 finding 复核：Round 1，无前轮。
- 本轮新发现：3 条（important 2 / minor 1）。
- 七视角正交体检（均独立扫过，未命中亦确认）：
    - 安全：`supervisor_router` 全局 `require_supervisor`（`internal_supervisor.py:53-57`）覆盖内部通知端点；`get_preview` 用 `require_user_session`；`_atomic_write` chmod 0600；`no-store` + `nosniff`；统一 404 `_NOT_FOUND` 无路径/内容；日志只记 `error_type`/计数；路径遍历被 DB 查询先行拦截。未命中。
    - 正确性：`commit_preview` 落盘前重读 policy、`record_preview_capture` epoch+instance fence、`preview_router` ETag/304/404 均复核通过；命中 f001/f002。
    - 契约·Breaking：`capture_preview_epoch` / `preview_captured_at` 加列进 baseline migration 符合项目零兼容负担铁律；OpenAPI 两文件、前端 generated 类型与源码同步；`agent_protocol.json` 补 `preview_policy`。仅有 minor 级文档缺口（见提示）。
    - 性能·资源：`_observe_preview_capture` 仅在 `captured_at` 变化时 POST；CDP 4 次往返/15s；`publish_transient` 与既有 `publish` 的 QueueFull 处理一致（`runtime_coordinator.py:74-114`）。同步文件 IO 提示见下。未命中 blocking。
    - 架构·可维护性：`preview.py` 三方共享职责清晰；命中 f003 死状态；`cdp_send_from_proxy` 重复 `CdpProxyManager.send_command` 并访问私有成员，见提示。
    - 健壮性·可观测：命中 f001（异常吞噬无补偿）；其余 catch 均有 `error_type` 日志且不泄漏内容/路径。
    - 测试·文档·规格：E2E 2 例真触达生产链路（JPEG 480 / no-store / ETag / 304 / 未登录 / 0600 / 撤销 404 / 停止保留 / 页面不变），集成测试注入三类迟到写入并验证重放环隔离；未发现恒真断言或 mock 掉被测逻辑。E2E 未比对 JPEG 内容是否含 MARKER、未声明 304 契约，见提示（测试轴/文档 minor，不进表）。
- 未进表的提示：
    - 文件过大 / 圈复杂度：本 task 新建实现文件最大 `preview.py` 161 行、`preview_capture.py` 157 行、`preview_router.py` 75 行；测试最大 `test_supervisor_preview_policy.py` 313 行；均远低于 400/600 阈值，无函数 CC≥15，零命中。
    - DRY：`preview_capture.py:2162-2187` 的 `cdp_send_from_proxy` 逐句复制 `cdp_proxy.py:97-121` 的 `send_command`（含 `_lock` / `_allocate_cmd_id` / `pending_cmd_futures` 私有成员），且已分叉（前者返回 `resp["result"]`，后者返回整个 `resp`）；当前各自正确，未来修一处易漏另一处。建议后续抽公共方法。
    - 同步 IO：`write_policy` / `commit_preview` / `clear_preview` 为同步文件 IO，直接在 async 路径（`bind_runtime_instance`、`capture_once`、`_apply_preview_policy`）调用；帧体量小（~10KB），当前影响可忽略，未进表。
    - 契约生成物：OpenAPI 的 preview 200 仅声明 `image/jpeg`，未声明 304 与 `Cache-Control` / `ETag` 响应头（`schemas/openapi/cbrowser_v1.json:1216-1303`，`cbrowser_internal.json` 同），与 `preview_router.py:1687-1699` 实现不一致；不影响功能，建议补齐。
    - 活动标签（系统性 follow-up）：`capture_once`（`preview_capture.py:2225-2238`）取 `Target.getTargets` 首个 page 作为「当前活动标签页」，而 d035 已实测 target 顺序不稳定、活动标签须产品自维护；全仓无 `activateTarget` / `bringToFront` / `client_tab_id` 映射用于采集。单标签（E2E 场景）与已批准的 CDP 约束下 AC-001 成立，多标签精确识别属产品级后续能力，建议独立 follow-up，本 task 不因此判空壳。
    - `src/frontend/node_modules` 为未跟踪目录（前端测试运行产物，非 `git add -N` 交付物），不影响交付完整性判定；交付新文件均已出现在 diff（name-status 全为 A）。
- 总体判断：7 条 AC 实现层真实落地、测试与 E2E 真栈支撑打勾；但策略下发链路存在 2 个未解决 important（异常吞噬无补偿、代次/instance 无单调保护），判 FAIL。
- 系统性 follow-up：① 多标签「当前活动标签页」产品自维护活动 target（依据 d035，建议标题「活动标签页精确识别与预览采集」，slug `active_tab_preview_capture`，非阻断）；② 策略下发的幂等单调性与 reconcile 自愈（合并进 f001/f002 修复，非独立 task）。

### AC 复验方式

- AC-001：TICK-VALID，re_verified。`preview_capture.py:2220-2269` 15s 循环 + `capture_screenshot_params` 480px/q70 + CDP viewport 截图，E2E 真栈断言 JPEG 宽 480 且 2 passed；多标签活动标签限制见结论段 follow-up。
- AC-002：TICK-VALID，re_verified。`preview_router.py:1657-1699` require_user_session / `image/jpeg` / `no-store` / ETag(captured_at) / 304 / 统一 404，单测与 E2E 断言 401/403、304、撤销 404。
- AC-003：TICK-VALID，re_verified。`runtime_views.py:95` + `domain/models.py:709` 注入 `preview_captured_at`；`runtime_coordinator.py:95-114` `publish_transient` 只 fan-out 不 append `_history`；`sse.ts:324-359` 按 event 分发且无 id 帧不改 `lastEventId`；集成测试验证 50 帧不进重放环。
- AC-004：TICK-VALID，re_verified。`commit_preview` 重读 policy 丢弃、`record_preview_capture` epoch+instance fence、reset 清预览且 E2E 撤销 404 均复核；异常/乱序路径缺陷见 f001/f002，不属实现空壳。
- AC-005：TICK-VALID，re_verified。stop 不调 `_clear_preview_state`（E2E `kept==200`），delete/reset 调（`profile_service.py:476,795`），`volume_spec.py:38` 独立挂 `/data/preview`，集成测试验证状态复制不复制预览。
- AC-006：TICK-VALID，re_verified。`preview.py:1903-1911` `_atomic_write` chmod 0600，单测/E2E 断言 0600，`test_error_body_never_leaks_path_or_image_content` 与全链路日志核实无内容/路径。
- AC-007：TICK-VALID，re_verified。`preview_capture.py` 不调 activate/bringToFront（单测断言），`clip.scale` 不改布局，E2E sleep 17s 跨采集周期断言 visibility/hidden/focus/marker/title 不变。

coverage = re_verified / 7

verdict: FAIL

## Round 2 (2026-11-08T03:00:00+08:00)

- round：2
- reviewed_at：2026-11-08T03:00:00+08:00
- 落点校验：不带 `-C` 的 `git rev-parse --show-toplevel` = `<repo_root>`，通过；`git -C ... diff d9e0843545275d26f64d7b2932fa933c4e3263fb` 共 5549 行，name-status 全为 A/M，交付新文件均已 `git add -N` 出现在 diff；`src/frontend/node_modules` 为运行产物、非交付物。
- 独立复验：`uv run --group gate pytest` 跑 6 个 preview 相关 unit/integration 文件，41 passed；另以直跑生产代码的时序探针复现 f004（详见 finding）。

reviewed_scope: 6b3cc2bf67d285f0

## Findings

### t040_code_f004 - 修复 f003 新增的 Agent 写者无条件写 policy.json，乱序 UDS 把策略回退到旧代次，撤销后采集恢复、预览文件重现

- 严重度：important
- 锚点：AC-004（关闭 `capture_preview` 后立即停止采集、已有预览被删除；迟到写入均被丢弃、不会重新出现预览）+ 不变量「采集、落盘、通知、读取四环节都校验策略代次与 runtime 实例；任一不一致时丢弃，并删除残留文件」
- 位置：`src/backend/cbrowser/runtime_agent/preview_capture.py:74-87`（`set_policy` 第 86 行无条件 `write_policy`）、`src/backend/cbrowser/supervisor/core.py:1842-1853`（每次放行都发一条独立 UDS `/control`）、`src/backend/cbrowser/runtime_agent/agent.py:507-516`、`src/backend/cbrowser/api/v1/router.py:85`、`src/backend/cbrowser/services/profile_service.py:533`
- 问题：Round 2 修 f003 时把 `write_policy` 加进 `set_policy`，Agent 成为共享 `policy.json` 的第四个写者；`core.py:1810-1831` 的 stale epoch / duplicate / stale instance 三重 fence 只保护 Supervisor 自己的写，Agent 侧 `set_policy` 无 epoch 单调校验、无锁，最后写入者无条件胜出。可复现：两次策略变化（如开启 epoch=2 后关闭 epoch=3，或 PATCH 与 reconcile 补发并发）经 Supervisor 顺序放行后，两条 UDS 请求乱序到达 Agent；`set_policy(disabled,3)` 先写、`set_policy(enabled,2)` 后写 → 文件回到 `enabled=True/epoch=2`。`capture_once`（`preview_capture.py:89-92`）读文件恢复采集，`commit_preview`（`preview.py:101-118`）重读同代次文件即落盘。本轮探针直跑生产代码实测输出：`policy file after out-of-order UDS: enabled=True epoch=2 ...`、`latest.jpg reappeared: True`、`meta reappeared: ... policy_epoch=2`、`read endpoint is_current_preview(DB epoch=3): False`。即撤销后采集不停、`latest.jpg`/`meta.json` 重新出现，DB epoch=3 使 `is_current_preview`（`preview.py:121-140`）恒 404 掩盖显示，隐私帧持续生成（health 通知经 `record_preview_capture`（`repository.py:649-672`）拒收后由 `internal_supervisor.py:175-179` 才删，形成反复出现/删除）。`test_runtime_agent_preview.py:196-241` 只验证单次 `/control`，无乱序下发时序用例。
- 建议：最小修复——`set_policy` 写文件前 `read_policy` 比较代次，仅 `epoch >= current.epoch`（且 instance 匹配）才写，或 Agent 完全不写文件、以 UDS 内存策略为唯一权威并把落盘收归单写者；补一条乱序 UDS 时序单测断言文件代次不回退、撤销后 `latest.jpg` 不重现。

## 结论

- 前轮 finding 复核（以当前 diff/代码为准，不采信 progress.md 处置表）：
    - `t040_code_f001`（important）：**已消除**。`router.py:66-101` `_apply_preview_policy` 已无 `except Exception`，`write_policy`(85)/`clear_preview`(94)/`clear_preview_capture`(95) 直调，`update_profile`(416) 无包裹 → 本地失败冒泡 500（`app.py:384-394` 固定文案）；`test_preview_router.py:150-157` 断言 `get_preview_dir→None` 时 PATCH 500。`runtime_coordinator.py:802-822` `request_preview_policy` 失败/`is_enabled()==False` 存 `_pending_preview_policy`(810/815)、成功才 pop(822)；补发链路真被调用：`router.py:99-100` → `trigger_reconcile`(851-862) → `_reconcile_profile_loop`(1079) → `reconcile_profile_now`(886) → `flush_pending_preview_policy`(830)；`flush` 仅成功后 pop(838)、失败 return 保留(837)，两处 except 均 `logger.warning` 带 `error_type`（816-820/832-836），无静默吞掉。残留边界：`is_enabled()==False` 时存 pending 无日志且 `trigger_reconcile`(852-855) 不建 loop，pending 滞留；此时策略由 API 写共享文件兜底、Agent 读文件生效，不构成 200 静默成功。
    - `t040_code_f002`（important）：**修不彻底**。`core.py:1806-1840` 三项已正确落地：stale epoch(1810-1815，严格 `<`，同 epoch 放行)、duplicate request_id(1816-1821)、stale instance(1822-1831) 全部前置到 `write_policy`(1837) 与 disabled `clear_preview`(1838-1839) 之前，无 fence 前回写路径；`test_supervisor_preview_policy.py:317-362` 已补「文件未被回写」断言（Round 1 缺口）。但「策略文件多写者无代次单调保护」根因未收敛：`router.py:85`、`profile_service.py:533` 仍无条件写，尤其 f003 修复新引入的 `preview_capture.py:86` 写者无 epoch fence，构成「仍有路径回退共享 policy.json」，已复现（见 f004）。
    - `t040_code_f003`（minor）：**已消除**。`preview_capture.py:74-87` `set_policy` 同时 `write_policy` 落文件(86)，`capture_once`(89-92) `read_policy` 消费共享文件策略，UDS 下发已能改变下一轮采集；`test_runtime_agent_preview.py:196-241` 断言 `/control` 后文件与内存策略同步。残留 `self._policy` property / `instance_id` 构造参数仍未被 `capture_once` 直接消费（死状态），属 minor 风格残留，不再构成「UDS 内存策略不参与采集决策」的行为缺陷。
- 本轮新发现：1 条（important 1 / minor 0 / critical 0）。
- 未进表的提示（用户点名 7 项逐项核查）：
    - pending 字典并发/内存：`_pending_preview_policy`(`runtime_coordinator.py:256`)、`_preview_request_ids`(`core.py:212`)、`_preview_captured_at`(`core.py:2696`) 均以 profile_id 为键、单机 profile 数有限，无无界增长；并发 PATCH 下可能短暂存旧代次 pending，但 Supervisor stale epoch fence 兜底，不造成策略回退，不 blocking。
    - reconcile 补发循环：`flush` 成功才 pop、失败保留并带 warning，`_reconcile_profile_loop`(1072-1129) 每轮重试有退避与上限，无死循环/重复下发；`trigger_reconcile`(858-859) cancel 同 profile 既有 task 会打断进行中的 start/stop reconcile，但重建 loop 重新驱动，不丢失，提示。
    - `_post_preview_policy` 抽离后 URL/token：`runtime_coordinator.py:774-800` URL 与 `control_server.py:299` 一致、Bearer `_token_str`、`trust_env=False`/timeout 10s/`transport=self.transport` 与 `close_supervisor_tunnels`(419-427) 一致；`request_id` 每次新 uuid(796)，flush 重发不被 duplicate fence 误拦；日志只打 `error_type`，无 token/URL 泄漏，无劣化。
    - 500 响应泄漏路径：`router.py:81-84` 固定 `"Preview storage unavailable"`；`write_policy`/`clear_preview` 抛 OSError 冒泡到 `app.py:384-394` 固定 `"An internal server error occurred"`，日志只记 `type(exc).__name__`(386)；`preview_router.py` 404 统一 `_NOT_FOUND`。无路径/内容泄漏，AC-006 仍成立。
    - epoch 单调校验误杀合法同 epoch 重发：`core.py:1811` 严格 `<` 放行同 epoch；`repository.py:435-438` 仅 `capture_preview` 值变化才递增 epoch，幂等 PATCH 不触发 POST；合法重发用新 request_id(796) 不撞 duplicate fence。无误杀。
    - fence 前置与「停止态撤销」失效：停止态 `apply_preview_policy` 因 `session is None`(1822-1831) 跳过 Supervisor 写/UDS，但 API 侧 `router.py:85-95` 仍 `write_policy(disabled)` + `clear_preview` + `clear_preview_capture` → `read_meta` 为 None → `is_current_preview`(`preview.py:128-130`) False → `preview_router.py:60` 404。撤销不失效。
    - `set_policy` 写文件与 Supervisor 写文件竞态：已作为 f004 进表，见上。
- 总体判断：7 条 AC 实现层仍真实落地、测试/E2E 真栈支撑打勾；前轮 f001/f003 已消除、f002 修不彻底，且 f003 修复引入的 Agent 共享文件写者带来未解决的 important 竞态（f004），判 FAIL。
- 系统性 follow-up：① f004 的 Agent 写者代次 fence / 单写者收敛与乱序时序单测，合并进本轮修复，非独立 task；② Round 1 已登记的多标签「活动标签页精确识别」（slug `active_tab_preview_capture`，依据 d035，非阻断）沿用，本 task 不因此判空壳。

### AC 复验方式

- AC-001：TICK-VALID，re_verified。`preview_capture.py:140-158` 15s 循环 + `preview.py:143-161` jpeg/q70/`clip.scale`→480px + CDP viewport-only 截图，E2E `test_profile_preview_e2e.py:93-101,161,204` 以 Pillow 中心平均色 ±20/通道比对双纯色页活动标签、`width==480`，用户监督纠正已落地。
- AC-002：TICK-VALID，re_verified。`preview_router.py:33-75` require_user_session / `image/jpeg` / `no-store` / ETag(captured_at) / 304 / 统一 404；`test_preview_router.py:84-147` 与 E2E `157-167,210-211,270-271` 断言 401/403、304、撤销 404、body 不含路径与内容。
- AC-003：TICK-VALID，re_verified。`runtime_views.py:95` + `domain/models.py:709` 注入 `preview_captured_at`；`runtime_coordinator.py:843-849,1698-1717` `publish_transient` 只 fan-out 不 append `_history`；`sse.ts:324-359,414-419` 按 event 分发且无 id 帧不改 `lastEventId`；`EnvironmentCard.tsx:35-37` 以 captured_at 作 `?v=`；`test_preview_late_writes.py:243-292` 50 帧不进重放环、重连仅回放 runtime_state。
- AC-004：TICK-VALID，re_verified。`preview.py:101-118` 落盘前重读 policy、`repository.py:649-672` epoch+instance fence、`internal_supervisor.py:175-179` 拒收即 `clear_preview`、`test_preview_late_writes.py:123-185` 注入三类迟到写入、E2E `265-271` 撤销即时 404；乱序 UDS 竞态见 f004，属边界缺陷非实现空壳。
- AC-005：TICK-VALID，re_verified。stop 不清预览（E2E `280-283` kept==200），delete/reset 清（`profile_service.py:278-290`，`test_preview_clear_on_lifecycle.py:35-63`），`volume_spec.py:38` 独立挂 `/data/preview`，`test_preview_late_writes.py:189-209` 含浏览器状态复制不复制预览。
- AC-006：TICK-VALID，re_verified。`preview.py:41-49` `_atomic_write` chmod 0600，E2E `213-219` 断言 latest.jpg/meta.json 0600，`test_preview_router.py:134-147` 断言 404 body 不含路径/内容；本轮复核 `app.py:384-394` 500 固定文案与 `router.py:81-84` 不泄漏路径。
- AC-007：TICK-VALID，re_verified。`preview_capture.py:94-130` 不调 activate/bringToFront（`test_runtime_agent_preview.py:109-111` 断言），`clip.scale` 不改布局，E2E `255-263` sleep 17s 跨采集周期断言 visibility/hidden/focus/marker/title 不变。

coverage = re_verified / 7

verdict: FAIL

## Round 3 (2026-11-08T04:00:00+08:00)

- round：3
- reviewed_at：2026-11-08T04:00:00+08:00
- 落点校验：不带 `-C` 的 `git rev-parse --show-toplevel` = `<repo_root>`，通过；`git -C '<repo_root>' diff d9e0843545275d26f64d7b2932fa933c4e3263fb` 共 62 文件 / 4553 增 / 90 删，`git status --short` name-status 全为 A/M，交付新文件均经 `git add -N` 出现在 diff；`src/frontend/node_modules` 为前端测试运行产物、非交付物。
- 门禁证据（供复核，不替代代码核实）：`.scratch/t040_evidence_20261108_032501` contract 257 passed/1 skipped、unit 1203 passed、repo_hygiene 8 passed；E2E 并行 50 passed/2 skipped、串行 52 passed；定向 `test_profile_preview_e2e.py` 2 passed（Pillow 像素语义 + 双纯色页活动标签）。

reviewed_scope: f002728c2b1ebfc0

### 前轮 finding 复核（逐条以当前 diff/代码为准，不采信 progress.md 处置表）

- `t040_code_f001`（important，本地 500 + pending/reconcile 补发）：**已消除**。`router.py:66-101` `_apply_preview_policy` 无 `except Exception` 包裹，`get_preview_dir` 为 None 时 500（`:80-84`），`write_policy`(85)/`clear_preview`(94)/`clear_preview_capture`(95) 直调，`update_profile`(413-416) 仅在 DB epoch 真变时调用；本地 OSError 冒泡到 `app.py:384-394` 固定 500 文案。`runtime_coordinator.py:802-838` `request_preview_policy` 失败/`is_enabled()==False` 存 `_pending_preview_policy`、仅成功 pop，`flush_pending_preview_policy` 失败保留并 `logger.warning` 带 `error_type`；`router.py:99-100` → `trigger_reconcile`(851-862) → `_reconcile_profile_loop`(1072-1131) → `reconcile_profile_now`(864) → `flush` 链路真接通；`test_preview_router.py` 断言 `get_preview_dir→None` 时 PATCH 500。非 200 静默成功。
- `t040_code_f002`（important，core 三重 fence 前置）：**已消除**。`core.py:1810-1815` stale epoch（严格 `<`，同 epoch 放行）、`:1816-1821` duplicate request_id、`:1822-1831` stale instance 三项全部前置到 `write_policy`(1837) 与 disabled `clear_preview`(1838-1839) 之前，无 fence 前回写路径；`test_supervisor_preview_policy.py:317-362` 已补「文件未被回写」断言（Round 1 缺口）。Round 2 判「修不彻底」的剩余根因（Agent 第四写者无 epoch fence）随 f004 修复收敛：`preview_capture.py` 不再 import/调用 `write_policy`（详见 f004）。剩余写者 `router.py:85`、`core.py:1837`、`profile_service.py:533`（bind，写 DB 权威 `policy_row` epoch）均非旧代次回退源，且 `core.py:1811` stale epoch fence 兜底。
- `t040_code_f003`（minor，UDS 内存策略死状态）：**已消除且更彻底**。`set_policy`(`preview_capture.py:73-87`) 设 `self._policy` 并 `_wake.set()`；`capture_once`(`:90`) 以 `self._policy or read_policy(...)` 消费内存策略驱动采集，`policy` property 不再是不参与决策的死状态。`instance_id` 构造参数(`:59,63`) 仍未被直接消费，属 minor 残留，不构成行为缺陷。
- `t040_code_f004`（important，乱序 UDS 回退代次）：**已消除**（重点，逐项给 `file:line` 证据）：
    - `set_policy` 不再写 `policy.json`：`preview_capture.py:12-19` 仅 import `read_policy`，`:73-87` 全程无 `write_policy` 调用；Agent 不再是写者，文件仅由 API/Supervisor 写。`test_runtime_agent_preview.py:232-242` `test_set_policy_is_epoch_monotonic_and_never_writes` 断言 `read_policy(directory) is None`。
    - 加 epoch 单调校验、stale 直接 return：`preview_capture.py:80-81` `if self._policy is not None and epoch < self._policy.epoch: return`。
    - `capture_once` 用 `self._policy or read_policy(...)`：`preview_capture.py:90`。
    - `commit_preview` 仍以共享 `policy.json` 为最终 fence：`preview.py:112` `current = read_policy(directory)` 重读共享文件；`_policy_matches`(`:88-98`) 校验 `current.enabled`、`current.epoch == expected.epoch`、`current.runtime_instance_id == expected.runtime_instance_id` 及 meta 双字段；不匹配(`:113-115`) 即 `clear_preview` + `return False`，不落盘。
    - 乱序 UDS 只能染内存无法回退共享文件、无法复活 `latest.jpg`/`meta.json`：Agent 不写文件，内存 `self._policy` 与共享文件分叉时 `commit_preview` 必因 epoch/instance/enabled 不等拒绝并删残留；`test_runtime_agent_preview.py:246-261` `test_stale_uds_cannot_reenable_capture_after_revocation` 直跑生产代码实测「内存 enabled/epoch=10 + 文件 disabled/epoch=10，stale epoch=9 早退」→ `capture_once` 后 `latest.jpg`/`meta.json` 均不存在。无路径回退，不标 FAIL。
    - 复核结论：4 条前轮 finding（f001/f002/f003/f004）**全部真正消除**。

### 本轮新发现（f004 修复引入的新问题扫描）

本轮新 finding：**0 条**（clean，不凑数）。按 4 个指定核查点逐一以代码核实：

- 内存策略与文件策略不一致时 `commit_preview` 是否安全：**安全**。`_policy_matches`(`preview.py:88-98`) 要求 6 项全等（含 `current.epoch == expected.epoch`），任一不一致即 `clear_preview` + 拒绝落盘(`:113-115`)，不写错帧、不复活撤销预览；`test_runtime_agent_preview.py:246-261` 实测。预期副作用见结论段提示。

- `self._policy` 与 `read_policy` 的竞态：**无数据竞争**。`set_policy` 是无 await 的同步方法(`preview_capture.py:73-87`)，由 `agent.py:512` 在 `/control` handler 内同步调用；`capture_once` 在独立 task(`agent.py:111`) 内 `:90` 行无 await 处读取，单 event loop 不撕裂。逻辑侧 `core.py:1811` 保证放行 sync 的 epoch ≥ 文件 epoch，成功 UDS 与文件同 epoch。

- `set_policy` 早退是否丢 wake：**不丢有效 wake**。早退仅针对 stale epoch(`preview_capture.py:80-81`)，本不应改变状态；`self._policy is None`（首包）及同/更高 epoch 均设置并 `_wake.set()`(`:82-87`)。

- Agent 重启后 `self._policy=None` 回退读文件是否仍正确：**正确**。`__init__`(`:64`) 置 None → `capture_once`(`:90`) `read_policy` 读 API/Supervisor 写的权威文件 → meta 按文件策略构造(`:132-136`) → `commit_preview` 重读同文件 epoch 相等 → 落盘；`record_preview_capture`(`repository.py:649-672`) DB epoch+instance 兜底旧实例。

- 未进表的提示（系统性边界，非 blocking，不进 finding 表）：`self._policy or read_policy`(`preview_capture.py:90`) 使内存策略一经 UDS 设置即永久遮蔽文件读取；`core.py:1858` 把 UDS 下发异常以 debug 日志吞掉后 `sync_preview_policy`(`control_server.py:303-307`) 仍返回 200、`request_preview_policy`(`runtime_coordinator.py:812-822`) 因此不存 pending 不补发。在「UDS 内部下发失败且 Agent 曾成功收过 UDS」的边缘路径下，文件已更新到新代次但内存停在旧策略：开启策略后 `capture_once`(`:91`) 因内存 disabled 直接 return、采集停摆，预览停更（Round 2 只读文件时靠文件兜底可自愈）。不产生错误帧、不复活撤销预览（f004 文件 fence 守住），属异常路径功能降级、非隐私/数据缺陷，不 blocking；建议后续把 UDS 下发失败纳入 reconcile 补发或让 `set_policy` 与文件做最终对齐，作为系统性 follow-up，不另立 finding。

- 总体判断：前轮 4 条 blocker 全部以 diff/代码核实消除，f004 修复的 4 个核查点均安全/正确，本轮 0 条新 blocker，7 条 AC 实现层持续真实落地，判 PASS。

### AC 复验方式

- AC-001：TICK-VALID，re_verified。`preview_capture.py:140-159` 15s 循环 + `:126-131` CDP viewport 截图 + `preview.py:143-161` jpeg/q70/`clip.scale`→480px，定向 E2E 2 passed 以 Pillow 双纯色页活动标签与 `width==480` 比对。
- AC-002：TICK-VALID，re_verified。`preview_router.py:33-75` `require_user_session` / `image/jpeg` / `no-store` / ETag(captured_at) / 304 / 统一 404 `_NOT_FOUND`，`test_preview_router.py` 与 E2E 断言 401/403、304、撤销 404、body 不含路径内容。
- AC-003：TICK-VALID，re_verified。`runtime_views.py:95` + `domain/models.py:709` 注入 `preview_captured_at`；`runtime_coordinator.py:843-849` `publish_transient` 只 fan-out 不 append `_history`；`sse.ts:339-343` 按 event 分发、`EnvironmentCard.tsx:37` 以 captured_at 作 `?v=`；`test_preview_late_writes.py:243-292` 50 帧不进重放环。
- AC-004：TICK-VALID，re_verified。`router.py:66-101` 即时写文件+UDS、`core.py:1810-1831` 三重 fence、`preview_capture.py:80-87` epoch 单调不写文件、`preview.py:101-118` 文件 fence+清残留、`repository.py:649-672` epoch+instance fence、`internal_supervisor.py:175-179` 拒收即清；`test_runtime_agent_preview.py:246-261` 乱序 UDS 不复活预览 + `test_preview_late_writes.py:123-185` 三类迟到写入 + E2E 撤销 404。
- AC-005：TICK-VALID，re_verified。stop 不调 `_clear_preview_state`（E2E kept==200），delete/reset 调（`profile_service.py:476,795` + `:278-290`），`volume_spec.py:38` 独立挂载 preview 目录（常量 `PREVIEW_CONTAINER_DIR`），`test_preview_late_writes.py:189-209` 含浏览器状态复制不复制预览。
- AC-006：TICK-VALID，re_verified。`preview.py:41-49` `_atomic_write` chmod 0600，E2E 断言 latest.jpg/meta.json 0600；`app.py:384-394` 500 固定文案、`router.py:81-84` 固定文案、`preview_router.py:18` 统一 404，均不泄漏内容/路径。
- AC-007：TICK-VALID，re_verified。`preview_capture.py:94-130` 不调 activate/bringToFront（`test_runtime_agent_preview.py:109-111` 断言），`preview.py:146-161` `clip.scale` 不改布局，E2E sleep 17s 跨采集周期断言 visibility/hidden/focus/marker/title 不变。

coverage = re_verified / 7

verdict: PASS

## Round 4 (2026-11-08T04:45:00+08:00)

- 落点仓库校验：`<repo_root>` 校验通过。
- 审查范围：`git -C '<repo_root>' diff d9e0843545275d26f64d7b2932fa933c4e3263fb`。
- 本轮背景：源码及测试代码相对 Round 3 **零改动**。指纹变更为 `3cfef0709d1ad59b` 仅因删除临时未跟踪的前端运行软链 `src/frontend/node_modules`、补充 `progress.md` 模板固定说明行及规范化 spike 报告结论措辞。

reviewed_scope: 3cfef0709d1ad59b

### 前轮 finding 复核

- `t040_code_f001`（important）：已消除。`router.py` 本地 500 处理与 `runtime_coordinator.py` 挂起策略对齐保持不变。
- `t040_code_f002`（important）：已消除。`core.py` 纪元与实例三项防御前置保持不变。
- `t040_code_f003`（minor）：已消除。内存策略消费与单调性保持不变。
- `t040_code_f004`（important）：已消除。Agent 仅消费内存/文件策略且不再写策略文件，彻底阻断旧代次回写路径。

### 本轮新发现

0 条（clean）。代码与测试源码相对 Round 3 无任何变动，无新增缺陷。

### AC 复验方式

- AC-001：TICK-VALID，re_verified。`preview_capture.py` 15s CDP 截图与 `preview.py` 缩放保持一致。
- AC-002：TICK-VALID，re_verified。`preview_router.py` 认证、缓存与 404/304 行为保持一致。
- AC-003：TICK-VALID，re_verified。`runtime_coordinator.py` 瞬态 SSE 与前端更新链路保持一致。
- AC-004：TICK-VALID，re_verified。API/Supervisor 单一写者与文件栅栏防御保持一致。
- AC-005：TICK-VALID，re_verified。生命周期清理与停止保留机制保持一致。
- AC-006：TICK-VALID，re_verified。0600 权限与无信息泄漏保持一致。
- AC-007：TICK-VALID，re_verified。无前台激活且不影响标签状态保持一致。

coverage = re_verified / 7

verdict: PASS
