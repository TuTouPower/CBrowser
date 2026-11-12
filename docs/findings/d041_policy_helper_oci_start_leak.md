# d041 策略helper在OCI启动异常后可残留created容器

- 来源：t057完整门禁B，非预览改动引入；用户于2026-11-12明确授权纳入修复。
- 结论：DockerAdapter.\_install_network_policy和_run_policy_helper将Docker SDK containers.run的返回值赋给helper。run已创建容器但start抛APIError时，赋值未完成，finally看到helper=None，不能清理created容器。B失败直接发生于安装路径；独立探针另行复现运行期路径同类缺陷。
- 证据：.scratch/t057/gate_B/junit/e2e.xml；.scratch/t057/oci_helper_red_result.json与oci_helper_red.log。独立真实Docker复现调用生产方法，启动错误为APIError，清理前残留created helper计数1；测试及复现的finally均已精确清理自身资源。
- 修复：两条策略路径均拆分create与start，在启动前持有句柄，原finally即可清理启动失败对象；原权限、网络命名空间、标签、等待预算和故障镜像保持。相应旧测试夹具仅适配SDK调用，不改变行为断言；其它类型helper不在本次修复范围。
- 验证范围：按用户明确要求，修复后只重跑原失败真实E2E，不重复全量门禁；完整B失败记录保留，定向验证单列。运行期独立Docker复现修复后残留计数0，见.scratch/t057/oci_helper_green.log。
- 现状：已修复。原失败真实E2E原样定向复验1 passed/0 failed/0 skipped（6.41秒），证据.scratch/t057/policy_fix_e2e.xml与policy_fix_e2e.log；同时验证失败封闭、无ready/runner标记、API失败状态收敛、端口释放及容器/网络零残留。
