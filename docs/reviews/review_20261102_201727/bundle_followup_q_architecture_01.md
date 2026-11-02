# bundle_followup_q_architecture_01

## Summary

精查证伪该疑点：发布链不存在替代前端构建路径或入口改写，cbrowser:latest 即便自带 legacy 前端也会被 COPY 覆盖，跨代拼接结论维持。

## Findings

No findings.

## evidence

```json
[
  "精查结论先行：疑点命题不成立——发布链中不存在任何能生成异于 src/main.tsx 入口的前端 bundle、改写 API 基路径、或让基础镜像自带与 legacy 后端配套前端的步骤；f_global_architecture_01 的『跨代拼接』结论维持，无需降级为文档问题。",
  "release.yml 的 Docker 构建（build-docker 两个 job）使用 docker/build-push-action 时只设 context: .、未设 file:，默认指向根目录 Dockerfile，而仓内根目录不存在 Dockerfile（全仓 find 仅 config/docker/ 与 docs/archive/spikes/ 下有）；即发布链根本不构建 config/docker/Dockerfile，更没有任何一步运行 npm/vite、注入构建变量或改写入门。原生安装包 job 调用 packaging/build_windows.ps1、packaging/build_macos.sh、packaging/make_universal_app.sh，而 packaging/ 目录在 HEAD 不存在。故 release.yml 内不存在替代前端构建路径（其与根 Dockerfile 缺失的矛盾本身已由 repo_ops 单元记录，本精查不重复立项）。",
  "唯一的前端构建定义是 src/frontend/package.json 的 build 脚本：tsc -b && vite build && vite build --config vite.selkies.config.ts。主构建的唯一 HTML 入口是 src/frontend/index.html，其 script 标签只加载 /src/main.tsx（全仓 src/frontend 下仅此一个 .html 文件）；vite.config.ts 无 base、无 define、无 rollupOptions.input 覆盖，仅有 server.proxy 的开发期 /api 代理（不进入构建产物）。vite.selkies.config.ts 是 lib 模式，只把 selkies_adapter_entry.ts 打成 IIFE 经典脚本写入 dist/selkies/（emptyOutDir: false），不是应用入口，也不产生第二套 UI。",
  "无构建期 API 基路径改写机制：src/frontend/src、index.html、vite.config.ts 中 grep VITE_ 与 import.meta.env 零命中；src/shared/api/client.ts:36-60 的 baseUrl 默认空字符串（同源），端点为硬编码字面量 /api/v1/*（client.ts:133-200）。ci.yml 的 frontend job 与文档门禁（docs/blueprint/testing.md:162-167）调用的都是同一个 npm run build，无 --entry/--base/--mode 等参数覆盖（且 ci.yml 本身引用重组前路径 frontend/、backend/，已由 repo_ops 记录）。",
  "config/docker/Dockerfile 本身不构建前端：FROM cbrowser:latest 后仅 COPY src/backend/（至 /app/backend/ 与 /app/src/backend/ 两处）和 COPY src/frontend/dist/ 至 /app/frontend/dist/。dist 被 .gitignore:16 忽略、干净克隆中不存在，COPY 只能采用本机预先 npm run build 的产物；vite 构建必然产出 index.html，目录 COPY 的合并语义下同相对路径文件被覆盖，故任何经此 Dockerfile 实际构建出的工件，其 /app/frontend/dist/index.html 必然是 v2 构建的入口文件；本机无 dist 时 COPY 直接使构建失败，不存在回退到基础镜像前端的路径。",
  "cbrowser:latest 基础镜像在仓内无任何定义：全仓没有任何 Dockerfile、脚本或 compose 服务产出它；既有记载仅表明它是开发者本机既有镜像——docs/archive/spikes/s001_selkies_runtime/report.md:36 称『仅复用本机既有 cbrowser:latest 基线镜像』，docs/handoff.md:22 称正在运行的 cbrowser:latest 容器是旧版 VNC。compose.yaml:5-9 又把自身构建产物同名标为 cbrowser:latest（自引用，已由 contracts_deploy 单元 f_contracts_deploy_01 记录）。DOCKER_DEPLOYMENT.md:34 的架构图亦把前端托管位置标为 /app/frontend/dist，与 COPY 目标一致，文档侧不存在另一套前端来源。",
  "伺服路径核对：entrypoint.sh:27 以 PYTHONPATH=/app/src:/app 在 /app 下执行 uvicorn backend.main:app，两个 backend 副本均为仓内 legacy 代码；src/backend/main.py:299 FRONTEND_DIR = bundle_dir() / 'frontend' / 'dist'，src/backend/runtime.py:34-49 的 bundle_dir() 在镜像布局下解析为 /app（frozen/_MEIPASS 分支只服务于已不存在的 packaging/ 原生打包），故 main.py:1832-1843 挂载的 /assets 与 SPA 回退 index.html 均取自 /app/frontend/dist——即 COPY 覆盖后的 v2 dist，与基础镜像自带内容无关。",
  "v2 的四个 runtime Dockerfile（browser_runtime/supervisor_runtime/gateway_runtime/stream_runtime）经 grep 均无 frontend/dist 引用，且 release.yml 与 compose.yaml 都不构建它们，不构成发布链中的替代工件来源。"
]
```

## result

```json
"refuted"
```

## limitations

```json
[
  "静态审阅：未实际执行 docker build 或 vite build；结论基于 COPY 覆盖语义、entrypoint 与 bundle_dir() 的路径解析，这些决定任何经 config/docker/Dockerfile 构建出的工件实际伺服的前端，与基础镜像的具体内容无关。",
  "cbrowser:latest 基础镜像是仓外本机产物，其层内容无法从本仓静态枚举；『其自带 legacy 前端』仅按候选反证处理并已说明为何不影响结论。如需对该镜像本身定性，需在持有该镜像的机器上 docker inspect/导出后另行核对（超出本精查静态范围）。"
]
```
