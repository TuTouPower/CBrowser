# Task spec

## 背景

`docs/plan_20261105_ui_redesign.md`（用户 2026-11-05 逐项确认，D10：技术底层默认升级到最新版本，含大版本）要求前端工具链先升到最新稳定版本，再在其上建设计系统与新页面。2026-11-05 于 main@3101540 核实现状（`src/frontend/package.json`）：Vite ^6、@vitejs/plugin-react ^4.3、Vitest ^4.1、TypeScript ~5.7、React/ReactDOM ^19.0、`react-router-dom` ^7.18.5、lucide-react ^0.468、jsdom ^28、@testing-library/jest-dom ^6.9、@types/node ^24、@tanstack/react-query ^5.105、openapi-typescript ^7.13；宿主构建 Node 24，`package.json` 无 `engines`。Selkies 适配层由 `vite.selkies.config.ts` 构建为经典 IIFE（`dist/selkies/selkies_adapter.js`），`postbuild` 经 `scripts/verify_frontend_dist.py` 校验产物形态、注入顺序与资源哈希。

## 契约区

### 范围

- 把 Vite、@vitejs/plugin-react、Vitest、TypeScript、React/ReactDOM、路由库、lucide-react、jsdom、@testing-library/\*、@types/node、@tanstack/react-query、openapi-typescript 升到当前最新稳定版本；路由库由 `react-router-dom` 换为 `react-router` 单包。
- 适配全部破坏性变更：路由 API、图标改名、Vitest 与 Vite 配置、TypeScript 新版类型检查。
- 宿主构建 Node 升到当前最新 LTS；`package.json` 声明 `engines`，前端门禁校验 Node 版本。
- 清理因升级而不再需要的变通配置（例如 `NODE_OPTIONS=--no-experimental-webstorage`，以实测为准）。
- 目标版本与例外原因写入 `docs/blueprint/decisions.md`。

### 非范围

- Tailwind CSS 4 迁移与设计系统（t036）。
- 页面结构、视觉与交互变化。
- Selkies 版本与 Stream 镜像（t034）。

### 验收标准

<!-- 规范（门禁必留，不得删除） -->

只写可观察、可独立验证的行为；每条使用稳定且不复用的 `AC-NNN`。需真实部署或人工环境验证时在编号前加 `[deploy]`。创建时均为未勾选（`- [ ]`）；实施验证通过后由实施 Agent 就地打勾（`- [x]`）；由 Review Agent 独立复核打勾真实性。技术选型不作为行为 AC。review 判 FAIL 且需修改交付内容时，实施 Agent 撤回全部打勾，修复并重验后重新打勾；reviewer 用 `TICK-VALID` / `TICK-VOID` 逐条判定。

<!-- /规范 -->

- [ ] AC-001：`scripts/run_gates.sh` 前端阶段（类型检查、Vitest、生产构建、postbuild 产物校验）在新工具链下全部通过；没有新增跳过的测试，因 API 消失而删除的测试在实施笔记逐条写明理由。
- [ ] AC-002：生产构建产出的 `dist/selkies/selkies_adapter.js` 仍为经典 IIFE（不含 ES module 语法），并注入在官方 module bundle 之前；`verify_frontend_dist.py` 通过。
- [ ] AC-003：`npm run generate:api` 在新工具链下成功生成类型；生成文件相对升级前只有生成器格式差异，没有类型语义变化（差异写入实施笔记），前端类型检查通过。
- [ ] AC-004：Node 版本不满足 `engines` 时，前端门禁失败并输出所需版本；满足时通过。
- [ ] AC-005：`CBROWSER_RUN_E2E=1 scripts/run_gates.sh` 中的前端真实栈 E2E（鉴权、会话、应用并重启）在新构建产物上无头通过。

### 可测试性声明

<!-- 规范（门禁必留，不得删除） -->

逐条说明不可自动测试的 AC 及替代验证；全部可测则写“全部 AC 可自动测试”。

<!-- /规范 -->

全部 AC 可自动测试。

## 上下文区

- 来源：`docs/plan_20261105_ui_redesign.md` WP01 与第 7.1 节（2026-11-05 于 main@3101540 核实依赖现状，结论见背景）。

### 有意不测

- 无。

### 测试策略

- 以现有 Vitest、类型检查与生产构建作为回归基线；路由库换包后，路由测试必须走生产 `routes` 定义。
- 适配层产物用 `verify_frontend_dist.py` 与 `tests/e2e/test_frontend_adapter_build.py` 校验形态与注入顺序。
- 所有浏览器测试无头运行。

### 未知契约清单

<!-- 规范（门禁必留，不得删除） -->

未核实的外部契约标为 `UNVERIFIED-BLOCKING` 或 `UNVERIFIED-SPIKE`；核实后改写为结论和验证方式。无则写“无”。

<!-- /规范 -->

- TypeScript 最新大版本与 openapi-typescript 的兼容（后者 peer 声明 `typescript ^5.x` 且依赖 TS 编译器 API）：UNVERIFIED-SPIKE，实施时以实际生成与类型检查验证；不兼容时选用兼容的最高版本，并在 `decisions.md` 写明原因与复查条件。
- Vite 最新大版本（Rolldown）对 `vite.selkies.config.ts` 经典 IIFE 产物的支持：UNVERIFIED-SPIKE，构建后用 `verify_frontend_dist.py` 验证。
- 新版 jsdom 与 Node LTS 下是否仍需 `--no-experimental-webstorage`：UNVERIFIED-SPIKE，移除后跑全量 Vitest 验证。

### 风险与回退

- 风险：Rolldown 改变 IIFE 产物或注入顺序，导致会话页适配层失效；路由库大版本改变 loader/导航语义。
- 回退：还原 `package.json` 与 `package-lock.json` 到升级前版本并重新构建。

### 依赖与约束

- 无前置依赖。t036 依赖本 task。
- 所有浏览器测试无头运行。

### Finalization 时更新的 blueprint

- `docs/blueprint/decisions.md`：前端工具链目标版本与例外（若有）。
- `docs/blueprint/conventions.md`：前端技术栈版本与 Node 版本要求。
- `docs/blueprint/frontend.md`：构建链路与路由库描述。
- `docs/blueprint/testing.md`：Node 版本门禁。
