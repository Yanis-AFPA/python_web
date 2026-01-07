from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_
from sqlalchemy.orm import selectinload
from typing import List, Optional
from datetime import datetime

from app.db.session import get_db
from app.models.event import Event as EventModel, EventFile as EventFileModel
from app.models.user import User, UserRole
from app.schemas.event import Event as EventSchema, EventCreate
from app.services.file_service import LocalFileService
from app.core.deps import get_current_active_user
from app.core.rbac import RoleChecker
from app.models.user import UserRole

router = APIRouter()
file_service = LocalFileService()

# Dependency instances
allow_any_authenticated = RoleChecker([UserRole.SUPER_ADMIN, UserRole.ADMIN, UserRole.MANAGER, UserRole.USER])
allow_manager_admin = RoleChecker([UserRole.SUPER_ADMIN, UserRole.ADMIN, UserRole.MANAGER])
allow_admin = RoleChecker([UserRole.SUPER_ADMIN, UserRole.ADMIN])

@router.get("/", response_model=List[EventSchema])
async def read_events(
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(allow_any_authenticated)
):
    query = select(EventModel).options(selectinload(EventModel.files))
    
    # RBAC & Public Logic
    # 1. Base: Everyone sees their own events
    query = query.where(
        or_(
            EventModel.owner_id == current_user.id,
            # 2. Plus Public Events logic
            # Admin/Manager/SuperAdmin: See ALL Public (Pending or Approved)
            # User: See only Approved Public
            (
                (EventModel.is_public == True) & 
                (
                    (EventModel.is_approved == True) if current_user.role not in [UserRole.ADMIN, UserRole.MANAGER, UserRole.SUPER_ADMIN] else True
                )
            )
        )
    )
    
    result = await db.execute(query.offset(skip).limit(limit))
    events = result.scalars().all()
    return events

@router.post("/", response_model=EventSchema)
async def create_event(
    title: str = Form(...),
    start_date: datetime = Form(...),
    end_date: datetime = Form(...),
    description: Optional[str] = Form(None),
    is_public: bool = Form(False),
    file: Optional[UploadFile] = File(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    event_data = EventCreate(title=title, start_date=start_date, end_date=end_date, description=description, is_public=is_public)
    
    db_event = EventModel(**event_data.model_dump())
    db_event.owner_id = current_user.id # Assign owner
    
    # Auto-approve if Manager/Admin, else Pending for Users
    if is_public:
        if current_user.role in [UserRole.ADMIN, UserRole.MANAGER, UserRole.SUPER_ADMIN]:
            db_event.is_approved = True
        else:
            db_event.is_approved = False # Pending Approval
    else:
        db_event.is_approved = True # Private events are always "approved" (or irrelevant)
    
    db.add(db_event)
    await db.commit()
    await db.refresh(db_event)
    
    if file:
        file_path = await file_service.save_file(file)
        db_file = EventFileModel(
            event_id=db_event.id,
            file_path=file_path,
            file_name=file.filename,
            content_type=file.content_type
        )
        db.add(db_file)
        await db.commit()
        
        # Re-fetch with files
        result = await db.execute(select(EventModel).options(selectinload(EventModel.files)).where(EventModel.id == db_event.id))
        db_event = result.scalar_one()

    return db_event

@router.delete("/{event_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_event(
    event_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(allow_any_authenticated)
):
    result = await db.execute(select(EventModel).where(EventModel.id == event_id))
    event = result.scalar_one_or_none()
    
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
        
    # RBAC: Admin/Manager or Owner can delete
    if current_user.role not in [UserRole.ADMIN, UserRole.MANAGER] and event.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not enough permissions")
        
    await db.delete(event)
    await db.commit()
    return None

@router.put("/{event_id}/approve", response_model=EventSchema)
async def approve_event(
    event_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(allow_manager_admin)
):
    result = await db.execute(select(EventModel).where(EventModel.id == event_id))
    event = result.scalar_one_or_none()
    
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
        
    event.is_approved = True
    db.add(event)
    await db.commit()
    await db.refresh(event)
    return event
