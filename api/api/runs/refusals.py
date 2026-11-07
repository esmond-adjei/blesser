"""Why a run's researched professors weren't saved, derived from what the run already records."""

import json
from collections import Counter

from sqlalchemy import or_, select

from api.agent import gates
from api.prospects.leads import MISS_STREAK_NOTE
from api.runs import models as run_models
from api.runs.service import get_run_or_404

NARROW = "research_one_professor"
SKIPPED_FOR_CAP = "narrow.skipped_cap"
NOT_REACHED = "narrow.not_reached"
STOPPED = "narrow.programme_stopped"
FAILED = "task.failed"
ENDED = "ended_without_save"
_LABELS = {
    SKIPPED_FOR_CAP: "Not researched (run full)",
    NOT_REACHED: "Not researched (budget used up)",
    STOPPED: "Not researched (programme kept missing)",
    FAILED: "Task failed",
    ENDED: "Ended without a save or a reason",
}


def _json(raw: str | None) -> dict:
    try:
        value = json.loads(raw or "")
    except (TypeError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def _label(code: str) -> str:
    return _LABELS.get(code) or gates.label(code)


def _counted(counter: Counter) -> list[dict]:
    return [
        {"gate": code, "label": _label(code), "count": n}
        for code, n in counter.most_common()
    ]


async def run_refusals(session, user_id: str, run_id: str) -> dict:
    run = await get_run_or_404(session, run_id, user_id)
    task = run_models.ResearchTask
    log = run_models.ToolCallLog
    tasks = (
        await session.execute(
            select(task.id, task.task_type, task.status, task.final_text, task.error).where(
                task.run_id == run_id, task.user_id == user_id
            )
        )
    ).all()
    narrow = {t.id: t for t in tasks if t.task_type == NARROW}
    calls = (
        await session.execute(
            select(log.task_id, log.tool_name, log.ok, log.input_json, log.result_json)
            .join(task, task.id == log.task_id)
            .where(
                task.run_id == run_id,
                task.user_id == user_id,
                or_(
                    log.ok.is_(False),
                    log.tool_name.in_(
                        ["confirm_no_match", "save_professor_record", "score_alignment"]
                    ),
                ),
            )
            .order_by(log.created_at)
        )
    ).all()

    refused: Counter = Counter()
    last_refusal: dict[str, str] = {}
    no_match: dict[str, str] = {}
    saved: set[str] = set()
    lexical = 0
    for call in calls:
        if call.tool_name == "score_alignment" and call.ok is not False:
            lexical += _json(call.result_json).get("method") == "lexical"
            continue
        if call.tool_name == "confirm_no_match" and call.ok is not False:
            no_match[call.task_id] = gates.no_match_reason(_json(call.input_json))
            continue
        if call.ok is False:
            result = _json(call.result_json)
            code = result.get("gate") or gates.classify(str(result.get("error", "")))
            refused[code] += 1
            last_refusal[call.task_id] = code
        elif call.tool_name == "save_professor_record":
            saved.add(call.task_id)

    not_saved: Counter = Counter()
    researched = 0
    for task_id, t in narrow.items():
        status = run_models.status_str(t.status)
        if status == run_models.TaskStatus.deferred.value and run.status == "done":
            stopped = (t.error or "").startswith(MISS_STREAK_NOTE)
            not_saved[STOPPED if stopped else NOT_REACHED] += 1
            continue
        if status not in (
            run_models.TaskStatus.done.value,
            run_models.TaskStatus.error.value,
        ):
            continue
        if (t.final_text or "").startswith("Skipped: the run already has"):
            not_saved[SKIPPED_FOR_CAP] += 1
            continue
        researched += 1
        if task_id in saved:
            continue
        if task_id in no_match:
            not_saved[no_match[task_id]] += 1
        elif task_id in last_refusal:
            not_saved[last_refusal[task_id]] += 1
        elif status == run_models.TaskStatus.error.value:
            not_saved[FAILED] += 1
        else:
            not_saved[ENDED] += 1

    return {
        "researched": researched,
        "saved": sum(1 for task_id in narrow if task_id in saved),
        "not_saved": _counted(not_saved),
        "refusals": _counted(refused),
        # Word-overlap fallbacks (embedding unavailable or rate-limited) miss same-topic work worded differently.
        "lexical_scores": lexical,
    }
