# p085 Profile 工厂按真实设备分布分派 persona

- 来源：2026-11-13 同类项目技术调研（`.scratch/reports/隐私浏览器同类项目技术调研.md` P2-14），借鉴 Camoufox BrowserForge / `coherence.py`、Foil 四层拆解
- 内容：按真实设备分布分派 persona（Linux 占比即只画 Linux、macOS persona 需装对应字体与大屏 DPR），seed 空间当有限资源去重，避免全量 `--fingerprint-platform=windows` + 同一 GPU 池造成群体聚类。核心认知：「更多随机 ≠ 更多掩护」——stock 浏览器不会做的噪声、异常 CSP、静态常量本身就是指纹（Obscura 静态 navigator 群体聚类最紧即反例）；检测方查的是关系而非单值：canvas↔audio、WebGL↔WebGPU、UA↔OS↔字体、tz↔IP 地理。CloakBrowser 用单 seed 派生全部随机值保证单会话跨 API 自洽，代价是 9 万 seed 空间 + 有限 GPU 池 + 固定常量导致的群体可聚类；Camoufox 用贝叶斯真实流量分布 + `coherence.py` 拒绝不可能组合补群体层。本次为只读调研，未授权改生产代码。
- 处理：t068；resolution=transferred；reason=已核实当前代码与有效 task，按同一交付面聚合转交 t068；过时描述与剩余范围见 task spec，归档仅表示转办
- 时间：2026-11-13T19:16:54+08:00
- 关联：p074（原子身份 bundle）、p081（引擎升级回归基线）、p069（archive，tz/locale/字体联动）、p063（archive，font sets path）、p022（archive，字体 E2E）、p045（parked，UA-CH arch）

## 目标

1. Profile 工厂按市场份额分布分派 persona，并校验组合在真实设备上可能出现。
2. seed 空间作为有限资源去重；同一 GPU 池/字体集/平台组合不得被批量复用。
3. 群体层一致性检查纳入创建期门禁，与 p074 的单会话自洽检查互补而非重复。

## 验收

1. 批量生成 N 个 Profile 后，平台/GPU/屏幕/字体组合分布与真实流量分布不显著偏离，且无不可能组合。
2. 新建 Profile 不因 seed 碰撞产生可聚类群体。
3. 与 p081 的基线比对共用同一组探针，不维护两套测量口径。
