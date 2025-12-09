import random, time

async def random_scroll(page):
    for _ in range(random.randint(1, 3)):
        await page.mouse.wheel(0, random.randint(200, 900))
        time.sleep(random.uniform(0.4, 1.2))

async def simulate_touch(page):
    await page.add_script_tag(content="""
        document.dispatchEvent(new TouchEvent('touchstart', { touches: [{}] }));
        document.dispatchEvent(new TouchEvent('touchend', { touches: [{}] }));
    """)

def is_captcha(page):
    return "captcha" in page.content().lower() or "verify" in page.url

def human_sleep():
    time.sleep(random.uniform(1.5, 4.2))

def backoff_retry(attempt):
    time.sleep(2 ** attempt + random.random())


