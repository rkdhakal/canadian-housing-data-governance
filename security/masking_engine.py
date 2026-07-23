"""
=============================================================
Canadian Housing Data Governance Project (independent portfolio project)
Script: security/masking_engine.py
Author: Ram Krishna Dhakal
Purpose: Classification-driven, role-based data masking engine.

         Reads three policy files and applies column-level access
         control to any dataframe:
           1. access_control_matrix.csv — role x tier -> ALLOW / MASK / DENY
           2. data_classification.csv   — column -> sensitivity tier
           3. masking_policy.csv        — column/tier -> masking method

         The engine references no column by name. All behaviour comes
         from configuration, so a new dataset is protected as soon as
         its columns are classified — no code change required.

         Masking methods: none | band | hash | redact | partial
=============================================================
"""

import os
import sys
import math
import hashlib
import pandas as pd
from datetime import datetime

# Fix Windows console encoding so status symbols print safely.
sys.stdout.reconfigure(encoding="utf-8")

# ── HOW TO RUN ────────────────────────────────────────────────
# python security/masking_engine.py

# ── PATHS (resolved relative to this file, so cwd doesn't matter) ──
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

ACCESS_MATRIX_PATH  = os.path.join(HERE, "access_control_matrix.csv")
CLASSIFICATION_PATH = os.path.join(HERE, "data_classification.csv")
MASKING_POLICY_PATH = os.path.join(HERE, "masking_policy.csv")
RAW_DATA_PATH       = os.path.join(ROOT, "data", "raw", "cmhc_housing_starts_2018_2023.csv")
SAMPLE_SENSITIVE_PATH = os.path.join(HERE, "sample_sensitive_records.csv")
AUDIT_LOG_PATH        = os.path.join(HERE, "access_audit_log.csv")

DEFAULT_DATASET  = "cmhc_housing_starts_2018_2023"
SAMPLE_DATASET   = "sample_sensitive_records"

# Identity recorded in the audit log. This demo has no authentication, so the
# ROLE is the meaningful signal. With real authentication (SSO/login) this
# becomes the authenticated username — no other change to the design.
DEFAULT_USER = "demo-session"

# Columns absent from data_classification.csv are treated as this tier.
# "Public" keeps derived/helper columns (e.g. _rule_id, _dimension) working;
# every unclassified column is reported back so the gap stays visible rather
# than silent. A stricter deployment can set this to "Internal" for
# secure-by-default behaviour.
UNCLASSIFIED_DEFAULT = "Public"

REDACT_TOKEN = "[RESTRICTED]"


# ── CONFIG LOADERS ────────────────────────────────────────────────────────────
def load_access_matrix():
    """Return {role: {tier: decision, ...}} from the access control matrix."""
    df = pd.read_csv(ACCESS_MATRIX_PATH)
    matrix = {}
    for _, row in df.iterrows():
        matrix[row["Role"]] = {
            "Public":           str(row["Public"]).strip().upper(),
            "Internal":         str(row["Internal"]).strip().upper(),
            "Confidential":     str(row["Confidential"]).strip().upper(),
            "Access_Tier":      row["Access_Tier"],
            "Export_Permitted": str(row["Export_Permitted"]).strip(),
        }
    return matrix


def load_classification(dataset):
    """Return {column: sensitivity_tier} for one dataset."""
    df = pd.read_csv(CLASSIFICATION_PATH)
    df = df[df["Dataset"] == dataset]
    return dict(zip(df["Column_Name"], df["Sensitivity_Tier"]))


def load_masking_policy():
    """Return the full masking policy table."""
    return pd.read_csv(MASKING_POLICY_PATH)


# ── POLICY RESOLUTION ─────────────────────────────────────────────────────────
def resolve_method(policy_df, dataset, column, tier):
    """
    Decide how to mask one column.

    Resolution order:
      1. Column-specific rule for this dataset
      2. Wildcard default for the sensitivity tier ('*', '*', tier)
      3. Fail-safe: redact
    """
    specific = policy_df[
        (policy_df["Dataset"] == dataset)
        & (policy_df["Column_Name"] == column)
        & (policy_df["Sensitivity_Tier"] == tier)
    ]
    if not specific.empty:
        row = specific.iloc[0]
        return row["Masking_Method"], row.get("Method_Parameter")

    default = policy_df[
        (policy_df["Dataset"] == "*")
        & (policy_df["Column_Name"] == "*")
        & (policy_df["Sensitivity_Tier"] == tier)
    ]
    if not default.empty:
        row = default.iloc[0]
        return row["Masking_Method"], row.get("Method_Parameter")

    return "redact", None


