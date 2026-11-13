# Task review t014（reviewer_focus: 测试）

- task：`t014_v2_clipboard_input`
- spec：`docs/tasks/t014_v2_clipboard_input/task.md`
- diff_anchor：`6d28f59bc554743fa7e4cd3c987173a4b1b41df7`
- target：`git -C '<repo>_t014' diff 6d28f59bc554743fa7e4cd3c987173a4b1b41df7`
- round：Round 1
- reviewed_at：2026-11-02T13:45:29+08:00

reviewed_scope: dbcc98b76b79d39d

## Findings

### t014_test_f001 - AC-005 只验证环境字符串，未验证 Selkies 运行时锁定/禁用/二进制拦截

- 严重度：important
- 锚点：AC-005「均服务端锁定；客户端改写设置不生效，关闭后双向均无剪贴板传输，图片等二进制剪贴板不传输」
- 位置：`tests/unit/test_stream_clipboard_policy.py:26-30`（映射断言）、`:33-58`（entrypoint 文本断言）
- 问题：唯一的 AC-005 测试只断言 `stream_environment()` 返回 `true|locked` / `false|locked`，以及 entrypoint 文件里存在对应文本；没有启动真实 Stream/Selkies，也没有驱动客户端 SETTINGS 去证明改写被拒、`clipboard_sync=false` 时双向无消息、二进制被拒。Selkies 2.1.0 把 `enable_clipboard` 解析为 str，`settings.py:2174-2180` 会剥掉 `|locked`；该设置的服务端锁定实际来自 `webrtc_mode.py:2904-2912` 的 `settings_allowed_to_update` 不含它，测试断言的字符串本身不证明锁定语义。`docker_adapter.py:833-845` 从 snapshot 读取 `clipboard_sync` 的接线也没有测试（reviewer 用 `.scratch/t014_review_test/probe_adapter_clipboard.py` 复验当前行为正确，但套件不会捕获回归）。
- 建议：新增真实 Docker/Selkies 集成用例：`clipboard_sync=false` 启动后发送客户端 SETTINGS 尝试改回 true，断言被拒；双向 clipboard 消息计数为 0；`enable_binary_clipboard` 尝试 true 被拒；关闭时文本也不传输。至少补 `start_stream_container` 对 snapshot `clipboard_sync=false` 的 env 断言。未补齐前 AC-005 不应打勾。

### t014_test_f002 - AC-001 只测 denied 提示，未测权限门控传输/后台覆盖/日志

- 严重度：important
- 锚点：AC-001「纯文本剪贴板传输遵从权限和明确用户操作，权限拒绝提供可执行提示；保护用户原剪贴板内容，后台页面不自动覆盖本机剪贴板，剪贴板内容不进入日志」
- 位置：`src/frontend/src/features/browser-session/clipboard_bridge.test.tsx:36-54`；`src/frontend/src/features/browser-session/ClipboardPermissionHint.tsx:13-23`
- 问题：直接覆盖 AC-001 的测试只有 `denied` 状态渲染 + `navigator.clipboard.readText/writeText` 未被调用；t004 的 sentinel 只证明 composition 期间 X11 clipboard 未变。它没有验证真实 Chrome 权限授予/拒绝下的纯文本传输、明确用户操作触发、原剪贴板内容保护、后台页面不自动覆盖宿主剪贴板、剪贴板内容不进入日志。`ClipboardPermissionHint` 只在 mount 时探测一次，测试也没有覆盖权限变化或恢复焦点后的状态；AC-001 的核心行为仍无证据。
- 建议：补真实 Chrome E2E：用独立 fixture 设置宿主剪贴板 sentinel，切换页面焦点/后台，断言后台不自动写宿主剪贴板、只有显式复制/粘贴才传输、日志不含剪贴板内容；或保持 AC-001 未勾。

### t014_test_f003 - AC-002 的四类输入目标/预编辑取消/标点/失败提示无测试

- 严重度：important
- 锚点：AC-002「地址栏、普通输入框、受控输入框、富文本中提交/预编辑取消/标点均精确到达目标浏览器，失败明确提示」
- 位置：`tests/e2e/test_stream_runtime_e2e.py:1418-1483`；`tests/e2e/test_frontend_session_e2e.py:321-345`
- 问题：t004 E2E 只覆盖一个 `probe_input` 的 composition commit（`Input.imeSetComposition` + `Input.insertText`）并断言 X11 clipboard sentinel 未变；t007 E2E 只覆盖两个页面的普通数字键盘输入。AC-002 明确列出的地址栏、受控输入框、富文本、预编辑取消（Escape）、标点、失败提示均无测试。本报告未在 t014 worktree 复跑这些继承测试，`.scratch` 中也无本 task 的 E2E 日志，打勾缺乏本 task 的直接证据。
- 建议：补真实 Chrome 场景（Playwright/CDP 真实键盘，不用 JS 合成事件），覆盖四类输入目标、预编辑取消、标点和输入失败提示；或收窄 AC-002 并保持未勾。

