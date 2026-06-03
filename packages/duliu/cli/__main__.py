#!/usr/bin/env python3
"""Duliu CLI — calls the same REST API as Web (M5)."""

from __future__ import annotations

import argparse
import json
import os
import sys
import uuid

import httpx

BASE = os.environ.get("DULIU_API", "http://localhost:8000").rstrip("/")


def _req(method: str, path: str, **kwargs) -> dict | list:
    url = f"{BASE}{path}"
    with httpx.Client(timeout=120.0) as client:
        r = client.request(method, url, **kwargs)
        if r.status_code >= 400:
            print(r.text, file=sys.stderr)
            sys.exit(1)
        if not r.content:
            return {}
        return r.json()


def cmd_health(_: argparse.Namespace) -> None:
    print(json.dumps(_req("GET", "/api/health"), ensure_ascii=False))


def cmd_tree(_: argparse.Namespace) -> None:
    t = _req("GET", "/api/tree")
    print(f"Workspace: {t['workspace']['name']}")
    for c in t.get("contest_sets", []):
        print(f"  [套题] {c['name']} ({c['id']})")
    for p in t.get("problems", []):
        print(f"  [单题] {p['title']} stage={p['current_stage']} ({p['id']})")


def cmd_status(args: argparse.Namespace) -> None:
    p = _req("GET", f"/api/problems/{args.problem_id}")
    print(f"{p['title']}: stage={p['current_stage']} originality={p.get('originality', 'ORIGINAL')}")
    stages = _req("GET", f"/api/problems/{args.problem_id}/stages")
    for s in stages:
        print(f"  {s['stage_id']}: {s['status']}")


def cmd_approve(args: argparse.Namespace) -> None:
    p = _req("GET", f"/api/problems/{args.problem_id}")
    stage = args.stage or p["current_stage"]
    _req(
        "POST",
        f"/api/problems/{args.problem_id}/stages/{stage}/approve",
        json={"note": args.note},
    )
    print(f"Approved {stage}")


def cmd_dispatch(args: argparse.Namespace) -> None:
    p = _req("GET", f"/api/problems/{args.problem_id}")
    stage = args.stage or p["current_stage"]
    out = _req(
        "POST",
        f"/api/problems/{args.problem_id}/dispatch",
        json={"stage_id": stage, "reason": "cli"},
    )
    print(json.dumps(out.get("dispatch", out), ensure_ascii=False, indent=2))


def cmd_crawl(args: argparse.Namespace) -> None:
    out = _req("POST", "/api/crawl/import", json={"url": args.url, "title": args.title})
    print(f"problem_id={out['problem']['id']} job_id={out['job']['id']}")
    if args.wait:
        _poll_job(out["job"]["id"])


def cmd_job(args: argparse.Namespace) -> None:
    if args.cancel:
        j = _req("POST", f"/api/jobs/{args.job_id}/cancel")
        print(json.dumps(j, ensure_ascii=False))
        return
    j = _req("GET", f"/api/jobs/{args.job_id}")
    print(json.dumps(j, ensure_ascii=False, indent=2))


def _poll_job(job_id: str) -> None:
    import time

    for _ in range(120):
        j = _req("GET", f"/api/jobs/{job_id}")
        if j["status"] in ("done", "failed", "cancelled"):
            print(json.dumps(j, ensure_ascii=False, indent=2))
            return
        time.sleep(1)
    print("timeout", file=sys.stderr)
    sys.exit(1)


def cmd_import_check(args: argparse.Namespace) -> None:
    job = _req("POST", f"/api/problems/{args.problem_id}/import/check")
    print(f"job_id={job['id']}")
    if args.wait:
        _poll_job(job["id"])


def cmd_confirm_submission(args: argparse.Namespace) -> None:
    _req(
        "POST",
        f"/api/problems/{args.problem_id}/import/confirm-submission",
        json={"submission_url": args.url, "handle": args.handle},
    )
    print("submission confirmed")


def cmd_chat(args: argparse.Namespace) -> None:
    sid = args.session_id
    if not sid:
        s = _req("POST", "/api/sessions", json={"title": "CLI", "problem_id": args.problem_id})
        sid = s["id"]
    body = {"message": args.message}
    if args.problem_id:
        body["problem_id"] = args.problem_id
    out = _req("POST", f"/api/sessions/{sid}/chat", json=body)
    print(out["assistant"]["content"])


def main() -> None:
    p = argparse.ArgumentParser(prog="duliu", description="Duliu CLI (M5)")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("health", help="API health").set_defaults(func=cmd_health)
    sub.add_parser("tree", help="List workspace tree").set_defaults(func=cmd_tree)

    s = sub.add_parser("status", help="Problem stage status")
    s.add_argument("problem_id", type=uuid.UUID)
    s.set_defaults(func=cmd_status)

    a = sub.add_parser("approve", help="Approve stage gate")
    a.add_argument("problem_id", type=uuid.UUID)
    a.add_argument("--stage", default=None)
    a.add_argument("--note", default=None)
    a.set_defaults(func=cmd_approve)

    d = sub.add_parser("dispatch", help="Dispatch stage agent")
    d.add_argument("problem_id", type=uuid.UUID)
    d.add_argument("--stage", default=None)
    d.set_defaults(func=cmd_dispatch)

    c = sub.add_parser("crawl", help="Import NON_ORIGINAL from URL")
    c.add_argument("url")
    c.add_argument("--title", default=None)
    c.add_argument("--wait", action="store_true")
    c.set_defaults(func=cmd_crawl)

    j = sub.add_parser("job", help="Get or cancel job")
    j.add_argument("job_id", type=uuid.UUID)
    j.add_argument("--cancel", action="store_true")
    j.set_defaults(func=cmd_job)

    ic = sub.add_parser("import-check", help="Run import_check stress")
    ic.add_argument("problem_id", type=uuid.UUID)
    ic.add_argument("--wait", action="store_true")
    ic.set_defaults(func=cmd_import_check)

    cs = sub.add_parser("confirm-submission", help="Confirm original OJ submission")
    cs.add_argument("problem_id", type=uuid.UUID)
    cs.add_argument("--url", default=None)
    cs.add_argument("--handle", default=None)
    cs.set_defaults(func=cmd_confirm_submission)

    ch = sub.add_parser("chat", help="Session agent message")
    ch.add_argument("message")
    ch.add_argument("--problem-id", dest="problem_id", type=uuid.UUID, default=None)
    ch.add_argument("--session-id", dest="session_id", default=None)
    ch.set_defaults(func=cmd_chat)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
