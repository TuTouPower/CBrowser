# Task spec

## 背景

添加代理弹窗暴露名称、协议、地址、端口、用户名、密码、国家码、地区标签、备注 9 个字段，外加独立的「从 URL 粘贴」框。用户只想输入「代理链接」与「备注」，粘贴后自动识别其余字段，国家由真实出口 IP 判定而非手填（p060）。

根因不是表单字段多，而是模型错误：

1. 存储 DTO（`ProxyCreateRequest` / `ProxyResponse` 的 `scheme/host/port/username/password` 平铺字段）直接充当录入模型；`parseProxyUrl` 只是前端辅助，链接与字段是两套可漂移的表示。缺少 `ProxyEndpoint` 值对象。
2. `country_code` 被建模为可写静态配置，实际是出口 IP 的**观测结果**，具有来源、时间、视角、端点指纹、凭据版本与失效条件；端点或密码变更后旧国家不会失效。
3. 探测视角：Browser 运行在独立网络命名空间，网络策略默认拒绝私有/保留地址，代理按解析地址与端口例外放行，DNS 在 gated Runtime 内解析（`docs/blueprint/supervisor.md`）。从 API 进程经代理探测得到的是 API 网络路径，可能与浏览器真实出口不同。
4. `127.0.0.1` 是视角相关地址：宿主、API 容器、Browser 容器指向三个不同网络栈；当前把 host 字符串原样交给 Chromium，本机代理“添加成功、启动连不上”。
5. 链接录入若保留完整链接，密码会进入 React state、DOM、表单历史与日志；探测接口若按请求 host 复用已存密码会形成 SSRF + 凭据外送。

用户 2026-11-10 裁决：loopback 端点由 Supervisor 按 Browser 网络视角映射到宿主并单端口放行（不引入 egress broker，p038 保持 parked）；出口国家在保存后自动探测，不提供保存前草稿探测接口。p040（parked）的出口 IP / 地理位置部分并入本 task，p040 保留连通性与延迟检测且继续暂搁。

## 契约区

### 范围

- 后端领域：新增代理端点值对象（scheme、host、port、username，密码仅以只写秘密存在）与链接解析器，规范化 scheme 白名单、IPv6、端口范围、凭据；端点指纹由 scheme/host/port/username 派生，不含密码。
- 链接格式：标准 URL `scheme://user:pass@host:port`、无协议 `host:port`（默认 http）、`host:port:user:pass`、`user:pass@host:port`；IPv6 与含特殊字符的密码。
- 代理 API 以链接作为创建与端点修改的录入入口；响应返回脱敏链接（不含密码）与派生字段；名称未提供时由 `host:port` 派生。
- 前端代理弹窗：默认只显示「代理链接」「备注」与只读国家状态；高级设置折叠，含名称、协议、地址、端口、用户名、只写密码、地区标签，均由端点值对象渲染与回写，不存在第二份真相；移除旧「从 URL 粘贴」框与国家输入。
- 链接解析后输入框改为显示脱敏链接，密码不留在 DOM、前端查询缓存、URL、日志中。
- 本机端点：host 为 loopback（`127.0.0.0/8`、`localhost`、`::1`）时标记为宿主本机端点；Supervisor 为 Browser 及探测 helper 把它映射到宿主可达地址，网络策略只对该地址与端口放行，其余私有地址仍拒绝。无法映射时在启动/探测前返回明确错误与处置提示。
- 出口观测：新增观测记录（代理、端点指纹、凭据版本、视角、出口 IP、国家码、来源、状态、错误码、观测时间、过期时间）；`Proxy.country_code` 可写字段移除，旧值不导入（无真实用户，不做数据迁移）。
- 探测由 Supervisor 执行：短生命周期 helper 采用与 Browser 相同的网络策略与代理参数访问 IP 回显端点，国家由本机 GeoLite2 数据库判定（复用 engine-cache 中已有 `GeoLite2-City.mmdb`），出口 IP 不发往第三方地理库。
- 代理保存或端点/凭据变更后自动发起探测；端点指纹或凭据版本变化、观测过期时旧观测失效；可手动重试。
- 探测接口只接受代理 ID，按已存端点执行，请求无法指定 host/port/scheme/username。
- 环境列表、Profile 表单、会话详情等展示国家处改为读取当前有效观测（无有效观测显示未知）。
- 重新生成 OpenAPI 与前端类型。

