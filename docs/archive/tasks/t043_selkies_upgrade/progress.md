---
tid: "t043"
slug: "selkies_upgrade"
title: "Selkies 升级到最新 2.x"
status: "done"
branch: "t043_selkies_upgrade"
worktree: ""
review_level: "full"
review_limit: "5"
verify_limit: "5"
diff_anchor: "2e9558147b6c8ce0a6357115e23c003593f37327"
depends_on: "t034"
conflicts_with: ""
note: "来源 plan_20261105_ui_redesign WP05；2026-11-05 按审阅从 t034 拆出"
---

# Task 进展

front matter 只经 `task.py` 修改；reviewer 只写对应 `review_*.md`。

## 实施笔记

执行期记录关键步骤、决策、验证、阻塞和用户批准的新轮次上限。

创建期不预测实施步骤。只记有追溯价值的内容；无事项时写“无”。

- 正式 spike：`docs/spikes/s012_selkies_2_2_upgrade_contract/`（report.md + code/ 下 2.1.0 / 2.2.1 官方 wheel 与解压源码），finding `docs/findings/d030_selkies_2_2_1_upgrade_contract.md`，结论回填 `task.md` 未知契约清单。目标 2.2.1（PyPI 最新 2.x，METADATA 支持 Python 3.15）。逐项比对：Python 模块清单相同；`webrtc_signaling_server.py` 的 HELLO / client_tab_id / resume_key / resume 语义不变（仅一处日志括号）；`_XTestKeyboard` 私有 ABI（4 方法签名、`_BIND_SETTLE_S`、6 实例属性）AST 校验 2.1.0/2.2.1 全部一致；`webrtc_engine.py` 的 `peer_conn` 字典结构 docstring 逐字相同；Web 客户端 `selkies-core.js` 从 `src/` 移到根但 `HELLO ${...}` 模板 / `client_tab_id` / `resume_key` 上下文逐字相同（`HELLO client ` 为运行时拼接串、非静态字面量），`adapter.ts` 的 WebSocket hook 有效。**无不可适配破坏性变化**，无需停止报告用户。
- 版本与依赖：`pyproject.toml` stream 组 `selkies==2.2.1`，`uv lock` 联动 pixelflux 2.2.1→2.2.3、pcmflux 2.2.0→2.2.1，重新导出 `config/docker/stream_runtime/requirements.txt`；`src/backend/cbrowser/stream_agent/x11_keymap.py` 新增 `SUPPORTED_SELKIES_VERSION="2.2.1"` 替换硬编码 `!= "2.1.0"` 门禁（ABI 校验本身不变），在真实 2.2.1 Stream 镜像内实跑 `_verify_selkies_keyboard_abi(_XTestKeyboard)` 通过。
- vendor 与 Web 客户端：`scripts/vendor_selkies_web.py` 的 `PINNED_SELKIES_VERSION` / wheel SHA256 / URL 改 2.2.1；注入 marker 由写死 2.1.0 bundle 名改为正则匹配「首个 module tag」，实跑 2.2.1 wheel vendor 后 adapter 位置 692 < 首个 module 722；`config/selkies/selkies_web_sha256.txt` 由 2.2.1 wheel 重生（2018 行，含根 `selkies-core.js`、不含 `src/` 旧路径）。`npm run build` 的 prebuild vendor + postbuild `verify_frontend_dist.py --check-freshness` 通过（AC-004）。
- TDD：`tests/e2e/test_frontend_session_vendor.py` 的 `test_pinned_constants`（断言 "2.1.0" 字面量）整体删除并写明理由，新增 `test_pinned_version_matches_lock`（pin 与 pyproject/uv.lock 动态一致）；`tests/e2e/test_frontend_adapter_build.py` 两处写死 `index-BpOBp7NB.js` 断言同样替换为版本无关的「首个 module tag」检查；新增 `tests/unit/test_t043_selkies_pin.py`（x11 版本门禁、SHA 清单、注入 marker 不冻结）。定向 12 + 6 passed。t034 两份 review 报告（随 base 进入 worktree）绝对路径按约定登记精确 sha256 指纹。
- 差异探针（完整门禁）：首轮 E2E 3 项失败——两项为写死 bundle 断言（已按 TDD 修复）、一项 `Reconnect button must be available`；第二项干净门禁 E2E 1 项失败 `View status button must be available`。**这两项是 2.2.1 引入的负载下时序回归，不是已登记偶发**：t032 登记遗留仅 t019 首帧超时与 Supervisor SIGKILL 端口恢复两项，t033 门禁的两项失败亦是这两项，该用例在 t033 与 t034 完整门禁均 PASS；它在 t043 两轮完整门禁连续失败、仅单跑通过。unit 首轮隐私白名单失败（t034 报告指纹，已登记）。根因与修复见下方「负载下时序回归根因」；修复后重跑完整门禁的结果见收尾报告。
- 长期文档：ADR 022（2.2.1 升级与契约适配、复查条件）、`conventions.md`、`stream_runtime.md`、`frontend.md`、`architecture.md` 版本表、`docs/specs/webrtc_remote_display.md`、`docs/specs_index.md` 关联 t043；ADR 002/013 历史「2.1.0 固定」原文不改（按 ADR 传播约定由 ADR 022 更新现行文档面）。

