# import streamlit as st
# from helpers.rotate_device import ANDROID_DEVICES
# import random
# import re
# import json
# import pandas as pd
# import time
# from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
# import os

# ####################################################################################################

# current_script_path = os.path.abspath(__file__)
# main_folder = os.path.dirname(current_script_path)

# def load_cookies():
#     path = os.path.join(main_folder, 'output', 'tiktok_cookie.json')
#     with open(path, 'r', encoding='utf-8') as f:
#         raw = json.load(f)

#     # If file is already a Playwright-style list, return as-is
#     if isinstance(raw, list) and raw and 'name' in raw[0]:
#         return raw

#     # Common chrome-export formats (e.g. from some extensions) might be dict keyed by name
#     # Normalize to Playwright format
#     normalized = []
#     if isinstance(raw, dict):
#         # e.g. {"cookies": [...]} or {"example.com": {"name":"value", ...}}
#         possible = raw.get('cookies') or raw.get('cookie') or None
#         if possible and isinstance(possible, list):
#             raw = possible

#     if isinstance(raw, list):
#         for c in raw:
#             # accept forms: {name, value, domain, path, expires}
#             name = c.get('name') or c.get('key') or c.get('cookieName') or None
#             value = c.get('value') or c.get('cookie') or c.get('cookieValue') or None
#             domain = c.get('domain') or c.get('host') or c.get('hostOnly') or None
#             path = c.get('path') or '/'
#             expires = c.get('expires')
#             # convert boolean hostOnly to domain starting without dot if needed
#             if domain and not domain.startswith('.'):
#                 # Playwright accepts either, but ensure domain has leading dot for subdomains
#                 domain = domain if domain.startswith('.') else '.' + domain

#             if not name or value is None or domain is None:
#                 # skip invalid
#                 continue

#             cookie = {
#                 "name": name,
#                 "value": value,
#                 "domain": domain,
#                 "path": path
#             }
#             if expires:
#                 try:
#                     cookie["expires"] = int(expires)
#                 except:
#                     pass
#             normalized.append(cookie)

#     return normalized

# class TikTokScraper:
#     VIDEO_RE = r"tiktok\.com/.*/video/(\d+)"
#     USER_RE = r"tiktok\.com/@([A-Za-z0-9._]+)"

#     def __init__(self, headless=False, debug=False):
#         self.cookies = load_cookies()
#         self.headless = headless
#         self.debug = debug

#     def detect(self, raw):
#         raw = raw.strip()
#         m = re.search(self.VIDEO_RE, raw)
#         if m:
#             return {"type": "video", "video_id": m.group(1)}
#         m = re.search(self.USER_RE, raw)
#         if m:
#             return {"type": "user", "username": m.group(1)}
#         if raw.isdigit():
#             return {"type": "video", "video_id": raw}
#         if raw.startswith("@"):
#             return {"type": "user", "username": raw[1:]}
#         return {"type": "user", "username": raw}

#     def _new_context(self, browser):
#         # pick random device
#         device = random.choice(ANDROID_DEVICES)

#         context = browser.new_context(
#             user_agent=device["user_agent"],
#             viewport=device["viewport"],
#             device_scale_factor=device.get("device_scale_factor", device.get("scale", 2.5)),
#             is_mobile=True,
#             has_touch=True,
#             locale="en-US",
#             bypass_csp=True,
#             java_script_enabled=True,
#             extra_http_headers={
#                 "Accept-Language": "en-US,en;q=0.9",
#                 "Referer": "https://www.tiktok.com/",
#                 # Sec-CH UA headers reduce suspicion
#                 "Sec-CH-UA-Platform": "\"Android\""
#             }
#         )

#         # Playwright expects cookie objects with at least: name, value, domain, path
#         try:
#             if isinstance(self.cookies, list):
#                 # ensure cookies domain is set to .tiktok.com if not present
#                 to_add = []
#                 for c in self.cookies:
#                     cookie = c.copy()
#                     if 'domain' not in cookie or not cookie['domain']:
#                         cookie['domain'] = '.tiktok.com'
#                     if 'path' not in cookie:
#                         cookie['path'] = '/'
#                     to_add.append(cookie)
#                 context.add_cookies(to_add)
#         except Exception as e:
#             print("Failed adding cookies:", e)

