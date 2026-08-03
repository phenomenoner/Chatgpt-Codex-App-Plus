[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
if (Test-Path Variable:\PSNativeCommandUseErrorActionPreference) {
    $PSNativeCommandUseErrorActionPreference = $false
}

$skillRoot = Split-Path -Parent $PSScriptRoot
$supervisor = Join-Path $skillRoot 'scripts\long-run-supervisor.ps1'
$testRoot = Join-Path $skillRoot ('.smoke-tasks-' + [Guid]::NewGuid().ToString('N'))
$hostPath = (Get-Process -Id $PID).Path
$launches = @()
$cleanupSafe = $false

function Invoke-OneWait {
    param(
        [Parameter(Mandatory = $true)][string]$TaskDirectory,
        [Parameter(Mandatory = $true)][int]$CompletedExitCode
    )

    $output = @(& $hostPath -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File $supervisor `
        -Action Wait -TaskDirectory $TaskDirectory -PollSeconds 2 -CompletedExitCode $CompletedExitCode)
    [pscustomobject]@{
        Output = $output
        WrapperExitCode = $LASTEXITCODE
        Receipt = (($output -join "`n") | ConvertFrom-Json)
    }
}

try {
    $completedLaunch = (& $supervisor -Action Start -Command 'Start-Sleep -Seconds 3; exit 0' `
        -TaskRoot $testRoot -ExpectedMinutes 5 -DeadlineMinutes 10 -StallMinutes 5 -HeartbeatSeconds 2 | ConvertFrom-Json)
    $launches += $completedLaunch
    $completed = Invoke-OneWait -TaskDirectory $completedLaunch.taskDirectory -CompletedExitCode 0
    if ($completed.WrapperExitCode -ne 0 -or $completed.Output.Count -ne 1 -or
        $completed.Receipt.condition -ne 'completed' -or $completed.Receipt.exitCode -ne 0) {
        throw 'Completed probe contract mismatch.'
    }
    if ($completedLaunch.waitCommand -notmatch [regex]::Escape('-CompletedExitCode 0')) {
        throw 'Start waitCommand did not advertise wrapper-safe completion.'
    }

    $legacyLaunch = (& $supervisor -Action Start -Command 'exit 0' `
        -TaskRoot $testRoot -ExpectedMinutes 5 -DeadlineMinutes 10 -StallMinutes 5 -HeartbeatSeconds 2 | ConvertFrom-Json)
    $launches += $legacyLaunch
    $legacy = Invoke-OneWait -TaskDirectory $legacyLaunch.taskDirectory -CompletedExitCode 10
    if ($legacy.WrapperExitCode -ne 10 -or $legacy.Output.Count -ne 1 -or
        $legacy.Receipt.condition -ne 'completed' -or $legacy.Receipt.exitCode -ne 0) {
        throw 'Legacy completed-exit-code probe contract mismatch.'
    }

    $failedLaunch = (& $supervisor -Action Start -Command 'exit 7' `
        -TaskRoot $testRoot -ExpectedMinutes 5 -DeadlineMinutes 10 -StallMinutes 5 -HeartbeatSeconds 2 | ConvertFrom-Json)
    $launches += $failedLaunch
    $failed = Invoke-OneWait -TaskDirectory $failedLaunch.taskDirectory -CompletedExitCode 0
    if ($failed.WrapperExitCode -ne 11 -or $failed.Output.Count -ne 1 -or
        $failed.Receipt.condition -ne 'failed' -or $failed.Receipt.exitCode -ne 7) {
        throw 'Failed probe contract mismatch.'
    }

    foreach ($launch in $launches) {
        $state = Get-Content -Raw -LiteralPath (Join-Path $launch.taskDirectory 'state.json') | ConvertFrom-Json
        if ($state.status -notin @('completed', 'failed', 'stalled', 'deadline', 'interrupted')) {
            throw "Task is not terminal: $($launch.taskDirectory)"
        }
        $worker = Get-Process -Id ([int]$state.workerPid) -ErrorAction SilentlyContinue
        if ($null -ne $worker) {
            Wait-Process -Id $worker.Id -Timeout 5 -ErrorAction SilentlyContinue
        }
        if ($null -ne (Get-Process -Id ([int]$state.workerPid) -ErrorAction SilentlyContinue)) {
            throw "Worker remains active: $($state.workerPid)"
        }
    }

    $cleanupSafe = $true
    [pscustomobject]@{
        startWaitCommandHasCompletedExitZero = $true
        completed = [ordered]@{
            wrapperExitCode = $completed.WrapperExitCode
            outputRecordCount = $completed.Output.Count
            condition = $completed.Receipt.condition
            processExitCode = $completed.Receipt.exitCode
        }
        legacyCompleted = [ordered]@{
            wrapperExitCode = $legacy.WrapperExitCode
            outputRecordCount = $legacy.Output.Count
            condition = $legacy.Receipt.condition
            processExitCode = $legacy.Receipt.exitCode
        }
        failed = [ordered]@{
            wrapperExitCode = $failed.WrapperExitCode
            outputRecordCount = $failed.Output.Count
            condition = $failed.Receipt.condition
            processExitCode = $failed.Receipt.exitCode
        }
    } | ConvertTo-Json -Depth 5
}
finally {
    if ($cleanupSafe -and (Test-Path -LiteralPath $testRoot -PathType Container)) {
        $resolvedSkill = [IO.Path]::GetFullPath($skillRoot).TrimEnd('\') + '\'
        $resolvedTest = [IO.Path]::GetFullPath($testRoot).TrimEnd('\')
        if (-not $resolvedTest.StartsWith($resolvedSkill, [StringComparison]::OrdinalIgnoreCase) -or
            [IO.Path]::GetFileName($resolvedTest) -notlike '.smoke-tasks-*') {
            throw "Refusing cleanup of unexpected path: $resolvedTest"
        }
        Remove-Item -LiteralPath $resolvedTest -Recurse -Force
    }
}
