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
|**跨服务中立实现**|端点/Origin、Agent 凭证、原子写、per-profile 锁、投递分类、实例 fence、出口探针 I/O|`src/backend/cbrowser/shared/`（除 `secret_files` 叶子外零 cbrowser import，见 architecture §5.6）|
|**前端 API 类型**|由 OpenAPI 生成的 TypeScript 接口|`src/frontend/src/shared/api/generated/`|
|**数据库 schema**|SQLAlchemy ORM Models、Alembic 迁移脚本|`src/backend/cbrowser/adapters/database/models.py`、`src/backend/migrations/versions/`|
|**配置 schema**|运行时配置验证、环境变量定义|`src/backend/cbrowser/*/config.py`、`config/`|
|**文档/元数据 schema**|task front matter、状态机 JSON 校验|`.repo_template/docs/task_template/`|

## 3. 路径与隐私规范

- 当前全部 tracked 文本与未跟踪且未忽略的新文件（含归档）不得出现开发者家目录绝对路径（`/Users/<name>/`、`/home/<name>/`）；容器内固定用户（`cbrowser`/`appuser`/`selkies` 等）与 `/tmp` 路径不受限。该约定由 `tests/unit/test_repo_hygiene.py` 守护。
- 归档 spike 只作历史证据，不在仓库内运行；先复制到 `.scratch/`，探针秘密与工作目录不得入库。
- **产品无代际标识（t051）**：默认数据根、现行文档、源码与脚本不得出现产品代际自指，模式清单见 `tests/unit/test_t051_generation_hygiene.py` 的 `PATTERNS`；例外仅 `scripts/deploy.sh` 的旧库探测（AC-004，须写出真实旧路径）与对应断言。协议版本（Stream/Agent `version="v2"`）、库版本（Pydantic v2、SQLAlchemy 2.x）、API `version="2.0.0"` 与 SemVer 发布头不在此限。
- **部署身份与前缀（t051）**：部署输入的资源 prefix 须匹配 `^[a-z0-9][a-z0-9_]*$`（不含连字符），由 deploy.sh 与 Supervisor 启动在任何 Docker 操作前校验；默认部署前缀为 `cbrowser-t005`（编译内既定标识，不在校验之列，DockerAdapter 构造不校验）；部署身份为确定性 `instance_id`，归属判定只凭 `com.cbrowser.instance-id` 标签值 == 本实例 instance_id（该键即部署身份键；运行时实例 id 写入容器运行时配置，不走标签）。

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
后端运行时同理且只有一份实现：`from cbrowser.shared.atomic_write import atomic_write_text`（独占临时文件 + fsync + replace + 目录 fsync；失败不破坏旧文件、不误删他人暂存）。禁止在服务包内再写原子写变体；无法整载荷落盘的流式写（如 artifact 上传）为例外，但必须满足同一耐久契约（fsync + replace + 目录 fsync）。

## 6. DESIGN.md 落点与业务代码只用语义 token（t036）

- 设计权威为仓库根 `DESIGN.md`（google-labs-code/design.md alpha 格式）；颜色、字体、字号、间距、圆角与组件只在其中定义。`npm run design:tokens` 用 `@google/design.md@0.4.0` 的 `lint()` 确定性生成 `src/frontend/src/styles/design_tokens.css`（Tailwind 4 `@theme` 变量）并入库，禁止手改产物；`design:lint` / `design:check` 为门禁。
- 业务代码（`shared/ui/`、`app/`、`features/*` 页面与手写 `globals.css`）只用语义 token 类（`bg-surface`、`text-on-surface`、`border-outline`、`rounded-md`、`px-md` 等），禁止 Tailwind 默认调色板类与 hex / rgb / hsl / oklch 颜色字面量；由 AC-003 源码与构建产物扫描约束。生成产物 `design_tokens.css` 按设计权威含 hex，不列入业务源码扫描。
- 根目录 `DESIGN.md` 大写属社区约定例外；其余新建普通文件与目录统一 snake_case，缩进用空格。
- `.design_reference/` 为 gitignore 只读参考原型，与 plan / `DESIGN.md` 冲突时以后两者为准。

## 7. 统一错误契约（t056 A15）

- **形状唯一**：全部 API、Gateway 与 Supervisor 的错误响应体均为 `ErrorResponse`：`error`（机器可读码）/ `message`（人类可读说明）/ `retryable`（布尔）三字段，另可附结构化 `details`（任意 JSON，422 时为字段级错误列表）。**不得**再把整包错误详情嵌套进 `detail`（旧形状 `{"detail": {"code": ..., ...}}` 已删除）；`details` 只放顶层三字段之外的剩余键，`error` / `message` / `retryable` 不在 `details` 内重复。
- **429**：错误码固定 `rate_limited`，同时返回 `Retry-After` 响应头。
- **422**：字段级错误列表进 `details`，每项含 `loc` / `msg` / `type`；引用不存在的分组或代理属此类（见 domain.md「分组、代理与配置版本三分」）。
- **限流与冲突**：限流、冲突等业务错误同样走本形状（`proxy_in_use` 的 `used_by_count`、幂等冲突的 `idempotency_conflict` 均在 `details` 内）。
- **下游错误透传（t069 严格化）**：控制面只认本形状。Runtime Coordinator 记录的下游错误仅当响应体是合法 `ErrorResponse` 时保留其 `error` 与 `message`（格式 `"<error>: <message>"`），以 `last_coordinator_error` 呈现；旧形状 `detail`、纯文本体与缺字段响应一律判为协议错误，记稳定标记 `protocol_error: downstream response is not a valid ErrorResponse`，绝不作为合法业务结果解析。Supervisor 查 Gateway 可见性、agent_executor 控制调用同样只认本形状（非规范 503 判未知、非规范 409 抛 `control_protocol_error`）。解析实现唯一落点 `cbrowser/shared/error_response.py`，禁止各消费方自设兜底。
- **契约来源**：OpenAPI（`schemas/openapi/`）与前端生成类型（`src/frontend/src/shared/api/generated/`）由脚本重新生成，禁止手改；前端 `ApiError` 的旧 `detail` 字段已改为 `details`。
