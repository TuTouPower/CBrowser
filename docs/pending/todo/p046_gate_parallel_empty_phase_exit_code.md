# p046 门禁两阶段空并行集合退出码不对称

- 来源：t044 code review `t044_code_f001`（minor）
- 内容：`scripts/run_gates.sh` 的 `run_gate_suite` 对串行阶段（c2）把 pytest exit 5（no tests collected）视为正常，但并行阶段（c1）未做同样处理；当某 suite 全部用例都标 `serial`、并行集合为空时，并行阶段返回 5 会让整个 suite 假失败。当前 unit / integration / E2E 三个 suite 的并行与串行集合均非空，不触发。修复方案：`c1` 与 `c2` 对称处理 exit 5（`if [ "$c1" != 0 ] && [ "$c1" != 5 ]; then return "$c1"; fi`）。
- 处理：待后续修复
