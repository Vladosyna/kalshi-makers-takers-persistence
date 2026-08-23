<#
.SYNOPSIS
    Wait for the running Pass 1 quote fetch to finish, then start Pass 2.

.DESCRIPTION
    The quote tail for 2026-05/06 finishes in the small hours, and the next
    collection step (Pass 2 trade tapes) is unattended work that has no reason
    to wait for someone to wake up. This watches for a CLEAN finish and starts
    it; overnight idle time is what this whole project keeps losing to.

    WATCH-ONLY WITH RESPECT TO RUNNING PROCESSES. It starts things; it never
    stops, kills or signals one. That is not a style preference: a previous
    supervisor in this repo killed a healthy fifteen-hour run on stale state,
    and a zombie copy of it later restarted a collector unnoticed and collided
    with the live process on SQLite "database is locked". Every launch here
    goes through tools/autostart_fetch.ps1, which carries the single-instance
    guard, the relaunch brake and the audit trail.

    HOW COMPLETION IS DETECTED, and why not the obvious way. `quoted ==
    eligible` is NOT the test -- some markets 404 permanently and never get a
    quotes row, so that equality can stay false forever (README: "Do not treat
    eligible == quoted as no work left"). The reliable signal is the
    collector's own clean return: it prints a stats JSON to stdout on success
    and nothing on a crash. So:

        kmt alive                        -> keep waiting
        kmt gone + .out.log non-empty    -> CLEAN FINISH  -> advance to Pass 2
        kmt gone + .out.log empty        -> died          -> relaunch Pass 1

    That third branch matters more than it looks. This collector has been
    killed by a Windows Update reboot, a hardware bugcheck and, twice, by the
    Claude VM Service restarting and taking its job object with it. Overnight,
    the watcher is also the thing that brings it back.

    WHAT IT DOES *NOT* ADVANCE TO. Only Pass 2 -- the long unattended fetch.
    `kmt build`, `kmt r1` and `kmt r2` are analysis, they produce the locked
    R2 artifact, and per docs/analysis_plan.md that lock is a deliberate act,
    not something a timer should perform at 3am.

    ITS OWN FRAGILITY, stated because it is real: this script runs inside the
    session's job object, so a Claude VM Service restart kills the watcher too
    -- the same failure it exists to paper over. If it disappears, the
    collection is unaffected; just start it again.
#>

[CmdletBinding()]
param(
    [int]$PollSeconds = 300,
    # Report what it would do at each decision point and change nothing.
    [switch]$DryRun
)

$ErrorActionPreference = 'Continue'

$RepoRoot    = Split-Path -Parent $PSScriptRoot
$LogDir      = Join-Path $RepoRoot 'data\logs'
$WatchLog    = Join-Path $LogDir 'watch_advance.log'
$ConfigPath  = Join-Path $RepoRoot 'data\autostart_fetch.json'
$Autostart   = Join-Path $PSScriptRoot 'autostart_fetch.ps1'
$Pass1Glob   = 'pass1_r2_quotes_tail-2026-05..2026-06_auto-*.log'

function Emit([string]$Message) {
    $line = "{0} {1}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $Message
    [Console]::Out.WriteLine($line); [Console]::Out.Flush()
    try { Add-Content -Path $WatchLog -Value $line -Encoding utf8 } catch { }
}

function ActivePass1Log() {
    Get-ChildItem $LogDir -Filter $Pass1Glob -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -notlike '*.out.log' } |
        Sort-Object LastWriteTime -Descending | Select-Object -First 1
}

function Start-Fetch([string]$Why) {
    if ($DryRun) { Emit "DRYRUN would launch ($Why)"; return }
    & powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass `
        -File $Autostart -MinRelaunchGapMinutes 0 2>&1 | ForEach-Object { Emit "  autostart: $_" }
}

# --- switch the config over to Pass 2 ---------------------------------------
function Set-ConfigToPass2() {
    $cfg = [ordered]@{
        '_what'          = 'The command tools/autostart_fetch.ps1 restarts after a reboot or crash. Read that script''s header first.'
        '_maintenance'   = 'NOT self-updating. When this phase finishes, either point ''args'' at the next phase or set ''enabled'' to false.'
        '_current_phase' = 'Pass 2 trade tapes for R2 in-scope markets. Switched here automatically by tools/watch_and_advance.ps1 when the 2026-05/06 quote tail exited cleanly. Next after this one is analysis -- kmt build, then kmt r2 -- which is deliberately NOT automated.'
        'enabled'        = $true
        'log_prefix'     = 'pass2_r2_tapes'
        'args'           = @('fetch', 'pass2', '--window', 'r2')
    }
    if ($DryRun) { Emit "DRYRUN would rewrite config to: kmt $($cfg.args -join ' ')"; return }
    $cfg | ConvertTo-Json -Depth 4 | Set-Content -Path $ConfigPath -Encoding utf8
    Emit "config repointed -> kmt $($cfg.args -join ' ')"
}

# --- main --------------------------------------------------------------------

$log = ActivePass1Log
Emit ("WATCHING for a clean finish of {0} (poll {1}s){2}" -f `
      $(if ($log) { $log.Name } else { '<no pass-1 log yet>' }), $PollSeconds, $(if ($DryRun) { ' [DRY RUN]' } else { '' }))

$lastTick = Get-Date
while ($true) {
    Start-Sleep -Seconds $PollSeconds
    $now = Get-Date
    $elapsed = ($now - $lastTick).TotalSeconds
    $lastTick = $now
    # A watcher on a Modern Standby host sleeps too. Treating a suspension as
    # elapsed time is how a healthy run gets called a hang.
    if ($elapsed -gt ($PollSeconds * 3)) {
        Emit ("RESUMED after {0}s -- watcher or host was suspended; skipping this tick" -f [int]$elapsed)
        continue
    }

    $alive = @(Get-Process -Name kmt -ErrorAction SilentlyContinue)
    if ($alive.Count -gt 0) { continue }

    $log = ActivePass1Log
    if (-not $log) { Emit 'no pass-1 log found and no collector running -- nothing to watch'; continue }
    $out = $log.FullName -replace '\.log$', '.out.log'
    $cleanFinish = (Test-Path $out) -and ((Get-Item $out).Length -gt 0)

    if (-not $cleanFinish) {
        Emit ("collector gone with an EMPTY {0} -- died rather than finished; relaunching Pass 1" -f (Split-Path -Leaf $out))
        Start-Fetch 'pass 1 died'
        continue
    }

    Emit "PASS 1 FINISHED CLEANLY. Its stats JSON:"
    Get-Content $out -ErrorAction SilentlyContinue | ForEach-Object { Emit "  $_" }
    Set-ConfigToPass2
    Start-Fetch 'advancing to pass 2'
    Emit 'PASS 2 STARTED. Analysis (kmt build / kmt r2) is deliberately left to a person.'
    break
}
