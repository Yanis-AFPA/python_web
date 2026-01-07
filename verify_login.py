import asyncio
import os
import sys

sys.path.append(os.getcwd())

from app.db.session import AsyncSessionLocal
from app.models.user import User
from app.models.event import Event # Fix relationship loading
from app.core.security import verify_password
from sqlalchemy import select

async def verify_login():
    email = "admin@example.com"
    passwords = ["admin", "P@ssw0rd"]
    
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()
        
        if not user:
            print(f"User {email} NOT FOUND!")
            return
            
        print(f"User {email} found. Role: {user.role}, Active: {user.is_active}")
        print(f"Hash in DB: {user.hashed_password}")
        
        for pwd in passwords:
            is_valid = verify_password(pwd, user.hashed_password)
            print(f"Password '{pwd}': {'VALID' if is_valid else 'INVALID'}")

if __name__ == "__main__":
    asyncio.run(verify_login())
