---
pid: "p124"
slug: "profile_color_scheme_duplicate_labels_and_runtime_semantics"
status: "closed"
resolution: "transferred"
reason: "已核实根因、同类范围与验收契约，按用户授权聚合转交 t075（环境运行身份、字体资产与真实就绪契约统一）；转办不表示实现完成"
fix_ref: "t075"
---
# p124 环境配色方案重复跟随系统选项且语义与生效说明不清

- 来源：2026-11-17 用户截图与追问：配色方案为什么有四项、两个“跟随系统”，选择深色是否真正生效；`pending-record` 后台 `bug-to-pending` analysis-only。
- 现象：新建/编辑环境配色菜单包含“跟随系统 / 浅色 / 深色 / 跟随系统”，首尾文案相同，实际写入不同值。用户无法区分这两项，也无法从界面判断深色作用于网页偏好、浏览器界面还是管理系统主题。
- 影响：所有复用 `ProfileForm` 的环境创建与编辑入口，中英文均重复；相同显示文案会写入 `null` 或 `no-preference`，配置含义不透明。不能因为显示重复或当前测量结果相同就认定两者在所有环境下等价。
- 根因：产品展示与领域语义缺陷。`src/frontend/src/features/profiles/ProfileForm.tsx:316-321` 的 `colorSchemeOptions` 同时定义 `__none__` 与 `no-preference`，二者共用 `formColorNoPreference`；`src/frontend/src/i18n.tsx:375,893` 分别译为 `Follow system` / `跟随系统`。表单 `:825-833` 把 `__none__` 转为 Python/JSON 空值，另一个保持字符串 `no-preference`。后端领域模型明确允许这两类值，不是菜单重复显示同一个 value；`normalizeColorScheme` 也保留二者。
- 同类扫描：已确认新建与编辑共享该选项数组；前端 `no-preference` 与配色同名重复均集中在 `ProfileForm`。系统 UI 主题是独立 `system/light/dark` 配置（`docs/blueprint/frontend.md`、`docs/specs/ui_design_system.md`），不应与 Profile 网页配色偏好混用。其他 Select 菜单长列表/布局问题分别见 p120/p118，不在本条重复。
- 测试缺口：现有 API 集成与 repository 测试只验证 `color_scheme` 收发、持久化；`tests/fixtures/automation_probe/harness.py:266` 虽采集 `prefersDark`，其快照 `:897` 固定为 `light`，没有三态切换对照。ProfileForm 测试未断言配色菜单文案唯一，也未分辨 `null` 与 `no-preference` 的提交/回显。缺少完整生产 BrowserRunner 启动后的 light/dark/明确默认语义测试，以及真实系统主题变化下的跟随行为测试。
- 线索：`.scratch/profile_color_scheme_probe/options_repro.py`、`options_result.json`（直接从现行选项数组与中英词典抽取，断言两个同名项分别提交空值与 `no-preference`）；`probe.py`、`engine_evaluate_result.log`、`engine_result.log`（隔离目标引擎测试及首轮 load 等待失败记录）。
- 处理：t075；resolution=transferred；reason=已核实根因、同类范围与验收契约，按用户授权聚合转交 t075（环境运行身份、字体资产与真实就绪契约统一）；转办不表示实现完成
- 关联：p118 为表单布局和帮助提示；p123 为全站文案一致性。本条专门处理 Profile 配色选项语义与实际生效证据。

## 生效链路与实测边界

- 源码链路已核实：领域/API/DB 保留 `color_scheme` → `src/backend/cbrowser/runtime_agent/runner.py:630-646` 将 `cfg.color_scheme` 传给 `launch_persistent_context_async` → 当前 CloakBrowser SDK `browser.py:843-874` 只在值非空时加入 Playwright `context_kwargs["color_scheme"]`。Python 空值会省略该参数；字符串 `no-preference` 会显式传递。二者路径不同。
- 当前 Playwright 本地实现中，页面未单独覆盖时使用 `contextOptions.colorScheme ?? "light"`，随后通过 Chromium `Emulation.setEmulatedMedia` 传递 `prefers-color-scheme`。Python API 字符串 `"null"` 才被映射为 `no-override`；本项目领域模型没有该字符串，CloakBrowser 的空值参数又会被省略。不能仅凭界面写“跟随系统”就宣称已经跟随宿主 Mac 或沙箱桌面主题。
- 真实目标引擎验证通过：使用当前生产 browser 镜像 `ea67d5ed27b9`，镜像内 `cloakbrowser 0.6.4`、`Playwright 1.64.1`，固定 CloakBrowser 引擎 `146.0.7680.177.3`，独立 Xvfb 有头运行；现有引擎只读挂载，网络关闭，每种配置独立临时 Profile。共测 `null/light/dark/no-preference`，每种采样初始页与新增页。

|配置值|两页 dark 查询|两页 light 查询|测试页 CSS 背景|
|---|---|---|---|
|`null`|false|true|`rgb(200, 200, 200)`|
|`light`|false|true|`rgb(200, 200, 200)`|
|`dark`|true|false|`rgb(10, 10, 10)`|
|`no-preference`|false|true|`rgb(200, 200, 200)`|

- 测试页通过 `@media (prefers-color-scheme: dark)` 改变背景，证明深色网页偏好在隔离固定引擎中有效。网页需遵循该偏好才会变暗；这不代表强制所有网站变暗、Chrome 工具栏变暗或管理界面主题改变，也不能认定跟随宿主 Mac 主题。
- 本次直接调用同版 SDK，未走完整 BrowserRunner。生产 runner 的配置传参有源码证据，但容器调度、Profile 修改后重启/恢复、真实页面导航及系统主题改变仍需后续整链验证。首轮 `Page.set_content(wait_until=load)` 超时；改用在空白页直接设置测试 DOM 后读取 CSS/media 查询，四组成功，未把首轮失败记成通过。
- 临时容器 `cbrowser-color-scheme-probe` 已退出并由 `--rm` 清理；所有 Profile 与 Xvfb 仅存在于容器 `/tmp`，现有运行 Profile 与真实 DB 未读写。宿主证据仅写 `.scratch/`。

## 后续验收方向

1. 配色选项名称与语义唯一、易懂；明确 `null` 与 `no-preference` 的最终领域含义，再决定合并、移除或清晰区分，不能只删除重复文案却保留不透明状态。
2. 如继续提供“跟随系统”，必须说明所跟随的系统、验证真实媒体偏好随该系统主题变化；不能把省略 SDK 参数直接当作跟随。设计涉及旧配置含义变化时明确迁移方案，不把 `null` 与 `no-preference` 无证据视为等价。
3. 说明此字段控制远端网页 `prefers-color-scheme`，页面是否呈现深色由网站 CSS/主题逻辑决定；与管理界面主题及浏览器工具栏区分。
4. 补表单中英文文案唯一性、各选项提交与持久化回显测试；补生产 BrowserRunner 的真实引擎 light/dark 与默认/跟随语义测试，覆盖初始页、新增页、导航与重启。先用现有行为作红绿对照，禁止仅将预期改成当前输出。
