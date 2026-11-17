---
tid: "t023"
slug: "frontend_session_consistency"
title: "统一前端会话、请求与交互语义"
status: "done"
branch: "t023_frontend_session_consistency"
worktree: ""
review_level: "full"
review_limit: "5"
verify_limit: "5"
diff_anchor: "aca792e864548c0c234baf34ca49ef08b821c418"
depends_on: "t022"
conflicts_with: "t020"
note: "review_20261103_185924：A17-A22/A49；复用运行时契约，不扩展现有字体和 ICE 任务"
---

# Task 进展

front matter 只经 `task.py` 修改；reviewer 只写对应 `review_*.md`。

## 实施笔记

执行期记录关键步骤、决策、验证、阻塞和用户批准的新轮次上限。

创建期不预测实施步骤。只记有追溯价值的内容；无事项时写“无”。

2026-11-03：用户授权按职责合并立项，本 task 为 53 项采纳结论中 7 项的唯一主承接；完整范围与 AC 对应见 task.md。现有 t019/t020 保留，原 A36/A37 拒绝；本轮未 start、未实现、未跑业务测试。

创建验证：`task.py preflight t023 --creation` 为 PASS；工作区未提交提示属于本批新建文档。无待外部用户决定的产品选项。

2026-11-04 执行（attempt 1 / execution_id 3d58b016eaf146d9869b7a8c909a5ac6 / owner exec-main-20261104-t023，base=t022 分支 aca792e）：

基线（干净 base，未改任何文件时实测）：模板契约 169 passed；v2 unit 710 passed + 2 failed（已知基线：test_repo_hygiene home 路径、test_runtime_persistence_guards terminal_storage_failure）；前端 Vitest 23 文件 105 passed；integration 基线单独记录于收尾前对照。注：契约测试 TMPDIR 必须在 git worktree 外，否则 fake_repo 的 .env 隔离出现 2 条误报（testing.md 已载明）。

实施计划（按 AC）：

- AC-001（A17）：redirect.ts 按规范化 pathname 比较（去尾斜杠 + 小写）排除一切 /login 变体；BrowserSessionPage 区分 loading / error（带重试）/ unknown（404）/ stopped；useBrowserSession 用 tRef 消除 t 身份对 runtime 检查 effect 的影响。
- AC-002（A18）：sse.ts 引入连接代次 generation（start/stop 推进、旧代次不投递/不重连、重复 start 不新增连接）；client.ts 区分外部取消（不可重试的 cancelled 错误）与内部超时（retryable timeout），并在请求结束后 removeEventListener 释放外部信号监听。
- AC-003（A19）：profiles/artifacts mutation hooks 改为每次 mutate/mutateAsync 调用边界生成动作 key（内部变量包裹 {input, actionKey}），重试复用同一 key、settle 不再清 ref；apply 复合动作由单次调用 key 派生 stop/start 两把不同 key。
- AC-004（A20）：SettingsPage 健康文案收窄为控制 API（新键 controlApiStatusTitle/controlApiStatusHint，删除旧 systemGatewayControlApi/systemApiServicesStatus）；ProfileFilesPage 上传失败文案带成功数、失败文件名、未处理数（新键 uploadPartialFailure），不输出文件内容。
- AC-005（A21）：i18n en 去 MessageDict 标注派生精确 TranslationKey，zh 以 satisfies Record\<TranslationKey,string> 约束 + 键集相等测试；i18n t() 身份在语言不变时保持稳定（useCallback 依赖 locale/dict）。types.ts 导出生成 ProfileRuntimeStatusEvent；sse.ts 以其为事件类型并在投递前验证真实事件语义（核心字段与状态枚举），畸形/未知事件走 error 通道不投递。
- AC-006（A22）：新增 shared/api/client-context（ApiClientContext + useApiClient），AppProviders 下发 apiClient，AppLayout 与各页面改经 context 取 client 并透传 hooks；页面流程测试改在 ApiClient 边界注入每例独立 stub（删除 BrowserSessionPage/ProfileDetailPage/searchDefaults/ProfileNewPage/ProfileFilesPage 中 vi.mock hooks 模块与单例普通赋值，改为真实接线）；auth_guard/router 测试改走 AppProviders apiClient 注入；client.test 两条名实不符用例改名并新增 fetch spy 断言 credentials=include；media_controls 断言具体 target origin；新增 tsconfig.test.json + test:types 门禁并接入 npm test，清除暴露的测试签名错误。
- AC-007（A49）：删除 readClipboardPermission 及仅测它的旧用例（保留 watcher 行为测试，删除理由见此）；删除 BrowserSessionViewProps.onSessionError；host_entry.tsx 移入 tests/fixtures/frontend_probe/ 并更新 host_builder.py 入口与相对 import；BrowserSessionMount 移入 features/browser-session 并从 types.ts 导入 BrowserSessionViewProps；删除 globals.css 零消费者 @layer components 块；tailwind 删除无消费者 accent（primary 为唯一品牌色权威）；AppLayout 两处标签回调参数 t 改名 tag。
- finalization：更新 blueprint/frontend.md 与 blueprint/testing.md；specs_index 关联 task 列处理见收尾。

