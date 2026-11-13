# p075 会话路径鉴权收口到 Caddy forward_auth

- 来源：2026-11-13 同类项目技术调研（`.scratch/reports/隐私浏览器同类项目技术调研.md` P0-2、P2-19），借鉴 SealSkin 控制面/数据面分离与 Caddy `forward_auth`
- 内容：全仓 grep 无 `forward_auth`；鉴权在应用层（`gateway/server.py` Origin、`auth/dependencies.py` CSRF+Origin+session），Caddyfile 部署期生成、不入库。SealSkin 把鉴权、凭证注入、cookie 剥离、CSP 全部收口到 Caddy：会话容器不发布宿主端口，`/<session>/*` 每个请求经 `forward_auth` 问 `/internal/resolve_session/<id>` 后才反代，一次性 `access_token` 换路径作用域 `HttpOnly`/`Secure` cookie，`/internal/*` 在 public listener 被拒绝，官方明确「no code of an image runs on the origin that holds the cookie」。本次为只读调研，未授权改生产代码；涉及部署期生成的 Caddyfile 与鉴权链路，需专项 task 与真链 E2E。
- 处理：未开
- 时间：2026-11-13T19:16:54+08:00
- 关联：p025（archive，网关节流/身份复检）、p004（archive，Selkies profile tokens）、p054（archive，Root CA 文档批）、p053（parked，LAN + 根证书下载，用户已明确暂搁，本条不复活其范围）

## 目标

1. Caddy 对会话路径每请求发送 GET 克隆问控制面，放行后注入容器凭证、剥离浏览器 cookie、加「容器响应不得作为持凭证 origin 的页面运行」CSP；`/internal/*` 公网拒绝。
2. 一次性 token → 路径作用域 `HttpOnly`/`Secure` cookie，替代长期 token 放 URL（避免 `Referer`/历史/日志泄露）。
3. 补 `Sec-Fetch-Site`/`Origin` 来源校验、非 credentialed CORS、COOP + `frame-ancestors 'none'`、丢弃 `Service-Worker-Allowed`；一次性 token 用于 `/stream/*` 与 `/cdp`。
4. 本地 CA 信任显式化（`caddy trust` 或分发 root CA、`skip_install_trust` 让行为可预测）仅在与 p053 暂搁范围不冲突的前提下评估。

## 结构性差异（不可整条照搬）

SealSkin 不暴露的是 HTTP 端口；CBrowser 的 WebRTC 媒体必须把 UDP mux 发布到 `127.0.0.1`，把 DTLS-SRTP/UDP 塞进 `forward_auth` 会破坏媒体路径。「零宿主端口」只适用于 HTTP 部分。

## 验收

1. 未持有效会话 cookie 直接请求容器路径返回拒绝，且容器响应不作为持管理面凭证 origin 的页面运行。
2. `/internal/*` 从公网 listener 不可达。
3. 现有 Gateway 鉴权、WebRTC 首帧与 viewer 重连真链 E2E 不回归。
