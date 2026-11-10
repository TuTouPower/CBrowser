# p069 时区交互升级（搜索与滚动候选）及语言（中/英）与中文字体加载自动联动

- 来源：用户提出
- 内容：新建/编辑 Profile 时，“时区”与“语言”目前为两个空白文本输入框，既无候选项也无联动；用户要求时区支持打字自动过滤候选与无输入时鼠标滚动浏览全量时区，语言自动根据时区匹配（当前仅支持中文与英文），且语言与字体加载联动：选中文时必须加载中文字体，选英文时严禁加载中文字体以避免指纹泄漏。
- 处理：t053；resolution=transferred；reason=已核实范围并转交该 task
- 时间：2026-11-10T22:00:00+08:00

## 用户原始诉求与核心规则

用户指出当前环境创建界面中网络部分的「时区」与「语言」存在交互和逻辑缺陷：

1. **时区选择（Searchable & Scrollable Combobox）**：
    - 允许用户键盘打字输入，输入时下方实时弹出匹配的候选时区列表供快速选择；
    - 用户未打字时，支持展开下拉列表，鼠标可直接在列表中上下滑动/滚动浏览所有标准 IANA 时区（如各大洲主要时区）。
2. **语言自动与时区匹配联动（Locale Auto-binding）**：
    - 语言不需要用户手动猜测并填写 BCP 47 编码，而是根据选择的时区自动推导；
    - 系统目前仅支持两种语言模式：**中文**与**英文**；
    - 匹配规则：所选时区属于中文地区（如 `Asia/Shanghai`、`Asia/Chongqing`、`Asia/Urumqi`、`Asia/Harbin`、`Asia/Hong_Kong`、`Asia/Macau`、`Asia/Taipei` 等）时自动联动选中中文（`zh-CN`）；其余所有时区自动联动选中英文（`en-US`）。
3. **字体加载与语言深度联动（Font Loading & Fingerprint Isolation）**：
    - **选择中文**：沙箱容器与运行时必须加载中文字体（如 Windows 平台下的微软雅黑/宋体，macOS 下的苹方/冬青黑体等），确保中文网页正常渲染且字体指纹与中文环境一致；
    - **选择英文**：沙箱与运行时**不要加载任何中文字体**（仅加载西文核心字体集），严格防止 JavaScript 指纹探测脚本（如 Font List Fingerprinting、Canvas measureText）在纯英文环境中嗅探到 CJK 字体，造成严重的系统指纹特征异常与风控泄漏。

## 现状分析与架构根因

### 1. 前端表单缺少标准化时区选择组件

- `src/frontend/src/features/profiles/ProfileForm.tsx` 中直接渲染裸 `<Input>` 文本框接收 `values.timezone` 与 `values.locale`；
- 没有内置标准 IANA 时区列表（`Intl.supportedValuesOf('timeZone')` 或离线规范列表），无打字过滤（Combobox/Autocomplete），无滚动选择能力；
- 语言（`locale`）与时区完全割裂，依赖用户手工输入；输入错误代码会导致 Chromium 启动异常或指纹不合规。

### 2. 语言与时区之间缺少领域推导契约

- 目前系统将 `timezone` 与 `locale` 视为两个互相独立的标量字段存储在数据库及 API 模型中；
- 缺乏明确的时区→语言判定映射层（Timezone-to-Locale resolver）；当用户改变时区时，前端表单无任何联动事件触发。

### 3. 平台字体集与语言特征未解耦细分

- 当前 `src/backend/cbrowser/font_sets/manifest.py` 将字体集按操作系统（`windows` / `macos`）打包绑定（`font_set_id`）；
- Windows 检测字体集仅包含 8 个西文字体（Arial、Calibri、Georgia 等），无独立中文字体切分；
- 沙箱内 `runtime_agent/fontconfig.py` 在未绑定字体集时直接回退 `/opt/cbrowser-base-fonts`（内含 Linux 的 `fonts-wqy-zenhei` 文泉驿字体，会直接暴露 Linux 特征）；
- 字体白名单未根据 Profile 的 `locale` / `language` 动态裁剪或按需挂载中文字体文件。英文 Profile 若暴露了中文系统字体，会直接被高危反爬探针标记。

## 拟定改造方案与涉及位点

### 1. 前端组件与联动交互

- **新建/升级 Combobox 组件**：基于现有 UI 设计规范，实现支持键盘键入过滤与鼠标滚动浏览的时区选择组件，数据源采用标准 IANA 时区全集，标注常用时区（如中国、美国各时区、英国、欧洲、日韩等）。
- **时区-语言映射逻辑**：
    - 维护 `resolveLocaleFromTimezone(tz: string): "zh-CN" | "en-US"` 纯函数；
    - 在 `ProfileForm.tsx` 中，当时区值发生变化时，自动更新 `locale` 字段；
    - 界面语言输入项改为只读/联动展示或带中英单选切换器（中文 `zh-CN` / 英文 `en-US`）。

### 2. 后端与沙箱字体按语言分流加载

- **字体集划分与按需挂载**：
    - 完善平台字体集规范（特别是 Windows 与 macOS 资产），明确区分西文基准字体集与中文拓展字体集（如 Windows 下的 `msyh.ttc`、`simsun.ttc`，macOS 下的 `PingFang.ttc` 等）；
    - Supervisor 在为 Browser 沙箱生成挂载与 `profile-fonts.conf` 白名单时，根据 Profile 的 `locale`（中文 vs 英文）决定是否挂载与暴露中文字体目录；
    - 当 `locale` 为英文（`en-US`）时，`profile-fonts.conf` 仅包含纯西文字体，坚决不暴露任何中文字体。

### 3. 测试与验证要求

- **前端单元测试**：测试时区 Combobox 打字筛选、鼠标滚动选择，以及选择不同时区时 `locale` 自动联动（中文 vs 英文）的行为。
- **后端/运行时单测与集成测试**：
    - 断言英文环境生成的 fontconfig 绝不包含任何中文字体路径；
    - 断言中文环境生成的 fontconfig 正确加载指定平台的中文字体。
