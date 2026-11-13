# p074 Profile 身份收敛为原子配置 bundle 并整体轮换

- 来源：2026-11-13 同类项目技术调研（`.scratch/reports/隐私浏览器同类项目技术调研.md` P0-1），借鉴 CloakBrowser `.cloakbrowser-seed`、Camoufox fpgen/`coherence.py`、CloakBrowser-Manager `ProfileMeta`/`ProfileState` 二分
- 内容：现状有 `fingerprint_seed`、启动 spec 带 `TZ`/`LC_ALL`、`CBROWSER_GEOIP_CACHE` 共享与 `--fingerprint-*` 全量 flag，但身份参数散落多处、未收敛为单一原子配置对象；代理只在 Chromium 进程层「允许」、未设 `WebRtcIPHandling`。目标是把 seed / GPU vendor+renderer / platform / hardware_concurrency / device_memory / screen / storage_quota / locale / timezone / language / proxy（含凭据）/ WebRTC IP handling / fonts+voices / Client Hints 建成 Profile 级原子 bundle，与 cookie/localStorage/cache 一起持久化；轮换 = 整体换 bundle + 清空状态，禁止就地改单个 flag；一个持久 Profile = 一个固定身份，禁止每次 launch 重随机。CloakBrowser 五位数 seed 仅 9 万空间、固定 GPU 池与常量集会造成群体聚类（Foil 拆解），单 seed 只保证单会话跨 API 自洽、不保证群体分布像真人。本次为只读调研，未授权改生产代码；涉及 Profile 数据模型与迁移，需备份验证可恢复后由专项 task 实施。
- 处理：t066；resolution=transferred；reason=已核实当前代码与有效 task，按同一交付面聚合转交 t066；过时描述与剩余范围见 task spec，归档仅表示转办
- 时间：2026-11-13T19:16:54+08:00
- 关联：p069（archive，tz/locale/字体联动）、p045（parked，UA-CH arch）、p067（archive，高级选项默认值）、p063（archive，font sets path）均为单项联动，无原子 bundle 模型，不重复登记

## 目标

1. 定义单一 identity bundle 值对象，Profile 元数据与浏览器状态各自独立但同属一个身份版本。
2. 轮换产生新 bundle 并清空状态；单字段修改一律拒绝或触发整体重算，避免 Windows UA + Apple M1 GPU、macOS UA + DirectX 之类不可能组合。
3. bundle 版本与 Profile 快照绑定，升级/回滚可追溯到具体身份版本。

## 前置与风险

- 破坏性数据模型变更，迁移前须验证备份可恢复、回退路径可用；按零兼容性负担直接定稿，不留旧字段兼容层。
- 备份/快照护栏见 p080；升级回归基线见 p081。

## 验收

1. 同一 Profile 多次 launch 的 seed/GPU/UA/Client Hints/tz/locale/WebRTC IP 全部一致。
2. 修改 bundle 任一字段后，该 Profile 的 cookie/localStorage/cache 被清空且新身份跨 API 自洽。
3. 群体层：随机生成 N 个 Profile 的组合分布通过一致性校验，不存在全量 `windows` + 同一 GPU 池的聚类。
