# Composition Shift and the Measurement of Bias in a Growing Prediction Market

### Evidence from Kalshi, 2021–2026

**Vladyslav Yurchyna**
Independent Researcher
vlad.yurchina@outlook.com

**Draft — 2026-08-27.** Target: *International Journal of Forecasting*.
Companion replication (in preparation for a replication outlet once the
original is published): `paper_b_replication.md`.
All figures regenerate from `reports/r1/r1_report.json`,
`reports/r2/verdict_lock.json`, `reports/r2/escalation_run.json` and
`reports/r2/event_study.json`.

**Pre-specification.** The R2 specification — the composition decomposition, the
static difference-in-differences, the verdict thresholds — was committed on
2026-07-28, before any R2 estimate existed. **The event study in §6.3 was not**;
it was added on 2026-08-27, after the static estimate was known. §6.4 states
which of its two halves is a validity check and which is exploratory, and the
abstract labels the exploratory result as such.

---

## Abstract

Prediction markets are now studied intensively enough that their own growth has
become a measurement problem. Using 376.8 million Kalshi fills through June
2026, we show that sports contracts went from 0.009% of the in-scope sample in
calendar 2024 to 58.8% after May 2025, and that **41% of the aggregate change in
the Mincer–Zarnowitz slope** at that boundary is composition rather than any
change in how the market prices risk. The natural before/after design across
early 2025 largely measures the arrival of an asset class.

We then ask the persistence question properly. Reconstructing Kalshi's fee
schedule from sixteen dated captures of its own published document, we find the
2025 maker fee was **not the exchange-wide regime change the literature
assumes**: a per-series surcharge covering 8.0% to 14.4% of in-scope markets,
revised five times, flat per contract before it was quadratic in price. That
rules out a step dummy and calls for a difference-in-differences between treated
and untreated series trading in the same months.

**The pre-specified estimate is a tight null: −0.0016 (0.0064)** on 98 treated
series. An event study added after that result was known supports parallel
trends (χ²(5) = 3.24, p = 0.66) and, **read as exploratory**, indicates a
transitory reduction three to four months after a series is charged. The maker's
return advantage at prices at or above 50c survives every plausible fee rate. We
publish the fee history, the category mapping and the full pipeline.

**Keywords:** prediction markets, favorite–longshot bias, composition effects,
difference-in-differences, transaction fees
**JEL:** G14, G13, D47, C52

---

---

## 1. Introduction

The favorite–longshot bias — cheap contracts winning less often than their
prices imply, expensive ones more often — is among the most replicated findings
in the study of betting and prediction markets (Thaler and Ziemba 1988;
Ottaviani and Sørensen 2008; Snowberg and Wolfers 2010). Kalshi, the first federally
licensed prediction market in the United States, has recently made it newly
measurable at scale: transaction-level data are public, the venue is large, and
its contracts settle unambiguously.

Two features of 2025 make it look like a natural experiment. Kalshi began
charging fees to liquidity providers, taxing the one margin recent work
identifies as exploitable. And in September 2025 the biases themselves were
publicly documented in a widely circulated working paper, whose authors closed
by inviting exactly the follow-up we conduct: whether the patterns persist "now
that they have been publicly documented."

The natural design is a before/after comparison of the aggregate bias. **Our
first result is that this design is contaminated, and we measure by how much.**

Kalshi did not merely grow across that boundary; it changed shape. Sports
contracts launched in early 2025 — almost exactly at the boundary any such study
would use — and by June 2026 they are 58.8% of the in-scope sample against
0.009% in calendar 2024. Because the bias is heterogeneous across categories,
an aggregate comparison mixes a change in pricing behaviour with a change in
what is being priced. Decomposed, 41% of the aggregate movement at the fee
boundary is the composition term.

This is not a hypothetical concern. Kalshi is being analysed now, on samples
that straddle the same boundary, and a naive aggregate comparison will report a
large apparent effect.

Our remaining contributions follow from taking the confound seriously.

**The fee treatment is not what it is assumed to be.** We reconstruct Kalshi's
fee schedule from sixteen dated captures of the exchange's own published
document, 2021-07 through 2026-02, plus per-series fee metadata for all 12,231
series. The maker fee was never exchange-wide: it is a surcharge on an
enumerated list of series, 29 at introduction and 111 by September 2025,
covering 8.0% to 14.4% of in-scope markets and 61% to 66% of volume. Its first
form was flat per contract, becoming quadratic in price only on 2025-07-08. Two
further carve-outs — a 0.14 taker rate before August 2021, and a half rate for
index markets covering 18.3% of the pre-2025 universe — are not modelled in the
existing literature at all.

**Properly identified, the fee produced no persistent change in the bias.**
Because treatment is per-series, staggered and revised, treated and untreated
series trade in the same months and a difference-in-differences is available.
The pre-specified estimate is −0.0016 (s.e. 0.0064) against never-treated
series. Treatment here was selected on market-making activity, which is adjacent
to the outcome, so the identifying assumption needs evidence rather than
assertion; an event study added after that estimate was known finds
pre-treatment coefficients jointly zero (p = 0.66), which supports it.

