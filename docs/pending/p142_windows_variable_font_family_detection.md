---
pid: "p142"
slug: "windows_variable_font_family_detection"
status: "closed"
resolution: "transferred"
reason: "已核实官方变量字体命名实例的实机匹配，并转交 t087"
fix_ref: "t087"
---
# p142 Windows 指纹版本与网页可见 Segoe UI Variable 子族不一致

- 现象：日区 Windows 环境的 `who.1ms.dog` 页面报告 Windows 版本与字体不一致。读取已打开页并运行无网络请求的字体探针，实测 `navigator.userAgentData` 为 Windows、`platformVersion=19.0.0`，Canvas 能识别 `Segoe UI Variable`，无法按家族名识别 `Segoe UI Variable Text` 和 `Segoe UI Variable Display`。站点将该 Client Hints 版本按 Windows 11 处理，要求以上两个名称至少一个可见。
- 影响：#26 和新建的美国 #76、日本 #77 均复现。#76、#77 均为 v1、英语、关闭 CJK，字体就绪已通过且实际 fontconfig 枚举无 `zh` 或 `zh-*` 标签。新增的两次独立网页探针均观察到 Windows `19.0.0`、Text/Display 名称落回退、Canvas 棋盘和离线音频常量改变。连接指纹和噪声独立登记。
- 根因：Fontconfig 枚举源文件 `SegUIVar.ttf` 时，把 Text、Display、Small 名称中的光学尺寸组放在 style，family 统一为 `Segoe UI Variable`。源文件 OpenType `fvar` 确认默认 Regular 和 Text Regular 同为 `wght=400, opsz=10.5`，Display Regular 为 `wght=400, opsz=36`，Small Regular 为 `wght=400, opsz=8`。以完整家族名查找时，现有路径选错候选面。微软 DirectWrite 文档明确将 `Segoe UI Variable Display` 作为一个 WWS 家族匹配。
- 修复证据：隔离容器使用同一固定引擎、官方只读字体集和新的 fontconfig 缓存。扫描阶段只对该字体文件及其相应命名实例补充家族别名，Text 默认实例同时匹配 `index=0`、`variable=false`、`Regular`。`fc-match` 分别选回原文件的 Text 0、Display 851968、Small 196608。网页 CSS 排版和 Canvas 72px 的样本文字宽度从回退字体的 612px 变为 Text 725px、Display 718px、Small 752px。Chrome CDP 确认归属原 Segoe 字体，基础家族仍为 725px，未知字体仍为 612px。CJK 关闭时仍为 218 个可见条目，均来自原挂载目录，`zh`、`zh-*` 标签仍为 0。
- 测试缺口：现有测试验证字体文件、可见性与 CJK 字形，未验证官方变量字体的命名实例匹配。实现需覆盖 Windows 专属规则、缺少目标字体时原有行为、基础家族和未知名称、真实浏览器排版与 Canvas、CJK 裁剪。补原生 Windows 11 Chrome 对照可验证跨 OS 字形与度量的差异。当前隔离实验已证实名到面的选择，原生 Windows 像素等价尚未测量。
- 线索：`.scratch/font_investigation/run.sh`、`.scratch/font_investigation/probe.py`、`.scratch/font_investigation/probe_cjk_off_result.txt`。前序美国和日本实测见 `.scratch/new_profile_comparison/us_raw_probe.json` 和 `.scratch/new_profile_comparison/jp_raw_probe.json`。[DirectWrite 字体选择](https://learn.microsoft.com/en-us/windows/win32/directwrite/font-selection) · [测站 Windows 字体规则](https://github.com/yt1988/who-are-you/blob/HEAD/src/app.js#L395)
- 处理：t087；resolution=transferred；reason=已核实官方变量字体命名实例的实机匹配，并转交 t087
