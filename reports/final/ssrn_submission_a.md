# SSRN submission sheet — Paper A

**2026-08-27.** Everything SSRN's submission form asks for, in the order it asks.
The paper itself is `paper_a_composition.md`; this file is not part of it.

## Title

Composition Shift and the Measurement of Bias in a Growing Prediction Market:
Evidence from Kalshi, 2021–2026

## Author

Vladyslav Yurchyna — Independent Researcher — vlad.yurchina@outlook.com

## Abstract (plain text, 365 words)

Prediction markets are now studied intensively enough that their own growth has become a measurement problem. We show this concretely on Kalshi, using 376.8 million fills through June 2026. Between the 2024 calendar year and the post-May-2025 window, sports contracts went from 0.009% of the in-scope sample to 58.8% — a category that barely existed becoming the majority of observations in fourteen months. Decomposing the aggregate change in the Mincer–Zarnowitz slope at that boundary, 41% of it is composition rather than any change in how the market prices risk. A before/after comparison of aggregate bias across early 2025 — the natural design, and one already being applied to this venue — largely measures the arrival of an asset class. Having established that, we ask the persistence question properly. Two events make Kalshi a candidate natural experiment: a maker fee in 2025 and the public documentation of its pricing biases in September 2025. We reconstruct the fee schedule from sixteen dated captures of Kalshi's own published document and find it is not the exchange-wide regime change the literature assumes: a per-series surcharge covering 8.0% to 14.4% of in-scope markets, revised five times, flat per contract before it was quadratic in price. That rules out a step dummy and calls for a difference-in-differences between treated and untreated series trading in the same months. The pre-specified estimate is a tight null: −0.0016 (0.0064) on 98 treated series and 119,646 event clusters. An event study around each series' own adoption date, added after that result was known and reported as such, finds pre-treatment coefficients jointly indistinguishable from zero (χ²(5) = 3.24, p = 0.66) — supporting parallel trends in a setting where treatment was visibly selected on market-making activity — and post-treatment coefficients jointly different from zero (χ²(10) = 21.01, p = 0.021). Read as exploratory, that indicates a transitory reduction in the bias three to four months after a series is charged, decaying back within the year; the static average would conceal such a shape by construction. The maker's return advantage at prices at or above 50c survives every fee layer and every plausible fee rate. We publish the fee history, the category mapping and the full pipeline.

## Keywords

prediction markets; favorite-longshot bias; composition effects;
difference-in-differences; transaction fees; market microstructure; Kalshi

## JEL classification

G14 (Information and Market Efficiency; Event Studies) — primary
G13 (Contingent Pricing; Futures Pricing)
D47 (Market Design)
C52 (Model Evaluation, Validation, and Selection)

## Networks / subject areas

Pick these in SSRN's own classification tree rather than from this list — the
eJournal names change and only the live tree is authoritative. The four areas
the paper belongs to are: **econometric methods** (the DiD and event study),
**market microstructure** (maker/taker structure and fees), **information and
market efficiency** (the bias itself), and **behavioral/experimental economics**
(the favorite–longshot bias literature). Match each to the nearest available
network.

## Files to upload

- The manuscript as PDF. SSRN accepts PDF; the Elsevier LaTeX build is for the
  journal submission and is not required here.
- No data files. The repository link below carries the pipeline and artifacts.

## Repository / data availability statement

The collection pipeline, analysis code, sixteen archived captures of Kalshi's
fee schedule with the parser producing a machine-readable step function, the
category mapping table, and the committed analysis plan with dated amendments
are public and MIT-licensed at
`github.com/Vladosyna/kalshi-makers-takers-persistence`. The repository contains
no execution code: every endpoint used is public and unauthenticated.

## Two things to settle before uploading

1. **The declaration of interest is still an open checkpoint** in the
   manuscript. SSRN does not require it, but posting a paper about a trading
   venue with an unresolved position-disclosure line is worse than pointless.
2. **The companion replication is not posted with this.** Paper B is held until
   the original is published. If both were posted together, a reader would take
   the replication as also submitted somewhere, which is not the case.
