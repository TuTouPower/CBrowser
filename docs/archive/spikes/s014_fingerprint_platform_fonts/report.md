# Spike s014：指纹平台与平台专有字体集

状态：**已完成**（2026-11-06）。4 项 UNVERIFIED-SPIKE 均已核实并回填 `task.md`；结论写入 `d032` / `d033`，`font_bundle` 去留与 UA-CH 裁决已定。真实引擎的离线字体探测页（canvas 测宽）E2E 留待 t041 实现阶段按 AC-005 交付，spike 阶段以 fontconfig `fc-list` 隔离实测替代，证据充分。

## 背景与目标

t041 要求 Profile 可选 `windows` / `macos` 指纹平台，平台专有字体由 agent 从官方渠道获取、只在运行时挂载、不进镜像不入库。实施前须用正式 spike 核实：两种平台在 cloakbrowser 0.6.4 / Chromium 146 下的 UA、Client Hints、字体可见性一致性；每种平台的基础字体组合；`font_bundle` 去留；微软官方评估版 ISO 的可获取性与 `install.wim` 字体提取。

## 已核实结论（本机，2026-11-06）

### 本机 macOS 字体资源

- `/System/Library/Fonts`：83 个文件；`/System/Library/Fonts/Supplemental`：290 个；`/Library/Fonts`：1 个；`/System/Library/AssetsV2`：70 个资产目录（与 plan 第 6.8 节记录一致）。
- 已确认存在：`Hiragino Sans GB.ttc`（冬青黑体）、`Songti.ttc`（宋体）、`Apple Color Emoji.ttc`、`Apple Symbols.ttf`、`AppleSDGothicNeo.ttc` 等。
- 苹方（PingFang）不在 `/System/Library/Fonts` 顶层，已定位到 `com_apple_MobileAsset_Font8` 资产包：`/System/Library/AssetsV2/com_apple_MobileAsset_Font8/86ba2c91f017a3749571a82f2c6d890ac7ffb2fb.asset/AssetData/PingFang.ttc`。**该项 UNVERIFIED-SPIKE 已核实。**

### 工具与引擎

- `/opt/homebrew/bin/7zz` = 7-Zip 26.03 (arm64)，可用于 ISO → `install.wim` → `Windows/Fonts` 提取。
- 本地 gate venv 的 `cloakbrowser` = 0.6.4（`python -m cloakbrowser info` 显示本机 channel 为 145.0.7632.109.2 且二进制未安装），**因此 146 内核实测必须在 Linux arm64 Docker 容器内用引擎缓存**（主仓 `.scratch/t032/data/engine-cache/chromium-146.0.7680.177.3`，沿用 s013 spike 的探针容器方法）。
- 磁盘可用 176 GiB，足够容纳 8 GB ISO 与提取产物。

### 微软官方评估版 ISO 可获取性

- 评估中心页面 `https://www.microsoft.com/en-us/evalcenter/download-windows-11-enterprise` 可访问（裸 `curl -I` 返回 `HTTP/2 403`，属 WAF/UA 差异；带浏览器视角抓取返回完整下载页，非「不可获取」）。
- 页面提供各语言 Enterprise 64-bit ISO 直链（`go.microsoft.com/fwlink/?LinkId=...`）。中文简体 Enterprise 采用 `LinkId=2382601`，302 跳转到 `software-static.download.prss.microsoft.com` 的 `26300.9457.260913-1737.26h2_ge_release_svc_refresh_CLIENTENTERPRISEEVAL_OEMRET_x64FRE_zh-cn.iso`，`HTTP 200`、`Content-Length: 8548628480`（**8.0 GB**，Windows 11 26H2 评估版，比 plan 估计的约 6 GB 大）。
- 已启动断点续传后台下载：`.scratch/t041/win11_ent_eval_zh-cn.iso`（PID 81158，日志 `.scratch/t041/iso_download.log`，实测速率约 5–7 MB/s）。**下载已完成**：19 分 47 秒，`8548628480` 字节 100%，curl 正常退出；文件只写 `.scratch/`，不入库、不进镜像（AC-008 边界）。

### Chromium 146 平台一致性实测（已完成，2026-11-06）

方法：`cbrowser-t032-probe:final` 容器（Python 3.12.16 + cloakbrowser 0.6.4 + Playwright），只读挂载 `chromium-146.0.7680.177.3` 引擎，Playwright `chromium.launch(executable_path=ENGINE, args=["--no-sandbox", "--fingerprint-platform=<p>"])`，脚本 `code/platform_probe.py`。先于 `about:blank` 测得 `navigator.userAgentData === null`（opaque origin 非安全上下文），改经 `http://127.0.0.1:<port>/`（`isSecureContext=true`）重测，两组结果：

|字段|windows|macos|一致|
|---|---|---|---|
|`navigator.platform`|`Win32`|`MacIntel`|✓ 各符合平台|
|UA|`Windows NT 10.0; Win64; x64`|`Macintosh; Intel Mac OS X 10_15_7`|✓ 各符合平台|
|`userAgentData.platform`|`Windows`|`macOS`|✓|
|`getHighEntropyValues().platformVersion`|`19.0.0`|`15.2.0`|✓ 各符合平台|
|`architecture` / `bitness`|`arm` / `64`|`arm` / `64`|**windows 下 `arm` 与 UA 的 `x64` 矛盾**（见下）|
|`languages`|`["en-US"]`|`["en-US"]`|相同|

