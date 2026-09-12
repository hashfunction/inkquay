# Copyright 2026 Trieflow LLC. MIT. Actual production sequence/native guard fixtures.
$ErrorActionPreference='Stop';Set-StrictMode -Version Latest
. (Join-Path $PSScriptRoot 'qualify-workflow.ps1')
function Check($Value,$Message){if(-not $Value){throw $Message}}
$contract=Get-InkWorkflowContract (Resolve-Path (Join-Path $PSScriptRoot '../..'))
Check ($contract.fileMnemonic -ceq '%f' -and $contract.exportMnemonic -ceq 'e') 'Actual source File/Export menu contract is missing'
# Mutate only a uniquely owned tiny source fixture; never modify the real UI.
$fixture=Join-Path ([IO.Path]::GetTempPath()) ('scriblark-menu-contract-'+[guid]::NewGuid().ToString('N'))
try {
    [void](New-Item -ItemType Directory -Path (Join-Path $fixture 'ui'))
    [void](New-Item -ItemType Directory -Path (Join-Path $fixture 'resources-templates'))
    $source=Resolve-Path (Join-Path $PSScriptRoot '../..')
    Copy-Item (Join-Path $source 'ui/pageTemplate.glade') (Join-Path $fixture 'ui/pageTemplate.glade')
    Copy-Item (Join-Path $source 'resources-templates/pagetemplates.ini.in') (Join-Path $fixture 'resources-templates/pagetemplates.ini.in')
    $xml=Get-Content (Join-Path $source 'ui/mainmenubar.xml') -Raw
    foreach($mutation in @('file-label','export-label','export-action','duplicate-export')) {
        $changed=switch($mutation) {
            'file-label' {$xml.Replace('>_File<','>F_ile<')}
            'export-label' {$xml.Replace('>_Export as PDF<','>Export as _PDF<')}
            'export-action' {$xml.Replace('>win.export-as-pdf<','>win.export-as<')}
            'duplicate-export' {$xml.Replace('>win.export-as<','>win.export-as-pdf<')}
        }
        [IO.File]::WriteAllText((Join-Path $fixture 'ui/mainmenubar.xml'),$changed)
        $rejected=$false;try{[void](Get-InkWorkflowContract $fixture)}catch{$rejected=$true}
        Check $rejected ('Changed source mnemonic/action accepted: '+$mutation)
    }
} finally {if(Test-Path -LiteralPath $fixture){Remove-Item -LiteralPath $fixture -Recurse -Force}}
foreach($name in @('first','reopened')) {
    foreach($failurePoint in @('none','before-file','file-key','after-file','before-export','export-key','after-export')) {
        $script:trace=[Collections.Generic.List[string]]::new();$script:secondary=[Collections.Generic.List[string]]::new()
        $observe={param($Phase) $script:trace.Add($Phase);if($Phase -ceq $failurePoint){throw ('original '+$Phase)};if($Phase -ceq 'input-failure' -and $failurePoint -ceq 'export-key'){throw 'secondary observation failure'}}
        $send={param($Keys,$Action) $point=if($Keys -ceq '%f'){'file-key'}elseif($Keys -ceq 'e'){'export-key'}else{throw 'Unreviewed mnemonic'}
            $script:trace.Add($point+':'+$Action);if($point -ceq $failurePoint){throw ('original '+$point)}}
        $recordDiagnostic={param($ErrorText) $script:secondary.Add($ErrorText)}
        $failure=$null;try{Invoke-InkExportMenuSequence $name $contract $observe $send $recordDiagnostic}catch{$failure=$_.Exception.Message}
        $full=@('before-file',('file-key:open-export-menu-'+$name+'.pdf'),'after-file','before-export',('export-key:export-'+$name+'.pdf'),'after-export')
        if($failurePoint -ceq 'none'){Check (-not $failure -and ($script:trace -join '|') -ceq ($full -join '|')) 'Normal one-shot sequence changed'}
        else {
            $index=@{ 'before-file'=0;'file-key'=1;'after-file'=2;'before-export'=3;'export-key'=4;'after-export'=5 }[$failurePoint]
            $expected=@($full[0..$index])+@('input-failure')
            Check ($failure -ceq ('original '+$failurePoint) -and ($script:trace -join '|') -ceq ($expected -join '|')) ('Input replay or original error loss: '+$name+'/'+$failurePoint+'; error='+$failure+'; trace='+($script:trace -join '|')+'; expected='+($expected -join '|'))
            if($failurePoint -ceq 'export-key'){Check ($script:secondary.Count -eq 1 -and $script:secondary[0] -match 'secondary observation failure') 'Secondary diagnostic error lost'}
        }
    }
}
# A failed secondary recording callback must still retain the first exception.
$failure=$null
try {
    Invoke-InkExportMenuSequence 'first' $contract {throw 'original observation'} {throw 'must not send'} {throw 'secondary retention'}
} catch {$failure=$_.Exception.Message}
Check ($failure -ceq 'original observation') 'Secondary recording replaced original failure'
Add-InkWorkflowTypes
function NativeWindow($Handle,$Owner,$Class='gdkWindowToplevel') {
    $window=[InkQuayWorkflow.Window]::new();$window.Handle=$Handle;$window.Owner=$Owner;$window.ProcessId=17;$window.Title='first.pdf - Scriblark'
    $window.ClassName=$Class;$window.Visible=$true;$window.Enabled=$true;$window.Width=816;$window.Height=639;return $window
}
function State {
    $state=[InkQuayWorkflow.InputState]::new();$state.MainHandle=100;$state.ProcessId=17;$state.ForegroundHandle=100;$state.ForegroundProcessId=17
    $state.FocusHandle=100;$state.FocusRoot=100;$state.FocusProcessId=17;$state.Windows=@((NativeWindow 100 0));$state.ForegroundOwnerChain=@(100);return $state
}
[InkQuayWorkflow.Native]::AssertExportInput((State),'first.pdf - Scriblark')
$popup=State;$popup.ForegroundHandle=101;$popup.ForegroundOwnerChain=@(101,100);$popup.Windows+=NativeWindow 101 100 'gdkWindowTemp'
[InkQuayWorkflow.Native]::AssertExportInput($popup,'first.pdf - Scriblark')
foreach($mutation in @('foreign-foreground','foreign-focus','missing-focus','wrong-focus-root','disabled-main','changed-title','unowned-popup','wrong-popup-class','duplicate-popup','inconsistent-popup-owner','disabled-popup','hidden-popup')) {
    $state=State
    switch($mutation){
        'foreign-foreground'{$state.ForegroundProcessId=18}
        'foreign-focus'{$state.FocusProcessId=18}
        'missing-focus'{$state.FocusHandle=0}
        'wrong-focus-root'{$state.FocusRoot=999}
        'disabled-main'{$state.Windows[0].Enabled=$false}
        'changed-title'{$state.Windows[0].Title='other document'}
        default{$state.ForegroundHandle=101;$state.Windows+=NativeWindow 101 999 'gdkWindowTemp';$state.ForegroundOwnerChain=@(101,999)
            if($mutation -ceq 'wrong-popup-class'){$state.Windows[1].ClassName='foreign';$state.ForegroundOwnerChain=@(101,100)}
            if($mutation -ceq 'inconsistent-popup-owner'){$state.ForegroundOwnerChain=@(101,100)}
            if($mutation -cin @('disabled-popup','hidden-popup')){$state.Windows[1].Owner=100;$state.ForegroundOwnerChain=@(101,100);if($mutation -ceq 'disabled-popup'){$state.Windows[1].Enabled=$false}else{$state.Windows[1].Visible=$false}}
            if($mutation -ceq 'duplicate-popup'){$state.Windows[1].Owner=100;$state.ForegroundOwnerChain=@(101,100);$state.Windows+=$state.Windows[1]}}
    }
    $rejected=$false;try{[InkQuayWorkflow.Native]::AssertExportInput($state,'first.pdf - Scriblark')}catch{$rejected=$true}
    Check $rejected ('Native input guard accepted '+$mutation)
}
Write-Output 'PASS: both source-backed one-shot export sequences, six failure boundaries each, secondary-error retention, main/owned-popup focus and twelve negative native guards, and four source contract mutations.'

