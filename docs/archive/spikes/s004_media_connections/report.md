> 范围更新：本报告保留对应实验快照及历史限制。用户随后明确豁免公网与原生Linux x86_64执行；当前有效门禁见t001/scope_adjustment.md及架构计划“执行调整”。未运行项不计为测试通过。

# 同 Profile 多页面媒体、输入与身份验证

## 问题

验证 v2.3 第18.4–8、12项底层媒体能力：真实 Browser/Stream 双容器、同外部 Google Chrome Context 的两个独立页面，共享同一 CloakBrowser 窗口；固定分辨率、音频、输入及页面身份互不误判。此处没有正式产品 UI/API，不代表完整架构完成。

## 成功判据

- 两个不同官方 client_tab_id 同时解码1920×1080并持续收到字节；外部窗口resize不改变远端尺寸。
- 已知440Hz非静音音源经PulseAudio、Selkies和Chrome解码，两个页面 bytesReceived/totalAudioEnergy 可观察；mute或close首页后次页仍持续。
- 两页实际输入经容器loopback CDP读取真实CloakBrowser DOM，111与222各出现3次、总长度6；单页111负例不能通过。
- 刷新保留身份，复制相同sessionStorage ID时重映射新ID；原页不被踢走。官方HELLO字符串不改写。
- 两个selected remote candidates均为UDP30006；只证明本机映射，不证明公网或TURN。

## 尝试

- 旧版双独立Context/720p、仅send成功、弱“包含A或TAB1”输入检查、改写HELLO、无实际音频等报告均未采纳为完成依据。
- 交付 `code/media_e2e_probe.py` 与四个shell，使用同Chrome Context双tab、固定1080p和实际DOM负/正例。
- 音频绑定真实incoming track到HTMLAudio，发送START_AUDIO并选择auto_null.monitor；据此观察非零音频，不推断先前零流量为浏览器权限问题。
- Web Locks在发送HELLO前检查同Origin活动ID；冲突时更新sessionStorage并关闭冲突socket，让官方重连逻辑重新生成HELLO。成功发送执行原始super.send(data)，不解析重写协议。
- 主控补可移植脚本目录和close首页后音频bytes/energy增长检查；独立review/黑盒对这份最终快照执行，五文件逐字节一致。

## 证据

独立Gemini模型cpa/gemini-3.8-flash，另session于2026-10-27上午实际启动专属容器、执行探针和收尾，各命令退出码0。测试55.58秒；详细源码行号与实测见 `blackbox_review.md`。

- 双decoder分辨率1920×1080，外部viewport800×600后保持不变，两个不同tab_id同时connected。
- 两端selected remote candidate均UDP30006。
- 4秒音频Tab1增长63,756 bytes、Tab2增长64,722 bytes，totalAudioEnergy分别6.9786/6.8845；首页mute后次页仍增长48,300 bytes。
- 单页负例DOM为111；双页交错正例DOM为121212，各3字符，总长6。
- 刷新保ID，复制和原页面Debugger.pause下均重映射冲突ID并建立连接，原页面仍在线。
- 首页关闭后次页继续解码24帧，音频增长48,784 bytes、energy增长约1.9718，CloakBrowser仍运行。
- item09/10明确NOT_RUN；overall为VERIFIED_PASS_WITH_NOT_RUN，不能改称全部通过。

原始重跑日志、JSON保存在主仓 `.scratch/v2_orchestration/review/.scratch/media_final_review/`，不将运行产物入库。复现前先复制代码到独立scratch（勿直接在docs运行）：

```bash
mkdir -p .scratch/media_probe
cp docs/spikes/s004_media_connections/code/* .scratch/media_probe/
cd .scratch/media_probe
trap 'bash stop_containers.sh' EXIT
bash start_containers.sh
uv run --no-project --with playwright python media_e2e_probe.py
```

前提：安装Google Chrome、uv、Docker，已由s001构建cbrowser-spike-runtime-browser:test及cbrowser-spike-runtime-stream:test。脚本固定使用localhost18081/UDP30006及cbrowser-spike-media前缀，不并发运行相同实验。容器临时目录不含用户Profile。

## 结论

- 第18.4–8、12媒体/页面原型通过独立真实重跑；全局帧率策略另行验证，公网与TURN不在本实验范围。
- 两页输入是串行到达的交错输入，证明没有独占锁及双方实际收到，不证明长期无丢键或1000次IME。
- HELLO未修改有源代码直接转发证据；测试仅检查HELLO前缀，不是网络级逐字节对照。独立review“完全严谨/无竞态”等宽泛断言不采纳；尚无多socket并发压力证明。
- Debugger.pause只暂停JavaScript，不是Page Lifecycle frozen/discard。Web Locks只在同Origin生效，正式入口必须保持统一Origin。
- 原型使用root、匿名Pulse与无Xauthority设置，不构成正式非root/只读/Profile安全边界验收。尚未证明整个产品架构及平台/性能要求。

## 是否采纳

- 决定：是，仅采纳上述底层媒体和同Origin页面身份适配可行性。
- 理由：真实双容器、官方Chrome双tab和远端DOM/媒体统计闭环，经独立重跑。
- 后续 task：t001
- 无需后续理由：不适用

## 关联 findings

- d007：多页面1080p、音频持续与真实输入可行；不含全局策略和正式安全验收。
- d005：编码帧率不能直接当作画面动态信号。
