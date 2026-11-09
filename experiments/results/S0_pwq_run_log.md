# S0 彭雯青任务运行记录

> 记录日期：2026-11-09
> 分支：`feature/pwq`（本地，未推送）
> 设备：联想 21LD（Core Ultra 5 125H / 32 GB / Windows 11）
> 运行时：`D:\Computation_Partitioning\SA-lab\.venv`（Python 3.11.9，pip 26.3）
> 模型：`models/manifest.json`（v1，SHA256 全部实测回填）

本记录只覆盖**电脑端可验证部分**（S0-P1–P6）。Android 端（S1）因 `mobile/` 尚无 Gradle 工程骨架、本机无真机/模拟器，本轮未开始。

---

## 1. 用例结果矩阵

| ID | 任务 | 产物 | 结果 | 证据 |
|---|---|---|---|---|
| S0-P1 | 模型清单 | `models/manifest.json` | 完成：5 条目，sha256 实测；英文 L6 标 `rejected` | manifest.json |
| S0-P2 | 固定 PCM 转写 | `experiments/scripts/s0_min_asr.py` | 通过：两段固定 WAV 均转写成功，片段偏移为原始采样索引 | `experiments/results/s0_asr_a.json` |
| S0-P3 | 最小编码 | `experiments/scripts/s0_min_encode.py` | 通过：384 维、norm≈1.0、token IDs 与登记一致 | `experiments/results/s0_encode.json` |
| S0-P4 | 金样例登记 | `contracts/examples/golden-s0.json` | 完成：9 个用例（含 3 句可控文本基线）；**存在顺序偏差，见 §3-1** | golden-s0.json |
| S0-P5 | 冷/热启动与内存 | `experiments/scripts/s0_startup.py` | 完成：语义冷启动 5 次、Vosk 冷启动 2 次、热推理 20 次 | `experiments/results/s0_startup.csv` |
| S0-P6 | 异常样例 | `experiments/scripts/s0_negative.py` | 通过：7/7 错误码符合契约 | `experiments/results/s0_negative.json` |
| S0-P7 | 契约评审 | 评审记录 | **未完成**：需林俊希（schema）/刘慧芳（片段字段）确认 | — |

模块自测：`server/tests/test_pwq_modules.py`，17 个用例全部通过（16.9 s，含 ONNX 加载）。

---

## 2. 实测数据

### 2.1 M2 转写（Vosk cn-0.22）

输入为 `experiments/samples/local/` 下两段合成语音（Microsoft Huihui Desktop，zh-CN；**非真人录音**，已被 `.gitignore` 排除，不入库）。

| 用例 | 音频 | 采样数 / 时长 | WAV SHA256 | 转写耗时 |
|---|---|---|---|---|
| A | s0_case_a.wav | 311440 / 19.465 s | `A60E61DA…6A02B2F` | 20458.5 ms（含模型加载与解码） |
| B | s0_case_b.wav | 249360 / 15.585 s | `30F8E15C…B6CA11B8` | 与 A 同进程连续运行，未单独拆分耗时 |

A 转写（原样，Vosk 输出为空格分词、无标点）：

```
考生 开始 作答 面对 群众 诉求 我 会 先 耐心 倾听 准确 记录 问题 在 按 职责 范围 分类 处理 能够 当场 解决 的 立即 解决 需要 协调 的 说明 办理 时限 并 及时 反馈 进展
```

B 转写：

```
首先 我 会 稳定 情绪 弄清 对方 最 关心 的 问题 然后 核实 事实 依据 避免 主观 判断 最后 提出 可 执行 的 方案 并 约定 下 一 次 沟通 时间
```

### 2.2 M3 编码（multilingual MiniLM L12 ONNX）

固定三句文本：

| 指标 | 实测值 |
|---|---|
| 向量维度 | 384 |
| 向量数 | 3（s1/s2/s3） |
| L2 范数 | 1.0 / 0.99999994 / 1.0 |
| cos(s1, s2) | 0.38707343 |
| token 数（“面对群众诉求，我会先耐心倾听并记录关键信息。”） | 18（含 `<s>`=0 / `</s>`=2 边界） |

token 序列（S0 锁定值）：

