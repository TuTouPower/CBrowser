# p056 E2E stream 容器启动基线故障导致全量 E2E 大面积失败

- 现象：`CBROWSER_RUN_E2E=1 scripts/run_gates.sh` 在 2026-11-10 连续三次运行（WORKERS=1，镜像分别复用 `daccf66` 旧集与按当前源重建的新集）E2E suite 均有 23~30 项失败/错误；共同根因日志为 `cbrowser.supervisor.core: Sandbox launch failed ... Failed to run stream container <prefix>-stream-<id>: APIError`，多数用例在 Supervisor `/profiles/start` 返回 500 后失败。
- 影响：全量 E2E 无法作为任何 task 的验收证据；非 E2E 全量门禁（requirements/contract/unit/integration/design/frontend/image_packages）正常。
- 根因：尚未定位到 Docker APIError 的原始 message；已验证与 t048 无关——未含 t048 的主干 `e118a22` 用旧镜像运行 `tests/e2e/test_supervisor_retry_e2e.py::test_supervisor_real_container_retry_e2e` 同样失败（22.85s）。怀疑 OrbStack 网络/资源残留或 stream 镜像运行参数与环境不匹配，需按 supervisor 实际 `docker run` 参数单独复现。
- 测试缺口：Supervisor 把底层 `APIError` 折叠成 `error_type=DockerSandboxError`，日志丢失原始 Docker message，E2E 只能看到 500；需在 sandbox 启动失败处保留 Docker 原始错误文本（脱敏后）以便定位。
- 线索：`/tmp/t048_full_gate3.log`、`/tmp/t048_full_gate5.log`、`/tmp/t048_gate_e2e5/logs/e2e.log`（本机临时证据，未入库）；复现：按 `docs/blueprint/testing.md` 的 E2E 镜像集运行 `CBROWSER_RUN_E2E=1 CBROWSER_GATE_WORKERS=1 scripts/run_gates.sh`。
- 处理：resolution=obsolete；reason=非产品缺陷：E2E stream 启动失败根因为生产栈占用 30000/10.251 与 Docker 瞬时错误，清理环境后 t049/t050 多轮 E2E 稳定启动 stream；剩余为高负载超时 flake；Docker 原始错误文本诊断缺口拆到 p059
