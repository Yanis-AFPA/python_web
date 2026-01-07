from typing import List
from fastapi import Depends, HTTPException
from app.models.user import User, UserRole
from app.core.deps import get_current_active_user

class RoleChecker:
    def __init__(self, allowed_roles: List[UserRole]):
        self.allowed_roles = allowed_roles

    def __call__(self, user: User = Depends(get_current_active_user)):
        if user.role not in self.allowed_roles:
            raise HTTPException(status_code=403, detail="Operation not permitted")
        return user
