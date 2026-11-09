# S1 Android 端 M3 可行性评估（tokenizer / 模型体积 / 验收）

- 日期：2026-11-09
- 作者：彭雯青（202430552622）
- 状态：**评估完成，未在真机验证**
- 依据：`models/weights/minilm-multilingual/tokenizer.json` 结构 + `experiments/results/s0_android_tokenizer_probe.json`

## 1. 结论

1. **tokenizer 可以纯 Java 实现，不必引入 sentencepiece JNI。** 模型是 Unigram（vocab 250002，unk_id=3），配 Metaspace 预分词与 `<s>/<s>` 模板；这些都能用 Java 复现。
2. **normalizer 可以跳过，但必须补全角处理。** 7 个样本中 5 个在"去掉 normalizer"后 token ID 完全一致；不一致的 2 个全部由全角字符引起（全角逗号 → `[UNK]`，全角数字 → `[UNK]`）。
3. **最大风险是模型体积，本机已完成量化实测。** fp32 ONNX 为 448.48 MB；动态 int8 为 **112.63 MB**（25.11%），同句向量余弦最低 0.9846，但匹配分数最大差 **0.0594**。手机上是否 OOM 仍未实测；int8 会改变数值，必须单独重跑容差验收。

## 2. 实测证据

来源：`experiments/results/s0_android_tokenizer_probe.json`（本机实测，2026-11-09）。

| 输入 | 与带 normalizer 是否一致 | 说明 |
|---|---|---|
| `面对群众诉求我会先耐心倾听准确记录问题` | **一致**（15 token） | M2 实际输出形态，主路径安全 |
| `面对群众诉求，我会先耐心倾听。` | 不一致 | 全角"，"→`[UNK]`（id 3），正常为 id 4 |
| `面对群众诉求,我会先耐心倾听.` | 一致 | 半角标点正常 |
| `2024年招录公告` | 一致 | 半角数字正常 |
| `２０２４年招录公告` | 不一致 | 全角数字整段 → `[UNK]` |
| `Hello World` | 一致 | 大小写不被 normalizer 改写 |
| `hello world` | 一致 | 同上 |

结论：**只要输入是"纯中文词块、无标点"，跳过 precompiled_charsmap 是安全的**——这正是当前 M2 的输出形态。

## 3. Android 端实现分解

| 步骤 | 做法 | 风险 |
|---|---|---|
| 归一化 | 先用 `java.text.Normalizer` 的 NFKC，再剥离标点；中文汉字不受影响 | NFKC 与 sentencepiece charsmap 不完全等价，需以 token ID 对齐为准 |
| 预分词 | 空格切分 → 空格替换为 `▁`，句首补 `▁`（中文无空格，等价于整句一个序列） | 低 |
| Unigram Viterbi | 读 vocab + scores，按 log 概率求最优切分；未登录字符落 `unk_id=3` | 需与 Python `tokenizers` 的 tie-break 一致 |
| 特殊 token | 句首 `<s>`=0，句尾 `</s>`=2 | 低 |
| 截断 | max_length=128，保留前 127 + `</s>` | 需确认与 tokenizers 的 truncation 方向一致（默认 longest_first） |
| 池化 | attention_mask 加权 mean pooling，再 L2 归一化 | float32 累加顺序不同会带来 1e-6 级差异 |
| 推理 | ONNX Runtime Android，输入 `input_ids/attention_mask/token_type_ids` int64 | 算子支持与耗时未验证 |

vocab 250002 的内存开销估算：字符串表约 15–25 MB，scores 约 1 MB（估算，未实测），可接受。

## 4. 验收标准（S1 落地前必须过）

1. 取 20 条中文句子（含 `golden-s0.json` 中的全部文本），Android 与 Python 的 **token ID 逐位相同**；
2. 同一批句子的**向量余弦 ≥ 0.999**，或最大绝对差 ≤ 1e-3（**先测再定，不预设 1e-4**）；
3. 若 ID 不一致，先定位是归一化还是 Viterbi tie-break，不允许直接放宽容差掩盖。

## 5. 模型体积与内存（本机已量化，真机未验证）

| 项 | fp32 | int8 | 说明 |
|---|---:|---:|---|
| 文件体积 | 448.48 MB（470268510 B） | **112.63 MB（118101091 B）** | int8 = fp32 的 25.11% |
| 会话加载（本机） | 1009.1 ms | 661.4 ms | 非手机数据 |
| 单句推理 p50（本机） | 9.995 ms | 3.669 ms | 2.72× |
| 同句向量余弦 | — | min 0.9846 / mean 0.9904 | 10 句 × 384 维 |
| 匹配分数最大绝对差 | — | **0.0594** | 阈值 ±0.06 内有翻转风险 |

来源：`experiments/results/s0_m3_quant_probe.json`，量化方式 `quantize_dynamic(weight_type=QInt8)`，
sha256 `2CA385CD…`（已登记 `manifest.json`）。

- 113 MB 仍不代表一定不 OOM：ORT 会把模型读入进程内存，峰值可能接近 2×；
- 顺序建议：真机先测 fp32 峰值内存与单句耗时；若 OOM 或明显拖慢，再用 int8；
- int8 必须重跑 §4 的 20 句验收，并**单独定容差**；不能直接复用 fp32 的 `golden-s0.json` 期望值。

## 6. 回退方案

| 触发条件 | 回退 |
|---|---|
| NFKC 后仍有 token 不一致 | 实现全角→半角映射表（0xFF01–0xFF5E），逐条对齐 |
| Unigram 对齐无法收敛 | 换 BERT WordPiece 中文模型（tokenizer 更易实现），但需改 manifest、golden 与选型评审 |
| fp32 在目标机型 OOM | 改用 int8（本机已量化：113 MB，余弦 ≥0.9846），重跑容差验收 |
| 手机推理耗时不可接受 | M3 改走远程执行（M5 已有 REMOTE 分支），但会牺牲离线承诺，需架构评审 |

## 7. 待办

- [ ] 真机测 ONNX Runtime 算子支持（本模型只用 MatMul/Gather/LayerNorm/Softmax 等常规算子，预期支持）
- [ ] 真机测 fp32 峰值内存与单句耗时
- [ ] 真机对比 fp32 / int8 的峰值内存与单句耗时（本机数据见 §5，不能替代真机）
- [ ] 20 句 token ID 对齐脚本（Android 侧输出 JSON，与 Python 结果比对）
- [ ] 确认 truncation 方向与 `tokenizers` 默认一致
