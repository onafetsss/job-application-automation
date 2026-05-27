"""Scrape routes — stub for Phase 2 plan 02-03 implementation."""

from fastapi import APIRouter

router = APIRouter()


@router.get("/")
async def scrape_status() -> dict:
    return {"status": "not_implemented"}
