# Task spec

## 背景

`docs/plan_20261105_ui_redesign.md` 第 6 节（D3、D4、D9、D13，用户 2026-11-05 确认）重建 Profile 领域模型：独立代理库、单值分组替换 Tag、元数据与运行配置拆分、运行时活动时间与浏览器版本上报。当前没有正式用户，不考虑兼容与数据迁移。2026-11-05 于 main@3101540 核实现状：

- 迁移链：`src/backend/migrations/versions/` 有 0001–0009 九个修订（auth、artifact、token expiry、font_bundle、control_state 等）。`scripts/deploy_v2.sh` 把 migration head 写入 release manifest，并以字符串比较 `applied_migration_version` 作为回退下限（第 166–177、433 行附近）；`tests/unit/test_t027_release_controller.py` 等测试硬编码 0002 / 0006 / 0008 / 0009。
- Tag：`profile_tags` 表（`adapters/database/models.py:133`），Profile 请求/响应含 `tags: list[Tag]`，`repository.update_profile` 把 tags 纳入请求签名与快照。
- 代理：`Profile.proxy` 为最长 512 的 URL 字符串（`adapters/database/models.py:28`），API 原样回显（含账密）。
- 配置版本：`repository.update_profile`（`repository.py:294` 起）任何 PATCH 都写入新版本与快照，运行中的 Profile 仅改名也提示「待应用并重启」。
- 运行时：没有最后启动 / 停止时间，也没有真实的浏览器版本上报。
- 删除：`ProfileService.delete_profile`（`services/profile_service.py:334`）不检查运行态，只删 DB 行与 Artifact，不删除 `profiles/{id}`、`runtime/{id}`、`runtime-events/{id}` 目录；`set_desired_state("stopped")`（`repository.py:711` 附近）不会把 observed 的 `error` 收敛为 `stopped`。
- OpenAPI：`v1_router` 使用无意义的 `tags=["v1"]`，其他 router 按 auth、artifacts、control、automation、internal-\* 分组。OpenAPI tags 是接口文档分组，与业务 Tag 无关，保留。

## 契约区

### 范围

- 迁移基线：把 0001–0009 合并为一个新的 baseline 修订，使用新的 revision 身份（不沿用 `0001_initial_schema`），删除旧迁移文件。旧 schema 代的数据库与数据目录不可升级：API 启动与部署脚本检测到后失败封闭，并给出重建数据目录的指引；不写数据迁移。本 task 之后，已部署过的修订不再原地改写，后续 schema 变更用增量迁移。
- release controller：回退下限改为按 Alembic 修订链判定，不再用字符串比较；旧 schema 代的 release 不能作为回退目标；相关测试按新语义重写，旧测试整体删除并写明理由。
- Group：表 `profile_groups`（`id`、`name` 唯一且 1–64 字符、`color` 取 slate / blue / teal / green / amber / orange / red / violet、`sort_order`、`created_at`、`updated_at`）；`profiles.group_id` 可空，外键 `ON DELETE SET NULL`；API `GET/POST /api/v1/groups`、`PATCH/DELETE /api/v1/groups/{group_id}`，支持批量调整排序。
- 删除业务 Tag 的全部实现：模型、表、请求与响应字段、快照字段、文案键。OpenAPI 分组保留；`tags=["v1"]` 改为按资源分组（如 profiles、groups、proxies、runtime）。
- Proxy：
    - 表 `proxies`：`id`、`name` 唯一、`scheme` 取 http / https / socks5、`host`、`port`、`username`、`password`、`credential_revision`、`country_code`（ISO 3166-1 alpha-2）、`region_label`、`notes`、时间戳。
    - `profiles.proxy_id` 可空，外键 `ON DELETE RESTRICT`；删除 `Profile.proxy`。
    - API `GET/POST /api/v1/proxies`、`GET/PATCH/DELETE /api/v1/proxies/{proxy_id}`：响应以 `has_password` 代替 `password`，并返回 `used_by_count`；PATCH 时 `password` 缺失表示不变、`null` 表示清除、字符串表示设置。
    - 删除：代理被任一 Profile 的当前配置或 runtime 绑定版本引用时，返回 409 `proxy_in_use` 并附引用数量。
- 代理凭据只存一份（`proxies` 表）：配置版本快照保存 `proxy_id`、非密连接参数与 `credential_revision`，不保存密码。runtime 启动时按 `proxy_id` 读取凭据，revision 与绑定快照不一致时失败封闭，原因 `proxy_credentials_changed`。凭据不进入日志、错误信息与 SSE。
- 修改代理连接字段（scheme、host、port、username、password）时，在同一个写事务内更新代理，并为每个引用它的 Profile 生成新配置版本（改密码同时递增 `credential_revision`）；事务提交后为受影响的 Profile 广播 SSE。
- 字段分类：
    - 元数据（`name`、`notes`、`sort_order`、`group_id`）直接写 `profiles`，不生成配置版本。
    - 即时策略：`capture_preview`，不生成配置版本，生效与撤销语义由 t040 交付。
    - 运行配置：其余影响浏览器运行的字段，只有值实际变化时才生成新版本。
    - 待应用提示仅由运行配置版本差异驱动。
