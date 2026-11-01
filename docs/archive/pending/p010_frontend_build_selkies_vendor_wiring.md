# p010 生产镜像构建未固定 Selkies 资源 vendor 步骤

- 来源：t007 评审范围外观察，归 t012
- 内容：`dist/selkies` 需先运行 `scripts/vendor_selkies_web.py`（固定 wheel SHA 并校验清单）再 `npm run build`；当前 `npm run build` 不含该步，生产 Dockerfile 若只 COPY `src/frontend/dist/` 无机械保障。t012 编排生产构建时须把 vendor→build 固化进镜像构建并校验 `dist/selkies/selkies_adapter.js` 与清单。另：vendor 脚本的清单位于 `tests/fixtures/gateway_probe/selkies_web_sha256.txt`，生产构建依赖测试目录，宜迁到 `config/` 或 `scripts/`。
- 处理：main；resolution=resolved；reason=p010: npm run build 的 prebuild 自动 vendor、postbuild 自动 verify；清单位移到 config/selkies；新增 scripts/verify_frontend_dist.py 与 Dockerfile dist 校验；测试 tests/e2e/test_frontend_build_wiring.py
