[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$Workspace,

    [Parameter(Mandatory = $true)]
    [string]$PromptFile,

    [Parameter(Mandatory = $true)]
    [string]$OutputDirectory,

    [Parameter(Mandatory = $true)]
    [string[]]$TargetPath,

    [ValidateRange(1, 120)]
    [int]$ExpectedMaxMinutes = 15,

    [ValidateSet('low', 'medium', 'high', 'xhigh', 'max', 'ultra')]
    [string]$ReasoningEffort = 'max'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

function Resolve-FullPath {
    param([Parameter(Mandatory = $true)][string]$Path)
    return [System.IO.Path]::GetFullPath($Path)
}

function Test-IsWithin {
    param(
        [Parameter(Mandatory = $true)][string]$Candidate,
        [Parameter(Mandatory = $true)][string]$Parent
    )
    $parentWithSeparator = $Parent.TrimEnd([System.IO.Path]::DirectorySeparatorChar, [System.IO.Path]::AltDirectorySeparatorChar) + [System.IO.Path]::DirectorySeparatorChar
    return $Candidate.Equals($Parent, [System.StringComparison]::OrdinalIgnoreCase) -or
        $Candidate.StartsWith($parentWithSeparator, [System.StringComparison]::OrdinalIgnoreCase)
}

function Get-RepositorySnapshot {
    param([Parameter(Mandatory = $true)][string]$Root)

    $paths = @(& git -C $Root ls-files -co --exclude-standard)
    if ($LASTEXITCODE -ne 0) {
        throw 'git ls-files failed while capturing the worker baseline'
    }
    $snapshot = [ordered]@{}
    foreach ($relative in $paths) {
        if ([string]::IsNullOrWhiteSpace($relative)) {
            continue
        }
        $full = Join-Path $Root $relative
        $key = $relative.Replace('\', '/')
        $snapshot[$key] = if (Test-Path -LiteralPath $full -PathType Leaf) {
            (Get-FileHash -Algorithm SHA256 -LiteralPath $full).Hash
        } else {
            '<missing>'
        }
    }
    return $snapshot
}

function Get-ChangedSnapshotPaths {
    param(
        [Parameter(Mandatory = $true)]$Before,
        [Parameter(Mandatory = $true)]$After
    )
    $all = @($Before.Keys) + @($After.Keys) | Sort-Object -Unique
    return @($all | Where-Object {
        -not $Before.Contains($_) -or -not $After.Contains($_) -or $Before[$_] -ne $After[$_]
    })
}

$workspaceFull = Resolve-FullPath $Workspace
$promptFull = Resolve-FullPath $PromptFile
$outputFull = Resolve-FullPath $OutputDirectory

if (-not (Test-Path -LiteralPath $workspaceFull -PathType Container)) {
    throw "Workspace does not exist: $workspaceFull"
}
if (-not (Test-Path -LiteralPath $promptFull -PathType Leaf)) {
    throw "Prompt file does not exist: $promptFull"
}
if (($workspaceFull -split '[\\/]') -contains '.agent-harness') {
    throw 'Refusing to run a Luna worker inside .agent-harness'
}

$gitRoot = (& git -C $workspaceFull rev-parse --show-toplevel 2>$null).Trim()
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($gitRoot)) {
    throw 'Workspace must be a Git worktree'
}
$gitRoot = Resolve-FullPath $gitRoot
if (-not $gitRoot.Equals($workspaceFull, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Workspace must be the exact Git root. Resolved root: $gitRoot"
}

if (Test-IsWithin -Candidate $outputFull -Parent $workspaceFull) {
    $outputRelative = [System.IO.Path]::GetRelativePath($workspaceFull, $outputFull)
    & git -C $workspaceFull check-ignore --quiet -- $outputRelative
    if ($LASTEXITCODE -ne 0) {
        throw 'OutputDirectory inside the workspace must be ignored by Git'
    }
}
if (Test-Path -LiteralPath $outputFull) {
    if (@(Get-ChildItem -LiteralPath $outputFull -Force).Count -ne 0) {
        throw "OutputDirectory must be new or empty: $outputFull"
    }
} else {
    New-Item -ItemType Directory -Path $outputFull | Out-Null
}

$targetFull = @()
$targetRelative = @()
foreach ($path in $TargetPath) {
    $resolved = if ([System.IO.Path]::IsPathRooted($path)) {
        Resolve-FullPath $path
    } else {
        Resolve-FullPath (Join-Path $workspaceFull $path)
    }
    if (-not (Test-IsWithin -Candidate $resolved -Parent $workspaceFull)) {
        throw "Target path is outside the workspace: $path"
    }
    $relative = [System.IO.Path]::GetRelativePath($workspaceFull, $resolved).Replace('\', '/')
    if ($relative -eq '.git' -or $relative.StartsWith('.git/') -or
        $relative -eq '.agent-harness' -or $relative.StartsWith('.agent-harness/')) {
        throw "Protected path cannot be targeted: $path"
    }
    $targetFull += $resolved
    $targetRelative += $relative
}

$eventsFile = Join-Path $outputFull 'events.jsonl'
$stderrFile = Join-Path $outputFull 'stderr.log'
$lastMessageFile = Join-Path $outputFull 'last-message.json'
$proposalFile = Join-Path $outputFull 'proposal.patch'
$manifestFile = Join-Path $outputFull 'run-manifest.json'
$taskWalFile = Join-Path $outputFull 'task-wal.md'
$checkpointMessageFile = Join-Path $outputFull 'checkpoint-last-message.json'
$checkpointProposalFile = Join-Path $outputFull 'checkpoint-proposal.patch'
$schemaFile = Join-Path $PSScriptRoot 'worker-output.schema.json'

$completionReserveMinutes = [Math]::Min(5, [Math]::Max(1, [Math]::Ceiling($ExpectedMaxMinutes * 0.2)))
$checkpointDueMinutes = [Math]::Max(1, $ExpectedMaxMinutes - $completionReserveMinutes)

$before = Get-RepositorySnapshot -Root $workspaceFull
$brief = Get-Content -LiteralPath $promptFull -Raw
$targetList = ($targetRelative | ForEach-Object { '- ' + $_ }) -join "`n"
$preamble = @"
You are a bounded code-generation worker operating under a main agent.

Workspace: $workspaceFull
Permitted proposal targets:
$targetList

Hard constraints:
- Read and obey repository AGENTS.md files.
- The workspace is intentionally read-only. Do not call apply_patch or attempt any filesystem write.
- Return an apply_patch-format proposal only for the permitted target paths. Do not propose secondary files, lockfiles, generated artifacts, configuration, or unrelated dirty files.
- Never access .agent-harness, credentials, private connection profiles, live services, external systems, Git history, branches, remotes, or publication state.
- Do not run git checkout, reset, clean, stash, rebase, pull, push, commit, or destructive commands.
- Stop with status blocked if the task requires another path, an unresolved contract decision, broader authority, or live action.
- Run only read-only focused checks authorized by the brief.
- Emit a concise progress message prefixed `WAL:` after each major read, design, and proposal stage. State what changed in your understanding, what comes next, and any blocker. Do this at least every few minutes during a long task.
- The applyPatch field must contain a complete `*** Begin Patch` / `*** End Patch` proposal compatible with the main agent's apply_patch tool. Use an empty string when blocked.
- The total worker budget is $ExpectedMaxMinutes minutes. By minute $checkpointDueMinutes, emit your best complete parseable proposal as a structured agent message, even if further polish remains. Reserve the final $completionReserveMinutes minute(s) for consistency checks and final serialization. Stop with status blocked before the total budget expires if the scoped proposal cannot be completed safely.

Task brief follows:

"@
$effectivePrompt = $preamble + $brief

$codex = (Get-Command codex -ErrorAction Stop).Source
$arguments = @(
    '-a', 'never',
    'exec',
    '--ephemeral',
    '--ignore-user-config',
    '--strict-config',
    '--color', 'never',
    '--json',
    '-C', $workspaceFull,
    '-s', 'read-only',
    '-m', 'gpt-5.6-luna',
    '-c', ('model_reasoning_effort="' + $ReasoningEffort + '"'),
    '--output-schema', $schemaFile,
    '-o', $lastMessageFile,
    '-'
)

$startedAt = (Get-Date).ToUniversalTime().ToString('o')
@(
    '# Codex CLI Luna worker task WAL',
    '',
    "- Started: $startedAt",
    '- Status: running',
    "- Total budget: $ExpectedMaxMinutes minutes",
    "- Complete checkpoint due: $checkpointDueMinutes minutes",
    "- Completion reserve: $completionReserveMinutes minutes",
    "- Workspace: $workspaceFull",
    "- Targets: $($targetRelative -join ', ')"
) | Set-Content -LiteralPath $taskWalFile -Encoding utf8

$effectivePrompt | & $codex @arguments 2> $stderrFile | ForEach-Object {
    $line = [string]$_
    Add-Content -LiteralPath $eventsFile -Value $line -Encoding utf8
    try {
        $event = $line | ConvertFrom-Json
        $walText = $null
        if ($event.type -eq 'thread.started') {
            $walText = "thread started: $($event.thread_id)"
        } elseif ($event.type -eq 'item.completed' -and $event.item.type -eq 'agent_message') {
            $message = ([string]$event.item.text).Trim()
            try {
                $structuredMessage = $message | ConvertFrom-Json
                if (-not [string]::IsNullOrWhiteSpace([string]$structuredMessage.summary)) {
                    $message = [string]$structuredMessage.summary
                }
                $checkpointPatch = [string]$structuredMessage.applyPatch
                if ($structuredMessage.status -eq 'proposal' -and
                    -not [string]::IsNullOrWhiteSpace($checkpointPatch)) {
                    $trimmedCheckpoint = $checkpointPatch.Trim()
                    if ($trimmedCheckpoint.StartsWith('*** Begin Patch') -and
                        $trimmedCheckpoint.EndsWith('*** End Patch')) {
                        $event.item.text | Set-Content -LiteralPath $checkpointMessageFile -Encoding utf8
                        $checkpointPatch | Set-Content -LiteralPath $checkpointProposalFile -Encoding utf8
                        $checkpointTimestamp = (Get-Date).ToUniversalTime().ToString('o')
                        Add-Content -LiteralPath $taskWalFile -Value "- $checkpointTimestamp host captured a complete structured proposal checkpoint" -Encoding utf8
                    }
                }
            } catch {
                # Plain agent messages remain useful progress evidence.
            }
            $message = $message -replace "`r?`n", ' '
            if ($message.Length -gt 2000) {
                $message = $message.Substring(0, 2000) + '...'
            }
            $walText = "agent: $message"
        } elseif ($event.type -eq 'item.started' -and $event.item.type -eq 'command_execution') {
            $command = ([string]$event.item.command).Trim() -replace "`r?`n", ' '
            if ($command.Length -gt 1000) {
                $command = $command.Substring(0, 1000) + '...'
            }
            $walText = "read/check started: $command"
        } elseif ($event.type -eq 'item.completed' -and $event.item.type -eq 'command_execution') {
            $walText = "read/check completed: exit=$($event.item.exit_code)"
        } elseif ($event.type -eq 'turn.completed') {
            $walText = 'turn completed'
        }
        if ($null -ne $walText) {
            $timestamp = (Get-Date).ToUniversalTime().ToString('o')
            Add-Content -LiteralPath $taskWalFile -Value "- $timestamp $walText" -Encoding utf8
        }
    } catch {
        $timestamp = (Get-Date).ToUniversalTime().ToString('o')
        Add-Content -LiteralPath $taskWalFile -Value "- $timestamp unparsed event retained in events.jsonl" -Encoding utf8
    }
}
$codexExit = $LASTEXITCODE
$finishedAt = (Get-Date).ToUniversalTime().ToString('o')
Add-Content -LiteralPath $taskWalFile -Value "- $finishedAt Status: Codex process exited with code $codexExit" -Encoding utf8
$after = Get-RepositorySnapshot -Root $workspaceFull
$workspaceMutations = @(Get-ChangedSnapshotPaths -Before $before -After $after)
$proposalPathViolations = @()
$proposalPatchPaths = @()
$patchPathViolations = @()
$proposal = $null

if ($codexExit -eq 0 -and (Test-Path -LiteralPath $lastMessageFile -PathType Leaf)) {
    $proposal = Get-Content -LiteralPath $lastMessageFile -Raw | ConvertFrom-Json
    foreach ($path in @($proposal.targetPaths)) {
        $normalized = $path.Replace('\', '/')
        $permitted = $false
        foreach ($target in $targetRelative) {
            if ($normalized -eq $target -or $normalized.StartsWith($target.TrimEnd('/') + '/')) {
                $permitted = $true
                break
            }
        }
        if (-not $permitted) {
            $proposalPathViolations += $normalized
        }
    }
    if ($proposal.status -eq 'proposal') {
        if ([string]::IsNullOrWhiteSpace($proposal.applyPatch)) {
            throw 'Luna returned proposal status without an apply_patch payload'
        }
        $trimmedPatch = $proposal.applyPatch.Trim()
        if (-not $trimmedPatch.StartsWith('*** Begin Patch') -or
            -not $trimmedPatch.EndsWith('*** End Patch')) {
            throw 'Luna returned a proposal that is not a complete apply_patch envelope'
        }
        foreach ($line in ($proposal.applyPatch -split "`r?`n")) {
            $path = $null
            if ($line -match '^\*\*\* (?:Add|Update|Delete) File: (.+?)\s*$') {
                $path = $Matches[1]
            } elseif ($line -match '^\*\*\* Move to: (.+?)\s*$') {
                $path = $Matches[1]
            }
            if ($null -eq $path) {
                continue
            }
            if ([System.IO.Path]::IsPathRooted($path)) {
                $patchPathViolations += $path
                continue
            }
            $resolved = Resolve-FullPath (Join-Path $workspaceFull $path)
            if (-not (Test-IsWithin -Candidate $resolved -Parent $workspaceFull)) {
                $patchPathViolations += $path
                continue
            }
            $normalized = [System.IO.Path]::GetRelativePath($workspaceFull, $resolved).Replace('\', '/')
            $proposalPatchPaths += $normalized
            $permitted = $false
            foreach ($target in $targetRelative) {
                if ($normalized -eq $target -or $normalized.StartsWith($target.TrimEnd('/') + '/')) {
                    $permitted = $true
                    break
                }
            }
            if (-not $permitted) {
                $patchPathViolations += $normalized
            }
        }
        if ($proposalPatchPaths.Count -eq 0) {
            throw 'Luna returned a proposal without an add, update, delete, or move patch header'
        }
        $proposal.applyPatch | Set-Content -LiteralPath $proposalFile -Encoding utf8
    }
}

$manifest = [ordered]@{
    schema = 'codex-cli-luna-worker.run.v1'
    codexVersion = (& $codex --version).Trim()
    model = 'gpt-5.6-luna'
    reasoningEffort = $ReasoningEffort
    expectedMaxMinutes = $ExpectedMaxMinutes
    checkpointDueMinutes = $checkpointDueMinutes
    completionReserveMinutes = $completionReserveMinutes
    sandbox = 'read-only'
    workspace = $workspaceFull
    promptFile = $promptFull
    promptSha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $promptFull).Hash
    targetPaths = @($targetRelative)
    workspaceMutations = @($workspaceMutations)
    proposalPathViolations = @($proposalPathViolations)
    proposalPatchPaths = @($proposalPatchPaths | Sort-Object -Unique)
    patchPathViolations = @($patchPathViolations | Sort-Object -Unique)
    proposalStatus = if ($null -eq $proposal) { '<missing>' } else { $proposal.status }
    codexExitCode = $codexExit
    eventsFile = $eventsFile
    taskWalFile = $taskWalFile
    checkpointMessageFile = if (Test-Path -LiteralPath $checkpointMessageFile) { $checkpointMessageFile } else { $null }
    checkpointProposalFile = if (Test-Path -LiteralPath $checkpointProposalFile) { $checkpointProposalFile } else { $null }
    stderrFile = $stderrFile
    lastMessageFile = $lastMessageFile
    proposalFile = if (Test-Path -LiteralPath $proposalFile) { $proposalFile } else { $null }
}
$manifest | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $manifestFile -Encoding utf8
$manifest | ConvertTo-Json -Depth 6

if ($codexExit -ne 0) {
    exit $codexExit
}
if ($workspaceMutations.Count -ne 0) {
    exit 86
}
if (@($proposalPathViolations).Count -ne 0) {
    exit 87
}
if (@($patchPathViolations).Count -ne 0) {
    exit 88
}
