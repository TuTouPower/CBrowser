> 与代码冲突时以代码与生效 spec 为准，并须同步修正本文。

# 约定（项目级）

模板流程的编号与 Markdown 格式见 `.repo_template/docs/usage.md`「命名与格式」。本文定义 CBrowser 项目特有的技术栈约定、代码规范与 schema 落点。

## 1. 技术栈与工具链约定

- **后端**：Python 3.15+，使用 `uv` 管理虚拟环境与依赖；依赖唯一锁定来源为根 `pyproject.toml` + `uv.lock`，各镜像与门禁的 requirements 由 `scripts/generate_requirements.sh` 按依赖组 `uv export` 生成，禁止手写并行依赖清单（t034）；Web 框架使用 FastAPI 与 Pydantic v2；ORM 统一使用 SQLAlchemy 2.1 异步/强类型语法；数据库迁移使用 Alembic。全部 Python 镜像基于 `python:3.15-slim-trixie` digest 固定，辅助阶段基于 `debian:trixie-slim` digest 固定；Caddy 基于 2.x digest 固定。
- **本地工具版本**：`.mise.toml` 固定 Node 26.13.0 与 Python 3.15.2；门禁与镜像主次版本一致。
- **前端**：TypeScript 5.9 + React 19.3，构建工具 Vite 8（Rolldown）；状态管理 TanStack Query 5，路由 `react-router` 8 单包（不再用 `react-router-dom`）；禁止前端手写与后端重复的 API 契约，统一通过 OpenAPI 生成类型。宿主构建 Node 固定 26 LTS（`.mise.toml`），`engines.node=">=26.0.0 <27"`。
- **TypeScript 版本例外**：因 `openapi-typescript@7.13.0` 的 peer 仍为 `typescript@^5.x`，TypeScript 不用最新 7.x，固定当前最高 5.x（5.9.3）；复查条件见 `docs/blueprint/decisions.md`「前端工具链目标版本（t033）」。
- **远程显示**：Selkies 2.2.1 官方稳定发布版本（t043 由 2.1.0 升级，ADR 022），纯 WebRTC 传输，不保留任何旧 RFB/VNC 链路；官方 Web 客户端由 `scripts/vendor_selkies_web.py` 按固定 wheel SHA256 解出，`config/selkies/selkies_web_sha256.txt` 由对应版本 wheel 生成。
- **容器与部署**：生产运行平台为 Linux Docker；本地开发验证支持 macOS (OrbStack)。

## 2. schema 类型落点

按消费方决定落点，`schemas/` 只放跨服务契约。

|类型|例子|落点|
|---|---|---|
|**跨服务接口契约**|OpenAPI 规范导出、Stream Gateway 信令协议|`schemas/openapi/`、`schemas/stream/`、`schemas/runtime/`|
|**代码内数据契约**|Pydantic model、API 请求/响应 DTO|`src/backend/cbrowser/domain/`|
|**前端 API 类型**|由 OpenAPI 生成的 TypeScript 接口|`src/frontend/src/shared/api/generated/`|
|**数据库 schema**|SQLAlchemy ORM Models、Alembic 迁移脚本|`src/backend/cbrowser/adapters/database/models.py`、`src/backend/migrations/versions/`|
|**配置 schema**|运行时配置验证、环境变量定义|`src/backend/cbrowser/*/config.py`、`config/`|
|**文档/元数据 schema**|task front matter、状态机 JSON 校验|`.repo_template/docs/task_template/`|

## 3. 路径与隐私规范

- 已跟踪的非归档文本文件不得出现开发者家目录绝对路径（`/Users/<name>/`、`/home/<name>/`）；容器内固定用户（`cbrowser`/`appuser`/`selkies` 等）与 `/tmp` 路径不受限。该约定由 `tests/unit/test_repo_hygiene.py` 守护。
- 归档 spike 只作历史证据，不在仓库内运行；先复制到 `.scratch/`，探针秘密与工作目录不得入库。

## 4. 编码与安全规范

1. **凭证保护**：禁止在代码、日志、数据库或 Docker 镜像中硬编码密码、JWT 密钥、CloakBrowser 许可证或代理账密。
2. **只读挂载**：容器沙箱内根文件系统必须为只读，仅对 `/tmp`、`/dev/shm` 以及 Profile 的挂载目录授予写权限。
3. **日志输出**：禁止使用 `print` / `console.log`，强制使用结构化日志组件；严禁记录剪贴板内容、输入法拼音、Cookie 或网页私密数据。
4. **代码格式化**：
    - Python 代码遵循 Ruff 规范，强制使用空格缩进（4 空格）。
    - 前端代码遵循 ESLint & Prettier 规范（2 空格）。
    - Markdown 文档统一使用 `md_kx` 格式化，表格使用 compact 格式。

## 5. 原子写原则

写权威/派生状态数据（`note.md` front matter、`docs/tasks_index.json`、`docs/pending/`、状态缓存等）必须走 tmp 文件 + fsync + `os.replace` 原子写，防止并发或异常断电导致文件损坏。
公共 helper：`from repo_task.documents import atomic_write_text`。
