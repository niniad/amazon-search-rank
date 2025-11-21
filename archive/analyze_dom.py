#!/usr/bin/env python3
"""DOM構造調査スクリプト - SB広告の構造を確認"""
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

def analyze_sponsored_sections(driver, keyword):
    """スポンサーセクションのDOM構造を分析"""
    driver.get("https://www.amazon.co.jp/")
    
    search_box = WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((By.ID, "twotabsearchtextbox"))
    )
    search_box.clear()
    search_box.send_keys(keyword)
    search_box.send_keys(Keys.ENTER)
    
    time.sleep(3)
    
    # スクロールして全要素をロード
    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
    time.sleep(2)
    
    print("=" * 80)
    print(f"検索キーワード: {keyword}")
    print("=" * 80)
    
    # 1. すべての「スポンサー」テキストを含む要素を探す
    print("\n【1. 'スポンサー'テキストを含む要素】")
    sponsored_elements = driver.find_elements(
        By.XPATH, 
        "//*[contains(text(), 'スポンサー') or contains(text(), 'Sponsored')]"
    )
    
    for idx, elem in enumerate(sponsored_elements[:10], 1):  # 最初の10個
        try:
            print(f"\n--- 要素 {idx} ---")
            print(f"Tag: {elem.tag_name}")
            print(f"Text: {elem.text[:100]}")
            print(f"Class: {elem.get_attribute('class')}")
            print(f"Y座標: {elem.location['y']}")
            
            # 親要素を3階層分表示
            parent = elem
            for level in range(1, 4):
                try:
                    parent = parent.find_element(By.XPATH, "..")
                    print(f"  親{level}: {parent.tag_name}, class={parent.get_attribute('class')}")
                except:
                    break
        except Exception as e:
            print(f"エラー: {e}")
    
    # 2. data-asinを持つ要素とその親構造を確認
    print("\n\n【2. data-asinを持つ要素（最初の20個）】")
    asin_elements = driver.find_elements(
        By.CSS_SELECTOR,
        ".s-main-slot div[data-asin], .s-main-slot li[data-asin]"
    )
    
    for idx, elem in enumerate(asin_elements[:20], 1):
        try:
            asin = elem.get_attribute("data-asin")
            if not asin:
                continue
                
            print(f"\n--- ASIN要素 {idx}: {asin} ---")
            print(f"Tag: {elem.tag_name}")
            print(f"Y座標: {elem.location['y']}")
            print(f"data-component-type: {elem.get_attribute('data-component-type')}")
            
            # 親要素を遡って「スポンサー」を探す
            parent = elem
            for level in range(1, 6):
                try:
                    parent = parent.find_element(By.XPATH, "..")
                    parent_class = parent.get_attribute('class') or ''
                    parent_text = parent.text[:200] if parent.text else ''
                    
                    has_sponsored = 'スポンサー' in parent_text or 'Sponsored' in parent_text
                    
                    print(f"  親{level}: {parent.tag_name}, class={parent_class[:50]}, スポンサー含む={has_sponsored}")
                    
                    if has_sponsored:
                        print(f"    → 'スポンサー'を含むテキスト: {parent_text[:100]}")
                        break
                except:
                    break
                    
        except Exception as e:
            print(f"エラー: {e}")

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
        
        for page_num in range(1, 4):  # 3ページ分
            print(f"\n{'='*80}")
            print(f"ページ {page_num}")
            print(f"{'='*80}\n")
            
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(2)
            
            # data-asinを持つ要素の親構造を確認
            asin_elements = driver.find_elements(
                By.CSS_SELECTOR,
                ".s-main-slot div[data-asin], .s-main-slot li[data-asin]"
            )
            
            print(f"総ASIN要素数: {len(asin_elements)}\n")
            
            # Y座標でグルーピング（同じセクションを識別）
            y_groups = {}
            for elem in asin_elements:
                try:
                    asin = elem.get_attribute("data-asin")
                    if not asin or not asin.strip():
                        continue
                    
                    y_pos = elem.location['y']
                    # 50px以内は同じグループ
                    group_key = (y_pos // 50) * 50
                    
                    if group_key not in y_groups:
                        y_groups[group_key] = []
                    
                    y_groups[group_key].append({
                        'asin': asin,
                        'y': y_pos,
                        'element': elem
                    })
                except:
                    continue
            
            # グループごとに分析
            for group_y in sorted(y_groups.keys()):
                items = y_groups[group_y]
                print(f"\n--- Y座標グループ: {group_y}px ({len(items)}商品) ---")
                
                # 最初の商品で代表チェック
                first_item = items[0]
                elem = first_item['element']
                
                component_type = elem.get_attribute('data-component-type') or 'なし'
                
                # 親を遡ってスポンサーを探す
                sponsored_info = None
                parent = elem
                
                for level in range(1, 6):
                    try:
                        parent = parent.find_element(By.XPATH, "..")
                        parent_class = parent.get_attribute('class') or ''
                        
                        # すべてのテキスト要素をチェック
                        text_elements = parent.find_elements(By.XPATH, ".//*")
                        for te in text_elements[:30]:
                            te_text = te.text or ''
                            te_tag = te.tag_name
                            
                            # 短いテキストで「スポンサー」を含むものを探す
                            if len(te_text) < 100 and ('スポンサー' in te_text or 'Sponsored' in te_text):
                                sponsored_info = {
                                    'level': level,
                                    'tag': te_tag,
                                    'text': te_text[:50],
                                    'class': parent_class[:50]
                                }
                                break
                        
                        if sponsored_info:
                            break
                    except:
                        break
                
                # 判定結果
                if sponsored_info:
                    print(f"  判定: 広告セクション")
                    print(f"    親階層: {sponsored_info['level']}")
                    print(f"    ラベル: {sponsored_info['text']}")
                    print(f"    タグ: {sponsored_info['tag']}")
                    print(f"    親クラス: {sponsored_info['class']}")
                elif component_type != 'なし':
                    print(f"  判定: 広告 (component-type={component_type})")
                else:
                    print(f"  判定: オーガニック")
                
                # 商品リスト
                for item in items[:5]:  # 最初の5商品のみ表示
                    print(f"    - {item['asin']}")
                if len(items) > 5:
                    print(f"    ... 他 {len(items)-5} 商品")
            
            # 次のページへ
            if page_num < 3:
                try:
                    next_btn = driver.find_element(By.CSS_SELECTOR, "a.s-pagination-next")
                    if "s-pagination-disabled" in next_btn.get_attribute("class"):
                        print("\n次のページがありません")
                        break
                    driver.execute_script("arguments[0].click();", next_btn)
                    time.sleep(3)
                except:
                    print("\n次のページボタンが見つかりません")
                    break
        
    finally:
        driver.quit()
