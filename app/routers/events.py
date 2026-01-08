from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_
from sqlalchemy.orm import selectinload
from typing import List, Optional
from datetime import datetime

from app.db.session import get_db
from app.models.event import Event as EventModel, EventFile as EventFileModel
from app.models.user import User, UserRole
from app.schemas.event import Event as EventSchema, EventCreate, EventUpdate
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
    doctor_name: Optional[str] = None,
    event_type: Optional[str] = None,
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
        
    # 2. Doctor (MANAGER): See ONLY their own events OR Meetings (Global)
    elif current_user.role == UserRole.MANAGER:
        query = query.where(
            or_(
                EventModel.owner_id == current_user.id,
                EventModel.event_type == "meeting"
            )
        )
    
    # --- Filters ---
    if event_type:
        query = query.where(EventModel.event_type == event_type)
        
    if doctor_name:
        # Case insensitive search on Doctor (Owner) First OR Last name
        query = query.join(EventModel.owner).where(
            or_(
                User.last_name.ilike(f"%{doctor_name}%"),
                User.first_name.ilike(f"%{doctor_name}%")
            )
        )

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
    title: Optional[str] = Form(None),
    start_date: datetime = Form(...),
    end_date: Optional[datetime] = Form(None),
    description: Optional[str] = Form(None),
    is_public: bool = Form(False),
    event_type: str = Form("consultation"),
    patient_id: Optional[int] = Form(None),
    owner_id: Optional[int] = Form(None), # Assign to Doctor
    file: Optional[UploadFile] = File(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    if not end_date:
        from datetime import timedelta
        end_date = start_date + timedelta(hours=1)
        
    # Default Title Generation
    if not title:
        # We need patient name for a good title
        patient_name = "Patient Inconnu"
        if patient_id:
            # We could fetch patient, but simpler to use generic "Consultation" and let frontend display handles proper naming
            # Actually, let's just save a generic Type title, because frontend dynamic display overrides it anyway?
            # Frontend currently uses: `${dName} - ${pName}` or just `${pName}`
            # But the 'title' field in DB is still used as fallback or main source.
            # Let's try to fetch patient name if possible, OR just use "Type"
            # To fetch patient effectively we need a query.
            # Let's just use the event_type as title for now, simple fallback.
            if event_type == "meeting":
                title = "Réunion"
            else:
                title = event_type.capitalize()
            
            if patient_id:
                 # Fetch patient to make it better?
                 # It's an async operation, cheaply doable.
                 p_res = await db.execute(select(PatientModel).where(PatientModel.id == patient_id))
                 p = p_res.scalar_one_or_none()
                 if p:
                     title = f"{title} - {p.first_name} {p.last_name}"

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
        
    # RBAC: Admin/Manager or Owner or Secretary can delete
    if current_user.role not in [UserRole.ADMIN, UserRole.MANAGER, UserRole.USER] and event.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not enough permissions")
        
    # Special Rule: Only Admin/SuperAdmin can delete 'meeting'
    if event.event_type == "meeting" and current_user.role not in [UserRole.ADMIN, UserRole.SUPER_ADMIN]:
         raise HTTPException(status_code=403, detail="Seuls les directeurs peuvent supprimer des réunions")

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

@router.put("/{event_id}", response_model=EventSchema)
async def update_event(
    event_id: int,
    event_in: EventUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(allow_any_authenticated)
):
    # Fetch existing
    result = await db.execute(select(EventModel).where(EventModel.id == event_id))
    db_event = result.scalar_one_or_none()
    
    if not db_event:
        raise HTTPException(status_code=404, detail="Event not found")

    # RBAC: Only Owner or Manager/Admin/Secretary can update
    if current_user.role not in [UserRole.ADMIN, UserRole.MANAGER, UserRole.USER] and db_event.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not enough permissions")

    # Special Rule: Only Admin/SuperAdmin can update 'meeting'
    if db_event.event_type == "meeting" and current_user.role not in [UserRole.ADMIN, UserRole.SUPER_ADMIN]:
         raise HTTPException(status_code=403, detail="Seuls les directeurs peuvent modifier des réunions")

    # Update fields
    update_data = event_in.model_dump(exclude_unset=True)
    
    # Conflict Check if dates changed
    if "start_date" in update_data or "end_date" in update_data:
        new_start = update_data.get("start_date", db_event.start_date)
        new_end = update_data.get("end_date", db_event.end_date)
        
        # FIX: Ensure dates are naive (remove timezone) to match DB
        if new_start.tzinfo is not None:
            new_start = new_start.replace(tzinfo=None)
        if new_end.tzinfo is not None:
            new_end = new_end.replace(tzinfo=None)

        # Update in dictionary for setattr later
        if "start_date" in update_data: update_data["start_date"] = new_start
        if "end_date" in update_data: update_data["end_date"] = new_end
        
        target_owner = update_data.get("owner_id", db_event.owner_id)
        
        if target_owner:
            conflict_query = select(EventModel).where(
                EventModel.owner_id == target_owner,
                EventModel.id != event_id, # Exclude self
                EventModel.start_date < new_end,
                EventModel.end_date > new_start
            )
            result = await db.execute(conflict_query)
            if result.scalars().first():
                 raise HTTPException(status_code=400, detail="Docteur indisponible sur ce créneau")

    for field, value in update_data.items():
        setattr(db_event, field, value)

    db.add(db_event)
    await db.commit()
    await db.refresh(db_event)
    
    # Eager load for response
    result = await db.execute(select(EventModel).options(
        selectinload(EventModel.files), 
        selectinload(EventModel.patient).selectinload(PatientModel.files),
        selectinload(EventModel.owner)
    ).where(EventModel.id == db_event.id))
    db_event = result.scalar_one()
    
    return db_event
