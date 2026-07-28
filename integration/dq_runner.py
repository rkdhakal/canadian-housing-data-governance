"""
=============================================================
Canadian Housing Data Governance Project (independent portfolio project)
Script: integration/dq_runner.py
Author: Ram Krishna Dhakal
Purpose: Source-agnostic data quality runner.

         Reads a source's declared rules from YAML, executes each one via
         the shared rule-type library, and produces a rule-level scorecard
         plus a record-level exception log.

         This file contains NO knowledge of housing data. There is no
         column name, threshold or province code anywhere in it. Point it
         at a different rules file and a different CSV and it works
         unchanged — that is the whole point of the exercise.

SAFETY: writes only to integration/output/. It never touches
        scorecard/ or data/processed/, so dq_engine.py and the Streamlit
        dashboard keep working exactly as before. Equivalence between the
        two is proven separately in step 4.

SCOPE:  rule execution and scoring only. Remediation stays in
        dq_engine.py for now.

How to run:
    python integration/dq_runner.py
    python integration/dq_runner.py --rules <path> --data <path>
=============================================================
"""

import argparse
import os
import sys
from datetime import datetime

import pandas as pd
import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from rule_types import build_context, evaluate           # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Defaults let the runner be executed with no arguments. In step 5 these get
# replaced by a lookup in integration/source_registry.yaml, so the runner
# stops needing to be told where anything lives.
DEFAULT_RULES  = os.path.join(ROOT, "integration", "rules", "cmhc_housing_starts.yaml")
DEFAULT_DATA   = os.path.join(ROOT, "data", "raw", "cmhc_housing_starts_2018_2023.csv")
OUTPUT_DIR     = os.path.join(ROOT, "integration", "output")

# Thresholds copied from dq_engine.py so scoring is directly comparable
WARN_THRESHOLD  = 95
GRADE_A_CUTOFF  = 99
GRADE_B_CUTOFF  = 95


