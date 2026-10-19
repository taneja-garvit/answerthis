import uuid
from typing import Literal

from fastapi import APIRouter, Query, Response

from app.api.deps import SessionDep
from app.schemas.audit import AuditResponse
from app.services import audit_export
from app.services.audit import build_audit
from app.services.projects import get_project_or_404

router = APIRouter(prefix="/projects/{project_id}", tags=["audit"])


@router.get("/audit", response_model=AuditResponse)
async def get_audit(project_id: uuid.UUID, session: SessionDep) -> AuditResponse:
    return await build_audit(session, project_id)


@router.get("/export")
async def export_audit(
    project_id: uuid.UUID,
    session: SessionDep,
    format: Literal["csv", "json"] = Query(...),
) -> Response:
    project = await get_project_or_404(session, project_id)
    audit = await build_audit(session, project_id)
    filename = audit_export.export_filename(project.title, format, audit.generated_at)
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    if format == "csv":
        # BOM so spreadsheet apps detect UTF-8 (en dashes, ≈, thin spaces).
        body = "﻿" + audit_export.render_csv(audit)
        return Response(body, media_type="text/csv; charset=utf-8", headers=headers)
    return Response(audit_export.render_json(audit), media_type="application/json", headers=headers)
