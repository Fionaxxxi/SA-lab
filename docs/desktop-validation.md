# 电脑端补充验证与复跑

本轮按用户要求先完成电脑工作，不安排手机连接。电脑诊断只覆盖 S0-P2/P3/P5/P6、S3 电脑模块与协议部分，不宣布 S0–S3 出口全部通过。

## 入口

- experiments/scripts/analyze_desktop.py：导入标准 WAV，读取每行一个要点的 UTF-8 文本，保存 JSON 与 Markdown 反馈。输出明确标为电脑输入、未经人工审核。
- experiments/scripts/desktop_startup.py：5 个独立进程各首次加载并推理；再起第 6 个进程，模型预热一次后记录 5 次复用推理。目录独占创建，避免覆盖已有测量。
- experiments/scripts/desktop_checks.py：独立 Uvicorn 真实服务的四模块 HTTP、同键重发/冲突、异常码、静音、20 次重新创建识别器和 WAV 拒绝用例。不会将合成录音登记成人工数据。
- contracts/examples/golden-desktop-v1.json：从已有电脑实测生成的回归候选期望，先于本轮新进程复跑写入。它不是首轮实测之前的预注册，也没有手机和同学签收。

在仓库根目录，用安装 requirements-team.lock 的 Python 3.11.9 执行 python -m experiments.scripts.analyze_desktop <WAV> --keypoints contracts/examples/desktop-keypoints.txt --models models --output <结果JSON>。

## 测量口径

进程冷启动会重新构建模型，不清空 Windows 文件缓存，因此不能称操作系统冷启动。加载时间含运行文件 SHA256 校验与四模块初始化。推理时间为 M1→M4，不含加载、WAV 解码、额外金样例检查和 UI 展示。峰值工作集和峰值提交量均来自 Windows 的进程生存期高水位；同一热进程的 5 条峰值不是 5 个独立峰值。

内存采集依据 [GetProcessMemoryInfo](https://learn.microsoft.com/en-us/windows/win32/api/psapi/nf-psapi-getprocessmemoryinfo) 及 [PROCESS_MEMORY_COUNTERS](https://learn.microsoft.com/en-us/windows/win32/api/psapi/ns-psapi-process_memory_counters)。工作集与提交量分别记录，单位为字节。系统内存、进程内存和 Java heap 不混用。

缺少模型清单或清单配置非法时，真实服务仍提供 /healthz，模块均不可用；单个模型缺失、哈希不符或加载失败只阻止该模块注册。不会用其他模型替代。客户端发往已知但不可用模块返回 503 MODEL_UNAVAILABLE。严格诊断模式会直接报告缺模型，不用剩余模块冒充完整链路。

## 版本偏差仍须评审

原计划含 JDK 17.0.21、本机实际构建用 17.0.19，均为主版本 17；补丁版本差异已登记。原计划中 Vosk、语义 ONNX、tokenizer 只提供截短 SHA256，无法据其恢复完整预期文件。本轮使用固定来源和实测完整哈希，清单与模型 ZIP 均已保存。Vosk 镜像 22 个文件与官方中央目录的大小和 CRC 一致；语义权重不能宣称与原计划截短哈希代表的文件相同。

实际候选模型与配置需三方确认，并在两台手机用同样输入复核。既往 protocol/JVM 的 fixture 字节计量仍保留独立标签。20 次静音识别请求只能证明对应重复调用与错误处理，不足以单独证明所有负载下无内存泄漏。
