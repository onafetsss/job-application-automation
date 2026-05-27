import argparse
import asyncio
import os

import structlog
from dotenv import load_dotenv

from src.queue.db import init_db, get_session_factory

# T-01-02: load_dotenv() before any os.environ access; no shell expansion of DB_PATH
load_dotenv()

structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer(),
    ]
)

log = structlog.get_logger()


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Autonomous Job Application Agent")
    parser.add_argument("--dry-run", action="store_true", help="Filter jobs without submitting")
    parser.add_argument(
        "--source", default="all", help="Ingestion source to run (default: all)"
    )
    parser.add_argument(
        "--limit", type=int, default=0, help="Max jobs to process (0 = unlimited)"
    )
    return parser


async def run(args: argparse.Namespace) -> None:
    # T-01-03: resolve DB_PATH via os.environ — never pass to shell; pathlib used in db.py
    db_path = os.environ.get("DB_PATH", "data/jobs.db")

    await init_db(db_path)
    print("DB initialised.")

    log.info("startup", dry_run=args.dry_run, source=args.source, limit=args.limit)

    # TODO (Phase 2): load eligibility config and replace sample_leads with real ingestion
    # TODO (Phase 2): import load_eligibility_config from src.filter.config_loader
    # TODO (Phase 2): import check_eligibility from src.filter.eligibility
    # TODO (Phase 2): import hash_url, is_duplicate from src.filter.dedup
    # TODO (Phase 2): import write_audit, AuditEvent from src.audit_log


def main() -> None:
    parser = build_arg_parser()
    args = parser.parse_args()
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
