# Cority ESBD Opportunity Engine

Three coordinated AI agents that mine the **Texas SmartBuy / Electronic State
Business Daily (ESBD)** for procurement opportunities that fit **Cority's
EHS+ (Environment, Safety, Health, Quality + Sustainability/ESG)** solutions —
wrapped in a Cority-branded web app and writing everything into **one Excel
workbook with three sheets**.

```
 ┌── Agent 1 ──────────┐   ┌── Agent 2 ──────────┐   ┌── Agent 3 ──────────┐
 │ Search ESBD with    │   │ Review the CSV,     │   │ Open each RFP, pull │
 │ your criteria and   │ → │ score ESHQ fit,     │ → │ full details + all  │
 │ Export to CSV       │   │ flag opportunities  │   │ attachments         │
 └─────────────────────┘   └─────────────────────┘   └─────────────────────┘
   sheet 1: Raw Results     sheet 2: ESHQ Opps        sheet 3: RFP Details
```

---

## What each agent does

**Agent 1 — Search & Export**
Drives `txsmartbuy.gov/esbd` in a real browser. You choose how to search from a
dropdown — **Keyword, Solicitation ID, Status, Date Range (preset), or custom
Start/End dates** (or combine everything in *Advanced*) — it runs the search,
clicks **Export to CSV**, captures the download, and loads it into **sheet 1**.

**Agent 2 — ESHQ Qualification**
Reads the downloaded CSV and scores every solicitation against Cority's product
pillars (Environment, Safety, Health, Quality, Sustainability/ESG,
Compliance/Risk). It keeps the fits and writes them — with a **fit score**,
**matched solution areas**, **matched keywords**, a **software signal** and a
**recommendation** — into **sheet 2**. Fully offline & deterministic; tune the
keywords in `backend/agents/cority_keywords.py`.

**Agent 3 — RFP Detail & Attachments**
For each solicitation (from Agent 2, or IDs you paste in) it opens the RFP detail
page, extracts every field (status, dates, contact, description, etc.) and
**downloads all attachments** into `data/attachments/<id>/`, writing one row per
RFP into **sheet 3**.

---

## Setup (Windows, one time)

You need Python 3.11+ (3.14 is fine). From a terminal in this folder:

```powershell
cd backend
python -m pip install -r requirements.txt
python -m playwright install chromium
```

## Run

Double-click **`start.bat`**, or:

```powershell
cd backend
python app.py
```

Then open **http://127.0.0.1:5000** and run the agents 1 → 2 → 3.
Tick **“Watch browser”** (top right) the first time to see the automation drive
the site live.

The master workbook is written to:
`data/output/ESBD_Cority_Opportunities.xlsx`
(downloadable from the app, or open it directly).

---

## Project layout

```
cority-esbd-agents/
├─ start.bat                  ← launcher
├─ backend/
│  ├─ app.py                  ← Flask server + agent orchestration (subprocesses)
│  ├─ config.py               ← paths, URLs, and ALL website selectors
│  ├─ requirements.txt
│  └─ agents/
│     ├─ agent1_search.py     ← search + Export to CSV
│     ├─ agent2_filter.py     ← ESHQ scoring → sheet 2
│     ├─ agent3_details.py    ← detail + attachments → sheet 3
│     ├─ cority_keywords.py   ← Cority ESHQ relevance engine (tune me)
│     ├─ browser.py           ← shared Playwright helpers
│     └─ excel_store.py       ← the one workbook, three sheets
├─ frontend/
│  └─ index.html              ← Cority-branded UI (single file)
├─ assets/                    ← Cority logo + brand reference
└─ data/
   ├─ downloads/  output/  attachments/  debug/
```

---

## If the site changes

ESBD markup occasionally changes. Every selector lives in **one place** —
`backend/config.py` → `SELECTORS`. Each entry is an ordered fallback list, so the
agents try several options before failing. On any failure the agent saves a
screenshot + HTML snapshot to `data/debug/` so you can see exactly what the page
looked like and adjust the selector.

## Notes
- Agents run as isolated subprocesses, so a stuck browser never takes down the UI,
  and the live log streams into the app while each agent runs.
- CSV export on ESBD is capped at 20,000 rows by the site itself.
- Attachments hosted on external portals (e.g. OpenGov) are captured as URLs in
  the RFP detail fields rather than downloaded.
