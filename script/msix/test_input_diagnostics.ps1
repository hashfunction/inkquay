# Copyright 2026 Trieflow LLC. MIT. Actual diagnostic routing and output boundary.
param([string]$NativeRecord)
$ErrorActionPreference='Stop';Set-StrictMode -Version Latest
. (Join-Path $PSScriptRoot 'qualify-msix-install.ps1') -LibraryOnly
. (Join-Path $PSScriptRoot 'input_diagnostics.ps1')
$temporary=if($IsWindows){[IO.Path]::GetTempPath()}else{'/private/tmp'}
$root=Join-Path $temporary ('scriblark-diag-test-'+[guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory $root | Out-Null
try {
    $owned=Join-Path $root ('.inkquay-install-'+[guid]::NewGuid().ToString('N'));New-Item -ItemType Directory $owned | Out-Null
    if($null -ne (Get-InkInputDiagnosticLaunch $false 'not a path')){throw 'Dormant mode inspected/output arguments'}
    $launch=Get-InkInputDiagnosticLaunch $true $owned
    if($launch.arguments -cne ('--input-diagnostics "'+(Join-Path $owned 'input-diagnostics.jsonl')+'"')){throw 'Broker argument differs'}
    $state=@{inputDiagnosticsRequested=$true;inputDiagnosticsPath=$launch.path;temporary=$owned;processOwned=$true;brokerProcessId=17;output=$root;inputDiagnosticsEvidence=$null;inputDiagnosticsErrors=[Collections.Generic.List[string]]::new()}
    $record=@{schema_version=1;diagnostic_only=$true;sequence=1;monotonic_us=10;process_id=17;phase='started';focus_type='none'}
    [IO.File]::WriteAllText($launch.path,(($record|ConvertTo-Json -Compress)+"`n"),[Text.UTF8Encoding]::new($false))
    Save-InkInputDiagnostics $state
    if(-not $state.inputDiagnosticsEvidence -or $state.inputDiagnosticsEvidence.records -ne 1){throw 'Actual output not captured'}
    $before=[IO.File]::ReadAllText($launch.path)
    try {Get-InkInputDiagnosticLaunch $true $owned;throw 'accepted existing output'}catch{if($_.Exception.Message -eq 'accepted existing output'){throw}}
    if([IO.File]::ReadAllText($launch.path) -cne $before){throw 'Existing output changed'}
    Remove-Item (Join-Path $root 'input-diagnostics.jsonl')
    foreach($case in @('wrong-pid','unknown-text','bad-type','missing-newline','too-large','foreign-path','unowned-process','duplicate-sequence')) {
        $candidate=@{}+$record;$state.inputDiagnosticsPath=$launch.path;$state.processOwned=$true
        switch($case){
            'wrong-pid'{$candidate.process_id=18}
            'unknown-text'{$candidate.text='private string'}
            'bad-type'{$candidate.focus_type='private path/name'}
            'foreign-path'{$state.inputDiagnosticsPath=Join-Path $root 'foreign.jsonl'}
            'unowned-process'{$state.processOwned=$false}
        }
        $raw=($candidate|ConvertTo-Json -Compress)+"`n"
        if($case -eq 'missing-newline'){$raw=$raw.TrimEnd()}
        if($case -eq 'too-large'){$raw='x'*1048577}
        if($case -eq 'duplicate-sequence'){$raw+=$raw}
        [IO.File]::WriteAllText($launch.path,$raw,[Text.UTF8Encoding]::new($false))
        $failed=$false;try{Save-InkInputDiagnostics $state}catch{$failed=$true}
        if(-not $failed -or (Test-Path (Join-Path $root 'input-diagnostics.jsonl'))){throw "Unsafe diagnostic accepted: $case"}
        Write-Output "PASS diagnostic refusal: $case"
    }
    if($NativeRecord) {
        $nativeRaw=[IO.File]::ReadAllBytes($NativeRecord)
        $first=([Text.UTF8Encoding]::new($false,$true).GetString($nativeRaw).Split("`n")[0])|ConvertFrom-Json
        $state.brokerProcessId=$first.process_id;$state.processOwned=$true;$state.inputDiagnosticsPath=$launch.path
        [IO.File]::WriteAllBytes($launch.path,$nativeRaw)
        Save-InkInputDiagnostics $state
        if($state.inputDiagnosticsEvidence.sha256 -cne (Get-FileHash -LiteralPath $NativeRecord).Hash.ToLowerInvariant()){throw 'Actual GTK writer bytes changed in production reader'}
        Write-Output "PASS actual GTK writer/production reader: $($state.inputDiagnosticsEvidence.records) records"
    }
    Write-Output 'PASS actual dormant/exclusive broker arguments and bounded owned output'
}finally{Remove-Item $root -Recurse -Force}
