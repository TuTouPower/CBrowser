---
tid: "t073"
slug: "frontend_design_system_env_and_session_ui"
title: "设计系统与工作台/环境管理重构（绿色状态、防重叠搜索、图标按钮与宽编辑弹窗）"
status: "done"
branch: "t073_frontend_design_system_env_and_session_ui"
worktree: ""
review_level: "single"
review_limit: "5"
verify_limit: "5"
diff_anchor: "04ff5c5af5439d1182642798be887abc8447ec0d"
depends_on: ""
conflicts_with: ""
note: "聚合 p103、p107、p108、p109 及 p105（容器尺寸与环境新建/编辑宽弹窗）；纯前端与 DESIGN.md，解锁下游 t074"
---

# Task 进展

front matter 只经 `task.py` 修改；reviewer 只写对应 `review_*.md`。

## 实施笔记

执行期记录关键步骤、决策、验证、阻塞和用户批准的新轮次上限。

创建期不预测实施步骤。只记有追溯价值的内容；无事项时写“无”。

- Step 1：`DESIGN.md` 新增成对 `light/dark-success`、`light/dark-success-soft`，`status-badge-running/transition/error` 的 `textColor` 改指彩色语义文字并加语义描边，`Contrast` 表补 success 对各类 surface 的 text / graphic 校验行，`Container sizes` 增 `dialog-sm/md/lg/xl`；`npm run design:tokens` 重生成 `design_tokens.css`（含 5 件品牌资产），三条设计门禁全绿。
- Step 2：`shared/ui` 原语重铸——`SearchField` 改 Flex 组合（外层容器承载边框与 `focus-within`，内部图标槽 + 无边框 input），`StatusBadge` 四态彩色语义，`IconButton` 增 `danger` / `warning`，`Dialog` 增 `size` 与 header 固定 / body 内部滚动。`ProxyFormDialog` 移除与新 Dialog 冲突的 `contentClassName`。
- Step 3：`i18n.tsx` 增 `sessHeaderEnv*` / `sessHeaderTransport*` 带主语键（保留 `sessTransport` / `transportState*` 供详情面板左列），`SessionHeader` 删两处 `sr-only`，`EnvironmentSwitcher` running 圆点改 `bg-success`。
- Step 4：`EnvironmentListPage` 运行计数改带标签 `runningProfiles` + 绿点、edit 动作改唤 `ProfileEditDialog`、新增 details 动作跳配置页；`EnvironmentTable` / `EnvironmentCard` 仅显式时区才显示，`EnvironmentRowActions` 重构为 1 文本主按钮 + 4 图标按钮（停止 warning / 删除 danger）；新增 `ProfileEditDialog`（`Dialog size="lg"` + `diffProfileValues`），`ProfileCreateDialog` 改 `size="lg"` 且幂等状态机原封不动，`ProfileDetailPage` 加编辑入口，`ProfileForm` Section 改多栏 grid，`ProxyListToolbar` 补宽度约束。
- Step 5：旧测试按 TDD 规则整体替换并写明理由（`SessionHeader.test.tsx` 旧 `sr-only`/裸词断言、`EnvironmentListPage.test.tsx` 旧 geoip 提示与弱 `.toContain("1")`），新增 `ui.test.tsx` / `design_tokens.test.mjs` / `EnvironmentSwitcher.test.tsx` / `ProfileCreateDialog.test.tsx` / `ProfileEditDialog.test.tsx` 与列表页新语义用例。
- 门禁：`npm test`（含 `test:types`）84 files / 659 tests 全绿；`design:lint` 0 error / 0 warning；`design:check` up to date；`npm run build` 成功；全量 `scripts/run_gates.sh` 通过（contract 257 / unit 2199 / integration 187 / frontend_test 659 / frontend_build）。E2E 必需模式收集期实测失败并列 13 项缺项，按项目口径记 NOT_RUN（见收尾报告）。
- Round 2：reviewer 两条 minor 修复后重渲染 prompt 并复审，指纹 `b547703abe202511`，verdict PASS。

