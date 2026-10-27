> 范围更新：本报告保留对应实验快照及历史限制。用户随后明确豁免公网与原生Linux x86_64执行；当前有效门禁见t001/scope_adjustment.md及架构计划“执行调整”。未运行项不计为测试通过。

# 共享捕获仲裁与真实页面可见性

## 问题

验证第18.9/10和第9章：后台页面不压低前台、持续变化视频不因无输入降8、全部后台/断开暂停、恢复画面。原型使用固定Selkies2.1.0，不代表全17项或生产性能门禁完成。

## 成功判据

- 真实damage驱动静止target8/持续动画target30，不能把编码器输出FPS当运动信号。
- 实际Peer输入经X11/浏览器DOM可见；单后台不影响另一前台；全部隐藏实际暂停捕获。
- 实际原生Chrome同窗口Tab切换/窗口最小化产生document.hidden变化，薄客户端只在input channel发送官方STOP/START，不伪造visibility状态。
- 全隐藏恢复实际set_framerate(8)先于resume，随后motion提频；后台恢复请求IDR，关闭全部后新连接恢复；客户端参数不能篡改全局FPS/尺寸/Turbo。

## 尝试

- v1机制及缺口保留report_v1.md与independent_review.md。
- R3独立Core失败、Native通过：存在双控制路径、测试专用600ms锁8、尺寸断言跳过和未适配旧Core S10。
- R4统一asyncio锁内幂等仲裁，移除600ms锁8；实际API action trace采用Agent内部上一事件时间戳截断，避免跨宿主/容器单调时钟比较。暂停时如实报告底层fps，不假写8。
- 旧Core S10整项退役，原测试完整保留code/revision_03/test_e2e_real_pipeline.py；理由为旧官方App未集成真实visibility，本项由新Native7全链路替代，未把旧失败预期改成当前输出。

## 证据

- 独立Gemini固定六文件实际Core9退出0，71.4秒；最终Native7退出0，24.9秒。报告independent_review_r4.md，六源与作者及主控重跑副本逐字节一致。
- 首次Native实际失败（期望2 Peer，实际1），原记录在主仓review_policy_r4.jsonl；reviewer通过单独诊断后未改六交付源再运行成功。不能删去首次失败或把最终一次成功声称所有启动时序可靠。
- 主控另复制相同六源，原生Native7再次退出0，日志task scratch/policy_r4_root/root_native.log；两Tab同window，前台持续解码/后台0，交换前后台后角色互换，最小化双hidden暂停，恢复set8→resume→motion30，关一页另一页继续，全部关闭捕获停止且容器内CDP仍有真实target。
- Core实际输入使光标到(250,250)、DOM inputCount由0增3。静止target8但damage输出可接近0，持续Canvas解码约29–31FPS；不是每静态秒必输出8帧。
- 非法参数经实际打开DataChannel发送，X11及decoder都保持1920×1080，Turbo攻击后静止回8。

复现先将code当前六文件复制到独立scratch，不复制revision_03运行，不直接在docs运行；需要s001基础镜像、Docker、本机GoogleChrome，独占HTTP18084/UDP30008及cbrowser-spike-capture前缀。先执行Core，再Native：

```bash
uv run --no-project --with playwright --with websockets python test_e2e_real_pipeline.py
uv run --no-project --with websockets python native_visibility_e2e.py
```

## 结论

- AC-003技术观察已由真实原生页面、服务端捕获API与解码三方验证，采纳R4可行性。
- 首次Native启动失败表明后台握手/并发负载时序仍有风险；正式客户端需处理激活/重连和明确失败，不据此豁免后续E2E。
- 独立报告“34.7ms提帧完全符合第19章延迟指标”推论不采纳：该时间是捕获API事件差，不是输入至画面P95或首帧P95，未做指定Linux容量与8小时测量。
- 此实验root/无Xauthority，不证明生产沙箱安全；多Profile CPU资源调度、完整IME、丢包音画同步及原生Linux待后续验收。架构冻结仍等t001其余项。

## 是否采纳

- 决定：是，仅采纳真实damage聚合和visibility适配可行性。
- 理由：最终独立Core9/Native7与主控原生7场景重跑均通过，历史失败与性能边界保留。
- 后续 task：t001
- 无需后续理由：不适用

## 关联 findings

- d005：编码FPS不是运动信号。
- d013：单一捕获仲裁和真实visibility闭环。
