"""
=============================================================
CMHC Housing Data Governance Project
Script: dq_engine.py
Author: Ram Krishna Dhakal
Purpose: Data Quality Rules Execution Engine
         Runs all 15 DQ rules against the CMHC housing dataset,
         flags failed records, writes exception files, and
         produces a clean remediated output dataset.
         Mirrors Informatica IDMC rule execution workflow.

         Rules coverage:
           Completeness  — DQ-001, DQ-003
           Validity       — DQ-002, DQ-004, DQ-005, DQ-006,
                            DQ-007, DQ-008, DQ-009, DQ-011, DQ-012
           Uniqueness     — DQ-010
           Accuracy       — DQ-013, DQ-014  (added v2)
           Consistency    — DQ-015          (added v2)
=============================================================
"""

import pandas as pd
import numpy as np
import os
from datetime import datetime

# ── HOW TO RUN ────────────────────────────────────────────────
# python dq_engine.py
# Output: data/processed/cmhc_housing_starts_remediated.csv
#         data/processed/dq_exceptions.csv
#         scorecard/dq_execution_scorecard.csv

# ── CONFIGURATION ─────────────────────────────────────────────────────────────
DATASET_PATH     = "data/raw/cmhc_housing_starts_2018_2023.csv"
PROCESSED_PATH   = "data/processed/cmhc_housing_starts_remediated.csv"
EXCEPTIONS_PATH  = "data/processed/dq_exceptions.csv"
SCORECARD_PATH   = "scorecard/dq_execution_scorecard.csv"

# Valid domain values (from data dictionary)
VALID_GEO_CODES  = {"ON","BC","AB","QC","MB","SK","NS","NB","NL","PE","NT","YT","NU"}
VALID_DWELLING   = {"Single-Detached","Semi-Detached","Row House",
                    "Apartment - 5+ storeys","Apartment - Under 5 storeys"}
VALID_MARKETS    = {"Homeowner","Rental","Condominium"}
VALID_STATUS     = {"","E","F","r"}

# Authoritative GEO name → GEO_CODE mapping (used by DQ-015)
GEO_MAPPING = {
    "Ontario": "ON",
    "British Columbia": "BC",
    "Alberta": "AB",
    "Quebec": "QC",
    "Manitoba": "MB",
    "Saskatchewan": "SK",
    "Nova Scotia": "NS",
    "New Brunswick": "NB",
    "Newfoundland and Labrador": "NL",
    "Prince Edward Island": "PE",
    "Northwest Territories": "NT",
    "Yukon": "YT",
    "Nunavut": "NU"
}


# ── STEP 1: LOAD DATA ─────────────────────────────────────────────────────────
def load_data(path):
    print(f"\n[1/6] Loading dataset...")
    df = pd.read_csv(path)
    df["_record_id"] = range(1, len(df) + 1)
    print(f"      ✓ {len(df):,} records loaded")
    return df


