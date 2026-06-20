"""
Agent 2 - Opportunity Qualification & Scoring.

Reads the CSV Agent 1 downloaded (or the most recent one) and runs the
multi-factor Cority Opportunity Scoring model (see scoring.py) on every
solicitation:

    Opportunity Score = Keyword(20%) + Semantic(30%) + Agency(15%)
                      + Technology(20%) + Budget(15%)

It keeps rows at/above the chosen minimum score, writes them - with all
sub-scores, recommended modules and a full executive summary - into sheet 2 of
the master workbook, and returns rich JSON so the UI can present each scored
opportunity with buttons to hand selected ones to Agent 3.

Run standalone:
    echo '{"min_score":60}' | python agents/agent2_filter.py --out r.json
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config
from agents import browser as b          # log / emit helpers
from agents import excel_store
from agents import scoring

OUT_HEADERS = [
    "Opportunity Score", "Action", "Solicitation ID", "Title", "Agency",
    "Due Date", "Keyword (20%)", "Semantic (30%)", "Agency Fit (15%)",
    "Tech Intent (20%)", "Budget (15%)", "Recommended Modules",
    "Why Cority Fits", "Executive Summary", "Source URL",
]
# 1-based columns that hold long free text (wrapped + widened in Excel).
WIDE_COLS = [4, 12, 13, 14]


def _latest_csv() -> Path | None:
    csvs = sorted(config.DOWNLOADS_DIR.glob("*.csv"),
                  key=lambda p: p.stat().st_mtime, reverse=True)
    return csvs[0] if csvs else None


def run(params: dict) -> dict:
    # Default threshold 60 = "Monitor and above" on the action scale.
    min_score = int(params.get("min_score", 60))
    csv_path = params.get("csv_path")
    csv_path = Path(csv_path) if csv_path else _latest_csv()

    result: dict = {"ok": False, "agent": "agent2"}
    if not csv_path or not Path(csv_path).exists():
        result["error"] = ("No source CSV found. Run Agent 1 first, or pass an "
                           "explicit csv_path.")
        return result

    b.log(f"Agent 2 - scoring {Path(csv_path).name} with the Cority "
          f"Opportunity model...")
    headers, rows = excel_store.read_csv(csv_path)
    b.log(f"  - {len(rows)} rows, {len(headers)} columns")

    analyses = [scoring.analyze(row) for row in rows]
    analyses.sort(key=lambda a: a.score, reverse=True)

    kept = [a for a in analyses if a.score >= min_score]
    archived = len(analyses) - len(kept)

    out_rows = [scoring.to_row(a) for a in kept]
    wb = excel_store.write_sheet(config.SHEET_OPPS, OUT_HEADERS, out_rows,
                                 index=1, wide_cols=WIDE_COLS)
    b.log(f"  - {len(kept)} opportunities >= {min_score} written to "
          f"'{config.SHEET_OPPS}' ({archived} archived below threshold)")

    # Tier counts for a quick read-out.
    tiers: dict[str, int] = {}
    for a in kept:
        tiers[a.action] = tiers.get(a.action, 0) + 1
    for action, n in tiers.items():
        b.log(f"      - {action}: {n}")

    result.update(
        ok=True,
        workbook=str(wb),
        source_csv=str(csv_path),
        reviewed=len(rows),
        matched=len(kept),
        archived=archived,
        min_score=min_score,
        tier_counts=tiers,
        opportunities=[scoring.to_json(a) for a in kept],
    )
    return result


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out")
    args = ap.parse_args()
    params = b.read_params_from_stdin()
    res = run(params)
    b.emit_result(res, args.out)
