# d014 原生 composition 提交可经官方消息和 XTest 到达真实浏览器

- 来源：s009_native_ime_input / t001
- 结论：外部Chrome CDP原生composition/textInput经input channel co,end到真实CloakBrowser DOM，容器clipboard哨兵不变；不需要粘贴或写远端DOM模拟。
- 证据：独立五源真实重跑19.517秒exit0；主控标点/取消/Emoji严格结果包装再跑exit0，源和原始日志见s009/report.md。空白页也出现末尾compositionend.isTrusted=false且未观察到JS dispatchEvent；不采纳未经源码证实的Blink具体内部机制解释。
- 影响：t004/t007/t008可保留官方输入路径；等待实际连接并用ASCII正例/消息/远端DOM互证。少量CDPfixture不等于OS候选窗、1000次IME/clipboard、受控/富文本或双页长期验收。
- 现状：有效
