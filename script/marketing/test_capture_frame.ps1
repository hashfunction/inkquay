# Copyright 2026 Trieflow LLC. MIT. Pure ownership/geometry refusals; no pixels claimed.
$ErrorActionPreference='Stop';Set-StrictMode -Version Latest
. (Join-Path $PSScriptRoot 'capture_ui.ps1')
Add-Type -Path (Join-Path $PSScriptRoot 'CaptureNative.cs')
function Check($Value,$Message){if(-not $Value){throw $Message}}
function Surface([long]$Handle,[string]$Title){
    $s=[ScriblarkMarketing.Surface]::new();$s.Handle=$Handle;$s.Pid=17;$s.Dpi=96;$s.Visible=$true;$s.Enabled=$true;$s.Maximized=$true;
    $s.Title=$Title;$s.Class='gdkWindowToplevel';$s.Bounds=@(-8,-8,1936,1048);return $s
}
function Frame([bool]$Dialog){
    $m=Surface 100 'A pocket of green.xopp - Scriblark';$t=Surface 100 $m.Title
    if($Dialog){$t=Surface 101 'Configure new page template';$t.Owner=100;$t.Maximized=$false;$t.Bounds=@(640,300,640,430);$m.Enabled=$false}
    return @{main=$m;target=$t;foreground=$t.Handle;work_area=@(0,0,1920,1032);desktop=@(0,0,1920,1080)}
}
foreach($dialog in @($false,$true)){
    $f=Frame $dialog;Assert-ScribCaptureFrame $f 17 100 'A pocket of green.xopp - Scriblark' $f.target.Handle $f.target.Title
    foreach($mutation in @('foreign-main','foreign-target','wrong-foreground','wrong-title','wrong-class','hidden','disabled-target','not-maximized','wrong-dpi','offscreen','partial-main','small-display')){
        $f=Frame $dialog;$targetTitle=$f.target.Title
        switch($mutation){
            'foreign-main'{$f.main.Pid=18};'foreign-target'{$f.target.Pid=18};'wrong-foreground'{$f.foreground=999};'wrong-title'{$f.target.Title='foreign'}
            'wrong-class'{$f.target.Class='foreign'};'hidden'{$f.main.Visible=$false};'disabled-target'{$f.target.Enabled=$false};'not-maximized'{$f.main.Maximized=$false};'wrong-dpi'{$f.target.Dpi=120}
            'offscreen'{$f.work_area[0]=500};'partial-main'{$f.main.Bounds[2]=800};'small-display'{$f.desktop[2]=1024}
        }
        $failed=$false;try{Assert-ScribCaptureFrame $f 17 100 'A pocket of green.xopp - Scriblark' $f.target.Handle $targetTitle}catch{$failed=$true};Check $failed ('Accepted '+$mutation)
    }
}
$f=Frame $true;$f.target.Owner=999;$failed=$false;try{Assert-ScribCaptureFrame $f 17 100 'A pocket of green.xopp - Scriblark' 101 'Configure new page template'}catch{$failed=$true};Check $failed 'Foreign dialog owner accepted'
[ScriblarkMarketing.Frame]::Require((Surface 100 'sample'),17,100,'sample',$false)
$s=Surface 100 'sample';$s.Pid=99;$failed=$false;try{[ScriblarkMarketing.Frame]::Require($s,17,100,'sample',$false)}catch{$failed=$true};Check $failed 'Native target policy accepted foreign PID'
'PASS actual frame policy: editor/dialog, 25 geometry/ownership refusals and compiled native target predicate.'
