# d033 平台字体集可由官方渠道获取，fontconfig 白名单隔离有效，font_bundle 应删除

- 来源：`docs/spikes/s014_fingerprint_platform_fonts/` 正式 spike（t041），2026-11-06；脚本 `code/platform_probe.py`、`code/ua_ch_flag_probe.py`、`code/ua_ch_cdp_probe.py`，以及探针容器内的 fontconfig 实测。
- 结论：**两种平台的专有字体均可从官方渠道取得；生成的 `FONTCONFIG_FILE` 只声明白名单目录时，平台字体可见而 Liberation/Nimbus/文泉驿等 Linux 专属字体完全不可见；两种平台都有原生 CJK 字体，故 `font_bundle`（按 Profile 选配文泉驿）应删除。**
- 证据：
    - Windows：微软评估中心 `download-windows-11-enterprise` → `go.microsoft.com/fwlink/?LinkId=2382601` → `26300.9457...CLIENTENTERPRISEEVAL_OEMRET_x64FRE_zh-cn.iso`（8,548,628,480 字节 / 26H2）→ `7zz` 提取 `sources/install.wim` → `Windows/Fonts` 346 文件 / 488 MB，含微软雅黑 `msyh.ttc`、宋体 `simsun.ttc`、黑体 `simhei.ttf`、Arial/Times/Calibri/Cambria/Consolas/Segoe UI/Tahoma/Verdana 全族。
    - macOS：`/System/Library/Fonts`（83）、`Supplemental`（290）、`/Library/Fonts`（1），苹方在 `/System/Library/AssetsV2/com_apple_MobileAsset_Font8/86ba2c91f017a3749571a82f2c6d890ac7ffb2fb.asset/AssetData/PingFang.ttc`；冬青黑体 `Hiragino Sans GB.ttc`、`STHeiti Medium.ttc`、宋体 `Songti.ttc` 齐全。
    - fontconfig 隔离实测（探针容器 `fc-list`，`FONTCONFIG_FILE` 不含 `/etc/fonts/fonts.conf`、只 `<dir>` 声明挂载目录）：windows 集可见 Arial / Calibri / Cambria / Consolas / Segoe UI / Microsoft YaHei / SimSun；macos 集可见 Helvetica / Helvetica Neue / Hiragino / Heiti / PingFang；**两平台对 `Liberation|Nimbus|WenQuanYi|DejaVu` 的命中数均为 0**。
    - 146 内核真实引擎 `--fingerprint-platform=windows` / `=macos`：`navigator.platform`、UA、`userAgentData.platform`、`platformVersion` 两平台均一致（详见 `d032`，CH `architecture` 问题另案）。
- 影响：t041 实现据此确定：基础开源字体按 plan 6.8 六项清单装入镜像 `/opt/cbrowser-base-fonts`，仅满足 CloakBrowser 安装要求，**不进入**指纹 Profile 的 `FONTCONFIG_FILE` 白名单（用户 2026-11-06 裁决：基础包是安装清单，不等于对指纹 Profile 可见；文泉驿 / Unifont / FreeFont / IPAGothic / Loma 是 Linux 特征）。平台字体集只读挂载到默认扫描路径之外；Runner 生成 `FONTCONFIG_FILE`：绑定平台字体集时只显式声明该集目录、不 include 系统配置；`font_set_id` 为 null（平台字体未配置）时**回退为基础开源字体可见**，保证页面可用（AC-006 正常启动；空字体集会让真实栈页面交互失败，第三轮门禁 13 项 E2E 失败的根因），runtime 状态报告「平台字体未配置」并在 `missing_fonts` 标明当前暴露 Linux 基础字体（用户 2026-11-06 裁决）；删除 `font_bundle` 字段、镜像字体包、代码与文档引用（AC-009）。字体不进镜像/仓库（AC-008）。真实 146 引擎 E2E 验证 windows CJK 解析到微软雅黑/宋体、macos 到苹方/冬青黑体、emoji 有平台字体或合理回退，`FONTCONFIG_FILE` 下 Linux 特征字体命中 0（`test_fingerprint_platform_e2e.py` 3 passed）。
- 现状：有效
- 复查条件：CloakBrowser 升级改变字体最低要求、macOS/Windows 官方字体来源或目录结构变化时重跑字体提取与 `fc-list` 隔离实测。
