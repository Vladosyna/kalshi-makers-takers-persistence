<#
.SYNOPSIS
    Bring the collector back after a reboot or a crash. Runs from the scheduled
    task KalshiMT-AutostartFetch; safe to run by hand at any time.

.DESCRIPTION
    README's "Running the long fetches" section called an unsupervised restart
    the largest remaining operational gap, and twice paid for it: fourteen hours
    on 2026-08-06/07 (connected standby, then an unattended reboot at 02:33) and
    thirty-five minutes on 2026-08-09 (bugcheck 0x124, a hardware machine-check
    crash under sustained load -- the third such crash in five weeks). Nothing
    was lost either time, because every phase is checkpointed, but nothing was
    collected either. This closes that gap.

    What it deliberately does NOT do is supervise a running collector. The one
    previous attempt at that killed a healthy fifteen-hour run on stale state,
    and a zombie copy of it later restarted the collector unnoticed and collided
    with the live process on SQLite "database is locked". So this script only
    ever STARTS something, never stops or kills anything, and it starts nothing
    when a collector already exists.

    Four safeguards, each answering a specific way this could go wrong:

      * single-instance guard -- exits if any kmt process is alive, so a manual
        launch and a scheduled firing cannot both hold the database;
      * relaunch brake -- refuses to start within MinRelaunchGapMinutes of the
        previous start, so a collector that dies immediately on a bad argument
        cannot become a hot loop hammering Kalshi's API;
      * kill switch -- "enabled": false in the config stops it without touching
        the scheduled task;
      * audit log -- EVERY firing appends a line to data/logs/autostart.log,
        including the no-ops. A restart that happens behind the operator's back
        is exactly what made the zombie watchdog expensive to diagnose, so this
        one leaves a trail whether it acts or not.

    The command itself lives in data/autostart_fetch.json rather than in the
    task registration, because the phase this repo is collecting changes over
    the life of the project (pass 1 quotes now, pass 2 tapes next) and the task
    should not need re-registering each time.

    IMPORTANT: the config is not self-updating. When the current phase finishes,
    edit "args" for the next one or set "enabled": false. A stale config keeps
    relaunching a phase with no work left -- harmless (it exits after a database
    query, without touching the API) but pointless.
#>

[CmdletBinding()]
param(
    # Minimum minutes between two launches by this script. The brake against a
    # crash loop; the scheduled task's repetition interval should be at or below
    # this, since the brake is what actually bounds the rate.
    [int]$MinRelaunchGapMinutes = 10,

    # Report what would happen and start nothing.
    [switch]$WhatIfOnly
)

$ErrorActionPreference = 'Stop'

$RepoRoot   = Split-Path -Parent $PSScriptRoot
$ConfigPath = Join-Path $RepoRoot 'data\autostart_fetch.json'
$StatePath  = Join-Path $RepoRoot 'data\autostart_fetch.state.json'
$LogDir     = Join-Path $RepoRoot 'data\logs'
$AuditLog   = Join-Path $LogDir 'autostart.log'
$KmtExe     = Join-Path $RepoRoot '.venv\Scripts\kmt.exe'

function Write-Audit([string]$Message) {
    $line = "{0} {1}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $Message
    try {
        if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir -Force | Out-Null }
        Add-Content -Path $AuditLog -Value $line -Encoding utf8
    } catch {
        # A log we cannot write must not stop a restart we can perform.
    }
    Write-Output $line
}

# --- kill switch and command -------------------------------------------------

if (-not (Test-Path $ConfigPath)) {
    Write-Audit "SKIP no config at $ConfigPath"
    exit 0
}

try {
    $config = Get-Content $ConfigPath -Raw -Encoding utf8 | ConvertFrom-Json
} catch {
    Write-Audit "SKIP config is not valid JSON: $($_.Exception.Message)"
    exit 1
}

if (-not $config.enabled) {
    Write-Audit 'SKIP disabled in config'
    exit 0
}

$fetchArgs = @($config.args)
if ($fetchArgs.Count -eq 0) {
    Write-Audit 'SKIP config has no args'
    exit 1
}

$prefix = if ($config.log_prefix) { [string]$config.log_prefix } else { 'autostart_fetch' }

# --- single-instance guard ---------------------------------------------------

$running = @(Get-Process -Name kmt -ErrorAction SilentlyContinue)
if ($running.Count -gt 0) {
    Write-Audit ("SKIP collector already running (PID {0})" -f ($running.Id -join ','))
    exit 0
}

# --- relaunch brake ----------------------------------------------------------

if (Test-Path $StatePath) {
    try {
        $state = Get-Content $StatePath -Raw -Encoding utf8 | ConvertFrom-Json
        if ($state.last_launch) {
            $since = (Get-Date) - [datetime]::Parse($state.last_launch, [Globalization.CultureInfo]::InvariantCulture)
            if ($since.TotalMinutes -lt $MinRelaunchGapMinutes) {
                Write-Audit ("SKIP brake: launched {0:N1} min ago, gap is {1} min -- a collector dying this fast is a fault to diagnose, not to retry" -f $since.TotalMinutes, $MinRelaunchGapMinutes)
                exit 0
            }
        }
    } catch {
        Write-Audit "WARN unreadable state file, ignoring brake: $($_.Exception.Message)"
    }
}

if (-not (Test-Path $KmtExe)) {
    Write-Audit "SKIP no collector executable at $KmtExe"
    exit 1
}

# --- launch ------------------------------------------------------------------

$stamp   = Get-Date -Format 'yyyyMMdd-HHmmss'
$errLog  = Join-Path $LogDir "$prefix-$stamp.log"
$outLog  = Join-Path $LogDir "$prefix-$stamp.out.log"

if ($WhatIfOnly) {
    Write-Audit ("WHATIF would launch: kmt {0}  -> {1}" -f ($fetchArgs -join ' '), (Split-Path -Leaf $errLog))
    exit 0
}

try {
    # Detached, exactly as README requires: a fetch parented to the shell that
    # started it dies with that shell, silently and mid-request.
    $proc = Start-Process -FilePath $KmtExe -ArgumentList $fetchArgs `
        -WorkingDirectory $RepoRoot -WindowStyle Hidden -PassThru `
        -RedirectStandardError $errLog -RedirectStandardOutput $outLog
} catch {
    Write-Audit "FAIL launch threw: $($_.Exception.Message)"
    exit 1
}

# Written after the launch, so a throw above does not consume the brake window.
$newState = [ordered]@{
    last_launch = (Get-Date).ToString('o')
    pid         = $proc.Id
    log         = $errLog
    args        = $fetchArgs
}
try {
    $newState | ConvertTo-Json -Depth 4 | Set-Content -Path $StatePath -Encoding utf8
} catch {
    Write-Audit "WARN could not write state file: $($_.Exception.Message)"
}

Write-Audit ("LAUNCHED pid {0}: kmt {1}  -> {2}" -f $proc.Id, ($fetchArgs -join ' '), (Split-Path -Leaf $errLog))
exit 0
