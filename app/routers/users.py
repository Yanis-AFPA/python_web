from typing import List, Any
from fastapi import APIRouter, Body, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.db.session import get_db
from app.models.user import User, UserRole
from app.schemas.user import UserCreate, UserResponse
from app.core.deps import get_current_active_user, get_current_user
from app.core import security
from app.core.rbac import RoleChecker

router = APIRouter()

# Permissions
allow_any_auth = RoleChecker([UserRole.SUPER_ADMIN, UserRole.ADMIN, UserRole.MANAGER, UserRole.USER])
allow_admin_super = RoleChecker([UserRole.SUPER_ADMIN, UserRole.ADMIN])
allow_super_only = RoleChecker([UserRole.SUPER_ADMIN])

# Schemas locally or moving to schemas if preferred
class UserUpdate(BaseModel):
    email: EmailStr | None = None
    password: str | None = None
    is_active: bool | None = None
    first_name: str | None = None
    last_name: str | None = None

class UserRoleUpdate(BaseModel):
    role: UserRole

class PasswordChange(BaseModel):
    current_password: str
    new_password: str

@router.get("/", response_model=List[UserResponse])
async def read_users(
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(allow_admin_super)
):
    result = await db.execute(select(User).offset(skip).limit(limit))
    return result.scalars().all()

@router.post("/", response_model=UserResponse)
async def create_user(
    user_in: UserCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(allow_admin_super)
):
    # Only Admin+ can create users
    # Regular Admin cannot create Super Admins
    if user_in.role == UserRole.SUPER_ADMIN and current_user.role != UserRole.SUPER_ADMIN:
        raise HTTPException(status_code=403, detail="Only Super Admin can create other Super Admins")

    result = await db.execute(select(User).where(User.email == user_in.email))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Email already registered")

    user = User(
        email=user_in.email,
        hashed_password=security.get_password_hash(user_in.password),
        role=user_in.role,
        is_active=True,
        first_name=user_in.first_name,
        last_name=user_in.last_name
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user

@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(allow_admin_super)
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
        
    if user.id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot delete yourself")
        
    # Standard Admin cannot delete Super Admin
    if user.role == UserRole.SUPER_ADMIN and current_user.role != UserRole.SUPER_ADMIN:
        raise HTTPException(status_code=403, detail="Cannot delete Super Admin")
        
    await db.delete(user)
    await db.commit()

# Update Role (Super Admin Only)
@router.put("/{user_id}/role", response_model=UserResponse)
async def update_user_role(
    user_id: int,
    role_update: UserRoleUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(allow_super_only) # SUPER ADMIN ONLY
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
        
    user.role = role_update.role
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user

# Change Own Password
@router.put("/me/password")
async def change_password(
    password_data: PasswordChange,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    if not security.verify_password(password_data.current_password, current_user.hashed_password):
        raise HTTPException(status_code=400, detail="Incorrect current password")
        
    current_user.hashed_password = security.get_password_hash(password_data.new_password)
    db.add(current_user)
    await db.commit()
    return {"msg": "Password updated successfully"}

# Update Own Profile (Name)
@router.put("/me/profile", response_model=UserResponse)
async def update_profile(
    user_update: UserUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    if user_update.first_name is not None:
        current_user.first_name = user_update.first_name
    if user_update.last_name is not None:
        current_user.last_name = user_update.last_name
    
    db.add(current_user)
    await db.commit()
    await db.refresh(current_user)
    return current_user
