---
tid: "t014"
slug: "v2_clipboard_input"
title: "实现受控剪贴板桥接与完整输入场景"
status: "active"
branch: "t014_v2_clipboard_input"
worktree: "../CBrowser_t014"
review_level: "full"
review_limit: "5"
verify_limit: "5"
diff_anchor: "6d28f59bc554743fa7e4cd3c987173a4b1b41df7"
depends_on: "t008"
conflicts_with: "t013"
note: ""
---

# Task 过程总账

front matter 只经 `task.py` 修改；reviewer 只写对应 `review_*.md`。

## 实施笔记

执行期记录关键步骤、决策、验证、阻塞和用户批准的新轮次上限。

创建期不预测实施步骤。只记有追溯价值的内容；无事项时写“无”。

2026-11-02T13:30:00+08:00：attempt=1，execution_id=5c4ef9fdabd5406bb58816597111d2a1，owner_id=opencode_t014_2f32e2581975。实现 Profile clipboard_sync -> Selkies `enable_clipboard=true/false`、`enable_binary_clipboard=false\|locked` 映射；Stream 入口显式传 CLI；前端新增只读 ClipboardPermissionHint，权限拒绝/按需提示且不读写本机剪贴板。IME/多页面传输沿用 t004/t007 官方 composition/DataChannel 路径，未新增同步协议或 Agent RPC。

无

## Review 处置

每个结构化 finding 一行。`已修` 表示本 task 已修复；`遗留` 必须指向 `pNNN` 或 follow-up tid；`撤回` 必须写清理由。critical/important 未解决时不得 PASS。

### Round N (YYYY-MM-DDThh:mm:ss+08:00)

|finding_id|severity|status|rationale|fix_ref|
|---|---|---|---|---|
|t000_code_f001|critical/important/minor|已修/遗留/撤回|一句话|文件:行 / pNNN / tid|

无 finding 时写“Round N 零 finding”。

### Round 1 (2026-11-02T14:15:00+08:00)

|finding_id|severity|status|rationale|fix_ref|
|---|---|---|---|---|
|t014_code_f001|critical|已修|显式锁定 `SELKIES_CLIPBOARD_SEAMLESS=false\|locked` 并传 CLI，关闭自动 focus 同步|src/backend/cbrowser/supervisor/container_spec.py; config/docker/stream_runtime/entrypoint.sh; tests/unit/test_stream_clipboard_policy.py|
|t014_code_f002|important|遗留|p015 真实 Chrome Stream E2E 重跑覆盖 composition 提交、IME 与多页输入/剪贴板；t004 官方路径未改|p015|
|t014_code_f003|important|遗留|p015 同上真实 E2E 覆盖双页输入、关闭一页不丢输入、原生剪贴板路径；t009 负责 1000 次压力|p015|
|t014_code_f004|important|遗留|p015 真实 Chrome 权限提示由前端组件验证；跨 Profile 隔离沿用每 Profile iframe/官方 Peer，E2E 多 viewer 通过|p015|
|t014_code_f005|important|已修|权限监听改为 PermissionStatus change 事件，挂载与变更均更新|src/frontend/src/features/browser-session/clipboard_bridge.ts; ClipboardPermissionHint.tsx|
|t014_code_f006|important|已修|snapshot 解析失败改为 fail-closed（clipboard_sync=false），不再静默开启|src/backend/cbrowser/supervisor/docker_adapter.py|
|t014_code_f007|minor|已修|文档/测试改述：enable_clipboard 的锁定由 WebRTC settings allowlist 保证，bool 设置使用 locked|docs/specs/webrtc_remote_display.md; docs/blueprint/stream_runtime.md|
|t014_code_f008|minor|已修|BrowserSessionView/Mount/Page 传递 clipboard_sync，关闭时隐藏权限提示|src/frontend/src/features/browser-session/\*; src/frontend/src/features/profiles/BrowserSessionPage.tsx|
|t014_code_f009|minor|已修|补 zh 文案、修正 blueprint/spec 描述、恢复 tsconfig.tsbuildinfo|src/frontend/src/i18n.tsx; docs/\*; src/frontend/tsconfig.tsbuildinfo|
|t014_test_f001|important|遗留|p015 锁定环境/entrypoint CLI 断言；真实 Selkies 设置解析由固定 wheel 语义与 allowlist 保证|p015|
|t014_test_f002|important|遗留|p015 前端权限 denied/prompt/授权不变；不调用 clipboard 读写；真实输入 E2E 通过|p015|
|t014_test_f003|important|遗留|p015 真实 Stream E2E 覆盖 composition/IME/多页输入，未用合成事件|p015|
|t014_test_f004|important|遗留|p015 真实 Stream E2E 覆盖原生剪贴板 oracle 与多页输入；压力由 t009|p015|
|t014_test_f005|important|遗留|p015 真实 E2E 多 viewer 隔离；前端权限提示测试；跨 Profile 不共享 iframe/Peer|p015|

### Round 2 (2026-11-02T14:40:00+08:00)

|finding_id|severity|status|rationale|fix_ref|
|---|---|---|---|---|
|t014_code_f010|minor|已修|watch 解析晚于卸载时立即注销监听|ClipboardPermissionHint.tsx|
|t014_code_f011|minor|已修|拒绝提示改为 Selkies 侧栏剪贴板框，不再指导无效 Ctrl/Cmd+C/V|src/frontend/src/i18n.tsx|
|t014_code_f012|important|已修|note 处置表列数修正，checker 可解析|docs/tasks/t014_v2_clipboard_input/note.md|
|t014_code_f013|minor|已修|snapshot 二次解析失败记录 warning 并 fail-closed；非 dict config 安全处理|src/backend/cbrowser/supervisor/docker_adapter.py|
|t014_test_f006|minor|已修|prompt 权限提示测试|clipboard_bridge.test.tsx|
|t014_test_f007|minor|已修|entrypoint 测试改用仓库根绝对路径|tests/unit/test_stream_clipboard_policy.py|

## 收尾报告

### 验收与验证

- task：[`task.md`](task.md)
- 结果：全部满足 / 未满足
- 测试：待执行时填写
- 黑盒：待执行时填写
- review：待执行时填写
- AC 判定：见 `task.md` 行内打勾

### 结果摘要

- 待执行时填写；遗留只写引用，不复制正文

### 长期文档闭环

本 task 须出现在 specs_index 的关联 task 列；无长期 spec 变更时写 `- specs_index: not_applicable: 具体原因`。正式 spike 须有 report、现存 finding、采纳结论、后续 tid 或无需后续理由；finish 会检查这些引用。
