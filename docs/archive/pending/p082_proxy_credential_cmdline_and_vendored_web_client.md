# p082 代理凭据移出命令行与服务端代管 Selkies Web 客户端

- 来源：2026-11-13 同类项目技术调研（`.scratch/reports/隐私浏览器同类项目技术调研.md` P1-9、本仓风险节），依据 Docker 代理凭据警告与 SealSkin `webclient.py`
- 内容：本地源码实读（需实测复核）：`runner.py:95`（`runner.py:62-95`）把代理账号密码 percent-encode 后内联进 `--proxy-server={scheme}://{user}:{pass}@{host}:{port}`，该串出现在 Browser 容器 `/proc/<pid>/cmdline` 与 `ps`，且 `--no-sandbox`（`runner.py:639`）下 renderer RCE 可读同容器进程信息，无第二道进程隔离。控制面密钥已全部走 `/run/secrets/*:ro`（`compose.yaml:36-38,47-49,85-87,137-139`），浏览器侧凭据却落在进程命令行。`runner.py:66-68` 注释承诺不进日志/异常，但注释不等于机制。另一子项：官方 Selkies Web 客户端现由同源 iframe 加载固定版本，建议按 image digest 一次性取出并由服务端自己 serve、做 SHA256 清单与无引用清除，server 更新即全端 UI 更新。本次为只读调研，未授权改生产代码。
- 处理：t065；resolution=transferred；reason=已核实当前代码与有效 task，按同一交付面聚合转交 t065；过时描述与剩余范围见 task spec，归档仅表示转办
- 时间：2026-11-13T19:16:54+08:00
- 关联：p006（archive，agent_secret 挂载，不同凭据）、p060（archive，链接录入 secret-safe）、p010（archive，frontend build Selkies vendor wiring）、p078（代理强制化）

## 目标

1. 凭据改为容器内 loopback 无认证转发器 + sidecar 注入认证（已共 netns）或代理侧 IP allowlist，凭据只以 `/run/secrets/*:ro` 文件存在，不进命令行、环境变量或日志；补 Browser 容器内不可读凭据的真链 E2E。
2. 服务端按 digest 托管官方 Web 客户端并做完整性清单，去除对外部 CDN/版本漂移的依赖。

## 必须权衡的收益损失

把凭据从 `--proxy-server` 移走会失去「首发即带 `Proxy-Authorization`、避免 CDP 407 往返」的效果，需实测确认转发器方案不引入可见的认证往返或指纹差异，不得静默改变启动行为。

## 验收

1. Browser 容器 `/proc/<pid>/cmdline`、`ps`、日志、异常栈中均无代理凭据。
2. 代理认证成功率与首包延迟不低于现状；转发器不可用时 fail-closed 而非回退直连。
3. Web 客户端资源全部来自服务端托管，digest 不匹配即拒绝加载。
