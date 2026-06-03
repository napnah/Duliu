import hashlib
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from duliu.config import settings
from duliu.db.models import (
    M3_STAGE_ORDER,
    M2_STAGE_ORDER,
    Artifact,
    ContestSet,
    ContestSlot,
    Problem,
    ProblemStage,
    StageStatus,
    Workspace,
)
from duliu.workflow.loader import contest_defaults

SAMPLE_STD_CPP = r"""#include <bits/stdc++.h>
using namespace std;
int main() {
    long long a, b;
    if (!(cin >> a >> b)) return 0;
    cout << a + b << "\n";
    return 0;
}
"""

SAMPLE_BRUTE_CPP = SAMPLE_STD_CPP

SAMPLE_STD_PYTHON = """import sys
def main():
    data = sys.stdin.read().strip().split()
    if not data:
        return
    a, b = int(data[0]), int(data[1])
    print(a + b)
if __name__ == "__main__":
    main()
"""

SAMPLE_STATEMENT = """# A + B

Given two integers `a` and `b`, print their sum.

## Input
Two integers `a` and `b` (-10^9 <= a, b <= 10^9).

## Output
One integer: a + b.

## Sample
Input:
```
3 4
```
Output:
```
7
```
"""

SAMPLE_CHECKER_PY = """import sys
inf = open(sys.argv[1])
ouf = open(sys.argv[2])
ans = open(sys.argv[3])
inf.readline()
user = ouf.read().strip()
ref = ans.read().strip()
sys.exit(0 if user == ref else 1)
"""


async def ensure_default_workspace(session: AsyncSession) -> Workspace:
    result = await session.execute(
        select(Workspace).where(Workspace.name == settings.default_workspace_name)
    )
    ws = result.scalar_one_or_none()
    if ws:
        return ws

    ws = Workspace(name=settings.default_workspace_name, config_json={})
    session.add(ws)
    await session.flush()
    return ws


async def ensure_m2_stages(session: AsyncSession) -> None:
    """Add ADVERSARIAL_REVIEW stage to existing problems (M1 → M2 migration)."""
    await _ensure_stages(session, ["ADVERSARIAL_REVIEW"])


async def ensure_m3_stages(session: AsyncSession) -> None:
    """Add PACKAGE + EDITORIAL stages (M2 → M3 migration)."""
    await _ensure_stages(session, ["PACKAGE", "EDITORIAL"])


async def _ensure_stages(session: AsyncSession, stage_ids: list[str]) -> None:
    problems = (await session.execute(select(Problem))).scalars().all()
    for p in problems:
        for stage_id in stage_ids:
            existing = (
                await session.execute(
                    select(ProblemStage).where(
                        ProblemStage.problem_id == p.id,
                        ProblemStage.stage_id == stage_id,
                    )
                )
            ).scalar_one_or_none()
            if existing:
                continue
            session.add(
                ProblemStage(
                    problem_id=p.id,
                    stage_id=stage_id,
                    status=StageStatus.PENDING.value,
                )
            )


def _add_stages(session: AsyncSession, problem: Problem, start_stage: str = "SPEC") -> None:
    for stage_id in M3_STAGE_ORDER:
        session.add(
            ProblemStage(
                problem_id=problem.id,
                stage_id=stage_id,
                status=StageStatus.AWAITING_HUMAN.value
                if stage_id == start_stage
                else StageStatus.PENDING.value,
            )
        )


async def seed_demo_problem(session: AsyncSession, workspace: Workspace) -> Problem | None:
    result = await session.execute(
        select(Problem).where(Problem.workspace_id == workspace.id, Problem.title == "M1 Demo A+B")
    )
    if result.scalar_one_or_none():
        return None

    spec = {
        "limits": {"time_ms": 1000, "memory_mb": 256},
        "samples": [{"input": "3 4\n", "output": "7\n"}, {"input": "0 0\n", "output": "0\n"}],
        "solution_languages": ["cpp", "python", "java"],
    }
    problem = Problem(
        workspace_id=workspace.id,
        title="M1 Demo A+B",
        originality="ORIGINAL",
        problem_type="TRADITIONAL",
        contest_style="ICPC",
        control_mode="HUMAN",
        current_stage="SPEC",
        spec_json=spec,
    )
    session.add(problem)
    await session.flush()
    _add_stages(session, problem)

    for kind, content, lang in [
        ("statement", SAMPLE_STATEMENT, None),
        ("std", SAMPLE_STD_CPP, "cpp"),
        ("brute", SAMPLE_BRUTE_CPP, "cpp"),
    ]:
        session.add(
            Artifact(
                problem_id=problem.id,
                kind=kind,
                version=1,
                content_text=content,
                sha256=hashlib.sha256(content.encode()).hexdigest(),
                author="seed",
                language=lang,
            )
        )
    await session.flush()
    return problem


