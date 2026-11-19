---
pid: "p147"
slug: "real_engine_probe_font_fixture"
status: "closed"
resolution: "transferred"
reason: "已核实真实引擎夹具的缺失输入并转交任务"
fix_ref: "t092"
---
# p147 真实引擎探针缺少字体集绑定与只读挂载

- 现象：从当前 Browser 候选镜像重建 Linux arm64 探针镜像后，`scripts/run_automation_probe.sh` 通过预检，链路与级别探测两条用例均失败。链路中的三个真实引擎子用例及级别探测均报 `FontConfigUnavailableError: font_set_unavailable`。
- 影响：t032 独立真实引擎门禁无法验证目标引擎链路、对话框和级别行为。
- 根因：独立探针夹具没有满足当前 BrowserRunner 启动契约。`run_automation_probe.sh` 未向容器的 `/run/cbrowser/fonts` 提供字体集，`tests/fixtures/automation_probe/harness.py::write_profile_snapshot` 也未给快照绑定 `font_set_id`。`run_levels.py` 和目标引擎链路共用该快照函数，因而在 BrowserRunner 校验字体集时停止。常规 Docker E2E 的字体夹具由 t088 单独修复（p145）。
- 测试缺口：常规 E2E 仅收集这两条用例，由 `CBROWSER_T029_PROBE_E2E` 跳过。独立探针应复用已有的最小字体集准备逻辑、挂载有效 manifest 和字体文件，并让快照绑定同一套件。预检应尽早报告字体输入缺口，正式复跑要求两条真实引擎用例均通过且无跳过。
- 线索：`.scratch/t032_probe_rebuilt_46Scq0/evidence.json`、`.scratch/t032_probe_rebuilt_46Scq0/probe.xml` 和子用例 `chain.xml`。
- 处理：t092；resolution=transferred；reason=已核实真实引擎夹具的缺失输入并转交任务
