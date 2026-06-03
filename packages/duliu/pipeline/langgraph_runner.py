"""M7 LangGraph ProblemGraph — wraps PipelineFacade.dispatch_core."""

from __future__ import annotations

import uuid
from typing import Any, TypedDict

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph
from sqlalchemy.ext.asyncio import AsyncSession

from duliu.config import settings
from duliu.db.models import Problem

_saver = MemorySaver()
_compiled: Any = None


class DispatchGraphState(TypedDict, total=False):
    problem_id: str
    stage_id: str
    reason: str
    run_id: str
    result: dict
    langgraph: bool


def _get_graph():
    global _compiled
    if _compiled is not None:
        return _compiled

    async def dispatch_node(state: DispatchGraphState, config) -> dict:
        from duliu.facade.pipeline import PipelineFacade

        conf = config.get("configurable") or {}
        session: AsyncSession = conf["session"]
        problem: Problem = conf["problem"]
        run_id = uuid.UUID(state["run_id"]) if state.get("run_id") else None
        result = await PipelineFacade.dispatch_core(
            session,
            problem,
            state["stage_id"],
            reason=state.get("reason") or "",
            run_id=run_id,
        )
        return {"result": result, "langgraph": True}

    builder = StateGraph(DispatchGraphState)
    builder.add_node("dispatch", dispatch_node)
    builder.set_entry_point("dispatch")
    builder.add_edge("dispatch", END)
    _compiled = builder.compile(checkpointer=_saver)
    return _compiled


async def invoke_dispatch(
    session: AsyncSession,
    problem: Problem,
    stage_id: str,
    *,
    reason: str = "",
    run_id: uuid.UUID | None = None,
) -> dict:
    """Run dispatch through LangGraph (MemorySaver checkpoint per problem thread)."""
    graph = _get_graph()
    rid = run_id or uuid.uuid4()
    thread_id = (problem.spec_json or {}).get("langgraph_thread_id") or str(problem.id)
    if not (problem.spec_json or {}).get("langgraph_thread_id"):
        problem.spec_json = {**(problem.spec_json or {}), "langgraph_thread_id": thread_id}
    config = {
        "configurable": {
            "thread_id": thread_id,
            "session": session,
            "problem": problem,
        }
    }
    initial: DispatchGraphState = {
        "problem_id": str(problem.id),
        "stage_id": stage_id,
        "reason": reason,
        "run_id": str(rid),
    }
    final = await graph.ainvoke(initial, config)
    result = final.get("result") or {}
    result["langgraph"] = True
    result["thread_id"] = thread_id
    return result


def langgraph_enabled() -> bool:
    return bool(settings.use_langgraph)
