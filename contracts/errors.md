# S0 错误码草案

本表是接口评审输入。S0 本机只核验固定样例和基础请求错误。S3 正式联调逐项核验完整 HTTP v1 行为。

| HTTP | 约定错误码 | 阶段 |
| --- | --- | --- |
| 400 | INVALID_PAYLOAD | S0 校验 JSON、必填字段及路径与请求体模块一致。PCM/向量的跨字段校验随 S3 联调。 |
| 401 | UNAUTHORIZED | S0 骨架核验固定响应入口的 Bearer 凭据。 |
| 404 | UNKNOWN_MODULE | S0 骨架核验模块白名单。 |
| 409 | VERSION_MISMATCH | S0 核验旧协议和演示模型/配置版本。真实版本在集成后对齐。 |
| 409 | IN_PROGRESS / REQUEST_CONFLICT | S3 去重及并发联调。 |
| 413 | PAYLOAD_TOO_LARGE | S0 骨架限制 4 MiB 请求体。 |
| 422 | NO_SPEECH / NO_TRANSCRIPT | S1 与真实模块核验，S3 确认远程映射。 |
| 503 | MODEL_UNAVAILABLE / BUSY | S0 仅返回未接真实模块的 MODEL_UNAVAILABLE。 |
| 504 | DEADLINE_EXCEEDED | S0 用剩余预算为零的固定请求验证错误信封。S3 验证实际远程执行超时。 |
| 客户端 | REMOTE_UNREACHABLE | S3 手机端联调。 |

错误含 `status=ERROR`、`executor`、`elapsed_ms` 和 `error{code,message}`，不能安全回显的身份字段置 null。
