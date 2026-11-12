param(
    [Parameter(Mandatory=$true)][string]$KotlinJars,
    [string]$Java='java', [string]$Python='python',
    [string]$Evidence='.evidence/experiment-wiring'
)
$ErrorActionPreference='Stop'
$project=(Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$jars=(Resolve-Path $KotlinJars).Path
$evidencePath=$ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($Evidence)
New-Item -ItemType Directory -Force -Path $evidencePath | Out-Null
if (Test-Path (Join-Path $evidencePath 'events.jsonl')) { throw 'Use fresh evidence directory' }
$runtime=@('kotlin-stdlib-1.9.22.jar','okhttp-4.12.0.jar','okio-jvm-3.6.0.jar','json-20240303.jar','annotations-13.0.jar') |
    ForEach-Object { (Resolve-Path (Join-Path $jars $_)).Path }
$classpath=$runtime -join [IO.Path]::PathSeparator
$source=@('application','transport') | ForEach-Object {
    Get-ChildItem -LiteralPath (Join-Path $project ('mobile/app/src/main/java/com/example/interviewfeedback/'+$_)) -Filter '*.kt' |
        Select-Object -ExpandProperty FullName
}
$source += Join-Path $project 'mobile/app/src/main/java/com/example/interviewfeedback/capture/WavPcmIO.kt'
$source += Join-Path $project 'mobile/app/src/test/java/com/example/interviewfeedback/experiment/ExperimentSmoke.kt'
$jar=Join-Path $evidencePath 'experiment-smoke.jar'
& $Java -cp (Join-Path $jars '*') org.jetbrains.kotlin.cli.jvm.K2JVMCompiler -no-stdlib -no-reflect -jvm-target 17 -classpath $classpath -d $jar $source
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Push-Location -LiteralPath $project
try {
    & $Python -c 'from server.tests.test_mobile_experiment import write_fixture_assets; import sys; write_fixture_assets(sys.argv[1])' $evidencePath
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    & $Java -cp ($jar+[IO.Path]::PathSeparator+$classpath) com.example.interviewfeedback.experiment.ExperimentSmokeKt $evidencePath
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    & $Python -m experiments.scripts.mobile_experiment validate (Join-Path $evidencePath 'experiment-records.zip') --output (Join-Path $evidencePath 'association-check.json')
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
} finally { Pop-Location }
