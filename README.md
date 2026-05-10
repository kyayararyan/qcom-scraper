# Quick Commerce Dark Store Price Scanner

## What this does
Scans a product URL across every Zepto dark store in a city to find the cheapest price, flag out-of-stock stores, and detect arbitrage opportunities.

## Architecture
```
darkstoremap.in JSON → Parse Zepto stores → For each store:
  → Generate delivery point near store
  → Set Zepto location via Playwright
  → Navigate to product page
  → Extract price / availability / ETA
  → Output comparison table + CSV
```

## Setup (Mac)

### Step 1: Install Python dependencies
```bash
pip3 install playwright
python3 -m playwright install chromium
```

### Step 2: Test the dark store parser (no browser needed)
```bash
cd qcom-scraper
python3 src/darkstore_parser.py
```
This fetches all Zepto dark stores in Delhi NCR and saves to `data/output/`.

### Step 3: Run a dry-run scan (3 stores only)
```bash
python3 src/price_scanner.py \
  --url "https://www.zepto.com/pn/bigmuscles-nutrition-nitric-whey-unflavoured/pvid/102f68ed-f550-488c-b16d-15b912608957" \
  --dry-run
```

### Step 4: Full scan (all stores, visible browser)
```bash
python3 src/price_scanner.py \
  --url "https://www.zepto.com/pn/bigmuscles-nutrition-nitric-whey-unflavoured/pvid/102f68ed-f550-488c-b16d-15b912608957"
```

### Step 5: Full scan (headless, faster)
```bash
python3 src/price_scanner.py \
  --url "https://www.zepto.com/pn/bigmuscles-nutrition-nitric-whey-unflavoured/pvid/102f68ed-f550-488c-b16d-15b912608957" \
  --headless
```

## CLI Options
| Flag | Description |
|------|-------------|
| `--url` | Zepto product URL (required) |
| `--city` | City to scan: delhi, mumbai, bangalore, etc. (default: delhi) |
| `--dry-run` | Scan only first 3 stores for testing |
| `--headless` | Run browser invisibly (faster but harder to debug) |
| `--max-stores` | Limit number of stores to scan |

## Output
- `data/output/zepto_darkstores.csv` — List of all dark stores with coordinates
- `data/output/zepto_darkstores.json` — Same in JSON format
- `data/output/scan_YYYYMMDD_HHMMSS.csv` — Price scan results
- `data/output/scan_YYYYMMDD_HHMMSS.json` — Same in JSON format
- Console summary table with arbitrage flags

## Legal
This is a personal-use tool. Automated scraping may violate Zepto's Terms of Service.
Do not redistribute or commercialize without legal review. See LEGAL.md.