```
[0, 6, 26811, 42444, 78119, 8681, 4, 89809, 2996, 117388, 107283, 10456, 2672, 42750, 42037, 5412, 30, 2]
```

### 2.3 M4 匹配（阈值 0.5 / 0.8）

可控三句基线（文本见 §2.2）：

| 要点 | 分数 | 证据句 | 0.5 覆盖 | 0.8 覆盖 |
|---|---|---|---|---|
| k1 耐心倾听并记录群众诉求 | 0.773077 | s1 | true | **false** |
| k2 按职责分类处理，当场解决 | 0.821228 | s2 | true | true |
| k3 说明办理时限并及时反馈 | 0.852047 | s3 | true | true |

结论：0.8 阈值会漏掉 k1，0.5 偏宽松；阈值必须用 S2 校准集确定，当前 `manifest.json` 标 `provisional_until_s2`。

### 2.4 冷/热启动与内存

| 场景 | 样本 | 加载耗时 | 推理耗时 | 峰值工作集 |
|---|---|---|---|---|
| 语义模型冷启动（子进程：import → 加载 → 首推理） | 5 | 1561.9–1733.7 ms，中位 1601.8 | 11.4–12.4 ms，中位 11.7 | 1124.3–1124.5 MB |
| 语义模型热推理（同进程） | 20 | — | 10.0–11.8 ms，中位 10.8，均值 10.735 | 1124.3 MB（稳定） |
| Vosk 模型冷启动（子进程：加载 + 1 s 静音识别） | 5 | 15601.3–16037.5 ms，中位 15734.2 | 241.7–244.9 ms，中位 242.5（含 recognizer 初始化） | 4909.6–4911.6 MB |

口径说明：

- 中位数与均值由 `s0_startup.csv` 排序后计算（均值经工具复核 = 10.735 ms），可复核；
- 峰值工作集是**单模型单进程**数值，包含 Python、numpy、onnxruntime / Kaldi 运行库基线，**两者不能相加**；
- 真实链路同进程同时加载 Vosk 与 ONNX 的峰值**本轮未测**，S1 需在手机上另行测量（手机内存上限更紧）；
- Vosk 冷启动约 15.7 s，主要成本是 2.0 GB 模型目录的加载；手机上必须换更轻模型或做首次安装期预加载，否则首启不可接受。

### 2.5 异常用例（7/7）

| 用例 | 构造 | 期望错误码 | 实际 |
|---|---|---|---|
| N1 odd-pcm | PCM 字节数为奇数 | INVALID_PAYLOAD | 一致 |
| N2 empty-segments | 空片段列表 | NO_SPEECH | 一致（首次运行因 `asr.py` 漏导入 `NoSpeech` 抛 NameError，已修复） |
| N3 bad-base64 | 非法 Base64 | INVALID_PAYLOAD | 一致 |
| N4 length-mismatch | 区间长度与 PCM 字节数不符 | INVALID_PAYLOAD | 一致 |
| N5 model-missing | 模型目录不存在 | MODEL_UNAVAILABLE | 一致 |
| N6 empty-text | 空文本 | INVALID_PAYLOAD | 一致 |
| N7 zero-vector | 零向量 | INVALID_PAYLOAD | 一致 |

### 2.6 M2 补充探针（纯解码 RTF + 停顿切句）

2026-11-09 追加，脚本 `experiments/scripts/s0_m2_probe.py`，数据 `s0_m2_probe.json`。
样本仍为 `s0_case_a.wav`（19.465 s）。

| 指标 | 实测值 |
|---|---|
| 模型加载（不计入 RTF） | 16108.3 ms |
| 纯解码 3 次 | 3586.9 / 3533.3 / 3478.6 ms，中位 3533.3 ms |
| **RTF（纯解码）** | **0.1815** |
| 词数 | 36 |
| 词间间隔 | 中位 0 ms，最大 750 ms，≥350 ms 仅 2 处 |

切句对比（同一段音频，同一组三个要点）：

| 切句方式 | 句数 | k1 | k2 | k3 |
|---|---:|---:|---:|---:|
| 按标点（整段 1 句） | 1 | 0.7731 | 0.8212 | 0.8520 |
| 按停顿 350 ms | 3 | 0.7136 | 0.6926 | 0.7763 |

