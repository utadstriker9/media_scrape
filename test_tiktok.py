from playwright.sync_api import sync_playwright
import json, os

current_script_path = os.path.abspath(__file__)
main_folder = os.path.dirname(current_script_path)
output_dir = os.path.join(main_folder, 'modules', 'output')
cookie_path = os.path.join(output_dir, 'tiktok_cookie.json')

def playwright_login():
    os.makedirs(output_dir, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.6312.122 Mobile Safari/537.36",
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

        with open(cookie_path, "w", encoding="utf-8") as f:
            json.dump(cookies, f, indent=2)

        print(f"Cookies saved to {cookie_path}")

        context.close()
        browser.close()

if __name__ == "__main__":
    playwright_login()
