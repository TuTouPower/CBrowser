# 项目交接记录（最新）

## 2026-11-05T20:30:00+08:00 队列推进：T032 已合入，t033/t034/t043 已 done，t035 完成 spike 后交接

### 状态与工作区

- branch `main`；交出时 head_commit `0ac2ac6`（`docs(pending): 登记并暂搁 p043 导入本机 Chrome 数据为 Profile 并绑定一键重复导入`，属其他会话提交，未动）。本地领先 origin/main，未 push。
- task 状态以 `task.py effective-status` 为准：t032 `done | main`；t033 / t034 / t043 `done | branch`；t035 `active | worktree`（`../CBrowser_t035`）；t036–t042 `backlog | main`。
- 已闭环成员的分支与实现 commit：`t033_frontend_toolchain_upgrade` = `00f828e`、`t034_runtime_platform_upgrade` = `2e95581`、`t043_selkies_upgrade` = `eeffb89`；三者均已完成 full review、finish、run-close，分支保留待整链 merge。t032 merge commit `483071a` 已进入 main。
- 队列为单一串行链 c1，链尾 t042；`plan --serial --json t033 t034 t043 t035 t041 t036 t037 t038 t039 t040 t042` 的 base 依次链式传递。merge 授权按 task-run 规则在整链完成后统一请求，本会话未请求、未 push。
- 主仓工作区干净；`0ac2ac6` 为其他会话改动，按工作区保护保留。

### 本轮结果（均已验证）

- **t033**：前端工具链升到最新稳定版（Vite 8 / plugin-react 6 / Vitest 5 / React 19.3 / react-router 8 单包 / lucide 1.68 / jsdom 30 / jest-dom 7 / @types/node 26 / TanStack Query 5.106），TypeScript 因 openapi-typescript peer 例外固定 5.9.3（ADR 020）；Node 固定 26 LTS + `check_node.mjs` 双分支门禁；3 项 SPIKE 实测闭环；完整门禁 `all_passed=true`。
- **t034**：Python 3.15.2 / Debian trixie / Caddy 2.11.8 digest 固定；修正 `pyproject.toml` 的 `dependencies` 误落 `[project.scripts]` 缺陷，PEP 735 六组依赖 + `uv.lock` 单一来源，`generate_requirements.sh` 按组导出并在 unit suite 校验；SQLAlchemy 2.1.8 / Alembic 1.20.1 / aiosqlite 0.22.1；cloakbrowser 锁 0.6.4（ADR 021）；5 镜像两次干净构建 ID 一致、包集合与 uv.lock MATCH；隔离实例发布 rh1→rh2→回退 rh1 三次健康检查全绿；完整门禁 `all_passed=true`。8 条 review minor 5 修 3 登记 `p044`。
- **t043**：Selkies 2.1.0 → 2.2.1，正式 spike `s012` + finding `d030` 证明协议/私有 ABI 无不可适配破坏变化；vendor pin/wheel SHA/URL/SHA 清单（2018 行）、注入 marker 改通用首个 module tag、`x11_keymap` 版本门禁、pixelflux 2.2.3 / pcmflux 2.2.1 联动；ADR 022。**按用户监督纠正**把 `test_frontend_session_freeze_resume_and_diagnostics` 的错误归因（原记为 t032/t033 已登记偶发）更正为 2.2.1 延迟初始化引入的负载下时序回归；修根因（`useBrowserSession` 的 `DIAGNOSTIC_STAGES` 守卫，诊断态忽略 iframe 的 WS_CLOSE/PC_STATE/LIFECYCLE_STALE）+ TDD 回归；修复后完整门禁 `all_passed=true`、E2E 103 项 0 失败、该用例在完整门禁中 PASS；scope 变化后重新 review（PASS）。
- **t035**：正式 spike `s013` + finding `d031` 闭环，UNVERIFIED-SPIKE 结论回填 `task.md`。在 Linux arm64 探针容器用真实引擎三组实测：Chromium 146 **支持**带认证 SOCKS5（正确凭据经代理加载、错误凭据 `ERR_SOCKS_CONNECTION_FAILED`、无认证对照正常），与契约背景「原生不支持」相反；AC-008 取「端到端经代理出站」分支。`code/probe.py` 可复现。12 条 AC 的代码改造未开始：曾起草 baseline 迁移与 models.py 局部改动，因会让 repository/domain/API/前端/测试全部引用失效，按「工作区保护 / 每个 commit 独立可验证」撤销，t035 worktree 保持干净一致（仅 spike 成果 + progress/task.md 回填）。

### 关键证据路径

- t033：`~/kar/code/CBrowser_t033/.scratch/evidence_t033c/`（已随 worktree 清理，证据摘要在 t033 `progress.md` / `final_report.md`）。
- t034：`.scratch/evidence_t034c/`（原 t034 worktree 已清理；摘要在 t034 `progress.md`）。
- t043：`.scratch/evidence_t043c/`（原 t043 worktree 已清理；摘要在 t043 `progress.md`）。
- t035 spike：`docs/spikes/s013_authenticated_socks5_engine_probe/`（report.md + code/probe.py）、`docs/findings/d031_authenticated_socks5_supported.md`（均在 t035 worktree，尚未 commit）。
- 环境：`~/kar/code/.cbrowser/e2e-env.sh`（引擎缓存与 E2E 变量）、`~/kar/code/.cbrowser/engine-cache`（Chromium 146 引擎缓存，已迁出 `.scratch`）、mise 固定 Node 26.13.0 / Python 3.15.2。镜像 ID 需重建镜像后按 `docker image inspect` 填入。

### 恢复入口与下一步

1. t035 保持 `active`、attempt `34759d07` running(inline)、worktree `../CBrowser_t035` 保留、代码层零半成品。**不要重复 `run-begin t035`**；先 `python3 .repo_template/scripts/task.py recovery t035` 判定现场，按 `.repo_template/docs/recovery.md` 继续。
2. t035 实施规划见 t035 `progress.md`「实施笔记」：迁移基线 `b7e1c9d4a2f3` 合并 0001–0009 并删旧文件 + 旧 schema 代 fail-closed + release controller 按修订链；Group/Proxy 表与 CRUD、删除业务 Tag 全部实现、配置版本三分（元数据/即时/运行）、代理字段变更同事务生成新版本 + SSE、runtime `last_started_at`/`last_stopped_at` 与浏览器版本上报链路（Runner CDP → Agent → Supervisor → API）、删除语义与目录清理、OpenAPI 导出与前端类型重生成、`domain.md`。12 条 AC 的测试须按新语义重写（旧测试整体删除并写明理由），最后跑完整门禁 + full review。
3. 队列后续成员 `t041 → t036 → t037 → t038 → t039 → t040 → t042` 仍为 backlog；每个仍需完整实施 + 门禁 + review + finish + run-close。
4. 整链完成后按 `task-integrate` / `integrate-chain` 逐项请求用户明确 merge 授权，单成员链用 `integrate {tid}`、多成员链用 `integrate-chain t042`；不 push。
5. 已知外部项：模板 contract 2 项失败已上报 `TuTouPower/repo_template#84`（消费仓未改模板）；`p044` 登记 t034 验证工具接线/弃用告警/mock 深度 follow-up。
