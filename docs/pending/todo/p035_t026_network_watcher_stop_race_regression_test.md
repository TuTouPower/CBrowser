# p035 t026 网络事件 watcher 停机竞态缺回归测试

- 来源：t026 遗留（t026_test_f009，Round 2 code f012 的测试面）
- 内容：runner `watch_docker_network_events` 的停机竞态修复（流登记后复查 stop_event、已置位则立即自关流）已落地并经两轮 code review 静态核对，但无回归测试——该 watcher 是 `serve_supervisor` 内的嵌套闭包，确定性复现「订阅与停机交错」需要先把 watcher 抽为模块级可测单元或给 serve_supervisor 加注入口。补测时二选一：(a) 抽 watcher 为模块级函数后测「stop 先于登记 ⇒ 流被关闭且泵不启动」；(b) 用假 Docker client + 可控 stop_event 驱动 serve_supervisor 的 watcher 线程并断言流关闭。生产行为本身无缺陷，本条只追测试债。
- 处理：未开
