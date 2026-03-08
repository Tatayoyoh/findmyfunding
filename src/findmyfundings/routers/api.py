"""JSON API endpoints for programmatic access."""

from fastapi import APIRouter, Query

from findmyfundings.models import FundingProgram
from findmyfundings.services import funding_repo, search_service

router = APIRouter(prefix="/api")


@router.get("/programs", response_model=list[FundingProgram])
async def list_programs():
    return await funding_repo.get_all()


@router.get("/programs/{program_id}", response_model=FundingProgram)
async def get_program(program_id: int):
    return await funding_repo.get_by_id(program_id)


@router.get("/search", response_model=list[FundingProgram])
async def search_programs(
    q: str = "",
    category: list[str] = Query(default=[]),
    min_amount: int | None = None,
    max_amount: int | None = None,
):
    return await search_service.search(
        query=q,
        categories=category if category else None,
        min_amount=min_amount,
        max_amount=max_amount,
    )


@router.get("/categories")
async def list_categories():
    return await funding_repo.get_categories()
