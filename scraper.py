"""
ekantipur-scraper: Extract structured data from ekantipur.com using Playwright.
Output: output.json with title, image_url, category, author (UTF-8, Nepali-safe).
"""

import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout


# --- Browser & page setup ---
def create_browser_context(headless: bool = False):
    """Launch browser and return (playwright, browser, page). Caller must close browser."""
    playwright = sync_playwright().start()
    browser = playwright.chromium.launch(headless=headless)
    context = browser.new_context(
        locale="ne-NP",
        extra_http_headers={"Accept-Language": "ne-NP,ne;q=0.9,en;q=0.8"},
    )
    page = context.new_page()
    page.set_default_timeout(30_000)
    return playwright, browser, page


# --- JSON output structure ---
OUTPUT_FILE = Path(__file__).resolve().parent / "output.json"
OUTPUT_STRUCTURE = {
    "entertainment": [],   # list of {title, image_url, category, author}
    "cartoon_of_the_day": None,  # {title, image_url, category, author} or None
}


# =============================================================================
# Task 2: Entertainment News (मनोरञ्जन) — top 5 articles
# URL: https://ekantipur.com/entertainment
# Selectors: div.category (card), div.category h2 (title), div.category img,
#            div.category span.author (author, may be missing)
# =============================================================================
def scrape_entertainment(page) -> list[dict]:
    """Scrape top 5 entertainment (मनोरञ्जन) articles; append to output.json via main()."""
    results = []
    url = "https://ekantipur.com/entertainment"

    try:
        # Navigate to entertainment section
        page.goto(url, wait_until="domcontentloaded")
        # Wait for dynamic content: network idle then article cards
        page.wait_for_load_state("networkidle")
        page.wait_for_selector("div.category", timeout=15_000)
    except PlaywrightTimeout:
        print("Timeout loading entertainment page.", file=sys.stderr)
        return results
    except Exception as e:
        print(f"Error loading entertainment page: {e}", file=sys.stderr)
        return results

    # Top 5 article cards: each is div.category (title in h2, optional img, optional author)
    cards = page.locator("div.category")
    count = cards.count()
    for i in range(min(5, count)):
        card = cards.nth(i)
        try:
            # title → div.category h2 (use inner text or link title attribute)
            title_el = card.locator("h2").first
            title = ""
            if title_el.count() > 0:
                anchor = card.locator("h2 a").first
                if anchor.count() > 0:
                    title = (anchor.get_attribute("title") or anchor.inner_text() or "").strip()
                else:
                    title = (title_el.inner_text() or "").strip()

            # image_url → div.category img (null if no image)
            img_el = card.locator("img").first
            image_url = None
            if img_el.count() > 0:
                src = img_el.get_attribute("src")
                image_url = src if src else None

            # author → div.category span.author (null if missing)
            author_el = card.locator("span.author").first
            author = None
            if author_el.count() > 0:
                author = (author_el.inner_text() or "").strip() or None

            results.append({
                "title": title,
                "image_url": image_url,
                "category": "मनोरञ्जन",
                "author": author,
            })
        except Exception as e:
            print(f"Error parsing entertainment card {i}: {e}", file=sys.stderr)
            continue

    return results


# =============================================================================
# Task 3: Cartoon of the Day (कार्टुन)
# URL: https://ekantipur.com/cartoon
# Extract: title (img alt or caption), image_url (first real cartoon image, skip logos),
#          author (cartoonist name if available). Save/update output.json in main().
# =============================================================================
def scrape_cartoon_of_the_day(page) -> dict | None:
    """Scrape cartoon of the day from https://ekantipur.com/cartoon."""
    url = "https://ekantipur.com/cartoon"

    try:
        # Step 1: Navigate to cartoon page
        page.goto(url, wait_until="domcontentloaded")
        # Step 2: Wait for dynamic content — network idle then at least one img
        page.wait_for_load_state("networkidle")
        page.wait_for_selector("img", timeout=15_000)
    except PlaywrightTimeout:
        print("Timeout loading cartoon page.", file=sys.stderr)
        return None
    except Exception as e:
        print(f"Error loading cartoon page: {e}", file=sys.stderr)
        return None

    try:
        # Step 3: Find first real cartoon image (skip logos/icons by URL)
        def is_logo_or_icon(src: str) -> bool:
            lower = (src or "").lower()
            return "logo" in lower or "icon" in lower or "favicon" in lower

        # Prefer images inside main content (article, main, content area)
        for container_sel in ["article img", "main img", ".content-area img", "img"]:
            candidates = page.locator(container_sel)
            for i in range(candidates.count()):
                img = candidates.nth(i)
                src = img.get_attribute("src") or ""
                if not src or is_logo_or_icon(src):
                    continue
                try:
                    img.wait_for(state="visible", timeout=2_000)
                except PlaywrightTimeout:
                    continue
                cartoon_img = img
                image_url = src
                break
            else:
                continue
            break
        else:
            cartoon_img = None
            image_url = None

        if not cartoon_img or not image_url:
            print("No cartoon image found on page.", file=sys.stderr)
            return None

        # Step 4: title → img alt attribute OR caption text
        title = (
            cartoon_img.get_attribute("alt")
            or cartoon_img.get_attribute("title")
            or ""
        ).strip()
        if not title:
            # Look for caption: figcaption, .caption, .cartoon-caption, or nearby text
            caption_el = page.locator("figcaption, .caption, .cartoon-caption").first
            if caption_el.count() > 0:
                title = (caption_el.inner_text() or "").strip()
        if not title:
            title = "कार्टुन"

        # Step 5: author → cartoonist name if available (common selectors)
        author = None
        for sel in ["span.author", ".cartoonist", ".author-name", "figcaption"]:
            el = page.locator(sel).first
            if el.count() > 0:
                text = (el.inner_text() or "").strip()
                # Prefer short author-like text (cartoonist name, not full caption)
                if text and len(text) < 100 and text != title:
                    author = text
                    break

        return {
            "title": title,
            "image_url": image_url,
            "category": "कार्टुन",
            "author": author,
        }
    except Exception as e:
        print(f"Error extracting cartoon: {e}", file=sys.stderr)
        return None


def main() -> None:
    data = dict(OUTPUT_STRUCTURE)
    playwright = None
    browser = None

    try:
        playwright, browser, page = create_browser_context(headless=False)

        # Task 2: Entertainment News (मनोरञ्जन) — top 5 articles
        data["entertainment"] = scrape_entertainment(page)

        # Task 3: Cartoon of the Day (कार्टुन)
        data["cartoon_of_the_day"] = scrape_cartoon_of_the_day(page)

    except Exception as e:
        print(f"Scraper error: {e}", file=sys.stderr)
        raise
    finally:
        if browser:
            browser.close()
        if playwright:
            playwright.stop()

    # Save/update output.json — UTF-8 encoding, ensure_ascii=False for Nepali (e.g. कार्टुन)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"Saved to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
