#!/usr/bin/env python3
"""CLI to trigger the batch matching job (scan unlinked documents and link to exam_sets).
Run from project root: python scripts/run_batch_matcher.py [limit]
"""

import asyncio
import logging
import sys

from app.services.batch_matcher import run_batch_matcher

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)


async def main() -> None:
    limit = 500
    if len(sys.argv) > 1:
        try:
            limit = int(sys.argv[1])
        except ValueError:
            print("Usage: python run_batch_matcher.py [limit]", file=sys.stderr)
            sys.exit(1)
    stats = await run_batch_matcher(limit=limit)
    print(
        f"Batch matcher: scanned={stats['scanned']} matched={stats['matched']} "
        f"created={stats['created']} errors={stats['errors']}"
    )


if __name__ == "__main__":
    asyncio.run(main())
