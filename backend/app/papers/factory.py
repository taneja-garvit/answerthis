import httpx

from app.core.config import Settings
from app.papers.base import PaperProvider
from app.papers.crossref import CrossrefProvider
from app.papers.openalex import OpenAlexProvider


def build_http_client(settings: Settings) -> httpx.AsyncClient:
    agent = "EvidenceReviewWorkspace/0.1"
    if settings.contact_email:
        agent += f" (mailto:{settings.contact_email})"
    return httpx.AsyncClient(headers={"User-Agent": agent}, follow_redirects=True)


def build_paper_providers(settings: Settings, client: httpx.AsyncClient) -> list[PaperProvider]:
    common = {"timeout": settings.http_timeout_seconds, "max_retries": settings.http_max_retries}
    return [
        CrossrefProvider(client, contact_email=settings.contact_email, **common),
        OpenAlexProvider(
            client,
            contact_email=settings.contact_email,
            api_key=settings.openalex_api_key,
            **common,
        ),
    ]
