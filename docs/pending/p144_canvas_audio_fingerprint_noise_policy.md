---
pid: "p144"
slug: "canvas_audio_fingerprint_noise_policy"
status: "closed"
resolution: "transferred"
reason: "已核实固定引擎噪声策略和真实验证方式，并转交 t086"
fix_ref: "t086"
---
# p144 固定引擎默认注入 Canvas 和音频指纹噪声

- 现象：使用当前固定 CloakBrowser 构建启动两个新 Windows 环境（美国 #76、日本 #77），均设英文、关闭中文字体，检测页仍报告 Canvas 或音频读值带噪声。两个环境分别用独立探针确认，两项实际读值都有变化。预期是按明确运行策略控制这两类读值。
- 影响：已实测旧日区和两个新 Windows 环境。默认噪声出自共同的浏览器启动路径，和环境创建时间、代理地区及中文字体开关无直接关系。其他平台经同一入口继承引擎默认，具体 API 表现尚未实测。
- 根因：产品缺少显式噪声策略。`runtime_agent/runner.py` 的唯一生产启动路径把种子、平台和其他参数传给 `launch_persistent_context_async`，未传噪声策略，固定构建继承引擎默认注入行为。`launch_args.py` 对高级参数的白名单会拒绝 `--fingerprint-noise=false`。隔离环境使用同一固定引擎、Windows 平台、同一 seed `352614`、同一东京时区和日语做对照，单独增加该参数后，固定 Canvas 棋盘逐像素和离线音频常量逐样本恢复准确。
- 修复方向：在统一运行入口明确关闭引擎噪声，继续传递现有 Profile seed 及平台等配置，保留用户参数白名单。确认相关引擎接口的读值影响，并记录隐私取舍。关闭噪声后，固定渲染和音频特征可被站点更稳定地读取。单次对照仅证明关闭噪声时种子参数仍同时传入，其他由种子决定的输出需按各自契约验收。
- 测试缺口：运行层伪 SDK 测试（`tests/unit/test_egress_plan_and_runner_sdk.py`）已有生产入口的参数采集，缺少噪声策略断言。现有 `fingerprint_verification/tls_capture.py` 主要采集 Canvas 和音频读值作为指纹；一致或可复现的签名仍可能来自注入噪声。在生产启动入口断言策略参数和原有 seed 同时传入，并经固定引擎对本地页面检查预期 RGBA 像素和常量音频样本。记录代理路径与直连路径的结果，对未经实测的平台标明覆盖边界。
- 线索：`.scratch/jp_profile_identity_research/probe_engine.py` 与 `.scratch/jp_profile_identity_research/engine_results.jsonl` 保留固定引擎对照。`.scratch/new_profile_comparison/us_raw_probe.json`、`.scratch/new_profile_comparison/jp_raw_probe.json` 保留两个新环境的实测读值。
- 处理：t086；resolution=transferred；reason=已核实固定引擎噪声策略和真实验证方式，并转交 t086
