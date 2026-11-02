# bundle_followup_q_system_properties_02

## Summary

精查证实：serve_spa 路径穿越在静态构造上可达——uvicorn 百分号解码后不做点段规范化、handler 无包含性校验，../../backend/main.py 与 ../../../etc/passwd 为可达目标；未做运行复现。

## Findings

No findings.

## evidence

```json
[
  "serve_spa 本体零防御 (src/backend/main.py:1835-1843)：file_path = FRONTEND_DIR / full_path 后仅判 exists() 与 is_file() 即 FileResponse(file_path)；无 resolve()、无 is_relative_to/commonpath 包含校验。pathlib 拼接不折叠 '..'，exists/is_file 与 FileResponse 的文件打开都按文件系统语义解析 '..'，可直接走出 dist 树。",
  "FileResponse 不做包含校验：Starlette 中做 realpath+commonprefix 包含校验的是 StaticFiles.lookup_path，而本仓 StaticFiles 只挂在 /assets (main.py:1833)；catch-all handler 是手写拼接 + 裸 FileResponse，不经过 StaticFiles，问题中假设的『FileResponse/静态层拒绝越界』对该 handler 不成立。",
  "解码链成立：legacy 部署路径上没有反代——compose.yaml:11 把 0.0.0.0:56661 直连容器 8080，entrypoint.sh:27 直接 exec uvicorn backend.main:app。Uvicorn (h11 与 httptools 两种协议实现) 均以 unquote 后的路径填充 scope['path']，且两个解析器都不折叠点段；Starlette Router 直接对 scope['path'] 做正则匹配、无 RFC 3986 点段规范化，path 转换器匹配含 '/' 与 '.' 的任意串。故 %2e%2e%2f 在进 handler 前已解码为字面 '../' 并被 full_path 整体捕获；原始 '/../' (curl --path-as-is) 同样直达。main.py 中唯一的中间件是 AuthMiddleware (main.py:257,524)，只做 token 判断、不做路径规范化。",
  "注册顺序不构成阻碍：catch-all 在 main.py 末尾 (1835) 注册、位于全部 API 路由之后 (源码注释亦明言 Must be AFTER API routes)，/api/* 优先命中 API 路由且 handler 内对 api/ 前缀再 404；但任意非 api 路径都落入 serve_spa，穿越只需避开 api/ 与 assets/ 前缀。",
  "穿越深度按镜像布局可达真实文件：生产镜像 (config/docker/Dockerfile) 把 dist 放在 /app/frontend/dist、后端源码在 /app/backend ( entrypoint 设 PYTHONPATH=/app/src:/app)。解码后 full_path='../../backend/main.py' 即命中 /app/backend/main.py，'../../../etc/passwd' 命中 /etc/passwd，'../../../data/...' 命中数据卷 /data (profiles 等)；exists/is_file 只要求目标是已存在文件 (无目录列举)，不构成包含边界。",
  "版本面反而加强结论：管辖 serve_spa 的版本在仓内根本没有精确 pin——生产 Dockerfile 是 FROM cbrowser:latest 且不做任何 pip 安装，FastAPI/Starlette 实际版本由仓外不透明基础镜像决定；仓内对 legacy 应用的声明只有下界 (src/backend/requirements.txt: fastapi>=0.115.0、uvicorn[standard]>=0.34.0，连 starlette 都未声明；pyproject.toml 同) 且无 lock 文件。仓内仅有的精确 pin (fastapi==0.162.0/starlette==1.10.0/uvicorn==0.54.0) 位于 browser_runtime 与 supervisor_runtime 的 requirements.txt，其 ENTRYPOINT 运行的是 cbrowser.supervisor 等 v2 服务，与 backend.main/serve_spa 无关。上述下界可解析到的全部版本线 (FastAPI>=0.115 对应的 Starlette 线及 Uvicorn>=0.34) 在本问题涉及的三项行为上一致：uvicorn 解码路径入 scope、Starlette 路由不折叠点段、FileResponse 无包含校验——版本不确定性不改变可达性结论。"
]
```

## result

```json
"confirmed"
```

## limitations

```json
[
  "按静态审阅约束未发任何真实请求、未运行应用：确认是基于『handler 代码 + 镜像布局 + ASGI 服务器/框架在相关版本线上的既定路径处理行为』的构造性确认，非运行期实测。",
  "生产镜像内实际的 Starlette/Uvicorn 精确版本不可从仓内核实 (FROM cbrowser:latest 的基础镜像不在仓内、无 lock)；结论依赖的是该版本线跨版本一致的三项框架行为，若基础镜像内装有仓外未知的路径规范化补丁或前置代理，结论需复核——仓内无任何此类迹象。",
  "starlette==1.10.0 的内部实现未逐行核查 (其为 v2 runtime 的 pin 且不适用于 legacy 应用)；对该版本线行为的判断基于 Starlette 路由/FileResponse 的长期稳定语义，未做源码级复核。"
]
```
