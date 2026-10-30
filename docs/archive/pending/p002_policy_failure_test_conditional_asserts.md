# p002 去除 policy failure E2E 中被 if 包裹的断言

- 来源：t005 遗留（t005_test_f001，minor）
- 内容：`tests/e2e/test_supervisor_policy_failure_e2e.py` 约 176/184 行以 `if gates_root.is_dir()` / `if runtime_dir.is_dir()` 包裹 ready/runner_info 残留断言，目录未创建时断言被跳过。同用例另有异常类型、failure_count 与零容器/网络泄漏的无条件断言保护。改为无条件断言（目录不存在即视为无残留）并复跑该 E2E。
- 处理：t005；resolution=resolved；reason=t005 Round2 前改为无条件断言，真实 policy failure E2E 复跑 1 passed（.scratch/t005_final/round1/policy_failure_p002.log）
