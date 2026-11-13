# Task review t043（reviewer_focus: 测试）

- task：`t043_selkies_upgrade`
- spec：`docs/tasks/t043_selkies_upgrade/task.md`
- diff_anchor：`2e9558147b6c8ce0a6357115e23c003593f37327`
- target：`git -C '<repo>_t043' diff 2e9558147b6c8ce0a6357115e23c003593f37327`
- round：1
- reviewed_at：2026-11-05T19:30:08+08:00

reviewed_scope: f57a06cc51579761

## Findings

### t043_test_f001 - 注入 marker 单测含恒真兜底分支，且只能排除 2.1.0 旧 bundle 名

- 严重度：minor
- 锚点：AC-004 测试可信度（非 AC 覆盖缺口；AC-004 由真实 vendor 调用与 `verify_frontend_dist.py` 独立覆盖）
- 位置：`tests/unit/test_t043_selkies_pin.py:60`（`test_injection_marker_is_not_version_frozen`）
- 问题：`assert re.search(r"type=\\?\"module", source) or "module" in source` 的右分支 `"module" in source` 对 `scripts/vendor_selkies_web.py` 恒真（源码注释与注入正则字面量均含 "module"）。reviewer 独立实测左分支已匹配 `type=\"module`（返回 `True`），断言实际靠左分支成立，右分支是冗余恒真兜底；且首断言 `assert "index-BpOBp7NB.js" not in source` 仅排除 2.1.0 旧名，若注入 marker 被改回任意其它写死 bundle 名（如 2.2.1 的 `index-BD8uW1M7.js`），此测试仍 PASS，marker 重新冻结无测试报警。这是新增测试内的弱断言，不降低既有覆盖、不 mock、不 skip，不构成 AC 假绿。
- 建议：去掉 `or "module" in source` 兜底，改为精确断言生产注入正则存在；或把该意图并入 `test_frontend_adapter_build.py` 的真实注入顺序测试，删除此静态断言。

### t043_test_f002 - wheel SHA 常量断言弱化为长度检查，未锁定到 uv.lock 单一权威源

- 严重度：minor
- 锚点：AC-001 测试可信度（SHA 清单/产物匹配由 `verify_manifest` 真实覆盖，非 AC 覆盖缺口）
- 位置：`tests/e2e/test_frontend_session_vendor.py:45-46`、`tests/unit/test_t043_selkies_pin.py:46`
- 问题：被整体删除的 `test_pinned_constants` 原有 `assert PINNED_WHEEL_SHA256 == "8bde…966"`（精确 change alarm）。新测试对 `PINNED_WHEEL_SHA256` 仅断言 `len(...) == 64` 与 `!= hashlib.sha256(b"").hexdigest()`，任意 64 位十六进制串均通过；全仓无自动化测试断言该常量与 `uv.lock` 中 selkies 2.2.1 wheel hash 一致。reviewer 用 `tomllib` 独立核对二者逐字相等（`sha256:18503b5c1491…a3cd`），故当前值正确，但常量漂移时无自动报警。vendor 运行时对错误 hash fail-closed，不产生错误产物。
- 建议：改为动态一致性断言，例如 `assert "sha256:" + PINNED_WHEEL_SHA256 == <uv.lock 中 selkies wheels[0].hash>`，既恢复 change alarm 又不写死版本字面量；`len == 64` 可保留为附加格式检查。

### t043_test_f003 - s012 spike 报告「下表结论即其输出」与 compare.py 实跑输出不一致

- 严重度：minor
- 锚点：验证材料准确性（spike 为「范围」要求、非行为 AC；协议兼容性由 AC-003 E2E 黑盒证据支撑）
- 位置：`docs/spikes/s012_selkies_2_2_upgrade_contract/report.md:5,18`、`docs/findings/d030_selkies_2_2_1_upgrade_contract.md:4`、`docs/spikes/s012_selkies_2_2_upgrade_contract/code/compare.py:44,110`
- 问题：reviewer 独立实跑 `compare.py`（`urllib.request.urlopen` 真下载 2.1.0/2.2.1 官方 wheel 并 `assert sha256`）输出 `protocol strings in core: {'HELLO client ': False, 'client_tab_id': True, 'resume_key': True}`（两版本 `HELLO client ` 均 `False`）；但 `report.md:5` 称「下表结论即其输出」、`:18` 称 `HELLO client ` 前缀「同一上下文逐字相同」，`d030:4` 亦称「上下文逐字相同」。实测 `grep -c 'HELLO client ' .scratch/vendor_test/selkies-core.js` = 0：`HELLO client ` 是运行时信令消息（`webrtc_signaling_client.py` 的 `"HELLO {}".format(self.peer_type)` 生成、`adapter.ts:212` 以 `startsWith("HELLO client ")` 消费），本就不该作为 `selkies-core.js` 静态源码字面量出现；compare.py 把运行时协议串当作客户端静态字面量检查，该检查项设计失真，报告据以作出的「逐字相同」结论与脚本输出矛盾。另 `report.md` 的「仅一处日志括号」「新增 8 字体」「518,208→521,206 bytes」「index.html 差异」等结论也不在 compare.py 的 4 类输出（模块数 / ABI / core 协议串 / 原生 pin）内，「下表结论即其输出」表述过宽。协议语义保持本身由 AC-003 会话/Stream E2E 黑盒证据支撑，不受此文档偏差影响。
- 建议：把 compare.py 的 HELLO 检查改到信令生成点（比对 `webrtc_signaling_client.py` / `webrtc_signaling_server.py` 的 `HELLO {}` 与 `client_tab_id` / `resume_key`），或明确 `HELLO client ` 为运行时消息、从 core.js 静态串检查中移除；同步收敛 report / d030 措辞，避免「下表结论即其输出」被误读为全部结论均由脚本覆盖。

