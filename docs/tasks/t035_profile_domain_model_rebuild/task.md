# Task spec

## 背景

`docs/plan_20261105_ui_redesign.md` 第 6 节（D3、D4、D9，用户 2026-11-05 确认）重建 Profile 领域模型：独立代理库、单值分组替换 Tag、元数据与运行配置拆分、运行时活动时间与浏览器版本上报。当前没有正式用户，也不需要兼容和数据迁移（用户 2026-11-05 明确）。2026-11-05 于 main@3101540 核实现状：

- Tag：`profile_tags` 表（`adapters/database/models.py:133`），`domain/models.py` 的 Profile 请求/响应含 `tags: list[Tag]`，`repository.update_profile` 把 tags 纳入请求签名与快照。
- 代理：`Profile.proxy` 为最长 512 的 URL 字符串（`adapters/database/models.py:28`），API 原样回显（含账密）。
- 配置版本：`repository.update_profile`（`repository.py:294` 起）任何 PATCH 都写入新的 `current_config_version` 与快照，运行中的 Profile 仅改名也提示「待应用并重启」。
- 运行时：没有最后启动 / 停止时间，也没有真实的浏览器版本上报。
- 删除：`ProfileService.delete_profile`（`services/profile_service.py:334`）不检查运行态，直接删除 DB 行。用户 2026-11-05 决定：非 stopped 状态拒绝删除。
- OpenAPI：各 router 使用 `APIRouter(tags=[...])` 分组（auth、artifacts、control、automation、internal-\* 等）。

## 契约区

### 范围

- 直接改写 `src/backend/migrations/versions/0001_initial_schema.py` 为目标 schema：不新增增量迁移，不写数据迁移，不迁移本地测试数据（本地旧库文件改名保留后重建）。
- Group：表 `profile_groups`（`id`、`name` 唯一且 1–64 字符、`color` 取 slate / blue / teal / green / amber / orange / red / violet、`sort_order`、`created_at`、`updated_at`）；`profiles.group_id` 可空，外键 `ON DELETE SET NULL`；API `GET/POST /api/v1/groups`、`PATCH/DELETE /api/v1/groups/{group_id}`，支持批量调整排序。
- 删除 Tag 的全部实现：模型、表、请求与响应字段、快照字段、文案键；删除所有 `APIRouter(tags=...)` 参数，导出的 OpenAPI 不含 `tags`。
- Proxy：表 `proxies`（`id`、`name` 唯一、`scheme` 取 http / https / socks5、`host`、`port`、`username`、`password`、`country_code`（ISO 3166-1 alpha-2）、`region_label`、`notes`、时间戳）；`profiles.proxy_id` 可空，外键 `ON DELETE RESTRICT`；删除 `Profile.proxy`。API `GET/POST /api/v1/proxies`、`GET/PATCH/DELETE /api/v1/proxies/{proxy_id}`：响应以 `has_password` 代替 `password`，并返回 `used_by_count`；PATCH 时 `password` 缺失表示不变、`null` 表示清除、字符串表示设置；删除被引用的代理返回 409 `proxy_in_use` 并附引用数量。
- 元数据与运行配置拆分：元数据（`name`、`notes`、`sort_order`、`group_id`）直接写 `profiles`，不生成配置版本；运行配置（其余影响浏览器运行的字段，含 `proxy_id` 解析出的完整代理参数）只有值实际变化时才生成新版本；修改代理的连接字段（scheme、host、port、username、password）时，为每个引用它的 Profile 生成新版本。
- 配置版本快照保存 `proxy_id` 与解析后的代理参数，runtime 以绑定快照为准；版本查询接口对代理密码脱敏；代理凭据不进入日志、错误信息与 SSE。
- `profile_runtimes` 新增 `last_started_at`（observed 进入 running 时写入）与 `last_stopped_at`（进入 stopped 或 error 时写入），ISO 8601 带时区，经 `ProfileRuntimeResponse` 与 SSE `ProfileRuntimeStatusEvent` 下发。
- 浏览器版本上报：Runner 在 ready 时经 CDP `Browser.getVersion` 取 product 与 userAgent，经 Agent 健康状态、Supervisor 沿现有链路传给 API；`ProfileRuntimeResponse` 增加 `browser_product` 与 `browser_user_agent`。
- 删除语义：非 stopped 状态的 Profile 删除返回 409 `profile_running`。
- 导出 `schemas/openapi/cbrowser_v1.json`，重新生成前端类型；前端只删除已移除字段的输入、展示与测试，使类型检查、测试与构建通过（新界面由 t037 / t038 交付）。
- `domain.md` 增加 Group、Proxy 实体与「环境 / Profile」术语对照，删除 Tag。

### 非范围

- `fingerprint_platform` 字段与 `font_bundle` 的去留（t041）。
- 预览接口与 `profile_preview` 事件（t040）。
- 代理连通性与出口 IP 检测（p040 已暂搁）。
- 新的前端页面（t037、t038、t039）。

### 验收标准

<!-- 规范（门禁必留，不得删除） -->

只写可观察、可独立验证的行为；每条使用稳定且不复用的 `AC-NNN`。需真实部署或人工环境验证时在编号前加 `[deploy]`。创建时均为未勾选（`- [ ]`）；实施验证通过后由实施 Agent 就地打勾（`- [x]`）；由 Review Agent 独立复核打勾真实性。技术选型不作为行为 AC。review 判 FAIL 且需修改交付内容时，实施 Agent 撤回全部打勾，修复并重验后重新打勾；reviewer 用 `TICK-VALID` / `TICK-VOID` 逐条判定。

<!-- /规范 -->

