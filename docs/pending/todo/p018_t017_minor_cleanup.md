# p018 t017 收尾 minor 清理

- 来源：t017 遗留（t017_code_f007-f010/f012-f015/f017/f018；t017_test_f007/f008/f012/f014/f015/f016）
- 内容：处理 API 客户端外部取消/超时区分与监听释放、SSE stop/start 竞争、SSE 尾帧解析去重、Http 请求复杂度拆分、跨源 baseUrl 凭据、会话页错误条跨 Profile 残留、logout rejection、文档门禁引用、反斜杠同源绕过、应用并重启 start 超时重放；补齐对应测试与 AppProviders retry 配置测试。
- 处理：未开
