---
pid: "p145"
slug: "runtime_e2e_fixtures_require_deployed_mount_contract"
status: "closed"
resolution: "transferred"
reason: "已核实范围并转交 t088"
fix_ref: "t088"
---
# p145 真实 Docker E2E 夹具缺少当前启动所需字体绑定及卷子路径

- 现象：真实 Docker E2E 必需模式中，旧部署镜像可重复复现 `font_set_unavailable` 与 named volume 子路径 404。t086 初测非串行阶段 14 个失败用例，逐个对应用旧版镜像复跑，14 个仍失败。
- 影响：新 Browser 镜像无法获得全量 E2E 通过证据。已核对问题涉及 Profile 默认设置、下载和预览、Supervisor 生命周期、搜索默认项、启动策略、Stream 及 X11 权限真实链路。发布运行时可借实际挂载资产启动，通过发布链与 E2E 夹具形状存在差距。
- 根因：测试环境缺少当前产品硬约束。`test_runtime_profile_defaults_e2e.py` 直接构造 Runner 输入，缺少 t075 要求的字体绑定及挂载。`test_x11_helper_permissions_e2e.py` 构造宿主路径模拟旧 bind mount，适配器按 t080 从命名卷解析子路径，daemon 找不到 `x11`。`test_supervisor_cache_initialization_e2e.py` 可同类复现 `engine_cache/geoip` 子路径不存在。Supervisor 链上其他字体错误见记录，修复前逐个追到对应夹具。
- 测试缺口：让 E2E 复用正式部署的字体绑定和卷布局，用完整夹具验证真实 Browser 启动。保留独立负例覆盖缺失字体、缺少卷子路径以及错误路径拒绝。启动后再进各测试原有业务断言。
- 线索：`.scratch/runtime_identity_acceptance/repro_old_e2e.sh` 最小复现，`.scratch/runtime_identity_acceptance/old_release_e2e.log`、`.scratch/runtime_identity_acceptance/old_release_parallel_e2e.log` 为旧镜像证据，`.scratch/t086_all_gates/` 为候选镜像对照。
- 处理：t088；resolution=transferred；reason=已核实范围并转交 t088
