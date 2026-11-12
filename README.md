# 公务员模拟面试语音作答分析

本分支扩展三人的 S0–S3 责任区，包含 Android 录音与导入、离线语音分析、反馈页面，电脑端真实算法适配器，以及端云执行协议和基线统计工具。

使用入口与真实验收条件见 [三人实施说明](docs/team-s0-s3.md)。Android arm64 调试 APK 已完整构建并通过签名校验；三种真实模型的电脑直接调用与 HTTP 回环已经通过合成语音诊断。模型包逐一验证了 25 个运行文件的 SHA256。双机运行、至少 30 段人工标注录音、真实性能与质量仍待实际验证。交付证据中的 demo、fixture、JVM 记录分别标记了固定样例的范围。

| 入口 | 内容 |
| --- | --- |
| mobile/ | Gradle 工程、录音和 WAV、SentencePiece JNI、Silero/Vosk/MiniLM、协调和反馈。 |
| models/prepare_models.py | 固定提交下载、模型文件 SHA256、manifest 和 Android 模型包生成。 |
| server/modules/ | 真实 VAD、ASR、语义及匹配。 |
| server/app.py | 网关启动，SA_MODULE_FACTORY 指向真实模块工厂。 |
| experiments/scripts/ | 实际样本检查、基线运行、统计、CER 和匹配质量。 |
| contracts/ | v1 候选契约、固定样例和错误约定。 |

阶段通过须按原 S0–S3 计划复核，特别是模型 token IDs、两机断网运行、人工标签、跨端容差和非作者签收。


无需手机的电脑端入口：experiments/scripts/analyze_desktop.py。电脑启动/内存测量、真实服务异常用例和固定回归样例见 [电脑验证说明](docs/desktop-validation.md)。手机与人工录音验证按用户安排后续执行。


APK 0.2.0 的节点计时面板、运行配置/样本自动关联及完整记录导出见 [实验操作说明](docs/experiment-workflow.md)。正式采集前先导出设备信息并用 mobile_experiment.py 生成配置。
