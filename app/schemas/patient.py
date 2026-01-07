from pydantic import BaseModel, EmailStr
from typing import Optional, List
from datetime import date
import datetime

class PatientBase(BaseModel):
    first_name: str
    last_name: str
    dob: Optional[date] = None
    phone: Optional[str] = None
    email: Optional[EmailStr] = None
    address: Optional[str] = None
    medical_history: Optional[str] = None

class PatientCreate(PatientBase):
    pass

class PatientUpdate(PatientBase):
    first_name: Optional[str] = None
    last_name: Optional[str] = None

class PatientFile(BaseModel):
    id: int
    file_name: str
    file_path: str
    uploaded_at: datetime.datetime

    class Config:
        from_attributes = True

class Patient(PatientBase):
    id: int
    files: List[PatientFile] = []

    class Config:
        from_attributes = True
