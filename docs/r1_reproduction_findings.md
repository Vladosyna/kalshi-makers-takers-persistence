# R1 reproduction: findings, construction pins, and open divergences

**Status 2026-07-27.** R1 now reproduces every headline quantity BDW report: the
Fig 3 favorite-longshot curve, all four Fig 5 return markers, Fig 6 and Table
10's maker/taker split including the full maker-share curve, Table 9's by-year
psi in sign and significance, and Table 8's category heterogeneity.

Working record of what reproduces, what does not, and every construction
decision taken to get there — written to be quotable in
the note's divergence-log section rather than as internal notes. Every number
here is reproducible from the committed pipeline (`kmt build`, `kmt r1`,
`tools/measure_backfill_hypothesis.py`).

Sample: our own independently collected R1 universe (2021-01-01 → 2025-04-30),
160,768 discovered in-window markets, 32,728 passing construction, 121,803 Yes
price observations, 9.46M fills in Pass 2's tape.

---

## 1. What reproduces

### Favorite–longshot bias (BDW Fig 3)

| Band | Mean price | Win rate | |
|---|---|---|---|
| 1–10c | 0.032 | 0.020 | below price |
| 11–20c | 0.151 | 0.105 | below |
| 21–30c | 0.251 | 0.195 | below |
| 31–40c | 0.351 | 0.307 | below |
| 41–50c | 0.456 | 0.431 | below |
| 51–60c | 0.557 | 0.587 | **above** |
| 61–70c | 0.658 | 0.702 | above |
| 71–80c | 0.760 | 0.817 | above |
| 81–90c | 0.861 | 0.905 | above |
| 91–99c | 0.971 | 0.982 | above |

Low-priced contracts win less than price implies, high-priced ones more, with
the crossover at 50c. This is the paper's central descriptive claim and it
reproduces cleanly on independently collected data.

### Returns by band (BDW Fig 5)

| Band | n | Gross | Net of taker fee |
|---|---|---|---|
| 1–10c | 55,704 | −0.472 | **−0.605** |
| 11–20c | 13,662 | −0.271 | −0.341 |
| 21–30c | 8,082 | −0.193 | −0.229 |
| 31–40c | 5,818 | −0.083 | −0.139 |
| 41–50c | 4,122 | −0.028 | −0.062 |
| 51–60c | 3,209 | +0.097 | +0.047 |
| 61–70c | 3,284 | +0.101 | +0.060 |
| 71–80c | 3,558 | +0.098 | +0.072 |
| 81–90c | 5,303 | +0.071 | +0.056 |
| 91–99c | 19,061 | +0.016 | +0.013 |
| **all** | 121,803 | **−0.250** | |

All four of BDW's stated markers hold: ≤10c lose more than 60% (net −60.5%),
small positive returns above 50c, still positive net above 70c, and an average
pre-fee return near their ≈ −20% (ours −25%).

### ψ by year (BDW Table 9)

Mincer–Zarnowitz `(Y−P) = α + ψP + ε`, cents, Yes-only, event-clustered SEs.

| Year | Our ψ | SE | BDW ψ | Verdict |
|---|---|---|---|---|
| 2021 | 0.0619 | 0.0142 | 0.041 | confirmed |
| 2022 | 0.0669 | 0.0082 | 0.023 | partially confirmed |
| 2023 | 0.0652 | 0.0105 | 0.036 | partially confirmed |
| 2024 | 0.0652 | 0.0072 | 0.048 | partially confirmed |
| 2025 (Jan–Apr) | 0.0337 | 0.0124 | 0.021 | confirmed |

Sign and significance reproduce in every year; magnitudes run higher. Note that
BDW's own reading — "some evidence the bias is diminishing" — rests on an
informal comparison across these years, which is exactly what R2 replaces with
a formal interaction test.

### ψ by category (BDW Table 8)

| Category | ψ | SE | n |
|---|---|---|---|
| Economics | 0.1296 | 0.0082 | 21,038 |
| Sports | 0.0767 | 0.0168 | 5,333 |
| Health | 0.0657 | 0.0166 | 2,150 |
| Financials | 0.0369 | 0.0099 | 20,164 |
| Climate and Weather | 0.0339 | 0.0041 | 29,121 |
| Mentions | 0.0330 | 0.0225 | 2,308 |
| **Politics** | **0.0309** | **0.0349** | 15,770 |
| **Entertainment** | **0.0254** | 0.0128 | 20,997 |

BDW's own heterogeneity claim is independently confirmed: politics is
insignificant (ψ = 0.031, SE = 0.035) and entertainment is weakest. This is
load-bearing for R2 — the whole category-interacted design exists because ψ is
category-heterogeneous, so confirming it on our own data is a prerequisite, not
a footnote.

### 1.5 Maker/taker split (BDW Fig 6 and Table 10)

Post-fee returns over the doubled price panel, roles attributed by which side
the taker took in the trade that set each observation's price.

