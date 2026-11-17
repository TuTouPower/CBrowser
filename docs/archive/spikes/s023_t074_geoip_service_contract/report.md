# Spike report

## 问题

候选免 Key HTTPS IP 地理服务（`ipwho.is`、`api.ip.sb/geoip`、`freeipapi.com`）在**真实代理出口**下的 JSON 结构稳定性、字段命名、单次网络 RTT、429 限流策略，以及与本地 `GeoLite2-City.mmdb` 的覆盖互补关系，决定 t074 Step 3 的主备优先级与回落设计。

## 成功判据

- 至少 5 个不同国家/地区的真实代理出口，逐服务记录 HTTP 状态、字段、RTT。
- 对可用服务做连续请求，观测是否出现 429 及触发次数。
- 本地 mmdb 能对同一批出口 IP 解析出 country_code / country_name / city，并与在线结果对比。
- 结论明确「主链路 / 补充链路 / 回落条件」三者。

## 尝试

- `code/geoip_probe.py`：gate venv `httpx 0.28.1`，`httpx.Client(proxy=http://127.0.0.1:<port>, trust_env=False, follow_redirects=True)`，5 端口 × 4 服务矩阵 + 12 次连续 IP 回显 burst；原始结果 `code/results.json`。
- 补充实测：curl 跟随 307 抓 `freeipapi` 原始字段；15 次连续请求 freeipapi 观测 429；Browser 容器 `geoip2` 查本地 mmdb。
- 代理为已验证可用的 `mihomo-proxy`（94 端口 / 90 个 200 / 82 个不同出口 IP），OrbStack `network_proxy=none` 反向隔离下容器纯物理直连。

## 证据

- `ipwho.is` / `api.ip.sb/geoip`：5/5 出口全部 `ConnectError: [SSL: UNEXPECTED_EOF_WHILE_READING]`，curl 对照 `LibreSSL SSL_connect: SSL_ERROR_SYSCALL`，不可用。
- `freeipapi.com/api/json`：307 → 跟随重定向后 5/5 200；原始字段 `ipAddress`、`countryCode`、`countryName`、`cityName`、`regionName`、`latitude`、`longitude`、`isProxy` 等；RTT 中位 749.7ms（629.3 / 1766.0ms 最小最大）。
- 429 限流：同出口连续 15 次 freeipapi → `200×9, 429×6`（第 10 次起）。`api.ipify.org` 连续 12 次 → 全部 200，无 429，RTT 中位 473.2ms（423.0 / 793.7ms）。
- 本地 mmdb：Browser 容器 `/data/engine-cache/geoip/GeoLite2-City.mmdb` 对 4 个出口解析为 HK/Hong Kong/Hong Kong、JP/Japan/Tokyo、SG/Singapore/Singapore、US/United States/San Jose；在线服务对同一美国 IP 报 Seattle，城市粒度互补而非一致。
- 真实公网服务表现受出口、时段、限流窗口影响，本轮为单时段样本；真实部署多国表现归 AC-006 `[deploy]` 验证，不冒充已验。

## 结论

在线免 Key 服务不可作为主数据源：两家 TLS 不可用、一家有硬 429 且需跟随 307、RTT 数百毫秒到 1.7 秒。可信设计为：以「经代理的 IP 回显（`api.ipify.org` 等）+ 本地 `GeoLite2-City.mmdb` 完整读取 `country.names` / `city.names`」为主链；在线 HTTPS GeoIP 服务仅作可选城市补充，且必须处理 307 跟随、429 退避、TLS 不可用三类失败并回落主链。`latency_ms` 只计实际代理 HTTP 往返，不含服务不可用时的退避等待。单一国家/地区本就有多个城市、多个落地 IP，城市字段只作观测值，不参与等价判定。可信度：本机真实代理多出口实测 + 本地 mmdb 实测，字段与限流结论可直接采纳；真实公网在线率与地理库主观准确度按项目「有意不测」口径归 `[deploy]`。

## 是否采纳

- 决定：是
- 理由：实测坐实「在线服务不可靠、本地 mmdb 必须为主链」，直接定型 Step 3 的主备与回落策略，避免把三家外部服务写成硬依赖。
- 后续 task：t074
- 无需后续理由：不适用

## 关联 findings

- `docs/findings/d048_t074_geoip_service_reliability_and_ratelimit.md`
