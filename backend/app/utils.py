"""Small cross-cutting helpers shared by routers and agent tools."""

from sqlalchemy.orm import Session

from .models import AuditLog, Notification


def write_audit(
    db: Session,
    entity_type: str,
    entity_id: int,
    action: str,
    user_id: int | None = None,
    field_changed: str | None = None,
    old_value: str | None = None,
    new_value: str | None = None,
) -> None:
    """Add an AuditLog row to the session (caller commits)."""
    db.add(
        AuditLog(
            entity_type=entity_type,
            entity_id=entity_id,
            action=action,
            field_changed=field_changed,
            old_value=old_value,
            new_value=new_value,
            user_id=user_id,
        )
    )


def create_notification(
    db: Session,
    user_id: int,
    type: str,
    message: str,
    entity_type: str | None = None,
    entity_id: int | None = None,
) -> Notification:
    """Add a Notification row to the session (caller commits)."""
    notif = Notification(
        user_id=user_id,
        type=type,
        message=message,
        entity_type=entity_type,
        entity_id=entity_id,
    )
    db.add(notif)
    return notif
