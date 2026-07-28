"""
=============================================================
Canadian Housing Data Governance Project (independent portfolio project)
Script: integration/prove_equivalence.py
Author: Ram Krishna Dhakal
Purpose: Prove the config-driven runner produces IDENTICAL results to the
         original hardcoded dq_engine.py.

         A refactor is only trustworthy if it is provably equivalent.
         This script runs both engines against the same dataset and
         compares them at three levels of strictness:

           1. Rule level    — same pass rate, failure count and status
           2. Record level   — the SAME EXACT rows fail each rule,
                               not merely the same number of rows
           3. Summary level  — same overall score, grade and totals

         Level 2 is the one that matters. Two engines can agree on
         "307 failures" while disagreeing about which 307 records.

         Exits 1 on any divergence, so it can gate a CI pipeline.

SAFETY: both engines run IN MEMORY. Nothing is written to disk and no
        existing artifact in scorecard/ or data/processed/ is modified.

How to run (from the project root):
    python integration/prove_equivalence.py
=============================================================
"""

import contextlib
import io
import os
import sys

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "integration"))

import dq_engine                                    # noqa: E402  the original engine
import dq_runner                                    # noqa: E402  the new runner
from rule_types import build_context                 # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

DATA  = os.path.join(ROOT, "data", "raw", "cmhc_housing_starts_2018_2023.csv")
RULES = os.path.join(ROOT, "integration", "rules", "cmhc_housing_starts.yaml")

PASS_MARK = "✓"
FAIL_MARK = "✗"

failures = []      # every divergence found


def note_failure(message):
    failures.append(message)


def quiet(fn, *args, **kwargs):
    """Run a noisy function without letting it print."""
    with contextlib.redirect_stdout(io.StringIO()):
        return fn(*args, **kwargs)


# ── RUN BOTH ENGINES ──────────────────────────────────────────────────────────
def run_original():
    df = quiet(dq_engine.load_data, DATA)
    results, exceptions = quiet(dq_engine.run_dq_rules, df)
    return results, exceptions


def run_new():
    df     = dq_runner.load_source(DATA)
    config = dq_runner.load_rules(RULES)
    results, exceptions = quiet(
        dq_runner.run_rules, df, config["rules"], build_context()
    )
    return results, exceptions


# ── COMPARISON HELPERS ────────────────────────────────────────────────────────
def failing_ids(exceptions, rule_id):
    """The set of _record_id values that failed a given rule."""
    if exceptions.empty:
        return set()
    subset = exceptions[exceptions["_rule_id"] == rule_id]
    return set(subset["_record_id"].tolist())


# ── LEVEL 1 + 2: PER RULE ─────────────────────────────────────────────────────
def compare_rules(old_results, new_results, old_exc, new_exc):
    print("─" * 96)
    print("  LEVEL 1 & 2 · PER-RULE COMPARISON")
    print("─" * 96)
    print(f"  {'Rule':<9} {'Failed (old)':>13} {'Failed (new)':>13} "
          f"{'Rate (old)':>11} {'Rate (new)':>11} {'Same rows':>11}   Verdict")
    print("─" * 96)

    old_ids = set(old_results["Rule_ID"])
    new_ids = set(new_results["Rule_ID"])

    if old_ids != new_ids:
        note_failure(f"Rule sets differ. Only in old: {old_ids - new_ids}. "
                     f"Only in new: {new_ids - old_ids}")

    for rule_id in sorted(old_ids & new_ids):
        o = old_results[old_results["Rule_ID"] == rule_id].iloc[0]
        n = new_results[new_results["Rule_ID"] == rule_id].iloc[0]

        same_count  = int(o["Records_Failed"]) == int(n["Records_Failed"])
        same_rate   = float(o["Pass_Rate_Pct"]) == float(n["Pass_Rate_Pct"])
        same_status = o["Status"] == n["Status"]

        o_ids, n_ids = failing_ids(old_exc, rule_id), failing_ids(new_exc, rule_id)
        same_rows    = o_ids == n_ids

        ok = same_count and same_rate and same_status and same_rows
        print(f"  {rule_id:<9} {int(o['Records_Failed']):>13,} {int(n['Records_Failed']):>13,} "
              f"{float(o['Pass_Rate_Pct']):>10.2f}% {float(n['Pass_Rate_Pct']):>10.2f}% "
              f"{(PASS_MARK if same_rows else FAIL_MARK):>11}   "
              f"{PASS_MARK + ' match' if ok else FAIL_MARK + ' DIVERGED'}")

        if not same_count:
            note_failure(f"{rule_id}: failure count {int(o['Records_Failed'])} vs {int(n['Records_Failed'])}")
        if not same_rate:
            note_failure(f"{rule_id}: pass rate {o['Pass_Rate_Pct']} vs {n['Pass_Rate_Pct']}")
        if not same_status:
            note_failure(f"{rule_id}: status {o['Status']} vs {n['Status']}")
        if not same_rows:
            only_old, only_new = o_ids - n_ids, n_ids - o_ids
            # Flag the count-matches case separately: it is the dangerous one,
            # because a summary comparison alone would have called it a match.
            headline = ("SAME COUNT BUT DIFFERENT ROWS" if same_count
                        else "different failing rows")
            note_failure(
                f"{rule_id}: {headline} — "
                f"{len(only_old)} only in old, {len(only_new)} only in new "
                f"(examples old={sorted(only_old)[:5]}, new={sorted(only_new)[:5]})"
            )


