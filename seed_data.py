import asyncio
import os
import sys

# Add app to path
sys.path.append(os.getcwd())

from app.db.session import AsyncSessionLocal
from app.models.user import User, UserRole
from app.models.patient import Patient, PatientFile
from app.models.event import Event, EventFile
from app.core.security import get_password_hash
from sqlalchemy import select, delete

async def seed_data():
    print("Seeding initial data...")
    async with AsyncSessionLocal() as db:
        
        # 1. Clear existing data (in correct order due to FKs)
        print("Cleaning database...")
        # Delete children first
        await db.execute(delete(EventFile))
        await db.execute(delete(PatientFile))
        
        # Delete parents
        await db.execute(delete(Event))
        await db.execute(delete(Patient))
        await db.execute(delete(User))
        
        await db.commit()
        
        print("Creating users...")
        # 2. PROVISIONING
        
        # Super Admin
        admin = User(
            email="admin@example.com",
            hashed_password=get_password_hash("admin"),
            first_name="Admin",
            last_name="System",
            role=UserRole.SUPER_ADMIN,
            is_active=True
        )
        db.add(admin)
        
        # Doctor (Manager)
        doctor = User(
            email="doctor@example.com",
            hashed_password=get_password_hash("doc"),
            first_name="Dr. House",
            last_name="Gregory",
            role=UserRole.MANAGER,
            specialty="Diagnostic",
            is_active=True
        )
        db.add(doctor)
        
        # Secretary (User)
        secretary = User(
            email="secretary@example.com",
            hashed_password=get_password_hash("sec"),
            first_name="Sophie",
            last_name="Martin",
            role=UserRole.USER,
            is_active=True
        )
        db.add(secretary)
        
        # 3. PATIENTS
        print("Creating patients...")
        patients = [
            Patient(first_name="Thomas", last_name="Anderson", phone="0601010101", email="neo@matrix.com", address="Matrix", medical_history="Bullet wound"),
            Patient(first_name="Sarah", last_name="Connor", phone="0602020202", email="sarah@skynet.com", address="Los Angeles", medical_history="Trauma"),
            Patient(first_name="Ellen", last_name="Ripley", phone="0603030303", email="ellen@nostromo.com", address="Space", medical_history="Alien infection")
        ]
        
        for p in patients:
            db.add(p)
            
        await db.commit()
        print("Database initialized successfully!")
        print("Users created:")
        print("- Admin: admin@example.com / admin")
        print("- Doctor: doctor@example.com / doc")
        print("- Secretary: secretary@example.com / sec")

if __name__ == "__main__":
    asyncio.run(seed_data())