# ── STEP 2: DEFINE & RUN ALL 15 DQ RULES ─────────────────────────────────────
def run_dq_rules(df):
    print(f"\n[2/6] Executing 15 DQ rules...")
    total = len(df)
    results        = []   # rule-level summary
    all_exceptions = []   # record-level failures

    def run_rule(rule_id, name, dimension, cde, description, severity, mask, remediation):
        """Execute one rule, collect results and exceptions."""
        failed_df = df[mask].copy()
        failed    = len(failed_df)
        passed    = total - failed
        score     = round(passed / total * 100, 2)
        status    = "PASS" if score == 100 else ("WARN" if score >= 95 else "FAIL")

        icon = "✓" if status == "PASS" else "⚠"
        print(f"      {icon} {rule_id} | {name:<50} | {score:>7.2f}% | {failed:>5} failed | {status}")

        # Record-level exceptions
        if failed > 0:
            failed_df["_rule_id"]        = rule_id
            failed_df["_rule_name"]      = name
            failed_df["_dimension"]      = dimension
            failed_df["_cde"]            = cde
            failed_df["_severity"]       = severity
            failed_df["_failure_reason"] = description
            failed_df["_remediation"]    = remediation
            failed_df["_flagged_at"]     = datetime.now().strftime("%Y-%m-%d %H:%M")
            all_exceptions.append(failed_df)

        results.append({
            "Rule_ID": rule_id, "Rule_Name": name,
            "DQ_Dimension": dimension, "CDE_Affected": cde,
            "Description": description, "Severity": severity,
            "Total_Records": total, "Records_Passed": passed,
            "Records_Failed": failed, "Pass_Rate_Pct": score,
            "Status": status, "Remediation_Action": remediation
        })

    # ── DQ-001: HOUSING_STARTS completeness ───────────────────────────────────
    run_rule(
        "DQ-001", "Housing Starts Completeness",
        "Completeness", "HOUSING_STARTS",
        "HOUSING_STARTS must not be NULL.",
        "High",
        df["HOUSING_STARTS"].isnull(),
        "Escalate to Data Steward. Attempt back-fill from source permit system. If unavailable, flag STATUS='F'."
    )

    # ── DQ-002: HOUSING_STARTS non-negative ───────────────────────────────────
    run_rule(
        "DQ-002", "Housing Starts Non-Negative",
        "Validity", "HOUSING_STARTS",
        "HOUSING_STARTS must be >= 0. Negative values are physically impossible.",
        "Critical",
        df["HOUSING_STARTS"].fillna(0) < 0,
        "Root cause: manual data entry error in source permit system. Remediation: take absolute value and flag record for steward review."
    )

    # ── DQ-003: AVERAGE_PRICE_CAD completeness ────────────────────────────────
    run_rule(
        "DQ-003", "Average Price Completeness",
        "Completeness", "AVERAGE_PRICE_CAD",
        "AVERAGE_PRICE_CAD must not be NULL on non-suppressed records.",
        "Medium",
        df["AVERAGE_PRICE_CAD"].isnull() & (df["STATUS"].fillna("") != "F"),
        "Escalate to Data Steward. Re-run price survey aggregation for affected period/geography."
    )

    # ── DQ-004: AVERAGE_PRICE_CAD non-negative ────────────────────────────────
    run_rule(
        "DQ-004", "Average Price Non-Negative",
        "Validity", "AVERAGE_PRICE_CAD",
        "AVERAGE_PRICE_CAD must be > 0. Negative prices are invalid.",
        "Critical",
        df["AVERAGE_PRICE_CAD"].fillna(0) < 0,
        "Root cause: sign-flip error during CPI adjustment. Remediation: take absolute value and reprocess through price adjustment pipeline."
    )

    # ── DQ-005: AVERAGE_PRICE_CAD ceiling ─────────────────────────────────────
    run_rule(
        "DQ-005", "Average Price Ceiling Check",
        "Validity", "AVERAGE_PRICE_CAD",
        "AVERAGE_PRICE_CAD must not exceed $10,000,000.",
        "Medium",
        df["AVERAGE_PRICE_CAD"].fillna(0) > 10_000_000,
        "Escalate to Data Owner for manual review. Likely data entry error or unit mismatch."
    )

    # ── DQ-006: GEO_CODE referential integrity ────────────────────────────────
    run_rule(
        "DQ-006", "GEO_CODE Referential Integrity",
        "Validity", "GEO_CODE",
        "GEO_CODE must be a valid Canadian province/territory code.",
        "High",
        ~df["GEO_CODE"].isin(VALID_GEO_CODES),
        "Lookup correct GEO_CODE from Statistics Canada geographic reference table."
    )

    # ── DQ-007: DWELLING_TYPE domain validity ─────────────────────────────────
    run_rule(
        "DQ-007", "Dwelling Type Domain Validity",
        "Validity", "DWELLING_TYPE",
        "DWELLING_TYPE must be one of 5 approved categories.",
        "High",
        ~df["DWELLING_TYPE"].isin(VALID_DWELLING),
        "Map to nearest approved dwelling type using reference lookup table. Escalate if ambiguous."
    )

    # ── DQ-008: INTENDED_MARKET domain validity ───────────────────────────────
    run_rule(
        "DQ-008", "Intended Market Domain Validity",
        "Validity", "INTENDED_MARKET",
        "INTENDED_MARKET must be one of: Homeowner, Rental, Condominium.",
        "High",
        ~df["INTENDED_MARKET"].isin(VALID_MARKETS),
        "Map to approved value using permit application reference data."
    )

    # ── DQ-009: REF_DATE format ───────────────────────────────────────────────
    run_rule(
        "DQ-009", "Reference Date Format",
        "Validity", "REF_DATE",
        "REF_DATE must follow YYYY-MM format.",
        "Medium",
        ~df["REF_DATE"].astype(str).str.match(r"^\d{4}-\d{2}$"),
        "Reformat to YYYY-MM using date parsing. Reject if year or month is out of valid range."
    )

    # ── DQ-010: Grain uniqueness ──────────────────────────────────────────────
    grain = ["REF_DATE","GEO_CODE","DWELLING_TYPE","INTENDED_MARKET"]
    run_rule(
        "DQ-010", "Grain Uniqueness",
        "Uniqueness", "REF_DATE+GEO_CODE+DWELLING_TYPE+INTENDED_MARKET",
        "Each grain combination must be unique.",
        "High",
        df.duplicated(subset=grain, keep=False),
        "Identify source of duplicate load. Remove duplicate keeping most recent record. Investigate ETL pipeline."
    )

    # ── DQ-011: REF_DATE not future ───────────────────────────────────────────
    current_month = datetime.now().strftime("%Y-%m")
    run_rule(
        "DQ-011", "Reference Date Not Future",
        "Validity", "REF_DATE",
        "REF_DATE must not be after the current month.",
        "Medium",
        df["REF_DATE"].astype(str) > current_month,
        "Remove future-dated records. Investigate source system for clock/date errors."
    )

    # ── DQ-012: STATUS code validity ──────────────────────────────────────────
    run_rule(
        "DQ-012", "Status Code Validity",
        "Validity", "STATUS",
        "STATUS must be blank, 'E', 'F', or 'r'.",
        "Low",
        ~df["STATUS"].fillna("").isin(VALID_STATUS),
        "Map to nearest valid status code. Blank (final) is default."
    )

    # ── DQ-013: HOUSING_STARTS accuracy — statistical range ───────────────────
    # Flags values above 20,000 OR above mean + 3 std dev for the same province.
    # Z-score approach catches province-specific outliers that absolute thresholds miss.
    # Real execution result: 6 failures (99.94% pass rate)
    province_stats_hs = (
        df[df["HOUSING_STARTS"].notna()]
        .groupby("GEO_CODE")["HOUSING_STARTS"]
        .agg(["mean", "std"]).reset_index()
        .rename(columns={"mean": "hs_mean", "std": "hs_std"})
    )
    df_013 = df.merge(province_stats_hs, on="GEO_CODE", how="left")
    mask_013 = (
        (df_013["HOUSING_STARTS"] > 20000) |
        (df_013["HOUSING_STARTS"] > df_013["hs_mean"] + 3 * df_013["hs_std"])
    )
    # Realign index so mask matches df index inside run_rule
    mask_013 = mask_013.values
    run_rule(
        "DQ-013", "Housing Starts Accuracy — Statistical Range",
        "Accuracy", "HOUSING_STARTS",
        "HOUSING_STARTS must not exceed 20,000 or mean + 3 std dev for its province. Extreme outliers flagged for steward review.",
        "High",
        mask_013,
        "Escalate to Data Steward. Cross-reference with municipal permit office records to confirm or correct value."
    )

    # ── DQ-014: AVERAGE_PRICE_CAD accuracy — statistical range ────────────────
    # Flags prices outside $100K–$3M bounds OR above mean + 3 std dev per province.
    # Real execution result: 117 failures (98.92% pass rate) — all negative prices,
    # confirming overlap with DQ-004 and internal consistency of the rule set.
    province_stats_pr = (
        df[df["AVERAGE_PRICE_CAD"].notna()]
        .groupby("GEO_CODE")["AVERAGE_PRICE_CAD"]
        .agg(["mean", "std"]).reset_index()
        .rename(columns={"mean": "price_mean", "std": "price_std"})
    )
    df_014 = df.merge(province_stats_pr, on="GEO_CODE", how="left")
    mask_014 = (
        df_014["AVERAGE_PRICE_CAD"].notna() &
        (
            (df_014["AVERAGE_PRICE_CAD"] < 100_000) |
            (df_014["AVERAGE_PRICE_CAD"] > 3_000_000) |
            (df_014["AVERAGE_PRICE_CAD"] > df_014["price_mean"] + 3 * df_014["price_std"])
        )
    )
    mask_014 = mask_014.values
    run_rule(
        "DQ-014", "Average Price Accuracy — Statistical Range",
        "Accuracy", "AVERAGE_PRICE_CAD",
        "AVERAGE_PRICE_CAD must be between $100,000 and $3,000,000 and not exceed mean + 3 std dev for its province.",
        "High",
        mask_014,
        "Escalate to Data Steward. Verify against CMHC price survey raw data for the affected province and period."
    )

    # ── DQ-015: GEO and GEO_CODE consistency ──────────────────────────────────
    # Cross-validates that the full province name (GEO) and 2-letter code (GEO_CODE)
    # always refer to the same province.
    # Real execution result: 0 failures (100% pass rate) — data is fully consistent.
    df["_expected_code"] = df["GEO"].map(GEO_MAPPING)
    mask_015 = df["_expected_code"].notna() & (df["GEO_CODE"] != df["_expected_code"])
    df.drop(columns=["_expected_code"], inplace=True)
    run_rule(
        "DQ-015", "GEO and GEO_CODE Consistency",
        "Consistency", "GEO + GEO_CODE",
        "GEO (full province name) and GEO_CODE (2-letter code) must always refer to the same province. Any mismatch indicates a data entry or join error.",
        "Critical",
        mask_015,
        "Correct GEO_CODE using the authoritative GEO-to-GEO_CODE lookup table. Investigate source join logic."
    )

    df_results    = pd.DataFrame(results)
    df_exceptions = pd.concat(all_exceptions, ignore_index=True) if all_exceptions else pd.DataFrame()

    return df_results, df_exceptions


