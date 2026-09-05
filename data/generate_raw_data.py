"""
Generates a reproducible "messy raw" version of the CMHC housing starts
dataset, so the DQ program has a genuine before -> after story instead of
scoring the same static CSV twice.

Builds a clean 10,800-row grid (72 months x 10 provinces x 5 dwelling types
x 3 markets), then injects realistic violations of the 15 DQ rules in
integration/rules/cmhc_housing_starts.yaml at controlled rates. Everything
is seeded, so re-running this script reproduces the exact same file.

Writes to a staging path (data/generated/), NOT the real raw CSV under
data/raw/ -- promoting a new raw file is a separate, deliberate decision.
"""

import numpy as np
import pandas as pd

SEED = 42
OUTPUT_PATH = "data/generated/cmhc_housing_starts_2018_2023_raw_v2.csv"

GEO_TO_CODE = {
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
}
DWELLING_TYPES = [
    "Single-Detached",
    "Semi-Detached",
    "Row House",
    "Apartment - 5+ storeys",
    "Apartment - Under 5 storeys",
]
INTENDED_MARKETS = ["Homeowner", "Rental", "Condominium"]
SURVEY_METHODS = ["Modelled Estimate", "Direct Survey", "Administrative Data"]
REF_DATES = pd.date_range("2018-01-01", "2023-12-01", freq="MS").strftime("%Y-%m").tolist()

# Per-province baseline distribution, modelled on the existing dataset's
# real (already-corrupted) mean/std -- gives new synthetic values the same
# realistic scale and spread per province.
HOUSING_STARTS_STATS = {
    "ON": (755, 305), "BC": (565, 243), "QC": (658, 296), "AB": (467, 236),
    "MB": (204, 160), "NB": (196, 159), "NL": (192, 157),
    "NS": (191, 154), "PE": (190, 156), "SK": (193, 152),
}
AVERAGE_PRICE_STATS = {
    "ON": (730122, 179048), "BC": (830413, 186352), "QC": (391623, 86166),
    "AB": (442396, 97133), "MB": (338482, 100292), "NB": (340844, 94934),
    "NL": (342833, 94749), "NS": (346249, 79399), "PE": (346516, 74235),
    "SK": (342090, 87148),
}

# Injection rates (moderate profile): fraction of rows given each violation.
# Shared columns (HOUSING_STARTS, AVERAGE_PRICE_CAD) budgets are drawn from
# disjoint pools so a row is null OR negative OR an outlier, never two at once.
RATES = {
    "housing_starts_null": 0.10,
    "housing_starts_negative": 0.08,
    "housing_starts_outlier": 0.04,
    "price_null": 0.10,
    "price_negative": 0.08,
    "price_ceiling": 0.03,
    "price_outlier": 0.04,
    "geo_code_invalid": 0.05,
    "dwelling_type_invalid": 0.05,
    "intended_market_invalid": 0.05,
    "ref_date_malformed": 0.06,
    "status_invalid": 0.05,
    "geo_mismatch": 0.05,
    "duplicate_grain": 0.03,
}


def build_clean_grid(rng: np.random.Generator) -> pd.DataFrame:
    rows = [
        {"REF_DATE": ref_date, "GEO": geo, "GEO_CODE": code,
         "DWELLING_TYPE": dwelling, "INTENDED_MARKET": market}
        for ref_date in REF_DATES
        for geo, code in GEO_TO_CODE.items()
        for dwelling in DWELLING_TYPES
        for market in INTENDED_MARKETS
    ]
    df = pd.DataFrame(rows)
    n = len(df)

    hs_mean = df["GEO_CODE"].map(lambda c: HOUSING_STARTS_STATS[c][0])
    hs_std = df["GEO_CODE"].map(lambda c: HOUSING_STARTS_STATS[c][1])
    df["HOUSING_STARTS"] = np.round(np.clip(rng.normal(hs_mean, hs_std), 5, 19000))

    price_mean = df["GEO_CODE"].map(lambda c: AVERAGE_PRICE_STATS[c][0])
    price_std = df["GEO_CODE"].map(lambda c: AVERAGE_PRICE_STATS[c][1])
    df["AVERAGE_PRICE_CAD"] = np.round(np.clip(rng.normal(price_mean, price_std), 100001, 1900000), 2)

    df["DATA_SOURCE"] = "CMHC Housing Market Survey"
    df["REPORTING_AGENCY"] = "Canada Mortgage and Housing Corporation"
    df["LAST_UPDATED"] = df["REF_DATE"] + "-15"
    df["SURVEY_METHOD"] = rng.choice(SURVEY_METHODS, size=n)
    df["GEOGRAPHY_TYPE"] = "Province/Territory"
    df["UOM"] = "Units"
    df["SCALAR_FACTOR"] = "units"
    # Same proportions as the original dataset: ~60% blank (final), ~20% F, ~20% E.
    df["STATUS"] = rng.choice(["", "F", "E"], size=n, p=[0.605, 0.198, 0.197])
    df["DECIMALS"] = 0

    return df


def pick_rows(rng: np.random.Generator, available: np.ndarray, rate: float, n_total: int) -> np.ndarray:
    """Randomly select rate * n_total row indices from the still-available pool."""
    k = int(round(rate * n_total))
    k = min(k, len(available))
    return rng.choice(available, size=k, replace=False)


