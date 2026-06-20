"""
Small Playwright helper layer shared by Agent 1 (search/export) and Agent 3
(detail/attachments).

The guiding idea: government markup changes and is inconsistent, so every
interaction tries an *ordered list* of selectors and uses the first that works,
logs what it did, and dumps a screenshot + HTML on failure so problems are easy
to diagnose instead of silent.
"""
from __future__ import annotations

import datetime as dt
import sys
from contextlib import contextmanager
from pathlib import Path

from playwright.sync_api import (
    Locator,
    Page,
    TimeoutError as PWTimeout,
    sync_playwright,
)

import config


def log(msg: str) -> None:
    """Progress line - captured by the Flask runner for live status."""
    stamp = dt.datetime.now().strftime("%H:%M:%S")
    print(f"[{stamp}] {msg}", flush=True)


# Flags required to run Chromium inside a container (Docker/Render) and harmless
# locally: no sandbox (root user), and don't use the tiny /dev/shm (avoids crashes).
LAUNCH_ARGS = ["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"]


@contextmanager
def browser_page(headful: bool | None = None):
    """Yield a ready-to-use Page with downloads enabled."""
    headless = config.HEADLESS if headful is None else not headful
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=headless, args=LAUNCH_ARGS)
        # NOTE: do NOT override user_agent here. The ESBD attachment endpoint
        # (NetSuite media.nl) rejects malformed/non-standard UA strings, which
        # made direct attachment fetches fail. Playwright's default UA works.
        context = browser.new_context(
            accept_downloads=True,
            viewport={"width": 1500, "height": 950},
        )
        context.set_default_timeout(config.ACTION_TIMEOUT_MS)
        context.set_default_navigation_timeout(config.NAV_TIMEOUT_MS)
        page = context.new_page()
        try:
            yield page
        finally:
            context.close()
            browser.close()


def first_locator(page: Page, selectors: list[str], timeout: int = 4000) -> Locator | None:
    """Return the first selector (from the ordered list) that resolves to a
    visible element, else None."""
    for sel in selectors:
        try:
            loc = page.locator(sel).first
            loc.wait_for(state="visible", timeout=timeout)
            return loc
        except PWTimeout:
            continue
        except Exception:
            continue
    return None


def safe_fill(page: Page, key: str, value: str) -> bool:
    """Fill the field identified by config.SELECTORS[key]. Returns success."""
    if not value:
        return False
    loc = first_locator(page, config.SELECTORS.get(key, []))
    if not loc:
        log(f"  - field '{key}' not found - skipped")
        return False
    try:
        loc.click()
        loc.fill("")
        loc.fill(str(value))
        log(f"  - {key} = {value!r}")
        return True
    except Exception as e:  # noqa: BLE001
        log(f"  - could not fill '{key}': {e}")
        return False


def safe_click(page: Page, key: str, timeout: int = 8000) -> bool:
    loc = first_locator(page, config.SELECTORS.get(key, []), timeout=timeout)
    if not loc:
        log(f"  - button '{key}' not found")
        return False
    try:
        loc.click()
        return True
    except Exception as e:  # noqa: BLE001
        log(f"  - could not click '{key}': {e}")
        return False


def select_status(page: Page, status: str) -> bool:
    """Choose a value in the Status <select> (ESBD uses a single-select)."""
    if not status:
        return False
    loc = first_locator(page, config.SELECTORS.get("status_select", []))
    if not loc:
        log(f"  - status select not found - skipped")
        return False
    try:
        loc.select_option(label=status)
        log(f"  - status = {status}")
        return True
    except Exception as e:  # noqa: BLE001
        log(f"  - could not select status '{status}': {e}")
        return False


def select_date_preset(page: Page, preset: str) -> None:
    if not preset:
        return
    loc = first_locator(page, config.SELECTORS.get("date_preset", []))
    if loc:
        try:
            loc.select_option(label=preset)
            log(f"  - date preset = {preset}")
            return
        except Exception:
            pass
    # Fallback: a button / radio with that text
    try:
        page.get_by_text(preset, exact=True).first.click(timeout=2000)
        log(f"  - date preset (text) = {preset}")
    except Exception:
        log(f"  - date preset '{preset}' not applied")


def dump_debug(page: Page, tag: str) -> str:
    """Save a screenshot + HTML snapshot; return the screenshot path as string."""
    ts = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    base = config.DEBUG_DIR / f"{tag}_{ts}"
    shot = base.with_suffix(".png")
    html = base.with_suffix(".html")
    try:
        page.screenshot(path=str(shot), full_page=True)
    except Exception:
        shot = Path("")
    try:
        html.write_text(page.content(), encoding="utf-8")
    except Exception:
        pass
    log(f"  - debug saved: {shot.name}")
    return str(shot)


def read_params_from_stdin() -> dict:
    """CLI entry helper - agents are launched as subprocesses with JSON on stdin."""
    import json
    raw = sys.stdin.read().strip()
    return json.loads(raw) if raw else {}


def emit_result(result: dict, out_path: str | None) -> None:
    """Write the final JSON result to --out (so logs on stdout stay clean)."""
    import json
    if out_path:
        Path(out_path).write_text(json.dumps(result, default=str, indent=2),
                                  encoding="utf-8")
    print("RESULT_JSON_BELOW", flush=True)
    print(json.dumps(result, default=str), flush=True)
