"""Read every track in the public Spotify playlist.

Opens the playlist's web page and, while it loads, picks up the request Spotify's
own page makes for the track list. It then asks that same feed for the whole
list, 100 tracks at a time (fast and doesn't depend on the page layout). If that
doesn't work, it falls back to scrolling the page and reading the rows.

No Spotify developer key is needed. Writes data/playlist.json (ids in playlist
order, plus title/artist for each). Exits with an error, and leaves the old file
untouched, if it can't read close to the full playlist.
"""
import json
import os
import sys
import time
import urllib.parse

from playwright.sync_api import sync_playwright

PLAYLIST_ID = os.environ.get("PLAYLIST_ID", "2YOQqyCK4VP8Owz1TF7sNB")
URL = f"https://open.spotify.com/playlist/{PLAYLIST_ID}"
OUT = os.path.join(os.path.dirname(__file__), "..", "data", "playlist.json")

# Runs inside the page. Only reads rows inside the playlist's own tracklist,
# so Spotify's "Recommended songs" block underneath is ignored.
COLLECT_JS = r"""
async () => {
  const pl = document.querySelector('[data-testid="playlist-tracklist"]');
  if (!pl) return {error: 'no playlist tracklist on page'};
  const grid = pl.querySelector('[aria-rowcount]') || pl;
  const expected = parseInt(grid.getAttribute('aria-rowcount') || '0', 10) - 1; // minus header row
  const found = {};
  const grab = () => {
    pl.querySelectorAll('[data-testid="tracklist-row"]').forEach(r => {
      const row = r.closest('[aria-rowindex]');
      const idx = row ? +row.getAttribute('aria-rowindex') : null;
      const links = [...r.querySelectorAll('a')];
      const t = links.find(a => (a.getAttribute('href') || '').startsWith('/track/'));
      if (!t || idx == null) return;
      const id = t.getAttribute('href').split('/')[2].split('?')[0];
      const artists = links.filter(a => (a.getAttribute('href') || '').startsWith('/artist/')).map(a => a.textContent.trim());
      const alb = links.find(a => (a.getAttribute('href') || '').startsWith('/album/'));
      found[idx] = {idx, id, title: t.textContent.trim(), artists, album: alb ? alb.textContent.trim() : ''};
    });
  };
  let sc = pl.querySelector('[data-testid="tracklist-row"]');
  while (sc && !(sc.scrollHeight > sc.clientHeight + 50 && /(auto|scroll)/.test(getComputedStyle(sc).overflowY))) sc = sc.parentElement;
  if (!sc) sc = document.scrollingElement;
  // Spotify loads rows in chunks and sometimes stalls. Keep going until every
  // row is read; when nothing new arrives, nudge the list up and back down.
  let last = -1, stable = 0;
  for (let i = 0; i < 1500 && stable < 40; i++) {
    grab();
    if (expected > 0 && Object.keys(found).length >= expected) break;
    if (stable && stable % 6 === 0) { sc.scrollTop -= 1500; await new Promise(r => setTimeout(r, 600)); }
    sc.scrollTop += 600;
    await new Promise(r => setTimeout(r, stable ? 700 : 400));
    const n = Object.keys(found).length;
    if (n === last) stable++; else { stable = 0; last = n; }
  }
  grab();
  return {expected, rows: Object.values(found).sort((a, b) => a.idx - b.idx)};
}
"""


def annotate(title, msg, level="error"):
    """Show a message as a GitHub Actions annotation (readable without the full log)."""
    msg = str(msg).replace("%", "%25").replace("\r", "").replace("\n", "%0A")[:3000]
    print(f"::{level} title={title}::{msg}", flush=True)


