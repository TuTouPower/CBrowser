# Task spec

## 背景

Selkies 的采集策略和键盘映射依赖动态子类、运行时全局替换和私有 ABI 扫描。本 task 将扩展改为可审计的受控制品，保留实际媒体和输入行为。

## 契约区

### 范围

- 先验证公开扩展点；不足时使用固定上游 wheel/sdist + 构建期最小显式补丁，或独立受控本地包；不将完整上游源码平铺进业务源码目录。
- 制品身份包含上游版本/哈希、补丁序列及哈希、构建过程、最终包哈希；前端静态清单单独校验，声明其与服务端来源关系。
- 采集策略与键盘映射由明确自有边界承担，移除运行时 monkey patch、上游源码 AST 和私有属性清单门禁。

### 非范围

- 不启用 p077 双模、TURN 或未验证 main；不承诺任意未来版本无需回归。
- active_peers 的现行可见性信号不足以证明宿主浏览器 tab 前台状态；不在本 task 增加新可见性协议。

### 验收标准

<!-- 规范（门禁必留，不得删除） -->

只写可观察、可独立验证的行为；每条使用稳定且不复用的 `AC-NNN`。需真实部署或人工环境验证时在编号前加 `[deploy]`。创建时均为未勾选（`- [ ]`）；实施验证通过后由实施 Agent 就地打勾（`- [x]`）；由 Review Agent 独立复核打勾真实性。技术选型不作为行为 AC。review 判 FAIL 且需修改交付内容时，实施 Agent 撤回全部打勾，修复并重验后重新打勾；reviewer 用 `TICK-VALID` / `TICK-VOID` 逐条判定。

<!-- /规范 -->

- [ ] [deploy] AC-001：Stream 通过实际官方 HELLO/client_tab_id/resume_key 建立 WebRTC 首帧，无运行时全局替换上游类/实例方法。
- [ ] [deploy] AC-002：按现行 active_peers/媒体 consumer 活跃信号仲裁静止 8 FPS、运动/输入 30 FPS，零活跃 consumer 时暂停并能恢复；单个暂停 consumer 不压低其他活跃 consumer，报告以实际信号命名。
- [ ] [deploy] AC-003：中文 IME、普通键盘、剪贴板、复制标签隔离、viewer resume 保持既有行为。
- [ ] AC-004：启动不再解析上游 AST/inspect.getsource 或私有 ABI 清单；自有策略单测不依赖上游私有类。
- [ ] AC-005：服务端受控包可从固定上游制品和已记录补丁重复构建，最终哈希可核对；客户端静态资源保持独立完整性验证，两端来源关系可追溯。

### 可测试性声明

<!-- 规范（门禁必留，不得删除） -->

逐条说明不可自动测试的 AC 及替代验证；全部可测则写“全部 AC 可自动测试”。

<!-- /规范 -->

- AC-001：需隔离真实 Docker/Chrome/引擎拓扑验收，可自动化但不可用 mock 替代；[deploy] 不授权生产发布。
- AC-002：需隔离真实 Docker/Chrome/引擎拓扑验收，可自动化但不可用 mock 替代；[deploy] 不授权生产发布。
- AC-003：需隔离真实 Docker/Chrome/引擎拓扑验收，可自动化但不可用 mock 替代；[deploy] 不授权生产发布。
- AC-004：可自动测试，触达生产函数或实际工具入口。
- AC-005：可自动测试，触达生产函数或实际工具入口。

## 上下文区

- 来源：2026-11-13 审阅复核：p072；复核 agent.py/policy.py/x11_keymap.py。架构中“不再依赖 Selkies 私有接口适配器”只适用于已删除的 ICE 代次适配器，不能泛化为采集/键盘已无私有扩展。

### 有意不测

- 非范围中的新增产品功能不作为本 task 验收；已声明 AC 不豁免。

### 测试策略

- 扩展与制品 spike 后再实施；真 Chrome/引擎覆盖帧率、consumer 暂停恢复、中文输入、复制标签和 resume。
- 整体替换失效 test_stream_keymap_abi.py、test_t043_selkies_pin.py 的旧补丁假设并说明理由；同时复验依赖锁、vendor 静态清单、hygiene 和镜像安装包身份，不以全部放宽扫描规避 vendor 边界。
- 按 docs/blueprint/testing.md 的 doctor_cmd/test_cmd/blackbox_verify 执行；本次仅改 backlog，创建校验不代表实现验收。

### 未知契约清单

<!-- 规范（门禁必留，不得删除） -->

未核实的外部契约标为 `UNVERIFIED-BLOCKING` 或 `UNVERIFIED-SPIKE`；核实后改写为结论和验证方式。无则写“无”。

<!-- /规范 -->

- 公开扩展能力、许可证及受控包构建：UNVERIFIED-SPIKE，读取实际 2.2.1 制品验证公开扩展或构建期补丁方案；不预先声称 hook 一定不存在。

### 风险与回退

- 风险：跨模块/制品或状态变更需按上述负向测试与 spike 验证；产品 BLOCKING 未消除不得实施。
- 回退：回退本 task 的完整实现 release；涉及数据先停写者并从已验证成套备份恢复，禁止仅降级数据库或以旧兼容分支兜底。

### 依赖与约束

- 硬依赖和冲突以 progress.md 的 task.py 调度字段为准；不把文件重叠当硬依赖。plan 仅输出图上候选，不能替代 preflight；产品 BLOCKING 必须先确认，SPIKE 先验证并回填。

### Finalization 时更新的 blueprint

- docs/blueprint/architecture.md、docs/blueprint/stream_runtime.md：明确删除的是 ICE 代次适配器，纠正 stream_runtime.md 现行私有接口陈述。
- docs/blueprint/decisions.md、docs/blueprint/testing.md：扩展制品身份、升级与行为门禁。
