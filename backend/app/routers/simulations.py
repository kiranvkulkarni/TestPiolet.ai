from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import schemas, simulator
from ..auth import get_current_user
from ..database import get_db
from ..models import User

router = APIRouter(prefix="/simulations", tags=["simulations"])


@router.post("")
def run_simulation(
    body: schemas.SimulationRequest,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Non-destructive what-if over the current plan (mirrors the agent's
    run_simulation tool — same code path). Read-only: nothing is written."""
    result = simulator.run_simulation(
        db, project_id=body.project_id, perturbations=body.perturbations
    )
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result
