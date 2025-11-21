import os
import sys
import logging
from google.cloud import storage
from pathlib import Path
import amazon_search_rank

# Configuration
BUCKET_NAME = os.environ.get("BUCKET_NAME", "amazon-search-ranks")
INPUT_BLOB_NAME = "input.csv"
DATA_PREFIX = "data/"
IMAGES_PREFIX = "images/"
LOCAL_INPUT = "input.csv"
LOCAL_OUTPUT_DIR = Path("@output")

logging.basicConfig(level=logging.INFO)
LOGGER = logging.getLogger("cloud_runner")

def download_input():
    """Download input.csv from GCS."""
    LOGGER.info(f"Downloading {INPUT_BLOB_NAME} from bucket {BUCKET_NAME}...")
    client = storage.Client()
    bucket = client.bucket(BUCKET_NAME)
    blob = bucket.blob(INPUT_BLOB_NAME)
    blob.download_to_filename(LOCAL_INPUT)
    LOGGER.info(f"Downloaded to {LOCAL_INPUT}")

def upload_outputs():
    """Upload all CSVs and images to GCS."""
    LOGGER.info("Uploading outputs to GCS...")
    client = storage.Client()
    bucket = client.bucket(BUCKET_NAME)

    # Upload CSVs
    if LOCAL_OUTPUT_DIR.exists():
        for csv_file in LOCAL_OUTPUT_DIR.glob("*.csv"):
            blob_name = f"{DATA_PREFIX}{csv_file.name}"
            blob = bucket.blob(blob_name)
            blob.upload_from_filename(str(csv_file))
            LOGGER.info(f"Uploaded {csv_file.name} -> gs://{BUCKET_NAME}/{blob_name}")

    # Upload Images
    images_dir = LOCAL_OUTPUT_DIR / "images"
    if images_dir.exists():
        for img_file in images_dir.glob("*.png"):
            blob_name = f"{IMAGES_PREFIX}{img_file.name}"
            blob = bucket.blob(blob_name)
            blob.upload_from_filename(str(img_file))
            LOGGER.info(f"Uploaded {img_file.name} -> gs://{BUCKET_NAME}/{blob_name}")

def main():
    try:
        # 1. Download Input
        download_input()
        
        # 2. Run Scraper
        # Configure arguments for amazon_search_rank
        sys.argv = ["amazon_search_rank.py"]
        
        # Check environment variable for screenshot toggle (Default: True for cloud)
        if os.environ.get("TAKE_SCREENSHOTS", "true").lower() == "true":
            sys.argv.append("--screenshot")
            
        # Check environment variable for pages
        pages = os.environ.get("MAX_PAGES")
        if pages:
            sys.argv.extend(["--pages", pages])

        LOGGER.info(f"Starting scraper with args: {sys.argv}")
        amazon_search_rank.main()
        
        # 3. Upload Outputs
        upload_outputs()
        
    except Exception as e:
        LOGGER.error(f"Cloud Run Job failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
