"""Real offline Chromium UI verification against the actual Flask HTML template.

Never uses Supabase, Bitget, secrets, cron or production deployment; an
in-memory synthetic snapshot is the only research fixture.
"""
from __future__ import annotations

import sys
import threading
from pathlib import Path

from playwright.sync_api import sync_playwright
from werkzeug.serving import make_server

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_v8_frontend_contract_20261105 import _sample_snapshot
import app as alpha


def fixture_data():
    return alpha.dashboard_payload(
        _sample_snapshot(),
        test_engine={"spec_id":"SYNTHETIC_BROWSER_TEST","verdict":"NOT_PROVEN",
                     "operational_status":"REVIEW_REQUIRED","completed_paper_trades":0},
        paper_lifecycle={},
    )


def assert_no_root_overflow(page, width: int):
    size = page.evaluate("""() => ({
      width: window.innerWidth,
      html: document.documentElement.scrollWidth,
      body: document.body.scrollWidth
    })""")
    assert size["html"] <= width + 1, f"root HTML overflow at {width}: {size}"
    assert size["body"] <= width + 1, f"root body overflow at {width}: {size}"


def main():
    alpha.bounded_dashboard_payload = fixture_data
    server = make_server("127.0.0.1", 0, alpha.app, threaded=True)
    origin = f"http://127.0.0.1:{server.server_port}"
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    verified = []
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            for width in (320, 375, 390, 430, 768, 1280, 1920):
                page = browser.new_page(viewport={"width":width,"height":860},
                                        device_scale_factor=1)
                errors = []
                page.on("pageerror", lambda err: errors.append(str(err)))
                response = page.goto(origin + "/", wait_until="networkidle", timeout=30000)
                assert response.status == 200
                assert page.locator("body.v8-body.v8-enhanced").count() == 1, f"V8 init failed at {width}"
                assert "Alpha Hunter V8" in page.title()
                assert_no_root_overflow(page,width)
                assert page.locator("#v8-view-overview").is_visible()
                assert page.locator("#v8-view-overview").get_by_text("Latest symbol evidence loaded").is_visible()
                assert page.locator('[id="runScanButton"]').count() == 0
                if width < 900:
                    nav = page.locator('.v8-bottom-nav [data-v8-tab="research"]')
                    assert nav.is_visible()
                else:
                    nav = page.locator('.v8-rail [data-v8-tab="research"]')
                    assert nav.is_visible()
                nav.click()
                assert page.locator("#v8-view-research").is_visible()
                assert page.locator(".v8-strategy-table tbody tr").count() >= 2
                if width < 900:
                    assert page.locator(".v8-mobile-card").count() >= 2
                    first = page.locator(".v8-mobile-card").first.locator(".v8-card-toggle")
                    assert first.get_attribute("aria-expanded") == "false"
                    first.click()
                    assert first.get_attribute("aria-expanded") == "true"
                    assert page.locator(".v8-mobile-card").first.get_by_text("Exact:",exact=False).count() >= 1
                    assert_no_root_overflow(page,width)
                else:
                    assert page.locator(".v8-strategy-table").is_visible()
                    visible_cols = page.locator(".v8-strategy-table thead th").evaluate_all(
                        "(cols) => cols.filter(c => getComputedStyle(c).display !== 'none').length"
                    )
                    assert visible_cols == 7, f"desktop table should show 7 columns at {width}, got {visible_cols}"
                    page.locator(".v8-strategy-table .v8-open-research").first.click()
                    assert page.locator("#v8-detail-panel").is_visible()
                    assert page.locator("#v8-detail-panel").get_by_text("Exact:",exact=False).count() >= 1
                search = page.locator("#v8-search")
                search.fill("BEAMUSDT")
                assert page.locator("#v8-result-count").get_attribute("role") == "status"
                assert page.locator("#v8-result-count").inner_text().startswith("1 research observation ·")
                if width < 900:
                    assert page.locator(".v8-mobile-card").count() == 1
                page.locator("#v8-reset").click()
                expected_total = page.locator(".v8-strategy-table tbody tr").count()
                assert page.locator("#v8-result-count").inner_text().startswith(
                    f"{expected_total} research " +
                    ("observation" if expected_total == 1 else "observations") + " ·"
                )
                target = (".v8-bottom-nav" if width < 900 else ".v8-rail")
                page.locator(f'{target} [data-v8-tab="results"]').click()
                assert page.locator("#v8-view-results").is_visible()
                assert page.get_by_text("Real-Time Profitability Test Engine").is_visible()
                page.locator(f'{target} [data-v8-tab="system"]').click()
                assert page.locator("#v8-view-system").is_visible()
                assert page.get_by_text("Safety Blocks").is_visible()
                assert page.locator("#v8-view-system").get_by_role("link",name="V14 Control Tower").count() == 1
                assert_no_root_overflow(page,width)
                assert not errors, f"JavaScript exceptions at {width}: {errors}"
                verified.append(width)
                page.close()
            browser.close()
        print("PASS: actual Flask V8 offline Chromium / seven responsive widths:", verified)
        print("PASS: desktop 7-column research, iPhone cards/detail, search/reset, 4 destinations")
        print("PASS: no document horizontal overflow, no JS errors, no scanner control")
    finally:
        server.shutdown()


if __name__ == "__main__":
    main()
