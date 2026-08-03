[CmdletBinding()]
param(
    [ValidateRange(10, 10000)]
    [int]$ReplacementCount = 250
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$skillRoot = Split-Path -Parent $PSScriptRoot
$supervisor = Join-Path $skillRoot 'scripts\long-run-supervisor.ps1'
$tokens = $null
$parseErrors = $null
$ast = [Management.Automation.Language.Parser]::ParseFile($supervisor, [ref]$tokens, [ref]$parseErrors)
if (@($parseErrors).Count -ne 0) { throw 'Cannot load functions from a script with parse errors.' }

$functionTexts = @{}
foreach ($name in @('Write-JsonAtomic', 'Read-JsonFile')) {
    $functionAst = $ast.Find({
        param($node)
        $node -is [Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq $name
    }, $true)
    if ($null -eq $functionAst) { throw "Function not found: $name" }
    $functionTexts[$name] = $functionAst.Extent.Text
    Invoke-Expression $functionAst.Extent.Text
}

$testRoot = Join-Path $skillRoot ('.atomic-write-test-' + [Guid]::NewGuid().ToString('N'))
$statePath = Join-Path $testRoot 'state.json'
$holderReady = Join-Path $testRoot 'holder.ready'
$readerReady = Join-Path $testRoot 'reader.ready'
$readerStop = Join-Path $testRoot 'reader.stop'
$holderJob = $null
$readerJob = $null

try {
    [void](New-Item -ItemType Directory -Path $testRoot)
    Write-JsonAtomic -Path $statePath -Value ([ordered]@{ sequence = 0; payload = 'initial' })

    # A foreign reader without FileShare.Delete reproduces the Windows rename race.
    $holderJob = Start-Job -ArgumentList $statePath, $holderReady -ScriptBlock {
        param($Path, $ReadyPath)
        $stream = [IO.File]::Open($Path, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::ReadWrite)
        try {
            [IO.File]::WriteAllText($ReadyPath, 'ready')
            Start-Sleep -Milliseconds 400
        }
        finally { $stream.Dispose() }
    }
    $readyLimit = [DateTimeOffset]::UtcNow.AddSeconds(5)
    while (-not (Test-Path -LiteralPath $holderReady) -and [DateTimeOffset]::UtcNow -lt $readyLimit) {
        Start-Sleep -Milliseconds 10
    }
    if (-not (Test-Path -LiteralPath $holderReady)) { throw 'Timed out waiting for the deterministic file holder.' }
    Write-JsonAtomic -Path $statePath -Value ([ordered]@{ sequence = 1; payload = 'held-reader-replacement' })
    [void](Wait-Job -Job $holderJob -Timeout 5)
    if ($holderJob.State -ne 'Completed') { throw "File-holder job ended in state $($holderJob.State)." }
    [void](Receive-Job -Job $holderJob -ErrorAction Stop)

    # Exercise the production reader concurrently with many exact production writes.
    $readerJob = Start-Job -ArgumentList $statePath, $readerReady, $readerStop, $functionTexts['Read-JsonFile'] -ScriptBlock {
        param($Path, $ReadyPath, $StopPath, $ReadFunctionText)
        Set-StrictMode -Version Latest
        $ErrorActionPreference = 'Stop'
        Invoke-Expression $ReadFunctionText
        $reads = 0
        $failures = [Collections.Generic.List[string]]::new()
        [IO.File]::WriteAllText($ReadyPath, 'ready')
        while (-not (Test-Path -LiteralPath $StopPath)) {
            try {
                $value = Read-JsonFile -Path $Path
                if ($null -eq $value.sequence) { throw 'Parsed state has no sequence.' }
                $reads++
            }
            catch { $failures.Add($_.Exception.Message) }
        }
        [pscustomobject]@{ Reads = $reads; Failures = @($failures) }
    }
    $readyLimit = [DateTimeOffset]::UtcNow.AddSeconds(5)
    while (-not (Test-Path -LiteralPath $readerReady) -and [DateTimeOffset]::UtcNow -lt $readyLimit) {
        Start-Sleep -Milliseconds 10
    }
    if (-not (Test-Path -LiteralPath $readerReady)) { throw 'Timed out waiting for the concurrent reader.' }

    for ($sequence = 2; $sequence -le $ReplacementCount; $sequence++) {
        Write-JsonAtomic -Path $statePath -Value ([ordered]@{ sequence = $sequence; payload = ('value-' + $sequence) })
    }
    [IO.File]::WriteAllText($readerStop, 'stop')
    [void](Wait-Job -Job $readerJob -Timeout 10)
    if ($readerJob.State -ne 'Completed') { throw "Concurrent-reader job ended in state $($readerJob.State)." }
    $readerResult = Receive-Job -Job $readerJob -ErrorAction Stop
    if ([int]$readerResult.Reads -le 0) { throw 'Concurrent reader completed no reads.' }
    if (@($readerResult.Failures).Count -ne 0) {
        throw "Concurrent reader observed invalid state: $(@($readerResult.Failures)[0])"
    }
    $final = Read-JsonFile -Path $statePath
    if ([int]$final.sequence -ne $ReplacementCount) {
        throw "Final sequence mismatch: $($final.sequence)"
    }

    [pscustomobject]@{
        deterministicHeldReaderReplacement = 'passed'
        replacements = $ReplacementCount
        concurrentReads = [int]$readerResult.Reads
        invalidReads = @($readerResult.Failures).Count
        finalSequence = [int]$final.sequence
    } | ConvertTo-Json -Compress
}
finally {
    foreach ($job in @($holderJob, $readerJob)) {
        if ($null -ne $job) {
            if ($job.State -in @('Running', 'NotStarted')) { Stop-Job -Job $job -ErrorAction SilentlyContinue }
            Remove-Job -Job $job -Force -ErrorAction SilentlyContinue
        }
    }
    if (Test-Path -LiteralPath $testRoot -PathType Container) {
        $resolvedSkill = [IO.Path]::GetFullPath($skillRoot).TrimEnd('\') + '\'
        $resolvedTest = [IO.Path]::GetFullPath($testRoot).TrimEnd('\')
        if (-not $resolvedTest.StartsWith($resolvedSkill, [StringComparison]::OrdinalIgnoreCase) -or
            [IO.Path]::GetFileName($resolvedTest) -notlike '.atomic-write-test-*') {
            throw "Refusing cleanup of unexpected path: $resolvedTest"
        }
        Remove-Item -LiteralPath $resolvedTest -Recurse -Force
    }
}
