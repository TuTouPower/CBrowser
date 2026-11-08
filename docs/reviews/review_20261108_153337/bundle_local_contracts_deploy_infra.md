# bundle_local_contracts_deploy_infra

## responsibilities

- 定义跨服务通信契约（OpenAPI v1/internal, JSON Schema: runtime_agent, supervisor_protocol, stream_protocol）
- 提供单机 Docker 编排配置（compose.yaml）、环境变量范本（.env.example）及运行时 Dockerfile
- 提供版本发布、回滚与网络初始化控制器（deploy_v2.sh）
- 提供代码规范与门禁检查脚本（run_gates.sh, gate_evidence_manifest.py, verify_frontend_dist.py 等）

## interfaces

- schemas/openapi/cbrowser_v1.json, cbrowser_internal.json
- schemas/runtime/agent_protocol.json, supervisor_protocol.json
- schemas/stream/agent_protocol.json
- CLI scripts/deploy_v2.sh {deploy|rollback|status}
- CLI scripts/run_gates.sh

## dependencies

- Docker Compose v2
- Caddy 2-alpine
- Python 3.15 + uv
- Pydantic v2
- FastAPI

## flows

- 发布流：deploy_v2.sh deploy 验证前置 -> 生成 0600 凭据 -> 写入初始网络配置与 Caddyfile -> 构建运行时镜像 -> 生成不可变 release.env -> compose up --wait -> 容器内 readiness probe -> 原子更新 current_release
- 协议导出流：scripts/export\_\*.py 读取模型 -> 导出标准 JSON Schema / OpenAPI Spec

## constraints

- 不可变发布（Immutable Release），失败不覆盖旧版本指针
- 零静态 Caddyfile 入库，网络配置由不可变版本确定性生成
- 依赖全量锁定：pyproject.toml 经 uv 导出 requirements.txt

## decisions

- Supervisor 作为容器内命令探针入口（docker compose exec），宿主机不开放管理端口
- Caddyfile 与前端 dist 指纹注入环境变量，由 compose 差异对比触发重建

## evidence

- compose.yaml:10-143
- scripts/deploy_v2.sh:357-517
- scripts/export_supervisor_protocol.py:15-48
- scripts/export_stream_protocol.py:24-30
- config/docker/supervisor_runtime/Dockerfile:1-32

## uncertainties

## Findings

- [High][95] scripts/export_supervisor_protocol.py:15-48 — Supervisor 协议导出脚本与实际 RPC 端点模型严重漂移，遗漏 8 个关键请求/响应模型

    - ID: f_contracts_supervisor_protocol_drift; verification: static
    - Evidence: export_supervisor_protocol.py 的 \_MESSAGES 仅包含 14 个模型，遗漏了 RebuildEdgeRequest, ConvergeStreamsRequest, PreviewPolicySyncResponse, CloseTunnelsRequest, CloseTunnelsResponse, AttendantDialogsResponse, AnswerAttendantDialogRequest, AnswerAttendantDialogResponse
    - Impact: 跨服务 RPC 契约文件与真实实现脱节，导致网络动态切换、隧道关闭与弹窗响应协议缺少 Schema 规格定义
    - Fix: 在 \_MESSAGES 中补齐上述 8 个模型或自动内省 protocol.py 中所有 BaseModel 子类并重新导出

- [High][95] scripts/export_stream_protocol.py:24-30 — Stream 信令协议导出脚本遗漏 AgentHumanInputTakeoverEnvelope 核心信令

    - ID: f_contracts_stream_protocol_drift; verification: static
    - Evidence: src/backend/cbrowser/stream_agent/protocol.py:311 定义了 AgentHumanInputTakeoverEnvelope，但 export_stream_protocol.py 未包含该消息
    - Impact: 人工接管控制流协议脱离契约权威，网关无法通过官方 Schema 验证接管数据包
    - Fix: 将 AgentHumanInputTakeoverEnvelope 加入导出脚本的 \_MESSAGES 并重新生成 Schema

