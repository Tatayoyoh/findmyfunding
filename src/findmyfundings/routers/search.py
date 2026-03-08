"""Main search page and HTMX search endpoint."""

from fastapi import APIRouter, Query, Request

from findmyfundings.services import funding_repo, search_service

router = APIRouter()


@router.get("/")
async def index(request: Request):
    categories = await funding_repo.get_categories()
    programs = await funding_repo.get_all()
    total = await funding_repo.count()
    return request.app.state.templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "categories": categories,
            "programs": programs,
            "total": total,
        },
    )


@router.get("/search")
async def search(
    request: Request,
    q: str = "",
    category: list[str] = Query(default=[]),
    min_amount: int | None = None,
    max_amount: int | None = None,
):
    programs = await search_service.search(
        query=q,
        categories=category if category else None,
        min_amount=min_amount,
        max_amount=max_amount,
    )
    return request.app.state.templates.TemplateResponse(
        "partials/program_list.html",
        {"request": request, "programs": programs},
    )
