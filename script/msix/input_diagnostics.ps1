# Copyright 2026 Trieflow LLC. MIT. Metadata only; never input or acceptance.
function Get-InkInputDiagnosticLaunch([bool]$Requested,[string]$OwnedTemporary) {
    if(-not $Requested){return $null}
    if(-not [IO.Path]::IsPathFullyQualified($OwnedTemporary) -or $OwnedTemporary -match '["\r\n\x00]' -or
        [IO.Path]::GetFileName($OwnedTemporary) -cnotmatch '^\.inkquay-install-[0-9a-f]{32}$') {throw 'Invalid owned input diagnostic directory'}
    Assert-NoReparsePath $OwnedTemporary
    if(-not (Get-Item -LiteralPath $OwnedTemporary -Force).PSIsContainer){throw 'Input diagnostic parent is not a directory'}
    $path=Join-Path (Get-CanonicalPath $OwnedTemporary) 'input-diagnostics.jsonl'
    if(Test-Path -LiteralPath $path){throw 'Input diagnostic output already exists; preserving it'}
    return @{path=$path;arguments=('--input-diagnostics "'+$path+'"')}
}
function Save-InkInputDiagnostics($State) {
    if(-not $State.inputDiagnosticsRequested -or -not $State.inputDiagnosticsPath){return}
    $expected=Join-Path $State.temporary 'input-diagnostics.jsonl'
    if(-not $State.processOwned -or $State.brokerProcessId -le 0 -or $State.inputDiagnosticsPath -cne $expected){throw 'Input diagnostic process/path ownership is unavailable'}
    Assert-NoReparsePath $expected
    $item=Get-Item -LiteralPath $expected -Force
    if($item.PSIsContainer -or $item.Length -le 0 -or $item.Length -gt 1048576){throw 'Input diagnostic file exceeds its bound'}
    $inputStream=[IO.File]::Open($expected,[IO.FileMode]::Open,[IO.FileAccess]::Read,[IO.FileShare]::Read)
    try {
        $buffer=[byte[]]::new(1048577);$length=0
        do {$read=$inputStream.Read($buffer,$length,$buffer.Length-$length);$length+=$read}while($read -gt 0 -and $length -lt $buffer.Length)
        if($length -eq 0 -or $length -gt 1048576 -or $buffer[$length-1] -ne 10){throw 'Input diagnostic bytes are oversized or incomplete'}
        $raw=[byte[]]::new($length);[Array]::Copy($buffer,$raw,$length)
    }finally{$inputStream.Dispose()}
    $text=[Text.UTF8Encoding]::new($false,$true).GetString($raw)
    $lines=$text.Substring(0,$text.Length-1).Split("`n")
    if($lines.Count -gt 512){throw 'Input diagnostic record bound exceeded'}
    $phases=@('started','attached','gtk-key','propagate-before','propagate-after','focus','grab','open-enabled','export-enabled','open-activate','export-activate','file-loaded','heartbeat','native-key','stopped','truncated')
    $types=@('focus_type','grab_type','device_grab_type','target_type','event_widget_type')
    $booleans=@('focus_sensitive','focus_in_main','focus_has_focus','grab_in_main','grab_visible','grab_mapped','grab_sensitive','device_grab_in_main','target_in_main','event_in_main','window_active','toplevel_focus','open_present','export_present','open_enabled','export_enabled','handled')
    $numbers=@('event_type','keyval','hardware_keycode','state','native_message','native_code','native_state')
    $allowed=@('schema_version','diagnostic_only','sequence','process_id','monotonic_us','phase')+$types+$booleans+$numbers
    $previous=0L;$index=0;$truncated=$false
    foreach($line in $lines) {
        $index++
        if($line.Length -gt 4096){throw 'Input diagnostic line bound exceeded'}
        $entry=$line|ConvertFrom-Json -AsHashtable
        if($entry.schema_version -ne 1 -or $entry.diagnostic_only -isnot [bool] -or -not $entry.diagnostic_only -or
            $entry.sequence -ne $index -or $entry.process_id -ne $State.brokerProcessId -or
            $entry.monotonic_us -isnot [long] -or $entry.monotonic_us -lt $previous -or $entry.phase -cnotin $phases){throw 'Input diagnostic identity/order differs'}
        $previous=$entry.monotonic_us
        foreach($key in $entry.Keys) {
            if($key -cnotin $allowed){throw 'Unexpected input diagnostic field'}
            if($key -cin $types -and ($entry[$key] -isnot [string] -or $entry[$key] -cnotmatch '^[A-Za-z0-9_]{1,80}$')){throw 'Unexpected GTK diagnostic type name'}
            if($key -cin $booleans -and $entry[$key] -isnot [bool]){throw 'Unexpected GTK diagnostic boolean'}
            if($key -cin $numbers -and ($entry[$key] -isnot [long] -or $entry[$key] -lt 0 -or $entry[$key] -gt [uint32]::MaxValue)){throw 'Unexpected GTK diagnostic numeric field'}
        }
        if($entry.Contains('keyval') -and $entry.keyval -notin @(101,69,111,79,102,70,65507,65508,65513,65514)){throw 'Unreviewed diagnostic key code'}
        if($entry.Contains('native_code') -and $entry.native_code -notin @(17,18,162,163,164,165,69,79,70)){throw 'Unreviewed native diagnostic key code'}
        if($entry.phase -ceq 'truncated') {if($index -ne $lines.Count){throw 'Records follow diagnostic truncation'};$truncated=$true}
    }
    if(($lines[0]|ConvertFrom-Json).phase -cne 'started'){throw 'Input diagnostic startup record missing'}
    $destination=Join-Path $State.output 'input-diagnostics.jsonl'
    $stream=[IO.File]::Open($destination,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None)
    try {$stream.Write($raw,0,$raw.Length)}finally{$stream.Dispose()}
    $State.inputDiagnosticsEvidence=@{file='input-diagnostics.jsonl';bytes=$raw.Length;sha256=(Get-FileHash -LiteralPath $destination).Hash.ToLowerInvariant();records=$lines.Count;truncated=$truncated;diagnostic_only=$true;process_id=$State.brokerProcessId}
}
