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
from app.models.patient import Patient as PatientModel

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
    # from app.models.patient import Patient as PatientModel # Moved global
    query = select(EventModel).options(
        selectinload(EventModel.files), 
        selectinload(EventModel.patient).selectinload(PatientModel.files),
        selectinload(EventModel.owner)
    )
    
    # RBAC Visibility Logic
    # 1. Secretary (USER) & Admin (ADMIN/SUPER_ADMIN): See ALL events (Global Calendar)
    if current_user.role in [UserRole.USER, UserRole.ADMIN, UserRole.SUPER_ADMIN]:
        pass # No filter, see all
        
    # 2. Doctor (MANAGER): See ONLY their own events (assigned to them)
    elif current_user.role == UserRole.MANAGER:
        query = query.where(EventModel.owner_id == current_user.id)
    
    result = await db.execute(query.offset(skip).limit(limit))
    events = result.scalars().all()
    
    # Files Privacy: Secretary (USER) cannot see attached files
    if current_user.role == UserRole.USER:
        for event in events:
            # We must be careful not to trigger a DB write if we were modifying a scalar, 
            # but 'files' is a relationship list. Modifying the list on the ORM object 
            # *might* be tracked. However, we are just returning Pydantic models usually?
            # FastAPI converts ORM to Pydantic. 
            # To be safe and avoid side effects on the session, we can just rely on the response model 
            # filtering if we could, but Pydantic doesn't know the user role.
            # We will manually set it to empty list.
            event.files = []
            if event.patient:
                event.patient.files = []
                event.patient.medical_history = None # Also mask history if exposing patient object here
            
    return events

@router.post("/", response_model=EventSchema)
async def create_event(
    title: str = Form(...),
    start_date: datetime = Form(...),
    end_date: datetime = Form(...),
    description: Optional[str] = Form(None),
    is_public: bool = Form(False),
    event_type: str = Form("consultation"),
    patient_id: Optional[int] = Form(None),
    owner_id: Optional[int] = Form(None), # Assign to Doctor
    file: Optional[UploadFile] = File(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    event_data = EventCreate(
        title=title, 
        start_date=start_date, 
        end_date=end_date, 
        description=description, 
        is_public=is_public,
        event_type=event_type,
        patient_id=patient_id
    )
    
    db_event = EventModel(**event_data.model_dump())
    
    # Assign Owner logic
    # If user is Admin or Secretary (User Role), they can assign to a doctor (owner_id)
    # If not provided, or if user is Doctor, it's their own event
    if owner_id and current_user.role in [UserRole.ADMIN, UserRole.SUPER_ADMIN, UserRole.USER]:
         db_event.owner_id = owner_id
    else:
         db_event.owner_id = current_user.id

    # Auto-approve logic
    # If assigned to specific doctor, typically it's "approved" / valid immediately if created by staff
    # We can simplify: All internal events are approved. Public logic is only for external/patient portal (future)
    # But sticking to current logic: 
    # If Secretary creates for Doctor -> Approved
    if current_user.role in [UserRole.ADMIN, UserRole.MANAGER, UserRole.SUPER_ADMIN, UserRole.USER]:
         db_event.is_approved = True
    else:
         # External / Patient (not implemented yet)
         db_event.is_approved = False
    
    # Conflict Detection: Prevent Doctor overlap
    # If explicitly assigned (or auto-assigned to self), check conflicts for that owner_id
    if db_event.owner_id:
        # Check overlapping events for this doctor
        # New Start < Existing End AND New End > Existing Start
        conflict_query = select(EventModel).where(
            EventModel.owner_id == db_event.owner_id,
            EventModel.start_date < end_date,
            EventModel.end_date > start_date
        )
        result = await db.execute(conflict_query)
        if result.scalars().first():
             raise HTTPException(status_code=400, detail="Docteur indisponible sur ce créneau (chevauchement)")

    db.add(db_event)
    await db.commit()
    await db.refresh(db_event)
    
    
    if file and file.filename:
        # RBAC: Secretary (USER) cannot upload medical files
        if current_user.role == UserRole.USER:
            raise HTTPException(status_code=403, detail="Secretaries cannot upload medical files")
            
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
        result = await db.execute(select(EventModel).options(
            selectinload(EventModel.files), 
            selectinload(EventModel.patient).selectinload(PatientModel.files)
        ).where(EventModel.id == db_event.id))
        db_event = result.scalar_one()

    else:
        # If no file was uploaded, we still need to load relationships for the schema (Patient, Files=[])
        result = await db.execute(select(EventModel).options(
            selectinload(EventModel.files), 
            selectinload(EventModel.patient).selectinload(PatientModel.files)
        ).where(EventModel.id == db_event.id))
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
    
    # Eager load for schema
    result = await db.execute(select(EventModel).options(
        selectinload(EventModel.files), 
        selectinload(EventModel.patient).selectinload(PatientModel.files)
    ).where(EventModel.id == event.id))
    event = result.scalar_one()
    
    return event