- `profile_runtimes` 新增 `last_started_at`（observed 进入 running 时写入）与 `last_stopped_at`（进入 stopped 或 error 时写入），ISO 8601 带时区，经 `ProfileRuntimeResponse` 与 SSE 下发。
- 浏览器版本上报：Runner 在 ready 时经 CDP `Browser.getVersion` 取 product 与 userAgent，经 Agent 健康状态、Supervisor 沿现有链路传给 API；`ProfileRuntimeResponse` 增加 `browser_product`、`browser_user_agent`。
- 删除语义（D13）：
    - desired 为 running、observed 为 starting / running / stopping，或绑定了 runtime 实例时，返回 409 `profile_running`。
    - observed 为 error 且没有实例时允许删除；对这类 Profile 请求停止时，observed 收敛为 stopped。
    - 删除时清理 DB 行、Artifact，以及 `profiles/{id}`、`runtime/{id}`、`runtime-events/{id}` 全部 Profile 专属目录。
- 导出 `schemas/openapi/cbrowser_v1.json` 并重新生成前端类型；前端只删除已移除字段的输入、展示与测试，使类型检查、测试与构建通过（新界面由 t037、t038 交付）。
- `domain.md` 增加 Group、Proxy 实体与「环境 / Profile」术语对照，删除 Tag。

### 非范围

- `fingerprint_platform`、字体集绑定与 `font_bundle` 的去留（t041）。
- 预览策略的执行与预览接口（t040）。
- 代理连通性与出口 IP 检测（p040 已暂搁）。
- 新的前端页面（t037、t038、t039）。

### 验收标准

<!-- 规范（门禁必留，不得删除） -->

只写可观察、可独立验证的行为；每条使用稳定且不复用的 `AC-NNN`。需真实部署或人工环境验证时在编号前加 `[deploy]`。创建时均为未勾选（`- [ ]`）；实施验证通过后由实施 Agent 就地打勾（`- [x]`）；由 Review Agent 独立复核打勾真实性。技术选型不作为行为 AC。review 判 FAIL 且需修改交付内容时，实施 Agent 撤回全部打勾，修复并重验后重新打勾；reviewer 用 `TICK-VALID` / `TICK-VOID` 逐条判定。

<!-- /规范 -->

- [x] AC-001：迁移目录只有一个 baseline 修订，其 revision 身份与旧链中的任何修订都不同；空库 `alembic upgrade head` 后 schema 与 ORM 模型一致（autogenerate 无差异）。
- [x] AC-002：用旧 schema 代的数据库启动 API，或用它部署时，均失败封闭并输出重建指引，不修改该数据库。release controller 按修订链判定回退下限：旧 schema 代的 release 被拒绝作为回退目标；同代 release 之间的发布与回退通过。
- [x] AC-003：分组 CRUD 与排序可用。名称重复、超长或颜色不在调色板内时被拒绝；删除分组后，原引用 Profile 的 `group_id` 变为 null；Profile 创建与 PATCH 可设置或清除 `group_id`，引用不存在的分组被拒绝。
- [x] AC-004：代理 CRUD 可用，协议、host、端口按规则校验，名称唯一。代理、Profile、配置版本、错误响应、SSE 与日志中都不出现代理密码；配置版本快照存储中也不含密码；代理响应含 `has_password` 与 `used_by_count`；PATCH `password` 的缺失 / null / 字符串三种语义分别为不变 / 清除 / 设置。
- [x] AC-005：代理被任一 Profile 的当前配置或 runtime 绑定版本引用时，删除返回 409 `proxy_in_use` 并附引用数量，代理与引用关系不变。
- [x] AC-006：只改元数据、只改 `capture_preview`，或提交与当前值相同的运行配置，都不生成新配置版本，运行中的 Profile 不出现待应用。修改代理连接字段时，在同一事务内为每个引用它的 Profile 生成新版本，提交后对这些 Profile 广播 SSE；只改代理名称、地区或备注不生成。
- [x] AC-007：引用代理的 Profile 启动后，浏览器出站流量经过该代理（真实栈 E2E 以本地测试代理记录到请求为证）。代理密码在 Profile 绑定版本之后被修改时，按旧版本重启失败封闭并报告 `proxy_credentials_changed`；应用新版本后启动成功。
- [x] AC-008：带认证 SOCKS5 按 spike 结论处理：引擎支持时端到端经代理出站；不支持时，API 以 422 拒绝创建或更新为该组合，并有测试覆盖。
- [x] AC-009：runtime 进入 running 时写入 `last_started_at`，进入 stopped 或 error 时写入 `last_stopped_at`（ISO 8601 带时区），两者经 runtime 响应与 SSE 下发；前端校验拒绝非法值。
- [x] AC-010：运行中 Profile 的 runtime 响应含 `browser_product` 与 `browser_user_agent`，与容器内浏览器 CDP `Browser.getVersion` 的返回值一致（真实栈 E2E）；未运行时两字段为 null。
- [x] AC-011：desired 为 running、observed 为 starting / running / stopping，或仍绑定实例的 Profile，删除返回 409 `profile_running`，数据与运行时不变。observed 为 error 且无实例的 Profile 可以删除，请求停止后 observed 变为 stopped。删除成功后，DB 行、Artifact 与全部 Profile 专属目录都不存在。
- [x] AC-012：Profile 请求与响应不含 `tags`、`proxy`；导出的 OpenAPI 按资源分组，不含 `v1` 分组。仓库中除 `docs/archive/**`、`docs/reviews/**`、`.repo_template/**`，以及 OpenAPI 分组、Docker 镜像 tag、git tag、HTML 元素 / `tagName` 等不同含义的用法外，不再出现业务 Tag 概念（扫描命令与结果写入实施笔记）。

