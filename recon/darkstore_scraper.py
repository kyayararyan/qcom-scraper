import requests
import json

URL = "https://darkstoremap.in/data/precomputed/delhi_10m_bike.json"

print("Fetching Delhi dark stores...")

data = requests.get(URL).json()

zepto_stores = []

for feature in data["features"]:

    props = feature.get("properties", {})
    coords = feature.get("geometry", {}).get("coordinates", [])

    brand = str(props).lower()

    if "zepto" in brand:

        zepto_stores.append({
            "name": props,
            "lat": coords[1],
            "lng": coords[0]
        })

print(f"\nFound {len(zepto_stores)} Zepto stores:\n")

for i, store in enumerate(zepto_stores):

    print("=" * 50)
    print(f"Store #{i+1}")
    print(store)