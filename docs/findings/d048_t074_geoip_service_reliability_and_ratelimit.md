# d048 免 Key HTTPS GeoIP 服务经真实代理出口不可用率高且有硬限流，主链必须回落「IP 回显 + 本地 mmdb」

- 来源：s023 经真实代理出口的 GeoIP 服务实测（2026-11-16，mihomo-proxy 88 节点端口中取 5 个不同出口：21000/21001/21003/21013/21062）
- 结论：
    1. `https://ipwho.is/` 与 `https://api.ip.sb/geoip` 经全部 5 个真实代理出口均 TLS 握手失败（`httpx.ConnectError: [SSL: UNEXPECTED_EOF_WHILE_READING]`），5/5 不可用；curl 对照同样报 `LibreSSL SSL_connect: SSL_ERROR_SYSCALL`。这两家不能作为主备链路。
    2. `https://freeipapi.com/api/json` 返回 307，须 `follow_redirects=True` 才 200；5/5 成功，字段为 `ipAddress` / `countryCode` / `countryName` / `cityName` / `regionName` / `latitude` / `longitude` / `isProxy`，RTT 中位 749.7ms（629.3–1766.0ms）。
    3. 限流硬阈值实测：同一出口连续 15 次请求 freeipapi，前 9 次 200、第 10 次起连续 429；IP 回显基线 `https://api.ipify.org` 连续 12 次全部 200、无 429，RTT 中位 473.2ms（423.0–793.7ms）。
    4. 本地兜底可用：Browser 容器 `/data/engine-cache/geoip/GeoLite2-City.mmdb`（`geoip2`）对 212.107.28.52 / 212.107.30.203 / 103.142.140.53 / 104.249.174.133 分别解析出 HK/Hong Kong/Hong Kong、JP/Japan/Tokyo、SG/Singapore/Singapore、US/United States/San Jose；在线服务对同一美国 IP 给 Seattle，城市粒度与本地库互补而非一致。
- 证据：`docs/spikes/s023_t074_geoip_service_contract/report.md`、`code/geoip_probe.py`、`code/results.json`。
- 影响：t074 Step 3 的 `shared/egress.py` 必须以「经代理的 IP 回显 + 本地 GeoLite2-City.mmdb 完整读取 country/city」为主链；在线 HTTPS GeoIP 服务仅作可选城市补充，且必须处理 307 跟随、429 退避、TLS 不可用三类失败并回落主链，绝不把出口 IP 作为唯一依赖。单一国家/地区存在多个城市、多个落地 IP，城市字段只作观测值不参与等价判定。
- 现状：有效
