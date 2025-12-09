from playwright.sync_api import sync_playwright
import json, time

def playwright_login():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0 Mobile Safari/537.36",
            viewport={"width": 390, "height": 844},
            device_scale_factor=3,
            is_mobile=True,
            has_touch=True,
            locale="en-US",
            timezone_id="Asia/Jakarta",
            permissions=["geolocation"],
        )


        page = context.new_page()
        page.goto("https://www.tiktok.com/login")

        print("Please complete login manually...")
        page.wait_for_selector('[data-e2e="profile-icon"]', timeout=0)

        print("Login detected! Saving cookies...")

        cookies = context.cookies()

        with open("tiktok_cookie.json", "w", encoding="utf8") as f:
            json.dump(cookies, f, indent=2)

        print("Cookies saved successfully!")

        context.close()
        browser.close()

if __name__ == "__main__":
    playwright_login()
