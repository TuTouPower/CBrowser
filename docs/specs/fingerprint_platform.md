# 需求规范：指纹平台与平台字体集 (fingerprint_platform)

## 1. 业务目标与适用范围

本 spec 累积 t041 交付的指纹平台选择与平台专有字体集隔离契约。Profile 可选 `windows` / `macos` 指纹平台并绑定同平台的不可变字体集；平台专有字体只从官方渠道取得、只在运行时只读挂载，不进镜像与仓库。基础开源字体进入 Browser 镜像满足 CloakBrowser 安装要求，但不进入指纹 Profile 的 fontconfig 白名单；Profile 可见集合只含绑定的平台字体集，避免 Linux 专属字体形成平台指纹矛盾（用户 2026-11-06 裁决）。关联 task：`docs/tasks/t041_fingerprint_platform_fonts/task.md`（AC-001~009）。证据：正式 spike `docs/spikes/s014_fingerprint_platform_fonts/report.md`、findings `d032`（UA-CH architecture 裁决）与 `d033`（字体集隔离实测）、`docs/plan_20261105_ui_redesign.md` 6.8 节。

## 2. 行为契约

### 2.1 运行配置字段

- `fingerprint_platform`：取值 `windows`（默认）/ `macos`；CloakBrowser 只支持这两种，无 Linux 指纹平台。
- `font_set_id`：引用同平台、按内容寻址的不可变字体集，可为 null（未配置平台字体）。
- 两字段经增量迁移 `0002_fingerprint_platform.py` 加入，属运行配置；修改任一都生成新 `ProfileConfigVersion`，重建容器后生效，不影响其他 Profile。
- Runner 按绑定配置版本快照选择平台，删除写死的 `--fingerprint-platform=windows` 启动参数。
- `font_set_id` 必须引用已存在且平台一致的字体集；引用不存在或平台不一致被拒绝。新建 Profile 默认使用该平台最新导入的字体集，无可用集时为 null。

### 2.2 字体分层与 fontconfig 白名单

- 基础开源字体六项（`fonts-noto-color-emoji` / `fonts-freefont-ttf` / `fonts-unifont` / `fonts-ipafont-gothic` / `fonts-wqy-zenhei` / `fonts-tlwg-loma-otf`）在 Browser 镜像 `/opt/cbrowser-base-fonts`，位于 fontconfig 默认扫描路径之外，且**不进入**指纹 Profile 白名单（仅满足 CloakBrowser 安装要求）。
- 平台字体集在宿主 `CBROWSER_FONTS_DIR/{platform}/{set_id}/`，内容寻址 `set_id` + `manifest.json`（来源、来源系统版本、逐文件 sha256），导入后不可修改；经 `.worktreeinclude` 供各 worktree 共享同一份。
- Supervisor 只把 Profile 绑定的字体集只读挂载到 Browser 容器 `/run/cbrowser/fonts/{platform}/{set_id}`（默认扫描路径之外），不挂整个字体根目录，不挂给 Stream 容器。
- Runner 生成 `FONTCONFIG_FILE`：绑定平台字体集时只以 `<dir>` 白名单声明该集目录，不 include `/etc/fonts/fonts.conf`，也不声明基础字体目录；绑定集场景下 Liberation / Nimbus / 文泉驿 / Unifont / FreeFont / IPAGothic / Loma 等 Linux 专属字体对两平台都不可见（真实 146 引擎 E2E 与 `fc-list` 实测命中 0，见 `d033`）。`font_set_id` 为 null（平台字体未配置）时**回退基础开源字体可见**，保证浏览器有字体、页面可用（AC-006 正常启动），runtime 状态报告「平台字体未配置」并在 `missing_fonts` 标明当前暴露 Linux 基础字体。
- `font_bundle`（文泉驿按 Profile 三态）已删除：字段、镜像字体包、代码、文档与测试引用一并清理（AC-009）。

### 2.3 平台一致性

