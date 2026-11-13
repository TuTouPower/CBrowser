# bundle_followup_q_system_properties_04

## Summary

静态语义判定：f_backend_core_02 的穿越在运行期可达，怀疑成立。本轮未做运行复现（不在授权内），但整条链的每一跳都已由具体版本的源码钉死、无剩余不确定性：(1) 部署链无规范化层——entrypoint.sh 直接 exec uvicorn backend.main:app，compose 直连发布端口，无反向代理；(2) uvicorn（httptools 与 h11 两种协议实现一致）先对请求路径做 urllib.parse.unquote 再写入 scope['path']，故 /%2e%2e%2f、/..%2f 与字面 /../（curl --path-as-is）三种形态到达路由时均为字面 ../ 段；(3) Starlette 路由直接对 scope path 做正则匹配，path 转换器正则为 .\* 且 convert 为恒等，routing.py 全文无 normpath/点段处理，full_path 原样进入 handler；(4) serve_spa 以 FRONTEND_DIR / full_path 拼接后仅判 exists()/is_file()，无 resolve/commonpath/包含校验，pathlib 不折叠 ..，由操作系统在打开时解析——镜像内 FRONTEND_DIR=/app/frontend/dist，上溯两级即达 /app（含后端源码），三级达 / 与 /data 卷；(5) 该路由按设计免鉴权：AuthMiddleware 对一切非 /api/ 路径直接放行（与 AUTH_TOKEN 是否设置无关），且 AUTH_TOKEN 默认空。因此任何能连到发布端口的主体均可未授权读取应用目录外的任意可读文件。一处对问题前提的修正：legacy 面在仓内并无钉版组合——src/backend/requirements.txt 与 pyproject.toml 只给下限（fastapi>=0.115.0、uvicorn>=0.34.0），基础镜像 cbrowser:latest 在仓外构建；仓内钉版（fastapi==0.162.0/starlette==1.10.0/uvicorn==0.54.0）属 v2 runtime 镜像。本结论的框架语义即按该钉版源码核对，且所依赖的三项语义（ASGI 解码后 path、路由不做点段规范化、穿越防护只存在于 StaticFiles 而非自定义路由）在 legacy 的整个版本区间内恒定，结论不随浮动版本改变。部署面限定：compose 默认把端口绑在 127.0.0.1，网络可达范围取决于部署配置（与 DOCKER_DEPLOYMENT.md 的局域网暴露表述之间的矛盾归 docs/contracts 单元），但代码路径可达性与免鉴权性质不以此为条件。仍缺的运行证据（不改变上述判定，仅作终局存档）：隔离实例中以未授权请求发送编码变体并记录响应状态与内容的抓包记录。

## Findings

No findings.

## evidence

```json
[
  "src/backend/main.py:1835-1843 — serve_spa 兜底路由 /{full_path:path}：file_path = FRONTEND_DIR / full_path，仅以 exists() 与 is_file() 为门，无 resolve()/commonpath/包含校验，不存在时才回退 index.html",
  "src/backend/main.py:116、275-278、524 — AUTH_TOKEN 取自环境变量、未设置即 None；AuthMiddleware 对 path 不以 /api/ 开头的请求直接放行（注释明示 static frontend 豁免），且它是全仓唯一一处 add_middleware；故 serve_spa 恒为未授权可达",
  "config/docker/entrypoint.sh 末段 — exec uvicorn backend.main:app --host 0.0.0.0 --port 8080，进程直连无代理；compose.yaml 将 127.0.0.1:${CBROWSER_PORT:-56661}:8080 直连发布，链路中无任何路径规范化层",
  "config/docker/Dockerfile — COPY src/frontend/dist/ /app/frontend/dist/ 且构建期跑 verify_frontend_dist.py 保证 dist 存在（main.py:1832 的 FRONTEND_DIR.exists() 门在镜像内恒真、路由恒注册）；/app/frontend/dist 上溯 ../.. 即 /app（backend 源码双份 COPY 在 /app/backend 与 /app/src/backend），../../.. 可达 / 与 /data 卷",
  "版本事实 — src/backend/requirements.txt:1-2 与 pyproject.toml:8-9 对 legacy 仅给下限 fastapi>=0.115.0、uvicorn[standard]>=0.34.0，无钉版；仓内钉版 fastapi==0.162.0 / starlette==1.10.0 / uvicorn==0.54.0 位于 config/docker/browser_runtime/requirements.txt:14,33,37 与 supervisor_runtime/requirements.txt:8,17,21（v2 镜像），以下框架语义按该钉版的已安装源码逐行核对",
  "uvicorn 0.54.0 源码 protocols/http/httptools_impl.py:257-264 — raw_path 经 urllib.parse.unquote 解码后写入 scope['path']（raw_path 另存原始字节）；protocols/http/h11_impl.py:204-205 同为 unquote 后写入；两种协议实现下 %2e%2e%2f 等编码点段到达路由时均为字面 ../",
  "starlette 1.10.0 源码 convertors.py:33-37 — PathConvertor.regex='.*'、convert() 恒等返回；routing.py Route.matches（约 254 行）以 get_route_path(scope) 直接做 path_regex 匹配，routing.py 全文无 normpath 或点段折叠逻辑，full_path 逐字传入 handler",
  "拼接语义 — pathlib 的 Path('/app/frontend/dist') / '../../backend/main.py' 不折叠 ..，exists()/is_file() 与 FileResponse 的文件打开均由操作系统解析点段，结果逃出 dist；对照：同文件 1833 行的 /assets 挂载用 StaticFiles（其自带包含校验），serve_spa 未用它",
  "测试覆盖 — src/backend/tests/ 对 serve_spa/兜底路由零覆盖：test_api.py 全部 TestClient GET 均请求 /api/* 路径，无任一用例请求非 API 路径或编码点段；仓内穿越类用例只存在于产物文件名净化路径（test_artifacts.py:36,84、test_downloads.py:48），与本路由无关"
]
```

## result

```json
"confirmed"
```
