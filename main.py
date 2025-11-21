import functions_framework
import datetime as dt
import logging
import csv
import requests
from pathlib import Path
from typing import Dict, Set, List, Tuple, Any
from bs4 import BeautifulSoup
from urllib.parse import quote_plus
from google.cloud import storage

# Configuration
AMAZON_URL = "https://www.amazon.co.jp/"
MAX_PAGES = 3
BUCKET_NAME = "your-bucket-name"  # Replace with your actual bucket name

# Logging setup
logging.basicConfig(level=logging.INFO)
LOGGER = logging.getLogger("amazon_rank_tracker")

def load_targets_from_gcs(bucket_name: str, file_name: str) -> Dict[str, Set[str]]:
    """Load keywords and ASINs from a CSV file in GCS."""
    storage_client = storage.Client()
    bucket = storage_client.bucket(bucket_name)
    blob = bucket.blob(file_name)
    
    if not blob.exists():
        raise FileNotFoundError(f"Input file not found in GCS: {file_name}")

    content = blob.download_as_text(encoding="utf-8-sig")
    grouped: Dict[str, Set[str]] = {}
    
    reader = csv.DictReader(content.splitlines())
    if not reader.fieldnames:
        raise ValueError("Header not found in input CSV")

    for row in reader:
        asin = (row.get("ASIN") or "").strip().upper()
        keyword = (row.get("SEARCH TERM") or "").strip()
        active = (row.get("ACTIVE") or "yes").strip().lower()
        
        if active not in {"yes", "y", "true", "1"}:
            continue
        if not asin or not keyword:
            continue
            
        grouped.setdefault(keyword, set()).add(asin)
        
    return grouped

def fetch_page_html(keyword: str, page_num: int) -> str:
    """Fetch a search-result page from Amazon."""
    query = quote_plus(keyword)
    url = f"{AMAZON_URL}s?k={query}&page={page_num}"
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "ja-JP,ja;q=0.9",
    }
    response = requests.get(url, headers=headers, timeout=30)
    response.raise_for_status()
    return response.text

def parse_page_bs4(
    html: str,
    page_num: int,
    target_asins: Set[str],
    keyword: str,
    cumulative_rank_offset: int,
) -> Tuple[List[Dict[str, Any]], int]:
    """Parse Amazon HTML with BeautifulSoup."""
    soup = BeautifulSoup(html, "html.parser")
    items = soup.select("div[data-component-type='s-search-result']")
    results: List[Dict[str, Any]] = []
    position_counter = 0
    organic_counter = 0
    
    for item in items:
        data_asin = item.get("data-asin")
        if not data_asin or data_asin.strip() == "":
            continue
            
        position_counter += 1
        text_content = item.get_text(separator=" ")
        
        # Determine sponsorship
        is_sponsored = False
        if "スポンサー" in text_content or "Sponsored" in text_content:
            is_sponsored = True
        for badge in item.select("span[aria-label]"):
            label = badge.get("aria-label", "")
            if "sponsored" in label.lower() or "スポンサー" in label:
                is_sponsored = True
                break
                
        if is_sponsored:
            item_type = "Sponsored Product"
        else:
            item_type = "Organic"
            organic_counter += 1
            
        asin = data_asin.strip().upper()
        
        if asin in target_asins:
            cumulative_rank = cumulative_rank_offset + position_counter
            cumulative_organic_rank = (
                cumulative_rank_offset + organic_counter if item_type == "Organic" else ""
            )
            results.append({
                "timestamp": dt.datetime.now().isoformat(timespec="seconds"),
                "keyword": keyword,
                "asin": asin,
                "type": item_type,
                "page": page_num,
                "rank": cumulative_rank,
                "organic_rank": cumulative_organic_rank,
            })
            
    return results, position_counter

@functions_framework.http
def amazon_rank_tracker(request):
    """HTTP Cloud Function entry point."""
    try:
        targets = load_targets_from_gcs(BUCKET_NAME, "input.csv")
    except Exception as e:
        LOGGER.error(f"Failed to load targets: {e}")
        return f"Error: {e}", 500

    all_results = []
    
    for keyword, asins in targets.items():
        cumulative_offset = 0
        for page in range(1, MAX_PAGES + 1):
            try:
                html = fetch_page_html(keyword, page)
                page_results, items_on_page = parse_page_bs4(
                    html, page, asins, keyword, cumulative_offset
                )
                all_results.extend(page_results)
                cumulative_offset += items_on_page
            except Exception as e:
                LOGGER.error(f"Error on page {page} for {keyword}: {e}")
                break
    
    # Save results to GCS
    if all_results:
        output_filename = f"amazon_ranks_{dt.datetime.now():%Y%m%d_%H%M%S}.csv"
        storage_client = storage.Client()
        bucket = storage_client.bucket(BUCKET_NAME)
        blob = bucket.blob(f"output/{output_filename}")
        
        csv_buffer = []
        headers = ["timestamp", "keyword", "asin", "type", "page", "rank", "organic_rank"]
        csv_buffer.append(",".join(headers))
        
        for res in all_results:
            row = [str(res.get(h, "")) for h in headers]
            csv_buffer.append(",".join(row))
            
        blob.upload_from_string("\n".join(csv_buffer), content_type="text/csv")
        return f"Success. Saved to {output_filename}", 200
    
    return "No results found", 200
