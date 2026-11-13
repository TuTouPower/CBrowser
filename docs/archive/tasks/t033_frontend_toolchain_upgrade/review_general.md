# Task review t033（reviewer_focus: 通用）

- task：`t033_frontend_toolchain_upgrade`
- spec：`docs/tasks/t033_frontend_toolchain_upgrade/task.md`
- diff_anchor：`483071a01e818ce94d6b51b70b8bc2f04b2a4f3f`
- target：`git -C '<repo>_t033' diff 483071a01e818ce94d6b51b70b8bc2f04b2a4f3f`
- round：1
- reviewed_at：2026-11-05T14:45:43+08:00

reviewed_scope: ec6c6978239a7bce

## Findings

### t033_gen_f001 - `check_node.mjs` semver 解析为 fail-open，且不完整

- 严重度：minor
- 锚点：行为缺陷（Node 门禁健壮性）；与 AC-004 相关，但当前 `engines.node` 解析正确，不构成 AC-004 违约
- 位置：`src/frontend/scripts/check_node.mjs:15-34`
- 问题：`min`/`exclusiveMax`/`inclusiveMax` 三个正则只识别 `>=`/`>`/`<`/`<=` + 纯数字边界，`ok` 初值为 `true`，三者都不匹配时无任何边界校验即打印 `frontend node ok` 并放行。若 `engines.node` 改成 `^26.0.0` / `~26` / `26.x` / `>=26 <27 || >=28` 等常见 semver 写法，门禁会在不报错的情况下完全失效（fail-open），任意 Node 版本都被接受。另 `parse` 用 `Number(part) || 0`（`:16`），把 `27.0.0-rc.1` 之类的 prerelease/build 元数据段吞成 `0`，边界比较失真。当前 `">=26.0.0 <27"` 解析正确：reviewer 实测 Node 24.21.0 → exit 1 并输出所需范围、Node 26.13.0 → exit 0，故 AC-004 成立。
- 建议：三个边界正则一个都没匹配到时显式 `console.error` + `process.exit(1)`（fail-closed），或改用完整 semver range 解析；`parse` 对非纯数字段保留/拒绝而非 `NaN → 0`。

### t033_gen_f002 - blueprint 把 Node 门禁接线与验证证据写错

- 严重度：minor
- 锚点：文档/配置一致性（AC-004 接线描述失实）；实现合理、文档过时，不计 FAIL
- 位置：`docs/blueprint/testing.md:16`、`docs/blueprint/decisions.md:246`、`docs/blueprint/testing.md:17`
- 问题：① `testing.md:16` 与 `decisions.md:246` 均称 `check_node.mjs` 在 `pretest`/`prebuild` 校验，但 `src/frontend/package.json` 的 `prebuild` 实为 `npm run vendor:selkies`，Node 检查挂在 `build` 链首（`"build": "npm run check:node && tsc -b && ..."`），只有 `pretest` 是 `check:node`；`progress.md:30` 自己也写「Node 检查移到 `build` 链首（`pretest` 保留）」，文档与自身实施笔记矛盾。② `testing.md:17` 称「Node 24.21 与 jsdom 30 实测 `npm test` 全套 216 项通过」，与证据矛盾：216 项来自 Node 26.13 门禁（`.scratch/evidence_t033b/logs/frontend_test.log`: 41 files / 216 tests），Node 24.21 的 SPIKE 为 `env -u NODE_OPTIONS npx vitest run` 冒烟 1 passed，且新门禁下 Node 24.21 跑 `npm test` 会被 `pretest` 拒绝（reviewer 实测 exit 1）。两处均系本次 diff 新增文字。
- 建议：按 `package.json` 实际接线把文档改为 `pretest` + `build` 链首；把 216 项证据归到 Node 26.13 门禁，Node 24.21 只写 SPIKE 冒烟结论。

### t033_gen_f003 - `testing.md` 门禁类别清单残留 `NODE_OPTIONS` 变通描述

