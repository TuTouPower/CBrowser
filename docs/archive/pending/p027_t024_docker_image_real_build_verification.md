# p027 t024 Docker 镜像真实构建验证义务

- 来源：t024 遗留（AC-001、AC-015 的 Docker 门禁在本机无 Docker 环境跳过，按用户口径立此追踪）
- 内容：在有 Docker 的环境完成两项真实构建验证：(1) Supervisor 镜像按修正后的 `Dockerfile.dockerignore`（已补 `launch_args.py` 准入）隔离构建，确认镜像构建成功且运行时可导入 `cbrowser.launch_args`；(2) Stream 镜像按 AC-015 的 builder/runtime 分阶 Dockerfile 冷构建，确认最终镜像无构建工具链，并以真实媒体/输入/剪贴板场景验证精简后的运行时库集合完整。静态守卫已由 t024 的 `tests/unit/test_docker_build_contexts.py` 与 `tests/unit/test_runtime_image_hygiene.py` 覆盖，本条只欠真实构建与运行验证。
- 处理：t032；resolution=transferred；reason=已核实为仍有效的真实环境执行债，并聚合转交本地最终验收 t032；task 内按原来源列出镜像/媒体/字体/API/运行时/前端/打包证据映射，不新建重复实现 task，不延用 skip/trust_prior 为 PASS。
