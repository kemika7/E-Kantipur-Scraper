"""
ekantipur-scraper: Extract structured data from ekantipur.com using Playwright.
Output: output.json with title, image_url, category, author (UTF-8, Nepali-safe).

DEBUGGING GUIDE
───────────────
Run with DEBUG=True to enable all debugging features:
  - Screenshot capture at key steps  →  screenshots/ folder
  - HTML structure logging           →  printed to stdout
  - Element count verification       →  printed to stdout
  - page.pause() breakpoints         →  opens Playwright Inspector (headless must be False)

Set DEBUG=False (and PAUSE=False) for a clean production run.

Playwright docs used:
  - page.goto()              → https://playwright.dev/python/docs/api/class-page#page-goto
  - page.wait_for_selector() → https://playwright.dev/python/docs/api/class-page#page-wait-for-selector
  - page.wait_for_load_state()→ https://playwright.dev/python/docs/api/class-page#page-wait-for-load-state
  - page.query_selector()    → https://playwright.dev/python/docs/api/class-page#page-query-selector
  - page.query_selector_all()→ https://playwright.dev/python/docs/api/class-page#page-query-selector-all
  - page.pause()             → https://playwright.dev/python/docs/api/class-page#page-pause
  - page.screenshot()        → https://playwright.dev/python/docs/api/class-page#page-screenshot
  - locator.count()          → https://playwright.dev/python/docs/api/class-locator#locator-count
  - locator.inner_html()     → https://playwright.dev/python/docs/api/class-locator#locator-inner-html
"""

import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

# ─────────────────────────────────────────────
# DEBUG FLAGS  (set to False for production run)
# ─────────────────────────────────────────────
DEBUG = True   # Master switch: enables screenshot capture, HTML logging, count checks
PAUSE = False  # Set to True to open Playwright Inspector at breakpoints (needs headless=False)

# Directory where debug screenshots are saved
SCREENSHOT_DIR = Path(__file__).resolve().parent / "screenshots"


# ─────────────────────────────────────────────
# Debugging helpers
# ─────────────────────────────────────────────

def debug_log(msg: str) -> None:
    """
    Print a debug message to stdout only when DEBUG is enabled.
    Uses UTF-8 encoding so Nepali text (e.g. मनोरञ्जन) prints correctly on all platforms.
    """
    if DEBUG:
        # sys.stdout.reconfigure ensures Nepali characters are never mangled
        sys.stdout.reconfigure(encoding="utf-8")
        print(f"[DEBUG] {msg}")


def take_screenshot(page, name: str) -> None:
    """
    Capture a full-page screenshot and save it to screenshots/<name>.png.

    WHY: Screenshots let you visually verify what Playwright actually loaded
    before you try to extract data.  Very useful when selectors return nothing.

    Ref: https://playwright.dev/python/docs/api/class-page#page-screenshot
    """
    if not DEBUG:
        return
    SCREENSHOT_DIR.mkdir(exist_ok=True)
    path = SCREENSHOT_DIR / f"{name}.png"
    # full_page=True captures everything below the fold too
    page.screenshot(path=str(path), full_page=True)
    debug_log(f"Screenshot saved → {path}")


def log_element_count(page, selector: str, label: str) -> int:
    """
    Count how many elements match `selector` and log the result.

    WHY: If the count is 0, your selector is wrong or the page hasn't loaded yet.
    This is the fastest way to confirm whether Playwright can see your target elements.

    Uses page.query_selector_all() which returns all matching elements (never raises).
    Ref: https://playwright.dev/python/docs/api/class-page#page-query-selector-all
    """
    if not DEBUG:
        # Outside debug mode, still return a useful count for control flow
        elements = page.query_selector_all(selector)
        return len(elements)

    elements = page.query_selector_all(selector)
    count = len(elements)
    debug_log(f"[{label}] Selector '{selector}' matched {count} element(s)")
    return count


