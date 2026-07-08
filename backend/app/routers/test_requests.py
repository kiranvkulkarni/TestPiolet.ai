from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from .. import schemas
from ..auth import get_current_user, require_not_viewer
from ..database import get_db
from ..models import Project, Task, TestRequest, User
from ..utils import write_audit

router = APIRouter(prefix="/test-requests", tags=["test-requests"])


def _get_or_404(db: Session, request_id: int) -> TestRequest:
    req = db.get(TestRequest, request_id)
    if req is None:
        raise HTTPException(status_code=404, detail="Test request not found")
    return req


def _with_task_count(db: Session, req: TestRequest) -> schemas.TestRequestOut:
    out = schemas.TestRequestOut.model_validate(req)
    out.task_count = db.scalar(
        select(func.count(Task.id)).where(Task.test_request_id == req.id)
    ) or 0
    return out


@router.get("", response_model=list[schemas.TestRequestOut])
def list_test_requests(
    project_id: int | None = None,
    status: str | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    query = select(TestRequest).order_by(TestRequest.created_at.desc())
    if project_id is not None:
        query = query.where(TestRequest.project_id == project_id)
    if status:
        query = query.where(TestRequest.status == status)
    requests = db.scalars(query).all()
    counts = dict(
        db.execute(select(Task.test_request_id, func.count(Task.id)).group_by(Task.test_request_id)).all()
    )
    out = []
    for r in requests:
        item = schemas.TestRequestOut.model_validate(r)
        item.task_count = counts.get(r.id, 0)
        out.append(item)
    return out


@router.post("", response_model=schemas.TestRequestOut, status_code=201)
def create_test_request(
    body: schemas.TestRequestCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_not_viewer),
):
    if db.get(Project, body.project_id) is None:
        raise HTTPException(status_code=404, detail="Project not found")
    req = TestRequest(**body.model_dump())
    db.add(req)
    db.flush()
    write_audit(db, "test_request", req.id, "create", current_user.id, new_value=req.title)
    db.commit()
    db.refresh(req)
    return _with_task_count(db, req)


@router.get("/{request_id}", response_model=schemas.TestRequestOut)
def get_test_request(
    request_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)
):
    return _with_task_count(db, _get_or_404(db, request_id))


@router.put("/{request_id}", response_model=schemas.TestRequestOut)
def update_test_request(
    request_id: int,
    body: schemas.TestRequestUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_not_viewer),
):
    req = _get_or_404(db, request_id)
    for field, value in body.model_dump(exclude_unset=True).items():
        old = getattr(req, field)
        if old != value:
            write_audit(
                db, "test_request", req.id, "update", current_user.id, field, str(old), str(value)
            )
            setattr(req, field, value)
    db.commit()
    db.refresh(req)
    return _with_task_count(db, req)


@router.delete("/{request_id}", status_code=204)
def delete_test_request(
    request_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_not_viewer),
):
    req = _get_or_404(db, request_id)
    write_audit(db, "test_request", req.id, "delete", current_user.id, old_value=req.title)
    db.delete(req)
    db.commit()


@router.get("/{request_id}/tasks", response_model=list[schemas.TaskOut])
def request_tasks(
    request_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)
):
    _get_or_404(db, request_id)
    return db.scalars(
        select(Task)
        .where(Task.test_request_id == request_id)
        .options(selectinload(Task.assignee), selectinload(Task.device_model))
        .order_by(Task.created_at.desc())
    ).all()