def _param_value(param, key):
    """Read a 'key=value' style parameter (e.g. 'band_width=100000')."""
    if param is None or (isinstance(param, float) and pd.isna(param)):
        return None
    text = str(param)
    if "=" in text:
        name, value = text.split("=", 1)
        return value.strip() if name.strip() == key else None
    return text.strip()


# ── MASKING METHODS ───────────────────────────────────────────────────────────
def mask_none(series, param):
    """Public data — returned unchanged."""
    return series


def mask_redact(series, param):
    """Replace every non-null value with a fixed token."""
    return series.apply(lambda v: v if pd.isna(v) else REDACT_TOKEN)


def mask_hash(series, param):
    """
    One-way SHA-256 hash, truncated (default 8 hex chars).

    Deterministic, so masked values can still be counted or joined.
    Note: unsalted by design for that reason — a production deployment
    handling real personal data should apply a salt or keyed hash.
    """
    length = 8
    text = "" if param is None or (isinstance(param, float) and pd.isna(param)) else str(param)
    if "_" in text and text.split("_")[-1].isdigit():
        length = int(text.split("_")[-1])
    return series.apply(
        lambda v: v if pd.isna(v)
        else hashlib.sha256(str(v).encode("utf-8")).hexdigest()[:length]
    )


def mask_band(series, param):
    """Round numeric values into a range, e.g. 743086.78 -> $700K-$800K."""
    width = 100_000
    raw = _param_value(param, "band_width")
    if raw is not None and str(raw).isdigit():
        width = int(raw)

    def to_band(value):
        if pd.isna(value):
            return value
        try:
            number = float(value)
        except (TypeError, ValueError):
            return REDACT_TOKEN
        low  = math.floor(number / width) * width
        high = low + width
        return f"${low / 1000:,.0f}K-${high / 1000:,.0f}K"

    return series.apply(to_band)


def mask_partial(series, param):
    """Show only a fragment, e.g. jane@example.ca -> j***@example.ca."""
    def to_partial(value):
        if pd.isna(value):
            return value
        text = str(value)
        if "@" in text:
            local, _, domain = text.partition("@")
            return f"{local[:1]}***@{domain}"
        if len(text) <= 2:
            return "***"
        return f"{text[:1]}***{text[-1:]}"

    return series.apply(to_partial)


METHODS = {
    "none":    mask_none,
    "redact":  mask_redact,
    "hash":    mask_hash,
    "band":    mask_band,
    "partial": mask_partial,
}


# ── AUDIT LOGGING ─────────────────────────────────────────────────────────────
AUDIT_COLUMNS = [
    "Timestamp", "User", "Role", "Action", "Dataset", "Rows_Returned",
    "Columns_Masked", "Columns_Denied", "Columns_Unclassified", "Export_Permitted",
]


def log_access(report, action="view", user=DEFAULT_USER):
    """
    Append one entry to the access audit log.

    The log is append-only: rows are added, never modified. The file header
    is written only when the log does not yet exist.

    Note: a CSV is the demonstration store. A production deployment would
    write to a database or append-only store (or stream to a SIEM), since a
    file on ephemeral hosting does not survive a restart.
    """
    entry = {
        "Timestamp":            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "User":                 user,
        "Role":                 report["role"],
        "Action":               action,
        "Dataset":              report["dataset"],
        "Rows_Returned":        report["rows"],
        "Columns_Masked":       "; ".join(report["columns_masked"]) or "none",
        "Columns_Denied":       "; ".join(report["columns_denied"]) or "none",
        "Columns_Unclassified": "; ".join(report["columns_unclassified"]) or "none",
        "Export_Permitted":     report["export_permitted"],
    }

    write_header = not os.path.exists(AUDIT_LOG_PATH)
    pd.DataFrame([entry], columns=AUDIT_COLUMNS).to_csv(
        AUDIT_LOG_PATH, mode="a", header=write_header, index=False
    )
    return entry


