from pydantic import BaseModel
from datetime import datetime
from typing import List, Optional

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

class EventCreate(EventBase):
    pass

class Event(EventBase):
    id: int
    is_approved: bool # Read only
    files: List[EventFile] = []

    class Config:
        from_attributes = True
