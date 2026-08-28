# A Replication of Bürgi, Deng and Whelan, *Makers and Takers: The Economics of the Kalshi Prediction Market*

**Vladyslav Yurchyna**
Independent Researcher
vlad.yurchina@outlook.com


**Draft — 2026-08-27.** Target: a replication outlet (e.g. *Journal of Comments
and Replications in Economics*), **held until the original is published** — JCRE
requires the replicated study to have appeared. As of this draft the original
circulates as a working paper (January 2026 version; CEPR DP 20631, CESifo WP
12122, UCD WP2025_19, GWU 2026-001, MPRA 126350).

Companion: `paper_a_composition.md`, which covers the post-2025 window, the
sourced fee schedule and the persistence estimate. This paper covers the
original's own window and does not repeat that material.

---

## Abstract

We attempt an independent replication of Bürgi, Deng and Whelan (BDW), who
document a favorite–longshot bias and a maker/taker return asymmetry on the
Kalshi prediction market over 2021 to April 2025. We do not use their data. We
re-collect the sample from Kalshi's public API, rebuild the panel from the
paper's own description, and compare.

**The headline results replicate.** All five by-year Mincer–Zarnowitz slopes are
recovered with matching sign and significance pattern. The maker return at
prices at or above 50c — the paper's exploitable margin — comes back at +2.09%
against their +2.6%. The maker share of the two extreme price bands, on the
basis the original states it, is 43.1% and 57.0% against their 43.5% and 56.5%.
The win-rate curve reproduces directly.

**Our sample is smaller and we can say why.** We recover 33,222 contracts
against their 46,282. The gap is dominated by the closing-spread filter: 3,257
markets clearing the volume and duration screens have no bid–ask history that
Kalshi will serve at all, which is structural rather than a collection
shortfall.

**Two construction ambiguities in the paper's prose are resolved against its own
arithmetic**, and both change the sample materially: the volume screen is
denominated in contracts rather than dollars, and prices are carried forward on
lookback days with no trade. We report both branches.

**One filter does not reproduce.** The original drops 63 contracts for
mismatching separately reported final prices. No reading available from Kalshi's
public fields recovers that rate. We say so, retain the contracts, and log the
divergence — and note that the discarded comparison turns out to be a strong
validation in its own right: 95.7% of our tape-derived closing prices match
Kalshi's independently reported final price to the cent.

---

## 1. What is being replicated and why it is worth replicating

BDW provide the first systematic evidence on pricing in Kalshi, the first
federally licensed prediction market in the United States. Their central results
are a favorite–longshot bias — cheap contracts winning less often than their
prices imply, expensive ones more often, a regularity surveyed by Ottaviani and
Sørensen (2008) and documented in parimutuel betting by Thaler and Ziemba
(1988) — and an asymmetry between the traders
who post offers (Makers) and those who accept them (Takers), with Takers losing
roughly 32% on average against Makers' roughly 10%, and Makers earning a small
positive return on contracts priced at or above 50c.

Three features make an independent replication worth the effort.

The result is **consequential**: the maker margin at ≥50c is an exploitable edge
in a regulated, publicly accessible venue, and its existence has implications
for how these markets are used and regulated.

The data are **public but not trivially so**. The original uses transaction-level
data obtained through Kalshi's API. Re-collecting rather than re-using their
extract tests the whole chain — sampling, filtering, panel construction — rather
than only the regression code. This is a *conceptual* replication in the sense
that matters: everything upstream of the estimator is rebuilt from the paper's
description.

The construction is **under-determined by the prose**. Two decisions that the
paper describes in words admit readings that differ by tens of percent in sample
size. That is precisely the kind of thing replication exists to surface.

**What kind of replication this is.** Clemens (2017) argues that "replication"
is used loosely enough in economics to obscure what a discrepant result means,
and separates tests that use the original's population and specification from
tests that vary either. This exercise keeps both: the population is the
original's window on the original's venue, the specification is the original's
equation, and only the sample is drawn again. A discrepancy here is therefore
evidence about collection, construction or coverage — not about whether the
original's method was the right one. Hamermesh (2007) makes the related point
that this kind of test is undersupplied relative to its value, which is part of
why we report the gaps in §4 and §6 rather than closing them by adjusting a
filter until the counts agree.

## 2. Independent collection

