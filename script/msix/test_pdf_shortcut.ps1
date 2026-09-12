# Copyright 2026 Trieflow LLC. MIT. Real source contract and native shortcut plan.
$ErrorActionPreference='Stop';Set-StrictMode -Version Latest
. (Join-Path $PSScriptRoot 'qualify-workflow.ps1')
function Check($Value,$Message){if(-not $Value){throw $Message}}
$contract=Get-InkWorkflowContract (Resolve-Path (Join-Path $PSScriptRoot '../..'))
Check ($contract.pdfExportShortcut -ceq '^%e') 'The user-visible direct PDF shortcut is missing'
Add-InkWorkflowTypes
function State {
    $s=[InkQuayWorkflow.InputState]::new();$s.MainHandle=100;$s.ProcessId=17;$s.ForegroundHandle=100;$s.ForegroundProcessId=17
    $s.FocusHandle=100;$s.FocusRoot=100;$s.FocusProcessId=17;$s.ForegroundOwnerChain=@(100)
    $w=[InkQuayWorkflow.Window]::new();$w.Handle=100;$w.ProcessId=17;$w.Title='first.pdf - Scriblark';$w.ClassName='gdkWindowToplevel';$w.Visible=$true;$w.Enabled=$true;$w.Width=816;$w.Height=639;$s.Windows=@($w);return $s
}
$plan=[InkQuayWorkflow.Native]::PlanPdfExportKeys((State),'first.pdf - Scriblark')
Check ((($plan|ForEach-Object {"$($_.VirtualKey):$($_.KeyUp)"}) -join ',') -ceq '17:False,18:False,69:False,69:True,18:True,17:True') 'Direct PDF chord differs'
foreach($mutation in @('alt','control','shift','windows','popup','foreign-focus','foreign-foreground','wrong-title','disabled-main')){
    $s=State
    switch($mutation){
        'alt'{$s.AltDown=$true};'control'{$s.ControlDown=$true};'shift'{$s.ShiftDown=$true};'windows'{$s.WindowsKeyDown=$true}
        'popup'{$w=[InkQuayWorkflow.Window]::new();$w.Handle=101;$w.Owner=100;$w.ProcessId=17;$w.Visible=$true;$w.Enabled=$true;$w.ClassName='gdkWindowTemp';$s.Windows+=$w}
        'foreign-focus'{$s.FocusProcessId=18};'foreign-foreground'{$s.ForegroundProcessId=18};'wrong-title'{$s.Windows[0].Title='other document'};'disabled-main'{$s.Windows[0].Enabled=$false}
    }
    $failed=$false;try{[void][InkQuayWorkflow.Native]::PlanPdfExportKeys($s,'first.pdf - Scriblark')}catch{$failed=$true};Check $failed ('Accepted '+$mutation)
}
'PASS direct PDF source contract, exact six-event native plan and nine input ownership/modifier refusals.'
$original=Get-Content (Join-Path $PSScriptRoot 'fixtures/scriblark-34695588044-reopened-menu-after-file.json') -Raw|ConvertFrom-Json
$observed=[InkQuayWorkflow.InputState]::new()
foreach($field in $original.native.PSObject.Properties){
    if($field.Name -ceq 'Windows'){$observed.Windows=@(foreach($item in $field.Value){$window=[InkQuayWorkflow.Window]::new();foreach($property in $item.PSObject.Properties){$window.($property.Name)=$property.Value};$window})}
    else{$observed.($field.Name)=$field.Value}
}
Check ([InkQuayWorkflow.Native]::PlanPdfExportKeys($observed,'first.pdf - Scriblark').Count -eq 6) 'Original sole reopened editor is not eligible for its direct shortcut'
$temporary=Join-Path ([IO.Path]::GetTempPath()) ('scriblark-shortcut-contract-'+[guid]::NewGuid().ToString('N'))
try{
    $source=Resolve-Path (Join-Path $PSScriptRoot '../..')
    [void](New-Item -ItemType Directory -Path (Join-Path $temporary 'ui'))
    [void](New-Item -ItemType Directory -Path (Join-Path $temporary 'resources-templates'))
    foreach($name in @('ui/pageTemplate.glade','resources-templates/pagetemplates.ini.in')){Copy-Item (Join-Path $source $name) (Join-Path $temporary $name)}
    $xml=Get-Content (Join-Path $source 'ui/mainmenubar.xml') -Raw
    foreach($replacement in @('&lt;Ctrl&gt;e','&lt;Ctrl&gt;&lt;Shift&gt;q','')){
        [IO.File]::WriteAllText((Join-Path $temporary 'ui/mainmenubar.xml'),$xml.Replace('&lt;Ctrl&gt;&lt;Alt&gt;e',$replacement))
        $rejected=$false;try{[void](Get-InkWorkflowContract $temporary)}catch{$rejected=$true};Check $rejected 'Changed public PDF shortcut accepted by workflow'
    }
    [IO.File]::WriteAllText((Join-Path $temporary 'ui/mainmenubar.xml'),$xml.Replace('>&lt;Ctrl&gt;e<','>&lt;Ctrl&gt;&lt;Alt&gt;e<'))
    $rejected=$false;try{[void](Get-InkWorkflowContract $temporary)}catch{$rejected=$_.Exception.Message -match 'conflicts'}
    Check $rejected 'Conflicting existing shortcut accepted'
}finally{if(Test-Path $temporary){Remove-Item -LiteralPath $temporary -Recurse -Force}}
'PASS original reopened-editor observation and four public-shortcut source mutations; no native delivery claimed here.'