DIAG_JS = r"""
() => ({
  url: location.href,
  title: document.title,
  tracklist: !!document.querySelector('[data-testid="playlist-tracklist"]'),
  rows: document.querySelectorAll('[data-testid="tracklist-row"]').length,
  rowcount: (document.querySelector('[aria-rowcount]') || {getAttribute: () => null}).getAttribute('aria-rowcount'),
  testids: [...new Set([...document.querySelectorAll('[data-testid]')].map(e => e.dataset.testid))].slice(0, 60).join(','),
  text: (document.body ? document.body.innerText : '').replace(/\s+/g, ' ').slice(0, 700),
})
"""


def diagnose(page, why):
    try:
        d = page.evaluate(DIAG_JS)
    except Exception as e:
        d = {"diag_error": str(e)}
    annotate("Playlist read failed", f"{why}\n" + "\n".join(f"{k}: {v}" for k, v in d.items()))



# ---- Spotify's own data feed --------------------------------------------------
FEED_HOST = "api-partner.spotify.com/pathfinder/"
DROP_HEADERS = {"host", "content-length", "cookie", "connection", "accept-encoding"}


def op_of(req):
    """Operation name and variables of a pathfinder request (GET v1 or POST v2)."""
    try:
        if req.method == "GET":
            q = urllib.parse.parse_qs(urllib.parse.urlparse(req.url).query)
            return q.get("operationName", [""])[0], json.loads(q.get("variables", ["{}"])[0])
        body = req.post_data_json or {}
        return body.get("operationName", ""), body.get("variables", {})
    except Exception:
        return "", {}


def find_content(node):
    """The {totalCount, items} block of a playlist response, wherever it sits."""
    if isinstance(node, dict):
        if isinstance(node.get("items"), list) and "totalCount" in node:
            return node
        for v in node.values():
            r = find_content(v)
            if r:
                return r
    elif isinstance(node, list):
        for v in node:
            r = find_content(v)
            if r:
                return r
    return None


def find_track(node):
    if isinstance(node, dict):
        uri = node.get("uri")
        if isinstance(uri, str) and uri.startswith("spotify:track:") and node.get("name"):
            return node
        for v in node.values():
            r = find_track(v)
            if r:
                return r
    elif isinstance(node, list):
        for v in node:
            r = find_track(v)
            if r:
                return r
    return None


def parse_items(items):
    rows = []
    for it in items:
        t = find_track(it)
        if not t:
            rows.append(None)  # a podcast episode or unavailable item; still takes a slot
            continue
        artists = [((a.get("profile") or {}).get("name") or a.get("name") or "")
                   for a in ((t.get("artists") or {}).get("items") or [])]
        album = (t.get("albumOfTrack") or t.get("album") or {}).get("name", "")
        rows.append({"id": t["uri"].split(":")[2], "title": t["name"], "artists": [a for a in artists if a], "album": album})
    return rows


def read_feed(page, req):
    """Replay the page's own playlist request with bigger pages until every track is read."""
    op, variables = op_of(req)
    headers = {k: v for k, v in req.all_headers().items() if k.lower() not in DROP_HEADERS and not k.startswith(":")}
    rows, total, offset = [], None, 0
    while total is None or offset < total:
        var = dict(variables, offset=offset, limit=100)
        if req.method == "GET":
            u = urllib.parse.urlparse(req.url)
            q = urllib.parse.parse_qs(u.query)
            q["variables"] = [json.dumps(var, separators=(",", ":"))]
            url = u._replace(query=urllib.parse.urlencode({k: v[0] for k, v in q.items()})).geturl()
            r = page.request.get(url, headers=headers)
        else:
            body = dict(req.post_data_json or {}, variables=var)
            r = page.request.post(req.url, headers=headers, data=json.dumps(body))
        if not r.ok:
            raise RuntimeError(f"{op} offset {offset}: HTTP {r.status} {r.text()[:200]}")
        content = find_content(r.json())
        if not content:
            raise RuntimeError(f"{op} offset {offset}: no track list in reply {r.text()[:200]}")
        total = int(content["totalCount"])
        batch = parse_items(content["items"])
        if not batch:
            break
        rows += batch
        offset += len(batch)
    return [x for x in rows if x], total, op


