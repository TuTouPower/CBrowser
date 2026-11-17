---
pid: "p117"
slug: "environment_delete_confirmation_modal_visibility"
status: "closed"
resolution: "transferred"
reason: "已核实根因、同类范围与验收契约，按用户授权聚合转交 t078（环境删除生命周期与列表操作统一）；转办不表示实现完成"
fix_ref: "t078"
---
# p117 环境单项与批量删除确认固定底栏难以发现，改为居中模态弹窗

- 来源：用户 2026-11-17 反馈：“删除环境的时候是弹窗，不要在最底下弹一个东西，根本看不到”。
- 现象：环境列表点击删除后，确认控件固定在视口底部，缺少遮罩与模态聚焦；用户难以发现。期望打开当前视口居中的删除确认弹窗，明确待删环境名称或批量数量、不可撤销提示、取消与红色确认按钮。
- 影响：环境管理单项删除（列表与卡片共用 `handleAction("delete")`）及批量删除。确认入口隐蔽且焦点不转移，键盘用户也难以获知当前等待确认；用户易误认为点击未生效。
- 根因：产品交互实现缺陷；不是共享 Dialog 的 CSS 或 Portal 故障。
    - `src/frontend/src/features/profiles/EnvironmentListPage.tsx:369` 的单项确认与 `:307` 的批量确认都直接渲染 `div`，样式为 `fixed bottom-2xl left-1/2 z-40 ...`，主动定位到底部。两者均无 `role="dialog"` / `role="alertdialog"`、`aria-modal`、遮罩、焦点转移或焦点圈定。
    - 已有 `src/frontend/src/shared/ui/Dialog.tsx` 采用 Radix Dialog Portal，内容 `fixed left-1/2 top-1/2 z-50`，具备居中模态能力，但删除确认未复用。`envDeleteConfirmTitle` 中英键已存在，当前删除确认未消费。
    - 同类扫描：单项与批量两条删除路径确认成立，均需修复；`BatchActionBar` 自身为底部操作栏，不应因本条改成弹窗。`MaintenanceTab.tsx:150` 维护页删除使用就地二次确认，`ProxyListPage.tsx:317` 使用内联 Banner，`GroupManagerDialog.tsx:282` 在已有分组模态框内就地确认，均不是本条已确认的“固定底部删除确认”根因，不扩大修复范围。
- 测试缺口：`EnvironmentListPage.test.tsx:714` 等测试直接按 `data-testid` 点击底栏确认，验证 API 次数、幂等键与失败选择保留；jsdom 不计算可视布局，未要求模态角色、中心位置、焦点与遮罩，因此底栏实现也能通过。
    - 应补组件交互：列表与卡片单项、批量删除均打开有可访问标题的模态框；打开时不调用删除；取消/Escape 关闭且不删除；显式确认后只删除目标并保持现有幂等约束；焦点进入弹窗并在取消后回到触发按钮。
    - 应补真实浏览器验证：长列表、滚动到任意位置、窄窗口时确认框始终落在视口可见区域中央，确认与取消按钮可见可操作；背景内容不可误操作。删除失败保留可见错误与重试/取消路径，避免仅靠难发现的底部提示；当前单项失败路径另有 `toast.show(error.message)`，实施时应结合弹窗状态统一复核。
- 线索：`.scratch/repro_delete_confirmation.test.tsx` 与 `.scratch/repro_delete_confirmation.vitest.config.mjs`。执行 `./src/frontend/node_modules/.bin/vitest run --config .scratch/repro_delete_confirmation.vitest.config.mjs --root .`：2 passed；直接渲染生产 `EnvironmentListPage`，点击单项/批量删除请求后，断言确认容器含 `fixed bottom-2xl`、无模态祖先，且删除 API stub 调用为零。未访问实际服务、未删除任何环境。证据为组件结构与交互复现，未将 jsdom 结果冒充真实浏览器可见性测量。
- 处理：t078；resolution=transferred；reason=已核实根因、同类范围与验收契约，按用户授权聚合转交 t078（环境删除生命周期与列表操作统一）；转办不表示实现完成
