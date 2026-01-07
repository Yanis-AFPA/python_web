from sqlalchemy import Column, Integer, String, Date, Text, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from datetime import datetime
from app.db.base_class import Base

class Patient(Base):
    id = Column(Integer, primary_key=True, index=True)
    first_name = Column(String, index=True, nullable=False)
    last_name = Column(String, index=True, nullable=False)
    dob = Column(Date, nullable=True) # Date of Birth
    phone = Column(String, nullable=True)
    email = Column(String, nullable=True)
    address = Column(String, nullable=True)
    
    # Medical Info (Restricted access typically, but we'll use RBAC logic in routes)
    medical_history = Column(Text, nullable=True)
    
    # Relationships
    events = relationship("Event", back_populates="patient")
    files = relationship("PatientFile", back_populates="patient", cascade="all, delete-orphan")

class PatientFile(Base):
    id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(Integer, ForeignKey("patient.id"), nullable=False)
    file_path = Column(String, nullable=False)
    file_name = Column(String, nullable=False)
    content_type = Column(String, nullable=False)
    uploaded_at = Column(DateTime, default=datetime.utcnow)
    
    patient = relationship("Patient", back_populates="files")
