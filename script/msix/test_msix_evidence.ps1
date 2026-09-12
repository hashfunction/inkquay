# Actual outer reporting path with only Windows orchestration replaced.
# Copyright 2026 Trieflow LLC. MIT licensed.
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
. (Join-Path $PSScriptRoot 'qualify-msix-install.ps1') -LibraryOnly
$script:ActualHelperEvidence=${function:Get-InkQuayHelperEvidence}
function Get-InkQuayHelperEvidence {
    if($scenario -ceq 'helper-failure'){throw 'owned helper metadata unavailable'}
    return & $script:ActualHelperEvidence
}
foreach ($scenario in @('helper-failure','missing','changed','changed-after-success','success','write-failure','observer-success','observer-failure','input-success','input-failure')) {
    $probeRoot = Join-Path ([IO.Path]::GetTempPath()) ('inkquay-evidence-test-' + [guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $probeRoot | Out-Null
    try {
        function Invoke-InkQuayQualificationCore([Collections.IDictionary]$Operations) {
            $captured = $Operations.Preflight.Module.SessionState.PSVariable.GetValue('state')
            $captured.output = $probeRoot
            $captured.package = Join-Path $probeRoot 'source.msix'
            [IO.File]::WriteAllText($captured.package, 'original bytes')
            $captured.unsignedPackageSha256 = (Get-FileHash -LiteralPath $captured.package -Algorithm SHA256).Hash.ToLowerInvariant()
            if ($scenario -eq 'missing') { Remove-Item -LiteralPath $captured.package }
            if ($scenario -in @('changed','changed-after-success')) { [IO.File]::WriteAllText($captured.package, 'changed bytes') }
            if ($scenario -eq 'write-failure') { [IO.File]::WriteAllText((Join-Path $probeRoot 'installation-qualification.json'), 'preserve existing evidence') }
            if ($scenario -in @('observer-success','observer-failure','input-success','input-failure')) {
                $captured.workflow=@{passed=$true}
                $captured.observerErrors.Add('fixture observer diagnostic failure')
            }
            if($scenario.StartsWith('input-')) {
                $captured.workflow=@{passed=$true}
                $captured.temporary=Join-Path $probeRoot 'temporary-owned';New-Item -ItemType Directory $captured.temporary | Out-Null
                $captured.inputDiagnosticsPath=Join-Path $captured.temporary 'input-diagnostics.jsonl'
                # Execute the production publication/cleanup operation with absent process
                # ownership. The secondary error must be retained without escaping it.
                & $Operations.RemoveTemporaryFiles
                if(Test-Path -LiteralPath $captured.temporary){throw 'Diagnostic failure skipped owned temporary cleanup'}
            }
            if ($scenario -in @('success','changed-after-success','observer-success','input-success')) {
                return [pscustomobject]@{ installation_qualification_passed=$true; primary_error=$null; cleanup_errors=@() }
            }
            return [pscustomobject]@{ installation_qualification_passed=$false; primary_error='original activation failure'; cleanup_errors=@('original uninstall failure') }
        }
        $failure = $null
        try { Invoke-InkQuayInstallQualification -PackagePath 'unused' -RecordPath 'unused' -SignToolPath 'unused' -OutputPath $probeRoot -CaptureCrashStack:($scenario.StartsWith('observer-')) -CaptureInputDiagnostics:($scenario.StartsWith('input-')) | Out-Null }
        catch { $failure = $_.Exception.Message }
        $evidencePath = Join-Path $probeRoot 'installation-qualification.json'
        if (-not (Test-Path -LiteralPath $evidencePath)) { throw "Missing final evidence in $scenario" }
        if ($scenario -eq 'write-failure') {
            if ((Get-Content -LiteralPath $evidencePath -Raw) -ne 'preserve existing evidence' -or $failure -notmatch 'Could not preserve.*original activation failure.*original uninstall failure') { throw 'Evidence write failure lost original errors or replaced previous bytes.' }
            continue
        }
        $evidence = Get-Content -LiteralPath $evidencePath -Raw | ConvertFrom-Json
        if($scenario.StartsWith('input-')) {
            if(-not $evidence.diagnostic_input_requested -or $evidence.diagnostic_observer_requested -or
                $evidence.installation_qualification_passed -or $evidence.workflow_acceptance -or
                $evidence.template_pdf_workflow_tested -or $evidence.interactive_pdf_workflows_verified -or
                $evidence.input_diagnostic_errors[0] -cne 'Input diagnostic process/path ownership is unavailable'){throw ('Input diagnostic conferred acceptance or lost secondary evidence: '+($evidence.input_diagnostic_errors -join '; '))}
            if($scenario -ceq 'input-success') {
                if($failure -or -not $evidence.diagnostic_run_completed){throw 'Input diagnostic control lost completed lifecycle'}
            } elseif(-not $failure -or $evidence.primary_error -cne 'original activation failure' -or
                $evidence.cleanup_errors[0] -cne 'original uninstall failure'){throw 'Input diagnostics displaced original errors'}
            continue
        }
        if ($scenario.StartsWith('observer-')) {
            if (-not $evidence.diagnostic_observer_requested -or $evidence.installation_qualification_passed -or
                $evidence.workflow_acceptance -or $evidence.template_pdf_workflow_tested -or $evidence.interactive_pdf_workflows_verified -or
                $evidence.observer_diagnostic_errors[0] -cne 'fixture observer diagnostic failure') { throw 'Observer-only run conferred consumer acceptance or lost secondary diagnostics.' }
            if ($scenario -ceq 'observer-success') {
                if ($failure -or -not $evidence.diagnostic_run_completed) { throw 'Diagnostic control lost successful lifecycle execution.' }
            } elseif (-not $failure -or $evidence.primary_error -cne 'original activation failure' -or
                $evidence.cleanup_errors[0] -cne 'original uninstall failure') { throw 'Observer diagnostics displaced primary/cleanup failures.' }
            continue
        }
        if ($scenario -ceq 'helper-failure') {
            if(-not $failure -or $evidence.installation_qualification_passed -or -not $evidence.unsigned_package_unchanged -or $null -ne $evidence.qualification_helpers -or
                $evidence.evidence_errors.Count -ne 1 -or $evidence.evidence_errors[0] -notmatch 'owned helper metadata unavailable' -or
                $evidence.primary_error -cne 'original activation failure' -or $evidence.cleanup_errors[0] -cne 'original uninstall failure'){throw 'Helper evidence failure displaced primary/cleanup evidence.'}
            continue
        }
        if ($scenario -eq 'success') {
            if ($failure -or -not $evidence.installation_qualification_passed -or -not $evidence.unsigned_package_unchanged -or $evidence.evidence_errors.Count) { throw 'Unchanged success control did not pass.' }
        } else {
            if (-not $failure -or $evidence.installation_qualification_passed -or $evidence.unsigned_package_unchanged -or $evidence.evidence_errors.Count -ne 1) { throw "Changed/missing source must fail in $scenario" }
            if ($scenario -ne 'changed-after-success' -and ($evidence.primary_error -ne 'original activation failure' -or $evidence.cleanup_errors[0] -ne 'original uninstall failure')) { throw 'Original primary/cleanup failures were lost.' }
        }
    } finally { Remove-Item -LiteralPath $probeRoot -Recurse -Force }
}
Write-Output 'PASS: ten final-hash, helper-error, diagnostic and exclusive-evidence reporting scenarios.'
