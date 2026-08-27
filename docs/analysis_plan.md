# Analysis Plan

**Committed:** 2026-07-16 (UTC). **Status:** primary document. §1–§6 unchanged since commitment; see §7 Addendum 1 (2026-07-28) for the construction re-pins forced by R1's reproduction, Addendum 2 (2026-07-28) for the fee schedule sourced from primary artifacts, Addendum 3 (2026-07-28) for the fee question's move to a series-level difference-in-differences, and Addendum 4 (2026-07-28) for the decision to collect the full R2 window and δ_pub's stated controlled sub-window — all made before any R2 estimate existed.

This document expands `Claude.md` (v1.1) §2/§4/§5 into exact equations, thresholds, and inequalities, committed once, before any R2 estimate is computed — per the spec's own requirement ("Commit `docs/analysis_plan.md` ... BEFORE computing any R2 estimate") and this repo's honesty framing: historical data means this is **specification commitment**, not outcome-blind pre-registration. R3 (§4 below) is the only genuinely prospective arm. Any later change is appended as a dated addendum (§7), never a silent rewrite of §1–§6 — the same append-only discipline the sibling lab's `docs/pre_analysis_plan.md` follows.

No R2 data has been analyzed as of this commitment — Phase 2 (fetch) is in progress and Phase 3 (R1 construction) has not run.

---

## 1. R1 — reproduction (2021 → 2025-04-30)

**Sequential gate**, before any estimate comparison: reconcile construction counts against BDW's pinned integers — 12,403 events / 46,282 Yes contracts / 156,986 Yes prices [Yes-only basis], 106,209+106,209 tail counts [doubled Yes+No basis]. Divergence on overlapping deterministic data is a coverage/filter question, not a sampling question — BDW's own standard errors are **not** the tolerance for this gate. Count deltas are reported first; estimate deltas (ψ, α, maker/taker split, etc.) are compared only after coverage is accounted for.

**Verdict vocabulary**, fixed here, applied per quantity:

- **confirmed** — counts reconcile within a documented coverage gap, AND sign + significance pattern reproduce.
- **partially confirmed** — pattern reproduces, magnitudes are materially different (quantified, attributed to coverage where possible).
- **diverged** — sign or significance pattern breaks on reconciled data.

## 2. R2 — extension (2025-05-01 → 2026-06-30)

### 2.1 Primary estimand

One pooled, category-interacted Mincer–Zarnowitz regression on Yes prices (cents), event-clustered standard errors, wild cluster bootstrap for any cell with fewer than 50 event clusters:

```
(Y − P) = α_c + ψ_c·P + Σ_b [ α_{b,c}·D_b + δ_{b,c}·(D_b·P) ] + ε
```

- `c` — category (interactions, not fixed effects, since ψ is a slope).
- `b ∈ {fee, publication}` — boundary dummies: `fee` = 1 on/after 2025-05-01, `publication` = 1 on/after 2025-09-08.
- The two primary test statistics are the **composition-weighted averages** `δ̄_fee` and `δ̄_pub`, weighted by the **frozen calendar-2024 category mix** (`data/frozen_2024_mix.json`, produced once during Phase 3's R1 construction from 2021–2025-04-30 data — an R1-window artifact, never recomputed from R2 data; Phase 7 refuses to run without it). Sports carries zero weight in this headline aggregate by construction (it did not exist in 2024) and is reported as its own stratum alongside it.

### 2.2 Verdict definitions (bind to formal tests, not per-window comparison)

Let `ψ̄_R1` be R1's reproduced full-sample ψ (§1) and its confidence interval. Verdicts are computed from a **cluster-robust test on the interaction coefficient `δ̄`** in the pooled regression above — never by comparing significance stars across separately-estimated per-window regressions (the informal trap BDW's own "diminishing bias" language falls into, and the trap this repo's methodological review flagged explicitly):

| Verdict | Condition |
|---|---|
| **persisted** | fail to reject `δ̄ = 0` AND reject `δ̄ = −ψ̄_R1` (full disappearance ruled out) |
| **attenuated** | reject `δ̄ = 0`, with `−ψ̄_R1 < δ̄ < 0` |
| **vanished** | fail to reject `δ̄ = −ψ̄_R1` AND reject `δ̄ = 0` |
| **reversed** | reject `δ̄ = 0`, with `ψ̄_R1 + δ̄` significantly `< 0` |
| **indeterminate** | none of the above cleanly hold — reported as such, never forced into the nearest label |

Applied separately to `δ̄_fee` and `δ̄_pub`.

### 2.3 Composition decomposition (mandatory companion to the headline)

```
Δψ_agg = Σ_c w̄_c · Δψ_c        (within)
       + Σ_c Δw_c · ψ̄_c        (between)
```

weights `w_c` from the frozen 2024 mix (§2.1). Any narrative sentence about "the bias" changing refers to the **within** component only; the between component is reported alongside, never folded into the headline claim.

### 2.4 Control venue (secular-trend check, not a difference-in-differences)

Polymarket's own monthly ψ path, same MZ spec, over **2025-05 → 2025-12 only** — computed from the SII-WANGZJ archive, which ends 2025-12-31. **Coverage gap, stated plainly:** R2's final ~6 months (2026-01 → 2026-06) have **no control venue**. Extending the archive is not merely unavailable — Polymarket's own 2026 fee reform begins January 2026 (crypto Jan, sports Feb, other categories Mar, per the sibling lab's sourced `data/fee_schedule.yaml`), so even a hypothetically longer archive would contaminate the control with Polymarket's own treatment inside this window. The Kalshi-vs-Polymarket differential is reported only over the covered sub-window; the later period is described as uncontrolled, not silently extrapolated.

