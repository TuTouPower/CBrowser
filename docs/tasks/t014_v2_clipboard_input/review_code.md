# Task review t014（reviewer_focus: 代码）

- task：`t014_v2_clipboard_input`
- spec：`docs/tasks/t014_v2_clipboard_input/task.md`
- diff_anchor：`6d28f59bc554743fa7e4cd3c987173a4b1b41df7`
- target：`git -C '<repo>_t014' diff 6d28f59bc554743fa7e4cd3c987173a4b1b41df7`
- round：1
- reviewed_at：2026-11-02T13:55:00+08:00

reviewed_scope: dbcc98b76b79d39d

## Findings

### t014_code_f001 - `clipboard_seamless` 仍为默认 true，官方客户端会自动读写本机剪贴板并跨 Profile 传播

- 严重度：critical
- 锚点：AC-001（明确用户操作、保护原剪贴板、后台不自动覆盖）、AC-003（容器与宿主剪贴板各自仅发生获授权变更）、AC-004（其他 Profile 不读到对应剪贴板数据）
- 位置：`src/backend/cbrowser/supervisor/container_spec.py:147-148`、`config/docker/stream_runtime/entrypoint.sh:177-178`；固定 wheel `selkies/settings.py:386-390`（`clipboard_seamless` 默认 `True`）与 `selkies/selkies_web/src/selkies-core.js` 的 `tn`/`on`/`canSync` 路径
- 问题：t014 只设置了 `SELKIES_ENABLE_CLIPBOARD` 与 `SELKIES_ENABLE_BINARY_CLIPBOARD`，没有设置/锁定 `SELKIES_CLIPBOARD_SEAMLESS=false`。Selkies 2.1.0 的 `clipboard_seamless` 默认 `True`；官方 WebRTC 客户端在 `focus` 时调用 `readAndSend()`（`navigator.clipboard.readText()`）把本机剪贴板发送到远端，并在远端剪贴板变化时用 `navigator.clipboard.write()`/`writeText()` 自动写入本机剪贴板。结果：用户仅聚焦会话就可能把本机剪贴板内容送到远端，远端复制也会覆盖用户原剪贴板；两个 Profile 的两个 tab 共享同一宿主剪贴板，Profile A 的数据可被 Profile B 的客户端在 focus 时读到并送入 B 的远端，违反 AC-004 的跨 Profile 隔离。前端提示 `i18n.tsx:306-307` 声称 “this page never overwrites it automatically”，与真实行为相反。
- 证据：`.scratch/t014_review_code/evidence/selkies_settings_probe.log` 显示 `clipboard_seamless=(True, False)`、`clipboard_enabled={'value': True}`；固定 wheel 的 `settings.py` 明确 `clipboard_seamless` 默认 True，帮助文本说明关闭后才会 “move clipboard content only when the user asks for it”。
- 建议：在 `stream_environment()` 与 entrypoint 中显式加入 `SELKIES_CLIPBOARD_SEAMLESS=false|locked`（bool 设置，`|locked` 有效），并增加真实 Chrome E2E 验证仅显式 Ctrl/Cmd+C/V 或侧栏剪贴板框触发传输、两 Profile 不互相传播；同时修正提示文案与 blueprint/spec 的 “显式复制/粘贴” 声明。

### t014_code_f002 - AC-002 已勾选，但没有四类输入目标、预编辑取消、标点或失败提示的实现/证据

- 严重度：important
- 锚点：AC-002
- 位置：`docs/tasks/t014_v2_clipboard_input/task.md:26`（已勾选）；继承证据仅 `tests/e2e/test_stream_runtime_e2e.py:1429-1481`
- 问题：t004 的现有 E2E 只在远端 `#overlayInput` 上做 8 组 composition 提交并断言 `co,end`，没有地址栏、普通输入框、受控输入框、富文本四类目标，也没有预编辑取消、标点、提交失败提示。t014 的 diff 没有新增任何 IME/输入 E2E；`note.md` 仅以 “沿用 t004/t007” 自述。按 AC-002 的语义，当前勾选不成立。
- 建议：在本 task 内补真实 Chrome 四类输入目标与 preedit cancel/标点/失败提示的 E2E；若确认由 t004 完整覆盖，则必须在 task.md 上下文区逐项列出继承证据并撤销本 task 的勾选声明，不能以自述代替证据。

