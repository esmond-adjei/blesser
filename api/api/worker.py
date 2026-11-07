"""Worker entry point (`python -m api.worker`); queue mechanics in api/scans/queue.py."""

import argparse
import asyncio

import api.models as _model_registry  # noqa: F401 - every table on Base.metadata
from api.core.config import log_config_warnings
from api.scans.queue import main_loop


def main() -> None:
    parser = argparse.ArgumentParser(description="Blesser worker")
    # Concurrent agent tasks; loops hold no DB connection while waiting on the model.
    parser.add_argument("--concurrency", type=int, default=4)
    # Backstop only: idle loops wake on an enqueue notification.
    parser.add_argument("--poll-interval", type=float, default=5.0)
    args = parser.parse_args()
    log_config_warnings()
    asyncio.run(main_loop(concurrency=args.concurrency, poll_seconds=args.poll_interval))


if __name__ == "__main__":
    main()
