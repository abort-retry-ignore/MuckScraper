#!/usr/bin/env python3
"""Turn publisher sitemaps into RSS for outlets that no longer ship live feeds.

Reuters dropped public RSS in 2020. CNN's rss.cnn.com feeds still answer, but
they stopped updating in 2024. Both still publish news sitemaps with real
article URLs, which MuckScraper can ingest without going through Google News
(news.google.com is on the ingestion blocklist).
"""

from __future__ import annotations

import html
import os
import re
import threading
import time
import urllib.request
from datetime import datetime, timezone
from email.utils import format_datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse
from xml.etree import ElementTree as ET

UA = "Mozilla/5.0 (compatible; MuckScraperFeedProxy/1.0; +https://github.com/grregis/MuckScraper)"
CACHE_SECONDS = 600
PORT = 8080
REUTERS_WINDOW = int(os.environ.get("REUTERS_WINDOW", "1200"))
REUTERS_PAGE = 100

_lock = threading.Lock()
_cache: dict[str, tuple[float, bytes]] = {}

TECH_TITLE = re.compile(
    r"\b(ai|a\.i\.|artificial intelligence|chip|chips|semiconductor|software|"
    r"cyber|tech|technology|robot|robots|nasa|spacex|startup|smartphone|"
    r"quantum|openai|anthropic|nvidia)\b",
    re.IGNORECASE,
)


