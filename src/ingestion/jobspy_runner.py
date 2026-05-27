"""JobSpy runner — async wrapper around synchronous python-jobspy scrape_jobs().

Runs scrape_jobs() in a thread executor to avoid blocking the FastAPI event loop.
"""

import asyncio
from functools import partial

import structlog
from jobspy import scrape_jobs

log = structlog.get_logger()


async def run_jobspy(
    search_term: str,
    location: str = "Remote",
    results_wanted: int = 25,
    hours_old: int = 24,
    site_names: list[str] | None = None,
) -> list[dict]:  # type: ignore[type-arg]
    """Scrape job listings via python-jobspy in a thread executor.

    Returns a list of dicts with keys: title, company, location, job_url, description.
    Returns an empty list when scrape_jobs returns None or an empty DataFrame.
    """
    if site_names is None:
        site_names = ["indeed"]

    log.info(
        "jobspy_scrape_start",
        search_term=search_term,
        location=location,
        results_wanted=results_wanted,
        hours_old=hours_old,
        site_names=site_names,
    )

    loop = asyncio.get_event_loop()
    jobs_df = await loop.run_in_executor(
        None,
        partial(
            scrape_jobs,
            site_name=site_names,
            search_term=search_term,
            location=location,
            results_wanted=results_wanted,
            hours_old=hours_old,
        ),
    )

    if jobs_df is None or jobs_df.empty:
        log.warning(
            "jobspy_scrape_empty",
            search_term=search_term,
            site_names=site_names,
        )
        return []

    keep = ["title", "company", "location", "job_url", "description"]
    # Only include columns that actually exist in the DataFrame
    available = [col for col in keep if col in jobs_df.columns]
    result_df = jobs_df[available].where(jobs_df[available].notna(), other=None)
    results = result_df.to_dict(orient="records")

    log.info(
        "jobspy_scrape_complete",
        search_term=search_term,
        site_names=site_names,
        count=len(results),
    )
    return results
