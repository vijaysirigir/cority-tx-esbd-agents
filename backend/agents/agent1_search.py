"""
Agent 1 - ESBD Search & Export.

Drives the Texas SmartBuy / ESBD search page, applies whatever criteria the user
chose (keyword, solicitation ID, agency, status, date preset or custom start/end
dates), runs the search and clicks **Export to CSV**, capturing the download.

The exported CSV is saved to data/downloads and loaded verbatim into sheet 1 of
the master workbook so Agent 2 can review it.

Run standalone:
    echo '{"keyword":"safety software"}' | python agents/agent1_search.py --out r.json
"""
from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path

# allow `python agents/agent1_search.py` from the backend dir
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config
from agents import browser as b
from agents import excel_store


def run(params: dict) -> dict:
    keyword = (params.get("keyword") or "").strip()
    solicitation_id = (params.get("solicitation_id") or "").strip()
    agency = (params.get("agency") or "").strip()
    status = params.get("status") or ""
    date_preset = (params.get("date_preset") or "").strip()
    start_date = (params.get("start_date") or "").strip()
    end_date = (params.get("end_date") or "").strip()
    headful = bool(params.get("headful"))

    # ESBD status is a single-select; accept a list for convenience.
    if isinstance(status, list):
        status = status[0] if status else ""
    status = str(status).strip()

    result: dict = {"ok": False, "agent": "agent1", "params": params}

    b.log("Agent 1 - opening ESBD search page...")
    try:
        with b.browser_page(headful=headful) as page:
            page.goto(config.ESBD_URL, wait_until="domcontentloaded")
            b.log(f"  - loaded {config.ESBD_URL}")
            page.wait_for_timeout(1500)

            applied = []
            if keyword and b.safe_fill(page, "keyword", keyword):
                applied.append("keyword")
            if solicitation_id and b.safe_fill(page, "solicitation_id", solicitation_id):
                applied.append("solicitation_id")
            if agency:
                loc = b.first_locator(page, config.SELECTORS["agency_name"])
                if loc:
                    try:
                        loc.select_option(label=agency)
                        applied.append("agency")
                        b.log(f"  - agency = {agency}")
                    except Exception:
                        b.log(f"  - agency '{agency}' not selectable")
            if status and b.select_status(page, status):
                applied.append("status")
            if date_preset and date_preset.lower() != "custom":
                b.select_date_preset(page, date_preset)
                applied.append("date_preset")
            if start_date and b.safe_fill(page, "start_date", start_date):
                applied.append("start_date")
            if end_date and b.safe_fill(page, "end_date", end_date):
                applied.append("end_date")

            result["criteria_applied"] = applied
            b.log(f"  - criteria applied: {applied or '(none - full list)'}")

            b.log("Running search...")
            if not b.safe_click(page, "search_btn"):
                # maybe the form auto-searches; press Enter as a fallback
                try:
                    page.keyboard.press("Enter")
                except Exception:
                    pass
            page.wait_for_load_state("networkidle", timeout=config.NAV_TIMEOUT_MS)
            page.wait_for_timeout(2000)

            # --- Export to CSV ------------------------------------------------
            b.log("Exporting results to CSV...")
            csv_path = _export_csv(page)
            if not csv_path:
                dbg = b.dump_debug(page, "agent1_export_failed")
                result["error"] = (
                    "Could not trigger / capture the 'Export to CSV' download. "
                    "A debug screenshot + HTML were saved so the selector can be "
                    "adjusted in config.SELECTORS['export_csv_btn']."
                )
                result["debug"] = dbg
                return result

            b.log(f"  - CSV saved: {csv_path.name}")

            # --- Load into master workbook -----------------------------------
            wb, nrows, headers = excel_store.load_csv_into_raw_sheet(csv_path)
            b.log(f"  - loaded {nrows} rows into '{config.SHEET_RAW}'")

            _, preview_rows = excel_store.read_csv(csv_path)
            result.update(
                ok=True,
                csv_path=str(csv_path),
                workbook=str(wb),
                row_count=nrows,
                headers=headers,
                preview=preview_rows[:25],
            )
            return result

    except Exception as e:  # noqa: BLE001
        b.log(f"!! Agent 1 failed: {e}")
        result["error"] = str(e)
        return result


def _export_csv(page) -> Path | None:
    """Click Export to CSV and capture the download. Returns saved path or None."""
    loc = b.first_locator(page, config.SELECTORS["export_csv_btn"], timeout=8000)
    if not loc:
        return None
    ts = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    target = config.DOWNLOADS_DIR / f"esbd_export_{ts}.csv"
    try:
        with page.expect_download(timeout=config.DOWNLOAD_TIMEOUT_MS) as dl_info:
            loc.click()
        download = dl_info.value
        download.save_as(str(target))
        return target if target.exists() else None
    except Exception as e:  # noqa: BLE001
        b.log(f"  - export click/download issue: {e}")
        return None


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out")
    args = ap.parse_args()
    params = b.read_params_from_stdin()
    res = run(params)
    b.emit_result(res, args.out)
