# p097 t063 AC-004 静态守护改为导入溯源判定（test 轴 Round 2 minor 遗留）

- 来源：t063 遗留（review_test Round 2 finding t063_test_f006，minor，不阻断 PASS）
- 内容：`tests/unit/test_t063_patched_keyboard_behavior.py` 的 AC-004 包级 AST 守护按「根标识符含 selkies 子串」判定 selkies 模块属性写入，Round 2 审阅实测四种拼写漏网：全点路径 `selkies.__main__.WebRTCService = f`、`from selkies import input_handler` 后 `input_handler._XTestKeyboard = f`、直接 `_XTestKeyboard.prebind = f`、短别名 `setattr(m, ...)`。当前 stream_agent 包经双路审阅实测干净、无实际违规，AC-004 现状不受影响；本项是把守护升级为导入溯源判定：先收集每个模块内由 selkies 导入绑定的名字（含别名与 from-import 的模块/类名），再对这些根名字的任意深度 1 属性赋值与 setattr 一律判违规，并补注入试探用例证明四种拼写均被逮住且现有包零误报。现在没做的原因：该守护属测试基础设施增强，溯源分析需谨慎处理误报边界，独立立项比在 t063 收尾轮内仓促改写更稳妥。
- 处理：未开
