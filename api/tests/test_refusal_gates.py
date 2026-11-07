import ast
import asyncio
import json
from pathlib import Path

from fastapi.testclient import TestClient

from api.agent import gates
from api.agent.tools import ToolContext, dispatch
from api.core.db import SessionLocal
from api.main import app
from api.runs.models import ResearchTask, Run, TaskStatus, ToolCallLog
from tests.conftest import TEST_USER_ID

API = Path(__file__).resolve().parents[1] / "api"

#: Refusal sites per file; None means every `{"error": ...}` literal in it.
SOURCES: dict[str, set[str] | None] = {
    "prospects/tools.py": None,
    "prospects/grounding.py": {"ground_professor_save", "unverified_save_error"},
    "outreach/draft_check.py": {"verify_draft"},
    "outreach/tools.py": None,
    "candidates/tools.py": None,
    "agent/tools/dispatch.py": None,
    "agent/tools/budgets.py": None,
    "billing/service.py": {"check_model_allowance", "check_quota", "reserve_tool_call"},
}


def _render(node: ast.AST) -> str | None:
    """A string expression's text, placeholders as X; None if not one."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        return "".join(
            v.value if isinstance(v, ast.Constant) else "X" for v in node.values
        )
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left, right = _render(node.left), _render(node.right)
        if left is not None:
            return left + (right or "X")
    return None


def _messages() -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    for rel, functions in SOURCES.items():
        tree = ast.parse((API / rel).read_text())
        scopes = [tree] if functions is None else [
            n
            for n in ast.walk(tree)
            if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef) and n.name in functions
        ]
        for scope in scopes:
            for node in ast.walk(scope):
                text = None
                if isinstance(node, ast.Dict):
                    for key, value in zip(node.keys, node.values, strict=True):
                        if isinstance(key, ast.Constant) and key.value == "error":
                            text = _render(value)
                elif functions is not None and isinstance(node, ast.Return) and node.value:
                    value = node.value
                    if isinstance(value, ast.Tuple) and value.elts:
                        value = value.elts[0]
                    text = _render(value)
                elif functions is not None and isinstance(node, ast.Call) and node.args:
                    name = getattr(node.func, "id", "")
                    if name in ("ForbiddenError", "_upgrade"):
                        text = next(
                            (r for r in map(_render, node.args) if r and len(r) > 20),
                            None,
                        )
                if text and text.strip() != "X":
                    found.append((rel, text))
    return found


def test_every_refusal_text_has_a_gate_code():
    messages = _messages()
    assert len(messages) > 30  # the walk actually found the refusals
    unknown = [(rel, text) for rel, text in messages if gates.classify(text) == gates.OTHER]
    assert unknown == []


def test_messages_built_elsewhere_are_classified():
    # Assembled outside the walked literals (limit_error, the tier check).
    for text, code in [
        ("Run program budget reached (10 schools saved). Do not save more", "cap.run_programs"),
        ("This run targets top_50 schools. Pass school_tier as one of those", "cap.tier_share"),
        ("The top_50 tier already has its share (5 of 5 schools).", "cap.tier_share"),
        ("OpenAlex is unavailable right now (HTTP 503). Don't invent papers", "tool.failed"),
        (
            "find_openalex_author failed: OpenAlex's daily budget is used up until 00:00 UTC.",
            "openalex.budget",
        ),
    ]:
        assert gates.classify(text) == code, text


def test_dispatch_tags_refusals():
    from api.prospects.models import Program, RunSchool, School

    async def go():
        async with SessionLocal() as session:
            run = Run(
                user_id=TEST_USER_ID, region="U", field="f", degree_level="phd",
                interest_statement="x", status="running",
            )  # fmt: skip
            session.add(run)
            await session.flush()
            school = School(user_id=TEST_USER_ID, run_links=[RunSchool(run_id=run.id)], name="S")
            session.add(school)
            await session.flush()
            program = Program(user_id=TEST_USER_ID, school_id=school.id, name="P")
            session.add(program)
            await session.commit()
            ctx = ToolContext(session=session, run=run, program=program)
            refused = await dispatch(
                "save_professor_record",
                {"name": "Ada", "openalex_id": "A1", "similarity_score": 0.5,
                 "rationale": "r", "papers": []},
                ctx,
            )  # fmt: skip
            no_match = await dispatch(
                "confirm_no_match", {"reason": "elsewhere", "reason_code": "institution"}, ctx
            )
            return refused, no_match

    refused, no_match = asyncio.run(go())
    assert refused["gate"] == "grounding.no_candidates"
    assert "gate" not in no_match and no_match["reason_code"] == "institution"


def test_run_refusals_summarises_why_professors_were_not_saved():
    async def seed():
        async with SessionLocal() as session:
            run = Run(
                user_id=TEST_USER_ID, region="U", field="f", degree_level="phd",
                interest_statement="x", status="done",
            )  # fmt: skip
            session.add(run)
            await session.flush()

            def narrow(status=TaskStatus.done, final_text="done"):
                task = ResearchTask(
                    run_id=run.id, user_id=TEST_USER_ID, task_type="research_one_professor",
                    status=status, final_text=final_text,
                )  # fmt: skip
                session.add(task)
                return task

            saved, low, refused = narrow(), narrow(), narrow()
            narrow(final_text="Skipped: the run already has 30 candidates (cap 30).")
            narrow(status=TaskStatus.error)
            narrow(status=TaskStatus.pending)
            await session.flush()

            def call(task, tool, ok, result, args=None):
                session.add(
                    ToolCallLog(
                        task_id=task.id, user_id=TEST_USER_ID, turn=1, tool_name=tool,
                        ok=ok, result_json=json.dumps(result), input_json=json.dumps(args or {}),
                    )
                )  # fmt: skip

            call(saved, "save_professor_record", False, {"error": "Rationale does not cite any"})
            call(saved, "save_professor_record", True, {"candidate_id": "c"})
            call(low, "confirm_no_match", True, {"acknowledged": True}, {"reason_code": "low_score"})
            # An older row: no gate field, classified from its text.
            call(refused, "save_professor_record", False,
                 {"error": "OpenAlex places this author at 'MIT', not 'CMU'."})  # fmt: skip
            await session.commit()
            return run.id

    run_id = asyncio.run(seed())
    body = TestClient(app).get(f"/api/runs/{run_id}/refusals").json()
    assert body["researched"] == 4  # saved, low, refused, failed
    assert body["saved"] == 1
    assert {r["gate"]: r["count"] for r in body["not_saved"]} == {
        "low_score": 1,
        "grounding.institution": 1,
        "narrow.skipped_cap": 1,
        "task.failed": 1,
    }
    assert {r["gate"]: r["count"] for r in body["refusals"]} == {
        "rationale.uncited": 1,
        "grounding.institution": 1,
    }
    labels = {r["gate"]: r["label"] for r in body["not_saved"]}
    assert labels["grounding.institution"] == "Institution didn't match"
    assert labels["narrow.skipped_cap"] == "Not researched (run full)"


def test_other_accounts_cannot_read_a_runs_refusals():
    resp = TestClient(app).get("/api/runs/does-not-exist/refusals")
    assert resp.status_code == 404
