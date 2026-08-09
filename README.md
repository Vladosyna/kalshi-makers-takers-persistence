# Kalshi Makers & Takers Replication

A read-only research instrument that answers one question with statistical rigor:

> Did Kalshi's favorite–longshot bias and maker/taker return asymmetry — as
> documented by Bürgi, Deng & Whelan (2025) through April 2025 — persist once
> Kalshi started charging maker fees and the paper itself went public?

This is a replication (2021 → 2025-04-30) plus an extension (2025-05-01 →
present) of Bürgi, Deng & Whelan, *Makers and Takers: The Economics of the
Kalshi Prediction Market* (CEPR DP 20631 / CESifo WP 12122 / MPRA 126350).
**No execution code, no order placement, no Kalshi account required** — every
endpoint this repo touches is Kalshi's public, unauthenticated market data
API (verified live by Step Zero below). See [`Claude.md`](Claude.md) for the
full engineering brief (v1.1 — single source of truth for scope, methodology,
and phasing); [`kalshi-replication-spec.md`](kalshi-replication-spec.md) is a
superseded v1.0 draft, kept for history only.

This is a separate, standalone repository — not part of, and not dependent
on, `polymarket-forecast-lab`.

## Why this exists

BDW's own sample cutoff is not arbitrary: they stop in April 2025 because
"Kalshi began to charge fees on Makers after April 2025," a change that
directly taxes the paper's headline exploitable margin (maker returns of
+2.6% on contracts ≥50c). They also explicitly invite the follow-up
question — "we think it will be interesting to see if the biases and return
patterns that we have reported persist now that they have been publicly
documented" — and the maker-fee change and the paper's first public posting
(CEPR, 2025-09-08) are close enough in time to attempt a coarse decomposition
between the two. The one confound that makes this hard: sports launched on
Kalshi almost exactly at the R1/R2 boundary, volumes jumped, and BDW's own
data shows the bias is category-heterogeneous — so any naive "did the
aggregate bias move" comparison is confounded with composition shift, not a
measure of persistence. Most of this repo's R2 design exists to take that
confound apart before applying any persistence verdict to what's left.

## How it works

```
 Kalshi public API ──▶ kmt step-zero  (hard gate: unauthenticated access,
  (trade-api/v2,          2021-2022 depth, taker-field population,
   live + historical)     /trades bracketing, quote availability)
        │
        ▼
 kmt fetch pass1   discovery + price panel (~11 boundary ticks/contract)
        │          + closing quotes, whole in-scope universe
        ▼
 kmt fetch pass2   full trade tape (every fill: price, count, taker_side)
        │          for contracts that survive the R1/R2 filters only
        ▼
 kmt build         R1 filters + Yes-only/doubled panel + BDW count
        │          reconciliation + frozen calendar-2024 category mix
        ▼
 kmt r1            R1 reproduction: MZ regression (event-clustered), by-year
        │          / by-category psi vs BDW Tables 8-9, win-rate curve vs
        │          Fig 3, returns-by-band vs Fig 5, maker/taker split vs
        │          Fig 6 / Table 10, divergence log
        ▼
 kmt r2            R2 extension: pooled category-interacted MZ regression,
        │          fee/publication boundary tests, within/between
        │          decomposition, verdict (persisted/attenuated/vanished/
        │          reversed/indeterminate), horizon robustness, Polymarket
        │          control-venue overlay, fee-sensitivity ribbon -- writes
        │          the locked R2 artifact
        ▼
 kmt r3-check      R3 firewall gate: refuses to proceed unless the R2
        │          verdict is already locked on disk
        ▼
 kmt escalate      escalation decision (note vs. standalone paper) bound to
        │          the same delta_bar tests as the verdict, not prose
        ▼
 kmt report        final report assembly (note or paper venue, BDW Section 6
                    citation, fee-layer and ribbon appendix)
```

Two-pass fetch is deliberate, not an afterthought: a naive single-pass budget
optimization (pull only boundary ticks everywhere) is correct for the price
panel but would silently destroy the maker/taker tape, which needs every
fill. Pass 1 is cheap and universe-wide; Pass 2 is the real API budget and
runs only on contracts that already passed the R1/R2 filters.

