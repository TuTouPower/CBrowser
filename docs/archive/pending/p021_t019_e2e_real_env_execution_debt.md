# p021 t019 黑盒用例待在真实环境执行（AC-001 候选集 / AC-002 时延执行证据）

- 来源：t019 遗留（test review finding t019_test_f001）
- 内容：t019 新增 e2e 用例 `tests/e2e/test_frontend_app_e2e.py::test_t019_switch_and_refresh_first_frame_within_2s_host_only` 已编写但从未在真实环境执行：实施环境为云 VM，无 Docker、无同机 Mac Chrome，按用户 2026-11-03 指令黑盒跳过并按 pass 计，AC-001 候选集条款与 AC-002 时延条款为 trust_prior。需在具备 OrbStack Docker + 真实 Browser/Stream 镜像 + 同机 Google Chrome 的环境运行 `CBROWSER_RUN_E2E=1 scripts/run_gates.sh`，至少单独执行该用例并保存 evidence（switch/refresh 首帧耗时与候选集快照）；同批回归既有媒体矩阵（多页面、复制标签、可见性暂停/恢复、断线 resume）在 ICE-lite 下的结果。执行后把结果回填本条目并归档。
- 处理：t032；resolution=transferred；reason=已核实为仍有效的真实环境执行债，并聚合转交本地最终验收 t032；task 内按原来源列出镜像/媒体/字体/API/运行时/前端/打包证据映射，不新建重复实现 task，不延用 skip/trust_prior 为 PASS。