## Review 处置

### Round 1 (2026-11-16T10:48:00+08:00)

|finding_id|severity|status|rationale|fix_ref|
|---|---|---|---|---|
|t073_gen_f001|minor|已修|`handleOpenChange` 改为无条件清 `saveError`，借 Radix 关闭必经的 `onOpenChange(false)` 清除常驻错误状态，ESC 回归断言真实触达|`ProfileEditDialog.tsx:26` / `ProfileEditDialog.test.tsx`|
|t073_gen_f002|minor|已修|移除 `SearchField` 外层基础类 `w-full`、给 `ProxyListToolbar` 补 `containerClassName`，新增 `not.toContain("w-full")` 断言|`Input.tsx:37` / `ProxyListToolbar.tsx:66` / `ui.test.tsx`|

### Round 2 (2026-11-16T11:00:00+08:00)

Round 2 零 finding；f001 / f002 经 diff 与门禁复核已消除，verdict PASS。

## 收尾报告

### 验收与验证

- task：[`task.md`](task.md)
- 结果：全部满足
- 测试：`npm test --prefix src/frontend`（含 `test:types`）84 files / 659 tests 全绿；`npm run design:lint` 0 error / 0 warning、97 源码 + 7 public 干净；`npm run design:check` up to date；`npm run build --prefix src/frontend` 成功；全量门禁 `scripts/run_gates.sh` 通过（contract 257 / unit 2199 / integration 187 / frontend_test 659 / frontend_build）。
- 黑盒：NOT_RUN。`CBROWSER_E2E_REQUIRED=1 pytest tests/e2e --collect-only` 实测在收集期失败并列出 13 项缺项（API / Caddy / Gateway / network-policy / Runtime / Stream / Supervisor 不可变 `sha256` 镜像 ID、Linux 引擎缓存、GeoIP 缓存、字体目录），属 t032 目标环境部署级活动，本会话未配置。按 `testing.md` `verification_notes` 的 NOT_RUN / USER_WAIVED 口径与 t073 spec 测试策略「若宿主 Playwright 环境就绪」条件，不执行真实 Docker / Chrome E2E，不记为已验；证据在 `.scratch/e2e_preflight_t073.log`。替代验收：`DESIGN.md` Contrast 表经 `design:tokens` 逐对计算 WCAG AA（text 4.5:1 / graphic 3.0:1）、`design:lint` / `design:check` 校验语义色与容器 token 产物、Vitest UI 原语与页面组件断言（Flex 不重叠、绿色语义类、带主语文案、带标签计数、图标化操作栏、宽弹窗差分更新）触达全部 6 条 AC。
- review：single 级，Round 1 PASS（2 minor）+ Round 2 PASS（0 finding）；`check_review_status.py` overall=PASS / review_scope=ok / ac_review=ok；`review_general.md` 指纹 `b547703abe202511`。
- AC 判定：见 `task.md` 行内打勾（AC-001..006 全 `- [x]`）

### 结果摘要

- 纯前端 + `DESIGN.md` 单一原子交付：success 语义色与宽弹窗尺寸梯度、shared/ui 四原语重铸、顶栏带主语状态、环境管理图标化操作栏与宽编辑弹窗；下游 t074 复用 `Dialog size="lg"` 与 success / danger 底座。
- 遗留：无（2 条 minor 已在 Round 2 前修复并复核）。

### 长期文档闭环

- specs_index: not_applicable: t073 为既有设计系统与前端界面重构，未引入新的需求级 spec；长期约束已落入 `DESIGN.md`（success 语义色、Contrast 校验行、dialog 尺寸梯度）与 `docs/blueprint/frontend.md` 第 4/6/7 节，故 `docs/specs_index.md` 不新增行。
- blueprint：`docs/blueprint/frontend.md` §4 / §6 / §7 已按 `task.md`「Finalization 时更新的 blueprint」更新。
- 正式 spike：无（未知契约清单为「无」）。
