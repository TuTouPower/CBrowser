# p022 t020 黑盒用例待在真实环境执行（AC-001 镜像 fc 断言 / AC-003 / AC-004 / AC-005 渲染断言）

- 来源：t020 遗留（实施环境为云 VM，无 Docker、无同机 Mac Chrome）
- 内容：t020 新增 e2e 用例 `tests/e2e/test_browser_font_bundles_e2e.py`（image_layout、render 三档、双 Profile isolation）已编写并通过收集，但从未在真实环境执行：按用户 2026-11-03 指令黑盒跳过并按 pass 计，AC-001 的镜像 `fc-list`/`fc-match` 条款与 AC-003/AC-004/AC-005 的真实 Chrome 渲染条款为 trust_prior。实施侧替代验证已完成：从 Debian bookworm 官方源下载 `fonts-wqy-microhei`/`fonts-wqy-zenhei` 两个 .deb 核实包内 `.ttc` 路径与体积；在本机 fontconfig 上以生成的 profile fontconfig 文件实测默认不可见、单包可见、双包互不串扰。需在具备 OrbStack Docker + 当前源构建的 Browser 镜像 + 引擎缓存的环境运行 `CBROWSER_RUN_E2E=1 scripts/run_gates.sh`，至少单独执行该文件全部用例并保存 evidence（镜像内 fc 输出、三档 canvas 度量/CDP 平台字体族、双 Profile 隔离结果）。执行后把结果回填本条目并归档。
- 处理：t032；resolution=transferred；reason=已核实为仍有效的真实环境执行债，并聚合转交本地最终验收 t032；task 内按原来源列出镜像/媒体/字体/API/运行时/前端/打包证据映射，不新建重复实现 task，不延用 skip/trust_prior 为 PASS。