#         # small stealth: override navigator.webdriver etc
#         context.add_init_script("""
#             Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
#             Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});
#             Object.defineProperty(navigator, 'plugins', {get: () => [1,2,3,4,5]});
#         """)
#         return context

#     def _fetch_sigi_state(self, page, timeout=15000):
#         # trigger some human-like activity
#         try:
#             page.wait_for_timeout(1000)
#             page.evaluate("window.scrollBy(0, 200)")
#             page.wait_for_timeout(1000)
#         except Exception:
#             pass

#         # Wait for SIGI_STATE script to appear
#         try:
#             page.wait_for_selector("script[id='SIGI_STATE']", timeout=timeout)
#         except PlaywrightTimeout:
#             # Still continue to grab content for debug
#             pass

#         html = page.content()
#         if self.debug:
#             print("HTML head snippet:", html[:2000])

#         # regex search multiline
#         m = re.search(r'<script id="SIGI_STATE"[^>]*>(.*?)</script>', html, re.S)
#         if not m:
#             return None
#         try:
#             return json.loads(m.group(1))
#         except Exception:
#             # sometimes content is escaped or partial — return None for upstream handling
#             return None

#     # --- SCRAPE VIDEO DETAILS ---
#     def get_video(self, video_id):
#         # use generic video URL (works without username)
#         url = f"https://www.tiktok.com/video/{video_id}"

#         with sync_playwright() as pw:
#             # use Chromium with some launch args to reduce bot detection
#             browser = pw.chromium.launch(
#                 headless=self.headless,
#                 args=[
#                     "--disable-blink-features=AutomationControlled",
#                     "--no-sandbox",
#                     "--disable-dev-shm-usage"
#                 ]
#             )
#             ctx = self._new_context(browser)
#             page = ctx.new_page()

#             try:
#                 page.goto(url, wait_until="domcontentloaded", timeout=30000)
#             except Exception as e:
#                 # try a second time
#                 print("goto error:", e)
#                 try:
#                     page.goto(url, wait_until="domcontentloaded", timeout=30000)
#                 except Exception as e2:
#                     print("second goto failed:", e2)
#                     ctx.close()
#                     browser.close()
#                     return None

#             data = self._fetch_sigi_state(page)
#             ctx.close()
#             browser.close()

#         if not data:
#             return None

#         # pick item
#         try:
#             # ItemModule keys are video IDs or small id strings
#             if "ItemModule" in data:
#                 # find matching item
#                 if video_id in data["ItemModule"]:
#                     item = data["ItemModule"][video_id]
#                 else:
#                     # fallback: first item
#                     vid_key = next(iter(data["ItemModule"]))
#                     item = data["ItemModule"][vid_key]
#             else:
#                 return None

#             return {
#                 "video_id": video_id,
#                 "author": item.get("author"),
#                 "desc": item.get("desc"),
#                 "create_time": item.get("createTime"),
#                 "stats": item.get("stats"),
#                 "video_url": item.get("video", {}).get("downloadAddr"),
#                 "cover": item.get("video", {}).get("cover")
#             }
#         except Exception as e:
#             print("parsing item error:", e)
#             return None

#     # --- SCRAPE PROFILE ---
#     def get_user(self, username):
#         url = f"https://www.tiktok.com/@{username}"

#         with sync_playwright() as pw:
#             browser = pw.chromium.launch(
#                 headless=self.headless,
#                 args=[
#                     "--disable-blink-features=AutomationControlled",
#                     "--no-sandbox",
#                     "--disable-dev-shm-usage"
#                 ]
#             )
#             ctx = self._new_context(browser)
#             page = ctx.new_page()