### t014_test_f004 - AC-003 的纯文本粘贴/无截断/无重复/剪贴板变更范围无测试

- 严重度：important
- 锚点：AC-003「纯文本粘贴无静默截断/重复，容器与宿主剪贴板各自仅发生获授权变更」
- 位置：`tests/e2e/test_stream_runtime_e2e.py:1478-1482`；`tests/e2e/test_frontend_session_e2e.py:222-239`、`:321-345`
- 问题：t007 E2E 覆盖两页输入和关闭一页后 B 页/容器仍运行；t004 E2E 只证明中文 composition 不修改 X11 clipboard sentinel。没有纯文本粘贴 round-trip、长文本截断/重复断言，也没有容器与宿主剪贴板各自变更次数的证据。AC-003 的剪贴板后半段完全未被验证。
- 建议：用真实 Chrome 双页 + 独立 clipboard fixture，粘贴长文本/多行/边界长度，断言远端 DOM 精确值与容器/宿主剪贴板变更次数；或保持 AC-003 未勾。

### t014_test_f005 - AC-004 无真实 Chrome 权限/拒绝/后台/切换 Profile 的剪贴板隔离测试

- 严重度：important
- 锚点：AC-004「真实Chrome页面在获得权限、权限拒绝、后台/恢复与切换Profile场景保持各自输入和剪贴板状态，其他Profile不读到对应剪贴板数据；所有测试使用独立已知fixture」
- 位置：`src/frontend/src/features/browser-session/clipboard_bridge.test.tsx:8-54`
- 问题：唯一权限测试是 jsdom 中 mock `navigator.permissions` 并渲染单个组件；没有真实 Chrome 的权限授予/拒绝、后台/恢复、切换 Profile 场景，也没有两个 Profile 的剪贴板隔离断言或独立 clipboard fixture。t007 的真实 Chrome E2E 覆盖的是视频/音频/输入，不是剪贴板权限或跨 Profile 剪贴板数据。
- 建议：补真实 Chrome 双 Profile E2E，使用独立已知 clipboard fixture，分别授予/拒绝权限、后台/恢复，断言 Profile B 读不到 Profile A 的剪贴板数据；或保持 AC-004 未勾。

### t014_test_f006 - prompt 状态提示未测

- 严重度：minor
- 锚点：AC-001 的权限状态提示；focus 要求的 denial/prompt hints
- 位置：`src/frontend/src/features/browser-session/ClipboardPermissionHint.tsx:34-39`；`clipboard_bridge.test.tsx:26-40`
- 问题：测试只覆盖 `denied`；`readClipboardPermission()` 返回 `prompt` 时的 `clipboardPermissionPrompt` / `clipboardPermissionPromptHint` 分支未渲染、未断言。该分支回归不会被发现。
- 建议：增加 prompt 状态渲染测试（mock 两个权限均为 prompt），断言 `data-clipboard-permission="prompt"` 和提示文案。

### t014_test_f007 - entrypoint 测试是纯文本 grep 且依赖 cwd

- 严重度：minor
- 锚点：AC-005 的入口 CLI 传递；测试可维护性
- 位置：`tests/unit/test_stream_clipboard_policy.py:33-58`
- 问题：测试只读取 `config/docker/stream_runtime/entrypoint.sh` 的文本并做字符串包含断言，不执行入口，也不验证 Selkies CLI 是否接受参数；`Path("config/...")` 相对 cwd，从非仓库根目录运行会直接 `FileNotFoundError`（reviewer 在 `.scratch/t014_review_test` 下复现：`1 failed, 1 passed`）。入口脚本语法/参数回归仍可通过该测试。
- 建议：用 `Path(__file__).resolve().parents[2]` 定位仓库根；增加 `bash -n` 或用一个 stub `python3` 执行入口并捕获 argv/env，断言实际传递值。

## 结论

- 前轮 finding 复核：Round 1，无前轮 finding。
- 改测方向复核：无。diff 未修改既有测试，只新增 `tests/unit/test_stream_clipboard_policy.py` 与 `clipboard_bridge.test.tsx`；未发现迁就实现的改测。
- 本轮新发现：7 条（5 条 important，2 条 minor）。

#### 未进表的提示

