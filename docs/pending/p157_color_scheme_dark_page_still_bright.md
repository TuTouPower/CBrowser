---
pid: "p157"
slug: "color_scheme_dark_page_still_bright"
status: "closed"
resolution: "transferred"
reason: "已核实原生外壳未消费环境配色，转交 task 统一原生主题与网页偏好并明确站点适配边界"
fix_ref: "t099"
---
# p157 Profile配置深色模式下浏览器外壳（地址栏/工具栏）未变黑且无适配网页保持纯白

- 来源：用户生产环境反馈（2026-11-21）「为什么这个页面那么亮呢？日趋华人这个环境.你可以上容器上看看」与「还有我设置的深色模式，为什么这个浏览器的地址栏、工具栏之类的还是白色呢？」。
- 现场证据：
    - Profile：`9ed642ad-0fea-43af-be8b-f8ebf9667982`（名称「日本华人」，用户打字错写为「日趋华人」），容器 `cbrowser-0086-browser` / `cbrowser-0086-stream`。
    - 配置状态：数据库与运行快照中 `color_scheme = "dark"`。
    - 容器内渲染与进程参数：
        - Chromium 启动参数无 `--force-dark-mode`，仅通过 Playwright 传递 `color_scheme="dark"`。
        - 容器 X11 截图（`.scratch/screenshot_taobao_x11.png`）：浏览器标签栏、地址栏、工具栏均为默认浅色/浅蓝（RGB: 211, 227, 253 与 255, 255, 255）。
        - `0084`（fae）打开 `https://who.1ms.dog/`（支持 dark media query）：网页内容区为深色 `(37, 38, 36)`，但浏览器工具栏依然是浅色。
        - `0086`（日本华人）打开 `https://reg.taobao.com/...`：浏览器工具栏是浅色，网页内容区也是纯白 `(255, 255, 255)`。

## 现象与影响

- 现象：用户在 Profile 配置中将配色方案选为「深色（dark）」：
    1. 浏览器的原生外壳（标签栏、地址栏、书签栏、工具栏、菜单）仍然是浅色/白色的；
    2. 打开传统无暗黑适配的中文网页（如淘宝注册页）时，网页也全屏呈现大面积刺眼纯白。
- 影响：
    - 浏览器原生界面未跟随深色模式：这是明确的工程缺陷，导致深色模式名不副实，即使在深色网页上，顶部也有一大块亮色工具栏。
    - 用户体验断层：用户期望选择「深色」后整个浏览环境均为深色，但遇到传统纯白页面时视觉刺眼。

## 根因分析（机制层）

1. **浏览器外壳未变黑（确定性缺陷：漏传 `--force-dark-mode`）**：
    - Chromium 的地址栏、工具栏、标签栏属于“Native Browser UI”，受操作系统 GTK 桌面主题或 Chromium 自身命令行参数控制。
    - CBrowser 在 `src/backend/cbrowser/runtime_agent/runner.py:662` 仅使用 Playwright 的 `launch_persistent_context_async(..., color_scheme=cfg.color_scheme)`。
    - Playwright 的 `color_scheme` 参数底层只调用 CDP `Emulation.setEmulatedMedia(features: [{name: 'prefers-color-scheme', value: 'dark'}])`，该接口**仅对网页内容区（WebContents）生效，完全不影响 Chromium 原生外壳**。
    - 在 `runner.py:601-636` 的 `extra_args` 中，当 `cfg.color_scheme == "dark"` 时，**完全没有往 Chromium 启动参数追加 `--force-dark-mode`**，导致浏览器外壳始终以默认浅色渲染。
2. **传统网页内容区保持纯白（W3C 规范与网页未适配）**：
    - `prefers-color-scheme: dark` 仅是媒体查询偏好。淘宝等传统站点样式表硬编码 `background-color: #fff`，无 dark media query，因此不会变黑。
    - 现行设计未开启 Chromium 强制全站网页反色（`--enable-features=WebContentsForceDark`）。
3. **Selkies 视频编码推流色彩空间加剧泛白感**：
    - Selkies 视频推流采用 `I420 (Limited Range)`，在客户端 `<video>` 播放大面积纯白背景时黑电平被轻微抬高，使浅灰细字对比度降低，进一步加重刺眼和泛白感。

## 同类位点扫描

- `src/backend/cbrowser/runtime_agent/runner.py`：`launch_persistent_context_async` 处仅传 `color_scheme`，未联动 `extra_args` 中的 `--force-dark-mode`。
- `src/frontend/src/features/profiles/ProfileForm.tsx:764`：UI 表单字段标签为「配色方案 / Color scheme」，未明确说明该字段是「指纹媒体查询（prefers-color-scheme）」还是「强制暗黑模式」，导致用户心智模型与底层行为脱节。
- `docs/blueprint/domain.md:27` 与 `docs/blueprint/browser_runtime.md:54`：明确将 `color_scheme` 仅定义为指纹运行配置，未定义强制反色能力。

## 测试缺口

- 现有测试（如 `tests/unit/test_runtime_agent_runner.py`、`tests/unit/test_profile_config.py`）仅验证了 `color_scheme` 从 Profile 字段到 Playwright 参数的传递与枚举合法性。
- 缺乏对 Chromium UI 启动参数（`--force-dark-mode`）以及窗口外壳渲染主题的断言。
- 缺乏对不同类型目标页面（支持媒体查询的页面 vs 纯静态无适配页面）的实际视觉/DOM 表现断言。

## 线索

- 现场复现与佐证目录：`.scratch/`
    - `.scratch/evidence.json`：汇总证据矩阵
    - `.scratch/screenshot_taobao_x11.png`：容器 X11 原生显存截图（证明 X11 内部淘宝页面为白底，文本为 `#111111`，工具栏为浅色）
    - `.scratch/taobao_cdp.png`：CDP 截屏（证明页面 DOM 元素无 dark media query）
    - `.scratch/screenshot_0084.png`：0084 容器在 `who.1ms.dog` 下表现为正常深色 `(37, 38, 36)`，工具栏为浅色
    - `.scratch/screenshot_0085.png`：0085 容器在 `about:blank` 下表现为深色 `(18, 18, 18)`，工具栏为浅色
- 用户原图见原始反馈，仓内复核使用上述截图。

## 建议方案与选项

1. **核心修复（浏览器外壳深色联动）**：
    - 在 `runner.py` 构建 `extra_args` 时，判断 `if cfg.color_scheme == "dark": extra_args.append("--force-dark-mode")`。
    - 确保当用户勾选深色时，Chromium 的地址栏、工具栏、标签栏、菜单原生进入深色主题。
2. **网页端澄清与可选特性**：
    - 前端表单澄清：“配色方案控制浏览器界面及网站暗黑模式偏好；未适配暗黑模式的传统纯白网站将保持原样”。
    - （可选）后续评估是否提供独立的“强制网页暗色（Force Dark Web Contents）”实验性开关。
3. **推流色彩优化**：
    - 评估 Selkies 在 X11 抓屏时使用 Full Range 编码或前端 `<video>` 渲染 CSS 对比度微调的可行性，降低 Limited Range 带来的黑电平抬高。

- 处理：t099；resolution=transferred；reason=已核实原生外壳未消费环境配色，转交 task 统一原生主题与网页偏好并明确站点适配边界