- 严重度：minor
- 锚点：范围「清理因升级而不再需要的变通配置」的遗漏（同一 touched 文件内过期描述）
- 位置：`docs/blueprint/testing.md:124`
- 问题：「门禁类别清单」表格仍写「前端 Vitest（`NODE_OPTIONS=--no-experimental-webstorage`）」，与本 task 删除 `run_gates.sh` 两处 `NODE_OPTIONS`、同文件 `:17` 更新「不再需要」、`frontend.md:51` 改写「无需 `NODE_OPTIONS`」直接矛盾。该行是本次已触及文件 `testing.md` 内未一并清理的旧描述，会误导后续按旧变通配置前端门禁。
- 建议：删除该 parenthetical，或改为「Vitest 5（无需 `NODE_OPTIONS`）」。

## 第 2 轮复核（scope 重绑定）

- scope：交付内容变化，review scope 由 `136fa78d7206e1c8` 重绑定为 `ec6c6978239a7bce`（已重跑 `render_review_prompts.py` 确认）。本轮只复核 3 条 minor 修复与报告 scope 声明，不重跑 Docker E2E / 完整门禁。
- 复核 diff：`git diff --cached <diff_anchor> -- src/frontend/scripts/check_node.mjs docs/blueprint/testing.md docs/blueprint/decisions.md`，仅 3 个交付文件、无测试文件；无新增问题、无弱化断言、无就地改旧测试预期。
- f001 已修并复核：`check_node.mjs` 三边界正则全不匹配、或边界 `parse` 为 `null` 时均 `console.error` + `process.exit(1)`（fail-closed）；`parse` 以纯数字段校验拒绝 prerelease / 非数字段；`ok` 改由 `bounds.every` 计算，不再 fail-open。`^26.0.0` 等不支持语法走拒绝路径并输出拒绝原因，AC-004 双分支行为不变。
- f002 已修并复核：`testing.md:16` 与 ADR 020 改为「`pretest` 与 `build` 链首」，与 `package.json` / `progress.md:30` 一致；216 项证据归 Node 26.13 门禁，Node 24.21 只写 SPIKE 冒烟 1 passed。
- f003 已修并复核：`testing.md` 门禁类别清单删除 `NODE_OPTIONS=--no-experimental-webstorage`，改为「Node 26 LTS，无需 `NODE_OPTIONS` 变通」。
- 处置表复核：`progress.md` 三行均「已修」，fix_ref 分别指向 `src/frontend/scripts/check_node.mjs:15`、`docs/blueprint/testing.md:16`、`docs/blueprint/testing.md:124`，与改动文件一致。
- 复核命令：`pytest tests/e2e/test_frontend_build_wiring.py tests/unit/test_t028_run_gates_evidence.py -q` → 13 passed；`node src/frontend/scripts/check_node.mjs`（当前 PATH node 24.21.0）→ exit 1 并输出「要求 engines.node=">=26.0.0 \<27"」，与 AC-004 旧分支一致，如实记录。
- 3 条 minor 全部闭环，无新 finding、无未解决 critical / important；5 条 AC 的 TICK-VALID 结论继续有效（本轮 diff 未触及测试与构建产物语义），覆盖率维持 4 / 5，verdict 保持 PASS。

## 结论

