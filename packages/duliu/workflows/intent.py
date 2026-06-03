"""Map natural language to creation workflow ids."""

from __future__ import annotations

import re

from duliu.workflows.registry import CREATION_WORKFLOWS


def detect_workflow_from_text(text: str) -> str | None:
    t = text.strip().lower()
    if not t:
        return None
    # explicit: workflow:find_problem / 工作流:找题
    m = re.search(r"(?:workflow|工作流)[:：]\s*(\w+)", t, re.I)
    if m:
        wid = m.group(1).replace("-", "_")
        if wid in CREATION_WORKFLOWS:
            return wid
    for meta in CREATION_WORKFLOWS.values():
        for trig in meta.chat_triggers:
            if trig.lower() in t:
                return meta.id
    # ordered: more specific first
    if re.search(r"找题|搜题|选题|想\s*idea|find\s*problem", t, re.I):
        return "find_problem"
    if re.search(r"写题面|编写题面|题面生成", t, re.I):
        return "write_statement"
    if re.search(r"解法分析|部分分|数据范围|子任务", t, re.I):
        return "solution_analysis"
    if re.search(r"生成数据|造数据|testlib|数据生成", t, re.I):
        return "generate_data"
    if re.search(r"写题解|编写题解|题解生成", t, re.I):
        return "write_editorial"
    return None


def parse_workflow_params(text: str, workflow_id: str) -> dict:
    """Best-effort extract params from user message."""
    params: dict = {}
    m = re.search(r"难度[：:\s]*(\d{3,4})", text)
    if m:
        params["difficulty"] = int(m.group(1))
    m = re.search(r"rating[：:\s]*(\d{3,4})", text, re.I)
    if m:
        params["difficulty"] = int(m.group(1))
    if re.search(r"\boi\b", text, re.I):
        params["contest_style"] = "OI"
    if re.search(r"\bicpc\b", text, re.I):
        params["contest_style"] = "ICPC"
    if re.search(r"codeforces|cf", text, re.I):
        params["style"] = "codeforces"
    if re.search(r"noip", text, re.I):
        params["style"] = "noip"
    topics = re.findall(r"知识点[：:\s]*([^\n，,]+)", text)
    if topics:
        params["topics"] = [x.strip() for x in re.split(r"[,，、]", topics[0]) if x.strip()]
    if workflow_id == "find_problem" and "部分分" in text:
        params["partial_scoring"] = True
    return params