# ── LEVEL 3: SUMMARY ──────────────────────────────────────────────────────────
def compare_summary(old_results, new_results, old_exc, new_exc):
    print("\n" + "─" * 96)
    print("  LEVEL 3 · SUMMARY COMPARISON")
    print("─" * 96)

    def summarise(results, exceptions):
        overall = round(results["Pass_Rate_Pct"].mean(), 2)
        return {
            "Overall score":      overall,
            "Grade":              "A" if overall >= 99 else ("B" if overall >= 95 else "C"),
            "Rules PASS":         int((results["Status"] == "PASS").sum()),
            "Rules WARN":         int((results["Status"] == "WARN").sum()),
            "Rules FAIL":         int((results["Status"] == "FAIL").sum()),
            "Total failures":     int(results["Records_Failed"].sum()),
            "Exception rows":     len(exceptions),
            "Unique records hit": exceptions["_record_id"].nunique() if not exceptions.empty else 0,
        }

    old_s, new_s = summarise(old_results, old_exc), summarise(new_results, new_exc)

    print(f"  {'Metric':<22} {'dq_engine.py':>16} {'dq_runner.py':>16}   Verdict")
    print("─" * 96)
    for key in old_s:
        ok = old_s[key] == new_s[key]
        print(f"  {key:<22} {str(old_s[key]):>16} {str(new_s[key]):>16}   "
              f"{PASS_MARK + ' match' if ok else FAIL_MARK + ' DIVERGED'}")
        if not ok:
            note_failure(f"Summary '{key}': {old_s[key]} vs {new_s[key]}")

    # Dimension scores
    print()
    old_dim = old_results.groupby("DQ_Dimension")["Pass_Rate_Pct"].mean().round(2)
    new_dim = new_results.groupby("DQ_Dimension")["Pass_Rate_Pct"].mean().round(2)

    for dim in sorted(set(old_dim.index) | set(new_dim.index)):
        o, n = old_dim.get(dim), new_dim.get(dim)
        ok = o == n
        print(f"  {dim:<22} {str(o):>16} {str(n):>16}   "
              f"{PASS_MARK + ' match' if ok else FAIL_MARK + ' DIVERGED'}")
        if not ok:
            note_failure(f"Dimension '{dim}': {o} vs {n}")

    # Strongest single check: the exact set of affected records, across all rules
    print()
    old_all = set(old_exc["_record_id"]) if not old_exc.empty else set()
    new_all = set(new_exc["_record_id"]) if not new_exc.empty else set()
    ok = old_all == new_all
    print(f"  {'Affected record set':<22} {len(old_all):>16,} {len(new_all):>16,}   "
          f"{PASS_MARK + ' identical' if ok else FAIL_MARK + ' DIVERGED'}")
    if not ok:
        note_failure(f"Affected record sets differ: {len(old_all - new_all)} only in old, "
                     f"{len(new_all - old_all)} only in new")


# ── MAIN ──────────────────────────────────────────────────────────────────────
def main():
    print("=" * 96)
    print("  EQUIVALENCE PROOF · dq_engine.py  vs  integration/dq_runner.py")
    print("  Author: Ram Krishna Dhakal")
    print("=" * 96)
    print(f"\n  Dataset : {os.path.relpath(DATA, ROOT)}")
    print(f"  Rules   : {os.path.relpath(RULES, ROOT)}")
    print("  Mode    : both engines run in memory; nothing is written to disk\n")

    old_results, old_exc = run_original()
    new_results, new_exc = run_new()

    print(f"  Original engine : {len(old_results)} rules executed")
    print(f"  New runner      : {len(new_results)} rules executed\n")

    compare_rules(old_results, new_results, old_exc, new_exc)
    compare_summary(old_results, new_results, old_exc, new_exc)

    print("\n" + "=" * 96)
    if failures:
        print(f"  {FAIL_MARK} NOT EQUIVALENT — {len(failures)} divergence(s) found")
        print("=" * 96)
        for f in failures:
            print(f"    - {f}")
        print("\n  The config-driven runner must NOT replace dq_engine.py until these are resolved.")
        sys.exit(1)

    print(f"  {PASS_MARK} EQUIVALENT — the config-driven runner reproduces dq_engine.py exactly")
    print("=" * 96)
    print("    Identical at rule level, record level and summary level.")
    print("    The 15 rules now live in YAML instead of Python with no change in behaviour.")
    sys.exit(0)


if __name__ == "__main__":
    main()
