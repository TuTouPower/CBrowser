---
tid: "t033"
slug: "frontend_toolchain_upgrade"
title: "前端工具链升级到最新稳定版本"
status: "done"
branch: "t033_frontend_toolchain_upgrade"
worktree: ""
review_level: "single"
review_limit: "5"
verify_limit: "5"
diff_anchor: "483071a01e818ce94d6b51b70b8bc2f04b2a4f3f"
depends_on: ""
conflicts_with: ""
note: "来源 plan_20261105_ui_redesign WP01"
---

# Task 进展

front matter 只经 `task.py` 修改；reviewer 只写对应 `review_*.md`。

## 实施笔记

执行期记录关键步骤、决策、验证、阻塞和用户批准的新轮次上限。

创建期不预测实施步骤。只记有追溯价值的内容；无事项时写“无”。

- 2026-11-05：三项 UNVERIFIED-SPIKE 全部实测闭环，结论回填 `task.md` 未知契约清单：① Vite 8.3.5（Rolldown）以真实 `vite.selkies.config.ts` 构建仍产出经典 IIFE（`(function() {` 开头、行首零 `import`/`export`）；② jsdom 30.1.3 + Vitest 5.1.0 + Node 24.21 `env -u NODE_OPTIONS` 全套无 `--no-experimental-webstorage` 变通；③ TypeScript 7.0.2 与 `openapi-typescript@7.13.0` peer `typescript@^5.x` 实测 ERESOLVE 冲突，按契约选兼容最高 5.x = 5.9.3，例外与复查条件写入 `docs/blueprint/decisions.md` ADR 020。
- 依赖升级（`src/frontend/package.json` + `package-lock.json`）：Vite 8.3.5、@vitejs/plugin-react 6.2.1、Vitest 5.1.0、React/ReactDOM 19.3.1、`react-router` 8.5.1（替换 `react-router-dom`）、lucide-react 1.68.0、jsdom 30.1.3、@testing-library/jest-dom 7.0.1、@testing-library/react 16.3.3、@types/node 26.6.6、@types/react(-dom) 19.3.0、@tanstack/react-query 5.106.0；Tailwind 4 迁移归 t036，故 tailwindcss/postcss/autoprefixer 不在本 task 范围。
- 破坏性变更适配：25 个源文件 `react-router-dom` → `react-router`（实测 8.5.1 单包导出 BrowserRouter/Link/Routes/RouterProvider/createBrowserRouter 等全部 DOM API，无 API 改写）；`npx tsc -p tsconfig.test.json --noEmit` 零错误，216 项 Vitest 全绿，图标与路由 API 无改名/失效。
- 宿主 Node 固定：新增 `.mise.toml`（node 26.13.0）、`package.json` 的 `engines.node=">=26.0.0 <27"`、`src/frontend/scripts/check_node.mjs`（`pretest` 与 `build` 链首校验，不满足输出所需范围并失败）；`scripts/run_gates.sh` 两处 `NODE_OPTIONS=--no-experimental-webstorage` 已移除。
- AC-003：`npm run generate:api` 用 openapi-typescript 7.13.0 重新生成，`diff` 与升级前产物零行差异；类型检查通过。
- AC-002：手动跑完整构建链（vendor → `tsc -b` → `vite build` → `vite build --config vite.selkies.config.ts` → build stamp → `verify_frontend_dist.py --check-freshness`）全绿；`dist/selkies/selkies_adapter.js` 10.64 kB 经典 IIFE、行首零 ESM 标记；`dist/selkies/index.html` 中 adapter tag 位置 552 < module bundle 位置 590（注入顺序保持在前）；`package-lock.json` 零 `react-router-dom` 残留。
- 长期文档：`docs/blueprint/decisions.md` ADR 020（版本、例外、复查条件）、`conventions.md`（技术栈与 Node 26）、`frontend.md`（React 19.3/Vite 8/react-router 8/Vitest 5）、`testing.md`（Node 26 门禁、移除 NODE_OPTIONS 变通）。
- TDD 回归：首轮门禁暴露「`prebuild` 加 `check:node` 打破 `test_package_build_runs_vendor_and_verification` 旧断言」与「`run_gates.sh` 顶部 PATH 前置覆盖 `test_t028_run_gates_evidence.py` 的 stub npm」。按项目规则不就地改旧断言：`prebuild` 恢复 `npm run vendor:selkies`，Node 检查移到 `build` 链首（`pretest` 保留），新增 `test_frontend_gate_checks_pinned_node_version` 覆盖新语义；撤销 `run_gates.sh` 的 PATH 前置（Node 版本切换归 mise，门禁只由 `check_node.mjs` 断言）。两处定向复跑：`test_frontend_build_wiring.py` 9 passed、`test_t028_run_gates_evidence.py` 4 passed。
- AC-004 双分支实证：Node 24.21 下 `npm run build` exit 1 并输出「前端门禁 Node 版本不满足：当前 24.21.0，要求 >=26.0.0 \<27」；Node 26.13 下 exit 0，构建链与 `verify_frontend_dist.py --check-freshness` 全绿。
- AC-005：修正后的完整 required+evidence 门禁（`CBROWSER_RUN_E2E=1`，Node 26.13，证据 `.scratch/evidence_t033b/`）E2E 103 项中，AC-005 点名的前端真实栈用例（鉴权守卫、会话 3 项、双标签/SSE/输入静音/生命周期恢复、应用并重启、adapter 构建、vendor 接线、Selkies 资源清单、新增 Node 门禁接线用例）全部 PASS。2 项失败为 `test_t019_switch_and_refresh_first_frame_within_2s_host_only`（首帧 3.795s > 2s，t032 已登记的高负载偶发）与 `test_supervisor_sigkill_reconciliation_and_event_persistence`（`assert None == 30000`，t032 已登记的 Supervisor 异步恢复等待遗留），均与前端工具链改动无关；按精确修改原则不就地改旧断言、不超范围改后端测试，如实登记。

