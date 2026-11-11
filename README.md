# 公务员模拟面试语音作答分析

本分支扩展三人的 S0–S3 责任区，包含 Android 录音与导入、离线语音分析、反馈页面，电脑端真实算法适配器，以及端云执行协议和基线统计工具。

使用入口与真实验收条件见 [三人实施说明](docs/team-s0-s3.md)。Android 代码待完整 SDK/NDK 环境构建，真实模型推理和双机基线待模型文件、真实录音与两台手机验证。交付证据中的 demo、fixture、JVM 记录分别标记了固定样例的范围。

| 入口 | 内容 |
| --- | --- |
| mobile/ | Gradle 工程、录音和 WAV、SentencePiece JNI、Silero/Vosk/MiniLM、协调和反馈。 |
| models/prepare_models.py | 固定提交下载、模型文件 SHA256、manifest 和 Android 模型包生成。 |
| server/modules/ | 真实 VAD、ASR、语义及匹配。 |
| server/app.py | 网关启动，SA_MODULE_FACTORY 指向真实模块工厂。 |
| experiments/scripts/ | 实际样本检查、基线运行、统计、CER 和匹配质量。 |
| contracts/ | v1 候选契约、固定样例和错误约定。 |

阶段通过须按原 S0–S3 计划复核，特别是模型 token IDs、两机断网运行、人工标签、跨端容差和非作者签收。
