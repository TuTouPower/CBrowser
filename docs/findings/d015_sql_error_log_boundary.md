# d015 安全 JSON 错误响应不能替代 SQL 异常日志脱敏

- 来源：t002；独立 uvicorn/SQLite HTTP 复现及提交内真实进程回归。
- 结论：仅注册通用 Exception 处理器返回安全 JSON，仍可能由 Starlette 向 Uvicorn 重抛原始 DB 异常并输出 SQL 参数；必须在正常异常分发层处理已知数据库异常，另行验证物理日志。
- 证据：主控隔离副本对重复私密 tag 发起真实创建请求，修复前 HTTP 500 响应未含标记，但 server.log 出现两次标记及 [parameters:]。修复将已知约束错误映射为安全领域错误并注册具体 DB 异常处理器；tests/integration/test_api_subprocess.py 的 test_ac006_db_constraint_integrity_error_no_secret_leak_in_logs 通过真实子进程验证 409、事务回滚、后续恢复及物理日志零标记。项目集成命令已实际通过；独立候选复验另记 task note。
- 影响：后续 t006/t008 新增持久化与鉴权路径须复用具体异常边界，保留 logging 并检查物理 stdout/stderr；不能禁用日志器、直写 stderr 或只断言响应体。raise ... from None 抑制异常链展示，并不删除异常对象的 __context__。本结论限已覆盖的 DB 异常路径，不声称任意未知 Python 异常均不会泄漏。
- 现状：有效

补充：SQLite锁错误分类必须使用驱动sqlite_errorcode/对应元数据，不能搜索SQLAlchemy异常全文中的busy/locked；该全文包含用户SQL参数。真实重复tag含这些词曾被误判503，t002新增4例真实HTTP先红后绿修复；IntegrityError应返回409且retryable=false。