def log_html_structure(page, selector: str, label: str, max_chars: int = 800) -> None:
    """
    Find the FIRST element matching `selector` and print its inner HTML.

    WHY: Inspecting the raw HTML tells you the exact tag names, class names,
    and nesting that you should use in your own selectors — no guessing required.

    Uses page.query_selector() (returns None if not found, safe to call always).
    Ref: https://playwright.dev/python/docs/api/class-page#page-query-selector
    """
    if not DEBUG:
        return

    element = page.query_selector(selector)
    if element is None:
        debug_log(f"[{label}] Selector '{selector}' → NO ELEMENT FOUND (check selector or wait longer)")
        return

    html = element.inner_html()
    # Truncate very long HTML so the log stays readable
    preview = html[:max_chars] + ("…" if len(html) > max_chars else "")
    debug_log(f"[{label}] HTML structure of '{selector}':\n{preview}")


def check_selector_exists(page, selector: str, label: str) -> bool:
    """
    Check whether a selector exists on the current page and log a clear message.

    WHY: Attempting to interact with a non-existent element throws Playwright errors.
    Always guard optional elements before accessing them.

    Returns True if at least one element matches, False otherwise.
    Ref: https://playwright.dev/python/docs/api/class-page#page-query-selector
    """
    element = page.query_selector(selector)
    exists = element is not None
    if DEBUG:
        status = "✓ FOUND" if exists else "✗ NOT FOUND"
        debug_log(f"[{label}] Selector '{selector}' → {status}")
    return exists


def pause_for_inspection(page, description: str) -> None:
    """
    Pause execution and open the Playwright Inspector for manual inspection.

    WHY: page.pause() halts the script and opens a Chrome DevTools-style
    inspector where you can click elements, run selectors, and step through
    Playwright actions interactively.

    IMPORTANT: Only works when browser is running in NON-headless mode.
    Set PAUSE=True and headless=False in create_browser_context() to use it.

    Ref: https://playwright.dev/python/docs/api/class-page#page-pause
    """
    if not PAUSE:
        return
    debug_log(f"⏸  Pausing for inspection: {description}")
    debug_log("    → Playwright Inspector is open. Close it (or press Resume) to continue.")
    page.pause()  # Blocks until you close the inspector or click Resume


# ─────────────────────────────────────────────
# Browser & page setup
# ─────────────────────────────────────────────

def create_browser_context(headless: bool = False):
    """
    Launch browser and return (playwright, browser, page). Caller must close browser.

    headless=False is required when using page.pause() / Playwright Inspector.
    headless=True is faster for silent production runs.
    """
    playwright = sync_playwright().start()
    browser = playwright.chromium.launch(headless=headless)
    context = browser.new_context(
        locale="ne-NP",
        extra_http_headers={"Accept-Language": "ne-NP,ne;q=0.9,en;q=0.8"},
    )
    page = context.new_page()
    page.set_default_timeout(30_000)
    return playwright, browser, page


# ─────────────────────────────────────────────
# JSON output structure
# ─────────────────────────────────────────────

OUTPUT_FILE = Path(__file__).resolve().parent / "output.json"
OUTPUT_STRUCTURE = {
    "entertainment": [],    # list of {title, image_url, category, author}
    "cartoon_of_the_day": None,  # {title, image_url, category, author} or None
}


# =============================================================================
# Task 2: Entertainment News (मनोरञ्जन) — top 5 articles
# URL: https://ekantipur.com/entertainment
# Selectors: div.category (card), div.category h2 (title), div.category img,
#            div.category span.author (author, may be missing)
# =============================================================================

