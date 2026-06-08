import streamlit as st
from helpers.regions import SHOPEE_DOMAIN_MAP

import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

import os
import subprocess
import platform
import pandas as pd
import requests as req
import json
import random
import re
import time

##########################################################################################
# Paths & constants
##########################################################################################

current_script_path = os.path.abspath(__file__)
main_folder         = os.path.dirname(current_script_path)
session_path        = os.path.join(main_folder, 'output', 'shopee_sessions')
DEBUG_OUTPUT_PATH   = os.path.join(main_folder, 'output')
_legacy_cookies     = os.path.join(main_folder, 'output', 'shopee_cookies.json')

SHOPEE_AUTH_COOKIES = ('SPC_EC', 'SPC_ST', 'SPC_U')

IS_WINDOWS = platform.system() == "Windows"

try:
    from helpers.rotate_device import ANDROID_DEVICES
except ImportError:
    ANDROID_DEVICES = [{
        "name": "Pixel 7",
        "user_agent": (
            "Mozilla/5.0 (Linux; Android 14; Pixel 7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/122.0.6261.119 Mobile Safari/537.36"
        ),
        "viewport": {"width": 412, "height": 892},
        "scale": 2.625,
    }]

##########################################################################################
# Cookie helpers
##########################################################################################

def get_cookies_file(region='shopee.co.id'):
    safe = region.replace('.', '_')
    return os.path.join(main_folder, 'output', f'shopee_cookies_{safe}.json')

def is_session_valid(region='shopee.co.id'):
    """Check cookie file on disk — fast, no browser needed."""
    fp = get_cookies_file(region)
    if not os.path.exists(fp) and os.path.exists(_legacy_cookies):
        fp = _legacy_cookies
    if not os.path.exists(fp):
        return False
    try:
        cookies = json.load(open(fp))
        now = time.time()
        auth = {c['name']: c for c in cookies if c['name'] in SHOPEE_AUTH_COOKIES}
        if not auth:
            return False
        for c in auth.values():
            if c.get('expiry') and c['expiry'] < now:
                return False
        return True
    except Exception:
        return False

def _load_cookie_dict(region='shopee.co.id'):
    """Return {name: value} dict from saved cookie file."""
    fp = get_cookies_file(region)
    if not os.path.exists(fp) and os.path.exists(_legacy_cookies):
        fp = _legacy_cookies
    with open(fp) as f:
        raw = json.load(f)
    return {c['name']: c['value'] for c in raw}

def save_cookies(driver, region='shopee.co.id'):
    fp = get_cookies_file(region)
    os.makedirs(os.path.dirname(fp), exist_ok=True)
    cookies = driver.get_cookies()
    with open(fp, 'w') as f:
        json.dump(cookies, f, indent=2)
    st.write(f"✅ Cookies saved → {fp}")
    st.write(f"📊 {len(cookies)} cookies for region: {region}")

##########################################################################################
# Requests-based scraping  (primary — no browser, no CAPTCHA)
##########################################################################################

def _make_session(region='shopee.co.id'):
    """Build a requests.Session pre-loaded with cookies and mobile headers."""
    device = random.choice(ANDROID_DEVICES)
    cookie_dict = _load_cookie_dict(region)

    session = req.Session()
    session.headers.update({
        'User-Agent':       device['user_agent'],
        'Accept':           'application/json',
        'Accept-Language':  'en-US,en;q=0.9,id;q=0.8',
        'Accept-Encoding':  'gzip, deflate, br',
        'Connection':       'keep-alive',
        'X-Api-Source':     'pc',
        'If-None-Match-':   '',
        'Referer':          f'https://{region}/',
    })
    # Inject CSRF token from cookies if present
    csrf = cookie_dict.get('csrftoken') or cookie_dict.get('SPC_EC', '')[:32]
    if csrf:
        session.headers['X-Csrftoken'] = csrf

    session.cookies.update(cookie_dict)
    return session, device['name']

def verify_session_requests(region='shopee.co.id'):
    """
    Hit a lightweight Shopee endpoint to confirm the session is alive.
    Returns (True, username) or (False, error_message).
    """
    try:
        session, _ = _make_session(region)
        resp = session.get(
            f'https://{region}/api/v4/account/basic/get_username_info',
            timeout=10
        )
        data = resp.json()
        if data.get('error') == 0:
            username = data.get('data', {}).get('username', 'unknown')
            return True, username
        return False, f"API error {data.get('error')}: {data.get('error_msg', '')}"
    except Exception as e:
        return False, str(e)

