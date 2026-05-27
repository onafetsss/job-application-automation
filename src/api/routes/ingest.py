"""Ingest routes — POST /ingest-lead universal entry point for all lead sources."""

from fastapi import APIRouter

router = APIRouter()


@router.get("/")
async def ingest_status() -> dict:
    return {"status": "not_implemented"}