That same event study also finds post-treatment coefficients jointly non-zero
(p = 0.021), suggesting a transitory reduction peaking three to four months
after a series is charged. **We report this as exploratory**, for the reason
§6.4 sets out: it is a hypothesis test run after a pre-specified test returned
zero, which is the shape specification search produces even when nobody went
looking. The naive step-dummy coefficient disagrees with both, for a third
reason again: it is dominated by one category that has shrunk by a factor of
fifty while retaining nearly a third of the composition-held-fixed weight.

**The exploitable margin survives.** The maker's return advantage at prices at
or above 50c is +2.40% gross in the post-boundary window and never crosses zero
across the plausible band of maker fee rates.

Section 2 describes the data. Section 3 validates the pipeline against published
results. Section 4 is the composition result. Section 5 is the fee schedule.
Section 6 is the persistence estimate. Sections 7 and 8 cover robustness and
related work.

## 2. Data

All data come from Kalshi's public `trade-api/v2` endpoints — no account, no
authentication, no order placement. Collection runs in two passes: a
universe-wide pass for market metadata, the boundary trades a daily-lookback
price panel requires, and closing quotes for the spread filter; then a
full-tape pass restricted to contracts surviving the filters, because
maker/taker quantities need every fill's price, size and taker side.

The completed tape is **376,760,957 fills across 62 monthly partitions**. The
in-scope set for the post-boundary window — markets clearing $1,000 volume, 24
hours open, and a closing bid–ask spread at or under 20c — is **391,427
markets**, all of them taped.

Three construction choices are stated because each silently changes the sample,
and because the second is a correction to the natural reading of the prior
literature.

**Volume is denominated in contracts, not dollars.** The original screens on
"We focus only on contracts that have reached a total trading volume upon market closure of at least $1,000", which reads as dollar notional, but Kalshi's `volume` field counts
contracts and the API exposes no notional field. At the contract reading
our independently collected universe lands within 0.1% of the published event
count; the dollar reading roughly halves the sample. Since a sample rule that
differentially removes cheap strikes is itself a result in a paper about the
favorite–longshot bias, both are computed and the contract reading is primary.

**Prices are carried forward on no-trade lookback days.** The original collects
"the final traded price as the market closed and also, where available, previous prices from 24-hour intervals up to 10 days before markets closed" — and "where available" reads as skipping empty days. The published
counts settle it the other way: 156,986 prices over 46,282 contracts is 3.39 per
contract, which skipping cannot reach. On our tape, skipping yields 2.50 and
carrying forward yields 3.50. Carrying forward is primary.

**One construction on both sides of every boundary.** The estimands below
measure a *change* in slope within our own data against our own reference bias.
A construction that switched at a boundary is the one thing that would break
identification, so the rule is fixed before any estimate is computed.

Categories come from Kalshi's own taxonomy, mapped through a versioned table in
the repository.

## 3. Validation

Before using this pipeline to make a claim about a boundary, we check that it
reproduces what is already known about the pre-boundary window. Bürgi, Deng and
Whelan (2026, hereafter BDW) provide the reference points.

| Quantity | Ours | BDW |
|---|---|---|
| Maker return, price ≥50c | **+2.09%** | +2.6% |
| Taker return | −28.40% | −31.46% |
| Maker share, 1–10c band | 43.1% | 43.5% |
| Maker share, 90–99c band | 57.0% | 56.5% |
| ψ, 2021 | 0.0409 | 0.041 |
| ψ, 2025 (Jan–Apr) | 0.0171 | 0.021 |

All five of their by-year slopes are recovered with matching sign and
significance pattern; magnitudes run slightly below theirs, within roughly one
standard error. The bias itself reproduces directly: in the 1–10c band
contracts win 2.43% of the time at a mean price of 3.22c, and in the 91–99c band
97.86% at 97.08c.

Our sample is smaller than theirs — 33,222 contracts against 46,282 — and the
shortfall is almost entirely the spread filter: 3,257 markets (8.2% of those
clearing volume and duration) have no bid–ask history that Kalshi will serve, so
the loss is structural rather than a collection gap. The full reconciliation,
the construction branches and the divergences are the subject of the companion
replication and are not repeated here.

Two checks worth stating. Kalshi's taker-side fields are populated on **100.0%**
of all 376.8 million fills in every era. And the two-way (event, contract)
cluster-robust variance reduces to one-way event clustering when contracts nest
in events; estimated both ways on the real panel the standard errors agree to
fourteen decimal places, so one-way event clustering is used throughout without
hedging.

## 4. Composition

### 4.1 The venue changed shape, not just size

Kalshi launched sports contracts in early 2025. The timing is unfortunate for
anyone studying the 2025 fee change, because it is essentially the same date.

