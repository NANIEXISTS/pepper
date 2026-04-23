from __future__ import annotations

from dataclasses import dataclass
import secrets
from typing import Callable

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from ..logging_config import get_logger
from ..persistence import TradeAuditStore
from ..settings import AuthSettings

logger = get_logger(__name__)

_ROLE_ORDER = {"viewer": 0, "trader": 1, "admin": 2}


@dataclass(slots=True)
class AuthenticatedOperator:
    username: str
    role: str


@dataclass(slots=True)
class OperatorAuthDependencies:
    require_viewer: Callable
    require_trader: Callable
    require_admin: Callable


def build_operator_auth(settings: AuthSettings, audit_store: TradeAuditStore) -> OperatorAuthDependencies:
    security = HTTPBasic(auto_error=False, realm=settings.realm)
    accounts = {account.username: account for account in settings.operators}

    if settings.enabled and not accounts:
        raise ValueError("Authentication is enabled but no operator accounts are configured.")

    async def authenticate(credentials: HTTPBasicCredentials | None = Depends(security)) -> AuthenticatedOperator:
        if not settings.enabled:
            return AuthenticatedOperator(username="local-dev", role="admin")

        if credentials is None:
            await _record_auth_event(
                audit_store,
                username="anonymous",
                role="anonymous",
                outcome="rejected",
                reason="missing_credentials",
            )
            raise _unauthorized(settings.realm, "Authentication required.")

        account = accounts.get(credentials.username)
        if account is None or not secrets.compare_digest(account.password, credentials.password):
            await _record_auth_event(
                audit_store,
                username=credentials.username or "anonymous",
                role="unknown",
                outcome="rejected",
                reason="invalid_credentials",
            )
            raise _unauthorized(settings.realm, "Invalid operator credentials.")

        return AuthenticatedOperator(username=account.username, role=account.role)

    def require_role(required_role: str) -> Callable:
        async def dependency(operator: AuthenticatedOperator = Depends(authenticate)) -> AuthenticatedOperator:
            if _ROLE_ORDER[operator.role] < _ROLE_ORDER[required_role]:
                await audit_store.record_operator_action(
                    username=operator.username,
                    role=operator.role,
                    action="authorize",
                    resource=required_role,
                    outcome="forbidden",
                    details={"required_role": required_role},
                )
                logger.warning(
                    "operator_authorization_forbidden",
                    username=operator.username,
                    role=operator.role,
                    required_role=required_role,
                )
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"{required_role.title()} role required.",
                )
            return operator

        return dependency

    return OperatorAuthDependencies(
        require_viewer=require_role("viewer"),
        require_trader=require_role("trader"),
        require_admin=require_role("admin"),
    )


def _unauthorized(realm: str, detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": f'Basic realm="{realm}"'},
    )


async def _record_auth_event(
    audit_store: TradeAuditStore,
    *,
    username: str,
    role: str,
    outcome: str,
    reason: str,
) -> None:
    await audit_store.record_operator_action(
        username=username,
        role=role,
        action="authenticate",
        resource="basic-auth",
        outcome=outcome,
        details={"reason": reason},
    )
    logger.warning(
        "operator_auth_event",
        username=username,
        role=role,
        outcome=outcome,
        reason=reason,
    )
