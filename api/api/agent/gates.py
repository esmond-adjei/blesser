"""Stable codes for the checks that refuse a tool call, classified from the refusal text.

A test fails on any handler refusal text no pattern here recognises.
"""

import re

#: (code, pattern, label), first match wins. Labels are for the run page.
GATES: tuple[tuple[str, re.Pattern[str], str], ...] = tuple(
    (code, re.compile(pattern, re.IGNORECASE), label)
    for code, pattern, label in (
        ("grounding.no_candidates", r"openalex_id must be one find_openalex_author returned", "Not found on OpenAlex in this task"),
        ("grounding.institution", r"OpenAlex places this author at", "Institution didn't match"),
        ("grounding.no_works", r"Fetch this author's works with get_author_works|No fetched works for this openalex_id", "Works not fetched"),
        ("grounding.paper_unknown", r"papers were not returned by get_author_works|Cite at least one paper returned", "Cited papers not from OpenAlex"),
        ("grounding.score_mismatch", r"similarity_score must", "Score not from score_alignment"),
        ("grounding.unverified_refused", r"unverified is only for professors|An unverified save still needs a rationale", "Unverified save not allowed"),
        ("score.empty", r"abstracts is empty", "Nothing to score"),
        ("rationale.uncited", r"Rationale (is empty|does not cite)", "Rationale didn't cite a paper"),
        ("draft.unstated_background", r"background the student never gave you", "Draft claimed unstated background"),
        ("draft.uncited", r"must name at least one of the professor's stored papers|no stored papers to cite", "Draft didn't cite a paper"),
        ("draft.format", r"Subject and body are both required|Subject is over|Body is \S+ words|Unfilled template placeholders", "Draft format"),
        ("cap.run_candidates", r"Run candidate budget", "Run's professor cap reached"),
        ("cap.program_professors", r"Program professor budget", "Programme's professor cap reached"),
        ("cap.program_leads", r"This program already has \S+ names queued", "Programme's name list full"),
        ("cap.run_programs", r"Run program budget|schools to this run, the most allowed", "Run's school cap reached"),
        ("cap.tier_share", r"This run targets .* schools\. Pass school_tier|tier already has its share", "School tier share"),
        ("cap.task_saves", r"Budget reached: at most", "Per-task save limit"),
        ("cap.task_tool_calls", r"^Tool call limit:", "Per-task tool call limit"),
        ("spend.daily_tool_calls", r"today's \S+ search, scoring and verification", "Daily tool allowance used"),
        ("spend.daily_tokens", r"today's \S+-token allowance", "Daily model allowance used"),
        ("spend.monthly", r"a month and you've used|Pro raises the limit", "Plan quota used"),
        ("plan.feature", r" is part of ", "Not in your plan"),
        ("spend.no_shared_model", r"no shared model|Confirm your email address to use the shared model", "Shared model unavailable"),
        ("optout", r"asked not to be included", "Opted out"),
        ("dedup.in_flight", r"Another worker appears to be saving this same professor", "Saved by another task"),
        ("agent.cancelled", r"were cancelled for this run", "Agent cancelled by you"),
        ("halted", r"work on halted runs is refused|This (task|agent) was .* its tools are refused", "Run, agent or task halted"),
        ("tool.disabled", r"is disabled by the operator|outside this task's allowlist|Unknown tool", "Tool not available"),
        ("context.missing", r"No program in context|No candidate_id given|Candidate not found in this run|Duplicate professor save failed", "Missing context"),
        ("openalex.waited", r"It is available again: call \S+ again", "Repeat a lookup after an OpenAlex wait"),
        ("openalex.budget", r"OpenAlex's daily budget", "OpenAlex budget used up"),
        ("openalex.auth", r"OpenAlex rejected the server's API key", "OpenAlex key rejected"),
        ("tool.repeated_failure", r"already failed in this task", "Repeated a failed call"),
        ("tool.failed", r"^\S+ failed: |unavailable right now", "Tool failed"),
    )
)

_LABELS = {code: label for code, _, label in GATES}

#: confirm_no_match reason codes (the tool's `reason_code` enum).
NO_MATCH_REASONS: dict[str, str] = {
    "low_score": "Work doesn't align",
    "no_openalex_match": "No OpenAlex match",
    "institution": "Different institution",
    "no_faculty_page": "No faculty page found",
    "other": "Other",
}

OTHER = "other"


def classify(error: str) -> str:
    """The gate code for a refusal text; `other` when none matches."""
    for code, pattern, _label in GATES:
        if pattern.search(error or ""):
            return code
    return OTHER


def label(code: str) -> str:
    return _LABELS.get(code) or NO_MATCH_REASONS.get(code) or "Other"


def with_gate(result: object) -> object:
    if isinstance(result, dict) and "error" in result and "gate" not in result:
        result["gate"] = classify(str(result["error"]))
    return result


def no_match_reason(tool_input: dict) -> str:
    code = str(tool_input.get("reason_code") or "").strip().lower()
    return code if code in NO_MATCH_REASONS else OTHER
