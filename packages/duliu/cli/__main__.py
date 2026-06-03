#!/usr/bin/env python3
"""Duliu CLI — calls the same REST API as Web (M5)."""

from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from pathlib import Path

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
    pid = _pid(args)
    p = _req("GET", f"/api/problems/{pid}")
    print(f"{p['title']}: stage={p['current_stage']} originality={p.get('originality', 'ORIGINAL')}")
    stages = _req("GET", f"/api/problems/{pid}/stages")
    for s in stages:
        print(f"  {s['stage_id']}: {s['status']}")


def cmd_approve(args: argparse.Namespace) -> None:
    pid = _pid(args)
    p = _req("GET", f"/api/problems/{pid}")
    stage = args.stage or p["current_stage"]
    _req(
        "POST",
        f"/api/problems/{pid}/stages/{stage}/approve",
        json={"note": args.note},
    )
    print(f"Approved {stage}")


def cmd_dispatch(args: argparse.Namespace) -> None:
    pid = _pid(args)
    p = _req("GET", f"/api/problems/{pid}")
    stage = args.stage or p["current_stage"]
    out = _req(
        "POST",
        f"/api/problems/{pid}/dispatch",
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


def _pid(args: argparse.Namespace) -> str:
    from duliu.cli.workspace_sync import resolve_problem_id

    raw = getattr(args, "problem_id", None)
    return resolve_problem_id(str(raw) if raw else None)


def cmd_use(args: argparse.Namespace) -> None:
    from duliu.cli.workspace_sync import write_active

    p = _req("GET", f"/api/problems/{args.problem_id}")
    path = write_active(str(args.problem_id), p.get("title", ""))
    print(f"Active problem: {p['title']} ({args.problem_id})")
    print(f"Wrote {path}")


def cmd_pull(args: argparse.Namespace) -> None:
    from duliu.cli.workspace_sync import pull_tree

    pid = _pid(args)
    p = _req("GET", f"/api/problems/{pid}")
    listing = _req("GET", f"/api/problems/{pid}/artifacts")
    artifacts = []
    for item in listing.get("items", []):
        kind = item.get("kind")
        if not kind:
            continue
        try:
            art = _req("GET", f"/api/problems/{pid}/artifacts/{kind}")
            artifacts.append(art)
        except SystemExit:
            pass
    root = pull_tree(pid, artifacts, p)
    print(f"Pulled {len(artifacts)} artifacts -> {root}")


def cmd_push(args: argparse.Namespace) -> None:
    from duliu.cli.workspace_sync import collect_push_payload, problem_dir

    pid = _pid(args)
    root = problem_dir(pid)
    payloads = collect_push_payload(root)
    if not payloads:
        print(f"No files under {root}", file=sys.stderr)
        sys.exit(1)
    for kind, content, language in payloads:
        body = {"content_text": content, "author": "human"}
        if language:
            body["language"] = language
        _req("PUT", f"/api/problems/{pid}/artifacts/{kind}", json=body)
        print(f"  pushed {kind}")
    print("Done.")


def cmd_compile(args: argparse.Namespace) -> None:
    pid = _pid(args)
    body = {
        "program": args.program,
        "use_editor_draft": args.draft,
        "language": args.language,
    }
    if args.draft:
        src = None
        if args.source_file:
            src = Path(args.source_file).read_text(encoding="utf-8")
        else:
            src = _local_source(pid, args.program)
        if src:
            body["draft"] = {"language": args.language, "source": src}
    job = _req("POST", f"/api/problems/{pid}/compile", json=body)
    print(f"job_id={job['id']}")
    if args.wait:
        _poll_job(job["id"])


def cmd_run(args: argparse.Namespace) -> None:
    pid = _pid(args)
    body = {
        "program": args.program,
        "input": args.input or "",
        "use_editor_draft": args.draft,
        "language": args.language,
        "use_checker": args.checker,
    }
    if args.expected:
        body["expected_out"] = args.expected
    if args.draft:
        src = None
        if args.source_file:
            src = Path(args.source_file).read_text(encoding="utf-8")
        else:
            src = _local_source(pid, args.program)
        if src:
            body["draft"] = {"language": args.language, "source": src}
    job = _req("POST", f"/api/problems/{pid}/run", json=body)
    print(f"job_id={job['id']}")
    if args.wait:
        _poll_job(job["id"])


def cmd_stress(args: argparse.Namespace) -> None:
    pid = _pid(args)
    job = _req(
        "POST",
        f"/api/problems/{pid}/stress/run",
        json={"mode": args.mode},
    )
    print(f"job_id={job['id']}")
    if args.wait:
        _poll_job(job["id"])


def _local_source(pid: str, program: str) -> str | None:
    from duliu.cli.workspace_sync import problem_dir

    root = problem_dir(pid)
    if not root.is_dir():
        return None
    for path in sorted(root.glob(f"{program}.*")):
        if path.suffix.lower() in (".cpp", ".py", ".java"):
            return path.read_text(encoding="utf-8")
    return None


def cmd_watch(args: argparse.Namespace) -> None:
    import time

    if getattr(args, "problem_id", None):
        pid = str(args.problem_id)
    else:
        from duliu.cli.workspace_sync import active_problem_id

        pid = active_problem_id()
    url = f"{BASE}/api/monitor/events/stream"
    if pid:
        url += f"?problem_id={pid}"

    last_id = None
    with httpx.Client(timeout=None) as client:
        with client.stream("GET", url) as resp:
            if resp.status_code >= 400:
                print(resp.text, file=sys.stderr)
                sys.exit(1)
            for line in resp.iter_lines():
                if not line or not line.startswith("data:"):
                    continue
                payload = line[5:].strip()
                if payload == "[DONE]":
                    break
                try:
                    ev = json.loads(payload)
                except json.JSONDecodeError:
                    print(payload)
                    continue
                eid = ev.get("id")
                if eid == last_id:
                    continue
                last_id = eid
                ts = (ev.get("created_at") or "")[:19]
                print(f"{ts} [{ev.get('source')}] {ev.get('type')}: {ev.get('message')}")
                if args.once:
                    break
                time.sleep(0)


def cmd_chat(args: argparse.Namespace) -> None:
    pid = getattr(args, "problem_id", None)
    if pid is None:
        try:
            from duliu.cli.workspace_sync import active_problem_id

            ap = active_problem_id()
            if ap:
                pid = uuid.UUID(ap)
        except Exception:
            pass
    sid = args.session_id
    if not sid:
        s = _req(
            "POST",
            "/api/sessions",
            json={"title": "CLI", "problem_id": str(pid) if pid else None},
        )
        sid = s["id"]
    body = {"message": args.message}
    if pid:
        body["problem_id"] = str(pid)
    out = _req("POST", f"/api/sessions/{sid}/chat", json=body)
    print(out["assistant"]["content"])
    for i, act in enumerate(out.get("suggested_actions") or [], 1):
        print(f"  [{i}] {act.get('label')} ({act.get('kind', 'chat')})")


def _resolve_problem_id(args: argparse.Namespace) -> uuid.UUID | None:
    pid = getattr(args, "problem_id", None)
    if pid is not None:
        return pid
    try:
        from duliu.cli.workspace_sync import active_problem_id

        ap = active_problem_id()
        if ap:
            return uuid.UUID(ap)
    except Exception:
        pass
    return None


def cmd_workflow_list(_: argparse.Namespace) -> None:
    rows = _req("GET", "/api/creation-workflows")
    for w in rows:
        triggers = ", ".join(w.get("chat_triggers") or [])
        req = "需题目" if w.get("requires_problem") else "可无题目"
        print(f"{w['id']:20} {w['name_zh']} [{req}]")
        print(f"  {w.get('summary', '')}")
        if triggers:
            print(f"  触发: {triggers}")
        print()


def cmd_workflow_run(args: argparse.Namespace) -> None:
    wid = args.workflow_id
    params: dict = {}
    if args.params_json:
        params = json.loads(args.params_json)
    if args.difficulty is not None:
        params["difficulty"] = args.difficulty
    if args.topics:
        params["topics"] = [t.strip() for t in args.topics.split(",") if t.strip()]
    if args.style:
        params["style"] = args.style
    if args.contest_style:
        params["contest_style"] = args.contest_style.upper()
    pid = _resolve_problem_id(args)
    body = {"params": params}
    if pid:
        out = _req(
            "POST",
            f"/api/problems/{pid}/creation-workflows/{wid}/run",
            json=body,
        )
    else:
        out = _req(
            "POST",
            f"/api/creation-workflows/{wid}/run",
            json=body,
            params={"problem_id": str(pid)} if pid else None,
        )
    print(out.get("summary") or out)
    preview = out.get("report_preview")
    if preview:
        print("\n--- preview ---\n")
        print(preview[:4000])


def cmd_chat_repl(args: argparse.Namespace) -> None:
    pid = args.problem_id
    if pid is None:
        try:
            from duliu.cli.workspace_sync import active_problem_id

            ap = active_problem_id()
            if ap:
                pid = uuid.UUID(ap)
        except Exception:
            pass
    s = _req(
        "POST",
        "/api/sessions",
        json={"title": "CLI REPL", "problem_id": str(pid) if pid else None},
    )
    sid = s["id"]
    print("Duliu chat-repl — Enter 发送，/quit 退出")
    while True:
        try:
            text = input("you> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not text or text in ("/quit", "/exit", "/q"):
            break
        body = {"message": text}
        if pid:
            body["problem_id"] = str(pid)
        out = _req("POST", f"/api/sessions/{sid}/chat", json=body)
        print(f"assistant> {out['assistant']['content']}\n")
        actions = out.get("suggested_actions") or []
        if actions:
            print("建议下一步:")
            for i, act in enumerate(actions, 1):
                print(f"  {i}. {act.get('label')} — 输入数字执行，或继续打字")
            choice = input("choice> ").strip()
            if choice.isdigit():
                idx = int(choice) - 1
                if 0 <= idx < len(actions):
                    act = actions[idx]
                    msg = act.get("message") or act.get("label")
                    if act.get("kind") == "chat" and msg:
                        body = {"message": msg}
                        if pid:
                            body["problem_id"] = str(pid)
                        out2 = _req("POST", f"/api/sessions/{sid}/chat", json=body)
                        print(f"assistant> {out2['assistant']['content']}\n")


def main() -> None:
    p = argparse.ArgumentParser(prog="duliu", description="Duliu CLI (M5)")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("health", help="API health").set_defaults(func=cmd_health)
    sub.add_parser("tree", help="List workspace tree").set_defaults(func=cmd_tree)

    s = sub.add_parser("status", help="Problem stage status")
    s.add_argument("problem_id", type=uuid.UUID, nargs="?", default=None)
    s.set_defaults(func=cmd_status)

    a = sub.add_parser("approve", help="Approve stage gate")
    a.add_argument("problem_id", type=uuid.UUID, nargs="?", default=None)
    a.add_argument("--stage", default=None)
    a.add_argument("--note", default=None)
    a.set_defaults(func=cmd_approve)

    d = sub.add_parser("dispatch", help="Dispatch stage agent")
    d.add_argument("problem_id", type=uuid.UUID, nargs="?", default=None)
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

    cr = sub.add_parser("chat-repl", help="Interactive session agent (IDE terminal)")
    cr.add_argument("--problem-id", dest="problem_id", type=uuid.UUID, default=None)
    cr.set_defaults(func=cmd_chat_repl)

    u = sub.add_parser("use", help="Set active problem (.duliu/active.json)")
    u.add_argument("problem_id", type=uuid.UUID)
    u.set_defaults(func=cmd_use)

    pl = sub.add_parser("pull", help="Pull artifacts to .duliu/problems/<id>/")
    pl.add_argument("problem_id", type=uuid.UUID, nargs="?", default=None)
    pl.set_defaults(func=cmd_pull)

    ps = sub.add_parser("push", help="Push local files to API artifacts")
    ps.add_argument("problem_id", type=uuid.UUID, nargs="?", default=None)
    ps.set_defaults(func=cmd_push)

    co = sub.add_parser("compile", help="Compile program")
    co.add_argument("problem_id", type=uuid.UUID, nargs="?", default=None)
    co.add_argument("--program", default="std")
    co.add_argument("--language", default="cpp")
    co.add_argument("--draft", action="store_true", help="Use --source-file as draft")
    co.add_argument("--source-file", default=None, help="Local source (e.g. .duliu/.../std.cpp)")
    co.add_argument("--wait", action="store_true")
    co.set_defaults(func=cmd_compile)

    rn = sub.add_parser("run", help="Run program with stdin")
    rn.add_argument("problem_id", type=uuid.UUID, nargs="?", default=None)
    rn.add_argument("--program", default="std")
    rn.add_argument("--input", default="")
    rn.add_argument("--expected", default=None)
    rn.add_argument("--language", default="cpp")
    rn.add_argument("--draft", action="store_true")
    rn.add_argument("--source-file", default=None)
    rn.add_argument("--checker", action="store_true")
    rn.add_argument("--wait", action="store_true")
    rn.set_defaults(func=cmd_run)

    st = sub.add_parser("stress", help="Stress test (quick/import_check)")
    st.add_argument("problem_id", type=uuid.UUID, nargs="?", default=None)
    st.add_argument("--mode", default="quick", choices=["quick", "import_check", "full"])
    st.add_argument("--wait", action="store_true")
    st.set_defaults(func=cmd_stress)

    w = sub.add_parser("watch", help="Tail monitor SSE for active problem")
    w.add_argument("problem_id", type=uuid.UUID, nargs="?", default=None)
    w.add_argument("--once", action="store_true", help="Print one event batch and exit")
    w.set_defaults(func=cmd_watch)

    wf = sub.add_parser("workflow", help="五步出题流程 (creation workflows)")
    wf_sub = wf.add_subparsers(dest="workflow_cmd", required=True)
    wf_sub.add_parser("list", help="List workflows").set_defaults(func=cmd_workflow_list)
    wr = wf_sub.add_parser("run", help="Run a workflow")
    wr.add_argument(
        "workflow_id",
        choices=[
            "find_problem",
            "write_statement",
            "solution_analysis",
            "generate_data",
            "write_editorial",
        ],
    )
    wr.add_argument("problem_id", type=uuid.UUID, nargs="?", default=None)
    wr.add_argument("--difficulty", type=int, default=None, help="CF rating / 难度")
    wr.add_argument("--topics", default=None, help="知识点，逗号分隔")
    wr.add_argument("--style", default=None, help="codeforces | noip")
    wr.add_argument("--contest-style", dest="contest_style", default=None, help="OI | ICPC")
    wr.add_argument("--params-json", default=None, help='JSON params, e.g. \'{"count":8}\'')
    wr.set_defaults(func=cmd_workflow_run)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
