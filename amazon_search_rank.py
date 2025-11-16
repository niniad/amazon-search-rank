import csv
import datetime as dt
import json
import logging
import os
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set
from urllib.parse import quote

from google.cloud import storage
from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager

AMAZON_URL = "https://www.amazon.co.jp"
RESULTS_SELECTOR = ".s-main-slot .s-result-item[data-asin]"
NEXT_BUTTON_SELECTOR = "a.s-pagination-next"
PLACEMENTS = ("sponsored", "organic")
CSV_HEADERS = [
    "timestamp",
    "run_date",
    "run_time",
    "keyword",
    "asin",
    "placement",
    "status",
    "page",
    "position_on_page",
    "overall_position",
]

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s][%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
LOGGER = logging.getLogger("amazon_rank_tracker")


def _get_row_value(row: Dict[str, str], key: str) -> str:
    target = key.strip().lower()
    for column, value in row.items():
        if column and column.strip().lower() == target:
            return (value or "").strip()
    return ""


def load_matrix() -> Dict[str, Set[str]]:
    """CSV (input.csv) からキーワードごとの ASIN 群を構築する。"""
    csv_path = Path(os.environ.get("INPUT_CSV", "input.csv"))
    if not csv_path.exists():
        raise FileNotFoundError(f"{csv_path} が見つかりません。")

    grouped: Dict[str, Set[str]] = {}
    with csv_path.open("r", newline="", encoding="utf-8-sig") as csv_file:
        reader = csv.DictReader(csv_file)
        if not reader.fieldnames:
            raise ValueError("CSV ヘッダーが空です。")

        for row in reader:
            asin = _get_row_value(row, "asin").upper()
            keyword = _get_row_value(row, "search term")
            active = _get_row_value(row, "active") or "yes"

            if active.lower() not in {"yes", "y", "true", "1"}:
                continue
            if not asin or not keyword:
                continue

            grouped.setdefault(keyword, set()).add(asin)

    if not grouped:
        raise ValueError("input.csv に有効な ASIN / キーワードの行がありません。")

    LOGGER.info("CSV から %s 個のキーワードを読み込みました。", len(grouped))
    return grouped


def build_proxy_argument() -> str:
    host = os.environ.get("IPROYAL_HOST")
    port = os.environ.get("IPROYAL_PORT")
    if not host or not port:
        LOGGER.warning("IPROYAL_HOST または IPROYAL_PORT が設定されていません。プロキシ未使用で実行します。")
        return ""

    username = os.environ.get("IPROYAL_USERNAME", "")
    password = os.environ.get("IPROYAL_PASSWORD", "")
    credentials = ""
    if username and password:
        credentials = f"{quote(username)}:{quote(password)}@"
    return f"http://{credentials}{host}:{port}"


@contextmanager
def chrome_driver():
    options = webdriver.ChromeOptions()
    options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--lang=ja-JP")
    ua = os.environ.get(
        "AMAZON_USER_AGENT",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
    )
    options.add_argument(f"--user-agent={ua}")

    proxy_arg = build_proxy_argument()
    if proxy_arg:
        options.add_argument(f"--proxy-server={proxy_arg}")
        LOGGER.info("Proxy を経由してアクセスします: %s", proxy_arg.rsplit("@", 1)[-1])
    else:
        LOGGER.warning("Proxy 未設定のため、直接接続で実行します。")

    driver = webdriver.Chrome(
        service=Service(ChromeDriverManager().install()),
        options=options,
    )
    driver.set_page_load_timeout(60)
    try:
        yield driver
    finally:
        driver.quit()


def wait_for_results(driver) -> None:
    WebDriverWait(driver, 30).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, RESULTS_SELECTOR))
    )


def go_to_search_results(driver, keyword: str) -> None:
    driver.get(AMAZON_URL)
    try:
        search_box = WebDriverWait(driver, 30).until(
            EC.presence_of_element_located((By.ID, "twotabsearchtextbox"))
        )
    except TimeoutException as exc:
        current_url = driver.current_url
        page_preview = (driver.page_source or "")[:1500]
        LOGGER.error(
            "検索ボックス取得に失敗: keyword='%s' url='%s'", keyword, current_url
        )
        LOGGER.debug("page preview: %s", page_preview)
        raise exc

    search_box.clear()
    search_box.send_keys(keyword)
    search_box.send_keys(Keys.ENTER)
    wait_for_results(driver)
    time.sleep(1)


def is_sponsored(element) -> bool:
    component_type = (element.get_attribute("data-component-type") or "").lower()
    if "sp-sponsored" in component_type:
        return True
    badges = element.find_elements(By.CSS_SELECTOR, "span[aria-label]")
    for badge in badges:
        label = (badge.get_attribute("aria-label") or "").lower()
        if "sponsored" in label or "スポンサー" in label:
            return True
    return False


