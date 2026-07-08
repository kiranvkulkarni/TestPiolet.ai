from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from .. import schemas
from ..auth import get_current_user, require_not_viewer
from ..database import get_db
from ..models import Comment, Task, User
from ..utils import create_notification, write_audit

router = APIRouter(prefix="/tasks/{task_id}/comments", tags=["comments"])


def _task_or_404(db: Session, task_id: int) -> Task:
    task = db.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@router.get("", response_model=list[schemas.CommentOut])
def list_comments(
    task_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)
):
    _task_or_404(db, task_id)
    return db.scalars(
        select(Comment)
        .options(selectinload(Comment.user))
        .where(Comment.task_id == task_id)
        .order_by(Comment.created_at)
    ).all()


@router.post("", response_model=schemas.CommentOut, status_code=201)
def create_comment(
    task_id: int,
    body: schemas.CommentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_not_viewer),
):
    task = _task_or_404(db, task_id)
    comment = Comment(task_id=task_id, user_id=current_user.id, content=body.content)
    db.add(comment)
    db.flush()
    write_audit(db, "comment", comment.id, "create", current_user.id)
    if task.assigned_to and task.assigned_to != current_user.id:
        create_notification(
            db, task.assigned_to, "comment",
            f'{current_user.name} commented on "{task.title}"', "task", task.id,
        )
    db.commit()
    db.refresh(comment)
    return comment


@router.put("/{comment_id}", response_model=schemas.CommentOut)
def update_comment(
    task_id: int,
    comment_id: int,
    body: schemas.CommentUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_not_viewer),
):
    comment = db.get(Comment, comment_id)
    if comment is None or comment.task_id != task_id:
        raise HTTPException(status_code=404, detail="Comment not found")
    if comment.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Can only edit your own comments")
    write_audit(db, "comment", comment.id, "update", current_user.id, "content")
    comment.content = body.content
    db.commit()
    db.refresh(comment)
    return comment


@router.delete("/{comment_id}", status_code=204)
def delete_comment(
    task_id: int,
    comment_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_not_viewer),
):
    comment = db.get(Comment, comment_id)
    if comment is None or comment.task_id != task_id:
        raise HTTPException(status_code=404, detail="Comment not found")
    if comment.user_id != current_user.id and current_user.role.value != "manager":
        raise HTTPException(status_code=403, detail="Cannot delete this comment")
    write_audit(db, "comment", comment.id, "delete", current_user.id)
    db.delete(comment)
    db.commit()