# ── STEP 3: ROOT CAUSE ANALYSIS ───────────────────────────────────────────────
def root_cause_analysis(df_exceptions):
    print(f"\n[3/6] Running root cause analysis...")

    if df_exceptions.empty:
        print("      ✓ No exceptions found.")
        return {}

    rca = {}

    # HOUSING_STARTS negative — breakdown by province
    neg_starts = df_exceptions[df_exceptions["_rule_id"] == "DQ-002"]
    if len(neg_starts) > 0:
        by_province = neg_starts.groupby("GEO_CODE").size().sort_values(ascending=False)
        rca["negative_starts_by_province"] = by_province.to_dict()
        top_prov = by_province.index[0]
        print(f"      ⚠ Negative HOUSING_STARTS: {len(neg_starts)} records. Most affected: {top_prov} ({by_province.iloc[0]} records)")

    # HOUSING_STARTS null — breakdown by year
    null_starts = df_exceptions[df_exceptions["_rule_id"] == "DQ-001"]
    if len(null_starts) > 0:
        null_starts = null_starts.copy()
        null_starts["_year"] = null_starts["REF_DATE"].astype(str).str[:4]
        by_year = null_starts.groupby("_year").size().sort_values(ascending=False)
        rca["null_starts_by_year"] = by_year.to_dict()
        print(f"      ⚠ NULL HOUSING_STARTS: {len(null_starts)} records across {len(by_year)} years")

    # AVERAGE_PRICE_CAD negative — breakdown by dwelling type
    neg_price = df_exceptions[df_exceptions["_rule_id"] == "DQ-004"]
    if len(neg_price) > 0:
        by_dwelling = neg_price.groupby("DWELLING_TYPE").size().sort_values(ascending=False)
        rca["negative_price_by_dwelling"] = by_dwelling.to_dict()
        print(f"      ⚠ Negative AVERAGE_PRICE_CAD: {len(neg_price)} records. Most affected: {by_dwelling.index[0]}")

    # HOUSING_STARTS accuracy outliers — breakdown by province (DQ-013)
    acc_starts = df_exceptions[df_exceptions["_rule_id"] == "DQ-013"]
    if len(acc_starts) > 0:
        by_province = acc_starts.groupby("GEO_CODE").size().sort_values(ascending=False)
        rca["accuracy_outliers_by_province"] = by_province.to_dict()
        print(f"      ⚠ HOUSING_STARTS accuracy outliers: {len(acc_starts)} records across {len(by_province)} province(s)")

    # AVERAGE_PRICE_CAD accuracy outliers — breakdown by province (DQ-014)
    acc_price = df_exceptions[df_exceptions["_rule_id"] == "DQ-014"]
    if len(acc_price) > 0:
        by_province = acc_price.groupby("GEO_CODE").size().sort_values(ascending=False)
        rca["price_accuracy_outliers_by_province"] = by_province.to_dict()
        print(f"      ⚠ AVERAGE_PRICE_CAD accuracy outliers: {len(acc_price)} records. Most affected: {by_province.index[0]}")

    return rca


