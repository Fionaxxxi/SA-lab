param(
    [Parameter(Mandatory = $true)][string]$KotlinJars,
    [string]$Java = 'java',
    [string]$Python = 'python',
    [string]$Evidence = '.evidence/ljx-jvm'
)

$ErrorActionPreference = 'Stop'
$project = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$jars = (Resolve-Path $KotlinJars).Path
$runtime = @(
    'kotlin-stdlib-1.9.22.jar', 'okhttp-4.12.0.jar',
    'okio-jvm-3.6.0.jar', 'json-20240303.jar', 'annotations-13.0.jar'
) | ForEach-Object { (Resolve-Path (Join-Path $jars $_)).Path }
$evidencePath = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($Evidence)
if (Test-Path (Join-Path $evidencePath 'coordinator.jsonl')) {
    throw "Use a fresh evidence directory: $evidencePath"
}
New-Item -ItemType Directory -Force -Path $evidencePath | Out-Null
$output = Join-Path $evidencePath 'coordinator.jar'
$package = 'java/com/example/interviewfeedback'
$source = @('application', 'transport') | ForEach-Object {
    Get-ChildItem -LiteralPath (Join-Path $project "mobile/app/src/main/$package/$_") -Filter '*.kt' |
        Select-Object -ExpandProperty FullName
}
$source += Join-Path $project "mobile/app/src/test/$package/application/CoordinatorSmoke.kt"
$separator = [IO.Path]::PathSeparator
$classpath = $runtime -join $separator
& $Java -cp (Join-Path $jars '*') org.jetbrains.kotlin.cli.jvm.K2JVMCompiler -no-stdlib -no-reflect -jvm-target 17 -classpath $classpath -d $output $source
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Push-Location $project
try {
    & $Python -m server.tests.jvm_http_smoke --java $Java --classpath "$output$separator$classpath" --evidence $evidencePath
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
} finally {
    Pop-Location
}
