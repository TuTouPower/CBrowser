# CBrowser 全仓汇总（intensive-review synthesis）

基线：HEAD `5136766aceb2a7bb5a7b6c766e1d4f29b36439d5`；盘点 782 个文本文件 / 160,799 行；22 个语义单元、八视角全覆盖（4 个单元的 tests 视角经定向补审后完成）；局部 findings 共 325 条（Critical 0 / High 21 / Medium 92 / Low 167 / Info 45，以聚合结果为准）。本汇总由主会话在通读全部局部 summary 与关键 findings 后形成，供四路全局审阅使用；静态审阅，未运行任何代码/测试/构建。

## 1. 这个仓库实际是什么

CBrowser 是从 CloakHQ/CloakBrowser-Manager fork 的多身份/隐私隔离浏览器管理系统，当前处于 v2 重构中途。仓库里同时存在三层东西，理解全仓问题的关键是分清它们：

1. **legacy 栈（仍是部署现实）**：`src/backend/` 的单体 FastAPI 应用（backend.main：profile CRUD、launch/stop、VNC/CDP 代理、剪贴板、SPA 托管、profiles.db 手写 sqlite），前端 `src/frontend/src/App.tsx + components/*` 的 v1 界面，以及根 `compose.yaml` + `config/docker/Dockerfile` 的单容器部署。Docker 入口实际执行的仍是这套（entrypoint 执行 `uvicorn backend.main:app`）。
2. **v2 栈（新架构，主体已实现但未接管部署）**：`src/backend/cbrowser/` 包——API 控制面（会话认证 Argon2、CSRF/Origin、内部 supervisor/gateway RPC）、Supervisor（唯一持 Docker Socket、双容器生命周期、对账/恢复、网络策略、资源监管）、Browser Runtime Agent（UDS、CDP 隧道、下载事件）、Stream Agent + Gateway（Selkies WebRTC 信令、ICE 代次轮换、TURN REST 凭证）、SQLAlchemy/Alembic 数据层（cbrowser.db、不可变配置版本快照）。四个 v2 runtime 镜像 digest 钉版、版本锁定。前端 v2（`app/` 路由 + `features/` + `shared/api`）与 v1 并存于同一源码树。
3. **repo_template 工具链与流程资产**：`.repo_template/`（task/pending/findings 状态机脚本、skills、模板测试）、`docs/`（blueprint 自称当前长期真相、specs、findings d001–d025、tasks t001–t014 的完整账簿与归档）、大量真实 Docker E2E/集成测试与 fixtures。流程纪律（AC 勾选、review 处置表、handoff 链）在归档中基本可核对，是这个仓库最成熟的部分。

迁移任务 t010（数据迁移）与 t011（删 legacy）仍是 backlog，t009（完整验收）降级、t012（正式 Docker 发布）未完成——这是理解下面多数跨单元问题的根：**v2 的完成度被文档与任务体系按「已交付」叙述，但部署、CI、发布三条链仍停在 legacy 世界**。

## 2. 跨单元主线问题

### 2.1 门禁与发布链整体失效（High 集中区）

- CI 两个 job 全部引用重组前路径（`backend/`、`frontend/`），且根 pyproject 的三处 testpaths 一处未覆盖——仓库实际没有可用的 CI 门禁（f_repo_ops_01；frontend_shell 从构建接线角度独立确认）。
- release.yml 的原生安装包三 job 引用已按架构决定删除的 `packaging/` 脚本，`release` job 依赖它们，打 v\* tag 走不到建 Release；Docker 构建未指定 `file:`，默认根 Dockerfile 不存在，真实入口是 `config/docker/Dockerfile`（f_repo_ops_02/03）。
- 生产镜像 `FROM cbrowser:latest`：基础镜像仓内无定义、无 digest 钉版、产物同名，干净机器构建失败或用残留同名镜像（f_contracts_deploy 的 High）。
- 与之对照：v2 runtime 镜像与 release 的 SHA 钉版、最小权限、manifest 回读校验都是扎实做法——失效的是「旧链没跟上重组」，不是工程能力缺失。

### 2.2 默认部署的安全姿态