Data come from Kalshi's public `trade-api/v2` endpoints, with no account and no
authentication. Collection uses two passes: a universe-wide pass for market
metadata, the boundary trades the daily-lookback panel requires, and closing
quotes for the spread screen; then a full trade-tape pass restricted to
contracts that survive the filters, because the maker/taker quantities require
every fill's price, size and taker side, and boundary ticks cannot substitute.

The full tape is 376,760,957 fills across 62 monthly partitions; the portion
relevant here is the original's window, 2021 through April 2025.

We apply the paper's stated screens: total traded volume at closure at or above
$1,000, a final bid–ask spread at or under 20c, and at least 24 hours open (which
excludes the hourly-reset crypto and index series). The panel is the last trade
on the closing day plus the last trade before the same time on each of up to ten
prior days, in US Eastern Time.

## 3. Two construction decisions, resolved against the paper's own arithmetic

### 3.1 Volume: contracts, not dollars

BDW write: "We focus only on contracts that have reached a total trading volume upon market closure of at least $1,000 to ensure there was a meaningful level of market activity."
That reads as dollar notional. Kalshi's `volume` field is denominated in **contracts**, and the API
exposes no notional field. Because a contract settles at $1, the two are easy to
conflate in prose and are not remotely equivalent in data.

The paper's own counts adjudicate. At the contract reading, and before the
duration and spread screens, our independently collected universe gives 12,416
events against their 12,403 (+0.1%) and 44,946 contracts against their 46,282
(−2.9%). A 0.1% event match on separately collected data is not coincidence.

We therefore take the contract reading as primary and report the dollar reading
as a branch. It is not discarded, because it is the literal text and because
under it the sample roughly halves — and a screen that differentially removes
cheap strikes is itself a finding in a paper about the favorite–longshot bias.

### 3.2 No-trade lookback days: carry forward, not skip

The paper describes this construction twice, and neither description settles it.
The introduction collects "the final traded price as the market closed and also, where available, previous prices from 24-hour intervals up to 10 days before markets closed"; Section 3.1 has "Going from final trades on the day a market closed back in 24-hour intervals to ten days before closing". The phrase
"where available" reads naturally as skipping days with no trade, and the second
description is silent on gaps altogether. The paper's counts say otherwise: 156,986 prices
over 46,282 contracts is 3.39 prices per contract, which skipping cannot reach.

Measured on our tape, with no refetching, skipping gives 2.50 prices per
contract and carrying the last price forward gives 3.50 — a 3.2% match against
3.39 versus 26% low. The same rule also decides whole contracts, not merely
rows: under skipping, 6,925 of 32,728 in-scope contracts (21.2%) contribute no
panel row at all, because the panel builder is all-or-nothing when the closing
day has no trade.

We take carrying forward as primary and report skipping as a branch.

We flag the reasoning explicitly, because pinning a construction to an
original's integers can look circular. It is not, provided the direction is
respected: counts are the **sample definition** and may legitimately be
calibrated to the original, since a slope is only comparable on a comparable
sample; the slope itself is the **result** and is never tuned. We calibrate the
former and report the latter as it falls.

## 4. The count-reconciliation gate

Estimates are compared only after counts are. Divergence between two collections
of the same deterministic public data is a coverage question rather than a
sampling question, so the original's standard errors are not used as a tolerance.

| Quantity | Ours | BDW | Δ |
|---|---|---|---|
| Events | 10,061 | 12,403 | −18.9% |
| Yes contracts | 33,222 | 46,282 | −28.2% |
| Yes prices | 124,732 | 156,986 | −20.6% |
| Doubled prices | 249,464 | 313,972 | −20.6% |

The doubled panel is exactly twice the Yes-only panel, as it must be.

**Where the shortfall comes from.** Of 39,794 markets clearing the volume and
duration screens, 3,257 (8.2%) carry a quote row whose spread is null: Kalshi
serves no bid–ask history for them, so no amount of additional collection
recovers them. Only 11 markets (0.03%) are merely unfetched. A further 3,451 are
genuinely wide and correctly excluded.

For the original to report 46,282 contracts *after* the same screens, its spread
filter must have bitten far less than ours. We cannot determine why from public
information. The most likely explanation is an asymmetry in bid–ask history
availability between their extract and what the API now serves, which would be a
data-vintage effect rather than a methodological difference. We report the gap
rather than adjusting a filter until it closes.

## 5. Results

