# Task spec

## 背景

Selkies 扩展目前靠 WebRTCService 运行时替换、动态子类与 \_XTestKeyboard 私有 ABI 校验。目标是把采集策略和输入映射落到项目可维护边界，删除私有运行时补丁，同时保持已验行为。

## 契约区

### 范围

- 验证锁定 Selkies 制品的公开扩展能力；不足时采用源码受控 vendor/fork 并明确维护边界，直接替换旧注入路径。
- 采集帧率、可见性及键盘映射由自有可测试实现承担；同步入口、依赖导出、官方客户端适配与升级说明。

### 非范围

- 不启用 p077 双模回退，不恢复 TURN/coturn 或 ICE 代次接管；不升级到未验证的上游 main。
- 不取消可复现制品版本与 SHA256 固定；删除的是私有 ABI 运行时耦合，不承诺任意未来版本无需验证。

### 验收标准

<!-- 规范（门禁必留，不得删除） -->

只写可观察、可独立验证的行为；每条使用稳定且不复用的 `AC-NNN`。需真实部署或人工环境验证时在编号前加 `[deploy]`。创建时均为未勾选（`- [ ]`）；实施验证通过后由实施 Agent 就地打勾（`- [x]`）；由 Review Agent 独立复核打勾真实性。技术选型不作为行为 AC。review 判 FAIL 且需修改交付内容时，实施 Agent 撤回全部打勾，修复并重验后重新打勾；reviewer 用 `TICK-VALID` / `TICK-VOID` 逐条判定。

<!-- /规范 -->

- [ ] AC-001：Stream 启动后可建立官方 HELLO/client_tab_id/resume_key 信令与真实 WebRTC 首帧，无运行时全局替换上游类或实例私有方法。
- [ ] AC-002：前台静止/运动按现行 8/30 FPS 策略仲裁，全后台暂停捕获，恢复前台重新出帧；后台 viewer 不压低前台流。
- [ ] AC-003：中文 IME、普通键盘、剪贴板、复制标签隔离及 viewer resume 保持既有行为。
- [ ] AC-004：Stream 启动不再通过解析上游 Python AST、inspect.getsource 或私有属性清单验证键盘 ABI；自有策略层单测无需导入上游私有类。
- [ ] AC-005：受控源制品与客户端完整性可复验；升级流程可定位项目维护改动，不需执行旧 monkey patch ABI 校验流程。

### 可测试性声明

<!-- 规范（门禁必留，不得删除） -->

逐条说明不可自动测试的 AC 及替代验证；全部可测则写“全部 AC 可自动测试”。

<!-- /规范 -->

全部 AC 可自动测试；涉及真实 Chrome、引擎、Docker 或网络行为的 AC 使用隔离真实环境探针，不以 mock 结果替代。界面视觉补人工核验，第三方公网检查仅显式 opt-in。

## 上下文区

- 来源：`p072`。2026-11-13 核实 stream_agent/agent.py 对 selkies_main.WebRTCService 赋值，policy.py 动态子类，x11_keymap.py 的 SUPPORTED_SELKIES_VERSION/inspect/ast。tests/unit/test_stream_keymap_abi.py 与 ADR 022 固化旧边界，实施时整体替换失效测试并说明。

### 有意不测

- 不启用 p077 双模回退，不恢复 TURN/coturn 或 ICE 代次接管；不升级到未验证的上游 main。：超出本 task 范围；其余已声明 AC 不豁免。

### 测试策略

- 先做锁定制品的扩展边界 spike，验证启动/信令不变式；结果入 findings 后定稿实现。
- 纯策略单测 + 真 Chrome/真引擎 WebRTC E2E，覆盖多 viewer、可见性仲裁、帧率、输入法、剪贴板、resume；全量项目门禁。
- 项目门禁：按 docs/blueprint/testing.md 的 doctor_cmd / test_cmd / blackbox_verify 执行；本批创建仅验证文档结构，不代表实现验收。

### 未知契约清单

<!-- 规范（门禁必留，不得删除） -->

未核实的外部契约标为 `UNVERIFIED-BLOCKING` 或 `UNVERIFIED-SPIKE`；核实后改写为结论和验证方式。无则写“无”。

<!-- /规范 -->

- Selkies 锁定制品公开扩展点及源码重分发约束：UNVERIFIED-SPIKE，读取实际 wheel/源码与许可证并完成最小启动验证，确定公开扩展或受控源码方案。

### 风险与回退

- 风险：替换入口可能破坏信令、X11 或采集生命周期；无真实链证据不得声称行为等价。
- 回退：回退整个不可变 release 与客户端匹配制品；不在新实现内保留旧 ABI fallback。

### 依赖与约束

- 保持本机 Docker/OrbStack 与唯一外部 Chrome 客户端边界；不复活 parked 条目。依赖建议见 progress.md；产品 BLOCKING 未确认前不可 start，SPIKE 先验证后回填。

### Finalization 时更新的 blueprint

- docs/blueprint/architecture.md、docs/blueprint/stream_runtime.md：自有扩展边界。
- docs/blueprint/decisions.md：修订 ADR 007/013/022 的现行描述并记录新决策。
- docs/blueprint/testing.md：替代 ABI 扫描的行为验收与升级门禁。
