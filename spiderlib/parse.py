"""Extract page metadata from HTML: title, description, canonical URL, robots meta, links, text.

Usage:
    parsed = parse_html(html, "http://example.com/page")
    parsed["title"], parsed["links"]
"""

import re
import hashlib
from html.parser import HTMLParser
from urllib.parse import urljoin
from spiderlib.urls import normalize_url

MAX_LINKS = 1000
MAX_TITLE = 300
MAX_DESCRIPTION = 500
MAX_TEXT = 5000

def decode_body(raw: bytes, content_type: str | None = None) -> str:
    charset = None

    # Check Content-Type header
    if content_type:
        match = re.search(r'charset=([\'"]?)([\w-]+)\1', content_type, re.IGNORECASE)
        if match:
            charset = match.group(2)

    # Check HTML meta tag
    if not charset:
        meta_match = re.search(rb'<meta[^>]+charset=["\']?([\w-]+)', raw[:2048], re.IGNORECASE)
        if meta_match:
            charset = meta_match.group(1).decode('latin-1')

    # Default to utf-8
    if not charset:
        charset = 'utf-8'

    try:
        return raw.decode(charset, errors='replace')
    except LookupError:
        return raw.decode('utf-8', errors='replace')

def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode('utf-8')).hexdigest()

def _collapse(s):
    return " ".join(s.split())

class MetadataParser(HTMLParser):
    def __init__(self, page_url):
        super().__init__(convert_charrefs=True)
        self.page_url = page_url
        self.base_url = page_url
        self.base_set = False
        self.title = ""
        self.meta_description = ""
        self.og_title = ""
        self.og_description = ""
        self.canonical = None
        self.noindex = False
        self.nofollow = False
        self.links = []
        self.text = []
        self.skip_depth = 0
        self.in_title = False
        self.title_done = False
        self.title_buffer = []
        self.robots_content = []
        self.page_norm = normalize_url(page_url)
        self.seen = set()

    def handle_starttag(self, tag, attrs):
        a = {k.lower(): (v or "") for k, v in attrs}
        if tag == 'base':
            if not self.base_set and a.get("href"):
                self.base_url = urljoin(self.page_url, a["href"])
                self.base_set = True
        elif tag == 'title':
            self.in_title = not self.title_done
        elif tag == 'meta':
            name = a.get("name", "").lower()
            content = a.get("content", "")
            if name == "description" and not self.meta_description:
                self.meta_description = content
            elif name == "robots":
                self.robots_content.append(content)
            property_attr = a.get("property", "").lower()
            if property_attr == "og:title" and not self.og_title:
                self.og_title = content
            elif property_attr == "og:description" and not self.og_description:
                self.og_description = content
        elif tag == 'link':
            rel = a.get("rel", "").lower()
            href = a.get("href")
            if "canonical" in rel.split() and href and self.canonical is None:
                self.canonical = normalize_url(href, self.base_url)
        elif tag == 'a':
            href = a.get("href")
            if href and not href.lower().startswith(("javascript:", "mailto:", "tel:", "data:")):
                normalized = normalize_url(href, self.base_url)
                if normalized and normalized != self.page_norm and normalized not in self.seen and len(self.links) < MAX_LINKS:
                    self.seen.add(normalized)
                    self.links.append(normalized)
        elif tag in ('script', 'style', 'noscript', 'template', 'title'):
            self.skip_depth += 1
        elif tag in ('br', 'p', 'div', 'li', 'tr', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6'):
            self.text.append(" ")

    def handle_endtag(self, tag):
        if tag == 'title':
            self.in_title = False
            self.title_done = True
        elif tag in ('script', 'style', 'noscript', 'template', 'title'):
            self.skip_depth = max(0, self.skip_depth - 1)

    def handle_data(self, data):
        if self.in_title:
            self.title_buffer.append(data)
            return
        if self.skip_depth == 0 and not self.in_title:
            self.text.append(data)

def parse_html(html: str, page_url: str) -> dict:
    parser = MetadataParser(page_url)
    try:
        parser.feed(html)
    except Exception:
        pass

    # Process robots meta tags
    for content in parser.robots_content:
        tokens = [token.strip().lower() for token in content.split(',')]
        if 'none' in tokens:
            parser.noindex = True
            parser.nofollow = True
        else:
            parser.noindex = parser.noindex or 'noindex' in tokens
            parser.nofollow = parser.nofollow or 'nofollow' in tokens

    # Final values
    description = _collapse(parser.meta_description or parser.og_description)[:MAX_DESCRIPTION]
    if not parser.title:
        parser.title = _collapse("".join(parser.title_buffer))[:MAX_TITLE]
    title = parser.title if parser.title else _collapse(parser.og_title)[:MAX_TITLE]

    return {
        "title": title,
        "description": description,
        "canonical": parser.canonical,
        "noindex": parser.noindex,
        "nofollow": parser.nofollow,
        "links": parser.links,
        "text": _collapse("".join(parser.text))[:MAX_TEXT]
    }
