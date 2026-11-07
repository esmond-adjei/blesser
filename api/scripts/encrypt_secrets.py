"""Re-save stored provider API keys encrypted (one-off after upgrading).

    make encrypt-secrets

Idempotent: already-encrypted values are left as they are.
"""

import asyncio

from sqlalchemy import text

from api.core.db import SessionLocal
from api.core.secrets import PREFIX, encrypt


async def main() -> None:
    async with SessionLocal() as session:
        rows = (
            await session.execute(
                text("SELECT user_id, provider, api_key FROM provider_configs")
            )
        ).all()
        changed = 0
        for user_id, provider, raw in rows:
            if raw and not raw.startswith(PREFIX):
                await session.execute(
                    text(
                        "UPDATE provider_configs SET api_key = :v "
                        "WHERE user_id = :u AND provider = :p"
                    ),
                    {"v": encrypt(raw), "u": user_id, "p": provider},
                )
                changed += 1
        await session.commit()
    print(
        f"encrypt-secrets: {changed} key(s) encrypted, {len(rows) - changed} already fine"
    )


if __name__ == "__main__":
    asyncio.run(main())
