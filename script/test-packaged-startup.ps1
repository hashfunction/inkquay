$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
if (-not $IsWindows -or $env:CI -ne 'true') { throw 'Requires an isolated Windows CI runner.' }
Set-Location (Resolve-Path (Join-Path $PSScriptRoot '..'))
$executable = (Resolve-Path 'build/dist/bin/Scriblark.exe').Path
$inventoryPath = (Resolve-Path 'build-evidence/package-inventory.json').Path
$inventoryHash = (Get-FileHash $inventoryPath -Algorithm SHA256).Hash.ToLowerInvariant()
$inventory = Get-Content -LiteralPath $inventoryPath -Raw | ConvertFrom-Json
$executableHash = (Get-FileHash $executable -Algorithm SHA256).Hash.ToLowerInvariant()
if ($inventory.sourceCommit -cne $env:GITHUB_SHA -or $inventory.files.'bin/Scriblark.exe'.sha256 -cne $executableHash) {
  throw 'Same-run package inventory does not bind the source and executable.'
}
$env:APPDATA = Join-Path (Get-Location).Path 'build-evidence/runtime-profile'
$env:LOCALAPPDATA = $env:APPDATA
$env:LANG = 'C'
$env:LANGUAGE = 'C'
New-Item -ItemType Directory -Force $env:APPDATA | Out-Null
$env:Path = "$env:SystemRoot\System32;$env:SystemRoot"
# A runner's build environment must not provide the missing product config.
Remove-Item Env:FONTCONFIG_FILE, Env:FONTCONFIG_PATH -ErrorAction SilentlyContinue
$process = Start-Process $executable -PassThru -RedirectStandardOutput 'build-evidence/startup-output.txt' -RedirectStandardError 'build-evidence/startup-error.txt'
try {
  $deadline = (Get-Date).AddSeconds(45)
  do {
    Start-Sleep -Milliseconds 500
    $process.Refresh()
    if ($process.HasExited) { throw "Scriblark exited during startup: $($process.ExitCode)" }
  } until ($process.MainWindowHandle -ne 0 -or (Get-Date) -gt $deadline)
  if ($process.MainWindowHandle -eq 0 -or $process.MainWindowTitle -cne 'Unsaved Document - Scriblark') {
    throw "Expected the native Scriblark main window, got: $($process.MainWindowTitle)"
  }
  Start-Sleep -Seconds 3
  $process.Refresh()
  if ($process.HasExited -or $process.MainWindowTitle -cne 'Unsaved Document - Scriblark') { throw 'Scriblark did not retain its actual empty-document window.' }
  if ((Get-Content 'build-evidence/startup-error.txt' -Raw) -match 'Fontconfig error:') { throw 'The staged app reported a Fontconfig configuration error.' }
  if ((Get-FileHash $inventoryPath -Algorithm SHA256).Hash.ToLowerInvariant() -cne $inventoryHash -or
      (Get-FileHash $executable -Algorithm SHA256).Hash.ToLowerInvariant() -cne $executableHash) {
    throw 'Startup inputs changed while observing the actual process.'
  }
  @{ package_inventory_sha256=$inventoryHash; source_commit=$env:GITHUB_SHA; generated_at_utc=[DateTime]::UtcNow.ToString('o'); windows_native_startup=$true; window_title=$process.MainWindowTitle; executable_sha256=(Get-FileHash $executable -Algorithm SHA256).Hash; interactive_pdf_workflows_verified=$false; physical_tablet_tested=$false; native_source_clearance=$false; msix_built=$false; submitted=$false } | ConvertTo-Json | Set-Content build-evidence/windows-startup.json -Encoding utf8NoBOM
} finally {
  if (-not $process.HasExited) {
    $process.CloseMainWindow() | Out-Null
    if (-not $process.WaitForExit(5000)) { $process.Kill() }
  }
  Get-Content build-evidence/startup-error.txt
}
