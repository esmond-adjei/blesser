"""Provider-neutral tool definitions for the discovery agent."""

TOOL_DEFINITIONS = [
    {
        "name": "search_web",
        "description": (
            "Search the web for opportunity pages: funders, programmes, calls, "
            "scholarships and the sites that list them."
        ),
        "parameters": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
    },
    {
        "name": "fetch_page",
        "description": (
            "Fetch and return the cleaned text of a web page, such as an "
            "opportunity's official page. Long pages end with a note giving "
            "the offset to read the rest from."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "url": {"type": "string"},
                "offset": {
                    "type": "integer",
                    "minimum": 0,
                    "description": "Character offset to continue a long page from.",
                },
            },
            "required": ["url"],
        },
    },
    {
        "name": "save_opportunity",
        "description": (
            "Add an open opportunity (grant, fellowship, accelerator, scholarship, "
            "competition, internship, call for proposals...) to the public catalogue. "
            "source_url must be a page you fetched with fetch_page in this task that "
            "names the opportunity; a stated deadline must appear on that page. An "
            "opportunity already in the catalogue is refreshed, never duplicated."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Name as the page writes it."},
                "organization": {
                    "type": "string",
                    "description": "Who runs or funds it, as the page writes it.",
                },
                "category": {
                    "type": "string",
                    "enum": ["startup", "research", "student"],
                    "description": "Who it is for: founders, researchers or students.",
                },
                "kind": {
                    "type": "string",
                    "enum": [
                        "grant", "fellowship", "scholarship", "accelerator", "incubator",
                        "competition", "internship", "call_for_proposals", "training",
                        "conference", "job", "other",
                    ],
                },
                "summary": {
                    "type": "string",
                    "description": "1-3 plain sentences: what it is and what it gives.",
                },
                "eligibility": {"type": "string", "description": "Who can apply."},
                "benefits": {
                    "type": "string",
                    "description": "Short: amount, funding or support, e.g. 'Up to USD 50,000'.",
                },
                "location": {
                    "type": "string",
                    "description": "Where it runs or who may apply, e.g. 'Ghana', 'Africa', 'Global'.",
                },
                "countries": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Eligible countries the page names, if it lists them.",
                },
                "requirements": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "What an application needs, e.g. 'Pitch deck', 'CV', 'Two references'.",
                },
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "A few sectors or fields, e.g. 'agritech', 'health', 'STEM'.",
                },
                "deadline": {
                    "type": "string",
                    "description": "The deadline as an ISO date yyyy-mm-dd, only if the page states one.",
                },
                "rolling": {
                    "type": "boolean",
                    "description": "True when the page says applications are rolling or always open.",
                },
                "link": {"type": "string", "description": "Where to apply, if different from source_url."},
                "source_url": {
                    "type": "string",
                    "description": "The fetched page these facts come from.",
                },
            },
            "required": ["title", "category", "source_url"],
        },
    },
]