2026-11-04 实施进度（AC-001～AC-007 全部落地，门禁实测）：

- AC-001：redirect 规范化比较 + redirect.test.ts 22 例；BrowserSessionPage 五态（loading / 非 404 错误带重试 / 404 未知 / runtime 错误带重试 / stopped）+ 真实接线页面测试 6 例；useBrowserSession 改 tRef（语言切换不重跑 runtime 检查，回归测试 1 例）。
- AC-002：client.ts timedOut 区分 cancelled（不可重试）/timeout（可重试）+ 监听释放，client.test 新增取消组；sse.ts 整文件重写（生成类型别名 + parseProfileRuntimeEvent 验证 + generation 代次隔离），sse_generation.test.ts 8 例。
- AC-003：shared/api/action_key_mutation.ts 的 useActionKeyMutation 在调用边界生成 key；profiles/artifacts 全部带 key hooks 迁入；actionkeys 测试 profiles 3 例 + artifacts 2 例，既有 retry/apply/wait 测试保持绿。apply 的 stop/start 键由单次动作 key 派生（页面级测试断言两键不同源同根）。
- AC-004：SettingsPage 改 controlApiStatusTitle/Hint（旧两键已删，SettingsPage.test 断言同步更新为新文案——A20 契约驱动的有意变更，非迁就实现输出）；ProfileFilesPage 首败即停 + uploadPartialFailure 文案（成功数/失败文件名/未处理数），页面测试新增部分失败用例。
- AC-005：types.ts 导出 ProfileRuntimeStatusEvent；i18n en 派生键集、zh satisfies 约束、字典导出 + 键集相等与非空测试（i18n.test 3 例）；t 身份经核实本就为 useCallback([locale])，语言切换重置问题由 AC-001 的 tRef 修复，i18n 侧无需再改。
- AC-006：shared/api/client_context.tsx（ApiClientContext + useApiClient，默认 defaultApiClient）；providers 下发；AppLayout 与六个页面改经 context。页面/守卫/路由测试全部改 ApiClient 边界注入独立 stub + 真实 hooks 接线（删除全部 vi.mock hooks 模块与单例普通赋值；ProfileAutomationPage.test 一并改注入）；覆盖流程：运行中挂载、启动成功/失败、保存、删除、复制、重置、apply（stop→start 顺序与派生键）、search-defaults 重试、字体包回显/提交、后台刷新不覆盖未保存编辑。client.test 两条名实不符用例已改名并补 fetch-spy credentials 断言 + downloadUrl 格式断言；media_controls postMessage 断言钉住 window.location.origin。新增 tsconfig.test.json + test:types（tsc -p，types 含 node）接入 npm test；为此新增 devDependency @types/node（测试本就使用 node:http/node:net）；门禁暴露的 69 处测试类型错误全部清除（夹具补全生成类型必填字段、SSE/运行时事件字面量补全为真实线形状、create 入参改用 DEFAULT_PROFILE_CREATE_VALUES、未用 import 删除、索引访问收紧）。
- AC-007：readClipboardPermission 已删（零生产消费者，其专属 2 例随之删除并在测试文件内注明理由，watcher 行为由组件测试保留覆盖）；onSessionError 已删；host_entry 移入 tests/fixtures/frontend_probe/（host_builder.py 入口路径更新 + 子进程注入 NODE_PATH 使 esbuild 能从 fixture 位置解析 bare import，已实测打包成功）；BrowserSessionMount 移入 features/browser-session 并复用 BrowserSessionViewProps；globals.css @layer components 块与 tailwind accent 已删（删除前 grep 确认零消费者）；AppLayout 标签回调改名 tag。生产构建后 grep dist 确认不含 \_\_cbrowserHostLoaded/\_\_statusBtnClicked。
- 门禁实测：前端 Vitest 27 文件 156 passed（基线 23/105）；test:types 零错误；生产 build（tsc -b + vite + selkies 校验）PASS。后端与模板契约全量对照在收尾轮执行。

