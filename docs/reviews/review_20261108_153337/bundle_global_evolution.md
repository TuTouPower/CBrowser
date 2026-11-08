# bundle_global_evolution

## Summary

从演进与长期成本视角评估：单 baseline Alembic 持久化重构（ADR 023）、全量不可变发布（deploy_v2.sh）与设计系统 Token 自动化编译门禁表现卓越，为长期演进奠定了极佳基础。主要演进负债集中在跨服务协议 Schema 导出缺乏自动化 CI 守护，以及历史审查与调研资产缺乏自动化归档流转机制。

## Findings

- [Medium][90] scripts/export_supervisor_protocol.py; export_stream_protocol.py; tests/unit/test_supervisor_schema.py — 跨服务通信 Schema 治理机制存在静默退化风险
    - ID: f_global_evolution_schema_drift_governance; verification: static
    - Evidence: 协议导出脚本遗漏了 8 个 Supervisor 消息与 1 个 Stream 关键信令，而单元测试采用硬编码白名单比对导致门禁失灵; 前端 OpenAPI 生成类型在 CI 中未强制检查 git diff
    - Impact: 随着后续接口与协议演进，跨语言与跨服务接口定义极易发生静默脱节与隐蔽破坏，增加团队沟通与版本迭代成本
    - Fix: 在 CI 门禁中增加 export_all_schemas.py && git diff --exit-code 强制校验，并使用反射断言协议模型全量导出

## questions

```json
[]
```

## question_decisions

```json
{}
```
