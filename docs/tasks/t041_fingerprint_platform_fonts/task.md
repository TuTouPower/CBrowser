# Task spec

## 背景

`docs/plan_20261105_ui_redesign.md` 第 6.8 节（D6、D7、D8，用户 2026-11-05 确认）：Profile 可选 windows 或 macos 指纹平台；平台专有字体由 agent 从官方渠道获取，只在运行时挂载，不进镜像、不入库。2026-11-05 于 main@3101540 核实现状：

- `runtime_agent/runner.py:506` 写死 `--fingerprint-platform=windows`；CloakBrowser 只支持 windows 与 macos，没有 Linux 指纹平台。
- 字体：Browser 镜像只有 `fonts-liberation`，另有按 Profile 可选的文泉驿 `font_bundle`（`none` / `wqy-microhei` / `wqy-zenhei`，`runtime_agent/fontconfig.py` 生成专属 `FONTCONFIG_FILE`）。ADR 015 写明「不挂载宿主字体目录」「Windows 专有字体因授权风险不做」，本 task 的决定将替代它。
- 两种指纹平台都有原生 CJK 字体（微软雅黑、宋体；苹方、冬青黑体），文泉驿本身会成为 Linux 特征。
- 引擎为无 key 免费内核 Chromium 146（t034 锁定 cloakbrowser 0.6.4）；官方对 macOS 指纹平台的改进记录在 156 版本。

## 契约区

### 范围

- 正式 spike（`spikes.py new`），在实施前完成：
    - 获取字体放入 `data/fonts/windows/` 与 `data/fonts/mac/`（`data/` 已被忽略）。Mac 字体从本机复制 `/System/Library/Fonts`、`/System/Library/Fonts/Supplemental`、`/Library/Fonts` 及 `/System/Library/AssetsV2/` 下的苹方资源；Windows 字体从微软官方 Windows 11 企业评估版 ISO（暂存 `.scratch/`）中用 `/opt/homebrew/bin/7zz` 从 `sources/install.wim` 提取 `Windows/Fonts`。只用官方渠道，不用第三方字体站或镜像。
    - 在 146 内核下验证两种平台：`cloakbrowser info` 的字体计数；离线字体探测页（按字体名渲染测宽）；`navigator.platform`、UA、UA Client Hints 的一致性。
    - 确定每种平台可见的基础字体组合，以及 `font_bundle` 的去留。
    - 结论写入 `docs/findings/`。
- 字段：Profile 运行配置新增 `fingerprint_platform`（windows / macos，默认 windows），进入配置版本快照；Runner 按绑定快照选择平台，删除写死的参数。
- 字体分层：
    - CloakBrowser 文档列出的基础开源字体进入 Browser 镜像（`fonts-noto-color-emoji`、`fonts-freefont-ttf`、`fonts-unifont`、`fonts-ipafont-gothic`、`fonts-wqy-zenhei`、`fonts-tlwg-loma-otf`，以 spike 结论为准）。
    - Supervisor 把平台字体目录只读挂载进 Browser 容器，挂载点位于 fontconfig 默认扫描路径之外。
    - Runner 为每个 Profile 生成 `FONTCONFIG_FILE`，只暴露该平台的字体集与 spike 认定的基础字体；Liberation 等 Linux 专属字体对两种平台都不可见。
- 字体完整性：Agent 用 Profile 的 fontconfig 检查 CloakBrowser 检测字体清单（Windows 8 个、Office 10 个、Mac 20 个），结果经 runtime 状态下发；缺失时 UI 告警，不阻断启动。
- 界面：环境配置表单的指纹平台选择（附平台字体状态）；环境列表指纹列的平台图标；会话详情面板的平台与平台字体状态；设置页的 Windows、macOS 字体集检测结果。
- 按 spike 结论处理 `font_bundle`：删除时一并删除字段、镜像字体包与相关代码文档。
- 新增 ADR 替代 ADR 015：平台字体只在运行时挂载，写明字体来源与分发边界。
- 字体不进入任何镜像与仓库；部署与发布脚本不复制该目录。
- baseline schema、OpenAPI 与前端类型同步。

### 非范围

- Linux 指纹平台。
- 升级到需要 key 的新版内核。
- 字体文件的分发或打包。

### 验收标准

<!-- 规范（门禁必留，不得删除） -->

只写可观察、可独立验证的行为；每条使用稳定且不复用的 `AC-NNN`。需真实部署或人工环境验证时在编号前加 `[deploy]`。创建时均为未勾选（`- [ ]`）；实施验证通过后由实施 Agent 就地打勾（`- [x]`）；由 Review Agent 独立复核打勾真实性。技术选型不作为行为 AC。review 判 FAIL 且需修改交付内容时，实施 Agent 撤回全部打勾，修复并重验后重新打勾；reviewer 用 `TICK-VALID` / `TICK-VOID` 逐条判定。