### 可测试性声明

<!-- 规范（门禁必留，不得删除） -->

逐条说明不可自动测试的 AC 及替代验证；全部可测则写“全部 AC 可自动测试”。

<!-- /规范 -->

全部 AC 可自动测试。

## 上下文区

- 来源：`docs/plan_20261105_ui_redesign.md` WP06、WP07 与第 6.1–6.6、6.9 节（2026-11-05 于 main@3101540 核实，结论见背景）；删除语义 D13 由用户 2026-11-05 决定，error 态判定与目录清理按审阅补全；凭据单一来源、迁移身份与 OpenAPI 分组按 2026-11-05 三份外部审阅修订。

### 有意不测

- 无。

### 测试策略

- unit / integration 覆盖：
    - 分组、代理 CRUD。
    - 版本判定矩阵：元数据 / 即时策略 / 相同值 / 运行字段 / 代理连接字段 / 代理元数据。
    - 密码在全部出口与快照存储中的缺席。
    - 代理修改的单事务版本递增。
    - 删除的状态矩阵与目录清理。
- release controller 用旧 schema 代数据库与 release 夹具验证失败封闭与回退下限。
- API 子进程测试覆盖 409 `proxy_in_use`、`profile_running` 与 PATCH 密码三态。
- 真实栈 E2E 用本地测试代理（http 与 socks5，各含有无认证）验证出站与凭据变更后的失败封闭，并验证浏览器版本与 CDP 一致。
- 浏览器版本传递链路（Agent → Supervisor → API）在实施开始时读代码确定。
- 所有浏览器测试无头运行。

### 未知契约清单

<!-- 规范（门禁必留，不得删除） -->

未核实的外部契约标为 `UNVERIFIED-BLOCKING` 或 `UNVERIFIED-SPIKE`；核实后改写为结论和验证方式。无则写“无”。

<!-- /规范 -->

- CloakBrowser 0.6.4（Chromium 146）对带认证 SOCKS5 的支持：**已验证结论（支持，AC-008 取「端到端经代理出站」分支）**。正式 spike `docs/spikes/s013_authenticated_socks5_engine_probe/report.md` + finding `docs/findings/d031_authenticated_socks5_supported.md`，在 Linux arm64 探针容器用真实引擎实测：`--proxy-server=socks5://user:pass@host:port` 时 greeting 只声明 method `0x02` 并完成用户名/密码子协商；正确凭据 → 认证 accepted、页面经代理加载；错误凭据 → `net::ERR_SOCKS_CONNECTION_FAILED`；无认证对照亦正常。契约背景「Chromium 原生不支持」假设不成立，故 API 不以 422 拒绝该组合，但凭据变更须按 `credential_revision` 失败封闭（AC-007）。复查条件：Chromium 主版本或指纹平台升级后重跑 s013。

### 风险与回退

- 风险：代理密码经日志或错误信息泄露；版本判定漏掉某个运行字段，改了配置却不提示应用；旧 schema 代数据库被误用而没有失败封闭。
- 回退：回退本 task commit 并重建本地数据目录。

### 依赖与约束

- 依赖 t034：在新的 SQLAlchemy / Python 版本上只重写一次模型。
- 本地旧数据目录直接重建，不迁移内容（D9）；只动本 task 的实例，不碰其他会话或 task 的部署实例。
- 所有浏览器测试无头运行。

### Finalization 时更新的 blueprint

- `docs/blueprint/domain.md`：Group、Proxy、元数据 / 即时策略 / 运行配置的区分、术语对照；删除 Tag。
- `docs/blueprint/persistence.md`：新 schema、baseline 身份与此后只追加的迁移规则。
- `docs/blueprint/security.md`：代理凭据单一来源与只写不回显。
- `docs/blueprint/browser_runtime.md`、`docs/blueprint/supervisor.md`：浏览器版本上报链路、活动时间与凭据解析。
- `docs/blueprint/decisions.md`：baseline 重置与此后迁移只追加的规则；Tag 替换为 Group；删除语义 D13；修订 ADR 017 的回退下限判定方式。
- `docs/specs/profile_management.md`、`docs/specs/runtime_lifecycle.md`、`docs/specs/release_deployment.md`；新建 `docs/specs/proxy_management.md`。
