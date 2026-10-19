from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.db.session import get_session
from app.services.evidence_retrieval import LexicalEvidenceRetriever
from app.services.pipeline import PipelineService


def get_app_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_pipeline(request: Request) -> PipelineService:
    # Providers (and their HTTP clients) are shared per process; the pipeline
    # object itself is per request so its per-run DOI memo starts empty.
    state = request.app.state
    return PipelineService(
        llm=state.llm,
        paper_providers=state.paper_providers,
        retriever=LexicalEvidenceRetriever(),
        settings=state.settings,
    )


SessionDep = Annotated[AsyncSession, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_app_settings)]
PipelineDep = Annotated[PipelineService, Depends(get_pipeline)]
