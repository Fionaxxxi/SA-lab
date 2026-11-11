# HTTP v1 错误与边界

| HTTP | 错误码 | 触发条件 |
| --- | --- | --- |
| 400 | INVALID_PAYLOAD | UTF-8 JSON、必填字段、路由与体、PCM/区间或向量非法。 |
| 401 | UNAUTHORIZED | Bearer 凭据缺失或无效。 |
| 404 | UNKNOWN_MODULE | 路径模块不在 M1–M4 白名单。 |
| 409 | VERSION_MISMATCH | 协议、模型或配置不匹配。 |
| 409 | IN_PROGRESS | 同去重键、同内容仍在执行。 |
| 409 | REQUEST_CONFLICT | 同去重键、不同内容。 |
| 413 | PAYLOAD_TOO_LARGE | HTTP 正文超过 4 MiB。 |
| 422 | NO_SPEECH / NO_TRANSCRIPT | 模块报告静音或语音无转写。 |
| 500 | INTERNAL_ERROR | 未归类的处理故障。 |
| 503 | MODEL_UNAVAILABLE / BUSY | 算法未登记、模型不可用或网关容量耗尽。 |
| 504 | DEADLINE_EXCEEDED | 剩余预算或服务等待上限到期。 |
| 客户端 | REMOTE_UNREACHABLE | 连接或 I/O 失败。 |

错误回显可安全解析的身份字段。无法解析、值超出当前 Schema 或授权前拒绝时字段为 null。错误输出包含 `status=ERROR`、`executor`、`elapsed_ms` 和 `error{code,message}`。客户端把过期身份结果当作版本错误处理。60 秒对应 960000 样本，采样数或区间越界归 INVALID_PAYLOAD，HTTP 体超过 4 MiB 归 PAYLOAD_TOO_LARGE。

去重键为 `task_id + attempt + plan_version + module_id`。摘要采用解析后的完整 JSON 对象，忽略对象字段次序和结构外的空白，包含 `remaining_budget_ms`。重发同一请求时保留原预算值。单进程缓存默认保留已完成响应 60 秒，最多 128 键，按每个进行中条目预留 4 MiB，累计额度 32 MiB。进行中返回 409。真实模块可能在超时后才退出，这期间键保持在途，迟到成功不会覆盖超时。缓存过期或服务重启后去重范围结束。客户端在任务内只采纳当前任务与 attempt，S3 显式失败，任务级恢复按后续阶段实现。
