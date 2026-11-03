# bundle_followup_q_architecture_03

## Summary

静态核对了 viewer 接入的完整调用链：浏览器 Origin 头 → Gateway handle_viewer_signal → GatewayApiClient.authorize_viewer → API 内部端点 viewer_authorize → AuthService.authorize_viewer。结论：Gateway 转发的不是原始头，而是 normalize_origin 的输出。server.py:478 取原始头到 raw_origin 后，:480 立即 origin = normalize_origin(raw_origin)，此后 raw_origin 不再被使用；:484 先用该规范化值对 Gateway 自身白名单（config 加载时已由 normalize_origins 规范化）做校验，:497 再把同一个规范化值传给 api.authorize_viewer。api_client.py:54-68 将 origin 原样放入 JSON body，无二次变换、也不重读原始头；internal_gateway.py 的 ViewerAuthorizeRequest.origin 是无校验器的纯 str 字段，handler 把 payload.origin 原样交给 AuthService。比对的另一侧同样是规范化值：api/app.py:89-91 在启动时以 normalize_origins 生成 app.state.allowed_origins。因此 auth/service.py:310 的未规范化精确比对（origin not in allowed_origins）实际比较的是两个规范化值：带默认端口或尾斜杠的合法 Origin 在 Gateway 侧已被 endpoint.py:13-28 的 normalize_origin 归一（剥默认端口 80/443、host 小写、路径仅允许空或 '/' 故尾斜杠不保留），不可能因该比对被误拒。全仓检索确认生产环境中 /viewer-authorize 的唯一调用方就是这条 Gateway 链（其余命中均为 tests），不存在绕过规范化的转发路径。故 f_backend_api_auth_02 不是实际可用性缺陷，降为纯口径/分层一致性问题：AuthService.authorize_viewer 本层不做规范化、隐性依赖所有调用方预先规范化，目前唯一调用链满足该前提，若未来新增直达调用方传入原始头才会误拒——属潜在一致性隐患而非现存缺陷。

## Findings

No findings.

## evidence

```json
[
  "src/backend/cbrowser/gateway/server.py:478-484 — raw_origin = request.headers.get('Origin','') 后立即 origin = normalize_origin(raw_origin)，规范化失败返回 403，再以 origin 对 config.allowed_origins 做白名单校验",
  "src/backend/cbrowser/gateway/server.py:497 — allowed, reason = await api.authorize_viewer(session_cookie, origin, profile_id)，转发的是规范化后的 origin 变量而非 raw_origin",
  "src/backend/cbrowser/gateway/api_client.py:54-68 — authorize_viewer 将 origin 原样写入 JSON body {'origin': origin} 发往 /api/v1/internal/gateway/viewer-authorize，无二次变换",
  "src/backend/cbrowser/gateway/endpoint.py:13-28 — normalize_origin 返回 scheme://host[:非默认端口]：剥离默认端口（80/443）、host 转小写、path 只允许 '' 或 '/'（尾斜杠不保留）、拒绝凭据/query/fragment",
  "src/backend/cbrowser/api/internal_gateway.py:57-63,101-107 — ViewerAuthorizeRequest.origin 为无 validator 的 str 字段；viewer_authorize handler 将 payload.origin 原样传入 auth_service.authorize_viewer，allowed_origins 取自 request.app.state",
  "src/backend/cbrowser/api/app.py:89-91 — app.state.allowed_origins = normalize_origins(raw_origins)，API 侧白名单在启动时已规范化",
  "src/backend/cbrowser/gateway/config.py:70-72 — Gateway 配置加载时 allowed_origins = normalize_origins(raw_origins)，Gateway 自身校验一侧亦为规范化列表",
  "src/backend/cbrowser/auth/service.py:298-311 — authorize_viewer 在 :310 以 if origin not in allowed_origins 做精确比对、本层不调用 normalize_origin（与 f_backend_api_auth_02 描述一致，但其两侧操作数实际均为规范化值）",
  "全仓 grep（src/ + tests/，viewer-authorize|authorize_viewer）：生产调用方仅 gateway/server.py:497 → gateway/api_client.py:58 一条链，其余命中均为 tests/integration 与 tests/unit，无绕过 Gateway 规范化的转发路径"
]
```

## result

```json
"refuted"
```
