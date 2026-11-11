# 模块契约

`module-request.schema.json`、`module-result.schema.json` 和 `execution-plan.schema.json` 是 HTTP v1 候选契约。用 `python -m unittest discover -s server/tests -v` 复跑示例。网关额外验证 PCM 字节、区间、模型/配置版本、向量长度与归一化等跨字段约束。

- `GET /healthz` 显示服务/协议版本、demo 标记、模型/配置版本与模块可用性。
- `POST /api/v1/modules/{M1..M4}/execute` 使用 UTF-8 JSON 和 Bearer token。请求体上限 4 MiB，PCM 最长 60 秒。每次仅执行一个模块。
- 成功回显 schema、任务、attempt、模块、计划、模型及配置身份，另有 `status/executor/elapsed_ms/output`。客户端验证全身份再采纳。
- `full_text` 将非空段文本去首尾空白后以 LF（`\n`）连接，段列表保留空段和原始采样坐标。
- `plan_version` 由客户端确定。候选协议的 `MANUAL_MIXED` 明确表示 M1–M4 同时包含 LOCAL、REMOTE；M0/M5 固定 LOCAL。成本版本在 S3 手动计划中为 null。
- 二维固定响应只用于协议验证。正式接入按模型清单确定维度、分词、池化和匹配阈值。

固定用例在 `examples/ljx-http-cases.json`，其中输入哈希取成功请求的排序键 UTF-8 紧凑 JSON。执行计划样例在 `examples/ljx-execution-plans.json`。错误与缓存说明见 [errors.md](errors.md)，评审状态见 [S0 契约评审记录](../docs/contract-review-s0.md)。