- 本次未复跑 Docker/Selkies E2E：`CBROWSER_RUNTIME_TEST_IMAGE`、`CBROWSER_STREAM_TEST_IMAGE`、`CBROWSER_RUNTIME_ENGINE_CACHE` 未设置；本地现有镜像早于本 diff，直接使用旧镜像不能证明新 entrypoint/映射。AC-002/003/004 的真实栈证据目前只依赖 t004/t007 历史记录。

- 本地已跑：`tests/unit/test_stream_clipboard_policy.py` 2 passed；完整 Vitest 17 files / 120 passed（含 `clipboard_bridge.test.tsx` 3 passed）。这些只证明单元层，不覆盖真实 Chrome/Docker 行为。

- 新增交付文件 `ClipboardPermissionHint.tsx`、`clipboard_bridge.ts`、`clipboard_bridge.test.tsx`、`test_stream_clipboard_policy.py` 当前为未跟踪状态（`git status` 显示 `??`），未出现在 `git diff 6d28f59...` 中；本报告按 worktree 内容审查。提交前请按流程 `git add -N` 或正式暂存，否则 diff 目标与 reviewed_scope 可能不一致。

- `src/frontend/tsconfig.tsbuildinfo` 在 worktree 中被修改（构建产物，包含新增文件路径）；不是测试 finding，但提交前应确认是否应随实现提交。

- `clipboard_bridge.test.tsx` 的 `afterEach` 只删除 `navigator.permissions`，未清理 `navigator.clipboard` stub；Vitest 按文件隔离下风险低，建议一并清理。

- 蓝图 `docs/blueprint/frontend.md:37` 要求 `ClipboardPermissionHint` 在 `/selkies` iframe 内按需探测，实际渲染在宿主页 `BrowserSessionView.tsx:76`；同源下权限状态可能一致，但本次测试没有 iframe 场景，建议 code reviewer 确认。

- 危险模式扫描：未发现 `.skip` / `.only` / 恒真断言 / 删除断言 / 注释断言 / 条件跳过弱化断言。`@ts-expect-error` 仅用于删除 test-only `navigator.permissions` stub，属预期类型错误，不构成掩盖失败。

- known pre-existing：`.repo_template` 契约失败与 `src/backend/tests` collection 错误未复跑，按用户说明 parked，不计入本报告。

- 总体判断：配置映射与前端提示实现本身未发现明显错误，但 5 条已勾 AC 的核心行为缺少可复现的真实栈证据，测试可信度不足，不能 PASS。

- 系统性 follow-up：无（本 task 内补齐真实 Chrome/Docker 用例；t009 只负责 1000 次输入/剪贴板与 8 小时基准，不覆盖上述基础权限、粘贴和隔离场景）。

### AC 复验方式

- AC-001：`trust_prior`。本地重跑 `clipboard_bridge.test.tsx` 3 passed，仅覆盖 denied 提示与不调用 `navigator.clipboard`；实际权限门控传输、原剪贴板保护、后台不自动覆盖、日志脱敏无真实 Chrome 证据。
- AC-002：`trust_prior`。查证 `tests/e2e/test_stream_runtime_e2e.py:1418-1483`（composition commit + X11 clipboard sentinel）与 `tests/e2e/test_frontend_session_e2e.py:321-345`（两页普通键盘输入），未复跑 Docker；地址栏/受控输入/富文本/取消/标点/失败提示无直接证据。
- AC-003：`trust_prior`。查证 `test_frontend_session_e2e.py:222-239`（关页后 B 页与容器仍运行）和 `:321-345`（两页输入），以及 t004 sentinel；纯文本粘贴/截断/重复/剪贴板变更范围无证据。
- AC-004：`trust_prior`。仅 `clipboard_bridge.test.tsx:8-54` 的 jsdom mock；真实 Chrome 权限授予/拒绝/后台恢复/切换 Profile/跨 Profile 剪贴板隔离无证据。
- AC-005：`re_verified`（仅映射/源码语义）。本地重跑 `test_stream_clipboard_policy.py` 2 passed，并用 `.scratch/t014_review_test/probe_adapter_clipboard.py` 验证 snapshot `clipboard_sync=True/False` 分别得到 `true|locked` / `false|locked`；另查 Selkies 2.1.0 wheel `settings.py:2174-2180`、`webrtc_mode.py:2904-2912` 确认 `|locked` 解析与 `enable_clipboard` 不在客户端可改列表。未做真实 Docker/Selkies 运行，客户端改写被拒、关闭后零传输、二进制拦截仍无运行时证据。

