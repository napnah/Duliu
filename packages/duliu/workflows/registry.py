"""User-facing problem creation workflows (五步出题流程)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class CreationWorkflowMeta:
    id: str
    name_zh: str
    summary: str
    requires_problem: bool
    chat_triggers: tuple[str, ...]


CREATION_WORKFLOWS: dict[str, CreationWorkflowMeta] = {
    "find_problem": CreationWorkflowMeta(
        id="find_problem",
        name_zh="1 · 找题 / 想 idea",
        summary="按难度、知识点、OI 部分分适宜性搜集/推荐候选题",
        requires_problem=False,
        chat_triggers=("找题", "搜题", "选题", "想题", "找 idea", "find problem"),
    ),
    "write_statement": CreationWorkflowMeta(
        id="write_statement",
        name_zh="2 · 编写题面",
        summary="生成 Codeforces 或 NOIP 风格 Markdown 题面",
        requires_problem=True,
        chat_triggers=("写题面", "题面", "statement", "编写题面"),
    ),
    "solution_analysis": CreationWorkflowMeta(
        id="solution_analysis",
        name_zh="3 · 数据范围与解法",
        summary="OI：部分分与子任务；ICPC：正解与错误解法甄别",
        requires_problem=True,
        chat_triggers=("解法分析", "部分分", "数据范围", "解法", "solution analysis"),
    ),
    "generate_data": CreationWorkflowMeta(
        id="generate_data",
        name_zh="4 · 生成数据",
        summary="按正解/gen 与 testlib 思路生成测试；OI 校验部分分",
        requires_problem=True,
        chat_triggers=("生成数据", "造数据", "generator", "testlib", "gen"),
    ),
    "write_editorial": CreationWorkflowMeta(
        id="write_editorial",
        name_zh="5 · 编写题解",
        summary="Markdown 题解（思路、复杂度、实现要点）",
        requires_problem=True,
        chat_triggers=("写题解", "题解", "editorial", "编写题解"),
    ),
}


def list_workflows() -> list[dict[str, Any]]:
    return [
        {
            "id": m.id,
            "name_zh": m.name_zh,
            "summary": m.summary,
            "requires_problem": m.requires_problem,
            "chat_triggers": list(m.chat_triggers),
        }
        for m in CREATION_WORKFLOWS.values()
    ]


def get_workflow(workflow_id: str) -> CreationWorkflowMeta:
    w = CREATION_WORKFLOWS.get(workflow_id)
    if not w:
        raise ValueError(f"unknown workflow: {workflow_id}")
    return w
