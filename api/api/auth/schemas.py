from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    # The sign-up form's "I agree to the Terms and Privacy notice" box.
    accept_terms: bool = False


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class RefreshIn(BaseModel):
    refresh_token: str = Field(min_length=1)


class LogoutIn(RefreshIn):
    # This browser's push subscription, removed with the session.
    push_endpoint: str | None = Field(default=None, max_length=2000)


class ChangePasswordIn(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)


class DeleteAccountIn(BaseModel):
    """Password, or for accounts without one, the account email."""

    password: str = Field(min_length=1, max_length=320)


class UserOut(BaseModel):
    id: str
    email: str
    created_at: datetime
    display_name: str | None = None
    # Public, unguessable, immutable URL; null when no picture is set.
    avatar_url: str | None = None
    email_verified: bool = False
    # False for accounts created through a sign-in provider only.
    has_password: bool = True
    # The plan in effect (Beta while plans don't apply), and whether the
    # account still has to pick one (onboarding's plan step).
    plan: str = "beta"
    needs_plan: bool = False
    # Unset model choices use the account's default own model, not Auto.
    prefer_own_model: bool = False
    # Gradis makes changes without asking first.
    agent_full_access: bool = False


class OAuthStartIn(BaseModel):
    next: str = Field(default="/", max_length=500)


class OAuthCallbackIn(BaseModel):
    code: str = Field(min_length=1, max_length=2000)
    state: str = Field(min_length=1, max_length=4000)


class OAuthLinkIn(BaseModel):
    link_token: str = Field(min_length=1, max_length=4000)
    password: str = Field(min_length=1, max_length=128)


class ForgotPasswordIn(BaseModel):
    email: EmailStr


class ResetPasswordIn(BaseModel):
    token: str = Field(min_length=10, max_length=200)
    new_password: str = Field(min_length=8, max_length=128)


class VerifyEmailIn(BaseModel):
    token: str = Field(min_length=10, max_length=200)


class ProfileUpdate(BaseModel):
    """Empty or whitespace clears the name (identity falls back to email)."""

    display_name: str | None = Field(default=None, max_length=200)
    # Omitted leaves the model preference as it is.
    prefer_own_model: bool | None = None
    agent_full_access: bool | None = None


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