async def seed_oi_demo_problem(session: AsyncSession, workspace: Workspace) -> Problem | None:
    result = await session.execute(
        select(Problem).where(Problem.workspace_id == workspace.id, Problem.title == "M2 Demo OI A+B")
    )
    if result.scalar_one_or_none():
        return None

    spec = {
        "limits": {"time_ms": 2000, "memory_mb": 512},
        "samples": [{"input": "3 4\n", "output": "7\n"}],
        "subtasks": [
            {"id": 1, "score": 30, "desc": "样例"},
            {"id": 2, "score": 70, "desc": "随机"},
        ],
        "solution_languages": ["cpp", "python"],
    }
    problem = Problem(
        workspace_id=workspace.id,
        title="M2 Demo OI A+B",
        originality="ORIGINAL",
        problem_type="TRADITIONAL",
        contest_style="OI",
        control_mode="HUMAN",
        current_stage="SPEC",
        spec_json=spec,
    )
    session.add(problem)
    await session.flush()
    _add_stages(session, problem)
    for kind, content, lang in [
        ("statement", SAMPLE_STATEMENT.replace("A + B", "A + B (OI)"), None),
        ("std", SAMPLE_STD_PYTHON, "python"),
        ("brute", SAMPLE_STD_CPP, "cpp"),
    ]:
        session.add(
            Artifact(
                problem_id=problem.id,
                kind=kind,
                version=1,
                content_text=content,
                sha256=hashlib.sha256(content.encode()).hexdigest(),
                author="seed",
                language=lang,
            )
        )
    await session.flush()
    return problem


async def seed_adversarial_ready_problem(session: AsyncSession, workspace: Workspace) -> Problem | None:
    result = await session.execute(
        select(Problem).where(Problem.workspace_id == workspace.id, Problem.title == "M2 Adv Ready")
    )
    if result.scalar_one_or_none():
        return None
    spec = {
        "limits": {"time_ms": 1000, "memory_mb": 256},
        "samples": [{"input": "1 2\n", "output": "3\n"}],
    }
    problem = Problem(
        workspace_id=workspace.id,
        title="M2 Adv Ready",
        originality="ORIGINAL",
        problem_type="TRADITIONAL",
        contest_style="ICPC",
        control_mode="HUMAN",
        current_stage="ADVERSARIAL_REVIEW",
        spec_json=spec,
    )
    session.add(problem)
    await session.flush()
    for stage_id in M3_STAGE_ORDER:
        st = StageStatus.AWAITING_HUMAN.value if stage_id == "ADVERSARIAL_REVIEW" else StageStatus.APPROVED.value
        session.add(ProblemStage(problem_id=problem.id, stage_id=stage_id, status=st))
    for kind, content, lang in [
        ("statement", SAMPLE_STATEMENT, None),
        ("std", SAMPLE_STD_CPP, "cpp"),
        ("brute", SAMPLE_BRUTE_CPP, "cpp"),
    ]:
        session.add(
            Artifact(
                problem_id=problem.id,
                kind=kind,
                version=1,
                content_text=content,
                sha256=hashlib.sha256(content.encode()).hexdigest(),
                author="seed",
                language=lang,
            )
        )
    await session.flush()
    return problem


