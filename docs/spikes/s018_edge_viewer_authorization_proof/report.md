# Spike report

## 问题

viewer 握手（`GET /stream/{profileId}/signal`）的控制面授权应以何种证明形态落地，才能同时满足：

- Gateway 不接收 `cbrowser_session`（管理会话 Cookie 不得进入 Gateway 进程）；
- 来源可认证：伪造转发头、直连 Gateway 绕过边缘均不能伪造授权；
- 授权上下文绑定 Profile、Origin、会话时效与撤销；
- 官方 Selkies 同源客户端的连接表达式不变（浏览器只带 Cookie 打开同源 WebSocket，不新增前端取令牌流程）；
- WebSocket Upgrade 语义成立。

候选：A. Caddy `forward_auth` 可信内部证明（边缘向 API 解析、回注可信头）；B. 短期授权交换（前端先以 Cookie 向 API 换短期令牌，再以令牌建 WS）。

## 成功判据

- 两候选在来源认证、重放窗口、到期/撤销生效点、Upgrade 行为、客户端改动面五项上逐项有据对比；
- 选定方案的每一跳证明关系可由单元/契约测试机械验证（云端可跑部分），真实 Caddy/Chrome 链验证归 t064 的 [deploy] AC-006。

## 尝试

- 阅读现行实现：Gateway `handle_viewer_signal` 直接读 `cbrowser_session` 并经内部端点 `/api/v1/internal/gateway/viewer-authorize` 把 Cookie 原文转发 API 校验（`src/backend/cbrowser/gateway/server.py`、`src/backend/cbrowser/gateway/api_client.py`、`src/backend/cbrowser/api/internal_gateway.py`、`src/backend/cbrowser/auth/service.py` 的 `authorize_viewer`）。
- 阅读现行边缘：`generate_caddyfile`（`src/backend/cbrowser/network_config.py`）仅 `handle /api/*`、`handle /stream/*` 两条裸反代，无 forward_auth、无头处理、无内部路径封锁。
- 对照 Caddy `forward_auth` 语义：子请求复制原请求头（含 Cookie、Origin）并附 `X-Forwarded-Uri` 等转发头直达 auth 上游，不重入站点路由；auth 响应 2xx 时按 `copy_headers` 把指定响应头写回待代理请求，非 2xx 直接以该状态回复客户端且不代理。子请求在代理与 Upgrade 之前完成，WebSocket 握手（HTTP GET + Upgrade）同样适用。
- 对照仓内既有跨服务证明形态：`cbrowser/shared/agent_credentials.py`（t062 中立模块）的 HMAC 派生令牌与 `hmac.compare_digest` 校验；秘密文件经 `read_secret_file`（≥32 字节）供给的一对一关系秘密（`gateway_api_key`、`agent_key` 等）。

## 证据

- 方案 B 与 task 非范围冲突：官方客户端经 `/selkies/` 同源 iframe 建联，表达式语义要求保留（task.md 非范围明示不改同源官方客户端）；B 要求前端在建联前多一步取令牌并把令牌带进 WS（URL 查询或子协议头），令牌进 URL 会落入访问日志，且改变官方客户端的连接发起方式。
- 方案 A 下 Cookie 只到边缘与 API：Caddy 对 signal 路由删除待代理请求的整个 `Cookie` 头（该路由无任何合法 Cookie 用途），Gateway 收到的请求中不存在 `cbrowser_session`，可由 Caddyfile 渲染契约测试与 Gateway 集成测试（带 Cookie 无证明头仍 401）双向验证。
- 来源认证分两跳、互不共用秘密：第一跳 Caddy→API 以部署秘密 `edge_proof_key` 呈现 `X-CBrowser-Edge-Proof` 头（Caddy 经进程环境变量持有，API 经秘密文件校验），且 Caddy 站点路由对外部请求显式 404 `/api/v1/internal/*`，解析端点在外部 listener 不可达；直达 API 的伪造调用缺证明头恒 403。第二跳 API→Gateway 为短期授权凭证（grant）：API 在校验会话/Origin/Profile 后以 `viewer_grant_key`（API 与 Gateway 共享的秘密文件）签发 HMAC 凭证，claims 仅含版本、profile_id、到期时间与随机 grant id，不含会话标识原文；Gateway 以同一秘密校验签名、到期与路径 Profile 一致性。内网直连 Gateway 者无密钥可伪造，伪造/过期/跨 Profile 在 Gateway 本地恒拒。
- 重放与时效：grant 有效期 60 秒且绑定单一 Profile，重放窗口与权力均严格小于会话 Cookie 本身（长期、跨 Profile 通用）；每次握手（含重连）都重走 forward_auth → API 按当前会话状态重新判定，退出登录/会话撤销在下一次握手立即生效，已建立连接不受影响（与现行 authorize_viewer 的握手期语义一致）。
- 撤销/到期的判定点唯一：会话有效性只由 API 的 `AuthService.authorize_viewer` 判定（现行逻辑复用，不复制第二份）；Gateway 不再经内部端点转发 Cookie，旧端点与 `GatewayApiClient.authorize_viewer` 随本方案删除。

## 结论

采纳方案 A：Caddy `forward_auth`（边缘证明头）＋ API 签发短期 HMAC viewer grant 回注、Gateway 本地验签。两跳秘密按仓内既有一对一秘密文件模式新增 `edge_proof_key`、`viewer_grant_key`，由 deploy.sh `ensure_internal_secrets` 生成。grant 的签发/校验实现落 `cbrowser/shared/` 中立模块（t062 边界），由 API 与 Gateway 共同消费。可信度：设计层结论由代码走读与 Caddy 官方 forward_auth 语义支撑；云端以单元/契约/集成测试验证每一跳的拒绝与放行，真实 Caddy/Chrome 链（Upgrade 实穿、Cookie 实剥离）属 [deploy] AC-006，合入后本地补验并登记为 p094。

## 是否采纳

- 决定：是
- 理由：唯一同时满足「Gateway 不接收会话 Cookie、来源双跳可认证、官方客户端零改动、撤销在握手点生效」的方案；方案 B 与非范围冲突且令牌落日志面更大。
- 后续 task：t064
- 无需后续理由：不适用

## 关联 findings

- findings.py 在本基线被既存编号重复阻断（`docs/findings/` 内 d037、d038 各存在两条不同条目，`findings.py new` 扫描时拒绝分配新号；该重复非本 task 引入，与 t062 执行时所遇为同一基线缺陷）。结论以本报告与 task.md 未知契约清单回填为准，编号修复后可补抽 dNNN。
