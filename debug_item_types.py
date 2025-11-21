#!/usr/bin/env python3
"""デバッグ用: 全要素の判定結果を出力"""
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager
import time

RESULTS_SELECTOR = ".s-main-slot div[data-asin], .s-main-slot li[data-asin]"

def create_driver():
    options = webdriver.ChromeOptions()
    options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--lang=ja-JP")
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

def get_item_type_debug(element, sponsored_label_cache, item_y):
    """デバッグ版のget_item_type"""
    # 1. Check direct attributes
    component_type = (element.get_attribute("data-component-type") or "").lower()
    if "sp-sponsored" in component_type or "sponsored" in component_type:
        return "Sponsored Product", f"component-type={component_type}"

    # 2. Check badges
    try:
        badges = element.find_elements(By.CSS_SELECTOR, "span[aria-label], .s-label-popover")
        for badge in badges:
            label = (badge.get_attribute("aria-label") or badge.text or "").lower()
            if "sponsored" in label or "スポンサー" in label:
                return "Sponsored Product", f"badge={label[:20]}"
    except Exception:
        pass

    # 3. Y-coordinate proximity
    closest_distance = 9999
    closest_label = ""
    
    for label_y, label_text in sponsored_label_cache:
        distance = abs(label_y - item_y)
        if distance < closest_distance:
            closest_distance = distance
            closest_label = label_text[:20]
        
        if distance < 200:
            return "Sponsored Section", f"proximity={distance}px, label={label_text[:20]}"
    
    return "Organic", f"closest={closest_distance}px"

if __name__ == "__main__":
    driver = create_driver()
    try:
        driver.get("https://www.amazon.co.jp/")
        
        search_box = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.ID, "twotabsearchtextbox"))
        )
        search_box.clear()
        search_box.send_keys("お食事エプロン")
        search_box.send_keys(Keys.ENTER)
        
        time.sleep(3)
        
        # Cache sponsored labels BEFORE scrolling
        sponsored_label_cache = []
        labels = driver.find_elements(
            By.XPATH,
            "//*[contains(text(), 'スポンサー') or contains(text(), 'Sponsored')]"
        )
        for label in labels:
            try:
                label_text = label.text or ''
                if len(label_text) < 50:
                    sponsored_label_cache.append((label.location['y'], label_text))
            except:
                continue
        
        print(f"=== スポンサーラベル: {len(sponsored_label_cache)}個 ===")
        for y, text in sorted(sponsored_label_cache)[:10]:
            print(f"  Y={y:4d}: {text[:30]}")
        
        # Get all items
        elements = driver.find_elements(By.CSS_SELECTOR, RESULTS_SELECTOR)
        
        # Get main slot bounds
        try:
            main_slot = driver.find_element(By.CSS_SELECTOR, ".s-main-slot")
            main_rect = main_slot.rect
            main_left = main_rect['x']
            main_right = main_left + main_rect['width']
        except:
            main_left = 0
            main_right = 2000
        
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
                
                # Filter logic from process_page
                if x < main_left or x > main_right:
                    continue
                if w < 100:
                    continue
                
                item_type, reason = get_item_type_debug(el, sponsored_label_cache, y)
                
                valid_items.append({
                    'asin': asin,
                    'y': y,
                    'x': x,
                    'type': item_type,
                    'reason': reason
                })
            except:
                continue
        
        # Sort and deduplicate
        valid_items.sort(key=lambda k: (k['y'], k['x']))
        
        unique_items = []
        seen_positions = []
        
        for item in valid_items:
            is_dup = False
            for seen in seen_positions:
                if seen[0] == item['asin'] and abs(seen[1] - item['y']) < 50 and abs(seen[2] - item['x']) < 50:
                    is_dup = True
                    break
            
            if not is_dup:
                unique_items.append(item)
                seen_positions.append((item['asin'], item['y'], item['x']))
        
        print(f"\n=== 最初の30商品の判定結果 ===\n")
        
        position = 0
        organic_count = 0
        
        for idx, item in enumerate(unique_items[:30], 1):
            position += 1
            if item['type'] == 'Organic':
                organic_count += 1
                print(f"{idx:2d}. Rank={position:2d}, OrgRank={organic_count:2d}, Y={int(item['y']):4d}, ASIN={item['asin']}, Type={item['type']:20s}, Reason={item['reason']}")
            else:
                print(f"{idx:2d}. Rank={position:2d}, OrgRank=  , Y={int(item['y']):4d}, ASIN={item['asin']}, Type={item['type']:20s}, Reason={item['reason']}")
        
        print(f"\n総商品数: {len(unique_items)}")
        
    finally:
        driver.quit()
