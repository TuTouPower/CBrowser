# Task spec

## 背景

代理凭据由 runner 编码进 --proxy-server，属于浏览器进程命令行可见数据。凭据必须移至 Browser 不可读的认证转发边界；p082 的 Web 托管子项已有固定 wheel 与 SHA256 实现，不重复建设。

## 契约区

### 范围

- 用无凭据本地入口与隔离认证转发路径替代 Chromium userinfo；凭据文件只挂到认证组件，不进 Browser 文件系统、argv、环境或诊断。
- 转发不可用、认证拒绝、DNS/连接异常时代理模式失败封闭；记录不含秘密的可观测原因。复用已存在 vendor_selkies_web 的完整性门禁。

### 非范围

- 不执行 p078 的强制全 Profile 代理、独立出口分配或未配置代理模式改造；不承诺不同 Profile 自动拥有不同公网 IP。
- 不更换已存在的 Selkies wheel vendor、本地托管或 SHA256 清单机制。

### 验收标准

<!-- 规范（门禁必留，不得删除） -->

只写可观察、可独立验证的行为；每条使用稳定且不复用的 `AC-NNN`。需真实部署或人工环境验证时在编号前加 `[deploy]`。创建时均为未勾选（`- [ ]`）；实施验证通过后由实施 Agent 就地打勾（`- [x]`）；由 Review Agent 独立复核打勾真实性。技术选型不作为行为 AC。review 判 FAIL 且需修改交付内容时，实施 Agent 撤回全部打勾，修复并重验后重新打勾；reviewer 用 `TICK-VALID` / `TICK-VOID` 逐条判定。

<!-- /规范 -->

- [ ] AC-001：真实 Browser 容器 argv、/proc、ps、环境、日志和异常不含代理账号密码，Browser 文件系统与其可读挂载不能读取认证组件密钥文件。
- [ ] AC-002：有账号密码的 HTTP/SOCKS 代理在实际引擎内能认证访问目标；URL 编码、IPv6 与特殊字符凭据处理正确且不进入诊断输出。
- [ ] AC-003：认证转发组件停止、认证失败或上游不可达时，代理模式无法回退宿主直连，返回可诊断的脱敏失败；未配置代理模式仍按现行契约运行。
- [ ] AC-004：同一测试目标与代理下，认证成功率不低于现状，首包时延差异有可复验报告并满足实施前确认的预算。
- [ ] AC-005：已托管 Selkies Web 资源仍通过固定制品和 SHA256 校验；被篡改资源在构建/发布验证阶段被拒绝，不新增外部 CDN。

### 可测试性声明

<!-- 规范（门禁必留，不得删除） -->

逐条说明不可自动测试的 AC 及替代验证；全部可测则写“全部 AC 可自动测试”。

<!-- /规范 -->

全部 AC 可自动测试；涉及真实 Chrome、引擎、Docker 或网络行为的 AC 使用隔离真实环境探针，不以 mock 结果替代。界面视觉补人工核验，第三方公网检查仅显式 opt-in。

## 上下文区

- 来源：`p082`。2026-11-13 核实 runtime_agent/runner.py build_proxy_server_arg 组装含 userinfo 的 --proxy-server。scripts/vendor_selkies_web.py 已钉死 2.2.1 wheel SHA256、校验逐文件清单并注入本地适配器，tests/unit/test_vendor_selkies_security.py 已有完整性测试。未实测的 renderer RCE 能力不作为已确认事实。

### 有意不测

- 不执行 p078 的强制全 Profile 代理、独立出口分配或未配置代理模式改造；不承诺不同 Profile 自动拥有不同公网 IP。：超出本 task 范围；其余已声明 AC 不豁免。

### 测试策略

- 在 .scratch 先调用真实参数构造器复现凭据入 argv，再验证新路径的 Browser 容器负向可读性；任何探针秘密用运行期随机值，不入库。
- 真 Docker+引擎覆盖代理协议/认证、组件崩溃与公网不可达，复用 vendor 安全测试；延迟基线按相同拓扑重复测量。
- 项目门禁：按 docs/blueprint/testing.md 的 doctor_cmd / test_cmd / blackbox_verify 执行；本批创建仅验证文档结构，不代表实现验收。

### 未知契约清单

<!-- 规范（门禁必留，不得删除） -->

未核实的外部契约标为 `UNVERIFIED-BLOCKING` 或 `UNVERIFIED-SPIKE`；核实后改写为结论和验证方式。无则写“无”。

<!-- /规范 -->

- 锁定引擎与现有代理方案的 HTTP/SOCKS 认证行为、首包基线：UNVERIFIED-SPIKE，真实代理探针比较旧链与隔离转发链。
- 认证首包时延可接受预算：UNVERIFIED-BLOCKING，先取得同机重复测量报告，再由用户确认允许的退化上限，不能擅自把不退化改成任意阈值。

### 风险与回退

- 风险：转发新增网络与进程边界，可能改变代理握手或泄漏凭据；需故障封闭和真实负向证据。
- 回退：停止受影响 Profile 后回退 release；恢复旧 release 前明确告知其命令行凭据风险，不在新实现保留自动 fallback。

### 依赖与约束

- 保持本机 Docker/OrbStack 与唯一外部 Chrome 客户端边界；不复活 parked 条目。依赖建议见 progress.md；产品 BLOCKING 未确认前不可 start，SPIKE 先验证后回填。

### Finalization 时更新的 blueprint

- docs/blueprint/security.md：代理凭据可读性与认证组件权限。
- docs/blueprint/supervisor.md、docs/blueprint/architecture.md：认证转发拓扑及失败封闭。
- docs/blueprint/testing.md：真实代理凭据负向测试和延迟基线。
