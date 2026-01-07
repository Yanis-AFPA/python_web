from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from datetime import datetime, date

from app.db.session import get_db
from app.models.patient import Patient
from app.models.event import Event
from app.models.user import User, UserRole
from app.core.rbac import RoleChecker

router = APIRouter()

allow_staff = RoleChecker([UserRole.SUPER_ADMIN, UserRole.ADMIN, UserRole.MANAGER, UserRole.USER])

@router.get("/stats")
async def get_dashboard_stats(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(allow_staff)
):
    # Base queries
    q_patients = select(func.count(Patient.id))
    
    today = date.today()
    start_of_day = datetime.combine(today, datetime.min.time())
    end_of_day = datetime.combine(today, datetime.max.time())
    
    q_today = select(func.count(Event.id)).where(
        and_(
            Event.start_date >= start_of_day,
            Event.start_date <= end_of_day
        )
    )

    q_pending = select(func.count(Event.id)).where(
        and_(
            Event.is_public == True,
            Event.is_approved == False
        )
    )

    # Scoping for Doctor (MANAGER)
    if current_user.role == UserRole.MANAGER:
        # Doctor sees count of ALL patients (shared db) or only theirs? 
        # Typically doctors share the patient base in a clinic. Let's keep patients global.
        # But Appointments Today -> Only theirs
        q_today = q_today.where(Event.owner_id == current_user.id)
        
        # Pending approvals -> Not relevant if we removed public logic, 
        # but if we keep it, maybe only assigned to them? Let's hide or keep 0
        q_pending = q_pending.where(Event.owner_id == current_user.id)

    # Execute
    total_patients = (await db.execute(q_patients)).scalar()
    appointments_today = (await db.execute(q_today)).scalar()
    pending_approvals = (await db.execute(q_pending)).scalar()

    return {
        "total_patients": total_patients,
        "appointments_today": appointments_today,
        "pending_approvals": pending_approvals
    }
