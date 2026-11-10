# p067 新建环境高级选项默认值调整（拟人化与便携Cookie默认开启）

- 来源：用户提出
- 内容：用户在新建环境时，高级选项中的拟人化（`humanize`）和便携 Cookie（`portable_cookies`）调整为默认开启；透明代理（`transparent_proxy`）与自动启动（`auto_launch`）保持默认关闭；其余选项（允许第三方 Cookie、设 Google 为默认、剪贴板同步、恢复会话、采集预览）保持默认开启。
- 处理：未开
- 时间：2026-11-10T21:15:00+08:00

## 用户原始诉求与规则裁定

在环境创建与编辑的高级折叠配置中，明确各开关项在新建环境时的默认状态：

1. **拟人化 (`humanize`)**：由默认关闭改为**默认开启 (`true`)**，新建环境默认启动鼠标轨迹平滑与按键随机延迟防检。
2. **便携 Cookie (`portable_cookies`)**：由默认关闭改为**默认开启 (`true`)**，解除 OS 硬件级密钥强绑定，便于数据迁移与沙箱克隆。
3. **透明代理 (`transparent_proxy`)**：**保持默认关闭 (`false`)**，防止无代理或普通 HTTP 代理因缺少透明封装协议导致 ERR_PROXY_CONNECTION_FAILED 强制断网。
4. **自动启动 (`auto_launch`)**：**保持默认关闭 (`false`)**，防止大量环境开机自启打满容器与宿主机资源。
5. **允许第三方 Cookie (`allow_3p_cookies`)**：**保持默认开启 (`true`)**，放行第三方 iframe 与跨站 OAuth 鉴权。
6. **设 Google 为默认 (`set_google_default`)**：**保持默认开启 (`true`)**，首次启动自动化配置 Google 默认搜索。
7. **剪贴板同步 (`clipboard_sync`)**：**保持默认开启 (`true`)**。
8. **恢复会话 (`restore_session`)**：**保持默认开启 (`true`)**。
9. **采集预览 (`capture_preview`)**：**保持默认开启 (`true`)**。

## 涉及修改位点

1. **前端默认值**：

    - `src/frontend/src/shared/api/types.ts`：更新 `DEFAULT_PROFILE_CREATE_VALUES`，将 `humanize`、`portable_cookies` 设为 `true`。

2. **后端领域与 API 模型**：

    - `src/backend/cbrowser/domain/models.py`：更新 `ProfileConfig`、`ProfileCreateRequest`、`ProfileResponse` 的字段默认值。

3. **数据库模型**：

    - `src/backend/cbrowser/adapters/database/models.py`：更新 `ProfileModel` 的 SQLAlchemy 默认值。

4. **Schema 与类型重生成**：

    - 运行 `python3 scripts/export_openapi.py` 刷新 `schemas/openapi/cbrowser_v1.json` 与 `cbrowser_internal.json`。
    - 运行 `npm run generate:api` 刷新前端生成的 API 类型。

5. **测试回归**：

    - 回归前后端单元测试，确保缺省值断言与表单初始化测试通过。