# ── STEP 4: REMEDIATE DATA ────────────────────────────────────────────────────
def remediate_data(df, df_results):
    print(f"\n[4/6] Applying automated remediations...")
    df_clean   = df.copy()
    remediated = 0

    # Fix negative HOUSING_STARTS → take absolute value
    neg_mask = df_clean["HOUSING_STARTS"].fillna(0) < 0
    count = neg_mask.sum()
    df_clean.loc[neg_mask, "HOUSING_STARTS"] = df_clean.loc[neg_mask, "HOUSING_STARTS"].abs()
    df_clean.loc[neg_mask, "_dq_flag"] = "DQ-002: Negative value corrected to absolute"
    remediated += count
    print(f"      ✓ DQ-002: {count} negative HOUSING_STARTS corrected (abs value applied)")

    # Fix negative AVERAGE_PRICE_CAD → take absolute value
    neg_price = df_clean["AVERAGE_PRICE_CAD"].fillna(0) < 0
    count2 = neg_price.sum()
    df_clean.loc[neg_price, "AVERAGE_PRICE_CAD"] = df_clean.loc[neg_price, "AVERAGE_PRICE_CAD"].abs()
    df_clean.loc[neg_price, "_dq_flag"] = df_clean.loc[neg_price, "_dq_flag"].fillna("") + " | DQ-004: Negative price corrected"
    remediated += count2
    print(f"      ✓ DQ-004: {count2} negative AVERAGE_PRICE_CAD corrected (abs value applied)")

    # NULL HOUSING_STARTS → flag for steward, don't auto-fill
    null_mask = df_clean["HOUSING_STARTS"].isnull()
    df_clean.loc[null_mask, "_dq_flag"] = df_clean.loc[null_mask, "_dq_flag"].fillna("") + " | DQ-001: NULL flagged for steward review"
    print(f"      ⚠ DQ-001: {null_mask.sum()} NULL HOUSING_STARTS flagged for steward review (not auto-filled)")

    # NULL AVERAGE_PRICE_CAD → flag for steward
    null_price = df_clean["AVERAGE_PRICE_CAD"].isnull() & (df_clean["STATUS"].fillna("") != "F")
    df_clean.loc[null_price, "_dq_flag"] = df_clean.loc[null_price, "_dq_flag"].fillna("") + " | DQ-003: NULL price flagged for steward review"
    print(f"      ⚠ DQ-003: {null_price.sum()} NULL AVERAGE_PRICE_CAD flagged for steward review")

    # DQ-013 accuracy outliers → flag for steward review, do not auto-correct
    province_stats_hs = (
        df_clean[df_clean["HOUSING_STARTS"].notna()]
        .groupby("GEO_CODE")["HOUSING_STARTS"]
        .agg(["mean", "std"]).reset_index()
        .rename(columns={"mean": "hs_mean", "std": "hs_std"})
    )
    df_temp = df_clean.merge(province_stats_hs, on="GEO_CODE", how="left")
    acc_mask = (
        (df_temp["HOUSING_STARTS"] > 20000) |
        (df_temp["HOUSING_STARTS"] > df_temp["hs_mean"] + 3 * df_temp["hs_std"])
    ).values
    df_clean.loc[acc_mask, "_dq_flag"] = df_clean.loc[acc_mask, "_dq_flag"].fillna("") + " | DQ-013: Statistical outlier flagged for steward review"
    print(f"      ⚠ DQ-013: {acc_mask.sum()} HOUSING_STARTS accuracy outliers flagged (not auto-corrected)")

    # DQ-014 price accuracy outliers → flag for steward review, do not auto-correct
    province_stats_pr = (
        df_clean[df_clean["AVERAGE_PRICE_CAD"].notna()]
        .groupby("GEO_CODE")["AVERAGE_PRICE_CAD"]
        .agg(["mean", "std"]).reset_index()
        .rename(columns={"mean": "price_mean", "std": "price_std"})
    )
    df_temp2 = df_clean.merge(province_stats_pr, on="GEO_CODE", how="left")
    price_acc_mask = (
        df_temp2["AVERAGE_PRICE_CAD"].notna() &
        (
            (df_temp2["AVERAGE_PRICE_CAD"] < 100_000) |
            (df_temp2["AVERAGE_PRICE_CAD"] > 3_000_000) |
            (df_temp2["AVERAGE_PRICE_CAD"] > df_temp2["price_mean"] + 3 * df_temp2["price_std"])
        )
    ).values
    df_clean.loc[price_acc_mask, "_dq_flag"] = df_clean.loc[price_acc_mask, "_dq_flag"].fillna("") + " | DQ-014: Price accuracy outlier flagged for steward review"
    print(f"      ⚠ DQ-014: {price_acc_mask.sum()} AVERAGE_PRICE_CAD accuracy outliers flagged (not auto-corrected)")

    # Mark clean records
    df_clean["_dq_flag"] = df_clean["_dq_flag"].fillna("CLEAN")
    df_clean["_remediation_date"] = datetime.now().strftime("%Y-%m-%d")

    total_flagged = (df_clean["_dq_flag"] != "CLEAN").sum()
    print(f"\n      Summary: {remediated} records auto-remediated | {total_flagged} total records flagged")

    return df_clean


