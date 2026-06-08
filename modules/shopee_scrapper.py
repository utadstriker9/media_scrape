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

def get_cookies_file(region='shopee.co.id'):
    safe_region = region.replace('.', '_')
    return os.path.join(main_folder, 'output', f'shopee_cookies_{safe_region}.json')

# Kept for backward compat — old single-file sessions
cookies_file = os.path.join(main_folder, 'output', 'shopee_cookies.json')

SHOPEE_AUTH_COOKIES = ('SPC_EC', 'SPC_ST', 'SPC_CDS_VER', 'SPC_U')

def is_session_valid(region='shopee.co.id'):
    """Return True if the saved cookies for this region still have valid auth tokens."""
    filepath = get_cookies_file(region)
    # Fallback: also check legacy single-file
    if not os.path.exists(filepath) and os.path.exists(cookies_file):
        filepath = cookies_file
    if not os.path.exists(filepath):
        return False
    try:
        with open(filepath) as f:
            all_cookies = json.load(f)
        now = time.time()
        auth = {c['name']: c for c in all_cookies if c['name'] in SHOPEE_AUTH_COOKIES}
        if not auth:
            return False
        for name, c in auth.items():
            expiry = c.get('expiry')
            if expiry and expiry < now:
                return False
        return True
    except Exception:
        return False

def start_driver(login_mode=False, use_session=False):
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

    # Essential Docker compatibility flags
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-setuid-sandbox")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--disable-extensions")
    options.add_argument("--disable-software-rasterizer")
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-features=VizDisplayCompositor")
    
    # Better for Docker
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--start-maximized")
    options.add_argument("--no-first-run")
    options.add_argument("--no-default-browser-check")
    options.add_argument("--disable-infobars")
    options.add_argument("--disable-notifications")
    
    # Anti-detection flags
    options.add_argument("--disable-web-security")
    options.add_argument("--allow-running-insecure-content")
    
    # Realistic user agent with recent Chrome version
    options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                     "AppleWebKit/537.36 (KHTML, like Gecko) "
                     "Chrome/131.0.0.0 Safari/537.36")
    
    # Additional preferences to avoid detection
    prefs = {
        "credentials_enable_service": False,
        "profile.password_manager_enabled": False,
        "profile.default_content_setting_values.notifications": 2,
    }
    options.add_experimental_option("prefs", prefs)
    # REMOVED: excludeSwitches and useAutomationExtension - causes errors with UC
    
    # Headless only for scraping mode
    if not login_mode:
        options.add_argument("--headless=new")
    
    # Force Chrome binary location (Docker)
    chrome_bin = os.environ.get('CHROME_BIN', '/usr/bin/google-chrome')
    if os.path.exists(chrome_bin):
        options.binary_location = chrome_bin
    elif os.path.exists('/usr/bin/google-chrome-stable'):
        options.binary_location = '/usr/bin/google-chrome-stable'

    try:
        driver = uc.Chrome(
            options=options,
            use_subprocess=False,
            version_main=None,
            driver_executable_path=None,
        )
        
        # Execute anti-detection JavaScript AFTER driver is created
        try:
            driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
                "source": """
                    Object.defineProperty(navigator, 'webdriver', {
                        get: () => undefined
                    });
                    Object.defineProperty(navigator, 'plugins', {
                        get: () => [1, 2, 3, 4, 5]
                    });
                    Object.defineProperty(navigator, 'languages', {
                        get: () => ['en-US', 'en', 'id']
                    });
                    window.chrome = {
                        runtime: {}
                    };
                    Object.defineProperty(navigator, 'permissions', {
                        get: () => ({
                            query: () => Promise.resolve({ state: 'granted' })
                        })
                    });
                """
            })
        except Exception as cdp_error:
            st.warning(f"⚠️ Could not inject anti-detection JS: {cdp_error}")
        
        # Set page load timeout
        driver.set_page_load_timeout(30)
        
        return driver
    except Exception as e:
        st.error(f"❌ Error starting Chrome: {e}")
        # Fallback: try with minimal options
        try:
            fallback_options = uc.ChromeOptions()
            fallback_options.add_argument("--no-sandbox")
            fallback_options.add_argument("--disable-dev-shm-usage")
            fallback_options.add_argument("--headless=new")
            
            chrome_bin = "/usr/bin/google-chrome"
            if os.path.exists(chrome_bin):
                fallback_options.binary_location = chrome_bin
            
            driver = uc.Chrome(
                options=fallback_options,
                use_subprocess=False,
                version_main=None,
            )
            driver.set_page_load_timeout(30)
            st.warning("⚠️ Using fallback Chrome options")
            return driver
        except Exception as fallback_error:
            st.error(f"❌ Fallback also failed: {fallback_error}")
            raise

