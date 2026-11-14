# p101 OrbStack 普通 bridge 透明代理致 ac003 peer 探针 HTTP 502

- 来源：gate4 真实补验新发现（2026-11-14），与 `docs/findings/d020_orbstack_bridge_reachability.md` 同源
- 内容：`tests/e2e/test_browser_runtime_e2e.py::test_ac003_controlled_uds_and_allowlist` 单跑稳定失败：`docker run` peer 探针内 `urllib.request.urlopen('http://cbrowser-t003-impl-http-server-*:8080/download-1.txt')` 返回 `HTTP Error 502: Bad Gateway`（`--showlocals` 抓到 stderr），而非 200；镜像无 `HTTP_PROXY` env（`docker image inspect` 确认），属 OrbStack 普通 bridge 透明代理拦截同网 HTTP。d020 已记录「普通 bridge 跨 Profile 隔离不能成立、透明代理因果仍未证实、当前动作采用 Runtime 自有 netns filter 且不修改 OrbStack 代理」，t005 AC-001/AC-006 网络隔离部分保持未通过。判定：本机环境卡点，非产品缺陷、非夹具问题；不得改测试预期或 xfail 凑绿。可行方向：按 d020 用 `internal=True` 网络或产品自有 netns filter 重做该网络级断言，或先做代理排除对照实验坐实因果后再决定。
- 处理：683aa10；resolution=resolved；reason=坐实 OrbStack 注入代理致 502，peer 探针用 ProxyHandler({}) 强制同网直连；ac003 E2E 1 passed、gate5 全绿，未改断言/产品/全局配置

## 终局补验证据（gate5，已修复）

- 坐实因果（非 d020 假设的网络层透明拦截）：OrbStack 向容器注入 `http_proxy`/`HTTP_PROXY=http://host.docker.internal:7890`（宿主 mihomo 代理），`no_proxy=localhost,127.0.0.1` **不含容器 DNS 名**；`urllib.request.urlopen` 默认取 `getproxies()` 把同网请求送进宿主代理，代理无法解析内网 DNS 名 → `HTTP Error 502: Bad Gateway`。轻量探针实证：`ProxyHandler({})` 绕过代理后报错变为 `Name or service not known`（非 502），502 响应头 `Server`/`Via` 均为 None；夹具 `/download-1.txt` 确为 `send_response(200)`，排除产品与目标 server 缺陷。
- 修法（提交 `683aa10`）：只改 `tests/e2e/test_browser_runtime_e2e.py:1195-1196` 的 peer 探针脚本，用 `urllib.request.build_opener(urllib.request.ProxyHandler({}))` 强制同网直连；**未改断言、未改产品代码、未改 OrbStack 全局配置、未 xfail/skip**。
- `test_ac003_controlled_uds_and_allowlist` 单跑 `1 passed in 14.32s`；gate5 全量 e2e 105 用例 0 failed / 2 skipped、`GATE_EXIT=0`。d020 的「透明代理因果仍未证实」结论不受影响（此处是 env 注入代理，非网络层拦截）。
