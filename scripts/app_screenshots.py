"""Screenshots of the web app for the progress report (headless Chromium via Playwright).

    python scripts/app_screenshots.py --url http://127.0.0.1:8765 --project <id> --out docs/progress/img/m4_app
"""

from __future__ import annotations

import argparse
from pathlib import Path


def main() -> None:
    from playwright.sync_api import sync_playwright

    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True)
    ap.add_argument("--project", required=True)
    ap.add_argument("--out", default="docs/progress/img/m4_app")
    ap.add_argument("--width", type=int, default=1440)
    ap.add_argument("--height", type=int, default=900)
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    base, pid = a.url.rstrip("/"), a.project

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": a.width, "height": a.height}, device_scale_factor=1)

        def shot(name: str, full: bool = False) -> None:
            page.wait_for_timeout(600)
            page.screenshot(path=str(out / name), full_page=full)
            print("wrote", out / name)

        page.goto(f"{base}/#/")
        page.wait_for_selector(".prow")
        shot("01_projects.png")

        page.goto(f"{base}/#/p/{pid}/setup")
        page.wait_for_selector("#steps .step")
        shot("02_inputs.png")

        page.goto(f"{base}/#/p/{pid}/rules")
        page.wait_for_selector(".draft")
        page.click('.seg button[data-f="approved"]')
        page.wait_for_selector(".draft")
        shot("03_rules_review.png")
        page.click('.seg button[data-f="all"]')
        page.wait_for_selector(".draft")
        page.locator('.draft [data-a="edit"]').first.click()
        shot("04_rule_editor.png")

        page.goto(f"{base}/#/p/{pid}/results")
        page.wait_for_selector(".fcard")
        page.wait_for_timeout(1200)
        shot("05_results.png")

        page.locator(".fcard.v-FAIL").first.click()
        page.wait_for_timeout(900)
        shot("06_finding_selected.png")

        page.click('[data-l="review"]')
        page.wait_for_timeout(500)
        page.click('[data-z="fit"]')
        el = page.locator(".ov-el.door").first
        el.click(force=True)
        shot("07_review_elements.png")

        page.goto(f"{base}/api/projects/{pid}/files/report.html")
        page.wait_for_timeout(1500)
        shot("08_html_report.png")
        browser.close()


if __name__ == "__main__":
    main()
