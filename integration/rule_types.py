"""
=============================================================
Canadian Housing Data Governance Project (independent portfolio project)
Script: integration/rule_types.py
Author: Ram Krishna Dhakal
Purpose: Reusable DQ rule-type library.

         Each rule type is implemented ONCE here, then reused by any
         source that declares it in its rules YAML. This is the "code"
         half of config-not-code: the config says WHAT to check, this
         file knows HOW to check it.

         Every check function has the same signature and contract:

             check_xxx(df, rule) -> boolean Series
                 True  = this row FAILED the rule
                 False = this row passed

         Rule types (7):
             not_null | range | domain | pattern | unique
             statistical_range | cross_field_consistency

         Nothing imports this file yet. dq_engine.py is unaffected and
         remains the authoritative engine until the runner (step 3) is
         built and proven to reproduce its results exactly.

How to run the self-test:
    python integration/rule_types.py
=============================================================
"""

import re
import sys
from datetime import datetime

import pandas as pd

# Streamlit replaces stdout, so guard the Windows console encoding fix
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


# ── RUN CONTEXT ───────────────────────────────────────────────────────────────
def build_context():
    """Values a rule can reference as ${placeholder}, resolved at run time."""
    return {"current_month": datetime.now().strftime("%Y-%m")}


def _resolve(value, context):
    """Substitute ${placeholder} against the run context; pass through others."""
    if isinstance(value, str) and value.startswith("${") and value.endswith("}"):
        key = value[2:-1]
        if key not in context:
            raise KeyError(f"Unknown placeholder '${{{key}}}' in rule config")
        return context[key]
    return value


def _apply_null_policy(mask, df, column, rule):
    """
    Honour the rule's declared `nulls` policy.

    nulls: ignore -> a null row can never fail this rule (a missing value is a
                     completeness problem, reported by the not_null rules)
    nulls: fail   -> a null row is a violation of this rule
    """
    policy = rule.get("nulls", "ignore")
    if policy == "ignore":
        return mask & df[column].notna()
    if policy == "fail":
        return mask | df[column].isna()
    raise ValueError(f"Rule {rule.get('id')}: unknown nulls policy '{policy}'")


# ── RULE TYPE 1: not_null ─────────────────────────────────────────────────────
def check_not_null(df, rule, context):
    """Fail rows where the column is NULL."""
    return df[rule["column"]].isna()


# ── RULE TYPE 2: range ────────────────────────────────────────────────────────
def check_range(df, rule, context):
    """
    Fail rows outside min / max. Either bound may be omitted.

    compare_as: string  -> lexical comparison (used by DQ-011, where REF_DATE
                           is a 'YYYY-MM' string compared against the current
                           month rather than a parsed date)
    """
    column = rule["column"]
    series = df[column].astype(str) if rule.get("compare_as") == "string" else df[column]

    mask = pd.Series(False, index=df.index)
    if "min" in rule:
        mask |= series < _resolve(rule["min"], context)
    if "max" in rule:
        mask |= series > _resolve(rule["max"], context)

    return _apply_null_policy(mask, df, column, rule)


# ── RULE TYPE 3: domain ───────────────────────────────────────────────────────
def check_domain(df, rule, context):
    """Fail rows whose value is not in the allowed list."""
    column = rule["column"]
    mask = ~df[column].isin(rule["allowed"])
    return _apply_null_policy(mask, df, column, rule)


# ── RULE TYPE 4: pattern ──────────────────────────────────────────────────────
def check_pattern(df, rule, context):
    """Fail rows whose value does not match the regex."""
    column = rule["column"]
    matched = df[column].astype(str).str.match(rule["regex"])
    mask = ~matched.fillna(False)
    return _apply_null_policy(mask, df, column, rule)