def fetch_product(shopid, itemid, region='shopee.co.id'):
    """
    Call Shopee's internal product API with saved cookies.
    Returns (item_dict, None) on success or (None, error_string) on failure.

    Strategy to avoid rate-limits:
      - Random 1.5–3 s delay before every request  (rate limiting)
      - Rotate User-Agent per call                  (fingerprint rotation)
      - Referer matches the product page            (app-like behaviour)
    """
    try:
        session, device_name = _make_session(region)
        session.headers['Referer'] = f'https://{region}/product-i.{shopid}.{itemid}'

        # Rate-limit buffer — mimic human think-time
        time.sleep(random.uniform(1.5, 3.0))

        url = f'https://{region}/api/v4/item/get?itemid={itemid}&shopid={shopid}'
        resp = session.get(url, timeout=15)

        if resp.status_code == 403:
            return None, "403 Forbidden — session expired or IP blocked. Re-login and try again."
        if resp.status_code == 429:
            return None, "429 Too Many Requests — wait a few minutes before retrying."

        data = resp.json()
        err  = data.get('error', -1)

        if err == 4:
            return None, "Session invalid (error 4). Please use 'First Login' to re-authenticate."
        if err != 0:
            return None, f"Shopee API error {err}: {data.get('error_msg', 'unknown')}"

        item = data.get('data', {}).get('item')
        if not item:
            return None, "API returned success but item data is empty."

        return item, device_name

    except req.exceptions.Timeout:
        return None, "Request timed out. Shopee may be slow — try again."
    except Exception as e:
        return None, str(e)

def _start_scrape_driver(region='shopee.co.id'):
    """
    Unified and enhanced driver factory.
    Implements advanced anti-detection techniques from the README.
    """
    options = uc.ChromeOptions()
    device = random.choice(ANDROID_DEVICES)

    # 1. Core anti-detection arguments
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--disable-extensions")
    options.add_argument("--no-first-run")
    options.add_argument("--disable-notifications")

    options.add_argument("--headless=new")
    # Use mobile user agent and viewport for scraping
    options.add_argument(f"--window-size={device['viewport']['width']},{device['viewport']['height']}")
    options.add_argument(f"--user-agent={device['user_agent']}")

    # OS-specific arguments
    if not IS_WINDOWS:
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        chrome_bin = os.environ.get('CHROME_BIN', '/usr/bin/google-chrome')
        if os.path.exists(chrome_bin):
            options.binary_location = chrome_bin

    # Start the driver
    chrome_version = get_chrome_major_version()
    driver = uc.Chrome(
        options=options,
        use_subprocess=IS_WINDOWS,
        version_main=chrome_version,
    )
    driver.set_page_load_timeout(45)

    # 2. Inject JS to hide webdriver presence
    driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
        "source": """
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});
            Object.defineProperty(navigator, 'plugins', {get: () => [1,2,3,4,5]});
        """
    })

    # 3. Apply full mobile emulation via CDP (more effective than args alone)
    driver.execute_cdp_cmd("Emulation.setDeviceMetricsOverride", {
        "mobile": True,
        "width": device['viewport']['width'],
        "height": device['viewport']['height'],
        "deviceScaleFactor": device['scale'],
        "screenOrientation": {"type": "portraitPrimary", "angle": 0},
    })
    driver.execute_cdp_cmd("Emulation.setTouchEmulationEnabled", {
        "enabled": True,
        "maxTouchPoints": 5
    })

    # 4. Load cookies for the scraping session
    driver.get(f"https://{region}/")
    time.sleep(1)
    try:
        cookies = json.load(open(get_cookies_file(region)))
        for cookie in cookies:
            if 'expiry' in cookie:
                del cookie['expiry'] # Let the browser manage expiry
            driver.add_cookie(cookie)
        time.sleep(1)
    except FileNotFoundError:
        # No cookies to load, this is fine for a first login
        pass

    return driver, device['name']

def _simulate_human_interaction(driver):
    """Mimic human-like scrolling and tapping to reduce bot detection."""
    try:
        # Smooth scroll down and up
        scroll_dist = random.randint(300, 600)
        driver.execute_script(f"window.scrollTo({{top: {scroll_dist}, behavior: 'smooth'}});")
        time.sleep(random.uniform(1.0, 2.0))
        driver.execute_script("window.scrollTo({top: 0, behavior: 'smooth'});")
        time.sleep(random.uniform(0.8, 1.5))
    except Exception:
        pass # Don't let this fail the whole script

