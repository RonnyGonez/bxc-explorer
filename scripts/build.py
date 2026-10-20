"""Build the explorer page from the current playlist and the tag library."""
import datetime
import json
import os
import sys

HERE = os.path.dirname(__file__)
sys.path.insert(0, HERE)
ROOT = os.path.join(HERE, "..")
tracks = {t["id"]: t for t in json.load(open(os.path.join(ROOT, "data", "tracks.json"), encoding="utf-8"))}
playlist = json.load(open(os.path.join(ROOT, "data", "playlist.json"), encoding="utf-8"))["tracks"]

# Playlist order, newest additions last; only tracks currently in the playlist.
_seen = set()
rows = [tracks[p["id"]] for p in playlist if p["id"] in tracks and not (p["id"] in _seen or _seen.add(p["id"]))]

# YouTube versions for the YouTube player (overrides win over automatic matches).
def _load_list(name):
    path = os.path.join(ROOT, "data", name)
    return json.load(open(path, encoding="utf-8")) if os.path.exists(path) else []
def _load(name):
    path = os.path.join(ROOT, "data", name)
    return json.load(open(path, encoding="utf-8")) if os.path.exists(path) else {}
yt = {k: v.get("v") for k, v in _load("youtube.json").items()}
yt.update(_load("youtube_overrides.json"))
rows = [dict(r, yt=yt[r["id"]]) if yt.get(r["id"]) else r for r in rows]

# Songs shared in the chat that aren't on Spotify: YouTube only (data/youtube_only.json).
for e in _load_list("youtube_only.json"):
    tid = "yt-" + e["yt"]
    base = tracks.get(tid) or {"id": tid, "t": e["title"], "a": e["artist"], "y": 0, "e": 0, "v": 0, "d": 0,
                               "ac": 0, "i": 0, "g": [], "lc": True, "pending": True}
    rows.append(dict(base, yt=e["yt"], yo=1))
updated = datetime.datetime.now(datetime.timezone.utc).strftime("%-d %B %Y")
html = (open(os.path.join(ROOT, "site", "template.html"), encoding="utf-8").read()
        .replace("__DATA__", json.dumps(rows, ensure_ascii=False, separators=(",", ":")))
        .replace("__UPDATED__", updated)
        .replace("__OG_DESC__", f"Now that's what I call Bangers Xchange Club Music {len(rows)}: the club's songs, sorted by mood. Pick one and press play.")
        .replace("__OG_V__", str(len(rows)))
        .replace("__PLAYLIST_ID__", json.load(open(os.path.join(ROOT, "data", "playlist.json")))["playlist_id"])
        .replace("__SPOTIFY_CLIENT_ID__", os.environ.get("SPOTIFY_CLIENT_ID", "").strip() or "__SPOTIFY_CLIENT_ID__"))
os.makedirs(os.path.join(ROOT, "_site"), exist_ok=True)
open(os.path.join(ROOT, "_site", "index.html"), "w", encoding="utf-8").write(html)
open(os.path.join(ROOT, "_site", ".nojekyll"), "w").close()
import shutil
try:   # link-preview card with the live song count
    import cover
    cover.draw(len(rows), os.path.join(ROOT, "_site", "og.jpg"))
except Exception as e:
    print("Couldn't draw the preview card, using the plain one:", e)
    shutil.copy(os.path.join(ROOT, "site", "og.jpg"), os.path.join(ROOT, "_site", "og.jpg"))
print(f"Built page with {len(rows)} tracks ({sum(1 for r in rows if r.get('pending'))} awaiting tags, {sum(1 for r in rows if r.get('yt'))} with a YouTube version, {sum(1 for r in rows if r.get('yo'))} YouTube only)")