### t014_code_f003 - AC-003 已勾选，但纯文本粘贴截断/重复与授权剪贴板变更无本 task 证据

- 严重度：important
- 锚点：AC-003
- 位置：`docs/tasks/t014_v2_clipboard_input/task.md:27`（已勾选）；`tests/e2e/test_stream_runtime_e2e.py:1478-1482`（仅验证 composition 未改 X11 clipboard）；`tests/e2e/test_frontend_session_e2e.py:248-338`（双页 ASCII 输入与独立静音）
- 问题：t004/t007 覆盖了双页输入、关闭一页不影响另一页和独立静音，但没有验证纯文本粘贴无静默截断/重复、容器与宿主剪贴板各自仅发生获授权变更，也没有双页剪贴板状态测试。新增 `tests/unit/test_stream_clipboard_policy.py` 只断言环境字符串，不触达粘贴路径。
- 建议：补真实 Chrome 大文本粘贴、精确内容/长度断言、双页并发粘贴与宿主/容器剪贴板变更断言；或将 AC-003 拆出未覆盖部分并保持未勾选。

### t014_code_f004 - AC-004 已勾选，但真实 Chrome 权限拒绝/后台恢复/切换 Profile 的剪贴板隔离无本 task 证据

- 严重度：important
- 锚点：AC-004
- 位置：`docs/tasks/t014_v2_clipboard_input/task.md:28`（已勾选）；`src/frontend/src/features/browser-session/clipboard_bridge.test.tsx:1-55`（jsdom mock `navigator.permissions`）；`tests/e2e/test_frontend_session_e2e.py`（无 clipboard permission 用例）
- 问题：t007 的 E2E 覆盖后台/恢复的视频可见性，不是剪贴板权限；t014 的前端测试只在 jsdom 中 stub `navigator.permissions`，没有真实 Chrome 的权限授予、权限拒绝、后台/恢复、切换 Profile 场景，也没有 “其他 Profile 读不到对应剪贴板数据” 的隔离断言。AC-004 当前勾选没有对应证据。
- 建议：补真实 Chrome + 独立已知 fixture 的权限矩阵与跨 Profile 隔离 E2E；在 `clipboard_sync=true` 且 `clipboard_seamless` 修正后，验证只有显式操作才跨页面/跨 Profile 传输。

### t014_code_f005 - 权限提示只在挂载时查询一次，实际拒绝流程不会出现 “denied” 提示

- 严重度：important
- 锚点：AC-001（权限拒绝提供可执行提示）、AC-004（获得权限、权限拒绝、后台/恢复）
- 位置：`src/frontend/src/features/browser-session/ClipboardPermissionHint.tsx:13-21`、`src/frontend/src/features/browser-session/clipboard_bridge.ts:17-32`
- 问题：`readClipboardPermission()` 只在 `useEffect(..., [])` 挂载时执行一次，没有监听 `permissionStatus.onchange`，也没有在 `focus`/`visibilitychange` 时重查。真实 Chrome 初始状态通常是 `clipboard-read=prompt`、`clipboard-write=granted`（本地实测，见 `.scratch/t014_review_code/evidence/chrome_permissions_probe.log`）；用户在首次 Ctrl+V 时拒绝后，组件仍停留在 “prompt” 文案，不会显示 AC-001 要求的拒绝提示。后台/恢复和权限变更同样不会刷新。
- 建议：保存 `PermissionStatus` 并监听 `onchange`，同时在 `focus`/`visibilitychange` 重新查询；补 prompt→denied、denied→granted、后台→恢复的组件测试。

