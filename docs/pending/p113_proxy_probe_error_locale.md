---
pid: "p113"
slug: "proxy_probe_error_locale"
status: "closed"
resolution: "transferred"
reason: "已核实根因、同类范围与验收契约，按用户授权聚合转交 t079（全站状态错误文案与代理地区呈现统一）；转办不表示实现完成"
fix_ref: "t079"
---
# p113 代理测速失败码在表格、卡片及编辑弹窗缺少本地化说明

- 来源：用户 2026-11-17 反馈；pending-record → bug-to-pending（analysis-only）。用户要求测速报错随界面语言显示可理解说明，禁止直接展示 `echo_unreachable` 等机器码。
- 现象：代理测速结果为 `observation_status="failed"` 且 `observation_error_code="echo_unreachable"` 时，无论界面为中文还是英文，状态直接显示 `echo_unreachable`；错误缺少人类可读解释。
- 影响：代理管理表格、卡片及代理编辑弹窗内的测速/国家状态均受影响；测速结果从后端持久化后，重新进入页面仍显示原始错误码。此缺陷是结果呈现层缺少本地化，不代表测速请求本身必然失败，也不是 HTTP 状态码。
- 根因：产品前端缺陷。三个失败分支均执行 `proxy.observation_error_code ?? t("proxyProbeFailed")`，非空机器码绕过 `t()`；现有中英字典仅有通用 `proxyProbeFailed`，没有探测错误分类文案。后端 `src/backend/cbrowser/shared/egress.py:198-207` 把回显服务 HTTP 请求失败归为 `echo_unreachable`，经探测执行与 observation 持久化链路正常保留机器码；应保留 API 机器码用于诊断，在 UI 映射成本地化原因，不修改成依赖界面语言的存储值。
- 同类扫描：全前端 `observation_error_code` 展示扫描确认三处，纳入同一修复范围：`src/frontend/src/features/proxies/ProxyTable.tsx:146`（表格）；`src/frontend/src/features/proxies/ProxyListPage.tsx:95` 的 `ProxyStatusText`（卡片）；`src/frontend/src/features/proxies/ProxyFormDialog.tsx:461` 的 `countryStatus`（编辑弹窗）。测速失败 Toast 已调用 `t("proxyProbeFailed")`，不是本次原始码泄漏位点。
- 期望：上述三处统一按当前界面语言展示失败原因；已知探测码有稳定中英映射，缺失、未知及新增机器码回退到本地化通用失败说明，禁止把未知码直接作为面向用户的主文案。`echo_unreachable` 文案须准确表示出口 IP 回显服务不可达，不能未经证据断言代理账号密码错误或代理永久失效。切换语言后，已持久化失败结果立即使用对应语言；保留失败语义红与诊断数据。
- 测试缺口：`src/frontend/src/features/proxies/ProxyListPage.test.tsx:574-597` 的测试名明确要求 failed error code in red，并断言 `proxy_auth_failed` 原样呈现，因此测试将缺陷固化为预期。现有测试只验证失败颜色与通用 Toast，缺少中英界面下的错误语义映射、三处展示一致性、未知码回退及切换语言后持久结果重绘。后续应新增触达真实组件的表格/卡片/编辑弹窗测试，覆盖代表性已知码 `echo_unreachable`、缺失码和未知码；断言可理解本地化文案、主状态不含机器码、失败颜色保留。旧测试若语义失效，按项目测试纪律整体删除并说明替代，不直接改预期迎合实现。
- 复现：在 `.scratch/` 导入真实 `ProxyTable` 与 `I18nProvider`，注入失败代理，分别设置 `cbrowser.locale=en/zh`。确认语言探针分别显示 `en: Speed test failed`、`zh: 测速失败`，而实际 `proxy-status-probe-error` 两次均严格等于 `echo_unreachable`；2 个复现测试通过。未访问或修改真实代理、数据库及外部网络。
- 线索：`.scratch/repro_proxy_error_locale.test.tsx`、`.scratch/repro_proxy_error_locale.vitest.config.ts`；执行 `./src/frontend/node_modules/.bin/vitest run --config .scratch/repro_proxy_error_locale.vitest.config.ts --root .`。
- 查重：p007 已闭环的历史通用 i18n 遗留，p104/p110 已转交 t074，p112 已完成真实部署补验；没有覆盖本次三个结果展示位点的未完成等价 pending，故新建，不改写历史条目。
- 处理：t079；resolution=transferred；reason=已核实根因、同类范围与验收契约，按用户授权聚合转交 t079（全站状态错误文案与代理地区呈现统一）；转办不表示实现完成
