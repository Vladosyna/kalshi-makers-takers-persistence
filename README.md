# Kalshi Makers & Takers: Replication and Persistence

A read-only research instrument built around one question:

> Did Kalshi's favorite–longshot bias and maker/taker return asymmetry — as
> documented by Bürgi, Deng & Whelan through April 2025 — persist once Kalshi
> started charging maker fees and the paper itself went public?

Two halves, and the second is the contribution. **R1** reproduces Bürgi, Deng
& Whelan, *Makers and Takers: The Economics of the Kalshi Prediction Market*
(2026; CEPR DP 20631 / CESifo WP 12122 / MPRA 126350) over their own window,
2021 → 2025-04-30. **R2** then asks their own closing question — they write
that "it will be interesting to see if the biases and return patterns that we
have reported persist now that they have been publicly documented" — across
two dated treatments they could not observe: the maker fee (2025-05) and the
paper's first public posting (2025-09-08).

Three things make this more than a re-run of someone else's regression:

- **The fee treatment is not what the paper says it is.** Sixteen dated
  captures of Kalshi's own published fee schedule show the maker fee was
  never an exchange-wide regime change but a **per-series surcharge**, revised
  five times, covering 8.0% → 14.4% of in-scope markets (61% → 66% of
  *volume*). That turns R2's headline from an exchange-wide before/after
  break into a **series-level difference-in-differences with treated and
  control markets trading in the same months** — better identification, and
  it absorbs the sports-composition shift as a side effect. The same sources
  turn up two carve-outs BDW do not model: a 0.14 taker rate before
  2021-08-01, and a half rate for index markets covering 18.3% of R1.
- **The composition confound is the design, not a footnote.** Sports launched
  on Kalshi almost exactly at the R1/R2 boundary, volumes jumped, and BDW's
  own tables show the bias is category-heterogeneous — so a naive "did the
  aggregate bias move" comparison measures composition, not persistence.
  Hence frozen calendar-2024 mix weighting, a within/between decomposition,
  and verdicts bound to formal interaction tests.
- **Divergences are reported, not smoothed.** BDW's 63-contract mismatch
  filter does not reproduce from any public field; what is implemented
  instead is a settlement-consistency check, the retained contracts are
  logged as a divergence, and the discarded comparison became a validation —
  95.7% of tape-derived closing prices match Kalshi's independently reported
  final price to the cent.

**No execution code, no order placement, no Kalshi account required** — every
endpoint this repo touches is Kalshi's public, unauthenticated market data
API (verified live by Step Zero below). See [`CLAUDE.md`](CLAUDE.md) for the
full engineering brief (v1.1 plus dated amendments — single source of truth
for scope, methodology, and phasing) and
[`docs/analysis_plan.md`](docs/analysis_plan.md) for the R2 equations and
verdict thresholds, committed before any R2 estimate was computed;
[`kalshi-replication-spec.md`](kalshi-replication-spec.md) is a superseded
v1.0 draft, kept for history only.

This is a separate, standalone repository — not part of, and not dependent
on, `polymarket-forecast-lab`.

## What came out of it

Two papers, both in [`reports/final/`](reports/final/), with every figure in
them checked against the artifacts that produced it on every CI run.

**[Paper A — *Composition Shift and the Measurement of Bias in a Growing
Prediction Market*](reports/final/paper_a_composition.md)** ([LaTeX](reports/final/paper_a_composition.tex),
[SSRN sheet](reports/final/ssrn_submission_a.md)). The extension, targeting the
*International Journal of Forecasting*:

- **41% of the aggregate change in the favorite–longshot slope at the 2025 fee
  boundary is composition, not behaviour.** Sports went from 0.009% of the
  in-scope sample in calendar 2024 to 58.8% after May 2025. A naive before/after
  comparison reports that the bias *strengthened* under a fee designed to tax
  it — a conclusion with no mechanism behind it, reached by not asking what the
  sample was made of.