### t014_code_f006 - `docker_adapter` 第二次解析 snapshot 失败时静默回退 `clipboard_sync=True`，关闭剪贴板的 Profile 可能以开启状态启动

- 严重度：important
- 锚点：AC-005（Profile `clipboard_sync` 关闭时 `enable_clipboard=false`）
- 位置：`src/backend/cbrowser/supervisor/docker_adapter.py:833-845`
- 问题：`_bound_snapshot_geometry()` 已在 `docker_adapter.py:790` 读取并校验同一 snapshot，随后 `start_stream()` 又独立读取/解析一次，并在 `except (OSError, ValueError, PathSecurityError)` 中把 `clipboard_sync` 静默设为 `True`。若 snapshot 在两次读取之间被替换、权限变化或解析失败，而 Profile 配置为 `clipboard_sync=false`，Stream 仍会以 `SELKIES_ENABLE_CLIPBOARD=true|locked` 启动，违反关闭语义，且失败无日志。该错误路径虽窄，但属于隐私相关的 fail-open。
- 建议：复用 `_bound_snapshot_geometry()` 已解析的 snapshot/config（一次读取），或在异常时 fail closed（拒绝启动或保持 `false`），并记录错误；补 snapshot 读取失败/替换的单元测试。

### t014_code_f007 - `enable_clipboard=true|locked` 在 Selkies 2.1.0 中是 no-op；当前仅靠 WebRTC allowlist 阻止客户端改写

- 严重度：minor
- 锚点：AC-005（“均服务端锁定”；“客户端改写设置不生效”）
- 位置：`src/backend/cbrowser/supervisor/container_spec.py:147`、`config/docker/stream_runtime/entrypoint.sh:177`、`tests/unit/test_stream_clipboard_policy.py:27`
- 问题：固定 wheel 的 `enable_clipboard` 是 `str` 类型（不是 bool），`_post_process_settings()` 会 `split("|")[0]` 丢弃 `|locked`；`build_client_settings_payload()` 发布的 `enable_clipboard` 只有 `value`，没有 `locked`；`sanitize_client_setting('enable_clipboard', 'false', ...)` 返回 `'false'`（probe 证据）。当前 WebRTC `settings_allowed_to_update` 恰好不包含 `enable_clipboard`，所以已知客户端路径不会改写；但 “服务端锁定” 并未按 AC 声明实现，测试只断言字符串，未验证锁。`enable_binary_clipboard` 的 `false|locked` 是有效的 bool 锁，binary 路径通过。
- 建议：修正 spec/blueprint 表述为 “`enable_clipboard` 由 WebRTC allowlist 保证客户端不可改写；`|locked` 仅对 bool 设置有效”，或在代码中增加对 `enable_clipboard` 的显式拒绝/锁定校验；测试应验证客户端实际发送 `SETTINGS,{"enable_clipboard":"false"}` 不生效，而不是只匹配环境字符串。

### t014_code_f008 - 提示未考虑 Profile 的 `clipboard_sync`，关闭剪贴板时仍显示 “请求权限” 文案

- 严重度：minor
- 锚点：AC-001/AC-005（关闭后双向均无传输；提示应与策略一致）
- 位置：`src/frontend/src/features/browser-session/BrowserSessionView.tsx:76`、`ClipboardPermissionHint.tsx:23-41`
- 问题：`ClipboardPermissionHint` 没有接收 Profile 的 `clipboard_sync`，只要 `stage === "connected"` 就按浏览器权限显示提示。Profile 明确关闭剪贴板时，服务端已禁用传输，但 UI 仍可能提示 “Clipboard access will be requested” 并引导用户授权，造成误导。
- 建议：从会话页把 `clipboard_sync` 传入（或通过 profile query 获取）；关闭时隐藏权限提示或显示 “此 Profile 已禁用剪贴板”，并补对应组件测试。

### t014_code_f009 - 文档/本地化/构建产物不一致

