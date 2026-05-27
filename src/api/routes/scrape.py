"""Scrape routes — POST /scrape-jobspy and POST /scrape-kalibrr endpoints.

Both endpoints call ingestion modules and return normalized job lead lists.
Zero-result detection emits an OPS-01 warning field per RESEARCH.md Pitfall 3.
No DB session needed — scrapers do not write to DB.
n8n loops the results through /ingest-lead separately.
"""

import structlog
from fastapi import APIRouter, Depends

from src.api.app import verify_api_key
from src.api.schemas import ScrapeJobSpyIn, ScrapeKalibrrIn
from src.ingestion.jobspy_runner import run_jobspy
from src.ingestion.kalibrr_scraper import scrape_kalibrr

log = structlog.get_logger()

router = APIRouter()


@router.post("/scrape-jobspy", dependencies=[Depends(verify_api_key)])
async def scrape_jobspy(payload: ScrapeJobSpyIn) -> dict:  # type: ignore[type-arg]
    """Scrape job listings via python-jobspy (Indeed and other boards).

    Calls run_jobspy() in a thread executor (jobspy is synchronous).
    Returns {"jobs": [...], "count": N} plus an optional "warning" field
    on zero results (OPS-01: possible IP block signal).
    """
    results = await run_jobspy(
        search_term=payload.search_term,
        location=payload.location,
        results_wanted=payload.results_wanted,
        hours_old=payload.hours_old,
        site_names=payload.site_names,
    )

    count = len(results)

    if count == 0:
        log.warning(
            "scrape_jobspy_zero_results",
            search_term=payload.search_term,
            location=payload.location,
            site_names=payload.site_names,
        )
        return {
            "jobs": [],
            "count": 0,
            "warning": "zero_results_possible_block",
        }

    log.info(
        "scrape_jobspy_complete",
        search_term=payload.search_term,
        count=count,
    )
    return {"jobs": results, "count": count}


@router.post("/scrape-kalibrr", dependencies=[Depends(verify_api_key)])
async def scrape_kalibrr_endpoint(payload: ScrapeKalibrrIn) -> dict:  # type: ignore[type-arg]
    """Scrape Kalibrr job listings via httpx + BeautifulSoup4.

    Returns {"jobs": [...], "count": N} plus an optional "warning" field
    on zero results (OPS-01: possible selector mismatch or IP block signal).

    NOTE: CSS selectors are best-effort pending human verification at
    the checkpoint:human-verify task in Plan 02-03.
    """
    results = await scrape_kalibrr(
        search_term=payload.search_term,
        max_pages=payload.max_pages,
    )

    count = len(results)

    if count == 0:
        log.warning(
            "scrape_kalibrr_zero_results",
            search_term=payload.search_term,
            max_pages=payload.max_pages,
        )
        return {
            "jobs": [],
            "count": 0,
            "warning": "zero_results_possible_block",
        }

    log.info(
        "scrape_kalibrr_complete",
        search_term=payload.search_term,
        count=count,
    )
    return {"jobs": results, "count": count}
