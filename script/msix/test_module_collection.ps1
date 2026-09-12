# Copyright 2026 Trieflow LLC. MIT. Real collector/file checks; no Windows activation claim.
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
. (Join-Path $PSScriptRoot 'qualify-msix-install.ps1') -LibraryOnly

# Execute the production assignment inside the same outer closure used by
# ActivateAndVerify. A second GetNewClosure loses state from that outer module.
$assignments=@(${function:Invoke-InkQuayInstallQualification}.Ast.FindAll({
    param($node)
    $node -is [Management.Automation.Language.AssignmentStatementAst] -and
        $node.Left -is [Management.Automation.Language.VariableExpressionAst] -and
        $node.Left.VariablePath.UserPath -ceq 'collectModules'
},$true))
if ($assignments.Count -ne 1) { throw 'Expected one production module collector assignment.' }
$script:CollectorAssignment=$assignments[0].Extent.Text
function Invoke-ActualCollector([Collections.IDictionary]$FixtureState) {
    $state=$FixtureState
    $operation=[scriptblock]::Create($script:CollectorAssignment + "`n& `$collectModules 'loaded-modules.json'`n& `$collectModules 'workflow-loaded-modules.json'").GetNewClosure()
    & $operation
}

$temporaryBase=if ($IsMacOS) { '/private/tmp' } else { [IO.Path]::GetTempPath() }
$fixtureRoot=Join-Path $temporaryBase ('inkquay-modules-'+[guid]::NewGuid().ToString('N'))
$previousSystemRoot=$env:SystemRoot
New-Item -ItemType Directory -Path $fixtureRoot | Out-Null
try {
    foreach ($scenario in @('valid','missing-runtime','unknown-package-module','changed-package-module','outside-roots','linked-module')) {
        $directory=Join-Path $fixtureRoot $scenario
        $packageRoot=Join-Path $directory 'package'
        $windowsRoot=Join-Path $directory 'windows'
        New-Item -ItemType Directory -Path (Join-Path $packageRoot 'bin'),$windowsRoot | Out-Null
        $env:SystemRoot=$windowsRoot
        $payload=[pscustomobject]@{}
        $modules=[Collections.Generic.List[object]]::new()
        foreach ($relative in @('bin/Scriblark.exe','bin/libgtk-3-0.dll','bin/libpoppler-glib-8.dll')) {
            $path=Join-Path $packageRoot $relative
            [IO.File]::WriteAllText($path,'fixture bytes for '+$relative)
            $payload | Add-Member -NotePropertyName $relative -NotePropertyValue ([pscustomobject]@{
                bytes=(Get-Item -LiteralPath $path).Length
                sha256=(Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()
            })
            $modules.Add([pscustomobject]@{FileName=$path;ModuleName=[IO.Path]::GetFileName($path)})
        }
        $windowsModule=Join-Path $windowsRoot 'kernel32.dll'
        [IO.File]::WriteAllText($windowsModule,'fixture Windows module bytes')
        $modules.Add([pscustomobject]@{FileName=$windowsModule;ModuleName='kernel32.dll'})
        switch ($scenario) {
            'missing-runtime' { $modules.RemoveAt(2) }
            'unknown-package-module' {
                $unknown=Join-Path $packageRoot 'bin/unknown.dll'
                [IO.File]::WriteAllText($unknown,'not in payload record')
                $modules.Add([pscustomobject]@{FileName=$unknown;ModuleName='unknown.dll'})
            }
            'changed-package-module' {
                # Equal length forces the real hash check, not only size rejection.
                $path=Join-Path $packageRoot 'bin/libgtk-3-0.dll'
                [IO.File]::WriteAllText($path,('x' * (Get-Item -LiteralPath $path).Length))
            }
            'outside-roots' {
                $foreign=Join-Path $directory 'foreign.dll'
                [IO.File]::WriteAllText($foreign,'outside both accepted roots')
                $modules.Add([pscustomobject]@{FileName=$foreign;ModuleName='foreign.dll'})
            }
            'linked-module' {
                $linked=Join-Path $directory 'linked-package'
                $linkType=if ($IsWindows) { 'Junction' } else { 'SymbolicLink' }
                New-Item -ItemType $linkType -Path $linked -Target $packageRoot | Out-Null
                $modules[0]=[pscustomobject]@{FileName=(Join-Path $linked 'bin/Scriblark.exe');ModuleName='Scriblark.exe'}
            }
        }
        $fixtureState=[ordered]@{
            installed=[pscustomobject]@{InstallLocation=$packageRoot}
            record=[pscustomobject]@{
                payload=$payload
                runtime=[pscustomobject]@{gtk='bin/libgtk-3-0.dll';poppler='bin/libpoppler-glib-8.dll'}
            }
            process=[pscustomobject]@{Modules=@($modules)}
            output=$directory
            modules=@()
        }
        $failure=$null
        try { Invoke-ActualCollector $fixtureState } catch { $failure=$_ }
        if ($scenario -eq 'valid') {
            if ($failure) { throw "Actual collector lost or rejected valid captured state: $failure`n$($failure.ScriptStackTrace)" }
            if ($fixtureState.modules.Count -ne 4) { throw 'Collector did not update the captured installation state.' }
            foreach ($name in @('loaded-modules.json','workflow-loaded-modules.json')) {
                $observed=@(Get-Content -LiteralPath (Join-Path $directory $name) -Raw | ConvertFrom-Json)
                if ($observed.Count -ne 4) { throw 'Incomplete initial or post-workflow module evidence.' }
                for ($index=0;$index -lt 4;$index++) {
                    $expectedPath=$modules[$index].FileName
                    $expectedHash=(Get-FileHash -LiteralPath $expectedPath -Algorithm SHA256).Hash.ToLowerInvariant()
                    $expectedOrigin=if ($index -lt 3) { 'package' } else { 'windows' }
                    if ($observed[$index].path -cne $expectedPath -or $observed[$index].sha256 -cne $expectedHash -or
                        $observed[$index].origin -cne $expectedOrigin) { throw 'Collector evidence differs from the actual fixture file.' }
                }
                if ($observed[1].relative_path -cne 'bin/libgtk-3-0.dll' -or $null -ne $observed[3].relative_path) {
                    throw 'Package-relative and Windows module origins were confused.'
                }
            }
        } else {
            $expectedFailure=switch ($scenario) {
                'missing-runtime' { 'did not load required packaged GTK/Poppler runtime' }
                'unknown-package-module' { 'absent from the verified payload record' }
                'changed-package-module' { 'hash differs from package record' }
                'outside-roots' { 'Defender module is outside its platform root' }
                'linked-module' { 'Reparse point in qualified path' }
            }
            if (-not $failure -or $failure.Exception.Message -notmatch $expectedFailure) { throw "${scenario}: expected policy rejection; observed $failure" }
            if ($fixtureState.modules.Count -or (Test-Path -LiteralPath (Join-Path $directory 'loaded-modules.json'))) {
                throw "${scenario}: rejected module set published success evidence"
            }
        }
        Write-Output "PASS actual module collector: $scenario"
    }
} finally {
    $env:SystemRoot=$previousSystemRoot
    Remove-Item -LiteralPath $fixtureRoot -Recurse -Force
}
