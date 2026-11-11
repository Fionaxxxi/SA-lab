# 三人 S0 至 S3 实现与验收

本分支覆盖三人的代码责任区。Android 工程新增录音、标准 WAV 导入与导出、Silero VAD、Vosk ASR、MiniLM 编码、余弦匹配、反馈、取消、实验事件导出。Python 服务提供四个真实模块的适配入口，保留网关的协议校验和去重。正式模型清单由下载脚本对实际文件计算哈希后生成。

## 启动入口

- Python 3.11.9 环境安装 requirements-gateway.lock，再安装 numpy 1.26.4、vosk 0.3.45、onnxruntime 1.20.1、sentencepiece 0.2.0、matplotlib 3.9.4。
- 运行 models/prepare_models.py，提供两个官方仓库完整提交 SHA。脚本下载固定版本、计算 SHA256、生成 manifest.json 与 android-models.zip。Vosk cn-0.22 权重较大，模型包存储和手机内存要按实机记录。
- 电脑设置 SA_MODULE_FACTORY=server.modules.integration:create_handlers、SA_MODEL_ROOT=models、SA_GATEWAY_TOKEN，以及 manifest 中的 SA_MODEL_VERSION 和 SA_CONFIG_VERSION，再按 server/README.md 启动单进程服务。
- 使用 JDK 17、Gradle 8.2、Android SDK 34、Build Tools 34.0.0、NDK 26.1.10909125 和 CMake 3.22.1 执行 gradle -p mobile assembleDebug。CMake 取得 SentencePiece v0.2.0 并构建 JNI。初次构建需联网。
- 手机安装后先导入模型 ZIP，在页面填写要点、电脑地址和凭据，选择 LOCAL、REMOTE 或 MANUAL_MIXED。录音权限被拒绝后仍可导入 WAV。调试版允许实验局域网 HTTP。
- experiments/scripts/compute_metrics.py 从 JSONL 生成 CSV，可用 --plot 输出图。check_samples.py 校验 30 段真实录音、哈希、标注和题目不重叠的划分。quality_metrics.py 对审核记录计算 CER、Precision、Recall、F1 与证据正确率。run_baseline.py 供电脑侧真实模块诊断，手机反馈时延使用手机日志。

## 仍需实际证据的验收

S0 的真实模型加载、金样例 token IDs 和数值容差需要模型文件及两台手机；S1 的录音、导入、权限、取消与重启需 APK 及真机；S2 需要至少 30 段带标注录音、两台手机的标准与扩展运行；S3 需要同一电脑与两台手机的真实跨端结果、差异单及签收。三人评审签名只能由实际参与者完成。

模型清单、模型金样例、基线结果和双机证据按实际运行生成。源码写入后仍应经过 Android 构建和真实模型复核，当前本地测试的实际结果记录在交付说明中。
