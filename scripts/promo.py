"""Record a phone-sized run-through of the live explorer for a short promo video.

Captures sharp frames straight from the browser (at 3x, like a real phone screen) and
writes promo/raw.mp4 plus promo/steps.json (when each step starts, in seconds).
"""
import base64
import subprocess
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
                        user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1")
    pg = ctx.new_page()
    frames = []
    cdp = ctx.new_cdp_session(pg)

    def on_frame(ev):
        frames.append((ev["metadata"]["timestamp"], ev["data"]))
        cdp.send("Page.screencastFrameAck", {"sessionId": ev["sessionId"]})

    cdp.on("Page.screencastFrame", on_frame)
    cdp.send("Page.startScreencast", {"format": "jpeg", "quality": 88, "maxWidth": 1170, "maxHeight": 2079})
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
    cdp.send("Page.stopScreencast")
    ctx.close()
    b.close()

# Turn the frames (sent only when the screen changes) into a steady 30fps video.
fdir = os.path.join(OUT, "frames")
shutil.rmtree(fdir, ignore_errors=True)
os.makedirs(fdir)
lines = []
start = frames[0][0]
# screencast timestamps are wall-clock seconds; make step times relative to the first frame
steps = [dict(s, t=round(s["t"] - (start - t0), 2)) for s in steps]
for k, (ts, data) in enumerate(frames):
    name = f"{k:05d}.jpg"
    open(os.path.join(fdir, name), "wb").write(base64.b64decode(data))
    dur = (frames[k + 1][0] - ts) if k + 1 < len(frames) else 0.5
    lines += [f"file 'frames/{name}'", f"duration {max(dur, 0.001):.4f}"]
lines.append(f"file 'frames/{len(frames) - 1:05d}.jpg'")
open(os.path.join(OUT, "frames.txt"), "w").write("\n".join(lines) + "\n")
subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", "frames.txt",
                "-vf", "fps=30,scale=1080:1920:flags=lanczos,format=yuv420p", "-c:v", "libx264", "-crf", "18", "raw.mp4"],
               cwd=OUT, check=True)
shutil.rmtree(fdir)
os.remove(os.path.join(OUT, "frames.txt"))

json.dump(steps, open(os.path.join(OUT, "steps.json"), "w"), indent=1)
print(steps)
