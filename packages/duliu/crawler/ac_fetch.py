"""M10: fetch Codeforces AC submission source as std (requires cookie)."""

from __future__ import annotations

import json
import re
from urllib.parse import urlparse

import httpx

from duliu.crawler.fetch import fetch_url


def _parse_cf_problem_url(url: str) -> tuple[int, str]:
    m = re.search(r"/problemset/problem/(\d+)/([A-Za-z0-9]+)", url)
    if not m:
        m = re.search(r"/contest/(\d+)/problem/([A-Za-z0-9]+)", url)
    if not m:
        raise ValueError("Cannot parse Codeforces problem URL")
    return int(m.group(1)), m.group(2).upper()


async def _cf_api_status(contest_id: int, index: str, *, handle: str | None) -> list[dict]:
    params = f"contestId={contest_id}&index={index}"
    if handle:
        params = f"handle={handle}&" + params
    api = f"https://codeforces.com/api/contest.status?{params}"
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.get(api)
        r.raise_for_status()
        data = r.json()
    if data.get("status") != "OK":
        raise ValueError(data.get("comment", "CF API error"))
    return data.get("result", [])


async def _fetch_submission_source(submission_id: int, cookie: str) -> str:
    url = f"https://codeforces.com/data/submitSource?submissionId={submission_id}"
    html = await fetch_url(url, cookie=cookie)
    m = re.search(r'<pre[^>]*>(.*?)</pre>', html, re.S | re.I)
    if m:
        from html import unescape

        return unescape(m.group(1)).strip()
    m2 = re.search(r'"sourceCode"\s*:\s*"((?:\\.|[^"])*)"', html)
    if m2:
        return json.loads(f'"{m2.group(1)}"')
    if len(html) < 50000 and ("int main" in html or "def " in html or "#include" in html):
        return html.strip()[:50000]
    raise ValueError("Could not parse submission source (check CF cookie)")


async def fetch_ac_std_for_problem(
    *,
    problem_url: str,
    cookie: str | None,
    handle: str | None = None,
) -> dict:
    """Return {submission_id, language, source} for latest AC on problem."""
    host = urlparse(problem_url).hostname or ""
    if "codeforces.com" not in host:
        raise ValueError("AC fetch only supports codeforces.com")
    if not cookie:
        raise ValueError("Codeforces cookie required in crawler settings")

    contest_id, index = _parse_cf_problem_url(problem_url)
    rows = await _cf_api_status(contest_id, index, handle=handle)
    ac_rows = [r for r in rows if r.get("verdict") == "OK"]
    if not ac_rows:
        raise ValueError("No AC submission found (try setting CF handle in import spec)")
    ac_rows.sort(key=lambda x: x.get("creationTimeSeconds", 0), reverse=True)
    sub = ac_rows[0]
    sid = int(sub["id"])
    source = await _fetch_submission_source(sid, cookie)
    lang = (sub.get("programmingLanguage") or "cpp").lower()
    if "python" in lang or lang == "py":
        plang = "python"
    elif "java" in lang:
        plang = "java"
    else:
        plang = "cpp"
    return {
        "submission_id": sid,
        "language": plang,
        "source": source,
        "handle": sub.get("author", {}).get("members", [None])[0],
    }