- 严重度：minor
- 锚点：文档与实现一致性；非行为 AC
- 位置：`docs/blueprint/frontend.md:37`、`docs/specs/webrtc_remote_display.md:41`、`src/frontend/src/i18n.tsx:302-307`、`src/frontend/tsconfig.tsbuildinfo:1`
- 问题：blueprint 写 “`ClipboardPermissionHint` 只在 `/selkies` iframe 内按需探测权限”，实际组件渲染在宿主页 `BrowserSessionView` 中（同源时权限查询等价，但描述错误）；spec 写 “传输仍由官方 Selkies 显式复制/粘贴触发，后台页面不自动覆盖”，与 f001 的 `clipboard_seamless=true` 行为矛盾；新增提示键只有英文，`zh` 字典缺失（`t()` 回退英文）；`tsconfig.tsbuildinfo` 是构建产物，本 task diff 修改了它，按项目 t007 约定不应进入交付。
- 建议：修正 blueprint/spec 表述；补 `zh` 文案；还原 `tsconfig.tsbuildinfo` 到基线，构建时再生成。

## 结论

- 本轮新发现：9 条（critical 1 / important 5 / minor 3）
- 未进表的提示：`src/backend/cbrowser/supervisor/docker_adapter.py` 1062 行（≥800 实现阈值，本 task 净增 14 行），无不可拆硬约束，建议后续拆分；`stream_environment` 圈复杂度低，无新增高复杂度函数。`docs/specs_index.md` 在 task 未收尾时已加入 t014，属流程提示，不单独计 finding。
- 总体判断：AC-001 的核心隐私语义被 Selkies 默认 `clipboard_seamless=true` 破坏；AC-002/003/004 被勾选但没有本 task 的实现/证据；AC-005 的 mapping、binary false、entrypoint CLI 基本成立，但 `enable_clipboard` 的 `|locked` 是 no-op，且 `docker_adapter` 存在 fail-open。当前存在未解决的 critical/important，FAIL。
- 系统性 follow-up：无新增独立 task；AC-002/003/004 的缺口应在 t014 内补齐（t009 只覆盖 1000 次压力，不替代本 task 的四类输入/权限/跨 Profile 场景）。

### AC 复验方式

- AC-001：`re_verified`（前端 `clipboard_bridge.test.tsx` 3 passed；固定 wheel probe `clipboard_seamless=(True, False)`；未运行真实 Docker/Chrome 剪贴板 E2E）。
- AC-002：`trust_prior`（仅继承 t004 `test_stream_runtime_e2e.py:1429-1481` 的 `#overlayInput` composition；本 task 无新证据，见 f002）。
- AC-003：`trust_prior`（继承 t004/t007 的双页输入/关闭/静音；无 paste 截断/重复与授权变更证据，见 f003）。
- AC-004：`trust_prior`（t007 仅覆盖后台可见性；无真实 Chrome clipboard 权限/切换 Profile 证据，见 f004）。
- AC-005：`re_verified`（`test_stream_clipboard_policy.py` 4 passed；wheel env/CLI probe 确认 `enable_clipboard=true/false`、`enable_binary_clipboard=(False,True)`；`enable_clipboard` 的 `|locked` 不生效，见 f007）。

coverage = 2 / 5
建议合并前人工抽查 trust_prior 项。

verdict: FAIL

## Round 2 (2026-11-02T14:30:00+08:00)

reviewed_scope: fc0ddf818c6a9558

### 前轮 finding 复核

