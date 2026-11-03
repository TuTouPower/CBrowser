# p024 t022 黑盒用例待在真实环境执行（运行时恢复 / 网关信令 / keymap 真实调用证据）

- 来源：t022 遗留（实施环境为云 VM，无 Docker、无 Chrome、无用户局域网/Mac 环境）
- 内容：t022 的契约行为已由本机可跑门禁验证（模板契约 169、v2 unit 679、integration 111、前端 104 + build，失败仅基线存量 2 条同 ID）。未执行的是依赖真实环境的条款，按用户 2026-11-04 豁免口径跳过按 pass 计：(1) `CBROWSER_RUN_E2E=1 scripts/run_gates.sh` 全套黑盒（真实容器拓扑下 X11 helper 权限、缓存代次挂载、网络策略 DROP 兜底的真实生效）；(2) AC-014/A47 的真实调用证据——Selkies 2.1.0 在真实 X 会话中的 owner-loss、正常退出与 keymap 初始化顺序（tests/e2e/test_stream_x11_keymap_e2e.py 与 stream_probe 探针需真实镜像运行，本机仅完成 wheel 源码级 ABI 核对与适配层契约测试）；(3) AC-011/A39 的真实多 Agent 拓扑恢复（本机已由真实 Gateway + WS 客户端集成测试覆盖小桶语义，真实 Stream 容器集群下的 429/重启恢复未验）；(4) AC-016/A55 的真实重试链（Supervisor→Agent UDS→Runner 活 context 消费 search-defaults 重试，本机以契约与路由级测试覆盖，真实容器内端到端未验）。需在具备 Docker + 当前源构建镜像的环境执行并保存 evidence，结果回填本条目后归档。
- 处理：t032；resolution=transferred；reason=已核实为仍有效的真实环境执行债，并聚合转交本地最终验收 t032；task 内按原来源列出镜像/媒体/字体/API/运行时/前端/打包证据映射，不新建重复实现 task，不延用 skip/trust_prior 为 PASS。