结论：task.md AC-004 明确列举的 `navigator.platform`、UA、UA Client Hints（`platform` / `platformVersion`）**两平台均一致，不触发「达不到一致时停止并报告用户」**。但实测暴露一个 AC-004 未列举、却与 t041「避免可被检测的指纹矛盾」风险直接相关的点：Linux arm64 宿主上 cloakbrowser 0.6.4 的 `--fingerprint-platform=windows` 未 patch UA CH 的 `architecture`，windows Profile 会同时呈现 `Win64; x64`（UA）与 `arm`（CH），构成平台/架构矛盾；macos 平台的 `arm` 与 Apple Silicon 一致。`about:blank` 下 UA CH 不可用也须在实现 E2E 时用 localhost/HTTPS 安全上下文，避免误判。此发现如实登记，实施 t041 时需决定是否纳入 AC-004 断言或报用户裁决。

### Windows 字体提取（已完成）

- `7zz l <iso>` 确认 `sources/install.wim` = `7585822780` 字节；`7zz x` 提取到 `.scratch/t041/wim_extract/sources/install.wim`（7.1 GB）。
- `7zz l <wim>` 显示 `Windows/Fonts` 347 条目；`7zz x <wim> Windows/Fonts` 得到 **346 个文件 / 488 MB**（`.scratch/t041/win_fonts/Windows/Fonts/`）。
- 关键字体确认存在：微软雅黑 `msyh.ttc` / `msyhl.ttc`、宋体 `simsun.ttc` / `simsunb.ttf`、黑体 `simhei.ttf`、Arial / Times / Calibri / Segoe UI / Tahoma / Verdana 全族（含粗斜体）。来源系统版本 `26300.9457`（Windows 11 26H2，ISO 构建日期 2026-09-14）。
- **该项 UNVERIFIED-SPIKE 已核实**：微软官方评估版 ISO 可获取、`install.wim` 可提取、`Windows/Fonts` 字体齐全。

## 待完成（ISO 下载结束后）

1. ~~`7zz x <iso> sources/install.wim` → `7zz x install.wim Windows/Fonts`~~ **已完成**（见上）；剩余：为导入工具生成 manifest 时逐文件计算 sha256 并登记来源系统版本 26300.9457。
2. ~~在 Chromium 146 探针容器内实测 `navigator.platform` / UA / UA Client Hints（platform、platformVersion）一致性~~ **已完成**（见上，两平台一致，未触发停止条件）。剩余：离线字体探测页按字体名渲染测宽（Windows 8 / Office 10 / Mac 20 清单）、`cloakbrowser info` 字体计数、Liberation 等 Linux 字体不可见性。
3. 用实测结果确定每种平台应暴露的基础字体组合，以及 `font_bundle`（文泉驿）去留 —— **已定（用户 2026-11-06 监督裁决）**：plan 6.8 六项基础开源字体是 CloakBrowser 的**镜像安装清单**，不等于对指纹 Profile 可见；文泉驿 / Unifont / FreeFont / IPAGothic / Loma 属 Linux 特征，留在镜像满足安装要求，但**不进入指纹 Profile 的 `FONTCONFIG_FILE` 白名单**。绑定平台字体集时可见集合只含该集（真实 Windows/macOS 上存在的字体）；`font_set_id` 为 null（平台字体未配置）时**回退为基础开源字体可见**，保证浏览器有字体、页面可用（AC-006 正常启动），runtime 状态报告「平台字体未配置」并在 `missing_fonts` 标明当前暴露 Linux 基础字体（用户 2026-11-06 裁决）。真实 146 引擎实测：windows 的 CJK 解析到微软雅黑 / 宋体、macos 到苹方 / 冬青黑体，emoji 有平台字体或合理回退（E2E `tests/e2e/test_fingerprint_platform_e2e.py` 3 passed）。`font_bundle` 删除。
4. 结论写入 `docs/findings/dNNN_*.md`（经 `findings.py` 创建），回填 `task.md` 的 4 项 UNVERIFIED-SPIKE 为结论与验证方式，再进入 9 条 AC 的实现。

## 后续 task

- 无需单独立项：本 spike 结论直接供 t041 实施使用。
- 复查条件：Chromium 主版本、cloakbrowser 平台能力或微软评估版 ISO 构建版本升级后，重跑两组平台实测与字体提取。

## 结论

- Windows / macOS 平台字体均可从官方渠道取得；fontconfig 白名单（不 include 系统配置、绑定集时**只声明该平台字体集目录**）实测有效：两平台平台字体可见、Liberation/Nimbus/WenQuanYi/Unifont/FreeFont/IPAGothic/Loma 等 Linux 特征字体命中 0；两平台都有原生 CJK 字体，故 `font_bundle` 删除。`font_set_id` 为 null 时回退基础字体可见、状态标记暴露 Linux 基础字体（否则浏览器无字体，真实栈 E2E 13 项页面交互失败）。见 `d033`。
- 146 内核 `--fingerprint-platform` 两平台的 `navigator.platform` / UA / CH `platform` / `platformVersion` 一致；`architecture=arm` 与 windows UA `x64` 的差异：引擎层无 flag、CDP 页面级覆盖实测漏 ServiceWorker（主文档/iframe/Worker/请求头 `x86`、SW 仍 `arm`），按用户裁决不做半套覆盖，见 `d032` + `p045`。
- 微软评估版 ISO（26H2，8.0 GB）可获取、`install.wim` 可提取；苹方位置已定位。
- `about:blank` 下 `navigator.userAgentData` 为 null，实现 E2E 须用 `http://127.0.0.1` / HTTPS 安全上下文。

## 决定

- 决定：是（spike 结论全部采纳：字体集隔离方案、`font_bundle` 删除、UA-CH 不做半套覆盖并登记 `p045`）。
- 后续 task：无需单独立项，结论直接供 t041 实施；UA-CH architecture 对齐由 `p045` 跟踪。
- 无需后续理由：全部 4 项 UNVERIFIED-SPIKE 已核实并回填 `task.md`。