- `t014_code_f001`：**已消除**。`container_spec.py:147-149` 与 `entrypoint.sh:177-179,203-205` 已显式设置并传递 `SELKIES_CLIPBOARD_SEAMLESS=false|locked`。独立 probe 固定 wheel：`clipboard_seamless=(False, True)`、`enable_binary_clipboard=(False, True)`、`clipboard_enabled/in/out=False`（`.scratch/t014_review_code_r2/evidence/selkies_seamless_probe.log`）；官方客户端 `canSync` 以 `clipboard_seamless` 为门控，自动 focus 读写路径已关闭。f001 的隐私阻断已解除；提示文案问题另见本轮 f011。
- `t014_code_f002`：**仍存在**。本轮独立重跑 `test_stream_runtime_multi_viewer_with_credentials_security_e2e`（真实 Browser/Stream/TURN 容器 + Mac Chrome，`1 passed in 86.94s`，`.scratch/t014_review_code_r2/evidence/e2e_stream_runtime_full.log`；首次因未设 `CBROWSER_TURN_TEST_IMAGE` 在 relay fixture 断言失败，属环境前置，非代码）只覆盖 `#overlayInput` 的 8 组 composition（`tests/e2e/test_stream_runtime_e2e.py:1417-1483`）与两页数字输入（`:1343-1381`）；地址栏、普通/受控输入框、富文本、预编辑取消、标点、失败提示均无实现或断言。`task.md:26` 的 AC-002 勾选仍不成立。
- `t014_code_f003`：**仍存在**。同一 E2E 覆盖双页输入与关闭一页后存活页输入（`test_stream_runtime_e2e.py:1567-1575`），但纯文本粘贴 round-trip、截断/重复断言、容器与宿主剪贴板“仅获授权变更”仍无；clipboard oracle 只断言中文 composition 期间 X11 剪贴板不变（`:1478-1483`），不是粘贴/授权变更测试。`task.md:27` 的 AC-003 勾选仍不成立。
- `t014_code_f004`：**仍存在**。E2E 是同一 Profile 的三个 viewer，不是两个 Profile；没有真实 Chrome 权限授予/拒绝、后台/恢复、切换 Profile、跨 Profile 剪贴板隔离断言。`clipboard_bridge.test.tsx` 仍是 jsdom mock（`navigator.permissions`）。`task.md:28` 的 AC-004 勾选仍不成立。
- `t014_code_f005`：**已消除**。`clipboard_bridge.ts:38-67` 订阅两个 `PermissionStatus` 的 `change` 并立即 `emit`；`ClipboardPermissionHint.tsx:16-20` 在挂载时调用。denied/prompt 状态可随权限变化更新；原“拒绝后仍显示 prompt”的阻断已解除。清理竞态另见 f010。
- `t014_code_f006`：**已消除（安全语义）**。`docker_adapter.py:833-845` 在第二次 snapshot 读取/解析失败时 `clipboard_sync=False`，不再 fail-open；AC-005 的关闭语义守住。异常吞掉与 `config` 非 dict 的窄路径见 f013。
- `t014_code_f007`：**已消除**。`docs/specs/webrtc_remote_display.md:40` 与 `docs/blueprint/stream_runtime.md:13` 已改述为：`enable_clipboard` 是字符串策略、`|locked` 不参与解析，客户端改写由 WebRTC settings allowlist 拒绝；固定 wheel `settings_allowed_to_update` 确实不含 `enable_clipboard`。
- `t014_code_f008`：**已消除**。`BrowserSessionPage.tsx:63` 传 `profile.clipboard_sync`，`BrowserSessionMount.tsx:21` 透传，`BrowserSessionView.tsx:77` 仅在 `clipboardSync` 为真时渲染提示；关闭 Profile 不再显示误导性权限提示。
- `t014_code_f009`：**修不彻底（minor 仍遗留）**。zh 文案（`i18n.tsx:630-635`）、blueprint/spec 描述已修；但 `git diff --numstat 6d28f59... -- src/frontend/tsconfig.tsbuildinfo` 仍为 `1 1`，构建产物仍在交付 diff 中，与 `note.md` “恢复 tsconfig.tsbuildinfo” 的处置不一致（t007/t008 约定该产物还原基线、不入 task diff）。

### 本轮新发现

#### t014_code_f010 - `ClipboardPermissionHint` 在权限查询完成前卸载会泄漏权限监听器

