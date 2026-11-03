# Task spec

## 背景

前端存在登录重定向、SSE 生命周期、并发 mutation 幂等键及页面状态的行为差异；测试接线和组件依赖方向未能稳定约束这些行为。本组交付可预测的会话/请求交互，使用后端已定义的运行时与初始化契约。

## 契约区

### 范围

- 前端 API client、SSE、i18n、Profile/Artifact mutations、登录/会话/设置/文件页面。
- 生产组件与测试宿主边界、样式 token、测试类型门禁与各页面真实接线回归。

### 非范围

- 不整改、转报或同步 repo_template，不修改其脚本、hook、契约测试、模板规则或账本示例；不创建已拒绝 A36/R10 的后续任务。
- 不建设已拒绝 A37/R11 的正式备份、恢复、迁移演练、生产切换闭环；不执行生产停服、数据删除或外部发布。
- 不重开 t009/t010/t012，不恢复 legacy，不扩大单机/同机 Chrome 的部署包络，不恢复 TURN。
- 现有 t019 的 ICE 建链延迟、t020 的字体配置各自保持范围；本 task 不重复实现或把其验收顺带标为完成。

### 验收标准

<!-- 规范（门禁必留，不得删除） -->

只写可观察、可独立验证的行为；每条使用稳定且不复用的 `AC-NNN`。需真实部署或人工环境验证时在编号前加 `[deploy]`。创建时均为未勾选（`- [ ]`）；实施验证通过后由实施 Agent 就地打勾（`- [x]`）；由 Review Agent 独立复核打勾真实性。技术选型不作为行为 AC。

<!-- /规范 -->

- [ ] AC-001（A17）：登录 next 的大小写、尾斜杠、query/hash 变体不会形成登录回环；会话页区分加载、错误、未知 Profile 与已停止并能重试，语言函数身份变化不重置已连接会话。
- [ ] AC-002（A18）：SSE 立即 stop/start、重复 start、旧读取异常及登出后均只有当前代次可投递或重连；外部取消与内部超时可区分，取消不重试且所有请求结束后移除取消监听。
- [ ] AC-003（A19）：同一 mutation 实例并发执行不同逻辑动作时使用不同幂等键，单动作网络重试沿用同一键；一个动作完成不清除另一个动作的键，stop/start 复合动作仍符合后端冲突语义。
- [ ] AC-004（A20）：设置页只将已观测到的控制 API 状态称为健康，不宣称未检查的媒体或全服务健康；部分文件上传失败时界面同时显示成功数、失败文件和未处理数，不输出文件内容。
- [ ] AC-005（A21）：不一致双语键或无效翻译键在编译期失败；SSE 消费采用生成事件类型并验证真实事件语义，合法事件可更新状态，未知/畸形事件不会被强转为合法运行状态。
- [ ] AC-006（A22）：页面主要运行、启动、保存、删除、复制、重置及 apply 流程通过真实组件/客户端接线测试；客户端 credentials、真实 retry、具体 target Origin 均有行为断言；测试实例互不污染，测试源码签名错误使类型门禁失败。
- [ ] AC-007（A49）：生产包不含测试宿主 globals 或零消费者入口；浏览器挂载组件及 props 由所属 feature 提供，shared 不反向导入 feature；已有剪贴板权限观察与页面样式保持行为，品牌色变更只修改一处权威即可一致生效。

### 可测试性声明

<!-- 规范（门禁必留，不得删除） -->

逐条说明不可自动测试的 AC 及替代验证；全部可测则写“全部 AC 可自动测试”。

<!-- /规范 -->

全部 AC 可自动测试；真实 Docker/Chrome、数据库与 HTTP 调用使用隔离数据根及受控故障注入，缺前提明确未验证，不将静态检查或 skip 作为真实运行证据。

## 上下文区

- 来源：用户 2026-11-03 明确要求为全部采纳项合并立项；[review_20261103_185924 决策](../../reviews/review_20261103_185924/adoption_decision.md)；本组 A17、A18、A19、A20、A21、A22、A49。原 D1=B、原 D2=A 已按用户选择写回；本轮仅创建 backlog，不授权实施或提交。

### 采纳项承接与设计边界

|采纳项|主验收|来源 finding|
|---|---|---|
|A17|AC-001|f_frontend_features_02, f_frontend_features_03, f_frontend_features_09|
|A18|AC-002|f_frontend_shell_01, f_frontend_shell_02|
|A19|AC-003|f_frontend_features_01, f_global_architecture_08, f_global_system_properties_06|
|A20|AC-004|f_frontend_features_10, f_frontend_features_12|
|A21|AC-005|f_frontend_shell_06, f_frontend_shell_11|
|A22|AC-006|f_frontend_features_05, f_frontend_features_11, f_frontend_shell_05, f_frontend_shell_07, f_frontend_shell_08|
|A49|AC-007|f_frontend_features_06, f_frontend_features_07, f_frontend_features_08, f_frontend_shell_03, f_frontend_shell_04, f_frontend_shell_09, f_frontend_shell_10|

以下为已采纳修复边界；具体结构选择以满足当前需求的最简单长期实现为准，不以开发时间或改动规模降级。

