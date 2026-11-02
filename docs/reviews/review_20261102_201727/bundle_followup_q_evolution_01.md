# bundle_followup_q_evolution_01

## Summary

精查证实：legacy 即现行部署，真实数据根在 ~/.cbrowser、v2 栈未运行，t010 迁移源是作者的真实数据；但数据量与增长速率无任何记录，强形式『每月新增』未获证明。

## Findings

No findings.

## evidence

```json
[
  "docs/handoff.md（2026-11-02T20:12，当前有效节）明言：「正在运行的 `cbrowser:latest` 容器是旧版 VNC，不受影响；v2 栈未运行」。即在 HEAD 当日，作者唯一在跑的实例就是 legacy 构建，v2 栈根本没有运行。同节首条用户决定：「CBrowser 仅本人单机使用」——唯一用户就是作者本人。",
  "DOCKER_DEPLOYMENT.md §1 把根 compose 的 legacy 栈叙述为当前已部署运行的服务（「当前服务已通过 Docker Compose 部署运行」），并给出其持久化数据根 ~/.cbrowser 的布局：profiles.db（配置元数据）、settings.json、profiles/（各浏览器会话数据与 Cookies）；§3 的备份/恢复流程也是围绕这个数据根写的。这不是发布残留的文档口径，而是现行运维手册对现状的描述。",
  "compose.yaml 把 ${CBROWSER_DATA_DIR:-~/.cbrowser} 挂载为 /data：所有现网状态都累积到这个 legacy 格式的数据根；出厂部署路径中不存在第二个 v2 数据根（v2 只存在于开发/测试拓扑与 fixture 中，见 tests_integration_fixtures 单元结论与歷次 handoff）。",
  "legacy 应用代码自 2026-10-26 仓库重组后冻结：最后一次触及 src/backend/main.py 的提交是 524e34e（重组本身），此后 src/backend 的工作全部在 cbrowser v2 包内。这与「在跑但冻结」的部署形态一致，而非「已废弃」：2026-11-02 handoff 仍把在跑的 legacy 容器当作不受新改动影响的现行系统来交代。",
  "由此：t010 的迁移源集是作者真实在用的数据根，不是近空集；t011 要退役的是当前正在运行的产品本体，而非仅删死代码。q_evolution_01 中「作者日常跑 v2 开发拓扑、legacy 仅作发布残留」的反设被 handoff 直接证伪。"
]
```

## result

```json
"confirmed"
```

## limitations

```json
[
  "「仍在积累」的速率维度（使用频率、月增量）无任何仓库记录可依，本结论只确认部署形态一半：legacy 是唯一现网部署、v2 未运行、迁移对象是真实数据根。",
  "静态审阅，未运行容器、未访问作者宿主机数据根；数据量问题若需确数，只能由作者本人在宿主机上盘点 ~/.cbrowser 后回填。"
]
```