- 严重度：minor
- 锚点：行为缺陷（资源泄漏）；AC-001/AC-004 的权限状态监听路径
- 位置：`src/frontend/src/features/browser-session/ClipboardPermissionHint.tsx:13-25`
- 问题：`watchClipboardPermission(...).then((stop) => { cleanup = stop; })` 在 Promise 解析后只赋值；若组件在 `navigator.permissions.query` 完成前卸载，effect cleanup 先执行时 `cleanup` 仍为 `undefined`，随后 Promise 解析得到的 `stop` 永远不会被调用，`PermissionStatus` 上的 `change` 监听器保留。StrictMode 双挂载/快速导航可放大该泄漏，且监听器闭包仍引用组件 setter。
- 建议：在 `.then` 中判断 `active`：`if (active) cleanup = stop; else stop();`，或把 `watchClipboardPermission` 改为同步注册/返回可取消句柄；补卸载早于查询完成的组件测试。

#### t014_code_f011 - `clipboard_seamless=false` 下拒绝提示仍指导 Ctrl/Cmd+C/V，实际不会读写宿主剪贴板

- 严重度：important
- 锚点：AC-001「权限拒绝提供可执行提示」；AC-005 的 `clipboard_seamless=false|locked` 行为
- 位置：`src/frontend/src/i18n.tsx:303-307`（en）、`:631-635`（zh）；固定 wheel `selkies_web/src/selkies-core.js` 的 `canSync`/`readAndSend` 路径
- 问题：官方 WebRTC 客户端把 `canSync` 绑定到 `window.clipboard_enabled && clipboard_seamless`；`clipboard_seamless=false` 时，Chromium 的 Ctrl+V 不会调用 `readLocalClipboard`，Ctrl+C 也不会把远端 X11 剪贴板写回宿主。只有侧栏剪贴板框的 `clipboardUpdateFromUI` → `sendExplicit` 路径会显式传输本地文本。当前 denied 提示却写 “then use Ctrl/Cmd+C or Ctrl/Cmd+V explicitly”，用户授权后按提示操作不会发生本地↔远端传输，提示不可执行且与 AC-005 的锁定语义冲突。
- 建议：把提示改为“打开会话侧栏剪贴板框，显式粘贴/读取文本”（并说明二进制已禁用），或仅在 `clipboard_sync=true` 且确实允许快捷键同步时使用 Ctrl/Cmd+C/V 文案；同步修正 `docs/specs/webrtc_remote_display.md:41` 的“显式复制/粘贴”表述。

#### t014_code_f012 - `note.md` 处置表未转义 `|`，`check_review_status.py` 无法解析

- 严重度：important
- 锚点：交付/流程门禁（可观测失败：review 状态无法计算）
- 位置：`docs/tasks/t014_v2_clipboard_input/note.md:47`（f001 行的 `false|locked`）、`:53`（f007 行的 `|locked`）
- 问题：两行 rationale 中的裸 `|` 使 table 变成 6 列，脚本报 `Review 处置表数据列数与表头不一致`（`.scratch/t014_review_code_r2/evidence/review_status.log`）；`check_review_status.py --task-dir docs/tasks/t014_v2_clipboard_input` 直接退出，overall 无法计算，阻塞 finalization。该问题由本轮修复自述引入，不是代码层 finding。
- 建议：将 `|locked` 写作 `` `\|locked` `` 或改用“locked 后缀”文字；修正后重跑 `check_review_status.py` 确认 `review_scope=ok`。

#### t014_code_f013 - snapshot 二次解析失败被静默吞掉，`config` 非 dict 时还会抛未捕获 `AttributeError`

