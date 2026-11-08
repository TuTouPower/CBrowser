# Browser Runtime 本机验证

本指南仅启动全新隔离测试容器，不部署正式系统，不读取 .env，不挂载现有 Profile。目标为 Mac OrbStack Linux arm64；公网及原生 Linux x86 执行按用户决定记 NOT_RUN / USER_WAIVED。

## 构建完整镜像

从仓库根目录执行，只把明确列出的源文件目录送入构建上下文，避免将 .env、用户数据或仓库 scratch 发送给 Docker：

```bash
set -euo pipefail
tar --exclude='__pycache__' -cf - \
  src/backend/cbrowser config/docker/browser_runtime tests/fixtures/runtime_probe \
  | docker build -f config/docker/browser_runtime/Dockerfile -t cbrowser-runtime:local-test -
export CBROWSER_RUNTIME_TEST_IMAGE="$(docker image inspect cbrowser-runtime:local-test --format '{{.Id}}')"
```

测试始终使用取得的不可变 image ID，不挂载宿主源码。镜像包含真正的 XShm 捕获探针；C 编译器及开发头文件只留在构建阶段，不进入运行阶段。

## 准备测试引擎缓存

已完成初始化的独立 Linux 缓存可以直接设置 CBROWSER_RUNTIME_ENGINE_CACHE。必须与待测镜像所用平台和 SDK build 对应，不能指向 Mac 原生 Chromium 或正式用户数据。Runtime 不负责下载或修复只读缓存。

若尚无测试缓存，在仓库内新建独立目录，确认容器 UID1000 可写后执行一次 SDK 初始化：

```bash
export CBROWSER_RUNTIME_ENGINE_CACHE="$PWD/.scratch/runtime_validation/engine-cache"
mkdir -p "$CBROWSER_RUNTIME_ENGINE_CACHE"
docker run --rm --name cbrowser-runtime-cache-init \
  --cap-drop ALL --security-opt no-new-privileges:true \
  --entrypoint python3 \
  -v "$CBROWSER_RUNTIME_ENGINE_CACHE:/data/engine-cache" \
  "$CBROWSER_RUNTIME_TEST_IMAGE" \
  -c 'from cloakbrowser.download import ensure_binary; ensure_binary()'
```

该步骤需要下载网络，仅写专属测试缓存。Linux 宿主若 UID 不同，先按实际所有权初始化这个新目录；不得对现有数据根递归 chmod/chown。Pro 许可证及选择的 build 由 Supervisor 初始化角色对接，指南不提供密钥或默认许可证。已初始化的 Pro 缓存可以通过 --engine-build 明确选择，实际许可运行须另行验证。

## 执行真实 E2E

先设置仓库内 TMPDIR、UV_CACHE_DIR，并使用 Python3.15+。项目声明的完整命令见 docs/blueprint/testing.md；专项运行：

```bash
export TMPDIR="$PWD/.scratch/runtime_validation/tmp"
export UV_CACHE_DIR="$PWD/.scratch/runtime_validation/uv_cache"
export PYTHONDONTWRITEBYTECODE=1
mkdir -p "$TMPDIR" "$UV_CACHE_DIR"
PYTHONPATH=src/backend uv run --no-project --python '>=3.15'   --with pytest --with pytest-asyncio --with fastapi --with pydantic   --with uvicorn --with httpx --with websockets --with cloakbrowser   pytest tests/e2e/test_browser_runtime_e2e.py     tests/e2e/test_runtime_profile_defaults_e2e.py -v
```

容器、桥接网络与新测试数据均使用独立随机标识。HTTP 夹具位于专属 Docker 网络，不监听宿主端口；浏览器仅发布 UDS，不映射 CDP TCP。测试结束清理自身容器及网络，失败容器日志保存在 .scratch/t003_implementation/tmp/logs，搜索设置场景保存在 .scratch/t003_profile_defaults。单元故障注入不等于真实断电；合成音频只用于校准，Profile 隔离以实际 Chrome WebAudio 录音测量。
