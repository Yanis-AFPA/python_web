from pydantic import BaseModel
from datetime import datetime
from typing import List, Optional
from app.schemas.patient import Patient

class EventFileBase(BaseModel):
    file_name: str
    content_type: Optional[str] = None

class EventFile(EventFileBase):
    id: int
    file_path: str
    
    class Config:
        from_attributes = True

class EventBase(BaseModel):
    title: str
    description: Optional[str] = None
    start_date: datetime
    end_date: datetime
    is_public: bool = False
    event_type: str = "consultation"
    patient_id: Optional[int] = None

class EventCreate(EventBase):
    pass

class Event(EventBase):
    id: int
    is_approved: bool # Read only
    files: List[EventFile] = []
    patient: Optional[Patient] = None

    class Config:
        from_attributes = True