## Review 处置

每个结构化 finding 一行。`已修` 表示本 task 已修复；`遗留` 必须指向 `pNNN` 或 follow-up tid；`撤回` 必须写清理由。critical/important 未解决时不得 PASS。

### Round 1（2026-11-04）

- t023_code_f001（important，AC-003）：已修——`client.profiles.retrySearchDefaults` 增加可选 idempotencyKey 并透传 `Idempotency-Key` 头（后端以该键为端到端 request_id 去重，router.py 注释与 coordinator 实现已核对）；`useRetrySearchDefaultsMutation` 改走 `useActionKeyMutation`；新增 hooks 级用例（重试复用同键、第二动作新键）与页面断言补键参数。实施笔记原「全部 hooks 已迁入」在修复前与代码不符，系本条纠正。
- t023_code_f002（important，AC-005）：已修——`parseProfileRuntimeEvent` 将 failure_count/restart_blocked/updated_at 改为必填校验（缺失或类型不符返回 null 走 error 通道）；新增「缺任一必填字段即拒绝」参数化用例；sse.test.ts 与 sse_hardening.test.ts 的模拟载荷补全为真实线形状（断言未动）。
- t023_code_f003（important，AC-002）：已修——`ApiClient.request` 将状态处理与响应体读取整体纳入同一 try/finally，超时与外部取消监听存续到体读完；错误体读取被 abort 时不再吞为「非 JSON」而交外层映射；新增「体仍在流式传输时外部取消以 cancelled 拒绝」用例。
- t023_code_f004（minor）：已修——search_defaults 子校验抽为独立 `isValidSearchDefaults` 辅助函数，顶层只保留主字段守卫。Round 2 复审认定修不彻底（顶层 CC≈16 仍略超阈值 15），随后核心字段守卫再抽为 `hasValidCoreFields`，顶层只剩空值/可选字段/子校验四道守卫，待 Round 3 定向复审确认。
- 门禁数字更正：integration 全量为 114 passed + 1 failed，失败用例 `test_api_search_defaults_routes::test_retry_route_requires_csrf_and_maps_outcomes` 与干净 base 全量同 ID（基线亦 114+1），零新增；先前笔记中「106 全过」为误读，已在本条更正，p026 同步修正。
- t023_test_f001（minor，AC-006）：已修——router.test 改为 makeStubClient 工厂每例构造（删除 beforeEach 逐个恢复方法的兜底）；ProfileAutomationPage.test 改为每次 render 构造新 stub。
- t023_test_f002（minor，AC-001）：已修——BrowserSessionPage.test 新增 loading 态用例（请求未决时只呈现加载、不出现 stopped/error/mount）与 runtime 错误分支重试用例（只重取 runtime、profile 不重复请求、恢复到待启动面板）。
- t023_test_f003（minor，AC-002）：已修——取消用例与新增超时用例均断言 external.signal.removeEventListener 在请求结束后被调用；体流式取消用例同样补断言。
- t023_test_f004（minor，AC-004）：已修——部分失败用例的文件内容改用与文件名无关的哨兵串，新增三条「文案不含文件内容」负向断言。
- t023_test_f005（minor，AC-002）：已修——sse_generation 两条负向断言弃用固定睡眠：旧代次用例改以当前代次两个完整重连周期作事件屏障；登出后用例改以重启后新代次两个重连周期作屏障（旧代次若误重连必多消费一次 fetch，计数断言可检出）。

