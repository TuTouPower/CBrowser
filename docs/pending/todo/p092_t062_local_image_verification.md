# p092 t062 合入前本地真实镜像补验（AC-005 deploy 链）

- 来源：t062 遗留（云端无 Docker，AC-005 的真实构建部分无法执行）
- 内容：t062 已在云端 finish（实现完成，中立包与镜像边界的云端可验部分经单元层闭包测试与双路 review 验证），但下列事项只能在带 Docker 的本地环境（Mac）验证，合入主干前须补跑并留证：
    1. AC-005 [deploy]：按改后 Dockerfile 构建全部运行镜像（api/gateway/supervisor/browser/stream），各镜像独立启动并 readiness 就绪；重点确认 Gateway 镜像（删除 domain 与 Supervisor 文件后）与 Supervisor 镜像（删除 Gateway 整包后）真实启动无导入失败，Browser 镜像新增 shared 整包后 runtime_agent 全功能（字体/预览/egress 探针）正常。
    2. AC-008 真实贯穿：固定默认端口（8005）与一组非默认控制端口各跑一次部署，CLI/runner/compose/控制客户端行为一致。
    3. 与本地 t068 及 e2e 修复线的合入顺序由主会话安排；本 pending 只登记验证事项，不授权跳过。
- 处理：AC-005 镜像链已补验；AC-008 双端口部署未跑，未闭环
- 时间：2026-11-14T19:07:00+08:00

## 本地补验证据（gate4）

- 已验：按 `8c1148c` 源码重建全部 verify 镜像（api/gateway/supervisor/browser/stream + caddy/proxy-forwarder/probe/invalid-policy，均固定 sha256）；gate4 `image_packages=0`（5 运行镜像 pip 包与 uv.lock 对齐，含受控 `selkies==2.2.1+cbrowser.1`）、`real_engine 2 passed`、`unit 2243/0`、`integration 208/0`；E2E 全量拓扑中 api/gateway/supervisor/browser/stream 容器均真实启动并 readiness 通过（Gateway 删 domain/Supervisor 删 Gateway 整包后无导入失败，Browser 带 shared 整包启动正常）。
- 卡点：AC-008 要求「默认端口 8005 与一组非默认控制端口各跑一次完整部署，CLI/runner/compose/控制客户端行为一致」，需两次 `scripts/deploy.sh` 部署；本批未启动生产栈，未验。本项第 3 条「与 t068/e2e 修复线合入顺序由主会话安排」已由 `da2974d`/`ee94faf` 在终局门禁中完成合入，不授权跳过。