| | Ours | BDW |
|---|---|---|
| Maker return | **−8.41%** | −9.64% |
| Taker return | **−34.30%** | −31.46% |
| Maker margin, ≥50c | **+3.32%** | +2.6% |

Maker share by band — BDW's Table 10 curve, reproduced across its whole length:

| Band | Ours | BDW |
|---|---|---|
| 1–10c | 43.0% | 43.5% |
| 11–20c | 46.5% | 46.7% |
| 21–30c | 47.3% | 48.9% |
| 31–40c | 46.6% | 47.8% |
| 41–50c | 48.0% | 49.5% |
| 51–60c | 51.4% | 50.4% |
| 61–70c | 54.6% | 52.2% |
| 71–80c | 52.6% | 51.1% |
| 81–90c | 53.3% | 53.3% |
| 91–99c | 57.1% | 56.5% |

This is the paper's headline result — makers outperform takers, and the ≥50c
maker margin is the exploitable edge whose survival R2 tests. Both endpoints of
the share curve land within 0.6 points, and the monotone tilt (takers hold the
cheap contracts that perform worst) reproduces throughout. The ≥50c margin
matters procedurally too: spec S5's escalation rule keys off its sign, so it is
now reported by the pipeline rather than recomputed ad hoc.

Note the observation counts differ by role (121,803 maker vs 103,144 taker) even
though the doubled panel splits 50/50 overall: taker observations whose fee is
not computable — a market closing before `data/fees.yaml`'s earliest entry — are
excluded from the taker average and counted, rather than silently charged zero.
Makers were fee-exempt in this window, so no maker observation is lost that way.

---

## 2. Construction pins decided by measurement

BDW's prose underdetermines their construction in at least three places. In each
case the deciding evidence is their own reported integers, not a judgement about
what they meant. This is legitimate only because of the spec's sequential gate:
counts are the **sample definition** (calibration), ψ is the **result** (the
independent test). Tuning ψ to match would be circular; tuning the sample
definition to match is not.

### 2.1 Volume filter: contracts, not dollars

BDW write "total traded volume at closure ≥ $1,000", which reads as dollar
notional. But Kalshi's `volume` field is denominated in **contracts** and the API
exposes no notional field; since a contract settles at $1, the units are nearly
indistinguishable in prose.

Measured at the volume-filter stage, before the 24h and spread filters:

| | Ours | BDW | Δ |
|---|---|---|---|
| contracts | 44,946 | 46,282 | −2.9% |
| events | 12,416 | 12,403 | **+0.1%** |

A 0.1% event match on independently collected data settles it. **Contract
reading is primary**; the dollar reading is retained as a reported sensitivity
branch (under it the sample roughly halves: 25,803 → 13,632 contracts).

Worth stating in the paper on its own merits: a sample rule in a
favorite-longshot-bias paper that differentially removes cheap strikes is itself
a result. The dollar reading removes longshots preferentially, because notional
= price × count falls with price.

### 2.2 No-trade lookback days: backfill, not skip

BDW: "last trade on closing day plus last trade before the same time on each of
up to 10 prior days." The natural reading is *skip* a day with no trade — which
is what this repo originally pinned. Their own n says otherwise:
156,986 / 46,282 = **3.39 prices per contract**.

| Rule | Prices | Per contract |
|---|---|---|
| skip | 64,614 | 2.50 |
| **backfill** | 121,803 | **3.72** |
| BDW | 156,986 | 3.39 |

Skip cannot reach 3.39. The two rules now **bracket** their value rather than
sitting below it.

The same rule also silently dropped whole contracts, not just rows: under skip,
6,925 of 32,728 in-scope contracts (**21.2%**) had no trade inside their closing
ET calendar day and so contributed nothing at all — the fetch is all-or-nothing
at day 0. Exactly 0 contracts had rows without a day-0 row, confirming the
mechanism.

Implementation note: the backfilled panel is built from Pass 2's tape via a
DuckDB ASOF JOIN — literally "last trade at or before this instant". Carrying
forward from the stored `price_panel` rows instead would inherit Pass 1's
same-ET-day restriction and so be an approximation.

### 2.3 Entry price: every observation, not just the closing day

BDW's stated ≈ −20% average pre-fee return decides this one:

| Entry construction | Mean gross return |
|---|---|
| every panel observation | **−0.250** |
| closing day only | −0.701 |

Restricting to the closing day is not a small variation: a contract still priced
at 1–10c on its final day has almost no chance left, so that band alone reaches
−97% and drags the whole figure to −70%. Using every observation also makes Fig 5
and the MZ regression describe the same sample — BDW's n = 156,986 is the full
price panel, not one row per contract.

---

## 3. Bugs the reproduction exposed

Both sat in the tails the headline depends on, and neither was visible until real
numbers were compared against BDW's.

