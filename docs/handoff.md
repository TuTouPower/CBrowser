# 项目交接记录（最新）

本文件只保留当前有效一节。上一节已追加到 `docs/archive/handoff.md`。

## 2026-11-02T07:29:33+08:00 基线最终候选冻结，完整门禁运行中

### 授权、状态与边界

- branch main；head_commit `94d915cebc8ebc3aa318652946aeb0fa1a7bee33`（本文单独提交）。用户“不需要创建task 直接改”“继续”授权持续；完整附件目标仍 active。不新建 canonical task，不改冻结队列、不 push。本地合并已预授权。
- t001–t007 done/integrated；t008 → t013 → t014 → t009 → t010 → t011 → t012 仍 backlog 无 attempt。基线全绿后才启动 t008。基线源码尚未 commit/merge。
- 自有八个 worktree 与 base/diff_anchor a673edf 不变。实现权威 baseline_fix，实跑 baseline_validation；两者当前完整候选字节一致。旧生产与其它项目未动。

### 本阶段新增证据

- 原第三恢复 node 已整体替换：真实诊断入库/去重不能改变健康运行实例，实际 Agent/PID/CDP/实例/配置/UDP 端口保持稳定。主控 focused_spool_authority_r1 三项真实恢复 E2E 全部 PASS/73.77s，包含两项原 SIGKILL 恢复节点；镜像属于 lint 前生产版本，仅作阶段证据。
- 后端 Ruff 审查抓到协调器非 dict JSON 错误响应异常穿透。恢复 start/stop 两处原保护边界，新增真实 RuntimeCoordinator、SQLite、ProfileService、仅 HTTP 边界 MockTransport 的 12 项回归。实现方最终回归 PASS；最终全库由主控门禁重跑。
- 后端 34 文件组件 SHA `ec55eddb322960a243fad109e7536411c1c3c362def265eaf951825bda533fd0`。独立 review R2 PASS，真实生产入口 15 项对抗 PASS；有效 Producer/live CDP 在 reviewer 授权范围内 NOT_RUN，由最终 Docker 门禁覆盖。R1 手抄循环/表达式不计生产运行证据，纠正报告已保留。
- 主控真实 run_uds_agent null 元数据探针修复后保持等待并可取消，证据 agent_metadata_poll_lint_probe_r2/result.json。
- tests/scripts 53 文件 lint 收尾抓到 viewer WS 非 dict JSON 导致断线回归；真实 aiohttp WS 探针 RED 后恢复原帧隔离边界，新增 null/list/int/bool 后继续处理正常 visibility 消息四项回归。实现方夹具 28 项 PASS。
- 主控按原 seed 精确核对并仅采纳 53 文件，加独立协调器新测试；未复制 actor 整个 worktree。lint 前后 AST assert guard 只见四个等价表达式变化（字典存在且非空改 get、set(generator) 改集合推导），无业务预期数值变化。记录 final_lint_assertion_guard.json。
- 主控最终默认 Ruff 联合 E/F/W/I 全范围检查 PASS：src/backend/cbrowser、tests、scripts。未修改全局 lint 配置。

### 最终候选与正在执行的门禁

- 完整候选 137 文件，SHA `5e9c58ec5fb339f90c3e50e1c804c1bb67184e87547a7eef9d0303259eb67586`；主仓 `.scratch/v2_baseline_20261101/fix_dispatch/combined_candidate_r6.patch` 及同名 JSON。
- 最终 driver PID 62095，`.scratch/v2_baseline_20261101/fix_dispatch/verify_final_round1.py`，wrapper 同目录；结果、原始日志、不可变镜像 ID 位于 `.scratch/v2_baseline_20261101/final_round1/`。外层唯一 Docker 锁，未往测试植入编排锁。
- 运行计划：六镜像重建/四入口 import、contract/unit/integration/legacy、Vitest/vendor/build、四 schema/前端类型漂移、完整 Ruff/文档格式、实际 42 E2E 模块清单、旧服务健康、逐组容器与网络残留检查、源码冻结校验。当前 Browser build PASS，Stream 正在 BuildKit 前端解析；其余尚未完成，不宣称全绿。
- SDK 固定 cloakbrowser==0.6.4，uv --no-project，缓存/TMPDIR 均 code 内 scratch，预编译字节码；构建后恢复 tracked tsbuildinfo 原字节，不纳入生成缓存漂移。原失败日志全部保留。

### 配置缺陷与审计

- 已披露 wrapper 不透传 CLI exit、SHA guard 不覆盖新增文件、三 lane 意外 uv.lock、SDK 报告权限拒绝后 shell 绕写、R1 reviewer 复制生产片段当证据等问题；详见前节与各 audit 文件。未修改 .repo_template、wrapper 或 guard。已核实并精确处理自有生成锁与孤儿进程，未动其它项目。
- backend R5 第一次 CLI 启动 database is locked、无工具调用或源码改动；核对文件哈希/mtime/PID 后有限重试成功。日志 ruff_backend_round5\*、retry\*。未改 SQLite 配置。
- 当前全部外部实现/review CLI 自然结束，源码不再由 actor 写入。主控门禁运行期间禁止改 validation 源码。

### 后续

- 持续观察最终门禁；失败保留日志并定位，禁止放宽断言。全绿及 review 后才形成 baseline 单执行 commit、本地合并，备份 scratch 后规范 remove/prune，再启动既有 t008。
- 剩余七 task、8 小时/1000 次 IME/1000 次 clipboard、容量/P95、旧链路移除、Compose 正式部署与官方 Chrome 黑盒均未完成。公网 TURN 与原生 Linux x86 仅两项 USER_WAIVED，功能保留。
