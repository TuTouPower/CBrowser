# bundle_local_backend_stream_gateway

## responsibilities

- 作为信令网关（Stream Gateway），维护 Stream Agent 动态注册表（心跳、会话鉴权、状态监控）
- 代理外部前端 ViewerConnection 与后端沙箱的 WebRTC 信令会话（SDP/ICE 双向转发），维持长连接隧道
- 在 Stream 沙箱内运行 StreamAgent，与 Gateway 长连接协同，向上游 Selkies 注入 Controller Token
- 执行 Profile 级别 8/30 FPS 动态帧率仲裁（LiveCapturePolicyAgent）、静止降频、后台纯黑/暂停捕获、前台恢复
- 通过 X11 键位热同步补丁（x11_keymap）保障输入法及特殊键分发与 Selkies 键盘 ABI 校验
- 管理 UDP 多路复用端口（30000–30991）及网络配置（network_config.py, launch_args.py）

## interfaces

- GET /gateway/v1/health 网关健康探针
- GET /stream/agent/register Stream Agent WebSocket 注册端点
- GET /stream/{profile_id}/signal 浏览器 Viewer WebRTC 信令 WebSocket 隧道
- GET /gateway/v1/internal/profiles/{profile_id}/visibility Supervisor 内部前台可见性与渲染状态
- POST /gateway/v1/internal/profiles/{profile_id}/quota Supervisor 动态 FPS 配额下发
- POST /gateway/v1/internal/profiles/{profile_id}/disconnect 内部强制踢出 Viewer 隧道

## dependencies

- aiohttp
- Pydantic v2
- Selkies 2.2.1 (WebRTC/GStreamer)
- X11 (Xlib, XKB, XTEST)

## flows

- 信令流：前端建立 /stream/{id}/signal WS -> Gateway 校验 Cookie 并调用 API viewer-authorize -> 向 Stream Agent 转发 tunnel open -> Stream Agent 连接本地 Selkies 18081 -> 注入 Token -> 双向桥接 SDP/ICE
- 仲裁流：用户页面在前台活动 -> Stream Agent 检测到输入或损坏帧 -> 提频至 30 FPS；无连接或后台 -> pause_screen_capture 停止抓屏节省资源

## constraints

- 同机直连，完全去除 TURN/coturn 依赖
- Stream 容器严禁挂载浏览器 User Data 目录、Docker Socket 及 SQLite 库
- Selkies Master Token 与 Controller Token 绝不透传至前端页面，前端仅持会话 Cookie

## decisions

- ADR 013: 移除 coturn，固定同机直连 host 模式
- ADR 022: Selkies 2.2.1 升级契约与 AST-based ABI 签名检测
- ADR 026: 局域网访问模式下 WebRTC host 候选绑定 0.0.0.0

## evidence

- src/backend/cbrowser/gateway/server.py:440-569,729-899
- src/backend/cbrowser/stream_agent/agent.py:344-473,567-653,850-950
- src/backend/cbrowser/stream_agent/policy.py:329-362,530-670
- src/backend/cbrowser/stream_agent/x11_keymap.py:40-115
- src/backend/cbrowser/udp_mux.py:13-40
- src/backend/cbrowser/preview.py:37-120

## uncertainties

## Findings

- [High][90] src/backend/cbrowser/gateway/server.py:731-760 — Gateway Viewer 信令限流使用 Caddy 代理 IP 导致跨用户连带拒绝服务

    - ID: f_gateway_viewer_throttle_proxy_ip; verification: static
    - Evidence: gateway/server.py:731 source = request.remote 获取客户端地址，并以此为 key 传入 authorization_throttle.allow(source, profile_id); 在反代架构下，request.remote 恒为 Caddy 容器 IP
    - Impact: 针对某 Profile 连续失败连接（如过期会话尝试 10 次）后直接封禁 Caddy IP，导致所有经由该反代访问该 Profile 的合法用户收到 429 报错，画面连接中断
    - Fix: 复用 resolve_client_ip 并传入 CBROWSER_TRUSTED_PROXY_CIDRS 解析真实客户端 IP

- [Medium][85] src/backend/cbrowser/stream_agent/agent.py:957; protocol.py:89; messaging.py:86-105 — tunnel_close_envelope 传递空 session_id 触发 Pydantic 校验异常

    - ID: f_stream_agent_tunnel_close_empty_session; verification: static
    - Evidence: protocol.py 中 agent_session_id 约束 min_length=1; agent.py:957 close_env = tunnel_close_envelope(..., session_id=self.agent_session_id or ''), 在未完成注册时传入空字符串触发 ValidationError
    - Impact: Worker 异常退出时由于校验失败直接抛错崩溃，无法正常向 Gateway 回传 1011 错误状态码
    - Fix: 在发送前校验 session_id，若为空则使用占位合法标识或在信封定义中允许关闭包放宽约束

