"""Deterministic checks on a drafted outreach email before it is saved.

A draft must cite a stored paper by title, stay within MAX_DRAFT_WORDS, carry
no unfilled {braces} ([bracket] placeholders are expected), and state no
background about the student (degree, grades, publications, experience,
affiliation) that isn't bracketed or grounded in the known facts. The target
school may appear only in the ask.

Unknown names are only questioned in clauses about the student's background,
never in the ask or about the professor. The checks are pattern-based, so the
prompt and brief remain the first defence.
"""

import re

MAX_DRAFT_WORDS = 250
MAX_SUBJECT_CHARS = 200

_BRACES = re.compile(r"\{[^{}\n]{0,80}\}")
_BRACKETED = re.compile(r"\[[^\[\]\n]{0,120}\]")
#: What bracketed text becomes before the claim checks: no claim, and not
#: an institution name.
_PLACEHOLDER = "placeholder"
_SENTENCES = re.compile(r"(?<=[.!?])\s+|\n+")
_FIRST_PERSON = re.compile(r"\b(i|i'm|i've|i am|i have|my|me)\b", re.IGNORECASE)
_THIRD_PERSON = re.compile(
    r"\b(the|this) (student|applicant|candidate)\b|"
    r"\b(he|she) (is|was|has|had|holds|earned|completed|studied|worked|graduated)\b",
    re.IGNORECASE,
)

#: Sentences that state the ask, not a credential ("I am applying for a
#: PhD"); the degree pattern ignores them.
_ASK = re.compile(
    r"\b(apply|applying|application|join|joining|admission|prospective|seeking|"
    r"hope to|would like to|looking for|interested in|taking students|pursue|"
    r"aspiring|aspire)\b",
    re.IGNORECASE,
)

#: (label, pattern, applies to ask sentences too)
_CLAIMS = [
    (
        "grades",
        re.compile(
            r"\b(c?gpa|grade point|first[- ]class|summa cum laude|magna cum laude|"
            r"with distinction|honou?rs degree|valedictorian|[0-4]\.\d{1,2}\s*/\s*4(\.0)?|"
            r"[0-4]\.\d{1,2}\s+(average|overall|cumulative|grade)|"
            r"(average|grades?|cumulative|marks?|score) (of |was |is )?[0-4]\.\d{1,2}\b|"
            r"\d{2}(\.\d+)?\s*%\s*(average|overall)|"
            r"(average|grades?|marks?) (of |was |is )?\d{2}(\.\d+)?\s*%|"
            r"top \d{1,2}\s*%|ranked (first|top|\d+)|percentile|class rank|"
            r"top of (my|the|his|her) (class|cohort|year)|dean'?s list|"
            r"(first|1st|second|2nd|third|3rd) in (my|the|his|her) (class|cohort|year))",
            re.IGNORECASE,
        ),
        True,
    ),
    (
        "degree",
        re.compile(
            r"\b(b\.?sc|b\.?s\.|b\.?a\.|b\.?eng|bachelor'?s?|m\.?sc|m\.?s\.|m\.?eng|"
            r"master'?s?|m\.?phil|ph\.?d|doctorate|undergraduate degree|graduated)\b",
            re.IGNORECASE,
        ),
        False,
    ),
    (
        "publications",
        re.compile(
            r"\b(published|publications?|first[- ]author(ed)?|co-?authored|"
            r"my (paper|papers|thesis|dissertation)|peer[- ]reviewed)\b",
            re.IGNORECASE,
        ),
        True,
    ),
    (
        "experience",
        re.compile(
            r"\b(\d+|one|two|three|four|five|six|several|many)\+?\s+years?\b",
            re.IGNORECASE,
        ),
        True,
    ),
]


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", text.lower())).strip()


