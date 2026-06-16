"""
search.py — محرك البحث على الإنترنت
Pluggable web-search engine.

- لو ضبطت TAVILY_API_KEY يستخدم Tavily (موثوق على السحابة).
- وإلا يستخدم DuckDuckGo عبر مكتبة ddgs (بدون مفتاح).

If TAVILY_API_KEY is set -> Tavily (reliable on cloud IPs).
Otherwise -> DuckDuckGo via the `ddgs` library (no key required).
"""

import os
import requests

TAVILY_URL = "https://api.tavily.com/search"


def _search_tavily(query: str, max_results: int) -> list:
    key = os.environ.get("TAVILY_API_KEY", "")
    payload = {
        "api_key": key,
        "query": query,
        "max_results": max_results,
        "search_depth": "basic",
    }
    r = requests.post(TAVILY_URL, json=payload, timeout=30)
    r.raise_for_status()
    data = r.json()
    out = []
    for item in data.get("results", []):
        out.append({
            "title": item.get("title", ""),
            "url": item.get("url", ""),
            "snippet": (item.get("content", "") or "")[:300],
            "source": "tavily",
        })
    return out


def _search_ddg(query: str, max_results: int) -> list:
    # استيراد كسول حتى لا يفشل الاستيراد لو المكتبة غير مثبّتة محلياً
    try:
        from ddgs import DDGS
    except Exception:
        try:
            from duckduckgo_search import DDGS  # اسم قديم للمكتبة
        except Exception:
            return []
    out = []
    try:
        with DDGS() as ddg:
            for item in ddg.text(query, max_results=max_results):
                url = item.get("href") or item.get("url") or ""
                snippet = item.get("body") or item.get("content") or ""
                out.append({
                    "title": item.get("title", ""),
                    "url": url,
                    "snippet": (snippet or "")[:300],
                    "source": "duckduckgo",
                })
    except Exception:
        return out
    return out


def web_search(query: str, max_results: int = 5) -> list:
    """يُرجع قائمة نتائج موحّدة: title, url, snippet, source. لا يرمي استثناءً أبداً."""
    try:
        if os.environ.get("TAVILY_API_KEY"):
            return _search_tavily(query, max_results)
        return _search_ddg(query, max_results)
    except Exception:
        return []


if __name__ == "__main__":
    for r in web_search("free python course", 3):
        print(r["title"], "->", r["url"])
