# 三人实现的第三方依赖

| 材料 | 版本或来源 | 许可及用途 |
| --- | --- | --- |
| OfflineVoiceAssistant | 指定 SHA 见 upstream-baseline.md | MIT，作为采集与工程结构参考。新采集实现由本次编写。 |
| Vosk Python / Android | 0.3.45 / 0.3.47 | Apache-2.0，离线中文转写。 |
| ONNX Runtime Python / Android | 1.20.1 / 1.20.0 | MIT，执行模型。版本差异须在跨端数值复核中登记。 |
| SentencePiece | 0.2.0 | Apache-2.0。CMake 从官方 v0.2.0 构建静态库，Python 使用对应包。 |
| multilingual MiniLM L12 v2 | e8f8c211226b894fcb81acc59f3b34ba3efd5f42 | Apache-2.0，384 维语义编码。 |
| Silero VAD | 066409f3d9db45a30d21dfcbf9147826ffdd7052 | MIT，语音片段检测。 |
| Vosk cn-0.22 | 官方模型站点 | Apache-2.0。权重实际 SHA256 随下载生成。 |
| OkHttp / Okio | 4.12.0 / 3.6.0 | Apache-2.0，HTTP 正文传输和计量。 |

模型生成的 manifest 保留下载来源和许可字段。交付源码保留依赖版本，正式分发 APK 时随库和权重的实际分发内容保留对应许可证。

本机 Vosk 使用固定镜像 LiangJingyi/vosk-model-cn-0.22@8949a406ac74d453ecae72ca9cfe09095cd3416c 的 model-cn.zip，归档 SHA256 为 9ba59cbaae7921102574b271d9928101eeecbf714a88e57bcff5393b8c4d49c1。该归档是重新打包件，不是官方 ZIP 的逐字节副本；与官方目录的 22 个文件逐一核对相对路径、解压大小和 CRC 一致，证据位于 vosk-archive-comparison.json。CRC 对照不等同于从两个来源取得每个文件的密码学哈希。运行 manifest 另含实际解压文件的 SHA256。

SentencePiece 原生依赖取自官方 PyPI 0.2.0 源码包，SHA256 a52c19171daaf2e697dc6cbe67684e0fa341b1248966f6aebb541de654d15843。Silero 通过固定 GitHub 提交的 jsDelivr CDN 下载，实际 SHA256 1a153a22f4509e292a94e67d6f9b85e8deb25b4988682b7e174c65279d8788e3。MiniLM 实际 SHA256 10f7a088420252b26caf819236ca2c9d2987afd0fc06fec7553b542a5655a05a。
