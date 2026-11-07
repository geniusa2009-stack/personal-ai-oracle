"""Isolated Playwright browser tools for Personal AI Oracle.

Uses a dedicated Oracle browser profile, never the user's everyday browser profile.
Only HTTP(S) pages are allowed. Private-network navigation is disabled by default.
"""

from __future__ import annotations

import ipaddress
import os
import socket
import threading
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from search import web_search

MAX_PAGE_TEXT = 18_000
_BROWSER_LOCK = threading.RLock()
_CONTEXT = None
_PAGE = None
_PLAYWRIGHT = None

TOOL_DEFINITIONS = [
    {
        "tool_id": "web.search",
        "name": "Search the web",
        "description": "Search public websites and return titles, URLs and snippets. input JSON: {query, max_results?}.",
        "input_schema": {"query": "string", "max_results": "integer?"},
    },
    {
        "tool_id": "web.navigate",
        "name": "Open website",
        "description": "Open a public HTTP(S) website in Oracle's isolated browser and return page text. input JSON: {url}.",
        "input_schema": {"url": "string"},
    },
    {
        "tool_id": "web.extract",
        "name": "Extract current webpage",
        "description": "Read the visible text from the current Oracle browser tab. input JSON: {}.",
        "input_schema": {},
    },
    {
        "tool_id": "web.links",
        "name": "List webpage links",
        "description": "List links from the current page. input JSON: {limit?}.",
        "input_schema": {"limit": "integer?"},
    },
    {
        "tool_id": "web.open_browser",
        "name": "Open Oracle browser window",
        "description": "Open the isolated Oracle browser profile. On a visible Mac session, sign-ins must be performed manually by the user. input JSON: {}.",
        "input_schema": {},
    },
]


def available_tools() -> list[dict[str, Any]]:
    return [dict(item) for item in TOOL_DEFINITIONS]


def _allow_private_network() -> bool:
    return os.environ.get("ORACLE_BROWSER_ALLOW_PRIVATE_NETWORK", "0").lower() in {
        "1", "true", "yes"
    }


