import os
import uuid

import aiofiles
from fastapi import APIRouter, Depends, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import schemas
from ..auth import get_current_user, require_not_viewer
from ..config import settings
from ..database import get_db
from ..models import Attachment, Task, User
from ..utils import write_audit

router = APIRouter(prefix="/tasks/{task_id}/attachments", tags=["attachments"])


def _task_or_404(db: Session, task_id: int) -> Task:
    task = db.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@router.get("", response_model=list[schemas.AttachmentOut])
def list_attachments(
    task_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)
):
    _task_or_404(db, task_id)
    return db.scalars(
        select(Attachment).where(Attachment.task_id == task_id).order_by(Attachment.created_at)
    ).all()


@router.post("", response_model=schemas.AttachmentOut, status_code=201)
async def upload_attachment(
    task_id: int,
    file: UploadFile,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_not_viewer),
):
    _task_or_404(db, task_id)
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    ext = os.path.splitext(file.filename or "")[1]
    stored_name = f"{uuid.uuid4().hex}{ext}"
    path = os.path.join(settings.UPLOAD_DIR, stored_name)

    max_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
    size = 0
    async with aiofiles.open(path, "wb") as out:
        while chunk := await file.read(1024 * 1024):
            size += len(chunk)
            if size > max_bytes:
                await out.close()
                os.remove(path)
                raise HTTPException(
                    status_code=413,
                    detail=f"File exceeds {settings.MAX_UPLOAD_SIZE_MB} MB limit",
                )
            await out.write(chunk)

    attachment = Attachment(
        task_id=task_id,
        filename=stored_name,
        original_filename=file.filename or stored_name,
        file_size=size,
        mime_type=file.content_type,
        uploaded_by=current_user.id,
    )
    db.add(attachment)
    db.flush()
    write_audit(
        db, "attachment", attachment.id, "create", current_user.id,
        new_value=attachment.original_filename,
    )
    db.commit()
    db.refresh(attachment)
    return attachment


@router.get("/{att_id}/download")
def download_attachment(
    task_id: int,
    att_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    attachment = db.get(Attachment, att_id)
    if attachment is None or attachment.task_id != task_id:
        raise HTTPException(status_code=404, detail="Attachment not found")
    path = os.path.join(settings.UPLOAD_DIR, attachment.filename)
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="File missing on server")
    return FileResponse(
        path,
        filename=attachment.original_filename,
        media_type=attachment.mime_type or "application/octet-stream",
    )


@router.delete("/{att_id}", status_code=204)
def delete_attachment(
    task_id: int,
    att_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_not_viewer),
):
    attachment = db.get(Attachment, att_id)
    if attachment is None or attachment.task_id != task_id:
        raise HTTPException(status_code=404, detail="Attachment not found")
    path = os.path.join(settings.UPLOAD_DIR, attachment.filename)
    if os.path.isfile(path):
        os.remove(path)
    write_audit(
        db, "attachment", attachment.id, "delete", current_user.id,
        old_value=attachment.original_filename,
    )
    db.delete(attachment)
    db.commit()
