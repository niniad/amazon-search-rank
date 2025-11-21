#!/usr/bin/env python3
"""Amazon.co.jp rank tracker for local execution.

Reads ASIN / keyword pairs from input.csv, opens Amazon via Selenium,
scans up to 3 pages (sponsored listings excluded) and saves the ranks
to @output/amazon-ranks-YYYYMMDD-HHMMSS.csv.
"""
from __future__ import annotations

import csv
import datetime as dt
import logging
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Set

from selenium import webdriver
from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager

AMAZON_URL = "https://www.amazon.co.jp/"
RESULTS_SELECTOR = ".s-main-slot .s-result-item[data-asin]"
NEXT_BUTTON_SELECTOR = "a.s-pagination-next"
MAX_PAGES = 3
OUTPUT_DIR = Path("@output")
OUTPUT_HEADERS = [
    "timestamp",
    "keyword",
    "asin",
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


def load_targets(input_path: Path) -> Dict[str, Set[str]]:
    if not input_path.exists():
        raise FileNotFoundError(f"入力ファイルが見つかりません: {input_path}")

    grouped: Dict[str, Set[str]] = {}
    with input_path.open("r", encoding="utf-8-sig", newline="") as csv_file:
        reader = csv.DictReader(csv_file)
        if not reader.fieldnames:
            raise ValueError("input.csv のヘッダーが読み取れませんでした")

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
        raise ValueError("input.csv に有効な ASIN / 検索語の組み合わせがありません")

    LOGGER.info("input.csv から %s 個のキーワードを読み込みました", len(grouped))
    return grouped


@contextmanager
def create_driver(headless: bool = True):
    options = webdriver.ChromeOptions()
    if headless:
        options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--lang=ja-JP")
    options.add_argument(
        "--user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36"
    )

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
        LOGGER.error("検索ボックス取得に失敗: keyword='%s' url='%s'", keyword, driver.current_url)
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


def collect_keyword_rows(
    keyword: str,
    asins: Set[str],
    driver,
    max_pages: int = MAX_PAGES,
) -> List[List[str]]:
    rows: List[List[str]] = []
    timestamp = dt.datetime.now().isoformat(timespec="seconds")
    found: Set[str] = set()
    overall_rank = 0

    for page in range(1, max_pages + 1):
        try:
            wait_for_results(driver)
        except TimeoutException:
            LOGGER.warning("検索結果の取得に失敗: %s (page %s)", keyword, page)
            break

        items = driver.find_elements(By.CSS_SELECTOR, RESULTS_SELECTOR)
        position_on_page = 0
        for element in items:
            asin = (element.get_attribute("data-asin") or "").strip().upper()
            if not asin or is_sponsored(element):
                continue

            position_on_page += 1
            overall_rank += 1

            if asin in asins and asin not in found:
                found.add(asin)
                rows.append(
                    [
                        timestamp,
                        keyword,
                        asin,
                        "found",
                        str(page),
                        str(position_on_page),
                        str(overall_rank),
                    ]
                )

        if len(found) == len(asins):
            break

        next_buttons = driver.find_elements(By.CSS_SELECTOR, NEXT_BUTTON_SELECTOR)
        if not next_buttons or "s-pagination-disabled" in next_buttons[0].get_attribute("class"):
            break
        driver.execute_script("arguments[0].click();", next_buttons[0])
        time.sleep(2)

    missing = asins - found
    for asin in sorted(missing):
        rows.append([timestamp, keyword, asin, "not_found", "", "", ""])

    return rows


def write_csv(rows: Iterable[Sequence[str]]) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"amazon-ranks-{dt.datetime.now():%Y%m%d-%H%M%S}.csv"
    output_path = OUTPUT_DIR / filename
    with output_path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.writer(csv_file)
        writer.writerow(OUTPUT_HEADERS)
        writer.writerows(rows)
    return output_path


def main() -> None:
    input_path = Path("input.csv")
    targets = load_targets(input_path)

    all_rows: List[List[str]] = []
    with create_driver(headless=True) as driver:
        for keyword, asins in targets.items():
            LOGGER.info("%s の順位を取得します (ASIN %s 件)", keyword, len(asins))
            go_to_search_results(driver, keyword)
            keyword_rows = collect_keyword_rows(keyword, asins, driver)
            all_rows.extend(keyword_rows)

    if not all_rows:
        LOGGER.warning("結果が空のため CSV を出力しません")
        return

    csv_path = write_csv(all_rows)
    LOGGER.info("出力ファイル: %s", csv_path)


if __name__ == "__main__":
    try:
        main()
    except WebDriverException as err:
        LOGGER.error("Selenium 実行中にエラーが発生しました: %s", err)
        sys.exit(1)
