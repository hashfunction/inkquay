# Disposable Windows CI installation qualification for Scriblark.
# Copyright 2026 Trieflow LLC. MIT licensed.
# Installation-flow structure adapted from ReticleQuay's MIT helper; the full
# retained notice is in RETICLEQUAY-MIT.txt.
[CmdletBinding()]
param(
    [Parameter()][string]$Package,
    [Parameter()][string]$PackageRecord,
    [Parameter()][string]$SignTool,
    [Parameter()][string]$Output,
    [Parameter()][switch]$CaptureCrashStack,
    [Parameter()][switch]$CaptureInputDiagnostics,
    [Parameter()][ValidateSet('qualification','store')][string]$IdentityMode='qualification',
    [Parameter()][switch]$LibraryOnly
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

function Invoke-InkQuayQualificationCore([Collections.IDictionary]$Operations) {
    $required = @(
        'Preflight','PrepareSignedCopy','Install','ActivateAndVerify','CloseCleanly','UninstallAndVerify',
        'StopOwnedProcess','RemoveOwnedPackage','RemoveTrustedCertificate','RemovePersonalCertificate','RemoveTemporaryFiles'
    )
    foreach ($name in $required) {
        if (-not $Operations.Contains($name) -or $Operations[$name] -isnot [scriptblock]) {
            throw "Missing qualification operation: $name"
        }
    }
    $primaryError = $null
    $cleanupErrors = [Collections.Generic.List[string]]::new()
    try {
        foreach ($name in @('Preflight','PrepareSignedCopy','Install','ActivateAndVerify','CloseCleanly','UninstallAndVerify')) {
            # Native tools such as SignTool emit stdout. Keep it in the host
            # log without turning this function's structured result into an array.
            & $Operations[$name] | Out-Host
        }
    } catch {
        $primaryError = $_.Exception.Message
    } finally {
        foreach ($name in @('StopOwnedProcess','RemoveOwnedPackage','RemoveTrustedCertificate','RemovePersonalCertificate','RemoveTemporaryFiles')) {
            try {
                & $Operations[$name] | Out-Host
            } catch {
                $cleanupErrors.Add("${name}: $($_.Exception.Message)")
            }
        }
    }
    return [pscustomobject][ordered]@{
        installation_qualification_passed = (-not $primaryError -and $cleanupErrors.Count -eq 0)
        primary_error = $primaryError
        cleanup_errors = @($cleanupErrors)
    }
}

function Invoke-CheckedNative([string]$Program, [string[]]$Arguments) {
    & $Program @Arguments
    if ($LASTEXITCODE -ne 0) { throw "$Program failed with exit $LASTEXITCODE" }
}

function Get-InkQuayProcessExitEvidence([Diagnostics.Process]$Process, [int]$TimeoutMilliseconds) {
    # Adapted from FileQuay 39f6fadb: getters can otherwise conceal observation errors.
    $evidence = [ordered]@{ process_id=$null; wait_completed=$false; exit_code=$null; normal_exit=$false; observation_error=$null }
    try {
        $evidence.process_id = $Process.get_Id()
        $evidence.wait_completed = $Process.WaitForExit($TimeoutMilliseconds)
        if ($evidence.wait_completed) {
            $evidence.exit_code = $Process.get_ExitCode()
            $evidence.normal_exit = $evidence.exit_code -eq 0
        }
    } catch { $evidence.observation_error = $_.Exception.ToString() }
    return [pscustomobject]$evidence
}

function Assert-NoReparsePath([string]$Path) {
    $item = Get-Item -LiteralPath $Path -Force -ErrorAction Stop
    while ($item) {
        if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw "Reparse point in qualified path: $($item.FullName)" }
        $item = if ($item -is [IO.DirectoryInfo]) { $item.Parent } else { $item.Directory }
    }
}

function Get-CanonicalPath([string]$Path) {
    return [IO.Path]::GetFullPath($Path).TrimEnd([IO.Path]::DirectorySeparatorChar, [IO.Path]::AltDirectorySeparatorChar)
}

function Test-PathInside([string]$Candidate, [string]$Root) {
    $candidatePath = Get-CanonicalPath $Candidate
    $rootPath = Get-CanonicalPath $Root
    return $candidatePath.Equals($rootPath, [StringComparison]::OrdinalIgnoreCase) -or
        $candidatePath.StartsWith($rootPath + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)
}

function Get-RecordPayloadEntry([object]$Record, [string]$Relative) {
    $property = $Record.payload.PSObject.Properties[$Relative]
    if (-not $property) { throw "Installed/package module is absent from the verified payload record: $Relative" }
    return $property.Value
}

