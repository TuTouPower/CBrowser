# 代理库界面

需求级 spec，累积 t038。权威交互与视觉约束见 `DESIGN.md` 与 `docs/blueprint/frontend.md` 第 8 节；后端代理 API 契约见 `docs/specs/profile_management.md`（t035 分组库 / 代理库 / 配置版本三分）。本文定义界面行为契约。

## 1. 列表（t038）

- `/proxies` 代理库页面列：名称、协议、地址（`host:port`，mono）、认证（有 / 无）、地区（国家码 + 标签）、使用环境数、操作（编辑 / 删除）。认证状态必须有文字或图标，不能只靠颜色。
- 工具栏：搜索（名称、host、地区标签，大小写不敏感）、协议筛选（http / https / socks5 / 全部）、主按钮「添加代理」。搜索与协议筛选可组合；结果随输入即时更新；全量客户端过滤、无分页。
- 空列表显示空状态。每视图最多一个主按钮。

## 2. 添加 / 编辑（t038）

- 字段：名称、协议、host、端口、用户名、密码、国家码、地区标签、备注。
- 校验与后端 `ProxyCreateRequest` 一致：name 1..255、host 1..512、port 1..65535 整数、country_code 空或恰好 2 字母（提交归一为大写）、scheme ∈ {http, https, socks5}。错误在对应字段旁显示，底部有汇总；校验不过不提交。
- 保存成功后代理列表即时更新；改连接字段会使 Profile 列表失效（后端生成新配置版本）。
- 「从 URL 粘贴」解析 `scheme://[user[:pass]@]host[:port]`：scheme 白名单、IPv6 方括号 host、百分号编码账密解码、port 范围。解析成功只覆盖解析出的字段；非法 URL 显示错误且**已填字段保持不变**。

## 3. 密码只写（t038）

- `ProxyResponse` 不含 password；编辑态只凭 `has_password` 布尔显示「已设置，留空不修改」，并提供「清除密码」。
- 提交 `ProxyUpdateRequest.password` 三态：留空省略该键（密码不变）、`null` 清除、字符串设置。
- 已保存的密码绝不出现在前端表单 state、react-query 查询缓存、DOM 与 URL；弹窗关闭清空本地 state。
- 密码只进一次请求体，不进日志、不回显。

## 4. 删除与被引用保护（t038）

- `used_by_count > 0` 时代理删除按钮禁用并提示先改绑。
- 后端删除返回 409 时响应体为 `{"detail":{"code":"proxy_in_use","used_by_count":N}}`（非 `ErrorResponse`）；前端从 `ApiError.detail` / `.data` 读取引用数并展示，不依赖 `errorCode`。
- 使用环境数为链接，跳 `/?proxy=<id>`；环境列表的 `useEnvironmentFilters` 已支持 `proxy` URL 参数按代理筛选。

## 5. 带认证 SOCKS5（t038 / AC-007）

- 依据 `docs/findings/d031_authenticated_socks5_supported.md`、spike s013 报告与 ADR 023（`docs/blueprint/decisions.md:280`）：CloakBrowser 0.6.4 / Chromium 146 **支持**带认证 SOCKS5；`src/backend` **不存在任何 socks5 拒绝分支**，API 永远不会返回该 422（`proxies_router.py` 的 409 仅 `proxy_in_use` / `proxy_name_in_use`）。
- 带认证 SOCKS5 为**直接支持**：表单默认允许 `socks5` + 用户名/密码提交，前端无阻止、**无降级路径、无「引擎不支持」提示**。任何 422 或其它后端错误统一走 `describeError()` 的结构化错误展示（`ApiError.detail` / `.data`）。
- task.md AC-007 字面「引擎不支持时阻止提交并说明原因」沿用 `docs/plan_20261105_ui_redesign.md` 的旧假设（已被 d031 实测推翻），该条件句的前提不成立，故不实现推测性降级代码。引擎 / 指纹平台升级后按 d031 复查条件重跑；若结论翻转，由后续 task 流程修订契约，不在当前代码预留兼容路径。

## 6. 文案与测试（t038）

- en / zh 文案键同步补入 `i18n.tsx`，键集相等与双语文案非空由 `i18n.test.tsx` 兜底。
- Vitest 在 ApiClient 边界注入每例独立 stub、走真实 hooks；URL 解析用表驱动纯函数测试；页面测试覆盖列、搜索 + 协议组合、密码三态与不残留、409 引用数、使用环境数跳转。
- 真实栈 E2E（无头 Chrome）覆盖「UI 新建代理 → 环境引用该代理 → 启动 → 浏览器出站经该代理」，用本地记录代理不依赖公网。