def save_cookies(driver, region='shopee.co.id'):
    filepath = get_cookies_file(region)
    cookies = driver.get_cookies()
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, 'w') as f:
        json.dump(cookies, f, indent=2)
    st.write(f"✅ Cookies saved → {filepath}")
    st.write(f"📊 {len(cookies)} cookies saved for region: {region}")

def load_cookies(driver, search_region='shopee.co.id'):
    filepath = get_cookies_file(search_region)
    # Fallback to legacy single file
    if not os.path.exists(filepath) and os.path.exists(cookies_file):
        st.warning("⚠️ Using legacy cookie file — re-login to create region-specific cookies.")
        filepath = cookies_file
    if not os.path.exists(filepath):
        st.warning(f"⚠️ No cookie file for region: {search_region}")
        return False
    try:
        with open(filepath, 'r') as f:
            all_cookies = json.load(f)

        now = time.time()
        # Warn if auth cookies are already expired
        auth_expired = [
            c['name'] for c in all_cookies
            if c['name'] in SHOPEE_AUTH_COOKIES and c.get('expiry', now + 1) < now
        ]
        if auth_expired:
            st.warning(f"⚠️ Expired auth cookies detected: {auth_expired}. Please re-login.")
            return False

        driver.get(f"https://{search_region}")
        time.sleep(3)

        loaded_count = 0
        for cookie in all_cookies:
            cookie.pop('sameSite', None)
            # Keep expiry so browser respects it; only remove if it would cause an add_cookie error
            try:
                driver.add_cookie(cookie)
                loaded_count += 1
            except Exception as e:
                # Retry without expiry field if it caused the error
                cookie.pop('expiry', None)
                try:
                    driver.add_cookie(cookie)
                    loaded_count += 1
                except Exception:
                    st.write(f"⚠️ Skipped cookie {cookie.get('name')}: {e}")

        st.write(f"✅ Loaded {loaded_count}/{len(all_cookies)} cookies")
        driver.refresh()
        time.sleep(3)
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
            st.session_state['search_region'] = search_region
        if example_but:
            st.session_state['pg_step'] = 4
        if test_but:
            st.session_state['pg_step'] = 5
            st.session_state['search_region'] = search_region

    # --- SEARCH RESULT ---
    if st.session_state['pg_step'] == 2:
        # Get saved search_region
        search_region = st.session_state.get('search_region', 'shopee.co.id')

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
        
        # Fast-fail: check expiry before launching a browser at all
        if not is_session_valid(search_region):
            st.error("🔒 Session expired or missing for this region. Please use 'First Login' to re-authenticate.")
            return

        driver = None
        try:
            with st.spinner("Starting browser..."):
                driver = start_driver(login_mode=False, use_session=False)

            with st.spinner("Loading cookies..."):
                cookie_loaded = load_cookies(driver, search_region=search_region)
                if not cookie_loaded:
                    st.warning("⚠️ No cookies loaded. Login might be required.")

            # Lightweight session health check: hit the user profile API
            with st.spinner("Verifying session..."):
                try:
                    driver.get(f"https://{search_region}/api/v4/account/basic/get_username_info")
                    time.sleep(2)
                    page_src = driver.page_source
                    if '"error":0' in page_src or '"username"' in page_src:
                        st.success("✅ Session active.")
                    elif '"error":4' in page_src or 'login' in driver.current_url.lower():
                        st.error("🔒 Session invalid. Please use 'First Login' again.")
                        if driver:
                            driver.quit()
                        return
                    else:
                        st.warning("⚠️ Session status unclear, proceeding anyway.")
                except Exception:
                    st.warning("⚠️ Could not verify session, proceeding anyway.")
            
            # Add random delay to mimic human behavior
            time.sleep(random.uniform(2, 4))
            
            product_url = f"https://{search_region}/product-i.{shopid}.{itemid}"
            
            with st.spinner(f"Loading product page..."):
                driver.get(product_url)
                
                # Wait with random intervals like a human
                time.sleep(random.uniform(5, 8))
                
                # Simulate human-like mouse movements (move to random positions)
                try:
                    driver.execute_script("""
                        window.scrollTo(0, Math.floor(Math.random() * 500));
                    """)
                    time.sleep(random.uniform(1, 2))
                    driver.execute_script("""
                        window.scrollTo(0, 0);
                    """)
                except:
                    pass
            
            # Debug: Show current URL
            current = driver.current_url.lower()
            st.write(f"📍 Current URL: {driver.current_url}")
            
            # Check for CAPTCHA/verification
            if "verify" in current or "captcha" in current:
                st.error("🤖 Bot detection triggered! CAPTCHA page detected.")
                
                
                # Save CAPTCHA screenshot
                try:
                    screenshot_dir = os.path.join(main_folder, "screenshots")
                    os.makedirs(screenshot_dir, exist_ok=True)
                    captcha_screenshot = os.path.join(screenshot_dir, "captcha_page.png")
                    driver.save_screenshot(captcha_screenshot)
                    if os.path.exists(captcha_screenshot):
                        st.image(captcha_screenshot, caption="CAPTCHA detected", width='stretch')
                except Exception as e:
                    st.warning(f"Could not save CAPTCHA screenshot: {e}")
                
                if driver:
                    driver.quit()
                return
            
            if "buyer/login" in current or "/login" in current:
                st.error("🔒 Session logged out. Please use 'First Login' button again.")
                if driver:
                    driver.quit()
                return

            # Save debug screenshot
            try:
                screenshot_dir = os.path.join(main_folder, "screenshots")
                os.makedirs(screenshot_dir, exist_ok=True)
                debug_screenshot = os.path.join(screenshot_dir, "debug_page.png")
                driver.save_screenshot(debug_screenshot)
                if os.path.exists(debug_screenshot):
                    st.image(debug_screenshot, caption="Debug: Current page view", width='stretch')
            except Exception as e:
                st.warning(f"Could not save screenshot: {e}")

            # Wait for page to fully load
            try:
                WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.TAG_NAME, "body"))
                )
            except TimeoutException:
                st.warning("⏱️ Page load timeout, continuing anyway...")

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
                "span.XUNR6d",
                "div[data-testid='product-name']",
                "h1"
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
                "div[class*='_3n5NQx']",
                "div[data-testid='product-price']"
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
                "div[class*='_3Oj5_n']",
                "div[data-testid='rating']"
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
                "div[class*='_3Lybjn']",
                "div[data-testid='shop-name']"
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
                "span[class*='_2JY50F']",
                "div[data-testid='description']"
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
                try:
                    debug_source = os.path.join(main_folder, "output", "debug_source.html")
                    with open(debug_source, "w", encoding="utf-8") as f:
                        f.write(driver.page_source)
                    st.write("📄 Page source saved to output/debug_source.html for inspection")
                except Exception as e:
                    st.warning(f"Could not save page source: {e}")
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
            import traceback
            st.code(traceback.format_exc())
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
            # Get saved search_region
            search_region = st.session_state.get('search_region', 'shopee.co.id')
            
            st.subheader("🔐 Shopee Login (QR Code)")
            
            st.warning("⚠️ **Docker Note**: QR login requires GUI access. For Docker:")
            st.info(f"""
            **Option 1 (Recommended)**:
            - Run login locally first
            - Copy `output/shopee_cookies_{search_region.replace('.', '_')}.json` to Docker volume

            **Option 2**:
            - Use X11 forwarding (Linux) or VNC (complex setup)
            """)

            driver = None
            try:
                with st.spinner("Starting browser for login..."):
                    driver = start_driver(login_mode=True, use_session=False)
                
                LOGIN_QR_URL = (
                    f"https://{search_region}/buyer/login/qr?"
                    f"next=https%3A%2F%2F{search_region}%2F"
                )
                driver.get(LOGIN_QR_URL)
                time.sleep(15)

                # Show screenshot in UI
                screenshot_dir = os.path.join(main_folder, "screenshots")
                os.makedirs(screenshot_dir, exist_ok=True)
                screenshot_path = os.path.join(screenshot_dir, "qr_fullpage.png")
                driver.save_screenshot(screenshot_path)
                if os.path.exists(screenshot_path):
                    st.image(screenshot_path, caption="📱 Scan this QR code with Shopee App", width='stretch')

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
                save_cookies(driver, region=search_region)
                st.success("🎉 Cookies saved — ready to scrape!")
                
                st.info("💡 Now you can use 'Search Data' to scrape products.")

            except Exception as e:
                st.error(f"❌ Login failed: {e}")
                import traceback
                st.code(traceback.format_exc())

            finally:
                if driver:
                    try:
                        driver.quit()
                    except Exception:
                        pass

            st.session_state['pg_step'] = 1
            time.sleep(2)
            st.rerun()

        do_login_flow()