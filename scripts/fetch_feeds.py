#!/usr/bin/env python3
"""Meridian feed builder.

Fetches RSS feeds for each section, normalizes stories, and writes
data/feed.json for the client app. Tolerant of individual feed failures.
"""

import feedparser
import hashlib
import html
import json
import re
import time
from datetime import datetime, timezone

FEEDS = {
    "top": [
        ("The New York Times", "https://rss.nytimes.com/services/xml/rss/nyt/HomePage.xml"),
        ("BBC News", "https://feeds.bbci.co.uk/news/rss.xml"),
    ],
    "tech": [
        ("NYT Technology", "https://rss.nytimes.com/services/xml/rss/nyt/Technology.xml"),
        ("The Verge", "https://www.theverge.com/rss/index.xml"),
        ("Ars Technica", "https://feeds.arstechnica.com/arstechnica/index"),
        ("Wired", "https://www.wired.com/feed/rss"),
        ("MIT Technology Review", "https://www.technologyreview.com/feed/"),
    ],
    "world": [
        ("NYT World", "https://rss.nytimes.com/services/xml/rss/nyt/World.xml"),
        ("BBC World", "https://feeds.bbci.co.uk/news/world/rss.xml"),
        ("The Guardian", "https://www.theguardian.com/world/rss"),
        ("NPR World", "https://feeds.npr.org/1004/rss.xml"),
        ("NYT Politics", "https://rss.nytimes.com/services/xml/rss/nyt/Politics.xml"),
    ],
    "avl": [
        ("Blue Ridge Public Radio", "https://www.bpr.org/index.rss"),
        ("Mountain Xpress", "https://mountainx.com/feed/"),
        ("Asheville Watchdog", "https://avlwatchdog.org/feed/"),
        ("Citizen Times", "https://www.citizen-times.com/rss/"),
        ("WLOS", "https://wlos.com/feed/rss2/news"),
    ],
    "travel_no": [
        ("The Local Norway", "https://feeds.thelocal.com/rss/no"),
        ("Life in Norway", "https://www.lifeinnorway.net/feed/"),
        ("Norway Today", "https://norwaytoday.info/feed/"),
        ("Science Norway", "https://www.sciencenorway.no/rss"),
    ],
    "travel_dk": [
        ("The Local Denmark", "https://feeds.thelocal.com/rss/dk"),
        ("CPH Post", "https://cphpost.dk/feed/"),
    ],
}

PER_SOURCE_CAP = 8
PER_SECTION_CAP = 28
SUMMARY_MAX = 300

TAG_RE = re.compile(r"<[^>]+>")
IMG_RE = re.compile(r'<img[^>]+src="([^">]+)"', re.IGNORECASE)
WS_RE = re.compile(r"\s+")


def strip_html(text):
    if not text:
        return ""
    text = TAG_RE.sub(" ", text)
    text = html.unescape(text)
    text = WS_RE.sub(" ", text).strip()
    return text


def clamp(text, n):
    if len(text) <= n:
        return text
    cut = text[: n - 1]
    if " " in cut:
        cut = cut.rsplit(" ", 1)[0]
    return cut + "…"


def extract_image(entry):
    # media:content / media:thumbnail
    for key in ("media_content", "media_thumbnail"):
        for m in entry.get(key, []) or []:
            url = m.get("url")
            if url and url.startswith("http"):
                return url
    # enclosures
    for link in entry.get("links", []) or []:
        if link.get("rel") == "enclosure" and str(link.get("type", "")).startswith("image"):
            if link.get("href"):
                return link["href"]
    # first <img> in summary/content
    blobs = []
    if entry.get("summary"):
        blobs.append(entry["summary"])
    for c in entry.get("content", []) or []:
        if c.get("value"):
            blobs.append(c["value"])
    for blob in blobs:
        m = IMG_RE.search(blob)
        if m:
            url = m.group(1)
            if url.startswith("http"):
                return url
    return None


def extract_tags(entry, section):
    tags = []
    for t in entry.get("tags", []) or []:
        term = strip_html(str(t.get("term", ""))).lower().strip()
        if term and len(term) < 40 and term not in tags:
            tags.append(term)
        if len(tags) >= 4:
            break
    return tags


def entry_timestamp(entry):
    for key in ("published_parsed", "updated_parsed"):
        val = entry.get(key)
        if val:
            try:
                return int(time.mktime(val))
            except Exception:
                pass
    return int(time.time())


def normalize(entry, source, section):
    title = strip_html(entry.get("title", ""))
    link = entry.get("link", "")
    if not title or not link:
        return None
    summary = clamp(strip_html(entry.get("summary", "")), SUMMARY_MAX)
    # Some feeds put the whole article in summary — if it starts with the title, trim it.
    if summary.lower().startswith(title.lower()):
        summary = summary[len(title):].lstrip(" -–—:").strip()
    sid = hashlib.md5(link.encode("utf-8")).hexdigest()[:12]
    return {
        "id": sid,
        "h": title,
        "s": source,
        "u": link,
        "y": summary,
        "img": extract_image(entry),
        "ts": entry_timestamp(entry),
        "t": extract_tags(entry, section),
    }


def main():
    out = {"generated_at": datetime.now(timezone.utc).isoformat(), "sections": {}}
    failures = []

    for section, feeds in FEEDS.items():
        stories = []
        seen_ids = set()
        seen_titles = set()
        for source, url in feeds:
            try:
                parsed = feedparser.parse(url, agent="MeridianBot/1.0 (+https://github.com)")
                entries = parsed.get("entries", [])[:PER_SOURCE_CAP]
                if not entries:
                    failures.append(f"{section}: {source} returned 0 entries")
                count = 0
                for e in entries:
                    story = normalize(e, source, section)
                    if not story:
                        continue
                    tkey = story["h"].lower()
                    if story["id"] in seen_ids or tkey in seen_titles:
                        continue
                    seen_ids.add(story["id"])
                    seen_titles.add(tkey)
                    stories.append(story)
                    count += 1
                print(f"[ok] {section}/{source}: {count} stories")
            except Exception as exc:  # noqa: BLE001 — keep going on any feed failure
                failures.append(f"{section}: {source} failed: {exc}")
                print(f"[fail] {section}/{source}: {exc}")
        stories.sort(key=lambda s: s["ts"], reverse=True)
        out["sections"][section] = stories[:PER_SECTION_CAP]

    total = sum(len(v) for v in out["sections"].values())
    print(f"\nTotal stories: {total}")
    if failures:
        print("Failures:")
        for f in failures:
            print(" -", f)

    if total == 0:
        raise SystemExit("No stories fetched at all — refusing to overwrite feed.json")

    with open("data/feed.json", "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, separators=(",", ":"))
    print("Wrote data/feed.json")


if __name__ == "__main__":
    main()