| Category | Calendar-2024 weight | Post-boundary weight | Change |
|---|---|---|---|
| **Sports** | **0.00009** | **0.5875** | **+0.5874** |
| Climate & Weather | 0.4744 | 0.0995 | −0.3749 |
| Financials | 0.3047 | 0.0059 | −0.2989 |
| Mentions | 0.0000 | 0.0646 | +0.0646 |
| Economics | 0.0690 | 0.0086 | −0.0604 |

Four categories present after the boundary — Exotics, Mentions, Social,
Transportation — did not exist in calendar 2024 at all.

This matters because the slope is category-heterogeneous. Estimated separately,
ψ ranges from 0.0107 in Entertainment to 0.0743 in Sports and 0.1206 in
Transportation. Re-weighting a heterogeneous quantity is not a neutral act.

### 4.2 Decomposing the aggregate change

Write the aggregate change in slope at a boundary as

  Δψ_agg = Σ_c w̄_c · Δψ_c  +  Σ_c Δw_c · ψ̄_c

where the first term holds composition fixed at the calendar-2024 mix and varies
only within-category behaviour, and the second holds behaviour fixed and varies
only weights. At the fee boundary:

| Term | Value | Share |
|---|---|---|
| Within (behaviour) | +0.0399 | 59% |
| **Between (composition)** | **+0.0278** | **41%** |
| Aggregate | +0.0677 | 100% |

The between term is dominated by one category. Sports alone contributes
**+0.0437** — more than the entire between component, with the shrinking
categories contributing negatively against it.

### 4.3 What this implies

An aggregate before/after comparison across early 2025 on Kalshi will find a
large apparent change in bias, of which roughly two fifths is the arrival of
sports contracts. The direction happens to be positive here, which is worth
noting: a naive reading of the aggregate would report that the bias *strengthened*
after a fee designed to tax it — a conclusion with no plausible mechanism behind
it, arrived at by not asking what the sample was made of.

### 4.4 What is and is not new here

The general principle is old. That an aggregate can move in the opposite
direction to every subgroup composing it is Simpson (1951); separating a
between-group weight change from a within-group behavioural change is the
Oaxaca (1973) and Blinder (1973) decomposition, and the shift-share logic that
underlies Bartik (1991) instruments. We claim no novelty for the arithmetic in
§4.2 and we use the standard form deliberately, so that the object being
reported is familiar.

What is specific to this setting is worth stating plainly, because the obvious
referee response to §4.2 is that it restates a textbook fact.

**The magnitude is not a textbook magnitude.** Shift-share decompositions were
developed for panels whose composition drifts over decades. A single category
going from 0.009% to 58.8% of the sample in fourteen months is not drift; it is
the venue becoming a different venue. The resulting distortion is large enough
to invert the economic reading rather than merely attenuate it: the naive
aggregate says a fee levied on liquidity providers made the market *less*
efficiently priced, which is not a mechanism anyone would defend if it were
stated aloud.

**The original's own robustness check does not reach this.** BDW anticipate the
category question and report that "Our results below are not sensitive to cutting the data off in December 2024 or to excluding the category containing sports bets." That check is correct on their
sample and does not cover ours, for a reason that is arithmetic rather than
methodological: sports is **4.3% of the observations inside their window** and
**58.8% after the boundary**, a factor of fourteen. Dropping a category worth
one observation in twenty-three barely moves an estimate, which is what they
found. The problem we identify is created by the share rising to a majority
*after* their sample ends, so no test run inside their window could have
detected it. Their check also asks a different question — whether a level
estimate survives deleting a category — where ours asks how much of a *change
across a boundary* is reweighting. Deleting sports and holding the mix fixed
are not the same operation.

**The trap is live, not hypothetical.** Kalshi is being analysed now, and the
samples in circulation straddle exactly this boundary — Becker (2026) covers
June 2021 to November 2025, which contains the sports launch in the middle. We
are not warning about a possible future error.

**And it is a property of young markets specifically.** A mature exchange adds
listings within existing asset classes; a new one adds asset classes. Prediction
markets are currently doing the latter — Kalshi added sports in 2025, and
Polymarket's own composition has moved comparably — so any study of this
literature's growth period inherits the problem rather than encountering it
occasionally.

The contribution is therefore the measurement and its consequence in a setting
where several groups are actively estimating the affected quantity, not the
decomposition identity.

The remedy we adopt is to fix the mix at the last full pre-sports year and to
report the two terms separately, with every behavioural claim referring to the
within term only. Sports is then reported as its own stratum rather than being
allowed to dominate an aggregate it did not exist to generate. Any equivalent
strategy would do; the point is that some strategy is required, and that its
absence is not visible in an aggregate coefficient.

## 5. What the fee schedule actually says

The design in Section 6 depends on the fee treatment being what we say it is, so
we sourced it rather than assuming it. Sixteen dated captures of Kalshi's own
published fee document (2021-07 to 2026-02) are archived in the repository with
the parse that produces the machine-readable schedule, alongside per-series fee
metadata for all 12,231 series obtained from Kalshi's API.

