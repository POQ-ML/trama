#!/usr/bin/env python
"""Local durable queue + source polling worker: python -m scripts.discovery_worker."""

import argparse
import asyncio
import logging
from pathlib import Path
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import settings
from app.core.database import SessionLocal
from app.services.execution import Runtime


async def work(once=False):
    runtime = Runtime(SessionLocal)
    try:
        while True:
            try:
                handled = await runtime.tick()
            except Exception:
                # Never log source bodies, tokens, SQL parameters or exception payloads.
                logging.getLogger("trama.worker").error(
                    "Worker transaction failed; retrying with bounded idle backoff"
                )
                handled = False
            if once:
                return
            await asyncio.sleep(0.05 if handled else settings.WORKER_POLL_SECONDS)
    finally:
        await runtime.aclose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Process durable discovery jobs and due monitor checks"
    )
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    try:
        asyncio.run(work(args.once))
    except KeyboardInterrupt:
        pass
