# 模型取得与清单

执行 `python models/prepare_models.py --semantic-revision <40位SHA> --silero-revision <40位SHA>`。SHA 分别来自官方 sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2 和 snakers4/silero-vad。脚本要求不可变提交，用实际文件计算完整 SHA256，下载或校验失败时保留失败状态。

模型配置采用 384 维、128 token、mean pooling 和 L2 归一化。长句每 126 个内容 token 加特殊 token 编码，再按内容 token 数加权汇总和归一化。Android 通过 SentencePiece 0.2.0 JNI 与 Python SentencePiece 0.2.0 对齐，XLM-R 的未知 token 映射为 3，其他 SentencePiece token 加 1，BOS=0、EOS=2。首次真模型运行须对齐 token IDs、张量和数值，才可形成金样例。

匹配阈值 0.8 是待校准配置，须用按题目划分的校准集确定并版本化，评价集用于独立报告质量。模型权重及生成的包不纳入 Git。
