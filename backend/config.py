"""
Central configuration for the Cority ESBD Agent suite.

Everything that is environment- or website-specific lives here so the agents
themselves stay clean. If TX SmartBuy changes its markup, you only have to
adjust the SELECTORS block below — no agent code changes required.
"""
from __future__ import annotations

import os
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BACKEND_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BACKEND_DIR.parent
DATA_DIR = PROJECT_DIR / "data"
DOWNLOADS_DIR = DATA_DIR / "downloads"          # raw CSVs exported by Agent 1
OUTPUT_DIR = DATA_DIR / "output"                # the master Excel workbook
ATTACHMENTS_DIR = DATA_DIR / "attachments"      # files pulled by Agent 3
DEBUG_DIR = DATA_DIR / "debug"                  # screenshots / html on failure
FRONTEND_DIR = PROJECT_DIR / "frontend"
ASSETS_DIR = PROJECT_DIR / "assets"

for _d in (DOWNLOADS_DIR, OUTPUT_DIR, ATTACHMENTS_DIR, DEBUG_DIR):
    _d.mkdir(parents=True, exist_ok=True)

# The single Excel workbook that all three agents read/write.
MASTER_WORKBOOK = OUTPUT_DIR / "ESBD_Cority_Opportunities.xlsx"

SHEET_RAW = "1. Raw Search Results"
SHEET_OPPS = "2. ESHQ Opportunities"
SHEET_DETAILS = "3. RFP Details"

# ---------------------------------------------------------------------------
# Target website
# ---------------------------------------------------------------------------
BASE_URL = "https://www.txsmartbuy.gov"
ESBD_URL = f"{BASE_URL}/esbd"

# Headless by default. Flip to False (or set ESBD_HEADFUL=1) to watch it run –
# very useful the first time you point it at the live site.
HEADLESS = os.environ.get("ESBD_HEADFUL", "0") != "1"

# Generous timeouts — government sites can be slow.
NAV_TIMEOUT_MS = 60_000
ACTION_TIMEOUT_MS = 30_000
DOWNLOAD_TIMEOUT_MS = 120_000

# ---------------------------------------------------------------------------
# Selectors for the ESBD search form.
#
# These are written as *ordered fallback lists*: the agent tries each selector
# in turn and uses the first one that exists on the page. That makes the
# automation resilient to small markup changes. Labels were derived from the
# live ESBD search page; tweak here if the site is updated.
# ---------------------------------------------------------------------------
SELECTORS = {
    "keyword": [
        "#keyword",
        "input[name='keyword']",
        "input[placeholder*='Keyword' i]",
        "label:has-text('Keyword') >> xpath=following::input[1]",
    ],
    "solicitation_id": [
        "#solicitationId",
        "input[name='solicitationId']",
        "input[placeholder*='Solicitation' i]",
        "label:has-text('Solicitation ID') >> xpath=following::input[1]",
    ],
    "agency_name": [
        "select[name='agency']",
        "#agency",
        "label:has-text('Agency') >> xpath=following::select[1]",
    ],
    "status_select": [
        "select[name='status']",
        "#status",
    ],
    "start_date": [
        "#startDate",
        "input[name='startDate']",
        "input[placeholder*='Start' i]",
        "label:has-text('Start Date') >> xpath=following::input[1]",
    ],
    "end_date": [
        "#endDate",
        "input[name='endDate']",
        "input[placeholder*='End' i]",
        "label:has-text('End Date') >> xpath=following::input[1]",
    ],
    "search_btn": [
        "button:has-text('Search')",
        "input[type='submit'][value*='Search' i]",
        "a:has-text('Search')",
    ],
    "clear_btn": [
        "button:has-text('Clear Filters')",
        "button:has-text('Clear')",
    ],
    "export_csv_btn": [
        "button:has-text('Export to CSV')",
        "a:has-text('Export to CSV')",
        "button:has-text('Export')",
        "a:has-text('CSV')",
    ],
    # On the results list, the clickable solicitation title that opens detail
    # (detail pages live at /esbd/<id>).
    "result_title_link": [
        "a[href*='/esbd/']",
        "a.solicitation-title",
        "table a[href]",
    ],
    # Date-range preset control (This Week / This Month / Custom ...). Optional.
    "date_preset": [
        "select[name='dateRange']",
        "#dateRange",
    ],
    # Attachment links on a detail page carry the real URL in data-href.
    "attachment_link": [
        "a[data-action='downloadURL']",
        "a[data-href]",
    ],
    # The "Download PDF" summary button on a detail page.
    "download_pdf_btn": [
        "button[data-action='downloadPDF']",
        "button:has-text('Download PDF')",
    ],
    # The Attachments tab toggle on a detail page.
    "attachments_tab": [
        "a[data-target='#tab-1']",
        "a:has-text('Attachments')",
    ],
}

# Base host for the NetSuite media endpoint that serves attachment files.
DETAIL_URL_TEMPLATE = f"{ESBD_URL}/{{id}}"

# Status checkbox labels exactly as shown on the site.
STATUS_OPTIONS = ["Posted", "Awarded", "No Award", "Closed", "Posting Cancelled"]

# Date-preset choices exactly as shown on the site.
DATE_PRESETS = [
    "This Week", "This Month", "This Fiscal Year",
    "Last Week", "Last Month", "Last Fiscal Year", "Custom",
]
