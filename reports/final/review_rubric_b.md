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
| 7 | Platform & style conformity | **4** | 7 | Author block, references and both declarations; manuscript class still open |
|  | **Total** | **52/70** | **59/70** | Gate is 56 |

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

## Source audit against the original PDF, 2026-08-28

The replicated paper was re-read in full and every claim both drafts attribute
to it was checked against the text. The copy supplied matched the January 2026
version already fetched from karlwhelan.com character for character, so the
drafts had been built against the right document.

**All 25 numeric and factual attributions hold.** Counts, returns, maker shares,
the Mincer-Zarnowitz coefficients, all five by-year slopes, the filters and the
fee formula are exactly as the drafts state them.

**Three passages were presented as quotations that the original does not say.**
They were paraphrases from this project's spec notes that hardened into
quotation marks somewhere between the spec and the draft:

| Draft said | The original says |
|---|---|
| "total traded volume at closure >= $1,000" | "We focus only on contracts that have reached a total trading volume upon market closure of at least $1,000" |
| "Last trade before the same time on each of up to 10 prior days" | "the final traded price as the market closed and also, **where available**, previous prices from 24-hour intervals up to 10 days before markets closed" |
| "some evidence the bias is diminishing" | "there is some evidence that the bias in prices is diminishing over time" |

Two of the three sat in sections whose entire argument is about what the
original's prose says, which is the worst place to paraphrase inside quotation
marks, because there the exact words are the evidence. Correcting the second one
strengthened the argument rather than weakening it: "where available" is a
plainer statement of the skip reading than our paraphrase was, and the original
describes the same construction a second time without mentioning gaps at all.
Paper B now quotes both descriptions and observes that neither settles what
their own counts settle.

**And the original supplies an objection that neither draft answered.** BDW
write: "Our results below are not sensitive to cutting the data off in December
2024 or to excluding the category containing sports bets." Paper A's headline
result is that sports composition contaminates the aggregate at that boundary,
so this is the first thing a referee -- or these authors -- would raise, and it
appeared nowhere in the paper. `CLAUDE.md` Section 1 had anticipated it
explicitly and told the drafts not to cite their robustness as covering ours;
the instruction was there and the paragraph was missing.

Paper A Section 4.4 now answers it, and the answer is arithmetic: sports is
**4.3% of the observations inside their window** against **58.8% after the
boundary**, a factor of fourteen. Deleting a category worth one observation in
twenty-three barely moves an estimate, which is what they found; the problem
arises from the share becoming a majority after their sample ends, so no test
run inside their window could have detected it.

**What this says about the rubric.** The rubric scored argument quality 9/10 and
did not find this, because it reviews a paper against itself -- its internal
logic, its structure, its coverage of its own claims. It cannot know that the
work being replicated pre-empts the headline result, because it never reads that
work. A checklist is not a referee, and the gap between them is exactly this
kind of finding.

`tools/audit_source_quotes.py` now checks that every quoted fragment in both
drafts is a recorded quotation, with the recorded set in
`docs/source_quotes.yaml` and an optional `--pdf` mode that re-verifies them
against the source. The paper itself is not committed: it is someone else's
work and this repository is public.

## What is still open

- **Manuscript class.** Markdown, and the target outlet's format is not yet
  fixed because the outlet decision waits on the original being published.
- **JCRE's own requirements are unread.** The venue is named as an example
  rather than confirmed, and its submission rules should be read before the
  format work is done rather than after.
- **The maker-return divergence (−1.33% against −9.64%) stands unresolved**, and
  the paper commits to contacting the original authors before submission. That
  is a real outstanding action, not a caveat.
- The declarations are settled as of 2026-08-28: interest declared none, and a
  Generative AI declaration added --- it was absent from both papers, not merely
  unconfirmed. The end matter was also reordered, since this paper had its
  reference list *before* its declarations.