- **The maker fee was never an exchange-wide regime change**, so a step dummy is
  the wrong estimator. Properly identified as a series-level
  difference-in-differences, the pre-specified estimate is a tight null:
  **−0.0016 (0.0064)** on 98 treated series and 119,646 event clusters.
- An event study added *after* that result was known — and labelled exploratory
  wherever it appears — supports parallel trends (χ²(5) = 3.24, p = 0.66) and
  suggests a transitory reduction three to four months after treatment.
- **The exploitable margin survives**: the maker's advantage at prices ≥50c is
  +2.40% gross after the boundary and never crosses zero across the plausible
  fee band.

**[Paper B — the replication](reports/final/paper_b_replication.md).** BDW's
central findings reproduce on independently collected data: all five by-year
slopes in sign and significance, the maker margin at ≥50c at **+2.09% against
their +2.6%**, both tail maker shares within half a percentage point. Three
things do not reproduce and all three are reported rather than smoothed — the
sample is 28% smaller for a reason that is named and quantified, the overall
maker return differs while its components match, and the 63-contract mismatch
filter cannot be reconstructed from any public field.

**Paper B is held until the replicated study is published** — replication
outlets require the original to have appeared, and as of 2026-08-28 it is still
a working paper. That status is re-checked before any submission.

Both drafts were scored against an external seven-dimension rubric and the
findings recorded: [Paper A](reports/final/review_rubric_a.md),
[Paper B](reports/final/review_rubric_b.md).

## Why this exists

**BDW's sample cutoff is a fee-regime boundary, not an arbitrary date.** They
stop in April 2025 because, in their words, Kalshi "began to charge fees on
Makers after April 2025" — a change that directly taxes the paper's headline
exploitable margin, maker returns of **+2.6% on contracts ≥50c**. Everything
after their window therefore lives under a treatment aimed squarely at the
thing they measured, and nobody has looked.

**The two treatments are separable in time.** The maker fee (2025-05) and the
paper's first public posting (CEPR, 2025-09-08) sit roughly four months apart,
which is what makes a coarse decomposition possible at all: a bias that decays
at the fee date is priced-in cost, one that decays at the publication date is
the anomaly being arbitraged away. That is the McLean–Pontiff
post-publication-decay question, asked on a prediction market rather than a
stock cross-section, on an anomaly its own authors invited someone to re-test.

**And it is answerable on purely historical data**, from a public API, with no
account and no execution — which is why the whole thing is a read-only
instrument that can be re-run end to end by anyone who clones it.

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
in the spec before Step Zero's fetch completed. See `CLAUDE.md` for the
resulting design (frozen-mix reweighting, pooled interaction tests, the
fee-sensitivity ribbon with a pre-registered "fragile" rule).

## Project status

**Complete.** Collection finished 2026-08-25; the analysis, both papers and
their verification are done. What remains is submission, and one open action the
replication commits to: contacting the original authors about the maker-return
divergence.

| | |
|---|---|
| Trade tape | **376,760,957 fills**, 62 monthly partitions, 12.4 GB |
| R1 window (2021 → 2025-04) | 33,222 contracts, 10,061 events, 124,732 Yes prices |
| R2 window (2025-05 → 2026-06) | 391,427 in-scope markets, all taped |
| Tests | **450 passing**, no network required |
| Manuscript checks | 73 figures, 7 invariants, 7 quotations, LaTeX structure |

All ten phases of the engineering brief are implemented: step-zero access gate,
two-pass fetch, R1 filters and count reconciliation, the sourced fee schedule,
the Mincer-Zarnowitz machinery with verified clustering equivalence, the
three-layer fee decomposition and sensitivity ribbon, the R2 pooled regression
and composition decomposition, the Polymarket control overlay, the R3 firewall,
and the escalation rule. The per-phase checklist is in the git history; it is
not repeated here because every box is ticked.

## Quickstart

