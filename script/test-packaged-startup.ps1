$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
if (-not $IsWindows -or $env:CI -ne 'true') { throw 'Requires an isolated Windows CI runner.' }
Set-Location (Resolve-Path (Join-Path $PSScriptRoot '..'))
$executable = (Resolve-Path 'build/dist/bin/inkquay.exe').Path
$env:APPDATA = Join-Path (Get-Location).Path 'build-evidence/runtime-profile'
$env:LOCALAPPDATA = $env:APPDATA
New-Item -ItemType Directory -Force $env:APPDATA | Out-Null
$env:Path = "$env:SystemRoot\System32;$env:SystemRoot"
$process = Start-Process $executable -PassThru -RedirectStandardOutput 'build-evidence/startup-output.txt' -RedirectStandardError 'build-evidence/startup-error.txt'
try {
  $deadline = (Get-Date).AddSeconds(45)
  do {
    Start-Sleep -Milliseconds 500
    $process.Refresh()
    if ($process.HasExited) { throw "InkQuay exited during startup: $($process.ExitCode)" }
  } until ($process.MainWindowHandle -ne 0 -or (Get-Date) -gt $deadline)
  if ($process.MainWindowHandle -eq 0 -or $process.MainWindowTitle -notmatch 'InkQuay') {
    throw "Expected the native InkQuay main window, got: $($process.MainWindowTitle)"
  }
  Start-Sleep -Seconds 3
  $process.Refresh()
  if ($process.HasExited) { throw 'InkQuay exited after opening its main window.' }
  @{ source_commit=$env:GITHUB_SHA; generated_at_utc=[DateTime]::UtcNow.ToString('o'); windows_native_startup=$true; window_title=$process.MainWindowTitle; executable_sha256=(Get-FileHash $executable -Algorithm SHA256).Hash; interactive_pdf_workflows_verified=$false; physical_tablet_tested=$false; native_source_clearance=$false; msix_built=$false; submitted=$false } | ConvertTo-Json | Set-Content build-evidence/windows-startup.json -Encoding utf8NoBOM
} finally {
  if (-not $process.HasExited) {
    $process.CloseMainWindow() | Out-Null
    if (-not $process.WaitForExit(5000)) { $process.Kill() }
  }
  Get-Content build-evidence/startup-error.txt
}