#: A capitalized name ("Stanford", "University of Ghana", "ETH Zurich").
_ORG = r"[A-Z][\w&'.-]*(?:\s+(?:of|for|and|de|the)\s+[A-Z][\w&'.-]*|\s+[A-Z][\w&'.-]*)*"
_ROLE = (
    r"(?i:student|graduate|alumn(?:us|a|i)|undergrad(?:uate)?|intern|researcher|"
    r"engineer|employee|research assistant|teaching assistant|lecturer|fellow|"
    r"degree|b\.?sc|m\.?sc|m\.?phil|ph\.?d|bachelor'?s|master'?s)"
)
# Not after a possessive: "your work from 2021", "their work at Google"
# describe someone else's work, not the student's employer.
_NOT_POSSESSED = r"(?<!your )(?<!Your )(?<!their )(?<!his )(?<!her )(?<!the )"
_AT_VERB = (
    _NOT_POSSESSED + r"(?i:work|worked|working|employed|intern|interned|interning|"
    r"enrolled|study|studied|studying|graduated)\s+(?i:at|for|from)"
)
#: (pattern capturing the institution, applies to ask sentences too)
_AFFILIATIONS = [
    # "a student at Stanford", "graduate of the University of Ghana",
    # "an MSc from ETH Zurich"
    (re.compile(rf"\b{_ROLE}\s+(?i:at|of|from|with|in)\s+(?:the\s+)?({_ORG})"), True),
    # "a Stanford student", "an ETH Zurich alumnus"
    (re.compile(rf"\b({_ORG})\s+{_ROLE}\b"), True),
    # "I work at Acme", "I studied at KNUST", "graduated from the University of Ghana"
    (re.compile(rf"\b{_AT_VERB}\s+(?:the\s+)?({_ORG})"), True),
    # "I attend Stanford University", "my alma mater is Stanford"
    (
        re.compile(
            rf"\b(?i:attend|attended|attending|alma mater (?:is|was))\s+(?:the\s+)?({_ORG})"
        ),
        True,
    ),
    # "did my undergrad at Stanford", "earned a BSc from KNUST"
    (
        re.compile(
            r"\b(?i:did|doing|completed|completing|finished|earned|got|received|"
            r"obtained|pursued|pursuing)\s+(?i:my|a|an|the)\s+[\w'-]+(?:\s+[\w'-]+)?"
            rf"\s+(?i:at|from|in)\s+(?:the\s+)?({_ORG})"
        ),
        True,
    ),
    # "I work at a robotics startup": unnamed, but still background ("I
    # hope to work at a lab like yours" is the ask, not a claim)
    (
        re.compile(
            r"\b(?i:i|i've|i have|i'm|i am|i was|we)\s+(?i:currently\s+|previously\s+|"
            r"also\s+|have\s+|had\s+|been\s+)*"
            rf"{_AT_VERB}\s+(?i:an?)\s+"
            r"(?!(?i:while|bit|moment|time|few|couple|long|year|month|week|day|talk|"
            r"seminar|conference|workshop|lecture)s?\b)"
            r"([\w-]+(?:\s+[\w-]+)?)"
        ),
        False,
    ),
]
#: Capitalized words that are not institution names.
_NOT_ORG = {
    "i", "a", "an", "the", "as", "my", "dear", "professor", "prof", "dr",
    "phd", "ph", "d", "msc", "ms", "masters", "master", "mphil", "bsc", "bs",
    "ba", "beng", "meng", "doctoral", "undergraduate", "graduate", "final",
    "year", "first", "second", "third", "fourth", "current", "former",
    _PLACEHOLDER,
}  # fmt: skip


def _org_terms(name: str) -> list[str]:
    return [t for t in _norm(name).split() if t not in _NOT_ORG and len(t) > 1]


