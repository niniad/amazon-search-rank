#!/usr/bin/env python3
"""Amazon.co.jp rank tracker (Selenium + Cloud Run Ready)

Features:
- Selenium-based scraping for accurate rendering.
- Robust ad detection (SP, SB, Video, Container-level).
- Screenshot capability for verification.
- Cloud Run Jobs compatible (headless).
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import logging
import os
import sys
import time
from pathlib import Path
from typing import Dict, List, Set, Tuple, Any

from selenium import webdriver
from selenium.common.exceptions import TimeoutException, WebDriverException, NoSuchElementException
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
AMAZON_URL = "https://www.amazon.co.jp/"
# Select all result items, including those in carousels or special sections if they have data-asin
RESULTS_SELECTOR = ".s-main-slot div[data-asin], .s-main-slot li[data-asin]"
NEXT_BUTTON_SELECTOR = "a.s-pagination-next"
MAX_PAGES = 3
OUTPUT_DIR = Path("@output")
IMAGES_DIR = OUTPUT_DIR / "images"
INPUT_FILE = Path("input.csv")

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s][%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
LOGGER = logging.getLogger("amazon_rank_tracker")


# ---------------------------------------------------------------------------
# Helper Functions
# ---------------------------------------------------------------------------
def load_targets(input_path: Path) -> Dict[str, Set[str]]:
    """Load targets from CSV."""
    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")

    grouped: Dict[str, Set[str]] = {}
    with input_path.open("r", encoding="utf-8-sig", newline="") as csv_file:
        reader = csv.DictReader(csv_file)
        if not reader.fieldnames:
            raise ValueError("Header not found in input.csv")
        for row in reader:
            asin = (row.get("ASIN") or "").strip().upper()
            keyword = (row.get("SEARCH TERM") or "").strip()
            active = (row.get("ACTIVE") or "yes").strip().lower()
            if active not in {"yes", "y", "true", "1"}:
                continue
            if not asin or not keyword:
                continue
            grouped.setdefault(keyword, set()).add(asin)
    
    if not grouped:
        raise ValueError("No valid targets in input.csv")
    LOGGER.info(f"Loaded {len(grouped)} keywords.")
    return grouped


def create_driver(headless: bool = True):
    """Create a Chrome driver instance."""
    options = webdriver.ChromeOptions()
    if headless:
        options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--lang=ja-JP")
    # Use a realistic User-Agent
    # Use a realistic User-Agent
    options.add_argument(
        "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
    
    # Force language preferences
    prefs = {
        "intl.accept_languages": "ja,ja-JP,en-US,en",
        "profile.default_content_setting_values.notifications": 2
    }
    options.add_experimental_option("prefs", prefs)

    driver = webdriver.Chrome(
        service=Service(ChromeDriverManager().install()),
        options=options,
    )
    driver.set_page_load_timeout(60)
    return driver


def set_location_to_tokyo(driver) -> None:
    """Ensure the delivery location is set to Tokyo (Zip: 100-0001)."""
    try:
        # Check current location label
        try:
            loc_label = driver.find_element(By.ID, "glow-ingress-line2").text
            if "東京" in loc_label or "Tokyo" in loc_label or "Japan" in loc_label or "100-0001" in loc_label:
                LOGGER.info(f"Location already set to: {loc_label}")
                return
        except:
            pass

        LOGGER.info("Setting location to Tokyo (100-0001)...")
        
        # Click location widget
        driver.find_element(By.ID, "nav-global-location-popover-link").click()
        time.sleep(2)
        
        # Input Zip Code
        zip_input = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.ID, "GLUXZipUpdateInput"))
        )
        zip_input.clear()
        zip_input.send_keys("100-0001")
        
        # Click Apply
        driver.find_element(By.ID, "GLUXZipUpdate").click()
        time.sleep(2)
        
        # Click Continue/Done if needed (sometimes it auto-reloads, sometimes needs confirmation)
        try:
            # Look for "Continue" or "Done" button in the popover footer
            confirm_btn = driver.find_element(By.CSS_SELECTOR, "#GLUXConfirmClose, [name='glowDoneButton']")
            confirm_btn.click()
        except:
            pass
            
        # Wait for reload
        time.sleep(3)
        LOGGER.info("Location update sequence completed.")
        
    except Exception as e:
        LOGGER.warning(f"Failed to set location: {e}")
        # Take debug screenshot for location failure
        try:
            driver.save_screenshot("location_error.png")
        except:
            pass


def wait_for_results(driver) -> None:
    """Wait for search results to load."""
    WebDriverWait(driver, 30).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, RESULTS_SELECTOR))
    )


def take_screenshot(driver, keyword: str, page: int) -> None:
    """Save a full-page screenshot."""
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    safe_keyword = "".join(c for c in keyword if c.isalnum() or c in (' ', '-', '_')).strip()
    filename = f"{dt.datetime.now():%Y%m%d_%H%M%S}_{safe_keyword}_{page}.png"
    filepath = IMAGES_DIR / filename
    try:
        # 1. Scroll to bottom to trigger lazy loading
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(2)
        
        # 2. Get full page dimensions
        total_width = driver.execute_script("return document.body.offsetWidth")
        total_height = driver.execute_script("return document.body.parentNode.scrollHeight")
        
        # 3. Resize window to full height (headless mode allows large dimensions)
        # Note: Chrome has a max texture size limit (approx 16384px). 
        # If page is longer, it might be cut off, but usually sufficient for search results.
        driver.set_window_size(total_width, total_height)
        time.sleep(1) # Wait for layout update
        
        driver.save_screenshot(str(filepath))
        LOGGER.info(f"Full-page screenshot saved: {filepath}")
        
    except Exception as e:
        LOGGER.warning(f"Failed to take screenshot: {e}")


def get_item_type(element, sponsored_label_cache=None) -> str:
    """Determine if an item is Organic, Sponsored Product, or other ad type.
    Uses Y-coordinate proximity to detect sponsored sections.
    
    Args:
        element: The WebElement to check
        sponsored_label_cache: Optional list of (y_position, text) tuples for sponsored labels
    """
    # 1. Check direct attributes (SP ads often have this)
    component_type = (element.get_attribute("data-component-type") or "").lower()
    if "sp-sponsored" in component_type or "sponsored" in component_type:
        return "Sponsored"

    # 2. Check badges inside the element (Standard SP label)
    try:
        badges = element.find_elements(By.CSS_SELECTOR, "span[aria-label], .s-label-popover")
        for badge in badges:
            label = (badge.get_attribute("aria-label") or badge.text or "").lower()
            if "sponsored" in label or "スポンサー" in label:
                return "Sponsored"
    except Exception:
        pass

    # 3. Y-coordinate based proximity detection
    # Check if there's a "Sponsored" label within 200px of this element
    try:
        item_y = element.location['y']
        
        # Use cached labels if provided, otherwise search
        if sponsored_label_cache is not None:
            label_positions = sponsored_label_cache
        else:
            # Fallback: search for labels (slower)
            try:
                driver = element.parent
                labels = driver.find_elements(
                    By.XPATH,
                    "//*[contains(text(), 'スポンサー') or contains(text(), 'Sponsored')]"
                )
                label_positions = []
                for label in labels:
                    try:
                        # Only consider visible labels
                        if not label.is_displayed():
                            continue
                        
                        label_text = label.text or ''
                        # Only consider short text (single word/phrase)
                        if len(label_text) < 50 and label_text.strip():
                            label_positions.append((label.location['y'], label_text))
                    except:
                        continue
            except:
                label_positions = []
        
        # Check if any label is within 200px
        for label_y, label_text in label_positions:
            distance = abs(label_y - item_y)
            if distance < 200:
                return "Sponsored"
                
    except Exception:
        pass

    return "Organic"





def process_page(
    driver, 
    keyword: str, 
    page: int, 
    target_asins: Set[str], 
    cumulative_offset: int,
    take_shots: bool
) -> Tuple[List[Dict[str, Any]], int]:
    """Process a single page of results."""
    
    # Cache sponsored labels BEFORE screenshot (before any scrolling)
    # This ensures we capture labels at the top of the page
    sponsored_label_cache = []
    try:
        labels = driver.find_elements(
            By.XPATH,
            "//*[contains(text(), 'スポンサー') or contains(text(), 'Sponsored')]"
        )
        for label in labels:
            try:
                # Only consider visible labels to avoid false positives
                if not label.is_displayed():
                    continue
                
                label_text = label.text or ''
                # Only consider short text (single word/phrase)
                if len(label_text) < 50 and label_text.strip():
                    sponsored_label_cache.append((label.location['y'], label_text))
            except:
                continue
    except Exception as e:
        LOGGER.warning(f"Failed to cache sponsored labels: {e}")
    
    LOGGER.info(f"Found {len(sponsored_label_cache)} sponsored labels on page {page}")
    
    if take_shots:
        take_screenshot(driver, keyword, page)

    # 1. Find all potential product items (div or li with data-asin)
    elements = driver.find_elements(By.CSS_SELECTOR, RESULTS_SELECTOR)
    
    # 2. Filter and Sort
    # - Must have non-empty ASIN
    # - Must be visible
    # - Sort by Y coordinate (top to bottom)
    # - Filter out items that are too far to the right (sidebar) or too narrow (small thumbnails)
    
    # Get main container width to estimate main column area
    try:
        main_slot = driver.find_element(By.CSS_SELECTOR, ".s-main-slot")
        main_rect = main_slot.rect
        main_left = main_rect['x']
        main_right = main_left + main_rect['width']
    except Exception:
        # Fallback if main slot not found
        main_left = 0
        main_right = 2000

    valid_items = []
    for el in elements:
        asin = el.get_attribute("data-asin")
        if not asin or not asin.strip():
            continue
        if not el.is_displayed():
            continue
        
        # Calculate position
        try:
            rect = el.rect
            x = rect['x']
            y = rect['y']
            width = rect['width']
            height = rect['height']
            
            # Filter: Skip items clearly outside the main content flow (e.g. far right sidebar)
            # Assuming main content starts around x=0 to x=300 depending on layout. 
            # Sidebar usually starts > 1000px on desktop.
            # But simpler: check if it intersects with the main slot X-range.
            
            # Also skip very small items (thumbnails in filters, history, etc.)
            if width < 50 or height < 50:
                continue

            # X-coordinate check: 
            # If item is significantly to the right of the main column start, it might be sidebar.
            # However, grid items have varying X. 
            # Better heuristic: Check if the element is contained within .s-main-slot or similar main container.
            # But we selected broadly. 
            # Let's use the 'main_right' boundary. If x > main_right, it's outside.
            # Actually, let's just check if it is INSIDE the s-main-slot div.
            # Checking ancestry for every item is slow.
            
            # Alternative: Just check X < 1000 (approx). 
            # Let's try to be more robust: Check if it is a descendant of .s-main-slot
            # We can do this by modifying the initial selector or filtering here.
            # Modifying selector is better: ".s-main-slot div[data-asin], .s-main-slot li[data-asin]"
            # But user wanted "Highly Rated" which might be outside standard slot? 
            # Usually "Highly Rated" is INSIDE s-main-slot.
            # "Amazon Influencer" might be inside too.
            # Sidebars are usually outside .s-main-slot.
            
            valid_items.append({
                'element': el,
                'asin': asin.strip().upper(),
                'y': y,
                'x': x
            })
        except Exception:
            continue

    # Sort by Y, then X (for items in the same row)
    valid_items.sort(key=lambda k: (k['y'], k['x']))

    # 3. Deduplicate Nested Items
    # Sometimes a container and its child both have data-asin. We want the outermost (or just one).
    # Since we sorted by Y, parents usually come before or at similar Y. 
    # A simple heuristic: if we see the exact same ASIN at nearly the same position, skip.
    # Or better: check if an element is inside another. 
    # For performance, we'll assume that `div[data-asin]` usually represents distinct cards.
    # We will just deduplicate by (ASIN, approximate_position) to avoid double counting the exact same visual card.
    
    unique_items = []
    seen_positions = [] # Store (asin, x, y)
    
    for item in valid_items:
        # Check if this is a duplicate of a recently added item (e.g. same ASIN within 50px)
        is_dup = False
        for seen in seen_positions:
            if seen[0] == item['asin'] and abs(seen[1] - item['y']) < 50 and abs(seen[2] - item['x']) < 50:
                is_dup = True
                break
        
        if not is_dup:
            unique_items.append(item)
            seen_positions.append((item['asin'], item['y'], item['x']))

    LOGGER.info(f"Found {len(unique_items)} visible items on page {page}")

    results = []
    position_counter = 0
    organic_counter = 0
    items_on_page = 0

    for item_data in unique_items:
        item = item_data['element']
        asin = item_data['asin']
        
        items_on_page += 1
        position_counter += 1
        
        item_type = get_item_type(item, sponsored_label_cache)
        
        if item_type == "Organic":
            organic_counter += 1
        
        if asin in target_asins:
            cumulative_rank = cumulative_offset + position_counter
            cumulative_organic_rank = (
                cumulative_offset + organic_counter if item_type == "Organic" else ""
            )
            
            LOGGER.info(f"Found {asin} (Type: {item_type}) at Rank {cumulative_rank}")
            
            results.append({
                "timestamp": dt.datetime.now().isoformat(timespec="seconds"),
                "keyword": keyword,
                "asin": asin,
                "type": item_type,
                "page": page,
                "rank": cumulative_rank,
                "organic_rank": cumulative_organic_rank,
            })

    return results, items_on_page


def main():
    parser = argparse.ArgumentParser(description="Amazon Rank Tracker (Selenium)")
    parser.add_argument("--screenshot", action="store_true", help="Take screenshots of search results")
    parser.add_argument("--pages", type=int, default=MAX_PAGES, help="Number of pages to scan")
    args = parser.parse_args()

    try:
        targets = load_targets(INPUT_FILE)
    except Exception as e:
        LOGGER.error(f"Initialization failed: {e}")
        sys.exit(1)

    all_results = []
    
    driver = create_driver(headless=True)
    try:
        for keyword, asins in targets.items():
            LOGGER.info(f"Searching for: {keyword}")
            driver.get(AMAZON_URL)
            
            # Ensure location is set to Japan/Tokyo
            set_location_to_tokyo(driver)
            
            try:
                search_box = WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.ID, "twotabsearchtextbox"))
                )
                search_box.clear()
                search_box.send_keys(keyword)
                search_box.send_keys(Keys.ENTER)
            except TimeoutException:
                LOGGER.error(f"Search box not found for {keyword}")
                
                # Take debug screenshot on error
                try:
                    timestamp = dt.datetime.now().strftime('%Y%m%d_%H%M%S')
                    filename = f"error_{timestamp}_{keyword}.png"
                    driver.save_screenshot(filename)
                    LOGGER.info(f"Saved error screenshot: {filename}")
                    
                    # Upload to GCS if bucket is set
                    bucket_name = os.environ.get("BUCKET_NAME")
                    if bucket_name:
                        from google.cloud import storage
                        client = storage.Client()
                        bucket = client.bucket(bucket_name)
                        blob = bucket.blob(f"errors/{filename}")
                        blob.upload_from_filename(filename)
                        LOGGER.info(f"Uploaded error screenshot to gs://{bucket_name}/errors/{filename}")
                except Exception as e:
                    LOGGER.error(f"Failed to save error screenshot: {e}")
                continue

            cumulative_offset = 0
            for page in range(1, args.pages + 1):
                LOGGER.info(f"Processing page {page}...")
                try:
                    wait_for_results(driver)
                    # Scroll down to ensure lazy-loaded elements (like bottom ads) are rendered
                    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                    time.sleep(2) 
                    
                    page_results, items_count = process_page(
                        driver, keyword, page, asins, cumulative_offset, args.screenshot
                    )
                    all_results.extend(page_results)
                    cumulative_offset += items_count
                    
                    # Pagination
                    if page < args.pages:
                        try:
                            next_btn = driver.find_element(By.CSS_SELECTOR, NEXT_BUTTON_SELECTOR)
                            if "s-pagination-disabled" in next_btn.get_attribute("class"):
                                LOGGER.info("No more pages.")
                                break
                            driver.execute_script("arguments[0].click();", next_btn)
                            time.sleep(2)
                        except NoSuchElementException:
                            LOGGER.info("Next button not found.")
                            break
                except Exception as e:
                    LOGGER.error(f"Error on page {page}: {e}")
                    break
                    
    finally:
        driver.quit()

    # Write Output
    if all_results:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        output_path = OUTPUT_DIR / f"amazon_ranks_{dt.datetime.now():%Y%m%d_%H%M%S}.csv"
        headers = ["timestamp", "keyword", "asin", "type", "page", "rank", "organic_rank"]
        
        with output_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=headers)
            writer.writeheader()
            writer.writerows(all_results)
        LOGGER.info(f"Saved results to {output_path}")
    else:
        LOGGER.warning("No results found.")

if __name__ == "__main__":
    main()
