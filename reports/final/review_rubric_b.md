# Self-referee scorecard — Paper B

**2026-08-27.** Paper B (`paper_b_replication.md`) scored against the same
external rubric used for Paper A — the final quality gate of
`lishix520/academic-paper-skills`. Seven dimensions, 10 points each, pass at
>=56/70. Context and what was ruled out: [review_rubric_a.md](review_rubric_a.md).

| # | Dimension | Before | After | Note |
|---|---|---:|---:|---|
| 1 | Overall argument quality | 9 | 9 | Answers the circularity objection in §3.2 before a referee can raise it |
| 2 | Literature integration | **4** | 8 | Cited exactly one work, and named two more without citing them |
| 3 | Clarity & accessibility | 9 | 9 | — |
| 4 | Originality & contribution | 8 | 8 | The two construction resolutions and the 95.7% validation carry it |
| 5 | Methodological rigor | 9 | 9 | Verdict vocabulary ex ante; count gate before estimates; branches reported |
| 6 | Structure & organization | 9 | 9 | — |
| 7 | Platform & style conformity | **4** | **6** | Author block and references added; manuscript class still open |
|  | **Total** | **52/70** | **58/70** | Gate is 56 |

## What was fixed

1. **The regression's own namesakes were uncited.** The paper estimates a
   Mincer–Zarnowitz regression and never cited Mincer and Zarnowitz (1969); it
   invoked Cameron–Gelbach–Miller two-way clustering and never cited Cameron,
   Gelbach and Miller (2011). Both now carry their references.
2. **No replication-methodology frame.** The paper called itself a "conceptual
   replication" without engaging the literature on what that term means. §1 now
   places it against Clemens (2017) — population and specification are the
   original's, only the sample is drawn again, so a discrepancy here is evidence
   about collection and coverage rather than about the original's method — and
   cites Hamermesh (2007) on why this kind of test is undersupplied.
3. **The favorite–longshot bias was asserted without support**, as in Paper A.
   Now carries Ottaviani and Sørensen (2008) and Thaler and Ziemba (1988).
4. **No reference list existed.** Added, 7 entries, each checked against its
   source on 2026-08-27, and carrying the same GWU cover-sheet note as Paper A.

## What the figure check found

All 73 checks across both papers pass, 24 of them Paper B's. Two of Paper B's
numbers had no artifact behind them when the check was written:

- **10,061 events** (§4's reconciliation table). Not held in any committed
  artifact. Counted directly against the database on 2026-08-27: **10,061
  distinct events over 33,222 markets, −18.9% against BDW's 12,403** — exactly
  what the paper states, including the delta. The number is correct; only its
  provenance was missing, and this file is now that provenance.
- The reconciliation and mismatch-filter rates (12,416 / 44,946 / 3,257 / 95.7%
  / 4.345%) are sourced in `docs/r1_reproduction_findings.md`, which is
  committed. They are not machine-checked, because they come from one-shot
  measurement tools rather than a standing artifact.

Contrast with Paper A, where the same check found **392,597** — a headline
sample size supported by no artifact and contradicted by both the locked run and
the live database. That is the asymmetry worth noting: an unsourced number is not
automatically wrong, and the only way to tell the two cases apart is to go and
look.

## What is still open

- **Manuscript class.** Markdown, and the target outlet's format is not yet
  fixed because the outlet decision waits on the original being published.
- **JCRE's own requirements are unread.** The venue is named as an example
  rather than confirmed, and its submission rules should be read before the
  format work is done rather than after.
- **The maker-return divergence (−1.33% against −9.64%) stands unresolved**, and
  the paper commits to contacting the original authors before submission. That
  is a real outstanding action, not a caveat.
- **The declaration of interest is an unconfirmed checkpoint**, as in Paper A.
