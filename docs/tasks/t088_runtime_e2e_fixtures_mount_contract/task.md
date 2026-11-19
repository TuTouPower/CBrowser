# Task spec

## 背景

`t075` 要求所有 Profile 必须绑定已验证平台字体集，`t080` / `t081` 将运行时目录和字体存储全面收敛至 Linux named volume（`MountPlanner`）。真实 Docker E2E 夹具和旧 E2E 用例仍沿用宿主目录 bind mount 与无字体绑定构造方式，导致全量 Docker E2E 门禁在并行与串行阶段大面积因 `font_set_unavailable` 与 named volume subpath `404` 失败。

## 契约区

### 范围

- 更新真实 Docker E2E 拓扑夹具（`GatewayTopologyHarness` 及其衍生夹具）与直接驱动 `DockerAdapter`、`SupervisorCore`、`BrowserRunner` 的 E2E 测试，使测试前提完整匹配生产字体绑定与 named volume 布局契约。
- 确保测试结束后精确清理各自创建的临时容器、网络与命名卷，不污染生产部署资源。

### 非范围

- 不放松或绕过生产代码的 `MountPlanner` fail-closed 挂载约束、`FontSetUnavailableError` 校验或 `scripts/run_gates.sh` 对 `CBROWSER_FONTS_DIR` 的隔离策略。
- 不修改现有 E2E 业务断言或降级/跳过真实拓扑检查，保留负向边界测试（缺失字体、缺失卷子路径等）的独立覆盖。

### 验收标准

<!-- 规范（门禁必留，不得删除） -->

只写可观察、可独立验证的行为；每条使用稳定且不复用的 `AC-NNN`。需真实部署或人工环境验证时在编号前加 `[deploy]`。创建时均为未勾选（`- [ ]`）；实施验证通过后由实施 Agent 就地打勾（`- [x]`）；由 Review Agent 独立复核打勾真实性。技术选型不作为行为 AC。review 判 FAIL 且需修改交付内容时，实施 Agent 撤回全部打勾，修复并重验后重新打勾；reviewer 用 `TICK-VALID` / `TICK-VOID` 逐条判定。

<!-- /规范 -->

- [ ] AC-001：共享真实拓扑 E2E 夹具按生产一致的 named volume 与只读平台字体集布局初始化 API/Supervisor/Caddy/Gateway 环境，保证由控制面创建并启动 Profile 时成功完成字体绑定与沙箱挂载，同时保留缺失或异常字体场景的独立负向验证。

- [ ] AC-002：直接验证缓存初始化、X11 权限收敛、运行时默认配置、策略失败封闭、双 Profile 隔离等独立 Docker E2E 用例采用预初始化的测试前缀命名卷与有效字体集完成前置准备，生产 fail-closed 逻辑保持未放宽，且测试结束完全清理所创建的测试容器、网络及命名卷。

- [ ] AC-003：在当前源码构建的不可变镜像与缓存前提下执行完整门禁必跑模式（含并行与串行两阶段 E2E、`image_packages` 与合并 JUnit 用例下限），全部门禁套件退出码为 0，不存在未授权跳过或断言弱化。

### 可测试性声明

<!-- 规范（门禁必留，不得删除） -->

逐条说明不可自动测试的 AC 及替代验证；全部可测则写“全部 AC 可自动测试”。

<!-- /规范 -->

全部 AC 可自动测试。

## 上下文区

- 关联 spec：docs/specs/gate_verification.md
- 来源：p145（2026-11-19，已确认真实 Docker E2E 14 个并行失败与串行失败均由旧夹具缺少字体绑定与 named volume 子路径引起）

### 有意不测

- 不在云端或非 Docker 环境模拟运行本批 E2E 用例：本批仅针对已配置本机 Docker daemon 与不可变测试镜像的必跑模式验证。

### 测试策略

- 先运行现有 `tests/e2e/` 失败子集确认复现，再依次重构 `GatewayTopologyHarness` 及独立 E2E 用例为 named volume + 受管字体集契约，最终执行完整 `CBROWSER_E2E_REQUIRED=1 CBROWSER_RUN_E2E=1` 全量门禁跑通并行与串行全部用例。

### 未知契约清单

<!-- 规范（门禁必留，不得删除） -->

未核实的外部契约标为 `UNVERIFIED-BLOCKING` 或 `UNVERIFIED-SPIKE`；核实后改写为结论和验证方式。无则写“无”。

<!-- /规范 -->

- 无。生产 `compose.yaml` 与 `MountPlanner`、`font_set_mount` 的契约已在仓内代码明确定义。

### 风险与回退

- 风险：并行 xdist worker 间若命名卷或字体目录前缀未隔离会产生清理互相干扰。通过每个测试前缀独立的命名卷及容器标签隔离并在 fixture `finally` 与 `gate_container_cleanup.py` 精确回收规避。
- 回退：通过标准 Git task 分支回退或保留问题记录重跑。

### 依赖与约束

- 必须保持 `docs/blueprint/conventions.md` 中关于 `t080` named volume 隔离与 `scripts/run_gates.sh` 隔离 `CBROWSER_FONTS_DIR` 的既有约定，以及 `tests/unit/test_gate_count` / `test_t045_*` 对共享栈和资源清理的约束。

### Finalization 时更新的 blueprint

- `docs/blueprint/testing.md`：若因测试收集数量变化或夹具契约补充需要同步说明则更新，否则写无新增变更。