**The maker fee was never exchange-wide.** Resting orders are free, in the
document's own words, "unless they are included in our 'Maker Fees' section" —
an enumerated list of 29 series at introduction, then 39, 48, 101 and 111 by
2025-09-17. On our in-scope universe that is 8.0% of markets and 61.0% of volume
in the first-list era, rising to 14.4% and 66.2%. A minority of markets and a
majority of dollars — which is why the treatment is economically real and
statistically awkward at the same time.

**It was flat before it was quadratic.** The first form is `round_up(0.0025·C)`
per contract, with no price dependence whatsoever, becoming
`0.0175·C·P·(1−P)` only on 2025-07-08.

**It began on 2025-05-13**, by the document's own revision stamp.

**Two carve-outs are absent from existing models.** The taker rate was 0.14 in
the July 2021 capture, dropping to 0.07 on 2021-08-01. And S&P 500 and
Nasdaq-100 markets pay half rate — 0.035 — in every capture from September 2022
onward, covering **18.3%** of the pre-2025 in-scope universe.

One gap is open and carried as bounds rather than closed by assumption: from the
2025-10-01 revision the document stopped enumerating series, so membership after
that date is propagated through the fee-sensitivity analysis as evidence bounds
(103 series primary, 138 upper).

The methodological consequence is larger than the individual corrections. A step
dummy at a single exchange-wide date is the wrong estimator for a treatment that
touched a minority of markets, was revised five times, and whose intensity ran
5.5% → 9.4% → 17.6% → 14.5% → 32.0% → 33.5% before decaying. But the same facts
supply the remedy: because treatment is per-series and staggered, treated and
untreated series trade side by side in the same months.

## 6. Persistence, properly identified

### 6.1 The difference-in-differences

We estimate

  (Y−P) = α + ψ·P + α_E·Ever + δ_E·(Ever·P)
        + Σ_m [α_m·D_m + δ_m·(D_m·P)] + α_D·Now + δ_D·(Now·P) + ε

where `Now` indicates that the market's series carried a maker fee on the day it
closed, `Ever` marks every observation of a series treated at some point, and
`D_m` are calendar-month dummies entering the slope as well as the level,
because the estimand is a slope. `δ_D` is identified from variation *within a
month, between* series that carried the fee and series that did not. Treatment
is read from the sourced schedule through the same lookup used for net returns,
so the design and the fee accounting cannot disagree about who was treated.

| Specification | δ_did | s.e. | 95% CI |
|---|---|---|---|
| Two-way fixed effects | +0.0113 | 0.0129 | [−0.0139, +0.0365] |
| **Clean controls** | **−0.0016** | **0.0064** | [−0.0141, +0.0109] |

Estimated on 98 treated series, 141,708 treated observations against 1,188,737
controls, 119,646 event clusters across 60 months, with no cell thin enough to
require a wild cluster bootstrap.

Because two-way fixed effects under staggered adoption permits already-treated
units to serve as controls for later-treated ones, with the attendant negative
weighting (Goodman-Bacon 2021), both fits are reported always; the
clean-controls variant restricts comparisons to never-treated series — the
correction Callaway and Sant'Anna (2021) and Sun and Abraham (2021) formalise —
and is the one reported on disagreement.

**Read on its own, this says the maker fee did not change the average slope.
§6.3 shows that reading is incomplete.**

### 6.2 The identifying assumption, and why selection sharpens it

δ_did is unbiased only under **parallel trends**: absent the fee, treated and
untreated series would have moved together in slope. This is an assumption, not
a result, and it deserves more scrutiny here than it usually gets, because
assignment to treatment was plainly not random.

Kalshi charged an enumerated list of series. Section 5 shows which: 8.0% to
14.4% of in-scope markets carrying 61% to 66% of volume — that is, the series
where market-making is most active and most profitable. Maker profitability is
not incidental to what we are measuring. It is economically linked to the very
slope the estimand concerns: §6.6 reports the maker's return advantage as a
headline quantity, and an exchange choosing to tax the series where that
advantage is largest is selecting on something adjacent to the outcome.

The `Ever` terms absorb **permanent** differences in level and slope between the
charged and uncharged groups, and those differences are certainly present. They
do not absorb a **differential trend**. Selection of this kind therefore raises
the bar that parallel trends must clear rather than lowering it, and asserting
the assumption without evidence would be the weakest point in the paper.

### 6.3 Event study: pre-trends, and a dynamic effect the average hides

We re-estimate with leads and lags measured in months from **each series' own
first treatment month**, never-treated series anchoring the calendar path, k=−1
omitted as the reference and endpoints binned. The sample is the same 1,330,445
observations and 119,646 clusters; 98 treated series fall into 11 adoption
cohorts.