function Get-VerifiedDefenderModuleEvidence([string]$Path, [string]$PlatformRoot) {
    # Windows run 34604065415 loaded Defender's signed AMSI module outside SystemRoot.
    # Restrict this exception to the observed module in the documented platform layout.
    $path = Get-CanonicalPath $Path
    $platform = Get-CanonicalPath $PlatformRoot
    if (-not (Test-PathInside $path $platform)) { throw 'Defender module is outside its platform root.' }
    $relative = [IO.Path]::GetRelativePath($platform, $path).Replace('\','/')
    if ($relative -cnotmatch '^\d+\.\d+\.\d+\.\d+-\d+/MpOav\.dll$') { throw 'Unexpected Defender module or platform path.' }
    Assert-NoReparsePath $path
    $item = Get-Item -LiteralPath $path -Force
    if ($item.PSIsContainer -or $item.LinkType) { throw 'Defender module is not a regular non-link file.' }
    $hash = (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()
    $signature = Get-AuthenticodeSignature -LiteralPath $path
    $certificate = $signature.SignerCertificate
    if ([string]$signature.Status -cne 'Valid' -or -not $certificate) {
        throw 'Defender module lacks a valid Microsoft Authenticode signature.'
    }
    $commonNames = [Collections.Generic.List[string]]::new()
    $organizations = [Collections.Generic.List[string]]::new()
    foreach ($rdn in $certificate.SubjectName.EnumerateRelativeDistinguishedNames()) {
        if ($rdn.HasMultipleElements) { throw 'Ambiguous multi-valued Defender signer RDN.' }
        switch ($rdn.GetSingleElementType().Value) {
            '2.5.4.3' { $commonNames.Add($rdn.GetSingleElementValue()) }
            '2.5.4.10' { $organizations.Add($rdn.GetSingleElementValue()) }
        }
    }
    if ($commonNames.Count -ne 1 -or $organizations.Count -ne 1 -or
        $commonNames[0] -cnotin @('Microsoft Windows Publisher','Microsoft Corporation','Microsoft Windows') -or
        $organizations[0] -cne 'Microsoft Corporation') {
        throw ('Defender signature does not identify the required Microsoft signer. Parsed certificate: ' +
            (@{common_names=@($commonNames);organizations=@($organizations);subject=$certificate.Subject;
                issuer=$certificate.Issuer;thumbprint=$certificate.Thumbprint;status=[string]$signature.Status} | ConvertTo-Json -Compress))
    }
    Assert-NoReparsePath $path
    if ((Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant() -cne $hash) { throw 'Defender module changed during signature verification.' }
    return [ordered]@{ sha256=$hash; signature_status=[string]$signature.Status;
        signer_subject=$certificate.Subject; signer_issuer=$certificate.Issuer; signer_thumbprint=$certificate.Thumbprint;
        signer_common_name=$commonNames[0]; signer_organization=$organizations[0] }
}

function Assert-FileMatchesRecord([string]$Path, [object]$Expected, [string]$Label) {
    Assert-NoReparsePath $Path
    $item = Get-Item -LiteralPath $Path -Force
    if ($item.PSIsContainer -or $item.LinkType) { throw "$Label is not a regular non-link file: $Path" }
    if ($item.Length -ne [int64]$Expected.bytes) { throw "$Label size differs from package record: $Path" }
    $hash = (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($hash -ne ([string]$Expected.sha256).ToLowerInvariant()) { throw "$Label hash differs from package record: $Path" }
    return $hash
}

function Add-InkQuayActivationTypes {
    if ('InkQuayQualification.NativePackageProbe' -as [type]) { return }
    Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
using System.Text;

namespace InkQuayQualification {
    [ComImport, Guid("45BA127D-10A8-46EA-8AB7-56EA9078943C")]
    internal class ApplicationActivationManagerClass { }

    [ComImport, Guid("2E941141-7F97-4756-BA1D-9DECDE894A3D"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    internal interface IApplicationActivationManager {
        [PreserveSig]
        int ActivateApplication([MarshalAs(UnmanagedType.LPWStr)] string appUserModelId,
            [MarshalAs(UnmanagedType.LPWStr)] string arguments, uint options, out uint processId);
        [PreserveSig]
        int ActivateForFile([MarshalAs(UnmanagedType.LPWStr)] string appUserModelId,
            IntPtr shellItemArray, [MarshalAs(UnmanagedType.LPWStr)] string verb, out uint processId);
        [PreserveSig]
        int ActivateForProtocol([MarshalAs(UnmanagedType.LPWStr)] string appUserModelId,
            IntPtr shellItemArray, out uint processId);
    }

    public static class ActivationBroker {
        public static uint Activate(string appUserModelId, string arguments) {
            var manager = (IApplicationActivationManager)new ApplicationActivationManagerClass();
            uint processId;
            int result = manager.ActivateApplication(appUserModelId, arguments, 0, out processId);
            if (result < 0) Marshal.ThrowExceptionForHR(result);
            if (processId == 0) throw new InvalidOperationException("Activation broker returned process ID zero.");
            return processId;
        }
    }

    public static class NativePackageProbe {
        [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr window);
        [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr window, int command);
        [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
        [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr window, out uint processId);
        private const int ERROR_SUCCESS = 0;
        private const int ERROR_INSUFFICIENT_BUFFER = 122;
        [DllImport("kernel32.dll", CharSet=CharSet.Unicode)]
        private static extern int GetPackageFullName(IntPtr process, ref uint length, StringBuilder packageFullName);

        public static string GetFullName(IntPtr process) {
            uint length = 0;
            int first = GetPackageFullName(process, ref length, null);
            if (first != ERROR_INSUFFICIENT_BUFFER || length == 0)
                throw new InvalidOperationException("Initial GetPackageFullName returned " + first + ", expected 122.");
            var value = new StringBuilder((int)length);
            int second = GetPackageFullName(process, ref length, value);
            if (second != ERROR_SUCCESS)
                throw new InvalidOperationException("Second GetPackageFullName returned " + second + ", expected 0.");
            return value.ToString();
        }
    }
}
'@
}

function Assert-InkQuayWindowEvidence($Snapshot) {
    if ($Snapshot.title -cne 'Unsaved Document - Scriblark' -or -not $Snapshot.visible -or $Snapshot.process_id -le 0 -or
        $Snapshot.width -lt 400 -or $Snapshot.height -lt 300 -or -not $Snapshot.screenshot_captured -or
        $Snapshot.screenshot_sha256 -cnotmatch '^[0-9a-f]{64}$' -or $Snapshot.sampled_colors -lt 16) {
        throw 'Missing exact rendered Scriblark window/screenshot evidence.'
    }
    # GTK may expose only its genuine root window. Record that limitation;
    # never claim a template/PDF interaction from a title or screenshot alone.
    $roots = @($Snapshot.controls | Where-Object {
        $_.name -ceq 'Unsaved Document - Scriblark' -and $_.control_type -ceq 'ControlType.Window' -and
        -not $_.offscreen -and $_.process_id -eq $Snapshot.process_id
    })
    if ($roots.Count -ne 1) { throw 'Expected one successfully observed owned GTK root window.' }

}

function Get-WindowQualification([Diagnostics.Process]$Process, [string]$OutputDirectory) {
    Add-Type -AssemblyName UIAutomationClient
    Add-Type -AssemblyName UIAutomationTypes
    $root = [Windows.Automation.AutomationElement]::FromHandle($Process.MainWindowHandle)
    if (-not $root) { throw 'UI Automation could not bind the activated main window.' }
    $rootBounds = $root.Current.BoundingRectangle
    if ($root.Current.Name -cne 'Unsaved Document - Scriblark' -or $root.Current.ProcessId -ne $Process.Id) { throw 'UIA root is not the exact owned Scriblark window.' }
    if ($root.Current.IsOffscreen -or $rootBounds.Width -le 0 -or $rootBounds.Height -le 0) { throw 'Activated main window is not visibly rendered.' }
    $topLevelWindows = [Collections.Generic.List[object]]::new()
    $processCondition = [Windows.Automation.PropertyCondition]::new([Windows.Automation.AutomationElement]::ProcessIdProperty, $Process.Id)
    $desktopWindows = [Windows.Automation.AutomationElement]::RootElement.FindAll([Windows.Automation.TreeScope]::Children, $processCondition)
    for ($index = 0; $index -lt $desktopWindows.Count; $index++) {
        $window = $desktopWindows.Item($index)
        $name = [string]$window.Current.Name
        $modal = $null
        if (-not $window.Current.IsOffscreen -and ($name -match '(?i)\b(error|exception|warning|traceback)\b' -or
            $window.Current.ClassName -ceq '#32770' -or
            ($window.TryGetCurrentPattern([Windows.Automation.WindowPattern]::Pattern,[ref]$modal) -and $modal.Current.IsModal))) {
            throw "Error/modal top-level surface detected: $name"
        }
        $topLevelWindows.Add([ordered]@{ name=$name; offscreen=[bool]$window.Current.IsOffscreen })
    }
    $items = [Collections.Generic.List[object]]::new()
    $actionable = 0
    $descendants = $root.FindAll([Windows.Automation.TreeScope]::Subtree, [Windows.Automation.Condition]::TrueCondition)
    if ($descendants.Count -gt 1000) { throw 'UIA window tree exceeds bounded capture.' }
    $limit = $descendants.Count
    for ($index = 0; $index -lt $limit; $index++) {
        $element = $descendants.Item($index)
        try {
            $name = [string]$element.Current.Name
            $control = [string]$element.Current.ControlType.ProgrammaticName
            $enabled = [bool]$element.Current.IsEnabled
            $offscreen = [bool]$element.Current.IsOffscreen
            if ($name -match '(?i)unhandled exception|traceback|fatal error|script error') {
                throw "Error surface detected in activated UI: $name"
            }
            if ($enabled -and -not $offscreen -and $name -and $control -match 'ControlType\.(Button|MenuItem|Edit|ComboBox|ListItem)') {
                $actionable++
            }
            $items.Add([ordered]@{ name=$name; control_type=$control; enabled=$enabled; offscreen=$offscreen; process_id=$element.Current.ProcessId })
        } catch {
            if ($_.Exception.Message -match '^Error surface detected') { throw }
        }
    }
    $treePath = Join-Path $OutputDirectory 'accessible-window-tree.json'
    Write-NewUtf8Json $treePath @($items)
    $screenshotCaptured = $false
    $screenshotError = $null
    $screenshotHash = $null
    $colors = [Collections.Generic.HashSet[int]]::new()
    try {
        Add-Type -AssemblyName System.Drawing
        Add-Type -AssemblyName System.Windows.Forms
        [InkQuayQualification.NativePackageProbe]::ShowWindow($Process.MainWindowHandle,9) | Out-Null
        [InkQuayQualification.NativePackageProbe]::SetForegroundWindow($Process.MainWindowHandle) | Out-Null
        Start-Sleep -Milliseconds 250
        [uint32]$foregroundPid=0
        [InkQuayQualification.NativePackageProbe]::GetWindowThreadProcessId(
            [InkQuayQualification.NativePackageProbe]::GetForegroundWindow(),[ref]$foregroundPid) | Out-Null
        if ($foregroundPid -ne $Process.Id) { throw 'Owned window is not foreground for screenshot.' }
        $rootBounds=$root.Current.BoundingRectangle
        $bounds = $rootBounds
        $rectangle=[Drawing.Rectangle]::new([int]$bounds.X,[int]$bounds.Y,[int]$bounds.Width,[int]$bounds.Height)
        if (-not [Windows.Forms.SystemInformation]::VirtualScreen.Contains($rectangle)) { throw 'Owned window is outside the visible desktop.' }
        $bitmap = [Drawing.Bitmap]::new([int][Math]::Ceiling($bounds.Width), [int][Math]::Ceiling($bounds.Height))
        $graphics = [Drawing.Graphics]::FromImage($bitmap)
        try {
            $graphics.CopyFromScreen([int]$bounds.X, [int]$bounds.Y, 0, 0, $bitmap.Size)
            $bitmap.Save((Join-Path $OutputDirectory 'qualification-window.png'), [Drawing.Imaging.ImageFormat]::Png)
            for ($y=0;$y -lt $bitmap.Height;$y+=7) { for ($x=0;$x -lt $bitmap.Width;$x+=7) { $colors.Add($bitmap.GetPixel($x,$y).ToArgb()) | Out-Null } }
            $screenshotHash=(Get-FileHash (Join-Path $OutputDirectory 'qualification-window.png') -Algorithm SHA256).Hash.ToLowerInvariant()
            $screenshotCaptured = $true
        } finally {
            $graphics.Dispose()
            $bitmap.Dispose()
        }
    } catch {
        $screenshotError = $_.Exception.Message
    }
    $snapshot = [ordered]@{
        title=$root.Current.Name; process_id=$Process.Id; visible=(-not $root.Current.IsOffscreen)
        width=$rootBounds.Width; height=$rootBounds.Height; controls=@($items)
        screenshot_sha256=$screenshotHash; sampled_colors=$colors.Count
        accessible_elements = $items.Count
        top_level_windows = @($topLevelWindows)
        actionable_controls_verified = ($actionable -gt 0)
        actionable_control_count = $actionable
        screenshot_captured = $screenshotCaptured
        screenshot_error = $screenshotError
        startup_limited = ($actionable -eq 0)
    }
    Write-NewUtf8Json (Join-Path $OutputDirectory 'window-observation.json') $snapshot
    Assert-InkQuayWindowEvidence $snapshot
    return $snapshot
}

function Write-NewUtf8Json([string]$Path, [object]$Value) {
    $bytes = [Text.UTF8Encoding]::new($false).GetBytes((ConvertTo-Json -InputObject $Value -Depth 20) + [Environment]::NewLine)
    $stream = [IO.FileStream]::new($Path, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
    try {
        $stream.Write($bytes, 0, $bytes.Length)
        $stream.Flush($true)
    } finally {
        $stream.Dispose()
    }
}

function Get-InkQuayHelperEvidence {
    $result=[ordered]@{}
    foreach($name in @('qualify-msix-install.ps1','qualify-workflow.ps1','WorkflowNative.cs','workflow_files.py','input_diagnostics.ps1')) {
        $path=Join-Path $PSScriptRoot $name
        Assert-NoReparsePath $path
        $result[$name]=@{bytes=(Get-Item -LiteralPath $path).Length;sha256=(Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()}
    }
    return $result
}

function Get-InkQuayIdentity([ValidateSet('qualification','store')][string]$Mode='qualification') {
    $identity = [ordered]@{
        packageName='Trieflow.InkQuay.Qualification'; publisher='CN=InkQuay-CI-Qualification'; version='1.0.1.0'
        architecture='x64'; applicationId='InkQuay'; executable='bin/Scriblark.exe'
        deviceFamily='Windows.Desktop'; minVersion='10.0.19041.0'; maxVersionTested='10.0.26100.0'; capability='runFullTrust'
    }
    if ($Mode -ceq 'store') {
        $identity.packageName='1659hashfunction.InkQuay'
        $identity.publisher='CN=B6A2631A-FD32-45CC-AE12-82466975F528'
    }
    return $identity
}
function Assert-InkQuayRecordIdentity($Record,[ValidateSet('qualification','store')][string]$Mode='qualification') {
    $expected=Get-InkQuayIdentity $Mode
    if ($Record.schemaVersion -cne 1 -or $Record.identityMode -cne $Mode -or
        $Record.qualificationIdentityOnly -isnot [bool] -or $Record.qualificationIdentityOnly -ne ($Mode -ceq 'qualification') -or
        $Record.storeIdentityUsed -isnot [bool] -or $Record.storeIdentityUsed -ne ($Mode -ceq 'store')) { throw 'Package identity mode/flags mismatch.' }
    foreach($field in @('signed','publicRelease','licenseClearanceClaimed','installationQualificationPassed')) {
        if($Record.$field -isnot [bool] -or $Record.$field -ne $false){throw "Unsigned unreleased package record required: $field"}
    }
    if (@($Record.identity.PSObject.Properties).Count -ne $expected.Count) { throw 'Unexpected identity fields.' }
    foreach($field in $expected.Keys) {
        if ($Record.identity.$field -isnot [string] -or $Record.identity.$field -cne $expected[$field]) { throw "Selected identity mismatch: $field" }
    }
}

. (Join-Path $PSScriptRoot 'input_diagnostics.ps1')

function Invoke-InkQuayInstallQualification([string]$PackagePath, [string]$RecordPath, [string]$SignToolPath, [string]$OutputPath, [switch]$CaptureCrashStack, [switch]$CaptureInputDiagnostics, [ValidateSet('qualification','store')][string]$IdentityMode='qualification') {
    $state = [ordered]@{
        package = $null; record = $null; output = $null; temporary = $null; signedCopy = $null
        publicCertificate = $null; certificate = $null; trustedCertificate = $null; trustAttempted = $false
        installed = $null; installedByUs = $false; process = $null; processOwned = $false; cleanupProcessExit = $null
        installAttempted = $false; brokerProcessId = 0; addCompleted = $false; ownedPackageFullName = $null; preflightPackageFullNames = @(); residualPackageFullNames = @(); processHandle = $null; processExit = $null
        activatedAtUtc = $null; verifiedExecutablePath = $null
        unsignedPackageSha256 = $null; signedPackageSha256 = $null; signTool = $null
        aumid = $null; processPackageFullName = $null; modules = @(); window = $null; workflow = $null
        executableSha256 = $null
        cleanClose = $false; uninstallVerified = $false
        inputDiagnosticsRequested = [bool]$CaptureInputDiagnostics; inputDiagnosticsPath = $null; inputDiagnosticsEvidence = $null
        inputDiagnosticsErrors = [Collections.Generic.List[string]]::new()
        observerRequested = [bool]$CaptureCrashStack; observerProcess = $null; observerDebugger = $null; observerAttached = $false
        observerNonce = $null; observerTarget = $null; observerStopped = $false; observerEvidence = $null
        observerErrors = [Collections.Generic.List[string]]::new()
    }
    $expectedIdentity = Get-InkQuayIdentity $IdentityMode

    $operations = [ordered]@{}
    $operations.Preflight = {
        if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT -or $env:CI -ne 'true') { throw 'Requires an isolated disposable Windows CI runner.' }
        foreach ($argument in @($PackagePath,$RecordPath,$SignToolPath,$OutputPath)) {
            if (-not $argument) { throw 'Package, package record, SignTool, and output are required.' }
        }
        $state.package = (Resolve-Path -LiteralPath $PackagePath).Path
        $recordFile = (Resolve-Path -LiteralPath $RecordPath).Path
        $state.signTool = (Resolve-Path -LiteralPath $SignToolPath).Path
        if ([IO.Path]::GetFileName($state.signTool) -ine 'signtool.exe') { throw 'Exact SignTool.exe path is required.' }
        $outputCandidate = [IO.Path]::GetFullPath($OutputPath)
        if (Test-Path -LiteralPath $outputCandidate) { throw 'Qualification output already exists and will not be replaced.' }
        New-Item -ItemType Directory -Path $outputCandidate -ErrorAction Stop | Out-Null
        $state.output = $outputCandidate
        $state.record = Get-Content -LiteralPath $recordFile -Raw -Encoding utf8 | ConvertFrom-Json
        if ($state.record.sourceCommit -cne $env:GITHUB_SHA) { throw 'Package source differs from this qualification run.' }
        Invoke-CheckedNative $env:INKQUAY_QUALIFICATION_PYTHON @(
            (Join-Path $PSScriptRoot 'verify_record.py'),'--record',$recordFile,'--package',$state.package,'--source-commit',$env:GITHUB_SHA,'--identity-mode',$IdentityMode)
        Assert-InkQuayRecordIdentity $state.record $IdentityMode
        $state.unsignedPackageSha256 = (Get-FileHash -LiteralPath $state.package -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($state.unsignedPackageSha256 -ne ([string]$state.record.containerVerification.package.sha256).ToLowerInvariant()) { throw 'Unsigned package hash differs from verified package record.' }
        $sdkVersion = [regex]::Escape([string]$state.record.makeAppx.sdkVersion)
        if ([string]$state.record.makeAppx.sdkVersion -cne '10.0.26100.0') { throw 'Only Windows SDK 10.0.26100.0 is qualified.' }
        Assert-FileMatchesRecord $state.record.makeAppx.path $state.record.makeAppx 'MakeAppx tool' | Out-Null
        if ($state.signTool -notmatch "(?i)[\\/]$sdkVersion[\\/]x64[\\/]signtool\.exe$") { throw 'SignTool does not match the exact qualified Windows SDK x64 directory.' }
        if ([IO.Path]::GetDirectoryName($state.signTool) -ine [IO.Path]::GetDirectoryName([string]$state.record.makeAppx.path)) { throw 'SignTool is not the exact sibling of the qualified MakeAppx tool.' }
        $state.signTool = [ordered]@{
            path = $state.signTool
            bytes = (Get-Item -LiteralPath $state.signTool).Length
            sha256 = (Get-FileHash -LiteralPath $state.signTool -Algorithm SHA256).Hash.ToLowerInvariant()
            sdk_version = [string]$state.record.makeAppx.sdkVersion
        }
        $existing = @(Get-AppxPackage -Name $expectedIdentity.packageName -ErrorAction Stop)
        $state.preflightPackageFullNames = @($existing | ForEach-Object { [string]$_.PackageFullName })
        if ($existing.Count -gt 0) { throw 'A matching Scriblark qualification package is already installed; refusing to replace or remove it.' }
    }.GetNewClosure()

    $operations.PrepareSignedCopy = {
        $runnerTemp = if ($env:RUNNER_TEMP) { $env:RUNNER_TEMP } else { [IO.Path]::GetTempPath() }
        $temporaryCandidate = Join-Path $runnerTemp ('.inkquay-install-' + [guid]::NewGuid().ToString('N'))
        New-Item -ItemType Directory -Path $temporaryCandidate -ErrorAction Stop | Out-Null
        $state.temporary = $temporaryCandidate
        $state.signedCopy = Join-Path $state.temporary 'Scriblark.Qualification.signed.msix'
        [IO.File]::Copy($state.package, $state.signedCopy, $false)
        $state.publicCertificate = Join-Path $state.temporary 'Scriblark.Qualification.public.cer'
        $state.certificate = New-SelfSignedCertificate -Type Custom -KeyUsage DigitalSignature -KeyExportPolicy NonExportable -KeySpec Signature `
            -CertStoreLocation 'Cert:\CurrentUser\My' -TextExtension @('2.5.29.37={text}1.3.6.1.5.5.7.3.3','2.5.29.19={text}') `
            -Subject $expectedIdentity.publisher -FriendlyName 'Scriblark ephemeral CI qualification' -NotAfter (Get-Date).AddHours(12)
        Export-Certificate -Cert $state.certificate -FilePath $state.publicCertificate -Force | Out-Null
        $state.trustAttempted = $true
        $state.trustedCertificate = Import-Certificate -FilePath $state.publicCertificate -CertStoreLocation 'Cert:\LocalMachine\TrustedPeople'
        foreach ($arguments in @(
            @('sign','/fd','SHA256','/sha1',$state.certificate.Thumbprint,'/s','My',$state.signedCopy),
            @('verify','/pa','/all','/v',$state.signedCopy)
        )) {
            if ((Get-Item -LiteralPath $state.signTool.path).Length -ne $state.signTool.bytes -or
                (Get-FileHash -LiteralPath $state.signTool.path -Algorithm SHA256).Hash.ToLowerInvariant() -ne $state.signTool.sha256) {
                throw 'SignTool changed after qualification preflight.'
            }
            Invoke-CheckedNative $state.signTool.path $arguments
        }
        if ((Get-Item -LiteralPath $state.signTool.path).Length -ne $state.signTool.bytes -or
            (Get-FileHash -LiteralPath $state.signTool.path -Algorithm SHA256).Hash.ToLowerInvariant() -ne $state.signTool.sha256) {
            throw 'SignTool changed during qualification signing.'
        }
        $signature = Get-AuthenticodeSignature -LiteralPath $state.signedCopy
        if ($signature.Status -ne [Management.Automation.SignatureStatus]::Valid -or $signature.SignerCertificate.Thumbprint -ne $state.certificate.Thumbprint) {
            throw "Test-copy signature is not valid for the ephemeral certificate: $($signature.Status)"
        }
        if ((Get-FileHash -LiteralPath $state.package -Algorithm SHA256).Hash.ToLowerInvariant() -ne $state.unsignedPackageSha256) { throw 'Unsigned source package changed during signing.' }
        $state.signedPackageSha256 = (Get-FileHash -LiteralPath $state.signedCopy -Algorithm SHA256).Hash.ToLowerInvariant()
    }.GetNewClosure()

    $operations.Install = {
        $state.installAttempted = $true
        Add-AppxPackage -Path $state.signedCopy -ErrorAction Stop
        $state.addCompleted = $true
        $matches = @(Get-AppxPackage -Name $expectedIdentity.packageName -ErrorAction Stop)
        if ($matches.Count -ne 1) { throw 'Expected exactly one installed qualification package.' }
        $candidate = $matches[0]
        if ([string]$candidate.Name -cne $expectedIdentity.packageName -or
            [string]$candidate.Publisher -cne $expectedIdentity.publisher -or
            [string]$candidate.Version -cne $expectedIdentity.version -or
            [string]$candidate.Architecture -cne 'X64' -or
            -not ([string]$candidate.PackageFullName).StartsWith($expectedIdentity.packageName + '_' + $expectedIdentity.version + '_x64_', [StringComparison]::Ordinal) -or
            -not [string]$candidate.PackageFamilyName) {
            throw 'Installed publisher/version/architecture differs from qualification identity.'
        }
        # Ownership is established only after our Add succeeds and one exact
        # expected registration is observed. A failed/partial Add cannot confer it.
        $state.installed = $candidate
        $state.ownedPackageFullName = [string]$candidate.PackageFullName
        $state.installedByUs = $true
        $state.aumid = [string]$state.installed.PackageFamilyName + '!' + $expectedIdentity.applicationId
        foreach ($entry in $state.record.payload.PSObject.Properties) {
            $relative = $entry.Name
            $expected = Get-RecordPayloadEntry $state.record $relative
            $hash = Assert-FileMatchesRecord (Join-Path $state.installed.InstallLocation ($relative -replace '/', [IO.Path]::DirectorySeparatorChar)) $expected $relative
            if ($relative -eq 'bin/Scriblark.exe') { $state.executableSha256 = $hash }

        }
    }.GetNewClosure()

    $operations.ActivateAndVerify = {
        Invoke-CheckedNative $env:INKQUAY_QUALIFICATION_PYTHON @(
            (Join-Path $PSScriptRoot 'verify_record.py'),'--record',$RecordPath,'--package',$state.package,
            '--source-commit',$env:GITHUB_SHA,'--identity-mode',$IdentityMode,'--installed-root',$state.installed.InstallLocation)
        Add-InkQuayActivationTypes
        $state.activatedAtUtc = [DateTime]::UtcNow
        $diagnosticLaunch=Get-InkInputDiagnosticLaunch $state.inputDiagnosticsRequested $state.temporary
        $activationArguments=$null
        if($diagnosticLaunch){$state.inputDiagnosticsPath=$diagnosticLaunch.path;$activationArguments=$diagnosticLaunch.arguments}
        $processId = [InkQuayQualification.ActivationBroker]::Activate($state.aumid,$activationArguments)
        $state.brokerProcessId = [int]$processId
        $state.process = [Diagnostics.Process]::GetProcessById([int]$processId)
        $state.processHandle = $state.process.SafeHandle
        if ($state.processHandle.IsInvalid -or $state.processHandle.IsClosed) { throw 'Cannot retain the live broker-activated process handle.' }
        $expectedExecutable = Get-CanonicalPath (Join-Path $state.installed.InstallLocation 'bin/Scriblark.exe')
        if ((Get-CanonicalPath $state.process.MainModule.FileName) -ine $expectedExecutable) { throw 'Broker returned an executable outside the owned installed path.' }
        $state.processPackageFullName = [InkQuayQualification.NativePackageProbe]::GetFullName($state.process.Handle)
        if ($state.processPackageFullName -cne $state.ownedPackageFullName) { throw 'Broker process does not have the exact owned package identity.' }
        Assert-FileMatchesRecord $expectedExecutable (Get-RecordPayloadEntry $state.record 'bin/Scriblark.exe') 'Activated executable' | Out-Null
        $state.processOwned = $true
        $state.verifiedExecutablePath = $expectedExecutable
        $deadline = [DateTime]::UtcNow.AddSeconds(30)
        do {
            Start-Sleep -Milliseconds 250
            $state.process.Refresh()
            if ($state.process.HasExited) { throw "Activated Scriblark exited during startup: $($state.process.ExitCode)" }
        } until ($state.process.MainWindowHandle -ne 0 -or [DateTime]::UtcNow -ge $deadline)
        if ($state.process.MainWindowHandle -eq 0) { throw 'Activated Scriblark did not create a main window.' }
        if ($state.process.MainWindowTitle -cne 'Unsaved Document - Scriblark') { throw "Unexpected activated main-window title: $($state.process.MainWindowTitle)" }
        $state.processPackageFullName = [InkQuayQualification.NativePackageProbe]::GetFullName($state.process.Handle)
        if ($state.processPackageFullName -cne [string]$state.installed.PackageFullName) { throw 'Activated process does not own the exact installed package full name.' }
        Start-Sleep -Seconds 3
        $state.process.Refresh()
        if ($state.process.HasExited -or $state.process.MainWindowHandle -eq 0 -or $state.process.MainWindowTitle -cne 'Unsaved Document - Scriblark') { throw 'Activated Scriblark did not survive the stable-window interval.' }
        # Keep this block in the activation operation's captured state scope.
        # GetNewClosure here creates another module and loses the inherited state.
        $collectModules = { param([string]$EvidenceName)
            $installRoot = Get-CanonicalPath $state.installed.InstallLocation
            $windowsRoot = Get-CanonicalPath $env:SystemRoot
            $modules = [Collections.Generic.List[object]]::new()
            $requiredRuntime = @{}
            foreach ($entry in $state.record.runtime.PSObject.Properties) { $requiredRuntime[[string]$entry.Value] = $false }
            foreach ($module in @($state.process.Modules)) {
                Assert-NoReparsePath $module.FileName
                $path = Get-CanonicalPath $module.FileName
                $platformSignature = $null
                if (Test-PathInside $path $installRoot) {
                    $relative = $path.Substring($installRoot.Length).TrimStart('\','/').Replace('\','/')
                    $expected = Get-RecordPayloadEntry $state.record $relative
                    $hash = Assert-FileMatchesRecord $path $expected "Loaded module $relative"
                    if ($requiredRuntime.ContainsKey($relative)) { $requiredRuntime[$relative] = $true }
                    $origin = 'package'
                } elseif (Test-PathInside $path $windowsRoot) {
                    $relative = $null
                    $hash = (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()
                    $origin = 'windows'
                } else {
                    $defenderRoot = Join-Path ([Environment]::GetFolderPath('CommonApplicationData')) 'Microsoft/Windows Defender/Platform'
                    $platformSignature = Get-VerifiedDefenderModuleEvidence -Path $path -PlatformRoot $defenderRoot
                    $relative = $null
                    $hash = $platformSignature.sha256
                    $origin = 'microsoft_defender_signed_platform'
                }
                $modules.Add([ordered]@{ name=$module.ModuleName; path=$path; origin=$origin; relative_path=$relative; sha256=$hash; platform_signature=$platformSignature })
            }
            foreach ($relative in $requiredRuntime.Keys) { if (-not $requiredRuntime[$relative]) { throw "Activated process did not load required packaged GTK/Poppler runtime: $relative" } }
            $state.modules = @($modules)
            Write-NewUtf8Json (Join-Path $state.output $EvidenceName) $state.modules
        }
        & $collectModules 'loaded-modules.json'
        $state.window = Get-WindowQualification $state.process $state.output
        . (Join-Path $PSScriptRoot 'crash_observer.ps1')
        try { Start-InkCrashObserver $state (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path }
        catch { Add-InkObserverError $state ('Unexpected observer start: '+$_.Exception.Message) }
        . (Join-Path $PSScriptRoot 'qualify-workflow.ps1')
        try { $state.workflow = Invoke-InkQuayWorkflow $state (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path }
        finally {
            try { Stop-InkCrashObserver $state }
            catch { Add-InkObserverError $state ('Unexpected observer stop: '+$_.Exception.Message) }
        }
        if ($state.workflow.passed -ne $true) { throw 'Installed template/PDF consumer workflow did not pass.' }
        & $collectModules 'workflow-loaded-modules.json'
        $state.process.Refresh()
        if ($state.process.HasExited -or $state.process.MainWindowHandle -eq 0) { throw 'Activated Scriblark did not survive the stable-window interval.' }
    }.GetNewClosure()

    $operations.CloseCleanly = {
        if (-not $state.process.CloseMainWindow()) { throw 'Activated Scriblark refused a normal main-window close request.' }
        $state.processExit = Get-InkQuayProcessExitEvidence $state.process 15000
        if (-not $state.processExit.normal_exit) { throw ('Activated Scriblark normal-close observation failed: ' + ($state.processExit | ConvertTo-Json -Compress)) }
        $state.cleanClose = $true
    }.GetNewClosure()

    $operations.UninstallAndVerify = {
        if (-not $state.installedByUs -or -not $state.ownedPackageFullName) { throw 'Exact installed package ownership was not established.' }
        Remove-AppxPackage -Package $state.ownedPackageFullName -ErrorAction Stop
        if (@(Get-AppxPackage -Name $expectedIdentity.packageName -ErrorAction Stop).Count -ne 0) { throw 'Package registration remains after uninstall.' }
        $state.uninstallVerified = $true
    }.GetNewClosure()

    $operations.StopOwnedProcess = {
        # Retain and use the original attached Process/OS handle, never reacquire
        # a potentially recycled PID during cleanup.
        try {
            if ($state.observerRequested -and -not $state.observerStopped) {
                . (Join-Path $PSScriptRoot 'crash_observer.ps1')
                try { Stop-InkCrashObserver $state }
                catch { Add-InkObserverError $state ('Unexpected observer cleanup: '+$_.Exception.Message) }
            }
            if ($state.processOwned -and $state.process -and $state.processHandle) {
                if (-not $state.process.HasExited) { $state.process.Kill() }
                $state.cleanupProcessExit = Get-InkQuayProcessExitEvidence $state.process 10000
                if (-not $state.cleanupProcessExit.wait_completed -or $state.cleanupProcessExit.observation_error) { throw ('Owned process cleanup failed: ' + ($state.cleanupProcessExit | ConvertTo-Json -Compress)) }
            }
        } finally {
            if ($state.process) { $state.process.Dispose() }
        }
    }.GetNewClosure()

    $operations.RemoveOwnedPackage = {
        if ($state.installAttempted) {
            $remaining = @(Get-AppxPackage -Name $expectedIdentity.packageName -ErrorAction Stop)
            $state.residualPackageFullNames = @($remaining | ForEach-Object { [string]$_.PackageFullName })
            if ($state.installedByUs -and $state.ownedPackageFullName) {
                $owned = @($remaining | Where-Object { [string]$_.PackageFullName -ceq $state.ownedPackageFullName })
                if ($owned.Count -gt 1) { throw 'Ambiguous duplicate registration state; all registrations preserved.' }
                if ($owned.Count -eq 1) { Remove-AppxPackage -Package $state.ownedPackageFullName -ErrorAction Stop }
            }
            # A matching registration after a failed Add may belong to another
            # invocation. Report residue without removing identity-tuple matches.
            $remaining = @(Get-AppxPackage -Name $expectedIdentity.packageName -ErrorAction Stop)
            $state.residualPackageFullNames = @($remaining | ForEach-Object { [string]$_.PackageFullName })
            if ($remaining.Count) { throw ('Unowned or unresolved package registrations preserved: ' + ($state.residualPackageFullNames -join ', ')) }
            if ($state.addCompleted -and -not $state.installedByUs) {
                throw 'Registration cleanup remains uncertain: Add completed but exact ownership was never observed; registrations were preserved.'
            }
        }
    }.GetNewClosure()

    $operations.RemoveTrustedCertificate = {
        if ($state.trustAttempted -and $state.certificate) {
            $path = 'Cert:\LocalMachine\TrustedPeople\' + $state.certificate.Thumbprint
            if (Test-Path -LiteralPath $path) { Remove-Item -LiteralPath $path -Force -ErrorAction Stop }
            if (Test-Path -LiteralPath $path) { throw 'Trusted public certificate remains after cleanup.' }
        }
    }.GetNewClosure()

    $operations.RemovePersonalCertificate = {
        if ($state.certificate) {
            $path = 'Cert:\CurrentUser\My\' + $state.certificate.Thumbprint
            if (Test-Path -LiteralPath $path) { Remove-Item -LiteralPath $path -DeleteKey -Force -ErrorAction Stop }
            if (Test-Path -LiteralPath $path) { throw 'Ephemeral personal certificate remains after cleanup.' }
        }
    }.GetNewClosure()

    $operations.RemoveTemporaryFiles = {
        # The original owned process cleanup has already run. Diagnostic publication
        # failures remain secondary and cannot replace primary/cleanup evidence.
        try { Save-InkInputDiagnostics $state }
        catch { $state.inputDiagnosticsErrors.Add($_.Exception.Message) }
        if ($state.temporary -and (Test-Path -LiteralPath $state.temporary)) {
            Remove-Item -LiteralPath $state.temporary -Recurse -Force -ErrorAction Stop
            if (Test-Path -LiteralPath $state.temporary) { throw 'Temporary signed-copy directory remains after cleanup.' }
        }
    }.GetNewClosure()

    $result = Invoke-InkQuayQualificationCore -Operations $operations
    if (-not $state.output) {
        # An output collision is intentionally not overwritten and cannot receive evidence.
        throw $result.primary_error
    }
    $evidenceErrors = [Collections.Generic.List[string]]::new()
    $unsignedUnchanged = $false
    if ($state.unsignedPackageSha256 -and $state.package) {
        try {
            $unsignedUnchanged = (Get-FileHash -LiteralPath $state.package -Algorithm SHA256 -ErrorAction Stop).Hash.ToLowerInvariant() -eq $state.unsignedPackageSha256
            if (-not $unsignedUnchanged) { $evidenceErrors.Add('Unsigned package changed after qualification.') }
        } catch {
            $evidenceErrors.Add('Unsigned package final verification failed: ' + $_.Exception.Message)
        }
    } elseif ($result.installation_qualification_passed) {
        $evidenceErrors.Add('Successful core qualification did not retain the unsigned package identity.')
    }
    $helperEvidence=$null
    try { $helperEvidence=Get-InkQuayHelperEvidence }
    catch { $evidenceErrors.Add('Qualification helper observation failed: ' + $_.Exception.Message) }
    $coreCompleted = $result.installation_qualification_passed -and $unsignedUnchanged -and $evidenceErrors.Count -eq 0
    $qualificationPassed = $coreCompleted -and -not $state.observerRequested -and -not $state.inputDiagnosticsRequested
    $evidence = [ordered]@{
        schema_version = 1
        generated_at_utc = [DateTime]::UtcNow.ToString('o')
        source_commit = if ($state.record) { [string]$state.record.sourceCommit } else { $null }
        identity_mode = $IdentityMode
        workflow_run_id = $env:GITHUB_RUN_ID
        workflow_run_attempt = $env:GITHUB_RUN_ATTEMPT
        qualification_helpers = $helperEvidence
        qualification_identity_only = ($IdentityMode -ceq 'qualification')
        identity = $expectedIdentity
        aumid = $state.aumid
        package_full_name = if ($state.installed) { [string]$state.installed.PackageFullName } else { $null }
        add_appx_completed = $state.addCompleted
        registration_ownership_established = $state.installedByUs
        owned_package_full_name = $state.ownedPackageFullName
        preflight_package_full_names = @($state.preflightPackageFullNames)
        residual_package_full_names = @($state.residualPackageFullNames)
        activated_process_package_full_name = $state.processPackageFullName
        unsigned_package_sha256 = $state.unsignedPackageSha256
        signed_copy_sha256 = $state.signedPackageSha256
        unsigned_package_unchanged = $unsignedUnchanged
        signtool = $state.signTool
        certificate_private_key_exported = $false
        executable_sha256 = $state.executableSha256
        loaded_module_count = @($state.modules).Count
        window = $state.window
        process_exit = $state.processExit
        cleanup_process_exit = $state.cleanupProcessExit
        process_identity_ownership_established = $state.processOwned
        clean_close_verified = $state.cleanClose
        uninstall_verified = $state.uninstallVerified
        installation_qualification_passed = $qualificationPassed
        diagnostic_observer_requested = $state.observerRequested
        diagnostic_observer_attached = $state.observerAttached
        diagnostic_run_completed = (($state.observerRequested -or $state.inputDiagnosticsRequested) -and $coreCompleted)
        diagnostic_input_requested = $state.inputDiagnosticsRequested
        input_diagnostics = $state.inputDiagnosticsEvidence
        input_diagnostic_errors = @($state.inputDiagnosticsErrors)
        diagnostic_observer = $state.observerEvidence
        observer_diagnostic_errors = @($state.observerErrors)
        workflow = $state.workflow
        workflow_acceptance = ($qualificationPassed -and $null -ne $state.workflow -and $state.workflow.passed -eq $true)
        template_pdf_workflow_tested = ($qualificationPassed -and $null -ne $state.workflow -and $state.workflow.passed -eq $true)
        interactive_pdf_workflows_verified = ($qualificationPassed -and $null -ne $state.workflow -and $state.workflow.passed -eq $true)
        physical_tablet_tested = $false
        upgrade_tested = $false
        wack_tested = $false
        store_identity_used = ($IdentityMode -ceq 'store')
        public_release = $false
        primary_error = $result.primary_error
        cleanup_errors = @($result.cleanup_errors)
        evidence_errors = @($evidenceErrors)
    }
    try {
        Write-NewUtf8Json (Join-Path $state.output 'installation-qualification.json') $evidence
    } catch {
        throw "Could not preserve qualification JSON: $($_.Exception.Message). Primary: $($result.primary_error); cleanup: $($result.cleanup_errors -join '; '); evidence: $($evidenceErrors -join '; ')"
    }
    if (-not $coreCompleted) {
        throw "Scriblark installation qualification failed. Primary: $($result.primary_error); cleanup: $($result.cleanup_errors -join '; '); evidence: $($evidenceErrors -join '; ')"
    }
    if ($state.observerRequested -or $state.inputDiagnosticsRequested) { Write-Output 'DIAGNOSTIC ONLY: consumer acceptance remains false and requires an uninstrumented run.' }
    else { Write-Output 'PASS: broker-activated exact package, verified owned modules/window/close, uninstalled, and cleaned certificate state.' }
}

if (-not $LibraryOnly) {
    try {
        Invoke-InkQuayInstallQualification -PackagePath $Package -RecordPath $PackageRecord -SignToolPath $SignTool -OutputPath $Output -CaptureCrashStack:$CaptureCrashStack -CaptureInputDiagnostics:$CaptureInputDiagnostics -IdentityMode $IdentityMode
    } catch {
        Write-Error $_
        exit 1
    }
}
