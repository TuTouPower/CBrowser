# Task spec

## 背景

完整落实 docs/v2_architecture_plan.md 对应正式实施阶段：产出 v2 正式部署产物与部署文档；t001全项技术验证通过前不实施。2026-11-02 按用户审批的 adoption（docs/reviews/review_20261102_201727，A15、A27）重构：本 task 提前到 t009 之前，只负责可部署产物与文档；CI/门禁归 t018（A41），真实部署到本机与数据切换归 t010。

## 契约区

### 范围

- 面向当前Mac的OrbStack/Docker与同机Chrome：正式compose、全部常驻服务（含API）的生产镜像与Caddy配置（是否包含coturn按t015结论），拓扑由单一权威定义产出并供测试夹具消费；构建可复现与供应链约束；README、DOCKER_DEPLOYMENT、CHANGELOG与AGENTS.md现状说明及可执行的部署/升级/备份恢复/故障定位文档。

### 非范围

- 不迁移真实用户数据、不切换在跑的部署、不删除legacy栈（归t010）；不负责CI与门禁脚本（归t018）；不推送外部镜像仓库、不做公网发布；不处理与本阶段无关重构。

### 验收标准

<!-- 规范（门禁必留，不得删除） -->

只写可观察、可独立验证的行为；每条使用稳定且不复用的 `AC-NNN`。需真实部署或人工环境验证时在编号前加 `[deploy]`。创建时均为未勾选（`- [ ]`）；实施验证通过后由实施 Agent 就地打勾（`- [x]`）；由 Review Agent 独立复核打勾真实性。技术选型不作为行为 AC。

<!-- /规范 -->

- [ ] [deploy] AC-001：在当前Mac/OrbStack全新数据根使用正式compose启动全部常驻服务和动态双Runtime，由同机Chrome访问，HTTPS登录/Chrome媒体/输入/Artifact/CDP/停止恢复端到端通过；网络映射和数据bindmount与架构一致，无默认弱口令或硬编码秘密。
- [ ] AC-002：构建可复现：全部常驻服务（含API）的生产镜像定义集中在config/docker/，基础镜像以digest钉版且产物标签与基础镜像标签分离，Python依赖带哈希锁定，每个镜像使用白名单构建上下文，运行镜像不含编译工具链，特权服务只持有记录在案的最小权限；构建期断言前端与后端API代际一致；arm64真实运行，x86_64可构建并通过静态检查（原生实跑按用户指示记NOT_RUN/USER_WAIVED）。
- [ ] [deploy] AC-003：README及DOCKER_DEPLOYMENT写明当前部署状态，并提供可直接执行的部署、网络模式、升级迁移、备份恢复和故障定位步骤（TURN相关内容按t015结论）；独立空环境按文档演练通过；CHANGELOG记录v2阶段变更；AGENTS.md项目描述与ADR一致。
- [ ] AC-005：拓扑由单一权威定义产出，测试夹具与正式部署消费同一定义，Caddy等配置由同一生成器产出；单一.env.example覆盖全部v2变量并标明必填项。

### 可测试性声明

<!-- 规范（门禁必留，不得删除） -->

逐条说明不可自动测试的 AC 及替代验证；全部可测则写“全部 AC 可自动测试”。

<!-- /规范 -->

- AC-001、AC-003需真实Docker+Chrome与按文档人工演练，保存演练记录与证据；其余AC可自动验证。原AC-004（真实部署到本机并冒烟）已于2026-11-02移入t010。

## 上下文区

- 来源：docs/v2_architecture_plan.md（2026-10-27逐项核对）；t001 已完成并归档（docs/archive/tasks/t001_v2_runtime_validation），技术门禁已通过
- 2026-11-02 用户审批的 adoption（docs/reviews/review_20261102_201727/adoption_decision.md）：A27（正式拓扑与镜像要求）、A15（入口文档现状）并入本task；CI/多架构发布流水线与release.yml处置归t018（A41，删除release.yml，外部发布不在本次范围）；真实部署到本机并冒烟移入t010。在本task之前不要从当前源码重建legacy镜像（会把v2前端打进legacy后端镜像，界面不可用）。

### 有意不测

- 公网穿透与原生Linux x86_64实跑：用户已豁免（NOT_RUN / USER_WAIVED）。

### 测试策略

- 正式构建+独立数据根compose实装+Chrome全链路冒烟；不把镜像构建当实装完成；测试夹具改为消费正式拓扑定义后，既有E2E在其上全绿。

### 未知契约清单

<!-- 规范（门禁必留，不得删除） -->

未核实的外部契约标为 `UNVERIFIED-BLOCKING` 或 `UNVERIFIED-SPIKE`；核实后改写为结论和验证方式。无则写“无”。

<!-- /规范 -->

- UNVERIFIED-SPIKE：以前置task最终已验证协议/模型/镜像为准（含t015的媒体链路结论与t016的文件所有权模型）；现有原型不得直接视为正式契约。涉及原生Linux/公网/实际数据/外部发布时必须核实入口与授权。

### 风险与回退

- 风险：跨服务权限、凭证或网络映射在正式拓扑下失败；夹具改为消费正式定义时暴露差异。
- 回退：隔离worktree、测试数据根和容器资源；保留失败日志，回退本阶段产物；不触碰在跑的legacy部署与用户数据。

### 依赖与约束

- 必须先取得t018完成产物（其前置t015/t016/t017）；所有正式实施继承t001全项通过硬门禁。公共文档/索引由主控串行收尾。

### Finalization 时更新的 blueprint

- README.md、DOCKER_DEPLOYMENT.md、CHANGELOG.md、AGENTS.md、docs/blueprint/architecture.md与testing.md：正式部署入口与现状。
