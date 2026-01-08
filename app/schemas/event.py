from pydantic import BaseModel
from datetime import datetime
from typing import List, Optional
from app.schemas.patient import Patient
from app.schemas.user import UserBase # Basic user info

class EventFileBase(BaseModel):
    file_name: str
    content_type: Optional[str] = None

class EventFile(EventFileBase):
    id: int
    file_path: str
    
    class Config:
        from_attributes = True

class EventBase(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    start_date: datetime
    end_date: datetime
    is_public: bool = False
    event_type: str = "consultation"
    patient_id: Optional[int] = None

class EventCreate(EventBase):
    end_date: Optional[datetime] = None

class EventUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    is_public: Optional[bool] = None
    event_type: Optional[str] = None
    patient_id: Optional[int] = None
    owner_id: Optional[int] = None

class Event(EventBase):
    id: int
    is_approved: bool # Read only
    files: List[EventFile] = []
    patient: Optional[Patient] = None
    owner: Optional[UserBase] = None

    class Config:
        from_attributes = True
