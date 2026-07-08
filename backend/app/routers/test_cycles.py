from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import schemas
from ..auth import get_current_user, require_manager
from ..database import get_db
from ..models import Project, TestCycle, User
from ..utils import write_audit

router = APIRouter(prefix="/test-cycles", tags=["test-cycles"])


def _get_or_404(db: Session, cycle_id: int) -> TestCycle:
    cycle = db.get(TestCycle, cycle_id)
    if cycle is None:
        raise HTTPException(status_code=404, detail="Test cycle not found")
    return cycle


@router.get("", response_model=list[schemas.TestCycleOut])
def list_test_cycles(
    project_id: int | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    query = select(TestCycle).order_by(TestCycle.created_at.desc())
    if project_id is not None:
        query = query.where(TestCycle.project_id == project_id)
    return db.scalars(query).all()


@router.post("", response_model=schemas.TestCycleOut, status_code=201)
def create_test_cycle(
    body: schemas.TestCycleCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_manager),
):
    if db.get(Project, body.project_id) is None:
        raise HTTPException(status_code=404, detail="Project not found")
    cycle = TestCycle(**body.model_dump())
    db.add(cycle)
    db.flush()
    write_audit(db, "test_cycle", cycle.id, "create", current_user.id, new_value=cycle.name)
    db.commit()
    db.refresh(cycle)
    return cycle


@router.get("/{cycle_id}", response_model=schemas.TestCycleOut)
def get_test_cycle(
    cycle_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)
):
    return _get_or_404(db, cycle_id)


@router.put("/{cycle_id}", response_model=schemas.TestCycleOut)
def update_test_cycle(
    cycle_id: int,
    body: schemas.TestCycleUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_manager),
):
    cycle = _get_or_404(db, cycle_id)
    for field, value in body.model_dump(exclude_unset=True).items():
        old = getattr(cycle, field)
        if old != value:
            write_audit(
                db, "test_cycle", cycle.id, "update", current_user.id, field, str(old), str(value)
            )
            setattr(cycle, field, value)
    db.commit()
    db.refresh(cycle)
    return cycle


@router.delete("/{cycle_id}", status_code=204)
def delete_test_cycle(
    cycle_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_manager),
):
    cycle = _get_or_404(db, cycle_id)
    write_audit(db, "test_cycle", cycle.id, "delete", current_user.id, old_value=cycle.name)
    db.delete(cycle)
    db.commit()
