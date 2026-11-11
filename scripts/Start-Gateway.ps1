param(
    [string]$Python = 'python',
    [string]$ModelRoot = (Join-Path $PSScriptRoot '../models'),
    [string]$ListenAddress = '127.0.0.1',
    [int]$Port = 8000
)
$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$resolvedModels = (Resolve-Path -LiteralPath $ModelRoot).Path
if (!(Test-Path -LiteralPath (Join-Path $resolvedModels 'manifest.json'))) { throw 'Missing manifest.json' }
$env:SA_MODEL_ROOT = $resolvedModels
$env:SA_MODULE_FACTORY = 'server.modules.integration:create_handlers'
Remove-Item Env:SA_DEMO -ErrorAction SilentlyContinue
if (!$env:SA_GATEWAY_TOKEN) { $env:SA_GATEWAY_TOKEN = [guid]::NewGuid().ToString('N') }
Write-Host "实验凭据（填写到手机）：$env:SA_GATEWAY_TOKEN"
Write-Host ('服务地址：http://{0}:{1} （手机应使用电脑局域网 IPv4 地址）' -f $ListenAddress,$Port)
Push-Location -LiteralPath $repoRoot
try { & $Python -m uvicorn server.app:create --factory --host $ListenAddress --port $Port --workers 1 --ws none --no-access-log }
finally { Pop-Location }