# Catch-all for other phrasings ("Stanford is where I did my undergrad"): in a
# clause about the student that doesn't address the professor, every
# capitalized name must come from the facts, target, professor or a cited
# paper. The second-person skip is per clause, so "I admire your work, and
# Stanford is my alma mater" still checks the alma mater.
_SECOND_PERSON = re.compile(r"\b(you|your|yours)\b", re.IGNORECASE)
#: The general name check only runs on clauses about the student's
#: background: "Moreover, I would love to apply these ideas" or "I am
#: fascinated by Large Language Models" name topics, not affiliations.
_BACKGROUND = re.compile(
    r"\b(undergrad\w*|graduat\w*|alma mater|degree|bachelor\w*|master'?s|"
    r"stud(?:y|ied|ying)\s+(?:at|in|for)|student|alumn\w*|intern\w*|employ\w*|"
    r"work(?:ed|ing)?\s+(?:at|for|with)|job|position|spent|summer|attend\w*|"
    r"enrol\w*|affiliat\w*|thesis|supervis\w*|advis\w*|where i)\b",
    re.IGNORECASE,
)
#: Short all-caps tokens are usually fields, venues or tools (NLP, ICML,
#: GNN). An acronym named as an affiliation is still caught by the
#: explicit patterns above ("I studied at KNUST", "a CMU graduate").
_ACRONYM = re.compile(r"^[A-Z0-9]{2,5}s?$")
_CLAUSES = re.compile(r"[;:\u2014]|\b(?:and|but|or)\b", re.IGNORECASE)
_NAME = re.compile(rf"(?<![\w'-]){_ORG}")
#: Capitalized words that start sentences or are otherwise not names.
_NOT_NAME = _NOT_ORG | {
    "after", "also", "although", "and", "at", "because", "before", "being",
    "both", "but", "by", "during", "each", "every", "for", "from", "having",
    "here", "however", "if", "in", "into", "it", "its", "last", "many", "me",
    "most", "next", "now", "of", "on", "one", "our", "over", "previously",
    "since", "so", "some", "that", "then", "there", "these", "this", "those",
    "through", "to", "two", "we", "what", "when", "where", "which", "while",
    "with", "within", "without", "yet", "student", "applicant", "candidate",
    "he", "she", "his", "her", "january", "february", "march", "april", "may",
    "june", "july", "august", "september", "october", "november", "december",
    "monday", "tuesday", "wednesday", "thursday", "friday", "saturday",
    "sunday", "english", "spring", "summer", "fall", "autumn", "winter", "term",
    "semester", "intake", "cycle", "cv", "resume", "transcript", "moreover",
    "furthermore", "thus", "hence", "given", "inspired", "additionally",
    "finally", "indeed", "currently", "recently", "please", "thank", "thanks",
    "best", "regards", "sincerely", "kind", "dear",
}  # fmt: skip


def _with_initials(text: str) -> str:
    """`text` plus the initials of its 2-4 word runs, so "reinforcement
    learning" also grounds "RL"."""
    words = text.split()
    initials = {
        "".join(w[0] for w in words[i : i + n])
        for n in (2, 3, 4)
        for i in range(len(words) - n + 1)
    }
    return f"{text} {' '.join(sorted(initials))}"


def _ungrounded_name(sentence: str, known: str) -> str | None:
    for clause in _CLAUSES.split(sentence):
        if _SECOND_PERSON.search(clause):
            continue
        if not (_FIRST_PERSON.search(clause) or _THIRD_PERSON.search(clause)):
            continue
        if not _BACKGROUND.search(clause):
            continue
        for match in _NAME.finditer(clause):
            words = [w for w in match.group(0).split() if not _ACRONYM.match(w)]
            terms = [
                t
                for t in _norm(" ".join(words)).split()
                if t not in _NOT_NAME
                and len(t) > 1
                and not t.endswith(("ly", "ing", "ed"))
            ]
            if terms and not _grounded(terms, known):
                return match.group(0)
    return None


def _grounded(terms: list[str], facts: str) -> bool:
    return all(f" {t} " in f" {facts} " for t in terms)


_ASPIRING = re.compile(r"\b(aspiring|future|would-be|prospective)\s+$", re.IGNORECASE)


def _ungrounded_affiliation(sentence: str, facts: str, targets: str, is_ask: bool):
    """The first institution the sentence names as the student's own that
    the known facts don't (the target school is fine inside the ask)."""
    for pattern, on_ask in _AFFILIATIONS:
        if is_ask and not on_ask:
            continue
        for match in pattern.finditer(sentence):
            terms = _org_terms(match.group(1))
            if not terms:
                continue  # "a PhD student", "student at [placeholder]"
            if _ASPIRING.search(sentence[: match.start()]):
                continue  # "an aspiring NLP researcher": a field, not an employer
            if _grounded(terms, facts):
                continue
            if is_ask and targets and _grounded(terms, targets):
                continue
            return match.group(0)
    return None


def cites_a_paper(body: str, titles: list[str]) -> bool:
    """True when the body names a stored paper: the whole normalized title, or a
    5-word run of it at least 20 characters long."""
    text = _norm(body)
    for title in titles:
        norm = _norm(title or "")
        if not norm:
            continue
        if norm in text:
            return True
        words = norm.split()
        for i in range(len(words) - 4):
            window = " ".join(words[i : i + 5])
            if len(window) >= 20 and window in text:
                return True
    return False


#: Words a draft may use for the degree the student is seeking.
_DEGREE_TERMS = {
    "phd": "phd ph d doctorate doctoral",
    "masters": "masters master master's msc m sc ms meng m eng mphil",
}


def target_names_for(school_name: str | None, *extra: str | None) -> str:
    """Target school (and professor) names plus initials; in a student claim they
    count only inside the ask."""
    names = [n for n in (school_name, *extra) if n]
    initials = ["".join(w[0] for w in n.split() if w[:1].isupper()) for n in names]
    return _norm(" ".join(names + initials))