Requirements: Python 3.12+ and [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/Vladosyna/kalshi-makers-takers-persistence && cd kalshi-makers-takers-persistence
uv sync
uv run pytest                # 450 tests, no network required
uv run ruff check .
uv run kmt --help
uv run kmt step-zero         # hard gate -- re-verify before any fresh fetch
```

Nothing above touches the network except `step-zero`. The analysis artifacts and
both manuscripts are committed, so the verification suite below runs on a fresh
clone with no data collection at all.

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

`pypdf` is a dev dependency, used by `fetch_fee_schedule_history.py` for the
parsing half (the archiving half is stdlib-only) and by
`audit_source_quotes.py --pdf`. It was deliberately excluded while collection
was running, because adding a dependency forces a `uv sync` and that cannot run
while a collector process holds `.venv/Scripts/kmt.exe` open. Collection
finished on 2026-08-25 and the reason expired; leaving it undeclared after that
only meant those tools worked on whichever interpreter happened to have it.

### Verifying the manuscripts

Four checks, run on every CI push. Each exists because something got past a
careful human read, and each is named for what it caught.

| Check | What it does | What it found |
|---|---|---|
| `tools/verify_paper_figures.py` | Reads each value from its artifact, formats it the way the paper should render it, and asserts that string is in the paper — 73 figures plus 7 cross-artifact invariants | A headline sample size (392,597) that **no artifact supported**, and an escalation verdict left `escalate: true` under a rule that had been superseded |
| `tools/audit_source_quotes.py` | Every quoted fragment in both drafts must be a recorded quotation from [`docs/source_quotes.yaml`](docs/source_quotes.yaml); `--pdf` re-verifies those against the source | **Three passages presented as quotations that the replicated paper does not say** — paraphrases from this project's own notes that hardened into quotation marks |
| `tools/lint_tex.py` | Structural checks on the LaTeX build: environments, braces, citations resolving to bibitems, refs to labels, escaping, table shapes, and that every figure in the Markdown reached the `.tex` | Its own first version, which used regexes whose backslash escaping silently matched nothing and reported a section that was sitting in the file |
| `tools/check_doc_links.py` | Every relative link in every Markdown file, resolved against **git's index** rather than the working directory, case included | A case-only mismatch invisible on Windows: git tracked `Claude.md` while the filesystem showed `CLAUDE.md`. Its own first version could not detect this and had to be fixed by [a test](tests/test_doc_links.py) |
| `tests/test_r3_firewall.py` | Fails if any `r3` import appears outside `src/kalshi_mt/r3/` | — |

The direction matters. A hand-check starts from the paper and finds a source for
each claim; it never notices a claim whose source was never there. These start
from the artifact.

`tools/build_paper_pdf.py` compiles the LaTeX and then checks the **rendered
PDF** against the artifacts — the same artifact-first direction, one step
further down the pipeline, because a compiler will happily build a document
with a wrong number in it. Current build: 20 pages, no errors, no undefined
references, all fonts vector, 22/22 figure and declaration checks. The
submission PDF is committed at
[`reports/final/paper_a_composition.pdf`](reports/final/paper_a_composition.pdf).

### Running the long fetches

**Historical, kept as an operations record.** Collection completed on
2026-08-25 and nothing here needs re-running to reproduce the papers. It is
retained because the failure modes below cost days to diagnose and are not
documented anywhere else.

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

**`Start-Process` detaches from the shell, not from the job object, and on
some hosts that is the difference that matters.** Where the shell runs inside
a service that keeps its descendants in a Windows *job object*, every
collector launched from it dies when that service restarts — orphaned rather
than parented, so tracing the parent chain shows nothing to blame. Observed
here on 2026-08-18 16:20:29 and again on 2026-08-19 10:26:03, both times with
the machine awake, no traceback, no exit summary, and the log stopping
mid-request within seconds of the service's own "stopped" line. The
diagnostic that identifies it: the collector's last log timestamp matches a
service-restart entry in the Windows Application log to the second, while the
System log shows no sleep, no reboot, and no bugcheck.

Creating the process from *outside* the job is the fix, and there are two
routes. Task Scheduler works — the Task Scheduler service creates the
process, so it never joins the caller's job — and is the mechanism the
scheduled-task section below is about. The cheaper-looking route, WMI
(`Win32_Process.Create` via `WmiPrvSE`), **was tried and does not work**:
[`tools/launch_detached.cmd`](tools/launch_detached.cmd) keeps the attempt and
its failure. The process is created successfully (`ReturnValue=0`) and then
dies within seconds, leaving a literal `^C` as the last byte of its log — the
WMI-created `cmd.exe` is given a console that immediately closes and delivers
a Ctrl+C. Do not spend the afternoon on it twice.

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

#### Advancing to the next phase: `tools/watch_and_advance.ps1`

A collection phase that finishes at 3am should not wait until morning for the
next one to start. [`tools/watch_and_advance.ps1`](tools/watch_and_advance.ps1)
polls for a **clean** finish of the Pass 1 quote fetch, repoints
`data/autostart_fetch.json` at Pass 2, and starts it.

It detects completion by the collector's own clean return — a stats JSON on
stdout — and **not** by `quoted == eligible`, which can stay false forever
because some markets 404 permanently (see above). Three branches, and the
third is why it is worth leaving running overnight:

| Observed | Action |
|---|---|
| `kmt` alive | keep waiting |
| gone, `.out.log` non-empty | clean finish → repoint config, start Pass 2 |
| gone, `.out.log` empty | it died → relaunch Pass 1 |

Like the restart script, it only ever *starts* processes — every launch goes
through `autostart_fetch.ps1` and inherits its guard, brake and audit trail —
and it stops at Pass 2 on purpose. `kmt build` / `kmt r1` / `kmt r2` are
analysis, they write the locked R2 artifact, and per
[`docs/analysis_plan.md`](docs/analysis_plan.md) that lock is a deliberate act
rather than something a timer performs unattended.

```powershell
powershell -ExecutionPolicy Bypass -File tools\watch_and_advance.ps1 -DryRun  # decide nothing, report what it would do
powershell -ExecutionPolicy Bypass -File tools\watch_and_advance.ps1          # for real; progress in data/logs/watch_advance.log
```

It shares the fragility it exists to cover: running inside the session's job
object, a Claude VM Service restart kills the watcher too. Collection is
unaffected if that happens — just start it again.

Two further mitigations remain operator-side because they change system state rather
than this program's behaviour: disable standby for the duration
(`powercfg /change standby-timeout-ac 0`), and check that Windows Update is not
configured to restart unattended overnight.

## Repository layout

```
src/kalshi_mt/      the package: fetch, store, r1, r2, r3, fees, control, report
tools/              one-shot measurements, provenance builders, manuscript checks
tests/              450 tests, no network
docs/
  analysis_plan.md          R2 equations, thresholds, verdict vocabulary, and six
                            dated addenda -- committed before any R2 estimate
  r1_reproduction_findings.md   the reconciliation against BDW's integers
  known_gaps.md             what is open, bounded, and carried rather than closed
  source_quotes.yaml        every quotation the papers take from the replicated paper
  sources/fees/             sixteen dated captures of Kalshi's published fee schedule
reports/
  r1/, r2/                  the analysis artifacts every figure is checked against
  final/                    both papers, the LaTeX build, the SSRN sheet, the rubric scores
data/                       fees.yaml, the frozen 2024 mix, the category map (the
                            rest -- database, tape, caches -- is gitignored)
```

`CLAUDE.md` is the engineering brief and the single source of truth for scope
and methodology; `kalshi-replication-spec.md` is its superseded v1.0 draft, kept
for history only.

## Citing this work

[`CITATION.cff`](CITATION.cff) is machine-readable and GitHub renders a "Cite
this repository" button from it. Cite the repository for the software and data
artifacts, and Paper A for the findings. The replicated study is Bürgi, Deng and
Whelan (2026), which is still a working paper — check its status before citing
it as published.

## Analysis discipline

A short field guide to the design choices this repo is built around — see
[`CLAUDE.md`](CLAUDE.md) for the full spec these implement.

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