### 负载下时序回归根因（t043 监督纠正）

- 事实核对：t032 登记的遗留只有 t019 首帧超时与 Supervisor SIGKILL 端口恢复；t033 完整门禁 E2E 的两项失败也是这两项；`test_frontend_session_freeze_resume_and_diagnostics` 在 t033/t034 完整门禁均 PASS。它在 t043（Selkies 2.2.1）两轮完整门禁连续失败（首轮 `Reconnect button`、次轮 `View status button`），只在单跑时通过 → 属 2.2.1 引入的负载下时序回归，先前记为「已登记偶发」是错误归因，已更正。
- 时序比对（spike wheel 源码实证）：2.1.0 主 bundle 自身设置 `__SELKIES_DEFER_INITIALIZATION=!0`、动态 import `selkies-core-*.js` 后**立即** `selkiesCoreInitialize()`；2.2.1 把 core 拆成 body 末尾独立 `<script type="module" src="selkies-core.js">`，主 bundle 改 `await cm()` + `lm()`（轮询等待 `window.selkiesCoreInitialize` 出现，10ms 间隔、上限 10s）才初始化。因此 2.2.1 客户端信令 WebSocket 的 `connect()` 明显晚于宿主 `useBrowserSession.checkRuntime()`。
- 失败链：不存在的 profile → 宿主 `checkRuntime` 很快判定非 running → `stage=runtime_not_ready`，诊断 overlay 与 reconnect/status 按钮渲染；之后（负载下更晚）iframe 客户端初始化完成 → 对 `/stream/<unknown>/signal` 建 WS → Gateway 以非 1000 关闭 → `adapter.ts` 包装的 `close` 事件向宿主 post `CBROWSER_WS_CLOSE` → 宿主 `handleMessage` **无条件**调用 `handleInitialSignalingClose(code)` → `setStage("reconnecting")` → overlay 卸载、按钮消失 → 测试 `query_selector` 拿到 None。单跑时该序列在 `wait_for_selector` 之前已走完并回到诊断态，故通过；完整门禁负载放大窗口导致连续两轮命中。
- 修复（修根因，未放宽断言、未加长超时）：`useBrowserSession.ts` 定义 `DIAGNOSTIC_STAGES`（runtime_not_ready / signaling_failed / web_locks_unavailable / ice_failed / media_no_frames / error / stopping），`handleMessage` 在这些诊断态下忽略 `CBROWSER_WS_CLOSE` / `CBROWSER_PC_STATE` / `CBROWSER_LIFECYCLE_STALE` —— runtime 未运行时 iframe 的传输事件是预期余波，不得把已稳定的诊断 UI 推回 connecting。`CBROWSER_WEB_LOCKS_UNAVAILABLE` 仍按原语义处理（更高优先级诊断）。用户手动点 reconnect 后 stage 变为 reconnecting，不在诊断列表，恢复逻辑不受影响。
- TDD：新增 `BrowserSessionView.test.tsx` 的「t043: deferred client WS close 不扰动诊断态」用例，先红（overlay 被卸载）后绿；`BrowserSessionView.test.tsx` 26 passed、全量前端 217 passed。修复后须以**完整门禁**中该用例通过为准，单跑通过不作数。

## Review 处置

每个结构化 finding 一行。`已修` 表示本 task 已修复；`遗留` 必须指向 `pNNN` 或 follow-up tid；`撤回` 必须写清理由。critical/important 未解决时不得 PASS。

### Round 1 (2026-11-05T19:20:00+08:00)

