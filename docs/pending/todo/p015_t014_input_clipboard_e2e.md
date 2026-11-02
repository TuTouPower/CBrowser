# p015 补 t014 四类输入与真实剪贴板权限 E2E

- 来源：t014 review（AC-002/003/004 未闭合）
- 内容：补真实 Chrome E2E：地址栏、普通输入框、受控输入框、富文本中的 composition 提交/预编辑取消/标点/失败提示；纯文本粘贴无截断/重复及双页并发；真实权限授予/拒绝、后台/恢复、切换 Profile 的剪贴板隔离；使用本 task 新 entrypoint/镜像验证 `enable_clipboard`/`clipboard_seamless` 运行时语义。当前 t014 仅完成 AC-001/AC-005，AC-002/003/004 保持未勾选。
- 处理：未开

## 2026-11-02 attempt 2 记录

- 尝试在既有 `tests/e2e/test_stream_runtime_e2e.py` 单体用例中追加四类目标/粘贴/地址栏测试；扩展 fixture 后，在 IME 阶段之后继续用原 CDP target 执行 `Runtime.evaluate` 被 Chrome 拒绝（target 已失效/状态不可复用），未能在该单体用例内稳定复用。相关实验改动已还原，未提交。
- 结论：需要独立 t014 E2E harness（新起 Browser+Stream+双 Profile，按场景分阶段），不要在 t004 单体用例后段追加；保留 AC-001/AC-005 已交付部分。
