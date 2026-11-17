# TURN ICE 新代接管与真实媒体连续性

## 问题

证明同一Chrome/服务端PeerConnection换新TURN凭证后实际双端relay，旧代退役后的新媒体继续；不得将make-before-break旧媒体误判成新代成功。

## 成功判据

- 真实CloakBrowser动画/音频经Selkies到GoogleChrome，1920×1080、解码/能量增长。
- 两轮新凭证：服务端ICE真实commit、新ufrag匹配Chrome实际selected relay pair、旧连接关闭并拒绝send；此后重新取基线观察视频/音频/pair字节增量。
- 无效第二轮凭证实际被coturn拒绝，新代不commit；旧媒体可继续，但不能使重启测试成功。
- 同一PC/DTLS与接收track引用连续，凭证不经argv或调试日志泄漏。

## 尝试

- 旧探针正常exit0；独立注入无效第二轮时新代0 relay candidate仍exit0，确认假绿，报告independent_review_failed.md，结果拒绝。
- 修订适配器增加真实commit/旧代close+sendreject诊断、Chrome selected pair新ufrag栅栏、commit后独立媒体增量。零relay candidate在发Offer前HTTP400拒绝。coturn从argv秘密改为0600配置只读挂载。
- 独立第二轮真实正常exit0/17.2秒，对抗exit1/15.6秒，见independent_review_generation.md；exit1核对真实401/HTTP400和未commit，不把通用异常当负例通过。
- 主控发现该快照客户端console还打印pendingIceConfig临时凭证，移除；补pc===initialPC、receiver track===initialTracks，并修正最终摘要取growth样本而非baseline。code为最终R3，独立重跑正常exit0/16.0秒，对抗真实拒绝exit1/15.6秒；最终hash及PC/track引用检查见independent_review_final.md。

## 证据

- 独立generation修订：新代2/3各关闭旧连接且send_rejected=true；新ufrag5if92qY8/wNQRi9H0匹配selected relay-relay pair，fresh baseline后分别+17/+15帧、音频能量+1.30、pair字节+1.2MB/+1.25MB。
- 无效凭证coturn401、API400，generation3未commit，5秒旧媒体+39帧被明确分类为旧连接连续性，不报新代成功。
- 这是OrbStack本地Docker172.29.0.0/16实验，HTTP18091/控制18092/UDP30016，coturn UDP40000–40020。TTL120秒临时凭证，不是正式24h/12h/6h调度。

复现先复制code至独立scratch，不能在docs直接运行或并发相同前缀。需要s001两个基础镜像、Docker、Chrome和uv：

```bash
bash probe_work/start_coturn.sh
bash stage2_containers.sh
uv run --no-project --with playwright --with websockets python stage2_media_restart_probe.py
uv run --no-project --with playwright --with websockets python stage2_adversarial_probe.py
bash probe_work/cleanup.sh
```

负例预期非零；必须检查其adversarial_result真实拒绝/未commit，不把任意失败当成功。无论步骤是否失败，均在finally清理本实验资源。

## 结论

- 已独立证明新代commit/旧代退役后的真实relay媒体及无效凭证反假绿；官方原生SDK仍有d003缺口，依赖固定私有代适配器，不称公共API原生支持。
- 最终PC/track引用加强和移除日志版本独立通过，两轮引用均===且每代+16帧、音频能量增长约1.3；无效代未commit、旧代+40帧仍不报成功。AC-004仍未勾选，因公网部分缺失。
- 客户端/服务端此实验同内网TURN URL，未证明不同公网/内网URL可达；公网候选、受限NAT、UDP阻断、TCP/TLS中继、24h/12h/6h调度及原生Linux均未完成。不能据局部SCOPED PASS冻结架构。

## 是否采纳

- 决定：是，仅采纳本地双端relay和同PC凭证换新可行性。
- 理由：最终九源逐字节匹配独立重跑快照，正常和真实拒绝负例均通过；完整AC-004仍缺公网，不冻结架构。
- 后续 task：t001
- 无需后续理由：不适用

## 关联 findings

- d003：SDK原生重启不能应用新凭证。
- d010：标准SDP三代DataChannel连续性。
- d012：新代commit栅栏与旧代退役后的真实TURN媒体证据。
