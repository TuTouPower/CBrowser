# p044 t034 验证工具自动化接入与回归深度 follow-up

- 来源：t034 review 遗留（`t034_test_f002` / `t034_test_f004` / `t034_test_f005`，均 minor，不阻断 t034 PASS）。
- 内容：
    1. `scripts/generate_requirements.sh --check` 目前是开发者/CI 助手，未被 `run_gates.sh` 调用；AC-002 的漂移门禁由 `tests/unit/test_t034_dependency_lock.py` 在 unit suite 内承担（真调 `uv export --only-group` 逐组全等比对）。若把 `--check` 直接接入 `run_gates.sh` 的 suite 列表，会改变 `tests/unit/test_t028_run_gates_evidence.py` 的 stub 契约（其 `list(suites)` 断言固定），需按 TDD 规则整体重写该 stub 测试并新增覆盖，成本与收益不匹配；后续如需单一入口，同步调整两处并保留 stub 契约。`scripts/verify_image_packages.py` 的五镜像比对结果已落盘 `.scratch/evidence_t034c/image_packages/`，但未接入 E2E/deploy 自动路径。
    2. `pyproject.toml` 全局 `filterwarnings = ["ignore::DeprecationWarning"]` 与 task.md 测试策略「把 DeprecationWarning 视为错误」存在口径差；E2E 实测 3 条 `StarletteDeprecationWarning`（`HTTP_422_UNPROCESSABLE_ENTITY`，来自 starlette 1.10，非 t034 引入）。后续可新增定向 `-W error::DeprecationWarning` 检查并替换该常量，同时精确忽略已知第三方噪声。
    3. `tests/unit/test_t034_runtime_paths.py` 对动态 `find` 的回归是源码文本断言；后续补以 `docker.from_env()` 为边界的 mock 单测，断言 `exec_run` 命令含 `find`、`get_archive` 使用返回路径、异常时 `container.remove(force=True)`，并把文本断言升级为「不含 `python3.<minor>` 形式 site-packages 字面量」。
    4. `tests/fixtures/supervisor_container_probe/api_runtime.Dockerfile` 仍是 `python:3.12-slim-bookworm` 测试夹具（非 AC-001 的六个运行镜像、无构建引用），可对齐 3.15/trixie。
- 处理：未开。以上均为验证深度/工具接线增强，不改变 t034 已验证的产品行为与 six-AC 结论。
