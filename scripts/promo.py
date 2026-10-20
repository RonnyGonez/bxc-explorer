"""Record a phone-sized run-through of the live explorer for a short promo video.

Writes promo/raw.webm and promo/steps.json (when each step starts, in seconds).
"""
import json
import os
import shutil
import time

from playwright.sync_api import sync_playwright

URL = os.environ.get("SITE", "https://ronnygonez.github.io/bxc-explorer/")
OUT = os.path.join(os.path.dirname(__file__), "..", "promo")
os.makedirs(OUT, exist_ok=True)

with sync_playwright() as p:
    b = p.chromium.launch(args=["--autoplay-policy=no-user-gesture-required"])
    ctx = b.new_context(viewport={"width": 390, "height": 693}, device_scale_factor=3, is_mobile=True, has_touch=True,
                        user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1",
                        record_video_dir=OUT, record_video_size={"width": 1080, "height": 1920})
    pg = ctx.new_page()
    t0 = time.time()
    steps = []
    mark = lambda name: steps.append({"step": name, "t": round(time.time() - t0, 2)})
    pg.goto(URL, wait_until="networkidle")
    pg.wait_for_timeout(1800)
    mark("mood")
    pg.select_option("#moodSel", "party")
    pg.wait_for_timeout(1900)
    mark("filters")
    pg.click("#filtersBtn")
    pg.wait_for_timeout(900)
    pg.locator("#genres .chip").nth(0).tap()
    pg.wait_for_timeout(1100)
    pg.click("#filtersBtn")
    pg.wait_for_timeout(700)
    mark("browse")
    pg.mouse.wheel(0, 260)
    pg.wait_for_timeout(1500)
    pg.mouse.wheel(0, -120)
    pg.wait_for_timeout(600)
    mark("play")
    pg.click("#playall")
    pg.wait_for_timeout(7500)
    mark("skip")
    pg.click("#next")
    pg.wait_for_timeout(5500)
    mark("end")
    pg.wait_for_timeout(300)
    video = pg.video.path()
    ctx.close()
    b.close()
shutil.move(video, os.path.join(OUT, "raw.webm"))
json.dump(steps, open(os.path.join(OUT, "steps.json"), "w"), indent=1)
print(steps)