<!-- /规范 -->

- [ ] AC-001：Profile 运行配置含 `fingerprint_platform`（windows / macos，默认 windows），修改时生成新配置版本；浏览器启动参数取自绑定快照，代码中不再写死平台。
- [ ] AC-002：两种平台启动后，`navigator.platform`、UA 与 UA Client Hints（platform、platformVersion）均与所选平台一致（真实引擎 E2E）。
- [ ] AC-003：平台字体只对对应平台可见：离线字体探测页在 windows Profile 中检出 Windows 检测字体清单而检不出 Mac 专有字体，macos Profile 反之；Liberation 等 Linux 专属字体在两种平台下都检不出（真实引擎 E2E）。
- [ ] AC-004：平台字体目录缺失或不完整时，Profile 仍可启动；runtime 状态列出缺失字体，环境配置表单、会话详情面板与设置页显示告警。
- [ ] AC-005：任一镜像层与 git 仓库中都没有平台字体文件（镜像层内容扫描与仓库扫描）；部署与发布脚本不复制字体目录。
- [ ] AC-006：`font_bundle` 按 spike 结论处理：删除时字段、镜像字体包、代码与文档引用一并删除，扫描为空；保留时新 ADR 写明原因。
- [ ] AC-007：设置页显示 Windows 与 macOS 字体集的检测结果，与 Agent 检查结果一致。

### 可测试性声明

<!-- 规范（门禁必留，不得删除） -->

逐条说明不可自动测试的 AC 及替代验证；全部可测则写“全部 AC 可自动测试”。

<!-- /规范 -->

全部 AC 可自动测试。

## 上下文区

- 来源：`docs/plan_20261105_ui_redesign.md` WP14、WP15 与第 6.8 节（2026-11-05 于 main@3101540 核实，结论见背景）。plan 已核对本机 `/System/Library/Fonts` 与 `Supplemental` 分别有 83、290 个文件，Mac 检测字体清单中的字体齐全。

### 有意不测

- 第三方指纹检测网站的评分：结果不可复现且依赖外网；以离线字体探测页与 UA / Client Hints 一致性断言代替。

### 测试策略

- unit 覆盖 fontconfig 生成（按平台的可见目录集合）与字体完整性检查。
- 真实引擎 E2E 用离线字体探测页验证字体可见性，并验证 UA / Client Hints 一致性。
- 镜像层扫描：`docker save` 后列出各层文件，断言不含平台字体目录与文件名。
- 所有浏览器测试无头运行。

### 未知契约清单

<!-- 规范（门禁必留，不得删除） -->

未核实的外部契约标为 `UNVERIFIED-BLOCKING` 或 `UNVERIFIED-SPIKE`；核实后改写为结论和验证方式。无则写“无”。

<!-- /规范 -->

- 146 内核下 macos 指纹平台的一致性（UA、Client Hints、字体）：UNVERIFIED-SPIKE，正式 spike 实测；达不到一致时停止并报告用户决定。
- 每种平台应暴露的基础字体组合，以及 `font_bundle` 的去留：UNVERIFIED-SPIKE，正式 spike 实测。
- 微软官方评估版 ISO 的可获取性与 `install.wim` 字体提取：UNVERIFIED-SPIKE，实施时获取；不可获取时报告 BLOCKED 并附证据。
- macOS 苹方等字体在 `/System/Library/AssetsV2/` 下的实际位置：UNVERIFIED-SPIKE，本机核实。

### 风险与回退

- 风险：字体隔离不完整，导致平台与字体特征不一致，形成可被检测的指纹矛盾；字体文件被误打进镜像或提交入库。
- 回退：回退本 task commit；平台字体目录可直接移除，Profile 仍可启动并显示告警。

### 依赖与约束

- 依赖 t039（会话详情面板）；经 t039 间接依赖 t035、t037。
- 与 t040、t042 同改 Runtime Agent、Supervisor 或设置页，用 `conflicts_with` 串行。
- 字体文件只写 `data/fonts/` 与 `.scratch/`，不进入镜像与仓库。
- 所有浏览器测试无头运行。

### Finalization 时更新的 blueprint

- `docs/blueprint/browser_runtime.md`：指纹平台与平台字体。
- `docs/blueprint/supervisor.md`：平台字体只读挂载。
- `docs/blueprint/security.md`：字体不进镜像。
- `docs/blueprint/decisions.md`：替代 ADR 015 的平台字体 ADR。
- `docs/specs/browser_isolation.md`；新建 `docs/specs/fingerprint_platform.md`。