## 结论

- 前轮 finding 复核（Round N≥2 才写）：无（首轮）。
- 改测方向复核：无「迁就实现」的改测。`test_frontend_session_vendor.py::test_pinned_constants`（断言 `"2.1.0"` 字面量）整体删除，新测试 docstring 写明理由，新增 `test_pinned_version_matches_lock`（pin 与 pyproject/uv.lock 动态一致），旧常量字面量未就地改成 2.2.1。`test_frontend_adapter_build.py:86-94,114` 两处写死 `index-BpOBp7NB.js` 断言**未整体删除测试函数**，而是在同一函数体就地替换为版本无关「首个 module tag」检查并写明理由——按 AGENTS.md「旧测试原样保留或整体删除+写明理由」严格程序措辞有张力，但替换目标是版本无关契约而非 2.2.1 实现输出，核心顺序断言 `index_text.index(adapter_tag) < first_module.start()` 保留且更通用，且真实调用 `vendor_selkies_web()` 产物；按 prompt 改测方向复核（「断言应有的预期」vs「让断言迁就当前实现」）判为前者，非就地改旧预期、非弱化、非假绿。`test_t028_run_gates_evidence.py` 与 `test_frontend_build_wiring.py` 经 `git diff --name-only <anchor>` 确认未改动（文件存在、无 D 行）。
- 本轮新发现：3 条（均 minor，无 critical / important）。
- 未进表的提示：
    - 假绿专项核对结论：无 mock 掉被测逻辑（新测试 import 真实 `x11_keymap` / `vendor_selkies_web`、读真实 pyproject / uv.lock / SHA 清单，compare.py 真下载 wheel 并校验 SHA）；无把 skip 算 PASS（`junit/e2e.xml` 2 skip 明示 reason `t029 probe recheck runs only under CBROWSER_T029_PROBE_E2E=1 (t032)`，为既有门控且该测试文件未被改动，t032 `final_report.md` AC-011 `chain.xml 16 passed、0 skip` 容器探针补证、AC-014 明写「不把 skip 算 PASS」，progress.md 亦标「探针门控」）；无「只改预期 / 反转断言 / 注释断言 / `.skip` / `.only` / `eslint-disable` / 条件跳过弱化」。
    - 白名单指纹：`shasum -a 256` 实测 `docs/tasks/t034_runtime_platform_upgrade/review_code.md` = `4c32bf40…`、`review_test.md` = `b562b89c…`，与 `review_privacy_allowlist.txt` 新增 4 行中 2 个当前路径逐字一致；另 2 行 archive 路径文件当前不存在（预防性登记、指纹与当前路径同值），`test_repo_hygiene.py::approved_snapshots` 只解析不校验路径存在、不豁免任何现有 tracked 文件，复跑 `test_repo_hygiene.py` 通过，非缺陷。
    - spike / finding 闭环：`report.md:27-29`「采纳决定」有结论与「无需后续 task；无独立回退分支需求」，`d030:7`「采纳：t043（无后续 tid）」，均有采纳结论 + 无需后续理由。
    - 版本门禁与注入顺序独立复核：`x11_keymap.py:120-126` 的 `version("selkies") != SUPPORTED_SELKIES_VERSION → raise RuntimeError` fail-closed 保留、`_verify_selkies_keyboard_abi` 未弱化；`vendor_selkies_web.py:234` 注入正则与 `verify_frontend_dist.py:28` 通用 `MODULE_TAG` 一致，`.scratch/vendor_test/index.html`（真实 2.2.1 产物）adapter 位置 677 < 首个 module 722，早于全部 2 个 module script（主 bundle + `selkies-core.js`）与 modulepreload link。
    - 范围外观察（不进表）：`progress.md:43` 自述「Round 1 零 finding」与 `review_code.md` 1 条 minor 及本报告 3 条 minor 不一致，属实施侧处置表文字，非测试缺陷；`AGENTS.md:3,8` 仍写 2.1.0 属项目根说明、非交付 diff。
