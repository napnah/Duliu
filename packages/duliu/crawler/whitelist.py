"""Allowed crawl hosts for NON_ORIGINAL import (M5)."""

from urllib.parse import urlparse

ALLOWED_HOSTS = frozenset(
    {
        "codeforces.com",
        "www.codeforces.com",
        "atcoder.jp",
        "luogu.com.cn",
        "www.luogu.com.cn",
    }
)

PLATFORM_BY_HOST = {
    "codeforces.com": "codeforces",
    "www.codeforces.com": "codeforces",
    "atcoder.jp": "atcoder",
    "luogu.com.cn": "luogu",
    "www.luogu.com.cn": "luogu",
}


def validate_url(url: str) -> tuple[str, str]:
    """Return (platform, normalized_url) or raise ValueError."""
    parsed = urlparse(url.strip())
    if parsed.scheme not in ("http", "https"):
        raise ValueError("URL must be http or https")
    host = (parsed.hostname or "").lower()
    if host not in ALLOWED_HOSTS:
        raise ValueError(f"Host not in whitelist: {host}")
    platform = PLATFORM_BY_HOST.get(host, "other")
    return platform, url.strip()
