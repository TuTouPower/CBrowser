---
slug: fingerprint_platform
status: active
tasks: [baseline, t075, t080, t081]
---
# 需求规范：指纹平台与平台字体集 (fingerprint_platform)

## 1. 业务目标与适用范围

本 spec 累积 t041 交付的指纹平台选择与平台专有字体集隔离契约、t053 交付的语言分流与字体集链路收紧，以及 t075 交付的运行身份统一（字体绑定改后端托管、CJK 暴露改显式开关、GPU 身份改引擎派生、字体就绪改启动前真实验证，ADR 040）。Profile 可选 `windows` / `macos` 指纹平台，字体集绑定由后端按平台从资产目录解析默认集，用户不再手选字体包；平台专有字体只从官方渠道取得、只在运行时只读挂载，不进镜像与仓库。基础开源字体进入 Browser 镜像满足 CloakBrowser 安装要求，但不进入指纹 Profile 的 fontconfig 白名单；Profile 可见集合只含绑定的平台字体集，避免 Linux 专属字体形成平台指纹矛盾（用户 2026-11-06 裁决）。关联 task：`docs/tasks/t041_fingerprint_platform_fonts/task.md`（AC-001~009）、`docs/tasks/t053_profile_locale_fonts_defaults/task.md`（AC-001~015）、`docs/tasks/t075_profile_identity_assets_and_readiness/task.md`（AC-001~009）、`docs/tasks/t081_immutable_font_resource_lifecycle/task.md`（AC-001~009，字体集不可变资源生命周期与资产目录，ADR 030）。证据：正式 spike `docs/spikes/s014_fingerprint_platform_fonts/report.md`、`docs/spikes/s026_gpu_platform_capability/report.md`（GPU 平台能力矩阵，结论入 findings `d051`）、findings `d032`（UA-CH architecture 裁决）与 `d033`（字体集隔离实测）、`docs/plan_20261105_ui_redesign.md` 6.8 节。

## 2. 行为契约

### 2.1 运行配置字段

- `fingerprint_platform`：取值 `windows`（默认）/ `macos`；CloakBrowser 只支持这两种，无 Linux 指纹平台。
- `font_set_id`：引用同平台、按内容寻址的不可变字体集。t075 起绑定改**后端托管**：创建与切换平台时由服务按资产目录默认规则解析（只取目录中 verified 的集，其中最近一次验证通过的胜出；t081 起完整性结论以目录记录为准，读路径不再实时哈希），创建/更新请求不再接受该字段，用户不能手选、不能置空；字体根已配置（一切真实部署）而平台无可用集时，创建/切换在写入前失败。未配置字体根的进程（字体子系统不在其职责内，如门禁测试 harness）创建可暂无绑定，但启动与就绪仍失败封闭，该状态在真实部署中不可达（deploy 恒设字体根）。克隆等携带既有绑定的内部路径校验后保留原绑定。
- `include_cjk_fonts`（t075）：中文字体暴露开关，属运行配置。创建未显式给出时按语言派生（`zh-CN` 开、其余关）；运行时 fontconfig 的中文 reject 规则只看此开关、不再看 `locale`。英文关 CJK 时中文字体对 Browser 不可见，开启时集中文字体参与真实渲染匹配。
- `color_scheme`（t075 收敛）：只允许 `light` / `dark`，默认 `light`；旧 `null` / `no-preference` 在固定引擎上都渲染为浅色，迁移统一映射为 `light`（p124 实测）。后台主题设置不改写 Profile 的提交值。
- GPU 身份（t075，s026 / d051）：由引擎按指纹种子 + 平台自动派生，SDK 无 GPU 选择参数；`gpu_family` 字段与 `--fingerprint-gpu-vendor` 透传已删除，手选 GPU 契约取消。受支持组合只有（windows，引擎自动派生）与（macos，引擎自动派生）；旧 `nvidia` / `intel` 取值无等价映射，迁移时进阻塞清单。
- 上述字段属运行配置；修改任一都生成新 `ProfileConfigVersion`，重建容器后生效，不影响其他 Profile。旧配置与历史快照由迁移 `0013_profile_identity.py` 一次性改写到新形状：不可等价映射（旧 GPU 取值、悬空绑定、无集可绑）在改写前整体失败并给出阻塞清单，迁移幂等，恢复口径为部署前 DB 文件级备份整体还原。
- Runner 按绑定配置版本快照选择平台，删除写死的 `--fingerprint-platform=windows` 启动参数。

