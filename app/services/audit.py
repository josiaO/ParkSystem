from sqlalchemy.orm import Session
from app.models import AuditLog, User


def write_audit(db: Session, user: User | None, action: str, target_type: str = "", target_id: str = "", detail: str = ""):
    db.add(AuditLog(
        user_id=user.id if user else None,
        action=action,
        target_type=target_type,
        target_id=target_id,
        detail=detail,
    ))
    db.commit()