def scrape_entertainment(page) -> list[dict]:
    """
    Scrape top 5 entertainment (मनोरञ्जन) articles.

    Debugging steps included:
      1. Screenshot right after page loads — confirm visual state.
      2. Log count of div.category cards — confirm selector works.
      3. Log HTML of first card — inspect tag/class structure.
      4. Pause for manual inspection before extraction begins.
      5. Per-card selector existence check for optional fields.
    """
    results = []
    url = "https://ekantipur.com/entertainment"

    # ── Step 1: Navigate and wait ─────────────────────────────────────────────
    debug_log(f"Navigating to entertainment page: {url}")
    try:
        # wait_until="domcontentloaded" is fast; we then wait for full network idle
        # Ref: https://playwright.dev/python/docs/api/class-page#page-goto
        page.goto(url, wait_until="domcontentloaded")

        # Wait for lazy-loaded scripts/images to finish fetching
        # Ref: https://playwright.dev/python/docs/api/class-page#page-wait-for-load-state
        page.wait_for_load_state("networkidle")

        # Confirm article cards are in the DOM before proceeding
        # Ref: https://playwright.dev/python/docs/api/class-page#page-wait-for-selector
        page.wait_for_selector("div.category", timeout=15_000)

        debug_log("Entertainment page loaded successfully.")
    except PlaywrightTimeout:
        print("Timeout loading entertainment page.", file=sys.stderr)
        return results
    except Exception as e:
        print(f"Error loading entertainment page: {e}", file=sys.stderr)
        return results

    # ── Step 2: Screenshot — visually verify what was loaded ──────────────────
    # WHY: If selectors return nothing, the screenshot shows whether
    #      JavaScript rendered the page or if a cookie/paywall blocked it.
    take_screenshot(page, "entertainment_loaded")

    # ── Step 3: Log how many article cards were found ─────────────────────────
    # WHY: If count == 0 the selector is wrong; if count differs from expected,
    #      the page structure may have changed.
    card_count = log_element_count(page, "div.category", "Entertainment")
    debug_log(f"Expecting ≥5 cards; found {card_count}. Will scrape min(5, {card_count}).")

    # ── Step 4: Log HTML of the FIRST card to understand its structure ─────────
    # WHY: This shows you exactly which child tags/classes hold title, image, author.
    log_html_structure(page, "div.category", "Entertainment first card")

    # ── Step 5: Pause for manual Playwright Inspector inspection ──────────────
    # WHY: You can click elements interactively and test selectors in the Inspector
    #      before trusting any automated extraction.  Gated by PAUSE flag.
    pause_for_inspection(page, "Entertainment — before card extraction loop")

    # ── Step 6: Extract data from top 5 cards ─────────────────────────────────
    cards = page.locator("div.category")
    for i in range(min(5, card_count)):
        card = cards.nth(i)
        debug_log(f"  → Processing entertainment card {i + 1}/{min(5, card_count)}")
        try:
            # Title: prefer anchor title attribute for clean text; fall back to inner_text()
            title_el = card.locator("h2").first
            title = ""
            if title_el.count() > 0:
                anchor = card.locator("h2 a").first
                if anchor.count() > 0:
                    title = (anchor.get_attribute("title") or anchor.inner_text() or "").strip()
                else:
                    title = (title_el.inner_text() or "").strip()
            debug_log(f"     title     : {title!r}")

            # Image URL: nullable — log clearly when missing
            img_el = card.locator("img").first
            image_url = None
            if img_el.count() > 0:
                src = img_el.get_attribute("src")
                image_url = src if src else None
            debug_log(f"     image_url : {image_url!r}")

            # Author: optional — check selector exists before trying to read it
            # WHY: Calling inner_text() on a non-existent element throws; guard it first.
            author = None
            author_found = check_selector_exists(
                # Use Playwright's locator approach scoped to card instead of page
                # but check_selector_exists works on the full page — we verify within card below
                page,
                f"div.category:nth-child({i + 1}) span.author",
                f"Entertainment card {i + 1} author",
            )
            author_el = card.locator("span.author").first
            if author_el.count() > 0:
                author = (author_el.inner_text() or "").strip() or None
            debug_log(f"     author    : {author!r}")

            results.append({
                "title": title,
                "image_url": image_url,
                "category": "मनोरञ्जन",
                "author": author,
            })
        except Exception as e:
            print(f"Error parsing entertainment card {i}: {e}", file=sys.stderr)
            continue

    debug_log(f"Entertainment scraping complete. Extracted {len(results)} article(s).")
    return results


# =============================================================================
# Task 3: Cartoon of the Day (कार्टुन)
# URL: https://ekantipur.com/cartoon
# Extract: title (img alt or caption), image_url (first real cartoon image, skip logos),
#          author (cartoonist name if available). Save/update output.json in main().
# =============================================================================

