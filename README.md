# Media Scrape

Media Scrape is a scraping toolkit for extracting product and media data from Shopee.  
It is designed to run fully inside Docker and provides a simple Streamlit UI for scraping, viewing, and exporting results.

---

## 🚀 Getting Started

### 1. Build the Docker Image
```bash
sudo docker build -f DockerFile -t media_scrape .
```

### 2. Run the Docker Container
```bash
sudo docker run -d \
  -p 8801:8801 \
  --name media_scrape \
  --shm-size="2g" \
  -v "$(pwd)/modules/output:/media_scrape/modules/output" \
  media_scrape
```
> The `-v` volume mount keeps your cookie files alive across container rebuilds.  
> Or just run `bash rerun_app.sh` which does all of the above automatically.

### 3. Open the Application
```
http://localhost:8801
```

---

## 🛒 Shopee Scraper Workflow

### Step 1 — Open the Shopee Scraper Page
Navigate to the **Shopee Scrapper** tab from the UI.  
![First Screenshot](https://raw.githubusercontent.com/utadstriker9/media_scrape/main/screenshots/first.png)

### Step 2 — Login (First-Time Only)
> ⚠️ QR login requires a visible browser. **Do this locally on Windows**, not inside Docker.

Click **First Login**, scan the QR code with the Shopee app, then copy the generated cookie file to your server:
```bash
scp modules/output/shopee_cookies_shopee_co_id.json user@server:/path/to/app/modules/output/
```
Cookie files are region-specific. If you scrape multiple regions, login once per region.

![Second Screenshot](https://raw.githubusercontent.com/utadstriker9/media_scrape/main/screenshots/second.png)
![Third Screenshot](https://raw.githubusercontent.com/utadstriker9/media_scrape/main/screenshots/third.png)

### Step 3 — Input Product ID or URL
Paste any Shopee product ID (`shopid,itemid`) or full item URL.  
![Fourth Screenshot](https://raw.githubusercontent.com/utadstriker9/media_scrape/main/screenshots/fourth.png)

### Step 4 — View & Download Output
Scraped data appears in the table and can be downloaded as a CSV file.  
![Output Screenshot](https://raw.githubusercontent.com/utadstriker9/media_scrape/main/screenshots/five.png)

---

## 🎯 Key Features

| Feature | Status |
|---|---|
| Shopee product scraper | ✅ Active |
| Mobile device emulation | ✅ Active |
| Device fingerprint rotation | ✅ Active |
| JSON-first data extraction | ✅ Active |
| Session health check | ✅ Active |
| Per-region cookie management | ✅ Active |
| TikTok media scraper | 🔧 Maintenance |

---

## 🛡️ Anti-Detection Strategy

Shopee runs aggressive bot detection. This section documents every layer of defence used or planned in this project.

---

### 1. Simulating a Real Mobile Session

**Why it matters:** Shopee's desktop web applies stricter bot detection than its mobile web. A headless desktop Chrome browser is one of the most-detected configurations. Mobile sessions have a dramatically lower CAPTCHA trigger rate.

**How it's implemented:**

Every scraping session picks a random Android device from `helpers/rotate_device.py` and applies it via Chrome DevTools Protocol (CDP) **after** the driver is created:

```python
# In start_driver(mobile_mode=True)
driver.execute_cdp_cmd("Emulation.setDeviceMetricsOverride", {
    "mobile": True,
    "width": 412, "height": 892,
    "deviceScaleFactor": 2.625,
    "screenOrientation": {"type": "portraitPrimary", "angle": 0},
})
driver.execute_cdp_cmd("Emulation.setTouchEmulationEnabled", {
    "enabled": True, "maxTouchPoints": 5
})
```

The `navigator.maxTouchPoints` JS property is also overridden to `5`, matching a real Android device. Without this, the JS fingerprint would still report `0` (desktop) even with CDP emulation.

---

### 2. Rotating Device Fingerprints

**Why it matters:** Repeatedly sending the exact same user agent, viewport, and screen size creates a fingerprint that Shopee's ML models can flag as a bot — especially across multiple requests.

**How it's implemented:**

`helpers/rotate_device.py` defines 8 real Android device profiles. Each new browser session picks one randomly via `_pick_device()` in `shopee_scrapper.py`:

```python
ANDROID_DEVICES = [
    { "name": "Samsung S21",      "user_agent": "...", "viewport": {"width": 412, "height": 915}, "scale": 3 },
    { "name": "Pixel 7",          "user_agent": "...", "viewport": {"width": 412, "height": 892}, "scale": 2.625 },
    { "name": "Xiaomi Redmi Note 12", ... },
    # ... 5 more
]
```

Each profile changes: `User-Agent`, `window-size`, `deviceScaleFactor`, `maxTouchPoints`, and the viewport override sent to Shopee's servers.

**To extend:** Add more devices to `ANDROID_DEVICES`. Use real UA strings from [useragentstring.com](https://www.useragentstring.com/) or Chrome DevTools mobile presets.

---

### 3. Avoiding Rate Limits

**Why it matters:** Sending requests too fast or too regularly creates traffic patterns that are trivially detectable. Shopee rate-limits by IP and session token.

**How it's implemented:**

- **Random delays** between every major action — page load, scroll, click:
  ```python
  time.sleep(random.uniform(2, 4))   # before navigating
  time.sleep(random.uniform(4, 6))   # after page load
  time.sleep(random.uniform(0.8, 1.5))  # between scroll events
  ```

- **`simulate_human_interaction(driver)`** — called after every page load. Performs a smooth scroll down, pause, scroll back up, and a random touch tap at a random screen coordinate.

**What's not yet implemented (planned):**

- **Proxy rotation:** Route each session through a different residential IP using a proxy pool (e.g. Bright Data, Oxylabs, or a free list with `requests[socks]`). Without this, all requests come from one IP and can be blocked at the network level regardless of browser fingerprint.
  ```python
  options.add_argument("--proxy-server=socks5://user:pass@proxy_host:port")
  ```

- **Request budget per session:** Limit how many products are scraped per browser instance before creating a new one with a fresh fingerprint.

---

### 4. Refreshing Tokens / Session Cookies

**Why it matters:** Shopee's `SPC_ST` (session token) expires in ~24 hours. `SPC_EC` lasts ~30 days. When `SPC_ST` expires, every request returns a login redirect — even if the cookies file exists on disk.

**How it's implemented:**

- `is_session_valid(region)` reads the cookie file and checks the `expiry` Unix timestamp of every auth cookie **before** starting a browser. If any auth cookie is expired, it shows a re-login prompt immediately (no browser wasted).

- `load_cookies()` also validates expiry before injecting and returns `False` early if expired.

- A lightweight session health check hits `/api/v4/account/basic/get_username_info` after cookie injection to confirm the session is live before loading the product page.

**What's not yet implemented (planned):**

Full automatic token refresh would require:
1. Detecting when `SPC_ST` is close to expiry (e.g. < 2 hours remaining)
2. Opening a visible browser, navigating to Shopee while already logged in (using `SPC_EC` which lasts longer)
3. Letting Shopee issue a new `SPC_ST` automatically via its normal session refresh flow
4. Saving the updated cookies back to disk

This is complex because it requires a non-headless browser step. The practical alternative is to re-login via QR every ~20 hours.

---

### 5. Solving CAPTCHA

**Why it matters:** Shopee shows a sliding-puzzle or image CAPTCHA when it detects suspicious traffic. The current code detects CAPTCHA and stops — it does not solve it.

**What's implemented:**

- CAPTCHA detection: checks if `"verify"` or `"captcha"` appears in the current URL after navigation. If detected, saves a screenshot and aborts with a clear error message.

**What's not yet implemented — options ranked by effort:**

| Option | Effort | Cost | Notes |
|---|---|---|---|
| **Mobile emulation** (already done) | Low | Free | Prevents most CAPTCHAs from appearing at all |
| **2Captcha / Anti-Captcha service** | Medium | ~$1–3 per 1000 solves | Sends CAPTCHA image to human solvers via API; ~15–30 sec solve time |
| **CapSolver / NoCaptchaAI** | Medium | Similar | Supports Shopee's slider CAPTCHA specifically |
| **Puppeteer-extra-plugin-recaptcha** | High | Per-solve | Node.js only; not directly usable here |
| **Manual intervention** | Low | Free | Show CAPTCHA screenshot in UI, wait for human to solve and click |

**2Captcha integration sketch (not yet active):**
```python
import requests

def solve_captcha_2captcha(api_key, site_key, page_url):
    # Submit
    resp = requests.post("http://2captcha.com/in.php", data={
        "key": api_key, "method": "userrecaptcha",
        "googlekey": site_key, "pageurl": page_url, "json": 1
    })
    task_id = resp.json()["request"]
    # Poll for result
    for _ in range(20):
        time.sleep(5)
        result = requests.get(
            f"http://2captcha.com/res.php?key={api_key}&action=get&id={task_id}&json=1"
        ).json()
        if result["status"] == 1:
            return result["request"]  # solved token
    return None
```

---

### 6. Mimicking Touch Events and App-like Behaviour

**Why it matters:** A real Shopee mobile user scrolls, taps, pauses, and swipes. A bot that just instantly navigates to a URL with no interaction is trivially detectable by Shopee's behavioural analysis layer.

**How it's implemented:**

`simulate_human_interaction(driver)` is called after every page load:
```python
def simulate_human_interaction(driver):
    # Smooth scroll down
    driver.execute_script("window.scrollTo({top: 400, behavior: 'smooth'});")
    time.sleep(random.uniform(0.8, 1.5))
    # Scroll back up
    driver.execute_script("window.scrollTo({top: 0, behavior: 'smooth'});")
    time.sleep(random.uniform(0.5, 1.0))
    # Dispatch a real TouchEvent at a random screen position
    driver.execute_script("""
        var touch = new Touch({ identifier: ..., target: document.body,
            clientX: 150, clientY: 300, radiusX: 5, radiusY: 5, force: 1 });
        document.dispatchEvent(new TouchEvent('touchstart', { touches: [touch], bubbles: true }));
        document.dispatchEvent(new TouchEvent('touchend',   { changedTouches: [touch], bubbles: true }));
    """)
```

`helpers/action_device.py` provides async versions (`random_scroll`, `simulate_touch`, `human_sleep`, `backoff_retry`) for use with Playwright-based scrapers (TikTok).

**What's not yet implemented (planned):**

- **Realistic swipe gestures:** A real finger swipe has a start point, several intermediate pointer events, and an end point. Selenium's `ActionChains` or CDP `Input.dispatchTouchEvent` can simulate this.
- **Idle dwell time:** Real users spend 10–30 seconds reading a product page before leaving. Currently the scraper exits as soon as data is extracted. Adding a `time.sleep(random.uniform(8, 20))` before `driver.quit()` would make the session look more human to server-side analytics.
- **Network condition emulation:** CDP can throttle bandwidth to match a 4G connection: `Network.emulateNetworkConditions`. This makes request timing realistic for a mobile user.

---

## 📂 Output Files

| File | Description |
|---|---|
| `modules/output/shopee_cookies_<region>.json` | Login session cookies per region |
| `modules/screenshots/debug_page.png` | Screenshot of last scraped page |
| `modules/screenshots/captcha_page.png` | Screenshot when CAPTCHA is detected |
| `modules/output/shopee_debug_source.html` | Raw HTML saved when scrape yields no data |

---

## 🧱 Tech Stack

| Layer | Technology |
|---|---|
| UI | Streamlit |
| Browser automation | undetected-chromedriver + Selenium |
| Anti-detection | CDP mobile emulation, UA rotation, JS injection |
| Containerisation | Docker |
| Language | Python 3.11 |

---

## 📌 Roadmap

- Instagram support  
- Shopee shop-level and review scraping  
- TikTok trending feed scraper  
- Proxy rotation management  
- Automatic CAPTCHA solving via CapSolver  
