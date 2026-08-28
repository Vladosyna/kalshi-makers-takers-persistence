"""Assert every headline figure in the drafts against the artifacts that produced it.

WHY THIS EXISTS
---------------
Both papers state that all figures regenerate from four JSON artifacts. That was
true when each number was written and checked by hand, once. Nothing re-checked
them afterwards, and the papers have since been edited for prose, citations,
abstract length and an author block -- every one of those edits touches the same
file the numbers live in.

WHAT IT CHECKS, AND IN WHICH DIRECTION
--------------------------------------
Not "parse a number out of the paper and see if it looks plausible". Each check
reads the value from the artifact, formats it exactly the way the paper is
supposed to render it, and asserts that string is present in the paper. So it
fails on three different mistakes:

  * the paper was edited and a digit changed;
  * the analysis was re-run and the artifact moved underneath the paper;
  * a number was written that no artifact supports at all.

The third is the one hand-checking misses, because a hand-check starts from the
paper and finds a source for each claim -- it never notices a claim whose source
was never there.

Usage:
    python tools/verify_paper_figures.py            # check, exit 1 on any failure
    python tools/verify_paper_figures.py --list     # show every check and its source
"""

from __future__ import annotations

import io
import json
import sys
import unicodedata
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PAPER_A = PROJECT_ROOT / "reports" / "final" / "paper_a_composition.md"
PAPER_B = PROJECT_ROOT / "reports" / "final" / "paper_b_replication.md"

R1 = PROJECT_ROOT / "reports" / "r1" / "r1_report.json"
LOCK = PROJECT_ROOT / "reports" / "r2" / "verdict_lock.json"
ESC = PROJECT_ROOT / "reports" / "r2" / "escalation_run.json"
EVENT = PROJECT_ROOT / "reports" / "r2" / "event_study.json"


def _load(p: Path) -> dict:
    with io.open(p, encoding="utf-8") as f:
        return json.load(f)


def _text(p: Path) -> str:
    with io.open(p, encoding="utf-8") as f:
        t = f.read()
    # The drafts use U+2212 MINUS SIGN in prose and U+002D in some tables. Fold
    # every dash-like codepoint to ASCII "-" so a check never fails on typography.
    for ch in ("−", "–", "—", "‐", "‑"):
        t = t.replace(ch, "-")
    return unicodedata.normalize("NFC", t)


def _norm(s: str) -> str:
    for ch in ("−", "–", "—", "‐", "‑"):
        s = s.replace(ch, "-")
    return s


class Check:
    """One assertion: an artifact value, rendered as the paper should render it."""

    def __init__(self, label, value, fmt, paper=PAPER_A, source=""):
        self.label = label
        self.value = value
        self.fmt = fmt
        self.paper = paper
        self.source = source

    def rendered(self) -> str:
        return _norm(self.fmt(self.value) if callable(self.fmt) else self.fmt.format(self.value))