- `AUTH_TOKEN` 默认空 = 开放模式，compose 发布 `0.0.0.0:56661`，legacy 应用在无 token 时禁用鉴权中间件，profile cookie/文件与 `/api/shutdown`、`/api/open-external` 对局域网开放（contracts_deploy High；backend_core 的未鉴权面与之叠加）。
- legacy 侧单点问题成串：剪贴板内容写日志（与 diagnostics 的脱敏承诺直接冲突，f_backend_core_02 High）；SPA 兜底路由疑似路径穿越且**零测试**（f_backend_core_01 suspected High + viewfix f_18 High 确认无回归网）；launch 参数清洗是可穿透的前缀黑名单且**测试只枚举黑名单自身条目**（runtime_adapters High + viewfix f_18 High）；database.py 按列集差异自动重建表，静默丢列方向无测试（backend_core + viewfix f_19）。
- v2 侧的安全工程明显更强（secret 文件 0600 + 最小长度、compare_digest、实例围栏、路径校验、fail-closed 取向），但仍有：supervisor 上报端点挂载位置即鉴权边界、auth 拒绝写审计行放大、RTC 轮换时序参数无有限性/顺序校验（可致网关离线或轮换静默失效）、看板 token 嵌入未鉴权页面（template_scripts_state）、账本读 OSError 静默返回空列表破坏 attempt 号 fail-closed 不变量（template_scripts_state High）。

### 2.3 测试体系：量大、多数真实，但「静默变绿」是系统性模式

- 正面：测试总量大且多为行为级（真实 SQLite/迁移、回环 WS/UDS、解码帧/PCM 频率 oracle、canary 泄漏检查、schema 字节钉版）。归档显示团队有真实 E2E 纪律。
- 系统性风险（多单元独立命中、互相印证）：
    - **环境门控 skip**：supervisor 与 stream 两组 E2E 靠 `CBROWSER_*_TEST_IMAGE` 等环境变量存在与否决定跑或 skip，CI 又从不提供——整层可绿着零覆盖（tests_e2e_supervisor High、tests_e2e_stream_frontend High）。
    - **前端 E2E 从不构建**：直接用磁盘上现成的 gitignored `dist`，源码改动可测过旧产物（tests_e2e_stream_frontend High）。
    - **夹具与生产分叉**：集成层 SupervisorGatewayFixture 的 visibility 语义与生产 Gateway 不同（tests_integration_fixtures High）；tab 仲裁测的是已与生产 adapter 分叉的 web_lock_shim（e2e_stream_frontend）；拓扑 harness 三处重复实现、TURN 配置三处生成。
    - **负断言靠固定 sleep**：安全相关的「非法输入不得变更状态」断言在固定 0.05–0.1s 后检查，可真空通过（tests_unit_stream_api、tests_unit_supervisor_runtime 的墙钟断言、e2e 的条件断言 p002 模式残留）。
    - **生产缺陷无回归网**（viewfix 四单元一致结论）：本轮各单元找到的主要缺陷——对账异常隔离、下载路径包含校验、serve_spa、sanitizer 穿透类、/health 非阻塞、runtime_mode 读回、ICE restart_pending 楔死、心跳循环单 try、信令无代次分支——**全部没有能抓住它们的测试**；多处测试只断言生产代码恰好不走的那条路径（假退出守卫断言的是生产从不调用的 emit_event）。
    - 仓库测试（domain/repository）用 `create_all` 建表而非跑迁移，模型↔迁移漂移不可检（tests_unit_supervisor_runtime）。

### 2.4 双栈分叉的维护税

- 两套后端、两套数据存储（profiles.db vs cbrowser.db + Alembic）、两套前端（v1 死树约 2900 行不可达但仍在树内、两套 API 客户端/登录页/设置 UI）、legacy runtime_mode/viewer_mode 读回硬编码且 PATCH 不回写（runtime_adapters High：字段实际不生效）。
- 文档三态违规与之同源：生效 spec 把 t010 才交付的迁移工具写成已交付且 AC 已勾（docs_current High）；blueprint 自称当前真相但 failure_count 阻断阈值与 runtime_events 级联删除两处与 ADR/代码/spec 不一致；门禁命令硬编码开发者个人路径；CHANGELOG 停在 v2 之前的 0.1.9。
- 归档纪律总体良好（t001–t008/t013 证据链完整、遗留项均有去向），但有 p011 假闭环（子项未做却标 resolved 且无 live 承接）、归档 handoff 含 32 处开发者本机绝对路径与 session/PID（公开 fork 随仓公开）、spike 脚本含关鉴权的启动入口与把真实 secret 写进源码目录的 harness（archive_spikes 3 条 Medium）。

### 2.5 工具链（.repo_template）的自伤面

