#!/usr/bin/env python3
"""Re-fetch animals that were mismatched or failed, with keyword validation.

Ordinary search can falsely match personal names and the like through
partial word matches (e.g. crow picking up "Jonathan Tweet"), so a result
title is accepted only if it contains one of the expected keywords.
Scientific names are also used to improve the hit rate.
"""
import os
import sys
import time
import urllib.parse
import urllib.error

# Reuse the API helpers from fetch_sounds
from fetch_sounds import api_get, get_mp3_url, download, SOUNDS_DIR, AUDIO_EXT

# (output name, search queries, keywords required for acceptance [any one suffices])
TARGETS = [
    ("gorilla", ["Gorilla gorilla", "gorilla grunt", "gorilla call", "western gorilla"],
                ["gorilla"]),
    ("lion",    ["Panthera leo roar", "lion roar", "lion growl", "lion vocalization"],
                ["lion", "panthera leo", "leo"]),
    ("tiger",   ["Panthera tigris roar", "tiger roar", "tiger growl", "Bengal tiger"],
                ["tiger", "panthera tigris", "tigris"]),
    ("crow",    ["Corvus corone caw", "carrion crow call", "American crow Corvus",
                 "Corvus brachyrhynchos"],
                ["crow", "corvus"]),
    ("goose",   ["Canada goose honk", "Branta canadensis call", "Anser anser call",
                 "greylag goose"],
                ["goose", "branta", "anser"]),
]


def search_validated(query, keywords):
    """Return a sound file from the search results whose title contains a keyword."""
    for srsearch in (f"{query} filetype:audio", query):
        try:
            data = api_get({
                "action": "query",
                "list": "search",
                "srsearch": srsearch,
                "srnamespace": "6",
                "srlimit": "20",
            })
        except urllib.error.HTTPError:
            continue
        for hit in data.get("query", {}).get("search", []):
            title = hit.get("title", "")
            low = title.lower()
            if not low.endswith(AUDIO_EXT):
                continue
            if any(k.lower() in low for k in keywords):
                return title
    return None


def main():
    os.makedirs(SOUNDS_DIR, exist_ok=True)
    ok, fail = [], []
    for name, queries, keywords in TARGETS:
        dest = os.path.join(SOUNDS_DIR, f"{name}.mp3")
        if os.path.exists(dest) and os.path.getsize(dest) > 1000:
            print(f"SKIP {name} (exists)")
            ok.append(name)
            continue
        got = False
        for q in queries:
            try:
                title = search_validated(q, keywords)
                if not title:
                    continue
                mp3 = get_mp3_url(title)
                if not mp3:
                    continue
                size = download(mp3, dest)
                print(f"OK   {name:8s} <- {title}  ({size} bytes)")
                ok.append(name)
                got = True
                break
            except Exception as e:
                print(f"..   {name:8s} q={q!r}: {e}", file=sys.stderr)
                time.sleep(0.5)
        if not got:
            print(f"FAIL {name}", file=sys.stderr)
            fail.append(name)
        time.sleep(1.5)
    print(f"\nGot: {', '.join(ok) or '(none)'}")
    if fail:
        print(f"Failed: {', '.join(fail)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