**Fee charged as if every order were one contract.** The fee model rounds the
*order total* up to the next cent, so assuming a 1-contract order overstates the
effective rate by up to **14.4×** at a 1c price ($0.000693 true vs $0.01
charged). This drove the 1–10c band's net return to **−181%**, below the
−(1 + fee rate) = −1.07 floor the return convention allows. The spec had warned
explicitly ("compute fees on actual per-order contract counts"); the fix carries
the tape's real order size through the panel. Rows without a size are excluded
from the net figure and counted, never silently charged.

*Convention note, since it looks like an error and is not:* the pinned
convention `r = (payout − P − f) / P` divides by the **stake**, not by total
outlay, so a total loss gives −1 − f/P, slightly below −100%. With a
proportional fee, f/P = rate·(1−P) ≤ rate, so the floor is −(1 + rate).

**Returns measured only at the closing-day price** — see 2.3. This is recorded
here as well as there because it was a coding decision that happened to encode a
construction choice, and the two are worth separating in the paper.

---

## 4. Open divergences

### 4.1 Structural: 8.2% of markets have no bid/ask history

Of the 39,794 markets clearing volume + 24h, **3,257 (8.2%)** have a quote row
whose spread is NULL — Kalshi serves no bid/ask history for them (Step Zero
Check 5's PARTIAL finding). This cannot shrink by fetching more. Only **11
markets (0.0%)** are merely not-yet-fetched, so the shortfall is emphatically
not an artifact of incomplete collection. BDW did not lose these. **Disclose, do
not engineer around.**

### 4.2 Residual count gap

After both re-pins: events −19.8%, contracts −29.3%, prices −22.4% (from
−47.9% / −70.5% / −74.6% before either). Our funnel loses 5,152 markets to the
24h filter and 6,555 to the spread filter (3,298 genuinely wide, 3,257
structurally uncomputable) off 44,946 at the volume stage. For BDW to report
46,282 *after* those same filters, their spread and duration filters must have
bitten far less than ours — which for the spread half is exactly 4.1.

### 4.3 Maker/taker — RESOLVED 2026-07-27, see §1.5

Was the largest open divergence; resolved by reading the primary PDF rather than
by further inference. Kept below for the record of what was ruled out, because
the elimination sequence is itself worth reporting: it shows the failure was a
unit-of-observation error, not a data limitation.

**Root cause.** We averaged over all ~9.9M *fills*; BDW average over the
*price panel* (up to 11 observations per contract). Two things in the paper pin
this beyond doubt: Table 10 totals 313,972 observations with Makers exactly
156,986 — the doubled panel, one role per side of every observation — and the
text states "Because we include the same contract at different points during its
lifetime, we want to make sure that our results are not driven by the small
minority of contracts that are in the sample up to 11 times", which only parses
on a panel basis. The fill population is dominated by heavily-traded mid-price
markets; the panel weights each contract's lifetime equally.

A second component: Figure 6 reports **post-fee** returns, and in BDW's window
makers were fee-exempt while takers paid the 0.07·P·(1−P) order-total formula.
Part of the headline gap is the fee, not behaviour — so the fee asymmetry has to
be in the code, and now is.

### 4.3b What had been ruled out first (retained for the record)

| | Maker | Taker |
|---|---|---|
| BDW | −9.64% | −31.46% |
| ours, unweighted per fill | −0.39% | −5.07% |
| ours, contract-weighted | −7.13% | −9.51% |
| ours, capital-weighted | +0.10% | −0.10% |

Sign and direction of the asymmetry reproduce; magnitude does not, and the
maker-share curve is flat (~50% in every band) where BDW report a 13-point tilt
(43.5% at 1–10c → 56.5% at 90–99c).

What is **ruled out**:

- *Missing data.* `taker_outcome_side`, `taker_book_side` and `taker_side` are
  100% populated in every era (2021-2022 through 2025-Jan-Apr). Note they carry
  one single bit between them — `taker_book_side` = 'bid' exactly when
  `taker_outcome_side` = 'yes' — so there is no additional maker/taker
  information in the tape beyond which outcome side the taker was on.
- *A coding error in the share.* The flat ~50% is a correct consequence of the
  doubled-by-complementary-price construction plus the observed taker-side /
  price distribution; recomputing by hand from the marginal frequencies gives
  0.5008 against the pipeline's 0.502.
- *Tape inconsistency.* The market is zero-sum in dollars, and capital-weighted
  returns confirm it: +0.10% maker against −0.10% taker.

That last point constrains what BDW's numbers can be. Two returns that are
**both** substantially negative cannot be a paired, dollar-weighted measure of
the same fills — those must offset. So their pair has to be an unweighted (or
otherwise non-capital) average over a population in which makers and takers hold
different price mixes. Our unweighted average is on that basis but is 4.6× less
asymmetric.

Next step is a source check rather than more guessing: read the exact averaging
basis and population off the primary PDF (which fills, which side attribution,
weighted how) before changing anything. This is the paper's headline quantity,
so it is the one place where inferring the construction from their integers —
the method used in section 2 — would be circular, because the integers *are* the
result under test.
