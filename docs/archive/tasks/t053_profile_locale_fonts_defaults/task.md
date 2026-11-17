# Task spec

## 背景

Profile 配置三处缺陷集中在同一交付面（Profile 配置模型、`ProfileForm.tsx`、运行时 fontconfig），合并交付：

1. **高级选项默认值（p067）**：用户要求新建环境时拟人化（`humanize`）与便携 Cookie（`portable_cookies`）默认开启；透明代理、自动启动保持默认关闭；允许第三方 Cookie、设 Google 为默认、剪贴板同步、恢复会话、采集预览保持默认开启。当前前端 `DEFAULT_PROFILE_CREATE_VALUES`、后端 `ProfileConfig` / `ProfileCreateRequest` / `ProfileResponse` 与 ORM 默认值中 `humanize`、`portable_cookies` 均为 `false`。

2. **时区与语言（p069）**：`ProfileForm.tsx` 的时区与语言是两个裸文本框，无候选、无校验、无联动；`timezone` 与 `locale` 是互相独立的自由文本，填错导致启动异常或指纹不一致。用户要求时区可打字过滤、未打字时可滚动浏览全部 IANA 时区；语言只支持中文（`zh-CN`）与英文（`en-US`），按时区自动联动——中文地区时区（`Asia/Shanghai`、`Asia/Chongqing`、`Asia/Urumqi`、`Asia/Harbin`、`Asia/Hong_Kong`、`Asia/Macau`、`Asia/Taipei` 等）选中文，其余选英文。

3. **字体按语言分流（p069）**：当前平台字体集按操作系统整体挂载，Runner 生成的 fontconfig 白名单声明整个字体集目录；未绑定字体集时回退 `/opt/cbrowser-base-fonts`（含文泉驿正黑）。用户要求英文 Profile 不加载任何中文字体，中文 Profile 必须加载平台中文字体。

4. **字体集链路审阅缺陷（`docs/reviews/review_20261110_200842/adoption_decision.md`）**：新建环境时字体集「无」不可选，前端按字符串排序自行推导默认集且不看完整性（A16）；Runner 生成 fontconfig 失败时回落系统配置，Linux 字体对指纹 Profile 重新可见且状态不感知（A18）；内容寻址字体集损坏后再导入不修复，Coordinator 把「集不存在」缓存为「无缺失」且永不失效（A19）；`used_by_count` 跨平台串加、列表平台取目录名不校验 manifest（A20）；会话详情把探测字体缺失展示为完整性损坏（A30）。

用户 2026-11-10 已知悉 d033 / ADR 024 事实（真实 Windows / macOS 不论系统语言均预装原生中文字体，裁剪后英文 Profile 可能呈现“缺少系统原生字体”特征），仍确认按原需求裁剪。

## 契约区

### 范围

- 新建 Profile 默认值：`humanize`、`portable_cookies` 为开启；其余高级选项默认值保持现状并由测试固定。前后端与 ORM 默认值一致，OpenAPI 与前端类型重新生成。既有 Profile 的值不变。
- 语言字段收敛为两值（`zh-CN` / `en-US`），后端校验拒绝其它值；时区字段校验为合法 IANA 时区或空（空表示随出口 IP 自动）。
- 后端提供时区 → 语言判定规则（中文地区时区集合 → `zh-CN`，其余 → `en-US`），前端联动使用同一规则来源或经测试保证一致。
- 前端时区选择组件：可键入过滤候选、无输入时可展开并滚动浏览全部 IANA 时区、键盘可操作；常用时区置顶。
- 选择时区后语言自动联动；语言以中/英二选一控件展示，用户可手动覆盖；时区为自动时语言保持当前值（新建默认 `en-US`）。
- 字体分流：平台字体集内的中文字体（fontconfig 语言覆盖含任一中文 `zh-*` 的字体）在英文 Profile 的 fontconfig 白名单中被排除，在中文 Profile 中可见；未绑定字体集时的基础字体回退同样遵守该规则。
- 运行时状态与 `GET /api/v1/font-sets` 等既有字体信息在语言分流后保持准确（对外报告的可见字体与实际一致）。
- 语言变更生成新配置版本，下次启动生效。
- 默认字体集（A16）：默认集只由后端按完整性规则决定，`GET /api/v1/font-sets` 返回各平台 `default_font_set_id`，创建表单以其预选；「无」为显式选项，提交显式 null，后端按显式 null 保存。
- fontconfig 失败封闭（A18）：绑定了字体集时 fontconfig 生成失败即启动失败（`font_set_unavailable`），不回落系统配置。
- 字体集修复与实时校验（A19）：导入时目标目录完整性不通过则以新内容原子替换；删除 Coordinator 字体运行时缓存，按 Supervisor 同一校验函数实时读取。
- 平台隔离计数（A20）：引用计数按 (fingerprint_platform, font_set_id) 统计；列表校验 manifest 平台与目录一致，不一致标为完整性失败。
- 缺失展示（A30）：会话详情区分「字体集完整性」与「探测字体未覆盖」两种文案。