Three caveats carried verbatim into any write-up:

1. Polymarket's tail bias is *reversed* relative to Kalshi's (Qin & Yang 2026) — this control informs market-wide secular efficiency drift, not level or sign; "parallel trends" language is not used.
2. Archive provenance: a different repository, a different use (the market's own calibration path, not a model-skill claim) — the sibling lab's own archive-usage guardrail does not apply here, and this line states why rather than leaving it to be inferred.
3. Spillover: BDW's publication could in principle move Polymarket too via cross-venue arbitrageurs. If the control shows a comparable δ at the same dates, that is reported as strengthening the secular-trend explanation, not as a defect in the design.

### 2.5 Secondary / descriptive (no verdict vocabulary, no escalation power on their own)

- Maker/taker return gap and the maker ≥50c margin over time, in the three fee layers (§3.2).
- Tail-bin (≤10c) post-fee loss rate path.
- Monthly ψ paths per category (illustration/descriptive; the composition-weighted `δ̄` tests in §2.2 are the inferential object, not a scan over these monthly points).

### 2.6 Horizon robustness (labeled, not a headline estimand)

The 10-daily-lookback panel pools observations across up to 11 horizons-to-close per contract. Re-estimate:

1. horizon-stratified ψ (ψ per lookback-day bucket), and
2. a one-observation-per-contract closing-price-only spec.

A `δ̄` that survives both is treated as evidence against pure horizon-composition drift; one that doesn't is reported as such, not discarded.

## 3. Fee handling

### 3.1 Return convention (pinned once)

For a buyer of side *s* at price *P* with per-contract fee *f*:

```
r = (payout − P − f) / P
```

Never subtract a per-notional fee from a per-capital return — the resulting 1/P bias is ≈20× at 5c and ≈2× at 50c, concentrated exactly on the tail bins and the ≥50c threshold the R2 headline depends on.

### 3.2 Three fee layers, every maker/taker quantity

| Layer | Definition |
|---|---|
| (a) gross / zero-fee | no fee subtracted |
| (b) net of own-era fees | the fee schedule in force on the trade's own fill date (`data/fees.yaml`) |
| (c) fee-held-constant counterfactual | the pre-2025-05 (taker-only) schedule applied to post-2025 trades |

The persistence narrative reads off layers **(a) and (c)**; layer (b) alone conflates fee incidence with behavioral change and is reported alongside, not as the headline.

### 3.3 Fee-sensitivity ribbon (pre-registered detectability rule)

For every fee-conditional R2 headline (tail-bin post-fee loss, maker/taker gap, maker ≥50c margin): recompute across a fee grid {zero-fee; BDW's pre-2025 taker formula `0.07·P·(1−P)`; the sourced post-2025 maker/taker rates ± a plausible band}, and report the **break-even fee rate** that drives each margin to zero.

**Pre-registered rule:** if a margin's sign flips anywhere inside the plausible fee band, that result is labeled **fragile** in the write-up, and — per §5 below — cannot trigger escalation on its own.

## 4. R3 — prospective arm (firewalled)

From 2026-07-04, the lab's live Kalshi collection adds order-book depth/spread covariates BDW's own tape lacks. Small *n*; labeled supplement only, never pooled with R1/R2's own estimates.

**Firewall rule:** R2's verdict (§2.2) is computed and locked to its own output artifact **before** any R3 number is examined. R2's narrative is not revised in light of R3, even if R3 is suggestive. This rule exists specifically because R3's window (from 2026-07-04) mechanically overlaps R2's tail (through 2026-06-30) — without a firewall, an analyst could let R3's early signal color how an ambiguous R2 verdict gets written up.

## 5. Escalation rule (bound to §2.2's tests, no informal language)

Escalate from a replication note to a standalone short paper **iff**:

```
( δ̄_fee  rejects zero at 5%, under the primary composition-weighted test )
                              OR
( δ̄_pub  rejects zero at 5%, under the primary composition-weighted test )
                              OR
( the maker ≥50c margin changes sign between layers (a) and (c)
  AND survives the entire fee-sensitivity ribbon — i.e. is NOT labeled "fragile" per §3.3 )
```

No other trigger. "Materially regime-shifted" is not used as a standalone justification anywhere in this repo's write-up — every escalation claim traces to one of the three conditions above.

## 6. Honesty framing (stated once, applies throughout)

This is **specification commitment**, not outcome-blind pre-registration: the data (2025-05 → 2026-06-30) already exists on Kalshi's servers as of this document's commitment date, even though this repo has not yet fetched or examined it (Phase 2 fetch is in progress; Phase 3 R1 construction, which the R2 pipeline in §2 depends on for the frozen 2024 mix, has not run). R3 (§4) is the only genuinely prospective arm — its data literally does not exist yet for markets closing after this document's commitment date. The verdict thresholds in §2.2, the fee layers in §3, and the escalation rule in §5 are fixed now, before any R2 estimate exists, specifically to remove analyst discretion at write-up time.

## 7. Addenda

### Addendum 1 — construction re-pins from R1's reproduction (committed 2026-07-28, UTC)

**Still before any R2 estimate.** `reports/r2/` does not exist and neither `kmt r2` nor any δ estimate has been computed as of this addendum. Everything below was decided from R1's reproduction against BDW's *published* integers, never from R2 data. §1–§6 above are unchanged, per this document's own append-only rule.

Why an addendum rather than an edit: R1's reproduction showed BDW's prose underdetermines their construction in three places, and each was resolved by measurement. The plan committed on 2026-07-16 described constructions we no longer use, so leaving it unamended while running R2 would have meant claiming commitment to a specification the code does not implement. Full evidence in `docs/r1_reproduction_findings.md`; the deciding numbers are restated here because they are what the commitment now rests on.

**Legitimacy of calibrating against their integers.** §1's sequential gate is what makes this sound rather than circular: counts define the *sample*, ψ is the *result*. Tuning the sample definition to reproduce their sample is calibration; tuning ψ to reproduce their ψ would be circular and is not done anywhere. Where a quantity under test *is* itself the target — the maker/taker figures — the construction was instead read off the source paper directly (item 4), precisely because inferring it from those integers would have been circular.

**1. Volume filter — CONTRACTS, not dollar notional (primary).** BDW write "volume ≥ \$1,000"; Kalshi's `volume` field is denominated in contracts and the API exposes no notional field. At the volume-filter stage our independently collected universe gives 44,946 contracts against their 46,282 (−2.9%) and 12,416 events against their 12,403 (**+0.1%**). The dollar-notional reading is retained as a **reported sensitivity branch** (it roughly halves the sample), logged under its own `universe_log` label so it cannot narrow the primary universe.

**2. No-trade lookback days — BACKFILL, not skip (primary).** Their own n decides it: 156,986 / 46,282 = **3.39** prices per contract, unreachable under skip (we measure 2.50; backfill gives 3.72, so the two rules bracket their value). Skip additionally dropped whole contracts, not just rows — 21.2% of in-scope contracts had no trade inside their closing ET day and contributed nothing at all. Skip is retained as a reported sensitivity branch. This amends the construction pin in `Claude.md` §3, which was itself amended on 2026-07-26 with the same evidence.

**3. Return-by-band entry price — every panel observation, not the closing day alone.** Their stated ≈ −20% average pre-fee return decides it: all observations give −0.250, closing-day-only gives −0.701. This also makes the Fig 5 figure and the MZ regression describe the same sample.

**4. Maker/taker basis — the doubled PANEL, not the fill tape.** Read directly off the primary PDF rather than inferred: Table 10 totals 313,972 observations with Makers exactly 156,986 (the doubled panel, one role per side), and the text states "because we include the same contract at different points during its lifetime … up to 11 times", which only parses on a panel basis. Roles follow the taker side of the trade that set each observation's price. Fees are asymmetric by construction — Figure 6 reports *post-fee* returns and makers were fee-exempt in their window.

**5. Binding consequence for R2 — one construction on both sides of every boundary.** δ measures the *change* in ψ at the fee and publication boundaries within our own data, and §2.2's verdicts reference our own `ψ̄_R1`. A panel or filter rule that differed across a boundary is the one thing that would actually break identification, so the primary construction (items 1, 2, 4) is applied uniformly to the R1 panel, the R2 panel and the pooled cross-boundary fit. Level fidelity to BDW is an R1 goal; internal consistency is R2's. This tightens §2.1 without altering its equation or thresholds.

**6. Fee-boundary precision — a disclosed limitation, not a change.** The source paper says only that "Kalshi began to charge fees on Makers after April 2025", with no date and no rate. `data/fees.yaml`'s 2025-05-01 therefore stands as an operationalization of that sentence, and the 0.0175 maker rate does **not** come from the paper and remains unconfirmed against a primary artifact. §3's three fee layers and §3.3's break-even ribbon are unchanged; the ribbon is what carries this uncertainty, and the "fragile" rule in §3.3 continues to withhold escalation where a margin's sign flips inside the plausible band. The paper *does* confirm the taker formula verbatim — `$0.07·P(1−P)`, order total rounded up to the nearest cent — which is what §3.1 and the implementation use.

**Unresolved dependencies as of Addendum 1, recorded so their absence is not discovered at write-up:**

- **Polymarket control venue (§2.4).** ~~The SII-WANGZJ archive carries no category column, so the Polymarket→Kalshi strata mapping §2.4 calls for cannot be built from it as it stands.~~ **RESOLVED 2026-07-28.** The archive still has no category column, but it does carry `event_slug`, `slug`, `event_title` and `question`, and the strata are now recovered from that text by ordered regex rules in `data/category_map_polymarket_kalshi.yaml` v2. Coverage on the control window: **94.7% of markets, 84.8% of volume** (`tools/measure_polymarket_categories.py`, 210,366 markets). An unrecognised market keeps `category = None` and still contributes to the market-wide ψ path, which is §2.4's headline and never depended on the strata; coverage is reported alongside any stratified figure rather than treated as a target to maximise. Two corrections came with it: the file's Kalshi-side vocabulary had been guessed from site navigation and was wrong in both directions (it contained "Culture", which does not exist in Kalshi's data, and omitted Exotics, Financials, Mentions, Commodities, Transportation, Companies, Social and Education), and the rule vocabulary is now built from measured token frequencies over the control window rather than from intuition.
- **R2 quote coverage.** As of this addendum, quotes exist for only 2 of R2's 14 months (2026-05, 2026-06); the months bracketing the publication boundary are not yet fetched. No δ can be computed until they are. This is a collection gap, not a specification change, and it is being closed before §2.1 is run.

### Addendum 2 — the fee schedule, sourced from primary artifacts (committed 2026-07-28, UTC)

**Still before any R2 estimate.** `reports/r2/` does not exist and no δ has been computed. Nothing below was learned from outcome data: every fact comes from documents Kalshi published, and the design consequence follows from what those documents *say the treatment was*, not from how any estimate came out. §1–§6 remain unchanged.

**This supersedes Addendum 1 item 6**, which recorded the maker fee's date and rate as unconfirmed and carried the uncertainty in §3.3's ribbon. They are now sourced, and the sourcing changed more than the two numbers.

**Evidence.** 16 dated captures of `kalshi.com/docs/kalshi-fee-schedule.pdf` spanning 2021-07 → 2026-02, archived in `docs/sources/fees/` with the parse in `version_history.json` (`tools/fetch_fee_schedule_history.py`); plus per-series `fee_type`/`fee_multiplier` for all 12,231 series from Kalshi's API, frozen in `data/series_fee_catalog.json` (`tools/fetch_series_fee_catalog.py`). `data/fees.yaml` is now generated from those two inputs by `tools/build_fees_yaml.py` and is no longer hand-written.

**What the artifacts say, against what the plan assumed:**

| | Assumed | Sourced |
|---|---|---|
| Maker fee, effective | 2025-05-01, read off BDW's "after April 2025" | **2025-05-13**, the document's own "Last Updated" stamp |
| Maker fee, form | `0.0175·C·P·(1−P)` | first **`round up(0.0025 · C)`** — flat per contract, no price dependence — becoming the quadratic 0.0175 form on **2025-07-08** |
| Maker fee, scope | exchange-wide | **an enumerated list of series**: 29 at introduction, 39 from 2025-06-05, 48 from 2025-07-08, 101 from 2025-09-02, 111 from 2025-09-17 |
| Taker fee | 0.07 throughout | 0.07 from 2021-08-01, but **0.14** in the 2021-07-20 capture, and **0.035** for S&P500 (`INX*`) and Nasdaq-100 (`NASDAQ100*`) markets in every capture from 2022-09 on |

BDW's own sentence is confirmed in direction and sharpened: makers were free everywhere until 2025-05-13, which is after their 2025-04-30 cutoff. Their uniform `0.07·P(1−P)` is confirmed verbatim as the *general* rate.

**Consequence for R1 (implemented).** R1's primary net-return figures are now priced with BDW's stated model explicitly (`fees/schedule.py:bdw_fee_model`), not with the sourced schedule, so that any gap against their Fig 5 is theirs to explain rather than an artifact of our fee model. The sourced schedule runs alongside as a reported sensitivity. The difference is itself a finding: the half-rate carve-out covers **18.3%** of R1's in-scope universe (7,266 markets) and 45 in-scope markets closed while the rate was 0.14. Neither appears in BDW's single-formula treatment. Gross returns and every ψ are untouched — fees enter only the net-return figures.

**Consequence for R2 (design question, deliberately NOT resolved here).** §2.1's `δ_fee` is specified as a break at a single exchange-wide date. The artifacts say there was no exchange-wide fee change: the fee reached an enumerated minority of series, and the size of that minority moved every time the list was revised. Measured on our own in-scope universe (`tools/measure_maker_fee_treatment.py`), with treatment read from `fees.yaml`'s dated lists:

| Window | Treated markets | Treated volume |
|---|---|---|
| First list era, 2025-05-13 → 2025-07-07 | 8.0% | 61.0% |
| All pre-October lists, 2025-05-13 → 2025-09-17 | 14.4% | 66.2% |
| Whole R2 window | 4.5% | 41.6% |

Monthly, the treated share of markets runs 5.5% (2025-05) → 9.4% → 17.6% → 14.5% → 32.0% → 33.5% (2025-10) → 22.9% → 16.7%, then decays through 2026 as the market count explodes.

*(Correction, same day: an earlier draft of this addendum reported 5.3% / 25.9%. That was computed from the 29-series introductory list alone over a window that did not match the fee's effective date, and it understates the treatment on both margins. The figures above use the full dated schedule.)*

So the treated set is a **minority of markets but a majority of volume** — and the MZ regression weights observations, not dollars, so what `δ_fee` actually sees is the market-count share: a step dummy applied to a sample most of whose observations were never treated, with treatment intensity that quadruples and then halves inside the window. A single break date is a poor description of that regardless of how the estimate comes out.

The same fact supplies the remedy: treated and untreated series coexist in the same months, giving a within-venue control group and a genuine difference-in-differences for the fee question — stronger identification than the pre/post break the plan committed to, and partly immune to the composition problem of §2.3 because sports grows in both arms. Recording it here rather than adopting it silently: switching a primary estimand is a specification change, it is the author's call, and R2 cannot run until quote collection finishes anyway. Whichever is chosen, `δ_pub` is unaffected — publication *was* an exchange-wide event.

**Remaining gap, carried explicitly.** From the 2025-10-01 version Kalshi removed the series list from the PDF and deferred to `kalshi.com/fee-schedule`, which is client-rendered and whose Wayback captures are empty shells. Per-series scope for 2025-10-01 → 2026-06-30 is therefore not directly observable. The two dated endpoints are **not nested** — 6 series left the list on 2025-09-17 and 8 more are absent from today's catalog, while 27 joined — so `fees.yaml` records evidence bounds, not logical ones: 103 series in both (primary), 138 in either. §3.3's ribbon is what carries the span, and §3.3's "fragile" rule continues to withhold escalation where a margin's sign flips inside it.

### Addendum 3 — the fee question moves to a series-level DiD (committed 2026-07-28, UTC)

**Still before any R2 estimate.** `reports/r2/` does not exist; `kmt r2` has not been run and no δ of any kind has been computed. This addendum resolves the design question Addendum 2 recorded and left open. It is a **specification change made from an institutional fact, not from data**: Kalshi's own published schedules say who was charged and when, and nothing here depends on how any estimate comes out. §1–§6 remain unchanged.

**What changes.** For the FEE question only, the primary estimand becomes the difference-in-differences coefficient `δ_did`, from

`(Y−P) = α + ψ·P + α_E·Ever + δ_E·(Ever·P) + Σ_m [α_m·D_m + δ_m·(D_m·P)] + α_D·Now + δ_D·(Now·P) + ε`

where `Now = 1` if the market's series carried a maker fee on the day it closed, `Ever = 1` for every row of a series treated at some point inside the panel, and `D_m` are calendar-month dummies. Month terms enter in the **slope** as well as the level, because the estimand is a slope. `δ_D ≡ δ_did` is identified from variation *within a month, between* series that had the fee that month and series that did not.

`Now` is read from `data/fees.yaml` through the same `entry_for` lookup the net-return layers use, so the DiD and the fee layers cannot disagree about who was treated. Treatment is time-varying and staggered by construction, matching the five dated list revisions.

**Why this rather than §2.1's `δ_fee`.** §2.1 tests a break at one exchange-wide date, and there was no exchange-wide fee change. Two things follow from the treatment measurements in Addendum 2. First, the regression weights observations rather than dollars, so `δ_fee`'s post-dummy is applied to a sample in which only 8–14% of observations were ever treated in the relevant months. Second, and worse for a step dummy, treatment intensity is not a step: the treated share of markets runs 5.5% → 9.4% → 17.6% → 14.5% → 32.0% → 33.5% and back down, as Kalshi revised the list five times. The DiD instead compares treated and untreated series observed in the same months, which uses the variation the revisions actually created — and it additionally absorbs the sports-composition shift §2.3 exists to handle, since sports grows in both arms.

Note what this argument does **not** claim: the fee was not economically marginal. By volume the treated series were 61% of the first-list era and 66% through 2025-09-17. The case against `δ_fee` is about what the estimator sees and how the treatment is shaped, not about the fee being small.

**`δ_fee` is retained, computed, and written to the locked artifact unchanged.** Reporting only the new estimand would hide a specification change instead of recording one. Both appear in `reports/r2/verdict_lock.json`; the paper reports both and says which is primary and why.

**Verdict vocabulary for `δ_did`**, fixed here before any estimate, mirroring §2.2's structure with `ψ̄_R1` as the reference bias:

- **persisted:** fail to reject `δ_did = 0` AND reject `δ_did = −ψ̄_R1`;
- **attenuated:** reject `δ_did = 0` with `−ψ̄_R1 < δ_did < 0`;
- **eliminated:** fail to reject `δ_did = −ψ̄_R1` AND reject `δ_did = 0`;
- **reversed:** reject `δ_did = 0` with `ψ̄_R1 + δ_did` significantly < 0;
- **not identified:** the design has no treated rows, no controls, or a single month. Reported as such, **never as a null** — `fit_did` returns `None` here rather than a zero.
- indeterminate combinations reported as such, no forcing.

**Staggered adoption, disclosed not discovered.** Two-way fixed effects with staggered treatment is the Goodman-Bacon / Callaway–Sant'Anna problem: already-treated units act as controls for later-treated ones, and heterogeneous dynamic effects can give some comparisons negative weight. Every run therefore reports **two** fits — the TWFE one above and a **clean-controls** variant in which treated observations are compared only against never-treated series. Agreement is the evidence that weighting is not driving the result; on disagreement, the clean-controls estimate is the one reported.

**Escalation (§5), tightened not loosened.** The fee arm's trigger now reads off `δ_did`, and requires rejection at 5% in **both** fits. That is a stricter bar than §5's original single test on `δ̄_fee`, so this cannot manufacture an escalation that the committed rule would have withheld. `δ̄_pub` and the maker-margin trigger are untouched.

**`δ_pub` is unaffected.** Publication was an exchange-wide event; §2.1's specification for it stands exactly as committed.

### Addendum 4 — the R2 window is collected in full, and δ_pub gets a stated controlled sub-window (committed 2026-07-28, UTC)

**Still before any R2 estimate.** No δ of any kind has been computed; as of this addendum **no month before 2026-05 is analysable at all** (see the readiness table below), so there is nothing to have looked at.

**The decision: collect §2's window in full, 2025-05-01 → 2026-06-30.** It was measured against a cheaper alternative and the alternative was declined.

Measured readiness on 2026-07-28, where "analysable" means quoted, spread-passing, and with Pass 2's tape present:

| Months | Eligible | Quoted | In scope | Analysable |
|---|---|---|---|---|
| 2025-05 … 2025-12 | 103,841 | 29,798 | 26,751 | **0** |
| 2026-01 … 2026-04 | 219,222 | **0** | 0 | **0** |
| 2026-05, 2026-06 | 530,823 | 102,758 | 58,750 | 58,750 |

Everything analysable today sits *after* both boundaries, which is why neither δ exists yet. Collection is three serial steps, not one: boundary-month quotes (≈48h at the measured 1,548 markets/hour), Pass 2 for the ~93,000 markets that will pass the spread filter with no tape at all, then the same two steps for 2026-01 … 2026-04.

**Why the full window rather than truncating at 2025-12-31.** Truncation was the cheap option and had a real argument behind it: the Polymarket control archive ends 2025-12-31, so the analysis window and the control window would coincide. It was declined because the control was never doing identification work — §2.4 says so in terms, and Polymarket's reversed tail bias puts parallel-trends language off the table. What truncation would actually cost is the thing the paper is about: BDW's §6 question is whether the biases persist *now that they have been documented*, and a 2025-12-31 cutoff measures **3.7 months** after the 2025-09-08 publication. The full window measures **~10 months**. Post-publication decay is a multi-year literature; three months is not a persistence test.

**What the control's absence in 2026 does and does not cost, stated so it is not discovered later.** It is asymmetric:

- **`δ_fee` is unaffected across the whole window.** Its identification is now within-Kalshi (Addendum 3): treated and untreated series in the same months, which needs no second venue.
- **`δ_pub` has no within-Kalshi control** — publication hit every series — so the secular-trend check is the only external check it had. Therefore: **δ_pub's controlled sub-window is 2025-05-01 → 2025-12-31, and everything after it is an uncontrolled extension of the horizon.** The two are reported as separate rows, never averaged into one figure.
- This is structural, not a collection gap. Polymarket's own staggered 2026 fee reform (crypto January, sports February, the rest March) means even a longer archive would carry Polymarket's own treatment inside our window. No archive fixes it; only a different control venue would, and none is in scope.
- A weak but genuine internal substitute is available and will be reported alongside: a **placebo on the categories BDW found no bias in** (politics, entertainment — their Table 8). If publication drove a change, it should appear where the bias was and not where it was not.

**Timeline consequence, recorded rather than left implicit.** §6's mid-August draft date does not survive this decision, and the operator accepted that explicitly ("время терпит"). The draft moves with collection; nothing in §2's specification, thresholds or verdict vocabulary changes.

### Addendum 5 — the venue in §5 no longer exists, and the output splits in two (2026-08-27, UTC)

**After the verdict, and it changes no estimand.** This addendum records a
publishing fact and its consequence for how the results are written up. Nothing
in §1–§6, no threshold and no verdict is touched; the escalation determination
(`reports/r2/escalation.json`, no triggers) stands as computed.

**What was checked.** §5 names two default venues for the non-escalated path:
"IJF replication section or IREE". Both were verified before drafting:

- **IREE no longer exists.** It has been replaced by the *Journal of Comments
  and Replications in Economics* (JCRE), which **requires the replicated study
  to have been published**. Bürgi, Deng & Whelan remains a working paper (the
  January 2026 version; CEPR DP 20631, CESifo WP 12122, UCD WP2025_19, GWU
  2026-001, MPRA 126350), so this route is closed until they appear in a
  journal.
- **No dedicated replication section could be confirmed at the IJF.** Its author
  guidelines set out data and code policy for regular submissions; a replication
  article type was not found. §5's assumption that one exists is unverified and
  is not relied on.

So §5's default — "a replication note" — is not an executable instruction as
written. Not because the result is weak, but because the genre was assumed to
be available and is not.

**Consequence, decided by the operator on 2026-08-27.** The work is written as
two papers plus an immediate preprint:

- **Paper A** (`reports/final/paper_a_composition.md`), submitted now: the
  composition confound as the headline contribution, the primary-sourced fee
  schedule, and the persistence estimate. The replication appears only as a
  short validation section pointing at Paper B.
- **Paper B** (`reports/final/paper_b_replication.md`), held: the full
  replication of BDW's own window, with the count reconciliation, the two
  construction re-pins, the maker-return divergence and the 63-contract filter
  that does not reproduce. Submitted to a replication outlet once the original
  is published.
- **A preprint now**, because the priority risk is real and dated: BDW invited
  this question in print and run their own pipeline, and Becker (2026) — Kalshi,
  72.1M trades to November 2025 — appeared on SSRN on 2026-08-01, three weeks
  before this draft.

**The split is designed so neither paper carries the other's substance.** Paper
A owns the post-boundary window, the fee reconstruction and the DiD; Paper B
owns the original's window and its divergences, and cites Paper A for the fee
schedule it uses as a robustness input. Self-overlap is the one real hazard of
publishing twice from one body of work, and this is the line drawn to avoid it.

**What did not change.** Escalation was determined under §5 as amended by
Addendum 3 and did not fire. Paper A is not the "standalone short paper" §5
contemplates: that paper would have been a persistence claim strong enough to
stand alone, and this one is not, precisely because the identified estimate is
null. Paper A's claim is methodological — that aggregate before/after
comparisons on this venue are contaminated, by a measured 41% — which §5's
escalation rule never governed and does not license.

### Addendum 6 — the event study is post-hoc, and its two halves differ in status (2026-08-27, UTC)

**Recorded after the fact, which is the whole point of recording it.** The
event study in `reports/r2/event_study.json` and §6.3 of Paper A was NOT
pre-specified. It was written on 2026-08-27, after `delta_did` had returned its
tight null, in response to a critique that the parallel-trends assumption was
nowhere stated or tested. §1–§6 and every threshold are untouched; the locked
verdict is untouched.

**Why the two halves are not the same kind of object.**

The **pre-period test** is a validity check on an identifying assumption. It
could only ever undermine the design, never manufacture a result, so running it
late costs nothing but a date — and a failure would have been reported as
readily as the pass that occurred (chi2(5) = 3.24, p = 0.66). Validity checks
added post-hoc are unconditionally admissible in a way hypothesis tests are not.

The **post-period joint test** is a hypothesis test conducted after a
pre-specified test returned zero, and it returned p = 0.021. That is exactly the
shape an innocent specification search produces, and the estimate it supports —
a transitory reduction in the bias at three to four months — is interesting
enough to be tempting. It is therefore **labelled exploratory** in the abstract,
the introduction, §6.3, §6.4 and the conclusion, and the pre-specified null
remains the headline answer to the fee question.

**Why this is stated rather than quietly absorbed.** The paper's own argument is
that aggregates hide structure and that the order of operations matters. A paper
making that argument has no standing to be casual about the order in which its
own analyses were run. The correct disposition of an exploratory finding is a
pre-specified test on data not yet used, and that is what the conclusion asks
for rather than claiming the effect is established.

**Precedent this sets for the repo.** Any analysis added after an estimate is
known carries its date and its status in the paper that reports it. A validity
check says so and needs no further defence; a hypothesis test says so and is
labelled exploratory unless it was committed in advance.
