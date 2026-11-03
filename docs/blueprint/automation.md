# 受控 CDP 自动化

外部自动化只经认证 WebSocket 进入 Supervisor，再由 Agent UDS 转发到浏览器回环 CDP；不发布任何 Browser CDP TCP 端口。

## 入口与鉴权

- 新建入口：`WS /api/v1/automation/profiles/{profileId}/cdp`。
- 旧入口薄适配：`WS /api/profiles/{profileId}/cdp`，同一处理器、同一 Bearer 凭证；不出现在 OpenAPI 中，不提供旧 CDP 端口映射。
- 自动化凭证由登录用户经 `POST /api/v1/automation/tokens` 创建，格式 `cbat_...`，只在创建响应返回明文；凭证限定可访问的 Profile。
- 客户端必须发送 `Authorization: Bearer <token>`；登录 Cookie 不被接受。Bearer 方案名大小写不敏感。
- 未授权、非授权 Profile、凭证撤销关闭码 4401；Supervisor 未配置或上游失败关闭 1011。
- 授权只经上述 v1 入口由 `AuthService.authorize_automation` 执行（t021）：内部 Gateway 面曾有的 `automation-authorize` RPC 无任何生产消费者，已整体删除（含 DTO 与内部 OpenAPI 条目）；Gateway 只调用 `viewer-authorize`。不得再新增平行的内部自动化授权面。

## 转发链

```text
external client
  -> API automation_router (token verify)
  -> Supervisor control WS /supervisor/v1/profiles/{id}/cdp (supervisor token, constant-time compare)
  -> Agent UDS /run/cbrowser/runtime/{profileId}/agent.sock (ws://localhost/cdp)
  -> Chrome loopback CDP
```

- API 只持有 Supervisor URL 与内部 token；不直接持有 Docker Socket。
- Supervisor 从 `core._sessions` 校验 Profile 处于 running，并经 `PathValidator` 校验 `agent.sock` 位于该 Profile 的 runtime 目录。
- 双向消息按文本/二进制原样透传；任一侧关闭即取消另一侧任务并关闭上游，避免半开隧道。
- 外部客户端断开后，Agent 重置并恢复默认下载捕获策略；随后真实下载仍进入 `/exchange/downloads` 并被 Artifact 链路捕获。

## 前端

`/automation/:profileId` 页面调用 `GET /api/v1/profiles/{profileId}/automation`，展示授权 WS 端点、运行状态、运行实例、Supervisor 配置状态与 Authorization 头格式；直接加载/刷新由认证守卫处理，不依赖前序页面状态。

## 验证

- 单元：Supervisor WS 到 UDS 的双向转发、缺失/错误 token 的 4401、大小写 Bearer。
- 集成：真实 API + Supervisor control uvicorn + UDS echo 的完整认证转发；API 状态接口；旧入口与新入口同样拒绝无效凭证。
- 真实 E2E：真实 Chrome 经 Agent UDS 执行 CDP 命令并触发下载，证明 loopback CDP 未被公网端口暴露。
