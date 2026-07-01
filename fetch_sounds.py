#!/usr/bin/env python3
"""Script to fetch animal sounds (MP3) from Wikimedia Commons.

For each animal, search the API for a sound file, obtain the URL of the
MP3 transcode version that Wikimedia auto-generates, and save it under
sounds/. The key point is to always fetch MP3, because afplay cannot play
Ogg Vorbis.
"""
import json
import os
import sys
import time
import urllib.parse
import urllib.request

# Save the fetched originals in raw/ (process_sounds.py processes them into sounds/)
SOUNDS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "raw")
API = "https://commons.wikimedia.org/w/api.php"
UA = "zoo-board/1.0 (educational personal project)"

# (output file name, search queries) -- queries are tried in order
ANIMALS = [
    ("cat",     ["cat meow", "Domestic cat meow", "meow"]),
    ("dog",     ["dog bark", "Dog barking", "bark dog"]),
    ("cow",     ["cow moo", "cattle moo", "cow vocalization"]),
    ("rooster", ["rooster crow", "cock crow", "chicken rooster"]),
    ("sheep",   ["sheep baa", "sheep bleat", "sheep vocalization"]),
    ("duck",    ["duck quack", "mallard quack", "duck call"]),
    ("frog",    ["frog croak", "frog call", "common frog"]),
    ("horse",   ["horse neigh", "horse whinny", "horse vocalization"]),
    ("pig",     ["pig oink", "pig grunt", "domestic pig"]),
    ("goat",    ["goat bleat", "goat vocalization", "goat sound"]),
    ("owl",     ["owl hoot", "tawny owl", "owl call"]),
    ("elephant",["elephant trumpet", "elephant call", "elephant sound"]),
    # -- noisy animals --
    ("gorilla", ["gorilla call", "gorilla vocalization", "gorilla grunt"]),
    ("donkey",  ["donkey bray", "donkey hee-haw", "donkey vocalization"]),
    ("lion",    ["lion roar", "lion vocalization", "lion growl"]),
    ("wolf",    ["wolf howl", "gray wolf howl", "wolf vocalization"]),
    ("monkey",  ["monkey call", "howler monkey", "macaque call"]),
    ("tiger",   ["tiger roar", "tiger growl", "tiger vocalization"]),
    ("seagull", ["seagull call", "herring gull call", "gull cry"]),
    ("peacock", ["peacock call", "peafowl call", "peacock vocalization"]),
    ("crow",    ["crow caw", "carrion crow", "crow call"]),
    ("goose",   ["goose honk", "greylag goose", "goose call"]),
]

AUDIO_EXT = (".ogg", ".oga", ".wav", ".flac", ".mp3", ".opus")


def api_get(params):
    params = dict(params)
    params["format"] = "json"
    url = API + "?" + urllib.parse.urlencode(params)
    # Retry with exponential backoff on 429 (rate limit)
    delay = 2.0
    for attempt in range(6):
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < 5:
                time.sleep(delay)
                delay *= 2
                continue
            raise
    raise RuntimeError("unreachable")


def search_audio_title(query):
    """Return the title of the first sound file (File:...) in the search results."""
    data = api_get({
        "action": "query",
        "list": "search",
        "srsearch": f"{query} filetype:audio",
        "srnamespace": "6",
        "srlimit": "10",
    })
    for hit in data.get("query", {}).get("search", []):
        title = hit.get("title", "")
        if title.lower().endswith(AUDIO_EXT):
            return title
    # Retry without the filetype specifier
    data = api_get({
        "action": "query",
        "list": "search",
        "srsearch": query,
        "srnamespace": "6",
        "srlimit": "10",
    })
    for hit in data.get("query", {}).get("search", []):
        title = hit.get("title", "")
        if title.lower().endswith(AUDIO_EXT):
            return title
    return None


def get_mp3_url(title):
    """Obtain a playable MP3 URL from a File title.

    If the original is mp3, return that URL; otherwise build and return the
    URL of Wikimedia's MP3 transcode version.
    """
    data = api_get({
        "action": "query",
        "titles": title,
        "prop": "imageinfo",
        "iiprop": "url",
    })
    pages = data.get("query", {}).get("pages", {})
    for _, page in pages.items():
        infos = page.get("imageinfo", [])
        if not infos:
            continue
        url = infos[0].get("url", "")
        if not url:
            continue
        if url.lower().endswith(".mp3"):
            return url
        # e.g.: https://upload.wikimedia.org/wikipedia/commons/a/ab/Foo.ogg
        #  -> https://upload.wikimedia.org/wikipedia/commons/transcoded/a/ab/Foo.ogg/Foo.ogg.mp3
        marker = "/commons/"
        if marker in url:
            head, tail = url.split("/commons/", 1)
            fname = tail.rsplit("/", 1)[-1]
            return f"{head}/commons/transcoded/{tail}/{fname}.mp3"
    return None


def download(url, dest):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        data = r.read()
    if len(data) < 1000:
        raise ValueError(f"file too small ({len(data)} bytes)")
    with open(dest, "wb") as f:
        f.write(data)
    return len(data)


def main():
    os.makedirs(SOUNDS_DIR, exist_ok=True)
    ok, fail = [], []
    for name, queries in ANIMALS:
        dest = os.path.join(SOUNDS_DIR, f"{name}.mp3")
        # Skip if already fetched (sufficient size)
        if os.path.exists(dest) and os.path.getsize(dest) > 1000:
            print(f"SKIP {name:9s} (already exists)")
            ok.append(name)
            continue
        got = False
        for q in queries:
            try:
                title = search_audio_title(q)
                if not title:
                    continue
                mp3 = get_mp3_url(title)
                if not mp3:
                    continue
                size = download(mp3, dest)
                print(f"OK   {name:9s} <- {title}  ({size} bytes)")
                ok.append(name)
                got = True
                break
            except Exception as e:
                print(f"..   {name:9s} query={q!r} failed: {e}", file=sys.stderr)
                time.sleep(0.3)
        if not got:
            print(f"FAIL {name}", file=sys.stderr)
            fail.append(name)
        time.sleep(1.5)
    print(f"\nDownloaded {len(ok)} sounds: {', '.join(ok)}")
    if fail:
        print(f"Failed: {', '.join(fail)}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
