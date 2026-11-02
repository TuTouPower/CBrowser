# bundle_followup_q_system_properties_03

## Summary

精查证实：fixtures 之外不存在用户可执行的 v2 五服务拉起路径，.env.example 无任何 v2 服务变量，『可部署但未文档化』不成立。

## Findings

No findings.

## evidence

```json
[
  "全仓唯一 compose 文件为根 compose.yaml：单服务、image cbrowser:latest、0.0.0.0:${CBROWSER_PORT:-56661}、entrypoint 执行 legacy backend.main:app。本审阅『根 compose 为唯一 compose 且入口为 legacy』的原始确认成立且完备。",
  "不存在任何引用 v2 runtime 镜像的非测试编排物：对 config/docker/*_runtime 的全仓引用检索显示，非测试引用只有各 Dockerfile 自身的 COPY 行、entrypoint 内部行与 docs/archive 的历史 handoff 记录；没有任何 compose 片段、启动脚本或 CI 步骤构建/运行 supervisor/gateway/stream/browser 四个生产 runtime 镜像。",
  "五服务完整形态（含数据卷与 secret 注入）只在 tests/fixtures/gateway_probe/topology.py 出现：镜像 ID 由 CBROWSER_*_TEST_IMAGE 等环境变量以 digest 形式注入，secret（supervisor/agent/gateway/gateway_api/turn 五类）在 _init_dirs_and_secrets 中按运行生成到临时目录——完整性是夹具内部的，不构成用户可执行路径。",
  "Caddy 与 coturn 在生产侧无配置工件：Caddyfile 仅有 tests/fixtures/gateway_probe/caddyfile.py 生成器；turnserver.conf 在非测试、非归档路径不存在。",
  ".env.example（21 行）不含任何 v2 服务变量（无 supervisor/gateway/turn/caddy/cbrowser.db 相关项），用户即使手工拼装也没有仓内给出的配置面。",
  "README 与 DOCKER_DEPLOYMENT.md 的部署说明只有 legacy compose 一条路径；docs/guides 四份文档均为 validation 指南（构建单个 runtime 镜像并跑探针），无五服务拉起步骤。",
  "仓内任务体系自述一致：docs/tasks/t012_v2_docker_release 状态 backlog，其范围正是『正式compose/五服务镜像、Caddy/coturn配置』与 AC-003 的部署文档演练，全部未完成——『v2 不可部署』不是文档遗漏，而是该交付物本身尚未生产。",
  "git 历史（--all，含删除记录）未出现 v2 编排文件的增删，排除『曾经有、后来删了』的可能。"
]
```

## result

```json
"confirmed"
```

## limitations

```json
[
  "静态检索结论：仓外（开发者本机）的私有编排脚本不在本问范围内，亦无法核查。",
  "git 历史按编排类路径模式检索，未逐提交全文审计。"
]
```
