# 真实样本采集

manifest.template.json 是待填写结构，仅有占位字段，不是已采集数据。复制至少 30 条并替换所有 TODO。每段必须有真实 WAV、实际 SHA256、逐字稿、标注者、独立复核者和实际同意记录；禁止填写未参与人员的姓名。音频为 16 kHz、单声道、16 位 PCM，最长 60 秒。同一 topic_id 只能分到 calibration 或 evaluation 其中一组。阈值只用 calibration 确定。

手机导出 WAV 到 samples/local/。逐字稿和 keypoints.expected_covered 由人填写；evidence 接受集合须基于实际输出句子逐条复核。运行 python experiments/scripts/check_samples.py experiments/samples/manifest.json 验证格式，不能用格式通过替代人工复核。APK 0.2.0 的登记实验会从导入配置和清单自动写入 run_id、sample_id、effective_input、清单哈希与题目分组；导入 WAV 按完整文件哈希匹配。普通模式使用独立的未登记编号，分类为 null，不作为已登记有效输入混算。操作见 docs/experiment-workflow.md。

quality_metrics.py 的审核输入另外包含 actual_text，以及每项匹配的 expected_covered、actual_covered、actual_evidence_sentence_id、accepted_evidence_sentence_ids。它只计算审核数据，不自动生成金标准。合成语音与 fixture 不纳入 30 段真实样本。

覆盖一致率、逐观测 CER 图与质量报告已经实现。审核输入模板是 quality-review.template.json，机器校验定义为 quality-review.schema.json。命令与统计口径见 docs/quality-report.md；原质量脚本的汇总模式仍保留。
