# Copyright 2026 Trieflow LLC. MIT. Ordinary installed UI, original pixels.
function Assert-ScribCaptureProcess($State) {
    $p=$State.process;$p.Refresh()
    if($p.SafeHandle.IsClosed -or $p.SafeHandle.IsInvalid -or $p.HasExited -or
       [InkQuayQualification.NativePackageProbe]::GetFullName($p.Handle) -cne $State.ownedPackageFullName -or
       (Get-CanonicalPath $p.MainModule.FileName) -ine (Get-CanonicalPath (Join-Path $State.installed.InstallLocation 'bin/Scriblark.exe'))){throw 'Retained capture executable/package differs'}
    $null=Assert-FileMatchesRecord $p.MainModule.FileName (Get-RecordPayloadEntry $State.record 'bin/Scriblark.exe') 'Actual capture executable'
}
function Get-ScribCaptureModules($State) {
    Assert-ScribCaptureProcess $State
    $root=Get-CanonicalPath $State.installed.InstallLocation;$windows=Get-CanonicalPath $env:SystemRoot
    $values=[Collections.Generic.List[object]]::new();$required=@($State.record.runtime.PSObject.Properties|ForEach-Object {[string]$_.Value})
    foreach($m in @($State.process.Modules)){
        Assert-NoReparsePath $m.FileName;$path=Get-CanonicalPath $m.FileName;$relative=$null;$signature=$null
        if(Test-PathInside $path $root){
            $relative=$path.Substring($root.Length).TrimStart('\','/').Replace('\','/')
            $hash=Assert-FileMatchesRecord $path (Get-RecordPayloadEntry $State.record $relative) 'Actual capture module';$origin='package'
            $required=@($required|Where-Object {$_ -cne $relative})
        }elseif(Test-PathInside $path $windows){$hash=(Get-FileHash $path).Hash.ToLowerInvariant();$origin='windows'}
        else{$signature=Get-VerifiedDefenderModuleEvidence $path (Join-Path ([Environment]::GetFolderPath('CommonApplicationData')) 'Microsoft/Windows Defender/Platform');$hash=$signature.sha256;$origin='microsoft_defender_signed_platform'}
        $values.Add(@{name=$m.ModuleName;path=$path;origin=$origin;relative_path=$relative;sha256=$hash;platform_signature=$signature})
    }
    if($required.Count){throw 'Captured process did not load required packaged runtimes'}
    return ,@($values)
}
function Assert-ScribCaptureFrame($Value,[int]$ExpectedPid,[long]$Main,[string]$MainTitle,[long]$Target,[string]$TargetTitle) {
    $m=$Value.main;$t=$Value.target;$a=$Value.work_area;$d=$Value.desktop
    if($m.Pid -ne $ExpectedPid -or $t.Pid -ne $ExpectedPid -or $m.Handle -ne $Main -or $t.Handle -ne $Target -or $Value.foreground -ne $Target -or
       $m.Title -cne $MainTitle -or $t.Title -cne $TargetTitle -or $m.Class -cne 'gdkWindowToplevel' -or $t.Class -cne 'gdkWindowToplevel' -or
       -not $m.Visible -or -not $t.Visible -or -not $t.Enabled -or -not $m.Maximized -or $m.Dpi -ne 96 -or $t.Dpi -ne 96){throw 'Actual capture surface differs'}
    foreach($r in @($m.Bounds,$t.Bounds,$a,$d)){if($r.Count -ne 4 -or $r[2] -le 0 -or $r[3] -le 0){throw 'Invalid native capture rectangle'}}
    if($a[2] -lt 1920 -or $a[3] -lt 1000 -or $d[2] -lt 1920 -or $d[3] -lt 1080 -or
       $a[0] -lt $d[0] -or $a[1] -lt $d[1] -or $a[0]+$a[2] -gt $d[0]+$d[2] -or $a[1]+$a[3] -gt $d[1]+$d[3] -or
       $m.Bounds[0] -gt $a[0] -or $m.Bounds[1] -gt $a[1] -or $m.Bounds[0]+$m.Bounds[2] -lt $a[0]+$a[2] -or $m.Bounds[1]+$m.Bounds[3] -lt $a[1]+$a[3]){throw 'Maximized editor does not fill the visible capture area'}
    if($Target -ne $Main -and ($t.Owner -ne $Main -or $t.Bounds[0] -lt $a[0] -or $t.Bounds[1] -lt $a[1] -or
       $t.Bounds[0]+$t.Bounds[2] -gt $a[0]+$a[2] -or $t.Bounds[1]+$t.Bounds[3] -gt $a[1]+$a[3])){throw 'Owned capture dialog is not inside editor'}
}
function Get-ScribCaptureFrame($State,[long]$Target){
    Assert-ScribCaptureProcess $State
    $screen=[Windows.Forms.Screen]::FromHandle([IntPtr]$State.main);$a=$screen.WorkingArea;$d=$screen.Bounds
    return @{main=[ScriblarkMarketing.Frame]::Observe($State.main);target=[ScriblarkMarketing.Frame]::Observe($Target);foreground=[ScriblarkMarketing.Frame]::Foreground();
        work_area=@($a.X,$a.Y,$a.Width,$a.Height);desktop=@($d.X,$d.Y,$d.Width,$d.Height)}
}
function Save-ScribCaptureFrame($State,[string]$Stem,[string]$MainTitle,$Window){
    if($Stem -cnotin @('01-note-workspace','02-page-template','03-pdf-export')){throw 'Unknown screenshot slot'}
    $before=Get-ScribCaptureFrame $State $Window.Handle
    Assert-ScribCaptureFrame $before $State.process.Id $State.main $MainTitle $Window.Handle $Window.Title
    $a=$before.work_area;$bitmap=[Drawing.Bitmap]::new($a[2],$a[3]);$g=[Drawing.Graphics]::FromImage($bitmap);$stream=[IO.MemoryStream]::new()
    try{$g.CopyFromScreen($a[0],$a[1],0,0,$bitmap.Size);$bitmap.Save($stream,[Drawing.Imaging.ImageFormat]::Png);$bytes=$stream.ToArray()}
    finally{$g.Dispose();$bitmap.Dispose();$stream.Dispose()}
    $after=Get-ScribCaptureFrame $State $Window.Handle
    Assert-ScribCaptureFrame $after $State.process.Id $State.main $MainTitle $Window.Handle $Window.Title
    if(($before|ConvertTo-Json -Depth 8 -Compress) -cne ($after|ConvertTo-Json -Depth 8 -Compress)){throw 'Native screenshot surface changed during capture'}
    $path=Join-Path $State.output ($Stem+'.png');$file=[IO.File]::Open($path,[IO.FileMode]::CreateNew)
    try{$file.Write($bytes,0,$bytes.Length);$file.Flush($true)}finally{$file.Dispose()}
    Write-NewUtf8Json (Join-Path $State.output ($Stem+'.json')) @{schema_version=1;purpose='original native marketing screenshot';consumer_acceptance=$false;pixel_manipulation=$false;
        package_full_name=$State.ownedPackageFullName;qualified_source_commit=$State.record.sourceCommit;process_id=$State.process.Id;before=$before;after=$after;
        png=@{bytes=$bytes.Length;sha256=(Get-FileHash $path).Hash.ToLowerInvariant()};captured_at_utc=[DateTime]::UtcNow.ToString('o')}
    $State.captures.Add($Stem)
}
function Invoke-ScribCaptureUi($State,[string]$QualifiedSource) {
    $contract=Get-InkWorkflowContract $QualifiedSource
    [xml]$menus=Get-Content (Join-Path $QualifiedSource 'ui/mainmenubar.xml') -Raw
    $view=@($menus.interface.menu.submenu|Where-Object {@($_.attribute|Where-Object name -eq 'label').'#text' -ceq '_View'})
    if($view.Count -ne 1 -or $view[0].SelectNodes('section/item')[($view[0].SelectNodes('section/item').Count-1)].SelectSingleNode("attribute[@name='action']").InnerText -cne 'win.zoom-fit'){throw 'Actual View menu final Zoom to Fit contract changed'}
    function Observe([string]$Title,[bool]$Dialog=$false){
        $deadline=[DateTime]::UtcNow.AddSeconds(20)
        do{Assert-ScribCaptureProcess $State;try{return Select-InkWorkflowWindow ([InkQuayWorkflow.Native]::Windows($State.process.Id)) $State.process.Id $State.main $Title $Dialog}catch{$last=$_.Exception.Message};Start-Sleep -Milliseconds 150}while([DateTime]::UtcNow -lt $deadline)
        throw $last
    }
    function Keys($Window,[string]$Value,[string]$Action){
        Assert-ScribCaptureProcess $State
        [ScriblarkMarketing.Frame]::Focus($Window.Handle,$State.process.Id,$State.main,$Window.Title,$Window.Handle -ne $State.main)
        [Windows.Forms.SendKeys]::SendWait($Value)
        $State.events.Add(@{action=$Action;hwnd=$Window.Handle;title=$Window.Title;process_id=$State.process.Id;at_utc=[DateTime]::UtcNow.ToString('o')})
        Start-Sleep -Milliseconds 300
    }
    function TextKeys([string]$Text){return [regex]::Replace($Text,'[+^%~(){}\[\]]',{param($m)'{'+$m.Value+'}'})}
    function Choose([string]$Title,[string]$Name){$w=Observe $Title $true;Keys $w '^l' 'chooser-location';Keys $w ('^a'+(TextKeys (Join-Path $State.demo $Name))+'{ENTER}') ('choose-'+$Name)}
    $main=Observe 'Unsaved Document - Scriblark'
    [ScriblarkMarketing.Frame]::Maximize($State.main,$State.process.Id,$main.Title)
    Start-Sleep -Milliseconds 400
    Keys $main '^o' 'open-sample';Choose 'Open file' 'A pocket of green.xopp'
    $title='A pocket of green.xopp - Scriblark';$main=Observe $title
    Keys $main '%v{END}{ENTER}' 'fit-sample-to-window'
    Save-ScribCaptureFrame $State '01-note-workspace' $title (Observe $title)
    Keys (Observe $title) ('%j{HOME}{DOWN '+$contract.configureMenuDown+'}{ENTER}') 'configure-page-template'
    $dialog=Observe $contract.templateTitle $true
    Keys $dialog ('%t{HOME}{DOWN '+$contract.cornellIndex+'}{TAB}^aWorkshop notes') 'select-and-name-cornell'
    Keys $dialog '%s' 'save-named-template'
    Keys $dialog '{ESC}' 'close-template-dialog'
    Keys (Observe $title) ('%j{HOME}{DOWN '+$contract.configureMenuDown+'}{ENTER}') 'reopen-template-library'
    $dialog=Observe $contract.templateTitle $true;Keys $dialog '%t{END}' 'reload-saved-template'
    Save-ScribCaptureFrame $State '02-page-template' $title (Observe $contract.templateTitle $true)
    Keys $dialog '{ESC}' 'return-to-notebook'
    $main=Observe $title
    [ScriblarkMarketing.Frame]::Focus($State.main,$State.process.Id,$State.main,$title,$false)
    if($contract.pdfExportShortcut -cne '^%e'){throw 'Reviewed public PDF export shortcut differs'}
    $count=[InkQuayWorkflow.Native]::SendPdfExportKeys([IntPtr]$State.main,$State.process.Id,$title)
    $State.events.Add(@{action='export-pdf';hwnd=$State.main;title=$title;native_input_method='SendInput';native_sendinput_events=$count;at_utc=[DateTime]::UtcNow.ToString('o')});Start-Sleep -Milliseconds 350
    Choose 'Export File' 'A pocket of green - handout.pdf'
    $deadline=[DateTime]::UtcNow.AddSeconds(30)
    do{Assert-ScribCaptureProcess $State;$reports=@(Get-ChildItem -LiteralPath $State.demo -File -Filter 'A pocket of green - handout.pdf.*.inkquay-report.json');if($reports.Count -eq 1){break};Start-Sleep -Milliseconds 150}while([DateTime]::UtcNow -lt $deadline)
    $State.verified=Invoke-ScribCaptureFiles 'verify' $State
    $windows=[InkQuayWorkflow.Native]::Windows($State.process.Id)
    $dialogs=@($windows|Where-Object {$_.Handle -ne $State.main -and $_.Owner -eq $State.main -and $_.Enabled -and $_.ClassName -ceq 'gdkWindowToplevel' -and $_.Title -cin @('','Scriblark')})
    if($dialogs.Count -ne 1){throw 'Actual checked PDF result dialog missing'}
    $dialog=Observe $dialogs[0].Title $true
    Save-ScribCaptureFrame $State '03-pdf-export' $title $dialog
    Keys $dialog '{ENTER}' 'dismiss-pdf-report'
    Keys (Observe $title) '^o' 'reopen-exported-pdf';Choose 'Open file' 'A pocket of green - handout.pdf'
    $null=Observe 'A pocket of green - handout.pdf - Scriblark';$State.pdfReopened=$true
    if(($State.captures -join ',') -cne '01-note-workspace,02-page-template,03-pdf-export'){throw 'Capture set incomplete'}
}