### 2.2 字体分层与 fontconfig 白名单

- 基础开源字体六项（`fonts-noto-color-emoji` / `fonts-freefont-ttf` / `fonts-unifont` / `fonts-ipafont-gothic` / `fonts-wqy-zenhei` / `fonts-tlwg-loma-otf`）在 Browser 镜像 `/opt/cbrowser-base-fonts`，位于 fontconfig 默认扫描路径之外，且**不进入**指纹 Profile 白名单（仅满足 CloakBrowser 安装要求）。
- 平台字体集在宿主 `CBROWSER_FONTS_DIR/{platform}/{set_id}/`，内容寻址 `set_id` + `manifest.json`（来源、来源系统版本、逐文件 sha256），导入后不可修改；经 `.worktreeinclude` 供各 worktree 共享同一份。
- Supervisor 只把 Profile 绑定的字体集只读挂载到 Browser 容器 `/run/cbrowser/fonts/{platform}/{set_id}`（默认扫描路径之外），不挂整个字体根目录，不挂给 Stream 容器。
- Runner 生成 `FONTCONFIG_FILE`：只以 `<dir>` 白名单声明绑定集目录，不 include `/etc/fonts/fonts.conf`，也不声明基础字体目录；Liberation / Nimbus / 文泉驿 / Unifont / FreeFont / IPAGothic / Loma 等 Linux 专属字体对两平台都不可见（真实 146 引擎 E2E 与 `fc-list` 实测命中 0，见 `d033`）。t075 起**无基础字体回退**：未绑定（仅旧快照可能出现）时白名单为空，Runner 启动前验证失败封闭，不再以暴露 Linux 基础字体的方式启动。
- `font_bundle`（文泉驿按 Profile 三态）已删除：字段、镜像字体包、代码、文档与测试引用一并清理（AC-009）。

### 2.3 平台一致性

- 两种平台启动后，`navigator.platform`、UA 与 UA Client Hints（`platform` / `platformVersion`）均与所选平台一致（AC-004，真实引擎 E2E）。
- `architecture=arm` 与 windows UA `x64` 的差异：引擎层无 flag、CDP 页面级覆盖漏 ServiceWorker，按用户裁决不做半套覆盖；见 `d032` 与 `p045`，AC-004 文本不改。

### 2.4 失败封闭与运行时完整性

- 绑定字体集缺失，或文件与 manifest 不一致时，启动失败封闭并报告 `font_set_unavailable`；未绑定同样失败封闭（t075，取代旧的基础字体回退）。
- t075 起字体就绪以 Runner 启动前的一次真实验证为准：对实际挂载目录核对 manifest、平台、逐文件 sha256 内容哈希，并用该实例生成的 fontconfig 跑真实 `fc-list` 枚举有效字体；CJK 开时另以 FreeType 真实光栅化证明至少一个中文面能渲染中文字形；挂载为空、manifest 损坏、内容不符、过滤后无必需字形（CJK 开时无中文字体面、CJK 关时中文字体泄漏）、中文字形渲染失败任一成立即不启动并记录失败原因。验证结论随 `runner_info` 持久化，Agent 健康与 runtime 响应/SSE 只读结论（`font_set_id`、`missing_fonts` 为可选探测字体的覆盖缺口、失败原因），不逐请求重扫字体字节；`ready` 要求字体结论为 verified。可选探测覆盖不足只记覆盖缺口、不判失败，与必需渲染失败严格区分。
- `GET /api/v1/font-sets` 需登录会话，列出各字体集的平台、来源、版本、静态完整性（Windows 8 个 / Office 10 个 / Mac 20 个检测字体覆盖情况）与 `used_by_count`；文件被篡改或缺失时完整性显示不一致（AC-002）。导入工具生成带 manifest 的不可变字体集，相同内容重复导入得到同一 `set_id`（AC-001）。

### 2.6 字体目录作为独立部署输入（t051）

- 字体目录是独立部署输入，不再经 `${CBROWSER_DATA_ROOT}/fonts` 派生：compose 以 `${CBROWSER_FONTS_DIR}:/fonts:ro` 只读挂载（API 与 Supervisor 容器内 `CBROWSER_FONTS_DIR=/fonts`），`CBROWSER_FONTS_DIR` 写入 release env。默认部署时 `CBROWSER_FONTS_DIR` 指向主仓 `data/fonts`。

