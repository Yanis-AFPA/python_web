from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.user import User, UserRole
from app.core import security

async def init_db(db: AsyncSession) -> None:
    # Check if admin exists
    result = await db.execute(select(User).where(User.email == "admin@example.com"))
    user = result.scalar_one_or_none()
    
    if not user:
        user = User(
            email="admin@example.com",
            hashed_password=security.get_password_hash("P@ssw0rd"),
            role=UserRole.ADMIN,
            is_active=True,
        )
        db.add(user)
        await db.commit()
        print("--- Default Admin Created (admin@example.com / P@ssw0rd) ---")
    else:
        print("--- Default Admin already exists ---")