### 5.1 By-year slopes (their Table 9)

The Mincer–Zarnowitz regression (Mincer and Zarnowitz 1969) `(Y−P) = α + ψP + ε`
in cents, Yes-only, with event-clustered standard errors:

| Year | Ours | s.e. | BDW | Verdict |
|---|---|---|---|---|
| 2021 | 0.0409 | 0.0159 | 0.041 | confirmed |
| 2022 | 0.0202 | 0.0122 | 0.023 | confirmed |
| 2023 | 0.0217 | 0.0144 | 0.036 | confirmed |
| 2024 | 0.0386 | 0.0083 | 0.048 | confirmed |
| 2025 (Jan–Apr) | 0.0171 | 0.0126 | 0.021 | confirmed |

Every year is positive with the significance pattern the original reports.
Magnitudes run systematically a little below theirs, all within roughly one
standard error; 2021 matches to three decimals. The verdict vocabulary was fixed
in advance: *confirmed* requires counts to reconcile within documented coverage
gaps and the sign and significance pattern to reproduce, and does not require
magnitudes to coincide.

The original's own reading — that "there is some evidence that the bias in prices is diminishing over time" — is a comparison across
windows rather than a formal test. Our
companion paper replaces it with an interaction test on a pooled panel.

### 5.2 The bias itself (their Figure 3)

| Band | Win rate | Mean price |
|---|---|---|
| 1–10c | **2.43%** | 3.22c |
| 91–99c | **97.86%** | 97.08c |

Cheap contracts win less often than their price implies; expensive ones more
often. This is the paper's central figure and it reproduces directly.

Returns by band reproduce the pattern as well: −37.3% gross in the bottom band
and −49.2% net under the original's own fee model, turning slightly positive
above 50c.

### 5.3 Makers and takers (their Figure 6 and Table 10)

| Quantity | Ours | BDW |
|---|---|---|
| Maker return | −1.33% | −9.64% |
| Taker return | −28.40% | −31.46% |
| **Maker return, price ≥50c** | **+2.09%** | **+2.6%** |
| Maker share, 1–10c band | 43.1% | 43.5% |
| Maker share, 90–99c band | 57.0% | 56.5% |

The exploitable margin — the number the paper's contribution rests on —
replicates closely. So do the maker shares, which are stated on the doubled
basis in the original and computed on the same basis here.

The overall maker return is our one material divergence: −1.33% against −9.64%.
The taker side is close, so the gap is specific to the maker leg. Given that the
≥50c maker figure and both maker shares match, we suspect a difference in how
the maker leg is averaged across price bands rather than a difference in the
underlying data, but we cannot resolve it from public information. It is logged
as a divergence rather than explained away. **Per replication-outlet practice,
this is the point on which the original authors would be contacted before
submission.**

## 6. A filter that does not reproduce

BDW drop 63 of 46,282 Yes contracts — 0.136% — for mismatching Kalshi's
separately reported final prices. The paper does not name the field, so we
measured every reading available from Kalshi's public data against that rate:

| Reading | Rate | vs 0.136% |
|---|---|---|
| Last-trade proxy | 0.000% | fires never |
| Tape price vs `last_price`, ≥1c | 4.345% | 32× too many |
| Settlement value vs `result` | 0.003% | 45× too few |

The price comparison is the closest in spirit and the furthest in magnitude, and
the two quantities it compares differ *by definition* — a tape-derived closing
price and an exchange-reported final price are not the same object — so a
disagreement between them is not evidence of an error. Tuning its threshold
until it produced 63 contracts would fit a filter whose definition we do not
know to a number we do.

We therefore implement the one unambiguous data error instead — Kalshi's own
settlement value contradicting its own `result`, which fires on 1 contract in
32,728 — retain the contracts BDW dropped, and record the divergence. At 0.136%
of their sample, the difference cannot move any reported quantity.

The failed comparison produced something useful. Run as a validation rather than
a filter, **95.7% of our tape-derived closing prices match Kalshi's
independently reported final price to the cent**, with median, 90th and 95th
percentile differences all exactly zero. That is strong independent evidence
that the tape reconstruction is correct — obtained precisely by failing to
reproduce a filter.

## 7. Two methodological points confirmed

