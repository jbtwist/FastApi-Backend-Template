from typing import Literal

from pydantic import BaseModel, Field


class OAuthProvidersOut(BaseModel):
    providers: list[str]


class OAuthStartIn(BaseModel):
    redirect_target: str | None = Field(default=None, max_length=2048)


class OAuthStartOut(BaseModel):
    state: str
    nonce: str
    expires_in: int


class OAuthNativeIn(BaseModel):
    state: str = Field(min_length=1, max_length=256)
    assertion: str = Field(min_length=1, max_length=16384)


class OAuthLinkPendingOut(BaseModel):
    status: Literal["link_email_sent"] = "link_email_sent"


class OAuthLinkConfirmIn(BaseModel):
    token: str = Field(min_length=1, max_length=256)
