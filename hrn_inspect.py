"""
Stage 1 diagnostic: fetch one HRN page, save HTML, print status.
"""
import requests, sys, os

URL = "https://entries.horseracingnation.com/entries-results/churchill-downs/2025-05-01"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "hrn_2025-05-01.html")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}

resp = requests.get(URL, headers=HEADERS, timeout=30)
print(f"Status : {resp.status_code}")
print(f"Size   : {len(resp.content):,} bytes")
print(f"URL    : {resp.url}")

with open(OUT, "w", encoding="utf-8") as f:
    f.write(resp.text)
print(f"Saved  : {OUT}")