coverage = 1 / 5（AC-005 仅映射/源码语义计为 re_verified；其运行时子项与其余 4 条为 trust_prior）
建议合并前人工抽查 trust_prior 项。

verdict: FAIL

## Round 2 (2026-11-02T14:26:00+08:00)

reviewed_scope: fc0ddf818c6a9558

### 前轮 finding 复核

|finding_id|Round 1 严重度|Round 2 结论|复核证据|
|---|---|---|---|
|t014_test_f001|important|仍存在（修不彻底）|`tests/unit/test_stream_clipboard_policy.py:26-31` 仍只断言 env 字符串，`:34-66` 仍只 grep entrypoint 文本；新增 `SELKIES_CLIPBOARD_SEAMLESS` 静态断言没有运行时锁定、关闭后零传输或二进制拦截证据。`docker_adapter.py:833-845` 的 snapshot→env 接线仍无测试。本轮用本地现存 Stream 镜像 `sha256:afc32c64...` 重跑 t004 E2E 1 passed（89.75s），但该镜像 `/app/entrypoint.sh` 不含新增 clipboard 参数（`evidence/stream_image_entrypoint_check.log`），说明该 E2E 可在 pre-t014 镜像上通过，不能证明本 task 的 entrypoint 或 AC-005 运行时语义。另 probe 显示两个 bool 设置的锁定后缀解析为 `(False, True)`，而 `enable_clipboard` 是普通字符串，`sanitize_client_setting("enable_clipboard","true",...)` 返回 `'true'`；其不可改写只依赖 WebRTC allowlist，测试未验证这一层。|
|t014_test_f002|important|仍存在（修不彻底）|`clipboard_bridge.test.tsx:36-46` 新增 prompt 渲染测试，`:48-66` 覆盖 denied 提示且不调用 `navigator.clipboard`；但 `mockPermissions`（`:8-17`）返回的对象只有 `state`，没有 `addEventListener`，`watchClipboardPermission`（`clipboard_bridge.ts:53-63`）的权限变更监听从未被测试。真实 Chrome 的权限授予/拒绝、后台/恢复、原剪贴板保护和日志脱敏仍无证据；E2E `test_stream_runtime_e2e.py:1383-1482` 仍只是 composition 期间的 X11 clipboard sentinel。|
|t014_test_f003|important|仍存在|E2E 重跑仍只覆盖 `#overlayInput` 的 8 组 composition 与 `probe_input` ASCII 输入（`tests/e2e/test_stream_runtime_e2e.py:1330-1482`）；地址栏、受控输入框、富文本、预编辑取消（Escape）、标点和输入失败提示均无测试。AC-002 在 `task.md:27` 仍打勾。|
|t014_test_f004|important|仍存在|E2E `tests/e2e/test_stream_runtime_e2e.py:1368-1380` 覆盖双页 Digit1/Digit2，`:1539-1575` 覆盖关闭一页后另一页继续输入；`:1480-1482` 仍只断言 composition 未改 X11 clipboard。纯文本粘贴 round-trip、无截断/重复、容器与宿主剪贴板各自仅发生获授权变更均无测试。|
|t014_test_f005|important|仍存在|E2E 多 viewer 测试是同一 Profile（`tests/e2e/test_stream_runtime_e2e.py:462`），没有跨 Profile 剪贴板隔离、真实 Chrome 权限授予/拒绝矩阵或后台/恢复场景；`clipboard_bridge.test.tsx` 仍是 jsdom mock。|
|t014_test_f006|minor|已消除|`clipboard_bridge.test.tsx:36-46` 新增 prompt 状态断言 `data-clipboard-permission="prompt"` 与文案；本轮该文件 4 passed。|
|t014_test_f007|minor|仍存在（部分修）|`:34-66` 已按非注释行匹配，但 `:35` 仍使用 `Path("config/docker/stream_runtime/entrypoint.sh")`。本轮从 `.scratch/t014_review_test_r2` 运行复现 `FileNotFoundError`（`evidence/unit_clipboard_foreign_cwd.log`）；测试仍依赖 cwd，且未执行 entrypoint 或 `bash -n`。|

### 本轮独立复验