## Methodological review

Before any code was written, the v1.1 spec went through an adversarial
multi-agent review — seven reviewers on independent dimensions (replication
fidelity, econometrics, R2 identification, fee reconstruction, data
feasibility, publication strategy, internal consistency), each finding then
run past a skeptic verifier whose default is to refute it. 41 of 43 findings
survived. The headline result: the category-composition confound (sports
launching at the R1/R2 boundary) was reclassified from a robustness footnote
to R2's central design problem, and the entire post-fee headline was found to
rest on an unsourced fee schedule with no sensitivity mechanism — both fixed
in the spec before Step Zero's fetch completed. See `Claude.md` for the
resulting design (frozen-mix reweighting, pooled interaction tests, the
fee-sensitivity ribbon with a pre-registered "fragile" rule).

## Project status

All ten phases in the engineering brief are implemented and tested
(**385/385 tests passing**):

- [x] Phase 0 — scaffold, config, CLI skeleton, scope guard
- [x] Phase 1 — Step Zero: the hard gate verifying Kalshi's public API has
      what this replication needs, before any fetch or account registration
- [x] Phase 2 — two-pass fetch pipeline (SQLite index + month-partitioned
      Parquet trade store), both passes resumable and concurrency-parallelized
- [x] Phase 2.5 — `docs/analysis_plan.md` committed (R2 equations, verdict
      thresholds, decomposition formula) before any R2 estimate was computed
- [x] Phase 3 — R1 filters, Yes-only/doubled panel construction, BDW count
      reconciliation, frozen calendar-2024 category-mix artifact
- [x] Phase 4 — `data/fees.yaml`: sourced fee schedule (taker formula from
      the paper, maker fee from 2025-05-01), right-continuous step-function
      lookup keyed on trade fill timestamp
- [x] Phase 5 — Mincer-Zarnowitz regression, event-clustered SEs, numerically
      verified two-way/one-way clustering equivalence, full R1 reproduction
      report (by-year/category psi, win-rate curve, returns by band,
      maker/taker split)
- [x] Phase 6 — three-layer fee decomposition (gross / net-of-own-era-fee /
      fee-held-constant counterfactual), return-convention fix
      (`r = (payout - P - fee)/P`, avoiding a ~20x-at-5c silent bias), and the
      fee-sensitivity ribbon with a break-even-rate statistic
- [x] Phase 7 — R2 pooled category-interacted regression (wild cluster
      bootstrap below 50 event clusters), within/between composition
      decomposition, five-outcome verdict binding, horizon-robustness checks
- [x] Phase 8 — Polymarket control-venue overlay (secular-trend check, not a
      DiD; reversed-tail-bias / provenance / spillover caveats stated
      explicitly, not left for a referee to find)
- [x] Phase 9 — R3 firewall: runtime gate plus a static scan that fails the
      build if any `r3` import appears outside `src/kalshi_mt/r3/`
- [x] Phase 10 — maker-margin time series across the three fee layers,
      escalation rule bound to the same delta_bar tests as the verdict
      vocabulary, final report assembly (note vs. standalone-paper venue)

Live data collection against the full 2021–2026 universe is under way; the
R1 reproduction tables, the R2 lock artifact, and the final report are
generated by `kmt build` / `kmt r1` / `kmt r2` once collection reaches the
full R1+R2 window — every stage of that pipeline is already implemented and
tested end-to-end against live samples, independent of how much of the
universe has been pulled so far.

Collection state (2026-07-28): R1's window is collected and reproduces every
headline BDW quantity — see [`docs/r1_reproduction_findings.md`](docs/r1_reproduction_findings.md).
Pass 2's trade tape is complete for both windows. What R2 is still waiting on
is closing quotes for the months that *bracket* its two boundaries
(2025-05 … 2025-12, ~104k eligible markets); `--panel-quote-close-from/-to`
exists to prioritise exactly those, because without them no delta is
identified no matter how much of 2026 is collected.

## Quickstart

