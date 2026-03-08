"""AI-powered extraction of structured funding data from scraped content."""

import json

import anthropic

from findmyfundings.config import settings
from findmyfundings.database import get_db
from findmyfundings.models import FundingExtraction

EXTRACTION_PROMPT = """Tu es un assistant spécialisé dans l'analyse de programmes de financement pour des structures (associations, ONG, coopératives, entreprises sociales, etc.).

À partir du texte suivant décrivant un programme de financement, extrais les informations structurées en JSON avec les champs suivants :

- min_amount_eur: montant minimum de financement en euros (entier ou null si non mentionné)
- max_amount_eur: montant maximum de financement en euros (entier ou null)
- cofinancing_pct: pourcentage de co-financement requis (entier ou null)
- eligible_structures: liste de types de structures éligibles (ex: ["association", "ONG", "coopérative"])
- eligible_themes: liste de thèmes/domaines éligibles (ex: ["environnement", "social", "énergie"])
- application_type: type de candidature - "appel_a_projets" | "fil_de_leau" | "permanent" | null
- next_deadline: prochaine date limite connue au format "YYYY-MM-DD" ou null
- summary: résumé en 2-3 phrases du programme de financement

Réponds UNIQUEMENT avec le JSON, sans explication.

Texte à analyser :
{content}"""


async def extract_funding_info(content: str) -> FundingExtraction | None:
    """Use Claude to extract structured funding info from text content."""
    if not settings.anthropic_api_key:
        return None

    try:
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        message = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1024,
            messages=[
                {
                    "role": "user",
                    "content": EXTRACTION_PROMPT.format(content=content[:10000]),
                }
            ],
        )

        response_text = message.content[0].text.strip()
        # Clean up potential markdown code blocks
        if response_text.startswith("```"):
            response_text = response_text.split("\n", 1)[1]
            response_text = response_text.rsplit("```", 1)[0]

        data = json.loads(response_text)
        return FundingExtraction(**data)

    except Exception:
        return None


async def update_program_with_extraction(
    program_id: int, extraction: FundingExtraction
):
    """Update a funding program with AI-extracted structured data."""
    db = await get_db()
    try:
        await db.execute(
            """UPDATE funding_programs SET
                min_amount_eur = ?,
                max_amount_eur = ?,
                cofinancing_pct = ?,
                eligible_structures = ?,
                eligible_themes = ?,
                application_type = ?,
                next_deadline = ?,
                last_scraped_at = CURRENT_TIMESTAMP,
                last_updated_at = CURRENT_TIMESTAMP
            WHERE id = ?""",
            (
                extraction.min_amount_eur,
                extraction.max_amount_eur,
                extraction.cofinancing_pct,
                json.dumps(extraction.eligible_structures, ensure_ascii=False),
                json.dumps(extraction.eligible_themes, ensure_ascii=False),
                extraction.application_type,
                str(extraction.next_deadline) if extraction.next_deadline else None,
                program_id,
            ),
        )
        await db.commit()
    finally:
        await db.close()
