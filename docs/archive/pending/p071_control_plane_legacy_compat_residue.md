# p071 控制面协议与资源归属层遗留兼容路径清理（零兼容性负担）

- 来源：2026-11-13 开发铁律审阅（技术债自查）
- 内容：t056「统一 ErrorResponse」改造后仍保留旧 `detail` 形状读取与混合版本降级路径，instance-id 归属判定仍保留 label 引入前的 legacy 分支，输入层存在新旧双轨校验。按「零兼容性负担」应直接删除过时路径、统一为单一形状，并修订把兼容行为写进规范的 `conventions.md:64`。当前未开：本次审阅为只读，未授权改生产代码。
- 处理：t062；resolution=transferred；reason=已核实当前代码与有效 task，按同一交付面聚合转交 t062；过时描述与剩余范围见 task spec，归档仅表示转办
- 时间：2026-11-13T18:57:05+08:00

## 违反点与证据

1. 协议层旧形状读取（t056 A15 后未删）：
    - `src/backend/cbrowser/api/runtime_coordinator.py:76-95` — `detail` 与裸文本兜底，注释自认 "A legacy `detail` body and raw text remain as fallbacks"。
    - `src/backend/cbrowser/supervisor/gateway_client.py:101-105` — `message or detail`，注释 "keep the legacy `detail` read so a mixed-version Gateway still parses"。
    - `src/backend/cbrowser/agent_executor/session.py:840-854` — `error` → `details.code` → `detail.code` → 硬编码 `control_conflict` 四层回退。
2. 双轨请求降级：`src/backend/cbrowser/supervisor/core.py:3208-3220` — 遇 422 去掉 `browser_product`/`browser_user_agent` 字段重发，为「API 层尚未声明两个版本字段」留并存期。
3. 规范层面反向固化：`docs/blueprint/conventions.md:64` 明文「Supervisors 混版本时旧形状 `detail` 与纯文本体仍被解析，不丢信息」，与铁律冲突，须一并改写。
4. 资源归属 legacy 分支（`com.cbrowser.instance-id` 已定为唯一判据）：
    - `src/backend/cbrowser/supervisor/network_spec.py:57-76` — 双侧无 deployment id 时回退 name+prefix+managed-by 旧检查。
    - `src/backend/cbrowser/supervisor/docker_adapter.py:917-923` — 注释自认 "legacy behaviour"，未配置时 prefix 全量认领。
    - `scripts/deploy.sh:577-579` — label 缺失但 compose project 匹配的旧容器豁免。
5. 输入层双轨与死输出：
    - `src/backend/cbrowser/launch_args.py:70-80` — `filter_launch_args` 对 legacy DB 行/快照静默丢弃非法参数，与严格 `validate_launch_args` 并存。
    - `src/backend/cbrowser/domain/profile_locale.py:87-90` — `None for legacy Profiles` 合法值分支。
    - `src/frontend/src/features/browser-session/adapter.ts:256-261` — `profileId || profile_id || 全局注入 || 传入值 || "default"` 五层兜底。
    - `src/backend/cbrowser/network_config_cli.py:34-36` — 仍输出已退役的 `BIND_HOST` / `PUBLIC_ORIGIN`，无消费方。

## 目标

1. 全部下游错误解析只认 `error`/`message`/`retryable` + `details` 单一形状，删除 `detail`、裸文本、硬编码兜底；非规范响应按错误处理而非静默兼容。
2. 删除 422 去字段重发；契约版本由统一发布链保证，不做滚动并存。
3. 归属判定只认 `com.cbrowser.instance-id`，删除无 label 时的 legacy 回退；t051 前创建的旧沙箱按既有 orphan 路径处置，不新增兼容分支。
4. 输入层收敛为单一严格校验，删除 `filter_launch_args`、多参数名 fallback、`None` 值分支与死输出变量。
5. 同步修订 `conventions.md:64`、`architecture.md` 5.5 节与相关 ADR 的现行文档面。

## 非目标

- 不改数据库迁移层：`migrations.py` 已 fail-closed、单 baseline、全部 `downgrade()` 抛错，符合铁律。
- 不删部署同代回滚（`previous` 指针）：其已拒绝跨代/降级/`ALLOWED_ORIGINS` 兼容，不算兼容层。
- `config/deploy/{previous,current}_release`、`compose.env` 为 gitignored 本地残留，不入库，不作为整改主体。
- 不在本 pending 内实施、建 task 或改生产代码。

## 验收

1. 全仓控制面协议解析路径 grep `detail` / `mixed-version` / `legacy ... parses` 零命中。
2. 混合版本响应体一律按非规范错误处理，不再静默解析。
3. 门禁测试覆盖：错误形状、422 响应、无 label 资源、非法 launch_args、多参数名输入。
