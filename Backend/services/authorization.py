"""
authorization.py — Enterprise Policy & Authorization Layer
===========================================================
Row/document tenancy + RBAC for all Praecantator data access.

Enforces:
  1. Tenant isolation: users can ONLY read/write their own tenant's data.
  2. Role-based access: ADMIN can approve incidents, VIEWER can only read.
  3. Operation-level policy: what roles can call each endpoint.
  4. Immutable audit-log writes: no role can delete or modify audit records.

Design:
  - Stateless: every request carries JWT claims → principal is extracted at the edge.
  - No database hits for policy checks (all logic is in-memory policy tables).
  - Soft-reject: returns AuthError (no exceptions for business logic), callers handle.

Integration:
  - FastAPI dependency: `Depends(require_permission("incident:approve"))`
  - Standalone: `auth.check(principal, "incident:approve", resource_tenant="t-123")`
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum
from typing import Any

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

# ── Role definitions ──────────────────────────────────────────────────────────


class Role(str, Enum):
    ADMIN = "admin"         # Full access: approve, dismiss, configure
    ANALYST = "analyst"     # Read + annotate incidents; cannot approve
    VIEWER = "viewer"       # Read-only: view incidents, signals, graph
    SERVICE = "service"     # Internal service account: pipeline writes
    SUPERADMIN = "superadmin"  # Cross-tenant admin (Praecantator ops only)


# ── Permission catalog ─────────────────────────────────────────────────────────

class Permission(str, Enum):
    # Incidents
    INCIDENT_READ = "incident:read"
    INCIDENT_APPROVE = "incident:approve"
    INCIDENT_DISMISS = "incident:dismiss"

    # Graph / network
    GRAPH_READ = "graph:read"
    GRAPH_WRITE = "graph:write"

    # Signals
    SIGNAL_READ = "signal:read"
    SIGNAL_WRITE = "signal:write"

    # Workflow
    WORKFLOW_READ = "workflow:read"
    WORKFLOW_TRIGGER = "workflow:trigger"

    # Configuration
    CONFIG_READ = "config:read"
    CONFIG_WRITE = "config:write"

    # Audit — NOBODY can delete, only read
    AUDIT_READ = "audit:read"

    # Admin cross-tenant
    TENANT_MANAGE = "tenant:manage"


# Role → Permission mapping
ROLE_PERMISSIONS: dict[Role, set[Permission]] = {
    Role.SUPERADMIN: set(Permission),  # all permissions
    Role.ADMIN: {
        Permission.INCIDENT_READ, Permission.INCIDENT_APPROVE, Permission.INCIDENT_DISMISS,
        Permission.GRAPH_READ, Permission.GRAPH_WRITE,
        Permission.SIGNAL_READ, Permission.SIGNAL_WRITE,
        Permission.WORKFLOW_READ, Permission.WORKFLOW_TRIGGER,
        Permission.CONFIG_READ, Permission.CONFIG_WRITE,
        Permission.AUDIT_READ,
    },
    Role.ANALYST: {
        Permission.INCIDENT_READ, Permission.INCIDENT_DISMISS,
        Permission.GRAPH_READ,
        Permission.SIGNAL_READ,
        Permission.WORKFLOW_READ,
        Permission.CONFIG_READ,
        Permission.AUDIT_READ,
    },
    Role.VIEWER: {
        Permission.INCIDENT_READ,
        Permission.GRAPH_READ,
        Permission.SIGNAL_READ,
        Permission.WORKFLOW_READ,
        Permission.AUDIT_READ,
    },
    Role.SERVICE: {
        Permission.INCIDENT_READ, Permission.INCIDENT_APPROVE, Permission.INCIDENT_DISMISS,
        Permission.GRAPH_READ, Permission.GRAPH_WRITE,
        Permission.SIGNAL_READ, Permission.SIGNAL_WRITE,
        Permission.WORKFLOW_READ, Permission.WORKFLOW_TRIGGER,
        Permission.AUDIT_READ,
    },
}


# ── Principal ─────────────────────────────────────────────────────────────────


@dataclass
class Principal:
    """Authenticated identity extracted from JWT or API key."""
    user_id: str
    tenant_id: str
    role: Role
    email: str = ""
    is_service_account: bool = False


# ── Auth error ────────────────────────────────────────────────────────────────


class AuthError(Exception):
    """Authorization failure — not an HTTP exception directly."""
    def __init__(self, message: str, code: str = "UNAUTHORIZED") -> None:
        super().__init__(message)
        self.code = code


# ── Core policy engine ────────────────────────────────────────────────────────


class PolicyEngine:
    """
    Stateless policy evaluator. Every check is a pure function.
    No database lookups — JWT claims carry all needed context.
    """

    def check(
        self,
        principal: Principal,
        permission: Permission | str,
        resource_tenant_id: str | None = None,
    ) -> bool:
        """
        Returns True if the principal may perform the given permission
        on a resource belonging to resource_tenant_id.

        Tenant isolation rule:
          - SUPERADMIN can cross tenants.
          - All other roles must match tenant exactly.
        """
        perm = Permission(permission) if isinstance(permission, str) else permission

        # Tenant isolation check (skip for SUPERADMIN)
        if principal.role != Role.SUPERADMIN and resource_tenant_id is not None:
            if principal.tenant_id != resource_tenant_id:
                return False

        # Role-permission check
        allowed = ROLE_PERMISSIONS.get(principal.role, set())
        return perm in allowed

    def require(
        self,
        principal: Principal,
        permission: Permission | str,
        resource_tenant_id: str | None = None,
    ) -> None:
        """Raise AuthError if the principal does not have the permission."""
        if not self.check(principal, permission, resource_tenant_id):
            raise AuthError(
                f"Principal '{principal.user_id}' (role={principal.role}, tenant={principal.tenant_id}) "
                f"lacks permission '{permission}' on tenant '{resource_tenant_id}'.",
                code="FORBIDDEN",
            )

    def filter_to_tenant(
        self,
        principal: Principal,
        items: list[dict],
        tenant_key: str = "tenant_id",
    ) -> list[dict]:
        """
        Filter a list of dicts to only those belonging to the principal's tenant.
        SUPERADMIN sees all items.
        """
        if principal.role == Role.SUPERADMIN:
            return items
        return [i for i in items if i.get(tenant_key) == principal.tenant_id]


# Global policy engine instance
policy = PolicyEngine()


# ── JWT / token extraction ────────────────────────────────────────────────────

_bearer_scheme = HTTPBearer(auto_error=False)


def _decode_local_jwt(token: str) -> dict[str, Any]:
    """Decode JWT using local secret (dev fallback). Swap for Firebase verify in prod."""
    import jwt as pyjwt

    secret = os.getenv("JWT_SECRET", "dev-secret-change-in-production")
    try:
        return pyjwt.decode(token, secret, algorithms=["HS256"])
    except Exception as exc:
        raise AuthError(f"Invalid token: {exc}", code="INVALID_TOKEN")


def _decode_firebase_jwt(token: str) -> dict[str, Any]:
    """Verify Firebase ID token (production path)."""
    try:
        import firebase_admin.auth as fb_auth  # type: ignore
        decoded = fb_auth.verify_id_token(token)
        return decoded
    except Exception as exc:
        raise AuthError(f"Firebase auth failed: {exc}", code="INVALID_TOKEN")


def extract_principal(token: str) -> Principal:
    """
    Extract a Principal from a bearer token.
    Uses Firebase in production (AUTH_PROVIDER=firebase) or local JWT in dev.
    """
    auth_provider = os.getenv("AUTH_PROVIDER", "local")

    if auth_provider == "firebase":
        claims = _decode_firebase_jwt(token)
    else:
        claims = _decode_local_jwt(token)

    return Principal(
        user_id=str(claims.get("sub", claims.get("uid", ""))),
        tenant_id=str(claims.get("tenant_id", claims.get("org_id", "demo-tenant"))),
        role=Role(claims.get("role", Role.ADMIN.value)),
        email=str(claims.get("email", "")),
        is_service_account=bool(claims.get("service_account", False)),
    )


# ── FastAPI dependencies ──────────────────────────────────────────────────────


async def get_current_principal(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> Principal:
    """
    FastAPI dependency: extract and validate the current user.

    Usage:
        @app.get("/incidents")
        async def list_incidents(principal: Principal = Depends(get_current_principal)):
            ...
    """
    if creds is None:
        # Development fallback: anonymous principal with full access
        if os.getenv("AUTH_PROVIDER", "local") == "local" and os.getenv("AUTH_OPTIONAL", "true") == "true":
            return Principal(
                user_id="local-dev-user",
                tenant_id=os.getenv("DEV_TENANT_ID", "demo-tenant"),
                role=Role.ADMIN,
                email="dev@local",
            )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing token")

    try:
        return extract_principal(creds.credentials)
    except AuthError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))


def require_permission(permission: Permission | str):
    """
    FastAPI dependency factory.

    Usage:
        @app.post("/incidents/{id}/approve")
        async def approve(
            id: str,
            principal: Principal = Depends(require_permission(Permission.INCIDENT_APPROVE))
        ):
            ...
    """
    async def _dep(principal: Principal = Depends(get_current_principal)) -> Principal:
        try:
            policy.require(principal, permission)
        except AuthError as e:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
        return principal

    return _dep


def require_tenant_permission(permission: Permission | str, tenant_param: str = "tenant_id"):
    """
    Like require_permission but also checks that the principal's tenant
    matches the resource tenant in the path/query param.

    Usage:
        @app.get("/tenants/{tenant_id}/incidents")
        async def list(
            tenant_id: str,
            principal = Depends(require_tenant_permission(Permission.INCIDENT_READ))
        ):
            ...
    """
    from fastapi import Request

    async def _dep(request: Request, principal: Principal = Depends(get_current_principal)) -> Principal:
        resource_tenant = (
            request.path_params.get(tenant_param)
            or request.query_params.get(tenant_param)
        )
        try:
            policy.require(principal, permission, resource_tenant_id=resource_tenant)
        except AuthError as e:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
        return principal

    return _dep


# ── Helper: tenant-scoped resource guard ─────────────────────────────────────


def guard_resource_tenant(principal: Principal, resource: dict, tenant_key: str = "tenant_id") -> None:
    """
    Inline guard — verify that a fetched resource belongs to the principal's tenant.
    Raise 403 if not. SUPERADMIN always passes.

    Usage in endpoint:
        incident = get_incident(incident_id)
        guard_resource_tenant(principal, incident)
    """
    if principal.role == Role.SUPERADMIN:
        return
    resource_tenant = resource.get(tenant_key, "")
    if resource_tenant and resource_tenant != principal.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Resource belongs to tenant '{resource_tenant}', not '{principal.tenant_id}'.",
        )