def build_checks() -> list[Check]:
    r1, lock, esc, ev = _load(R1), _load(LOCK), _load(ESC), _load(EVENT)

    mt = r1["maker_taker_split"]
    wr = r1["win_rate_by_band"]
    dec = lock["decomposition"]["fee"]
    twfe = lock["maker_fee_did"]["twfe"]
    clean = lock["maker_fee_did"]["clean_controls"]
    mm = esc["maker_margin"]

    fills = sum(e["trade_count"] for e in r1["taker_field_population_by_era"].values())

    c = []
    a = lambda *args, **kw: c.append(Check(*args, **kw))

    # -- Section 2, data ------------------------------------------------------
    a("total fills", fills, "{:,} fills", source="r1_report.taker_field_population_by_era (summed)")
    a("R1 in-scope contracts", r1["in_scope_markets"], "{:,} contracts",
      source="r1_report.in_scope_markets")
    # This one was wrong in the draft -- it read 392,597, a number that appears
    # in no artifact at all. The filter-pass count from the locked run is the
    # sample the analysis actually ran on, and it is what the sentence describes.
    a("R2 in-scope markets", lock["r2_filters"]["passed"],
      lambda v: f"**{v:,}\nmarkets**",
      source="verdict_lock.r2_filters.passed")

    # -- Section 3, validation against BDW ------------------------------------
    a("maker return >=50c", mt["maker_return_50c_plus"], "+{:.2%}",
      source="r1_report.maker_taker_split.maker_return_50c_plus")
    a("taker return", mt["taker_return"], "{:.2%}",
      source="r1_report.maker_taker_split.taker_return")
    a("maker share 1-10c", mt["maker_share_by_band"]["1-10c"], "{:.1%}",
      source="r1_report.maker_taker_split.maker_share_by_band['1-10c']")
    a("maker share 91-99c", mt["maker_share_by_band"]["91-99c"], "{:.1%}",
      source="r1_report.maker_taker_split.maker_share_by_band['91-99c']")
    a("psi 2021", r1["by_year_psi"]["2021"]["fit"]["psi"], "{:.4f}",
      source="r1_report.by_year_psi.2021.fit.psi")
    a("psi 2025", r1["by_year_psi"]["2025"]["fit"]["psi"], "{:.4f}",
      source="r1_report.by_year_psi.2025.fit.psi")
    a("win rate 1-10c", wr["1-10c"]["win_rate"], "{:.2%}",
      source="r1_report.win_rate_by_band['1-10c'].win_rate")
    a("mean price 1-10c", wr["1-10c"]["mean_price"], lambda v: f"{v*100:.2f}c",
      source="r1_report.win_rate_by_band['1-10c'].mean_price")
    a("win rate 91-99c", wr["91-99c"]["win_rate"], "{:.2%}",
      source="r1_report.win_rate_by_band['91-99c'].win_rate")
    a("mean price 91-99c", wr["91-99c"]["mean_price"], lambda v: f"{v*100:.2f}c",
      source="r1_report.win_rate_by_band['91-99c'].mean_price")

    # -- Section 4, composition ----------------------------------------------
    a("within term", dec["within"], "+{:.4f}", source="verdict_lock.decomposition.fee.within")
    a("between term", dec["between"], "+{:.4f}", source="verdict_lock.decomposition.fee.between")
    a("aggregate", dec["aggregate"], "+{:.4f}", source="verdict_lock.decomposition.fee.aggregate")
    a("between share", dec["between"] / dec["aggregate"], "{:.0%}",
      source="verdict_lock.decomposition.fee.between / .aggregate")
    a("within share", dec["within"] / dec["aggregate"], "{:.0%}",
      source="verdict_lock.decomposition.fee.within / .aggregate")

    # -- Section 6, the difference-in-differences -----------------------------
    a("TWFE delta", twfe["delta_did"], "+{:.4f}",
      source="verdict_lock.maker_fee_did.twfe.delta_did")
    a("TWFE se", twfe["delta_did_se"], "{:.4f}",
      source="verdict_lock.maker_fee_did.twfe.delta_did_se")
    a("clean-controls delta", clean["delta_did"], "{:.4f}",
      source="verdict_lock.maker_fee_did.clean_controls.delta_did")
    a("clean-controls se", clean["delta_did_se"], "{:.4f}",
      source="verdict_lock.maker_fee_did.clean_controls.delta_did_se")
    a("treated series", twfe["n_treated_series"], "{:,} treated series",
      source="verdict_lock.maker_fee_did.twfe.n_treated_series")
    a("treated observations", twfe["n_treated_obs"], "{:,}",
      source="verdict_lock.maker_fee_did.twfe.n_treated_obs")
    a("control observations", twfe["n_control_obs"], "{:,}",
      source="verdict_lock.maker_fee_did.twfe.n_control_obs")
    a("event clusters", twfe["n_clusters"], "{:,} event clusters",
      source="verdict_lock.maker_fee_did.twfe.n_clusters")
    a("months", twfe["months"], "{:,} months",
      source="verdict_lock.maker_fee_did.twfe.months")
    a("reference slope psi_bar_R1", lock["psi_bar_r1"], "{:.4f}",
      source="verdict_lock.psi_bar_r1")

    # -- Section 6.3, the event study ----------------------------------------
    a("pre-trend chi2", ev["pretrend_chi2"], lambda v: f"({ev['pretrend_df']}) = {v:.2f}",
      source="event_study.pretrend_chi2 / .pretrend_df")
    a("pre-trend p", ev["pretrend_p"], "p = {:.2f}", source="event_study.pretrend_p")
    a("post-trend chi2", ev["posttrend_chi2"], lambda v: f"({ev['posttrend_df']}) = {v:.2f}",
      source="event_study.posttrend_chi2 / .posttrend_df")
    a("post-trend p", ev["posttrend_p"], "p = {:.3f}", source="event_study.posttrend_p")
    a("event-study n", ev["n"], "{:,}", source="event_study.n")
    for k in ("3", "4"):
        a(f"event-study delta k=+{k}", ev["coefficients"][k], "{:.4f}",
          source=f"event_study.coefficients['{k}']")

    # -- Section 6.5 / 6.7, the pre-specified composition-weighted estimands ---
    a("naive fee delta", lock["delta_bar"]["fee"]["delta_bar"], "+{:.4f}",
      source="verdict_lock.delta_bar.fee.delta_bar")
    a("naive fee CI lo", lock["delta_bar"]["fee"]["ci_lo"], "+{:.4f}",
      source="verdict_lock.delta_bar.fee.ci_lo")
    a("naive fee CI hi", lock["delta_bar"]["fee"]["ci_hi"], "+{:.4f}",
      source="verdict_lock.delta_bar.fee.ci_hi")
    a("publication delta", lock["delta_bar"]["publication"]["delta_bar"], "{:.4f}",
      source="verdict_lock.delta_bar.publication.delta_bar")
    a("publication CI lo", lock["delta_bar"]["publication"]["ci_lo"], "{:.4f}",
      source="verdict_lock.delta_bar.publication.ci_lo")
    a("publication CI hi", lock["delta_bar"]["publication"]["ci_hi"], "+{:.4f}",
      source="verdict_lock.delta_bar.publication.ci_hi")

    # -- Section 6.6, the exploitable margin ----------------------------------
    a("maker margin layer a", mm["layer_a"], "+{:.2%}", source="escalation_run.maker_margin.layer_a")
    a("maker margin layer b", mm["layer_b"], "+{:.2%}", source="escalation_run.maker_margin.layer_b")
    a("maker margin layer c", mm["layer_c"], "+{:.2%}", source="escalation_run.maker_margin.layer_c")
    a("maker sides", mm["n_maker_a"], "{:,}", source="escalation_run.maker_margin.n_maker_a")
    a("taker sides", mm["n_taker_a"], "{:,}", source="escalation_run.maker_margin.n_taker_a")
    ribbon = esc["ribbon"]["margins"]
    a("ribbon max", max(ribbon), "+{:.4f}", source="escalation_run.ribbon.margins (max)")
    a("ribbon min", min(ribbon), "+{:.4f}", source="escalation_run.ribbon.margins (min)")

    # -- Section 7, horizon robustness ----------------------------------------
    a("close-only fee delta", lock["horizon_robustness"]["close_only"]["delta_bar_fee"], "+{:.4f}",
      source="verdict_lock.horizon_robustness.close_only.delta_bar_fee")

    # ======================================================================
    # Paper B. The replication states more of R1 than Paper A does, so the
    # by-year table and the count reconciliation are checked here rather than
    # in the shared block above.
    # ======================================================================
    b = lambda *args, **kw: c.append(Check(*args, paper=PAPER_B, **kw))

    b("B: total fills", fills, "{:,} fills",
      source="r1_report.taker_field_population_by_era (summed)")
    b("B: in-scope contracts", r1["in_scope_markets"], "{:,}",
      source="r1_report.in_scope_markets")
    b("B: Yes prices", lock["r1_panel_n"], "{:,}", source="verdict_lock.r1_panel_n")
    b("B: doubled prices", lock["r1_panel_n"] * 2, "{:,}",
      source="verdict_lock.r1_panel_n x 2")

    for year in ("2021", "2022", "2023", "2024", "2025"):
        fit = r1["by_year_psi"][year]["fit"]
        b(f"B: psi {year}", fit["psi"], "{:.4f}", source=f"r1_report.by_year_psi.{year}.fit.psi")
        b(f"B: psi {year} se", fit["psi_se"], "{:.4f}",
          source=f"r1_report.by_year_psi.{year}.fit.psi_se")

    b("B: maker return", mt["maker_return"], "{:.2%}",
      source="r1_report.maker_taker_split.maker_return")
    b("B: taker return", mt["taker_return"], "{:.2%}",
      source="r1_report.maker_taker_split.taker_return")
    b("B: maker return >=50c", mt["maker_return_50c_plus"], "+{:.2%}",
      source="r1_report.maker_taker_split.maker_return_50c_plus")
    b("B: maker share 1-10c", mt["maker_share_by_band"]["1-10c"], "{:.1%}",
      source="r1_report.maker_taker_split.maker_share_by_band['1-10c']")
    b("B: maker share 91-99c", mt["maker_share_by_band"]["91-99c"], "{:.1%}",
      source="r1_report.maker_taker_split.maker_share_by_band['91-99c']")

    b("B: win rate 1-10c", wr["1-10c"]["win_rate"], "{:.2%}",
      source="r1_report.win_rate_by_band['1-10c'].win_rate")
    b("B: win rate 91-99c", wr["91-99c"]["win_rate"], "{:.2%}",
      source="r1_report.win_rate_by_band['91-99c'].win_rate")

    rb = r1["returns_by_band"]["1-10c"]
    b("B: bottom-band gross return", rb["mean_gross_return"], "{:.1%}",
      source="r1_report.returns_by_band['1-10c'].mean_gross_return")
    b("B: bottom-band net return", rb["mean_net_return"], "{:.1%}",
      source="r1_report.returns_by_band['1-10c'].mean_net_return")

    cv = r1["clustering_verification"]
    b("B: clustering psi se", cv["one_way_psi_se"], "{:.18f}",
      source="r1_report.clustering_verification.one_way_psi_se")

    return c