async def seed_spj_demo_problem(session: AsyncSession, workspace: Workspace) -> Problem | None:
    result = await session.execute(
        select(Problem).where(Problem.workspace_id == workspace.id, Problem.title == "M2 Demo SPJ")
    )
    if result.scalar_one_or_none():
        return None

    spec = {
        "limits": {"time_ms": 1000, "memory_mb": 256},
        "samples": [{"input": "3 4\n", "output": "7\n"}],
    }
    problem = Problem(
        workspace_id=workspace.id,
        title="M2 Demo SPJ",
        originality="ORIGINAL",
        problem_type="SUBMIT_ANSWER",
        contest_style="ICPC",
        control_mode="HUMAN",
        current_stage="SPEC",
        spec_json=spec,
    )
    session.add(problem)
    await session.flush()
    _add_stages(session, problem)
    for kind, content, lang in [
        ("statement", SAMPLE_STATEMENT + "\n\n(SPJ checker required)\n", None),
        ("std", SAMPLE_STD_CPP, "cpp"),
        ("checker", SAMPLE_CHECKER_PY, "python"),
    ]:
        session.add(
            Artifact(
                problem_id=problem.id,
                kind=kind,
                version=1,
                content_text=content,
                sha256=hashlib.sha256(content.encode()).hexdigest(),
                author="seed",
                language=lang,
            )
        )
    await session.flush()
    return problem


async def seed_demo_contest_set(session: AsyncSession, workspace: Workspace) -> ContestSet | None:
    result = await session.execute(
        select(ContestSet).where(
            ContestSet.workspace_id == workspace.id,
            ContestSet.name == "M1 Demo ICPC Set",
        )
    )
    if result.scalar_one_or_none():
        return None
    return await create_contest_set(
        session, workspace, "M1 Demo ICPC Set", contest_style="ICPC", slot_count=13
    )


async def seed_oi_contest_set(session: AsyncSession, workspace: Workspace) -> ContestSet | None:
    result = await session.execute(
        select(ContestSet).where(
            ContestSet.workspace_id == workspace.id,
            ContestSet.name == "M2 Demo OI Set",
        )
    )
    if result.scalar_one_or_none():
        return None
    defaults = contest_defaults("OI")
    count = defaults.get("problem_count", 4)
    return await create_contest_set(
        session, workspace, "M2 Demo OI Set", contest_style="OI", slot_count=count
    )


INTERACTIVE_STD_CPP = r"""#include <bits/stdc++.h>
using namespace std;
int main() {
    int x;
    if (!(cin >> x)) return 0;
    if (x == 7) cout << "yes\n";
    else cout << "no\n";
    return 0;
}
"""

INTERACTIVE_INTERACTOR_PY = r"""import os
import subprocess
import sys

bin = os.environ["DULIU_SOLUTION_BIN"]
p = subprocess.Popen([bin], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
out, _ = p.communicate(input="7\n", timeout=2)
if "yes" in (out or "").lower():
    print("AC")
    sys.exit(0)
print("WA")
sys.exit(1)
"""

COMMUNICATION_PROTOCOL = """# Communication Protocol (demo)

Two processes A/B alternate messages via interactor (M3 stub).
Interactor validates turn order and message format.
"""


async def refresh_interactive_interactor(session: AsyncSession, workspace: Workspace) -> None:
    """Fix interactor seed if an old broken template was stored."""
    result = await session.execute(
        select(Problem).where(Problem.workspace_id == workspace.id, Problem.title == "M3 Demo Interactive")
    )
    problem = result.scalar_one_or_none()
    if not problem:
        return
    art_r = await session.execute(
        select(Artifact)
        .where(Artifact.problem_id == problem.id, Artifact.kind == "interactor")
        .order_by(Artifact.version.desc())
        .limit(1)
    )
    art = art_r.scalar_one_or_none()
    if not art or "stdin.close" not in art.content_text:
        return
    session.add(
        Artifact(
            problem_id=problem.id,
            kind="interactor",
            version=art.version + 1,
            content_text=INTERACTIVE_INTERACTOR_PY,
            sha256=hashlib.sha256(INTERACTIVE_INTERACTOR_PY.encode()).hexdigest(),
            author="seed",
            language="python",
        )
    )


async def seed_interactive_demo(session: AsyncSession, workspace: Workspace) -> Problem | None:
    result = await session.execute(
        select(Problem).where(Problem.workspace_id == workspace.id, Problem.title == "M3 Demo Interactive")
    )
    if result.scalar_one_or_none():
        return None
    spec = {
        "limits": {"time_ms": 2000, "memory_mb": 256},
        "samples": [{"input": "7\n", "output": "yes\n"}],
        "interactive": True,
    }
    problem = Problem(
        workspace_id=workspace.id,
        title="M3 Demo Interactive",
        originality="ORIGINAL",
        problem_type="INTERACTIVE",
        contest_style="ICPC",
        control_mode="HUMAN",
        current_stage="SPEC",
        spec_json=spec,
    )
    session.add(problem)
    await session.flush()
    _add_stages(session, problem)
    for kind, content, lang in [
        ("statement", SAMPLE_STATEMENT.replace("A + B", "Guess 7 (Interactive)"), None),
        ("std", INTERACTIVE_STD_CPP, "cpp"),
        ("interactor", INTERACTIVE_INTERACTOR_PY, "python"),
    ]:
        session.add(
            Artifact(
                problem_id=problem.id,
                kind=kind,
                version=1,
                content_text=content,
                sha256=hashlib.sha256(content.encode()).hexdigest(),
                author="seed",
                language=lang,
            )
        )
    await session.flush()
    return problem


