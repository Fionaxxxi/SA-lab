# OfflineVoiceAssistant 上游基线

已克隆到本地 `.evidence/upstream/OfflineVoiceAssistant`，该目录由组仓库忽略。HEAD 已检出为 detached commit `826f957d396bbec40bc3008e44bb5e6c8143edf5`。[上游固定提交](https://github.com/brain-marchine/OfflineVoiceAssistant/tree/826f957d396bbec40bc3008e44bb5e6c8143edf5)

```powershell
git clone --no-checkout https://github.com/brain-marchine/OfflineVoiceAssistant .evidence/upstream/OfflineVoiceAssistant
git -C .evidence/upstream/OfflineVoiceAssistant checkout --detach 826f957d396bbec40bc3008e44bb5e6c8143edf5
git -C .evidence/upstream/OfflineVoiceAssistant rev-parse HEAD
```

| 索引 | 用途 |
| --- | --- |
| `app/src/main/java/com/offline/voiceassistant/speech/AudioCaptureEngine.kt` | 刘定位录音读帧与释放。 |
| 同包 `SpeechCaptureConfig.kt`、`VoskSpeechEngine.kt`、`VoskModelInstaller.kt` | 刘、彭定位采集参数、识别器和模型资源。 |
| `app/build.gradle.kts`、`build.gradle.kts`、`gradle/wrapper/gradle-wrapper.properties` | 核对参考构建版本，正式 Android 版本由两机通过后冻结。 |
| `LICENSE` | MIT，Copyright (c) 2026 OfflineVoiceAssistant contributors。 |

本分支新增的协议草案与固定响应骨架为本次实现。若其他分支迁入上游代码，随实际迁移提交登记源路径、目标路径、修改范围及 MIT 版权声明。