# Never send the Export mnemonic into the unchanged reopened editor.
$plan=[InkQuayWorkflow.Native]::PlanExportKeys((State),'first.pdf - Scriblark','%f')
Check ((($plan | ForEach-Object {"$($_.VirtualKey):$($_.KeyUp)"}) -join ',') -ceq '18:False,70:False,70:True,18:True') 'File chord key plan differs'
$missingMenu=$false;try{[void][InkQuayWorkflow.Native]::PlanExportKeys((State),'first.pdf - Scriblark','e')}catch{$missingMenu=$true}
Check $missingMenu 'Export mnemonic accepted without an observed owned GTK menu'
$menu=State;$menu.Windows+=NativeWindow 101 100 'gdkWindowTemp';$menu.Windows[1].Title='com.trieflow.inkquay'
$plan=[InkQuayWorkflow.Native]::PlanExportKeys($menu,'first.pdf - Scriblark','e')
Check ((($plan | ForEach-Object {"$($_.VirtualKey):$($_.KeyUp)"}) -join ',') -ceq '69:False,69:True') 'Export key plan differs'
foreach($mutation in @('held-alt','held-control','held-shift','held-windows','foreign-menu','duplicate-menu','disabled-menu','wrong-menu-title')) {
    $state=State;$state.Windows+=NativeWindow 101 100 'gdkWindowTemp';$state.Windows[1].Title='com.trieflow.inkquay'
    switch($mutation){
        'held-alt'{$state.AltDown=$true};'held-control'{$state.ControlDown=$true};'held-shift'{$state.ShiftDown=$true};'held-windows'{$state.WindowsKeyDown=$true}
        'foreign-menu'{$state.Windows[1].Owner=999};'duplicate-menu'{$state.Windows+=$state.Windows[1]};'disabled-menu'{$state.Windows[1].Enabled=$false};'wrong-menu-title'{$state.Windows[1].Title='foreign popup'}
    }
    $rejected=$false;try{[void][InkQuayWorkflow.Native]::PlanExportKeys($state,'first.pdf - Scriblark','e')}catch{$rejected=$true}
    Check $rejected ('Native chord accepted '+$mutation)
}
Write-Output 'PASS native File/Export key plans, missing-menu refusal and eight modifier/popup refusals.'
foreach($phase in @('first-menu-before-export','reopened-menu-after-file')) {
    $original=Get-Content (Join-Path $PSScriptRoot ('fixtures/scriblark-34695588044-'+$phase+'.json')) -Raw | ConvertFrom-Json
    $state=[InkQuayWorkflow.InputState]::new()
    foreach($field in $original.native.PSObject.Properties) {
        if($field.Name -ceq 'Windows') {
            $state.Windows=@(foreach($window in $field.Value) {
                $w=[InkQuayWorkflow.Window]::new();foreach($property in $window.PSObject.Properties){$w.($property.Name)=$property.Value};$w
            })
        } else {$state.($field.Name)=$field.Value}
    }
    $title=@($state.Windows | Where-Object Handle -eq $state.MainHandle)[0].Title
    if($phase -ceq 'first-menu-before-export') {Check ([InkQuayWorkflow.Native]::PlanExportKeys($state,$title,'e').Count -eq 2) 'Actual first open menu was rejected'}
    else {
        $rejected=$false;try{[void][InkQuayWorkflow.Native]::PlanExportKeys($state,$title,'e')}catch{$rejected=$true}
        Check $rejected 'Actual reopened editor accepted Export without its menu'
    }
}
Write-Output 'PASS unchanged original Windows first-menu/reopened-no-menu observations.'
