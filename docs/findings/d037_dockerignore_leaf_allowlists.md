# d037 Dockerignore 父目录否定规则会递归放行内容

- 来源：t060_gate_infra_and_privacy，原生 BuildKit COPY 实验。
- 结论：`!src/`、`!config/` 等父目录否定规则会重新纳入子树；它们不是“仅允许遍历目录”。白名单应直接列叶子文件或必要子树，Docker 会为叶子例外遍历被排除的父目录。
- 证据：原 supervisor ignore 下，原生 `COPY src/backend/cbrowser/services/profile_service.py` 成功，违反只允许两个 services 文件的契约；移除父目录否定规则后，该 COPY 以 not found 拒绝，而两份允许文件仍可 COPY。`tests/e2e/test_native_build_contexts_e2e.py` 用原生 BuildKit 对五个运行镜像规则执行 5 个正例、26 个反例（bytecode、cache 目录、秘密与数据路径、额外 services 文件），5 项参数化测试全部通过。
- 影响：五个运行镜像及独立探针镜像使用叶子白名单；静态 matcher 修正目录规则语义，并由原生 Docker E2E 守护，避免近似模型与真实构建行为相悖。
- 现状：有效。API 的 `!src/backend` 是实际 COPY 整个 backend 子树的明确准入，保留该规则；其 bytecode 继续由末尾排除规则拒绝。