def main():
    for attempt in (1, 2):
        try:
            return read_once()
        except SystemExit as e:
            if attempt == 2:
                raise
            print(f"Attempt {attempt} failed ({e}); trying again in a minute.", flush=True)
            time.sleep(60)


def read_once():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(
            viewport={"width": 1280, "height": 1000},
            user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                        "(KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36"),
            locale="en-US",
        )
        seen_ops, feed_reqs = [], []

        def on_request(req):
            if FEED_HOST in req.url:
                op, var = op_of(req)
                seen_ops.append(op)
                if PLAYLIST_ID in json.dumps(var) and "offset" in var:
                    feed_reqs.append(req)

        page.on("request", on_request)
        page.goto(URL, wait_until="domcontentloaded", timeout=60000)
        for _ in range(60):
            if feed_reqs:
                break
            page.wait_for_timeout(500)
        if feed_reqs:
            try:
                rows, total, op = read_feed(page, feed_reqs[0])
                print(f"Feed ({op}): {len(rows)} tracks of {total}", flush=True)
                print(f"::notice title=Playlist read::Read {len(rows)} of {total} tracks from Spotify's feed ({op})", flush=True)
                if total and len(rows) >= total * 0.97:
                    browser.close()
                    return save([dict(r, idx=i) for i, r in enumerate(rows)], total)
                annotate("Playlist feed incomplete", f"{op}: {len(rows)} of {total}; falling back to scrolling", "warning")
            except Exception as e:
                annotate("Playlist feed failed", f"{type(e).__name__}: {e}; falling back to scrolling", "warning")
        else:
            annotate("Playlist feed not seen", "Requests seen: " + ", ".join(sorted(set(seen_ops)))[:1500] + "; falling back to scrolling", "warning")
        # Decline the cookie banner and close the language picker if they appear.
        try:
            page.locator("#onetrust-reject-all-handler").click(timeout=5000)
        except Exception:
            pass
        try:
            page.locator('[data-testid="language-selection-modal"] [data-testid="close-button"]').click(timeout=3000)
        except Exception:
            page.keyboard.press("Escape")
        try:
            page.wait_for_selector('[data-testid="playlist-tracklist"] [data-testid="tracklist-row"]', timeout=60000)
        except Exception as e:
            diagnose(page, f"Track rows never appeared ({type(e).__name__})")
            browser.close()
            sys.exit("Scrape failed: track rows never appeared")
        time.sleep(2)
        result = page.evaluate(COLLECT_JS)
        if "error" in result or len(result.get("rows", [])) < result.get("expected", 0) * 0.97:
            diagnose(page, f"After scrolling: {result.get('error') or str(len(result['rows'])) + ' of ' + str(result['expected']) + ' rows read'}")
        browser.close()

    if "error" in result:
        sys.exit("Scrape failed: " + result["error"])
    return save(result["rows"], result["expected"])


def save(rows, expected):
    # Same track can sit in a playlist twice; keep the first appearance.
    seen, tracks = set(), []
    for r in rows:
        if r["id"] in seen:
            continue
        seen.add(r["id"])
        tracks.append({"id": r["id"], "title": r["title"], "artists": r["artists"], "album": r["album"]})
    print(f"Read {len(rows)} rows ({len(tracks)} unique) of {expected} expected")
    if expected <= 0 or len(rows) < expected * 0.97:
        annotate("Playlist read incomplete", f"Only read {len(rows)} of {expected} rows; first idx {rows[0]['idx'] if rows else None}, last idx {rows[-1]['idx'] if rows else None}")
        sys.exit(f"Only read {len(rows)} of {expected} rows; keeping the previous data.")
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump({"playlist_id": PLAYLIST_ID, "count": len(rows), "tracks": tracks}, f, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