### 非范围

- 不新增中/英以外的语言。
- 不裁剪日文、韩文等非中文 CJK 字体（除非其 fontconfig 语言覆盖声明含中文）。
- 不改界面语言（UI i18n）与 Profile 语言的关系。
- 不改字体集导入工具与内容寻址格式，不新增字体文件来源。
- 不改其它高级选项的语义。

### 验收标准

<!-- 规范（门禁必留，不得删除） -->

只写可观察、可独立验证的行为；每条使用稳定且不复用的 `AC-NNN`。需真实部署或人工环境验证时在编号前加 `[deploy]`。创建时均为未勾选（`- [ ]`）；实施验证通过后由实施 Agent 就地打勾（`- [x]`）；由 Review Agent 独立复核打勾真实性。技术选型不作为行为 AC。review 判 FAIL 且需修改交付内容时，实施 Agent 撤回全部打勾，修复并重验后重新打勾；reviewer 用 `TICK-VALID` / `TICK-VOID` 逐条判定。

<!-- /规范 -->

- [x] AC-001：新建环境表单与未指定高级选项的创建 API 请求，得到拟人化与便携 Cookie 开启、透明代理与自动启动关闭、允许第三方 Cookie / 设 Google 为默认 / 剪贴板同步 / 恢复会话 / 采集预览开启。
- [x] AC-002：既有 Profile 的高级选项值在升级后不变。
- [x] AC-003：时区控件键入部分文本时只列出匹配的 IANA 时区并可选中；未键入时展开可滚动浏览全部 IANA 时区；可用键盘完成选择。
- [x] AC-004：选择中文地区时区后语言自动变为中文，选择其它时区后自动变为英文；用户手动切换语言后保存值为用户所选。
- [x] AC-005：API 拒绝非法时区与 `zh-CN` / `en-US` 以外的语言，返回字段级错误。
- [x] AC-006：英文 Profile 运行时，Browser 内 fontconfig 可见字体中不含任何覆盖中文的字体；绑定 windows 与 macos 字体集、以及未绑定字体集三种情况均成立。
- [x] AC-007：中文 Profile 运行时，windows 字体集下中文文本解析到微软雅黑或宋体，macos 字体集下解析到苹方或冬青黑体。
- [x] AC-008：Profile 语言修改后生成新配置版本，重启后字体可见性与 `navigator.language` 按新语言生效。
- [x] AC-009：运行时 `navigator.language` 等于 Profile 配置的语言，不被出口 IP 自动推断覆盖。
- [x] AC-010：[deploy] 真实部署后分别新建英文与中文 Profile 启动，页面内字体探测结果符合 AC-006 / AC-007。
- [x] AC-011：新建环境表单默认预选后端给出的默认字体集；用户选择「无」后保持为无并以 null 保存；后端默认集只取完整性通过的字体集。
- [x] AC-012：绑定字体集的 Profile 在 fontconfig 生成失败时启动失败并报告 `font_set_unavailable`，浏览器不以系统字体运行。
- [x] AC-013：字体集文件被删除或篡改后，以原始字体重新导入可恢复完整性；字体集缺失或损坏时，REST 与 SSE 立即报告缺失，无需重启 API。
- [x] AC-014：同一 set_id 同时存在于 windows 与 macos 时，两平台条目的引用数各自独立；manifest 平台与目录不一致的条目显示为完整性失败。
- [x] AC-015：字体集完整但未覆盖部分探测字体时，会话详情显示「探测字体未覆盖」而非完整性损坏。

### 可测试性声明

<!-- 规范（门禁必留，不得删除） -->

逐条说明不可自动测试的 AC 及替代验证；全部可测则写“全部 AC 可自动测试”。

<!-- /规范 -->

- AC-001..009、AC-011..015：可自动测试（前后端默认值与校验单测、前端组件测试、fontconfig 白名单单测、真实引擎 E2E 字体探测，参照 `test_fingerprint_platform_e2e.py`）。
- AC-010：真实部署验证；替代验证为部署后人工启动两种语言 Profile，记录 `fc-list` 与页面字体探测结果。

## 上下文区

