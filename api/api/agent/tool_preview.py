"""Small, valid JSON previews. Never cut JSON in the middle of a value."""

import json


def preview(value: object, limit: int) -> str:
    if isinstance(value, str):
        if len(value) <= limit:
            return value
        return json.dumps({"text": value[:max(0, limit - 160)], "omitted_characters": len(value) - max(0, limit - 160)})
    text = json.dumps(value, default=str)
    if len(text) <= limit:
        return text

    def shrink(item, depth=0):
        if isinstance(item, dict):
            return {k: shrink(v, depth + 1) for k, v in list(item.items())[:16]}
        if isinstance(item, (list, tuple)):
            shown = [shrink(v, depth + 1) for v in item[:3]]
            if len(item) > 3:
                shown.append({"omitted_items": len(item) - 3})
            return shown
        if isinstance(item, str) and len(item) > 200:
            return {"text": item[:200], "omitted_characters": len(item) - 200}
        return item

    compact = shrink(value)
    if len(json.dumps(compact, default=str)) <= limit:
        return json.dumps(compact, default=str)
    # Keep identity fields so result cards can still link to the saved item.
    summary = {k: v for k, v in value.items() if isinstance(v, (str, int, float, bool, type(None))) and len(str(v)) <= 160} if isinstance(value, dict) else {}
    summary["summary"] = (
        "Preview cut short; open the linked record for full details."
        if "id" in summary
        else "Preview cut short; the full result went to the model."
    )
    while len(json.dumps(summary, default=str)) > limit and len(summary) > 1:
        summary.pop(next(iter(summary)))
    return json.dumps(summary, default=str)
