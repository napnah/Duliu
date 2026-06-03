"""Lightweight HTML parsers for whitelisted OJ problem pages."""

from __future__ import annotations

import re
from html import unescape


def _strip_tags(html: str) -> str:
    text = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.I | re.S)
    text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.I | re.S)
    text = re.sub(r"<[^>]+>", " ", text)
    return unescape(re.sub(r"\s+", " ", text)).strip()


def parse_codeforces(html: str, url: str) -> dict:
    title_m = re.search(
        r'<div\s+class="title"\s*>.*?<a[^>]*>([^<]+)</a>',
        html,
        re.I | re.S,
    )
    title = unescape(title_m.group(1).strip()) if title_m else "Codeforces Problem"
    pid_m = re.search(r"/problemset/problem/(\d+)/([A-Za-z0-9]+)", url)
    problem_id = f"CF{pid_m.group(1)}{pid_m.group(2)}" if pid_m else None
    stmt_m = re.search(
        r'<div\s+class="problem-statement"[^>]*>(.*?)</div>\s*<div\s+class="problem-constraints"',
        html,
        re.I | re.S,
    )
    statement = _strip_tags(stmt_m.group(1))[:12000] if stmt_m else ""
    if not statement:
        stmt_m2 = re.search(r'<div\s+class="problem-statement"[^>]*>(.*?)</div>', html, re.I | re.S)
        statement = _strip_tags(stmt_m2.group(1))[:12000] if stmt_m2 else _strip_tags(html)[:4000]
    return {
        "title": title,
        "problem_id": problem_id,
        "statement_markdown": f"# {title}\n\n来源: {url}\n\n{statement}",
        "platform": "codeforces",
    }


def parse_luogu(html: str, url: str) -> dict:
    title_m = re.search(r"<title>([^<]+)</title>", html, re.I)
    raw = title_m.group(1) if title_m else "Luogu Problem"
    title = raw.split("-")[0].strip() if "-" in raw else raw.strip()
    pid_m = re.search(r"problem/(P\d+)", url, re.I)
    problem_id = pid_m.group(1).upper() if pid_m else None
    content_m = re.search(r'class="markdown"[^>]*>(.*?)</div>', html, re.I | re.S)
    statement = _strip_tags(content_m.group(1))[:12000] if content_m else ""
    return {
        "title": title or "Luogu Problem",
        "problem_id": problem_id,
        "statement_markdown": f"# {title}\n\n来源: {url}\n\n{statement or '(请在本站查看完整题面)'}",
        "platform": "luogu",
    }


def parse_atcoder(html: str, url: str) -> dict:
    title_m = re.search(r'<span\s+class="h2"[^>]*>([^<]+)</span>', html, re.I)
    title = unescape(title_m.group(1).strip()) if title_m else "AtCoder Problem"
    task_m = re.search(r"tasks/([a-z0-9_]+)", url, re.I)
    problem_id = task_m.group(1) if task_m else None
    stmt_m = re.search(
        r'<div[^>]*id="task-statement"[^>]*>(.*?)</div>\s*<div[^>]*class="part"',
        html,
        re.I | re.S,
    )
    if not stmt_m:
        stmt_m = re.search(r'<div[^>]*id="task-statement"[^>]*>(.*)', html, re.I | re.S)
    statement = _strip_tags(stmt_m.group(1))[:12000] if stmt_m else ""
    return {
        "title": title,
        "problem_id": problem_id,
        "statement_markdown": f"# {title}\n\n来源: {url}\n\n{statement}",
        "platform": "atcoder",
    }


def parse_problem_html(html: str, platform: str, url: str) -> dict:
    if platform == "codeforces":
        return parse_codeforces(html, url)
    if platform == "luogu":
        return parse_luogu(html, url)
    if platform == "atcoder":
        return parse_atcoder(html, url)
    return {
        "title": "Imported Problem",
        "problem_id": None,
        "statement_markdown": f"来源: {url}\n\n{_strip_tags(html)[:4000]}",
        "platform": platform,
    }