- [ ] AC-001：分组 CRUD 与排序可用。名称重复、超长或颜色不在调色板内时被拒绝；删除分组后，原引用 Profile 的 `group_id` 变为 null；Profile 创建与 PATCH 可设置或清除 `group_id`，引用不存在的分组被拒绝。
- [ ] AC-002：代理 CRUD 可用，协议、host、端口按规则校验，名称唯一。代理、Profile、配置版本、错误响应与 SSE 中都不出现代理密码；代理响应含 `has_password` 与 `used_by_count`；PATCH `password` 的缺失 / null / 字符串三种语义分别为不变 / 清除 / 设置。
- [ ] AC-003：删除被引用的代理返回 409 `proxy_in_use` 并附引用数量，代理与引用关系不变。
- [ ] AC-004：只改元数据（名称、备注、排序、分组），或提交与当前值相同的运行配置，都不生成新配置版本，运行中的 Profile 不出现待应用；修改代理连接字段时，为每个引用它的 Profile 生成新版本；只改代理名称、地区或备注不生成。
- [ ] AC-005：配置版本快照含 `proxy_id` 与解析后的完整代理参数，版本查询响应对密码脱敏；引用代理的 Profile 启动后，浏览器出站流量经过该代理（真实栈 E2E 以本地测试代理记录到请求为证）。
- [ ] AC-006：带认证 SOCKS5 按 spike 结论处理：引擎支持时端到端经代理出站；不支持时，API 以 422 拒绝创建或更新为该组合，并有测试覆盖。
- [ ] AC-007：runtime 进入 running 时写入 `last_started_at`，进入 stopped 或 error 时写入 `last_stopped_at`（ISO 8601 带时区），两者经 runtime 响应与 SSE 下发；前端校验拒绝非法值。
- [ ] AC-008：运行中 Profile 的 runtime 响应含 `browser_product` 与 `browser_user_agent`，与容器内浏览器 CDP `Browser.getVersion` 的返回值一致（真实栈 E2E）；未运行时两字段为 null。
- [ ] AC-009：删除非 stopped 状态的 Profile 返回 409 `profile_running`，数据与运行时都不变；删除 stopped 的 Profile 时，一并清理其数据与 Artifact。
- [ ] AC-010：空库执行 `alembic upgrade head` 后，schema 与 ORM 模型一致（autogenerate 无差异），且只存在 baseline 一个修订。
- [ ] AC-011：导出的 OpenAPI 不含 `tags`；Profile 请求与响应不含 `tags`、`proxy`；仓库中除 `docs/archive/**`、`docs/reviews/**`、`.repo_template/**`，以及 Docker 镜像 tag、git tag、HTML 元素 / `tagName` 等不同含义的用法外，不再出现业务 Tag 概念（扫描命令与结果写入实施笔记）。

### 可测试性声明

<!-- 规范（门禁必留，不得删除） -->

逐条说明不可自动测试的 AC 及替代验证；全部可测则写“全部 AC 可自动测试”。

<!-- /规范 -->

全部 AC 可自动测试。

## 上下文区

- 来源：`docs/plan_20261105_ui_redesign.md` WP06、WP07 与第 6.1–6.6、6.9 节（2026-11-05 于 main@3101540 核实，结论见背景）；删除语义由用户 2026-11-05 决定。

### 有意不测

- 无。

### 测试策略

- unit / integration 覆盖分组、代理 CRUD，元数据与运行配置的版本判定矩阵（元数据 / 相同值 / 运行字段 / 代理连接字段 / 代理元数据），以及密码在全部出口的脱敏。
- API 子进程测试覆盖 409 `proxy_in_use`、`profile_running` 与 PATCH 密码三态。
- 真实栈 E2E 用本地测试代理（http 与 socks5，各含有无认证）验证出站，并验证浏览器版本与 CDP 一致。
- 浏览器版本传递链路（Agent → Supervisor → API）在实施开始时读代码确定。
- 所有浏览器测试无头运行。

### 未知契约清单

<!-- 规范（门禁必留，不得删除） -->

未核实的外部契约标为 `UNVERIFIED-BLOCKING` 或 `UNVERIFIED-SPIKE`；核实后改写为结论和验证方式。无则写“无”。

<!-- /规范 -->

- CloakBrowser 0.6.4（Chromium 146）对带认证 SOCKS5 的支持（Chromium 原生不支持）：UNVERIFIED-SPIKE，用真实引擎经本地带认证 SOCKS5 代理实测，结论决定 AC-006 的分支并写入 `docs/findings/`。

### 风险与回退

- 风险：代理密码经快照、日志或错误信息泄露；版本判定漏掉某个运行字段，改了配置却不提示应用。
- 回退：回退本 task commit 并重建本地库。

### 依赖与约束

- 依赖 t034：在新的 SQLAlchemy / Python 版本上只重写一次模型。
- 与 t040、t041 同改 baseline 与 runtime 模型，由它们依赖本 task。
- 所有浏览器测试无头运行。

### Finalization 时更新的 blueprint

- `docs/blueprint/domain.md`：Group、Proxy、元数据与运行配置的区分、术语对照；删除 Tag。
- `docs/blueprint/persistence.md`：新 schema 与 baseline 重写策略。
- `docs/blueprint/security.md`：代理密码只写不回显。
- `docs/blueprint/browser_runtime.md`、`docs/blueprint/supervisor.md`：浏览器版本上报链路与活动时间。
- `docs/blueprint/decisions.md`：baseline 重写策略及失效条件（出现真实用户后迁移恢复为只追加）；Tag 替换为 Group；运行中 Profile 拒绝删除。
- `docs/specs/profile_management.md`、`docs/specs/runtime_lifecycle.md`；新建 `docs/specs/proxy_management.md`。
