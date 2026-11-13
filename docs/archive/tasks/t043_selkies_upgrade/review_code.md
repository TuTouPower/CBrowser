# Task review t043（reviewer_focus: 代码）

- task：`t043_selkies_upgrade`
- spec：`docs/tasks/t043_selkies_upgrade/task.md`
- diff_anchor：`2e9558147b6c8ce0a6357115e23c003593f37327`
- target：`git -C '<repo>_t043' diff 2e9558147b6c8ce0a6357115e23c003593f37327`
- round：1
- reviewed_at：2026-11-05T19:21:12+08:00

reviewed_scope: f57a06cc51579761

## Findings

### t043_code_f001 - 现行 blueprint 概述仍写 Selkies 2.1.0，ADR 022 传播未覆盖同文件其它语句

- 严重度：minor
- 锚点：文档与实现不一致（非行为 AC，纯版本描述）；ADR 传播约定 `docs/blueprint/decisions.md:10`
- 位置：`docs/blueprint/architecture.md:5`、`docs/blueprint/architecture.md:76`、`docs/blueprint/stream_runtime.md:5`
- 问题：本 task 把 architecture.md 版本表（:31）与 stream_runtime.md 的 x11 段（:47）改为 2.2.1，但同一批「当前系统」语句仍写 2.1.0：architecture.md:5「通过 Selkies 2.1.0 WebRTC 实现低延迟远程画面传输」、:76 架构图「Selkies 2.1.0 WebRTC 捕获编码引擎」、stream_runtime.md:5「Stream Runtime 负责单个 Profile 的 Selkies 2.1.0 捕获」。现行文档面同时出现 2.1.0 / 2.2.1，读者据此会误判当前钉版。按 `decisions.md:10`「新增或替代 ADR 时，同一变更须同步核对并更新受影响的现行文档面」，这三处属应同步而未同步的现行描述。历史描述行（architecture.md:15 / :31 备注「官方 2.1.0 缺乏原生 ICE restart」、stream_runtime.md:43 的 t019 回退说明、decisions.md 的 ADR 002 / 013、`docs/specs/v2_runtime_validation.md` 的 t001 验收快照）描述过去版本事实，保留 2.1.0 合理，不在本条范围。
- 建议：把上述三处现行语句改为 2.2.1（或注明「t043 起 2.2.1」）；历史描述行保持不动。纯文档同步，不改代码与行为，按项目技术约束判断（普通版本号非行为 AC）不阻断。

## 结论

