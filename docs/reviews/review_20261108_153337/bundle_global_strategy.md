# bundle_global_strategy

## Summary

从战略适配视角评估：CBrowser 聚焦单机 Docker 沙箱与低延迟直连 WebRTC，彻底去除 TURN/coturn 与分布式依赖，架构战略定位精准，技术复杂度与单机隐私隔离目标高度匹配。核心矛盾在于测试工程与环境依赖存在平台特化倾向（macOS 路径硬编码），需在后续演进中解耦以支持标准 Linux CI。

## Findings

- [Medium][90] tests/e2e/conftest.py:27; tests/integration/test_agent_executor_chain.py:343 — 测试架构存在操作系统环境阻抗，阻碍多平台 CI 战略落地
    - ID: f_global_strategy_platform_impedance; verification: static
    - Evidence: E2E 测试硬编码 macOS Chrome 路径，集成测试存在 18 处 GUI 强依赖跳过; 系统核心容器与后端业务虽为标准 Linux 容器化，但在非开发机宿主上难以执行自动化门禁验收
    - Impact: 阻碍团队协作与跨平台持续集成，增加了部署到标准 Linux 服务器后的验证成本
    - Fix: 统一将宿主依赖转为环境变量探测，并将 GUI 强依赖测试从常规 integration 组剥离至专用 e2e 组

## questions

```json
[
  {
    "id": "q_strategy_01",
    "question": "当前系统声明支持在 Linux 环境运行与部署，但在 E2E 和测试套件中强依赖 macOS 路径 /Applications/Google Chrome.app，是否存在战略上的平台支持脱节？",
    "units": [
      "tests_integration_e2e",
      "contracts_deploy_infra"
    ],
    "evidence_needed": "检查测试夹具与部署脚本中的平台依赖与探测回退机制",
    "counterevidence": "若系统定位完全限定于本地 macOS OrbStack 且有明确规约限制"
  }
]
```

## question_decisions

```json
{
  "q_strategy_01": {
    "result": "confirmed",
    "reason": "精查证实容器化核心具备完全的 Linux 跨平台能力，平台硬编码纯属测试套件与夹具的历史包袱，采纳精查证据并确认为 Medium 级别战略与工程改进项",
    "followup_sha256": "61f2b5736b96536f122a98dd52257562e5105b2889613bcfd0a91909ab42c547"
  }
}
```
