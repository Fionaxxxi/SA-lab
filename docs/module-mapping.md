# 模块映射：设计单元 → 代码落点

本文件回答一个问题：体系结构文档（SAD）与实施计划按 M0–M5 组织，而代码在单人开发阶段做了合并与迁移。评审、复跑或写报告时，需要一张能直接查的对照表，说明每个设计单元在仓库里的确切位置，以及为什么合并。

## 1. 设计模块 ↔ 代码落点

| 设计单元 | 契约职责 | 实际代码落点 | 偏离说明 |
|---|---|---|---|
| M0 采集 | 16 kHz / 单声道 / s16le WAV，输出采样数 | `capture/InterviewAudioRecorder.kt`、`WavPcmIO.kt`、`LastAudioStore.kt` | 无偏离；`LastAudioStore` 额外负责录音在 Activity 重建后恢复 |
| M1 VAD | 输出升序、不重叠的 `segments[]`，无语音返回 `NO_SPEECH` | `analysis/semantic/RealModules.kt` 的 `vad()` | 与 M2–M4 合并在同一个类；Silero 512 帧窗口、64 context、256 state、阈值读 config |
| M2 ASR | `transcript{full_text, segments[]}`，有语音无转写返回 `NO_TRANSCRIPT` | 同上 `asr()` | 同上；Vosk `Recognizer` 按 8000 字节块流式送入 |
| M3 语义编码 | 384 维、max_length 128、mean pooling、L2 | 同上 `encode()` + `SentencePiece.kt` + `cpp/tokenizer.cpp` | 同上；分词走 JNI SentencePiece，推理走 ONNX Runtime |
| M4 要点匹配 | `matches[{keypoint_id, score, covered, evidence_sentence_id, evidence_text}]` | 同上 `match()` | 同上；点积 + 阈值（阈值来自 config，不硬编码） |
| M5 反馈 | 只采纳当前 `task_id` / `attempt` 的结果一次 | `ui/MobileScreen.kt`、`MainActivity.kt` | 无偏离 |
| 执行计划 | LOCAL / REMOTE / MANUAL_MIXED 三模式与合法性校验 | `application/Execution.kt` | 无偏离；`ExecutionPlan` 用 `require` 强制三模式的互斥条件 |
| 任务协调 | 只采纳当前任务，重启后旧任务标中断 | `application/TaskCoordinator.kt` | 无偏离 |
| 远程传输 | HTTP v1，一请求一模块 | `transport/RemoteExecutor.kt`、`WireJson.kt` | 无偏离 |
| 任务持久化 | 任务日志与终态 | `transport/FileTaskJournal.kt` | **原计划 `storage/`，迁入 `transport/`**；理由是同属"跨进程状态持久化" |
| 实验导出 | JSONL / 事件导出 | `transport/ExperimentFiles.kt` | 原计划 `storage/`，迁入 `transport/` |
| 计时与测量 | 节点耗时、上行/下行字节 | `application/TaskMeasurements.kt` | **原计划 `monitor/`，迁入 `application/`**；理由是与 `TaskCoordinator` 同用一套时钟 |
| 服务端模块 | M1–M4 的 Python 实现，与手机端同契约 | `server/modules/{vad,asr,semantic,match}.py` | 无偏离；`audio_io.py` 负责 WAV 读写，`integration.py` 负责编排 |
| 网关 | 校验、超时、去重、路由、错误码 | `server/gateway/{protocol,service,fixtures}.py`、`server/app.py` | 无偏离 |
| 切分与复算（S4） | 最小割、16 种归属枚举 | `planner/` | 仅 README，阶段未到 |

路径前缀统一为 `mobile/app/src/main/java/com/example/interviewfeedback/`。

## 2. 为什么合并

一个人在同一段时间内实现 M1–M4，四个模块共用同一套模型目录、同一份 config、同一个 `CallId` 生成规则。若拆成四个文件，每个文件都要重复一遍路径解析、模型加载失败处理和错误码映射；合并成一个 `RealModules` 反而把"模型加载一次、四模块共享"这件事表达清楚。

代价是**目录不再等于模块**。所以本文件存在。

## 3. 契约没有跟着变

合并只发生在实现层，接口层保持原样：

- `LocalModules` 仍是四个方法：`vad(audio, id)`、`asr(segments, id)`、`encode(input, id)`、`match(embeddings, id)`；
- `LocalExecutor` 仍按 `Module.M1..M4` 分派；
- `CallId` 仍是 `(taskId, attempt, module, planVersion, modelVersion, configVersion, schemaVersion=1)`；
- `ErrorCode` 仍是 14 个，与 `contracts/errors.md` 一一对应。

因此"模块合并"不影响任何跨端载荷、错误码或执行计划语义。检查方式：`contracts/module-request.schema.json` 与 `module-result.schema.json` 均未因合并且改。

## 4. 构建入口

- Gradle Wrapper 已补：`mobile/gradlew`、`mobile/gradlew.bat`、`mobile/gradle/wrapper/{gradle-wrapper.jar,gradle-wrapper.properties}`，固定 Gradle 8.2。
- 仍需本机具备：JDK 17、Android SDK（compileSdk 34）、**NDK 26.1.10909125**、**CMake 3.22.1**。缺少 NDK 或 CMake 时，`externalNativeBuild` 会失败，因为 `cpp/tokenizer.cpp` 走 JNI 编译。
- 构建命令：`cd mobile && ./gradlew :app:assembleDebug`（Windows 用 `gradlew.bat`）。

## 5. 证据入口

| 证据 | 位置 |
|---|---|
| 契约与错误码 | `contracts/` |
| 模型清单与下载脚本 | `models/manifest.json`、`models/prepare_models.py` |
| 实验配置与样本模板 | `experiments/configs/`、`experiments/samples/` |
| 实验脚本 | `experiments/scripts/`（13 个 Python + 1 个说明） |
| 服务端测试 | `server/tests/`（10 个文件，含 JVM/实验/模型注册表） |
| 金样例 | `contracts/examples/golden-desktop-v1.json` |
| 架构决策 | `docs/adr/` |

## 6. 维护规则

新增或迁移模块时，同步更新本表第 1 节与第 3 节的契约检查项。若某次变更同时修改了 `LocalModules` 接口，必须在表里标出"契约变更"，并同步 `contracts/` 与 `docs/contract-review-s0.md`。
