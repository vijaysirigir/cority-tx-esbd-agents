"""
Agent 2 - ESHQ Opportunity Review.

Reads the CSV that Agent 1 downloaded (or the most recent one), scores every
solicitation against Cority's ESHQ product pillars (see cority_keywords.py),
keeps the relevant ones, and writes them - with fit score, matched solution
areas, matched keywords and a recommendation - into sheet 2 of the master
workbook.

Run standalone:
    echo '{"min_score":3}' | python agents/agent2_filter.py --out r.json
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config
from agents import browser as b  # only for log/emit helpers
from agents import cority_keywords as ck
from agents import excel_store

# Heuristics to locate common columns inside whatever the ESBD CSV gives us.
_AGENCY_HINTS = ["agency", "member name", "organization", "entity"]
_STATUS_HINTS = ["status"]
_DUE_HINTS = ["due", "close", "response date", "deadline"]
_POSTED_HINTS = ["posting", "posted", "issue date", "open date", "created"]


def _find_col(headers: list[str], hints: list[str]) -> str | None:
    for h in headers:
        hl = (h or "").lower()
        if any(hint in hl for hint in hints):
            return h
    return None


def _latest_csv() -> Path | None:
    csvs = sorted(config.DOWNLOADS_DIR.glob("*.csv"),
                  key=lambda p: p.stat().st_mtime, reverse=True)
    return csvs[0] if csvs else None


def run(params: dict) -> dict:
    min_score = int(params.get("min_score", 3))
    csv_path = params.get("csv_path")

    result: dict = {"ok": False, "agent": "agent2"}

    if csv_path:
        csv_path = Path(csv_path)
    else:
        csv_path = _latest_csv()

    if not csv_path or not Path(csv_path).exists():
        result["error"] = (
            "No source CSV found. Run Agent 1 first, or pass an explicit "
            "csv_path."
        )
        return result

    b.log(f"Agent 2 - reviewing {Path(csv_path).name}...")
    headers, rows = excel_store.read_csv(csv_path)
    b.log(f"  - {len(rows)} rows, {len(headers)} columns")

    agency_col = _find_col(headers, _AGENCY_HINTS)
    status_col = _find_col(headers, _STATUS_HINTS)
    due_col = _find_col(headers, _DUE_HINTS)
    posted_col = _find_col(headers, _POSTED_HINTS)

    out_headers = [
        "Cority Fit Score", "Solicitation ID", "Title", "Agency", "Status",
        "Due / Close Date", "Posted Date", "Solution Area(s)",
        "Matched Keywords", "Software Signal", "Recommendation",
    ]
    out_rows = []
    opportunities = []

    for row in rows:
        m = ck.score_row(row, min_score=min_score)
        if m.score < min_score:
            continue
        sid = ck.pick_id(row)
        title = ck.pick_title(row)
        agency = row.get(agency_col, "") if agency_col else ""
        status = row.get(status_col, "") if status_col else ""
        due = row.get(due_col, "") if due_col else ""
        posted = row.get(posted_col, "") if posted_col else ""

        out_rows.append([
            m.score, sid, title, agency, status, due, posted,
            ", ".join(m.pillars), ", ".join(m.keywords),
            "Yes" if m.software_signal else "No", m.recommendation,
        ])
        opportunities.append({
            "score": m.score, "solicitation_id": sid, "title": title,
            "agency": agency, "status": status, "due": due,
            "pillars": m.pillars, "keywords": m.keywords,
            "software": m.software_signal, "recommendation": m.recommendation,
        })

    # Best opportunities first.
    paired = sorted(zip(out_rows, opportunities),
                    key=lambda t: t[0][0], reverse=True)
    out_rows = [p[0] for p in paired]
    opportunities = [p[1] for p in paired]

    wb = excel_store.write_sheet(
        config.SHEET_OPPS, out_headers, out_rows, index=1,
        wide_cols=[3, 9, 11],  # Title, Matched Keywords, Recommendation
    )
    b.log(f"  - {len(out_rows)} ESHQ opportunities written to '{config.SHEET_OPPS}'")

    result.update(
        ok=True,
        workbook=str(wb),
        source_csv=str(csv_path),
        reviewed=len(rows),
        matched=len(out_rows),
        min_score=min_score,
        opportunities=opportunities,
    )
    return result


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out")
    args = ap.parse_args()
    params = b.read_params_from_stdin()
    res = run(params)
    b.emit_result(res, args.out)
