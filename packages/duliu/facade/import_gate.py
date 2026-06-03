"""M6 gates for NON_ORIGINAL import flow."""

from __future__ import annotations

from duliu.db.models import Problem


def submission_confirmed(problem: Problem) -> bool:
    imp = problem.spec_json.get("import") or {}
    req = imp.get("submission_requirement") or {}
    return bool(req.get("user_confirmed"))


def import_ready(problem: Problem) -> bool:
    imp = problem.spec_json.get("import") or {}
    return imp.get("status") == "imported"


def import_check_passed(problem: Problem) -> bool:
    imp = problem.spec_json.get("import") or {}
    chk = imp.get("import_check") or {}
    return bool(chk.get("ok"))


def validate_approve(problem: Problem, stage_id: str) -> None:
    if problem.originality != "NON_ORIGINAL":
        return
    if stage_id == "IMPORT":
        if not import_ready(problem):
            raise ValueError("IMPORT: 请先完成爬取导入（statement）")
        if not import_check_passed(problem):
            raise ValueError("IMPORT: 请先运行 import_check 对拍并通过")
        if not submission_confirmed(problem):
            raise ValueError("IMPORT: 请确认已在原题平台提交")
        return
    if not submission_confirmed(problem):
        raise ValueError("NON_ORIGINAL: 请先在流水线确认「已在原题平台提交」")


def validate_dispatch(problem: Problem, stage_id: str) -> None:
    from duliu.db.models import stage_order_for

    if problem.originality != "NON_ORIGINAL":
        return
    order = stage_order_for(problem.contest_style, problem.originality)
    if stage_id not in order:
        return
    if "IMPORT" in order and order.index(stage_id) > order.index("IMPORT") and not import_ready(problem):
        raise ValueError("请先完成 IMPORT 爬取")
    if "SOLUTION" in order and order.index(stage_id) >= order.index("SOLUTION"):
        if not submission_confirmed(problem):
            raise ValueError("NON_ORIGINAL: 请先确认原题提交")