# ── RULE TYPE 5: unique ───────────────────────────────────────────────────────
def check_unique(df, rule, context):
    """
    Fail rows that duplicate a grain combination.

    flag_all: true -> report every member of a duplicate set (keep=False),
                      so a steward sees all copies, not just the extras.
    """
    keep = False if rule.get("flag_all", True) else "first"
    return df.duplicated(subset=rule["columns"], keep=keep)


# ── RULE TYPE 6: statistical_range ────────────────────────────────────────────
def check_statistical_range(df, rule, context):
    """
    Fail rows outside hard bounds OR above mean + N standard deviations,
    calculated within each group (e.g. per province).

    Grouping matters: a value that is normal for Ontario may be an extreme
    outlier for Prince Edward Island. A single global threshold cannot see that.
    """
    column   = rule["column"]
    group_by = rule["group_by"]
    stats    = df[df[column].notna()].groupby(group_by)[column].agg(["mean", "std"])

    upper = df[group_by].map(stats["mean"]) + rule["std_multiplier"] * df[group_by].map(stats["std"])

    mask = df[column] > upper
    if "hard_max" in rule:
        mask |= df[column] > rule["hard_max"]
    if "hard_min" in rule:
        mask |= df[column] < rule["hard_min"]

    return _apply_null_policy(mask, df, column, rule)


# ── RULE TYPE 7: cross_field_consistency ──────────────────────────────────────
def check_cross_field_consistency(df, rule, context):
    """
    Fail rows where two columns disagree, judged against an authoritative
    mapping (e.g. GEO 'Ontario' must always pair with GEO_CODE 'ON').

    unmapped: skip -> a source value absent from the mapping is not judged
    unmapped: fail -> a source value absent from the mapping is a violation
    """
    expected = df[rule["source_column"]].map(rule["mapping"])
    mask = expected.notna() & (df[rule["target_column"]] != expected)

    if rule.get("unmapped", "skip") == "fail":
        mask |= expected.isna()

    return mask


# ── TYPE REGISTRY ─────────────────────────────────────────────────────────────
# The lookup table that makes the config work: the runner reads `type` from
# the YAML and finds the implementation here. Adding an eighth rule type is
# one new function plus one new line below — no change to the runner.
RULE_TYPES = {
    "not_null":                check_not_null,
    "range":                   check_range,
    "domain":                  check_domain,
    "pattern":                 check_pattern,
    "unique":                  check_unique,
    "statistical_range":       check_statistical_range,
    "cross_field_consistency": check_cross_field_consistency,
}


# ── SINGLE ENTRY POINT ────────────────────────────────────────────────────────
def evaluate(df, rule, context=None):
    """
    Execute one declared rule and return a boolean Series (True = failed).

    Applies two things that are common to every rule type, so no individual
    check function has to care about them:
      1. the `where` scope filter (conditional rules, e.g. DQ-003)
      2. ${placeholder} resolution (dynamic bounds, e.g. DQ-011)
    """
    context   = context if context is not None else build_context()
    rule_type = rule["type"]

    if rule_type not in RULE_TYPES:
        raise ValueError(
            f"Rule {rule.get('id')}: unknown type '{rule_type}'. "
            f"Known types: {', '.join(sorted(RULE_TYPES))}"
        )

    mask = RULE_TYPES[rule_type](df, rule, context)

    # Conditional rules: only rows matching `where` are in scope
    if "where" in rule:
        in_scope = df.index.isin(df.query(rule["where"]).index)
        mask = mask & in_scope

    return mask.astype(bool)