# ── MAIN API ──────────────────────────────────────────────────────────────────
def apply_masking(df, role, dataset=DEFAULT_DATASET,
                  action="view", user=DEFAULT_USER, audit=True):
    """
    Apply role-based masking to a dataframe.

    Returns (masked_dataframe, report) where report describes what the
    engine did.

    Auditing is on by default and happens inside this function, so masking
    and logging cannot be separated — every access is recorded by
    construction. Pass audit=False only for tests.
    """
    matrix = load_access_matrix()
    if role not in matrix:
        raise ValueError(f"Unknown role '{role}'. Known roles: {list(matrix)}")

    classification = load_classification(dataset)
    policy_df      = load_masking_policy()
    decisions      = matrix[role]

    out = df.copy()
    report = {
        "role": role,
        "dataset": dataset,
        "rows": len(out),
        "columns_allowed": [],
        "columns_masked": [],
        "columns_denied": [],
        "columns_unclassified": [],
        "export_permitted": decisions["Export_Permitted"],
    }

    for column in list(out.columns):
        tier = classification.get(column)
        if tier is None:
            tier = UNCLASSIFIED_DEFAULT
            report["columns_unclassified"].append(column)

        decision = decisions.get(tier, "MASK")

        if decision == "ALLOW":
            report["columns_allowed"].append(column)

        elif decision == "DENY":
            out.drop(columns=[column], inplace=True)
            report["columns_denied"].append(column)

        else:  # MASK
            method, param = resolve_method(policy_df, dataset, column, tier)
            func = METHODS.get(str(method).strip(), mask_redact)
            out[column] = func(out[column], param)
            report["columns_masked"].append(f"{column} ({method})")

    if audit:
        log_access(report, action=action, user=user)

    return out, report


# ── DEMONSTRATION ─────────────────────────────────────────────────────────────
def _demo(title, df, dataset, roles, note=""):
    """Print the same rows as seen by each role, for one dataset."""
    print("=" * 72)
    print(f"  {title}")
    if note:
        print(f"  {note}")
    print("=" * 72)

    for role in roles:
        masked, report = apply_masking(df, role, dataset=dataset)
        print("─" * 72)
        print(f"  Viewing as : {role}")
        print(f"  Masked     : {report['columns_masked'] or 'none'}")
        print(f"  Denied     : {report['columns_denied'] or 'none'}")
        print(f"  Export     : {report['export_permitted']}")
        print("─" * 72)
        print(masked.to_string(index=False))
        print()


if __name__ == "__main__":
    print("\n" + "=" * 72)
    print("  Data Masking Engine — role-based demonstration")
    print("  Author: Ram Krishna Dhakal")
    print("=" * 72 + "\n")

    roles = ["Data Owner", "Data Steward", "Data Custodian", "Data Consumer"]

    # ── Dataset 1: the housing dataset (Public columns + one Internal column) ──
    preview_cols = ["REF_DATE", "GEO_CODE", "DWELLING_TYPE",
                    "HOUSING_STARTS", "AVERAGE_PRICE_CAD"]
    housing = pd.read_csv(RAW_DATA_PATH).head(5)[preview_cols]
    _demo(
        "DATASET 1 — cmhc_housing_starts_2018_2023  (5 sample rows)",
        housing, DEFAULT_DATASET, roles,
        "AVERAGE_PRICE_CAD is classified Internal; all other columns are Public.",
    )

    # ── Dataset 2: synthetic fixture exercising the Confidential tier ──────────
    sensitive = pd.read_csv(SAMPLE_SENSITIVE_PATH)
    _demo(
        f"DATASET 2 — sample_sensitive_records  ({len(sensitive)} rows, showing 6)",
        sensitive.head(6), SAMPLE_DATASET, roles,
        "Synthetic fixture. APPLICANT_NAME/APPLICANT_EMAIL are Confidential (PII); "
        "ESTIMATED_VALUE_CAD is Internal.",
    )

    # ── The audit trail these accesses just produced ───────────────────────────
    if os.path.exists(AUDIT_LOG_PATH):
        log = pd.read_csv(AUDIT_LOG_PATH)
        shown = ["Timestamp", "Role", "Dataset", "Columns_Masked", "Columns_Denied"]
        print("=" * 72)
        print(f"  ACCESS AUDIT LOG — {len(log)} total entries (showing the last 8)")
        print(f"  Full detail: {os.path.basename(AUDIT_LOG_PATH)}")
        print("=" * 72)
        print(log[shown].tail(8).to_string(index=False))
        print()
