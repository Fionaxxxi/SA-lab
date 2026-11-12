# 0003 分词采用 SentencePiece JNI 而非纯 Java 复现

- 状态：已采纳（S1 实现）
- 日期：2026-11-12

## 背景

M3 使用的 MiniLM multilingual 模型要求输入与训练时一致的 token id。该模型的 tokenizer 是 SentencePiece Unigram（vocab 250002，`unk_id=3`），带 `Precompiled` normalizer 与 `Metaspace` 预切分。手机端没有 `tokenizers` 这个 Python 库，必须另选实现路径：

- 路径 A：用纯 Kotlin/Java 复现 Unigram 切分与 normalizer；
- 路径 B：用 JNI 直接调用 SentencePiece C++，加载同一份 `.model` 文件。

## 决策

采用路径 B。`cpp/tokenizer.cpp` 用 `SentencePieceProcessor::Load` 载入模型，`Encode` 输出 token id；`SentencePiece.kt` 通过 `System.loadLibrary("interview_tokenizer")` 调用；`RealModules` 把 id 映射为模型输入（`if (id == 0) 3 else id + 1`，再补 `<s> / </s>`）。

## 依据

对同一批 7 句中文（含全角标点与全角数字）做逐 token 对比：

| 对照 | 结果 |
|---|---|
| SentencePiece C++（Python 绑定）vs HuggingFace `tokenizers` | **7/7 逐位一致** |
| HuggingFace 原始配置 vs 剥掉 normalizer 后 | **5/7 一致**，2 个失败样本均为全角字符（全角逗号 id 4 → 3、全角数字 `[387,2357,470]` → `[6,3,470]`） |

结论：JNI 路径与训练侧完全等价；纯 Java 路径的难点不在 Unigram 切分，而在 `Precompiled` charsmap（全角/兼容字符归一化表），漏掉它会把全角标点和全角数字打成 `unk`。

## 后果

- 分词结果与 Python 端、HuggingFace 端可逐位对齐，跨端相似度对照时不会把"分词差异"误判成"模型差异"。
- 代价是构建依赖变重：`mobile/app/build.gradle.kts` 声明 `ndkVersion = "26.1.10909125"` 与 `cmake version = "3.22.1"`，缺少 NDK 或 CMake 时无法构建 APK。这是当前复跑的门槛之一。
- 模型文件需随应用打包，`models/prepare_models.py` 负责下载与校验。

## 备选与未采纳理由

| 备选 | 未采纳理由 |
|---|---|
| 纯 Java 实现 Unigram | 切分逻辑可实现，但 `Precompiled` charsmap 需要移植并覆盖全角、兼容汉字、控制字符等规则；实测已证明漏掉它会造成 token 不一致 |
| 纯 Java + 手写全角映射表 | 只能覆盖已枚举的字符，无法保证与训练侧一致；适合作为"没有 NDK 时的降级方案"，不适合作为主路径 |
| 换用 `tokenizer.json` 的纯 JVM 实现 | 当前 Android 依赖里没有等价库；自建解析器等于重写一遍路径 A |

## 复核方式

`experiments/results/tokenizer_structure.txt` 记录 tokenizer 结构；`experiments/scripts/s0_android_tokenizer_probe.py` 复现上述 7 句对比；`cpp/tokenizer.cpp` 与 `SentencePiece.kt` 为实际调用点。
