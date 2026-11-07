"""Provider-neutral tool definitions for the research worker."""

TOOL_DEFINITIONS = [
    {
        "name": "search_web",
        "description": (
            "Search the web. Use this to find university program pages, "
            "department websites, and faculty listing pages."
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
            "Fetch and return the cleaned text content of a web page, e.g. "
            "a department faculty listing or a professor's homepage. Long "
            "pages end with a note giving the offset to read the rest from."
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
        "name": "find_openalex_author",
        "description": (
            "Search OpenAlex for a researcher by name, optionally disambiguated "
            "by institution. Returns candidate author records with an openalex_id "
            "you need for get_author_works. Always confirm the institution matches "
            "before proceeding - common names return multiple unrelated people. "
            "An ORCID or DBLP id linked on the faculty page is used first; when "
            "OpenAlex has nobody at the school or is down, DBLP and NIH/NSF grants "
            "are checked, and their candidates carry a `source` and a prefixed id "
            "(dblp:, nih:, nsf:, orcid:) that works everywhere an openalex_id does."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "institution_hint": {"type": "string"},
            },
            "required": ["name"],
        },
    },
    {
        "name": "get_author_works",
        "description": (
            "Get an OpenAlex author's most recent publications: title, year, venue, "
            "link and the start of each abstract. score_alignment scores the full "
            "abstracts, so pass full: true only if you must read one in full."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "openalex_id": {"type": "string"},
                "full": {
                    "type": "boolean",
                    "description": "Return whole abstracts instead of the first few lines.",
                },
            },
            "required": ["openalex_id"],
        },
    },
    {
        "name": "score_alignment",
        "description": (
            "Compute a deterministic similarity score between the student's "
            "research interest and a professor's fetched works. Pass the "
            "openalex_id you fetched works for: the works are scored on the "
            "server, and the result lists the best-matching titles to cite. "
            "Always use this rather than estimating a match score yourself."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "openalex_id": {
                    "type": "string",
                    "description": "Author whose works get_author_works fetched (or a dblp:, nih:, nsf: or orcid: id find_openalex_author returned).",
                },
                "interest_text": {
                    "type": "string",
                    "description": "Legacy: only with abstracts.",
                },
                "abstracts": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Legacy: texts to score instead of fetched works.",
                },
            },
        },
    },
    {
        "name": "save_professor_record",
        "description": (
            "Persist a professor and their fetched papers to the database, "
            "and record their alignment score and your rationale for the match. "
            "Call this once you have gathered and scored a professor's work."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "profile_url": {"type": "string"},
                "openalex_id": {
                    "type": "string",
                    "description": "The author id find_openalex_author returned: an OpenAlex id, or a dblp:, nih:, nsf: or orcid: id from another source.",
                },
                "lab_name": {
                    "type": "string",
                    "description": "Research group or lab the PhD student would join, when known from the faculty or lab page.",
                },
                "bio": {
                    "type": "string",
                    "description": "Short biography of the professor, quoted or closely paraphrased from their faculty page when available.",
                },
                "bio_source": {
                    "type": "string",
                    "description": "'faculty' when the bio comes from their faculty page, 'generated' when you wrote it from their papers.",
                },
                "socials": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "label": {"type": "string"},
                            "url": {"type": "string"},
                        },
                        "required": ["label", "url"],
                    },
                    "description": "Academic links beyond the faculty profile: Scholar, lab page, personal site, ResearchGate. Skip social-media profiles.",
                },
                "photo_url": {
                    "type": "string",
                    "description": (
                        "Their portrait: an exact URL from the 'Images on this page' "
                        "list fetch_page gave for their profile or faculty page, when "
                        "the alt text or file name shows it is this professor. Include "
                        "it whenever one is listed."
                    ),
                },
                "papers": {
                    "type": "array",
                    "description": "The aligned works by exact title, as get_author_works returned them. Only the title is needed: abstract, year and URL are stored from OpenAlex.",
                    "items": {
                        "type": "object",
                        "properties": {"title": {"type": "string"}},
                        "required": ["title"],
                    },
                },
                "similarity_score": {
                    "type": "number",
                    "minimum": 0,
                    "maximum": 1,
                    "description": "Exactly the score score_alignment returned for this author's fetched abstracts.",
                },
                "rationale": {
                    "type": "string",
                    "description": "1-3 sentences on WHY this professor's work aligns, citing specific papers.",
                },
                "unverified": {
                    "type": "boolean",
                    "description": (
                        "Only when OpenAlex can't confirm them: it was unavailable, found "
                        "nobody by this name, or lists no works for them. Saves the "
                        "professor flagged for the student, with no papers and no score; "
                        "the rationale says what you checked."
                    ),
                },
            },
            "required": ["name", "rationale"],
        },
    },
    {
        "name": "save_program",
        "description": (
            "Persist a school + specific graduate program you've identified as "
            "relevant to the student's target field and region. This queues the "
            "program for faculty research in a later step, so only save programs "
            "you're reasonably confident actually exist and match the degree level "
            "and field requested - not every program the school happens to offer."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "school_name": {"type": "string"},
                "school_country": {"type": "string"},
                "school_website": {"type": "string"},
                "school_image_url": {
                    "type": "string",
                    "description": (
                        "The school's logo, crest or a campus photo: an exact URL "
                        "from the 'Images on this page' list fetch_page gave for "
                        "one of the school's own pages. Include it whenever one is "
                        "listed."
                    ),
                },
                "school_tier": {
                    "type": "string",
                    "enum": ["top", "strong", "solid", "accessible"],
                    "description": (
                        "The school's selectivity tier, when the brief lists "
                        "target tiers: required then, and must be one of them."
                    ),
                },
                "program_name": {"type": "string"},
                "department_url": {
                    "type": "string",
                    "description": "URL of the department or faculty listing page, if found.",
                },
            },
            "required": ["school_name", "program_name"],
        },
    },
    {
        "name": "save_email_draft",
        "description": (
            "Save a personalized cold email draft for a candidate you've already "
            "saved with save_professor_record. This never sends anything - it only "
            "queues a draft for human review."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "candidate_id": {"type": "string"},
                "subject": {"type": "string", "maxLength": 200},
                "body": {
                    "type": "string",
                    "maxLength": 2000,
                    "description": "At most 250 words. Cite a matched paper by title; use [brackets] for facts about the student you weren't given.",
                },
            },
            "required": ["candidate_id", "subject", "body"],
        },
    },
    {
        "name": "spawn_professor_research",
        "description": (
            "Queue faculty names for individual research: one "
            "research_one_professor task per name, each researching exactly "
            "one professor. Call once with all plausible names from the "
            "faculty listing, best first: names past the program's share wait "
            "and start as slots free up. Then stop - do not research "
            "professors yourself in this task."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "names": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Faculty names exactly as listed on the department page.",
                },
            },
            "required": ["names"],
        },
    },
    {
        "name": "save_application",
        "description": (
            "Index a graduate application you've researched (admissions page, "
            "deadline, requirements, fee waiver) into the student's application "
            "tracker. Call this after fetching the program's admissions page "
            "when it carries real application facts - not guesses. An existing "
            "entry for the same school + program is updated in place, filling "
            "only empty fields, so researcher edits are never overwritten. "
            "Notes must follow the application note template from your task "
            "instructions."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "school": {"type": "string"},
                "program": {"type": "string"},
                "degree_type": {"type": "string"},
                "location": {"type": "string"},
                "link": {
                    "type": "string",
                    "description": "Admissions page URL you fetched.",
                },
                "deadline": {
                    "type": "string",
                    "description": "ISO date yyyy-mm-dd, or empty when unknown.",
                },
                "requirements": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Application requirements found, e.g. statement, transcripts, references.",
                },
                "offer": {"type": "string"},
                "fee_waiver": {"type": "boolean"},
                "fee_waiver_notes": {"type": "string"},
                "professors": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Professor names linked to this application, if any.",
                },
                "notes": {
                    "type": "string",
                    "description": "Application notes in the required template format (see task instructions).",
                },
            },
            "required": ["school", "notes"],
        },
    },
    {
        "name": "confirm_no_match",
        "description": (
            "Call this when you have finished investigating and concluded "
            "there is nothing worth saving - e.g. the professor's work does "
            "not align, or no faculty listing could be found. This counts as "
            "completing the task; do not just finish without calling it."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "reason": {
                    "type": "string",
                    "description": "One sentence on what you checked and why nothing qualified.",
                },
                "reason_code": {
                    "type": "string",
                    "enum": [
                        "low_score",
                        "no_openalex_match",
                        "institution",
                        "no_faculty_page",
                        "other",
                    ],
                    "description": (
                        "Which reason applies: low_score (work doesn't align), "
                        "no_openalex_match, institution (OpenAlex places them "
                        "elsewhere), no_faculty_page, or other."
                    ),
                },
            },
            "required": ["reason", "reason_code"],
        },
    },
]