def _start_login_driver(region='shopee.co.id'):
    """
    Starts a VISIBLE, user-friendly browser for manual login.
    The window is large and easy to use. Deep mobile emulation is NOT applied here
    to prevent the window from resizing itself to a small mobile screen.
    """
    options = uc.ChromeOptions()

    # Core anti-detection arguments
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--disable-extensions")
    options.add_argument("--no-first-run")
    options.add_argument("--disable-notifications")
    
    # Use a larger, user-friendly window for the visible login browser
    options.add_argument("--window-size=800,950")
    options.add_argument("--window-position=0,0") # Position window at top-left
    # Use a generic desktop user-agent for simplicity during login
    options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                         "AppleWebKit/537.36 (KHTML, like Gecko) "
                         "Chrome/124.0.0.0 Safari/537.36")

    if not IS_WINDOWS:
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")

    chrome_version = get_chrome_major_version()
    driver = uc.Chrome(
        options=options,
        use_subprocess=IS_WINDOWS,
        version_main=chrome_version,
    )
    driver.set_page_load_timeout(45)

    return driver

def fetch_product_with_browser(shopid, itemid, region='shopee.co.id'):
    """Fallback: Scrape product page using a full browser."""
    driver, device_name = _start_scrape_driver(region)
    try:
        # Navigate to the real product page, not the API endpoint.
        # This is more human-like and less likely to be blocked.
        url = f'https://{region}/product-i.{shopid}.{itemid}'
        driver.get(url)

        # Check for CAPTCHA or other blocks
        if "verify" in driver.current_url or "captcha" in driver.current_url:
            dbg_path = os.path.join(DEBUG_OUTPUT_PATH, "shopee_captcha.png")
            driver.save_screenshot(dbg_path)
            return None, f"Browser fallback failed: CAPTCHA detected. Screenshot saved to {dbg_path}"


        # Shopee embeds the page's data in a <script> tag. We wait for it and extract it.
        script_element = WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.XPATH, "//script[contains(text(), 'window.__PRELOADED_STATE__')]"))
        )
        script_content = script_element.get_attribute('innerHTML')

        # Extract the JSON part from the script content
        json_str = script_content.split('=', 1)[1].strip()
        if json_str.endswith(';'):
            json_str = json_str[:-1]

        data = json.loads(json_str)

        # The item data is nested within this preloaded state
        item = data.get('item', {}).get('item')
        if not item:
            return None, "Browser fallback failed: Could not find item data in the preloaded page state."
        return item, device_name
    finally:
        driver.quit()

def parse_product(item, shopid, itemid, region):
    """
    Parse the raw item dict from Shopee's API into a flat result dict.
    Shopee stores prices as actual_price * 100_000.
    """
    def fmt_price(raw):
        if not raw:
            return None
        val = int(raw) // 100_000
        return f"Rp {val:,}"

    rating_info  = item.get('item_rating', {})
    rating_star  = rating_info.get('rating_star', 0)
    rating_count = sum(rating_info.get('rating_count', []))

    images = item.get('images', [])
    img_urls = [f"https://down-id.img.susercontent.com/file/{h}" for h in images[:3]]

    price_min = item.get('price_min') or item.get('price')
    price_max = item.get('price_max') or item.get('price')

    if price_min and price_max and price_min != price_max:
        price_str = f"{fmt_price(price_min)} – {fmt_price(price_max)}"
    else:
        price_str = fmt_price(price_min)

    return {
        "product_url":  f"https://{region}/product-i.{shopid}.{itemid}",
        "title":        item.get('name'),
        "price":        price_str,
        "rating":       f"{rating_star:.1f} ⭐ ({rating_count:,} ratings)" if rating_star else None,
        "sold":         item.get('sold'),
        "stock":        item.get('stock'),
        "liked":        item.get('liked_count'),
        "brand":        item.get('brand') or None,
        "shop_name":    item.get('shop_name'),
        "description":  (item.get('description') or '')[:600],
        "images":       '\n'.join(img_urls),
    }

##########################################################################################
# Selenium helpers  (LOGIN ONLY — not used for scraping)
##########################################################################################

