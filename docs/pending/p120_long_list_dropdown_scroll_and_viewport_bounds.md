---
pid: "p120"
slug: "long_list_dropdown_scroll_and_viewport_bounds"
status: "closed"
resolution: "transferred"
reason: "已核实根因、同类范围与验收契约，按用户授权聚合转交 t077（表单布局与长集合选择交互统一重构）；转办不表示实现完成"
fix_ref: "t077"
---
# p120 长列表下拉与浮层缺少滚动或视口约束，候选越界不可达

- 来源：2026-11-17 用户反馈新建环境选择大量代理无法滑动，并要求扫描所有环境/代理相关入口；pending-record → bug-to-pending（analysis-only）。
- 现象：共享 Select 候选增加时整体撑高，滚轮不能滚动内部候选；其他增长型浮层也存在缺少高度限制或未适配低视口的问题。
- 影响：新建/编辑环境代理及分组选择、环境列表分组/代理筛选、代理国家/城市筛选，以及代理使用环境浮层、批量移动分组、环境切换器和 Dialog 内时区候选。共享组件机制及各独立浮层机制分开记录，不能只修 ProfileForm 一个调用点。
- 根因：产品布局/滚动约束缺失，确认机制与范围如下。

|机制与源码|已确认结果|修复边界|
|---|---|---|
|`shared/ui/Select.tsx:90-105` Content 使用 popper + overflow-hidden，未消费 Radix 的 content available-height；Viewport 仅 p-sm|真实生产 Select 200 代理，视口高1005px，Content 高6418px、available-height=902.75px，但 max-height=none；Viewport clientHeight=scrollHeight=6416，scrollTop=0。真实滚轮后 scrollTop 仍0，末项 Proxy199 顶部6469.5px|约束实际可用高度并形成内部滚动；不能仅加 overflow-y-auto 而仍让容器无限撑高。Portal/碰撞避让本身不收缩内容|
|`ProxyUsedByPopover.tsx:30-65` 普通 ul；`shared/ui/Popover.tsx:24-34` 无高度/滚动限制|100 环境、1292x1005 视口，浮层 top44/bottom3113.875，高3069.875，末项 bottom3100.875|关联环境列表内部滚动，浮层留在视口，末项可达|
|`EnvironmentListPage.tsx:333-357` 移动分组 fixed bottom-2xl + flex-wrap，无 max-height/overflow|100 分组、1292x1005 视口，菜单 top=-329/bottom973，高1302，首部分组在屏幕上方；未点击迁移|移动候选可查找可滚动，不以无限展开按钮撑满屏幕|
|`EnvironmentSwitcher.tsx:176` 固定 max-h-panel=448px，未结合 Popover available-height|100 环境在常规高度已搜索/滚动；1000x400 时浮层 top80/bottom598，高518，仍超出视口|保留已有搜索，按实际剩余视口调整整体浮层与列表高度|
|`TimezoneCombobox.tsx` 候选 absolute、max-h-dropdown-list=256px、overflow-y-auto，非 Portal 且无上下翻转|真实 Dialog+时区组件、1000x400 视口，菜单 top295.945/bottom551.945，最近滚动祖先 bottom363，打开时被裁切|处理父级裁切与视口定位；父容器仍可滚动，不据此断言全部时区永久不可达|

## 同类扫描与排除

- 共享 Select 增长型数据消费方：ProfileForm 的代理/分组/字体（创建与编辑共用）、EnvironmentListToolbar 的代理/分组、ProxyListToolbar 的国家/城市；上述均直接传候选数组且没有独立高度兜底。Settings、ProxyFormDialog 也使用 Select，当前候选数量固定，纳入短列表回归，不宣称已发生数量溢出。
- GroupManagerDialog：100 组实测 Dialog 保持90vh且内部 scrollHeight>clientHeight，已有有效滚动；无需因本条重写。新建/编辑环境外层 Dialog 同样有高度限制与正文滚动，问题在内层候选/浮层。
- DropdownMenu 当前未发现业务消费方，不因共享组件存在而虚构实际受影响页面。
- 与 p118 的文本换行/控件宽度缺陷不同；本条是候选容器高度、滚动和定位。国家城市排序见 p115，规模验收总表见 p119。

## 测试缺口与期望

- 多数 Select/ProfileForm/ProxyListPage 测试只用少量 fixture，jsdom 不计算布局。Timezone 测试只检查 overflow-y-auto 类并 stub scrollIntoView；Dialog 测试只检查 max-height 类，导致弹层真正越界时仍通过。
- 后续真实浏览器覆盖200代理、100分组/国家城市候选、100关联环境，普通/低高度/窄视口及长名称；断言容器在可用视口、clientHeight受限且存在内部滚动范围、滚轮确实改变 scrollTop、首末项鼠标/键盘可达、选择提交正确、Escape/焦点回归与背景滚动隔离。
- 保留已有同值选择提交语义，不因更改滚动破坏 p070 已修的 onOptionSelect 判据；候选搜索的全局要求见 p119。
- 证据层级：Select 导入真实组件与生产构建 CSS；其他浮层 harness 导入真实组件与 globals.css，以 mock 数据隔离验证，并非真实部署完整E2E。`wheel_and_end.json` 中键盘 End 后状态不能证明末项键盘可达或不可达，本条仅将真实滚轮与几何结果作为已确认缺陷证据。
- 线索：`.scratch/select_scroll_probe/main.tsx`、`vite.config.mjs`、`before.json`、`wheel_and_end.json`；`.scratch/many_items_audit/main.tsx`、`report.md`。启动对应本地 Vite harness 后，以 ego-browser 检查页面；不操作真实服务。
- 处理：t077；resolution=transferred；reason=已核实根因、同类范围与验收契约，按用户授权聚合转交 t077（表单布局与长集合选择交互统一重构）；转办不表示实现完成