停顿切出的三句：

1. `0–1620 ms`：考生开始作答（题面/口令语，不是作答内容）
2. `2310–10410 ms`：面对群众诉求我会先耐心倾听准确记录问题在按职责范围分类处理
3. `11160–18750 ms`：能够当场解决的立即解决需要协调的说明办理时限并及时反馈进展

三点结论（已同步写入 `docs/S0-P7_契约评审材料.md` §4）：

- **整段一句会系统性抬高分数**（+0.06～0.13），因为整句向量覆盖了全部要点；
  切句后分数下降是证据变准，不是匹配变差。
- **阈值必须绑定切句策略**：切句后 0.8 下三条全不过、0.5 下三条全过；换切句方式等于换尺子。
- **350 ms 对合成语音偏大**：s2 仍长达 8.1 s，k1/k2 依然同句。真人语料的停顿分布必须在 S2 重测。

RTF 0.1815 只能代表“本机 + 单段 + 合成音 + vosk 0.3.45”，不能外推到手机；
手机 CPU 单核性能通常弱于本机，S1 必须实测。

### 2.7 金样例复现性（3 次重跑）

2026-11-09 追加，脚本 `experiments/scripts/s0_repro_check.py`，比对结果 `s0_repro_check.json`。

| 项 | 结果 |
|---|---|
| 重跑次数 | 3 |
| 输出文件 | `experiments/results/repro/golden_run_1..3.json`，字节数均 18180 |
| 用例数 | 9 |
| 内容完全一致的用例 | **9 / 9** |
| 差异数 | 0 |
| 忽略字段 | `generated_at`、`elapsed_ms`（每次运行必然变化） |

结论：同一机器、同一 venv、`intra_op_num_threads=1` 下，M2 转写、M3 向量、M4 匹配逐用例可复现，
金样例可以作为本机回归基线。

边界：这**不是**跨端一致性证明。手机端 vosk 0.3.47、不同 CPU 浮点实现、int8 量化都可能改变数值，
S1 仍需刘慧芳在真机复跑后比对；容差若超 1e-4，按实测放宽并写偏差单。

### 2.8 M3 int8 动态量化（S1 体积/精度预研）

2026-11-09 追加，脚本 `experiments/scripts/s0_m3_quant_probe.py`，数据 `s0_m3_quant_probe.json`。
量化方式 `onnxruntime.quantization.quantize_dynamic(weight_type=QInt8)`，权重 int8、激活 fp32。

| 项 | fp32 | int8 | 变化 |
|---|---:|---:|---|
| 文件体积 | 448.48 MB | **112.63 MB** | 25.11% |
| 文件字节 | 470268510 | 118101091 | -352167419 |
| 会话加载 | 1009.1 ms | 661.4 ms | -34.5% |
| 单句推理 p50 | 9.995 ms | **3.669 ms** | 2.72× |
| 单句推理 p90 | 10.775 ms | 3.983 ms | 2.70× |
| 量化耗时 | — | 10856.1 ms | 一次性 |

精度（10 句 × 3 要点）：

| 指标 | 值 |
|---|---|
| 同句向量余弦（fp32 vs int8） | min 0.9846 / mean 0.9904 / max 0.9934 |
| 向量分量最大绝对差 | 0.0267 |
| 匹配分数最大绝对差 | **0.0594**（k2），均值 0.0176 |
| top-1 证据句一致 | 3 / 3 |
| 0.5 / 0.8 阈值翻转 | 本批样本 0 / 0 |

结论：

- **体积是主要收益**：448 MB → 113 MB，是 S1 手机 OOM 风险最直接的缓解手段；但 113 MB 仍需真机确认
  加载峰值（ORT 会把模型读入内存，瞬时占用可能接近 2×）。
- **精度代价不可忽略**：分数偏差最大 0.059，真实分数落在阈值 ±0.06 内就可能翻转判定。
  本批 10 句没有翻转，样本量不足以证明校准集也不会。
- **int8 与 fp32 数值不等价**：`contracts/examples/golden-s0.json` 的期望值只对 fp32 有效；
  S1 若采用 int8，必须单独生成期望值或写明容差，不能直接复用。
- 本机数据不代表手机：ARM CPU、ORT Android 构建、NEON 优化都会改变耗时。