async def seed_communication_demo(session: AsyncSession, workspace: Workspace) -> Problem | None:
    result = await session.execute(
        select(Problem).where(Problem.workspace_id == workspace.id, Problem.title == "M3 Demo Communication")
    )
    if result.scalar_one_or_none():
        return None
    problem = Problem(
        workspace_id=workspace.id,
        title="M3 Demo Communication",
        originality="ORIGINAL",
        problem_type="COMMUNICATION",
        contest_style="ICPC",
        control_mode="HUMAN",
        current_stage="SPEC",
        spec_json={"limits": {"time_ms": 2000, "memory_mb": 256}, "team_size": 2},
    )
    session.add(problem)
    await session.flush()
    _add_stages(session, problem)
    for kind, content, lang in [
        ("statement", "Team communication demo\n", None),
        ("protocol", COMMUNICATION_PROTOCOL, None),
        ("std", INTERACTIVE_STD_CPP, "cpp"),
        ("interactor", INTERACTIVE_INTERACTOR_PY, "python"),
    ]:
        session.add(
            Artifact(
                problem_id=problem.id,
                kind=kind,
                version=1,
                content_text=content,
                sha256=hashlib.sha256(content.encode()).hexdigest(),
                author="seed",
                language=lang,
            )
        )
    await session.flush()
    return problem


async def seed_package_ready_problem(session: AsyncSession, workspace: Workspace) -> Problem | None:
    result = await session.execute(
        select(Problem).where(Problem.workspace_id == workspace.id, Problem.title == "M3 Package Ready")
    )
    if result.scalar_one_or_none():
        return None
    spec = {
        "limits": {"time_ms": 1000, "memory_mb": 256},
        "samples": [{"input": "3 4\n", "output": "7\n"}],
    }
    problem = Problem(
        workspace_id=workspace.id,
        title="M3 Package Ready",
        originality="ORIGINAL",
        problem_type="TRADITIONAL",
        contest_style="ICPC",
        control_mode="HUMAN",
        current_stage="PACKAGE",
        spec_json=spec,
    )
    session.add(problem)
    await session.flush()
    for stage_id in M3_STAGE_ORDER:
        st = StageStatus.AWAITING_HUMAN.value if stage_id == "PACKAGE" else StageStatus.APPROVED.value
        session.add(ProblemStage(problem_id=problem.id, stage_id=stage_id, status=st))
    for kind, content, lang in [
        ("statement", SAMPLE_STATEMENT, None),
        ("std", SAMPLE_STD_CPP, "cpp"),
        ("brute", SAMPLE_BRUTE_CPP, "cpp"),
    ]:
        session.add(
            Artifact(
                problem_id=problem.id,
                kind=kind,
                version=1,
                content_text=content,
                sha256=hashlib.sha256(content.encode()).hexdigest(),
                author="seed",
                language=lang,
            )
        )
    await session.flush()
    return problem


async def create_contest_set(
    session: AsyncSession,
    workspace: Workspace,
    name: str,
    contest_style: str = "ICPC",
    slot_count: int | None = None,
) -> ContestSet:
    if slot_count is None:
        slot_count = 13 if contest_style == "ICPC" else contest_defaults("OI").get("problem_count", 4)
    cs = ContestSet(
        workspace_id=workspace.id,
        name=name,
        contest_style=contest_style,
        slot_count=slot_count,
    )
    session.add(cs)
    await session.flush()
    labels = [chr(ord("A") + i) for i in range(slot_count)] if contest_style == "ICPC" else [
        f"P{i + 1}" for i in range(slot_count)
    ]
    for label in labels:
        session.add(ContestSlot(contest_set_id=cs.id, slot_label=label, status="EMPTY"))
    await session.flush()
    return cs