|finding_id|status|fix_ref|
|---|---|---|
|t023_code_f001|已修|t023|
|t023_code_f002|已修|t023|
|t023_code_f003|已修|t023|
|t023_code_f004|已修|t023|
|t023_test_f001|已修|t023|
|t023_test_f002|已修|t023|
|t023_test_f003|已修|t023|
|t023_test_f004|已修|t023|
|t023_test_f005|已修|t023|

## 收尾报告

### 验收与验证

- task：[`task.md`](task.md)
- 结果：已实施，AC-001～AC-007 全部验证通过并打勾
- 测试：模板契约 169 passed；v2 unit 710 passed + 2 failed（基线存量同 ID：test_repo_hygiene home 路径、test_runtime_persistence_guards terminal_storage_failure，零新增）；integration 114 passed + 1 failed（test_api_search_defaults_routes::test_retry_route_requires_csrf_and_maps_outcomes，干净 base 全量同 ID、单文件单独跑亦失败，属本机环境存量，零新增）；前端 Vitest 27 文件 162 passed + test:types 零错误；生产 build PASS，dist 不含测试宿主 globals
- 黑盒：`CBROWSER_RUN_E2E=1 scripts/run_gates.sh` 依赖 Docker/真实拓扑，本机无 Docker，按用户 2026-11-03 豁免口径跳过并按 pass 计；真实环境执行义务见 p026
- review：full review 三轮——Round 1 code FAIL（important 3 + minor 1）/ test PASS（minor 5）→ 9 条 finding 全部已修；Round 2 code PASS（f004 残余 minor）/ test PASS（新 finding 0）；Round 3 定向复审两路 PASS（f004 残余消除，顶层 CC≈8），reviewed_scope 与最终 diff 一致
- AC 判定：见 `task.md` 行内打勾

### 结果摘要

- 前端会话、请求与交互语义统一：登录回跳变体封堵、会话页五态区分、SSE 生成类型校验 + 代次隔离、请求取消/超时可区分且监听存续至体读完、全部写操作（含 search-defaults 重试）按调用边界分配幂等键、设置页健康文案收窄、上传部分失败三段报告、i18n 键集编译期对齐、页面测试全面改为 ApiClient 边界注入 + 真实接线并新增测试类型门禁、零消费者代码与测试宿主移出生产树。遗留只写引用：真实环境黑盒义务见 p026；review 提示的既存项（sse_hardening 尾 flush 用例固定 50ms 睡眠的时序强度、i18n.tsx 文件体积）非本 task finding，未在本轮处理。

### 长期文档闭环

- specs_index：已将 t023 追加至 webrtc_remote_display、profile_management、storage_and_artifacts、access_control 四行关联 task 列并刷新时间戳；四份 spec 正文均已累积 t023 小节
- blueprint：frontend.md（客户端注入/取消语义/动作键、SSE 校验与代次、上传失败报告、设置页健康口径、i18n 键集、会话页状态区分、测试接线与类型门禁）与 testing.md（test:types 门禁）已更新
- spike/finding：无正式 spike、无新 finding 抽取
