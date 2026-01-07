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

router = APIRouter()
file_service = LocalFileService()

@router.get("/", response_model=List[EventSchema])
async def read_events(
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    query = select(EventModel).options(selectinload(EventModel.files))
    
    # RBAC: Admin sees all, User sees own
    if current_user.role != UserRole.ADMIN:
        query = query.where(EventModel.owner_id == current_user.id)
    
    result = await db.execute(query.offset(skip).limit(limit))
    events = result.scalars().all()
    return events

@router.post("/", response_model=EventSchema)
async def create_event(
    title: str = Form(...),
    start_date: datetime = Form(...),
    end_date: datetime = Form(...),
    description: Optional[str] = Form(None),
    file: Optional[UploadFile] = File(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    event_data = EventCreate(title=title, start_date=start_date, end_date=end_date, description=description)
    
    db_event = EventModel(**event_data.model_dump())
    db_event.owner_id = current_user.id # Assign owner
    
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
    current_user: User = Depends(get_current_active_user)
):
    result = await db.execute(select(EventModel).where(EventModel.id == event_id))
    event = result.scalar_one_or_none()
    
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
        
    # RBAC: Admin or Owner can delete
    if current_user.role != UserRole.ADMIN and event.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not enough permissions")
        
    await db.delete(event)
    await db.commit()
    return None
