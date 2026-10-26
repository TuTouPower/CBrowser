# 测试

CBrowser 质量门禁与测试契约规范。章节名 `verification_policy` / `verification_notes` / `doctor_cmd` / `test_cmd` / `blackbox_verify` 是 preflight 与 skill 的机械锚点，不得改名；命令写在对应章节的代码块内，严格按 Bash 的 `-e -o pipefail` 执行。

## verification_policy

project_configured

## verification_notes

当前项目采用多层验证体系：

1. 模板与工作流工具链契约：通过运行 `.repo_template/tests`（带 `-m contract` 标记）验证 task 状态机、文档解析及仓库整洁度；
2. 业务后端单元测试：通过 `uv` 运行 `src/backend/tests`，涵盖 API 接口、鉴权、下载捕获、数据库及生命周期；
3. 容器黑盒与健康检查：通过 curl 检查运行中的容器健康探针 `http://127.0.0.1:56661/api/health`，并支持通过 ego-browser 执行端到端网页交互自动化验证。

## doctor_cmd

环境前置检查：契约测试可成功收集；另需 `md_kx` 在 PATH。

```bash
pytest .repo_template/tests -q --collect-only -m contract
command -v md_kx
```

## test_cmd

日常测试（红/绿）：模板契约测试与后端业务测试全部跑通。

```bash
pytest .repo_template/tests -q -m contract
PYTHONPATH=src uv run --with pytest --with pytest-asyncio --with fastapi --with pydantic --with httpx --with "cloakbrowser>=0.6.3" pytest src/backend/tests -q
```

## blackbox_verify

服务存活探针与任务状态自检：

```bash
curl -sf http://127.0.0.1:56661/api/health
python3 .repo_template/scripts/task.py list
python3 .repo_template/scripts/repo_sync.py status
```

## Schema / codegen 验证

项目涉及 OpenAPI 导出及前端类型。

- 触发路径：`src/backend/api/`
- 生成命令：无
- 验证命令：无
- 合并后动作：无
- migration 窗口：无

## 门禁类别清单

|类别|必须覆盖|常见盲区|
|---|---|---|
|**单元测试**|pytest 后端业务测试（384 tests）与前端 Vitest（49 tests）|mock 掉真实逻辑、假绿|
|**契约测试**|pytest 模板轻量契约测试（168 tests）|路径或状态机格式不匹配|
|**文档格式**|`python3 .repo_template/scripts/md_format.py --check`|遗漏 pre-commit 钩子|
|**容器黑盒**|容器健康检查与 ego-browser 网页端到端操控|只看进程存活、界面实际不可用|
