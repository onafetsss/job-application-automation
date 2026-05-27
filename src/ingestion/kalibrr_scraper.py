"""Kalibrr scraper — async job listing scraper using httpx + BeautifulSoup4.

CSS selectors are best-effort and must be verified against live Kalibrr HTML
(see RESEARCH.md Open Question 1 / checkpoint:human-verify task in Plan 02-03).
"""

from urllib.parse import urljoin

import httpx
import structlog
from bs4 import BeautifulSoup

log = structlog.get_logger()

_KALIBRR_BASE = "https://www.kalibrr.com"
_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


def _extract_text(element) -> str:  # type: ignore[no-untyped-def]
    """Return stripped text from a BeautifulSoup element, or empty string if None."""
    if element is None:
        return ""
    return element.get_text(strip=True)


def _extract_url(element) -> str:  # type: ignore[no-untyped-def]
    """Extract and absolutize href from an anchor element."""
    if element is None:
        return ""
    href = element.get("href", "")
    if not href:
        return ""
    if href.startswith("http"):
        return href
    return urljoin(_KALIBRR_BASE, href)


def _parse_job_cards(soup: BeautifulSoup) -> list[dict]:  # type: ignore[type-arg]
    """Best-effort extraction of job cards from a parsed Kalibrr listing page.

    Tries multiple selector strategies in order of specificity.
    IMPORTANT: Selectors must be verified against live HTML at the checkpoint task.
    Returns a list of dicts with keys: title, company, location, url.
    Skips cards where title could not be extracted.
    """
    jobs: list[dict] = []  # type: ignore[type-arg]

    # Strategy 1: data-testid-based selectors (React component pattern)
    cards = soup.select("[data-testid='job-card']")

    # Strategy 2: common class patterns for job listing containers
    if not cards:
        cards = soup.select("div.job-card")

    # Strategy 3: anchor links to /c/ or /opportunity/ job detail pages (Kalibrr URL pattern)
    if not cards:
        card_anchors = soup.select("a[href*='/c/']") + soup.select("a[href*='/opportunity/']")
        for anchor in card_anchors:
            # The anchor itself is the job card container in this layout
            title_el = anchor.select_one("h2, h3, [data-testid='job-title'], .job-title")
            company_el = anchor.select_one(
                "[data-testid='company-name'], .company-name, [class*='company']"
            )
            location_el = anchor.select_one(
                "[data-testid='job-location'], .job-location, [class*='location']"
            )
            title = _extract_text(title_el)
            if not title:
                title = _extract_text(anchor)
            url = _extract_url(anchor)
            if title and url:
                jobs.append(
                    {
                        "title": title,
                        "company": _extract_text(company_el),
                        "location": _extract_text(location_el),
                        "url": url,
                    }
                )
        return jobs

    # Parse cards from Strategy 1 or 2
    for card in cards:
        title_el = card.select_one(
            "h2, h3, [data-testid='job-title'], .job-title, [class*='title']"
        )
        company_el = card.select_one(
            "[data-testid='company-name'], .company-name, [class*='company']"
        )
        location_el = card.select_one(
            "[data-testid='job-location'], .job-location, [class*='location']"
        )
        anchor_el = card.select_one("a")

        title = _extract_text(title_el)
        url = _extract_url(anchor_el)

        if not title or not url:
            continue

        jobs.append(
            {
                "title": title,
                "company": _extract_text(company_el),
                "location": _extract_text(location_el),
                "url": url,
            }
        )

    return jobs


async def scrape_kalibrr(
    search_term: str,
    max_pages: int = 3,
) -> list[dict]:  # type: ignore[type-arg]
    """Scrape Kalibrr job listings for the given search term.

    Paginates from page 1 to max_pages. Stops early if a page returns no job cards.
    Returns a list of dicts with keys: title, company, location, url.

    Handles HTTP errors gracefully — returns whatever was collected before the error.
    CSS selectors are best-effort and require verification against live HTML
    (checkpoint:human-verify in Plan 02-03).
    """
    jobs: list[dict] = []  # type: ignore[type-arg]

    log.info(
        "kalibrr_scrape_start",
        search_term=search_term,
        max_pages=max_pages,
    )

    async with httpx.AsyncClient(
        headers={"User-Agent": _USER_AGENT},
        follow_redirects=True,
        timeout=30.0,
    ) as client:
        for page in range(1, max_pages + 1):
            url = f"{_KALIBRR_BASE}/job-board/te/{search_term}/{page}"

            try:
                resp = await client.get(url)
                resp.raise_for_status()
            except httpx.HTTPStatusError as exc:
                log.error(
                    "kalibrr_http_error",
                    search_term=search_term,
                    page=page,
                    status_code=exc.response.status_code,
                    error=str(exc),
                )
                # Return whatever was collected before the error rather than crashing
                break
            except httpx.RequestError as exc:
                log.error(
                    "kalibrr_request_error",
                    search_term=search_term,
                    page=page,
                    error=str(exc),
                )
                break

            soup = BeautifulSoup(resp.text, "html.parser")
            page_jobs = _parse_job_cards(soup)

            log.info(
                "kalibrr_page_scraped",
                search_term=search_term,
                page=page,
                jobs_found=len(page_jobs),
            )

            if not page_jobs:
                # No cards found on this page — stop pagination early
                break

            jobs.extend(page_jobs)

    log.info(
        "kalibrr_scrape_complete",
        search_term=search_term,
        total_jobs=len(jobs),
    )
    return jobs