- 状态机脚本是全仓流程的权威实现，整体 fail-closed 取向明确，但：ledger 读失败 fail-open（High，见 2.2）；repo_cleanup 剪枝按根相对路径匹配、嵌套 node_modules/data 不剪枝可能误删；repo_sync 写文件跟随目标侧文件软链可写出仓外且不在回滚范围；link-skills 无事务却能 rmtree 真实目录且报告谎称已入回滚栈；purge 的全部拒绝护栏在测试中被 stub 成放行、drop 有一条手工模拟的假测试、review 证据由 fixture 伪造 PASS 且门禁在夹具中被整体禁用（template_tests）——**工具链的破坏性命令恰是测试最薄的地方**，与 2.3 的模式同构。

## 3. 相对优势（避免误判为全盘否定）

- v2 核心的并发/恢复设计（实例围栏、OperationJournal 幂等、事件 spool+去重、2/10/30 退避与第 4 次阻断、网络策略 netns fail-closed）经多单元交叉核对，实现与契约基本一致且有真实 Docker E2E 证据链（归档）。
- 契约面：OpenAPI 路由与实现 29/29 对齐、三份协议 schema 与生成脚本逐字一致且有漂移守卫测试；v2 镜像 digest 钉版 + 非 root（supervisor 除外，有据）。
- 前端 v2：i18n 双语 291/291 键对齐、生成类型与 OpenAPI 路径集 22/22 无漂移、postMessage 双向校验 origin+source、无 XSS sink。
- 文档/任务体系的证据链密度在同类个人项目中罕见；本轮发现的问题多为「叙述跑在实现前面」，而非无记录的混乱。

## 4. 审阅方法与限制

- 全部静态审阅：未运行代码、测试、构建、Docker；运行期才能定的问题（serve_spa 穿越的实际可达性、墙钟测试的真实 flake 率、aiohttp 默认消息上限等）以 suspected/uncertainties 保留。
- 生成型大文件（OpenAPI JSON、Selkies 哈希清单、spike 的 image_manifest）按 key/结构级覆盖，已在对应单元 uncertainties 注明。
- 本汇总的跨单元判断（如「默认部署姿态」）由 contracts_deploy、backend_core、backend_api_auth 三个单元的证据拼接，三者互相独立得出。

## Local uncertainty resolutions

```json
{
  "backend_supervisor:3": {
    "reason": "tests 视角已由定向补审完成：补审者全量通读 supervisor 核心/恢复/停止/事件/启动恢复单测与两份核心 E2E，并结合兄弟测试单元结论判定，verdict=completed，新增 f_backend_supervisor_13..15 已并入 local_backend_supervisor.json，该视角不再是缺口。",
    "evidence": [
      "_meta/viewfix_backend_supervisor_tests.json",
      "local_backend_supervisor.json views.tests.status=completed"
    ]
  },
  "backend_stream_gateway:3": {
    "reason": "tests 视角已由定向补审完成：补审者全量通读 gateway registry/rotation、stream agent lifecycle、ICE transport/security、rtc/gateway config 单测并与集成层核对，verdict=completed，新增 f_backend_stream_gateway_18..22 已并入。",
    "evidence": [
      "_meta/viewfix_backend_stream_gateway_tests.json",
      "local_backend_stream_gateway.json views.tests.status=completed"
    ]
  },
  "backend_runtime_adapters:1": {
    "reason": "tests 视角已由定向补审完成：补审者全量通读 runtime agent/下载对账/artifact/复制重置单测与 2791 行 runtime E2E，verdict=completed，新增 f_backend_runtime_adapters_18..22 已并入。",
    "evidence": [
      "_meta/viewfix_backend_runtime_adapters_tests.json",
      "local_backend_runtime_adapters.json views.tests.status=completed"
    ]
  },
  "backend_core:1": {
    "reason": "compose 是否默认注入 AUTH_TOKEN 已由 contracts_deploy 单元核实：根 .env.example 与 compose.yaml 显示 AUTH_TOKEN 默认空白（Blank = open），f_backend_core_05 的暴露前提成立，该不确定性已由跨单元证据消解（结论并入 repository_summary 2.2）。",
    "evidence": [
      "local_contracts_deploy.json（AUTH_TOKEN 默认空 + compose 0.0.0.0:56661）",
      "local_backend_core.json"
    ]
  },
  "backend_api_auth:2": {
    "reason": "src/backend/tests/test_auth.py 所测 legacy backend 是否仍在部署产物中，已由 backend_core 单元核实：config/docker/entrypoint.sh:27 执行 uvicorn backend.main:app，legacy 栈即当前 Docker 部署的实际入口，故 f_backend_api_auth_13 应按「活栈的测试」定性而非死测试。",
    "evidence": [
      "local_backend_core.json summary.responsibilities（Docker 入口为 backend.main:app）",
      "config/docker/entrypoint.sh:27"
    ]
  }
}
```
