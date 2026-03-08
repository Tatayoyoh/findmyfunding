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
    min_amount: str = "",
    max_amount: str = "",
):
    min_val = int(min_amount) if min_amount.strip() else None
    max_val = int(max_amount) if max_amount.strip() else None
    programs = await search_service.search(
        query=q,
        categories=category if category else None,
        min_amount=min_val,
        max_amount=max_val,
    )
    return request.app.state.templates.TemplateResponse(
        "partials/program_list.html",
        {"request": request, "programs": programs},
    )
