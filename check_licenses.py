#!/usr/bin/env python3
"""Retrieve the Wikimedia Commons license information for the bundled sound files.

From each sound's source (its Commons file name), retrieve the license short name, author,
whether attribution is required, and the non-free determination, used to decide whether it can be
open-sourced and to build the attribution/credits.
"""
import json
import sys
import time
import urllib.parse
import urllib.request

API = "https://commons.wikimedia.org/w/api.php"
UA = "zoo-board-license-check/1.0"

# Saved file name -> Commons source file name (from the download log)
SOURCES = {
    "cat":      "File:Meow of a pleading cat.oga",
    "dog":      "File:Barking of a dog 2.ogg",
    "duck":     "File:En-au-quack like a duck.ogg",
    "frog":     "File:Single Frog Croak.oga",
    "cow":      "File:Single Cow Moo.ogg",
    "rooster":  "File:Rooster crowing.ogg",
    "sheep":    "File:Sheep bleating.ogg",
    "horse":    "File:Wiehern.ogg",
    "pig":      "File:Mudchute pig 2.ogg",
    "goat":     "File:Man bleats like goat or.ogg",
    "owl":      "File:Maghreb owl hooting.wav",
    "elephant": "File:Elephant voice - trumpeting.ogg",
    "donkey":   "File:157763 felix-blume a-donkey-is-braying-in-his-enclosure-in-south-of-france.wav",
    "wolf":     "File:Wolf howls.ogg",
    "monkey":   "File:Brown woolly monkey alarm call.wav",
    "tiger":    "File:439280 schots angry-tiger.wav",
    "seagull":  "File:XC707075 - European Herring Gull - Larus argentatus.mp3",
    "peacock":  "File:DM550170 Pavo cristatus call in farm Slovakia.oga",
    "crow":     "File:Corvus corone - Carrion Crow XC491193.mp3",
    "goose":    "File:Branta canadensis - Canada Goose XC127624.ogg",
    # gorilla is a self-made synthesized sound via ffmpeg (no source)
}


def api_get(params):
    params = dict(params, format="json")
    url = API + "?" + urllib.parse.urlencode(params)
    for attempt in range(6):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < 5:
                time.sleep(2 * (attempt + 1))
                continue
            raise
    return {}


def get_meta(title):
    data = api_get({
        "action": "query",
        "titles": title,
        "prop": "imageinfo",
        "iiprop": "extmetadata|url",
    })
    for _, page in data.get("query", {}).get("pages", {}).items():
        infos = page.get("imageinfo", [])
        if not infos:
            return None
        em = infos[0].get("extmetadata", {})
        def g(k):
            return (em.get(k, {}) or {}).get("value", "")
        return {
            "license": g("LicenseShortName"),
            "license_url": g("LicenseUrl"),
            "artist": g("Artist"),
            "attribution_required": g("AttributionRequired"),
            "non_free": g("NonFree"),
            "restrictions": g("Restrictions"),
            "descurl": infos[0].get("descriptionurl", ""),
        }
    return None


def strip_html(s):
    import re
    return re.sub(r"<[^>]+>", "", s).replace("&amp;", "&").strip()


def main():
    print(f"{'name':9s} {'license':22s} {'attr':5s} {'nonfree':8s} artist")
    print("-" * 80)
    rows = []
    for name, title in SOURCES.items():
        meta = get_meta(title)
        if not meta:
            print(f"{name:9s} (retrieval failed)")
            continue
        lic = meta["license"] or "?"
        attr = meta["attribution_required"] or "?"
        nf = meta["non_free"] or "0"
        artist = strip_html(meta["artist"])[:30]
        print(f"{name:9s} {lic:22s} {attr:5s} {nf:8s} {artist}")
        rows.append((name, title, meta))
        time.sleep(0.3)

    # Generate the attribution/credits file
    with open("ATTRIBUTIONS.md", "w") as f:
        f.write("# Sound credits\n\n")
        f.write("`gorilla` is a self-made synthesized sound in this project (ffmpeg). "
                "Everything else is from Wikimedia Commons.\n\n")
        for name, title, meta in rows:
            f.write(f"## {name}\n")
            f.write(f"- Source: {meta['descurl']}\n")
            f.write(f"- Author: {strip_html(meta['artist']) or 'Unknown'}\n")
            f.write(f"- License: {meta['license']}")
            if meta["license_url"]:
                f.write(f" ({meta['license_url']})")
            f.write("\n\n")
    print("\nGenerated ATTRIBUTIONS.md.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