| Event time k | δ_k | s.e. | 95% CI |
|---|---|---|---|
| −6 | −0.0428 | 0.0285 | [−0.0988, +0.0131] |
| −5 | −0.0187 | 0.0624 | [−0.1410, +0.1037] |
| −4 | −0.0975 | 0.0875 | [−0.2690, +0.0740] |
| −3 | +0.0016 | 0.0633 | [−0.1225, +0.1257] |
| −2 | −0.0235 | 0.0410 | [−0.1039, +0.0569] |
| **−1** | — | — | *reference* |
| 0 | −0.0092 | 0.0258 | [−0.0598, +0.0414] |
| +1 | +0.0179 | 0.0278 | [−0.0365, +0.0724] |
| +2 | −0.0120 | 0.0291 | [−0.0691, +0.0451] |
| **+3** | **−0.0771** | 0.0342 | **[−0.1441, −0.0102]** |
| **+4** | **−0.0826** | 0.0342 | **[−0.1496, −0.0157]** |
| +5 | −0.0462 | 0.0369 | [−0.1185, +0.0261] |
| +6 | −0.0210 | 0.0257 | [−0.0713, +0.0293] |
| +7 | −0.0552 | 0.0346 | [−0.1230, +0.0127] |
| +8 | −0.0242 | 0.0257 | [−0.0746, +0.0261] |
| +9 | −0.0037 | 0.0244 | [−0.0515, +0.0441] |

**Parallel trends is supported.** Every pre-treatment interval covers zero, and
the joint Wald test that all five are zero gives **χ²(5) = 3.24, p = 0.66**.
Slopes were not already diverging before Kalshi charged anybody. Given the
selection argument above, this is the evidence the design needed rather than a
formality.

**The post-treatment coefficients are jointly non-zero — an exploratory finding,
labelled as such here and everywhere it is repeated.** The joint test that all
ten are zero gives **χ²(10) = 21.01, p = 0.021**, rejecting at 5%. We report the
joint test rather than the two starred rows, because ten coefficients tested
individually at 5% would produce at least one "significant" month roughly forty
percent of the time under the null; the joint statistic is what establishes
there is something to explain.

The exploratory label is not modesty. This test was not pre-specified and was
run after the pre-specified one returned zero — see the status note at the end
of this section, which readers should take as attached to every sentence in the
next two paragraphs.

The shape is coherent: nothing at impact, a **negative** deviation peaking at
three and four months after a series is charged — the favorite–longshot slope
*falling* in treated series relative to controls — and decay back toward zero by
nine months. So the fee did move the bias, transitorily and with a lag, in the
direction of less bias.

We flag two things we cannot settle. The delayed onset is not obviously
explicable by a fee that takes effect immediately, and we do not have a
mechanism we would defend; candidate explanations include contracts written
before treatment settling after it, and adjustment in maker behaviour rather
than in posted prices. And the point estimates at k=+3 and +4 are large relative
to the baseline slope of 0.0254 — they imply a temporary sign reversal — with
correspondingly wide intervals. We report the shape and the joint test, and we
do not build a magnitude claim on two coefficients.

**When this analysis was added, and why the two halves differ in status.** The
static difference-in-differences was pre-specified in the analysis plan
committed on 2026-07-28. The event study was not: it was added on 2026-08-27,
after the static estimate was known, in response to a critique of the
then-unstated parallel-trends assumption. The two halves of it do not have the
same epistemic standing.

The pre-period test is a **validity check on an identifying assumption**. It was
worth running whatever it showed, it can only undermine the design rather than
manufacture a finding, and we would have reported a failure as readily as this
pass. Adding such a check late costs nothing but a date.

The post-period joint test is a **hypothesis test conducted after a
pre-specified test returned zero**, and it returned p = 0.021. We label it
exploratory on that basis. We say so plainly because a transitory effect
surfacing in a second analysis, after the first found nothing, is precisely the
pattern that innocent specification search produces — and a paper arguing that
aggregates hide structure has no standing to be casual about the order in which
its own analyses were run.

Accordingly the pre-specified null remains the headline result for the fee
question, and the hump is reported as a labelled exploratory finding that
warrants a pre-specified test on future data rather than as an established
effect.

### 6.4 What the static estimate does and does not say

The static δ_did of −0.0016 (0.0064) is not wrong; it is an average, and its
tight interval is a statement about that average rather than about every month
within it. Averaging a delayed, transitory, decaying effect over ten
post-treatment months is exactly how it becomes indistinguishable from zero.

This is worth naming, because it is the same failure mode as §4 in a different
guise. There, an aggregate over categories hid the fact that its movement was
composition. Here, an aggregate over event time hides the fact that a null is
made of a hump. In both cases the aggregate is not false, and in both cases
reporting only the aggregate would have been.

The honest summary of the fee question, with each part carrying its status:
**pre-specified, no persistent change in the bias; exploratory, a transitory
reduction around three to four months after treatment; and separately
established, no evidence that the maker's exploitable margin was eliminated** —
the last of which §6.6 shows directly and which was pre-specified as the
fee-sensitivity ribbon.

**A limitation we state rather than bury.** With 11 adoption cohorts, the
event-study coefficients can still be contaminated across cohorts in the way
Sun and Abraham (2021) describe, since a treated cohort's post-period overlaps
another's pre-period. Never-treated series carry most of the identifying weight
here, which limits the problem but does not eliminate it. A fully
interaction-weighted or Callaway–Sant'Anna estimator would settle it, and we
regard that as the natural next step rather than something this draft has done.

