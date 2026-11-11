# S2 计量与 S4 成本输入

每份正式运行配置用 `run-config.schema.json` 校验，唯一 `run_id` 对应一套设备、网络、输入及版本条件。每组计划、录音与导入、冷与热启动分别记录。JVM 联调与记账样例的运行配置在 `ljx-fixture-runs.json`，正式采集按一配置一 run。标准负载及目标在 `measurement-v1.json`。数值为小组的先验目标，当前没有两台手机的实测结论。

| 字段 | 单位和来源 |
| --- | --- |
| `run_id, device_id, task_id, attempt, sample_id, input_source, mode` | 客户端。关联运行配置、样本、任务与实际尝试。 |
| `plan_version, model_version, config_version, event_schema_version` | 客户端。任务建立时固定，配合 run 配置的 APK / 服务提交和模型清单哈希复现。 |
| `event, module_id, executor, status, error_code` | 客户端。M0/M5 始终 LOCAL。MODULE_END 可为 OK、ERROR、IGNORED。TASK_TERMINAL 保留 FAILED、CANCELLED、INTERRUPTED。 |
| `effective_input, audio_samples` | 预先分类的有效输入标记，PCM 样本数。未知记 null，正式统计前核对样本表。 |
| `elapsed_ms, module_time_known` | MODULE_END 用单调时钟，远程成功使用服务器模块持续时间，网关拒绝和远程故障的耗时不当作纯执行。TASK_TERMINAL 用提交到终态保存，重启中断记 null。FEEDBACK_VISIBLE 用提交到完整反馈，M5 的 MODULE_END 计终态保存。 |
| `round_trip_ms, serialize_ms, deserialize_ms` | 手机单调时钟。往返从 HTTP 调用前到读完正文，序列化和反序列化单列。未发生记 null。 |
| `bytes_up, bytes_down` | 客户端观测的 HTTP JSON 正文 UTF-8 字节，含 Base64。成功传输逐笔核对，失败上传记录交给写入缓冲的字节、下载记录已读取的字节。包头、重传和加密开销需另测。 |

以 run/device/task 去重计算任务完成率，失败、取消、中断进入有效输入分母，静音和无效输入单列。相同身份的重复终态只算一次，有冲突须先审查证据。成功任务的 `FEEDBACK_VISIBLE` 才进入时延分位数，注明有效反馈时延样本量。成功但缺展示事件留作缺测，不用保存耗时代替。RTF 使用成功任务提交到分析结果保存的持续时间除以 `audio_samples/16000`。CER、覆盖率和证据准确性用人工标注计算，阈值在校准集确定。吞吐量用无人工等待的连续顺序运行窗口计算。温度、电量、充电、省电、网络条件与模型预热写入 run 配置或旁路设备轨迹。

## 给 S4 的原始列

| 记录 | 列 | 归属和单位 |
| --- | --- | --- |
| 节点 | `run_id, task_id, attempt, sample_id, device_id, module_id, executor, status, elapsed_ms, module_time_known` | 对相同输入分别实测本地和远程纯计算，毫秒。加载、排队和失败单列。 |
| 远程调用 | `module_id, bytes_up, bytes_down, round_trip_ms, serialize_ms, deserialize_ms` | 每次调用记录正文字节和持续时间。往返减服务器执行仅作综合开销代理，无法拆出单向时延。 |
| 数据边 | `from_module, to_module, artifact_type, producer_download_bytes, consumer_upload_bytes, network_profile_id, overhead_owner` | S4 由相邻模块和真实 HTTP 正文追溯。连续远程仍由手机中转，分别登记前节点回传和后节点重传。题目元数据等附加载荷显式归属，避免重复记账。 |

彭雯青的统计脚本和两机原始日志尚未取得。以上为待对列的 v1 字段，S2-T2 应由统计脚本导入同一组成功、失败、取消和重复样例后签收。
