"""Tool groups: tools that toggle as one unit. Every tool belongs to one group, by what it works on.

Groups are scope-agnostic: a group applies to whichever members a scope has.
"""

TOOL_GROUPS: dict[str, dict] = {
    "web": {
        "label": "Web",
        "description": "Search the web and read the pages it finds.",
        "tools": ("search_web", "fetch_page"),
    },
    "scholar": {
        "label": "Scholarly records",
        "description": "Look up authors on OpenAlex, pull their works and score their fit.",
        "tools": ("find_openalex_author", "get_author_works", "score_alignment"),
    },
    "search": {
        "label": "Search and show",
        "description": "Search everything in your account and show records as cards.",
        "tools": ("search", "show_record"),
    },
    "runs": {
        "label": "Runs",
        "description": "Look up, start, pause and remove research runs.",
        "tools": ("list_runs", "get_run", "list_tasks", "create_run", "update_run", "set_run_status", "delete_run"),
    },
    "schools": {
        "label": "Schools and programmes",
        "description": "Look up, save, edit and remove schools and their programmes.",
        "tools": (
            "list_schools", "get_school", "create_school", "update_school", "delete_school",
            "list_programs", "get_program", "save_program", "create_program", "update_program", "delete_program",
        ),
    },
    "professors": {
        "label": "Professors",
        "description": "Research, save, edit and remove professors and their papers.",
        "tools": (
            "spawn_professor_research", "save_professor_record", "confirm_no_match",
            "get_professor", "create_professor", "update_professor", "save_professor_papers", "delete_professor",
        ),
    },
    "opportunities": {
        "label": "Opportunities",
        "description": "Find, save and look up opportunities in the public catalogue.",
        "tools": ("save_opportunity",),
    },
    "matches": {
        "label": "Matches",
        "description": "Look up, review, edit and remove the professors matched to your interests.",
        "tools": ("list_candidates", "get_candidate", "update_candidate", "review_candidate", "delete_candidate"),
    },
    "applications": {
        "label": "Applications",
        "description": "Look up, track, edit and remove your applications.",
        "tools": ("list_applications", "get_application", "save_application", "create_application",
                  "update_application", "delete_application"),
    },
    "drafts": {
        "label": "Email drafts",
        "description": "Write, edit and remove outreach emails.",
        "tools": ("list_drafts", "list_candidate_drafts", "save_email_draft", "update_draft", "delete_draft"),
    },
    # The id stays "cv" so saved settings keep applying.
    "cv": {
        "label": "Documents",
        "description": "Read your documents and suggest changes for your review.",
        "tools": (
            "list_documents",
            "read_document",
            "suggest_changes",
            "cv_list_documents",
            "cv_read",
            "cv_get_application_context",
            "cv_suggest_changes",
            "cv_list_suggestions",
        ),
    },
}

_GROUP_OF = {tool: gid for gid, g in TOOL_GROUPS.items() for tool in g["tools"]}


def group_of(tool_name: str) -> str | None:
    return _GROUP_OF.get(tool_name)


def list_groups() -> list[dict]:
    return [
        {
            "id": gid,
            "label": g["label"],
            "description": g["description"],
            "tools": list(g["tools"]),
        }
        for gid, g in TOOL_GROUPS.items()
    ]
