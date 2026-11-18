---
pid: "p128"
slug: "t078_ac007_real_deletion_lifecycle_verification"
status: "closed"
resolution: "resolved"
reason: "2026-11-18 本地真实运行补验通过：p126/t076 AC-008 经真实 Chrome/Browser 容器、API/SSE/UI 全链路核对列表、代理使用计数、运行绑定明细一致，SSE 重连可恢复，既有 22/23/24/26 环境零变化；p128/t078 AC-007 完成运行态停止并删除、停止失败保留数据后 retry 完成、API 重启中断恢复与重复确认幂等，以及长列表/低视口/列表卡片下确认与错误信息可见性对照。证据：.scratch/local_verify_20261118/report.md 及同目录证据 JSON。另修复部署大小写缺陷并跑通项目门禁 scripts/run_gates.sh（all_passed=true）。"
---
# p128 t078 AC-007：隔离真实运行环境停止并删除全生命周期验证

- 来源：t078 [deploy] AC-007；云端不可验、待 Mac 补验
- 内容：在隔离真实运行环境完成停止并删除、停止失败保留数据及中断恢复对照；长列表/低视口/列表卡片下确认与错误始终可见。云端无 Docker/Chrome/真实运行实例，做不了该验证；不得用 mock、skip 或历史结果代替。
- 处理：resolution=resolved；reason=2026-11-18 本地真实运行补验通过：p126/t076 AC-008 经真实 Chrome/Browser 容器、API/SSE/UI 全链路核对列表、代理使用计数、运行绑定明细一致，SSE 重连可恢复，既有 22/23/24/26 环境零变化；p128/t078 AC-007 完成运行态停止并删除、停止失败保留数据后 retry 完成、API 重启中断恢复与重复确认幂等，以及长列表/低视口/列表卡片下确认与错误信息可见性对照。证据：.scratch/local_verify_20261118/report.md 及同目录证据 JSON。另修复部署大小写缺陷并跑通项目门禁 scripts/run_gates.sh（all_passed=true）。
