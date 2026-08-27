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
| 2 | Literature integration | **5** | 7 | Was 11 works cited in prose with no bibliography |
| 3 | Clarity & accessibility | 9 | 9 | — |
| 4 | Originality & contribution | 9 | 9 | Fee-schedule sourcing from 16 dated captures is the novel input |
| 5 | Methodological rigor | 9 | 9 | Pre-specification dated; post-hoc labelled; own gaps named |
| 6 | Structure & organization | 8 | 9 | One broken cross-reference |
| 7 | Platform & style conformity | **5** | **5** | Unresolved — see below |
|  | **Total** | **54/70** | **57/70** | Gate is 56 |

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
5. **No reference list existed.** Added, 17 entries.

## What is still open

**Platform conformity, 5/10 — the one dimension still under the flag threshold.**
Three items, none of which can be settled without the author's own input:

- **No author, affiliation or corresponding-author block**, and no declaration of
  interest. Elsevier requires both.
- **The abstract is 376 words** against the ~200 that IJF expects. SSRN has no
  such cap, so this blocks the journal submission and not the preprint.
- **The manuscript is Markdown**, not the Elsevier LaTeX article class.

**Three references carry explicit `[TO VERIFY]` markers** — Becker (2026),
Whelan (2023), Qin and Yang (2026). They are cited from this project's own
notes and their bibliographic data was not re-checked against the sources for
this draft. The markers are deliberate: a plausible-looking reconstruction is
worse than a visible hole, because only the hole gets fixed.

**No standing check re-verifies the paper's numbers against the artifacts.** The
20/20 and 12/12 verification passes were run once, by hand. Every figure in the
paper is regenerable from `reports/r1/r1_report.json`,
`reports/r2/verdict_lock.json`, `reports/r2/escalation_run.json` and
`reports/r2/event_study.json`, so a script could assert them on every commit.
Recommended, not done here.

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
