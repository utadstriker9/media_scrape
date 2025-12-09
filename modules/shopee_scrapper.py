import streamlit as st
from helpers.regions import SHOPEE_DOMAIN_MAP

from typing import Optional, Tuple, Dict, Any
import undetected_chromedriver as uc
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.common.exceptions import (
    NoSuchElementException,
    TimeoutException,
    WebDriverException
)
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

import os
import pandas as pd
import requests
import json
from datetime import datetime
import random
import re, base64, time

##########################################################################################

current_script_path = os.path.abspath(__file__)
main_folder = os.path.dirname(current_script_path)
session_path = os.path.join(main_folder, 'output', 'shopee_sessions')
cookies_file = os.path.join(main_folder, 'output', 'shopee_cookies.json')

def start_driver(login_mode=False, use_session=False):  # CHANGED: Default to False
    """
    Args:
        login_mode: If True, runs non-headless for QR login
        use_session: If True, uses persistent session folder (user-data-dir)
                     If False, uses cookie-based session (more portable)
    """
    options = uc.ChromeOptions()

    if use_session:
        options.add_argument(f"--user-data-dir={session_path}")
        options.add_argument("--profile-directory=Default")

    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-setuid-sandbox")
    options.add_argument("--disable-features=VizDisplayCompositor")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--window-size=1366,768")
    options.add_argument("--disable-extensions")
    options.add_argument("--disable-software-rasterizer")
    options.add_argument("--single-process")  
    options.add_argument("--no-zygote") 
    
    # User agent
    options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                     "AppleWebKit/537.36 (KHTML, like Gecko) "
                     "Chrome/120.0.0.0 Safari/537.36")
    
    # Headless only for scraping mode
    if not login_mode:
        options.add_argument("--headless=old")

    try:
        driver = uc.Chrome(
            options=options,
            use_subprocess=False, 
            version_main=None,
            driver_executable_path=None, 
        )
        return driver
    except Exception as e:
        print(f"❌ Error starting Chrome: {e}")
        options.binary_location = "/usr/bin/google-chrome-stable"
        driver = uc.Chrome(
            options=options,
            use_subprocess=False,
            version_main=None,
        )
        return driver

def save_cookies(driver, filepath=cookies_file):
    cookies = driver.get_cookies()
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    
    with open(filepath, 'w') as f:
        json.dump(cookies, f, indent=2)
    
    st.write(f"✅ Cookies saved to {filepath}")
    st.write(f"📊 Saved {len(cookies)} cookies")

def load_cookies(driver, filepath=cookies_file):
    if not os.path.exists(filepath):
        st.warning(f"⚠️ Cookie file not found: {filepath}")
        return False
    
    try:
        with open(filepath, 'r') as f:
            cookies = json.load(f)
        
        # Navigate to domain first
        driver.get("https://shopee.co.id")
        time.sleep(2)
        
        loaded_count = 0
        for cookie in cookies:
            # Remove problematic fields
            cookie.pop('sameSite', None)
            cookie.pop('expiry', None)
            
            try:
                driver.add_cookie(cookie)
                loaded_count += 1
            except Exception as e:
                st.write(f"⚠️ Could not add cookie {cookie.get('name')}: {e}")
        
        st.write(f"✅ Loaded {loaded_count}/{len(cookies)} cookies")
        driver.refresh()
        time.sleep(2)
        return True
    except Exception as e:
        st.error(f"❌ Error loading cookies: {e}")
        return False

##########################################################################################

