# Task review t087（reviewer_focus: 通用）

- task：`t087_windows_variable_font_named_instances`
- spec：`docs/tasks/t087_windows_variable_font_named_instances/task.md`
- diff_anchor：`1531b20999354236467897f8e02eacfee0d447b8`
- target：`git diff 1531b20999354236467897f8e02eacfee0d447b8`
- round：1
- reviewed_at：2026-11-19T09:45:39+08:00

reviewed_scope: 22db76213d05c2a1

## Findings

### t087_gen_f001 - 已验证的官方字体文件改名后丢失光学实例匹配

- 严重度：important
- 锚点：AC-001 要求 Windows 环境挂载含所需实例的官方字体集后，按 Display 名称选中真实 Display 实例。
- 位置：`src/backend/cbrowser/runtime_agent/fontconfig.py:112`，`src/backend/cbrowser/runtime_agent/fontconfig.py:156`，`src/backend/cbrowser/font_sets/manifest.py:253`。
- 问题：把同一份官方 Segoe UI Variable 字节以 `SegUIVar.ttf` 和 `official.ttf` 分别导入，`import_font_set` 保留源文件名，两个字体集的完整性与 `verify_mounted_font_set` 均通过。候选镜像内执行 `fc-match 'Segoe UI Variable Display'`，原名命中 `Regular Display|851968`，改名副本命中 `Regular|0`。字体集契约接受该副本，文件路径判定使内部真实 Display 实例无法按名称匹配。
- 建议：在既有 Windows 平台与已绑定目录白名单限制下，根据扫描得到的内部家族和实例属性匹配，并用官方字节改名的导入场景复验。

## 结论

- 本轮新发现：1 条。
- 未进表的提示：无。已审查正确性、安全、契约及类型、资源、架构、健壮性与测试文档。
- 总体判断：候选镜像与工作树两个改动模块的 SHA-256 一致。原始文件名时首次启动与重启均匹配 Text、Display、Small，CSS 宽度分别为 725、718、752，未知名字回退为 612。仍有已验证官方字节改名后的匹配缺口。
- 系统性 follow-up：无。

### AC 复验方式

- AC-001：TICK-VOID，re_verified。已独立重跑原名浏览器探针，随后在同一候选镜像以真实字体导入、运行验收与 `fc-match` 复现有效改名字体集的 Display 请求命中默认实例。
- AC-002：TICK-VALID，re_verified。`src/backend/cbrowser/runtime_agent/fontconfig.py:155` 限制 Windows 扫描规则，相关单测 31 通过、7 跳过，候选镜像两次启动均保有字体校验和排除中文覆盖的约束。

coverage = 2 / 2

verdict: FAIL

## Round 2 (2026-11-19T09:52:13+08:00)

reviewed_scope: 84be80b684be89aa

### Findings

无新发现。

### 结论

- 前轮 finding 复核：t087_gen_f001 已消除。`src/backend/cbrowser/runtime_agent/fontconfig.py:111` 以字体内部家族和 PostScript 名识别候选实例，Windows 条件与绑定集目录白名单保持有效。独立将同一官方字节以三种名称导入，导入完整性与运行字体验收全部通过，三种名称均匹配原文件的 Text、Display、Small，实例索引分别为 0、851968、196608。
- 当前候选镜像中的 `fontconfig.py` 与 `runner.py` 两个 SHA-256 均与工作树一致。已独立重跑真实浏览器和相关单测，结果见下。
- 系统性 follow-up：无。

### AC 复验方式

- AC-001：TICK-VALID，re_verified。候选镜像内分别验证原名、大小写变体与任意改名的官方文件，实际命中正确实例；浏览器首次启动和重启的 CSS 宽度均为 Text 725、Display 718、Small 752，未知名称正常回退至 612。
- AC-002：TICK-VALID，re_verified。`src/backend/cbrowser/runtime_agent/fontconfig.py:155` 保持 Windows 专用规则，改名集只列出其绑定目录所含字体，真实 Runner 两次字体验收均通过且未枚举中文覆盖字体，相关单测 31 通过、7 跳过。

coverage = 2 / 2

verdict: PASS