def _fetch(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/xml,text/xml,*/*"})
    with urllib.request.urlopen(request, timeout=25) as response:
        return response.read()


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _text(node: ET.Element, name: str) -> str:
    for child in node.iter():
        if _local(child.tag) == name and child.text:
            return child.text.strip()
    return ""


def _parse_date(value: str) -> datetime | None:
    value = (value or "").strip()
    if not value:
        return None
    value = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        parsed = None
    if parsed is None:
        try:
            from email.utils import parsedate_to_datetime
            parsed = parsedate_to_datetime(value)
        except (TypeError, ValueError):
            parsed = None
    if parsed is None:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _image_loc(node: ET.Element) -> str:
    """The sitemap <image:image><image:loc> under a <url>, if any."""
    for child in node.iter():
        if _local(child.tag) != "image":
            continue
        for grandchild in child.iter():
            if _local(grandchild.tag) == "loc" and grandchild.text:
                return grandchild.text.strip()
    return ""


def _items_from_sitemap(xml: bytes, keep) -> list[dict]:
    root = ET.fromstring(xml)
    items = []
    for node in root.iter():
        if _local(node.tag) != "url":
            continue
        loc = _text(node, "loc")
        if not loc or not keep(loc, node):
            continue
        title = _text(node, "title") or urlparse(loc).path.rstrip("/").rsplit("/", 1)[-1].replace("-", " ")
        published = _parse_date(_text(node, "publication_date") or _text(node, "lastmod"))
        items.append({
            "title": title,
            "url": loc,
            "published": published,
            "image": _image_loc(node) or None,
        })
    return items


def _reuters_items() -> list[dict]:
    items = []
    failures = 0
    for start in range(0, REUTERS_WINDOW, REUTERS_PAGE):
        url = f"https://www.reuters.com/arc/outboundfeeds/sitemap/?outputType=xml&from={start}"
        try:
            xml = _fetch(url)
        except Exception:
            # A single blocked page should not lose the rest of the window.
            failures += 1
            if failures >= 3:
                break
            continue
        failures = 0

        def keep(loc: str, _node: ET.Element) -> bool:
            path = urlparse(loc).path.lower()
            return path.startswith("/technology/") or path.startswith("/science/")

        page = _items_from_sitemap(xml, keep)
        items.extend(page)
        if b"<loc>" not in xml:
            break
    return items


def _cnn_items() -> list[dict]:
    xml = _fetch("https://edition.cnn.com/sitemap/news.xml")

    def keep(loc: str, node: ET.Element) -> bool:
        path = urlparse(loc).path.lower()
        if any(part in path for part in ("/video/", "/videos/", "/audio/", "/cnn-underscored/", "/live-news/")):
            return False
        if any(part in path for part in ("/science/", "/climate/", "/space/", "/tech/", "/technology/")):
            return True
        title = _text(node, "title")
        return "/business/" in path and bool(TECH_TITLE.search(title))

    return _items_from_sitemap(xml, keep)


def _rss(channel_title: str, channel_link: str, items: list[dict], cap: int = 40) -> bytes:
    deduped = []
    seen = set()
    for item in sorted(items, key=lambda row: row["published"] or datetime.min.replace(tzinfo=timezone.utc), reverse=True):
        if item["url"] in seen:
            continue
        seen.add(item["url"])
        deduped.append(item)
        if len(deduped) >= cap:
            break

    body = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<rss version="2.0">',
        "<channel>",
        f"<title>{html.escape(channel_title)}</title>",
        f"<link>{html.escape(channel_link)}</link>",
        "<description>Science and technology headlines</description>",
    ]
    for item in deduped:
        body.append("<item>")
        body.append(f"<title>{html.escape(item['title'])}</title>")
        body.append(f"<link>{html.escape(item['url'])}</link>")
        body.append(f"<guid>{html.escape(item['url'])}</guid>")
        if item.get("image"):
            body.append(
                f'<enclosure url="{html.escape(item["image"])}" type="image/jpeg"/>'
            )
        if item["published"]:
            body.append(f"<pubDate>{format_datetime(item['published'])}</pubDate>")
        body.append("</item>")
    body.extend(["</channel>", "</rss>"])
    return "\n".join(body).encode("utf-8")


def _cached(key: str, builder) -> bytes:
    now = time.time()
    with _lock:
        cached = _cache.get(key)
        if cached and now - cached[0] < CACHE_SECONDS:
            return cached[1]
    payload = builder()
    with _lock:
        _cache[key] = (time.time(), payload)
    return payload


def reuters_rss() -> bytes:
    return _cached("reuters", lambda: _rss("Reuters", "https://www.reuters.com/technology/", _reuters_items()))


def cnn_rss() -> bytes:
    return _cached("cnn", lambda: _rss("CNN", "https://www.cnn.com/science", _cnn_items()))


_LIFESPAN_ITEM = re.compile("<item>(.*?)</item>", re.S)
_TAG = re.compile("<(?:title|link|pubDate)>(?:<!\\[CDATA\\[)?(.*?)(?:\\]\\]>)?</(?:title|link|pubDate)>")
_ENCLOSURE_RE = re.compile('<enclosure[^>]+url="([^"]+)"')


def _lifespan_items() -> list[dict]:
    """WordPress caps its RSS at 10 posts; pages 2-5 hold the older ones."""
    items = []
    for page in range(1, 6):
        url = f"https://www.lifespan.io/feed/?paged={page}"
        try:
            xml = _fetch(url).decode("utf-8", "replace")
        except Exception:
            continue
        for block in _LIFESPAN_ITEM.findall(xml):
            fields = _TAG.findall(block)
            if len(fields) < 2:
                continue
            title, link = fields[0].strip(), fields[1].strip()
            published = _parse_date(fields[2]) if len(fields) > 2 else None
            enclosure = _ENCLOSURE_RE.search(block)
            if title and link.startswith("http"):
                items.append({
                    "title": title,
                    "url": link,
                    "published": published,
                    "image": enclosure.group(1) if enclosure else None,
                })
    return items


def lifespan_rss() -> bytes:
    # Same channel title as lifespan.io's own feed, so the scheduler keeps
    # filing these under the existing outlet instead of creating a second one.
    return _cached("lifespan", lambda: _rss("Lifespan Research Institute", "https://www.lifespan.io/news/", _lifespan_items(), cap=60))


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        path = urlparse(self.path).path
        try:
            if path == "/healthz":
                body, content_type = b"ok\n", "text/plain"
            elif path == "/reuters.xml":
                body, content_type = reuters_rss(), "application/rss+xml; charset=utf-8"
            elif path == "/cnn.xml":
                body, content_type = cnn_rss(), "application/rss+xml; charset=utf-8"
            elif path == "/lifespan.xml":
                body, content_type = lifespan_rss(), "application/rss+xml; charset=utf-8"
            else:
                self.send_error(404)
                return
        except Exception as exc:
            message = f"feed proxy error: {exc}\n".encode()
            self.send_response(502)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(message)))
            self.end_headers()
            self.wfile.write(message)
            return
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt: str, *args) -> None:
        print(f"[feed-proxy] {self.address_string()} {fmt % args}")


def main() -> None:
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print(f"feed proxy listening on {PORT}")
    server.serve_forever()


if __name__ == "__main__":
    main()
