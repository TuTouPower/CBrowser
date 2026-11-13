# p088 URL 驱动的 session-to-tab 反向入口

- 来源：2026-11-13 同类项目技术调研（`.scratch/reports/隐私浏览器同类项目技术调研.md` P2-17），借鉴 Kasm RBI `kasm_url` / `/go?kasm_url=`
- 内容：提供 Caddy 路由 + 前端 postMessage，在既有 Profile 会话内打开目标 URL、创建/切换对应 tab 并激活 viewer；只在 resume 既有会话时触发，不静默新建 Profile。Kasm 的 seamless browsing 工作流是拦截原请求 → 重定向到隔离平台并把原 URL 编码进 `kasm_url` → 隔离容器内浏览器打开该 URL；本条只取「反向入口」这一交互形态，不引入前向代理改写。本次为只读调研，未授权改生产代码。
- 处理：未开
- 时间：2026-11-13T19:16:54+08:00
- 关联：p076（per-tab targetId 映射，共用同一张表）、p075（Caddy 路由与鉴权收口）、p037（archive，LAN/HTTP 切换）、p053（parked，LAN 多设备，不复活）

## 安全前置

URL 参数必须绑定已认证会话，防开放重定向与跨 Profile 越权；不得因 URL 驱动入口绕过 p075 的 forward_auth 与 p084 的 CDP 边界。

## 验收

1. 经反向入口打开 URL 时复用既有会话与 Profile，不新建 Profile、不重置身份。
2. 目标 tab 被正确创建/切换并激活 viewer，与 p076 的 target 映射一致。
3. 未认证会话或跨 Profile 目标 URL 被拒绝，有负向测试。
