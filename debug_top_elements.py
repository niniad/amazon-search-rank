#!/usr/bin/env python3
"""デバッグ用: 最上部の要素を詳細に調査"""
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
        
        print("=== 最上部要素の詳細調査 ===\n")
        
        # 1. .s-main-slot 内のすべての要素
        print("【1. .s-main-slot内のdata-asin要素（Y < 1000px）】")
        main_slot_items = driver.find_elements(
            By.CSS_SELECTOR,
            ".s-main-slot div[data-asin], .s-main-slot li[data-asin]"
        )
        
        top_items = []
        for elem in main_slot_items:
            try:
                asin = elem.get_attribute("data-asin")
                if not asin or not asin.strip():
                    continue
                
                y = elem.location['y']
                if y < 1000:  # 最上部のみ
                    is_displayed = elem.is_displayed()
                    component_type = elem.get_attribute('data-component-type') or 'なし'
                    
                    top_items.append({
                        'asin': asin,
                        'y': y,
                        'displayed': is_displayed,
                        'component_type': component_type
                    })
            except:
                continue
        
        # Y座標でソート
        top_items.sort(key=lambda x: x['y'])
        
        for idx, item in enumerate(top_items, 1):
            print(f"{idx:2d}. Y={item['y']:4d}, ASIN={item['asin']}, Displayed={item['displayed']}, Type={item['component_type']}")
        
        # 2. .s-main-slot の外の要素
        print("\n【2. .s-main-slot外のdata-asin要素（Y < 1000px）】")
        all_items = driver.find_elements(
            By.CSS_SELECTOR,
            "div[data-asin], li[data-asin]"
        )
        
        outside_items = []
        for elem in all_items:
            try:
                # .s-main-slot内かチェック
                try:
                    elem.find_element(By.XPATH, "./ancestor::*[contains(@class, 's-main-slot')]")
                    continue  # s-main-slot内なのでスキップ
                except:
                    pass  # s-main-slot外
                
                asin = elem.get_attribute("data-asin")
                if not asin or not asin.strip():
                    continue
                
                y = elem.location['y']
                if y < 1000:
                    is_displayed = elem.is_displayed()
                    component_type = elem.get_attribute('data-component-type') or 'なし'
                    parent_class = elem.find_element(By.XPATH, "..").get_attribute('class') or ''
                    
                    outside_items.append({
                        'asin': asin,
                        'y': y,
                        'displayed': is_displayed,
                        'component_type': component_type,
                        'parent_class': parent_class[:50]
                    })
            except:
                continue
        
        outside_items.sort(key=lambda x: x['y'])
        
        for idx, item in enumerate(outside_items, 1):
            print(f"{idx:2d}. Y={item['y']:4d}, ASIN={item['asin']}, Displayed={item['displayed']}, Type={item['component_type']}, Parent={item['parent_class']}")
        
        # 3. 動画要素の確認
        print("\n【3. 動画要素（video タグ）】")
        videos = driver.find_elements(By.TAG_NAME, "video")
        print(f"動画要素数: {len(videos)}")
        
        for idx, video in enumerate(videos[:5], 1):
            try:
                y = video.location['y']
                is_displayed = video.is_displayed()
                parent = video.find_element(By.XPATH, "..")
                parent_asin = parent.get_attribute('data-asin') or 'なし'
                
                print(f"{idx}. Y={y:4d}, Displayed={is_displayed}, 親のASIN={parent_asin}")
            except Exception as e:
                print(f"{idx}. エラー: {e}")
        
    finally:
        driver.quit()
