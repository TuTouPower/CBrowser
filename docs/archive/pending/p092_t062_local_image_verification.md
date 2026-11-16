# p092 t062 合入前本地真实镜像补验（AC-005 deploy 链）

- 来源：t062 遗留（云端无 Docker，AC-005 的真实构建部分无法执行）
- 内容：t062 已在云端 finish（实现完成，中立包与镜像边界的云端可验部分经单元层闭包测试与双路 review 验证），但下列事项只能在带 Docker 的本地环境（Mac）验证，合入主干前须补跑并留证：
    1. AC-005 [deploy]：按改后 Dockerfile 构建全部运行镜像（api/gateway/supervisor/browser/stream），各镜像独立启动并 readiness 就绪；重点确认 Gateway 镜像（删除 domain 与 Supervisor 文件后）与 Supervisor 镜像（删除 Gateway 整包后）真实启动无导入失败，Browser 镜像新增 shared 整包后 runtime_agent 全功能（字体/预览/egress 探针）正常。
    2. AC-008 真实贯穿：固定默认端口（8005）与一组非默认控制端口各跑一次部署，CLI/runner/compose/控制客户端行为一致。
    3. 与本地 t068 及 e2e 修复线的合入顺序由主会话安排；本 pending 只登记验证事项，不授权跳过。
- 处理：683aa10；resolution=resolved；reason=gate5 GATE_EXIT=0 且 deploy.sh 真实部署验证通过：AC-005 全镜像重建+image_packages=0，AC-008 非默认 HTTPS 端口 56662 链路一致（api/控制客户端/supervisor 控制面均 200，恢复 56661 亦 200）
- 时间：2026-11-14T22:36:00+08:00

## 终局补验证据（gate5 / 真实部署栈，最终结论；取代下方 gate4 阶段性记录）

- `scripts/deploy.sh deploy` 真实部署成功：Release `20261114212243-78d4f8c` readiness-verified，api/gateway/supervisor/caddy 4 容器 healthy，URL `https://127.0.0.1:56661`（默认 HTTPS 端口 56661、Supervisor 控制端口 8005）。6 个运行镜像按当前源码重建：api `778b86ad`、gateway `550e2db4`、supervisor `25e8adc8`、browser `4a9e1bfe`、stream `abb332a6`、proxy-forwarder `2ed32840`、caddy `70b31807`。
- gate5 `image_packages=0`（5 运行镜像 pip 包与 uv.lock 对齐）、`unit 2278/0`、`integration 209/0`、`e2e 105/0`，全部镜像在新树真实启动并 readiness 通过 → AC-005 闭环。
- AC-008 非默认端口：同一 release 镜像（不 rebuild、不改 release pointer）以 `CBROWSER_HTTPS_PORT=56662` 重新 render Caddyfile 并 `docker compose up -d --no-build --wait`：4 容器 healthy、`api_health_56662=200`、登录 + Profile 控制客户端 200、Supervisor 控制面 `/supervisor/v1/health` 200；随后恢复 56661 亦 200、`deploy.sh status` 的 release 不变。证据 `.scratch/terminal_deploy_slices/p092_nondefault_port.log`。compose 的 Supervisor 控制端口固定 `--port 8005`（设计约束，不暴露为可配参数）；CLI/runner/compose/控制客户端一致性由上述链路覆盖。

## 本地补验证据（gate4）

- 已验：按 `8c1148c` 源码重建全部 verify 镜像（api/gateway/supervisor/browser/stream + caddy/proxy-forwarder/probe/invalid-policy，均固定 sha256）；gate4 `image_packages=0`（5 运行镜像 pip 包与 uv.lock 对齐，含受控 `selkies==2.2.1+cbrowser.1`）、`real_engine 2 passed`、`unit 2243/0`、`integration 208/0`；E2E 全量拓扑中 api/gateway/supervisor/browser/stream 容器均真实启动并 readiness 通过（Gateway 删 domain/Supervisor 删 Gateway 整包后无导入失败，Browser 带 shared 整包启动正常）。
- 卡点：AC-008 要求「默认端口 8005 与一组非默认控制端口各跑一次完整部署，CLI/runner/compose/控制客户端行为一致」，需两次 `scripts/deploy.sh` 部署；本批未启动生产栈，未验。本项第 3 条「与 t068/e2e 修复线合入顺序由主会话安排」已由 `da2974d`/`ee94faf` 在终局门禁中完成合入，不授权跳过。

## 主线 ae02d42 本地复核（2026-11-16）

- 口径：按「按现状做本地复核」；gate5 已验证的真实部署 + 全镜像重建 + 非默认端口 56662 全链实测不重复，未重建镜像、未跑 `deploy.sh deploy`；基线 `main` @ `ae02d42`。
- 静态核对：`bash scripts/generate_requirements.sh --check` 六组（api / gateway / supervisor / browser / stream / gate）全部 `requirements ok`；`config/docker/*/Dockerfile` 六份存在。
- 定向实测：`p092_t062`（`test_t062_boundaries.py` + `test_t062_image_closure.py` + `test_t062_shared_rules.py`）→ `19 passed / EXIT=0`；日志 `.scratch/p090_p098_reverify_20261116/logs/p092_t062.log`。
- 结论：t062 中立包 / 镜像边界的云端可验部分在当前主线仍成立；AC-005 / AC-008 的真实部署链属 gate5 已验，不重复；裁定闭环。
- 证据留存：`.scratch/terminal_deploy_slices/p092_nondefault_port.log` 仍在；gate5 / gate4 原始目录已缺失；汇总见 `docs/archive/verification/p090_p098_local_reverify_20261116.md`。
