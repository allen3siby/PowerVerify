from typing import List, Optional
from fastapi import Header, HTTPException, Depends

VALID_ROLES = ["ADMIN", "VERIFICATION_OFFICER", "AUDITOR"]

class UserContext:
    def __init__(self, user_id: str, role: str):
        self.user_id = user_id
        self.role = role.upper()

def get_current_user(
    x_user_id: Optional[str] = Header(None, alias="X-User-Id"),
    x_user_role: Optional[str] = Header(None, alias="X-User-Role"),
) -> UserContext:
    """
    Extracts authenticated user context from request headers with safe academic defaults.
    In production environments, this integrates with enterprise OAuth2 / JWT / SSO tokens.
    """
    user_id = x_user_id.strip() if x_user_id and x_user_id.strip() else "officer.sharma"
    role = x_user_role.strip().upper() if x_user_role and x_user_role.strip() else "VERIFICATION_OFFICER"

    if role not in VALID_ROLES:
        role = "VERIFICATION_OFFICER"

    return UserContext(user_id=user_id, role=role)

def require_role(allowed_roles: List[str]):
    """
    Role-based permission dependency.
    Restricts sensitive operations (status change, assignment, decisions) to authorized roles.
    Auditor has strictly read-only access.
    """
    def dependency(user: UserContext = Depends(get_current_user)) -> UserContext:
        if user.role not in [r.upper() for r in allowed_roles]:
            raise HTTPException(
                status_code=403,
                detail=f"Access Denied: Role '{user.role}' lacks authorization. Required role(s): {allowed_roles}."
            )
        return user
    return dependency
