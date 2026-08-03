[CmdletBinding(SupportsShouldProcess = $true, ConfirmImpact = 'Medium')]
param(
    [string[]]$Skill = @(),
    [string]$DestinationRoot = (Join-Path ([Environment]::GetFolderPath('UserProfile')) '.agents\skills'),
    [switch]$Force
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$repositoryRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$sourceRoot = [System.IO.Path]::GetFullPath((Join-Path $repositoryRoot 'skills'))
$destinationFull = [System.IO.Path]::GetFullPath($DestinationRoot)

$recommended = @(
    'batch-complete-independent-review',
    'codex-cli-luna-worker',
    'completeness-and-test-synthesis',
    'incident-to-regression',
    'long-run-supervisor'
)

if ($Skill.Count -eq 0) {
    $Skill = $recommended
}

$available = @{}
Get-ChildItem -LiteralPath $sourceRoot -Directory | ForEach-Object {
    if (Test-Path -LiteralPath (Join-Path $_.FullName 'SKILL.md')) {
        $available[$_.Name] = $_.FullName
    }
}

foreach ($name in $Skill) {
    if (-not $available.ContainsKey($name)) {
        $choices = ($available.Keys | Sort-Object) -join ', '
        throw "Unknown vendored skill '$name'. Available: $choices"
    }
}

if ($PSCmdlet.ShouldProcess($destinationFull, 'Create user skill directory')) {
    New-Item -ItemType Directory -Path $destinationFull -Force | Out-Null
}

foreach ($name in $Skill) {
    $source = [System.IO.Path]::GetFullPath($available[$name])
    $target = [System.IO.Path]::GetFullPath((Join-Path $destinationFull $name))
    if (-not $target.StartsWith($destinationFull + [System.IO.Path]::DirectorySeparatorChar, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Resolved skill target escapes the destination root: $target"
    }

    if (Test-Path -LiteralPath $target) {
        if (-not $Force) {
            throw "Skill already exists at '$target'. Re-run with -Force to create a recoverable backup and replace it."
        }
        $stamp = [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfffZ')
        $backup = "$target.backup-$stamp"
        if ($PSCmdlet.ShouldProcess($target, "Move existing skill to $backup")) {
            Move-Item -LiteralPath $target -Destination $backup
        }
    }

    if ($PSCmdlet.ShouldProcess($target, "Install $name from the verified public bundle")) {
        Copy-Item -LiteralPath $source -Destination $target -Recurse
    }
}

Write-Host "Selected skills: $($Skill -join ', ')"
Write-Host "Destination: $destinationFull"
Write-Host 'Restart Codex if newly installed skills are not detected automatically.'
