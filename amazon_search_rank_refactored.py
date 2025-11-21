#!/usr/bin/env python3
"""
Amazon.co.jp Rank Tracker
=========================
Selenium-based scraper to track product rankings on Amazon Japan.

Features:
- Accurate ad detection (Sponsored vs Organic)
- Full-page screenshot capability
- Cloud Run Jobs compatible
- Y-coordinate based proximity detection for sponsored items

Usage:
    python amazon_search_rank.py [--screenshot]
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import logging
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

# ==============================================================================
# CONFIGURATION
# ==============================================================================
AMAZON_URL = "https://www.amazon.co.jp/"
RESULTS_SELECTOR = ".s-main-slot div[data-asin], .s-main-slot li[data-asin]"
NEXT_BUTTON_SELECTOR = "a.s-pagination-next"
MAX_PAGES = 3
OUTPUT_DIR = Path("@output")
IMAGES_DIR = OUTPUT_DIR / "images"
INPUT_FILE = Path("input.csv")

# Proximity threshold for sponsored label detection (in pixels)
SPONSORED_PROXIMITY_THRESHOLD = 200

# ==============================================================================
# LOGGING SETUP
# ==============================================================================
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s][%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
LOGGER = logging.getLogger("amazon_rank_tracker")


# ==============================================================================
# DATA LOADING
# ==============================================================================
def load_targets(input_path: Path) -> Dict[str, Set[str]]:
    """
    Load target ASINs and search terms from CSV file.
    
    Args:
        input_path: Path to input CSV file
        
    Returns:
        Dictionary mapping search terms to sets of ASINs
        
    Raises:
        FileNotFoundError: If input file doesn't exist
        ValueError: If no valid targets found
    """
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
            
            # Skip inactive entries
            if active not in {"yes", "y", "true", "1"}:
                continue
            
            # Skip entries with missing data
            if not asin or not keyword:
                continue
            
            grouped.setdefault(keyword, set()).add(asin)
    
    if not grouped:
        raise ValueError("No valid targets in input.csv")
    
    LOGGER.info(f"Loaded {len(grouped)} keywords.")
    return grouped


# ==============================================================================
# BROWSER SETUP
# ==============================================================================
def create_driver(headless: bool = True) -> webdriver.Chrome:
    """
    Create and configure Chrome WebDriver.
    
    Args:
        headless: Whether to run in headless mode
        
    Returns:
        Configured Chrome WebDriver instance
    """
    options = webdriver.ChromeOptions()
    
    if headless:
        options.add_argument("--headless=new")
    
    # Performance and compatibility options
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--lang=ja-JP")
    
    # User agent to avoid detection
    options.add_argument(
        "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )

    driver = webdriver.Chrome(
        service=Service(ChromeDriverManager().install()),
        options=options,
    )
    driver.set_page_load_timeout(60)
    
    return driver


def wait_for_results(driver: webdriver.Chrome, timeout: int = 10) -> None:
    """
    Wait for search results to load.
    
    Args:
        driver: Chrome WebDriver instance
        timeout: Maximum wait time in seconds
        
    Raises:
        TimeoutException: If results don't load within timeout
    """
    WebDriverWait(driver, timeout).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, RESULTS_SELECTOR))
    )


# ==============================================================================
# SCREENSHOT FUNCTIONALITY
# ==============================================================================
def take_screenshot(driver: webdriver.Chrome, keyword: str, page: int) -> None:
    """
    Capture full-page screenshot of current search results.
    
    Args:
        driver: Chrome WebDriver instance
        keyword: Search keyword (for filename)
        page: Page number (for filename)
    """
    try:
        IMAGES_DIR.mkdir(parents=True, exist_ok=True)
        
        # Scroll to bottom to load all content
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(1)
        
        # Get full page dimensions
        total_height = driver.execute_script("return document.body.scrollHeight")
        viewport_width = driver.execute_script("return document.body.clientWidth")
        
        # Resize window to capture full page
        driver.set_window_size(viewport_width, total_height)
        time.sleep(0.5)
        
        # Save screenshot
        timestamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = IMAGES_DIR / f"{timestamp}_{keyword}_{page}.png"
        driver.save_screenshot(str(filename))
        
        LOGGER.info(f"Full-page screenshot saved: {filename}")
        
    except Exception as e:
        LOGGER.warning(f"Failed to take screenshot: {e}")


# ==============================================================================
# AD DETECTION
# ==============================================================================
def get_item_type(element, sponsored_label_cache=None) -> str:
    """
    Determine if an item is Organic or Sponsored.
    
    Uses multiple detection methods:
    1. Check data-component-type attribute
    2. Check for sponsored badges within the element
    3. Check proximity to "Sponsored" labels on the page
    
    Args:
        element: The WebElement to check
        sponsored_label_cache: Optional list of (y_position, text) tuples for sponsored labels
    
    Returns:
        'Sponsored' if the item is any type of ad, 'Organic' otherwise
    """
    # Method 1: Check data-component-type attribute
    component_type = (element.get_attribute("data-component-type") or "").lower()
    if "sp-sponsored" in component_type or "sponsored" in component_type:
        return "Sponsored"

    # Method 2: Check for sponsored badges inside the element
    try:
        badges = element.find_elements(By.CSS_SELECTOR, "span[aria-label], .s-label-popover")
        for badge in badges:
            label = (badge.get_attribute("aria-label") or badge.text or "").lower()
            if "sponsored" in label or "スポンサー" in label:
                return "Sponsored"
    except Exception:
        pass

    # Method 3: Y-coordinate based proximity detection
    # Check if there's a "Sponsored" label within threshold distance
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
                        label_text = label.text or ''
                        # Only consider short text (single word/phrase)
                        if len(label_text) < 50:
                            label_positions.append((label.location['y'], label_text))
                    except:
                        continue
            except:
                label_positions = []
        
        # Check if any label is within proximity threshold
        for label_y, label_text in label_positions:
            distance = abs(label_y - item_y)
            if distance < SPONSORED_PROXIMITY_THRESHOLD:
                return "Sponsored"
                
    except Exception:
        pass

    return "Organic"


# ==============================================================================
# PAGE PROCESSING
# ==============================================================================
def process_page(
    driver: webdriver.Chrome, 
    keyword: str, 
    page: int, 
    target_asins: Set[str], 
    cumulative_offset: int,
    take_shots: bool
) -> Tuple[List[Dict[str, Any]], int]:
    """
    Process a single search results page.
    
    Args:
        driver: Chrome WebDriver instance
        keyword: Search keyword
        page: Current page number
        target_asins: Set of ASINs to track
        cumulative_offset: Running count of items from previous pages
        take_shots: Whether to capture screenshots
        
    Returns:
        Tuple of (results list, new cumulative offset)
    """
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
                label_text = label.text or ''
                # Only consider short text (single word/phrase)
                if len(label_text) < 50:
                    sponsored_label_cache.append((label.location['y'], label_text))
            except:
                continue
    except Exception as e:
        LOGGER.warning(f"Failed to cache sponsored labels: {e}")
    
    LOGGER.info(f"Found {len(sponsored_label_cache)} sponsored labels on page {page}")
    
    if take_shots:
        take_screenshot(driver, keyword, page)

    # Find all potential product items
    elements = driver.find_elements(By.CSS_SELECTOR, RESULTS_SELECTOR)
    
    # Get main content area bounds to filter out sidebar items
    try:
        main_slot = driver.find_element(By.CSS_SELECTOR, ".s-main-slot")
        main_rect = main_slot.rect
        main_left = main_rect['x']
        main_right = main_left + main_rect['width']
        LOGGER.info(f"Main slot detected: x={main_left}, width={main_rect['width']}")
    except Exception as e:
        LOGGER.warning(f"Failed to detect main slot: {e}")
        # Fallback if main slot not found
        main_left = 0
        main_right = 2000

    # Filter and collect valid items
    valid_items = []
    for el in elements:
        asin = el.get_attribute("data-asin")
        if not asin or not asin.strip():
            continue
        if not el.is_displayed():
            continue
        
        try:
            rect = el.rect
            x, y, w, h = rect['x'], rect['y'], rect['width'], rect['height']
            
            # Filter out items outside main content area
            if x < main_left or x > main_right:
                continue
            
            # Filter out very small items (thumbnails, etc.)
            if w < 100:
                continue
            
            valid_items.append({
                'element': el,
                'asin': asin.strip().upper(),
                'x': x,
                'y': y,
            })
        except Exception:
            continue

    # Sort by Y coordinate (top to bottom), then X (left to right)
    valid_items.sort(key=lambda k: (k['y'], k['x']))

    # Deduplicate items at same position
    # Sometimes the same product appears multiple times due to nested elements
    unique_items = []
    seen_positions = []  # Store (asin, y, x)
    
    for item in valid_items:
        # Check if this is a duplicate of a recently added item
        is_dup = False
        for seen in seen_positions:
            if (seen[0] == item['asin'] and 
                abs(seen[1] - item['y']) < 50 and 
                abs(seen[2] - item['x']) < 50):
                is_dup = True
                break
        
        if not is_dup:
            unique_items.append(item)
            seen_positions.append((item['asin'], item['y'], item['x']))

    LOGGER.info(f"Found {len(unique_items)} visible items on page {page}")
    
    # Debug: Log specific ASINs
    for idx, item in enumerate(unique_items, 1):
        if item['asin'] in ['B0DBSB6XY9', 'B0D88XNCHG']:
            item_type = get_item_type(item['element'], sponsored_label_cache)
            LOGGER.info(f"DEBUG: Rank {idx}, ASIN={item['asin']}, Y={int(item['y'])}, Type={item_type}")

    # Process items and generate results
    results = []
    position_counter = 0
    organic_counter = 0

    for item_data in unique_items:
        item = item_data['element']
        asin = item_data['asin']
        
        position_counter += 1
        
        # Determine if item is sponsored or organic
        item_type = get_item_type(item, sponsored_label_cache)
        
        if item_type == "Organic":
            organic_counter += 1
        
        # Record if this is a target ASIN
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

    new_offset = cumulative_offset + position_counter
    return results, new_offset


# ==============================================================================
# SEARCH EXECUTION
# ==============================================================================
def search_keyword(
    driver: webdriver.Chrome,
    keyword: str,
    target_asins: Set[str],
    max_pages: int,
    take_shots: bool
) -> List[Dict[str, Any]]:
    """
    Search for a keyword and track target ASINs across multiple pages.
    
    Args:
        driver: Chrome WebDriver instance
        keyword: Search keyword
        target_asins: Set of ASINs to track
        max_pages: Maximum number of pages to search
        take_shots: Whether to capture screenshots
        
    Returns:
        List of result dictionaries for found ASINs
    """
    LOGGER.info(f"Searching for: {keyword}")
    
    # Navigate to Amazon and perform search
    driver.get(AMAZON_URL)
    
    try:
        search_box = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.ID, "twotabsearchtextbox"))
        )
        search_box.clear()
        search_box.send_keys(keyword)
        search_box.send_keys(Keys.ENTER)
    except TimeoutException:
        LOGGER.error(f"Failed to load search page for: {keyword}")
        return []

    all_results = []
    cumulative_offset = 0
    found_asins = set()

    # Process each page
    for page in range(1, max_pages + 1):
        LOGGER.info(f"Processing page {page}...")
        
        try:
            wait_for_results(driver)
        except TimeoutException:
            LOGGER.warning(f"Failed to load results for: {keyword} (page {page})")
            break

        page_results, cumulative_offset = process_page(
            driver, keyword, page, target_asins, cumulative_offset, take_shots
        )
        
        all_results.extend(page_results)
        found_asins.update(r["asin"] for r in page_results)

        # Stop if all targets found
        if found_asins == target_asins:
            LOGGER.info("All target ASINs found!")
            break

        # Navigate to next page
        if page < max_pages:
            try:
                next_btn = driver.find_element(By.CSS_SELECTOR, NEXT_BUTTON_SELECTOR)
                if "s-pagination-disabled" in next_btn.get_attribute("class"):
                    LOGGER.info("No more pages available")
                    break
                driver.execute_script("arguments[0].click();", next_btn)
                time.sleep(2)
            except NoSuchElementException:
                LOGGER.info("Next button not found")
                break

    # Record not found ASINs
    not_found = target_asins - found_asins
    for asin in sorted(not_found):
        all_results.append({
            "timestamp": dt.datetime.now().isoformat(timespec="seconds"),
            "keyword": keyword,
            "asin": asin,
            "type": "",
            "page": "",
            "rank": "",
            "organic_rank": "",
        })

    return all_results


# ==============================================================================
# OUTPUT
# ==============================================================================
def save_results(results: List[Dict[str, Any]]) -> Path:
    """
    Save results to CSV file.
    
    Args:
        results: List of result dictionaries
        
    Returns:
        Path to output CSV file
    """
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    timestamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = OUTPUT_DIR / f"amazon_ranks_{timestamp}.csv"
    
    with output_file.open("w", encoding="utf-8", newline="") as f:
        fieldnames = ["timestamp", "keyword", "asin", "type", "page", "rank", "organic_rank"]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)
    
    LOGGER.info(f"Saved results to {output_file}")
    return output_file


# ==============================================================================
# MAIN
# ==============================================================================
def main():
    """Main execution function."""
    parser = argparse.ArgumentParser(description="Amazon.co.jp Rank Tracker")
    parser.add_argument(
        "--screenshot",
        action="store_true",
        help="Take full-page screenshots of each search results page"
    )
    args = parser.parse_args()

    try:
        # Load targets from input file
        targets = load_targets(INPUT_FILE)
        
        # Create browser instance
        driver = create_driver(headless=True)
        
        try:
            all_results = []
            
            # Process each keyword
            for keyword, asins in targets.items():
                keyword_results = search_keyword(
                    driver, keyword, asins, MAX_PAGES, args.screenshot
                )
                all_results.extend(keyword_results)
            
            # Save all results
            if all_results:
                save_results(all_results)
            else:
                LOGGER.warning("No results to save")
                
        finally:
            driver.quit()
            
    except Exception as e:
        LOGGER.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
