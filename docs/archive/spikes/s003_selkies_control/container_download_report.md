# 真实 CloakBrowser 跨容器 UDS 下载与断开恢复

## 目的与拓扑

补齐原s003只在宿主Google Chrome上运行的边界。Browser容器实际运行CloakBrowser、loopback CDP、Browser Agent代理与本地HTTP fixture；另一个Supervisor客户端容器仅通过共享named volume的agent.sock调用CDP，两容器均network=none，不发布TCP端口。客户端只读挂载runtime和exchange，不挂载浏览器Profile，也不持有Docker Socket。

源代码为code/container_uds五文件。container_cdp_probe.py复用原真实CDP代理，仅将Chrome路径改成容器实际Cloak二进制并在root实验加--no-sandbox；独立Browser/客户端驱动在另外四文件，不是生产实现。

## 已执行证据

主控于2026-10-27T10:41:13+08:00核对以下真实实验，各退出码0：

- 单容器真实CloakBrowser原完整测试通过；两次完成事件和下载内容50/51bytes，外部覆盖目录最终为空。
- 跨容器recovery：Supervisor容器经UDS附加真实Cloak页面并触发首次下载，文件内容匹配；另一automation UDS客户端覆盖下载目录/关闭事件后断开，管理session自动重臂且收到CDP成功响应；第二次真实下载产生新GUID、51bytes回到default，两文件数量正确，external为空。Browser.close后Browser Agent容器真实exit0。
- 独立override_control对照：使用全新容器/卷，保持外部客户端连接，覆盖策略后实际下载到external/download-1.txt，内容50bytes正确且default空。证明覆盖命令确实生效，恢复正例不是忽略覆盖造成假绿。
- networknone与无PortBindings由Docker inspect核对，不用HTTP ACK或内部计数替代文件内容。原始日志位于task worktree .scratch/container_cdp_probe/下root_verify.log、cross_container_verify.log、override_control_verify.log。

独立Gemini已对最终五文件逐字节一致快照完成源码审查和两次真实重跑，均exit0，详见container_download_review.md。事件持久化、并发重臂、异步listener句柄仍属生产实现缺口，不宣称完整生产链路通过。

## 复现

需Docker与已有cbrowser-spike-runtime-browser:test镜像；宿主Python只调用标准库，websockets运行在镜像中。不直接在docs执行，以免生成日志进入文档目录：

```bash
mkdir -p .scratch/container_cdp_probe
cp docs/spikes/s003_selkies_control/code/container_uds/*.py .scratch/container_cdp_probe/
python3 .scratch/container_cdp_probe/run_cross_container.py --case override_control
python3 .scratch/container_cdp_probe/run_cross_container.py
```

只操作cbrowser-spike-cdp-uds前缀容器/卷。脚本finally清理这些专属资源，单次客户端50秒timeout；两条命令串行运行，不能并发占用相同名字。

## 边界

- 本实验是真实跨容器UDS与下载原型，不是正式Supervisor/FastAPI/Artifact事件链路；正常退出重启防误启动另见recovery_review.md。
- 两容器使用root，未验非root/只读或业务授权；无外部CDP端口不代表生产鉴权全部通过。
- 下载事件驻内存，未做持久Artifact上报；多客户端同时覆盖/断开可能竞争，未证明并发或长期稳定。
- 原代理在Browser.close时可能记录预期连接断开为listener error，未据此推断生产异常处理正确。
- 只在本机OrbStack arm64运行，不替代Linux x86_64平台和长压验收。
