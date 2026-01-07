import asyncio
import os
import sys

# Add app to path
sys.path.append(os.getcwd())

from app.db.session import AsyncSessionLocal
from app.models.patient import Patient
from app.models.event import Event # Fix relationship loading
from app.db.base_class import Base

async def seed_patients():
    print("Seeding patients...")
    async with AsyncSessionLocal() as db:
        patients = [
            Patient(first_name="Jean", last_name="Dupont", phone="0601020304", email="jean.dupont@example.com", address="1 Rue de la Paix", medical_history="Hypertension"),
            Patient(first_name="Marie", last_name="Curie", phone="0600000000", email="marie.curie@example.com", address="Labo 1", medical_history="Radiation exposure"),
            Patient(first_name="Pierre", last_name="Martin", phone="0611223344", email="pierre.martin@example.com", address="5 Avenue Victor Hugo", medical_history="None"),
            Patient(first_name="Sophie", last_name="Lemoine", phone="0699887766", email="sophie.lemoine@example.com", address="10 Blvd Saint-Michel", medical_history="Allergy to Penicillin"),
            Patient(first_name="Lucas", last_name="Bernard", phone="0655443322", email="lucas.bernard@example.com", address="Lyon", medical_history="Asthma")
        ]
        
        for p in patients:
            # Check exist ?
            # Just add, collision unlikely on seed
            db.add(p)
        
        await db.commit()
    print("Patients seeded!")

if __name__ == "__main__":
    asyncio.run(seed_patients())