**Clustering.** The specification calls for Cameron, Gelbach and Miller (2011) two-way
(event, contract) cluster-robust variance, and argues that with contracts nested
in events it reduces algebraically to one-way event clustering, since the
intersection term equals the contract term. Estimated both ways on the real
panel, the standard errors agree to fourteen decimal places (ψ s.e.
0.006003661900808133 versus …132). One-way event clustering is used throughout
without hedging.

**Taker-side field availability.** The maker/taker split depends on Kalshi
populating a taker-side field consistently across eras, which a pre-collection
probe can only sample thinly. Recomputed over every fill collected —
376,760,957 of them — the population rate is **100.0%** for
`taker_outcome_side`, `taker_book_side` and the legacy `taker_side`, in all five
eras, with zero unparseable timestamps. The maker/taker decomposition rests on a
field that is always present.

## 8. Conclusion

BDW's central findings replicate on independently collected data. The
favorite–longshot bias reproduces in shape and magnitude; all five by-year
slopes reproduce in sign and significance; the maker margin at prices at or
above 50c, which is the paper's most consequential number, reproduces at +2.09%
against +2.6%; and the maker shares at both tails reproduce to within half a
percentage point.

Three things do not reproduce, and all three are informative rather than
damaging. Our sample is 28% smaller, for a reason we can name and quantify.
The overall maker return differs materially while its components do not. And the
63-contract mismatch filter cannot be reconstructed from public fields at all,
which we report as an unresolved ambiguity in the original's description rather
than papering over with a tuned threshold.

Two of the paper's construction descriptions are ambiguous in ways that change
the sample by tens of percent, and in both cases the paper's own reported counts
resolve them. We suggest that future work of this kind state the volume
denomination and the no-trade lookback rule explicitly; both are one sentence,
and both are load-bearing.

---

---

### Declaration of interest

The author declares no competing financial interest. The author does not trade
on Kalshi, holds no positions on the venue studied, has no financial or personal
relationship with the exchange or with the authors of the work replicated, and
received no funding for this research.

### Data and code availability

The full pipeline, the collected universe's derived artifacts, the analysis
plan with dated amendments, and a machine-readable reconstruction of Kalshi's
fee schedule from sixteen archived primary captures are public and
MIT-licensed. The repository contains no execution code: every endpoint used is
public and unauthenticated.

## Declaration of Generative AI and AI-assisted technologies in the writing process

During the preparation of this work the author used Claude (Anthropic) in order
to draft and revise manuscript prose and to generate the data-collection and
analysis code in the accompanying repository. After using this tool the author
reviewed and edited the content as needed and takes full responsibility for the
content of the publication.

---

## References

Bürgi, C., Deng, W., Whelan, K., 2026. *Makers and Takers: The Economics of the
Kalshi Prediction Market.* Working paper, January 2026 version. CEPR Discussion
Paper 20631; CESifo Working Paper 12122; UCD Working Paper WP2025_19; GWU
Working Paper 2026-001; MPRA Paper 126350. (The GWU series cover sheet, dated
February 2026, reads "Makers *or* Takers"; the paper's own title page inside
that document reads "Makers *and* Takers" and its 44 pages are identical to the
January version. We cite the authors' title.)

Cameron, A.C., Gelbach, J.B., Miller, D.L., 2011. Robust inference with
multiway clustering. *Journal of Business & Economic Statistics* 29 (2),
238–249.

Clemens, M.A., 2017. The meaning of failed replications: a review and proposal.
*Journal of Economic Surveys* 31 (1), 326–342.

Hamermesh, D.S., 2007. Viewpoint: Replication in economics. *Canadian Journal
of Economics* 40 (3), 715–733.

Mincer, J., Zarnowitz, V., 1969. The evaluation of economic forecasts. In:
Mincer, J. (Ed.), *Economic Forecasts and Expectations: Analysis of Forecasting
Behavior and Performance.* National Bureau of Economic Research, New York,
pp. 3–46.

Ottaviani, M., Sørensen, P.N., 2008. The favorite-longshot bias: an overview of
the main explanations. In: Hausch, D.B., Ziemba, W.T. (Eds.), *Handbook of
Sports and Lottery Markets.* Elsevier, Amsterdam, pp. 83–101.

Thaler, R.H., Ziemba, W.T., 1988. Anomalies: parimutuel betting markets:
racetracks and lotteries. *Journal of Economic Perspectives* 2 (2), 161–174.

*All entries were checked against their sources on 2026-08-27.*