- [High][90] scripts/deploy_v2.sh:503-508 — 重新部署脚本读取已应用网络配置时遗漏提取 https_port，导致自定义端口被重置

    - ID: f_deploy_script_bind_port_drop; verification: static
    - Evidence: deploy_v2.sh:503 注释声明提取 bind host 与 https port，但实际代码仅 grep 了 bind_host，未读取 https_port; 后续直接回退到默认值 HTTPS_PORT=56661
    - Impact: 用户在 Web 控制台修改了网络端口后，执行 deploy 升级会导致端口被强行重置回默认 56661，破坏配置持久性
    - Fix: 在 deploy_v2.sh 中增加从 applied_network_version.json 解析 https_port 并同步更新环境变量

- [Medium][85] scripts/deploy_v2.sh:455-501 — deploy_v2.sh 内联硬编码 Caddyfile 与配置 JSON 模板，违反单一事实源原则

    - ID: f_deploy_script_inline_caddyfile; verification: static
    - Evidence: deploy_v2.sh 使用 cat \<< EOF 在 Bash 中手写生成初始 Caddyfile 与 applied_network_version.json，且 caddyfile_sha256 硬编码为空字符串; 与 Python 模块 network_config.py 形成双生成器分歧
    - Impact: Caddyfile 逻辑演进时初次部署与动态 apply 产生行为漂移，且落盘配置中的哈希值为伪值
    - Fix: 调用 python3 -m cbrowser.network_config 生成初始配置与 Caddyfile，废除 Bash 内联模板

- [High][90] config/docker/supervisor_runtime/Dockerfile:1-32; compose.yaml:71-76 — supervisor_runtime 镜像与编排以 root 用户运行且未进行能力剥离

    - ID: f_docker_supervisor_root_cap; verification: static
    - Evidence: Dockerfile 无 USER 指令默认 UID 0，compose.yaml 未声明 cap_drop: [ALL]，且只读挂载了 /var/run/docker.sock; Unix socket 在 Linux VFS 中不受只读挂载限制，Supervisor 拥有对 Docker 守护进程的未受限访问权
    - Impact: Supervisor 容器若存在漏洞，攻击者可借助 root 身份与 docker socket 直接逃逸接管宿主机
    - Fix: 引入 socket proxy 限制 Docker API 方法，或通过 user namespace 与严格 capabilities 最小化剥离权限

- [Medium][85] config/docker/browser_runtime/Dockerfile:105 — browser_runtime 镜像复制全量后端源码，导致沙箱环境代码最小化原则失效

    - ID: f_docker_browser_copy_all_backend; verification: static
    - Evidence: browser_runtime Dockerfile 执行 COPY src/backend/cbrowser /app/src/backend/cbrowser，将全量后端代码打入浏览器镜像
    - Impact: 浏览器容器直面不受信外部 Web 内容，一旦发生逃逸，攻击者可在沙箱内直接读取 Supervisor、Gateway 与 API 模块源码
    - Fix: 采用白名单复制，仅将 runtime_agent/, domain/, font_sets/ 等必需模块复制进镜像

- [Medium][85] compose.yaml:28,58,100 — compose.yaml 未做密钥隔离，全量挂载 SECRETS_DIR 导致凭据越权可读

    - ID: f_compose_secrets_dir_overexpose; verification: static
    - Evidence: api, gateway, supervisor 均挂载了相同的 /run/secrets:ro 目录，目录内包含 admin_password, supervisor_key 等全部 5 个密钥; gateway 与 api 运行 UID 同为 1000，gateway 可读取非属自身的 admin_password 与 supervisor_key
    - Impact: 违背最小权限原则，若面对公网的网关容器受损，攻击者可盗取最高特权的管理员凭据
    - Fix: 在 compose 中改为精确挂载单文件，或将不同角色的密钥物理放置于不同子目录

