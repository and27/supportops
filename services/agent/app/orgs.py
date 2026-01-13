import logging
import os
from typing import Any

from fastapi import HTTPException, Request
from supabase import Client

from .auth_utils import auth_enabled, get_auth_user
from .logging_utils import log_event

_default_org_id: str | None = None


def load_memberships(supabase: Client, user_id: str) -> list[dict[str, Any]]:
    try:
        result = (
            supabase.table("members")
            .select("org_id, role")
            .eq("user_id", user_id)
            .execute()
        )
    except Exception as exc:
        log_event(logging.ERROR, "db_error", error=str(exc), user_id=user_id)
        raise HTTPException(status_code=500, detail="db_error")
    return result.data or []


def get_member_role(supabase: Client, org_id: str, user_id: str) -> str:
    memberships = load_memberships(supabase, user_id)
    for membership in memberships:
        if membership.get("org_id") == org_id:
            return membership.get("role") or "viewer"
    raise HTTPException(status_code=403, detail="org_forbidden")


def ensure_write_access(
    request: Request,
    supabase: Client,
    org_id: str,
    user_id: str | None,
) -> None:
    if auth_enabled():
        if not user_id:
            raise HTTPException(status_code=401, detail="auth_required")
        role = get_member_role(supabase, org_id, user_id)
        if role == "viewer":
            raise HTTPException(status_code=403, detail="forbidden")
        return
    role = request.headers.get("x-org-role", "").lower()
    if role == "viewer":
        raise HTTPException(status_code=403, detail="forbidden")


def ensure_admin_access(supabase: Client, org_id: str, user_id: str | None) -> None:
    if not auth_enabled():
        return
    if not user_id:
        raise HTTPException(status_code=401, detail="auth_required")
    role = get_member_role(supabase, org_id, user_id)
    if role != "admin":
        raise HTTPException(status_code=403, detail="forbidden")


def get_default_org_id(supabase: Client) -> str:
    global _default_org_id
    if _default_org_id:
        return _default_org_id
    slug = os.getenv("DEFAULT_ORG_SLUG", "default")
    try:
        result = (
            supabase.table("orgs").select("id").eq("slug", slug).limit(1).execute()
        )
    except Exception as exc:
        log_event(logging.ERROR, "db_error", error=str(exc), org_slug=slug)
        raise HTTPException(status_code=500, detail="db_error")
    if not result.data:
        log_event(logging.ERROR, "default_org_missing", org_slug=slug)
        raise HTTPException(status_code=500, detail="default_org_missing")
    _default_org_id = result.data[0]["id"]
    return _default_org_id


def resolve_org_id(
    supabase: Client,
    request: Request | None = None,
    payload_org_id: str | None = None,
    user_id: str | None = None,
) -> str:
    org_id = payload_org_id
    if request is not None:
        org_id = org_id or request.headers.get("x-org-id")
        org_id = org_id or request.query_params.get("org_id")
    if auth_enabled():
        if not user_id:
            raise HTTPException(status_code=401, detail="auth_required")
        memberships = load_memberships(supabase, user_id)
        org_ids = [
            member.get("org_id") for member in memberships if member.get("org_id")
        ]
        if not org_ids:
            raise HTTPException(status_code=403, detail="org_forbidden")
        if org_id:
            if org_id not in org_ids:
                raise HTTPException(status_code=403, detail="org_forbidden")
            return org_id
        if len(org_ids) == 1:
            return org_ids[0]
        raise HTTPException(status_code=400, detail="org_required")
    if org_id:
        return org_id
    return get_default_org_id(supabase)


def resolve_org_context(
    supabase: Client,
    request: Request,
    payload_org_id: str | None = None,
) -> tuple[str, str | None]:
    user_id = get_auth_user(request)
    org_id = resolve_org_id(supabase, request, payload_org_id, user_id)
    return org_id, user_id
