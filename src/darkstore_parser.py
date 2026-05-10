"""
Parse darkstoremap.in precomputed JSON to extract Zepto dark store locations.
Supports: Delhi, Gurgaon, Faridabad, Ghaziabad, Noida (all in delhi JSON).
"""

import json
import urllib.request
import csv
import os
from datetime import datetime

# City endpoints on darkstoremap.in
CITY_ENDPOINTS = {
    "delhi": "https://darkstoremap.in/data/precomputed/delhi_10m_bike.json",
    "mumbai": "https://darkstoremap.in/data/precomputed/mumbai_10m_bike.json",
    "bangalore": "https://darkstoremap.in/data/precomputed/bangalore_10m_bike.json",
    "hyderabad": "https://darkstoremap.in/data/precomputed/hyderabad_10m_bike.json",
    "pune": "https://darkstoremap.in/data/precomputed/pune_10m_bike.json",
    "chennai": "https://darkstoremap.in/data/precomputed/chennai_10m_bike.json",
    "kolkata": "https://darkstoremap.in/data/precomputed/kolkata_10m_bike.json",
}


def fetch_stores(city="delhi", brand="zepto"):
    """Fetch and filter dark stores by city and brand."""
    url = CITY_ENDPOINTS.get(city.lower())
    if not url:
        print(f"City '{city}' not supported. Available: {list(CITY_ENDPOINTS.keys())}")
        return []

    print(f"Fetching {city} dark stores from darkstoremap.in ...")
    try:
        raw = json.loads(urllib.request.urlopen(url, timeout=15).read())
    except Exception as e:
        print(f"Failed to fetch data: {e}")
        return []

    stores = []
    for entry in raw.get("data", []):
        store_info = entry.get("store", {})
        if store_info.get("brand", "").lower() == brand.lower():
            stores.append({
                "name": store_info.get("name", "UNKNOWN"),
                "lat": store_info.get("lat"),
                "lng": store_info.get("lng"),
                "brand": store_info.get("brand", ""),
            })

    print(f"Found {len(stores)} {brand} stores in {city}")
    return stores


def save_to_csv(stores, output_path="data/output/zepto_darkstores.csv"):
    """Save store list to CSV."""
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["name", "lat", "lng", "brand"])
        writer.writeheader()
        writer.writerows(stores)
    print(f"Saved {len(stores)} stores to {output_path}")


def save_to_json(stores, output_path="data/output/zepto_darkstores.json"):
    """Save store list to JSON."""
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    payload = {
        "fetched_at": datetime.now().isoformat(),
        "count": len(stores),
        "stores": stores,
    }
    with open(output_path, "w") as f:
        json.dump(payload, f, indent=2)
    print(f"Saved {len(stores)} stores to {output_path}")


if __name__ == "__main__":
    stores = fetch_stores(city="delhi", brand="zepto")

    if not stores:
        print("No stores found. Exiting.")
        exit(1)

    save_to_csv(stores)
    save_to_json(stores)

    # Print summary table
    print(f"\n{'='*60}")
    print(f"  ZEPTO DARK STORES — DELHI NCR")
    print(f"{'='*60}")
    print(f"  {'#':<4} {'Store Name':<30} {'Lat':<12} {'Lng':<12}")
    print(f"  {'-'*4} {'-'*30} {'-'*12} {'-'*12}")
    for i, s in enumerate(stores, 1):
        print(f"  {i:<4} {s['name']:<30} {s['lat']:<12} {s['lng']:<12}")
    print(f"{'='*60}")
    print(f"  Total: {len(stores)} Zepto dark stores")
    print(f"{'='*60}")
