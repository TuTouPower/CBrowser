# bundle_followup_q_architecture_01

## Summary

全仓核对（compose 文件、Dockerfile、docker 命令调用点、*_runtime 路径引用、部署类文件名、systemd/launchd/Makefile/其他编排器、scripts/、docs/guides、docs/tasks 现行三本任务书、blueprint、tests/fixtures 拓扑夹具）后确认：contracts_deploy 单元范围之外同样不存在可供运维者执行的 v2 五服务部署路径。仓库自身的规划与蓝图一致把正式编排定为 backlog 任务 t012 的待产出交付物（正式 compose、含 API 在内的全部生产镜像、Caddy 配置、单一权威拓扑定义），t012/t009/t010 三本任务书 status 均为 backlog 且部署相关 AC 全部未勾选；API 至今没有生产 Dockerfile（config/docker/ 只有 legacy 与四个 runtime 镜像），测试拓扑中的 API 容器用的是 tests/fixtures 下的夹具镜像。唯一接近反证条件的工件是 tests/fixtures/gateway_probe/topology.py 的 GatewayTopologyHarness：它能组装 Gateway+API+Supervisor+Caddy 的真实容器拓扑，但不构建任何镜像（六个镜像 ID 必须外部预构建后经 CBROWSER_* 环境变量注入）、API 为夹具镜像、拓扑是每轮 E2E 验证的临时实例并受 E2E 门禁约束，属测试基础设施而非部署工件，不满足『可实际执行的 v2 编排』口径。故『无部署路径』结论维持，f_global_architecture_01 不降级；但其措辞宜精确为『无面向运维的部署路径、五服务仅在 E2E 夹具拓扑中被组装过』。

## Findings

No findings.

## evidence

```json
[
  "全仓 compose 检索（find *compose*.yml / *compose*.yaml，排除 .git）：仅 ./compose.yaml 一份，其唯一服务为 legacy（config/docker/Dockerfile，image cbrowser:latest，127.0.0.1:56661:8080），无 profiles、无第二份 compose。",
  "config/docker/{browser,stream,gateway,supervisor}_runtime 四个 Dockerfile 路径在 config/docker 之外的全部引用（grep 全仓，排除 .git 与 docs/reviews/）：归档 task 书的写域声明（docs/archive/tasks/t003_v2_browser_runtime/task.md:11、t004_v2_stream_runtime/task.md:11 均明示主写域不包含『正式 compose』）、docs/blueprint/stream_runtime.md:9（正式网络、端口分配、Gateway 与认证由 t005/t006/t012 对接）、docs/guides/*_validation.md 的单镜像验证构建命令、tests/unit/test_baseline_runtime_regressions.py:23-65 的 Dockerfile 打包断言——无一处是可执行的部署编排。",
  "docs/blueprint/architecture.md:13 与 :21 为仓库自身定案：『Docker 编排、认证、媒体与前端由后续 task 实施……正式鉴权与交付分别由 t006/t012 验收』『Browser/Stream 的正式编排和入口切换仍由后续任务完成，独立组件测试通过不能代表整套部署完成』。",
  "docs/tasks/t012_v2_docker_release/task.md 契约区：『正式compose、全部常驻服务（含API）的生产镜像与Caddy配置……拓扑由单一权威定义产出并供测试夹具消费』是该 task 的待产出范围；其 note.md front matter status 为 backlog，AC-001/AC-002/AC-003/AC-005 全部未勾选（- [ ]）。docs/tasks/t009_v2_full_acceptance、t010_v2_data_migration 的 note.md status 同为 backlog，t010 的 [deploy] AC-010（本机正式部署并冒烟）未勾选。",
  "API 无生产镜像：config/docker/ 下只有 legacy Dockerfile 与 browser/stream/gateway/supervisor 四个 runtime Dockerfile；测试拓扑中的 API 容器使用夹具镜像 tests/fixtures/supervisor_container_probe/api_runtime.Dockerfile（经 CBROWSER_API_TEST_IMAGE 注入，见 docs/guides/supervisor_validation.md:17），t012 AC-002 把『全部常驻服务（含API）的生产镜像定义集中在config/docker/』列为未来验收项，反证其当前不存在。",
  "最接近的反证候选及其不成立理由：tests/fixtures/gateway_probe/topology.py:1 自述为『Real Docker container graph topology for Gateway, API, Supervisor and Caddy』，GatewayTopologyHarness（:61-83）以 docker-py 组装真实容器，但 browser/stream/gateway/supervisor/api/caddy 六个镜像全部经 _get_image 从 CBROWSER_* 环境变量读取外部预构建的不可变镜像 ID、harness 自身不做任何构建；且其拓扑为 Gateway E2E 验证的每轮临时实例（随机密钥、临时数据根、受 require_e2e_env 门禁），用途与形态均属测试夹具，非部署脚本或任务交付物。t012 AC-005『测试夹具改为消费正式拓扑定义』被列为未来目标，亦反证当前夹具不消费任何正式部署定义。",
  "指南中的可执行命令仅到单镜像验证构建为止：docs/guides/browser_runtime_validation.md:12-13 给出 docker build -f config/docker/browser_runtime/Dockerfile -t cbrowser-runtime:local-test 的验证构建；docs/guides/stream_runtime_validation.md:8、supervisor_validation.md:19 描述的均为构建后取镜像 ID 供 E2E 注入，无任何把五服务组装为常驻部署的命令或步骤。",
  "阴性检索范围：仓库无 *.service / *.plist / Makefile / justfile；kubectl、helm、ansible、terraform、podman、launchctl 在源码、脚本与文档中零命中；scripts/ 仅含四个 schema 导出器、run_gates.sh、vendor_selkies_web.py 与前端 dist 校验/戳记脚本，无部署脚本；以 deploy 命名的文件仅 DOCKER_DEPLOYMENT.md（内容为 legacy 单容器，按 f_contracts_deploy_05 与现状矛盾）。",
  "全仓 docker build/run/compose 调用点（*.py/*.sh/*.md/*.yaml/*.toml，排除 .git 与 reviews 目录）：生产面只有 DOCKER_DEPLOYMENT.md:64-107 的 legacy docker compose 命令；其余均为 docs/archive/spikes/ 下使用各自 spike Dockerfile 的一次性实验脚本（s001 run_spike.sh、s004/s009 start_containers.sh 等）与归档 task review 中按任务临时构建的 :e2e 测试镜像记录，均非 v2 正式运行时的部署路径。"
]
```

## result

```json
"refuted"
```