def _validate_url(url: str) -> str:
    if not isinstance(url, str) or not url.strip() or len(url) > 2048:
        raise ValueError("url must be a non-empty URL under 2048 characters")
    parsed = urlparse(url.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("Only absolute HTTP and HTTPS URLs are supported")
    if parsed.username or parsed.password:
        raise ValueError("URLs containing embedded credentials are not allowed")
    if not _allow_private_network():
        host = parsed.hostname.rstrip(".").casefold()
        if host in {"localhost", "localhost.localdomain"} or host.endswith(".local"):
            raise PermissionError("Private and local network destinations are disabled")
        try:
            addresses = [ipaddress.ip_address(host)]
        except ValueError:
            try:
                addresses = [
                    ipaddress.ip_address(item[4][0])
                    for item in socket.getaddrinfo(host, parsed.port or (443 if parsed.scheme == "https" else 80))
                ]
            except OSError as exc:
                raise ValueError("The website hostname could not be resolved") from exc
        if not addresses or any(not address.is_global for address in addresses):
            raise PermissionError("Private, loopback and non-global destinations are disabled")
    return url.strip()


def _ensure_browser():
    global _CONTEXT, _PAGE, _PLAYWRIGHT
    if _CONTEXT is not None and _PAGE is not None and not _PAGE.is_closed():
        return _PAGE
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError(
            "Playwright is not installed. Install requirements, then run: "
            "python -m playwright install chromium"
        ) from exc
    profile = Path(
        os.environ.get(
            "ORACLE_BROWSER_PROFILE",
            str(Path.home() / ".personal_ai_oracle" / "browser-profile"),
        )
    ).expanduser()
    profile.mkdir(parents=True, exist_ok=True)
    headless = os.environ.get("ORACLE_BROWSER_HEADLESS", "1").lower() not in {
        "0", "false", "no"
    }
    _PLAYWRIGHT = sync_playwright().start()
    _CONTEXT = _PLAYWRIGHT.chromium.launch_persistent_context(
        user_data_dir=str(profile),
        headless=headless,
        args=["--disable-background-networking", "--disable-sync"],
    )

    def guard_route(route):
        try:
            _validate_url(route.request.url)
        except (ValueError, PermissionError):
            route.abort()
        else:
            route.continue_()

    _CONTEXT.route("**/*", guard_route)
    pages = _CONTEXT.pages
    _PAGE = pages[0] if pages else _CONTEXT.new_page()
    return _PAGE


def execute(tool_id: str, tool_input: dict[str, Any] | str) -> dict[str, Any]:
    if isinstance(tool_input, str):
        import json
        try:
            tool_input = json.loads(tool_input)
        except ValueError:
            return {"name": tool_id, "status": "error", "result": "Input must be valid JSON"}
    if not isinstance(tool_input, dict):
        return {"name": tool_id, "status": "error", "result": "Input must be a JSON object"}

    try:
        if tool_id == "web.search":
            query = tool_input.get("query")
            maximum = tool_input.get("max_results", 6)
            if not isinstance(query, str) or not query.strip():
                raise ValueError("query is required")
            if isinstance(maximum, bool) or not isinstance(maximum, int):
                raise ValueError("max_results must be an integer")
            maximum = max(1, min(maximum, 10))
            results = web_search(query.strip()[:500], maximum)
            return {
                "name": tool_id,
                "status": "success",
                "result": results,
            }

        with _BROWSER_LOCK:
            page = _ensure_browser()
            if tool_id == "web.open_browser":
                return {
                    "name": tool_id,
                    "status": "success",
                    "result": "Oracle's isolated browser is ready. Sign into websites manually in the visible browser window if needed.",
                }
            if tool_id == "web.navigate":
                url = _validate_url(tool_input.get("url", ""))
                response = page.goto(url, wait_until="domcontentloaded", timeout=45_000)
                final_url = _validate_url(page.url)
                title = page.title()[:300]
                text = page.locator("body").inner_text(timeout=10_000)
                return {
                    "name": tool_id,
                    "status": "success",
                    "result": {
                        "url": final_url,
                        "title": title,
                        "http_status": response.status if response else None,
                        "text": text[:MAX_PAGE_TEXT],
                    },
                }
            if tool_id == "web.extract":
                if not page.url or page.url == "about:blank":
                    raise ValueError("No webpage is open yet")
                return {
                    "name": tool_id,
                    "status": "success",
                    "result": {
                        "url": _validate_url(page.url),
                        "title": page.title()[:300],
                        "text": page.locator("body").inner_text(timeout=10_000)[:MAX_PAGE_TEXT],
                    },
                }
            if tool_id == "web.links":
                if not page.url or page.url == "about:blank":
                    raise ValueError("No webpage is open yet")
                limit = tool_input.get("limit", 40)
                if isinstance(limit, bool) or not isinstance(limit, int):
                    raise ValueError("limit must be an integer")
                limit = max(1, min(limit, 100))
                links = page.locator("a[href]").evaluate_all(
                    """nodes => nodes.slice(0, 100).map(a => ({
                        text: (a.innerText || a.getAttribute('aria-label') || '').trim().slice(0, 180),
                        href: a.href
                    }))"""
                )
                safe_links = []
                for link in links:
                    try:
                        href = _validate_url(link.get("href", ""))
                    except (ValueError, PermissionError):
                        continue
                    safe_links.append({"text": link.get("text", ""), "url": href})
                    if len(safe_links) >= limit:
                        break
                return {"name": tool_id, "status": "success", "result": safe_links}
        raise ValueError(f"Unknown web tool: {tool_id}")
    except Exception as exc:
        return {
            "name": tool_id,
            "status": "error",
            "result": f"{type(exc).__name__}: {str(exc)[:1000]}",
        }


def close_browser() -> None:
    global _CONTEXT, _PAGE, _PLAYWRIGHT
    with _BROWSER_LOCK:
        if _CONTEXT is not None:
            _CONTEXT.close()
        if _PLAYWRIGHT is not None:
            _PLAYWRIGHT.stop()
        _CONTEXT = None
        _PAGE = None
        _PLAYWRIGHT = None