### 6.5 The naive coefficient, and why it disagrees

The composition-weighted step coefficient at the fee boundary is +0.0399 with a
95% interval of [+0.0071, +0.0726] — nominally significant, positive, and
therefore implying the bias strengthened under a fee designed to tax it.

Two features explain it and neither is behavioural. First, as Section 5
establishes, the step is applied to a sample most of whose observations were
never treated, against a treatment whose intensity quadrupled and then halved
inside the window. Second, its within component is essentially one category:
Financials contributes +0.0437 of the +0.0399, on a within-category slope change
of +0.1435, while holding 30.5% of the composition-held-fixed weight against
0.59% of the current sample. Holding the mix fixed is correct — it is the whole
point — but the consequence is that the headline rests on a cell that has shrunk
fiftyfold, and we decline to build a persistence claim on it.

### 6.6 The exploitable margin survives

The maker's advantage at prices at or above 50c, in the post-boundary window,
computed in three fee layers on 202,725,609 maker and 167,925,545 taker sides
with no observation lost to gaps in the fee history:

| Layer | Margin |
|---|---|
| Gross | **+2.40%** |
| Net of own-era fees | +4.39% |
| Pre-2025 schedule held constant | +4.54% |

The net layer exceeding the gross layer is the expected direction rather than an
anomaly: under fees the taker pays and the maker mostly does not, so the spread
between them widens. Swept across an eleven-point grid spanning the plausible
maker fee band, the margin declines monotonically from +0.0454 to +0.0431 and
**never crosses zero**. There is no break-even rate inside the band.

The margin documented before the boundary is therefore still present after it,
and no plausible maker fee erases it.

### 6.7 The publication boundary

The publication coefficient is −0.0311 with an interval of [−0.0637, +0.0014].
It contains zero, and it also contains the negative of our reference bias. On
this sample, persistence and disappearance cannot be distinguished. We report
that rather than choosing.

## 7. Robustness

**Horizon.** The panel pools eleven daily lookback horizons. Estimated
separately, the naive fee coefficient swings from +0.098 at one day to −0.008 at
nine; the one-observation-per-contract closing-price specification gives +0.0117
against the pooled +0.0399. The difference-in-differences is not subject to this
sensitivity, but the failure of the naive coefficient to survive the horizon
check is a further reason not to read it behaviourally.

**Control venue.** Polymarket's monthly slope over 2025-05 to 2025-12 provides a
secular-trend check — not a difference-in-differences, and we do not use
parallel-trends language. Three caveats are stated here rather than left for a
referee. Polymarket's tail bias runs in the opposite direction to Kalshi's (Qin and Yang
2026), so the comparison controls for market-wide drift in efficiency and not
for level or sign. The Polymarket data come from a public third-party archive, which the
author worked with in separate research on Polymarket forecasting — the project this
paper's question originated in. That work measures forecasters' skill; this one
measures the market's own calibration path, so the archive is put to a different
use here, and its full provenance is documented in the repository. And cross-venue
arbitrage could propagate the publication event to Polymarket as well, which
would strengthen a secular-trend reading rather than undermine the design.

The control window closes at 2025-12-31 for a structural reason: Polymarket
began its own staggered fee reform in January 2026, so a longer archive would
carry that venue's own treatment inside ours. The fee estimate is unaffected,
being identified within Kalshi. **The publication estimate is controlled only
through 2025-12-31**, and the remaining six months are reported as an
uncontrolled extension of the horizon rather than averaged into a single figure.

## 8. Related work

**Kalshi and the favorite–longshot bias.** BDW is the immediate antecedent and
remains a working paper as of this draft (January 2026 version; CEPR DP 20631,
CESifo WP 12122, UCD WP2025_19, GWU 2026-001, MPRA 126350). Our companion paper
is a full replication of it. The favorite–longshot bias itself is among the most
replicated regularities in betting and prediction markets — surveyed by
Ottaviani and Sørensen (2008), documented in parimutuel betting by Thaler and
Ziemba (1988) and estimated structurally by Snowberg and Wolfers (2010) — and we
take its existence as established rather than as something this paper
demonstrates. On prediction markets as forecasting instruments generally we
follow Wolfers and Zitzewitz (2004).

Whelan (2023) introduces fees into a prediction-market model and shows that fees
levied on winnings generate a form of favorite–longshot bias in post-fee loss
rates. It is theoretical and uses no Kalshi data. Section 5 speaks directly to
its assumptions: the fee it models as uniform is neither uniform nor, in its
first eight months, price-dependent.

Becker (2026) analyses 72.1 million Kalshi trades from June 2021 to November
2025, confirms the longshot bias by price level, decomposes returns by market
role — takers −1.12% and makers +1.12% mean excess return per trade — and
documents a YES/NO asymmetry in taker order flow. Its role decomposition agrees
with ours in direction; magnitudes are not comparable, since the estimand is
excess return per trade rather than return on a contract position. It does not
address the fee regime, dated boundaries, or composition, and its sample ends
seven months before ours. We note that its window straddles the sports launch,
which is the configuration Section 4 is about.

