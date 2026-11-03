# Task spec

## 背景

browser runtime 镜像当前不安装任何 CJK 字体，中文网页在容器内显示为缺字或 fallback。历史上提交 `0b4dc78` 曾主动 purge CJK 字体以降低中文字体指纹暴露，`docs/guides/browser_isolation_analysis.md` 也将「宿主机中文字体零泄露」列为容器隔离目标。用户现要求把中文字体改为 per-profile 可配置：部分 profile 无中文字体，部分 profile 可选不同中文字体包。

2026-11-03 已在本地真实引擎验证：字体放在 fontconfig 默认扫描路径之外，通过按 profile 设置 `FONTCONFIG_FILE`（include 系统配置并追加字体目录）可精确控制 Chrome 是否可见中文；`none` 时中文与私用区字符等宽，挂载字体目录后中文正常解析。该机制不需要宿主字体文件或额外 volume 挂载。

## 契约区

### 范围

- browser 镜像构建时从 Debian 官方包解出 `fonts-wqy-microhei` 与 `fonts-wqy-zenhei`，存放到 fontconfig 默认扫描路径之外的 `/opt/cbrowser-fonts/{wqy-microhei,wqy-zenhei}`。
- Profile 配置新增 `font_bundle`，取值 `none`、`wqy-microhei`、`wqy-zenhei`，默认 `none`；覆盖领域模型、创建/更新/响应 DTO、OpenAPI 契约、SQLite 列与 Alembic 迁移、repository 读写映射。
- Browser runner 按 `font_bundle` 为 Chrome 进程生成 fontconfig 配置：`none` 时无中文字体，其余档位只让对应字体目录参与扫描。
- 前端 Profile 创建与编辑界面提供三档选择，并回显当前值。
- 覆盖配置校验、迁移、字体开关和真实浏览器渲染的自动化测试。

### 非范围

- 不安装或分发 Windows 专有中文字体（SimSun、Microsoft YaHei 等）。
- 不挂载宿主操作系统字体目录，不在宿主数据目录预置字体文件。
- 不改变 Stream 容器的字体行为（画面渲染只发生在 Browser 容器）。
- 不为存量 Profile 自动切换为非 `none` 档位。
- 不实现字体子集、按语言自动选择或字体回退链定制。

### 验收标准

<!-- 规范（门禁必留，不得删除） -->

只写可观察、可独立验证的行为；每条使用稳定且不复用的 `AC-NNN`。需真实部署或人工环境验证时在编号前加 `[deploy]`。创建时均为未勾选（`- [ ]`）；实施验证通过后由实施 Agent 就地打勾（`- [x]`）；由 Review Agent 独立复核打勾真实性。技术选型不作为行为 AC。

<!-- /规范 -->

- [ ] AC-001：构建后的 Browser 镜像默认不提供中文字体：在未设置 profile 字体开关的容器内，`sans-serif` 的中文解析不命中任何中文字体，且 `fonts-wqy-microhei`、`fonts-wqy-zenhei` 的字体文件不在 fontconfig 默认扫描路径中。
- [ ] AC-002：Profile 创建、更新与读取支持 `font_bundle` 取值 `none`、`wqy-microhei`、`wqy-zenhei`；未提供时默认 `none`，存量 Profile 读取结果也为 `none`，其他取值被拒绝。
- [ ] AC-003：`font_bundle=none` 的 Profile 启动后，Chrome 渲染中文与私用区字符使用相同 fallback（文本度量一致），不出现中文字体解析。
- [ ] AC-004：`font_bundle=wqy-microhei` 的 Profile 启动后，Chrome 实际使用文泉驿微米黑渲染中文；`font_bundle=wqy-zenhei` 的 Profile 启动后，Chrome 实际使用文泉驿正黑渲染中文。
- [ ] AC-005：两个 Profile 同时运行不同 `font_bundle` 时，各自 Browser 容器的字体可见集合互不影响；修改某 Profile 的 `font_bundle` 会产生新配置版本，重建该 Profile 容器后新值生效且不影响其他 Profile。
- [ ] AC-006：前端 Profile 创建与编辑界面可查看并选择三档字体，保存后回显与 API 返回一致。

### 可测试性声明

<!-- 规范（门禁必留，不得删除） -->

逐条说明不可自动测试的 AC 及替代验证；全部可测则写“全部 AC 可自动测试”。

<!-- /规范 -->