- `tests/unit/test_stream_clipboard_policy.py`：repo 根目录 2 passed；从 `.scratch/t014_review_test_r2` 运行 1 failed / 1 passed（f007 复现）。
- `tests/unit` 全量：491 passed，7 warnings in 41.98s（`evidence/unit_all_tail.log`）。
- `clipboard_bridge.test.tsx`：4 passed（`evidence/vitest_clipboard_bridge.log`）。
- 前端全量：17 files / 121 passed in 18.55s（`evidence/frontend_all_tail.log`）。
- 真实 t004 Stream E2E：`test_stream_runtime_multi_viewer_with_credentials_security_e2e` 1 passed in 89.75s，使用 `CBROWSER_RUNTIME_TEST_IMAGE=sha256:fce542f...`、`CBROWSER_STREAM_TEST_IMAGE=sha256:afc32c64...`、`CBROWSER_TURN_TEST_IMAGE=sha256:e2bca2f...` 与只读 engine cache（`evidence/e2e_stream_rerun.log`）。该重跑确认 composition/IME/双页输入/多 viewer 路径未回归，但不能替代 AC-002/003/004 缺失场景。
- Selkies 2.1.0 wheel probe：`clipboard_seamless=false|locked` → `(False, True)`，`enable_binary_clipboard=false|locked` → `(False, True)`，`enable_clipboard=false` 的客户端 `true` 在共享 sanitizer 中返回 `'true'`（`evidence/selkies_settings_probe.log`）。
- 合成事件扫描：E2E 使用真实 Chrome 的 `page.keyboard.press` 与 CDP `Input.imeSetComposition`/`Input.insertText`，未用 JS 合成事件或写远端 DOM 冒充提交；此项未发现回归。

### 未进表的提示

- 新增交付文件 `ClipboardPermissionHint.tsx`、`clipboard_bridge.ts`、`clipboard_bridge.test.tsx`、`test_stream_clipboard_policy.py` 仍为未跟踪状态（`git status --short` 显示 `??`），未出现在 `git diff 6d28f59...` 中；本报告按 worktree 内容审查，`reviewed_scope` 与当前 worktree 指纹一致。提交前应正式暂存或 `git add -N`。
- `clipboard_bridge.test.tsx` 的 `afterEach` 仍未清理 `navigator.clipboard` stub（Round 1 已提示），当前测试顺序下风险低，建议一并清理。
- 真实 E2E 重跑未构建包含本 task entrypoint 的 Stream 镜像；若要以 E2E 证明 entrypoint/AC-005，需重建当前源 Stream 镜像并记录不可变镜像 ID，同时增加客户端 SETTINGS 改写、`clipboard_sync=false` 零传输、二进制剪贴板拒绝的断言。
- `.repo_template` 契约失败与 `src/backend/tests` collection 错误按用户说明为 pre-existing parked，不计入本报告。
- `check_review_status.py` 因 `note.md` Round 1 处置表存在未转义的 `|`（如 `false|locked`、`|locked`）报「Review 处置表数据列数与表头不一致」，无法输出自动 scope 校验；本轮手工计算当前 worktree 指纹为 `fc0ddf818c6a9558`，与 prompt 注入值一致。按只读边界未修改 `note.md`，该处置表需由实施侧修正。

### 改测方向复核

- 无。diff 未修改既有测试断言；新增测试未发现迁就实现的改写。

### AC 复验方式

- AC-001：`trust_prior`。本轮重跑 `clipboard_bridge.test.tsx` 4 passed，覆盖 prompt/denied 初始提示；真实纯文本传输、原剪贴板保护、后台不自动覆盖、日志脱敏仍无真实 Chrome 证据。
- AC-002：`trust_prior`。真实 E2E 重跑覆盖 `#overlayInput` composition 与 `probe_input` ASCII；地址栏/受控输入框/富文本/预编辑取消/标点/失败提示无直接证据。
- AC-003：`trust_prior`。E2E 重跑覆盖双页输入和关闭一页后存活；纯文本粘贴、截断/重复、容器与宿主剪贴板变更范围无证据。
- AC-004：`trust_prior`。仅有同一 Profile 的多 viewer E2E 与 jsdom 权限测试；跨 Profile 剪贴板隔离、真实权限授予/拒绝、后台/恢复无证据。
- AC-005：`re_verified`（仅 env/entrypoint 静态与 wheel 语义）。重跑 `tests/unit/test_stream_clipboard_policy.py` 2 passed，并用 wheel probe 确认 bool 锁定解析；真实运行时客户端改写、关闭后零传输、二进制拦截仍未验证。

coverage = 1 / 5
建议合并前人工抽查 trust_prior 项。

### 结论

- 本轮新发现：0 条。
- 总体判断：f001、f002、f003、f004、f005 仍为未解决的 important；f006 已消除；f007 仍为 minor。AC-002/003/004 仍缺少有效测试支撑，AC-005 运行时仍无证据，不能 PASS。
- 系统性 follow-up：无新增（真实 Chrome/Docker 场景仍应在本 task 内补齐；t009 只负责 1000 次压力，不替代这些基础场景）。

verdict: FAIL