**Anomalies after publication.** The publication boundary in §6.7 asks a
question with an established finance literature behind it. McLean and Pontiff
(2016) estimate that cross-sectional return predictors decay by roughly 58% out
of sample after publication, of which about a third is attributable to
publication itself rather than to in-sample overfitting, and interpret the
residual decay as informed trading against a documented signal. The prediction
market case is cleaner in one respect and harder in another: contracts settle
unambiguously, so there is no benchmark model to misspecify, but a single venue
with two candidate treatments four months apart supports far less separation
than a cross-section of thousands of predictors. BDW's own closing invitation is
this literature's question asked of their result, and §6.7 reports that our
sample cannot answer it.

**Staggered difference-in-differences.** Our treatment is adopted at different
dates by different series, which is the setting in which conventional two-way
fixed effects is now known to misbehave. Goodman-Bacon (2021) shows that the
TWFE estimand is a weighted average of all available two-group comparisons,
including ones that use already-treated units as controls for later-treated
ones, and that those comparisons can receive negative weight when effects are
heterogeneous over time. Callaway and Sant'Anna (2021), Sun and Abraham (2021)
and de Chaisemartin and d'Haultfœuille (2020) each propose estimators that
restrict comparisons to clean control groups and aggregate the resulting
group-time effects explicitly.

Our clean-controls specification is the simplest member of that family: it
restricts every comparison to treated-versus-never-treated, which is precisely
the correction those papers identify as necessary. We report it alongside the
TWFE fit rather than instead of it, and treat their agreement as the evidence
that weighting is not driving the result. Where they disagree, the
clean-controls estimate is the one reported. The event study in §6.3 is
specified in the same spirit — event time is measured relative to each series'
own adoption date, and never-treated series anchor the calendar path.

**Composition and decomposition.** The within/between decomposition in §4.2 is
standard: Simpson (1951) for the aggregation reversal, Oaxaca (1973) and Blinder
(1973) for the two-term form, and the shift-share tradition behind Bartik (1991)
for holding a mix fixed while letting behaviour vary. §4.4 states what we do and
do not claim as new.

## 9. Conclusion

A venue that grows by changing what it lists cannot be studied with an aggregate
before/after comparison. On Kalshi, 41% of the apparent change in bias at the
2025 fee boundary is the arrival of sports contracts, which went from 0.009% to
58.8% of the sample in fourteen months. The remedy is cheap — fix the mix,
decompose, report both terms — and its absence is invisible in the coefficient
it distorts.

On the question that motivated the exercise: the maker fee, correctly measured
as the per-series and repeatedly revised surcharge it actually was, produced
**no persistent change in the bias**. That is the pre-specified result and it
stands as the answer.

An event study added afterwards, in response to a referee's question about the
identifying assumption, supports that assumption — pre-treatment slopes were not
diverging, which the selection into treatment made worth checking rather than
assuming — and additionally suggests a transitory reduction peaking three to
four months after a series is charged. We label that second finding exploratory
and do not treat it as established, because it emerged from an analysis run
after the pre-specified one returned zero. If it is real, it should survive a
pre-specified test on data this paper does not yet have, and that is the test we
would want run before anyone believes it.

The maker's advantage at prices at or above 50c persists after the boundary and
survives every plausible fee rate, so whatever the fee did, it did not remove
the edge. Whether the public documentation of these patterns changed them cannot
be settled on this sample, and we do not claim it can.

The fee history, the category mapping, the archived source documents and the
complete pipeline are public.

---

### Declaration of interest

The author declares no competing financial interest. The author does not trade
on Kalshi, holds no positions on the venue studied, has no financial or personal
relationship with the exchange or with the authors of the work replicated, and
received no funding for this research.

### Data and code availability

The repository contains the collection pipeline, the analysis code, sixteen
archived captures of Kalshi's fee schedule with the parser that turns them into
a machine-readable step function, the category mapping table, and the committed
analysis plan with its dated amendments. It is MIT-licensed and contains no
execution code: every endpoint used is public and unauthenticated.

---

## Declaration of Generative AI and AI-assisted technologies in the writing process

During the preparation of this work the author used Claude (Anthropic) in order
to draft and revise manuscript prose and to generate the data-collection and
analysis code in the accompanying repository. After using this tool the author
reviewed and edited the content as needed and takes full responsibility for the
content of the publication.

---

## References

Bartik, T.J., 1991. *Who Benefits from State and Local Economic Development
Policies?* W.E. Upjohn Institute for Employment Research, Kalamazoo, MI.

Becker, J., 2026. The Microstructure of Wealth Transfer in Prediction Markets.
Self-published 18 January 2026; formalized version, SSRN Working Paper 7217640,
1 August 2026.

Blinder, A.S., 1973. Wage discrimination: reduced form and structural estimates.
*Journal of Human Resources* 8 (4), 436–455.