- 总体判断：4 条 AC 打勾均有真实测试 / 门禁 / 替代证据支撑，无 TICK-VOID；核心假绿检查（删测归因、改测方向、skip 计数、白名单指纹、生产逻辑可达）全部通过；仅 3 条 minor 测试可信度 / 验证材料准确性观察，无未解决 critical / important。PASS。
- 系统性 follow-up：无（3 条均为本仓内可修的 minor，无需新 tid）。

## 第 2 轮复核（scope 重绑定与根因修复）

- 背景：用户监督纠正指出 `test_frontend_session_freeze_resume_and_diagnostics` 在 2.2.1 两轮完整门禁连续失败属 2.2.1 引入的负载下时序回归，非 t032/t033 已登记偶发；Round 1 AC-003 的「已登记负载类偶发」归因作废。主代理修根因并补 TDD 后交付 diff 变化，被审 diff 指纹由 `4b9e2a7f46ceee2f` 重绑定为 `f57a06cc51579761`（重跑 `render_review_prompts.py`，本 reviewer 用 `repo_task.monitoring.review_scope_fingerprint` 独立重算一致）。progress.md 错误归因已更正、「负载下时序回归根因」章节（:34-40）存在，Review 处置表 4 行齐全、fix_ref 指向实际修复文件。
- 3 条 minor 已复核修复：f001 去掉恒真兜底，改为断言 vendor 源码不含任意 `assets/index-*.js` 哈希名（`test_t043_selkies_pin.py:60-69`）；f002 两个测试文件（`test_t043_selkies_pin.py:46-52`、`test_frontend_session_vendor.py:44-49`）的 wheel SHA 断言改为与 `uv.lock` selkies wheel hash 相等；f003 report/d030/task.md/progress 的 `HELLO client ` 表述改为「运行时拼接串、非静态字面量」，`compare.py` 的 PROTOCOL 改查 `HELLO ` 模板、输出与报告一致。code reviewer 的 f001（blueprint 现行概述）亦已修。
- 根因修复与 TDD 红绿经复核：`useBrowserSession.ts:38-46` 新增 `DIAGNOSTIC_STAGES`，`handleMessage`（:275-282）仅在诊断态忽略 `CBROWSER_WS_CLOSE`/`CBROWSER_PC_STATE`/`CBROWSER_LIFECYCLE_STALE`；守卫不覆盖 `CBROWSER_WEB_LOCKS_UNAVAILABLE`（:324 单独按原语义处理，更高优先级诊断），诊断态之外（如 `connected`）的 live session WS_CLOSE 恢复逻辑未改动。diff 为纯新增（生产 +27、测试 +29，无删除），旧测试预期与旧分支未就地改动、未放宽断言、未加长超时。`BrowserSessionView.test.tsx:194-221` 新增回归用例真触发 `CBROWSER_WS_CLOSE`（code 1006）并断言 `session-diagnostics-overlay` 与 reconnect/status 两按钮保持，走真实 iframe `MessageEvent` → 真实 `handleMessage`，不 mock 被测逻辑、不构成假绿；progress.md:40 登记先红（overlay 被卸载）后绿，本 reviewer 复跑 `BrowserSessionView.test.tsx` 26 passed、既有 `AC-007: CBROWSER_WS_CLOSE on a live connection triggers a real rebuild`（:370-386）与 `AC-008: Web Locks unavailable`（:125-139）一并通过；`test_t043_selkies_pin.py` + `test_frontend_session_vendor.py` 5 passed。
- 4 条 AC 的 TICK-VALID 结论继续有效（AC-003 事实归因已更正为负载下时序回归，E2E 黑盒证据与修复后门禁判据不受影响）；本轮无新 finding；verdict 保持 PASS。
- 最终判据是修复后完整门禁（证据 `.scratch/evidence_t043c/`）中该 E2E 用例通过，单跑不作数；本 reviewer 未跑 Docker E2E / 完整门禁，仅复核上述定向单测与 diff。

## AC 复验方式

