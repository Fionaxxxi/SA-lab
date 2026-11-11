# 三人实现的第三方依赖

| 材料 | 版本或来源 | 许可及用途 |
| --- | --- | --- |
| OfflineVoiceAssistant | 指定 SHA 见 upstream-baseline.md | MIT，作为采集与工程结构参考。新采集实现由本次编写。 |
| Vosk Python / Android | 0.3.45 / 0.3.47 | Apache-2.0，离线中文转写。 |
| ONNX Runtime Python / Android | 1.20.1 / 1.20.0 | MIT，执行模型。版本差异须在跨端数值复核中登记。 |
| SentencePiece | 0.2.0 | Apache-2.0。CMake 从官方 v0.2.0 构建静态库，Python 使用对应包。 |
| multilingual MiniLM L12 v2 | 用户提供固定仓库 SHA 后下载 | Apache-2.0，384 维语义编码。 |
| Silero VAD | 用户提供固定仓库 SHA 后下载 | MIT，语音片段检测。 |
| Vosk cn-0.22 | 官方模型站点 | Apache-2.0。权重实际 SHA256 随下载生成。 |
| OkHttp / Okio | 4.12.0 / 3.6.0 | Apache-2.0，HTTP 正文传输和计量。 |

模型生成的 manifest 保留下载来源和许可字段。交付源码保留依赖版本，正式分发 APK 时随库和权重的实际分发内容保留对应许可证。
