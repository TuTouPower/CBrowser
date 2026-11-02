# bundle_followup_q_architecture_04

## Summary

精查证实：会话面上的 Supervisor 上报挂载是纯冗余暴露——生产 Supervisor 只走内部面，前端从不调用会话面路径，唯一消费者是一个扮演 Supervisor 的验收测试（新 Low）。

## Findings

- [Low][90] tests/integration/test_v2_api_subprocess.py:485-698 — 规范级运行时收敛验收测试 (AC-003/AC-006) 经用户会话面行使 Supervisor 上报权, 把冗余暴露锁进测试基线
  - ID: f_followup_q_architecture_04_01; verification: static
  - Evidence: 该文件以管理员登录会话 (cbrowser_session) 调用 POST /api/v1/runtimes/bind|observed|events 模拟 Supervisor 上报 (行 485、495、544 等), 是全仓唯一使用会话面这三条路径的测试。; 其余 Supervisor 行为测试 (test_supervisor_rpc/manual_retry/status_truth 等) 均走 /api/v1/internal/supervisor 内部面, 证明同一语义完全可在内部面验收。; 后果: 摘除会话面挂载 (f_backend_api_auth_02 / f_global_architecture_02 的修复方向) 会先撞红这批 AC 级测试, 形成『为保测试而保留暴露』的反向锁定; 且该测试以用户会话成功伪造实例绑定与 observed 状态, 本身即是会话面越权的活体演示。
  - Impact: 抬高收敛授权边界的修复成本, 并使测试基线持续为冗余暴露背书; 若未来有人以『有测试在用』为由保留挂载, 暴露将长期化。
  - Fix: 将 test_v2_api_subprocess.py 中 bind/observed/events 调用迁至 /api/v1/internal/supervisor/* 并为其 server harness 配置 Supervisor 令牌 (其余用户面调用保持会话), 随后再从 profile_router 摘除这三条路由。

## evidence

```json
[
  "生产 Supervisor 只走内部面: supervisor/core.py:847 POST /api/v1/internal/supervisor/runtimes/bind、core.py:1245 POST /api/v1/internal/supervisor/runtimes/observed、supervisor/event_forwarder.py:165 POST /api/v1/internal/supervisor/runtimes/events; 内部面由 require_supervisor 的 Bearer 服务令牌守卫 (internal_supervisor.py:30-53), 复用的正是同一批 handler 函数 (internal_supervisor.py:57-99)。真实组件没有任何一处调用会话面路径。",
  "v2 前端手写代码零调用: 对 src/frontend/src 的 .ts/.tsx 全量检索 runtimes/bind|observed|events 无任何手写命中; 三条路径仅出现在生成物 shared/api/generated/cbrowser_v1.d.ts:198/215/232 与 schemas/openapi/cbrowser_v1.json:1347/1429/1511 中, 是 OpenAPI schema 的机械产物, UI 代码从不调用。",
  "会话面挂载形态: 三个 handler 定义在 profile_router 上 (api/v1/router.py:706-835), 该 router 唯一守卫为 require_csrf_and_origin + require_user_session (router.py:56), handler 自身无任何授权依赖; 经 app.py:333 的 v1_router 对外暴露为 /api/v1/runtimes/*, 且进入公开 OpenAPI schema (supervisor_router 则 include_in_schema=False, app.py:338)。",
  "测试按面分类: 全部 Supervisor 行为测试都用内部面前缀 —— tests/integration/test_supervisor_rpc.py:117/164、test_supervisor_manual_retry.py:21/101、test_supervisor_status_truth.py:62 均设 prefix=\"/api/v1/internal/supervisor\"; test_supervisor_observation_authority.py、test_normal_exit_replay.py、test_runtime_coordinator_integration.py 与 tests/e2e 全部 supervisor 套件同样只用内部面。",
  "会话面的唯一消费者是验收测试而非产品流程: tests/integration/test_v2_api_subprocess.py (AC-003/AC-006, 行 485-698) 经 /api/v1/auth/login 取得管理员会话 (tests/fixtures/api_auth.py:30-46, cbrowser_session cookie) 后, 用该会话对 /api/v1/runtimes/bind|observed|events 发请求, 内联注释自述其角色为 “Supervisor binds inst_1” —— 即用用户会话扮演 Supervisor, 属测试便利, 不是任何合法用户面流程。"
]
```

## result

```json
"confirmed"
```

## limitations

```json
[
  "静态检索结论: 未运行测试套件或服务进程, 调用方结论基于全仓 grep 分类与逐文件核对。",
  "仅核查本仓内消费者; 仓外调用方 (如上游 CloakBrowser-Manager 的客户端、未入库的运维脚本) 不在范围内, 但 docs/guides 与 docs/blueprint 中无任何对会话面 runtimes 路径的引用。"
]
```