- 前轮 finding 复核：Round 1，无前轮。
- 本轮新发现：3 条，全部 minor（1 条门禁健壮性、2 条文档一致性），无 critical / important。
- 未进表的提示：新增 `test_frontend_gate_checks_pinned_node_version` 为结构化接线断言（校验 `package.json` 字段与 checker 文件包含 `engines` / `process.exit(1)` / `process.versions.node`），不直接执行 `check_node.mjs` 的 semver 分支；行为层证据由 AC-004 双分支实证与 reviewer 独立复跑提供，属「覆盖可更广」观察，按规则不进 finding 表、不标 blocking。`check_node.mjs` 为 43 行自研 semver 子集（项目无 semver 依赖），符合简洁优先，弱点已在 f001 处置。完整门禁 2 项 E2E 失败（t019 首帧 3.795s、Supervisor `assert None == 30000`）经核为后端/性能遗留，t033 diff 未触及这两份测试，非工具链回归；按项目口径不据此判 TICK-VOID。无文件过大 / 圈复杂度 / 单 task 改动面等规模问题需升级 review level。7 视角（规格/AC、实现正确性、安全、契约·Breaking、性能·资源、架构·可维护、健壮性·可观测、测试可信·文档）均已扫过：安全面无外部输入、无注入/越权/secret；协议契约面仅 `react-router-dom`→`react-router` 换包（spec 范围要求，diff 中 25 个 import 纯改名，lockfile 零 `react-router-dom` 残留，ADR 020 / frontend.md / conventions.md 均记录），无公开签名/schema 变更；构建链 `prebuild=vendor` → `build=check:node && tsc -b && vite build && vite build --config vite.selkies.config.ts` → `postbuild=stamp && verify:selkies`，四阶段在证据中全绿。
- 总体判断：5 条 AC 全部 TICK-VALID，仅 3 条 minor（健壮性 + 文档一致性），无未解决 critical / important，PASS。
- 系统性 follow-up：无（3 条 minor 在本 task 处置表内消化即可；2 项 E2E 环境/性能遗留已由 t032 `final_report.md` 登记，不重复立项）。

### AC 复验方式

- AC-001：TICK-VALID，re_verified。`.scratch/evidence_t033b/suites.tsv` 与 `manifest.json` 显示 `frontend_test` / `frontend_build` 均 exit 0；`frontend_test.log` 41 files / 216 tests passed 且无 skip 行，`frontend_build.log` 含 `tsc -b`、vite v8.3.5 两次构建、`postbuild` 的 `verify_frontend_dist.py --check-freshness`；`git diff <anchor>` 无 `.skip` 新增、`git status` 无删测（无 D 行）；定向 `pytest tests/e2e/test_frontend_build_wiring.py tests/unit/test_t028_run_gates_evidence.py -q` → 13 passed。
- AC-002：TICK-VALID，re_verified。直接读 `dist/selkies/selkies_adapter.js` 以 `(function() {` 开头、`grep -nE '^(import|export)'` 零命中（经典 IIFE）；`dist/selkies/index.html` 中 adapter tag 位置 552 < module bundle 位置 590（注入在前）；`frontend_build.log` 含 `verify:selkies --check-freshness`；定向复跑 `test_adapter_must_load_before_module_bundle` / `test_module_adapter_fails` 通过。
- AC-003：TICK-VALID，re_verified。`package.json` diff 前后 `openapi-typescript` 同为 `^7.13.0`（生成器版本未变）；`git diff <anchor> --name-only` 不含 `src/shared/api/generated/cbrowser_v1.d.ts`（生成文件零差异，无类型语义变化）；`frontend_build.log` 的 `tsc -b` 与 `frontend_test.log` 的 `test:types` 前置门禁均通过（`npm test` exit 0）。
- AC-004：TICK-VALID，re_verified。直跑 `node src/frontend/scripts/check_node.mjs`（PATH node 24.21.0）→ exit 1、输出「要求 engines.node=">=26.0.0 \<27"」；`mise exec -- node src/frontend/scripts/check_node.mjs`（26.13.0）→ exit 0；`package.json` 的 `pretest=npm run check:node`、`build` 链首 `npm run check:node && `、`.mise.toml` node 26.13.0 接线属实；`test_frontend_build_wiring.py:61-69` 旧断言原样保留、`:72-91` 为纯新增测试（非就地改旧预期、无 mock 被测逻辑、无 skip）。
- AC-005：TICK-VALID，trust_prior。不重跑 Docker/Chrome E2E（约束）；依赖 `.scratch/evidence_t033b/junit/e2e.xml`（reviewer 解析 103 项 / 2 失败 / 2 skip）、`manifest.json`（`all_passed=false`，如实登记）、`suites.tsv`：AC-005 点名的前端真实栈用例（`test_frontend_app_auth_guard_e2e`、会话 3 项、双标签/SSE/输入静音/生命周期恢复、display apply、adapter 构建、vendor 接线、Selkies 资源清单、新增 Node 门禁接线用例）全部 PASS；2 失败为 `test_t019_switch_and_refresh_first_frame_within_2s_host_only`（3.795s > 2s，t032 已登记高负载偶发）与 `test_supervisor_sigkill_reconciliation_and_event_persistence`（`assert None == 30000`，Supervisor 异步恢复等待遗留，属后端且 t033 diff 未触及该测试），2 skip 为 t029 探针门控、不计 PASS。

