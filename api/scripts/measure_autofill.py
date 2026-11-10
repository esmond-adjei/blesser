import argparse
import asyncio
import json
import time
from collections import Counter
from pathlib import Path

import httpx

from api.autofill import service
from api.autofill.matcher import deterministic, document_match, free_text
from api.autofill.schemas import FormField
from api.core.config import settings

FIXTURES = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "autofill"


def load_fields(form):
    return [
        FormField.model_validate(
            {key: value for key, value in row.items() if key != "expected"}
        )
        for row in form["fields"]
    ]


def match(fields, kit):
    fills = []
    for field in fields:
        result = deterministic(
            field, kit["profile"], kit["project"], kit["profile"]["sensitive"]
        ) or document_match(field, kit["documents"])
        if result:
            fills.append(result)
    return fills


class MeasuredProvider:
    def __init__(self, provider):
        self.provider = provider
        self.usage = None
        self.calls = 0
        self.truncated = False
        self.error = None

    async def chat(self, **kwargs):
        self.calls += 1
        try:
            response = await self.provider.chat(**kwargs)
        except Exception as exc:
            self.error = type(exc).__name__
            raise
        self.usage = response.usage
        self.truncated = response.truncated
        return response


async def measure(real_draft):
    kit = json.loads((FIXTURES / "kit.json").read_text())
    forms = [
        json.loads(path.read_text())
        for path in sorted(FIXTURES.glob("*.json"))
        if path.stem != "kit"
    ]
    start = time.perf_counter()
    rows = []
    rule_counts = Counter()
    rule_correct = Counter()
    for form in forms:
        fields = load_fields(form)
        form_kit = {**kit, "profile": {**kit["profile"], **form.get("profile", {})}}
        fills = match(fields, form_kit)
        keys = {fill.key for fill in fills}
        expected = {row["key"]: row["expected"] for row in form["fields"]}
        correct = 0
        for item in fills:
            rule = item.rule
            rule_counts[rule] += 1
            target = expected[item.key]
            if (
                target
                and target.get("source") != "drafted"
                and all(
                    getattr(item, key) == value
                    for key, value in target.items()
                    if key not in {"rule", "confidence"}
                )
            ):
                correct += 1
                rule_correct[rule] += 1
        rows.append(
            {
                "fixture": form["name"],
                "fields": len(fields),
                "deterministic": len(fills),
                "correct": correct,
                "incorrect": len(fills) - correct,
                "expected_saved": sum(
                    row is not None and row.get("source") != "drafted"
                    for row in expected.values()
                ),
                "drafted": 0,
                "unfilled": len(fields) - len(fills),
                "draft_eligible": sum(
                    field.key not in keys and free_text(field) for field in fields
                ),
            }
        )
    totals = {
        key: sum(row[key] for row in rows)
        for key in (
            "fields",
            "deterministic",
            "correct",
            "incorrect",
            "expected_saved",
            "drafted",
            "unfilled",
            "draft_eligible",
        )
    }
    output = {
        "baseline": {
            "mode": "matcher and documents only; no saved answers or model calls",
            "fixtures": rows,
            "totals": totals,
            "percent": {
                key: round(100 * totals[key] / totals["fields"], 2)
                for key in ("deterministic", "drafted", "unfilled")
            },
            "elapsed_ms": round((time.perf_counter() - start) * 1000, 2),
            "per_rule": {
                rule: {
                    "fills": count,
                    "correct": rule_correct[rule],
                    "incorrect": count - rule_correct[rule],
                }
                for rule, count in sorted(rule_counts.items())
            },
        }
    }
    if real_draft:
        live = {"provider": settings.llm_provider, "model": settings.llm_model}
        output["real_draft"] = live
        if settings.llm_provider.lower() != "ollama":
            live["status"] = "skipped: configured provider is not Ollama"
            return output
        base_url = settings.resolve_llm_base_url().rstrip("/")
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(
                    base_url + "/models",
                    headers={
                        "Authorization": f"Bearer {settings.resolve_llm_api_key()}"
                    },
                )
                response.raise_for_status()
        except httpx.HTTPError as exc:
            live.update(status="unreachable", error=type(exc).__name__)
            return output
        form = next(form for form in forms if form["name"] == "siwa")
        fields = load_fields(form)
        saved = match(fields, kit)
        keys = {fill.key for fill in saved}
        pending = [
            field for field in fields if field.key not in keys and free_text(field)
        ]
        provider = MeasuredProvider(service.get_provider())
        service.get_provider = lambda: provider
        start = time.perf_counter()
        drafted = await service.draft(
            pending, kit["profile"], kit["project"], kit["profile"]["sensitive"]
        )
        live.update(
            status="failed" if provider.error else "completed",
            fixture=form["name"],
            latency_seconds=round(time.perf_counter() - start, 3),
            calls=provider.calls,
            usage=provider.usage,
            truncated=provider.truncated,
            error=provider.error,
            fields=len(fields),
            deterministic=len(saved),
            drafted=len(drafted),
            unfilled=len(fields) - len(saved) - len(drafted),
            attempted_keys=[field.key for field in pending],
            accepted_fills=[fill.model_dump() for fill in drafted],
        )
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--real-draft", action="store_true")
    args = parser.parse_args()
    print(json.dumps(asyncio.run(measure(args.real_draft)), indent=2))
