# d039 OrbStack目录flock只在同一内核内互斥

- 来源：t057 task，2026-11-12T09:47:30+08:00 记录实测。
- 结论：同一OrbStack Linux虚拟机的两个Docker容器共享bind目录时，目录inode flock互斥；Mac宿主与虚拟机之间不互通。
- 证据：实施侧.scratch/t057/flock_probe.py及flock_probe.log；独立review复测.scratch/t057/code_review/lock_probe/result.json。两侧均观察container_to_container=true；实施侧host_to_container=false、container_to_host=false。初始“全部互通”断言失败，未记为通过；所有专属容器已退出。
- 影响：预览发布/清除/回收锁仅协调既定API、Supervisor、Agent全在Linux Docker的生产拓扑；不保证Mac辅助进程与容器间互斥。读端依靠打开文件后的不可变字节快照，不依赖跨虚拟机锁。目录销毁重建会更换inode，生命周期仍由实例/策略围栏约束；不将该锁描述成全局策略事务。
- 现状：有效
