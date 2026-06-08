import random
import asyncio

async def random_scroll(page):
    for _ in range(random.randint(1, 3)):
        await page.mouse.wheel(0, random.randint(200, 900))
        await asyncio.sleep(random.uniform(0.4, 1.2))

async def simulate_touch(page):
    await page.evaluate("""() => {
        document.dispatchEvent(new TouchEvent('touchstart', { touches: [new Touch({ identifier: 1, target: document.body })] }));
        document.dispatchEvent(new TouchEvent('touchend', { changedTouches: [new Touch({ identifier: 1, target: document.body })] }));
    }""")

async def is_captcha(page):
    content = await page.content()
    return "captcha" in content.lower() or "verify" in page.url

async def human_sleep():
    await asyncio.sleep(random.uniform(1.5, 4.2))

async def backoff_retry(attempt):
    await asyncio.sleep(2 ** attempt + random.random())
