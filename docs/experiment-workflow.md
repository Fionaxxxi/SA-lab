# 实验配置、样本关联与节点耗时

APK 0.2.0 新增两个完整入口：节点计时面板，以及导入配置/样本清单后的登记实验。HTTP v1 不变；run-config v1 的 runtime 新增可选 mode、remote_modules 字段，新手机入口要求显式 mode，旧运行配置需用生成工具重新生成。

## 页面与计时

每个任务显示 M0–M5 的实际执行端、节点状态与耗时。远程节点同时显示 HTTP 往返、序列化和反序列化时间。网关拒绝/连接错误等计算时间未知的情况标成“调用耗时（计算时间未知）”，不伪装为纯计算时间。没有采纳计时记录的节点不显示假造的 0 ms。

同一份 ModuleMeasurement 保存到任务文件、事件和页面；取消后的 IGNORED 回包不会覆盖已采纳的计时。任务显示“到结果保存”和“到完整反馈”两个时长；后者在反馈绘制后登记 FEEDBACK_VISIBLE。完整反馈展示时长不以节点时长简单相加。导入/停止录音的准备时间纳入 M0；模型校验等准备开销仍保留在提交到终态总时长，首次本地节点可能包含模型初始化。

## 登记实验

1. 真机可用后安装新版 APK，导入同一份模型包，导出“本机及模型信息 JSON”。设备编号是本次安装持久化的 UUID；卸载/清除应用数据会变更，需重新生成配置。
2. 在电脑准备真实样本清单，沿用 experiments/samples/manifest.template.json 字段。FIXTURE 测试清单可少量且未审核；FORMAL 必须满足至少 30 条、明确有效输入分类、人工标注/复核/同意及按题目分组。工具只验证记录完整性，不代替实际人工审核。
3. 用 mobile_experiment.py prepare 从本机信息、模型 manifest 原始字节和样本清单生成运行配置；再把运行配置 JSON 与原始样本清单 JSON 导入应用。
4. 页面自动固定 LOCAL/REMOTE/MANUAL_MIXED 归属，不允许再手改执行端或参考要点。导入 WAV 默认按完整 WAV 文件 SHA256 自动找到唯一 sample_id，并自动取得 keypoints 与 effective_input。相同音频对应多个编号时，必须明确选中一个样本；选中编号但哈希不一致会拒绝。
5. 录音实验须先选登记样本，配置 source=RECORDING。sample.sha256 是登记参考音频；新录音 hash 单独记 actual_wav_sha256，不会假称与参考录音相同。有效输入分类来自预先登记，不按识别成功/失败反推。新录音本身及质量仍需人工复核。
6. 相同 run_id 一经开始不能换配置或样本清单。重复使用原配置可产生新 task_id。变更模式、冷热配置、要点数或版本请创建新 run_id。

run.input.duration_s=0 表示变长负载；正值表示标称时长，允许 250 ms 操作偏差，实际 audio_samples 始终保留。超出范围的已绑定任务记 FAILED/INVALID_PAYLOAD，保留登记分类。不同要点数可共用同一份完整样本清单，通过 --keypoint-count 为每个 run 选择负载，选择的样本须与配置一致。

设备/模型/配置/APK 版本及原始清单哈希会自动核对；网络、冷/热和缓存字段是实验计划，正式操作仍需按清单确认。设备信息里的电量/温度是导出时读数，未宣称全程连续采样。配置不完整、哈希不匹配等在正式任务创建前拒绝，显示原因，不伪造执行记录。

普通模式自动产生独立的未登记 sample_id，effective_input=null，明确显示未分类；不能作为已登记正式样本混入。

## 电脑命令

在仓库根目录执行：

    python -m experiments.scripts.mobile_experiment prepare --device-info device-info.json --models models --samples samples.json --run-id phoneA-local-cold-001 --mode LOCAL --source IMPORT --condition FIXTURE --warmup COLD --duration-s 10 --output run.json

正式数据准备好后才选择 --condition FORMAL。清单含不同数量要点时添加 --keypoint-count 3（或实际负载数）。使用模型包中的 manifest 原始文件，避免仅因重新排版改变其 SHA256。输出文件独占创建，不覆盖已有配置。

## 导出与统计

“导出完整实验记录 ZIP”包含 events.jsonl、导入配置原始字节、样本清单原始字节与冻结计划。默认不包含 WAV。单独 JSONL 导出入口仍保留。

    python -m experiments.scripts.mobile_experiment validate experiment-records.zip --output association-check.json

    python experiments/scripts/compute_metrics.py events.jsonl --output baseline.csv --plot

validate 会核对 SHA256、run_id、sample_id、分类、执行归属和原始清单。失败、取消、中断仍在有效输入分母中，预分类无效输入排除。FEEDBACK_VISIBLE 才进入完整反馈时延。引用完整性通过不等于实际人声、设备或签字真实性已获证明。

## 本机验证范围

JVM 使用与 Android 相同的 application/transport 代码构建并执行。三模式各含成功、失败、取消、重启中断、无效输入，导出 72 条关联事件后由独立 Python 工具校验；保存与读取后的计时/实验字段逐项一致。另跑真实 HTTP 回环，客户端字节和网关记录一致。算法为明确标记的 fixture，不是手机或真实模型性能结果。Android 编译和签名验证另附实际日志；真机布局、录音及绘制时间仍待设备操作复核。
