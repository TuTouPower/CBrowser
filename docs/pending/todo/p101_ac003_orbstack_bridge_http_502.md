# p101 OrbStack 普通 bridge 透明代理致 ac003 peer 探针 HTTP 502

- 来源：gate4 真实补验新发现（2026-11-14），与 `docs/findings/d020_orbstack_bridge_reachability.md` 同源
- 内容：`tests/e2e/test_browser_runtime_e2e.py::test_ac003_controlled_uds_and_allowlist` 单跑稳定失败：`docker run` peer 探针内 `urllib.request.urlopen('http://cbrowser-t003-impl-http-server-*:8080/download-1.txt')` 返回 `HTTP Error 502: Bad Gateway`（`--showlocals` 抓到 stderr），而非 200；镜像无 `HTTP_PROXY` env（`docker image inspect` 确认），属 OrbStack 普通 bridge 透明代理拦截同网 HTTP。d020 已记录「普通 bridge 跨 Profile 隔离不能成立、透明代理因果仍未证实、当前动作采用 Runtime 自有 netns filter 且不修改 OrbStack 代理」，t005 AC-001/AC-006 网络隔离部分保持未通过。判定：本机环境卡点，非产品缺陷、非夹具问题；不得改测试预期或 xfail 凑绿。可行方向：按 d020 用 `internal=True` 网络或产品自有 netns filter 重做该网络级断言，或先做代理排除对照实验坐实因果后再决定。
- 处理：未开