def collect_keyword_ranks(
    keyword: str,
    asins: Set[str],
    max_pages: int,
    timestamp: str,
    run_date: str,
    run_time: str,
) -> List[List[str]]:
    rows: List[List[str]] = []
    placement_results: Dict[str, Dict[str, Optional[Dict[str, str]]]] = {
        asin: {placement: None for placement in PLACEMENTS}
        for asin in asins
    }
    overall_positions = {placement: 0 for placement in PLACEMENTS}

    with chrome_driver() as driver:
        go_to_search_results(driver, keyword)

        for page in range(1, max_pages + 1):
            try:
                wait_for_results(driver)
            except TimeoutException:
                LOGGER.warning("検索結果の読み込みに失敗: %s (page %s)", keyword, page)
                break

            per_page_positions = {placement: 0 for placement in PLACEMENTS}
            items = driver.find_elements(By.CSS_SELECTOR, RESULTS_SELECTOR)

            for element in items:
                asin = (element.get_attribute("data-asin") or "").strip().upper()
                if not asin:
                    continue

                placement = "sponsored" if is_sponsored(element) else "organic"
                per_page_positions[placement] += 1
                overall_positions[placement] += 1

                if asin in asins and placement_results[asin][placement] is None:
                    placement_results[asin][placement] = {
                        "status": "found",
                        "page": str(page),
                        "position_on_page": str(per_page_positions[placement]),
                        "overall_position": str(overall_positions[placement]),
                    }

            if page == max_pages:
                break

            next_buttons = driver.find_elements(By.CSS_SELECTOR, NEXT_BUTTON_SELECTOR)
            if not next_buttons:
                LOGGER.info("次ページが存在しないため %s ページで終了: %s", page, keyword)
                break

            next_button = next_buttons[0]
            if "s-pagination-disabled" in next_button.get_attribute("class"):
                LOGGER.info("次ページが無効のため %s ページで終了: %s", page, keyword)
                break

            driver.execute_script("arguments[0].click();", next_button)
            time.sleep(2)

    for asin in asins:
        for placement in PLACEMENTS:
            result = placement_results[asin][placement]
            if result is None:
                rows.append(
                    [
                        timestamp,
                        run_date,
                        run_time,
                        keyword,
                        asin,
                        placement,
                        "not_found",
                        "",
                        "",
                        "",
                    ]
                )
            else:
                rows.append(
                    [
                        timestamp,
                        run_date,
                        run_time,
                        keyword,
                        asin,
                        placement,
                        result["status"],
                        result["page"],
                        result["position_on_page"],
                        result["overall_position"],
                    ]
                )

    return rows


def write_csv(rows: Iterable[List[str]]) -> Path:
    temp_dir = tempfile.mkdtemp()
    timestamp = dt.datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    output_path = Path(temp_dir) / f"amazon-ranks-{timestamp}.csv"
    with output_path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.writer(csv_file)
        writer.writerow(CSV_HEADERS)
        for row in rows:
            writer.writerow(row)
    return output_path


def upload_to_gcs(local_path: Path) -> str:
    bucket_name = os.environ.get("GCS_BUCKET_NAME")
    if not bucket_name:
        raise ValueError("GCS_BUCKET_NAME が設定されていません。")

    sa_key = os.environ.get("GCP_SA_KEY")
    if not sa_key:
        raise ValueError("GCP_SA_KEY が設定されていません。")

    try:
        credentials_info = json.loads(sa_key)
    except json.JSONDecodeError as exc:
        raise ValueError("GCP_SA_KEY が正しい JSON 形式ではありません。") from exc

    client = storage.Client.from_service_account_info(credentials_info)
    bucket = client.bucket(bucket_name)

    prefix = os.environ.get("GCS_PREFIX", "amazon-rankings")
    destination = f"{prefix}/{local_path.name}"
    blob = bucket.blob(destination)
    blob.upload_from_filename(local_path.as_posix())
    return destination


def main() -> None:
    matrix = load_matrix()
    max_pages = int(os.environ.get("MAX_PAGES", "3"))
    LOGGER.info("監視対象キーワード: %s 件", len(matrix))
    run_timestamp_actual = dt.datetime.utcnow().replace(microsecond=0)
    scheduled_timestamp = run_timestamp_actual.replace(minute=0, second=0, microsecond=0)
    run_timestamp = run_timestamp_actual.isoformat() + "Z"
    run_date = scheduled_timestamp.strftime("%Y-%m-%d")
    run_time = scheduled_timestamp.strftime("%H:%M")

    all_rows: List[List[str]] = []
    for keyword, asins in matrix.items():
        LOGGER.info("キーワード '%s' の順位を取得します (ASIN %s 件)", keyword, len(asins))
        rows = collect_keyword_ranks(
            keyword, asins, max_pages, run_timestamp, run_date, run_time
        )
        all_rows.extend(rows)

    if not all_rows:
        LOGGER.warning("ランキング結果が空のため、CSV 出力をスキップします。")
        return

    csv_path = write_csv(all_rows)
    LOGGER.info("一時 CSV を作成しました: %s", csv_path)
    destination = upload_to_gcs(csv_path)
    bucket_name = os.environ.get("GCS_BUCKET_NAME", "")
    LOGGER.info("GCS にアップロードしました: gs://%s/%s", bucket_name, destination)


if __name__ == "__main__":
    main()

