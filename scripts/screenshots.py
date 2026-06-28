"""Capture dashboard screenshots for the README using Playwright.

Assumes the app is already running (see module docstring in README) and
serving on the given base URL with demo data seeded.

    python -m scripts.screenshots --base-url http://localhost:5050
"""

from __future__ import annotations

import argparse
from pathlib import Path

from playwright.sync_api import sync_playwright

OUT_DIR = Path(__file__).resolve().parent.parent / "docs" / "screenshots"


def capture(base_url: str) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch()

        # --- Desktop dashboard --------------------------------------------
        page = browser.new_page(viewport={"width": 1280, "height": 900}, device_scale_factor=2)
        page.goto(base_url, wait_until="networkidle")
        page.wait_for_selector("#targets-body tr")
        page.wait_for_timeout(600)
        page.screenshot(path=OUT_DIR / "dashboard.png", full_page=True)
        print("saved dashboard.png")

        # --- Endpoint detail (latency chart) ------------------------------
        page.click("#targets-body tr:nth-child(4)")  # recommendations-api (slow)
        page.wait_for_selector("#detail-panel:not(.hidden)")
        page.wait_for_timeout(700)
        page.screenshot(path=OUT_DIR / "endpoint-detail.png", full_page=True)
        print("saved endpoint-detail.png")
        page.close()

        # --- Mobile view --------------------------------------------------
        mobile = browser.new_page(viewport={"width": 414, "height": 880}, device_scale_factor=2)
        mobile.goto(base_url, wait_until="networkidle")
        mobile.wait_for_selector("#targets-body tr")
        mobile.wait_for_timeout(600)
        mobile.screenshot(path=OUT_DIR / "dashboard-mobile.png", full_page=True)
        print("saved dashboard-mobile.png")

        browser.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://localhost:5050")
    args = parser.parse_args()
    capture(args.base_url)