- 部署时字体 preflight 只警告、永不阻塞：字体目录缺失或无有效字体集时，部署输出可执行提示（如何导入字体集），部署继续；`GET /api/v1/font-sets` 的返回以实际导入的字体集为准。

- 平台字体只从官方渠道取得：macOS 取本机 `/System/Library/Fonts`、`Supplemental`、`/Library/Fonts` 与 `/System/Library/AssetsV2/` 下的苹方资源；Windows 取微软官方 Windows 11 企业评估版 ISO，经 `7zz` 从 `sources/install.wim` 提取 `Windows/Fonts`。不使用第三方字体站或 GitHub 镜像。

- 字体不进入任何镜像层与 git 仓库，部署 / 发布脚本不复制字体目录；系统不提供字体集删除功能（AC-008）。

### 2.7 语言分流与字体集链路收紧（t053）

- 语言是运行配置字段 `locale`，封闭枚举 `zh-CN` / `en-US`（新建默认 `en-US`），非法值在写入边界 422 拒绝；时区 `timezone` 为合法 IANA 时区名或 null（null 表示自动、随出口 IP），非法时区 422 拒绝。时区 → 语言：中文地区时区集合（`Asia/Shanghai` / `Asia/Chongqing` / `Asia/Urumqi` / `Asia/Harbin` / `Asia/Hong_Kong` / `Asia/Macau` / `Asia/Taipei`）→ `zh-CN`，其余 → `en-US`；时区为空时语言保持当前值。语言变更生成新 `ProfileConfigVersion`，重启后生效。
- fontconfig 白名单按 `include_cjk_fonts` 开关排除覆盖中文的字体（t075 取代 t053 的按 `locale` 分流）：开关关时，对中文语言标签（`zh` / `zh-cn` / `zh-tw` / `zh-hk` / `zh-mo` / `zh-sg`）各追加一条 `<selectfont><rejectfont>`，排除 fontconfig `lang` 覆盖含任一中文标签的字体；开关开时不裁剪。裁剪只看字体的 `lang` 覆盖声明；日文、韩文等非中文 CJK 字体除非其 `lang` 覆盖声明含中文，否则不被裁剪。开关的创建默认按语言派生（见 2.1），用户可独立修改，修改语言不再自动改写开关。
- 绑定字体集时 fontconfig 生成失败即启动失败并报告 `font_set_unavailable`，浏览器不以系统字体运行（A18）。字体集文件被删除或篡改后，以原始字体重新导入可原子恢复完整性；字体集缺失或损坏时，REST 与 SSE 立即报告缺失，无需重启 API（A19）。`GET /api/v1/font-sets` 返回 `items` 与各平台 `default_font_set_id`；`used_by_count` 按 `(fingerprint_platform, font_set_id)` 统计；manifest 平台与目录不一致的条目标为完整性失败（A20）。会话详情区分「字体集完整性」与「探测字体未覆盖」两种文案（A30）。
- 已知取舍：真实 Windows / macOS 不论系统语言均预装原生中文字体（d033 / ADR 024），裁剪后英文 Profile 可能呈现“缺少系统原生字体”特征；用户 2026-11-10 已知悉仍确认裁剪（ADR 030，部分替代 ADR 024 的“字体集整体可见”部分）。英文 Profile 访问中文页面时中文字符回退为方框，属用户确认取舍。

## 3. 验收标准（摘要）

完整 AC 与可测试性声明见关联 task `t041` 与 `t053`；本 spec 只作需求级累积。

- [x] AC-001：导入工具生成带 manifest 的不可变字体集，相同内容同一 `set_id`、内容变化新 `set_id`、已有集不被修改。
- [x] AC-002：`GET /api/v1/font-sets` 需登录，列出平台 / 来源 / 版本 / 静态完整性 / `used_by_count`，篡改或缺失显示不一致。
- [x] AC-003：两字段可创建与 PATCH、引用校验、默认集由后端按完整性规则给出（t053 A16）、修改生成新配置版本、启动参数取自绑定快照。
- [x] AC-004：两平台 `navigator.platform` / UA / UA-CH `platform` / `platformVersion` 一致（真实引擎 E2E；architecture 不做半套覆盖）。
- [x] AC-005：离线字体探测页两平台专有无串扰、Linux 字体不可见、可见字体只来自基础与绑定集（真实引擎 E2E）。
- [x] AC-006：绑定集缺失 / 不一致失败封闭 `font_set_unavailable`；null 回退基础字体启动为 t041/t053 旧语义，t075 起改为未绑定同样失败封闭、无回退。
- [x] AC-007：runtime 响应与 SSE 含实际 `font_set_id` 与 `missing_fonts`。
- [x] AC-008：镜像层与仓库无平台字体，部署 / 发布脚本不复制，worktree 经 `.worktreeinclude` 共享。
- [x] AC-009：`font_bundle` 字段、镜像字体包、代码与文档引用一并删除，扫描为空。

