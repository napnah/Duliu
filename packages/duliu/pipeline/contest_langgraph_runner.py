"""M17 LangGraph contest set evaluation: scan_slots → evaluate → finalize."""

from __future__ import annotations

import uuid
from typing import Any, TypedDict

from sqlalchemy.ext.asyncio import AsyncSession

from duliu.config import settings
from duliu.db.models import ContestSet

_compiled: Any = None

CONTEST_GRAPH_NODES = ("scan_slots", "evaluate", "finalize")


class ContestEvalState(TypedDict, total=False):
    contest_set_id: str
    slot_summary: list
    report: dict
    langgraph: bool


def contest_graph_metadata() -> dict:
    return {
        "nodes": list(CONTEST_GRAPH_NODES),
        "edges": [
            ["scan_slots", "evaluate"],
            ["evaluate", "finalize"],
            ["finalize", "END"],
        ],
    }


async def _get_graph():
    global _compiled
    if _compiled is not None:
        return _compiled

    from langgraph.graph import END, StateGraph

    from duliu.pipeline.checkpoint_saver import get_checkpointer

    checkpointer = await get_checkpointer()

    async def scan_slots_node(state: ContestEvalState, config) -> dict:
        from sqlalchemy import select

        from duliu.db.models import ContestSlot, Problem

        conf = config.get("configurable") or {}
        session: AsyncSession = conf["session"]
        contest_set: ContestSet = conf["contest_set"]
        slots = (
            await session.execute(
                select(ContestSlot)
                .where(ContestSlot.contest_set_id == contest_set.id)
                .order_by(ContestSlot.slot_label)
            )
        ).scalars().all()
        summary = []
        for slot in slots:
            row = {"slot_label": slot.slot_label, "status": slot.status}
            if slot.problem_id:
                p = await session.get(Problem, slot.problem_id)
                if p:
                    row["title"] = p.title
                    row["stage"] = p.current_stage
            summary.append(row)
        return {"slot_summary": summary}

    async def evaluate_node(state: ContestEvalState, config) -> dict:
        from duliu.facade.contest import ContestFacade

        conf = config.get("configurable") or {}
        session: AsyncSession = conf["session"]
        contest_set: ContestSet = conf["contest_set"]
        report = await ContestFacade.evaluate_set_core(session, contest_set)
        return {"report": report}

    async def finalize_node(state: ContestEvalState, config) -> dict:
        report = dict(state.get("report") or {})
        report["graph_nodes"] = list(CONTEST_GRAPH_NODES)
        report["finalized"] = True
        report["slot_count"] = len(state.get("slot_summary") or [])
        return {"report": report, "langgraph": True}

    builder = StateGraph(ContestEvalState)
    builder.add_node("scan_slots", scan_slots_node)
    builder.add_node("evaluate", evaluate_node)
    builder.add_node("finalize", finalize_node)
    builder.set_entry_point("scan_slots")
    builder.add_edge("scan_slots", "evaluate")
    builder.add_edge("evaluate", "finalize")
    builder.add_edge("finalize", END)
    _compiled = builder.compile(checkpointer=checkpointer)
    return _compiled


async def invoke_contest_eval(
    session: AsyncSession,
    contest_set: ContestSet,
) -> dict:
    """Run set evaluation via LangGraph or direct facade fallback."""
    from duliu.facade.contest import ContestFacade

    if not settings.use_langgraph:
        return await ContestFacade.evaluate_set_core(session, contest_set)

    try:
        graph = await _get_graph()
    except (ImportError, ModuleNotFoundError):
        return await ContestFacade.evaluate_set_core(session, contest_set)

    thread_id = (contest_set.set_eval_json or {}).get("langgraph_thread_id") or str(contest_set.id)
    if not (contest_set.set_eval_json or {}).get("langgraph_thread_id"):
        contest_set.set_eval_json = {
            **(contest_set.set_eval_json or {}),
            "langgraph_thread_id": thread_id,
        }

    config = {
        "configurable": {
            "thread_id": thread_id,
            "session": session,
            "contest_set": contest_set,
        }
    }
    initial: ContestEvalState = {"contest_set_id": str(contest_set.id)}
    final = await graph.ainvoke(initial, config)
    report = final.get("report") or {}
    report["langgraph"] = True
    report["thread_id"] = thread_id
    from duliu.pipeline.checkpoint_saver import checkpointer_mode

    report["checkpointer"] = checkpointer_mode()
    report["graph"] = contest_graph_metadata()
    return report


async def list_contest_checkpoint_history(thread_id: str, *, limit: int = 20) -> list[dict]:
    """List LangGraph state snapshots for a contest set evaluation thread."""
    if not settings.use_langgraph:
        return []
    try:
        graph = await _get_graph()
    except (ImportError, ModuleNotFoundError):
        return []
    config = {"configurable": {"thread_id": thread_id}}
    items: list[dict] = []
    try:
        async for snap in graph.aget_state_history(config, limit=limit):
            vals = snap.values or {}
            items.append(
                {
                    "checkpoint_id": snap.config.get("configurable", {}).get("checkpoint_id"),
                    "slot_count": len(vals.get("slot_summary") or []),
                    "has_report": bool(vals.get("report")),
                    "finalized": (vals.get("report") or {}).get("finalized"),
                    "langgraph": vals.get("langgraph"),
                }
            )
    except Exception:
        return items
    return items
