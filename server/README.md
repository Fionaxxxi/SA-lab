# S0 服务骨架

在仓库根目录，用 Python 3.11.9 建 venv 并启动本机服务。

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-gateway.lock
.\.venv\Scripts\python.exe -m unittest discover -s server/tests -v
$env:SA_GATEWAY_TOKEN = [guid]::NewGuid().ToString('N')
.\.venv\Scripts\python.exe -m uvicorn server.app:create --factory --host 127.0.0.1 --port 8000 --ws none
```

若 `py -3.11` 对应其他补丁版本，改用 Python 3.11.9 的完整解释器路径。项目 venv 是本机环境。网关依赖已锁，模型依赖随彭雯青提供的实际环境核对。

另一窗口调用 `Invoke-RestMethod http://127.0.0.1:8000/healthz`。探活显示真实 M1–M4 均未接入，仅 M4 有固定协议样例。运行单元测试可复跑固定响应、缺字段、错版本、零预算、无效凭据及白名单。零预算只验证错误信封，真实远程超时属 S3。