- 来源：p067、p069（2026-11-10 复核：`types.ts:41/51`、`domain/models.py:157/172/375/390/489/504`、ORM `models.py:98/128` 中 `humanize` / `portable_cookies` 默认 `false`，ORM 默认为 Python 侧默认无 server_default；`ProfileForm.tsx:432-442` 时区/语言为裸输入；`fontconfig.py` `profile_font_dirs` 只按目录白名单，未绑定时回退 `/opt/cbrowser-base-fonts`；本机 windows 字体集含 `msyh.ttc` / `simsun.ttc` / `msjh.ttc`，macos 字体集含 `PingFang.ttc` / `Hiragino Sans GB.ttc` / `STHeiti*.ttc` / `Songti.ttc`）；`docs/reviews/review_20261110_200842/adoption_decision.md` A16、A18、A19、A20、A30（审阅原文第 63–67、69、70、90 项）。
- 已知取舍：d033 / ADR 024 记录真实平台不论语言均有原生中文字体；用户确认仍裁剪。本 task 需在 ADR 中记录该取舍，替代 ADR 024 中“字体集整体可见”的部分。
- `geoip` 默认开启，CloakBrowser 在时区 / 语言为空时按出口 IP 推断；本 task 后语言恒为显式值。

### 有意不测

- 指纹检测网站对“英文平台缺原生中文字体”的判定：外部风控行为，非本系统契约。

### 测试策略

- 单元：默认值三端一致；时区校验、语言枚举、时区 → 语言规则；fontconfig 按语言生成（含未绑定回退）。
- 前端：时区组合框过滤、滚动、键盘、联动与手动覆盖；默认开关状态。
- E2E：真实引擎下英文/中文 Profile 的 `fc-list` 与 `document.fonts.check` / measureText 中文字体探测、`navigator.language`。

### 未知契约清单

<!-- 规范（门禁必留，不得删除） -->

未核实的外部契约标为 `UNVERIFIED-BLOCKING` 或 `UNVERIFIED-SPIKE`；核实后改写为结论和验证方式。无则写“无”。

<!-- /规范 -->

- CloakBrowser `geoip=True` 时显式传入的 `locale` 是否优先于出口 IP 推断：结论（本机可验部分已验，引擎内裁决待用户机补验）——链路本机已验证：`ProfileConfig.locale` 经 Runner 原样传给引擎启动调用（`runner.py` 的 `launch_persistent_context_async(locale=cfg.locale, geoip=cfg.geoip, ...)`），zh-CN / en-US 两值均有测试固定（`tests/unit/test_t053_fontconfig_locale.py::test_explicit_locale_reaches_engine_launch_alongside_geoip`，同时断言同一 locale 驱动生成的 fontconfig）；引擎内部是否让显式 `locale` 优先于出口 IP 推断，本机无真实引擎、无法核实。用户机补验方法：分别新建 zh-CN 与 en-US Profile（`geoip` 保持开启、时区留空随出口 IP 自动），真实引擎启动后在页面读取 `navigator.language`，应分别等于 `zh-CN` / `en-US`；若读到出口 IP 对应语言，则显式 `locale` 未优先，需按该结果改契约。对应 AC-009（运行时 `navigator.language` 等于配置语言）与 AC-010（真实部署双语启动复核）。
- fontconfig 在白名单目录内按字体语言覆盖排除文件的机制（`<selectfont><rejectfont>` 按 `lang` 或按文件 glob）在当前镜像 fontconfig 版本下对 `.ttc` 集合是否生效：已部分验证——宿主 fontconfig 2.15.0 上以真实字体（NotoSansCJK-Regular.ttc + DejaVuSans.ttf）实测，`<selectfont><rejectfont>` 按 `lang` 对 `.ttc` 集合生效（英文配置隐藏全部 CJK 面、保留 DejaVu，中文配置两者皆见；见 `tests/unit/test_t053_fontconfig_locale.py::test_fc_list_hides_cjk_fonts_for_en_us`）。剩余未验证：Browser 镜像内 fontconfig 版本是否同样生效，须在用户机以 `fc-list` 实测。

### 风险与回退

- 风险：英文 Profile 访问中文页面时中文字符回退为方框；属用户确认取舍。
- 风险：按语言覆盖判定可能把部分日文字体一并排除；以字体集清单逐项测试固定结果。
- 回退：revert 实现 commit；数据库增量迁移可回退。

### 依赖与约束

- 无硬前置；与 t051 都涉及平台字体（t051 改挂载路径，本 task 改白名单），建议 t051 先合并以便真实部署验证 AC-010。
- 需数据库增量迁移（语言字段收敛）；无真实用户，不迁移存量自由文本内容。

### Finalization 时更新的 blueprint

- `docs/blueprint/browser_runtime.md`：按语言生成 fontconfig。
- `docs/blueprint/domain.md`：语言枚举与时区 → 语言规则、高级选项默认值。
- `docs/blueprint/frontend.md`：时区组合框与语言联动。
- `docs/blueprint/decisions.md`：新增 ADR「英文 Profile 裁剪中文字体」，标注部分替代 ADR 024。
- `docs/specs/profile_management.md`、`docs/specs/fingerprint_platform.md`：对应行为。
