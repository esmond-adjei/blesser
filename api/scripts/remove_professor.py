"""Remove a researched person from every account and block re-collection.

For removal requests from professors (or anyone else Graduator stored as a
research subject)::

    cd api && uv run python -m scripts.remove_professor --openalex-id https://openalex.org/A123
    cd api && uv run python -m scripts.remove_professor --name "Ada Lovelace" --school "ETH Zurich"
    cd api && uv run python -m scripts.remove_professor --email ada@example.edu --note "request 2026-10-15"

Deletes matching professor records with their papers, candidate scores,
outreach drafts and professor index entries, and records an opt-out so future research skips them.
"""

import argparse
import asyncio

from api.core.db import SessionLocal
from api.prospects.optouts import remove_person


async def _run(args) -> dict:
    async with SessionLocal() as session:
        return await remove_person(
            session,
            openalex_id=args.openalex_id,
            name=args.name,
            school=args.school,
            email=args.email,
            note=args.note,
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--openalex-id")
    parser.add_argument("--name")
    parser.add_argument("--school")
    parser.add_argument("--email")
    parser.add_argument("--note")
    counts = asyncio.run(_run(parser.parse_args()))
    print(
        "removed {professors} professor record(s), {candidates} candidate(s), "
        "{drafts} draft(s), {papers} paper(s), {indexed} index entr(ies); "
        "opt-out recorded".format(**counts)
    )


if __name__ == "__main__":
    main()