def scrape_cartoon_of_the_day(page) -> dict | None:
    """
    Scrape cartoon of the day from https://ekantipur.com/cartoon.

    Debugging steps included:
      1. Screenshot right after page loads.
      2. Log count of all <img> tags to understand how many images exist.
      3. Log HTML of the first article/main container to inspect structure.
      4. Existence checks for each optional selector (author, caption).
      5. Pause for manual inspection before image extraction.
    """
    url = "https://ekantipur.com/cartoon"

    # ── Step 1: Navigate and wait ─────────────────────────────────────────────
    debug_log(f"Navigating to cartoon page: {url}")
    try:
        page.goto(url, wait_until="domcontentloaded")
        page.wait_for_load_state("networkidle")

        # Wait until at least one <img> is in the DOM
        page.wait_for_selector("img", timeout=15_000)
        debug_log("Cartoon page loaded successfully.")
    except PlaywrightTimeout:
        print("Timeout loading cartoon page.", file=sys.stderr)
        return None
    except Exception as e:
        print(f"Error loading cartoon page: {e}", file=sys.stderr)
        return None

    # ── Step 2: Screenshot — visually verify cartoon page loaded ──────────────
    take_screenshot(page, "cartoon_loaded")

    # ── Step 3: Log total <img> count to understand the image landscape ────────
    # WHY: ekantipur.com embeds logos, ads, and icons; knowing the total count
    #      helps you understand how many non-cartoon images you need to skip.
    img_count = log_element_count(page, "img", "Cartoon page")
    debug_log(f"Total <img> elements on page: {img_count} (includes logos, icons, ads)")

    # ── Step 4: Log HTML of main content containers to find cartoon image ──────
    # Try from most-specific to least-specific container
    for container in ["article", "main", ".content-area"]:
        if check_selector_exists(page, container, f"Cartoon container '{container}'"):
            log_html_structure(page, container, f"Cartoon container '{container}'", max_chars=1000)
            break

    # ── Step 5: Check optional selectors now so we know what's available ───────
    debug_log("Checking optional selectors on cartoon page:")
    check_selector_exists(page, "figcaption", "Cartoon — figcaption")
    check_selector_exists(page, ".caption", "Cartoon — .caption")
    check_selector_exists(page, ".cartoon-caption", "Cartoon — .cartoon-caption")
    check_selector_exists(page, "span.author", "Cartoon — span.author")
    check_selector_exists(page, ".cartoonist", "Cartoon — .cartoonist")
    check_selector_exists(page, ".author-name", "Cartoon — .author-name")

    # ── Step 6: Pause for manual Playwright Inspector inspection ──────────────
    pause_for_inspection(page, "Cartoon — before image extraction")

    # ── Step 7: Find first real cartoon image (skip logos/icons) ──────────────
    try:
        def is_logo_or_icon(src: str) -> bool:
            """Return True if the image src looks like a logo, icon, or favicon."""
            lower = (src or "").lower()
            return "logo" in lower or "icon" in lower or "favicon" in lower

        cartoon_img = None
        image_url = None

        # Try progressively broader containers; stop at the first usable image
        # Ref: https://playwright.dev/python/docs/api/class-locator
        for container_sel in ["article img", "main img", ".content-area img", "img"]:
            candidates = page.locator(container_sel)
            candidate_count = candidates.count()
            debug_log(f"Trying container selector '{container_sel}': {candidate_count} image(s) found")

            for i in range(candidate_count):
                img = candidates.nth(i)
                src = img.get_attribute("src") or ""

                # Skip missing src or known non-cartoon images
                if not src or is_logo_or_icon(src):
                    debug_log(f"  Skipping image {i}: src={src!r} (empty or logo/icon)")
                    continue

                # Wait up to 2 s for the image to be visible
                # Ref: https://playwright.dev/python/docs/api/class-locator#locator-wait-for
                try:
                    img.wait_for(state="visible", timeout=2_000)
                except PlaywrightTimeout:
                    debug_log(f"  Image {i} timed out waiting to be visible: {src!r}")
                    continue

                debug_log(f"  ✓ Selected cartoon image {i}: {src!r}")
                cartoon_img = img
                image_url = src
                break
            else:
                continue  # inner loop exhausted without a break — try next container
            break           # inner loop found an image — stop trying containers

        if not cartoon_img or not image_url:
            print("No cartoon image found on page.", file=sys.stderr)
            debug_log("Tried all container selectors — no usable cartoon image located.")
            return None

        # Screenshot after selecting the cartoon image — confirm page state
        take_screenshot(page, "cartoon_image_selected")

        # ── Step 8: Extract title from alt/title attribute or caption ──────────
        title = (
            cartoon_img.get_attribute("alt")
            or cartoon_img.get_attribute("title")
            or ""
        ).strip()
        debug_log(f"Title from img alt/title: {title!r}")

        if not title:
            # Look for a caption element near the image
            for cap_sel in ["figcaption", ".caption", ".cartoon-caption"]:
                cap_el = page.locator(cap_sel).first
                if cap_el.count() > 0:
                    title = (cap_el.inner_text() or "").strip()
                    debug_log(f"Title from caption selector '{cap_sel}': {title!r}")
                    break

        if not title:
            # Fallback: use the Nepali word for cartoon
            title = "कार्टुन"
            debug_log("No title found; using fallback 'कार्टुन'.")

        # ── Step 9: Extract author / cartoonist name ────────────────────────────
        author = None
        for sel in ["span.author", ".cartoonist", ".author-name", "figcaption"]:
            el = page.locator(sel).first
            if el.count() > 0:
                text = (el.inner_text() or "").strip()
                # Accept only short, author-like text (not a full paragraph/caption)
                if text and len(text) < 100 and text != title:
                    author = text
                    debug_log(f"Author found via '{sel}': {author!r}")
                    break
        if author is None:
            debug_log("No author found for cartoon — will be null in output.")

        return {
            "title": title,
            "image_url": image_url,
            "category": "कार्टुन",
            "author": author,
        }

    except Exception as e:
        print(f"Error extracting cartoon: {e}", file=sys.stderr)
        return None


