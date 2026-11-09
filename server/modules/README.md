# server/modules（彭雯青负责的 M2–M4 电脑端实现）

本目录是电脑端（Python）参考实现，用于**锁定契约、生成金样例、给 Android 端对齐**，不是最终手机端代码。
手机端 Kotlin 实现见 `mobile/app/src/main/java/com/example/interviewfeedback/analysis/{asr,semantic}/`（S1 待建）。

## 文件

| 文件 | 对应模块 | 职责 |
|---|---|---|
| `asr.py` | M2 | PCM 片段 → `transcript{full_text, segments[]}`；校验 Base64、字节数、片段顺序与唯一性 |
| `semantic.py` | M3 | 文本 → 句子切分 → tokenize → ONNX → mean pooling → L2 归一化（384 维） |
| `match.py` | M4 | 句子向量与要点向量余弦匹配，输出 `score/covered/evidence_sentence_id` |
| `config.py` | — | 读 `models/manifest.json`，解析模型路径、M3/M4 配置 |
| `errors.py` | — | `ModuleError` 及 `INVALID_PAYLOAD / NO_SPEECH / NO_TRANSCRIPT / MODEL_UNAVAILABLE / DEADLINE_EXCEEDED` |

## 调用约定

- `transcribe_segments(segments, model_dir=None)`：输入 `[{segment_id, start_sample, end_sample, pcm_b64}]`，返回 `{"transcript": {...}}`；
  `start_sample/end_sample` 是**原始录音采样索引**，左闭右开；`end_sample - start_sample` 必须等于 PCM 字节数 / 2。
- `SemanticEncoder().encode_transcript(transcript, keypoints)`：返回 `{"embeddings": {dimension, answer_sentences[], keypoints[]}}`。
  **M4 的输入是内层 `embeddings` 对象，不是外层信封**——这是 S0 实测中踩到的接口错误，已写入评审清单 C1。
- `match(embeddings, threshold=None)`：返回 `{"matches": [{keypoint_id, score, covered, evidence_sentence_id, evidence_text}]}`；
  并列取最早句；零向量、维度不符、NaN 一律 `INVALID_PAYLOAD`。
- 阈值默认读 `manifest.json → configs.m4_matching.threshold`（当前 0.5，标 `provisional_until_s2`）。

## 已知限制

1. Vosk 中文输出为空格分词、无标点，`split_sentences` 会把整段切成一句；接入 M1 后以 VAD 段为句子单位。
2. 电脑端 `vosk 0.3.45`，Android 端依赖 `0.3.47`，同段音频结果可能不同，须以手机结果为准。
3. 每段独立 `KaldiRecognizer`，跨段长句不接续；S1 需用真实分段输入复核。

## 自测

```powershell
$py = "D:\Computation_Partitioning\SA-lab\.venv\Scripts\python.exe"
& $py -m unittest discover -s "D:\Computation_Partitioning\SA-lab\server\tests" -p "test_*.py" -v
```

用例说明与实测数据见 `experiments/results/S0_pwq_run_log.md`。