---

## 3. 偏差、限制与已知风险（必须随代码一起交接）

1. **S0-P4 执行顺序与计划相反。** 计划要求“先登记期望，再跑实际”，本轮是先跑出结果再写入 golden。已写入 `provenance.note`：
   期望值由实现方生成，属于基线锁定，不是第三方独立预期。**S1 必须由刘慧芳在手机端复跑比对**，才算闭环。
2. **Vosk 中文输出不带标点。** 真实转写被 `split_sentences` 整段切成 1 句，M4 三个要点都落在同一句上。
   已实现词级时间戳（`include_words=True`，默认关闭）与按停顿切句（`pause_ms=350`），
   实测切出 3 句，但中间句仍长 8.1 s、k1/k2 同句；且切句后分数整体下降（见 §2.6）。
   该扩展字段尚未进 schema，待 S0-P7 的 C6/C7 确认。
3. **测试语音为合成音，不是真人。** 只能证明链路与格式可用，不能用于 CER 结论；S2 语料必须真人录制。
   §2.6 的停顿分布（中位 0 ms、仅 2 处 ≥350 ms）不具备代表性，不能据此定 `pause_ms`。
4. **vosk 版本差两个小版本。** 电脑端 venv 为 `vosk 0.3.45`，上游 Android 依赖 `com.alphacephei:vosk-android:0.3.47`；
   同一段音频的转写结果可能不同，S1/S3 对照必须以手机结果为准，差异写偏差单。
5. **电脑端 M2 与 Android M2 不是同一份代码。** 本轮 Python 实现用于锁定契约与期望值；S1 Kotlin 实现必须对齐字段与错误码，
   不能假设数值逐位相同。
6. **阈值 0.5 尚未校准，且与切句策略耦合。** 整段一句时 k1=0.7731（0.8 会漏）；切句后同一要点降到 0.7136。
   两者不是同一把尺子，S2 校准集必须在**最终切句策略**下采集，S2 前不得对外宣称匹配准确率。
7. **异常用例覆盖的是模块边界，不是端到端。** 真机的权限拒绝、麦克风占用、任务取消等场景尚未验证。
8. **未做性能结论。** 本轮只记录单次耗时与启动开销，不是 S2 的 P90/RTF 统计（样本量不足、设备不同）。
9. **int8 量化会改变数值。** 体积降到 fp32 的 25.11%，同句向量余弦最低 0.9846，但匹配分数最大差 0.0594；
   阈值 0.5/0.8 在边界附近可能翻转。int8 只作“体积换精度”的备选，是否采用由 S1 真机结果与 S2 校准决定。

---

## 4. 复现命令（PowerShell，venv 已就绪）

```powershell
$env:PYTHONIOENCODING="utf-8"
$py = "D:\Computation_Partitioning\SA-lab\.venv\Scripts\python.exe"
$root = "D:\Computation_Partitioning\SA-lab"

# 1) 转写
& $py "$root\experiments\scripts\s0_min_asr.py" `
  --wav "$root\experiments\samples\local\s0_case_a.wav" `
  --out "$root\experiments\results\s0_asr_a.json"

# 2) 编码 + 匹配
& $py "$root\experiments\scripts\s0_min_encode.py" `
  --out "$root\experiments\results\s0_encode.json"

# 3) 异常用例
& $py "$root\experiments\scripts\s0_negative.py" `
  --out "$root\experiments\results\s0_negative.json"

# 4) 金样例
& $py "$root\experiments\scripts\make_golden_s0.py" `
  --wav-a "$root\experiments\samples\local\s0_case_a.wav" `
  --wav-b "$root\experiments\samples\local\s0_case_b.wav" `
  --out "$root\contracts\examples\golden-s0.json"

# 5) 冷/热启动
& $py "$root\experiments\scripts\s0_startup.py" `
  --out "$root\experiments\results\s0_startup.csv"

# 6) 模块自测
& $py -m unittest discover -s "$root\server\tests" -p "test_*.py" -v

# 7) M2 补充探针（纯解码 RTF + 停顿切句）
& $py "$root\experiments\scripts\s0_m2_probe.py" `
  --out "$root\experiments\results\s0_m2_probe.json"

