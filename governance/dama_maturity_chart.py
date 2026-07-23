"""
=============================================================
Canadian Housing Data Governance Project (independent portfolio project)
Script: governance/dama_maturity_chart.py
Author: Ram Krishna Dhakal
Purpose: Render a radar (spider) chart of DAMA-DMBOK maturity,
         comparing Current vs Target scores across the scored
         knowledge areas. Reads governance/dama_alignment.csv so
         the chart always reflects the latest assessment.

         Output: governance/dama_maturity_chart.png
=============================================================
"""

import os
import sys
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

# Fix Windows console encoding so status symbols (✓, →) print safely.
sys.stdout.reconfigure(encoding="utf-8")

# ── HOW TO RUN ────────────────────────────────────────────────
# python governance/dama_maturity_chart.py

# ── PATHS (resolved relative to this script, so cwd doesn't matter) ──
HERE = os.path.dirname(os.path.abspath(__file__))
CSV  = os.path.join(HERE, "dama_alignment.csv")
OUT  = os.path.join(HERE, "dama_maturity_chart.png")

# ── Project colour palette (matches the Streamlit dashboard) ──
CMHC_DARK = "#1F4E79"
CMHC_MID  = "#2E75B6"


def wrap(label, width=16):
    """Wrap long axis labels onto multiple lines so they don't overlap."""
    words, lines, cur = label.split(), [], ""
    for w in words:
        if len(cur) + len(w) + 1 <= width:
            cur = (cur + " " + w).strip()
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return "\n".join(lines)


def main():
    df = pd.read_csv(CSV)

    # Keep only areas with a numeric maturity score (excludes N/A rows).
    df = df[pd.to_numeric(df["Current_Maturity"], errors="coerce").notna()].copy()
    df["Current_Maturity"] = df["Current_Maturity"].astype(int)
    df["Target_Maturity"]  = df["Target_Maturity"].astype(int)

    areas   = df["Knowledge_Area"].tolist()
    current = df["Current_Maturity"].tolist()
    target  = df["Target_Maturity"].tolist()

    # Radar geometry: one spoke per area, loop closed back to the start.
    n = len(areas)
    angles = np.linspace(0, 2 * np.pi, n, endpoint=False).tolist()
    current += current[:1]
    target  += target[:1]
    angles  += angles[:1]

    fig, ax = plt.subplots(figsize=(9, 9), subplot_kw=dict(polar=True))
    ax.set_theta_offset(np.pi / 2)   # start at the top
    ax.set_theta_direction(-1)       # go clockwise

    # Target polygon (dashed outline).
    ax.plot(angles, target, color=CMHC_DARK, linewidth=2, linestyle="--", label="Target maturity")
    ax.fill(angles, target, color=CMHC_DARK, alpha=0.08)

    # Current polygon (filled) — the visible gap between the two is the improvement needed.
    ax.plot(angles, current, color=CMHC_MID, linewidth=2, label="Current maturity")
    ax.fill(angles, current, color=CMHC_MID, alpha=0.25)

    # Area labels around the rim.
    ax.set_xticks(angles[:-1])
    ax.set_xticklabels([wrap(a) for a in areas], fontsize=9, color="#2c3e50")

    # Radial scale 1–5.
    ax.set_ylim(0, 5)
    ax.set_yticks([1, 2, 3, 4, 5])
    ax.set_yticklabels(["1", "2", "3", "4", "5"], fontsize=8, color="#888888")
    ax.set_rlabel_position(180 / n)

    ax.set_title("DAMA-DMBOK Maturity — Current vs Target",
                 fontsize=14, color=CMHC_DARK, fontweight="bold", pad=28)
    ax.legend(loc="upper right", bbox_to_anchor=(1.15, 1.10), fontsize=9, frameon=False)

    fig.text(0.5, 0.03,
             "Document & Content Management excluded (not applicable — structured tabular data).",
             ha="center", fontsize=8, color="#888888")

    fig.savefig(OUT, dpi=150, bbox_inches="tight")
    print(f"      ✓ Saved chart → {OUT}")


if __name__ == "__main__":
    main()
