# d040 JPEG完整性检查须拒绝libjpeg容错警告

- 来源：t057独立代码review t057_code_f003。
- 结论：Pillow 13.0.0可容错解码补回EOI的截断JPEG并填充灰色区域；仅load成功不足以证明码流完整。jpeginfo 1.7.1的`--check -`完整扫描可将这类警告判为非零，同时接受合法纯色帧。
- 证据：.scratch/t057/red_decoder_warning.log；Docker实测jpeginfo_probe_supported.log：合法纯色exit=0，删除1000字节熵数据再补EOI的帧exit=1；Mac使用上游v1.7.1源码在本任务scratch构建同版工具。首次`--check --stdin`无位置参数在实装版本对合法帧亦返回1，未采纳；仅用已验的`--check -`接口。
- 官方接口：[jpeginfo源码及说明](https://github.com/tjko/jpeginfo/tree/v1.7.1)，标准输入读取图像数据，`--check`完整解码检查；不使用读取文件名列表的`--file -`。
- 影响：Browser镜像提供jpeginfo，Agent通过stdin传入JPEG，丢弃stdout/stderr，限制子进程2秒；缺工具或超时失败封闭。Pillow仍负责格式/尺寸检查，不采用像素阈值；Mac门禁工具仅安装在本task scratch并通过PATH提供，不修改系统安装。
- 现状：有效
