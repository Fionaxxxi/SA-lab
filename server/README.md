# 局域网网关启动

在仓库根目录用 Python 3.11.9 创建 venv。在 Windows PowerShell 中执行：

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe --version
.\.venv\Scripts\python.exe -m pip install -r requirements-gateway.lock
.\.venv\Scripts\python.exe -m unittest discover -s server/tests -v
$env:SA_GATEWAY_TOKEN = [guid]::NewGuid().ToString('N')
$env:SA_DEMO = '1'
.\.venv\Scripts\python.exe -m uvicorn server.app:create --factory --host 127.0.0.1 --port 8000 --workers 1 --ws none --no-access-log
```

`py -3.11` 若指向别的补丁版本，改用 Python 3.11.9 的完整解释器路径执行 `-m venv`。本次验证使用本地 venv 代替 Conda。仓库已有 `environment.yml` 可用于建立 Conda 环境，再在环境内安装同一网关锁文件。网关锁包含测试依赖。模型环境可另行安装 `requirements-models-candidate.lock`。该文件在 Windows Python 3.11.9 已验证 NumPy 1.26.4、Vosk 0.3.45 和 ONNX Runtime 1.20.1 可导入，ONNX Runtime 提供 CPUExecutionProvider。真实模型、分词器及 Android 对照后再定稿。

另一 PowerShell 窗口执行探活：

```powershell
Invoke-RestMethod http://127.0.0.1:8000/healthz
```

在有 `SA_GATEWAY_TOKEN` 的窗口可将固定请求送到服务：

```powershell
$case = (Get-Content -Raw -Encoding UTF8 contracts/examples/ljx-http-cases.json | ConvertFrom-Json).cases[0]
Invoke-RestMethod -Uri http://127.0.0.1:8000/api/v1/modules/M4/execute -Method Post `
  -Headers @{ Authorization = "Bearer $env:SA_GATEWAY_TOKEN" } -ContentType 'application/json' `
  -Body ([Text.Encoding]::UTF8.GetBytes(($case.request | ConvertTo-Json -Depth 30 -Compress)))
```

真实模式移除 `SA_DEMO`，设置 `SA_MODULE_FACTORY=server.modules.integration:create_handlers`，以及与手机一致的 `SA_MODEL_VERSION`、`SA_CONFIG_VERSION` 和 `SA_VECTOR_DIMENSION`。示例 factory 名是接入点，由算法联调时提供。它返回 `dict[str, Callable[[dict], dict]]`，键限 M1–M4，每个函数接收协议的 payload 并返回 output，业务失败用 `ProtocolError(code, message)`。加载模型、阈值和规则后才登记该模块，无法加载的模块可省略，health 会显示不可用。适配器可能在不同手机请求中并发运行，持有的资源应支持此并发或由适配器串行化。

用受控局域网的指定网卡地址替换 127.0.0.1 后，手机使用同一地址、端口和临时 Bearer 凭据。网关单进程运行，固定响应只开启在明确的 demo 模式。正式采集关闭 demo，按真实样例确认四个模块可用再记录。成功、拒绝和设备失败的判定见 [HTTP v1 错误表](../contracts/errors.md)。
