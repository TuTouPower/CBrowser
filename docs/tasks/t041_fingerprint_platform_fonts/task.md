# Task spec

## 背景

`docs/plan_20261105_ui_redesign.md` 第 6.8 节（D6、D7、D8、D15，用户 2026-11-05 确认）：Profile 可选 windows 或 macos 指纹平台；平台专有字体由 agent 从官方渠道获取，只在运行时挂载，不进镜像、不入库；Profile 绑定不可变字体集，指纹跨时间稳定（D15）。2026-11-05 按审阅调整顺序：本 task 只交付后端与运行时，排在 t035 之后、所有 UI task 之前，界面由 t036（设置页）、t037（环境表单与列表）、t039（会话详情面板）一次建成。2026-11-05 于 main@3101540 核实现状：

- `runtime_agent/runner.py:506` 写死 `--fingerprint-platform=windows`；CloakBrowser 只支持 windows 与 macos。
- 字体：Browser 镜像有 `fonts-liberation`，另有按 Profile 可选的文泉驿 `font_bundle`。`runtime_agent/fontconfig.py` 生成的专属配置 `<include>` 了系统 `/etc/fonts/fonts.conf`，因此 `/usr/share/fonts` 下 apt 安装的全部字体（含 Linux 专属字体）对所有 Profile 可见。ADR 015 写明「不挂载宿主字体目录」，本 task 的决定将替代它。
- Supervisor 只挂载 `${CBROWSER_DATA_ROOT}`（各实例独立），容器内看不到其他宿主路径；`data/` 被 gitignore，task worktree 中默认不存在；仓库根目前没有 `.worktreeinclude`。
- 两种指纹平台都有原生 CJK 字体（微软雅黑、宋体；苹方、冬青黑体），文泉驿本身会成为 Linux 特征。
- 引擎按 D7 为 cloakbrowser 0.6.4 无 key 模式的 Chromium 146。

## 契约区

### 范围

- 正式 spike（`spikes.py new`），在实施前完成：
    - 从官方渠道获取字体：Mac 从本机 `/System/Library/Fonts`、`/System/Library/Fonts/Supplemental`、`/Library/Fonts` 与 `/System/Library/AssetsV2/` 下的苹方资源复制；Windows 从微软官方 Windows 11 企业评估版 ISO（暂存 `.scratch/`）中用 `/opt/homebrew/bin/7zz` 从 `sources/install.wim` 提取 `Windows/Fonts`。不用第三方字体站或镜像。
    - 在 146 内核下验证两种平台：`cloakbrowser info` 的字体计数；离线字体探测页（按字体名渲染测宽）；`navigator.platform`、UA、UA Client Hints 的一致性。
    - 确定每种平台可见的基础字体组合，以及 `font_bundle` 的去留。
    - 结论写入 `docs/findings/`。
- 字体集存储：
    - 宿主目录由 `CBROWSER_FONTS_DIR` 指定，各实例共享；以 `.worktreeinclude` 登记，使 task worktree 共享同一份字体。
    - 导入工具（宿主脚本）把字体导入为不可变、按内容寻址的字体集 `{platform}/{set_id}/`，附 `manifest.json`（来源、来源系统版本、每个文件的 sha256）；导入后不再修改。
    - 本 task 不提供删除字体集的功能。
- 字体集目录接口：`GET /api/v1/font-sets` 列出各字体集的平台、来源、版本、静态完整性（文件与 manifest 是否一致、检测字体清单的覆盖情况：Windows 8 个、Office 10 个、Mac 20 个）与 `used_by_count`；API 只读挂载字体目录。
- 运行配置字段：以增量迁移新增 `fingerprint_platform`（windows / macos，默认 windows）与 `font_set_id`。
    - `font_set_id` 必须引用已存在且平台一致的字体集。
    - 新建 Profile 默认使用该平台最新导入的字体集；没有导入任何字体集时为 null。
    - 两个字段都进入配置版本快照，修改时生成新版本。