Bürgi, C., Deng, W., Whelan, K., 2026. *Makers and Takers: The Economics of the
Kalshi Prediction Market.* Working paper, January 2026 version. CEPR Discussion
Paper 20631; CESifo Working Paper 12122; UCD Working Paper WP2025_19; GWU
Working Paper 2026-001; MPRA Paper 126350. (The GWU series cover sheet, dated
February 2026, reads "Makers *or* Takers"; the paper's own title page inside
that document reads "Makers *and* Takers" and its 44 pages are identical to the
January version. We cite the authors' title.)

Callaway, B., Sant'Anna, P.H.C., 2021. Difference-in-differences with multiple
time periods. *Journal of Econometrics* 225 (2), 200–230.

de Chaisemartin, C., d'Haultfœuille, X., 2020. Two-way fixed effects estimators
with heterogeneous treatment effects. *American Economic Review* 110 (9),
2964–2996.

Goodman-Bacon, A., 2021. Difference-in-differences with variation in treatment
timing. *Journal of Econometrics* 225 (2), 254–277.

McLean, R.D., Pontiff, J., 2016. Does academic research destroy stock return
predictability? *Journal of Finance* 71 (1), 5–32.

Oaxaca, R., 1973. Male–female wage differentials in urban labor markets.
*International Economic Review* 14 (3), 693–709.

Ottaviani, M., Sørensen, P.N., 2008. The favorite-longshot bias: an overview of
the main explanations. In: Hausch, D.B., Ziemba, W.T. (Eds.), *Handbook of
Sports and Lottery Markets.* Elsevier, Amsterdam, pp. 83–101.

Qin, B., Yang, R., 2026. *Polymarket-v1 Database.* arXiv:2606.04217.

Simpson, E.H., 1951. The interpretation of interaction in contingency tables.
*Journal of the Royal Statistical Society, Series B* 13 (2), 238–241.

Snowberg, E., Wolfers, J., 2010. Explaining the favorite–long shot bias: is it
risk-love or misperceptions? *Journal of Political Economy* 118 (4), 723–746.

Sun, L., Abraham, S., 2021. Estimating dynamic treatment effects in event
studies with heterogeneous treatment effects. *Journal of Econometrics* 225 (2),
175–199.

Thaler, R.H., Ziemba, W.T., 1988. Anomalies: parimutuel betting markets:
racetracks and lotteries. *Journal of Economic Perspectives* 2 (2), 161–174.

Whelan, K., 2023. *How Do Prediction Market Fees Affect Prices and
Participants?* CEPR Discussion Paper 17972; MPRA Paper 116926, University
Library of Munich.

Wolfers, J., Zitzewitz, E., 2004. Prediction markets. *Journal of Economic
Perspectives* 18 (2), 107–126.

*All entries were checked against their sources on 2026-08-27.*

---

## Appendix A. Extended abstract (preprint posting)

*The abstract above is trimmed for journal length. This longer version is the
one posted with the preprint, where no cap applies; the two make identical
claims and carry identical status labels.*

Prediction markets are now studied intensively enough that their own growth has
become a measurement problem. We show this concretely on Kalshi, using 376.8
million fills through June 2026.

Between the 2024 calendar year and the post-May-2025 window, sports contracts
went from **0.009% of the in-scope sample to 58.8%** — a category that barely
existed becoming the majority of observations in fourteen months. Decomposing
the aggregate change in the Mincer–Zarnowitz slope at that boundary,
**41% of it is composition rather than any change in how the market prices
risk.** A before/after comparison of aggregate bias across early 2025 — the
natural design, and one already being applied to this venue — largely measures
the arrival of an asset class.

Having established that, we ask the persistence question properly. Two events
make Kalshi a candidate natural experiment: a maker fee in 2025 and the public
documentation of its pricing biases in September 2025. We reconstruct the fee
schedule from sixteen dated captures of Kalshi's own published document and find
it is **not the exchange-wide regime change the literature assumes**: a
per-series surcharge covering 8.0% to 14.4% of in-scope markets, revised five
times, flat per contract before it was quadratic in price. That rules out a step
dummy and calls for a difference-in-differences between treated and untreated
series trading in the same months.

**The pre-specified estimate is a tight null: −0.0016 (0.0064)** on 98 treated
series and 119,646 event clusters. An event study around each series' own
adoption date, added after that result was known and reported as such, finds
pre-treatment coefficients jointly indistinguishable from zero (χ²(5) = 3.24,
p = 0.66) — supporting parallel trends in a setting where treatment was visibly
selected on market-making activity — and post-treatment coefficients jointly
different from zero (χ²(10) = 21.01, p = 0.021). Read as **exploratory**, that
indicates a transitory reduction in the bias three to four months after a series
is charged, decaying back within the year; the static average would conceal such
a shape by construction. The maker's return advantage at prices at or above 50c
survives every fee layer and every plausible fee rate.

We publish the fee history, the category mapping and the full pipeline.

---
