# Copyright 2026 Trieflow LLC. MIT. Actual shared writer; generated metadata only.
$ErrorActionPreference='Stop';Set-StrictMode -Version Latest
. (Join-Path $PSScriptRoot 'qualify-msix-install.ps1') -LibraryOnly
$work=Join-Path ([IO.Path]::GetTempPath()) ('scriblark-json-writer-'+[guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $work|Out-Null
$failures=[Collections.Generic.List[string]]::new();$passed=0
try {
 foreach($count in @(0,1,2)) {
  try {
   $items=[Collections.Generic.List[object]]::new()
   for($i=0;$i -lt $count;$i++){$items.Add([ordered]@{name='Unsaved Document - Scriblark';control_type='ControlType.Window';enabled=$true;offscreen=$false;process_id=2744+$i})}
   $standalone=Join-Path $work "tree-$count.json";$embedded=Join-Path $work "window-$count.json"
   Write-NewUtf8Json $standalone @($items)
   Write-NewUtf8Json $embedded ([ordered]@{controls=@($items);nested=@{empty=@();single=@(@{active=$true;count=1});multiple=@(1,2)};observed_utc='2026-09-12T17:00:00.1234567Z'})
   $tree=[Text.Json.JsonDocument]::Parse([IO.File]::ReadAllText($standalone));$window=[Text.Json.JsonDocument]::Parse([IO.File]::ReadAllText($embedded))
   try {
    if($tree.RootElement.ValueKind -ne [Text.Json.JsonValueKind]::Array -or $tree.RootElement.GetArrayLength() -ne $count){throw 'Declared root array lost its shape'}
    $controls=$window.RootElement.GetProperty('controls')
    if($controls.ValueKind -ne [Text.Json.JsonValueKind]::Array -or $controls.GetArrayLength() -ne $count){throw 'Embedded controls lost their shape'}
    for($i=0;$i -lt $count;$i++) {
     if([Text.Json.JsonSerializer]::Serialize[Text.Json.JsonElement]($tree.RootElement[$i]) -cne [Text.Json.JsonSerializer]::Serialize[Text.Json.JsonElement]($controls[$i])){throw 'Standalone and embedded original nodes differ'}
    }
    $nested=$window.RootElement.GetProperty('nested')
    foreach($pair in @(@('empty',0),@('single',1),@('multiple',2))){$array=$nested.GetProperty($pair[0]);if($array.ValueKind -ne [Text.Json.JsonValueKind]::Array -or $array.GetArrayLength() -ne $pair[1]){throw 'Nested array shape differs'}}
    if($nested.GetProperty('single')[0].GetProperty('active').ValueKind -ne [Text.Json.JsonValueKind]::True -or
       $nested.GetProperty('single')[0].GetProperty('count').ValueKind -ne [Text.Json.JsonValueKind]::Number -or
       $window.RootElement.GetProperty('observed_utc').GetString() -cne '2026-09-12T17:00:00.1234567Z'){throw 'Nested scalar types or original timestamp changed'}
    $passed++
   } finally {$tree.Dispose();$window.Dispose()}
  } catch {$failures.Add("array count ${count}: $($_.Exception.Message)")}
 }
 $path=Join-Path $work 'existing.json';[IO.File]::WriteAllText($path,'preserve')
 $refused=$false;try{Write-NewUtf8Json $path @(@{changed=$true})}catch{$refused=$true}
 if(-not $refused -or [IO.File]::ReadAllText($path) -cne 'preserve'){$failures.Add('Existing output replaced')}else{$passed++}
 if($failures.Count){throw ($failures -join "`n")}
 "PASS: $passed actual JSON writer cases; empty/single/multiple arrays, nested typed records, exact original node equality and exclusive output."
} finally {Remove-Item -LiteralPath $work -Recurse -Force}
