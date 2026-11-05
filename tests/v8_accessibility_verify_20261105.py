"""Phase 6 independent WCAG 2.0/2.1/2.2 AA and WebKit smoke.

Synthetic Flask evidence only. No production service, scanner, database, orders,
API keys, network feeds, or test-trade execution. axe-core is loaded locally
from a pinned CI npm development package, never an external runtime CDN.
"""
from __future__ import annotations

import json
import os
import sys
import threading
from pathlib import Path

from playwright.sync_api import sync_playwright
from werkzeug.serving import make_server

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import app as alpha
from test_v8_frontend_contract_20261105 import _sample_snapshot


def fixture_data():
    return alpha.dashboard_payload(
        _sample_snapshot(),
        test_engine={"spec_id": "ACCESSIBILITY_SYNTHETIC", "verdict": "NOT_PROVEN"},
        paper_lifecycle={},
    )


def audit_with_axe(page, label, axe_js):
    page.add_script_tag(path=str(axe_js))
    result = page.evaluate("""async () => {
        const r = await axe.run(document, {
            runOnly: {type: 'tag', values: [
                'wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa'
            ]}
        });
        return r.violations.map(v => ({
            id: v.id, impact: v.impact, description: v.description,
            affected: v.nodes.slice(0, 4).map(n => n.target)
        }));
    }""")
    if result:
        print("ACCESSIBILITY VIOLATIONS " + label + "\n" + json.dumps(result, indent=2), flush=True)
    assert not result, f"WCAG A/AA axe violations in {label}: {[v['id'] for v in result]}"
    print("PASS: WCAG A/AA axe-core", label, flush=True)


def main():
    axe_js = Path(os.environ.get("V8_AXE_CORE_PATH", "node_modules/axe-core/axe.min.js")).resolve()
    if not axe_js.is_file():
        raise RuntimeError("Pinned local axe-core file missing; accessibility cannot be declared passed")

    alpha.bounded_dashboard_payload = fixture_data
    server = make_server("127.0.0.1", 0, alpha.app, threaded=True)
    origin = f"http://127.0.0.1:{server.server_port}"
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        with sync_playwright() as p:
            for browser_name, widths in (("chromium", (390, 1280)), ("webkit", (390, 1280))):
                browser = getattr(p, browser_name).launch(headless=True)
                for width in widths:
                    page = browser.new_page(viewport={"width": width, "height": 860},
                                            device_scale_factor=1)
                    response = page.goto(origin, wait_until="networkidle", timeout=30000)
                    assert response.status == 200
                    assert page.locator("body.v8-body.v8-enhanced").count() == 1
                    dimensions = page.evaluate("""() => ({
                        inner: innerWidth, root: document.documentElement.scrollWidth,
                        body: document.body.scrollWidth
                    })""")
                    assert dimensions["root"] <= width + 1 and dimensions["body"] <= width + 1, (
                        f"{browser_name} {width}px horizontal overflow: {dimensions}"
                    )
                    audit_with_axe(page, f"{browser_name}-{width}-overview", axe_js)
                    nav = ".v8-bottom-nav" if width < 900 else ".v8-rail"
                    page.locator(f'{nav} [data-v8-tab="research"]').click()
                    assert page.locator("#v8-view-research").is_visible()
                    if width < 900:
                        page.locator(".v8-card-toggle").first.click()
                        assert page.locator(".v8-card-expanded").first.is_visible()
                    else:
                        page.locator(".v8-open-research").first.click()
                        assert page.locator("#v8-detail-panel").is_visible()
                    audit_with_axe(page, f"{browser_name}-{width}-research-detail", axe_js)
                    page.locator(f'{nav} [data-v8-tab="results"]').click()
                    audit_with_axe(page, f"{browser_name}-{width}-results", axe_js)
                    page.locator(f'{nav} [data-v8-tab="system"]').click()
                    audit_with_axe(page, f"{browser_name}-{width}-system", axe_js)
                    page.close()
                browser.close()
            print("PASS: Chromium + WebKit responsive navigation and WCAG A/AA at 390 and 1280px")
    finally:
        server.shutdown()


if __name__ == "__main__":
    main()
