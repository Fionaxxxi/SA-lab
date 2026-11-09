# 上游源码基线登记（OfflineVoiceAssistant）

> 本文件按实施计划 3.1.1 登记上游代码的来源、版本、路径与迁移去向。原始克隆只留在 `.evidence/`（已被 `.gitignore` 排除），不进入小组版本库。

## 一、基线信息

| 项目 | 内容 |
|---|---|
| 上游仓库 | https://github.com/brain-marchine/OfflineVoiceAssistant |
| 锁定提交 | `826f957d396bbec40bc3008e44bb5e6c8143edf5` |
| 克隆日期 | 2026-11-09 |
| 本地路径 | `.evidence/upstream/OfflineVoiceAssistant`（仅本地） |
| 文件数量 | 1138 |
| 许可证 | MIT License，Copyright (c) 2026 OfflineVoiceAssistant contributors |
| 源码前缀 | `app/src/main/java/com/offline/voiceassistant/` |
| 上游版本号 | versionCode 26 / versionName 3.1.4 |

## 二、构建参数（迁移时对齐）

| 项 | 上游取值 |
|---|---|
| AGP / Kotlin | 8.2.2 / 1.9.22 |
| Gradle | 8.2（仅 `gradle/wrapper/gradle-wrapper.properties`） |
| compileSdk / minSdk / targetSdk | 34 / 26 / 31 |
| ABI | arm64-v8a |
| JDK | 17（`sourceCompatibility`/`jvmTarget`） |
| Vosk 依赖 | `com.alphacephei:vosk-android:0.3.47` |
| 其他依赖 | androidx core-ktx 1.12.0、appcompat 1.6.1、material 1.11.0、constraintlayout 2.1.4、lifecycle 2.7.0、coroutines 1.7.3 |

**已知限制（须在 S0 记录）：**

1. 上游**没有** `gradlew`、`gradlew.bat`、`gradle-wrapper.jar`，只有 wrapper 配置。不能直接运行上游 wrapper，只能用 Android Studio 自带 Gradle 或本机 Gradle。
2. 上游**不含** Vosk 模型（`app/src/main/assets` 只有 knowledge 文本）。`vosk-model-cn-0.22` 约 1300 MB，需单独下载或由手机导入。
3. 上游含 NDK/CMake、sherpa-onnx、llama.cpp、productFlavors（slim/full）等本组用不到的构建逻辑，不能整段照搬。

## 三、迁移映射

| 上游文件 | 行数 | 小组目标 | 处理方式 | 主责 / 验证 |
|---|---|---|---|---|
| `speech/AudioCaptureEngine.kt` | 212 | `capture/InterviewAudioRecorder.kt` | **改造**：保留 AudioRecord 初始化、音源回退、电平计算、stop/release；拆掉“录音直接喂 Vosk”的耦合，改为输出 16 kHz/mono/s16le PCM 并写 WAV（M0） | 刘慧芳 / 林俊希 |
| `speech/SpeechCaptureConfig.kt` | 13 | `capture/` 内配置类 | 复制或合并 | 刘慧芳 |
| `speech/VoskSpeechEngine.kt` | 237 | `analysis/asr/VoskAsrModule.kt` | **复制后改包名**：保留 `ensureModel`/`createRecognizer`/`parseResult`/`release`；输出改为 Transcript 契约（M2） | 彭雯青 / 刘慧芳 |
| `speech/VoskModelInstaller.kt` | 170 | `analysis/asr/VoskModelInstaller.kt` | **复制后裁剪**：保留 URI/外部 zip/网络下载三条路径；`isBundled` 分支可保留但默认不打包模型 | 彭雯青 |
| `model/ModelUriStore.kt`、`model/ExternalModelLocator.kt`、`model/UriStreamCopier.kt` | — | `analysis/asr/` 或独立 `model/` 包 | 复制（Vosk 安装依赖） | 彭雯青 |
| `VoiceAssistantService.kt` | 937 | `application/InterviewSessionController.kt` | **只取骨架**：`startListeningInternal()` 的“创建识别器→启动采集→回调分发”、`stopListening()` 的停止顺序；其余唤醒词/声纹/LLM/通知逻辑全部丢弃 | 林俊希 |
| `app/build.gradle.kts` | 169 | `mobile/app/build.gradle.kts` | **只取** SDK 参数、abiFilters、JDK17、Vosk 依赖；删除 flavors、CMake、下载任务、压缩资源脚本 | 林俊希 |

### 不迁移清单

| 上游模块 | 不迁理由 |
|---|---|
| `llm/`（LocalGgufEngine、RemoteOllamaEngine、HybridLlmEngine） | 本组不做本地大模型，M1–M4 由端侧小模型或远程模块完成 |
| `speaker/`、`k2fsa/sherpa/` | 本组不做声纹验证 |
| `rag/`、`KnowledgeActivity` | 本组不做知识库问答 |
| `tts/` | 本组不朗读反馈 |
| `notification/WeChatNotificationService` | 与本项目无关 |
| `audio/BluetoothAudioManager` | 首版统一手机内置麦克风 |
| `nlp/WakeWords`、`EndWords`、`CommandProcessor`、`CommandFraming`、`ActionExecutor` | 本组是“录音→分析→反馈”，不需要唤醒词/命令解析 |
| `VoiceprintEnrollActivity`、`MainActivity` 的语音助手 UI | 需按“考生端面试界面”重写 |

## 四、迁移时必须注意的实现差异

1. **VAD 实现不同**：上游用能量阈值（`speechThreshold`、`endSilenceFrames`）做端点检测，本组 M1 要求 Silero VAD ONNX。`AudioCaptureEngine` 里的阈值逻辑只能作兜底，不能当作 M1。
2. **录音与识别耦合**：上游 `AudioCaptureEngine.start()` 直接持有 `Recognizer` 并调用 `acceptWaveForm`。本组 M0 必须先落 PCM/WAV，M2 再独立转写，两者要解耦。
3. **置信度**：上游无 `result` 字段时统一给 0.55，本组 M2 契约不含置信度，可保留但不作为判定依据。
4. **模型体积**：cn-0.22 约 1300 MB，不能打进 APK；走“首次下载 / 手机导入 zip”两种方式，`/models/weights/` 与 `*.zip` 均已被 `.gitignore` 排除。

## 五、待 S0 确认

- [ ] 最终包名：当前 `com.example.interviewfeedback` 为目录占位（见 `mobile/README.md`）
- [ ] Gradle wrapper 生成方式（Android Studio 生成 vs 本机 Gradle）
- [ ] Vosk 模型版本：先按 cn-0.22 验证，再按两台手机内存与同一段录音结果决定是否换更轻的中文模型
- [ ] 登记人：本次基线由彭雯青整理，迁移执行人按上表填写实际姓名与日期
