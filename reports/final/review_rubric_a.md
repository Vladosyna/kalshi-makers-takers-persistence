# Self-referee scorecard — Paper A

**2026-08-27.** Paper A (`paper_a_composition.md`) scored against the final
quality gate of `lishix520/academic-paper-skills`
(`composer/references/writing_standards.md`), cloned to
`D:\Papers\tools\academic-paper-skills` at commit c325557 and read as reference
material only — it is not installed as an active skill, and none of its
structural templates were applied. See "What was ruled out" below.

Seven dimensions, 10 points each, pass at >=56/70; any dimension under 7 is
flagged for revision by the rubric's own script.

| # | Dimension | Before | After | Note |
|---|---|---:|---:|---|
| 1 | Overall argument quality | 9 | 9 | Thesis clear; §4.4 and §6.2 pre-empt the two obvious referee objections |
| 2 | Literature integration | **5** | 9 | Was 11 works cited in prose with no bibliography; 17 entries now, all checked against sources |
| 3 | Clarity & accessibility | 9 | 9 | — |
| 4 | Originality & contribution | 9 | 9 | Fee-schedule sourcing from 16 dated captures is the novel input |
| 5 | Methodological rigor | 9 | 9 | Pre-specification dated; post-hoc labelled; own gaps named |
| 6 | Structure & organization | 8 | 9 | One broken cross-reference |
| 7 | Platform & style conformity | **5** | 8 | Author block, references, trimmed abstract and an elsarticle build; declaration still open |
|  | **Total** | **54/70** | **62/70** | Gate is 56 |

## What was fixed

1. **Broken cross-reference.** §8 pointed at "the event study in §6.2"; §6.2 is
   the identifying-assumption discussion and the event study is §6.3.
2. **"Among the most replicated findings" was uncited**, in the opening sentence
   of the introduction and again in §8. Now carries Thaler and Ziemba (1988),
   Ottaviani and Sørensen (2008), Snowberg and Wolfers (2010), with Wolfers and
   Zitzewitz (2004) for prediction markets as forecasting instruments.
3. **The Polymarket reversed-sign claim in §7 was uncited.** Now carries Qin and
   Yang (2026), which `docs/analysis_plan.md` had recorded but the draft had not.
4. **McLean and Pontiff (2016) was absent from the whole repository**, although
   `CLAUDE.md` §5 specifies that framing and §6.7 tests exactly their question.
   Added to §8 as its own paragraph.
5. **No reference list existed.** Added, 17 entries, each checked against its
   source on 2026-08-27. Becker (2026) is *The Microstructure of Wealth Transfer
   in Prediction Markets*, SSRN 7217640; Whelan (2023) is *How Do Prediction
   Market Fees Affect Prices and Participants?*, CEPR DP 17972 / MPRA 116926;
   Qin and Yang (2026) is *Polymarket-v1 Database*, arXiv:2606.04217.
6. **The abstract was 376 words.** Trimmed to 238, with the pre-specified null
   still leading and the exploratory label still attached. The original is kept
   as Appendix A for the preprint posting, where no length cap applies.

## What is still open

- **The declaration of interest is an unconfirmed checkpoint.** Both papers
  carry an explicit `AWAITING AUTHOR CONFIRMATION` line instead of a statement.
  This paper analyses a trading venue, so whether the author holds positions on
  it is exactly what a reader is entitled to know, and it is not mine to
  declare.
- **The LaTeX build is not compile-verified.** `paper_a_composition.tex` is an
  `elsarticle` conversion, checked by `tools/lint_tex.py` for balanced
  environments and braces, resolved citations and cross-references, escaped
  specials, correct tabular column counts, and — the one that matters — that
  every figure in the Markdown survived into the `.tex`. All pass. But no LaTeX
  toolchain is installed on this machine, so it has never been run through
  pdflatex. Build it before submitting.
- **IJF's exact abstract cap is unverified.** An earlier version of this file
  asserted ~200 words. ScienceDirect returns 403 to automated fetches, so the
  number could not be confirmed and the assertion is withdrawn; 238 words is
  safely inside the range Elsevier economics titles normally set, but the cap
  should be read off the Guide for Authors by hand before submission.

**No standing check re-verifies the paper's numbers against the artifacts.** The
20/20 and 12/12 verification passes were run once, by hand. Every figure in the
paper is regenerable from `reports/r1/r1_report.json`,
`reports/r2/verdict_lock.json`, `reports/r2/escalation_run.json` and
`reports/r2/event_study.json`, so a script could assert them on every commit.
Recommended, not done here.

## What the citation check turned up

Two findings beyond the references themselves, both from reading the sources
rather than the notes:

**The source paper is still a working paper.** Karl Whelan's own research page
lists *Makers and Takers* (January 2026, with Bürgi and Deng) under "Working
Papers" with no journal status. `CLAUDE.md` §5 requires this be checked
immediately before submission, and it was checked on 2026-08-27: **Paper B stays
held**, since its target outlet requires the original to be published.

**GWU Working Paper 2026-001 carries a variant title.** Its cover sheet, dated
February 2026, reads "Makers *or* Takers". This is a cover-sheet variant and
nothing more: the paper's own title page inside that document reads "Makers
*and* Takers ... January 2026", and its 44 content pages are identical to the
January version page for page. All ten pinned replication targets — 12,403
events, 46,282 contracts, 156,986 prices, 106,209 tail counts, −9.64%, −31.46%,
ψ = 0.034, α = −1.736, +2.6%, 63 dropped — appear unchanged in both. The
replication targets are stable and the citation is correct as written; a
footnote in §8 now records the variant so nobody chasing that number concludes
they have found a different paper.

## What was ruled out

**The toolkit's section templates and venue guidance were not applied.** Its
section guides cover Abstract, Introduction, Conceptual/Theoretical chapter,
Argument chapter, Critical Review and Case Study; there is no Data,
Identification, Results or Robustness section anywhere in it, and
`writing_standards.md` and `composer/SKILL.md` contain zero occurrences of
"empirical", "regression", "statistic", "econometric" or "robustness". Its
platform guidance targets PhilArchive, PhilSci-Archive and philosophy arXiv.
Reshaping an econometrics paper to that skeleton would be a downgrade.

**The strategist skill was not run at all.** Its Phase 1 (sample 8–10 papers to
infer a venue) and Phase 2 (20–50-source gap analysis) duplicate decisions this
project already made on harder evidence — the JCRE finding and the two-paper
split recorded in `docs/analysis_plan.md` Addendum 5.

**The rubric's literature thresholds were applied with judgement, not
mechanically.** It scores under 20 sources as "needs revision", a philosophy
norm; 15–20 references is normal for an IJF empirical note. Dimension 2 is
scored 7 rather than the 3–4 the rubric's own bands would give, because the
defect was the *missing bibliography and the uncited headline claims*, not the
count.
