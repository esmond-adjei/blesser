"""Backfill per-account ownership (migration 015 -> 016).

Assigns every unowned domain row to one account: roots (runs,
applications, CV documents, conversations, registries) directly, children
through their parent chain::

    cd api && uv run python -m scripts.backfill_owner --email you@example.com

Refuses to run when the account is unknown rather than guessing, unless
--create is given (prompts for a password and creates the account first).
"""

import argparse
import asyncio
import getpass

from sqlalchemy import text

from api.auth import security as auth_security
from api.core.db import SessionLocal
from api.core.ids import new_id


async def _fetch_user_id(session, email: str) -> str | None:
    row = (
        await session.execute(
            text("SELECT id FROM users WHERE email = :email"), {"email": email}
        )
    ).first()
    return row[0] if row else None


# (table, parent table, child fk, parent pk) — roots take the owner
# directly, children inherit through one parent hop each, applied
# roots-first.
BACKFILL: tuple[tuple[str, str | None, str | None, str | None], ...] = (
    ("runs", None, None, None),
    ("applications", None, None, None),
    ("cv_documents", None, None, None),
    ("assistant_conversations", None, None, None),
    ("provider_configs", None, None, None),
    ("agent_tools", None, None, None),
    ("agent_tasks", None, None, None),
    ("research_tasks", "runs", "run_id", "id"),
    ("schools", "runs", "run_id", "id"),
    ("candidate_scores", "runs", "run_id", "id"),
    ("professor_index", "runs", "run_id", "id"),
    ("tool_call_logs", "research_tasks", "task_id", "id"),
    ("programs", "schools", "school_id", "id"),
    ("email_drafts", "candidate_scores", "candidate_id", "id"),
    ("professors", "programs", "program_id", "id"),
    ("papers", "professors", "professor_id", "id"),
    ("cv_tailored_versions", "cv_documents", "document_id", "id"),
    ("cv_suggestions", "cv_documents", "document_id", "id"),
    ("assistant_messages", "assistant_conversations", "conversation_id", "id"),
)


async def _create_user(session, email: str, password: str) -> str:
    user_id = new_id()
    await session.execute(
        text(
            "INSERT INTO users (id, email, password_hash) "
            "VALUES (:id, :email, :hash)"
        ),
        {"id": user_id, "email": email, "hash": auth_security.hash_password(password)},
    )
    await session.commit()
    return user_id


def _prompt_password(email: str) -> str:
    for _ in range(3):
        first = getpass.getpass(f"password for {email} (8+ chars): ")
        if len(first) < 8:
            print("too short — 8+ characters required")
            continue
        second = getpass.getpass("repeat the password: ")
        if first != second:
            print("passwords don't match — try again")
            continue
        return first
    raise SystemExit("aborted: password not confirmed")


async def backfill(email: str, create: bool = False) -> dict[str, int]:
    address = email.strip().lower()
    counts: dict[str, int] = {}
    async with SessionLocal() as session:
        user_id = await _fetch_user_id(session, address)
        if user_id is None:
            if not create:
                raise SystemExit(
                    f"no account for {address} — sign up / sign in once, then "
                    "rerun, or rerun with --create to create it here"
                )
            user_id = await _create_user(session, address, _prompt_password(address))
            print(f"created account {address}")
        for table, parent, fk, pk in BACKFILL:
            if parent is None:
                result = await session.execute(
                    text(f"UPDATE {table} SET user_id = :uid WHERE user_id IS NULL"),
                    {"uid": user_id},
                )
            else:
                result = await session.execute(
                    text(
                        f"UPDATE {table} SET user_id = {parent}.user_id "
                        f"FROM {parent} "
                        f"WHERE {table}.{fk} = {parent}.{pk} "
                        f"AND {table}.user_id IS NULL"
                    )
                )
            counts[table] = result.rowcount
        await session.commit()
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill row ownership to one account")
    parser.add_argument("--email", required=True, help="owner account email")
    parser.add_argument(
        "--create",
        action="store_true",
        help="create the account first when it does not exist (prompts for a password)",
    )
    args = parser.parse_args()
    counts = asyncio.run(backfill(args.email, create=args.create))
    total = sum(counts.values())
    for table, count in counts.items():
        print(f"{table}: {count}")
    print(f"assigned {total} row(s) to {args.email.strip().lower()}")


if __name__ == "__main__":
    main()
