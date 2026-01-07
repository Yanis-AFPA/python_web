from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey, Boolean
from sqlalchemy.orm import relationship
from app.db.base_class import Base
from app.models.user import User

class Event(Base):
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, index=True, nullable=False)
    description = Column(Text, nullable=True)
    start_date = Column(DateTime, nullable=False)
    end_date = Column(DateTime, nullable=False)
    is_public = Column(Boolean, default=False)
    is_approved = Column(Boolean, default=False)
    

    owner_id = Column(Integer, ForeignKey("user.id"), nullable=True) # Nullable for migration/existing data for now
    owner = relationship("User", back_populates="events")
    
    files = relationship("EventFile", back_populates="event", cascade="all, delete-orphan")

class EventFile(Base):
    id = Column(Integer, primary_key=True, index=True)
    event_id = Column(Integer, ForeignKey("event.id"), nullable=False)
    file_path = Column(String, nullable=False)
    file_name = Column(String, nullable=False) # Original filename
    content_type = Column(String, nullable=True)
    
    event = relationship("Event", back_populates="files")
