"""FastAPI authentication dependencies."""
from typing import Optional
from fastapi import Depends, Header, HTTPException, Request, status
import jwt
from app.auth.jwt import SupabaseJWTVerifier, get_jwt_verifier
from app.auth.supabase import SupabaseClient, get_supabase_client
from app.core.config import get_settings


class AuthUser:
    """Authenticated user with membership info."""

    def __init__(self, user_id: str, org_id: str, roles: list[str]):
        self.user_id = user_id
        self.org_id = org_id
        self.roles = roles

    def has_role(self, role: str) -> bool:
        return role in self.roles


async def get_current_user(
    request: Request,
    authorization: Optional[str] = Header(None),
    jwt_verifier: "SupabaseJWTVerifier" = Depends(get_jwt_verifier),
    supabase_client: "SupabaseClient" = Depends(get_supabase_client),
) -> AuthUser:
    """Extract and verify the current user from the JWT token."""
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": {"code": "unauthenticated", "message": "Missing authorization header"}},
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        scheme, token = authorization.split(" ", 1)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": {"code": "unauthenticated", "message": "Invalid authorization header format"}},
            headers={"WWW-Authenticate": "Bearer"},
        )

    if scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": {"code": "unauthenticated", "message": "Invalid authentication scheme"}},
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Verify token and get user ID
    try:
        user_id = jwt_verifier.get_user_id(token)
    except jwt.InvalidTokenError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": {"code": "unauthenticated", "message": f"Invalid token: {str(e)}"}},
            headers={"WWW-Authenticate": "Bearer"},
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": {"code": "unauthenticated", "message": "Token verification failed"}},
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Get user's memberships
    memberships = supabase_client.get_user_memberships(user_id)
    if not memberships:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": {"code": "forbidden", "message": "User is not a member of any organization"}},
        )

    # If user has multiple memberships, we need to determine which org to use
    # For now, if single membership, use it. If multiple, we'll handle in endpoints.
    if len(memberships) == 1:
        membership = memberships[0]
        return AuthUser(
            user_id=user_id,
            org_id=membership["org_id"],
            roles=membership.get("roles", []),
        )
    else:
        # Multiple memberships - store in request state for endpoints to handle
        request.state.user_id = user_id
        request.state.memberships = memberships
        # Return a temporary user without org_id; endpoints will validate
        return AuthUser(
            user_id=user_id,
            org_id="",
            roles=[],
        )


async def get_current_user_single_org(
    request: Request,
    user: AuthUser = Depends(get_current_user),
) -> AuthUser:
    """Dependency that requires user to have exactly one organization membership."""
    if not user.org_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": {
                    "code": "validation_error",
                    "reason": "multiple_memberships",
                    "message": "User belongs to multiple organizations; operation requires single organization context",
                }
            },
        )
    return user


def require_role(user: AuthUser, role: str) -> AuthUser:
    """Check if user has the required role."""
    if not user.has_role(role):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": {"code": "forbidden", "message": f"Requires role: {role}"}},
        )
    return user


def require_creator(user: AuthUser = Depends(get_current_user_single_org)) -> AuthUser:
    """Require creator role."""
    return require_role(user, "creator")


def require_manager(user: AuthUser = Depends(get_current_user_single_org)) -> AuthUser:
    """Require manager role."""
    return require_role(user, "manager")


def require_owner(user: AuthUser = Depends(get_current_user_single_org)) -> AuthUser:
    """Require owner role."""
    return require_role(user, "owner")


def require_reviewer(user: AuthUser = Depends(get_current_user_single_org)) -> AuthUser:
    """Require reviewer role."""
    return require_role(user, "reviewer")


def require_creator_or_owner(user: AuthUser = Depends(get_current_user_single_org)) -> AuthUser:
    """Require creator or owner role."""
    if not user.has_role("creator") and not user.has_role("owner"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": {"code": "forbidden", "message": "Requires creator or owner role"}},
        )
    return user


async def get_request_id(request: Request) -> str:
    """Get or generate request ID."""
    return getattr(request.state, "request_id", "")