# =============================================================================
# Entry point
# =============================================================================

def main() -> None:
    """
    Orchestrate scraping and save results to output.json.

    Debug mode summary printed at start so you know which flags are active.
    """
    # Print active debug configuration at startup
    sys.stdout.reconfigure(encoding="utf-8")
    print(f"[CONFIG] DEBUG={DEBUG}  PAUSE={PAUSE}  screenshots → {SCREENSHOT_DIR}")
    print("[CONFIG] Launching browser (headless=False for Playwright Inspector support)")

    data = dict(OUTPUT_STRUCTURE)
    playwright = None
    browser = None

    try:
        # headless=False is required for page.pause() / Playwright Inspector.
        # Switch to headless=True for a silent, faster production run.
        playwright, browser, page = create_browser_context(headless=False)

        # ── Task 2: Entertainment News (मनोरञ्जन) ─────────────────────────────
        print("\n── Scraping Entertainment (मनोरञ्जन) ──────────────────────────────")
        data["entertainment"] = scrape_entertainment(page)
        print(f"   → {len(data['entertainment'])} article(s) collected.")

        # ── Task 3: Cartoon of the Day (कार्टुन) ──────────────────────────────
        print("\n── Scraping Cartoon of the Day (कार्टुन) ────────────────────────")
        data["cartoon_of_the_day"] = scrape_cartoon_of_the_day(page)
        print(f"   → cartoon_of_the_day: {'found' if data['cartoon_of_the_day'] else 'not found'}")

    except Exception as e:
        print(f"Scraper error: {e}", file=sys.stderr)
        raise
    finally:
        if browser:
            browser.close()
        if playwright:
            playwright.stop()

    # ── Save output.json (UTF-8, ensure_ascii=False preserves Nepali text) ────
    # ensure_ascii=False is critical: without it, मनोरञ्जन becomes \\u092e\\u0928...
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"\n✓ Saved to {OUTPUT_FILE}")
    if DEBUG:
        print(f"✓ Debug screenshots saved to {SCREENSHOT_DIR}/")


if __name__ == "__main__":
    main()