- 运行时：
    - Runner 按绑定快照选择平台，删除写死的参数。
    - Supervisor 只把绑定的字体集目录只读挂载进 Browser 容器，挂载点位于 fontconfig 默认扫描路径之外。
    - 基础开源字体在镜像内放到默认扫描路径之外。
    - 生成的 `FONTCONFIG_FILE` 只显式声明允许的字体目录（基础字体与绑定字体集），不引入系统字体目录；Linux 专属字体对两种平台都不可见。
- 失败与告警：绑定的字体集缺失，或文件与 manifest 不一致时，启动失败封闭，原因 `font_set_unavailable`。`font_set_id` 为 null 时正常启动，runtime 状态报告「平台字体未配置」。
- 运行时完整性：Agent 用 Profile 的 fontconfig 检查检测字体清单，runtime 响应与 SSE 下发实际使用的 `font_set_id` 与缺失字体列表。
- 按 spike 结论处理 `font_bundle`：删除时以增量迁移删除字段，并一并删除镜像字体包、代码与文档。
- 新增 ADR 替代 ADR 015：平台字体只在运行时挂载、Profile 绑定不可变字体集，写明字体来源与分发边界。
- 字体不进入任何镜像与仓库；部署与发布脚本不复制字体目录。
- OpenAPI 与前端类型同步；前端只做使类型检查与构建通过的最小改动（界面由 t036、t037、t039 交付）。

### 非范围

- 设置页、环境表单、列表与会话详情面板的字体与平台界面（t036、t037、t039）。
- Linux 指纹平台。
- 升级 cloakbrowser 或改用需要 key 的内核（D7）。
- 字体集删除与字体文件的分发或打包。

### 验收标准

<!-- 规范（门禁必留，不得删除） -->

只写可观察、可独立验证的行为；每条使用稳定且不复用的 `AC-NNN`。需真实部署或人工环境验证时在编号前加 `[deploy]`。创建时均为未勾选（`- [ ]`）；实施验证通过后由实施 Agent 就地打勾（`- [x]`）；由 Review Agent 独立复核打勾真实性。技术选型不作为行为 AC。review 判 FAIL 且需修改交付内容时，实施 Agent 撤回全部打勾，修复并重验后重新打勾；reviewer 用 `TICK-VALID` / `TICK-VOID` 逐条判定。

<!-- /规范 -->

- [ ] AC-001：导入工具生成带 manifest（来源、来源系统版本、文件 sha256）的不可变字体集；相同内容重复导入得到相同 `set_id`，内容变化得到新 `set_id`，已有字体集不被修改。
- [ ] AC-002：`GET /api/v1/font-sets` 需要登录会话，列出各字体集的平台、来源、版本、静态完整性与 `used_by_count`；文件被篡改或缺失时完整性显示不一致。
- [ ] AC-003：`fingerprint_platform` 与 `font_set_id` 可经 Profile 创建与 PATCH 设置，引用不存在或平台不一致的字体集被拒绝；新建 Profile 默认使用该平台最新的字体集；修改任一字段都生成新配置版本；浏览器启动参数取自绑定快照，代码中不再写死平台。
- [ ] AC-004：两种平台启动后，`navigator.platform`、UA 与 UA Client Hints（platform、platformVersion）均与所选平台一致（真实引擎 E2E）。
- [ ] AC-005：离线字体探测页上，windows Profile 检出 Windows 检测字体清单而检不出 Mac 专有字体，macos Profile 反之；Liberation 等 Linux 专属字体在两种平台下都检不出；可见字体只来自基础字体与绑定的字体集（真实引擎 E2E）。
- [ ] AC-006：绑定的字体集缺失或与 manifest 不一致时，启动失败封闭并报告 `font_set_unavailable`；`font_set_id` 为 null 的 Profile 正常启动，runtime 状态报告平台字体未配置。
- [ ] AC-007：运行中 Profile 的 runtime 响应与 SSE 含实际使用的 `font_set_id` 与缺失的检测字体列表，与 Agent 用该 Profile fontconfig 的检查结果一致。
- [ ] AC-008：任一镜像层与 git 仓库中都没有平台字体文件（镜像层内容扫描与仓库扫描）；部署与发布脚本不复制字体目录；task worktree 经 `.worktreeinclude` 访问同一字体目录。
- [ ] AC-009：`font_bundle` 按 spike 结论处理：删除时字段、镜像字体包、代码与文档引用一并删除，扫描为空；保留时新 ADR 写明原因。

