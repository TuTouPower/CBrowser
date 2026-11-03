# bundle_followup_q_architecture_02

## Summary

怀疑消解。核对范围：src/backend/cbrowser/api/internal_supervisor.py 全文（路由级依赖声明与 add_api_route 注册循环）、src/backend/cbrowser/api/app.py 的 include_router 与 contracted_openapi 后处理、仓内 FastAPI 版本钉版（config/docker/supervisor_runtime 与 browser_runtime 的 requirements.txt 均钉 fastapi==0.162.0；pyproject.toml 与 src/backend/requirements.txt 下限 fastapi>=0.115.0）、FastAPI 0.162.0 与 0.115.0 两个版本 routing.py 中 APIRouter.add_api_route 的官方源码、tests/integration/conftest.py 的 supervisor_api 夹具与 test_supervisor_rpc.py 全文，并全仓检索该面其余测试（test_v2_api_subprocess.py、test_supervisor_observation_authority.py 等）。结论有二：(1) 框架语义确定成立——add_api_route 在钉版 0.162.0（routing.py L5794/L5798/L5824）与下限 0.115.0（L1779）中都先以 self.dependencies.copy() 初始化路由依赖集再合并单路由依赖，路由级 dependencies 无条件进入每条经 add_api_route 创建的路由，装饰器路由亦经同一函数（api_route 委托 add_api_route），故 /health 与循环注册的 8 条路由受同一 require_supervisor 保护，不存在传播分叉；(2) 集成测试已断言未授权被拒——真实 uvicorn 子进程上对 add_api_route 注册的 PATCH desired-state 与 GET /profiles 无令牌请求断言 401，对 /health 断言无令牌/错令牌 401（含 WWW-Authenticate: Bearer）与正确令牌 200。本问反证条件的两个析取项同时满足。残余覆盖缺口（不改变结论）：bind/observed/events 三条写路径未见各自的无令牌 401 断言（仅有带正确令牌的 200 流），且 require_supervisor 的 503 未配置分支在全部测试中无断言；三条写路径与已被负向断言的兄弟路由走同一注册循环与同一合并依赖，机制层面无差异。

## Findings

No findings.

## evidence

```json
[
  "src/backend/cbrowser/api/internal_supervisor.py:46-50 supervisor_router = APIRouter(prefix='/api/v1/internal/supervisor', dependencies=[Depends(require_supervisor)])；L26-43 require_supervisor：app.state.supervisor_token 为 None 时 503，凭据缺失或 hmac.compare_digest 不匹配时 401 并带 WWW-Authenticate: Bearer",
  "src/backend/cbrowser/api/internal_supervisor.py:60-102 除 /health 用 @supervisor_router.get 装饰器外，其余 8 条路由（profiles 列表/详情、version、runtime、desired-state PATCH、runtimes/bind、runtimes/observed、runtimes/events）全部经 supervisor_router.add_api_route(path, endpoint, methods=[...], response_model=...) 注册且未传 dependencies 参数，保护完全依赖路由级依赖传播",
  "src/backend/cbrowser/api/app.py:344-346 app.include_router(supervisor_router, include_in_schema=include_internal_schema)；路由依赖在 add_api_route 建路由时已固化进 APIRoute 对象，include 不剥离",
  "版本钉版：config/docker/supervisor_runtime/requirements.txt:8 与 config/docker/browser_runtime/requirements.txt:14 均为 fastapi==0.162.0；pyproject.toml:8 与 src/backend/requirements.txt:1 为 fastapi>=0.115.0",
  "FastAPI 0.162.0 官方源码 fastapi/routing.py APIRouter.add_api_route：L5794 current_dependencies = self.dependencies.copy()，L5796-5798 再 extend 单路由 dependencies，L5812-5824 以 dependencies=current_dependencies 构造路由；同文件 L5939-5995 显示 api_route 装饰器委托 add_api_route，两类注册路径依赖处理一致（经 raw.githubusercontent.com/fastapi/fastapi/0.162.0/fastapi/routing.py 静态读取）",
  "FastAPI 0.115.0（声明下限）官方源码 fastapi/routing.py L1779 同有 current_dependencies = self.dependencies.copy()，全版本区间内合并行为一致，无版本敏感性",
  "tests/integration/conftest.py:18-47 supervisor_api 夹具以 subprocess.Popen 启动真实 uvicorn 进程（python -m uvicorn cbrowser.api.main:app），CBROWSER_SUPERVISOR_TOKEN_FILE 指向 0600 令牌文件，非 TestClient 进程内调用",
  "tests/integration/test_supervisor_rpc.py:8-22（文件 docstring：Internal Supervisor RPC must authenticate over an actual HTTP process）GET /health 无 Authorization 头与随机错 Bearer 均断言 401 且响应头 www-authenticate == 'Bearer'、令牌不出现在响应体；正确令牌断言 200 {'status': 'ok'}",
  "tests/integration/test_supervisor_rpc.py:32 对 add_api_route 注册的 PATCH /api/v1/internal/supervisor/profiles/{id}/runtime/desired-state 无任何请求头断言 401；L78 对 add_api_route 注册的 GET /api/v1/internal/supervisor/profiles 无请求头断言 401、带令牌断言 200——若路由级依赖未传播，这两条请求将直达 handler 返回 200，断言即为针对传播失效的回归哨兵",
  "tests/integration/test_supervisor_rpc.py:36-70、L84-155 与 tests/integration/test_v2_api_subprocess.py:463、491-680、tests/integration/test_supervisor_observation_authority.py:82：bind/observed/events 在真实子进程套件中均以正确 Supervisor Bearer 调用并断言 200，但全仓未检索到针对这三条端点各自的无令牌/错令牌 401 断言",
  "全仓检索未发现该内部面的 503 断言：require_supervisor 的『token 未配置→503』分支（internal_supervisor.py:36）无任何测试覆盖（tests 中该面的 401 断言仅见 test_supervisor_rpc.py:16/32/78）",
  "已剔除的伪证据：src/backend/cbrowser/api/app.py:385-393 contracted_openapi 按路径前缀对全部 /api/v1/internal/* 操作覆写 security=[{serviceBearer: []}] 与错误码，故 tests/unit/test_runtime_agent_protocol_export.py:48-50 对 /runtimes/bind 的 OpenAPI security 断言不能独立证明路由依赖传播，本结论不依赖该证据"
]
```

## result

```json
"refuted"
```
