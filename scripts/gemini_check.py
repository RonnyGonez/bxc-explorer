"""Diagnose the Gemini key: which models it can see, and which call styles work."""
import json, os, urllib.error, urllib.request

KEY = os.environ.get("GEMINI_API_KEY", "")
BASE = "https://generativelanguage.googleapis.com/v1beta"


def note(title, msg, level="notice"):
    print(f"::{level} title={title}::" + str(msg).replace("\n", " ")[:900], flush=True)


def call(url, body=None, headers=None):
    req = urllib.request.Request(url, data=json.dumps(body).encode() if body else None,
                                 headers={"Content-Type": "application/json", **(headers or {})},
                                 method="POST" if body else "GET")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")


if not KEY:
    note("Gemini check", "No GEMINI_API_KEY reached this run", "warning")
    raise SystemExit
code, body = call(f"{BASE}/models?pageSize=200&key={KEY}")
if code != 200:
    note("Gemini models", f"HTTP {code}: {body[:600]}", "warning")
    raise SystemExit
models = [m["name"].split("/")[-1] for m in json.loads(body).get("models", [])
          if "generateContent" in m.get("supportedGenerationMethods", [])]
note("Gemini models", f"{len(models)} usable: " + ", ".join(models))
flash = [m for m in models if "flash" in m and "image" not in m and "tts" not in m and "live" not in m][:6]
prompt = 'Reply with JSON only: {"ok": true}'
for m in flash:
    c1, b1 = call(f"{BASE}/models/{m}:generateContent?key={KEY}", {"contents": [{"parts": [{"text": prompt}]}]})
    c2, b2 = call(f"{BASE}/openai/chat/completions", {"model": m, "messages": [{"role": "user", "content": prompt}],
                  "response_format": {"type": "json_object"}}, {"Authorization": f"Bearer {KEY}"})
    note(f"Gemini {m}", f"native HTTP {c1}{'' if c1 == 200 else ' ' + b1[:160]} | openai-style HTTP {c2}{'' if c2 == 200 else ' ' + b2[:160]}",
         "notice" if 200 in (c1, c2) else "warning")
