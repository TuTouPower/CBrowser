# bundle_followup_q_architecture_02

## Summary

精查证实：仓内不存在 tests 之外的 v2 五服务可执行装配，t012 以 backlog 原文记录其为未启动工作；v2 API 无生产 Dockerfile（其唯一镜像定义是测试 fixture）为新 Medium。

## Findings

- [Medium][90] tests/fixtures/supervisor_container_probe/api_runtime.Dockerfile；docs/guides/supervisor_validation.md:19 — v2 API 常驻服务的唯一镜像定义是测试 fixture，验证指南将其列为正式构建入口
  - ID: f_followup_q_architecture_02_01; verification: static
  - Evidence: 全仓 Dockerfile 清单核对：config/docker/ 下有 supervisor/gateway/stream/browser 四个 v2 runtime 的生产 Dockerfile，唯独 API 没有；API 镜像定义仅存在于 tests/fixtures/supervisor_container_probe/api_runtime.Dockerfile。; docs/guides/supervisor_validation.md:19 将该 fixture Dockerfile 与 supervisor 生产 Dockerfile 并列为『三个构建入口』，未标注其测试属性。
  - Impact: 生产与测试的边界在 API 这一常驻服务上完全重合：任何想在 fixture 之外运行 v2 的人只能借用测试镜像定义（其依赖与上下文按测试需要裁剪，如指南所述为 arm64 冷启动补 greenlet），且没有生产侧的版本/钉版治理点；这也是 f_global_architecture_03『拓扑只存在于 fixture』的一个具体锚点。
  - Fix: 在 t012 落地前，至少把 API 的生产 Dockerfile 迁入 config/docker/api_runtime/ 并让 fixture 改为消费它（或显式继承），使五个常驻服务的镜像定义同处一地、同一治理方式。（验证：config/docker/ 下出现 api_runtime/Dockerfile；fixture 改为引用它；指南同步更新构建入口清单。）

## evidence

```json
[
  "全仓只有一个 compose 文件：根 compose.yaml，单服务 cbrowser（image cbrowser:latest，build config/docker/Dockerfile），entrypoint.sh:27 执行 uvicorn backend.main:app——即 legacy 单容器，与五服务拓扑无关。",
  "五服务拓扑（api/supervisor/gateway/coturn/caddy）在全仓只实现了一次：tests/fixtures/gateway_probe/topology.py（文件头自述 'Real Docker container graph topology for Gateway, API, Supervisor, coturn, Caddy'），经 docker-py containers.run 逐个拉起，镜像 ID 全部由 CBROWSER_*_TEST_IMAGE / CBROWSER_API_TEST_IMAGE / CBROWSER_GATEWAY_IMAGE / CBROWSER_SUPERVISOR_TEST_IMAGE 环境变量注入且断言为 sha256 digest，secret 在 _init_dirs_and_secrets 中按运行临时生成——这是测试夹具的形态，不是用户可执行的部署工件。",
  "生产侧 Caddy 配置与 coturn 配置均不存在：全仓 Caddyfile 只有 tests/fixtures/gateway_probe/caddyfile.py（生成器），turnserver 相关只有 docs/archive/spikes 的 start_coturn.sh 原型脚本；config/ 下无 Caddyfile、无 turnserver.conf。",
  "v2 API 服务在生产侧连镜像定义都没有：全仓 Dockerfile 清单中 config/docker/ 只有 legacy Dockerfile 与 browser/gateway/stream/supervisor 四个 *_runtime；API 镜像的唯一定义是 tests/fixtures/supervisor_container_probe/api_runtime.Dockerfile，docs/guides/supervisor_validation.md:19 亦把该 fixture Dockerfile 列为『三个构建入口』之一。",
  "scripts/ 只有 export_openapi/export_*_protocol/vendor_selkies_web/verify_frontend_dist 等导出与校验工具，无任何启动/编排脚本；无 Makefile/justfile/Taskfile；.github/workflows 不构建任何 *_runtime 镜像。",
  "面向用户的文档只有 legacy 路径：README『快速上手』与 DOCKER_DEPLOYMENT.md 均只给出根 compose 的 docker compose up；docs/guides 的四份指南是单镜像构建 + 验证探针的 validation 文档（browser_runtime_validation.md 只构建 browser_runtime 一个镜像做本机校验），不含五服务装配步骤。",
  "仓库自身把正式装配记为未开工的未来工作：docs/tasks/t012_v2_docker_release/task.md 范围明列『正式compose/五服务镜像、Caddy/coturn配置』，note.md 状态为 backlog（depends_on t011），AC-001（全新数据根用正式 compose 启动五常驻服务）未勾选。",
  "git 历史检索（--all，含删除文件）未出现过 v2 compose、Caddyfile 或 turnserver.conf 的增删记录；compose 相关提交均为 legacy compose 的改名/重组。"
]
```

## result

```json
"confirmed"
```

## limitations

```json
[
  "静态检索结论：无法排除开发者本机存在仓外私有脚本——但问题问的是仓内工件，仓外脚本不改变『仓库不含可执行装配』的结论。",
  "git 历史仅按路径模式（*compose*/Caddyfile*/turnserver*）与删除文件名检索，未逐提交审计全部历史内容。"
]
```
