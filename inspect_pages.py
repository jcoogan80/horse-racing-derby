"""
One-shot inspection script.
Loads two Equibase pages via the existing Selenium session and saves raw HTML.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from HorseRacing import create_driver

OUT_DIR = os.path.dirname(os.path.abspath(__file__))

PAGES = [
    ("https://www.equibase.com/static/entry/CD050125USA-EQB.html",
     "entry_inspection.html"),
    ("https://www.equibase.com/static/latechanges/html/latechangesCD-USA.html",
     "latechanges_cd_inspection.html"),
]

driver = create_driver()
try:
    for i, (url, fname) in enumerate(PAGES):
        print(f"\nLoading: {url}")
        driver.get(url)

        if i == 0:
            print("  First page — waiting 60 s (solve CAPTCHA if prompted)...")
            import time; time.sleep(60)
        else:
            import time; time.sleep(10)

        html = driver.page_source
        out_path = os.path.join(OUT_DIR, fname)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(html)
        print(f"  Saved {len(html):,} chars -> {fname}")
finally:
    driver.quit()
    print("\nDone. Browser closed.")