#             try:
#                 page.goto(url, wait_until="domcontentloaded", timeout=30000)
#             except Exception as e:
#                 print("goto error:", e)
#                 try:
#                     page.goto(url, wait_until="domcontentloaded", timeout=30000)
#                 except Exception as e2:
#                     print("second goto failed:", e2)
#                     ctx.close()
#                     browser.close()
#                     return None

#             data = self._fetch_sigi_state(page)
#             ctx.close()
#             browser.close()

#         if not data:
#             return None

#         try:
#             user = list(data.get("UserModule", {}).get("users", {}).values())[0]
#             stats = list(data.get("UserModule", {}).get("stats", {}).values())[0]
#             return {
#                 "username": user.get("uniqueId"),
#                 "nickname": user.get("nickname"),
#                 "avatar": user.get("avatarMedium"),
#                 "followers": stats.get("followerCount"),
#                 "following": stats.get("followingCount"),
#                 "hearts": stats.get("heartCount"),
#             }
#         except Exception as e:
#             print("parse user error:", e)
#             return None

# ####################################################################################################

# def scrapper_tiktok():

#     if 'pg_step' not in st.session_state:
#         st.session_state['pg_step'] = 1

#     # --- SEARCH FORM ---
#     with st.form(key='tiktok_form'):
#         bol, bol2 = st.columns((1.4, 0.8))

#         with bol:
#             search_text = st.text_area('Input ID / URL / Username that you want to search')
#             search_text = str(search_text)

#         with bol2:
#             search_param = st.selectbox("Search by:", ("ID", "URL", "Username"))
#             search_param = str(search_param)

#         bolls1, bolls2 = st.columns([0.3, 1.4])

#         with bolls1:
#             search_but = st.form_submit_button(label='Search Data')

#         with bolls2:
#             example_but = st.form_submit_button(label='Show Example')

#         if search_but:
#             st.session_state['pg_step'] = 2
#         if example_but:
#             st.session_state['pg_step'] = 4

#     # --- SEARCH RESULT ---
#     if st.session_state['pg_step'] == 2:

#         if not search_text.strip():
#             st.warning(f'Please input {search_param} that you want to search!')
#             return

#         st.write(f"Search Result for {search_param}: {search_text}")
#         st.divider()

#         parser = TikTokScraper()
#         detected = parser.detect(search_text)
#         st.info(f"Auto detected: {detected}")

#         if detected["type"] == "video":
#             data = parser.get_video(detected["video_id"])
#             ids_tiktok = detected["video_id"]

#         elif detected["type"] == "user":
#             data = parser.get_user(detected["username"])
#             ids_tiktok = detected["username"]

#         else:
#             st.error("Unable to detect input type.")
#             return

#         if not data:
#             st.error("Failed to extract TikTok data.")
#             return

#         st.success(f"Extracted IDs → {ids_tiktok}")
#         st.divider()

#         # ---- BUILD RECORD ----
#         record = data

#         # Display table
#         df = pd.DataFrame([record])
#         st.dataframe(df)

#         # Download CSV
#         csv_data = df.to_csv(index=False, sep=';')
#         st.download_button(
#             label="📥 Download as CSV",
#             data=csv_data,
#             file_name=f"tiktok_{ids_tiktok}.csv",
#             mime="text/csv"
#         )

#     # --- SHOW EXAMPLE ---
#     if st.session_state['pg_step'] == 4:
#         st.subheader('Example TikTok Scrapper')
#         example_data = {
#             "Search Type": ["ID", "URL","Username"],
#             "How to Input": [
#                 "Example: https://www.tiktok.com/@mat_clayy/video/7553966154146942264?_r=1&_t=ZS-91V9LNC2QXI -> 7553966154146942264",
#                 "Example: https://www.tiktok.com/@mat_clayy/video/7553966154146942264?_r=1&_t=ZS-91V9LNC2QXI",
#                 "Example: https://www.tiktok.com/@mat_clayy/video/7553966154146942264?_r=1&_t=ZS-91V9LNC2QXI -> @mat_clayy"
#             ]
#         }
#         st.dataframe(pd.DataFrame(example_data))
