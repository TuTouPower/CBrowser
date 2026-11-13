# p092 t062 合入前本地真实镜像补验（AC-005 deploy 链）

- 来源：t062 遗留（云端无 Docker，AC-005 的真实构建部分无法执行）
- 内容：t062 已在云端 finish（实现完成，中立包与镜像边界的云端可验部分经单元层闭包测试与双路 review 验证），但下列事项只能在带 Docker 的本地环境（Mac）验证，合入主干前须补跑并留证：
    1. AC-005 [deploy]：按改后 Dockerfile 构建全部运行镜像（api/gateway/supervisor/browser/stream），各镜像独立启动并 readiness 就绪；重点确认 Gateway 镜像（删除 domain 与 Supervisor 文件后）与 Supervisor 镜像（删除 Gateway 整包后）真实启动无导入失败，Browser 镜像新增 shared 整包后 runtime_agent 全功能（字体/预览/egress 探针）正常。
    2. AC-008 真实贯穿：固定默认端口（8005）与一组非默认控制端口各跑一次部署，CLI/runner/compose/控制客户端行为一致。
    3. 与本地 t068 及 e2e 修复线的合入顺序由主会话安排；本 pending 只登记验证事项，不授权跳过。
- 处理：未开
