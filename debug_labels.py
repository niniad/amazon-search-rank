#!/usr/bin/env python3
"""スポンサーラベルの詳細調査"""
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
        
        print("=== スポンサーラベルの詳細（Y < 500px） ===\n")
        
        labels = driver.find_elements(
            By.XPATH,
            "//*[contains(text(), 'スポンサー') or contains(text(), 'Sponsored')]"
        )
        
        top_labels = []
        for label in labels:
            try:
                y = label.location['y']
                if y < 500:
                    text = label.text or ''
                    tag = label.tag_name
                    is_displayed = label.is_displayed()
                    aria_label = label.get_attribute('aria-label') or ''
                    class_name = label.get_attribute('class') or ''
                    
                    top_labels.append({
                        'y': y,
                        'text': text,
                        'tag': tag,
                        'displayed': is_displayed,
                        'aria_label': aria_label,
                        'class': class_name
                    })
            except:
                continue
        
        top_labels.sort(key=lambda x: x['y'])
        
        for idx, lbl in enumerate(top_labels, 1):
            print(f"{idx:2d}. Y={int(lbl['y']):4d}, Tag={lbl['tag']:10s}, Displayed={lbl['displayed']}")
            print(f"     Text: '{lbl['text'][:50]}'")
            print(f"     AriaLabel: '{lbl['aria_label'][:50]}'")
            print(f"     Class: '{lbl['class'][:60]}'")
            print()
        
        # 最上部のdata-asin要素も確認
        print("\n=== 最上部のdata-asin要素（Y < 300px） ===\n")
        
        items = driver.find_elements(
            By.CSS_SELECTOR,
            ".s-main-slot div[data-asin], .s-main-slot li[data-asin]"
        )
        
        top_items = []
        for item in items:
            try:
                asin = item.get_attribute('data-asin')
                if not asin or not asin.strip():
                    continue
                
                y = item.location['y']
                if y < 300:
                    top_items.append({
                        'asin': asin,
                        'y': y,
                        'component_type': item.get_attribute('data-component-type') or 'なし'
                    })
            except:
                continue
        
        top_items.sort(key=lambda x: x['y'])
        
        for idx, itm in enumerate(top_items, 1):
            print(f"{idx}. Y={int(itm['y']):4d}, ASIN={itm['asin']}, Type={itm['component_type']}")
        
    finally:
        driver.quit()
