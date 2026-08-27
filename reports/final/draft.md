# Kalshi Makers & Takers -- Replication Note (Draft)
*(candidate venues: IJF replication section, IREE)*

Draft assembled: 2026-08-27T01:19:54+00:00
R2 verdict locked: 2026-08-25T19:01:00+00:00

## 1. Introduction

> "We think it will be interesting to see if the biases and return patterns that we have reported persist now that they have been publicly documented."
>
> -- Burgi, Deng & Whelan, Section 6

This work takes up that invitation: does the favorite-longshot bias and the maker/taker return asymmetry BDW document persist after their maker-fee change (2025-05-01) and public posting (2025-09-08)?

## 2. R1 reproduction

Reproduced full-sample psi_bar_R1 = 0.0254.
Full by-year/by-category divergence log: D:\Papers\Kalshi replication lab\reports\r1\divergence_log.md

## 3. R2 findings

### 3.1 Primary composition-weighted test (S2.1-S2.2)
- **delta_bar_fee**: 0.0399 cents/cents, 95% CI [0.0071, 0.0726] -- verdict: **indeterminate**
- **delta_bar_pub**: -0.0311 cents/cents, 95% CI [-0.0637, 0.0014] -- verdict: **indeterminate**

### 3.2 Composition decomposition (S2.3)
- **fee boundary**: within = 0.0399, between = 0.0278, aggregate = 0.0677 (within is the persistence narrative's own object; between is reported alongside, never folded into that claim -- docs/analysis_plan.md S2.3).
- **publication boundary**: within = -0.0311, between = 0.0278, aggregate = -0.0033 (within is the persistence narrative's own object; between is reported alongside, never folded into that claim -- docs/analysis_plan.md S2.3).

Categories fit: Climate and Weather, Commodities, Companies, Crypto, Economics, Elections, Entertainment, Exotics, Financials, Health, Mentions, Politics, Science and Technology, Social, Sports, Transportation, World
Panel sizes: R1=124732, R2=1205713, pooled=1330445

### 3.3 Horizon robustness (S2.6)

| lookback_day | n | delta_bar_fee | delta_bar_pub | categories fit |
|---|---|---|---|---|
| 0 | 424646 | 0.0117 | -0.0153 | 17 |
| 1 | 277892 | 0.0978 | -0.0264 | 17 |
| 2 | 149290 | 0.0056 | 0.0128 | 17 |
| 3 | 108011 | 0.0153 | 0.0158 | 17 |
| 4 | 85482 | 0.0125 | 0.0170 | 17 |
| 5 | 71644 | 0.0534 | -0.0316 | 17 |
| 6 | 57839 | 0.0379 | -0.0179 | 17 |
| 7 | 44194 | 0.0018 | -0.0187 | 17 |
| 8 | 39315 | 0.0115 | -0.0119 | 17 |
| 9 | 36968 | -0.0077 | -0.0057 | 17 |
| 10 | 35164 | 0.0226 | -0.0147 | 17 |

One-observation-per-contract spec (S2.6 item 2): n=424646, delta_bar_fee=0.0117, delta_bar_pub=-0.0153.

## 4. Fee layers and the maker >=50c margin (S3.2-S3.3)

| layer | margin (maker - taker, >=50c) | n_maker | n_taker |
|---|---|---|---|
| (a) gross | 0.0240 | 202725609 | 167925545 |
| (b) net of own-era fees | 0.0439 | 202725609 | 167925545 |
| (c) fee-held-constant counterfactual | 0.0454 | 202725609 | 167925545 |

Fee-sensitivity ribbon (S3.3), swept over the maker rate: break-even rate = never crosses zero in-grid, sign_flips = False, **fragile = False** (a fragile result cannot trigger escalation on its own, per the pre-registered rule).

## 5. Control venue: Polymarket (S2.4)

| month | psi | n | n_clusters |
|---|---|---|---|
| 2025-05 | -0.0223 | 4719 | 4719 |
| 2025-06 | 0.0003 | 7114 | 7114 |
| 2025-07 | 0.0006 | 8009 | 8009 |
| 2025-08 | 0.0018 | 9241 | 9241 |
| 2025-09 | 0.0136 | 22791 | 22791 |
| 2025-10 | -0.0021 | 25298 | 25298 |
| 2025-11 | -0.0063 | 39905 | 39905 |
| 2025-12 | -0.0051 | 46020 | 46020 |

**Mandatory caveats (carried verbatim, docs/analysis_plan.md S2.4):**
1. Polymarket's tail bias is REVERSED relative to Kalshi's (Qin & Yang 2026) -- this control informs market-wide secular efficiency drift, not level or sign; 'parallel trends' language must not be used.
2. Archive provenance: a different repository, a different use (the market's own calibration path, not a model-skill claim) -- the sibling forecast lab's own archive-usage guardrail does not apply here.
3. Spillover: BDW's publication could in principle move Polymarket too via cross-venue arbitrageurs. If the control shows a comparable delta at the same dates, that strengthens the secular-trend explanation -- it is not a defect in this design.

**Coverage gap:** The control overlay covers only 2025-05 through 2025-12 (the SII-WANGZJ archive's own end date). R2's final ~6 months (2026-01 through 2026-06) have NO control venue: extending the archive is not merely unavailable -- Polymarket's own 2026 fee reform begins January 2026, so even a hypothetically longer archive would contaminate the control with Polymarket's own treatment inside that window. The Kalshi-vs-Polymarket differential is reported only over the covered sub-window; the later period is uncontrolled, not silently extrapolated.

## 6. Escalation determination (S5)

**Escalate: False**

No trigger condition fired.

**Fee arm** -- Addendum 3: the trigger reads off delta_did and needs
rejection at 5% in BOTH fits.

- twfe: delta_did=0.0113 95% CI [-0.0139, 0.0365] -- rejects zero: False
- clean_controls: delta_did=-0.0016 95% CI [-0.0141, 0.0109] -- rejects zero: False
- **fee arm condition met: False**

- delta_bar_fee = 0.0399, rejects zero at 5%: True -- REPORTED ONLY, superseded as a trigger by the DiD above (Addendum 3 keeps it so a specification change is recorded, not hidden)
- delta_bar_pub rejects zero at 5%: False (available=True, delta_bar=-0.0311)
- maker margin sign-flip (a vs c) surviving the ribbon: False (layer_a=0.0240, layer_c=0.0454, sign_flip=False, ribbon_fragile=False)

## 7. R3 (firewalled, prospective)

R2's verdict above is locked to its own output artifact before any R3 number is examined (docs/analysis_plan.md S4). This narrative is not revised in light of R3, even if R3 is suggestive. See kalshi_mt.r3.firewall.