# ── STEP 5: BUILD SCORECARD ───────────────────────────────────────────────────
def build_scorecard(df_results, df_clean):
    print(f"\n[5/6] Building execution scorecard...")
    total = len(df_clean)

    by_dim = df_results.groupby("DQ_Dimension").agg(
        Rules=("Rule_ID","count"),
        Avg_Score=("Pass_Rate_Pct","mean"),
        Total_Failed=("Records_Failed","sum")
    ).reset_index()
    by_dim["Avg_Score"] = by_dim["Avg_Score"].round(2)

    overall  = round(df_results["Pass_Rate_Pct"].mean(), 2)
    passing  = (df_results["Status"] == "PASS").sum()
    warning  = (df_results["Status"] == "WARN").sum()
    failing  = (df_results["Status"] == "FAIL").sum()
    clean_records = (df_clean["_dq_flag"] == "CLEAN").sum()

    print(f"      ✓ Overall Score  : {overall}%")
    print(f"      ✓ Rules PASS     : {passing} | WARN: {warning} | FAIL: {failing}")
    print(f"      ✓ Clean records  : {clean_records:,} / {total:,} ({round(clean_records/total*100,2)}%)")

    return {
        "overall_score": overall,
        "passing": passing, "warning": warning, "failing": failing,
        "clean_records": clean_records, "total": total,
        "by_dim": by_dim
    }


