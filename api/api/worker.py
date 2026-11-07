"""Worker entry point (`python -m api.worker`); queue mechanics in api/runs/queue.py."""

import argparse
import asyncio

import api.models as _model_registry  # noqa: F401 - every table on Base.metadata
from api.core.config import log_config_warnings, settings
from api.runs.queue import main_loop


def main() -> None:
    parser = argparse.ArgumentParser(description="Graduator worker")
    # One task per professor, so loops are the throughput knob. Loops hold no DB
    # connection while waiting on the model; remote-politeness ceilings still apply.
    parser.add_argument("--concurrency", type=int, default=8)
    # Backstop only: idle loops wake on an enqueue notification.
    parser.add_argument(
        "--poll-interval", type=float, default=settings.worker_idle_poll_seconds
    )
    args = parser.parse_args()
    log_config_warnings()
    asyncio.run(
        main_loop(
            concurrency=args.concurrency, poll_interval_seconds=args.poll_interval
        )
    )


if __name__ == "__main__":
    main()
