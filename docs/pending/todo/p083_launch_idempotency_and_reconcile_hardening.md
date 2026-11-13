# p083 launch 幂等、进度可观测与运维对账加固

- 来源：2026-11-13 同类项目技术调研（`.scratch/reports/隐私浏览器同类项目技术调研.md` P1-12），借鉴 SealSkin 控制平面
- 内容：SealSkin 的 launch 韧性做法：`X-Idempotency-Key`（10 分钟、非 GET 至多一次、首次仍在跑则等待）、launch progress 阶段查询、`reserveTab`（Launch 点击时先开空标签，避免长启动结束后才开的标签被当弹窗拦下）、bridge 版本协商（不匹配给 Update required 而非坏 UI）、`persistence.py` 单写者 + 原子替换 + 每路径锁 + 自身写 hash 辨识 + watchfiles 重载、每 30s 与 backend reconcile + 孤儿容器清理、`quota.py` 管 session/storage/time、启动时 self-inspect 把容器内路径翻译成 host 路径、launch 前持 lease 防并发超发。项目已有 reconcile / registration grace / 事件反馈 / Docker API 错误细节，但幂等键、bridge 版本协商、reserveTab、lease 缺位。本次为只读调研，未授权改生产代码；复用现有 reconcile 而非另起一套控制平面。
- 处理：未开
- 时间：2026-11-13T19:16:54+08:00
- 关联：p042（archive，registration grace state sync）、p034（archive，runtime/infra 生命周期解耦）、p057（archive，event feedback loop）、p058（archive，observation label helper）、p059（archive，Docker API 错误细节）、p051（archive，门禁期间容器消失）、p073（todo，跨服务共享代码收拢：原子写/per-profile 锁应单一来源）

## 目标

1. 非 GET launch 请求支持幂等键；重复请求等待首次结果，不重复拉起容器。
2. launch progress 阶段可查询；`reserveTab` 在用户点击时先占位；bridge 版本不匹配给明确升级提示。
3. 持久化单写者 + 原子替换 + 每文件锁 + 自身写 hash 辨识；与 Docker 实际状态定时对账、按 label 清理无引用容器；launch 前持 lease 防并发超发。

## 前置

原子写与 per-profile 锁须与 p073 的中立包收口合并考虑，避免再造第三份重复实现。

## 验收

1. 同一幂等键并发/重试只产生一个容器，且失败可重试不产生孤儿。
2. 长启动期间用户可见阶段进度；取消/失败不残留半成品容器或 DB 行。
3. 控制面重启后与 Docker 实际状态在规定窗口内收敛一致。
