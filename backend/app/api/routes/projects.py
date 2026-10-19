import uuid

from fastapi import APIRouter, Response, status

from app.api.deps import SessionDep
from app.schemas.project import ProjectCreate, ProjectResponse
from app.services import projects as project_service

router = APIRouter(prefix="/projects", tags=["projects"])


@router.post("", status_code=status.HTTP_201_CREATED, response_model=ProjectResponse)
async def create_project(
    payload: ProjectCreate, session: SessionDep, response: Response
) -> ProjectResponse:
    project = await project_service.create_project(session, payload)
    response.headers["Location"] = f"/api/projects/{project.id}"
    return project


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(project_id: uuid.UUID, session: SessionDep) -> ProjectResponse:
    return await project_service.get_project(session, project_id)
