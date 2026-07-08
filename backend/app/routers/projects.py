from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import schemas
from ..auth import get_current_user, require_manager
from ..database import get_db
from ..models import Project, Task, TestRequest, User
from ..utils import write_audit

router = APIRouter(prefix="/projects", tags=["projects"])


def _get_or_404(db: Session, project_id: int) -> Project:
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.get("", response_model=list[schemas.ProjectOut])
def list_projects(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return db.scalars(select(Project).order_by(Project.created_at.desc())).all()


@router.post("", response_model=schemas.ProjectOut, status_code=201)
def create_project(
    body: schemas.ProjectCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_manager),
):
    project = Project(**body.model_dump())
    db.add(project)
    db.flush()
    write_audit(db, "project", project.id, "create", current_user.id, new_value=project.name)
    db.commit()
    db.refresh(project)
    return project


@router.get("/{project_id}", response_model=schemas.ProjectOut)
def get_project(
    project_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)
):
    return _get_or_404(db, project_id)


@router.put("/{project_id}", response_model=schemas.ProjectOut)
def update_project(
    project_id: int,
    body: schemas.ProjectUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_manager),
):
    project = _get_or_404(db, project_id)
    for field, value in body.model_dump(exclude_unset=True).items():
        old = getattr(project, field)
        if old != value:
            write_audit(
                db, "project", project.id, "update", current_user.id, field, str(old), str(value)
            )
            setattr(project, field, value)
    db.commit()
    db.refresh(project)
    return project


@router.delete("/{project_id}", status_code=204)
def delete_project(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_manager),
):
    project = _get_or_404(db, project_id)
    write_audit(db, "project", project.id, "delete", current_user.id, old_value=project.name)
    db.delete(project)
    db.commit()


@router.get("/{project_id}/test-requests", response_model=list[schemas.TestRequestOut])
def project_test_requests(
    project_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)
):
    _get_or_404(db, project_id)
    requests = db.scalars(
        select(TestRequest)
        .where(TestRequest.project_id == project_id)
        .order_by(TestRequest.created_at.desc())
    ).all()
    counts = dict(
        db.execute(
            select(Task.test_request_id, func.count(Task.id))
            .join(TestRequest, Task.test_request_id == TestRequest.id)
            .where(TestRequest.project_id == project_id)
            .group_by(Task.test_request_id)
        ).all()
    )
    out = []
    for r in requests:
        item = schemas.TestRequestOut.model_validate(r)
        item.task_count = counts.get(r.id, 0)
        out.append(item)
    return out
