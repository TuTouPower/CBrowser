# d001 改造前测试与运行基线

- 来源：t001；2026-10-27T01:20:00+08:00 初次技术验证
- 结论（t001 时点）：当时主分支旧实现后端与模板契约测试通过；这不能证明目标媒体架构可运行。
- 证据：在 3c8bdbc 基线执行 `uv run --with pytest --with pytest-asyncio --with httpx pytest .repo_template/tests -q -m contract`，168 passed、1 skipped、477 deselected；执行 `PYTHONPATH=src uv run --with pytest --with pytest-asyncio --with httpx pytest src/backend/tests -q`，384 passed、1 warning；`curl -sf http://127.0.0.1:56661/api/health` 返回 `{"status":"ok"}`。原始输出保存在主仓 `.scratch/baseline/baseline_contract.log` 与 `baseline_backend.log`，未入库。
- 前端环境证据：Node v26.8.2 下直接 `npm test` 为 28 failed / 21 passed，异常位于 i18n.tsx:503 的 localStorage.getItem；用 `NODE_OPTIONS=--no-experimental-webstorage npm test` 为 49 passed（4 files），未改业务代码或断言。原始日志见主仓 `.scratch/baseline/baseline_frontend.log` 与 `baseline_frontend_no_webstorage.log`。
- 影响：后续改造以旧功能回归基线和新增真实媒体实验分别验收，禁止以现有测试通过替代第18章17项验证。
- 现状：有效