- 两种平台启动后，`navigator.platform`、UA 与 UA Client Hints（`platform` / `platformVersion`）均与所选平台一致（AC-004，真实引擎 E2E）。
- `architecture=arm` 与 windows UA `x64` 的差异：引擎层无 flag、CDP 页面级覆盖漏 ServiceWorker，按用户裁决不做半套覆盖；见 `d032` 与 `p045`，AC-004 文本不改。

### 2.4 失败封闭与运行时完整性

- 绑定字体集缺失，或文件与 manifest 不一致时，启动失败封闭并报告 `font_set_unavailable`；`font_set_id` 为 null 时回退基础开源字体可见、正常启动，runtime 状态报告「平台字体未配置」并在 `missing_fonts` 标明当前暴露 Linux 基础字体（AC-006）。
- Agent 用 Profile 的 fontconfig 复核检测字体清单；runtime 响应与 SSE 下发实际使用的 `font_set_id` 与 `missing_fonts`，与复核结果一致（AC-007）。
- `GET /api/v1/font-sets` 需登录会话，列出各字体集的平台、来源、版本、静态完整性（Windows 8 个 / Office 10 个 / Mac 20 个检测字体覆盖情况）与 `used_by_count`；文件被篡改或缺失时完整性显示不一致（AC-002）。导入工具生成带 manifest 的不可变字体集，相同内容重复导入得到同一 `set_id`（AC-001）。

### 2.6 字体目录作为独立部署输入（t051）

- 字体目录是独立部署输入，不再经 `${CBROWSER_DATA_ROOT}/fonts` 派生：compose 以 `${CBROWSER_FONTS_DIR}:/fonts:ro` 只读挂载（API 与 Supervisor 容器内 `CBROWSER_FONTS_DIR=/fonts`），`CBROWSER_FONTS_DIR` 写入 release env。默认部署时 `CBROWSER_FONTS_DIR` 指向主仓 `data/fonts`。
- 部署时字体 preflight 只警告、永不阻塞：字体目录缺失或无有效字体集时，部署输出可执行提示（如何导入字体集），部署继续；`GET /api/v1/font-sets` 的返回以实际导入的字体集为准。

- 平台字体只从官方渠道取得：macOS 取本机 `/System/Library/Fonts`、`Supplemental`、`/Library/Fonts` 与 `/System/Library/AssetsV2/` 下的苹方资源；Windows 取微软官方 Windows 11 企业评估版 ISO，经 `7zz` 从 `sources/install.wim` 提取 `Windows/Fonts`。不使用第三方字体站或 GitHub 镜像。
- 字体不进入任何镜像层与 git 仓库，部署 / 发布脚本不复制字体目录；系统不提供字体集删除功能（AC-008）。

## 3. 验收标准（摘要）

完整 AC 与可测试性声明见关联 task `t041`；本 spec 只作需求级累积。

- [x] AC-001：导入工具生成带 manifest 的不可变字体集，相同内容同一 `set_id`、内容变化新 `set_id`、已有集不被修改。
- [x] AC-002：`GET /api/v1/font-sets` 需登录，列出平台 / 来源 / 版本 / 静态完整性 / `used_by_count`，篡改或缺失显示不一致。
- [x] AC-003：两字段可创建与 PATCH、引用校验、默认最新集、修改生成新配置版本、启动参数取自绑定快照。
- [x] AC-004：两平台 `navigator.platform` / UA / UA-CH `platform` / `platformVersion` 一致（真实引擎 E2E；architecture 不做半套覆盖）。
- [x] AC-005：离线字体探测页两平台专有无串扰、Linux 字体不可见、可见字体只来自基础与绑定集（真实引擎 E2E）。
- [x] AC-006：绑定集缺失 / 不一致失败封闭 `font_set_unavailable`，null 正常启动并报告平台字体未配置。
- [x] AC-007：runtime 响应与 SSE 含实际 `font_set_id` 与 `missing_fonts`。
- [x] AC-008：镜像层与仓库无平台字体，部署 / 发布脚本不复制，worktree 经 `.worktreeinclude` 共享。
- [x] AC-009：`font_bundle` 字段、镜像字体包、代码与文档引用一并删除，扫描为空。
