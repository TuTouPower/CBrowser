# bundle_followup_q_system_properties_01

## Summary

怀疑消解，但先明示门槛差异：原题要求以运行证据（启动真实 API 进程、无/错/对令牌三态请求并记录状态码）定论，本轮静态审阅未启动进程、未复跑测试，故本文件不声称包含本轮运行记录。判定静态证据已足的理由：本问的怀疑是条件式——『若 add_api_route 不继承 router 级依赖，则该面无鉴权』，其全部不确定性系于一个确定性的框架代码路径，而非涌现的运行时行为。该路径已在钉版 FastAPI 0.162.0 的 routing.py 中逐行核实（add_api_route 以 self.dependencies.copy() 为基合并依赖并构造路由，L5794/L5798/L5824），声明下限 0.115.0 同样成立（L1779）；路由依赖集在导入注册时即被这段代码固定，任何运行同一钉版的进程不具备偏离空间，传播不成立在代码层被排除。佐证（非本轮执行）：仓内 tests/integration 以真实 uvicorn 子进程承载的 test_supervisor_rpc.py 已把原题要求的三态检查编码为断言，覆盖装饰器路由 /health 与两条 add_api_route 注册路由的无令牌 401 及正确令牌 200；若传播失效这些断言必然失败。残余事项（属执行状态确认与覆盖补强，非语义缺口）：(1) 本轮未复跑该套件，其当前 CI 绿灯状态未独立确认——按原题面完全闭环只需在 CI 执行 tests/integration/test_supervisor_rpc.py 并留存结果；(2) bind/observed/events 未见各自的负向 401 断言、503 未配置分支无断言，建议补齐三条写路径的无/错令牌负向用例。

## Findings

No findings.

## evidence

```json
[
  "静态约束明示：本轮为纯静态审阅，未启动任何 API 进程、未执行任何测试；以下结论由钉版框架源码的确定性语义与仓内既存的真实子进程测试断言构成，未包含本轮新产生的运行记录",
  "src/backend/cbrowser/api/internal_supervisor.py:46-50 supervisor_router 声明 dependencies=[Depends(require_supervisor)]；L60-102 中 bind（POST /runtimes/bind）、observed（POST /runtimes/observed）、events（POST /runtimes/events）与其余 5 条路由全部经 supervisor_router.add_api_route 注册、未传 dependencies，L26-43 require_supervisor 对缺失/错误凭据返回 401（hmac.compare_digest 比对 + WWW-Authenticate: Bearer）、未配置令牌返回 503",
  "版本钉版：config/docker/supervisor_runtime/requirements.txt:8 与 config/docker/browser_runtime/requirements.txt:14 均钉 fastapi==0.162.0；pyproject.toml:8 与 src/backend/requirements.txt:1 下限 fastapi>=0.115.0",
  "FastAPI 0.162.0 官方源码 fastapi/routing.py APIRouter.add_api_route L5794/L5796-5798/L5812-5824：current_dependencies = self.dependencies.copy() 后 extend 单路由依赖并以之构造 APIRoute，路由依赖集在模块导入注册时即由这段固定代码决定；0.115.0 同文件 L1779 同一行存在，全区间无条件合并（经 raw.githubusercontent.com 静态读取两个版本源码）",
  "src/backend/cbrowser/api/app.py:344-346 include_router(supervisor_router) 不改写已构造路由的 dependencies；该面路径仅存在于 supervisor_router（tests/unit/test_runtime_agent_protocol_export.py:53-66 断言 /api/v1/runtimes/bind 等不在公开面、仅在内部面），无第二条无依赖注册路径绕过",
  "tests/integration/conftest.py:18-47 supervisor_api 夹具以 subprocess 启动真实 uvicorn cbrowser.api.main:app 并注入 CBROWSER_SUPERVISOR_TOKEN_FILE；tests/integration/test_supervisor_rpc.py:12-22 在该真实进程上断言无 Authorization 与随机错 Bearer 请求 /health 均 401 且 www-authenticate == 'Bearer'、正确令牌 200，L32 断言 add_api_route 注册的 PATCH desired-state 无头请求 401，L78 断言 add_api_route 注册的 GET /profiles 无头请求 401——这些既存断言即为原题所需『无/错/对令牌』运行检查的测试形态（本轮未复跑，其当前绿灯状态未经本轮执行确认）",
  "覆盖缺口清单（本轮静态检索确认）：bind/observed/events 三条状态写路径未见各自的无令牌/错令牌 401 断言，仅有带正确令牌的 200 流（test_supervisor_rpc.py、test_v2_api_subprocess.py、test_supervisor_observation_authority.py）；require_supervisor 的 503 未配置分支在全部 tests 中无断言",
  "已剔除的伪证据：src/backend/cbrowser/api/app.py:385-393 contracted_openapi 按 /api/v1/internal/ 前缀统一覆写 operation security 与 401/403/503 响应码，内部 OpenAPI 中 /runtimes/bind 的 serviceBearer 标记系后处理盖章、非路由依赖的生成结果，不能作为传播成立的证据，本结论未依赖它"
]
```

## result

```json
"refuted"
```
