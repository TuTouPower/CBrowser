# CBrowser

CBrowser 是多身份与隐私隔离的浏览器管理系统，用于管理独立的浏览器会话、指纹、代理、Cookies 与历史记录。

本项目 Fork 自上游仓库 [CloakHQ/CloakBrowser-Manager](https://github.com/CloakHQ/CloakBrowser-Manager)，底层核心依赖 [PyPI: cloakbrowser](https://pypi.org/project/cloakbrowser/) 隐私指纹对抗引擎（支持过 Cloudflare Turnstile、reCAPTCHA v3、BrowserScan 等指纹检测）。

本项目遵循 `repo_template` 研发规范。工具链位于 `.repo_template/`，业务源码统一放置于 `src/`。

## 目录结构

```text
.
├── .repo_template/         # 模板工具链与契约门禁
├── .opencode/commands/     # 工作流快捷命令
├── config/                 # 配置文件（.env.example, Docker 构建配置）
├── compose.yaml            # Docker 服务拓扑编排
├── schemas/                # 跨服务接口契约
├── src/
│   ├── backend/            # FastAPI 服务端代码与测试
│   └── frontend/           # React + Vite 前端管理界面
├── tests/                  # 端到端与集成测试
└── docs/                   # 研发文档与蓝图（blueprint, specs, tasks, pending, guides, archive）
```

## 快速上手

### Docker 部署

```bash
# 复制环境变量配置
cp config/.env.example .env

# 构建并启动服务
docker compose up --build -d

# 查看服务日志
docker compose logs -f
```

启动前必须在 `.env` 中把 `AUTH_TOKEN` 设为随机值（例如 `openssl rand -hex 32`），留空等于关闭认证。服务只监听本机回环地址，启动后访问 `http://localhost:56661`，在登录弹窗中输入该值。

## 工作流与任务管理

```bash
# 查看任务状态
python3 .repo_template/scripts/task.py list

# 待办事项总账
python3 .repo_template/scripts/pending.py list

# 运行轻量契约测试
pytest .repo_template/tests -q -m contract
```

详细规范请参阅 [`AGENTS.md`](AGENTS.md) 与 [`DOCKER_DEPLOYMENT.md`](DOCKER_DEPLOYMENT.md)。