- 严重度：minor
- 锚点：健壮性/可观测性；AC-005 关闭语义的失败路径
- 位置：`src/backend/cbrowser/supervisor/docker_adapter.py:833-845`
- 问题：`except (OSError, ValueError, PathSecurityError)` 只把 `clipboard_sync` 设为 `False`，没有任何日志；同时 `json.loads(...).get("config", {})` 在 `config` 为 `null`/列表时返回 `None`/非 dict，后续 `.get` 抛 `AttributeError`，不在捕获列表内。首次 `_bound_snapshot_geometry()` 已校验过 config，但两次读取之间 snapshot 被替换时该窄路径可触发；当前行为虽仍 fail-closed，但诊断信息丢失且异常类型未覆盖。
- 建议：复用 `_bound_snapshot_geometry` 的一次读取结果（或在同一 try 中校验 `isinstance(config, dict)`），失败时 `logger.warning/error` 记录 profile 与异常类型（不含剪贴板内容），并补 snapshot 读取失败/替换的单元测试。

### 结论（Round 2）

- 前轮 finding 复核：f001/f005/f006/f007/f008 已消除；f002/f003/f004 仍存在（真实 E2E 只覆盖 composition/双页输入，不覆盖 AC 要求的四类目标、粘贴、权限/跨 Profile）；f009 修不彻底（`tsconfig.tsbuildinfo` 仍在 diff）。
- 本轮新发现：4 条（important 2：f011/f012；minor 2：f010/f013）。
- 未进表的提示：`docker_adapter.py` 1062 行（≥800 实现阈值，本 task 净增 14 行，无不可拆硬约束）；`readClipboardPermission()` 与 `watchClipboardPermission()` 的状态归并逻辑重复且前者仅测试使用，属维护性提示；4 个新交付文件仍为 `??` 未 `git add -N`，`git diff 6d28f59...` 不含它们，提交前需正式暂存；`specs_index.md` 在 task 未收尾时已登记 t014，属流程提示。
- 总体判断：f001 的 critical 隐私阻断已解除，f005/f006 的权限监听与 fail-open 已修复；但 AC-002/003/004 的勾选仍缺少契约要求的真实场景证据，且 f011 使 AC-001 的拒绝提示不可执行、f012 阻塞 review 状态门禁。当前仍有未解决的 important，FAIL。
- 系统性 follow-up：无新增独立 task；AC-002/003/004 的缺口应在 t014 内补齐（t009 只覆盖 1000 次压力，不替代四类输入/权限/跨 Profile 场景）。

### AC 复验方式（Round 2）

- AC-001：`re_verified`（代码/映射/组件测试）。独立 probe 固定 wheel 确认 `clipboard_seamless=false|locked` 解析为 `(False, True)` 且客户端 `canSync` 门控关闭自动读写；`clipboard_bridge.test.tsx` 4 passed。真实 Chrome 权限授予/拒绝、后台/恢复未复跑，相关子项仍依赖实现侧证据；提示文案问题见 f011。
- AC-002：`trust_prior`。本轮重跑 t004 E2E 的 8 组 composition 与双页输入（1 passed in 86.94s），但地址栏、普通/受控输入框、富文本、预编辑取消、标点、失败提示无证据（f002）。
- AC-003：`trust_prior`。本轮 E2E 覆盖双页输入与关闭一页后存活页输入；纯文本粘贴截断/重复、容器/宿主剪贴板授权变更无证据（f003）。
- AC-004：`trust_prior`。仅 jsdom 权限组件测试 + 同 Profile 多 viewer E2E；无真实 Chrome 权限拒绝、后台/恢复、切换 Profile 与跨 Profile 剪贴板隔离（f004）。
- AC-005：`re_verified`（映射/源码语义）。`tests/unit/test_stream_clipboard_policy.py` 2 passed；固定 wheel probe 确认 `enable_clipboard=false`、`enable_binary_clipboard=(False, True)`、`clipboard_seamless=(False, True)` 与 allowlist 不含 `enable_clipboard`；未用新 entrypoint 构建镜像跑真实 Docker/Selkies，关闭后零传输/二进制拦截的运行时子项仍为 `trust_prior`。

coverage = 2 / 5
建议合并前人工抽查 trust_prior 项（AC-002/003/004 及 AC-001/005 的真实运行时子项）。

verdict: FAIL
