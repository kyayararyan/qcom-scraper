from playwright.sync_api import sync_playwright
import time

PRODUCT_URL = "https://www.zepto.com/pn/bigmuscles-nutrition-nitric-whey-unflavoured/pvid/102f68ed-f550-488c-b16d-15b912608957"

PINCODES = [
    "110017",
    "110048",
    "110034",
    "110075",
    "110092",

    "122001",
    "122002",
    "122011",
    "122018",

    "121001",
    "121002",
    "121003",

    "201010",
    "201012",
    "201014"
]

with sync_playwright() as p:

    browser = p.chromium.launch(
        headless=False,
        slow_mo=700
    )

    page = browser.new_page()

    for pincode in PINCODES:

        print(f"\\n===== Testing {pincode} =====")

        page.goto("https://www.zepto.com")

        print("Set location manually:", pincode)
        input("Press ENTER after location changes...")

        page.goto(PRODUCT_URL)

        time.sleep(5)

        page_text = page.locator("body").inner_text().lower()

        # availability detection
        if "out of stock" in page_text:
            print("STATUS: OUT OF STOCK")

        elif "add to cart" in page_text:
            print("STATUS: AVAILABLE TO ORDER")

        elif "not available" in page_text:
            print("STATUS: NOT AVAILABLE IN THIS AREA")

        else:
            print("STATUS: UNKNOWN")

        # price detection
        price_candidates = []

        for word in page_text.split():
            if "₹" in word:
                price_candidates.append(word)

        print("Prices:", price_candidates[:10])

    browser.close()