# 模型取得与清单

执行 `python models/prepare_models.py --semantic-revision <40位SHA> --silero-revision <40位SHA>`。SHA 分别来自官方 sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2 和 snakers4/silero-vad。脚本要求不可变提交，用实际文件计算完整 SHA256，下载或校验失败时保留失败状态。

模型配置采用 384 维、128 token、mean pooling 和 L2 归一化。长句每 126 个内容 token 加特殊 token 编码，再按内容 token 数加权汇总和归一化。Android 通过 SentencePiece 0.2.0 JNI 与 Python SentencePiece 0.2.0 对齐，XLM-R 的未知 token 映射为 3，其他 SentencePiece token 加 1，BOS=0、EOS=2。首次真模型运行须对齐 token IDs、张量和数值，才可形成金样例。

当前 `models/manifest.json` 是本地 `rules-v2` 候选，匹配阈值 0.54；仍须用按题目划分的校准集确定并版本化，评价集用于独立报告质量。25 个原始权重未修改，因此 `feature/lhf` 不上传权重或包含它们的模型 ZIP。取得原有权重并放入 `models/weights/` 后，可用项目 Conda 环境运行 `python models/package_models.py --verify-only` 逐项核对清单 SHA256，再运行 `python models/package_models.py --output models/android-models.zip` 生成与当前清单配套的手机包。打包程序不会下载或修改权重；若清单与文件不符会拒绝打包。新生成 ZIP 的原始 SHA256 与此前本机 `outputs/android-models-rules-v2.zip` 可以不同，手机正式运行配置须绑定**实际导入**的 ZIP 清单字节。


固定源码版本：MiniLM e8f8c211226b894fcb81acc59f3b34ba3efd5f42，Silero 066409f3d9db45a30d21dfcbf9147826ffdd7052。脚本还校验当前固定的 ONNX SHA256。自定义 Vosk 镜像使用 --vosk-archive、--vosk-source、--vosk-sha256 显式登记；解压后将单一根目录规范为 weights/vosk-model-cn-0.22，并为全部文件分别计算哈希。正式模型包只收录 manifest 和运行文件，排除源归档及分块。
