"""
Phase 4 v5: Dark Store Price Scanner for Zepto

KEY FIXES in v5:
- Uses inp.type(pincode, delay=150) instead of inp.fill() — triggers Zepto's autocomplete
- Smart wait: polls for suggestions instead of hardcoded sleep(3.5)
- Retry logic: failed pin codes get a second attempt

Usage:
    python3 src/price_scanner.py --url "https://www.zepto.com/pn/..." --city delhi --dry-run
    python3 src/price_scanner.py --url "https://www.zepto.com/pn/..." --city delhi --headless
    python3 src/price_scanner.py --url "https://www.zepto.com/pn/..." --city delhi
"""

import argparse
import asyncio
import csv
import json
import os
import random
import re
import time
import urllib.request
from datetime import datetime

try:
    from playwright.async_api import async_playwright
    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False

from darkstore_parser import fetch_stores


# ---------------------------------------------------------------------------
# Reverse geocode
# ---------------------------------------------------------------------------

def reverse_geocode(lat, lng):
    url = (
        f"https://nominatim.openstreetmap.org/reverse?"
        f"lat={lat}&lon={lng}&format=json&addressdetails=1"
    )
    req = urllib.request.Request(url, headers={"User-Agent": "qcom-scraper/1.0"})
    try:
        data = json.loads(urllib.request.urlopen(req, timeout=10).read())
        address = data.get("address", {})
        pincode = address.get("postcode", "")
        area = (
            address.get("suburb")
            or address.get("neighbourhood")
            or address.get("city_district")
            or ""
        )
        return pincode, area
    except Exception as e:
        print(f"    Geocode failed for {lat},{lng}: {e}")
        return "", ""


def enrich_stores_with_pincodes(stores, cache_path="data/output/store_pincodes.json"):
    cache = {}
    if os.path.exists(cache_path):
        with open(cache_path) as f:
            cache = json.load(f)
        print(f"  Loaded pin code cache ({len(cache)} entries)")

    enriched = []
    new_lookups = 0

    for i, store in enumerate(stores):
        key = f"{store['lat']},{store['lng']}"
        if key in cache:
            store["pincode"] = cache[key]["pincode"]
            store["area"] = cache[key]["area"]
        else:
            pincode, area = reverse_geocode(store["lat"], store["lng"])
            store["pincode"] = pincode
            store["area"] = area
            cache[key] = {"pincode": pincode, "area": area}
            new_lookups += 1
            if i < len(stores) - 1:
                time.sleep(1.1)
        enriched.append(store)
        if (i + 1) % 20 == 0:
            print(f"  Geocoded {i + 1}/{len(stores)} stores...")

    os.makedirs(os.path.dirname(cache_path), exist_ok=True)
    with open(cache_path, "w") as f:
        json.dump(cache, f, indent=2)

    if new_lookups > 0:
        print(f"  Geocoded {new_lookups} new stores (cached for next run)")

    unique_pincodes = len(set(s["pincode"] for s in enriched if s["pincode"]))
    print(f"  {len(enriched)} stores -> {unique_pincodes} unique pin codes")
    return enriched


# ---------------------------------------------------------------------------
# Location button click (handles first visit + subsequent visits)
# ---------------------------------------------------------------------------

async def click_location_button(page):
    """Click Zepto's location button.
    First visit: button says 'Select Location'
    After location set: button shows area name (first button on page)
    """
    # Try known text first
    for sel in [
        'button:has-text("Select Location")',
        'button:has-text("Deliver to")',
        'button:has-text("Enter your delivery location")',
    ]:
        try:
            el = page.locator(sel).first
            if await el.is_visible(timeout=2000):
                await el.click()
                print(f"    Clicked: {sel}")
                return True
        except Exception:
            continue

    # Fallback: first non-Login, non-Cart button (always the address button)
    try:
        buttons = page.locator("button")
        count = await buttons.count()
        for i in range(min(count, 5)):
            btn = buttons.nth(i)
            if not await btn.is_visible(timeout=1000):
                continue
            text = (await btn.inner_text()).strip()
            if text.lower() in ["login", "cart", "your cart is empty", ""]:
                continue
            await btn.click()
            print(f"    Clicked address button: '{text[:40]}'")
            return True
    except Exception:
        pass

    return False


