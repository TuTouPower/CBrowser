# p023 t021 黑盒用例待在真实环境执行（控制 API / 文件交换真实拓扑断言）

- 来源：t021 遗留（实施环境为云 VM，无 Docker、无用户局域网/Mac 环境）
- 内容：t021 的契约行为已由本机可跑门禁全量验证（模板契约 169、v2 unit 603、integration 105、前端 97 + build，失败均为基线存量同 ID）。未执行的是依赖真实拓扑的黑盒条款：`CBROWSER_RUN_E2E=1` 的 E2E 套件（真实 Chrome 容器下载事件→Supervisor 转发→API 入库全链、删除意图在真实进程重启后的续跑、Gateway 经真实 Origin 归一化的 viewer 授权；另含在构建产物（镜像/wheel 布局）中 import `cbrowser.runtime_event_log` 并调用 `emit_runtime_event_log` 一次的打包级验证（本机测试以源码布局运行，打包布局未验，见 review t021_test_f004）。按用户 2026-11-03 指令黑盒跳过并按 pass 计，上述真实环境条款为 trust_prior。需在具备 Docker + 当前源构建镜像的环境运行 `CBROWSER_RUN_E2E=1 scripts/run_gates.sh` 并保存 evidence（下载入库记录、重启后续跑删除结果、viewer 授权变体结果）。执行后把结果回填本条目并归档。
- 处理：t032；resolution=transferred；reason=已核实为仍有效的真实环境执行债，并聚合转交本地最终验收 t032；task 内按原来源列出镜像/媒体/字体/API/运行时/前端/打包证据映射，不新建重复实现 task，不延用 skip/trust_prior 为 PASS。