coverage = 4 / 5

## reviewer 复跑记录

- `git -C <repo>_t033 rev-parse --show-toplevel` → `<repo>_t033`（落点校验通过）；`git -C ... log --oneline -3` → HEAD `483071a` 即 diff_anchor，故用 plain `git diff <anchor>`（不用 `...HEAD`，后者为空）。
- `git -C ... status --short --untracked-files=all` → 35 个文件 staged（A/M/MM），无未跟踪交付文件（无 `??`），新交付 `.mise.toml` / `check_node.mjs` 已进 index、出现在 `git diff <anchor>` 中。
- `git -C ... diff 483071a01e818ce94d6b51b70b8bc2f04b2a4f3f -- . ':!src/frontend/package-lock.json'` → 全量审查 36 个可读文件；`git -C ... diff --cached --stat` → 37 文件。
- `git -C ... grep -n react-router-dom -- ':!src/frontend/package-lock.json'` → 命中仅 archive/reviews/plan/progress 等历史与说明文本，源码与 lockfile 零残留（`grep -c` on lockfile = 0）；`git -C ... grep -n 'no-experimental-webstorage\|NODE_OPTIONS'` → 命中 archive/d001/plan/task 历史及 `testing.md:124`（f003）。
- `node src/frontend/scripts/check_node.mjs`（PATH node 24.21.0）→ exit 1，`前端门禁 Node 版本不满足：当前 24.21.0，要求 engines.node=">=26.0.0 <27"`；`mise exec -- node src/frontend/scripts/check_node.mjs`（26.13.0）→ exit 0，`frontend node ok: 26.13.0 satisfies ">=26.0.0 <27"`。
- `.scratch/gate_t033b/venv/bin/python -m pytest tests/e2e/test_frontend_build_wiring.py tests/unit/test_t028_run_gates_evidence.py -q` → `13 passed in 5.34s`。
- `.scratch/evidence_t033b/suites.tsv` / `manifest.json` → contract/unit/integration/frontend_test/frontend_build exit 0，e2e exit 1，`all_passed=false`；`logs/frontend_test.log` → `Test Files 41 passed (41)` / `Tests 216 passed (216)`；`logs/frontend_build.log` → `check:node` 通过、vite v8.3.5、adapter 10.64 kB、`verify_frontend_dist.py --check-freshness`。
- `python3` 解析 `junit/e2e.xml` → 103 testcase / 2 failure / 2 skipped，失败名与 t032 登记一致；前端真实栈用例逐条 PASS。
- `head -c 300 dist/selkies/selkies_adapter.js` → `(function() {`；`grep -nE '^(import|export)[ (]'` → 零命中；`python3` 计算 `index.html` adapter tag pos 552 < module pos 590。
- `git -C ... diff <anchor> --name-only | grep -i generated` → 生成类型文件零差异（未进 diff）。
- `python3 -c "from repo_task import monitoring; monitoring.review_scope_fingerprint(...)"` → `136fa78d7206e1c8`（与报告声明一致）。
- `grep -rn 'sigkill_reconciliation\|None == 30000' docs/` → 仅 t033 `progress.md` 自述与测试定义；t032 `final_report.md:15,50` 与 `progress.md:51` 登记同根因「post-startup 异步恢复 session，测试读早了」遗留，判定与前端工具链改动无关。
- 写报告后执行：`python3 .repo_template/scripts/md_format.py docs/tasks/t033_frontend_toolchain_upgrade/review_general.md`；`python3 .repo_template/scripts/check_review_status.py --task-dir docs/tasks/t033_frontend_toolchain_upgrade`。

verdict: PASS
