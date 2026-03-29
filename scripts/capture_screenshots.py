#!/usr/bin/env python3
"""Capture screenshots from a running web application for PRD documentation."""

import asyncio
import argparse
import json
from pathlib import Path
from urllib.parse import urljoin


async def capture_screenshots(base_url: str, output_dir: str, routes: list = None,
                              width: int = 1920, height: int = 1080, wait: int = 2000):
    """Capture screenshots from a web application."""
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        print("Error: Install playwright: pip install playwright && playwright install")
        return {}

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    screenshots = {}
    visited = set()
    routes = routes or ['/']

    async with await async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={'width': width, 'height': height})

        for route in routes:
            if route in visited:
                continue
            visited.add(route)
            url = urljoin(base_url, route)

            try:
                print(f"Capturing: {url}")
                await page.goto(url, wait_until='networkidle', timeout=30000)
                await page.wait_for_timeout(wait)

                safe_name = route.strip('/').replace('/', '-') or 'home'
                filepath = output_path / f"{safe_name}.png"
                await page.screenshot(path=str(filepath), full_page=True)
                screenshots[route] = str(filepath)
            except Exception as e:
                print(f"Failed {route}: {e}")

        await browser.close()

    with open(output_path / 'screenshots.json', 'w') as f:
        json.dump(screenshots, f, indent=2)

    print(f"\nCaptured {len(screenshots)} screenshots to {output_dir}")
    return screenshots


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Capture screenshots for PRD')
    parser.add_argument('--url', required=True, help='Base URL')
    parser.add_argument('--output', default='./screenshots', help='Output directory')
    parser.add_argument('--routes', nargs='*', default=['/'], help='Routes to capture')
    args = parser.parse_args()

    asyncio.run(capture_screenshots(args.url, args.output, args.routes))