### 非范围

- 不实现统一 egress broker / 内置 mihomo（p038 保持 parked）。
- 不做连通性与延迟检测（p040 剩余部分保持 parked）。
- 不做保存前草稿探测与临时凭据预览接口。
- 不允许人工声明国家。
- 不迁移旧 `country_code` 数据，不保留旧字段兼容。

### 验收标准

<!-- 规范（门禁必留，不得删除） -->

只写可观察、可独立验证的行为；每条使用稳定且不复用的 `AC-NNN`。需真实部署或人工环境验证时在编号前加 `[deploy]`。创建时均为未勾选（`- [ ]`）；实施验证通过后由实施 Agent 就地打勾（`- [x]`）；由 Review Agent 独立复核打勾真实性。技术选型不作为行为 AC。review 判 FAIL 且需修改交付内容时，实施 Agent 撤回全部打勾，修复并重验后重新打勾；reviewer 用 `TICK-VALID` / `TICK-VOID` 逐条判定。

<!-- /规范 -->

- [ ] AC-001：添加代理弹窗默认只显示代理链接、备注与只读国家状态；高级设置默认折叠，展开后可编辑名称、协议、地址、端口、用户名、密码、地区标签，且没有国家输入。
- [ ] AC-002：四种链接格式（含 IPv6 与特殊字符密码）均解析为正确端点；非法输入显示字段级错误，不清空已解析结果。
- [ ] AC-003：修改高级字段后脱敏链接同步更新；修改链接后高级字段同步更新，两者始终一致。
- [ ] AC-004：链接解析与保存后，密码不出现在 DOM、前端查询缓存、URL、API 响应与日志中；界面显示脱敏链接。
- [ ] AC-005：未手动填写名称时名称为 `host:port`；手动修改后不被后续解析覆盖。
- [ ] AC-006：代理保存后自动探测出口，界面依次显示检测中与国家码或未知；失败时显示未知并可重试，不出现猜测值。
- [ ] AC-007：端点或凭据变更后旧观测立即失效，界面不再显示旧国家，并自动重新探测；观测过期后同样失效。
- [ ] AC-008：在「API 直连出口 ≠ 代理出口」的夹具下，观测的出口 IP 与国家等于代理出口，而非 API 出口。
- [ ] AC-009：探测接口无法把已存密码发往与已存端点不同的 host、port、scheme 或 username；负向测试覆盖。
- [ ] AC-010：链接为 `http://127.0.0.1:<port>` 的宿主本机代理，被 Profile 引用后 Browser 可经其访问外网，探测也可得到观测；Browser 网络策略对宿主其它端口与其它私有地址仍拒绝。
- [ ] AC-011：本机端点无法映射时，启动与探测在执行前返回明确错误与处置提示，不出现启动成功但无法联网。
- [ ] AC-012：[deploy] 真实部署端到端：粘贴链接创建代理 → 自动观测国家 → 环境引用 → 启动 → 浏览器内访问 IP 回显所得出口与观测一致；宿主本机代理链路同样成立。

### 可测试性声明

<!-- 规范（门禁必留，不得删除） -->

逐条说明不可自动测试的 AC 及替代验证；全部可测则写“全部 AC 可自动测试”。

<!-- /规范 -->