# ── LOAD ──────────────────────────────────────────────────────────────────────
def load_rules(path):
    with open(path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    return config


def load_source(path):
    df = pd.read_csv(path)
    df["_record_id"] = range(1, len(df) + 1)
    return df


# ── EXECUTE ───────────────────────────────────────────────────────────────────
def run_rules(df, rules, context):
    """Execute every declared rule. Returns (rule results, record exceptions)."""
    total          = len(df)
    results        = []
    all_exceptions = []

    for rule in rules:
        mask   = evaluate(df, rule, context)
        failed = int(mask.sum())
        passed = total - failed
        score  = round(passed / total * 100, 2)
        status = "PASS" if score == 100 else ("WARN" if score >= WARN_THRESHOLD else "FAIL")

        icon = "✓" if status == "PASS" else "⚠"
        print(f"      {icon} {rule['id']} | {rule['name']:<50} | {score:>7.2f}% | {failed:>5} failed | {status}")

        if failed > 0:
            failed_df = df[mask].copy()
            failed_df["_rule_id"]        = rule["id"]
            failed_df["_rule_name"]      = rule["name"]
            failed_df["_dimension"]      = rule["dimension"]
            failed_df["_cde"]            = rule["cde"]
            failed_df["_severity"]       = rule["severity"]
            failed_df["_failure_reason"] = rule["description"]
            failed_df["_remediation"]    = rule["remediation"]
            failed_df["_flagged_at"]     = datetime.now().strftime("%Y-%m-%d %H:%M")
            all_exceptions.append(failed_df)

        results.append({
            "Rule_ID": rule["id"], "Rule_Name": rule["name"],
            "DQ_Dimension": rule["dimension"], "CDE_Affected": rule["cde"],
            "Description": rule["description"], "Severity": rule["severity"],
            "Rule_Type": rule["type"],
            "Total_Records": total, "Records_Passed": passed,
            "Records_Failed": failed, "Pass_Rate_Pct": score,
            "Status": status, "Remediation_Action": rule["remediation"],
        })

    df_results    = pd.DataFrame(results)
    df_exceptions = pd.concat(all_exceptions, ignore_index=True) if all_exceptions else pd.DataFrame()
    return df_results, df_exceptions


# ── SCORE ─────────────────────────────────────────────────────────────────────
def score(df_results):
    """Aggregate rule results the same way dq_engine.py does."""
    overall = round(df_results["Pass_Rate_Pct"].mean(), 2)
    grade   = "A" if overall >= GRADE_A_CUTOFF else ("B" if overall >= GRADE_B_CUTOFF else "C")

    by_dim = df_results.groupby("DQ_Dimension").agg(
        Rules_Count=("Rule_ID", "count"),
        Avg_Pass_Rate=("Pass_Rate_Pct", "mean"),
        Total_Failed=("Records_Failed", "sum"),
    ).reset_index()
    by_dim["Avg_Pass_Rate"] = by_dim["Avg_Pass_Rate"].round(2)

    return {
        "overall": overall,
        "grade":   grade,
        "passing": int((df_results["Status"] == "PASS").sum()),
        "warning": int((df_results["Status"] == "WARN").sum()),
        "failing": int((df_results["Status"] == "FAIL").sum()),
        "total_failures": int(df_results["Records_Failed"].sum()),
        "by_dim":  by_dim,
    }


# ── SAVE ──────────────────────────────────────────────────────────────────────
def save_outputs(source_id, df_results, df_exceptions, stats):
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    scorecard_path = os.path.join(OUTPUT_DIR, f"{source_id}_scorecard.csv")
    df_results.to_csv(scorecard_path, index=False)
    print(f"      ✓ Rule scorecard  → integration/output/{source_id}_scorecard.csv")

    if not df_exceptions.empty:
        exceptions_path = os.path.join(OUTPUT_DIR, f"{source_id}_exceptions.csv")
        df_exceptions.to_csv(exceptions_path, index=False)
        print(f"      ✓ Exception log   → integration/output/{source_id}_exceptions.csv "
              f"({len(df_exceptions):,} rows)")

    dim_path = os.path.join(OUTPUT_DIR, f"{source_id}_by_dimension.csv")
    stats["by_dim"].to_csv(dim_path, index=False)
    print(f"      ✓ By dimension    → integration/output/{source_id}_by_dimension.csv")


# ── MAIN ──────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Source-agnostic DQ rule runner")
    parser.add_argument("--rules", default=DEFAULT_RULES, help="Path to a rules YAML file")
    parser.add_argument("--data",  default=DEFAULT_DATA,  help="Path to the source CSV")
    args = parser.parse_args()

    print("=" * 100)
    print("  Config-Driven DQ Runner")
    print("  Author: Ram Krishna Dhakal")
    print("=" * 100)

    config    = load_rules(args.rules)
    rules     = config["rules"]
    source_id = config["source_id"]

    print(f"\n[1/4] Loading rules config...")
    print(f"      ✓ {len(rules)} rules declared for '{source_id}'")
    print(f"      ✓ Rule types used: {', '.join(sorted({r['type'] for r in rules}))}")

    print(f"\n[2/4] Loading source data...")
    df = load_source(args.data)
    print(f"      ✓ {len(df):,} records, {len(df.columns) - 1} columns")

    context = build_context()
    print(f"\n[3/4] Executing {len(rules)} rules...")
    df_results, df_exceptions = run_rules(df, rules, context)

    stats = score(df_results)

    print(f"\n[4/4] Saving outputs...")
    save_outputs(source_id, df_results, df_exceptions, stats)

    print("\n" + "=" * 100)
    print("  RESULTS")
    print("=" * 100)
    print(f"  Overall DQ Score  : {stats['overall']}%  (Grade {stats['grade']})")
    print(f"  Rules             : {stats['passing']} PASS | {stats['warning']} WARN | {stats['failing']} FAIL")
    print(f"  Total failures    : {stats['total_failures']:,}")
    if not df_exceptions.empty:
        print(f"  Unique records    : {df_exceptions['_record_id'].nunique():,} affected by at least one rule")
    print()
    for _, row in stats["by_dim"].iterrows():
        print(f"    {row['DQ_Dimension']:<15} {row['Rules_Count']:>2} rules | "
              f"{row['Avg_Pass_Rate']:>6.2f}% | {row['Total_Failed']:>4} failed")
    print("=" * 100)


if __name__ == "__main__":
    main()
