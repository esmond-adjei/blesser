"""Ops usage report: model calls and tokens across all accounts.

make usage-report DAYS=30
"""

import argparse
import asyncio

from api.core.db import SessionLocal
from api.metering import service as metering


async def _main(days: int) -> None:
    async with SessionLocal() as session:
        summary = await metering.summary(session, None, days)
        top = await metering.top_accounts(session, days, limit=10)
    t = summary["totals"]
    print(
        f"Last {days} days: {t['calls']:,} calls, {t['input_tokens']:,} in / {t['output_tokens']:,} out tokens"
    )
    print("\nBy feature / provider / model")
    for row in summary["by_feature"]:
        print(
            f"  {row['feature']:<12} {row['provider']:<16} {row['model']:<32}"
            f" {row['calls']:>8,} calls {row['input_tokens'] + row['output_tokens']:>14,} tokens"
        )
    print("\nHeaviest accounts")
    for row in top:
        print(
            f"  {row['email']:<40} {row['calls']:>8,} calls {row['tokens']:>14,} tokens"
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=30)
    asyncio.run(_main(parser.parse_args().days))
