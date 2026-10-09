"""FastAPI dependencies: launch secret, DB session, current user."""

import hmac
from typing import Iterator, Optional

from fastapi import Depends, Header, Request
from sqlalchemy.orm import Session

from api.errors import ApiError
from api.services import Services

SECRET_HEADER = "X-Launch-Secret"


def require_launch_secret(request: Request, x_launch_secret: Optional[str] = Header(default=None)) -> None:
    """Only the process that started the sidecar knows the secret, so other
    local programs cannot call the API. Checked before anything else."""
    expected: str = request.app.state.launch_secret
    if x_launch_secret is None or not hmac.compare_digest(x_launch_secret.encode(), expected.encode()):
        raise ApiError(403, "launch_secret_invalid", "Missing or wrong launch secret.")


def get_db(request: Request) -> Iterator[Session]:
    db = request.app.state.session_factory()
    try:
        yield db
    finally:
        db.close()


def get_services(request: Request, db: Session = Depends(get_db)) -> Services:
    return Services(db, request.app.state.session_timeout_hours)


def bearer_token(authorization: Optional[str] = Header(default=None)) -> str:
    scheme, _, token = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise ApiError(401, "not_authenticated", "Please sign in.")
    return token.strip()


class CurrentUser:
    """The signed-in user, resolved by AuthService.validate_session."""

    def __init__(self, user, token: str):
        self.id: str = user.id
        self.token = token
        self.user = user


def _resolve(services: Services, token: str) -> CurrentUser:
    user = services.auth.validate_session(token)  # raises SessionExpiredError -> 401
    if user is None or not user.is_active:
        raise ApiError(401, "session_expired", "Your session has ended. Please sign in again.")
    return CurrentUser(user, token)


def current_user_allow_pending(
    token: str = Depends(bearer_token), services: Services = Depends(get_services)
) -> CurrentUser:
    """Signed in - even if the account still has to rotate its password."""
    return _resolve(services, token)


def current_user(user: CurrentUser = Depends(current_user_allow_pending)) -> CurrentUser:
    """Signed in AND past the forced password change. Qt blocks the main
    window behind that dialog; the API enforces the same thing server-side."""
    if user.user.must_change_password:
        raise ApiError(403, "password_change_required", "You must change your password before continuing.")
    return user
