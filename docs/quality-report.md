# 覆盖一致率、逐观测 CER 和质量报告

本工具已实现覆盖标签一致率、逐样本明细/分布图和质量报告自动生成。输入必须包含人工参考转写、人工覆盖标签与实际模型输出；工具不自行制造金标准，不从执行日志猜测转写全文或人工判断。

## 一次生成

在仓库根目录，使用已安装 requirements-team.lock 的 Python 3.11.9：

    python -m experiments.scripts.quality_metrics experiments/samples/local/quality-review.json --output experiments/results/quality-local/evaluation-001 --split evaluation

只输出 JSON 汇总可省略 --output，保留原有命令用法。输出目录须为新目录，防止不同运行的结果或旧图混入。不需要重编译 APK 或连接手机。

可先用已登记的数学测试例复跑：

    python -m experiments.scripts.quality_metrics contracts/examples/quality-fixture-v1.json --output experiments/results/quality-local/fixture-001

该示例是 FIXTURE：构造的文字、标签与故意错误，不是模型在真实录音上的质量。预期整体 CER=5/7、逐观测均值=0.875、TP/TN/FP/FN=2/1/1/2、覆盖一致率=0.5、证据命中率=2/3。独立复算与自动测试均保留。

## 输入

字段模板见 experiments/samples/quality-review.template.json；机器校验定义见 quality-review.schema.json。模板有空值，须填写实际数据后才可运行，不是已完成的标注。

顶层为 schema_version=1、condition 和 records。condition 使用：

- FIXTURE：测试数据，报告与图明确标注，不作为真实录音结论。
- UNREVIEWED：数据可计算，但审核信息尚不完整。
- REVIEWED：已登记审核人员、同意、原始音频哈希、任务与版本信息。工具验证字段完整性，不能证明人员实际参与，也不会自动签收阶段。

原有 JSON 数组输入仍可计算，默认 UNREVIEWED。旧数组缺编号时只生成 legacy-row 序号供引用，不冒充真实 sample_id。不能用 CLI 把已有 FIXTURE 信封改标签。

每条观测包括：

- sample_id；登记数据带 run_id/device_id/task_id、topic_id、split、model_version/config_version、mode、input_source、effective_input。REVIEWED 还须 audio_sha256、annotator、reviewer、consent=true，标注和复核人员应不同。
- reference_text 是人工逐字稿；actual_text 是实际模型转写，真实无转写时填空字符串，不能删掉这些失败记录。
- matches 每项带 keypoint_id、expected_covered（人工标签）和 actual_covered（实际判断）。actual_covered=null 表示没有返回预测，不擅自填 false。
- 返回已覆盖时，actual_evidence_sentence_id 可为真实句子编号或 null；accepted_evidence_sentence_ids 必须是人工审核的接受集合。空集合表示没有可接受证据，不能直接把模型给出的句子复制为“人工正确答案”。

没有任何覆盖标签的观测可用于 CER，但报告明确列出缺少标注的数量，不能从中推导覆盖质量。

## 计算口径

| 指标 | 计算 |
| --- | --- |
| 覆盖标签一致率 | (TP+TN)/(TP+TN+FP+FN)，包含正确未覆盖 TN。 |
| 全标注要点正确率 | (TP+TN)/全部已标注要点；没有返回预测的项不给正确分。 |
| 预测可用率 | 有返回预测的要点 / 全部已标注要点；缺测单列。 |
| Precision / Recall / F1 | 基于有返回预测的混淆计数；不能替代全任务完成率。 |
| 整体 CER | 归一化字符编辑距离总和 / 参考字符总和，按字数加权。 |
| 逐观测 CER | 每次实际输出单列；另给均值、P50/P90/P99 和分布，不把均值当成整体 CER。 |
| 证据命中率 | 返回已覆盖的项中，真实 evidence id 落入人工接受集合的比例。 |

去除空白与 Unicode 标点，不改大小写与数字。空实际转写计入错误；CER 可超过 100%，不截断。有效参考转写归一化后为空会拒绝。任何指标分母为零显示 N/A/JSON null。

预分类 effective_input=false 的记录保留在明细但排除质量指标。未分类记录按可计算输入做描述性统计并单列，未补造分类。完全重复的已标识观测去重；同一个任务/样本身份的冲突输出拒绝，须先选择最终采纳的记录。

不同运行、设备、模型、配置、模式、输入来源和划分分别出组表。同题跨校准集与评价集会拒绝，即使本次只筛 evaluation。整体混合组数值只作描述性汇总。重复运行同一音频不冒充新的独立音频，样本编号数和已知不同音频哈希数分别列出。

默认 CER 对照目标为 0.2，来自 measurement-v1。可用 --cer-target、--coverage-target、--evidence-target 指定数值对照；覆盖和证据目标默认未设置，不擅自用模型的相似度阈值代替质量目标。目标对照不自动判定 S2 验收通过。

## 产物

- quality_summary.json：统计、分母、分组、限制、输入和工具源码哈希。
- per_sample.csv：逐观测 CER、覆盖计数、原始来源行、任务身份、未纳入原因及参考/实际文本。
- per_keypoint.csv：逐要点人工与模型标签、是否一致、证据接受集合及命中结果；无要点时仍有明确空表头。
- group_metrics.csv：每组独立统计。
- cer_distribution.png：逐观测柱图和分布图，横轴索引与明细对应，缺测不当作 0。
- coverage_confusion.png：TP/TN/FP/FN 与缺测数量。
- quality_report.md：数据说明、目标对照、分组、逐条结果、最差样本与排查建议，包含未达目标项。
- review_input.json：原始输入字节，方便复核文本和审核字段；输入 SHA256 与报告核对。
- artifact_sha256.json：生成文件逐个校验值。

CSV 文本按文本方式供表格软件查看；原始输入以 JSON 为准。报告会保留提供的转写和审核数据，真实材料建议存放在已忽略的 samples/local 与 results/quality-local 目录。

## 仍需实际工作

工具和测试数据不能代替至少 30 段真实录音、人工标注/复核、校准与独立评价、两机验证及签收。真实材料提供后可直接用同一工具生成质量报告，不需要再补写这些统计功能。