- [Medium][85] src/backend/cbrowser/gateway/config.py:57-75 — Gateway 首次冷启动缺少 applied_network_version.json 导致 403 阻断

    - ID: f_gateway_missing_applied_network_403; verification: static
    - Evidence: gateway/config.py 中 allowed_origins 若未检测到 applied_network_version.json 文件，直接回退为默认空列表 []
    - Impact: 在本地开发、单测或未使用部署脚本预置文件的场景下，前端合法的 WebRTC 信令连接全部触发 403 Origin not allowed 阻断
    - Fix: 当配置文件不存在时，自动回退到默认本地白名单（https://127.0.0.1:56661, https://localhost:56661）

- [High][90] src/backend/cbrowser/stream_agent/x11_keymap.py:35-194 — 违反拒绝妥协铁律：使用 AST 源码解析与运行时 monkey-patch 私有类规避上游 Selkies 底层修复

    - ID: f_stream_agent_x11_keymap_monkeypatch; verification: static
    - Evidence: x11_keymap.py 包含 203 行代码，通过 Python ast 模块反编译 selkies.input_handler.\_XTestKeyboard.__init__ 源码以检查私有属性; 在 install_x11_keymap_refresh 中直接在内存中劫持替换 \_XTestKeyboard.prebind 等私有方法与内部属性; 违背核心架构铁律：'拒绝妥协：严禁使用临时补丁或局部修补来规避底层重构；发现设计缺陷时必须从根因修正，必要时彻底重构或重写'
    - Impact: 猴子补丁机制与脆弱的 AST 反射强耦合上游未公开私有实现细节，极易在上游微小变动或底层运行环境差异下发生非预期故障
    - Fix: 从根因解决：向上游 Selkies 项目提交流或定制构建包含 XKBCOMP 刷新支持的官方 wheel 包，彻底移除 AST 逆向与运行时 monkey-patch

## views

```json
{
  "security": {
    "status": "completed",
    "reviewer": "agent_backend_stream_gateway"
  },
  "correctness": {
    "status": "completed",
    "reviewer": "agent_backend_stream_gateway"
  },
  "contracts": {
    "status": "completed",
    "reviewer": "agent_backend_stream_gateway"
  },
  "performance": {
    "status": "completed",
    "reviewer": "agent_backend_stream_gateway"
  },
  "design": {
    "status": "completed",
    "reviewer": "agent_backend_stream_gateway"
  },
  "robustness": {
    "status": "completed",
    "reviewer": "agent_backend_stream_gateway"
  },
  "tests": {
    "status": "completed",
    "reviewer": "agent_backend_stream_gateway"
  },
  "documentation": {
    "status": "completed",
    "reviewer": "agent_backend_stream_gateway"
  }
}
```

## files_reviewed

```json
[
  "src/backend/cbrowser/adapters/database/artifact_repository.py",
  "src/backend/cbrowser/adapters/database/migrations.py",
  "src/backend/cbrowser/adapters/database/models.py",
  "src/backend/cbrowser/adapters/database/repository.py",
  "src/backend/cbrowser/adapters/database/session.py",
  "src/backend/cbrowser/adapters/filesystem/artifact_store.py",
  "src/backend/cbrowser/gateway/__init__.py",
  "src/backend/cbrowser/gateway/__main__.py",
  "src/backend/cbrowser/gateway/api_client.py",
  "src/backend/cbrowser/gateway/config.py",
  "src/backend/cbrowser/gateway/endpoint.py",
  "src/backend/cbrowser/gateway/registry.py",
  "src/backend/cbrowser/gateway/server.py",
  "src/backend/cbrowser/launch_args.py",
  "src/backend/cbrowser/network_config.py",
  "src/backend/cbrowser/preview.py",
  "src/backend/cbrowser/stream_agent/__init__.py",
  "src/backend/cbrowser/stream_agent/agent.py",
  "src/backend/cbrowser/stream_agent/boundary.py",
  "src/backend/cbrowser/stream_agent/config.py",
  "src/backend/cbrowser/stream_agent/messaging.py",
  "src/backend/cbrowser/stream_agent/policy.py",
  "src/backend/cbrowser/stream_agent/policy_rules.py",
  "src/backend/cbrowser/stream_agent/protocol.py",
  "src/backend/cbrowser/stream_agent/x11_keymap.py",
  "src/backend/cbrowser/udp_mux.py"
]
```
