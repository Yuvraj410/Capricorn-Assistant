"""Looking things up for real: search the web (free, no API key), then the local brain reads the
results and Capri tells you the answer, instead of just opening a Google page.

Search: the `ddgs` package (DuckDuckGo and other engines, free) with a plain DuckDuckGo HTML fallback.
"""
from __future__ import annotations

import html
import logging
import re
from typing import Any
from urllib.parse import parse_qs, quote_plus, unquote, urlparse

import requests

log = logging.getLogger(__name__)
FRESH = re.compile(r"\b(today|tonight|now|current|currently|latest|recent|news|live|this week|right now|price|prices|"
                   r"stock|stocks|market|markets|score|scores|weather|forecast|update|happening|release date|"
                   r"who won|election|crypto|bitcoin)\b", re.I)


def domain(url: str) -> str:
    d = urlparse(url).netloc.lower()
    return d[4:] if d.startswith("www.") else d


def _ddgs(query: str, n: int, news: bool) -> list[dict]:
    from ddgs import DDGS  # type: ignore
    out: list[dict] = []
    with DDGS(timeout=8) as d:
        if news:
            try:
                for r in d.news(query, max_results=max(3, n // 2), timelimit="w"):
                    out.append({"title": r.get("title", ""), "url": r.get("url", ""), "snippet": r.get("body", ""),
                                "date": str(r.get("date", ""))[:10], "source": r.get("source", "")})
            except Exception:
                log.debug("news search failed", exc_info=True)
        for r in d.text(query, max_results=n):
            out.append({"title": r.get("title", ""), "url": r.get("href", ""), "snippet": r.get("body", ""),
                        "date": "", "source": ""})
    return out


def _ddg_html(query: str, n: int) -> list[dict]:
    """Fallback without extra packages: DuckDuckGo's plain HTML page."""
    r = requests.get(f"https://html.duckduckgo.com/html/?q={quote_plus(query)}", timeout=8,
                     headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Capricorn/0.1"})
    r.raise_for_status()
    out = []
    blocks = re.findall(r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>.*?'
                        r'class="result__snippet"[^>]*>(.*?)</(?:a|div)>', r.text, re.S)
    for href, title, snip in blocks[:n]:
        if "uddg=" in href:
            href = unquote(parse_qs(urlparse(href).query).get("uddg", [href])[0])
        clean = lambda s: html.unescape(re.sub(r"<[^>]+>", "", s)).strip()  # noqa: E731
        out.append({"title": clean(title), "url": href, "snippet": clean(snip), "date": "", "source": ""})
    return out


def search(query: str, n: int = 6) -> list[dict]:
    news = bool(FRESH.search(query))
    results: list[dict] = []
    try:
        results = _ddgs(query, n, news)
    except ImportError:
        log.info("ddgs not installed - using the DuckDuckGo HTML fallback")
    except Exception:
        log.warning("ddgs search failed - trying the fallback", exc_info=True)
    if not results:
        try:
            results = _ddg_html(query, n)
        except Exception:
            log.warning("web search failed", exc_info=True)
    seen, uniq = set(), []
    for r in results:
        key = r["url"] or r["title"]
        if key and key not in seen and (r["snippet"] or r["title"]):
            seen.add(key)
            uniq.append(r)
    log.info("web search %r -> %d results", query, len(uniq))
    return uniq[: n + 3]


def results_text(results: list[dict[str, Any]], limit_chars: int = 3500) -> str:
    lines, used = [], 0
    for i, r in enumerate(results, 1):
        meta = ", ".join(x for x in (r.get("source") or domain(r.get("url", "")), r.get("date", "")) if x)
        line = f"[{i}] {r.get('title', '').strip()} ({meta}): {r.get('snippet', '').strip()}"
        if used + len(line) > limit_chars:
            break
        lines.append(line)
        used += len(line)
    return "\n".join(lines)