- [Low][80] config/docker/automation_probe/Dockerfile:5-6 — automation_probe Dockerfile 硬编码特定架构 arm64 deb 安装包

    - ID: f_docker_automation_probe_arm64_deb; verification: static
    - Evidence: Dockerfile 直接 ADD 了 xautomation_1.09-4_arm64.deb
    - Impact: 在 x86_64/amd64 主机上构建 probe 镜像将直接失败或安装错误架构二进制，破坏跨平台 CI
    - Fix: 改用 apt-get install -y xautomation 或基于 TARGETARCH 参数动态选择安装包

## views

```json
{
  "security": {
    "status": "completed",
    "reviewer": "agent_contracts_deploy_infra"
  },
  "correctness": {
    "status": "completed",
    "reviewer": "agent_contracts_deploy_infra"
  },
  "contracts": {
    "status": "completed",
    "reviewer": "agent_contracts_deploy_infra"
  },
  "performance": {
    "status": "completed",
    "reviewer": "agent_contracts_deploy_infra"
  },
  "design": {
    "status": "completed",
    "reviewer": "agent_contracts_deploy_infra"
  },
  "robustness": {
    "status": "completed",
    "reviewer": "agent_contracts_deploy_infra"
  },
  "tests": {
    "status": "completed",
    "reviewer": "agent_contracts_deploy_infra"
  },
  "documentation": {
    "status": "completed",
    "reviewer": "agent_contracts_deploy_infra"
  }
}
```

## files_reviewed

```json
[
  ".env.example",
  ".gitattributes",
  ".gitignore",
  ".md_kx.toml",
  ".mise.toml",
  ".prettierignore",
  ".worktreeinclude",
  "BINARY-LICENSE.md",
  "LICENSE",
  "compose.yaml",
  "config/docker/api_runtime/Dockerfile",
  "config/docker/api_runtime/Dockerfile.dockerignore",
  "config/docker/api_runtime/requirements.txt",
  "config/docker/automation_probe/Dockerfile",
  "config/docker/automation_probe/Dockerfile.dockerignore",
  "config/docker/browser_runtime/Dockerfile",
  "config/docker/browser_runtime/Dockerfile.dockerignore",
  "config/docker/browser_runtime/entrypoint.sh",
  "config/docker/browser_runtime/requirements.txt",
  "config/docker/gateway_runtime/Dockerfile",
  "config/docker/gateway_runtime/Dockerfile.dockerignore",
  "config/docker/gateway_runtime/requirements.txt",
  "config/docker/stream_runtime/Dockerfile",
  "config/docker/stream_runtime/Dockerfile.dockerignore",
  "config/docker/stream_runtime/entrypoint.sh",
  "config/docker/stream_runtime/requirements.txt",
  "config/docker/supervisor_runtime/Dockerfile",
  "config/docker/supervisor_runtime/Dockerfile.dockerignore",
  "config/docker/supervisor_runtime/requirements.txt",
  "config/selkies/selkies_web_sha256.txt",
  "pyproject.toml",
  "schemas/openapi/cbrowser_internal.json",
  "schemas/openapi/cbrowser_v1.json",
  "schemas/runtime/agent_protocol.json",
  "schemas/runtime/supervisor_protocol.json",
  "schemas/stream/agent_protocol.json",
  "scripts/deploy_v2.sh",
  "scripts/export_openapi.py",
  "scripts/export_runtime_agent_protocol.py",
  "scripts/export_stream_protocol.py",
  "scripts/export_supervisor_protocol.py",
  "scripts/gate-requirements.txt",
  "scripts/gate_container_cleanup.py",
  "scripts/gate_evidence_manifest.py",
  "scripts/generate_requirements.sh",
  "scripts/import_font_set.py",
  "scripts/merge_junit.py",
  "scripts/redact_evidence.py",
  "scripts/run_automation_probe.sh",
  "scripts/run_gates.sh",
  "scripts/supervisor_readiness_probe.py",
  "scripts/vendor_selkies_web.py",
  "scripts/verify_frontend_dist.py",
  "scripts/verify_image_packages.py",
  "scripts/write_frontend_build_stamp.py"
]
```
