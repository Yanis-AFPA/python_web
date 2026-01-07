from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List

from app.db.session import get_db
from app.models.patient import Patient as PatientModel, PatientFile as PatientFileModel
from app.schemas.patient import Patient, PatientCreate, PatientUpdate
from app.models.user import User, UserRole
from app.core.rbac import RoleChecker
from fastapi import UploadFile, File
from app.services.file_service import LocalFileService

router = APIRouter()
file_service = LocalFileService()

# RBAC:
# - Reading (List/Get): Authenticated (Secretary, Doctor, Admin)
# - Creating/Updating: Secretary, Doctor, Admin
# - Deleting: Admin only

allow_all_staff = RoleChecker([UserRole.SUPER_ADMIN, UserRole.ADMIN, UserRole.MANAGER, UserRole.USER])
allow_write_access = RoleChecker([UserRole.SUPER_ADMIN, UserRole.ADMIN, UserRole.MANAGER, UserRole.USER]) # Secretaries (User) can create patients
allow_admin = RoleChecker([UserRole.SUPER_ADMIN, UserRole.ADMIN])

@router.get("/", response_model=List[Patient])
async def read_patients(
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(allow_all_staff)
):
    from sqlalchemy.orm import selectinload
    result = await db.execute(select(PatientModel).options(selectinload(PatientModel.files)).offset(skip).limit(limit))
    patients = result.scalars().all()
    
    # Mask medical history for Secretaries
    # Mask medical history and files for Secretaries
    if current_user.role == UserRole.USER:
        for p in patients:
            p.medical_history = None
            p.files = []
            
    return patients

@router.post("/", response_model=Patient)
async def create_patient(
    patient: PatientCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(allow_write_access)
):
    db_patient = PatientModel(**patient.model_dump())
    db.add(db_patient)
    await db.commit()
    await db.refresh(db_patient)
    
    # Re-fetch with eager loading to avoid MissingGreenlet
    from sqlalchemy.orm import selectinload
    result = await db.execute(select(PatientModel).options(selectinload(PatientModel.files)).where(PatientModel.id == db_patient.id))
    patient = result.scalar_one()
    
    return patient

@router.get("/{patient_id}", response_model=Patient)
async def read_patient(
    patient_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(allow_all_staff)
):
    from sqlalchemy.orm import selectinload
    result = await db.execute(select(PatientModel).options(selectinload(PatientModel.files)).where(PatientModel.id == patient_id))
    patient = result.scalar_one_or_none()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
        
    # Medical Privacy: Secretary (USER) cannot see medical history
    if current_user.role == UserRole.USER:
        patient.medical_history = None
        
    return patient

@router.put("/{patient_id}", response_model=Patient)
async def update_patient(
    patient_id: int,
    patient_update: PatientUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(allow_write_access)
):
    result = await db.execute(select(PatientModel).where(PatientModel.id == patient_id))
    patient = result.scalar_one_or_none()
    
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    
    update_data = patient_update.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(patient, key, value)
        
    db.add(patient)
    await db.commit()
    await db.refresh(patient)
    
    # Re-fetch with eager loading
    from sqlalchemy.orm import selectinload
    result = await db.execute(select(PatientModel).options(selectinload(PatientModel.files)).where(PatientModel.id == patient.id))
    patient = result.scalar_one()
    
    return patient

@router.delete("/{patient_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_patient(
    patient_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(allow_admin)
):
    result = await db.execute(select(PatientModel).where(PatientModel.id == patient_id))
    patient = result.scalar_one_or_none()
    
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
        
    await db.delete(patient)
    await db.commit()
    return None

@router.post("/{patient_id}/files", response_model=Patient)
async def upload_patient_file(
    patient_id: int,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(allow_write_access) # Secretaries can upload
):
    result = await db.execute(select(PatientModel).where(PatientModel.id == patient_id))
    patient = result.scalar_one_or_none()
    
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    file_path = await file_service.save_file(file)
    
    db_file = PatientFileModel(
        patient_id=patient.id,
        file_path=file_path,
        file_name=file.filename,
        content_type=file.content_type
    )
    db.add(db_file)
    await db.commit()
    
    # Refresh patient with files
    # We might need to handle eager loading if not lazy
    await db.refresh(patient) # This might not load files depending on config
    
    # Robust re-fetch with files
    from sqlalchemy.orm import selectinload
    result = await db.execute(select(PatientModel).options(selectinload(PatientModel.files)).where(PatientModel.id == patient_id))
    patient = result.scalar_one()
    
    # Hide medical history for Secretary if needed (Reuse read logic)
    if current_user.role == UserRole.USER:
        patient.medical_history = None
        
    return patient