Requirements: Python 3.12+ and [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/Vladosyna/kalshi-makers-takers-replication && cd kalshi-makers-takers-replication
uv sync
uv run pytest                # 385 tests, no network required
uv run kmt --help
uv run kmt step-zero         # hard gate -- re-verify before any fresh fetch
```

`kmt step-zero` is a hard gate (spec §3): if any required Kalshi endpoint
turns out to need authentication, it exits with a STOP banner and
instructions, and registers nothing on its own. Read
`reports/step_zero/findings.md` after it runs. Live run verdict so far: **GO**
— no endpoint required an account.

## Commands

| Command | Purpose |
|---|---|
| `kmt step-zero` | Hard gate: verify Kalshi's public API serves what R1/R2 need, before any fetch |
| `kmt status` | Data health: row counts, fetch-log state |
| `kmt fetch pass1` | Discovery + price panel (boundary ticks) + closing quotes, universe-wide |
| `kmt fetch pass2` | Full trade tape (every fill) for contracts that already passed the R1/R2 filters |
| `kmt build` | R1 filters, panel construction, BDW count-reconciliation gate, frozen 2024 category mix |
| `kmt r1` | R1 reproduction report: MZ regression, by-year/category psi, win-rate curve, returns by band, maker/taker split, divergence log |
| `kmt r2` | R2 extension: pooled category-interacted regression, decomposition, verdict, horizon robustness, Polymarket overlay -- writes the locked artifact |
| `kmt r3-check` | R3 firewall gate: refuses to proceed unless R2's verdict is already locked |
| `kmt escalate` | Escalation decision (replication note vs. standalone paper), bound to the pre-registered delta_bar tests |
| `kmt report` | Assemble the final report/note |

### Provenance tools

The fee schedule is the most error-prone input in this replication (spec §7),
so it is not hand-written. These regenerate it and the evidence behind it:

| Tool | What it produces |
|---|---|
| `tools/fetch_fee_schedule_history.py` | Archives every Wayback capture of Kalshi's published fee-schedule PDF into `docs/sources/fees/` and parses them into `version_history.json` (effective date, rates, functional form, per-series scope) |
| `tools/fetch_series_fee_catalog.py` | Freezes per-series `fee_type`/`fee_multiplier` for all ~12k series from Kalshi's API into `data/series_fee_catalog.json` |
| `tools/build_fees_yaml.py` | Generates `data/fees.yaml` from the two above — **do not hand-edit the YAML** |
| `tools/measure_fee_model_impact.py` | Prices R1's panel under both BDW's stated fee model and Kalshi's published schedule, band by band |
| `tools/measure_maker_fee_treatment.py` | Treated share of the R2 universe by month, and a join check that the fee schedule's series names match collected ones |
| `tools/measure_mismatch_filter.py` | All four readings of BDW's 63-contract mismatch filter, against their 0.136% rate |
| `tools/measure_polymarket_categories.py` | Control-venue strata coverage, with per-stratum samples to judge the rules on |
| `tools/check_panel_determinism.py` | Builds the R1 panel twice and compares rows, prices, order sizes and taker sides |
| `tools/r2_readiness.py` | Which R2 months are **analysable** (quoted + spread-passing + taped), and whether each boundary is ready |
| `tools/measure_endpoint_families.py` | Which trade endpoint answers by market age, how many markets need both, and how many are permanently unquotable |

`fetch_fee_schedule_history.py` needs `pypdf` for the parsing half (the
archiving half is stdlib-only); it is deliberately not a project dependency,
since adding one forces a `uv sync` that cannot run while a collector process
holds `.venv/Scripts/kmt.exe` open.

### Running the long fetches

Both passes take hours to days against the real universe, so launch them
**detached from whatever shell started them** — a fetch parented to an
interactive session dies with that session, silently and with nothing in the
log but an abrupt stop mid-request (observed 2026-07-28: seven hours of work
ended with no traceback, no error line, no summary). On Windows:

```powershell
Start-Process -FilePath .\.venv\Scripts\kmt.exe `
  -ArgumentList 'fetch','pass1','--max-series','0','--panel-quote-window','r2',
                '--panel-quote-close-from','2025-05-01','--panel-quote-close-to','2025-12-31' `
  -WorkingDirectory (Get-Location) -WindowStyle Hidden `
  -RedirectStandardError data\logs\pass1.log -RedirectStandardOutput data\logs\pass1.out.log
```

Nothing is lost when a run does die: every phase is resumable from its own
checkpoint, and the panel/quote phase's resume predicate is `ticker NOT IN
quotes` — the row `fetch_closing_quote` writes last, after the panel rows.

**Do not treat `eligible == quoted` as "no work left".** This README said so
until 2026-08-01, on the reasoning that the quote row is written *always*, even
when no quote is retrievable. It is not written when the fetch raises before
reaching it: 32 markets (`KXMLBMENTION-25OCT25-*`) return 404 permanently from
Kalshi, so the count stops short of eligible **forever**. A watchdog keying on
that equality calls a clean finish a crash and restarts a completed phase —
which is exactly what happened, at 103,809 of 103,841.

The reliable completion signal is the collector's own clean return: it prints a
stats JSON to stdout on success and nothing on a crash, and that JSON carries
`markets_failed` (32 here) so the residue is reported rather than inferred.
Useful properties for anything supervising a run:

- a stalled log is a hang — the process tree is `kmt.exe → python.exe →
  python.exe`, so a wedged worker can leave the top-level process alive;
- **but a supervisor on a Modern Standby host sleeps too**, so before calling
  a stale log a hang it must check whether *it* was suspended (compare its own
  tick duration against the interval). Otherwise every host sleep is reported
  as a collector hang and kills a healthy process;
- and read staleness from the log's **last line**, not its `LastWriteTime`.
  Windows updates the directory entry of a file held open for writing lazily,
  so the timestamp can sit frozen for hours while the file grows — 19
  consecutive false "possible hang" alerts came from trusting it, against a
  collector running at full rate.

**A fetch does not survive a reboot on its own.** `keep_system_awake` defers
*idle* sleep and held for six days unbroken; it cannot override a sleep the
user or a policy initiates, and it cannot survive a restart at all. Twice
observed, and the two have different causes worth telling apart:

- **2026-08-06/07, sleep then reboot.** The host entered connected standby at
  20:35 (Kernel-Power 506), the frozen collector wrote its last line at 20:53,
  Windows initiated a shutdown transition at 02:30 (Kernel-Power 109) and
  rebooted at 02:33 — after which the collector simply did not exist.
  **Fourteen hours** passed before anyone noticed.
- **2026-08-09, hardware crash.** Bugcheck `0x124`
  (`WHEA_UNCORRECTABLE_ERROR`) at 16:47 under sustained load, with
  `SleepInProgress=0` — not a standby event at all. Dump creation failed
  (`volmgr` 161), so there is no minidump; Windows ran its own memory
  diagnostic on the next boot and found no errors. Two earlier minidumps sit in
  `C:\Windows\Minidump` (2026-07-05, 2026-07-28), making this the third crash
  in five weeks on a machine that has eight more days of continuous fetching
  ahead of it. **Thirty-five minutes** lost, only because someone was watching.

Neither cost any data — every phase is checkpointed, and the SQLite store is
WAL with `synchronous=FULL`, so an abrupt power loss can drop the last
uncommitted transaction but cannot corrupt the file. That was verified after
the 2026-08-09 crash rather than assumed: `quick_check`, `foreign_key_check`
and a full `integrity_check` all returned `ok` on the 6.5 GB database.

#### Restarting a dead collector: `tools/autostart_fetch.ps1`

[`tools/autostart_fetch.ps1`](tools/autostart_fetch.ps1) is the guarded
restart, driven by
[`data/autostart_fetch.json`](data/autostart_fetch.json). It is **deliberately
not registered as a scheduled task** — see "Why it is not scheduled" below — so
it is a one-command manual restart:

```powershell
powershell -ExecutionPolicy Bypass -File tools\autostart_fetch.ps1             # restart if dead
powershell -ExecutionPolicy Bypass -File tools\autostart_fetch.ps1 -WhatIfOnly # say what it would do, change nothing
```

It only ever *starts* a collector — it never stops, kills or supervises one.
That restraint is deliberate: the one previous supervisor killed a healthy
fifteen-hour run on stale state, and a zombie copy of it later restarted the
collector unnoticed and collided with the live process on SQLite "database is
locked". Four safeguards:

| Safeguard | Answers |
|---|---|
| Single-instance guard (exits if any `kmt` is alive) | a manual launch and a scheduled firing both holding the database |
| Relaunch brake (default 10 min between starts) | a collector dying instantly on a bad argument becoming a hot loop against Kalshi's API |
| `"enabled": false` kill switch | stopping it without touching the task registration |
| Audit line on **every** firing, including no-ops, in `data/logs/autostart.log` | a restart happening behind the operator's back, which is what made the zombie watchdog expensive to diagnose |

The command lives in the JSON, not the task, because the phase being collected
changes over the project's life. **The config is not self-updating**: when a
phase finishes, point `args` at the next one or set `"enabled": false`. A stale
config relaunches a phase with no work left — harmless, since it exits after a
database query without touching the API, but pointless.

#### Why it is not scheduled

It *was*, briefly, on 2026-08-09, as `KalshiMT-AutostartFetch` with an at-logon
trigger and a 15-minute standing heartbeat. It worked — the guard fired
correctly, the audit trail recorded every firing, and the collector was never
touched — and it was **unregistered within the hour because it flashed a
console window on the desktop every fifteen minutes**. On an interactive
desktop that is not a cosmetic detail; it makes the machine unusable, and a
supervisor nobody can stand to leave running is not a supervisor.

The cause is that an unelevated registration forces `LogonType Interactive`,
which runs the action in the user's own session, and `powershell.exe` there
gets a console — `-WindowStyle Hidden` suppresses the window's *contents*, not
the brief `conhost` allocation. Two ways to fix it properly, neither applied
because both are the operator's call:

1. **Elevated, no window ever.** An `S4U` principal runs the action in session
   0, where there is no desktop to flash on, and additionally allows an
   at-startup trigger — which also closes the one case the interactive version
   never covered, the unattended 02:33 reboot with nobody logging in
   (2026-08-06/07 exactly). Needs an **administrator** shell; attempted
   unelevated on 2026-08-09 and refused with `Access is denied`.

   ```powershell
   $a = New-ScheduledTaskAction -Execute 'powershell.exe' -WorkingDirectory 'D:\Papers\Kalshi replication lab' `
        -Argument '-NoProfile -NonInteractive -ExecutionPolicy Bypass -File "D:\Papers\Kalshi replication lab\tools\autostart_fetch.ps1"'
   $t = @((New-ScheduledTaskTrigger -AtStartup),
          (New-ScheduledTaskTrigger -AtLogOn -User "$env:USERDOMAIN\$env:USERNAME"))
   $t[0].Repetition = (New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Minutes 15)).Repetition
   $p = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType S4U -RunLevel Limited
   Register-ScheduledTask -TaskName KalshiMT-AutostartFetch -Action $a -Trigger $t -Principal $p -Force
   ```

2. **Unelevated, hidden via a `wscript` shim.** `wscript.exe` running a
   one-line `.vbs` that calls `WshShell.Run(cmd, 0, False)` starts the
   PowerShell with no console at all, so an interactive-logon task stays
   silent. Cheaper to set up, but still cannot provide an at-startup trigger.

Note the trap either version must avoid: a logon trigger's *repetition cycle
starts at the next logon*, so a task registered mid-session shows an empty
`NextRunTime` and never repeats. It would cover the reboot case and silently
not the crash case. The heartbeat has to ride on its own standing trigger,
which is why the snippet above sets `$t[0].Repetition` explicitly.

Two further mitigations remain operator-side because they change system state rather
than this program's behaviour: disable standby for the duration
(`powercfg /change standby-timeout-ac 0`), and check that Windows Update is not
configured to restart unattended overnight.

## Analysis discipline

A short field guide to the design choices this repo is built around — see
[`Claude.md`](Claude.md) for the full spec these implement.

- **Sequential gate: counts before estimates.** R1's estimates are only
  compared to BDW's after construction counts (12,403 events / 46,282
  contracts / 156,986 prices / 106,209+106,209 tails) reconcile against
  BDW's pinned integers. Divergence on overlapping deterministic data is a
  coverage question, not a sampling question — BDW's own standard errors are
  never used as the reconciliation tolerance.
  [`r1/reconcile.py`](src/kalshi_mt/r1/reconcile.py).
