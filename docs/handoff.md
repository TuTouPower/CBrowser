# 项目交接记录（最新）

本文件只保留当前有效一节。上一节已追加到 `docs/archive/handoff.md`。

## 2026-11-01T12:27:04+08:00 累计审阅采纳完成，p008/p010 闭环

### 一、当前状态

- branch：main；head_commit：`2c3251569b1a9e6c1efc56c1e2d6922ef47cf1ff`（p010 merge；本文另行提交）。
- t001–t007 全部 done 并已合入 main。本轮完成：
    - t001–t007 累计三路审阅（`docs/reviews/review_20261101_075819/`）与 `adoption_decision.md` 决策落地。
    - A1–A31 全部实施；D1 按推荐 A 落地；R1–R8 按决策不实施。
    - A25 结构重构；p001、p005 闭环。
    - p008 Selkies resume 修复；p010 前端 vendor/build 接线修复。
- `docs/pending/todo/` 已清空；p001、p005–p013 全部归档到 `docs/archive/pending/`。
- 所有临时 worktree 已 `git worktree remove` + `prune`，adoption/p008/p010 分支已删除；未 push。

### 二、本轮提交

- 审阅报告与决策：`8352cb1`（review_20261101_075819）。
- 采纳轨道合并：`ed9d628`（docs A26/A27）、`5d5fe53`（build A11/A30）、`4c23b1b`（frontend A10/A28/A29）、`e6ccf6a`（backend A1–A9/A12–A24）。
- 结构重构：`d9f0034`（A25，merge `ef8e890`）。
- p008：`871ac3b`（merge `9e892a3`）。
- p010：`d26f90b`（merge `2c32515`）。
- 各采纳项在 main 历史中为独立 commit；A4/A5/A15/A24 有少量修正 commit（见 `git log --oneline`）。

### 三、验证结果

- 后端 unit：383 passed。
- 后端 integration：62 passed。
- 前端 Vitest：112 passed；`tsc -b` 通过。
- 前端构建：worktree 内实际执行 `npm run build --prefix src/frontend` 通过（prebuild vendor → tsc/vite → adapter IIFE → postbuild verify）。
- 前端构建接线测试：`tests/e2e/test_frontend_build_wiring.py` 8 passed；adapter/vendor 测试 13 passed。
- 未运行：需要不可变镜像/engine cache 的 Docker E2E、内核网络负例、真实 Chrome 前端 E2E；不得以历史 PASS 冒充本轮通过。

### 四、后续 task 队列

`docs/runtime/goal_queue.json` 顺序：t008 → t013 → t014 → t009 → t010 → t011 → t012。剩余 7 项均为 backlog，从当前 main 开工。

- t008（Artifacts/CDP 自动化）：以当前 main 为基线；前端 `/profiles/:id/files`、`/automation/:id` 仍是占位页；p007 已闭环。
- t013（复制/重置）、t014（剪贴板与完整输入）、t009（容量/P95/8h/1000 次输入）、t010（旧数据迁移，先备份可恢复）、t011（移除旧 VNC/RFB/原生桌面）、t012（Compose 生产交付）。
- t012 注意：
    - p006（agent_secret）与 p010（vendor/build）已闭环，不再需要在本 task 处理。
    - 前端生产构建必须走 `npm run build`（prebuild 自动 vendor、postbuild 自动校验）；清单在 `config/selkies/selkies_web_sha256.txt`。
    - `config/docker/Dockerfile` 已对 COPY 的 `dist/` 运行 `scripts/verify_frontend_dist.py`；Compose 不得绕过该校验。
    - API 仍需 `CBROWSER_SUPERVISOR_URL` + `CBROWSER_SUPERVISOR_TOKEN_FILE` + `CBROWSER_REQUIRE_SUPERVISOR=1`。

### 五、本轮架构变化（读代码前须知）

- 观测权威：Supervisor 以 Docker 容器状态/退出码与 Runtime Agent 进程监督为权威；磁盘事件只作诊断补充，不再直接驱动 `observed_state`/`desired_state`；`lifecycle/error` 收敛为 `observed_state=error` 并保留 `desired_state=running`；scan 对同实例会话短路；事件游标 + quarantine。
- Stream 出站：按 `CBROWSER_WEBRTC_MODE` 分档；relay-only 仅 Gateway/coturn/本实例 mux，local/lan/public 允许公共目的地址，私有/保留段始终 DROP。
- 停止/清理：Gateway 不可达时降级 teardown；端口释放走 finally；停止协调有上限。
- 配置：Gateway 端点单一来源，默认 18080；Origin 归一；不再硬编码 18097。
- 凭证/权限：`agent_secret` 在 `secrets/<profile>/agent_secret.txt`（0600，仅挂 Stream）；内部 token 强制 0600；宿主目录 chown 1000 + 0700/0750，x11 1777。
- 认证：受信代理 XFF + 每来源窗口 + 全局预算；429 带 Retry-After。
- TURN：轮换 future 校验 generation；current 过期 fail-closed；disconnect/stop 取消任务；upstream 关闭码透传。
- 数据：`runtime_events` 随 Profile 删除，`audit_events` 保留；tags 三态（缺席不改 / null 清空 / `[]` 清空）；failure_count 第 4 次阻断。
- 前端/构建：诊断数组有界、输入合并、i18n 补全、测试去固定 sleep；`npm run build` 已绑定 vendor/verify；Selkies manifest 在 `config/selkies/`。
- Selkies resume：viewer 隧道关闭/Gateway 断线后 Agent 保留 loopback upstream 10s，同 `tab_id`/`resume_key` 重连由 `RESUMED` 接管；见 d025。

### 六、环境与已知注意

- 前端构建需要 `python3` 与 Selkies wheel 缓存/网络；缓存默认 `.scratch/selkies_wheels/`。构建会改写 `src/frontend/tsconfig.tsbuildinfo`，提交前 `git show HEAD:...` 还原。
- p009（multi_viewer 固定 sleep）、p012（同 tab 驱逐关闭码）、p013（静止画面出帧）已修复并归档。
- 仍存在但未在本轮处理的偶发：`test_browser_runtime_e2e.py::test_ac006...` 偶发 Pulse 连接拒绝；`test_supervisor_namespace_policy_e2e.py` 偶发公网 IPv4 出站超时。复跑归因，不放宽断言。
- 本机 BuildKit 直连 Docker Hub 不稳：构建失败先 `docker pull` 基础镜像；sha256 不能直接当 FROM，需先 `docker tag`。
- Docker E2E 仍需外层互斥锁；测试代码不得自带锁或引用 `.scratch` 编排目录。

### 七、本地对象

- 本轮 worktree 已清理；`review/adoption-*`、`fix/p008-selkies-resume`、`fix/p010-selkies-vendor-wiring` 分支已删除。
- `.scratch/selkies_wheels/`：固定 wheel 缓存，可保留。
- 既有 t005/t006/t007 镜像与 `.scratch/v2_orchestration/` 证据仍在，按需清理；来源不明容器/网络继续不动。
