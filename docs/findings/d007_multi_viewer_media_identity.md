# d007 同 Context 多页面共享真实媒体、输入与页面身份适配可行

- 来源：t001 / s004_media_connections，2026-10-27独立Gemini真实黑盒55.58秒、退出码0；交付五文件与重跑快照逐字节一致。
- 结论：同一Google Chrome Context两个不同client_tab_id能同时解码同一Docker CloakBrowser的1080p画面与非零音频；关闭首页后次页媒体继续。Web Locks可在同Origin下防复制sessionStorage ID踢掉原页，保持官方HELLO直接转发。
- 证据：s004/code与blackbox_review.md。两selected remote候选均UDP30006；双页真实输入经容器CDP读取121212（各3次，总6），单页负例111；首tab关闭后次页继续24帧、音频48,784字节和约1.9718能量增长。刷新保ID，Debugger.pause原页时复制仍重映射。
- 影响：支持官方多controller连接与客户端身份适配，不引入控制租约；Debugger.pause不是Page lifecycle冻结，HELLO前缀检查不是网络逐字节校验。未证明全局8/30策略、公网/TURN、正式非root/只读/Profile隔离或长期输入可靠性。
- 现状：有效
