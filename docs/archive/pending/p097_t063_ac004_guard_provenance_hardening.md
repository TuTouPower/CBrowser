# p097 t063 AC-004 静态守护改为导入溯源判定（test 轴 Round 2 minor 遗留）

- 来源：t063 遗留（review_test Round 2 finding t063_test_f006，minor，不阻断 PASS）
- 内容：`tests/unit/test_t063_patched_keyboard_behavior.py` 的 AC-004 包级 AST 守护按「根标识符含 selkies 子串」判定 selkies 模块属性写入，Round 2 审阅实测四种拼写漏网：全点路径 `selkies.__main__.WebRTCService = f`、`from selkies import input_handler` 后 `input_handler._XTestKeyboard = f`、直接 `_XTestKeyboard.prebind = f`、短别名 `setattr(m, ...)`。当前 stream_agent 包经双路审阅实测干净、无实际违规，AC-004 现状不受影响；本项是把守护升级为导入溯源判定：先收集每个模块内由 selkies 导入绑定的名字（含别名与 from-import 的模块/类名），再对这些根名字的任意深度 1 属性赋值与 setattr 一律判违规，并补注入试探用例证明四种拼写均被逮住且现有包零误报。现在没做的原因：该守护属测试基础设施增强，溯源分析需谨慎处理误报边界，独立立项比在 t063 收尾轮内仓促改写更稳妥。
- 处理：764fed0；resolution=resolved；reason=不立项直接改主分支：AC-004 AST 守护升级为导入溯源判定，四种漏网拼写全部逮住、现有包零误报；单文件 19 passed、全量 unit 2279 passed
- 时间：2026-11-15T00:00:00+08:00

## 开发铁律重判与修复（2026-11-15）

- 重判：原守护按「根标识符含 `selkies` 子串」判定，四种拼写漏网 = **假绿灯**。按「发现设计缺陷必须从根因修正、拒绝局部补丁」，不是补几个字符串 case，而是换成导入溯源判定。
- 修复（`tests/unit/test_t063_patched_keyboard_behavior.py`）：弃用子串启发式，改两遍式——先收集每个模块由 selkies 导入绑定的名字（含别名、from-import 的模块/类名），再沿 `Attribute` 链追溯到根 `Name` 判定 `Assign` / `AugAssign` / `AnnAssign` 目标与 `setattr` 首参，根名命中即违规。抽成 `_selkies_root_names` / `_is_selkies_attribute_write` / `_selkies_guard_violations`，试探用例直调生产守护函数。原有 `inspect` 禁用、`SUPPORTED_SELKIES_VERSION` / 私有 ABI gate 检查全部保留。
- 覆盖：四种漏网拼写（全点路径 `selkies.__main__.WebRTCService = f`、from-import 别名、裸类名、短别名 `setattr`）注入试探全部逮住；「含 selkies 子串但无导入」反证不误报；真实 `stream_agent` 包扫描零违规。
- 验证：单文件 19 passed / 0 failed；全量 unit 2279 passed / 5 skipped / 0 failed。未改产品代码、未删任何现有断言。

## 本地补验证据（gate4，历史）

- 判定：`tests/unit/test_t063_patched_keyboard_behavior.py` 的 AC-004 AST 守护升级为导入溯源判定（收集 selkies 导入绑定名、任意深度属性赋值与 setattr 判违规、补四种拼写注入试探用例），属测试基础设施增强，不属带 Docker/真实 Chrome 的本地验证事项；本批次不授权改测试源码。
- 现状：gate4 `unit 2243/0` 全绿，现有守护当前零误报、stream_agent 包无实际违规；四种拼写漏网（全点路径 / from-import 别名 / 直接属性 / `setattr`）仍存在，需独立 task 处理误报边界后方可升级。
- 卡点：无本地环境卡点，纯属工作量与立项顺序。