- AC-001..011：可自动测试（解析器矩阵单测、API 契约与负向测试、前端组件测试含 DOM/查询缓存断言、Supervisor helper 与网络策略集成测试、带受控上游代理与 IP 回显夹具的 E2E）。
- AC-012：依赖真实外部代理与公网出口；替代验证为真实部署后人工执行端到端流程并记录出口 IP 与观测对比。

## 上下文区

- 来源：p060（2026-11-10 复核：`ProxyCreateRequest` / `ProxyUpdateRequest` 仍为平铺字段且 `country_code` 可写；`credential_revision` 已存在可复用；前端 `parseProxyUrl.ts` 为表单辅助；`docker_adapter._resolved_endpoint` 对 IP 字面量直接放行，loopback 会落到容器自身网络栈）；p040（parked，出口 IP 部分并入）。
- 事实：本机 `data/v2/engine-cache/geoip/GeoLite2-City.mmdb` 已由 runtime cache initializer 下载；p062 实测 OrbStack 容器经 `host.docker.internal:7890` 可达宿主 FlClash（Docker CLI 启动容器）。
- `country_code` 现有读取位点：`ProxyTable.tsx`、`ProxyFormDialog.tsx`、`EnvironmentTable.tsx`、`SessionDetailsPanel.tsx`、`repository.py`、`models.py`。

### 有意不测

- 第三方 IP 回显服务可用性：外部依赖，以本地受控回显夹具测试逻辑。
- GeoLite2 库自身准确性：外部数据。

### 测试策略

- 单元：链接解析矩阵、端点规范化与指纹、观测失效规则（指纹/凭据版本/TTL）、探测接口负向、脱敏链接。
- 前端：弹窗默认可见字段、高级字段双向一致、密码不在 DOM 与查询缓存、名称派生、国家状态徽标。
- 集成/E2E：受控上游代理 + 受控 IP 回显夹具（API 直连出口与代理出口不同），验证观测取自 Browser 同视角；宿主本机端点映射与网络策略放行/拒绝。

### 未知契约清单

<!-- 规范（门禁必留，不得删除） -->

未核实的外部契约标为 `UNVERIFIED-BLOCKING` 或 `UNVERIFIED-SPIKE`；核实后改写为结论和验证方式。无则写“无”。

<!-- /规范 -->

- Supervisor 经 Docker API 创建的沙箱（非 Docker CLI）能否解析并到达宿主 loopback 上仅监听 `127.0.0.1` 的服务，以及需显式 `extra_hosts host-gateway` 与否：UNVERIFIED-SPIKE，实施前在本机 OrbStack 以 Supervisor 同参数创建容器实测并写入 findings。
- IP 回显端点选型（自建/第三方、返回格式、经 HTTP 与 SOCKS5 代理的可用性）：UNVERIFIED-SPIKE，实施时以最小回显请求实测并记录数据外发范围。

### 风险与回退

- 风险：宿主映射放宽网络策略导致 Browser 可访问宿主其它服务；以“仅放行映射地址+端口”负向测试覆盖。
- 风险：探测 helper 与 Browser 参数漂移导致视角不一致；helper 与 Browser 共享同一参数构造函数。
- 风险：移除 `country_code` 影响多处展示；全量替换为观测读取。
- 回退：revert 实现 commit；数据库增量迁移可回退。

### 依赖与约束

- 无前置 task；与 t051 均改 Supervisor `docker_adapter.py`，建议 t051 先合并。
- 需数据库增量迁移（观测表、移除 `country_code`）。

### Finalization 时更新的 blueprint

- `docs/blueprint/domain.md`：代理端点值对象与出口观测。
- `docs/blueprint/supervisor.md`：宿主本机端点映射、探测 helper 与网络策略。
- `docs/blueprint/security.md`：链接录入秘密处理与探测接口凭据外送防护。
- `docs/blueprint/frontend.md`：代理录入交互。
- `docs/blueprint/decisions.md`：新增 ADR「代理链接为唯一录入，国家为 Browser 同视角观测」。
- `docs/specs/proxy_management.md`：录入与观测行为。
