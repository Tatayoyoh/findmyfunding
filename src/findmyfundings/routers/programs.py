"""Program detail page."""

from fastapi import APIRouter, Request, HTTPException

from findmyfundings.services import funding_repo

router = APIRouter()


@router.get("/program/{program_id}")
async def program_detail(request: Request, program_id: int):
    program = await funding_repo.get_by_id(program_id)
    if not program:
        raise HTTPException(status_code=404, detail="Programme non trouvé")
    return request.app.state.templates.TemplateResponse(
        "detail.html",
        {"request": request, "program": program},
    )
