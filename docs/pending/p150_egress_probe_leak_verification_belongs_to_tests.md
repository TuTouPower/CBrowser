---
pid: "p150"
slug: "egress_probe_leak_verification_belongs_to_tests"
status: "closed"
resolution: "transferred"
reason: "已核实 main(HEAD b297639) 上两条问题均仍有效、无等价 active/backlog task；按用户 2026-11-20 授权依开发铁律聚合为一个根因重构 task，并纳入 useBatchActions 环境批量与沙箱依赖测试改写，已转交 t094"
fix_ref: "t094"
---
# p150 出口探针不应承担浏览器防泄露验证职责，该职责应由单元与端到端测试保证

- 来源：用户 2026-11-20 口述。在解释 Supervisor 周期性创建的 egress-probe / network-policy-agent 短命容器职责时提出。
- 内容：
    1. 职责界定：验证"浏览器 Profile 会不会泄露真实 IP / 强制代理隔离是否生效"属于**本地单元测试与端到端测试**的职责，不应由运行时的代理测速探针（egress probe）承担，也不应把探针描述成防泄露保证。egress probe 的定位只是面向用户的**测速与出口信息展示**（出口 IP、国家城市、延迟），不是质量防线。
    2. 根因（违反开发铁律）：早期 t052/p040 把"测出口"与"验隔离"焊成同一职责，才把一个纯展示功能架到容器沙箱上——每次测速新建 helper 容器 + policy-agent sidecar + 专用 bridge 网络 + finally 强删，单次约 5 秒并产生持续容器 churn。这是用重型基础设施兜测试职责，属架构错位。后续 p110（延迟口径）、d049（池化与计时解耦）都是给这个错误底座打局部补丁，违反"架构至上 / 拒绝妥协 / 零兼容负担"。
    3. 解决方案（从根因重构，不做兼容层）：职责剥离后沙箱只剩两点——强制走代理（避免测到真实出口）与凭证不进命令行。两点后端直接做：http client 显式指定 proxy + `trust_env=False` 天然只走代理，凭证本就在后端配置中。据此**删除容器沙箱整条路径**（helper、policy-agent、专用网络、Docker 调用、清理逻辑），改为后端内轻量探测：固定白名单回显域名、每请求新建 client（防多代理串扰）、`monotonic()` 只包 HTTP 往返、读本地 GeoIP。同步改写文档/文案中所有"自检隔离 / 防泄露"表述为"测速与出口展示"。不留双路径、不留兼容开关。
    4. 必须兑现的前提（否则方案不成立）：①协议全覆盖——产品支持 http/https/socks5，轻量探测须全部支持，不得降级只测 http；②SSRF 防护——回显端点固定白名单，拒绝私有/保留地址，避免后端被当成内网探测器；③并发隔离——批量测速多代理不得共用全局代理环境变量，每请求独立 client；④防泄露验证由 E2E 真正补上（本条职责归位的前提），否则删除沙箱会失去"顺带发现规则失效"的副作用，但那是测试缺位，不是保留沙箱的理由。
    5. 待办：核查产品文档（`docs/blueprint/supervisor.md`、`docs/guides/`）、UI 文案、API 契约与代码注释/命名中，是否存在把 egress probe 表述为"自检隔离是否生效 / 防泄露"的描述；若有按第 3 点改写。另按第 4 点核实防泄露（代理强制、IPv6/DNS 不绕过）是否已由单元测试与真实 Docker E2E 覆盖，有缺口则补测试。
    6. 与已有条目关系：p110（测速延迟口径与状态持久化，已转 t074）、d049（轻量探针隔离与计时，其"不池化"结论在删除沙箱后失效）、p143（Windows 出口 TCP 特征一致性，parked）均不覆盖本条职责归位与沙箱删除问题，故单列。
- 处理：t094；resolution=transferred；reason=已核实 main(HEAD b297639) 上两条问题均仍有效、无等价 active/backlog task；按用户 2026-11-20 授权依开发铁律聚合为一个根因重构 task，并纳入 useBatchActions 环境批量与沙箱依赖测试改写，已转交 t094
