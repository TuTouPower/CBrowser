# p061 会话页面详情侧边栏由顶部按钮控制开关且关闭时彻底收起

- 来源：用户提出
- 内容：会话页面移除侧边栏内部顶部的「详情」标题及「收起详情/展开详情」按钮行；点击顶部工具栏的详情按钮（PanelRight）控制右侧侧边栏展开与关闭；关闭时彻底收起侧边栏（不再占位保留空白侧边栏），再次点击重新展开。
- 处理：未开
- 时间：2026-11-10T19:40:00+08:00

## 用户原始诉求

会话页面中：

1. 去掉「收起详情」、「展开详情」，以及「详情」那一行；
2. 点击顶部详情按钮，展开右侧侧边栏的详情，再点一下就是关闭；
3. 不要只是清除详情里面的内容却还留着这个空白侧边栏。

## 当前现状与根因分析

1. `SessionDetailsPanel.tsx` 内部保留了标题行 `h2: {t("sessDetails")}` 与切换按钮 `Button: {open ? t("sessDetailsClose") : t("sessDetailsOpen")}`，造成内部有独立的折叠交互。
2. 当 `open === false` 时，`SessionDetailsPanel` 的 `<aside>` 外层容器仍然具有固定的 `w-details` 宽度与背景边框（`flex h-full w-details flex-col gap-md border-l border-outline bg-surface p-md`），仅内部各区块通过 `{open && (...)}` 条件隐藏，导致界面表现为「内容被清空但右侧依然留有一整列空白侧边栏」。
3. 顶部 `SessionHeader` 已有 `PanelRight` 详情按钮，但与面板内部按钮语义重复，且面板容器没有随 `open` 状态彻底隐藏或收起。

## 目标改造方案

1. **移除面板内冗余头部**：

    - 移除 `SessionDetailsPanel.tsx` 顶部的「详情」标题与「收起详情 / 展开详情」按钮行。
    - 面板作为纯粹的详情内容容器（或保持其语义化的 `<aside>`）。

2. **侧边栏容器随开关状态彻底折叠/隐藏**：

    - 当 `detailsOpen` 为 `false` 时，右侧侧边栏不占位（例如条件渲染 `detailsOpen ? <SessionDetailsPanel ... /> : null` 或外层 `hidden`），彻底关闭侧边栏，释放画面空间。
    - 当 `detailsOpen` 为 `true` 时，展示完整侧边栏和详情内容。

3. **单一控制入口**：

    - 顶部工具栏中的 `PanelRight` 按钮作为详情侧边栏唯一的展开/关闭切换开关。

4. **同步适配测试与国际化**：

    - 调整 `SessionDetailsPanel.test.tsx` 与 `SessionHeader.test.tsx` 中关于内部按钮及文本的断言。
    - 清理未使用的国际化文案或保留作为顶部按钮 label。