## Review 处置

每个结构化 finding 一行。`已修` 表示本 task 已修复；`遗留` 必须指向 `pNNN` 或 follow-up tid；`撤回` 必须写清理由。critical/important 未解决时不得 PASS。

### Round 2 (2026-11-05T14:20:00+08:00)

|finding_id|severity|status|rationale|fix_ref|
|---|---|---|---|---|
|t033_gen_f001|minor|已修|`check_node.mjs` 三边界正则不匹配或边界含非纯数字段时显式 fail-closed，`parse` 拒绝 prerelease/非数字段；Node 24.21 exit 1、Node 26.13 exit 0、`^26.0.0` 不支持语法 exit 1|src/frontend/scripts/check_node.mjs:15|
|t033_gen_f002|minor|已修|`testing.md` 与 ADR 020 改为「`pretest` 与 `build` 链首」；216 项证据归 Node 26.13 门禁，Node 24.21 只写 SPIKE 冒烟|docs/blueprint/testing.md:16|
|t033_gen_f003|minor|已修|`testing.md` 门禁类别清单删除 `NODE_OPTIONS` 变通描述，改为 Node 26 LTS 无需变通|docs/blueprint/testing.md:124|

Round 1 零 finding（review_general.md PASS、0 TICK-VOID、5 条 AC 全 TICK-VALID）；Round 2 为处置上述 3 条 minor 后的复核。

## 收尾报告

### 验收与验证

- task：[`task.md`](task.md)
- 结果：全部满足（AC-001~005 均在新工具链与新构建产物上取得证据；完整门禁 `all_passed=false` 的 2 项 E2E 失败为 t032 已登记遗留，不写成通过）
- 测试：完整 required+evidence 门禁 `CBROWSER_RUN_E2E=1 scripts/run_gates.sh`（Node 26.13，证据 `.scratch/evidence_t033b/`）：contract 223 项 0 失败、unit 998 项 0 失败、integration 160 项、frontend_test（216 Vitest + 类型检查）0 失败、frontend_build（含 postbuild `verify_frontend_dist.py --check-freshness`）0 失败、e2e 103 项 2 失败 2 skip；定向补验 `test_frontend_build_wiring.py` 9 passed、`test_t028_run_gates_evidence.py` 4 passed、`npx tsc -p tsconfig.test.json --noEmit` 零错误、`npm run generate:api` 产物零差异。
- 黑盒：`CBROWSER_RUN_E2E=1 scripts/run_gates.sh` 的 E2E 必需模式在新构建产物上以真实 Docker/Chrome 拓扑执行；AC-005 点名的前端真实栈 E2E（鉴权、会话、应用并重启）全部无头通过；2 项失败（t019 首帧 3.795s、Supervisor 端口恢复 None）与 2 项探针门控 skip 逐项如实登记，skip 不计 PASS。
- review：single 级独立 review（`review_general.md`）PASS。
- AC 判定：见 `task.md` 行内打勾

### 结果摘要

- 前端工具链升到当前最新稳定版本（Vite 8 / plugin-react 6 / Vitest 5 / React 19.3 / react-router 8 单包 / lucide 1.68 / jsdom 30 / jest-dom 7 / @types/node 26 / TanStack Query 5.106），TypeScript 因 openapi-typescript peer 例外固定 5.9.3（ADR 020 记录复查条件）。
- Node 固定 26 LTS：`.mise.toml` + `engines` + `check_node.mjs` 双分支门禁；移除 `NODE_OPTIONS` 变通。
- 遗留只写引用：完整门禁 2 项 E2E 失败见 t032 `final_report.md`「发布判定」与 `.scratch/evidence_t033b/`；均与本 task 改动无关，不复制正文。

### 长期文档闭环

- specs_index: not_applicable: 本 task 为前端工具链版本升级，不产生新的需求级行为契约；目标版本、TypeScript 例外与复查条件写入 `docs/blueprint/decisions.md` ADR 020，技术栈约定写入 `conventions.md`，构建链写入 `frontend.md`，Node 门禁写入 `testing.md`。
- 三项 UNVERIFIED-SPIKE 为一次性实验，证据留在 `.scratch/t033_spike/`，不建正式 sid；结论已回填 `task.md` 未知契约清单。