# ── SELF-TEST ─────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 65)
    print("  Rule Type Library — self-test on 5 synthetic rows")
    print("=" * 65)

    df = pd.DataFrame({
        "REF_DATE":        ["2023-01", "2023-02", "2023-02", "9999-01", "2023-3"],
        "GEO_CODE":        ["ON",      "ON",      "ON",      "BC",      "XX"],
        "GEO":             ["Ontario", "Ontario", "Ontario", "Alberta", "Ontario"],
        "DWELLING_TYPE":   ["Row House"] * 5,
        "INTENDED_MARKET": ["Rental"] * 5,
        "STATUS":          ["",        "F",       "E",       "",        "Z"],
        "HOUSING_STARTS":  [100,       None,      -5,        120,       99999],
        "AVERAGE_PRICE_CAD": [500000,  None,      -200000,   600000,    550000],
    })

    print("\nTest data (5 rows, deliberately broken):")
    print(df.to_string(index=False))

    tests = [
        ("not_null (HOUSING_STARTS)",
         {"id": "T1", "type": "not_null", "column": "HOUSING_STARTS"},
         "row 2 is null"),

        ("not_null + where (price, skip STATUS='F')",
         {"id": "T2", "type": "not_null", "column": "AVERAGE_PRICE_CAD",
          "where": "STATUS != 'F'"},
         "row 2 is null BUT suppressed, so excluded -> 0 failures"),

        ("range (HOUSING_STARTS >= 0)",
         {"id": "T3", "type": "range", "column": "HOUSING_STARTS",
          "min": 0, "nulls": "ignore"},
         "row 3 is -5; null row ignored"),

        ("range (dynamic max = current month)",
         {"id": "T4", "type": "range", "column": "REF_DATE",
          "max": "${current_month}", "compare_as": "string", "nulls": "ignore"},
         "row 4 is 9999-01, in the future"),

        ("domain (GEO_CODE)",
         {"id": "T5", "type": "domain", "column": "GEO_CODE",
          "allowed": ["ON", "BC", "AB"], "nulls": "fail"},
         "row 5 is 'XX'"),

        ("domain (STATUS, blank allowed)",
         {"id": "T6", "type": "domain", "column": "STATUS",
          "allowed": ["", "E", "F", "r"], "nulls": "ignore"},
         "row 5 is 'Z'"),

        ("pattern (REF_DATE YYYY-MM)",
         {"id": "T7", "type": "pattern", "column": "REF_DATE",
          "regex": r"^\d{4}-\d{2}$", "nulls": "fail"},
         "row 5 is '2023-3', single-digit month"),

        ("unique (REF_DATE + GEO_CODE)",
         {"id": "T8", "type": "unique",
          "columns": ["REF_DATE", "GEO_CODE"], "flag_all": True},
         "rows 2 and 3 are both 2023-02 / ON -> both flagged"),

        ("statistical_range (HOUSING_STARTS per province)",
         {"id": "T9", "type": "statistical_range", "column": "HOUSING_STARTS",
          "group_by": "GEO_CODE", "std_multiplier": 3,
          "hard_max": 20000, "nulls": "ignore"},
         "row 5 is 99999, above the hard max"),

        ("cross_field_consistency (GEO vs GEO_CODE)",
         {"id": "T10", "type": "cross_field_consistency",
          "source_column": "GEO", "target_column": "GEO_CODE",
          "mapping": {"Ontario": "ON", "Alberta": "AB"}, "unmapped": "skip"},
         "row 4 says Alberta but code BC; row 5 says Ontario but code XX"),
    ]

    ctx = build_context()
    print(f"\nRun context: current_month = {ctx['current_month']}\n")

    for label, rule, expectation in tests:
        mask   = evaluate(df, rule, ctx)
        failed = [i + 1 for i in df.index[mask]]
        print(f"  {label}")
        print(f"    failed rows : {failed if failed else 'none'}")
        print(f"    expected    : {expectation}")
        print()

    # Unknown type must raise, not silently pass
    try:
        evaluate(df, {"id": "T11", "type": "made_up_type", "column": "GEO"}, ctx)
        print("  ✗ Unknown rule type was NOT rejected — this is a bug")
    except ValueError as e:
        print(f"  ✓ Unknown rule type correctly rejected:\n    {e}")

    print("\n" + "=" * 65)
    print(f"  All 7 rule types exercised. Registered types: {len(RULE_TYPES)}")
    print("=" * 65)