def get_chrome_major_version():
    try:
        if IS_WINDOWS:
            import winreg
            for hive, path in [
                (winreg.HKEY_CURRENT_USER,  r"Software\Google\Chrome\BLBeacon"),
                (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Google\Chrome\BLBeacon"),
                (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Wow6432Node\Google\Chrome\BLBeacon"),
            ]:
                try:
                    key = winreg.OpenKey(hive, path)
                    ver, _ = winreg.QueryValueEx(key, "version")
                    return int(ver.split('.')[0])
                except Exception:
                    continue
        else:
            chrome_bin = os.environ.get('CHROME_BIN', 'google-chrome')
            r = subprocess.run([chrome_bin, '--version'], capture_output=True, text=True, timeout=5)
            m = re.search(r'(\d+)\.\d+', r.stdout)
            if m:
                return int(m.group(1))
    except Exception:
        pass
    return None



def _dismiss_language_modal(driver):
    """
    Auto-dismiss Shopee's language selector if it appears.
    Tries JavaScript click first (bypasses scroll issues), then CSS selector.
    """
    try:
        # JS approach: find and click the OK / Confirm button regardless of scroll position
        dismissed = driver.execute_script("""
            // Try common button texts
            var texts = ['OK', 'Oke', 'Confirm', 'Continue', 'Lanjutkan'];
            for (var t of texts) {
                var els = Array.from(document.querySelectorAll('button, div[role="button"], span'));
                for (var el of els) {
                    if (el.innerText && el.innerText.trim().toUpperCase() === t.toUpperCase()) {
                        el.click();
                        return true;
                    }
                }
            }
            return false;
        """)
        if dismissed:
            time.sleep(1)
            return True
    except Exception:
        pass

    # CSS fallback
    for sel in ["button[class*='confirm']", "button[class*='ok']",
                "div[class*='language'] button", "button:last-of-type"]:
        try:
            btn = driver.find_element(By.CSS_SELECTOR, sel)
            driver.execute_script("arguments[0].scrollIntoView(true);", btn)
            time.sleep(0.3)
            btn.click()
            time.sleep(1)
            return True
        except Exception:
            continue
    return False

##########################################################################################
# Streamlit UI
##########################################################################################

def scrapper_shopee():

    if 'pg_step' not in st.session_state:
        st.session_state['pg_step'] = 1

    # ── Search form ──────────────────────────────────────────────────────────
    with st.form(key='shopee_form'):
        col_left, col_right = st.columns((1.4, 0.8))

        with col_left:
            search_text = st.text_area('Input ID / URL that you want to search')

        with col_right:
            search_param  = st.selectbox("Search by:", ("ID", "URL"))
            region_name   = st.selectbox("Region:", list(SHOPEE_DOMAIN_MAP.keys()))
            search_region = SHOPEE_DOMAIN_MAP[region_name]

        c1, c2, c3 = st.columns([0.8, 0.4, 0.4])
        with c1: search_but  = st.form_submit_button('Search Data')
        with c2: example_but = st.form_submit_button('Show Example')
        with c3: login_but   = st.form_submit_button('First Login')

        if search_but:
            st.session_state.update({'pg_step': 2, 'search_region': search_region,
                                     'search_text': str(search_text),
                                     'search_param': str(search_param)})
        if example_but:
            st.session_state['pg_step'] = 4
        if login_but:
            st.session_state.update({'pg_step': 5, 'search_region': search_region})

    # ── Search result ────────────────────────────────────────────────────────
    if st.session_state['pg_step'] == 2:
        search_region = st.session_state.get('search_region', 'shopee.co.id')
        search_text   = st.session_state.get('search_text', '').strip()
        search_param  = st.session_state.get('search_param', 'ID')

        if not search_text:
            st.warning(f'Please input {search_param} to search.')
            return

        st.write(f"🔍 Searching {search_param}: `{search_text}`")
        st.divider()

        # Parse IDs
        if search_param == "URL":
            m = re.search(r"i\.(\d+)\.(\d+)", search_text)
            if not m:
                st.error("Cannot extract shopid/itemid from URL.")
                return
            shopid, itemid = m.group(1), m.group(2)
        else:
            try:
                shopid, itemid = [p.strip() for p in search_text.split(",")]
            except ValueError:
                st.error("ID format must be: shopid,itemid")
                return

        st.success(f"✅ shopid: `{shopid}` · itemid: `{itemid}`")
        st.divider()

        # ── Fast cookie check (no browser) ───────────────────────────────────
        if not is_session_valid(search_region):
            st.error("🔒 No valid session for this region. Click **First Login** to authenticate.")
            return

        # ── Session health check (requests, no browser) ──────────────────────
        with st.spinner("Verifying session..."):
            ok, msg = verify_session_requests(search_region)
            if ok:
                st.success(f"✅ Session active · user: **{msg}**")
            else:
                st.warning(f"⚠️ Session check: {msg} — attempting scrape anyway.")

        # ── Fetch product via requests (no Selenium, no CAPTCHA) ─────────────
        with st.spinner("Fetching product data..."):
            item, err_or_device = fetch_product(shopid, itemid, search_region)

        # ── Fallback to browser if requests fail ─────────────────────────────
        if item is None and "403 Forbidden" in str(err_or_device):
            st.warning("⚠️ Requests failed (403 Forbidden). Retrying with a full browser...")
            with st.spinner("Fetching with browser... (this may take a moment)"):
                try:
                    item, err_or_device = fetch_product_with_browser(shopid, itemid, search_region)
                except Exception as e:
                    err_or_device = f"Browser fallback failed: {e}"

        if item is None:
            st.error(f"❌ {err_or_device}")
            # Save debug info
            try:
                with open(os.path.join(DEBUG_OUTPUT_PATH, "shopee_last_error.html"), 'w', encoding='utf-8') as f:
                    f.write(str(err_or_device))
            except Exception:
                pass
            return

        st.info(f"📱 Device used: {err_or_device}")

        result = parse_product(item, shopid, itemid, search_region)
        st.success("✅ Data scraped successfully!")

        # ── Display ──────────────────────────────────────────────────────────
        display = {k: v for k, v in result.items() if k != 'images'}
        df = pd.DataFrame([display])
        st.dataframe(df, use_container_width=True)

        if result.get('images'):
            st.subheader("📸 Product Images")
            for url in result['images'].split('\n'):
                if url:
                    st.write(url)

        csv = df.to_csv(index=False, sep=';')
        st.download_button(
            label="📥 Download CSV",
            data=csv,
            file_name=f"shopee_{itemid}.csv",
            mime="text/csv"
        )

    # ── Example ──────────────────────────────────────────────────────────────
    if st.session_state['pg_step'] == 4:
        st.subheader('Example Input')
        st.dataframe(pd.DataFrame({
            "Search Type": ["ID", "URL"],
            "How to Input": [
                "shopid,itemid  →  e.g. 12345,987654321",
                "Full URL  →  e.g. https://shopee.co.id/Some-Product-i.12345.987654321"
            ]
        }), use_container_width=True)

    # ── Login ─────────────────────────────────────────────────────────────────
    if st.session_state['pg_step'] == 5:
        _do_login()

# ─────────────────────────────────────────────────────────────────────────────
# Login helpers
# ─────────────────────────────────────────────────────────────────────────────

def _do_login():
    search_region = st.session_state.get('search_region', 'shopee.co.id')
    st.subheader("🔐 Shopee Login")

    st.info("""
    **Docker / server users:** Run login locally on Windows first, then copy the cookie file:
    ```
    scp modules/output/shopee_cookies_shopee_co_id.json user@server:/path/to/app/modules/output/
    ```
    """)

    method = st.radio("Login method:", ["Email / Password", "QR Code (requires Shopee mobile app)"],
                      horizontal=True)

    if method.startswith("Email"):
        with st.form("credential_form"):
            email    = st.text_input("Email or phone number")
            password = st.text_input("Password", type="password")
            submit   = st.form_submit_button("Login")
        if submit:
            if not email or not password:
                st.warning("Please enter both email and password.")
            else:
                _login_with_credentials(search_region, email, password)
    else:
        _login_with_qr(search_region)

def _take_screenshot(driver, name="login_state.png"):
    screenshot_dir = os.path.join(main_folder, "screenshots")
    os.makedirs(screenshot_dir, exist_ok=True)
    path = os.path.join(screenshot_dir, name)
    driver.save_screenshot(path)
    if os.path.exists(path):
        st.image(path, use_container_width=True)
    return path

def _wait_for_auth_cookies(driver, timeout=120):
    """Poll until Shopee auth cookies appear. Returns True if logged in."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        jar = {c['name']: c['value'] for c in driver.get_cookies()}
        if 'SPC_EC' in jar or 'SPC_ST' in jar:
            return True
        time.sleep(1)
    return False

def _login_with_credentials(region, email, password):
    """
    Open a visible browser, auto-type credentials, handle OTP manually.

    Strategy (anti-detection):
      - Human-like typing speed (random 50–150 ms per character)
      - Random pause between email and password fields
      - Mobile device emulation (same as scraping fingerprint)
      - If OTP / CAPTCHA appears: screenshot is shown, user completes it
        in the visible browser window — no automation needed for that step.
    """
    driver = None
    try:
        with st.spinner("Opening browser..."):
            driver = _start_login_driver(region=region)

        driver.get(f"https://{region}/buyer/login")
        time.sleep(random.uniform(4, 6))

        # Dismiss language/onboarding modal if present
        if _dismiss_language_modal(driver):
            _simulate_human_interaction(driver) # Add human-like pause/scroll
            st.write("ℹ️ Language selector dismissed automatically.")
            time.sleep(2)

        _take_screenshot(driver, "login_page.png")

        # ── Type email ────────────────────────────────────────────────────────
        try:
            email_field = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR,
                    "input[name='loginKey'], input[type='text'], input[type='email']"))
            )
            email_field.click()
            time.sleep(random.uniform(0.3, 0.6))
            for ch in email:
                email_field.send_keys(ch)
                time.sleep(random.uniform(0.05, 0.15))
            time.sleep(random.uniform(0.5, 1.0))
        except Exception as e:
            st.warning(f"⚠️ Could not auto-fill email: {e}. Please type it in the browser window.")

        # ── Type password ─────────────────────────────────────────────────────
        try:
            pwd_field = driver.find_element(By.CSS_SELECTOR, "input[type='password']")
            pwd_field.click()
            time.sleep(random.uniform(0.3, 0.6))
            for ch in password:
                pwd_field.send_keys(ch)
                time.sleep(random.uniform(0.05, 0.12))
            time.sleep(random.uniform(0.5, 1.0))
        except Exception as e:
            st.warning(f"⚠️ Could not auto-fill password: {e}. Please type it in the browser window.")

        # ── Submit ────────────────────────────────────────────────────────────
        try:
            btn = driver.find_element(By.CSS_SELECTOR,
                "button[type='submit'], button[class*='btn-solid'], div[class*='submit']")
            btn.click()
        except Exception:
            # Fallback: press Enter in password field
            try:
                from selenium.webdriver.common.keys import Keys
                driver.find_element(By.CSS_SELECTOR, "input[type='password']").send_keys(Keys.RETURN)
            except Exception:
                st.warning("⚠️ Could not click submit. Please press Enter in the browser window.")

        time.sleep(4)
        _take_screenshot(driver, "after_submit.png")

        st.info("""
        ⏳ **Waiting for login to complete (up to 2 min).**

        If an OTP, CAPTCHA, or verification step appeared in the browser — complete it manually.
        The session will be saved automatically once Shopee confirms the login.
        """)

        logged_in = _wait_for_auth_cookies(driver, timeout=120)

        if not logged_in:
            st.error("⏱️ Login timed out. Check the screenshot above and try again.")
            _take_screenshot(driver, "login_timeout.png")
            return

        time.sleep(3)  # let Shopee issue all session cookies
        save_cookies(driver, region=region)
        st.success("🎉 Cookies saved — ready to scrape!")

    except Exception as e:
        st.error(f"❌ Login error: {e}")
        import traceback
        st.code(traceback.format_exc())
    finally:
        if driver:
            try:
                driver.quit()
            except Exception:
                pass

    st.session_state['pg_step'] = 1
    time.sleep(1)
    st.rerun()

def _login_with_qr(region):
    """QR code login — requires Shopee mobile app to scan."""
    driver = None
    try:
        with st.spinner("Opening browser..."):
            driver = _start_login_driver(region=region)

        driver.get(
            f"https://{region}/buyer/login/qr?"
            f"next=https%3A%2F%2F{region}%2F"
        )
        time.sleep(8)

        # Dismiss language/onboarding modal if present
        if _dismiss_language_modal(driver):
            _simulate_human_interaction(driver) # Add human-like pause/scroll
            st.write("ℹ️ Language selector dismissed automatically.")
            time.sleep(4)

        _take_screenshot(driver, "qr_login.png")
        st.caption("📱 Open Shopee app → Profile → Scan QR")

        st.info("⏳ Waiting for QR scan… (90 s timeout)")
        logged_in = _wait_for_auth_cookies(driver, timeout=90)

        if not logged_in:
            st.error("⏱️ Login timeout (90 s). Please try again.")
            return

        time.sleep(3)
        save_cookies(driver, region=region)
        st.success("🎉 Cookies saved — ready to scrape!")

    except Exception as e:
        st.error(f"❌ Login error: {e}")
        import traceback
        st.code(traceback.format_exc())
    finally:
        if driver:
            try:
                driver.quit()
            except Exception:
                pass

    st.session_state['pg_step'] = 1
    time.sleep(1)
    st.rerun()