# ---------------------------------------------------------------------------
# Smart wait for suggestions
# ---------------------------------------------------------------------------

async def wait_for_suggestions(page, pincode, timeout_seconds=6):
    """Poll page text until address suggestions appear, or timeout."""
    geo_keywords = ["india", "delhi", "haryana", "uttar pradesh", "rajasthan",
                     "sector", "colony", "nagar", "vihar", "enclave", "block",
                     "phase", "extension", "market", "road", "marg"]

    for _ in range(int(timeout_seconds / 0.3)):
        await asyncio.sleep(0.3)
        try:
            text = await page.inner_text("body")
            # Check if pincode appears in text AND an address keyword is nearby
            if pincode in text:
                text_lower = text.lower()
                if any(kw in text_lower for kw in geo_keywords):
                    print(f"    Suggestions loaded")
                    return True
        except Exception:
            pass

    print(f"    Suggestions did not appear within {timeout_seconds}s")
    return False


# ---------------------------------------------------------------------------
# Scan one store
# ---------------------------------------------------------------------------

async def scan_product_at_store(page, product_url, store, delay_range=(3, 7)):
    store_name = store["name"]
    pincode = store.get("pincode", "")

    if not pincode:
        return {
            "store_name": store_name, "pincode": "",
            "error": "No pin code", "scanned_at": datetime.now().isoformat(),
        }

    print(f"\n  Scanning: {store_name} (pin: {pincode}, area: {store.get('area', '')})")

    result = {
        "store_name": store_name,
        "store_lat": store["lat"],
        "store_lng": store["lng"],
        "pincode": pincode,
        "area": store.get("area", ""),
        "product_name": None,
        "mrp": None,
        "selling_price": None,
        "discount_pct": None,
        "in_stock": None,
        "delivery_eta": None,
        "scanned_at": datetime.now().isoformat(),
        "error": None,
    }

    try:
        # Step 1: Go to Zepto homepage
        await page.goto("https://www.zepto.com/", wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(random.uniform(2, 3))

        # Step 2: Click location button
        clicked = await click_location_button(page)
        if not clicked:
            result["error"] = "Could not find location selector"
            return result
        await asyncio.sleep(random.uniform(1, 2))

        # Step 3: Type pin code SLOWLY (triggers autocomplete)
        input_selectors = [
            'input[placeholder*="Search"]',
            'input[placeholder*="search"]',
            'input[placeholder*="area"]',
            'input[placeholder*="location"]',
            'input[placeholder*="address"]',
            'input[placeholder*="Enter"]',
            'input[placeholder*="pincode"]',
            'input[type="search"]',
            'input[type="text"]',
        ]

        typed = False
        for sel in input_selectors:
            try:
                inp = page.locator(sel).first
                if await inp.is_visible(timeout=3000):
                    await inp.click()
                    # Clear any existing text
                    await inp.press("Control+a")
                    await inp.press("Backspace")
                    # TYPE slowly — this is the key fix!
                    await inp.type(pincode, delay=150)
                    typed = True
                    print(f"    Typed pin {pincode} (keystroke mode)")
                    break
            except Exception:
                continue

        if not typed:
            result["error"] = "Could not find location input field"
            return result

        # Step 4: Smart wait for suggestions (replaces hardcoded sleep)
        suggestions_appeared = await wait_for_suggestions(page, pincode, timeout_seconds=6)

        if not suggestions_appeared:
            result["error"] = f"No suggestions for pin {pincode}"
            return result

        # Step 5: Click first suggestion
        # The suggestions contain address text — find and click elements with the pincode
        suggestion_clicked = False

        # Try text-based clicking: find any element containing the pincode + "India"
        try:
            suggestion = page.locator(f"text=/{pincode}/i").first
            if await suggestion.is_visible(timeout=2000):
                await suggestion.click()
                suggestion_clicked = True
                print(f"    Clicked suggestion containing '{pincode}'")
                await asyncio.sleep(random.uniform(1, 2))
        except Exception:
            pass

        if not suggestion_clicked:
            # Fallback: try common suggestion selectors
            for sel in [
                '[data-testid="suggestion-item"]',
                '[class*="suggestion"]',
                '[class*="search-result"]',
                '[role="option"]',
                '[role="listbox"] > *',
            ]:
                try:
                    items = page.locator(sel)
                    if await items.count() > 0:
                        await items.first.click()
                        suggestion_clicked = True
                        print(f"    Clicked suggestion: {sel}")
                        await asyncio.sleep(random.uniform(1, 2))
                        break
                except Exception:
                    continue

        if not suggestion_clicked:
            # Last resort: click any div/span containing the pincode text
            try:
                els = page.locator(f"div:has-text('{pincode}'), span:has-text('{pincode}')")
                count = await els.count()
                for i in range(min(count, 10)):
                    el = els.nth(i)
                    text = (await el.inner_text()).strip()
                    # Must contain pincode AND be an address (not just the input field)
                    if pincode in text and len(text) > 10 and "india" in text.lower():
                        await el.click()
                        suggestion_clicked = True
                        print(f"    Clicked address element: '{text[:50]}'")
                        await asyncio.sleep(random.uniform(1, 2))
                        break
            except Exception:
                pass

        # Step 6: Confirm location if needed
        for sel in [
            'button:has-text("Confirm")',
            'button:has-text("Done")',
            'button:has-text("Save")',
            'button:has-text("Continue")',
            'button:has-text("Deliver here")',
            'button:has-text("Confirm Location")',
        ]:
            try:
                el = page.locator(sel).first
                if await el.is_visible(timeout=2000):
                    await el.click()
                    print(f"    Confirmed: {sel}")
                    await asyncio.sleep(random.uniform(1, 2))
                    break
            except Exception:
                continue

        # Step 7: Navigate to product page
        await asyncio.sleep(random.uniform(1, 2))
        await page.goto(product_url, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(random.uniform(3, 5))

        # Step 8: Extract product data
        page_text = await page.inner_text("body")

        # Product name
        for sel in ['h1', '[data-testid="product-title"]']:
            try:
                el = page.locator(sel).first
                if await el.is_visible(timeout=3000):
                    result["product_name"] = (await el.inner_text()).strip()
                    break
            except Exception:
                continue

        # Availability
        avail_keywords = ["out of stock", "currently unavailable", "not available", "sold out", "notify me"]
        result["in_stock"] = not any(kw in page_text.lower() for kw in avail_keywords)

        # Price extraction — isolate product section before "Similar Products"
        similar_idx = page_text.lower().find("similar products")
        product_section = page_text[:similar_idx] if similar_idx > 0 else page_text[:2000]

        price_pattern = re.compile(r'₹\s*\n?\s*([\d,]+(?:\.\d{1,2})?)')
        matches = price_pattern.findall(product_section)

        valid_prices = []
        for p in matches:
            try:
                val = float(p.replace(",", ""))
                if 50 <= val <= 50000:
                    valid_prices.append(val)
            except ValueError:
                continue

        # Deduplicate preserving order
        seen = set()
        unique_prices = []
        for p in valid_prices:
            if p not in seen:
                seen.add(p)
                unique_prices.append(p)

        if unique_prices:
            if len(unique_prices) >= 2:
                result["selling_price"] = min(unique_prices[0], unique_prices[1])
                result["mrp"] = max(unique_prices[0], unique_prices[1])
                if result["mrp"] > 0:
                    result["discount_pct"] = round(
                        (1 - result["selling_price"] / result["mrp"]) * 100, 1
                    )
            else:
                result["selling_price"] = unique_prices[0]

        # Delivery ETA
        eta_match = re.search(r'(\d+)\s*min', page_text, re.IGNORECASE)
        if eta_match:
            result["delivery_eta"] = f"{eta_match.group(1)} min"

        stock_str = "IN STOCK" if result["in_stock"] else "OUT OF STOCK"
        print(f"    OK {stock_str} | Rs{result['selling_price']} | MRP Rs{result['mrp']} | ETA {result['delivery_eta']}")

    except Exception as e:
        result["error"] = str(e)[:200]
        print(f"    ERROR: {result['error']}")

    # Polite delay
    delay = random.uniform(*delay_range)
    print(f"    Waiting {delay:.1f}s ...")
    await asyncio.sleep(delay)

    return result


# ---------------------------------------------------------------------------
# Orchestrator with retry
# ---------------------------------------------------------------------------

async def run_scan(product_url, city="delhi", dry_run=False, headless=False, max_stores=None):
    stores = fetch_stores(city=city, brand="zepto")
    if not stores:
        print("No stores found.")
        return []

    print(f"\n  Resolving pin codes for {len(stores)} stores...")
    stores = enrich_stores_with_pincodes(stores)
    stores = [s for s in stores if s.get("pincode")]

    # Deduplicate by pin code
    seen = {}
    unique_stores = []
    for store in stores:
        pc = store["pincode"]
        if pc not in seen:
            seen[pc] = store
            unique_stores.append(store)
    print(f"  Deduped to {len(unique_stores)} unique pin codes")
    stores = unique_stores

    if dry_run:
        stores = stores[:3]
        print(f"\n  DRY RUN: 3 pin codes only")

    if max_stores:
        stores = stores[:max_stores]

    print(f"\n  Product: {product_url}")
    print(f"  Pin codes: {len(stores)}")
    print(f"  Mode: {'headless' if headless else 'visible browser'}")
    print(f"  Est. time: ~{len(stores) * 18}s")
    print(f"{'='*60}")

    if not HAS_PLAYWRIGHT:
        print("\n  ERROR: pip3 install playwright && python3 -m playwright install chromium")
        return []

    results = []
    failed_stores = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=headless,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
        )
        context = await browser.new_context(
            viewport={"width": 1440, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            locale="en-IN",
            timezone_id="Asia/Kolkata",
        )
        page = await context.new_page()

        # First pass
        for i, store in enumerate(stores, 1):
            print(f"\n  [{i}/{len(stores)}] {store['name']} -> pin {store['pincode']}")
            try:
                r = await scan_product_at_store(page, product_url, store)
                results.append(r)
                if r.get("error"):
                    failed_stores.append(store)
            except Exception as e:
                print(f"    FATAL: {e}")
                results.append({
                    "store_name": store["name"],
                    "pincode": store.get("pincode", ""),
                    "error": str(e)[:200],
                    "scanned_at": datetime.now().isoformat(),
                })
                failed_stores.append(store)

        # Retry pass — try failed stores one more time
        if failed_stores:
            print(f"\n{'='*60}")
            print(f"  RETRY PASS: {len(failed_stores)} failed stores")
            print(f"{'='*60}")

            # Remove failed results (we'll replace with retry results)
            failed_names = {s["name"] for s in failed_stores}
            results = [r for r in results if r.get("store_name") not in failed_names]

            for i, store in enumerate(failed_stores, 1):
                print(f"\n  [RETRY {i}/{len(failed_stores)}] {store['name']} -> pin {store['pincode']}")
                try:
                    r = await scan_product_at_store(page, product_url, store, delay_range=(4, 8))
                    results.append(r)
                except Exception as e:
                    print(f"    RETRY FATAL: {e}")
                    results.append({
                        "store_name": store["name"],
                        "pincode": store.get("pincode", ""),
                        "error": f"RETRY FAILED: {str(e)[:150]}",
                        "scanned_at": datetime.now().isoformat(),
                    })

        await browser.close()

    return results


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def save_results(results, product_url):
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    os.makedirs("data/output", exist_ok=True)

    csv_path = f"data/output/scan_{ts}.csv"
    if results:
        all_keys = set()
        for r in results:
            all_keys.update(r.keys())
        all_keys = sorted(all_keys)
        with open(csv_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=all_keys)
            writer.writeheader()
            writer.writerows(results)
        print(f"\n  CSV -> {csv_path}")

    json_path = f"data/output/scan_{ts}.json"
    with open(json_path, "w") as f:
        json.dump({
            "product_url": product_url,
            "scanned_at": datetime.now().isoformat(),
            "total_stores": len(results),
            "results": results,
        }, f, indent=2)
    print(f"  JSON -> {json_path}")
    return csv_path, json_path


def print_summary(results):
    print(f"\n{'='*85}")
    print(f"  SCAN RESULTS")
    print(f"{'='*85}")

    successful = [r for r in results if not r.get("error") and r.get("selling_price")]
    failed = [r for r in results if r.get("error")]
    oos = [r for r in results if not r.get("error") and r.get("in_stock") == False]

    if successful:
        successful.sort(key=lambda x: x.get("selling_price", float("inf")))
        lowest = successful[0]
        highest = successful[-1]

        print(f"\n  {'Store':<25} {'Pin':>7} {'Price':>8} {'MRP':>8} {'Disc':>6} {'Stock':>6} {'ETA':>8}")
        print(f"  {'-'*25} {'-'*7} {'-'*8} {'-'*8} {'-'*6} {'-'*6} {'-'*8}")

        for r in successful:
            flag = " <-BEST" if r == lowest else ""
            disc = f"{r.get('discount_pct', 0):.0f}%" if r.get("discount_pct") else "-"
            eta = r.get("delivery_eta") or "-"
            stock = "YES" if r.get("in_stock") else "NO"
            print(
                f"  {r['store_name']:<25} {r.get('pincode',''):>7} "
                f"Rs{r['selling_price']:>6.0f} Rs{r.get('mrp',0):>6.0f} "
                f"{disc:>6} {stock:>6} {eta:>8}{flag}"
            )

        if len(successful) > 1 and lowest["selling_price"] != highest["selling_price"]:
            diff = highest["selling_price"] - lowest["selling_price"]
            pct = (diff / highest["selling_price"]) * 100
            print(f"\n  ---")
            print(f"  ARBITRAGE DETECTED")
            print(f"  Cheapest : {lowest['store_name']} (pin {lowest.get('pincode','')}) -> Rs{lowest['selling_price']:.0f}")
            print(f"  Priciest : {highest['store_name']} (pin {highest.get('pincode','')}) -> Rs{highest['selling_price']:.0f}")
            print(f"  You save : Rs{diff:.0f} ({pct:.1f}%)")
            print(f"  ---")
        elif successful:
            print(f"\n  Same price everywhere: Rs{lowest['selling_price']:.0f}")

    if oos:
        print(f"\n  OUT OF STOCK ({len(oos)}):")
        for r in oos:
            print(f"    - {r['store_name']} (pin {r.get('pincode','')})")

    if failed:
        print(f"\n  FAILED ({len(failed)}):")
        for r in failed:
            print(f"    - {r['store_name']}: {r.get('error','?')[:50]}")

    total = len(results)
    success_rate = (len(successful) + len(oos)) / total * 100 if total else 0
    print(f"\n  TOTAL: {len(successful)} priced | {len(oos)} OOS | {len(failed)} failed | {total} total")
    print(f"  SUCCESS RATE: {success_rate:.0f}%")
    print(f"{'='*85}\n")


def main():
    parser = argparse.ArgumentParser(description="Zepto Dark Store Price Scanner v5")
    parser.add_argument("--url", required=True, help="Zepto product URL")
    parser.add_argument("--city", default="delhi", help="City (default: delhi)")
    parser.add_argument("--dry-run", action="store_true", help="Scan only 3 stores")
    parser.add_argument("--headless", action="store_true", help="Headless browser")
    parser.add_argument("--max-stores", type=int, help="Max stores to scan")

    args = parser.parse_args()

    print(f"\n{'='*60}")
    print(f"  ZEPTO DARK STORE PRICE SCANNER v5")
    print(f"  fix: type() not fill(), smart wait, retry logic")
    print(f"{'='*60}")

    results = asyncio.run(
        run_scan(
            product_url=args.url,
            city=args.city,
            dry_run=args.dry_run,
            headless=args.headless,
            max_stores=args.max_stores,
        )
    )

    if results:
        save_results(results, args.url)
        print_summary(results)


if __name__ == "__main__":
    main()