def scrapper_shopee():

    if 'pg_step' not in st.session_state:
        st.session_state['pg_step'] = 1

    # --- SEARCH FORM ---
    with st.form(key='shopee_form'):
        bol, bol2 = st.columns((1.4, 0.8))

        with bol:
            search_text = st.text_area('Input ID / URL that you want to search')
            search_text = str(search_text)

        with bol2:
            search_param = st.selectbox("Search by:", ("ID", "URL"))
            search_param = str(search_param)

            region_name = st.selectbox("Region:", list(SHOPEE_DOMAIN_MAP.keys()))
            search_region = SHOPEE_DOMAIN_MAP[region_name]

        bolls1, bolls2, bolls3 = st.columns([0.8, 0.4, 0.4])

        with bolls1:
            search_but = st.form_submit_button(label='Search Data')

        with bolls2:
            example_but = st.form_submit_button(label='Show Example')
        
        with bolls3:
            test_but = st.form_submit_button(label='First Login')

        if search_but:
            st.session_state['pg_step'] = 2
        if example_but:
            st.session_state['pg_step'] = 4
        if test_but:
            st.session_state['pg_step'] = 5

    # --- SEARCH RESULT ---
    if st.session_state['pg_step'] == 2:

        if not search_text.strip():
            st.warning(f'Please input {search_param} that you want to search!')
            return

        st.write(f"🔍 Search Result for {search_param}: {search_text}")
        st.divider()

        def extract_ids_from_url(url):
            pattern = r"i\.(\d+)\.(\d+)"
            match = re.search(pattern, url)
            if match:
                return match.group(1), match.group(2)
            return None, None

        # Parse input
        if search_param == "URL":
            shopid, itemid = extract_ids_from_url(search_text)
            if not shopid or not itemid:
                st.error("Unable to extract shopid / itemid from URL.")
                return 
        else:
            try:
                shopid, itemid = [p.strip() for p in search_text.split(",")]
            except:
                st.error("For ID search, format must be: shopid,itemid")
                return 

        st.success(f"✅ Extracted IDs → shopid: {shopid}, itemid: {itemid}")
        st.divider()
        
        driver = None
        try:
            with st.spinner("Starting browser..."):
                driver = start_driver(login_mode=False, use_session=False)  # CHANGED
                
            with st.spinner("Loading cookies..."):
                cookie_loaded = load_cookies(driver)
                if not cookie_loaded:
                    st.warning("⚠️ No cookies loaded. Login might be required.")
            product_url = f"https://{search_region}/product-i.{shopid}.{itemid}"
            
            with st.spinner(f"Loading product page..."):
                driver.get(product_url)
                time.sleep(8)  # INCREASED wait time
            
            # Debug: Show current URL
            current = driver.current_url.lower()
            st.write(f"📍 Current URL: {driver.current_url}")
            
            if "buyer/login" in current or "/login" in current:
                st.error("🔒 Session logged out. Please use 'First Login' button again.")
                return

            # Save debug screenshot
            debug_screenshot = "debug_page.png"
            driver.save_screenshot(debug_screenshot)
            st.image(debug_screenshot, caption="Debug: Current page view", use_container_width=True)

            # Try multiple selectors for each field
            result = {
                "product_url": product_url,
                "title": None,
                "price": None,
                "rating": None,
                "shop_name": None,
                "description": None
            }

            # Title - try multiple selectors
            title_selectors = [
                "h1.vR6K3w",
                "h1[class*='attM6y']",
                "div[class*='_44qnta']",
                "span.XUNR6d"
            ]
            for selector in title_selectors:
                try:
                    result["title"] = driver.find_element(By.CSS_SELECTOR, selector).text.strip()
                    if result["title"]:
                        st.write(f"✅ Title found with: {selector}")
                        break
                except:
                    continue

            # Price - try multiple selectors
            price_selectors = [
                "div.IZPeQz.B67UQ0",
                "div[class*='pqTWkA']",
                "div[class*='_3n5NQx']"
            ]
            for selector in price_selectors:
                try:
                    result["price"] = driver.find_element(By.CSS_SELECTOR, selector).text.strip()
                    if result["price"]:
                        st.write(f"✅ Price found with: {selector}")
                        break
                except:
                    continue

            # Rating
            rating_selectors = [
                "div.F9RHbS.dQEiAI.jMXp4d",
                "div[class*='_3Oj5_n']"
            ]
            for selector in rating_selectors:
                try:
                    result["rating"] = driver.find_element(By.CSS_SELECTOR, selector).text.strip()
                    if result["rating"]:
                        st.write(f"✅ Rating found with: {selector}")
                        break
                except:
                    continue

            # Shop name
            shop_selectors = [
                "div.fV3TIn",
                "div[class*='_3Lybjn']"
            ]
            for selector in shop_selectors:
                try:
                    result["shop_name"] = driver.find_element(By.CSS_SELECTOR, selector).text.strip()
                    if result["shop_name"]:
                        st.write(f"✅ Shop name found with: {selector}")
                        break
                except:
                    continue

            # Description
            desc_selectors = [
                "p.QN2lPu",
                "div[class*='_2u0jt9']",
                "span[class*='_2JY50F']"
            ]
            for selector in desc_selectors:
                try:
                    desc_elems = driver.find_elements(By.CSS_SELECTOR, selector)
                    result["description"] = "\n".join([d.text.strip() for d in desc_elems if d.text.strip()])
                    if result["description"]:
                        st.write(f"✅ Description found with: {selector}")
                        break
                except:
                    continue

            # Check if we got any data
            has_data = any(v for k, v in result.items() if k != "product_url" and v)
            
            if not has_data:
                st.error("❌ No data scraped. The page might require login or CSS selectors changed.")
                st.info("💡 Tip: Check the debug screenshot above to see if content loaded properly.")
                
                # Save page source for debugging
                with open("debug_source.html", "w", encoding="utf-8") as f:
                    f.write(driver.page_source)
                st.write("📄 Page source saved to debug_source.html for inspection")
            else:
                st.success("✅ Data scraped successfully!")
        
            # Display table
            df = pd.DataFrame([result])
            st.dataframe(df)

            # Download CSV
            csv_data = df.to_csv(index=False, sep=';')
            st.download_button(
                label="📥 Download as CSV",
                data=csv_data,
                file_name=f"shopee_item_{itemid}.csv",
                mime="text/csv"
            )

        except WebDriverException as e:
            st.error(f"❌ WebDriver error: {e}")
        except Exception as e:
            st.error(f"❌ Unexpected error: {e}")
        finally:
            if driver:
                try:
                    driver.quit()
                except Exception:
                    pass

    # --- SHOW EXAMPLE ---
    if st.session_state['pg_step'] == 4:
        st.subheader('Example Shopee Scrapper')
        example_data = {
            "Search Type": ["ID", "URL"],
            "How to Input": [
                "shopid,itemid → Example: 12345,987654321",
                "Paste full Shopee URL → Example:\nhttps://shopee.co.id/Some-Product-i.12345.987654321"
            ]
        }
        st.dataframe(pd.DataFrame(example_data))


    if st.session_state['pg_step'] == 5:
        def do_login_flow():
            st.subheader("🔐 Shopee Login (QR Code)")

            driver = None
            try:
                with st.spinner("Starting browser for login..."):
                    driver = start_driver(login_mode=True, use_session=False)
                
                LOGIN_QR_URL = (
                    "https://shopee.co.id/buyer/login/qr?"
                    "next=https%3A%2F%2Fshopee.co.id%2F"
                )
                driver.get(LOGIN_QR_URL)
                time.sleep(15)

                # Show screenshot in UI
                screenshot_path = "qr_fullpage.png"
                driver.save_screenshot(screenshot_path)
                st.image(screenshot_path, caption="📱 Scan this QR code with Shopee App", use_container_width=True)

                st.info("⏳ Waiting for login... (90 sec timeout)")

                login_success = False
                start_ts = time.time()

                while time.time() - start_ts < 90:
                    cookies = {c["name"]: c["value"] for c in driver.get_cookies()}

                    # SPC_EC or SPC_ST appear after successful QR login
                    if "SPC_EC" in cookies or "SPC_ST" in cookies:
                        login_success = True
                        break

                    time.sleep(1)

                if not login_success:
                    st.error("⏱️ Login timeout (90 sec). Please try again.")
                    return

                st.success("✅ Login successful!")
                save_cookies(driver)
                st.success("🎉 Cookies saved — ready to scrape!")
                
                st.info("💡 Now you can use 'Search Data' to scrape products.")

            except Exception as e:
                st.error(f"❌ Login failed: {e}")

            finally:
                if driver:
                    driver.quit()

            st.session_state['pg_step'] = 1
            time.sleep(2)
            st.rerun()

        do_login_flow()