# 8) S2 指标统计（拿到真人记录后替换 input）
& $py "$root\experiments\scripts\compute_metrics.py" `
  --input "$root\experiments\results\s2_records.jsonl" `
  --out "$root\experiments\results\s2_summary.json"

# 9) Android tokenizer 可行性探针
& $py "$root\experiments\scripts\s0_android_tokenizer_probe.py"

# 10) 金样例复现性（3 次重跑 + 逐用例比对）
for ($i = 1; $i -le 3; $i++) {
  & $py "$root\experiments\scripts\make_golden_s0.py" `
    --wav-a "$root\experiments\samples\local\s0_case_a.wav" `
    --wav-b "$root\experiments\samples\local\s0_case_b.wav" `
    --out "$root\experiments\results\repro\golden_run_$i.json"
}
& $py "$root\experiments\scripts\s0_repro_check.py" `
  --runs "$root\experiments\results\repro\golden_run_1.json" `
         "$root\experiments\results\repro\golden_run_2.json" `
         "$root\experiments\results\repro\golden_run_3.json" `
  --out "$root\experiments\results\s0_repro_check.json"

# 11) M3 int8 动态量化探针（需 pip install onnx）
& $py "$root\experiments\scripts\s0_m3_quant_probe.py" `
  --model "$root\models\weights\minilm-multilingual\model.onnx" `
  --tokenizer "$root\models\weights\minilm-multilingual\tokenizer.json" `
  --out-model "$root\models\weights\minilm-multilingual\model_int8.onnx" `
  --out "$root\experiments\results\s0_m3_quant_probe.json"
```

前置：`models/weights/vosk-model-cn-0.22/` 与 `models/weights/minilm-multilingual/` 已按 manifest 放好；
两段 WAV 因 `.gitignore` 不入库，需由本机重新合成或向彭雯青索取（不入库是有意为之）。

---

## 5. 给组员的接口确认清单（S0-P7 评审用）

| 编号 | 需要确认的点 | 提出方 | 待确认人 |
|---|---|---|---|
| C1 | M3 返回 `{"embeddings": {...}}` 信封，M4 输入取内层 `embeddings` 对象，是否写进 schema | 彭雯青 | 林俊希 |
| C2 | `sentence_id` 采用 `s1..sn` 连续编号，是否与 M1 的 `segment_id` 需要可追溯映射 | 彭雯青 | 刘慧芳 |
| C3 | M2 `text` 保留 Vosk 空格分词原样，展示层去空格；是否在契约层规定 | 彭雯青 | 林俊希 |
| C4 | `NO_SPEECH`（M1 空段）与 `NO_TRANSCRIPT`（M2 有语音无文本）边界是否按现实现 | 彭雯青 | 林俊希 |
| C5 | 阈值与 `config_version` 的绑定方式（manifest `configs.m4_matching`） | 彭雯青 | 林俊希 |
| C6 | M2 `words` 词级时间戳是否进 schema、是否默认开启（现为可选、默认关） | 彭雯青 | 林俊希 |
| C7 | M3 `pause_ms` 是否进 manifest、`with_timing` 是否只作调试字段 | 彭雯青 | 林俊希 |

完整论证、实测数据与建议决议见 `docs/S0-P7_契约评审材料.md`。

---

## 6. 未完成项

| 项 | 状态 | 阻塞原因 |
|---|---|---|
| S0-P7 契约评审 | 材料已出，待签字 | 需三人共同确认（C1–C7） |
| S1 Kotlin（M2/M3/M4） | 未开始 | `mobile/` 无 Gradle 骨架、无 `gradlew`、无真机 |
| S1 Android 端 M3 可行性 | 已评估 + int8 实测 | 见 `docs/S1_Android端M3可行性评估.md`；tokenizer 可纯 Java 实现，fp32 448 MB / int8 113 MB，真实占用待真机 |
| S2 语料与统计 | 脚本就绪，数据未采 | `compute_metrics.py` 已写并自测；缺真人录音与两台手机 |
| S3 跨端对照 | 未开始 | 依赖 S1 |
| git 提交 | 已推送 | `feature/pwq` @ `10ab049`，作者 `Yin-pro-akf <2146555838+Yin-pro-akf@users.noreply.github.com>` |