- **Composition-held-fixed R2 estimand.** The primary R2 test is a single
  pooled, category-interacted Mincer-Zarnowitz regression, with the headline
  delta_bar composition-weighted by the frozen calendar-2024 category mix —
  sports (which didn't exist pre-2025) carries zero weight in the headline
  and is reported as its own stratum instead.
  [`r2/regression.py`](src/kalshi_mt/r2/regression.py),
  [`r2/decomposition.py`](src/kalshi_mt/r2/decomposition.py).
- **Formal verdict binding, not eyeballed windows.** Persisted / attenuated /
  vanished / reversed / indeterminate are a deterministic function of one
  composition-weighted delta_bar's confidence interval against two reference
  points (0 and -psi_bar_R1) — never a comparison of significance stars
  across separately-estimated per-window regressions.
  [`r2/verdicts.py`](src/kalshi_mt/r2/verdicts.py).
- **Return convention, pinned once.** `r = (payout - P - fee) / P` for every
  fee layer — subtracting a per-notional fee from a per-capital return
  produces a ~20x bias at 5c and ~2x at 50c, concentrated exactly on the tail
  bins and the ≥50c threshold the headline margin depends on.
  [`fees/returns.py`](src/kalshi_mt/fees/returns.py).
- **Three fee layers, every time.** Gross/zero-fee, net-of-own-era-fee, and a
  fee-held-constant counterfactual (pre-2025 schedule applied to post-2025
  trades) — the persistence narrative reads off layers (a)/(c); layer (b)
  alone conflates fee incidence with behavioral change.
  [`fees/returns.py`](src/kalshi_mt/fees/returns.py).
- **Detectability, not just a point estimate.** A pre-committed
  fee-sensitivity ribbon reports the break-even fee rate that zeroes the
  maker ≥50c/>70c margins; if the true fee is close to that point, or the
  margin's sign flips inside the plausible band, the result is labeled
  "fragile" and cannot trigger escalation on its own.
  [`fees/ribbon.py`](src/kalshi_mt/fees/ribbon.py).
- **Control venue, not a DiD.** Polymarket's monthly psi path is overlaid as
  a secular-trend check only — its tail bias is reversed, so it controls for
  market-wide efficiency drift, not for level or sign; parallel-trends
  language is deliberately off the table.
  [`control/polymarket.py`](src/kalshi_mt/control/polymarket.py).
- **R3 firewall.** R2's verdict is computed and locked before any R3 number
  is examined, and R2 prose is never revised in light of R3 — enforced by a
  runtime gate plus a static import scanner
  (`tests/test_scope.py`-style tripwire).
  [`r3/firewall.py`](src/kalshi_mt/r3/firewall.py).
- **Clustering.** Contracts nest inside events, so Cameron-Gelbach-Miller
  two-way (event, contract) clustering reduces algebraically to one-way
  event clustering — verified numerically, not just asserted. Thin
  monthly/category cells fall back to a wild cluster bootstrap below 50
  event clusters. [`r1/regression.py`](src/kalshi_mt/r1/regression.py).

## Scope invariants

1. **No execution code.** Read-only research instrument; no order placement,
   no wallets, no Kalshi account required by default.
2. **Public endpoints only.** Every fetch call targets Kalshi's
   unauthenticated `trade-api/v2` — verified live by `kmt step-zero`, not
   assumed.
3. **Polite API citizenship.** Shared token-bucket rate limiter (bounded
   concurrency, not just a configured number), exponential backoff on
   429/5xx, resumable cursors, per-market fetch-count reconciliation.
4. **R3 firewall.** The prospective arm cannot influence R2's already-locked
   verdict, enforced in code, not just in prose.
5. **Basis-tagged numbers.** Every reproduced count/share is tagged
   Yes-only or doubled — the two bases are not interchangeable and are never
   silently compared against each other.

## License

Published under the **MIT license** ([`LICENSE`](LICENSE)) — no usage
restrictions of any kind. The standard MIT warranty disclaimer applies;
downstream users are responsible for compliance in their own jurisdictions.
