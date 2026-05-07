"""
Run this to debug why the scraper isn't finding race data.
"""

import requests
from bs4 import BeautifulSoup

url = "https://www.equibase.com/static/chart/summary/AQU022126USA-EQB.html"

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

print("Fetching page...")
resp = requests.get(url, headers=headers, timeout=15)
print(f"HTTP Status: {resp.status_code}")
print(f"Page length: {len(resp.text)} characters")

soup = BeautifulSoup(resp.text, "html.parser")

# Test 1 - find race divs
race_divs = soup.find_all("div", class_="c-results-data")
print(f"\nRace divs found (c-results-data): {len(race_divs)}")

# Test 2 - find race headers
headers_found = soup.find_all("h5", class_="coolgraybg")
print(f"Race headers found (coolgraybg): {len(headers_found)}")
for h in headers_found:
    print(f"  → {h.get_text(strip=True)}")

# Test 3 - find winner tables
tables = soup.find_all("table", class_="clear fullwidth text-left")
print(f"\nWinner tables found: {len(tables)}")

# Test 4 - print first 500 chars of page to see what we got
print(f"\nFirst 500 characters of page:")
print(resp.text[:500])
