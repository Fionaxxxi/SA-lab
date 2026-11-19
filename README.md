# Android 客户端

## 本地 rules-v2 候选（2026-11-13）

要点漏判修复已同步到电脑和手机源码：无标点长回答拆为短句/肯定短窗口，否定行动句不作为“已覆盖”证据；模型清单配置为 `rules-v2`、阈值 0.54。`feature/lhf` 包含 `outputs/InterviewFeedback-0.3.1-rules-v2-debug.apk`，但按用户要求不上传未修改的权重或本机 `outputs/android-models-rules-v2.zip`。手机必须另取得与 `models/manifest.json` 匹配的权重并按 `models/README.md` 打包、导入；旧 `rules-v1` 模型包不能与此 APK 混用。这是本地候选，尚未完成两手机与人工标签验收，详细结果见 `docs/S0-S3剩余验收实施清单.md` 第 10 节。旧版 0.3.0 与新调试 APK 签名不同，不能覆盖安装，卸载前先导出需要保留的数据。

## 当前状态（2026-11-12）

Gradle 工程已提交，S1 的本地链路代码已实现：录音与 WAV 导入导出、Silero VAD、Vosk 中文识别、SentencePiece 分词 + ONNX 语义编码、要点匹配、反馈页、任务协调与取消。

**已实现 ≠ 已验收。** 真机两机复跑、异常路径签收与 S2 基线数据仍未完成，证据状态见仓库根目录 `docs/desktop-validation.md` 与 `docs/team-s0-s3.md`。

## 模块与目录

实现期把 M1–M4 合并在 `analysis/semantic/RealModules.kt` 一个类里（共用一套模型目录与配置），`analysis/asr/`、`analysis/vad/` 保留为空目录。设计单元与代码落点的完整对照见 `docs/module-mapping.md`。

| 包 | 职责 |
|---|---|
| `capture/` | M0：录音、WAV 编解码、最近一次录音恢复 |
| `analysis/semantic/` | M1–M4：VAD、ASR、语义编码、要点匹配；`SentencePiece.kt` + `cpp/tokenizer.cpp` 为分词 JNI |
| `application/` | 执行计划（LOCAL / REMOTE / MANUAL_MIXED）、任务协调、节点计时 |
| `transport/` | HTTP v1 远程调用、任务日志、实验事件导出 |
| `ui/` | 录音页与反馈页 |

## 构建

- Gradle Wrapper 已随仓库提交（`gradlew` / `gradlew.bat`，固定 Gradle 8.2），无需本机预装 Gradle。
- 需要：JDK 17、Android SDK（compileSdk 34）、**NDK 26.1.10909125**、**CMake 3.22.1**。后两者用于编译 `cpp/tokenizer.cpp`；缺失时 `externalNativeBuild` 会失败。
- 命令：`cd mobile && ./gradlew :app:assembleDebug`（Windows 用 `gradlew.bat`）。

## 包名

`com.example.interviewfeedback` 仍为占位，定稿方案与影响面见 `docs/package-name-decision.md`，待三人确认后统一替换。

## 模型

模型权重不入库，由 `models/prepare_models.py` 按 `models/manifest.json` 的固定提交下载并逐文件校验 SHA256。缺少 `semantic.onnx`、`silero_vad.onnx` 或 `sentencepiece.bpe.model` 时，对应模块在加载期即报 `MODEL_UNAVAILABLE`。
