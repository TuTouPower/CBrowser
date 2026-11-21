---
pid: "p153"
slug: "geoip_cache_missing_in_api_probe"
status: "closed"
resolution: "resolved"
reason: "已由 t096 完成：API 容器显式注入 GeoIP 依赖与路径配置，前端细化错误语义，根治 geoip_db_missing 全失败，已合入 main"
fix_ref: "t096"
---
# p153 测速全失败主因：探测迁入 API 进程后漏配 GeoIP 路径

- 来源：t095 实施期独立子代理研究「mihomo proxy 是否故障」的结论（2026-11-20）。用户生产反馈「测速全部失败」，排查发现并非代理问题。
- 生产证据（release decd8bd，作业 049e0ef6）：终态 `failed=88, completed=0`；成员错误码 `geoip_db_missing` 84 个、`echo_unreachable` 4 个。前端无 `geoip_db_missing` 文案，回退显示通用「测速失败」。

## 现象与影响

批量测速 88 个代理全部失败，用户看到清一色「测速失败/经代理无响应」，但代理本身可用、网络可达。根因在代码/配置层，导致几乎全部探测在已拿到出口 IP 后仍判失败——测速功能实质不可用。

## 根因（机制层）

- t094 把探测从 Supervisor helper 容器迁入 API 进程。生产 runner 无参构造，GeoIP 查询依赖全局环境变量 `CBROWSER_GEOIP_DB` / `CBROWSER_GEOIP_CACHE` 定位 mmdb。
- 这两个变量只在 compose 的 supervisor 服务配置，api 服务未配 → API 进程 `db_path=None` → 回显阶段成功、GeoIP 阶段抛 `geoip_db_missing`。
- mmdb 文件实际已在 API 容器的 `/data/engine-cache/geoip/`，只是进程找不到路径。属架构重构后隐式环境依赖未迁移，非运维、非代理、非节点过期。
- 已排除：mihomo 服务未启动（Up healthy）、端口不通（\*:21000-21093 LISTEN）、节点过期（Expire 2026-12-07）、容器内无法访问宿主 loopback（host.docker.internal 映射生效）、探测显式代理/白名单机制错误。

## 建议动作

- 核心：给 API 服务补 `CBROWSER_GEOIP_CACHE`（与 supervisor 一致）；更彻底是 runner 显式注入 `GeoIpLookup`，去掉隐式全局 env 依赖，防同类重构再漏配。
- 前端：补 `geoip_db_missing`/`geoip2_missing` 本地化文案，避免通用失败掩盖根因。
- 剩余 4 个 `echo_unreachable` 为真实节点网络状况，按需检查或更新订阅，不影响主体恢复。

## 与 t095 关系

t095 处理进度实时性与并发，不覆盖本条。本条独立，可单独立 task 修复。

## 处理

- 未开
- 处理：t096；resolution=resolved；reason=已由 t096 完成：API 容器显式注入 GeoIP 依赖与路径配置，前端细化错误语义，根治 geoip_db_missing 全失败，已合入 main
