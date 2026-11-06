"""Real offline Chromium UI verification against the actual Flask HTML template.

Never uses Supabase, Bitget, secrets, cron or production deployment; an
in-memory synthetic snapshot is the only research fixture.
"""
from __future__ import annotations

import sys
import threading
import os
from pathlib import Path

from playwright.sync_api import sync_playwright
from werkzeug.serving import make_server

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_v8_frontend_contract_20261105 import _sample_snapshot, _synthetic_actionable_rows, _synthetic_radar_rows
import app as alpha


def fixture_data():
    data = alpha.dashboard_payload(
        _sample_snapshot(),
        test_engine={"spec_id":"SYNTHETIC_BROWSER_TEST","verdict":"NOT_PROVEN",
                     "operational_status":"REVIEW_REQUIRED","completed_paper_trades":0},
        paper_lifecycle={},
    )
    data["actionable"] = _synthetic_actionable_rows()
    data["research"] = _synthetic_radar_rows()
    return data


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
    screenshot_dir = Path(os.getenv("V8_SCREENSHOT_DIR", "artifacts/v8-browser"))
    screenshot_dir.mkdir(parents=True, exist_ok=True)
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
                if width in (390, 1280):
                    page.screenshot(path=str(screenshot_dir / f"overview-{width}.png"),
                                    full_page=True)
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
                radar_cards = page.locator("#v8-view-research .v8-radar-card")
                radar_table = page.locator("#v8-view-research .v8-radar-table")
                assert radar_cards.count() == 2
                assert radar_table.locator("tbody tr").count() == 2
                if width < 900:
                    assert radar_cards.first.is_visible(), f"Radar mobile card absent at {width}"
                    assert not radar_table.is_visible(), f"Radar desktop table squeezed at {width}"
                    for card in radar_cards.all():
                        rect = card.bounding_box()
                        assert rect and rect["width"] >= 200
                        assert rect["x"] >= -1 and rect["x"] + rect["width"] <= width + 1, (
                            f"Radar card horizontal overflow at {width}: {rect}"
                        )
                    assert radar_cards.first.get_by_text("1.223688",exact=True).is_visible()
                    assert radar_cards.nth(1).get_by_text("0.24",exact=True).is_visible()
                    assert radar_cards.nth(1).locator(".v8-radar-card-state").inner_text() == "Direction Emerging Long"
                    assert radar_cards.nth(1).locator(".v8-radar-card-state").get_attribute("title") == (
                        "Research status code: DIRECTION_EMERGING_LONG"
                    )
                    assert radar_cards.nth(1).get_by_text("BEST RETEST / LIMIT ZONE",exact=True).is_visible()
                    rationale = radar_cards.first.locator(".v8-radar-reason")
                    assert rationale.locator("p").is_hidden()
                    rationale.locator("summary").click()
                    assert rationale.locator("p").is_visible()
                else:
                    assert radar_table.is_visible()
                    assert not radar_cards.first.is_visible()
                if width in (390, 1280):
                    page.screenshot(path=str(screenshot_dir / f"radar-{width}.png"),
                                    full_page=True)
                methodology = page.locator("#v8-view-research .v8-strategy-context")
                assert methodology.count() == 1
                assert methodology.get_attribute("open") is None
                assert methodology.locator("summary").is_visible()
                methodology.locator("summary").click()
                assert methodology.locator(".v8-strategy-context-body").is_visible()
                methodology.locator("summary").click()
                assert_no_root_overflow(page,width)
                if width in (390, 1280):
                    page.screenshot(path=str(screenshot_dir / f"research-{width}.png"),
                                    full_page=True)
                assert page.locator(".v8-strategy-table tbody tr").count() >= 2
                if width < 900:
                    assert page.locator(".v8-mobile-card").count() >= 2
                    first = page.locator(".v8-mobile-card").first.locator(".v8-card-toggle")
                    assert first.get_attribute("aria-expanded") == "false"
                    first.click()
                    assert first.get_attribute("aria-expanded") == "true"
                    if width == 390:
                        page.screenshot(path=str(screenshot_dir / "research-detail-390.png"),
                                        full_page=True)
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
                # Sorting changes presentation, not canonical evidence or prices.
                page.locator("#v8-reset").click()
                page.locator("#v8-sort").select_option("symbol")
                if width < 900:
                    sorted_symbols = page.locator(".v8-card-pair").all_inner_texts()
                    assert sorted_symbols == sorted(sorted_symbols), (
                        f"mobile symbol sort failed at {width}: {sorted_symbols}"
                    )
                else:
                    sorted_symbols = page.locator(".v8-strategy-table tbody tr td:first-child").all_inner_texts()
                    assert sorted_symbols == sorted(sorted_symbols), (
                        f"desktop symbol sort failed at {width}: {sorted_symbols}"
                    )
                page.locator("#v8-sort").select_option("rr")
                page.locator("#v8-sort").select_option("persistence")
                page.locator("#v8-reset").click()
                assert page.locator("#v8-sort").input_value() == "canonical"
                expected_total = page.locator(".v8-strategy-table tbody tr").count()
                assert page.locator("#v8-result-count").inner_text().startswith(
                    f"{expected_total} research " +
                    ("observation" if expected_total == 1 else "observations") + " ·"
                )
                target = (".v8-bottom-nav" if width < 900 else ".v8-rail")
                page.locator(f'{target} [data-v8-tab="results"]').click()
                assert page.locator("#v8-view-results").is_visible()
                assert page.get_by_text("Real-Time Profitability Test Engine").is_visible()
                assert page.locator(".top .v8-scan-time").count() == 1
                assert page.locator(".top .v8-scan-time").get_attribute("datetime")
                assert page.locator(".top .v8-scan-time").inner_text().endswith("UTC")
                status_value = page.locator(".v8-integrity-metric .v8-status-value")
                assert status_value.is_visible()
                assert status_value.inner_text() == "Review Required"
                assert status_value.get_attribute("title") == "Status code: REVIEW_REQUIRED"
                if width < 900:
                    bbox = status_value.bounding_box()
                    assert bbox and bbox["width"] >= 160, (
                        f"Unreadably narrow integrity status at {width}: {bbox}"
                    )
                cards = page.locator("#v8-view-results .v8-queue-card")
                table = page.locator("#v8-view-results .v8-queue-table")
                assert cards.count() == 2
                assert table.locator("tbody tr").count() == 2
                if width < 900:
                    assert cards.first.is_visible(), f"Mobile paper queue missing at {width}"
                    assert not table.is_visible(), f"Squeezed desktop queue exposed at {width}"
                    for card in cards.all():
                        rect = card.bounding_box()
                        assert rect is not None and rect["width"] >= 200
                        assert rect["x"] >= -1 and rect["x"] + rect["width"] <= width + 1, (
                            f"Paper queue card overflows {width}px: {rect}"
                        )
                    assert cards.first.get_by_text("0.10488", exact=True).is_visible()
                    assert cards.first.get_by_text("6.46", exact=True).is_visible()
                    assert cards.first.get_by_text("0.09%", exact=True).is_visible()
                    reason = cards.first.locator(".v8-queue-reason")
                    assert reason.locator("p").is_hidden()
                    reason.locator("summary").click()
                    assert reason.locator("p").is_visible()
                    assert "No order authority" in cards.first.inner_text()
                else:
                    assert table.is_visible(), f"Desktop table missing at {width}"
                    assert not cards.first.is_visible()
                    assert table.evaluate("(t)=>t.scrollWidth >= t.clientWidth")
                if width in (390, 768, 1280):
                    page.screenshot(
                        path=str(screenshot_dir / f"paper-queue-{width}.png"),
                        full_page=True,
                    )
                assert_no_root_overflow(page, width)
                page.locator(f'{target} [data-v8-tab="system"]').click()
                assert page.locator("#v8-view-system").is_visible()
                assert page.get_by_text("Safety Blocks").is_visible()
                assert page.locator("#v8-view-system").get_by_role("link",name="V14 Control Tower").count() == 1
                trust = page.locator("#v8-trust-title")
                assert trust.is_visible()
                assert "What Alpha Hunter does" in trust.inner_text()
                assert page.get_by_text("Real-money order authority is disabled.").is_visible()
                if width in (390, 1280):
                    page.screenshot(path=str(screenshot_dir / f"system-{width}.png"),
                                    full_page=True)
                page.evaluate("""() => history.replaceState(null, '', '?do_not_copy=synthetic_secret#v8-system')""")
                page.locator("#v8-copy-view-link").click()
                page.wait_for_function("""() => {
                  const s = document.querySelector('#v8-share-feedback')?.textContent || '';
                  return s.includes('copied') || s.includes('Select and copy');
                }""")
                feedback = page.locator("#v8-share-feedback").inner_text()
                assert "No credentials or research values included" in feedback
                fallback = page.locator("#v8-share-manual")
                if fallback.is_visible():
                    assert fallback.input_value() == origin + "/#v8-system"
                    assert "do_not_copy" not in fallback.input_value()
                assert_no_root_overflow(page,width)
                targets = page.evaluate("""() => {
                    const selectors = innerWidth < 900
                        ? [".v8-bottom-nav .v8-tab", ".v8-card-toggle"]
                        : [".v8-rail .v8-tab", ".v8-open-research"];
                    return [...document.querySelectorAll(selectors.join(","))]
                      .filter(e => e.getClientRects().length && getComputedStyle(e).visibility !== "hidden")
                      .slice(0, 12).map(e => ({name: e.textContent.trim().slice(0,30),
                        w: e.getBoundingClientRect().width, h: e.getBoundingClientRect().height}));
                }""")
                assert targets and all(t["w"] >= 44 and t["h"] >= 44 for t in targets), (
                    f"undersized interactive target at {width}: {targets}"
                )
                # The UI is intentionally read-only: there must not be
                # background Bitget, Supabase or private API calls.
                resources = page.evaluate("""() => performance.getEntriesByType('resource')
                    .map(e => e.name).filter(name => !name.startsWith(location.origin))""")
                assert not resources, f"unexpected external network resources: {resources}"
                assert not errors, f"JavaScript exceptions at {width}: {errors}"
                verified.append(width)
                page.close()
            browser.close()
        print("PASS: actual Flask V8 offline Chromium / seven responsive widths:", verified)
        print("PASS: desktop 7-column research, iPhone cards/detail, search/reset, 4 destinations")
        print("PASS: no document horizontal overflow, no JS errors, no scanner control")
        print("PASS: ≥44px key navigation/touch targets, no external resource fetches")
        print("PASS: research sorting, mobile expansion, accessible tabs, images:", screenshot_dir)
    finally:
        server.shutdown()


if __name__ == "__main__":
    main()