# ── STEP 6: SAVE OUTPUTS ─────────────────────────────────────────────────────
def save_outputs(df_clean, df_results, df_exceptions, scorecard_stats):
    print(f"\n[6/6] Saving outputs...")
    os.makedirs("data/processed", exist_ok=True)
    os.makedirs("scorecard", exist_ok=True)
    os.makedirs("docs", exist_ok=True)

    # Drop internal helper columns for clean output
    export_cols = [c for c in df_clean.columns if not c.startswith("_")]
    df_clean[export_cols + ["_dq_flag","_remediation_date"]].to_csv(PROCESSED_PATH, index=False)
    print(f"      ✓ Remediated dataset  → {PROCESSED_PATH} ({len(df_clean):,} records)")

    if not df_exceptions.empty:
        df_exceptions.to_csv(EXCEPTIONS_PATH, index=False)
        print(f"      ✓ Exception log       → {EXCEPTIONS_PATH} ({len(df_exceptions):,} exception records)")

    df_results.to_csv(SCORECARD_PATH, index=False)
    print(f"      ✓ Execution scorecard → {SCORECARD_PATH}")

    # Auto-generate summary and by-dimension scorecards so they never go stale
    _total_r = len(df_clean)
    _passing  = int((df_results["Status"] == "PASS").sum())
    _warning  = int((df_results["Status"] == "WARN").sum())
    _failing  = int((df_results["Status"] == "FAIL").sum())
    _overall  = round(df_results["Pass_Rate_Pct"].mean(), 2)

    def _dim_score(dim):
        rows = df_results[df_results["DQ_Dimension"] == dim]["Pass_Rate_Pct"]
        return round(rows.mean(), 2) if len(rows) > 0 else None

    pd.DataFrame([{
        "Dataset": "cmhc_housing_starts_2018_2023",
        "Scorecard_Date": datetime.now().strftime("%Y-%m-%d"),
        "Total_Records": _total_r,
        "Total_DQ_Rules": len(df_results),
        "Rules_PASS": _passing, "Rules_WARN": _warning, "Rules_FAIL": _failing,
        "Total_Rule_Failures": int(df_results["Records_Failed"].sum()),
        "Overall_DQ_Score_Pct": _overall,
        "Overall_Grade": "A" if _overall >= 99 else ("B" if _overall >= 95 else "C"),
        "Completeness_Score": _dim_score("Completeness"),
        "Validity_Score": _dim_score("Validity"),
        "Uniqueness_Score": _dim_score("Uniqueness"),
        "Accuracy_Score": _dim_score("Accuracy"),
        "Consistency_Score": _dim_score("Consistency"),
        "Recommended_Action": (
            "Escalate DQ-001, DQ-002, DQ-003, DQ-004, DQ-013, DQ-014 to Data Steward. "
            "Root cause analysis required for negative values and statistical outliers."
        )
    }]).to_csv("scorecard/dq_scorecard_summary.csv", index=False)
    print(f"      ✓ Summary scorecard   → scorecard/dq_scorecard_summary.csv")

    _dim_rows = []
    for _dim, _grp in df_results.groupby("DQ_Dimension"):
        _avg = round(_grp["Pass_Rate_Pct"].mean(), 2)
        _dim_rows.append({
            "DQ_Dimension": _dim, "Rules_Count": len(_grp),
            "Avg_Pass_Rate": _avg, "Total_Failed": int(_grp["Records_Failed"].sum()),
            "Rules_Passing": int((_grp["Status"] == "PASS").sum()),
            "Rules_Warning": int((_grp["Status"] == "WARN").sum()),
            "Rules_Failing": int((_grp["Status"] == "FAIL").sum()),
            "Dimension_Score": _avg,
            "Dimension_Grade": "A" if _avg >= 99 else ("B" if _avg >= 95 else "C")
        })
    pd.DataFrame(_dim_rows).to_csv("scorecard/dq_scorecard_by_dimension.csv", index=False)
    print(f"      ✓ By-dimension scorecard → scorecard/dq_scorecard_by_dimension.csv")


# ── MAIN ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 65)
    print("  CMHC Housing DQ Rules Execution Engine  (v2 — 15 rules)")
    print("  Author: Ram Krishna Dhakal")
    print("=" * 65)

    df                        = load_data(DATASET_PATH)
    df_results, df_exceptions = run_dq_rules(df)
    rca                       = root_cause_analysis(df_exceptions)
    df_clean                  = remediate_data(df, df_results)
    scorecard_stats           = build_scorecard(df_results, df_clean)
    save_outputs(df_clean, df_results, df_exceptions, scorecard_stats)

    print("\n" + "=" * 65)
    print("  ✅ DQ Engine execution complete!")
    print(f"  Overall DQ Score  : {scorecard_stats['overall_score']}%")
    print(f"  Clean Records     : {scorecard_stats['clean_records']:,} / {scorecard_stats['total']:,}")
    print(f"  Exceptions logged : data/processed/dq_exceptions.csv")
    print(f"  Clean dataset     : data/processed/cmhc_housing_starts_remediated.csv")
    print(f"  Scorecard         : scorecard/dq_execution_scorecard.csv")
    print(f"  Dashboard         : streamlit run app.py")
    print("=" * 65)