|finding_id|severity|status|rationale|fix_ref|
|---|---|---|---|---|
|t043_code_f001|minor|已修|`architecture.md:5,76` 与 `stream_runtime.md:5` 的现行概述改 2.2.1（历史 t001/t019 语境保留 2.1.0）|docs/blueprint/architecture.md:5|
|t043_test_f001|minor|已修|去掉恒真兜底，改为断言 vendor 源码不含任何 `assets/index-*.js` 哈希名 + 含 `module_match` 与 module 正则|tests/unit/test_t043_selkies_pin.py:54|
|t043_test_f002|minor|已修|wheel SHA 断言改为与 `uv.lock` 的 selkies wheel hash 相等（两个测试文件）|tests/e2e/test_frontend_session_vendor.py|
|t043_test_f003|minor|已修|更正 report/d030/task.md/progress 表述：`HELLO client ` 是运行时拼接串、非静态字面量；`compare.py` 的 PROTOCOL 改查 `HELLO ` 模板 + client_tab_id/resume_key，输出与报告一致|docs/spikes/s012_selkies_2_2_upgrade_contract/report.md|

Round 1 零 critical/important；4 条 minor 全部已修。另按用户监督纠正修复 2.2.1 负载下时序回归（见「负载下时序回归根因」），交付内容变化后 scope 失效、已重新 review。

## 收尾报告

### 验收与验证

- task：[`task.md`](task.md)
- 结果：全部满足（AC-001~004 均在 2.2.1 镜像与新 vendor 产物上取得证据；2.2.1 引入的负载下时序回归已修根因，修复后完整门禁 `all_passed=true`、目标 E2E 用例在完整门禁中 PASS）
- 测试：完整 required+evidence 门禁 `CBROWSER_RUN_E2E=1 scripts/run_gates.sh`（Node 26.13、Python 3.15；最终证据 `.scratch/evidence_t043c/`）：contract / unit / integration / frontend_test / frontend_build / e2e **六个 suite 全部 exit 0，`manifest.json` 的 `all_passed=true`**；e2e 103 项 0 失败、2 skip（探针门控，t032 已由容器探针补证）。`test_frontend_session_freeze_resume_and_diagnostics` 在修复后的完整门禁中 PASS（用户要求的最终判据，单跑不作数）。`verify_frontend_dist.py --check-freshness` 通过；定向：`test_t043_selkies_pin.py` + `test_stream_keymap_abi.py` + `test_frontend_session_vendor.py`、`test_frontend_adapter_build.py` 全通过、`BrowserSessionView.test.tsx` 26 passed（含新增回归用例）、全量前端 217 passed、真实 2.2.1 镜像内 `_verify_selkies_keyboard_abi(_XTestKeyboard)` 通过、`verify_image_packages.py` 35 包一致。
- 黑盒：全量真实栈 E2E 的会话与 Stream 场景（会话阶段、同 Profile 多页面、复制标签页身份重映射、刷新/关闭首个页面、IME 组合输入、音频、剪贴板、可见性暂停恢复、Viewer 断线 resume）在完整门禁中全部无头通过。`test_frontend_session_freeze_resume_and_diagnostics` 在 2.2.1 两轮完整门禁连续失败（Reconnect / View status 按钮），定位为 2.2.1 延迟初始化导致的负载下时序回归（见「负载下时序回归根因」），已修根因；修复后完整门禁中该用例 PASS、`all_passed=true`。首轮门禁另 2 项失败（写死 2.1.0 bundle 名的旧断言）与 unit 隐私白名单（t034 报告指纹）已按 TDD/约定修复并登记。
- review：full 级独立 review（`review_code.md` / `review_test.md`）PASS。
- AC 判定：见 `task.md` 行内打勾

### 结果摘要

- Selkies 2.1.0 → 2.2.1（s012 spike + d030 finding 证明无不可适配破坏变化）：Stream 镜像、vendor 脚本 pin/wheel SHA/URL、SHA 清单（2018 行）、注入 marker（通用首个 module tag）、pixelflux 2.2.3 / pcmflux 2.2.1 随 uv.lock 联动、`x11_keymap` 版本门禁；ADR 022 与现行 blueprint/spec 同步，历史 ADR 原文不改。
- 遗留只写引用：无。2.2.1 引入的负载下时序回归已在本 task 内修根因并补 TDD 回归测试；修复后的完整门禁结果见收尾报告，不把该失败挂载到 t032 遗留。

### 长期文档闭环

- 本 task 更新 `docs/specs/webrtc_remote_display.md`（2.2.1 版本条目）；该 spec 已在 `docs/specs_index.md` 生效表内并追加 t043 关联，无新增 slug。
- 正式 spike `s012` 的 report、`code/` 下两版本官方 wheel 与比对材料入库；finding `d030` 记录结论与采纳；完结归档由 `repo-hygiene` 处理。