全部 AC 可自动测试。AC-003 与 AC-004 通过真实 Browser 容器内 Chrome 的 canvas 文本度量与 CDP 实际字体族查询断言；AC-001 通过镜像构建后的 `fc-list`/`fc-match` 断言。

## 上下文区

- 来源：用户需求（2026-11-03）；历史提交 `0b4dc78` 与 `docs/guides/browser_isolation_analysis.md` 记录默认移除 CJK 字体的反指纹取舍（文档已标记 Superseded，容器隔离目标由 v2 继承）。

### 有意不测

- Windows 专有中文字体：不可自由分发，不纳入测试；若后续引入须单独评估授权。
- 字体抗锯齿、字形美观度与不同 DPI 的视觉差异：属于渲染质量而非行为契约，不设 AC。
- 非 Chrome 进程（Openbox、X11 工具）的字体渲染：不影响网页字体枚举，不测。

### 测试策略

- 单元测试：`font_bundle` 的默认值与非法值校验；repository 创建/更新/读取映射；runner 生成 fontconfig 配置的内容与 `FONTCONFIG_FILE` 设置（`none` 时清除且不引入字体目录）。
- 迁移测试：旧 SQLite 数据库升级后新增列默认 `none`，既有 Profile 行为不变。
- 集成/端到端：构建 Browser 镜像后，分别以三档启动 Profile，用真实 Chrome 的 canvas 中文/私用区文本度量与 CDP 平台字体族断言差异；同时运行两个不同档位 Profile 验证互不影响。
- 镜像黑盒：默认容器内 `fc-list` 不含文泉驿字体，字体仅存在于 `/opt/cbrowser-fonts/` 下的对应目录。

### 未知契约清单

<!-- 规范（门禁必留，不得删除） -->

未核实的外部契约标为 `UNVERIFIED-BLOCKING` 或 `UNVERIFIED-SPIKE`；核实后改写为结论和验证方式。无则写“无”。

<!-- /规范 -->

无。以下契约已于 2026-11-03 在本地真实引擎与镜像实测核实：

- `FONTCONFIG_FILE` 指向 include 系统配置并追加 `/opt` 字体目录时，Chrome 实际启用中文字体；未设置时中文与私用区字符等宽。
- `fonts-wqy-microhei` 与 `fonts-wqy-zenhei` 可从 Debian bookworm 源获取，包内字体分别为 5.2MB 与 16.8MB 的 `.ttc` 文件，无额外运行时依赖。
- `--read-only` 容器配合现有 tmpfs（`/tmp`、`/home/cbrowser`）可正常运行该 fontconfig 路径，字体缓存写入 `XDG_CACHE_HOME=/tmp/.cache`。

### 风险与回退

- 风险：字体指纹取舍变化——启用中文字体会让对应 Profile 暴露 Linux 中文字体特征，与现有 Windows 平台伪装不一致；字体包使镜像增大约 22MB；fontconfig 覆盖配置写错可能让系统字体整体不可用；端到端测试依赖 Docker 与镜像构建。
- 回退：`font_bundle` 默认 `none`，把 Profile 改回 `none` 并重启容器即恢复现状；runner 只在生成配置成功后设置 `FONTCONFIG_FILE`，失败时保持默认系统配置；数据库新增列可保留不破坏旧数据；镜像回退只需恢复 Dockerfile 构建段。

### 依赖与约束

- 依赖 Browser 镜像重建与现有配置版本/容器重启机制；字体包来源为 Debian bookworm 官方仓库。
- 字体文件不得进入 fontconfig 默认扫描路径，否则 `none` 档位失效。
- 不改变容器只读根文件系统、非 root 用户与现有挂载边界；不新增宿主目录依赖。
- 存量 Profile 默认 `none`，升级不得改变其现有字体可见集合。

### Finalization 时更新的 blueprint

- `docs/blueprint/browser_runtime.md`：字体 bundle 的分层方式、默认无 CJK 的取舍与 `FONTCONFIG_FILE` 开关边界。
- `docs/blueprint/domain.md`：`ProfileConfig.font_bundle` 字段语义、三档取值与默认值。
- `docs/blueprint/persistence.md`：`profiles` 表新增列与迁移约束。
- `docs/blueprint/decisions.md`：record「默认无中文字体 + per-profile 可选开源 CJK」的反指纹取舍与不做 Windows 专有字体的理由。