def known_facts_for(run) -> str:
    """The brief's known facts as one text: degree sought, field, interest statement."""
    level = (getattr(run, "degree_level", "") or "").lower()
    degree = " ".join(
        terms for key, terms in _DEGREE_TERMS.items() if level in (key, "either")
    )
    return " ".join(
        [degree, getattr(run, "field", "") or "", run.interest_statement or ""]
    )


def unsupported_claims(
    body: str,
    known_facts: str,
    targets: str = "",
    paper_titles: list[str] | None = None,
    context: str = "",
) -> list[str]:
    """Background claims the known facts don't support, as short quotes.
    Bracketed text never counts."""
    facts = _norm(known_facts)
    known = _with_initials(
        " ".join(
            [
                facts,
                targets,
                _norm(context),
                *(_norm(t or "") for t in paper_titles or []),
            ]
        )
    )
    found: list[str] = []
    for sentence in _SENTENCES.split(_BRACKETED.sub(f" {_PLACEHOLDER} ", body)):
        sentence = sentence.strip()
        if not sentence or not (
            _FIRST_PERSON.search(sentence) or _THIRD_PERSON.search(sentence)
        ):
            continue
        is_ask = bool(_ASK.search(sentence))
        affiliation = _ungrounded_affiliation(sentence, facts, targets, is_ask)
        if affiliation is None and not is_ask:
            # The ask names the target's world ("join the Robotics
            # Institute at CMU"); the explicit patterns still check it.
            affiliation = _ungrounded_name(sentence, known)
        if affiliation is not None:
            found.append(f'affiliation: "{sentence[:90]}"')
            continue
        claim = _ungrounded_claim(sentence, facts, is_ask)
        if claim is not None:
            found.append(f'{claim}: "{sentence[:90]}"')
    return found


_FUTURE = re.compile(r"\b(next|coming|future|following|upcoming)\s+$", re.IGNORECASE)


def _ungrounded_claim(sentence: str, facts: str, is_ask: bool) -> str | None:
    """Label of the first unsupported claim, checked per clause. In a clause that
    turns to the professor only the part before "you/your" is the student's, and
    plans ("in the next five years") are not experience."""
    for clause in _CLAUSES.split(sentence):
        own = _SECOND_PERSON.split(clause, maxsplit=1)[0]
        for label, pattern, on_ask in _CLAIMS:
            if is_ask and not on_ask:
                continue
            match = pattern.search(own)
            if match is None:
                continue
            if label == "experience" and _FUTURE.search(own[: match.start()]):
                continue
            term = _norm(match.group(0))
            if term and f" {term} " in f" {facts} ":
                continue
            return label
    return None


def verify_draft(
    subject: str,
    body: str,
    paper_titles: list[str] | None,
    known_facts: str | None = None,
    targets: str = "",
    context: str = "",
) -> str | None:
    """Error message for the model, or None when the draft may be saved.
    `paper_titles` None skips the citation check, `known_facts` None the claim
    check (drafts asked for in chat)."""
    if not subject.strip() or not body.strip():
        return "Subject and body are both required."
    if len(subject) > MAX_SUBJECT_CHARS:
        return f"Subject is over {MAX_SUBJECT_CHARS} characters; shorten it."
    words = len(body.split())
    if words > MAX_DRAFT_WORDS:
        return (
            f"Body is {words} words; keep it to {MAX_DRAFT_WORDS} or fewer. "
            "Cut background and filler, keep the paper and the ask."
        )
    braces = _BRACES.findall(subject + "\n" + body)
    if braces:
        return (
            f"Unfilled template placeholders {braces[:3]}. Write the text, or use "
            "[square brackets] only for facts about the student you weren't given."
        )
    if known_facts is not None:
        claims = unsupported_claims(body, known_facts, targets, paper_titles, context)
        if claims:
            return (
                "The draft states background the student never gave you: "
                + "; ".join(claims[:3])
                + ". Write those facts as [square-bracket placeholders] for the "
                "student to fill in, or leave them out."
            )
    if paper_titles is not None:
        if not paper_titles:
            return "This professor has no stored papers to cite; don't draft."
        if not cites_a_paper(body, paper_titles):
            return (
                "The body must name at least one of the professor's stored papers "
                f"by title: {paper_titles[:5]}"
            )
    return None