### 可测试性声明

<!-- 规范（门禁必留，不得删除） -->

逐条说明不可自动测试的 AC 及替代验证；全部可测则写“全部 AC 可自动测试”。

<!-- /规范 -->

全部 AC 可自动测试。

## 上下文区

- 来源：`docs/plan_20261105_ui_redesign.md` WP14、WP15 与第 6.8 节（2026-11-05 于 main@3101540 核实，结论见背景）；D15（Profile 绑定字体集）由用户 2026-11-05 决定；fontconfig 系统 include 泄漏、字体目录挂载路径与全局检测来源按 2026-11-05 外部审阅补全。plan 已核对本机 `/System/Library/Fonts` 与 `Supplemental` 分别有 83、290 个文件，Mac 检测字体清单中的字体齐全。

### 有意不测

- 第三方指纹检测网站的评分：结果不可复现且依赖外网；以离线字体探测页与 UA / Client Hints 一致性断言代替。

### 测试策略

- unit 覆盖 manifest 生成与内容寻址、fontconfig 生成（只声明允许目录）、字段校验与默认字体集选择、静态完整性检查。
- 真实引擎 E2E 用离线字体探测页验证字体可见性与 UA / Client Hints 一致性，并验证缺失字体集时失败封闭。
- 镜像层扫描：`docker save` 后列出各层文件，断言不含平台字体目录与文件名。
- 所有浏览器测试无头运行。

### 未知契约清单

<!-- 规范（门禁必留，不得删除） -->

未核实的外部契约标为 `UNVERIFIED-BLOCKING` 或 `UNVERIFIED-SPIKE`；核实后改写为结论和验证方式。无则写“无”。

<!-- /规范 -->

- 146 内核下 macos 指纹平台的一致性（UA、Client Hints、字体）：UNVERIFIED-SPIKE，正式 spike 实测；达不到一致时停止并报告用户。
- 每种平台应暴露的基础字体组合，以及 `font_bundle` 的去留：UNVERIFIED-SPIKE，正式 spike 实测。
- 微软官方评估版 ISO 的可获取性与 `install.wim` 字体提取：UNVERIFIED-SPIKE，实施时获取；不可获取时报告 BLOCKED 并附证据。
- macOS 苹方等字体在 `/System/Library/AssetsV2/` 下的实际位置：UNVERIFIED-SPIKE，本机核实。

### 风险与回退

- 风险：字体隔离不完整，导致平台与字体特征不一致，形成可被检测的指纹矛盾；字体文件被误打进镜像或提交入库。
- 回退：回退本 task commit（含增量迁移的 downgrade）。

### 依赖与约束

- 依赖 t035（新 baseline 与运行配置版本判定）。
- 字体文件只写 `CBROWSER_FONTS_DIR` 与 `.scratch/`，不进入镜像与仓库。
- 所有浏览器测试无头运行。

### Finalization 时更新的 blueprint

- `docs/blueprint/browser_runtime.md`：指纹平台、字体集与 fontconfig 隔离。
- `docs/blueprint/supervisor.md`：字体集只读挂载。
- `docs/blueprint/security.md`：字体不进镜像与仓库。
- `docs/blueprint/persistence.md`：增量迁移。
- `docs/blueprint/decisions.md`：替代 ADR 015 的平台字体与字体集绑定 ADR。
- `docs/specs/browser_isolation.md`；新建 `docs/specs/fingerprint_platform.md`。