- AC-001：TICK-VALID，re_verified。独立复跑 `test_pinned_version_matches_lock` + `test_vendored_tree_matches_reference_manifest`（`verify_manifest` 对 2018 行 SHA 清单与真实 vendored 树逐文件 sha256 校验）+ `test_t043_selkies_pin.py` 共 20 passed；核对 pyproject / uv.lock / requirements / Dockerfile / vendor pin 全 2.2.1、`PINNED_WHEEL_SHA256` 与 uv.lock selkies wheel hash 逐字一致、SHA 清单含根 `selkies_web/selkies-core.js` 且 `selkies_web/src/` 旧路径 0 条、主 bundle `index-BD8uW1M7.js`（2.1.0 旧名已移除）。
- AC-002：TICK-VALID，re_verified。独立复跑 `test_x11_keymap_version_gate_matches_lock` + `test_stream_keymap_abi.py` 通过；读 `x11_keymap.py:120-126` 确认版本门禁 fail-closed 保留、`_verify_selkies_keyboard_abi`（4 方法签名 / `_BIND_SETTLE_S` / 6 实例属性 AST）未弱化；真实 2.2.1 镜像内 ABI 实跑与 x11 键盘映射 E2E 通过依 `.scratch/evidence_t043b/` 门禁证据。
- AC-003：TICK-VALID，trust_prior。约束不跑 Docker / Chrome E2E，无法独立复跑无头全量；依赖 `.scratch/evidence_t043b/manifest.json`（contract / unit / integration / frontend_test / frontend_build 五 suite `exit_code=0`、`all_passed=false`）、`suites.tsv` 与 `junit/e2e.xml`（reviewer 解析 103 = 100 passed + 1 failed + 2 skipped）：唯一失败 `test_frontend_session_freeze_resume_and_diagnostics` 为 UI 按钮断言 `View status button must be available`（`e2e.log:128`），`.scratch/e2e_recheck2/` 三组 basetemp 对应 `test_frontend_session_e2e.py` 全文件 3 个用例定向重跑（progress.md 登记 3 passed / 90.64s），属 t032 / t033 已登记负载类偶发；2 skip 为 t032 探针门控、t032 `final_report.md` AC-011 容器探针补证，均不计 PASS 且如实登记。
- AC-004：TICK-VALID，re_verified。独立复跑 `test_frontend_adapter_build.py` 4 passed（真实调用 `vendor_selkies_web()` 产 index.html 并校验注入顺序与经典 IIFE）；读 `verify_frontend_dist.py:28` 通用 `MODULE_TAG`（base 既有、本 task 未改）与 `vendor_selkies_web.py:234` 注入正则一致；用 `.scratch/vendor_test/index.html`（真实 2.2.1 产物）实测 adapter 位置 677 < 首个 module 722，早于全部 2 个 module script 与 modulepreload link，`index.html.official` 无 adapter tag、注入恰一次；`npm run build` 的 `verify_frontend_dist.py --check-freshness` 通过依门禁证据。

coverage = 3 / 4

## reviewer 复跑记录

- 落点校验：`git rev-parse --show-toplevel` → `<repo>_t043`。
- diff 全量：`git -C … diff 2e9558147b6c8ce0a6357115e23c003593f37327`（24 文件，含测试 4 改 1 增）、`git -C … diff --name-only <anchor>`（确认 `test_t028_run_gates_evidence.py` / `test_frontend_build_wiring.py` 未改）、`git status --short`。
- 轻量单测（`.scratch/venv315/bin/python`，`PYTHONPATH=src/backend`）：`pytest tests/unit/test_t043_selkies_pin.py tests/unit/test_stream_keymap_abi.py tests/e2e/test_frontend_session_vendor.py tests/unit/test_repo_hygiene.py -q` → 20 passed；`pytest tests/e2e/test_frontend_adapter_build.py -q` → 4 passed（真下载 2.2.1 wheel 并 vendor）。
- spike 实跑：`.scratch/venv315/bin/python docs/spikes/s012_selkies_2_2_upgrade_contract/code/compare.py` → 两版本 31 模块、ABI 全一致、`native pins` 2.2.1/2.2.0 → 2.2.3/2.2.1、`HELLO client ` 为 `False`（见 f003）。
- 证据解析：python `xml.etree` 解析 `evidence_t043b/junit/*.xml`（5 suite 全绿、e2e 103 / 1F / 2S）、`manifest.json`、`suites.tsv`；`e2e.log` 尾行与失败栈、t032 / t033 登记、`.scratch/e2e_recheck*/` 目录。
- 独立核对：`shasum -a 256` t034 两份 review 报告；`wc -l` / `grep` 核对 SHA 清单 2018 行与 2.2.1 特征；`tomllib` 比对 `PINNED_WHEEL_SHA256` 与 uv.lock；python 实测 `re.search(r"type=\\?\"module", source)` 与 `"module" in source` 皆真、vendor_test/index.html 注入位置 677 < 722；`compare.py` 输出与 report.md 交叉比对。
- 格式与门禁：`python3 .repo_template/scripts/md_format.py docs/tasks/t043_selkies_upgrade/review_test.md`、`python3 .repo_template/scripts/check_review_status.py --task-dir docs/tasks/t043_selkies_upgrade`。

verdict: PASS