- 本轮新发现：1 条（minor）。clean 范围内无 critical / important。
- 未进表的提示：
    - 版本 pin 全链路一致性（独立脚本复核通过）：`pyproject.toml` / `uv.lock` / `config/docker/stream_runtime/requirements.txt` / `scripts/vendor_selkies_web.py` / `x11_keymap.SUPPORTED_SELKIES_VERSION` 全为 2.2.1；`PINNED_WHEEL_SHA256=18503b5c...` 与 `uv.lock` 的 selkies wheel hash 逐字一致，wheel URL 同为 `packages/40/33/ece2923...`；`PINNED_SELKIES_VERSION` 与 pyproject / uv.lock 动态一致（新增单测 3 passed）。Dockerfile / agent.py / x11_keymap.py 注释版本引用同步。除 f001 三处外，conventions / frontend / stream_runtime(x11 段) / architecture(表) / specs / specs_index 均为 2.2.1。
    - vendor 注入 marker 正则可靠：`vendor_selkies_web.py:234` 的 `r"<script[^>]+type=\"module\"[^>]*>"` 与产品校验脚本 `verify_frontend_dist.py:28` 的 `MODULE_TAG`（base 既有、本 task 未改）完全一致，注入点取首个 module tag、插 adapter 于其前；独立构造 2.2.1 index.html 样本（head 内 inline `__SELKIES_DEFER_INITIALIZATION` + modulepreload `<link>` + 主 bundle module，body 末尾 `selkies-core.js` module）实跑，首个命中为 head 主 bundle，adapter 位于全部 module tag 之前（171 < 216/328），符合「经典 IIFE adapter 在 head 首位、早于全部 module」；`<head>` fallback 分支保留。`[^>]+` 不能跨 `>`，只在单个开标签内匹配，未发现误匹配到 inline script / link 的情形。
    - SHA 清单与 2.2.1 wheel 对应：`config/selkies/selkies_web_sha256.txt` 2018 行，含 `index-BD8uW1M7.js`、Inter woff2、rolldown-runtime、jsdb、根 `selkies_web/selkies-core.js`，不含 `selkies_web/src/` 旧路径（与 s012 spike / d030 finding 的 2.2.1 文件清单特征吻合）；`verify_manifest`（:39-88）对每文件做真实 sha256 校验并拒清单外文件，非恒真、非 mock。
    - `x11_keymap` 版本门禁仍 fail-closed：`x11_keymap.py:123-126` 的 `version("selkies") != SUPPORTED_SELKIES_VERSION or not Path(_XKBCOMP).is_file(): raise RuntimeError` 保持短路即抛；`_verify_selkies_keyboard_abi`（:88-115，4 方法签名 / `_BIND_SETTLE_S` / 6 实例属性 AST）逐字保留未弱化；改动仅把硬编码 `"2.1.0"` 提为常量并让错误信息更明确。
    - 历史 ADR 002 / 013 不改合规：`decisions.md:3`「追加新条目，不重写历史」、:9「冻结原文不改」、:10 传播清单；本 task 以 ADR 022 新增 + 同步现行文档面处置，正确。spec 范围第 3 条字面「修订 ADR 002、013」与 ADR 不可变约定冲突，按 prompt 技术约束判断（非行为 AC、应同步长期 ADR / spec）不判 blocking。
    - TDD 与断言（测试层，交 test reviewer 复核，不据此改 code verdict）：`test_pinned_constants`（断言 "2.1.0" 字面量）整体删除并写明理由、新增 `test_pinned_version_matches_lock`，符合「旧测试原样保留或整体删除+写明理由、禁止就地改旧预期」。观察到以下测试层 anti-pattern，AC 仍由真实产品逻辑与门禁证据支撑、非假绿：(1) `tests/unit/test_t043_selkies_pin.py:60` `assert re.search(...) or "module" in source` 第二分支恒真（脚本注释即含 "module"）；(2) `tests/e2e/test_frontend_session_vendor.py:45-46` wheel SHA 断言由原具体值降为 `len==64` 且 `!= sha256(b"")`，不再锁定到具体值 / uv.lock；(3) `tests/e2e/test_frontend_adapter_build.py:91-94`、`:114` 两处写死 `index-BpOBp7NB.js` 断言为同函数内就地替换为版本无关「首个 module tag」检查（非整体删除 / 新增，与「旧测试原样保留或整体删除」程序要求有张力，但改为语义约束而非迎合实现输出、核心顺序断言 `index(adapter) < first_module.start()` 保留且更强），未发现 mock 掉被测逻辑（verify_manifest / vendor / 注入均真实执行）。
    - 隐私白名单登记 `tests/unit/review_privacy_allowlist.txt` 新增 4 行：2 个当前路径 sha256 实测 OK，2 个 archive 路径为未来归档预留（文件当前不存在、sha 与当前路径同值），沿用 t032/t033 成对登记约定，非缺陷。
    - 文件过大 / 圈复杂度：实现源码 x11_keymap.py 203 行、vendor_selkies_web.py 302 行、agent.py 仅注释改动，测试文件均 < 400/600 阈值；SHA 清单 2018 行为生成物、spike wheel 材料排除；无函数 CC≥10，不进表。
    - 7 视角（安全 / 正确性 / 契约·Breaking / 性能·资源 / 架构·可维护性 / 健壮性·可观测 / 测试·文档·规格）已扫：vendor 正则处理的是 wheel 内固定 index.html，无外部输入直达执行风险；wheel SHA 与清单校验仍 fail-closed；未发现 swallowed error / 资源泄漏 / 越界 / Breaking 配置键变更。除 f001 与上述测试层提示外未命中。
    - 范围外观察（不在本 task diff 改动面，不进表）：`AGENTS.md:3`/`:8` 仍写 2.1.0（项目根说明，非交付 diff）；`docs/specs/v2_runtime_validation.md:17`/`:71`/`:136` 为 t001 历史验收快照，保留 2.1.0 合理。
- 总体判断：实现层 2.1.0→2.2.1 升级全链路一致，vendor 注入 / SHA 清单 / ABI 门禁可靠且 fail-closed，4 条 AC 打勾均有真实实现与门禁证据支撑；仅 1 条 minor 文档同步项，无未解决 critical / important。PASS。
- 系统性 follow-up：无（f001 为 minor 文档同步，建议本 task 内修，无需新 tid）。

### AC 复验方式

