"""Web tools: search and page fetching, so the agent isn't limited to what's already
on disk. Both are read-only network calls - no API key, since they hit DuckDuckGo's
keyless HTML search and fetch pages directly rather than going through a paid API.
"""
from __future__ import annotations

import html
import re
import urllib.parse

import requests

from .base import ToolResult, truncate_output

_UA = "Mozilla/5.0 (compatible; Geocentric/0.1; local coding agent)"
_TIMEOUT = 12

_RESULT_RE = re.compile(
    r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>', re.DOTALL
)
_SNIPPET_RE = re.compile(
    r'<a[^>]+class="result__snippet"[^>]*>(.*?)</a>', re.DOTALL
)
_TAG_RE = re.compile(r"<[^>]+>")
_SCRIPT_STYLE_RE = re.compile(r"<(script|style)[^>]*>.*?</\1>", re.DOTALL | re.IGNORECASE)
_WHITESPACE_RE = re.compile(r"[ \t]+")
_BLANK_LINES_RE = re.compile(r"\n{3,}")


def _clean_html_text(fragment: str) -> str:
    return html.unescape(_TAG_RE.sub("", fragment)).strip()


def _resolve_ddg_redirect(href: str) -> str:
    """DuckDuckGo's HTML results wrap targets as //duckduckgo.com/l/?uddg=<encoded>&...
    rather than linking straight out; unwrap that so the agent gets a real URL it can
    pass straight to fetch_url."""
    if "uddg=" not in href:
        return href if href.startswith("http") else f"https:{href}"
    parsed = urllib.parse.urlparse(href if href.startswith("http") else f"https:{href}")
    qs = urllib.parse.parse_qs(parsed.query)
    target = qs.get("uddg", [None])[0]
    return urllib.parse.unquote(target) if target else href


def web_search(query: str, max_results: int = 8):
    """Keyless web search via DuckDuckGo's HTML endpoint."""
    max_results = max(1, min(max_results, 20))
    try:
        resp = requests.post(
            "https://html.duckduckgo.com/html/",
            data={"q": query},
            headers={"User-Agent": _UA},
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
    except requests.exceptions.RequestException as e:
        return ToolResult(ok=False, error=f"Web search failed: {e}")

    links = _RESULT_RE.findall(resp.text)
    snippets = _SNIPPET_RE.findall(resp.text)

    if not links:
        return ToolResult(ok=True, output="(no results)", meta={"count": 0})

    lines = []
    for i, (href, title_html) in enumerate(links[:max_results]):
        title = _clean_html_text(title_html)
        url = _resolve_ddg_redirect(href)
        snippet = _clean_html_text(snippets[i]) if i < len(snippets) else ""
        entry = f"{i + 1}. {title}\n   {url}"
        if snippet:
            entry += f"\n   {snippet}"
        lines.append(entry)

    return ToolResult(
        ok=True,
        output=truncate_output("\n\n".join(lines)),
        meta={"count": len(lines), "query": query},
    )


def fetch_url(url: str, max_chars: int = 8000):
    """Fetch a URL and return its readable text - script/style stripped, tags
    stripped, entities decoded. Not a full readability extractor, but enough to let
    the agent actually read a page it found via web_search instead of guessing at
    its content from the search snippet alone."""
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return ToolResult(ok=False, error=f"Not a fetchable URL: {url!r} (need http:// or https://)")

    try:
        resp = requests.get(url, headers={"User-Agent": _UA}, timeout=_TIMEOUT, allow_redirects=True)
        resp.raise_for_status()
    except requests.exceptions.RequestException as e:
        return ToolResult(ok=False, error=f"Fetch failed: {e}")

    content_type = resp.headers.get("Content-Type", "")
    if "html" not in content_type and "text" not in content_type:
        return ToolResult(ok=False, error=f"{url} is {content_type or 'binary'}, not fetchable as text")

    text = _SCRIPT_STYLE_RE.sub("", resp.text)
    text = _TAG_RE.sub("\n", text)
    text = html.unescape(text)
    text = _WHITESPACE_RE.sub(" ", text)
    text = _BLANK_LINES_RE.sub("\n\n", text)
    text = "\n".join(line.strip() for line in text.splitlines()).strip()

    if not text:
        return ToolResult(ok=False, error=f"{url} returned no readable text")

    truncated = text[:max_chars]
    omitted = len(text) - len(truncated)
    output = truncated + (f"\n\n... [{omitted:,} more characters omitted]" if omitted > 0 else "")
    return ToolResult(ok=True, output=output, meta={"url": resp.url, "status": resp.status_code})
