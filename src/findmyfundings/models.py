from datetime import date, datetime

from pydantic import BaseModel, Field


class SourceLink(BaseModel):
    url: str
    label: str = ""
    last_hash: str | None = None
    last_checked_at: datetime | None = None
    has_changed: bool = False


class FundingProgram(BaseModel):
    id: int | None = None
    category: str
    name: str
    project_types: str = ""
    selection_criteria: str = ""
    permanent: bool = False
    start_submission_date: date | None = None
    end_submission_date: date | None = None
    pdp_axes: str = ""
    comments: str = ""
    source_urls: list[SourceLink] = []

    # Structured fields (Firecrawl-extracted)
    min_amount_eur: int | None = None
    max_amount_eur: int | None = None
    cofinancing_pct: int | None = None
    eligible_structures: list[str] = []
    eligible_themes: list[str] = []
    application_type: str | None = None
    next_deadline: date | None = None

    # New fields (Firecrawl extraction)
    summary: str = ""
    eligibility_criteria: list[str] = []
    fundable_axes: list[str] = []
    relevant_links: list[str] = []
    pdf_documents: list[str] = []
    tags: list[str] = []

    # Metadata
    last_scraped_at: datetime | None = None
    last_updated_at: datetime | None = None
    created_at: datetime | None = None


class FundingExtraction(BaseModel):
    """Schema requested from Firecrawl /extract endpoint.

    Field names + descriptions guide the LLM. Keep them explicit and in French
    since target pages are French. Required for the spec:
    * Date limite de soumission (start/end_submission_date + permanent)
    * Critères d'éligibilité (eligibility_criteria + eligible_structures + eligible_themes)
    * Montant des fonds (min/max_amount_eur, cofinancing_pct)
    * Résumé (summary)
    * Domaine d'application (project_types)
    * Titre (name)
    * Axes finançables (fundable_axes)
    * Liens pertinents (relevant_links)
    * Documents PDF (pdf_documents)
    * Tags (tags)
    """
    name: str = Field(default="", description="Titre / nom du programme de financement")
    summary: str = Field(default="", description="Résumé en 2-3 phrases du programme")
    project_types: str = Field(default="", description="Domaine d'application : types de projets éligibles")

    eligibility_criteria: list[str] = Field(
        default_factory=list,
        description="Critères d'éligibilité formels : statut juridique requis, taille de structure, ancienneté, territoire, secteur, etc. Un critère par item, formulé clairement.",
    )
    eligible_structures: list[str] = Field(
        default_factory=list,
        description="Types de structures éligibles (ex: association, ONG, coopérative, SCOP, entreprise sociale)",
    )
    eligible_themes: list[str] = Field(
        default_factory=list,
        description="Thèmes ou domaines couverts (ex: environnement, social, énergie, jeunesse)",
    )

    min_amount_eur: int | None = Field(default=None, description="Montant minimum en euros")
    max_amount_eur: int | None = Field(default=None, description="Montant maximum en euros")
    cofinancing_pct: int | None = Field(default=None, description="Pourcentage de co-financement requis")

    application_type: str | None = Field(
        default=None,
        description='Type de candidature: "appel_a_projets" | "fil_de_leau" | "permanent"',
    )
    permanent: bool = Field(default=False, description="True si dépôt permanent/fil de l'eau/sans date limite")
    start_submission_date: date | None = Field(default=None, description="Date de début de soumission au format YYYY-MM-DD")
    end_submission_date: date | None = Field(default=None, description="Date de fin de soumission au format YYYY-MM-DD")
    next_deadline: date | None = Field(default=None, description="Prochaine date limite connue au format YYYY-MM-DD")

    fundable_axes: list[str] = Field(
        default_factory=list,
        description="Axes / volets finançables : actions ou catégories de dépenses couvertes par le programme",
    )
    relevant_links: list[str] = Field(
        default_factory=list,
        description="URLs pertinentes mentionnées sur la page (FAQ, formulaires, contacts, guides)",
    )
    pdf_documents: list[str] = Field(
        default_factory=list,
        description="URLs des documents PDF référencés (règlement, dossier de candidature, annexes)",
    )
    tags: list[str] = Field(
        default_factory=list,
        description='Tags courts caractérisant le programme (ex: "environnement", "social", "innovation", "jeunesse"). 3 à 8 tags pertinents.',
    )


