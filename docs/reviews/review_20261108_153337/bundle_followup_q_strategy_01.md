# bundle_followup_q_strategy_01

## Summary

精查证实：E2E 测试套件中确实硬编码了 macOS 路径 /Applications/Google Chrome.app，且缺少针对 Linux 常见路径与环境变量的探测回退。但在部署脚本 deploy_v2.sh 与容器 Dockerfile 中，均基于标准 Debian/Alpine Linux 环境构建，运行容器本身具备跨平台能力。问题主要局限于宿主测试与执行器层，确需解耦以满足跨平台 CI 战略要求。

## Findings

No findings.

## evidence

```json
[
  "tests/e2e/conftest.py:27 HOST_CHROME_PATH = Path('/Applications/Google Chrome.app/Contents/MacOS/Google Chrome')",
  "tests/e2e/test_stream_runtime_e2e.py:39 CHROME_PATH = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'",
  "scripts/deploy_v2.sh 使用标准 Docker 命令，无 macOS 专属命令依赖",
  "config/docker/ 全部 Dockerfile 均基于 debian:bookworm-slim 或 alpine:3.21，无平台硬编码（除 automation_probe 的 arm64 deb 包）"
]
```

## result

```json
"confirmed"
```
