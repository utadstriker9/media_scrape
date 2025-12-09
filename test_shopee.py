import undetected_chromedriver as uc
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time
import os


##########################################################################################

current_script_path = os.path.abspath(__file__)
main_folder = os.path.dirname(current_script_path)
session_path = os.path.join(main_folder, 'modules', 'output', 'shopee_sessions')

def start_driver():
    options = Options()
    options.add_argument(f"--user-data-dir={session_path}")
    options.add_argument("--profile-directory=Default")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=412,915")  

    driver = uc.Chrome(
        options=options,
        headless=False,
        version_main=143,    
    )
    return driver

##########################################################################################


if __name__ == "__main__":
    driver = start_driver()
    driver.get("https://shopee.co.id/")
    time.sleep(60) 
