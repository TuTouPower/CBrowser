> 范围更新：本报告保留对应实验快照及历史限制。用户随后明确豁免公网与原生Linux x86_64执行；当前有效门禁见t001/scope_adjustment.md及架构计划“执行调整”。未运行项不计为测试通过。

# 原生 Chrome composition 到真实浏览器输入

## 问题

验证第20.1技术阶段的中文输入通道：外部Chrome原生composition/textInput经官方input DataChannel和X11到真实CloakBrowser，不用剪贴板粘贴或写远端DOM模拟。

## 成功判据

- 先验证实际连接和ASCII正例，再原生CDP imeSetComposition/insertText；输入消息和远端只读DOM精确匹配。
- 中文、标点、预编辑取消、Emoji有可复核实际结果；容器clipboard哨兵保持，宿主clipboard不访问。
- 不用JS dispatchEvent或更改远端DOM制造通过；区分CDP输入机制与真实OS候选窗。

## 尝试

- 主控初版未等待实际连接，事件存在但远端为空；失败保留，不定性为产品输入法Bug。
- 连接/ASCII控制后中文实际到达；原断言要求末尾compositionend也trusted，过严。原失败保留，改为原生trusted compositionstart/textInput、实际co,end消息和远端DOM三方闭环，不把末尾信任标记当传输成功证据。
- 独立reviewer保持五源不改重跑，并加独立标点/取消/Emoji harness及空白页/dispatchEvent探针。reviewer清理自有临时harness后，主控从完整OpenCode写入日志恢复同一原文，保留可重跑证据。
- 额外harness原版只记录部分match布尔值；主控新verify_extra_harness.py逐项核验JSON，任何不匹配非零。未改原预期。该包装在真实容器完整重跑exit0，待t001最终全scope review一并审查。

## 证据

- 独立五源SHA256与主控副本一致，ime_native_probe.py实际exit0、19.517秒；命令/源码核查见independent_review.md。
- ASCII7经真实输入到DOM，清空后中文提交：trusted compositionstart/update/textInput，input channel实际co,end,中文，远端DOM严格中文，容器clipboard哨兵不变。
- 额外harness和主控严格包装真实重跑：你好，世界！精确匹配，预编辑chexiao实际可见、取消后为空，Emoji精确匹配，clipboard哨兵不变；task scratch/ime_extended/extended.log与extra_harness_result.json保留原始结果，进程4979退出0，专属资源清理。
- 源码固定commit6ee68a7a815956e6745e916741f13335e0b3ff53：X11 co,end使用_type_text_xtest或xdotool type，不使用clipboard paste；Wayland不是本实验平台。
- 空白页同样出现末尾compositionend.isTrusted=false，JS dispatchEvent探针未观察到页面调用，可排除Selkies站点合成这一解释。独立报告进一步断言Blink InputMethodController具体内部机制，未读到对应Chromium实现证据，主控不采纳该细节，只记录Chrome/CDP层对照观察。

复现将code内容复制至独立scratch，不直接在docs运行；需s001基础镜像、本机Chrome/Docker/uv，独占HTTP18095/UDP30018及cbrowser-spike-ime前缀。

```bash
bash start_containers.sh
uv run --no-project --with playwright python ime_native_probe.py
uv run --no-project --with playwright python verify_extra_harness.py
uv run --no-project --with playwright python test_blank_cdp.py
bash stop_containers.sh
```

任一失败均保留退出码并在finally执行专属资源清理。test_blank_cdp仅观察事件，不能以它退出0替代输入到远端验证。

## 结论

- 原生CDP composition/textInput→官方输入消息→X11→真实DOM技术通道通过，clipboard未被用作提交模拟。
- 仅少量fixture，未验证OS候选窗GUI、1000次组合输入、地址栏/受控/富文本全矩阵、双页长期IME、真实剪贴板权限拒绝及用户原内容保护；第19.3门禁全部保留，后续t004/t007/t008/t009继续实现验收。
- root/匿名Pulse旧媒体fixture不是生产沙箱安全证据；原生Linux仍未运行。

## 是否采纳

- 决定：是，仅采纳原生composition与X11输入技术可行性。
- 理由：独立五源真实重跑与主控额外精确结果验证，保留真实OS/压力边界。
- 后续 task：t001
- 无需后续理由：不适用

## 关联 findings

- d014：X11原生IME提交不需clipboard，末尾事件信任标记不能替代全链路判定。
