#!/usr/bin/env python3
"""簡易DOM構造調査 - 広告セクションの特定に焦点"""
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager
import time

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
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(2)
        
        print("=== ページ1: 広告セクション分析 ===\n")
        
        # 1. まず、すべての「スポンサー」ラベルの位置を特定
        print("【スポンサーラベルの位置】")
        sponsored_labels = driver.find_elements(
            By.XPATH,
            "//*[contains(text(), 'スポンサー') or contains(text(), 'Sponsored')]"
        )
        
        label_positions = []
        for idx, label in enumerate(sponsored_labels[:15], 1):
            try:
                y = label.location['y']
                text = label.text[:30]
                tag = label.tag_name
                parent_class = label.find_element(By.XPATH, "..").get_attribute('class') or ''
                
                print(f"{idx}. Y={y:4d}, Tag={tag:10s}, Text={text}, ParentClass={parent_class[:40]}")
                label_positions.append(y)
            except:
                pass
        
        # 2. ASIN要素をY座標でグループ化
        print("\n【ASIN要素のグループ（Y座標別）】")
        asin_elements = driver.find_elements(
            By.CSS_SELECTOR,
            ".s-main-slot div[data-asin], .s-main-slot li[data-asin]"
        )
        
        y_groups = {}
        for elem in asin_elements:
            try:
                asin = elem.get_attribute("data-asin")
                if not asin or not asin.strip():
                    continue
                
                y = elem.location['y']
                group_key = (y // 100) * 100  # 100px単位でグループ化
                
                if group_key not in y_groups:
                    y_groups[group_key] = []
                
                y_groups[group_key].append({
                    'asin': asin,
                    'y': y,
                    'component_type': elem.get_attribute('data-component-type') or 'なし'
                })
            except:
                continue
        
        # 3. グループごとに、近くにスポンサーラベルがあるかチェック
        for group_y in sorted(y_groups.keys())[:20]:  # 最初の20グループ
            items = y_groups[group_y]
            
            # このグループの近く（±200px）にスポンサーラベルがあるか
            nearby_labels = [ly for ly in label_positions if abs(ly - group_y) < 200]
            
            component_type = items[0]['component_type']
            
            if nearby_labels:
                status = f"広告（ラベル距離: {min([abs(ly - group_y) for ly in nearby_labels])}px）"
            elif component_type != 'なし':
                status = f"広告（component-type={component_type}）"
            else:
                status = "オーガニック"
            
            print(f"\nY={group_y}px: {len(items)}商品, 判定={status}")
            for item in items[:3]:
                print(f"  - {item['asin']} (Y={item['y']})")
            if len(items) > 3:
                print(f"  ... 他{len(items)-3}商品")
        
    finally:
        driver.quit()