t053 交付（语言分流与字体集链路收紧，完整 AC 见 `t053` task）：

- [x] AC-006：英文 Profile 运行时，Browser 内 fontconfig 可见字体中不含任何覆盖中文的字体；绑定 windows 与 macos 字体集、以及未绑定字体集三种情况均成立（fontconfig 单测 + 宿主 `fc-list` 实测；真实引擎部分待用户机补验）。
- [x] AC-007：中文 Profile 运行时，windows 字体集下中文文本解析到微软雅黑或宋体，macos 字体集下解析到苹方或冬青黑体（真实引擎部分待用户机补验）。
- [x] AC-008：Profile 语言修改后生成新配置版本，重启后字体可见性与 `navigator.language` 按新语言生效（版本生成已测；真实引擎部分待用户机补验）。
- [x] AC-009：运行时 `navigator.language` 等于 Profile 配置的语言，不被出口 IP 自动推断覆盖（真实引擎验证待用户机补验）。
- [x] AC-010：[deploy] 真实部署后分别新建英文与中文 Profile 启动，页面内字体探测结果符合 AC-006 / AC-007（本机未验证、不得记为已验，待用户机部署补验）。
- [x] AC-011：新建环境表单默认预选后端给出的默认字体集；用户选择「无」后保持为无并以 null 保存；后端默认集只取完整性通过的字体集。（t075 起表单不再提供字体集选择，绑定全部由后端托管，本条为 t053 历史语义。）
- [x] AC-012：绑定字体集的 Profile 在 fontconfig 生成失败时启动失败并报告 `font_set_unavailable`，浏览器不以系统字体运行。
- [x] AC-013：字体集文件被删除或篡改后，以原始字体重新导入可恢复完整性；字体集缺失或损坏时，REST 与 SSE 立即报告缺失，无需重启 API。
- [x] AC-014：同一 set_id 同时存在于 windows 与 macos 时，两平台条目的引用数各自独立；manifest 平台与目录不一致的条目显示为完整性失败。
- [x] AC-015：字体集完整但未覆盖部分探测字体时，会话详情显示「探测字体未覆盖」而非完整性损坏。

t075 交付（环境运行身份、字体资产与真实就绪契约统一，完整 AC 见 `t075` task）：

- [x] AC-001：字体绑定改后端托管，创建/克隆/切平台后绑定与平台一致，非法组合在写入前以可理解错误失败；用户不再手选字体包。
- [x] AC-002：字体与 GPU 身份在保存、克隆、重启后一致（GPU 为引擎按种子+平台派生）；无目录默认集时创建失败。
- [x] AC-003：配色只剩 light/dark，提交与回显一致，后台主题不改写。
- [x] AC-004：旧配置与历史快照由迁移 0013 一次性改写到新形状，不可等价映射改写前阻塞并给出清单，重复迁移幂等，备份恢复演练通过。
- [x] AC-005：字体源目录不存在时 Supervisor 挂载构造即失败，绝不由 daemon 建空目录后零字体启动。
- [x] AC-006：挂载空 / manifest 损坏 / 内容不符 / 过滤后无必需字形时 Runner 不报告可用、实例不就绪。
- [x] AC-007：CJK 开关关时中文字体不可见、开时中文真实渲染匹配（云端以真实 fc-list 枚举验证，引擎渲染部分待本地补验 p137）。
- [x] AC-008：可选探测覆盖不足与必需渲染失败在结论中严格区分；改普通配置不影响 Cookie 与会话。
- [x] AC-009：[deploy] 真实容器化编排下双平台字体隔离与中英文可读——云端不可验，按 2026-11-18 裁定打勾并顺延本地补验 p137。
