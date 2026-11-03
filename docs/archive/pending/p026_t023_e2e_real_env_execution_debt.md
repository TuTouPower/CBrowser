# p026 t023 黑盒用例待在真实环境执行（前端会话 E2E 与测试宿主构建链）

- 来源：t023 遗留（实施环境为云 VM，无 Docker、无 Chrome、无用户局域网/Mac 环境）
- 内容：t023 的契约行为已由本机可跑门禁验证（模板契约 169、v2 unit 710 + 基线存量失败 2 条同 ID、integration 114 passed + 1 failed（失败为干净 base 同 ID 的存量项 `test_api_search_defaults_routes::test_retry_route_requires_csrf_and_maps_outcomes`，零新增）、前端 Vitest 27 文件 156 + test:types 零错误、生产 build PASS、dist 不含测试全局）。未执行的是依赖真实环境的条款，按用户 2026-11-03 豁免口径跳过按 pass 计：(1) `CBROWSER_RUN_E2E=1 scripts/run_gates.sh` 全套黑盒（`tests/e2e/test_frontend_app_e2e.py`、`test_frontend_session_e2e.py` 在真实容器拓扑 + 无头 Chrome 下验证会话挂载、语言切换不重置会话、SSE 代次隔离的真实链路行为）；(2) 迁移后的测试宿主构建链端到端（`tests/fixtures/frontend_probe/host_builder.py` 从新位置 `host_entry.tsx` 经 esbuild + NODE_PATH 打包 session.js 并由 harness 提供服务——本机已单独验证 esbuild 打包成功，完整 harness 运行需真实栈）。需在具备 Docker + 当前源构建镜像的环境执行并保存 evidence，结果回填本条目后归档。
- 处理：t032；resolution=transferred；reason=已核实为仍有效的真实环境执行债，并聚合转交本地最终验收 t032；task 内按原来源列出镜像/媒体/字体/API/运行时/前端/打包证据映射，不新建重复实现 task，不延用 skip/trust_prior 为 PASS。