def consistency_checks() -> list[tuple[str, bool, str]]:
    """Cross-artifact invariants that no single figure would reveal."""
    lock, esc, ev = _load(LOCK), _load(ESC), _load(EVENT)
    out = []

    # The event study and the static DiD must be fitted on the same panel, or
    # section 6.4's "the average hides a hump" argument compares two samples
    # rather than two estimators.
    twfe = lock["maker_fee_did"]["twfe"]
    out.append((
        "event study and static DiD share a panel",
        ev["n"] == twfe["n"] and ev["n_clusters"] == twfe["n_clusters"],
        f"event study n={ev['n']:,}/{ev['n_clusters']:,} clusters vs "
        f"TWFE n={twfe['n']:,}/{twfe['n_clusters']:,}",
    ))

    # Addendum 3 supersedes delta_bar_fee with the series-level DiD. An
    # escalation artifact still keyed on delta_bar_fee is running pre-Addendum-3
    # logic, whatever the code now says.
    escl = esc["escalation"]
    stale = "delta_bar_fee_significant" in escl.get("triggers", [])
    out.append((
        "escalation artifact reflects Addendum 3",
        not stale,
        f"triggers={escl.get('triggers')} escalate={escl.get('escalate')} "
        "-- delta_bar_fee was superseded by the series-level DiD",
    ))

    # The decomposition must actually decompose.
    d = lock["decomposition"]["fee"]
    out.append((
        "within + between = aggregate",
        abs((d["within"] + d["between"]) - d["aggregate"]) < 1e-9,
        f"{d['within']:.6f} + {d['between']:.6f} != {d['aggregate']:.6f}",
    ))

    # Elsevier requires a Declaration of interest and a separate Generative AI
    # declaration, the latter immediately before the reference list. Both papers
    # carried an AWAITING placeholder until 2026-08-28; a placeholder that
    # survives into a submission is worse than no declaration, so it is a check.
    for paper in (PAPER_A, PAPER_B):
        t = _text(paper)
        out.append((
            f"{paper.name}: both declarations present, no placeholder",
            ("## Declaration of Generative AI" in t
             and "### Declaration of interest" in t
             and "AWAITING" not in t),
            f"generative-AI={'## Declaration of Generative AI' in t} "
            f"interest={'### Declaration of interest' in t} "
            f"placeholder-left={'AWAITING' in t}",
        ))
        ai = t.find("## Declaration of Generative AI")
        refs = t.find("\n## References")
        out.append((
            f"{paper.name}: AI declaration precedes the reference list",
            ai != -1 and refs != -1 and ai < refs,
            f"ai at {ai}, references at {refs}",
        ))

    return out


def main() -> int:
    checks = build_checks()

    if "--list" in sys.argv:
        for ch in checks:
            print(f"  {ch.label:34} {ch.rendered():>22}   <- {ch.source}")
        return 0

    texts = {PAPER_A: _text(PAPER_A), PAPER_B: _text(PAPER_B)}
    failed = []
    for ch in checks:
        if ch.rendered() not in texts[ch.paper]:
            failed.append(ch)

    print(f"figure checks: {len(checks) - len(failed)}/{len(checks)} passed")
    for ch in failed:
        print(f"  MISSING  {ch.label}: artifact says {ch.rendered()!r}, "
              f"not found in {ch.paper.name}")
        print(f"           source: {ch.source}")

    print()
    bad_inv = []
    for label, ok, detail in consistency_checks():
        print(f"  {'ok  ' if ok else 'FAIL'} {label}")
        if not ok:
            print(f"       {detail}")
            bad_inv.append(label)

    if failed or bad_inv:
        print(f"\n{len(failed)} figure(s) and {len(bad_inv)} invariant(s) failed")
        return 1
    print("\nall figures and invariants check out")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