- AC-001：TICK-VALID，re_verified。独立脚本核对 pyproject / uv.lock / requirements / vendor / x11 全为 2.2.1，vendor `PINNED_WHEEL_SHA256` 与 uv.lock selkies wheel hash 逐字一致，SHA 清单 2018 行含 2.2.1 wheel 特征且 verify_manifest 真实逐文件校验；镜像内 `version("selkies")==2.2.1` 依实施侧 `verify_image_packages.py` 证据。
- AC-002：TICK-VALID，re_verified。`x11_keymap.py:123-126` 版本门禁仍 fail-closed 且 `SUPPORTED_SELKIES_VERSION` 与 lock 一致，`_verify_selkies_keyboard_abi`（:88-115）4 方法签名 / `_BIND_SETTLE_S` / 6 实例属性 AST 校验完整保留；x11 键盘映射 E2E 通过依 `.scratch/evidence_t043b/` 门禁与真实 2.2.1 镜像内 `_verify_selkies_keyboard_abi` 实跑证据。
- AC-003：TICK-VALID，trust_prior。本轮约束不跑 Docker E2E，无法独立复跑无头全量；实现层独立确认本 task diff 无任何 `src/frontend` 适配层 / 信令代码改动、s012 spike 证明 HELLO / client_tab_id / resume_key 与私有 ABI 逐字不变，会话与 Stream E2E 无头通过依赖 `.scratch/evidence_t043b/` 门禁证据（5 suite 全绿，e2e 仅 1 项已如实登记的 t032/t033 负载类 UI 偶发，全文件定向重跑 3 passed）。
- AC-004：TICK-VALID，re_verified。`verify_frontend_dist.py`（本 task 未改，base 即通用 MODULE_TAG 正则）真实校验 adapter tag 恰一个、经典 IIFE 形态、adapter 须在首个 module 之前；vendor 注入改为与之一致的「首个 module tag」正则，独立构造 2.2.1 index.html 样本实跑确认 adapter 早于全部 module（171 < 216/328）；`--check-freshness` 通过依 `npm run build` 门禁证据。

## 第 2 轮复核（scope 重绑定与根因修复）

- scope 重绑定：交付内容因根因修复变化，被审 diff 指纹由 `4b9e2a7f46ceee2f` 重绑为 `f57a06cc51579761`（已重跑 `render_review_prompts.py`）。本轮复核 `git diff --cached 2e9558147b6c8ce0a6357115e23c003593f37327` 下 `useBrowserSession.ts` 与 `BrowserSessionView.test.tsx` 的增量；按约束不跑 Docker E2E / 完整门禁，修复后门禁以 `.scratch/evidence_t043c/` 实际结果为准。
- f001 已修：`docs/blueprint/architecture.md:5`、`:76` 与 `docs/blueprint/stream_runtime.md:5` 的现行概述均改为 2.2.1，历史 t001/t019 语境保留 2.1.0；与 progress.md 处置表「已修」一致，该 finding 闭环。
- 根因修复经复核，诊断态守卫语义正确：`useBrowserSession.ts:38-46` 的 `DIAGNOSTIC_STAGES` 恰为 7 个诊断/终止态（runtime_not_ready / signaling_failed / web_locks_unavailable / ice_failed / media_no_frames / error / stopping），与 `SessionStage` 全集中的 live/瞬态（checking_runtime / connecting_signaling / media_waiting / connected / reconnecting）无交集；`:275-282` 以 `stageRef.current`（`:119-124` 随 `stage` 同步）为条件，仅在上述诊断态下对 `CBROWSER_WS_CLOSE` / `CBROWSER_PC_STATE` / `CBROWSER_LIFECYCLE_STALE` 早退。`CBROWSER_WEB_LOCKS_UNAVAILABLE`（`:324-327`）不在忽略列表、保持原语义；手动 reconnect 置 `reconnecting`（`:153`）不在列表，恢复逻辑不受影响。改动仅条件早退，未改 `handleInitialSignalingClose`、`reconnect` 或任何定时器阈值。
- live session 不受影响：`AC-007: CBROWSER_WS_CLOSE on a live connection triggers a real rebuild` 以 `initialStage: "connected"` 渲染，不在诊断列表，`wasConnectedRef` 为真仍走 `:333-352` 真实重建；定向实跑 `BrowserSessionView.test.tsx` 26 passed（含该用例与新增回归用例）。新增用例「诊断态下 deferred client WS close 不扰动 stage」断言 overlay / stage 标题 / reconnect / status 四元素仍在，未放宽既有断言，未加长任何 `waitFor` 超时。
- 4 条 AC 的 TICK-VALID 结论继续有效：AC-001/002/004 的实现面与门禁证据不因本轮增量改变，AC-003 依「本 task 无前端适配层 / 信令代码改动」与修复后完整门禁证据仍成立；TICK-VOID 仍为 0，`coverage = 3 / 4` 不变。
- 文档与代码一致：progress.md 处置表 4 行齐全、错误归因已更正（t032 遗留仅 t019 首帧超时与 Supervisor SIGKILL，该用例 t033/t034 完整门禁均 PASS），「负载下时序回归根因」章节的失败链、7 个诊断态、忽略的 3 类事件与代码逐项吻合；`compare.py` 的 PROTOCOL 已改查 `HELLO ` 模板。
- 本轮无新 finding，总体结论保持 PASS。

coverage = 3 / 4

verdict: PASS