- **A17 · 消除登录 next 回环并准确呈现会话错误**：redirect.ts 仅比较规范化 pathname，排除 /LOGIN、/login/、query/hash 变体；BrowserSessionPage 区分 loading/error/unknown/stopped 并提供重试；useBrowserSession 不因 t 函数身份变化重置已连接状态。补对应行为回归。
- **A18 · SSE 连接代次隔离，区分取消与超时**：sse.ts 每次 start/stop 推进 generation，旧 await/catch/finally 不得投递事件或重连；重复 start 不增加连接。client.ts 区分外部取消与内部超时并释放监听，取消不可重试。用可控 fetch/stream 验证立即 stop/start、登出后零重连和取消行为。
- **A19 · 每次逻辑 mutation 独立分配幂等键**：profiles/artifacts mutations 在每次 mutate/mutateAsync 调用边界建立动作 key，重试继续使用该 key，settle 不得清除另一动作 key；不要把新 key 直接放进每次 retry 调用的 mutationFn。补同实例并发异参、单动作重试及 stop/start 复合动作测试；后端冲突语义保持。
- **A20 · 前端文案只声明已有健康证据并显示上传部分成功**：SettingsPage/i18n 将状态名称收窄为控制 API；ProfileFilesPage 失败文案带成功数、失败文件和未处理数。补健康文案与部分成功页面测试，不输出私密文件内容。
- **A21 · 生成类型覆盖 SSE，编译约束双语键集**：i18n 从 en 精确键集派生 TranslationKey，zh 用 satisfies Record\<TranslationKey,string>；types.ts 导出生成 ProfileRuntimeStatusEvent，sse.ts 在验证真实事件语义后引用该类型，不用 Partial 掩盖不一致。运行 tsc 与 SSE/i18n 测试。
- **A22 · 前端测试验证真实接线并恢复 mock 隔离**：页面在 ApiClient 边界注入每例独立 stub，补 running/启动/保存/删除/复制/重置/apply 关键流程；spyOn 或注入替代单例普通赋值。断言 credentials=include、真实 retry、具体 target origin；增加测试 tsconfig noEmit 类型门禁，清除因此暴露的签名错误，不重写旧预期迎合实现。
- **A49 · 前端层次、组件契约与样式源一致**：移除 readClipboardPermission 及其独立旧测试，保留实际 watcher 的权限行为测试；删未实现 onSessionError prop，若后续确有消费者再按需求定义。host_entry 移入测试 fixture，更新构建入口与 import，验证生产 bundle 不含测试 globals。BrowserSessionMount 移至 browser-session feature，并从真实组件导入 props；删除零消费者 CSS 组件块，不为保留其定义反向迁移全部页面。primary 为品牌色权威，删除无消费者 accent 或从同一 token 派生语义色，避免重复字面量；标签回调使用 tag，不遮蔽翻译函数。

### 有意不测

- repo_template 整改、正式备份恢复/切换与已拒绝项：用户明确排除，不新建相关测试。
- 公网/跨主机媒体与原生 x86 环境：不扩大现行单机包络，沿用已记录用户豁免，不宣称实测。

### 测试策略

- 在受控 fetch/stream 和 fake timers 下验证 stop/start、登出、取消、超时与重试；使用并发异参 mutation 证明逻辑动作隔离。
- 用独立 ApiClient stub 驱动真实页面关键流程，精确断言 credential/Origin/部分成功文案；新增测试 tsconfig 门禁并运行 tsc/Vitest。
- 构建实际生产 bundle 证明测试宿主 globals 不进入产物；覆盖 i18n 键集编译错误与真实 SSE 合法/非法事件，不重写旧期望掩盖行为改变。

### 未知契约清单

<!-- 规范（门禁必留，不得删除） -->

未核实的外部契约标为 `UNVERIFIED-BLOCKING` 或 `UNVERIFIED-SPIKE`；核实后改写为结论和验证方式。无则写“无”。

<!-- /规范 -->

无未核实外部契约；沿用现有 React、TanStack Query、ApiClient 与 Selkies adapter 的已声明接口。后端 SSE/初始化形状以依赖 task 导出契约为准，不先行手写镜像类型。

### 风险与回退

- 风险：mutation key 生命周期和请求取消变更可能使已完成操作重复执行；组件/宿主迁移可能漏入口，过度 mock 可能掩盖页面接线。
- 回退：通过完整行为回归后按同一前端构建版本交付；失败撤回本组未发布构建，不改后端幂等记录或尝试重复执行已完成动作。组件迁移直接更改消费者，不留临时双入口。

### 依赖与约束

- 依赖运行时 task 完成 A44 snapshot/live 与 A55 初始化状态/重试的生产契约，消费生成类型与已接通入口；不重复实现 A55。
- 与 t020 共改 Profile 创建/编辑界面和 API 类型，执行需串行；t019 不作为本组硬依赖。
- 保持已批准的任意内容 Artifact 政策；不新增恶意代码扫描或任意搜索引擎选择 UI。

### Finalization 时更新的 blueprint

- `docs/blueprint/frontend.md`：请求/连接代次、幂等动作、页面错误与组件/测试宿主边界。
- `docs/blueprint/testing.md`：前端真实接线、测试类型检查与生产 bundle 验证。
