$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'qualify-msix-install.ps1') -LibraryOnly
$fixture=[ordered]@{title='Unsaved Document - InkQuay';visible=$true;process_id=123;width=800;height=600;screenshot_captured=$true;screenshot_sha256=('a'*64);sampled_colors=30;controls=@([pscustomobject]@{name='Unsaved Document - InkQuay';control_type='ControlType.Window';offscreen=$false;process_id=123})}
Assert-InkQuayWindowEvidence $fixture
foreach($kind in @('title','screenshot','offscreen','wrong-process','missing-root','error-only')) {
 $candidate=[ordered]@{}+$fixture
 switch($kind) {
  title {$candidate.title='Xournal++'}
  screenshot {$candidate.screenshot_captured=$false}
  offscreen {$candidate.visible=$false}
  wrong-process {$candidate.process_id=456}
  missing-root {$candidate.controls=@()}
  error-only {$candidate.controls=@([pscustomobject]@{observation_error='UIA failed'})}
 }
 $rejected=$false;try{Assert-InkQuayWindowEvidence $candidate}catch{$rejected=$true}
 if(-not $rejected){throw "Invalid window evidence accepted: $kind"}
}
'One genuine GTK root control and six negative window scenarios passed; no native UI claim.'