def inject_errors(df: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    n = len(df)
    df = df.copy()

    # --- HOUSING_STARTS: null -> negative -> outlier, disjoint pools ---
    pool = np.arange(n)
    null_idx = pick_rows(rng, pool, RATES["housing_starts_null"], n)
    pool = np.setdiff1d(pool, null_idx)
    neg_idx = pick_rows(rng, pool, RATES["housing_starts_negative"], n)
    pool = np.setdiff1d(pool, neg_idx)
    outlier_idx = pick_rows(rng, pool, RATES["housing_starts_outlier"], n)

    df.loc[null_idx, "HOUSING_STARTS"] = np.nan
    df.loc[neg_idx, "HOUSING_STARTS"] = -df.loc[neg_idx, "HOUSING_STARTS"]
    df.loc[outlier_idx, "HOUSING_STARTS"] = rng.uniform(21000, 30000, size=len(outlier_idx)).round()

    # --- AVERAGE_PRICE_CAD: null (non-suppressed only) -> negative -> ceiling -> outlier ---
    eligible_for_null = df.index[df["STATUS"] != "F"].to_numpy()
    price_null_idx = pick_rows(rng, eligible_for_null, RATES["price_null"], n)

    pool = np.setdiff1d(np.arange(n), price_null_idx)
    price_neg_idx = pick_rows(rng, pool, RATES["price_negative"], n)
    pool = np.setdiff1d(pool, price_neg_idx)
    price_ceiling_idx = pick_rows(rng, pool, RATES["price_ceiling"], n)
    pool = np.setdiff1d(pool, price_ceiling_idx)
    price_outlier_idx = pick_rows(rng, pool, RATES["price_outlier"], n)

    df.loc[price_null_idx, "AVERAGE_PRICE_CAD"] = np.nan
    df.loc[price_neg_idx, "AVERAGE_PRICE_CAD"] = -df.loc[price_neg_idx, "AVERAGE_PRICE_CAD"]
    df.loc[price_ceiling_idx, "AVERAGE_PRICE_CAD"] = rng.uniform(2100000, 2900000, size=len(price_ceiling_idx)).round(2)
    # Below the province mean+3std but still inside [100k, 2M] is impossible to
    # target generically, so use hard_min breach instead: a real but implausibly
    # low price for the province (still fails DQ-014's $100,000 hard_min).
    df.loc[price_outlier_idx, "AVERAGE_PRICE_CAD"] = rng.uniform(20000, 95000, size=len(price_outlier_idx)).round(2)

    # --- Independent single-column violations ---
    geo_code_idx = pick_rows(rng, np.arange(n), RATES["geo_code_invalid"], n)
    df.loc[geo_code_idx, "GEO_CODE"] = rng.choice(["XX", "ONT", "on", "99"], size=len(geo_code_idx))

    dwelling_idx = pick_rows(rng, np.arange(n), RATES["dwelling_type_invalid"], n)
    df.loc[dwelling_idx, "DWELLING_TYPE"] = rng.choice(["Single Detached", "Townhouse", "Unknown"], size=len(dwelling_idx))

    market_idx = pick_rows(rng, np.arange(n), RATES["intended_market_invalid"], n)
    df.loc[market_idx, "INTENDED_MARKET"] = rng.choice(["homeowner", "Rent", "Co-op"], size=len(market_idx))

    ref_date_idx = pick_rows(rng, np.arange(n), RATES["ref_date_malformed"], n)
    df.loc[ref_date_idx, "REF_DATE"] = df.loc[ref_date_idx, "REF_DATE"].str.replace("-", "/", regex=False)

    status_idx = pick_rows(rng, np.arange(n), RATES["status_invalid"], n)
    df.loc[status_idx, "STATUS"] = rng.choice(["X", "Cancelled", "pending"], size=len(status_idx))

    # GEO_CODE changed to a *different valid* code so only DQ-015 fires, not DQ-006.
    mismatch_idx = pick_rows(rng, np.arange(n), RATES["geo_mismatch"], n)
    other_codes = list(GEO_TO_CODE.values())
    df.loc[mismatch_idx, "GEO_CODE"] = [
        rng.choice([c for c in other_codes if c != correct])
        for correct in df.loc[mismatch_idx, "GEO"].map(GEO_TO_CODE)
    ]

    # --- Duplicate grain keys: overwrite N rows with a copy of N other rows. ---
    # Row count stays 10,800: those grain combos now appear twice, and the
    # combos they used to hold are simply missing -- a realistic ETL bug.
    dup_targets = pick_rows(rng, np.arange(n), RATES["duplicate_grain"], n)
    remaining = np.setdiff1d(np.arange(n), dup_targets)
    dup_sources = rng.choice(remaining, size=len(dup_targets), replace=False)
    df.loc[dup_targets, :] = df.loc[dup_sources, :].to_numpy()

    return df


def main():
    rng = np.random.default_rng(SEED)
    df = build_clean_grid(rng)
    df = inject_errors(df, rng)

    column_order = [
        "REF_DATE", "GEO", "GEO_CODE", "DWELLING_TYPE", "INTENDED_MARKET",
        "HOUSING_STARTS", "AVERAGE_PRICE_CAD", "DATA_SOURCE", "REPORTING_AGENCY",
        "LAST_UPDATED", "SURVEY_METHOD", "GEOGRAPHY_TYPE", "UOM",
        "SCALAR_FACTOR", "STATUS", "DECIMALS",
    ]
    df = df[column_order]
    df.to_csv(OUTPUT_PATH, index=False)
    print(f"Wrote {len(df)} rows to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
